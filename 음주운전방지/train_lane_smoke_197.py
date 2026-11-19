"""AI Hub 197 임시 분할에서 DeepLabV3–MobileNetV3 학습 흐름을 확인합니다."""

import argparse
import json
import math
import random
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader, TensorDataset
from torchvision import __version__ as torchvision_version
from torchvision.models.segmentation import deeplabv3_mobilenet_v3_large

from convert_lane_masks_197 import encode, read_image, verify
from split_lane_masks_197 import read_csv


IMAGE_SIZE = (384, 240)  # 너비, 높이
THRESHOLD = 0.5
LEARNING_RATE = 0.001
POSITIVE_WEIGHT = 5.0


def sample_rows(split_dir, split, count, seed):
    rows = sorted(read_csv(split_dir / f"{split}.csv"), key=lambda row: row["jpg"])
    if len(rows) < count:
        raise ValueError(f"{split}.csv에 {count}쌍이 필요합니다.")
    return random.Random(seed).sample(rows, count)


def load_samples(rows, size=IMAGE_SIZE):
    images, targets, checks = [], [], []
    width, height = size
    for row in rows:
        jpg, mask_path = Path(row["jpg"]), Path(row["mask"])
        photo = read_image(jpg, cv2.IMREAD_COLOR | cv2.IMREAD_IGNORE_ORIENTATION)
        mask = read_image(mask_path, cv2.IMREAD_UNCHANGED)
        source_white = verify(mask, photo.shape[:2])
        source_height, source_width = mask.shape
        if source_height < height or source_width < width:
            raise ValueError(f"축소할 원본이 입력 크기보다 작습니다: {jpg}")

        photo_small = cv2.resize(photo, size, interpolation=cv2.INTER_AREA)
        # 면적 안에 흰 차선이 조금이라도 있으면 대상 픽셀을 차선으로 남깁니다.
        coverage = cv2.resize(mask.astype(np.float32) / 255, size, interpolation=cv2.INTER_AREA)
        target = coverage > 0
        y, x = np.nonzero(mask)
        target_y = ((2 * y + 1) * height) // (2 * source_height)
        target_x = ((2 * x + 1) * width) // (2 * source_width)
        retained = int(target[target_y, target_x].sum())
        if retained != source_white:
            raise ValueError(f"축소 후 사라진 차선 픽셀 위치가 있습니다: {mask_path}")
        checks.append({
            "jpg": str(jpg),
            "mask": str(mask_path),
            "original_white": source_white,
            "resized_white": int(target.sum()),
            "source_white_centers_covered": retained,
        })
        rgb = cv2.cvtColor(photo_small, cv2.COLOR_BGR2RGB)
        # RGB [0, 255]를 [-1, 1]로 바꿔 모델에 넣습니다.
        images.append(torch.from_numpy(rgb).permute(2, 0, 1).float() / 127.5 - 1)
        targets.append(torch.from_numpy(target).unsqueeze(0).float())
    return TensorDataset(torch.stack(images), torch.stack(targets)), checks


def new_model(device):
    # 외부 가중치 없이 모델과 백본을 무작위 초기화합니다.
    return deeplabv3_mobilenet_v3_large(
        weights=None, weights_backbone=None, num_classes=1, aux_loss=False
    ).to(device)


def loss_fn(logits, targets):
    positive_weight = logits.new_tensor(POSITIVE_WEIGHT)
    bce = F.binary_cross_entropy_with_logits(logits, targets, pos_weight=positive_weight)
    probabilities = logits.sigmoid()
    dimensions = (1, 2, 3)
    intersection = (probabilities * targets).sum(dim=dimensions)
    total = probabilities.sum(dim=dimensions) + targets.sum(dim=dimensions)
    dice_loss = 1 - ((2 * intersection + 1) / (total + 1)).mean()
    return bce + dice_loss


def train_epoch(model, batches, optimizer, device):
    model.train()
    total = 0.0
    for images, targets in batches:
        images, targets = images.to(device), targets.to(device)
        optimizer.zero_grad(set_to_none=True)
        loss = loss_fn(model(images)["out"], targets)
        value = loss.item()
        if not math.isfinite(value):
            raise ValueError(f"학습 손실이 유한하지 않습니다: {value}")
        loss.backward()
        optimizer.step()
        total += value * len(images)
    return total / len(batches.dataset)


@torch.inference_mode()
def evaluate(model, batches, device):
    model.eval()
    loss_total = 0.0
    intersection = predicted_count = target_count = 0
    predictions = []
    for images, targets in batches:
        logits = model(images.to(device))["out"]
        targets = targets.to(device)
        value = loss_fn(logits, targets).item()
        if not math.isfinite(value):
            raise ValueError(f"검증 손실이 유한하지 않습니다: {value}")
        loss_total += value * len(images)
        predicted = logits.sigmoid() >= THRESHOLD
        intersection += (predicted & targets.bool()).sum().item()
        predicted_count += predicted.sum().item()
        target_count += targets.sum().item()
        predictions.append(predicted.cpu())
    union = predicted_count + target_count - intersection
    metrics = {
        "val_loss": loss_total / len(batches.dataset),
        "lane_iou": intersection / union,
        "lane_dice": 2 * intersection / (predicted_count + target_count),
        "predicted_positive_pixels": predicted_count,
        "target_positive_pixels": target_count,
    }
    return metrics, torch.cat(predictions)


