# 051  차량 사진을 순서대로 읽어 방향지시등 행동 분류 시험하기
# 050이 고른 연속 사진과 기존 ImageNet 가중치를 사용합니다.
# 실제 차량 상자만 잘라 특징을 뽑고 시간 순서를 읽는 층과 분류층을 학습합니다.
# 독립 촬영본이 부족하므로 학습 표본 재측정 결과와 체크포인트를 따로 보관합니다.
# 다음 실습은 여러 CCTV에서 두 행동을 확보한 뒤 촬영 단위로 검증하는 것입니다.

import argparse
import hashlib
import json
from pathlib import Path

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import torch
from torch.nn import functional as F

from convert_lane_masks_197 import read_image
from redbox_winker import LABELS, SEQUENCE_LENGTH, WinkerModel, load_winker, predict_winker, prepare


def crops_for(images, window):
    crops = []
    for _, name, bbox in window["frames"]:
        image = read_image(images / name, cv2.IMREAD_COLOR)
        x, y, w, h = map(round, bbox)
        crops.append(image[y:y+h, x:x+w].copy())
    return crops


def metrics(logits, labels):
    # 행은 실제 행동, 열은 예측입니다. 각 행동을 한 번씩 양성으로 두고 계산합니다.
    predictions = logits.argmax(1)
    cm = torch.bincount(2*labels + predictions, minlength=4).reshape(2,2).tolist()
    classes = {}
    for i, name in enumerate(LABELS):
        tp = cm[i][i]
        p = tp / max(1, cm[0][i] + cm[1][i])
        r = tp / max(1, sum(cm[i]))
        classes[name] = dict(precision=p, recall=r, f1=2*p*r/(p+r) if p+r else 0)
    return dict(loss=F.cross_entropy(logits, labels).item(),
                accuracy=(predictions == labels).float().mean().item(),
                macro_f1=sum(c["f1"] for c in classes.values())/2, per_class=classes, confusion=cm)


def plot(history, path):
    epochs = [entry["epoch"] for entry in history]
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.5), layout="constrained")
    for axis, keys in zip(axes, [("loss",), ("accuracy","macro_f1")]):
        for key in keys:
            axis.plot(epochs, [entry[key] for entry in history], marker="o", label=key)
        axis.legend()
        axis.set(xlabel="Epoch (0 = before training)", xticks=epochs)
    axes[1].set_ylim(-.05,1.05)
    fig.suptitle("71566 smoke run | training windows only")
    fig.savefig(path, dpi=150)
    plt.close(fig)


def train(args):
    data = json.loads(args.windows.read_text("utf-8"))
    windows, images = data["windows"], Path(data["images"])
    if set(w["label"] for w in windows) != set(LABELS):
        raise ValueError("두 행동 모두 연속 입력이 있어야 합니다.")
    if args.epochs < 1:
        raise ValueError("최소 한 회전이 필요합니다.")
    device = torch.device("cuda")
    torch.manual_seed(71566)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    model = WinkerModel()
    digest = hashlib.sha256(args.weights.read_bytes()).hexdigest()
    if not digest.startswith("8738ca79"):
        raise ValueError("MobileNetV3-Large ImageNet V1 가중치를 확인하세요.")
    state = torch.load(args.weights, map_location="cpu", weights_only=True)
    model.features.load_state_dict({k.removeprefix("features."):v for k,v in state.items()
                                    if k.startswith("features.")}, strict=True)
    model.features.requires_grad_(False)
    model.to(device).eval()
    args.output.mkdir(parents=True, exist_ok=False)
    # 특징 추출부와 그 안의 평균·분산은 고정합니다. 같은 사진의 특징은 한 번만 계산합니다.
    features = []
    with torch.no_grad():
        for w in windows:
            x = prepare(crops_for(images,w)).unsqueeze(0).to(device)
            features.append(model.encode(x))
    data_x = torch.cat(features)
    y = torch.tensor([LABELS.index(w["label"]) for w in windows], device=device)
    # 구간 수가 적은 불이행도 같은 비중으로 학습합니다.
    weights = len(y) / (2 * torch.bincount(y).float())
    opt = torch.optim.AdamW([*model.sequence.parameters(), *model.head.parameters()], lr=.001)
    history = []
    for epoch in range(args.epochs + 1):
        if epoch:
            model.sequence.train()
            model.head.train()
            opt.zero_grad()
            loss = F.cross_entropy(model.classify(data_x), y, weight=weights)
            loss.backward()
            opt.step()
        model.eval()
        with torch.no_grad():
            logits = model.classify(data_x)
            entry = metrics(logits, y)
            entry.update(epoch=epoch, optimization_loss=loss.item() if epoch else None,
                         validation=None)
            history.append(entry)
    out = args.output
    path = out / "winker_smoke.pt"
    torch.save(dict(state_dict=model.state_dict(), classes=list(LABELS), sequence_length=SEQUENCE_LENGTH,
                    scope="training_smoke_only", imagenet_sha256=digest, seed=71566,
                    epochs=args.epochs), path)
    restored = load_winker(path, device)
    cases = []
    for window, batched in zip(windows, logits.softmax(1), strict=True):
        crops = crops_for(images, window)
        # 일괄 입력과 한 구간 입력의 수치 차이는 따로 재고, 저장 전후는 동일 입력끼리 비교합니다.
        expected = predict_winker(model, crops)
        scores = predict_winker(restored, crops)
        if max(abs(scores[k]-expected[k]) for k in LABELS) > 1e-6:
            raise RuntimeError("저장 전후 예측이 다릅니다.")
        # 첫 사진만 반복한 대조 실험입니다. 시간 변화 없이도 맞히는지 확인합니다.
        static = predict_winker(restored, [crops[0]] * SEQUENCE_LENGTH)
        cases.append(dict(group=window["group"], id=window["id"], first=window["frames"][0][0],
                          last=window["frames"][-1][0], truth=window["label"], scores=scores,
                          prediction=max(scores,key=scores.get), static_prediction=max(static,key=static.get),
                          batch_max_delta=max(abs(v-scores[k]) for k,v in zip(LABELS,batched.tolist()))))
    report = dict(scope="training_smoke_only", device=torch.cuda.get_device_name(device),
                  torch_version=str(torch.__version__), seed=71566, batch_size=len(y), lr=.001,
                  device_of_parameters=str(next(model.parameters()).device),
                  samples_by_class=dict(zip(LABELS,torch.bincount(y).tolist())), epochs=history,
                  reload_checked=len(cases), cases=cases, validation=None, test=None,
                  split_reason="목표 클래스별 독립 원본 촬영이 각각 1개뿐임")
    (out/"metrics.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    plot(history, out/"training.png")
    print(report["device"], "재로딩 대조", len(cases), "학습 표본", history[-1])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--windows", required=True, type=Path)
    parser.add_argument("--weights", type=Path, default=Path(__file__).resolve().parent /
                        "output/lane_transfer_197/weights/mobilenet_v3_large-8738ca79.pth")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--epochs", type=int, default=3)
    train(parser.parse_args())
