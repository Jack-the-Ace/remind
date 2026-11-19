"""AI Hub 197 임시 검증 세트에서 무작위 초기화와 ImageNet 초기화를 비교합니다."""

import argparse
import hashlib
import random
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
import torch
from skimage.morphology import skeletonize
from torch.utils.data import DataLoader
from torchvision.models import MobileNet_V3_Large_Weights

from convert_lane_masks_197 import encode, read_image
from diagnose_lane_batchnorm_197 import assert_same_parameters
from split_lane_masks_197 import read_csv
from train_lane_197 import BATCH_SIZE, fit_epoch, prepare, update_batchnorm, validation
from train_lane_smoke_197 import IMAGE_SIZE, LEARNING_RATE, POSITIVE_WEIGHT, THRESHOLD, emit, new_model


WEIGHTS = MobileNet_V3_Large_Weights.IMAGENET1K_V1
TOLERANCE_PX = 3


def ratio(numerator, denominator):
    return numerator / denominator if denominator else 0.0


def lane_metrics(predictions, targets, tolerance_px=TOLERANCE_PX):
    pred = predictions[:, 0].numpy()
    truth = targets[:, 0].numpy().astype(bool)
    overlap = int(np.count_nonzero(pred & truth))
    pred_area, truth_area = int(pred.sum()), int(truth.sum())
    pred_center_count = truth_center_count = near_truth = near_pred = 0
    for predicted, actual in zip(pred, truth, strict=True):
        # 굵은 마스크를 1픽셀 중심선으로 줄인 뒤 상대 중심선과의 거리를 잽니다.
        gt_line = skeletonize(actual)
        pr_line = skeletonize(predicted)
        pred_center_count += int(pr_line.sum())
        truth_center_count += int(gt_line.sum())
        if pr_line.any() and gt_line.any():
            to_true = cv2.distanceTransform((~gt_line).astype(np.uint8), cv2.DIST_L2, cv2.DIST_MASK_PRECISE)
            to_pred = cv2.distanceTransform((~pr_line).astype(np.uint8), cv2.DIST_L2, cv2.DIST_MASK_PRECISE)
            near_truth += int(np.count_nonzero(to_true[pr_line] <= tolerance_px))
            near_pred += int(np.count_nonzero(to_pred[gt_line] <= tolerance_px))
    center_precision = ratio(near_truth, pred_center_count)
    center_recall = ratio(near_pred, truth_center_count)
    return {
        "pixel_precision": ratio(overlap, pred_area),
        "pixel_recall": ratio(overlap, truth_area),
        f"centerline_precision_at_{tolerance_px}px": center_precision,
        f"centerline_recall_at_{tolerance_px}px": center_recall,
        f"centerline_f1_at_{tolerance_px}px": ratio(2 * center_precision * center_recall, center_precision + center_recall),
        "predicted_area_per_center_pixel": ratio(pred_area, pred_center_count),
        "target_area_per_center_pixel": ratio(truth_area, truth_center_count),
        "target_positive_fraction": truth_area / truth.size,
    }


def report_eval(model, batches, device, targets, log, model_name, bn_mode):
    stats, masks = validation(model, batches, device)
    emit(log, event="final_evaluation", model=model_name, batchnorm=bn_mode, **stats, **lane_metrics(masks, targets))
    return masks


def load_backbone(path, model):
    # 공식 체크포인트의 features만 불러오고 차선 출력층은 그대로 둡니다.
    sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    expected_prefix = Path(WEIGHTS.url).stem.rsplit("-", 1)[-1]
    if not sha256.startswith(expected_prefix):
        raise ValueError(f"공식 ImageNet 체크포인트의 SHA-256 접두사 불일치: {sha256}")
    state = torch.load(path, map_location="cpu", weights_only=True)
    features = {k.removeprefix("features."): v for k, v in state.items() if k.startswith("features.")}
    model.backbone.load_state_dict(features, strict=True)
    loaded = model.backbone.state_dict()
    if any(not torch.equal(tensor, loaded[name].cpu()) for name, tensor in features.items()):
        raise RuntimeError("사전학습 특징 가중치가 원본과 다릅니다.")
    return sha256, len(features)


