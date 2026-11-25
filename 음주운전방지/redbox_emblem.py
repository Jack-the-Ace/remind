# 실험용 브랜드 표시 함수입니다. 선택 차량에 속하고 다른 차와 겹치지 않는 엠블럼만 봅니다.
# 여러 선명한 프레임에서 검증 문턱을 넘긴 같은 브랜드를 기억합니다.
# 차량 선택 키가 바뀌면 기록을 초기화합니다. 추적 보류 중에는 정보를 전달하지 않습니다.
from collections import Counter
import hashlib
import json
from pathlib import Path
import numpy as np

CANON={"hyundai":"Hyundai","kia":"Kia","bmw":"BMW","mercedes":"Mercedes-Benz","audi":"Audi",
       "chevrolet":"Chevrolet","toyota":"Toyota","volkswagen":"Volkswagen","lexus":"Lexus"}

def iou(a,b):
    a,b=np.asarray(a),np.asarray(b)
    inter=np.maximum(0,np.minimum(a[2:],b[2:])-np.maximum(a[:2],b[:2])).prod()
    return float(inter/max(1,np.prod(a[2:]-a[:2])+np.prod(b[2:]-b[:2])-inter))

def owned(box,target,others):
    x,y,X,Y=box
    cx,cy=(x+X)/2,(y+Y)/2
    if x<target[0] or y<target[1] or X>target[2] or Y>target[3]:
        return False
    return not any(a<=cx<=c and b<=cy<=d for a,b,c,d in others)

def detections(model,img,target,others,offset):
    # 차량을 잘라서 넣었으면 잘라낸 시작점을 더해 원본 좌표로 되돌립니다.
    result=model.predict(img,imgsz=640,device=0,conf=.05,verbose=False)[0]
    found=[]
    for x,y,X,Y,cf,k in result.boxes.data.cpu().tolist():
        box=(np.array([x,y,X,Y])+offset).tolist()
        found.append(dict(brand=CANON[result.names[int(k)]],box=box,conf=cf,owned=owned(box,target,others)))
    return found

def read_policy(path, weights=None):
    """검증을 통과한 브랜드만 표시 대상으로 돌려줍니다."""
    record = json.loads(Path(path).read_text(encoding="utf8"))
    if weights is not None and record.get("weights_sha256"):
        if hashlib.sha256(Path(weights).read_bytes()).hexdigest() != record["weights_sha256"]:
            raise ValueError("표시 기준을 정한 모델과 입력 모델이 다릅니다.")
    return {CANON[name]: value for name, value in record["per_class"].items() if value is not None}


def inspect_target(detector, image, target, neighbors, thresholds, crop=True):
    """한 프레임의 지정 차량에서 엠블럼 상자와 표시할 수 있는 브랜드 후보를 구합니다."""
    height, width = image.shape[:2]
    x, y, right, bottom = np.rint(target).astype(int)
    x, right = np.clip([x, right], 0, width)
    y, bottom = np.clip([y, bottom], 0, height)
    if x >= right or y >= bottom:
        return [], set()
    source = image[y:bottom, x:right] if crop else image
    offset = [x, y, x, y] if crop else [0, 0, 0, 0]
    proposals = detections(detector, source, target, neighbors, offset)
    labels = accepted((item for item in proposals if item["owned"]), thresholds)
    return proposals, labels


def accepted(detections,policy):
    # 검증에서 지지가 부족한 브랜드에는 문턱이 없습니다.
    return {d["brand"] for d in detections if d["brand"] in policy and d["conf"]>=policy[d["brand"]]}

class TargetBrand:
    def __init__(self):
        self.key=None
        self.frames={}
        self.brand="-"

    def update(self,key,frame,labels,confirmed=True):
        if self.key!=key:
            self.key=key
            self.frames.clear()
            self.brand="-"
        if not confirmed:
            return "-"
        self.frames[frame]=set(labels)
        counts=Counter(k for row in self.frames.values() for k in row)
        # 서로 다른 브랜드가 문턱을 넘었으면 한쪽을 임의 선택하지 않습니다.
        self.brand=next(iter(counts)) if len(counts)==1 and max(counts.values())>=3 else "-"
        return self.brand

def fuse(emblem,mobile):
    # 각 방식이 따로 표시할 수 있고 그 브랜드까지 일치할 때만 종합 결과를 냅니다.
    return emblem if emblem!="-" and emblem==mobile else "-"
