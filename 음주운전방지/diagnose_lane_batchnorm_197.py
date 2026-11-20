# 028  평가할 때 차선이 사라지는 이유 찾기
# 가중치를 고정하고 BatchNorm 통계만 바꿔 같은 사진의 예측을 비교합니다.
# --splits의 학습 사진과 새 --output을 지정합니다.
# 진단 로그와 비교 사진으로 일반 평가와 통계 재계산의 차이를 확인합니다.

"""같은 가중치와 학습 사진 4장으로 BatchNorm 통계의 영향을 검사합니다."""

import argparse
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory

import torch
from torch import nn
from torch.utils.data import DataLoader

from train_lane_overfit_197 import measure, save_comparisons
from train_lane_smoke_197 import (
    IMAGE_SIZE, LEARNING_RATE, THRESHOLD, emit, load_samples, new_model, sample_rows, train_epoch,
)


def batchnorms(model):
    return {name: layer for name, layer in model.named_modules() if isinstance(layer, nn.BatchNorm2d)}


def snapshot(layers):
    return {
        name: (layer.num_batches_tracked.item(), layer.running_mean.detach().clone(),
               layer.running_var.detach().clone())
        for name, layer in layers.items()
    }


def record_stats(before, after):
    return {
        name: {
            "num_batches_tracked": [before[name][0], count],
            "running_mean_first4": [before[name][1][:4].tolist(), mean[:4].tolist()],
            "running_var_first4": [before[name][2][:4].tolist(), variance[:4].tolist()],
            "max_mean_delta": (mean - before[name][1]).abs().max().item(),
            "max_var_delta": (variance - before[name][2]).abs().max().item(),
        }
        for name, (count, mean, variance) in after.items()
    }


def train_case(model, batches, device, images, log):
    # 기존 학습 루프를 사용합니다. 직전 평가 다음 업데이트의 실제 forward 모드를 관찰합니다.
    layers = batchnorms(model)
    names = list(layers)
    selected = {name: layers[name] for name in (
        names[0], next(name for name in names if name.startswith("classifier.") and ".project." in name)
    )}
    optimizer = torch.optim.AdamW(model.parameters(), lr=LEARNING_RATE)
    model.eval()
    for update in range(1, 201):
        if update % 25 == 1 or update == 200:
            before = snapshot(selected)
            modes = []
            handle = model.register_forward_pre_hook(
                lambda module, inputs: modes.append((module.training, all(layer.training for layer in layers.values())))
            )
            try:
                loss = train_epoch(model, batches, optimizer, device)
            finally:
                handle.remove()
            changes = record_stats(before, snapshot(selected))
            if modes != [(True, True)] or any(
                end - start != 1 for start, end in (v["num_batches_tracked"] for v in changes.values())
            ):
                raise RuntimeError("학습 forward가 BatchNorm 누적 통계를 갱신하지 않았습니다.")
            emit(log, event="training_bn_update", update=update, loss=loss,
                 training_at_forward=modes[0][0], all_bn_training=modes[0][1], layers=changes)
        else:
            loss = train_epoch(model, batches, optimizer, device)
        if update % 25 == 0:
            model.eval()
            last_eval = snapshot(selected)
            with torch.no_grad():
                model(images)
            if any(change["max_mean_delta"] or change["max_var_delta"]
                   or len(set(change["num_batches_tracked"])) != 1
                   for change in record_stats(last_eval, snapshot(selected)).values()):
                raise RuntimeError("평가 forward가 BatchNorm 누적 통계를 바꿨습니다.")
            emit(log, event="intermediate_eval", update=update, all_bn_eval=not any(
                layer.training for layer in layers.values()
            ), tracked_before_and_after={name: values[0] for name, values in last_eval.items()})
    return selected


@torch.no_grad()
def probabilities(model, images, *, single=False):
    inputs = images.split(1) if single else (images,)
    return torch.cat([model(batch)["out"].sigmoid() for batch in inputs])


def save_case(output, name, probs, rows, targets, log):
    positive = targets.bool().to(probs.device)
    predictions = (probs >= THRESHOLD).cpu()
    emit(log, event="comparison", case=name, **measure(probs, positive), per_image={
        Path(row["jpg"]).stem: measure(p, mask)
        for row, p, mask in zip(rows, probs, positive, strict=True)
    })
    save_comparisons(rows, targets, predictions, output / name)
    return predictions


@torch.no_grad()
def recalibrate(model, images):
    # 누적 통계를 초기화하고 학습 사진 4장의 한 배치로 다시 채웁니다.
    model.eval().requires_grad_(False)
    layers = batchnorms(model)
    sample_counts = {}

    def count_input(name, inputs):
        tensor = inputs[0]
        sample_counts[name] = tensor.numel() // tensor.shape[1]

    hooks = []
    for name, layer in layers.items():
        layer.reset_running_stats()
        layer.momentum = 1.0
        layer.train()
        hooks.append(layer.register_forward_pre_hook(
            lambda module, inputs, key=name: count_input(key, inputs)
        ))
    try:
        model(images)
    finally:
        for hook in hooks:
            hook.remove()
    model.eval()
    return sample_counts