def checkpoint(model, output, name, epoch, seed, initialization, bn_mode, image_size=IMAGE_SIZE):
    torch.save({
        "model": "deeplabv3_mobilenet_v3_large",
        "model_state_dict": model.state_dict(),
        "epoch": epoch,
        "seed": seed,
        "image_size": image_size,
        "normalization": "RGB / 127.5 - 1",
        "threshold": THRESHOLD,
        "split_status": "provisional",
        "backbone_initialization": initialization,
        "batchnorm": bn_mode,
    }, output / f"{name}.pt")


def fit_model(initialization, args, train_set, val_batches, targets, output, device, log):
    torch.manual_seed(args.seed)
    model = new_model(device)
    # 같은 시드의 분할 헤드와 동일한 배치 순서를 양쪽에서 사용합니다.
    head_digest = hashlib.sha256()
    for tensor in model.classifier.state_dict().values():
        head_digest.update(tensor.detach().cpu().numpy().tobytes())
    if initialization == "imagenet_v1":
        digest, tensors = load_backbone(args.weights, model)
        emit(log, event="pretrained_loaded", model=initialization, weights=str(WEIGHTS), url=WEIGHTS.url,
             sha256=digest, matched_backbone_tensors=tensors)
    emit(log, event="initialization", model=initialization, head_sha256=head_digest.hexdigest())
    train_batches = DataLoader(train_set, batch_size=BATCH_SIZE, pin_memory=True, shuffle=True,
                               generator=torch.Generator().manual_seed(args.seed))
    optimizer = torch.optim.AdamW(model.parameters(), lr=LEARNING_RATE)
    for epoch in range(1, args.epochs + 1):
        train_loss, train_iou = fit_epoch(model, train_batches, optimizer, device)
        stats, _ = validation(model, val_batches, device)
        emit(log, event="epoch", model=initialization, epoch=epoch, train_loss=train_loss, train_iou=train_iou, **stats)

    report_eval(model, val_batches, device, targets, log, initialization, "as_trained")
    checkpoint(model, output, initialization + "_as_trained", args.epochs, args.seed, initialization, "as_trained")
    # 학습 사진 전체로만 BN 통계를 다시 채우고 가중치 일치 여부를 확인합니다.
    recalibrated = new_model(device)
    recalibrated.load_state_dict(model.state_dict())
    calibration = DataLoader(train_set, batch_size=BATCH_SIZE, pin_memory=True, shuffle=True,
                             generator=torch.Generator().manual_seed(args.seed + 1))
    layers = update_batchnorm(recalibrated, calibration, device)
    assert_same_parameters(model, recalibrated)
    emit(log, event="batchnorm_recalibration", model=initialization, pairs=len(train_set), batches=len(calibration),
         layers=layers, identical_weights=True)
    path_name = initialization + "_recalibrated"
    checkpoint(recalibrated, output, path_name, args.epochs, args.seed, initialization, "recalibrated")
    restored = torch.load(output / f"{path_name}.pt", map_location=device, weights_only=True)
    recalibrated.load_state_dict(restored["model_state_dict"])
    masks = report_eval(recalibrated, val_batches, device, targets, log, initialization, "recalibrated")
    return masks


