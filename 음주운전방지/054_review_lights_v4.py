# 054  선택된 등화 모델의 정답·예측 대조와 별도 영상 적용
# 053에서 고른 best.pt와 검증 사진 또는 블랙박스 영상을 읽습니다.
# 검증에서는 같은 사진의 배경과 차량 세부를 각각 가려 무엇이 달라지는지 봅니다.
# 영상에서는 보이는 상태와 영상 시각만 기록합니다. 점멸과 차선변경 연결은 다음 실습입니다.
import argparse
import json
import os
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
import yaml

BASE = Path(__file__).resolve().parent
os.environ["YOLO_OFFLINE"] = "true"
os.environ["YOLO_CONFIG_DIR"] = str(BASE / "output/roboflow_v4/config")
from ultralytics import YOLO
from ultralytics.engine.results import Results

LIGHTS = (0, 1, 2, 3, 5)


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def truth(path, width, height):
    rows = []
    for text in path.read_text(encoding="utf-8-sig").splitlines():
        if text.strip():
            cls, x, y, w, h = map(float, text.split())
            rows.append((int(cls), np.array([(x-w/2)*width, (y-h/2)*height,
                                             (x+w/2)*width, (y+h/2)*height])))
    return rows


def overlap(a, b):
    intersection = np.maximum(np.minimum(a[2:], b[2:])-np.maximum(a[:2], b[:2]), 0).prod()
    return intersection / max(1, np.prod(a[2:]-a[:2])+np.prod(b[2:]-b[:2])-intersection)


def compare_detections(rows, result):
    # 같은 클래스 상자끼리 IoU 0.5 이상일 때 한 번만 짝을 지어 검출 개수를 셉니다.
    taken = set()
    detected = Counter()
    predicted = Counter()
    for *xyxy, confidence, label in sorted(result.boxes.data.cpu().tolist(),key=lambda r:-r[4]):
        label = int(label)
        if label not in LIGHTS:
            continue
        predicted[label] += 1
        candidates = [(overlap(np.array(xyxy), box), i) for i,(cls,box) in enumerate(rows)
                      if cls == label and i not in taken]
        score, index = max(candidates, default=(0,None))
        if score >= .5:
            taken.add(index)
            detected[label] += 1
    return detected, predicted


def interventions(image, rows):
    # 상태 상자 크기가 차량 상자에 가까워 모든 차량 상자의 합집합을 사용합니다.
    mask = np.zeros(image.shape[:2], np.uint8)
    smooth = image.copy()
    for cls, box in rows:
        if cls != 4:
            x1,y1,x2,y2 = np.maximum(np.rint(box).astype(int), 0)
            cv2.rectangle(mask, (x1,y1), (x2,y2), 255, -1)
            roi = image[y1:y2,x1:x2]
            if roi.size:
                # 차체 색과 대략적 윤곽은 남기고 세부 등화 무늬를 함께 줄입니다.
                coarse = cv2.resize(roi,(4,4),interpolation=cv2.INTER_AREA)
                smooth[y1:y2,x1:x2] = cv2.resize(coarse,(roi.shape[1],roi.shape[0]))
    inside = mask != 0
    only_cars = np.full_like(image,114)
    only_cars[inside] = image[inside]
    background = image.copy()
    background[inside] = 114
    return [image, only_cars, background, smooth]


def panel(image, rows, result, names):
    annotated=image.copy()
    for cls,box in rows:
        a,b,c,d = np.rint(box).astype(int)
        color = (70,240,70) if cls==6 else (30,190,250)
        cv2.rectangle(annotated,(a,b),(c,d),color,2)
        cv2.putText(annotated,names[cls],(max(0,a),max(15,b-2)),0,.6,(0,0,0),3)
        cv2.putText(annotated,names[cls],(max(0,a),max(15,b-2)),0,.6,color,1)
    pictures=[image,annotated,result.plot(line_width=2)]
    tiles=[]
    for title,im in zip(["Original","Ground truth","YOLO26 best | conf >= 0.25"],pictures):
        tile=cv2.copyMakeBorder(im,32,0,0,0,cv2.BORDER_CONSTANT)
        cv2.putText(tile,title,(8,23),0,.65,(255,255,255),1)
        tiles.append(tile)
    return np.hstack(tiles)


