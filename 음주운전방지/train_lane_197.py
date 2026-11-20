# 029  960쌍으로 차선 모델 학습하기
# 작은 실험에서 확인한 학습 방법을 전체 학습·검증 목록에 적용합니다.
# --splits와 새 --output을 지정합니다. 기본 --epochs는 5입니다.
# 기본·통계 재계산 모델과 training.jsonl을 남겨 사전학습 실험과 비교합니다.

"""AI Hub 197 임시 분할에서 학습하고 BatchNorm 재계산 전후를 검증합니다."""

import argparse
import math
import random
from collections import defaultdict
from copy import deepcopy
from pathlib import Path

import torch
from torch.utils.data import DataLoader, TensorDataset

from diagnose_lane_batchnorm_197 import assert_same_parameters, batchnorms
from split_lane_masks_197 import read_csv
from train_lane_smoke_197 import (
    IMAGE_SIZE, LEARNING_RATE, POSITIVE_WEIGHT, THRESHOLD, emit, evaluate,
    load_samples, loss_fn, new_model, save_preview,
)


BATCH_SIZE = 8


def prepare(rows, size=IMAGE_SIZE):
    # 기존 전처리를 나눠 호출해 중간 텐서가 한꺼번에 메모리에 쌓이지 않게 합니다.
    width, height = size
    images = torch.empty((len(rows), 3, height, width))
    targets = torch.empty((len(rows), 1, height, width))
    for start in range(0, len(rows), 24):
        chunk = rows[start:start + 24]
        data, _ = load_samples(chunk, size)
        destination = slice(start, start + len(chunk))
        images[destination], targets[destination] = data.tensors
    return TensorDataset(images, targets)


def fit_epoch(model, batches, optimizer, device):
    model.train()
    total_loss = 0.0
    pixel_counts = torch.zeros(2, dtype=torch.int64, device=device)
    for images, targets in batches:
        images, targets = images.to(device, non_blocking=True), targets.to(device, non_blocking=True)
        optimizer.zero_grad(set_to_none=True)
        logits = model(images)["out"]
        loss = loss_fn(logits, targets)
        value = loss.item()
        if not math.isfinite(value):
            raise RuntimeError(f"학습 손실 오류: {value}")
        loss.backward()
        optimizer.step()
        total_loss += value * len(images)
        with torch.no_grad():
            predicted = logits.sigmoid() >= THRESHOLD
            expected = targets.bool()
            pixel_counts[0] += (predicted & expected).sum()
            pixel_counts[1] += (predicted | expected).sum()
    intersection, union = pixel_counts.tolist()
    return total_loss / len(batches.dataset), intersection / union


def validation(model, batches, device):
    stats, masks = evaluate(model, batches, device)
    stats["black_images"] = (~masks.flatten(1).any(dim=1)).sum().item()
    return stats, masks


@torch.no_grad()
def update_batchnorm(model, batches, device):
    # 학습 사진을 배치별로 한 번 통과시켜 평균과 분산을 누적합니다.
    # BatchNorm만 학습 모드로 두어 Dropout은 꺼진 상태를 유지합니다.
    model.eval().requires_grad_(False)
    layers = batchnorms(model)
    momenta = {name: layer.momentum for name, layer in layers.items()}
    for layer in layers.values():
        layer.reset_running_stats()
        layer.momentum = None
        layer.train()
    for images, _ in batches:
        model(images.to(device, non_blocking=True))
    for name, layer in layers.items():
        layer.momentum = momenta[name]
    model.eval()
    observed = {layer.num_batches_tracked.item() for layer in layers.values()}
    if observed != {len(batches)}:
        raise RuntimeError(f"일부 BatchNorm 층에 배치가 누락됐습니다: {observed}")
    return len(layers)


def save_and_verify(model, folder, name, reference, solo_batches, device, seed, epochs, log):
    path = folder / f"{name}.pt"
    state = model.state_dict()
    torch.save({
        "model_state_dict": state,
        "model": "deeplabv3_mobilenet_v3_large",
        "image_size": IMAGE_SIZE,
        "normalization": "RGB / 127.5 - 1",
        "threshold": THRESHOLD,
        "split_status": "provisional",
        "batchnorm": name,
        "epoch": epochs,
        "seed": seed,
    }, path)
    loaded = new_model(device)
    loaded.load_state_dict(torch.load(path, map_location=device, weights_only=True)["model_state_dict"])
    restored = loaded.state_dict()
    if any(not torch.equal(tensor, restored[key]) for key, tensor in state.items()):
        raise RuntimeError(f"체크포인트 왕복 검사 실패: {path}")
    stats, single = validation(loaded, solo_batches, device)
    differences = (single != reference).flatten(1).sum(dim=1)
    emit(log, event="restored_single_image", case=name, checkpoint=str(path),
         state_dict_exact=True, identical_images=(differences == 0).sum().item(),
         changed_pixels=differences.sum().item(), max_changed_pixels_per_image=differences.max().item(), **stats)