def assert_same_parameters(reference, model):
    if any(not torch.equal(weights, other)
           for weights, other in zip(reference.parameters(), model.parameters(), strict=True)):
        raise RuntimeError("BatchNorm 비교 중 모델 가중치가 바뀌었습니다.")


def checkpoint_round_trip(model, path, device, seed):
    expected = model.state_dict()
    torch.save({"model_state_dict": expected, "image_size": IMAGE_SIZE,
                "threshold": THRESHOLD, "seed": seed}, path)
    restored = new_model(device)
    restored.load_state_dict(torch.load(path, weights_only=True, map_location=device)["model_state_dict"])
    restored.eval()
    actual = restored.state_dict()
    if any(not torch.equal(tensor, actual[name]) for name, tensor in expected.items()):
        raise RuntimeError("체크포인트에서 가중치 또는 BatchNorm 버퍼가 달라졌습니다.")
    return restored


def run(args, output, log):
    device = torch.device("cuda")
    torch.manual_seed(args.seed)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    rows = sample_rows(args.splits, "train", 4, args.seed)
    data, _ = load_samples(rows)
    images, targets = data.tensors
    images = images.to(device)
    model = new_model(device)
    emit(log, event="configuration", gpu=torch.cuda.get_device_name(), seed=args.seed, updates=200,
         image_size=IMAGE_SIZE, threshold=THRESHOLD, training_jpgs=[row["jpg"] for row in rows])
    monitored = train_case(model, DataLoader(data, batch_size=4), device, images, log)

    # 이전 4장 실험에는 체크포인트가 없으므로 이번 재현 모델의 버퍼를 왕복 검사합니다.
    with TemporaryDirectory(dir=output) as staging:
        baseline = checkpoint_round_trip(model, Path(staging) / "baseline.pt", device, args.seed)
    emit(log, event="baseline_checkpoint_verified", bn_layers=len(batchnorms(baseline)),
         tracked_counts=sorted({layer.num_batches_tracked.item() for layer in batchnorms(baseline).values()}))
    old_probs = probabilities(baseline, images)
    save_case(output, "01_original_running_stats", old_probs, rows, targets, log)

    batch_model = deepcopy(baseline)
    for layer in batchnorms(batch_model).values():
        layer.track_running_stats = False
        layer.train()
    assert_same_parameters(baseline, batch_model)
    batch_probs = probabilities(batch_model, images)
    save_case(output, "02_current_batch_stats", batch_probs, rows, targets, log)

    calibrated = deepcopy(baseline)
    counts = recalibrate(calibrated, images)
    assert_same_parameters(baseline, calibrated)
    calibrated_layers = batchnorms(calibrated)
    emit(log, event="recalibrated_running_buffers", layers=record_stats(
        snapshot(monitored), snapshot({name: calibrated_layers[name] for name in monitored})
    ), activation_counts=sorted(set(counts.values())))
    recalibrated_probs = probabilities(calibrated, images)
    recalibrated_masks = save_case(output, "03_recalibrated_running_stats", recalibrated_probs, rows, targets, log)

    # running_var에는 표본 분산이 저장됩니다. 배치 평가와 동일한 모집단 분산도 대조합니다.
    population = deepcopy(calibrated)
    with torch.no_grad():
        for name, layer in batchnorms(population).items():
            layer.running_var.mul_((counts[name] - 1) / counts[name])
    matched_probs = probabilities(population, images)
    emit(log, event="population_variance_control",
         max_difference_from_batch_stats=(matched_probs - batch_probs).abs().max().item(),
         **measure(matched_probs, targets.bool().to(device)))

    # 일반적인 재계산 결과에서 차선이 나오면 그 통계를 저장해 단건 평가를 합니다.
    # 일반 재계산이 실패한 경우에는 모집단 분산을 저장한 대조군의 단건 평가를 확인합니다.
    checkpoint_case = "population_variance"
    candidate, expected = population, matched_probs
    if recalibrated_masks.any().item():
        candidate, expected = calibrated, recalibrated_probs
        checkpoint_case = "recalibrated_running_stats"
    if not (expected >= THRESHOLD).any().item():
        emit(log, event="completed", restored_single_image_inference=False)
        return
    assert_same_parameters(baseline, candidate)
    path = output / "batchnorm_recalibrated.pt"
    restored = checkpoint_round_trip(candidate, path, device, args.seed)
    restored_batch = probabilities(restored, images)
    if not torch.equal(restored_batch >= THRESHOLD, expected >= THRESHOLD):
        raise RuntimeError("체크포인트를 다시 읽은 뒤 배치 예측이 바뀌었습니다.")
    single_probs = probabilities(restored, images, single=True)
    single_masks = save_case(output, "04_restored_single_image", single_probs, rows, targets, log)
    emit(log, event="completed", checkpoint_case=checkpoint_case, checkpoint=str(path),
         state_dict_exact=True, single_masks_equal_to_batch=torch.equal(single_masks, (restored_batch >= THRESHOLD).cpu()),
         max_single_probability_delta=(single_probs - restored_batch).abs().max().item())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--splits", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--seed", type=int, default=197)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with (output / "diagnosis.jsonl").open("x", encoding="utf-8") as log:
        run(args, output, log)


if __name__ == "__main__":
    main()