def review(model, data, out):
    config=yaml.safe_load(data.read_text(encoding="utf-8"))
    root=Path(config["path"])
    paths=sorted((root/config["val"]).glob("*.jpg"))
    modes=["original","vehicle_boxes_only","background_only","vehicle_detail_removed"]
    totals={m:(Counter(),Counter()) for m in modes}
    supports=Counter()
    saved=Counter()
    for path in paths:
        img=cv2.imdecode(np.fromfile(path,np.uint8),cv2.IMREAD_COLOR)
        rows=truth(path.parent.parent/"labels"/(path.stem+".txt"),img.shape[1],img.shape[0])
        supports.update(c for c,_ in rows if c in LIGHTS)
        results=model.predict(interventions(img,rows),device=0,imgsz=640,conf=.25,verbose=False)
        for mode,result in zip(modes,results,strict=True):
            hit,pred=compare_detections(rows,result)
            totals[mode][0].update(hit)
            totals[mode][1].update(pred)
            if mode=="original":
                # 맞힌 사례와 놓친 사례를 각각 대표 사진으로 저장합니다.
                for c,_ in rows:
                    if c not in LIGHTS:
                        continue
                    key=(c,"hit" if hit[c] else "miss")
                    if saved[key]==0:
                        target=out/f"{key[1]}_{c}_{path.name}"
                        cv2.imencode(".jpg",panel(img,rows,result,config["names"]))[1].tofile(target)
                        saved[key]+=1
    scores={mode:{config["names"][c]: dict(gt=supports[c],matched=tp[c],predicted=pr[c])
                  for c in LIGHTS} for mode,(tp,pr) in totals.items()}
    save(out/"validation_controls.json",dict(images=len(paths),confidence=.25,iou=.5,conditions=scores))
    review_motorcycle(model, root/config["val"], out, config["names"])


def review_motorcycle(model, images, out, names):
    # 육안으로 대조한 같은 이륜차입니다. 987의 오른쪽 등불과 988의 라벨 차이를 살펴봅니다.
    records=[]
    pictures=[]
    for number in (987,988):
        files=list(images.glob(f"Screenshot-{number}-*.jpg"))
        if len(files)!=1:
            return
        path=files[0]
        image=cv2.imdecode(np.fromfile(path,np.uint8),cv2.IMREAD_COLOR)
        rows=truth(path.parent.parent/"labels"/(path.stem+".txt"),640,640)
        vehicle=min((box for cls,box in rows if cls==6),key=lambda b:b[0])
        variants=[("original",image)]
        if number==987:
            mask=np.zeros(image.shape[:2],np.uint8)
            mask[405:430,124:147]=255
            variants.append(("lamp_patch_removed",cv2.inpaint(image,mask,3,cv2.INPAINT_TELEA)))
        for name,variant in variants:
            result=model.predict(variant,device=0,imgsz=640,conf=.001,verbose=False)[0]
            matching=[(int(cls),score) for *xyxy,score,cls in result.boxes.data.cpu().tolist()
                      if overlap(vehicle,np.asarray(xyxy))>=.5]
            scores={names[c]:max((s for k,s in matching if k==c),default=None) for c in (*LIGHTS,6)}
            records.append(dict(source=number,variant=name,scores_at_iou_05=scores))
            if name=="original":
                visible=result[result.boxes.conf>=.25]
                pictures.append(panel(image,rows,visible,names))
    cv2.imencode(".jpg",np.vstack(pictures))[1].tofile(out/"same_motorcycle.jpg")
    save(out/"same_motorcycle.json",records)