def run(args, folder, log):
    if not torch.cuda.is_available():
        raise RuntimeError("이번 학습에 필요한 CUDA GPU가 없습니다.")
    device = torch.device("cuda")
    torch.manual_seed(args.seed)
    torch.set_num_threads(min(torch.get_num_threads(), 4))
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    train = read_csv(args.splits / "train.csv")
    val = read_csv(args.splits / "val.csv")
    if (len(train), len(val)) != (960, 120):
        raise ValueError("학습 960쌍과 검증 120쌍이 필요합니다.")
    if {r["provisional_group"] for r in train} & {r["provisional_group"] for r in val}:
        raise ValueError("학습과 검증의 임시 그룹이 중복됩니다.")
    emit(log, event="configuration", split_status="provisional", seed=args.seed, epochs=args.epochs,
         train_pairs=len(train), val_pairs=len(val), pretrained=False, gpu=torch.cuda.get_device_name(),
         torch=torch.__version__, image_size=IMAGE_SIZE, batch_size=BATCH_SIZE, threshold=THRESHOLD,
         optimizer="AdamW", learning_rate=LEARNING_RATE, positive_weight=POSITIVE_WEIGHT,
         loss="BCEWithLogits + soft Dice")
    train_set, val_set = prepare(train), prepare(val)
    emit(log, event="preprocessing_verified", pairs=len(train_set) + len(val_set))
    train_batches = DataLoader(train_set, batch_size=BATCH_SIZE, pin_memory=True, shuffle=True,
                               generator=torch.Generator().manual_seed(args.seed))
    val_batches = DataLoader(val_set, batch_size=BATCH_SIZE)
    solo_batches = DataLoader(val_set, batch_size=1)
    model = new_model(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=LEARNING_RATE)
    for epoch in range(1, args.epochs + 1):
        train_loss, train_iou = fit_epoch(model, train_batches, optimizer, device)
        stats, base_masks = validation(model, val_batches, device)
        emit(log, event="epoch", epoch=epoch, train_loss=train_loss, train_lane_iou=train_iou, **stats)
    emit(log, event="batchnorm_comparison", case="baseline", epoch=args.epochs, **stats)

    recalibrated = deepcopy(model)
    calibration_batches = DataLoader(train_set, batch_size=BATCH_SIZE, pin_memory=True, shuffle=True,
                                     generator=torch.Generator().manual_seed(args.seed + 1))
    layer_count = update_batchnorm(recalibrated, calibration_batches, device)
    assert_same_parameters(model, recalibrated)
    calibrated_stats, calibrated_masks = validation(recalibrated, val_batches, device)
    emit(log, event="batchnorm_comparison", case="recalibrated", epoch=args.epochs, bn_layers=layer_count,
         calibration_pairs=len(train_set), calibration_batches=len(calibration_batches),
         weights_identical=True, **calibrated_stats)

    groups = defaultdict(list)
    for index, row in enumerate(val):
        groups[row["provisional_group"]].append(index)
    rng = random.Random(args.seed)
    previews = [i for group in sorted(groups) for i in rng.sample(groups[group], min(2, len(groups[group])))]
    for name, variant, predictions in (("baseline", model, base_masks),
                                        ("recalibrated", recalibrated, calibrated_masks)):
        save_and_verify(variant, folder, name, predictions, solo_batches, device, args.seed, args.epochs, log)
        preview_folder = folder / f"{name}_previews"
        preview_folder.mkdir()
        for i in previews:
            save_preview(val[i], val_set.tensors[1][i, 0], predictions[i, 0], preview_folder)
    emit(log, event="completed", optimizer_steps=args.epochs * len(train_batches),
         preview_jpgs=[Path(val[i]["jpg"]).name for i in previews])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--splits", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--seed", type=int, default=197)
    args = parser.parse_args()
    if args.epochs < 1:
        parser.error("--epochs는 1 이상이어야 합니다.")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with (output / "training.jsonl").open("x", encoding="utf-8") as log:
        run(args, output, log)


if __name__ == "__main__":
    main()