def save_preview(row, target, prediction, output):
    jpg = Path(row["jpg"])
    original = read_image(jpg, cv2.IMREAD_COLOR | cv2.IMREAD_IGNORE_ORIENTATION)
    target = cv2.cvtColor(target.numpy().astype(np.uint8) * 255, cv2.COLOR_GRAY2BGR)
    prediction = cv2.cvtColor(prediction.numpy().astype(np.uint8) * 255, cv2.COLOR_GRAY2BGR)
    panels = []
    for image, label, interpolation in (
        (original, "Original", cv2.INTER_AREA),
        (target, "Ground truth", cv2.INTER_NEAREST),
        (prediction, f"Prediction (p >= {THRESHOLD})", cv2.INTER_NEAREST),
    ):
        panel = cv2.resize(image, (576, 360), interpolation=interpolation)
        panel = cv2.copyMakeBorder(panel, 32, 0, 0, 0, cv2.BORDER_CONSTANT)
        cv2.putText(panel, label, (12, 23), cv2.FONT_HERSHEY_SIMPLEX, .65, (255, 255, 255), 1, cv2.LINE_AA)
        panels.append(panel)
    path = output / f"{jpg.stem}_comparison.jpg"
    path.write_bytes(encode(path, np.hstack(panels)))


def emit(log, **record):
    line = json.dumps(record, ensure_ascii=False, allow_nan=False)
    print(line, flush=True)
    log.write(line + "\n")
    log.flush()


def run(args, output, log):
    torch.manual_seed(args.seed)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    device = torch.device("cuda" if torch.cuda.is_available() and not args.cpu else "cpu")
    if device.type == "cpu":
        torch.set_num_threads(min(torch.get_num_threads(), 4))
    train_rows = sample_rows(args.splits, "train", 16, args.seed)
    val_rows = sample_rows(args.splits, "val", 8, args.seed + 1)
    train_set, train_checks = load_samples(train_rows)
    val_set, val_checks = load_samples(val_rows)
    train_groups = {row["provisional_group"] for row in train_rows}
    val_groups = {row["provisional_group"] for row in val_rows}
    if train_groups & val_groups:
        raise ValueError("학습·검증 샘플의 임시 그룹이 겹칩니다.")
    emit(log, event="preprocessing_verified", purpose="smoke_test", split_status="provisional",
         seed=args.seed, val_seed=args.seed + 1, device=str(device),
         gpu=torch.cuda.get_device_name() if device.type == "cuda" else None,
         torch=torch.__version__, torchvision=torchvision_version, epochs=args.epochs,
         image_size=list(IMAGE_SIZE), batch_size=4, learning_rate=LEARNING_RATE,
         positive_weight=POSITIVE_WEIGHT, pretrained=False, threshold=THRESHOLD,
         retained_pairs=len(train_checks) + len(val_checks))
    (output / "samples.json").write_text(
        json.dumps({"train": train_checks, "val": val_checks}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    train_batches = DataLoader(train_set, batch_size=4, shuffle=True, generator=torch.Generator().manual_seed(args.seed))
    val_batches = DataLoader(val_set, batch_size=4)
    model = new_model(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=LEARNING_RATE)
    for epoch in range(1, args.epochs + 1):
        loss = train_epoch(model, train_batches, optimizer, device)
        metrics, predictions = evaluate(model, val_batches, device)
        emit(log, event="epoch", epoch=epoch, train_loss=loss, **metrics)

    checkpoint = output / "deeplabv3_mobilenetv3.pt"
    torch.save({
        "model": "deeplabv3_mobilenet_v3_large",
        "model_state_dict": model.state_dict(),
        "image_size": IMAGE_SIZE,
        "normalization": "RGB / 127.5 - 1",
        "threshold": THRESHOLD,
        "epoch": args.epochs,
        "seed": args.seed,
        "split_status": "provisional",
    }, checkpoint)
    restored = new_model(device)
    restored.load_state_dict(torch.load(checkpoint, map_location=device, weights_only=True)["model_state_dict"])
    _, restored_predictions = evaluate(restored, val_batches, device)
    if not torch.equal(predictions, restored_predictions):
        raise ValueError("체크포인트를 다시 읽은 뒤 검증 마스크가 달라졌습니다.")
    previews = output / "val_previews"
    previews.mkdir()
    for index, row in enumerate(val_rows[:4]):
        save_preview(row, val_set.tensors[1][index, 0], restored_predictions[index, 0], previews)
    emit(log, event="completed", optimizer_steps=args.epochs * len(train_batches),
         checkpoint_reloaded=True, comparisons=4)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--splits", required=True, type=Path, help="train.csv와 val.csv가 있는 폴더")
    parser.add_argument("--output", required=True, type=Path, help="이번 실행에 사용할 새 출력 폴더")
    parser.add_argument("--seed", type=int, default=197)
    parser.add_argument("--epochs", choices=(1, 2), type=int, default=2)
    parser.add_argument("--cpu", action="store_true", help="CUDA가 있어도 CPU 사용")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    # 같은 출력 폴더에 시험 결과를 덮어쓰지 않도록 새 로그를 독점 생성합니다.
    with (output / "training.jsonl").open("x", encoding="utf-8") as log:
        run(args, output, log)


if __name__ == "__main__":
    main()