def compare_examples(rows, targets, previous, random_control, transfer, seed, output, log):
    groups = defaultdict(list)
    for index, row in enumerate(rows):
        groups[row["provisional_group"]].append(index)
    rng = random.Random(seed)
    selected = [index for group in sorted(groups) for index in rng.sample(groups[group], 2)]
    for name, baseline, label in (("previous_vs_imagenet", previous, "Previous model"),
                                  ("controlled_comparison", random_control, "Random initialization")):
        folder = output / name
        folder.mkdir()
        for i in selected:
            photo = read_image(Path(rows[i]["jpg"]), cv2.IMREAD_COLOR | cv2.IMREAD_IGNORE_ORIENTATION)
            panels = []
            for title, pixels in (("Original", None), ("Ground truth", targets[i, 0]),
                                  (label, baseline[i, 0]), ("ImageNet backbone", transfer[i, 0])):
                if pixels is None:
                    panel = cv2.resize(photo, (480, 300), interpolation=cv2.INTER_AREA)
                else:
                    enlarged = cv2.resize(pixels.numpy().astype(np.uint8) * 255, (480, 300),
                                          interpolation=cv2.INTER_NEAREST)
                    panel = cv2.cvtColor(enlarged, cv2.COLOR_GRAY2BGR)
                panel = cv2.copyMakeBorder(panel, 30, 0, 0, 0, cv2.BORDER_CONSTANT)
                cv2.putText(panel, title, (10, 21), cv2.FONT_HERSHEY_SIMPLEX, .62, (255, 255, 255), 1, cv2.LINE_AA)
                panels.append(panel)
            path = folder / (Path(rows[i]["jpg"]).stem + "_comparison.jpg")
            path.write_bytes(encode(path, np.hstack(panels)))
    emit(log, event="completed", preview_jpgs=[Path(rows[i]["jpg"]).name for i in selected])


def run(args, output, log):
    if not torch.cuda.is_available():
        raise RuntimeError("RTX 3060 Ti의 CUDA를 사용할 수 없습니다.")
    device = torch.device("cuda")
    torch.set_num_threads(min(torch.get_num_threads(), 4))
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    train, val = (read_csv(args.splits / f"{split}.csv") for split in ("train", "val"))
    if (len(train), len(val)) != (960, 120) or {r["provisional_group"] for r in train} & {
        r["provisional_group"] for r in val
    }:
        raise ValueError("학습 960쌍과 검증 120쌍의 임시 분할을 확인하세요.")
    emit(log, event="configuration", split_status="provisional", epochs=args.epochs, seed=args.seed,
         gpu=torch.cuda.get_device_name(), batch_size=BATCH_SIZE, image_size=IMAGE_SIZE, threshold=THRESHOLD,
         learning_rate=LEARNING_RATE, optimizer="AdamW", positive_weight=POSITIVE_WEIGHT,
         loss="BCEWithLogits + soft Dice", normalization="RGB / 127.5 - 1", tolerance_px=TOLERANCE_PX)
    train_set, val_set = prepare(train), prepare(val)
    val_batches = DataLoader(val_set, batch_size=BATCH_SIZE)
    targets = val_set.tensors[1]
    emit(log, event="data_profile", train_pairs=len(train), val_pairs=len(val),
         training_positive_fraction=train_set.tensors[1].mean().item(), validation_positive_fraction=targets.mean().item())
    old = new_model(device)
    previous_predictions = {}
    for mode, file in (("as_trained", "baseline.pt"), ("recalibrated", "recalibrated.pt")):
        saved = torch.load(args.previous / file, map_location=device, weights_only=True)
        old.load_state_dict(saved["model_state_dict"])
        previous_predictions[mode] = report_eval(old, val_batches, device, targets, log, "previous_random", mode)
    del old, saved
    random_masks = fit_model("random", args, train_set, val_batches, targets, output, device, log)
    transfer_masks = fit_model("imagenet_v1", args, train_set, val_batches, targets, output, device, log)
    compare_examples(val, targets, previous_predictions["recalibrated"], random_masks, transfer_masks, args.seed, output, log)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--splits", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--previous", required=True, type=Path, help="첫 학습 체크포인트 폴더")
    parser.add_argument("--weights", required=True, type=Path, help="공식 MobileNetV3-Large ImageNet V1 파일")
    parser.add_argument("--epochs", type=int, choices=range(5, 11), default=5, metavar="5..10")
    parser.add_argument("--seed", type=int, default=197)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with (output / "comparison.jsonl").open("x", encoding="utf-8") as log:
        run(args, output, log)


if __name__ == "__main__":
    main()
