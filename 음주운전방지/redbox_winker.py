# 051 보조 모듈  같은 차량을 연속해서 본 뒤 방향지시등 행동 점수 읽기
# 약 10 Hz로 얻은 같은 차량의 연속 BGR 사진 12장을 입력합니다.
# MobileNet이 차량 외관을 숫자로 바꾸고 GRU가 순서대로 읽어 두 행동의 점수를 냅니다.
# 추적이 끊기면 새 구간을 모읍니다. 결과는 독립 검증 전 연구용으로만 사용합니다.

import cv2
import numpy as np
import torch
from torch import nn
from torchvision.models import mobilenet_v3_large

LABELS = ("방향지시등 이행", "방향지시등 불이행")
SEQUENCE_LENGTH = 12
SIZE = 128


def prepare(crops):
    if len(crops) != SEQUENCE_LENGTH:
        raise ValueError("같은 차량의 연속 사진 12장이 필요합니다.")
    frames = []
    for image in crops:
        if image is None or image.ndim != 3 or image.shape[2] != 3 or image.size == 0 or image.dtype != np.uint8:
            raise ValueError("빈 영상 또는 잘못된 BGR 입력입니다.")
        h, w = image.shape[:2]
        scale = SIZE / max(h, w)
        rgb = cv2.cvtColor(cv2.resize(image, (max(1, round(w*scale)), max(1, round(h*scale)))),
                           cv2.COLOR_BGR2RGB)
        # 차량 비율을 유지하고 남는 테두리는 ImageNet 평균색으로 채웁니다.
        square = np.full((SIZE, SIZE, 3), (124, 116, 104), np.uint8)
        top, left = (SIZE-rgb.shape[0])//2, (SIZE-rgb.shape[1])//2
        square[top:top+rgb.shape[0], left:left+rgb.shape[1]] = rgb
        frames.append(square)
    batch = torch.from_numpy(np.stack(frames)).permute(0,3,1,2).float() / 255
    return (batch - torch.tensor([.485,.456,.406])[:,None,None]) / torch.tensor([.229,.224,.225])[:,None,None]


class WinkerModel(nn.Module):
    def __init__(self):
        super().__init__()
        self.features = mobilenet_v3_large(weights=None).features
        self.sequence = nn.GRU(960, 32, batch_first=True)
        self.head = nn.Linear(32, len(LABELS))

    def encode(self, batch):
        n, t = batch.shape[:2]
        return self.features(batch.flatten(0,1)).mean(dim=(-2,-1)).reshape(n,t,960)

    def classify(self, features):
        _, last = self.sequence(features)
        return self.head(last[0])

    def forward(self, batch):
        return self.classify(self.encode(batch))


def load_winker(path, device="cpu"):
    record = torch.load(path, map_location="cpu", weights_only=True)
    if record["classes"] != list(LABELS) or record["sequence_length"] != SEQUENCE_LENGTH:
        raise ValueError("체크포인트의 행동 이름이나 입력 길이가 다릅니다.")
    model = WinkerModel()
    model.load_state_dict(record["state_dict"])
    return model.to(device).eval()


@torch.inference_mode()
def predict_winker(model, crops):
    """차선변경 시점에 추적이 이어진 동일 차량의 BGR crop 12장이 필요합니다."""
    device = next(model.parameters()).device
    probabilities = model(prepare(crops).unsqueeze(0).to(device)).softmax(-1)[0].tolist()
    return dict(zip(LABELS, probabilities))
