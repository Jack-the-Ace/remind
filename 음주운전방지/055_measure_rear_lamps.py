# 055  선택 차량의 양쪽 등화와 차체 밝기를 영상 시각으로 비교하기
# track 단계는 006의 타깃 추적으로 상자를 저장합니다. select는 원본 화면에서 고른 점입니다.
# measure 단계는 확인한 후면 위치를 상자 크기에 맞춰 옮기고 색과 점멸을 측정합니다.
# 결과는 별도 실험 폴더의 그래프·영상·JSON에 남깁니다. 다음 단계는 다른 촬영에서 검증하기입니다.
import argparse
import json
import os
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent
os.environ["YOLO_OFFLINE"] = "true"
os.environ["YOLO_CONFIG_DIR"] = str(ROOT / "output/lamp_cv/config")


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=1, allow_nan=False), encoding="utf8")


def read(path):
    return json.loads(path.read_text(encoding="utf8"))


def crop(frame, box):
    x,y,X,Y = np.rint(box).astype(int)
    return frame[max(0,y):min(frame.shape[0],Y), max(0,x):min(frame.shape[1],X)]


def track(case, out, ocr):
    from ultralytics import YOLO
    from track_preview import Target
    from redbox_vehicle_info import VehicleInfo
    from importlib import import_module

    cap = cv2.VideoCapture(str(ROOT/"videos"/case["video"]))
    fps = cap.get(cv2.CAP_PROP_FPS)
    first, last = case["frames"]
    if not cap.isOpened() or not fps:
        raise ValueError(case["video"])
    cap.set(cv2.CAP_PROP_POS_FRAMES, first-1)
    model = YOLO(str(ROOT/"yolo26n.pt"))
    classes = [i for i,n in model.names.items() if n in ("car","bus","truck","motorcycle")]
    target = Target()
    reader, ocr_status = import_module("041_redbox_mvp").ocr() if ocr else (None,"off")
    info = VehicleInfo(reader)
    rows, tiles = [], []
    try:
        for f in range(first,last+1):
            ok, image = cap.read()
            if not ok:
                raise OSError(f"F{f} 읽기 실패")
            # 작은 차량을 보는 보조 실험은 도로 일부를 확대해 검출하고 원본 좌표로 되돌립니다.
            x,y,X,Y=case.get("road_crop",[0,0,image.shape[1],image.shape[0]])
            result = model.track(image[y:Y,x:X],classes=classes,conf=.1,persist=True,tracker="bytetrack.yaml",
                                 device=0,verbose=False)[0]
            detections = [dict(id=int(b.id.item()),box=(b.xyxy[0].cpu().numpy()+[x,y,x,y]).tolist(),
                               **{"class":result.names[int(b.cls.item())]})
                          for b in result.boxes if b.id is not None]
            if f==first:
                px,py = case["select"]
                candidates = [d for d in detections if d["box"][0]<=px<=d["box"][2] and d["box"][1]<=py<=d["box"][3]]
                if not candidates:
                    raise ValueError(f"지정점에 차량 없음: {f}, {case['select']}, {detections}")
                vehicle = min(candidates,key=lambda d:(d["box"][2]-d["box"][0])*(d["box"][3]-d["box"][1]))
                target.select(vehicle,image,f)
            else:
                vehicle = target.update(detections,image,f)
            row = dict(frame=f,time=(f-1)/fps,box=vehicle["box"] if vehicle else None,
                       track_id=vehicle["id"] if vehicle else None)
            rows.append(row)
            if ocr and vehicle and (f-first)%2==0 and len(info.ocr_frames)<12:
                info.sample(image,vehicle,f)
            if (f-first)%max(1,round(fps*case.get("sample_step",.25)))==0:
                tile=np.zeros((109,170,3),np.uint8)
                if vehicle:
                    tile[:87]=cv2.resize(crop(image,vehicle["box"]),(170,87))
                cv2.putText(tile,f"F{f} {row['time']:.2f}s",(3,104),0,.46,(255,255,255),1)
                tiles.append(tile)
    finally:
        cap.release()
        if info.windows_ocr:
            info.windows_ocr.close()
    for page in range(0,len(tiles),60):
        group=tiles[page:page+60]
        while len(group)%8:
            group.append(np.zeros_like(group[0]))
        canvas=np.vstack([np.hstack(group[i:i+8]) for i in range(0,len(group),8)])
        cv2.imencode(".jpg",canvas)[1].tofile(out/f"targets_{page}.jpg")
    save(out/"track.json",dict(video=case["video"],fps=fps,rows=rows,ocr=ocr_status,
                               ocr_samples=info.ocr_frames,info=info.snapshot()))


def reference(case,out):
    # 정차한 한 차량을 사람이 원본에서 고른 대조 실험입니다. 006 추적 결과와 별도로 보관합니다.
    # 번호판 주변의 차체 무늬를 첫 장과 대조합니다. 비슷하지 않으면 좌표도 측정하지 않습니다.
    first,last=case["frames"]
    x,y,X,Y=case["reference_box"]
    cap=cv2.VideoCapture(str(ROOT/"videos"/case["video"]))
    fps=cap.get(cv2.CAP_PROP_FPS)
    cap.set(cv2.CAP_PROP_POS_FRAMES,first-1)
    rows=[]
    try:
        for f in range(first,last+1):
            ok,im=cap.read()
            if not ok: raise OSError(f"원본 F{f} 읽기 실패")
            gray=cv2.cvtColor(im,cv2.COLOR_BGR2GRAY)
            if f==first:
                u,v,U,V=case["reference_patch"]
                template=gray[v:V,u:U].copy()
            margin=18
            search=gray[v-margin:V+margin,u-margin:U+margin]
            scores=cv2.matchTemplate(search,template,cv2.TM_CCOEFF_NORMED)
            _,quality,_,(dx,dy)=cv2.minMaxLoc(scores)
            dx-=margin;dy-=margin
            box=[x+dx,y+dy,X+dx,Y+dy] if quality>=.84 and max(abs(dx),abs(dy))<margin else None
            rows.append(dict(frame=f,time=(f-1)/fps,box=box,track_id=None,match=quality))
    finally:cap.release()
    save(out/"track.json",dict(video=case["video"],fps=fps,rows=rows,source="manual_reference_template"))


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("stage",choices=("track","reference","measure"))
    parser.add_argument("--cases",type=Path,default=ROOT/"rear_lamp_cases.json")
    parser.add_argument("--case",required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--ocr",action="store_true")
    args=parser.parse_args()
    config=read(args.cases)[args.case]
    if args.stage in ("track","reference"):
        dest=args.output/args.case
        dest.mkdir(parents=True,exist_ok=False)
        if args.stage=="reference":
            reference(config,dest)
        else:
            track(config,dest,args.ocr)
    else:
        from rear_lamp_patterns import measure
        measure(config,args.output/args.case)
