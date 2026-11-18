"""RedBox 차선 모델이 학습 사진 4장의 정답을 따라 그리는지 확인합니다."""

import argparse
import json
from pathlib import Path

import torch
from torch.utils.data import DataLoader

from train_lane_smoke_197 import (
    IMAGE_SIZE,
    LEARNING_RATE,
    POSITIVE_WEIGHT,
    THRESHOLD,
    emit,
    load_samples,
    loss_fn,
    new_model,
    sample_rows,
    save_preview,
    train_epoch,
)


def measure(probabilities, target):
    predicted = probabilities >= THRESHOLD
    intersection = (predicted & target).sum().item()
    union = (predicted | target).sum().item()
    return {
        "lane_iou": intersection / union,
        "predicted_lane_pixels": predicted.sum().item(),
        "target_lane_pixels": target.sum().item(),
        "mean_probability_on_lane": probabilities[target].mean().item(),
        "mean_probability_on_background": probabilities[~target].mean().item(),
        "max_probability_on_lane": probabilities[target].max().item(),
        "max_probability_on_background": probabilities[~target].max().item(),
    }


@torch.inference_mode()
def evaluate_training_samples(model, images, targets, names, update, train_loss, log, *, batch_stats=False):
    model.eval()
    if batch_stats:
        # 최종 진단에서 BatchNorm만 현재 배치 통계를 씁니다. Dropout은 평가 모드를 유지합니다.
        for layer in model.modules():
            if isinstance(layer, torch.nn.BatchNorm2d):
                layer.track_running_stats = False
                layer.train()
    logits = model(images)["out"]
    if logits.shape != targets.shape or not torch.isfinite(logits).all().item():
        raise ValueError("모델 출력과 정답의 모양이 다르거나 출력에 비유한 값이 있습니다.")
    # BCE에는 원본 로짓을 전달하고, 픽셀별 예측 확률에는 sigmoid를 한 번 적용합니다.
    probabilities = logits.sigmoid()
    lane_pixels = targets.bool()
    metrics = measure(probabilities, lane_pixels)
    per_image = {
        name: measure(probability, target)
        for name, probability, target in zip(names, probabilities, lane_pixels, strict=True)
    }
    event = "batchnorm_batch_stats_diagnostic" if batch_stats else "training_samples"
    emit(log, event=event, update=update, train_step_loss=train_loss,
         eval_loss=loss_fn(logits, targets).item(), **metrics, per_image=per_image)
    return (probabilities >= THRESHOLD).cpu()


def save_comparisons(rows, targets, predictions, folder):
    folder.mkdir()
    for row, target, predicted in zip(rows, targets[:, 0], predictions[:, 0], strict=True):
        save_preview(row, target, predicted, folder)


def run(args, output, log):
    if not torch.cuda.is_available():
        raise RuntimeError("이번 실험에 필요한 CUDA GPU를 찾지 못했습니다.")
    device = torch.device("cuda")
    torch.manual_seed(args.seed)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    rows = sample_rows(args.splits, "train", 4, args.seed)
    names = [Path(row["jpg"]).stem for row in rows]
    training_set, checks = load_samples(rows)
    images, targets = training_set.tensors
    if targets.dtype != torch.float32 or targets.unique().tolist() != [0.0, 1.0]:
        raise ValueError("이진 정답은 float32 배경 0, 차선 1이어야 합니다.")
    emit(log, event="configuration", split_status="provisional", split="train",
         sample_names=names, seed=args.seed, gpu=torch.cuda.get_device_name(),
         torch=torch.__version__, batch_size=4, updates=args.updates, interval=args.interval,
         image_size=list(IMAGE_SIZE), model="deeplabv3_mobilenet_v3_large", pretrained=False,
         learning_rate=LEARNING_RATE, positive_weight=POSITIVE_WEIGHT, threshold=THRESHOLD,
         loss="BCEWithLogits + soft Dice", target_values=[0, 1],
         input_shape=list(images.shape), target_shape=list(targets.shape))
    (output / "samples.json").write_text(json.dumps(checks, ensure_ascii=False, indent=2), encoding="utf-8")
    batches = DataLoader(training_set, batch_size=4)
    gpu_images, gpu_targets = images.to(device), targets.to(device)
    model = new_model(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=LEARNING_RATE)

    before = evaluate_training_samples(model, gpu_images, gpu_targets, names, 0, None, log)
    save_comparisons(rows, targets, before, output / "before")
    for update in range(1, args.updates + 1):
        # 4장 전체가 배치 하나이므로 train_epoch 한 번이 업데이트 한 번입니다.
        train_loss = train_epoch(model, batches, optimizer, device)
        if update % args.interval == 0 or update == args.updates:
            after = evaluate_training_samples(model, gpu_images, gpu_targets, names, update, train_loss, log)
    save_comparisons(rows, targets, after, output / "after")
    if not after.any().item():
        evaluate_training_samples(
            model, gpu_images, gpu_targets, names, args.updates, train_loss, log, batch_stats=True
        )
    emit(log, event="completed", optimizer_steps=args.updates, comparisons_before=4, comparisons_after=4)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--splits", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path, help="이번 실행에 사용할 새 출력 폴더")
    parser.add_argument("--seed", type=int, default=197)
    parser.add_argument("--updates", type=int, default=200, choices=range(100, 201), metavar="100..200")
    parser.add_argument("--interval", type=int, default=25)
    args = parser.parse_args()
    if args.interval < 1:
        parser.error("--interval은 1 이상이어야 합니다.")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with (output / "training.jsonl").open("x", encoding="utf-8") as log:
        run(args, output, log)


if __name__ == "__main__":
    main()
