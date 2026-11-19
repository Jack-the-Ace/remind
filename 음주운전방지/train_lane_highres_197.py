"""기존 사전학습 설정으로 640×400 차선 모델을 5회전 학습하고 검증합니다."""

import argparse
import hashlib
import json
from copy import deepcopy
from pathlib import Path
from time import perf_counter

import cv2
import numpy as np
import torch
from torch.utils.data import DataLoader

from compare_lane_transfer_197 import checkpoint, lane_metrics, load_backbone
from diagnose_lane_batchnorm_197 import assert_same_parameters
from split_lane_masks_197 import read_csv
from train_lane_197 import BATCH_SIZE, fit_epoch, prepare, update_batchnorm, validation
from train_lane_smoke_197 import IMAGE_SIZE, LEARNING_RATE, POSITIVE_WEIGHT, THRESHOLD, emit, new_model


HIGH_SIZE = (640, 400)
EPOCHS = 5
SEED = 197


def read_model(path, size, device):
    state = torch.load(path, map_location=device, weights_only=True)
    if (tuple(state["image_size"]) != size or state["normalization"] != "RGB / 127.5 - 1"
            or state["threshold"] != THRESHOLD or state["batchnorm"] != "recalibrated"):
        raise ValueError(f"체크포인트 조건 불일치: {path}")
    model = new_model(device)
    model.load_state_dict(state["model_state_dict"])
    return model.eval()


def match_grid(mask, size):
    # 각 모델에서 0.5로 이진화한 뒤 최근접 보간으로 공통 평가 좌표에 맞춥니다.
    if mask.shape[-2:] == size[::-1]:
        return mask
    resized = [cv2.resize(image[0].numpy().astype(np.uint8), size, interpolation=cv2.INTER_NEAREST_EXACT)
               for image in mask]
    return torch.from_numpy(np.stack(resized)).unsqueeze(1).bool()


def common_grid_metrics(name, mask, truth, size, tolerance):
    aligned = match_grid(mask, size)
    valid = truth.bool()
    intersection = (aligned & valid).sum().item()
    union = (aligned | valid).sum().item()
    return {
        "model": name, "evaluation_size": size, "centerline_tolerance_px": tolerance,
        "lane_iou": intersection / union,
        "black_images": (~aligned.flatten(1).any(dim=1)).sum().item(),
        **lane_metrics(aligned, valid, tolerance),
    }


def run(args, log):
    device = torch.device("cuda:0")
    torch.manual_seed(SEED)
    torch.set_num_threads(min(torch.get_num_threads(), 4))
    cv2.setNumThreads(2)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    train, val = (read_csv(args.splits / f"{name}.csv") for name in ("train", "val"))
    if (len(train), len(val)) != (960, 120) or {r["provisional_group"] for r in train} & {
        r["provisional_group"] for r in val
    }:
        raise ValueError("학습·검증 분할을 확인하세요.")
    emit(log, event="configuration", split_status="provisional", gpu=torch.cuda.get_device_name(device),
         image_size=HIGH_SIZE, epochs=EPOCHS, train_pairs=len(train), val_pairs=len(val), seed=SEED,
         batch_size=args.batch_size, learning_rate=LEARNING_RATE, optimizer="AdamW",
         normalization="RGB / 127.5 - 1", loss="BCEWithLogits + soft Dice", positive_weight=POSITIVE_WEIGHT,
         threshold=THRESHOLD)
    model = new_model(device)
    head_hash = hashlib.sha256(b"".join(p.cpu().numpy().tobytes() for p in model.classifier.state_dict().values()))
    digest, count = load_backbone(args.weights, model)
    emit(log, event="initialization", matched_backbone_tensors=count, imagenet_v1_sha256=digest,
         head_sha256=head_hash.hexdigest())
    train_data, val_data = prepare(train, HIGH_SIZE), prepare(val, HIGH_SIZE)
    emit(log, event="preprocessing_verified", pairs=len(train) + len(val))
    train_batches = DataLoader(train_data, batch_size=args.batch_size, pin_memory=True, shuffle=True,
                               generator=torch.Generator().manual_seed(SEED))
    val_batches = DataLoader(val_data, batch_size=args.batch_size)
    optimizer = torch.optim.AdamW(model.parameters(), lr=LEARNING_RATE)
    torch.cuda.reset_peak_memory_stats(device)
    for epoch in range(1, EPOCHS + 1):
        start = perf_counter()
        loss, iou = fit_epoch(model, train_batches, optimizer, device)
        stats, _ = validation(model, val_batches, device)
        emit(log, event="epoch", epoch=epoch, train_loss=loss, train_lane_iou=iou,
             elapsed_seconds=perf_counter()-start, **stats)
    checkpoint(model, args.output, "imagenet_v1_640x400_as_trained", EPOCHS, SEED, "imagenet_v1",
               "as_trained", HIGH_SIZE)

    # 학습 사진만 한 번 통과시킵니다. 검증 사진과 가중치 업데이트는 사용하지 않습니다.
    recalibrated = deepcopy(model)
    calibration_batches = DataLoader(train_data, batch_size=args.batch_size, pin_memory=True, shuffle=True,
                                     generator=torch.Generator().manual_seed(SEED + 1))
    layers = update_batchnorm(recalibrated, calibration_batches, device)
    assert_same_parameters(model, recalibrated)
    name = "imagenet_v1_640x400_recalibrated"
    checkpoint(recalibrated, args.output, name, EPOCHS, SEED, "imagenet_v1", "recalibrated", HIGH_SIZE)
    emit(log, event="batchnorm_calibration", pairs=len(train_data), batches=len(calibration_batches), layers=layers,
         weights_identical=True, gpu_peak_allocated_mib=torch.cuda.max_memory_allocated(device)/2**20)
    del model, recalibrated, optimizer, train_batches, calibration_batches, train_data

    high = read_model(args.output / f"{name}.pt", HIGH_SIZE, device)
    high_native, high_mask = validation(high, val_batches, device)
    base = read_model(args.baseline, IMAGE_SIZE, device)
    low_data = prepare(val, IMAGE_SIZE)
    low_native, low_mask = validation(base, DataLoader(low_data, batch_size=args.batch_size), device)
    result_rows = []
    for size, tolerance, truth in ((HIGH_SIZE, 5, val_data.tensors[1]), (IMAGE_SIZE, 3, low_data.tensors[1])):
        for label, mask, native in (("384x240", low_mask, low_native), ("640x400", high_mask, high_native)):
            result = common_grid_metrics(label, mask, truth, size, tolerance)
            result["native_val_loss"] = native["val_loss"]
            result_rows.append(result)
            emit(log, event="common_grid_evaluation", **result)
    (args.output / "photo_metrics.json").write_text(json.dumps(result_rows, indent=2) + "\n", encoding="utf-8")
    emit(log, event="completed", optimizer_steps=EPOCHS * (len(train) // args.batch_size),
         checkpoint=name + ".pt")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--splits", required=True, type=Path)
    parser.add_argument("--weights", required=True, type=Path)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--batch-size", choices=(4, 8), type=int, default=BATCH_SIZE)
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output / "training.jsonl").open("x", encoding="utf-8") as log:
        run(args, log)


if __name__ == "__main__":
    main()