def score_split(model, data, split, out):
    # 학습 재측정과 최종 테스트는 다른 폴더에 기록해 검증 결과와 구별합니다.
    result=model.val(data=str(data.resolve()),split=split,imgsz=640,batch=16,device=0,workers=0,
                     project=str(out.resolve()),name=split,plots=True,verbose=False)
    box=result.box
    per_class=[{key:(value.item() if isinstance(value,np.generic) else value) for key,value in row.items()}
               for row in result.summary()]
    save(out/f"{split}_metrics.json",dict(split=split,precision=float(box.mp),recall=float(box.mr),
         macro_f1=float(box.f1.mean()),map50=float(box.map50),map50_95=float(box.map),
         per_class=per_class,gt=result.nt_per_class.tolist()))


def video_preview(model, source, out, limit):
    cap=cv2.VideoCapture(str(source))
    if not cap.isOpened():
        raise ValueError(f"영상 열기 실패: {source}")
    fps=cap.get(cv2.CAP_PROP_FPS)
    size=tuple(int(cap.get(k)) for k in (cv2.CAP_PROP_FRAME_WIDTH,cv2.CAP_PROP_FRAME_HEIGHT))
    if fps<=0 or min(size)<=0:
        cap.release()
        raise ValueError("영상 시각 또는 해상도를 읽을 수 없습니다.")
    dest=out/"lights_preview.mp4"
    writer=cv2.VideoWriter(str(dest),cv2.VideoWriter_fourcc(*"mp4v"),fps,size)
    if not writer.isOpened():
        cap.release()
        raise OSError(dest)
    n=0
    try:
        with (out/"observations.jsonl").open("w",encoding="utf-8") as log:
            while not limit or n<limit:
                ok,frame=cap.read()
                if not ok:
                    break
                # V4와 같이 640 정사각형으로 늘려 입력하고, 상자는 원본 영상 크기로 되돌립니다.
                square=cv2.resize(frame,(640,640))
                prediction=model.predict(square,device=0,imgsz=640,conf=.25,verbose=False)[0]
                boxes=prediction.boxes.data.clone()
                boxes[:,[0,2]]*=size[0]/640
                boxes[:,[1,3]]*=size[1]/640
                result=Results(frame,str(source),prediction.names,boxes=boxes)
                obs=[dict(label=result.names[int(c)],box=b,confidence=p)
                     for *b,p,c in result.boxes.data.cpu().tolist()]
                log.write(json.dumps(dict(frame=n+1,seconds=n/fps,objects=obs),ensure_ascii=False)+"\n")
                writer.write(result.plot(line_width=2))
                n+=1
    finally:
        cap.release()
        writer.release()
    check=cv2.VideoCapture(str(dest))
    ok,_=check.read()
    frames=int(check.get(cv2.CAP_PROP_FRAME_COUNT))
    check.release()
    if not ok or frames!=n:
        raise RuntimeError("저장 영상의 재생 또는 프레임 수 확인 실패")
    print(dest,n,"frames",fps,"FPS")


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--weights",required=True,type=Path)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--validation",type=Path)
    group.add_argument("--video",type=Path)
    parser.add_argument("--score-split",choices=("train","val","test"),
                        help="--validation의 데이터 YAML에서 한 분할만 평가합니다.")
    parser.add_argument("--limit",type=int,default=0,help="영상 시험 프레임 수, 0이면 전체")
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    if args.score_split and not args.validation:
        parser.error("--score-split에는 --validation 데이터 YAML이 필요합니다.")
    if args.limit<0:
        parser.error("--limit는 0 이상이어야 합니다.")
    if not args.weights.is_file():
        raise FileNotFoundError(args.weights)
    args.output.mkdir(parents=True,exist_ok=False)
    detector=YOLO(str(args.weights))
    if args.score_split and args.validation:
        score_split(detector,args.validation,args.score_split,args.output)
    elif args.validation:
        review(detector,args.validation,args.output)
    else:
        video_preview(detector,args.video,args.output,args.limit)
