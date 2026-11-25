# 063  전체 화면과 같은 프레임의 지정 차량 crop에서 검출한 엠블럼을 대조합니다.
# 059의 12개 구간은 그대로 사용하고 추가 차량은 055로 직접 선택·추적합니다.
# 프레임별 상자는 원본 좌표로 복원합니다. 결과 영상과 JSON은 HUD 밖에 따로 저장합니다.
import argparse
from importlib import import_module
import json
import os
from pathlib import Path
import cv2
import numpy as np
from redbox_emblem import TargetBrand, accepted, fuse, inspect_target, iou, read_policy

ROOT=Path(__file__).resolve().parent
os.environ["YOLO_OFFLINE"]="true"
os.environ["YOLO_CONFIG_DIR"]=str(ROOT/"output/emblem_v1/config")
from ultralytics import YOLO
from redbox_brand import predict_crops,restore
BASE=ROOT/"output/compcars_brand/drive"
# 원본에서 읽은 브랜드입니다. 측면에서 표식이 안 보이는 차는 정답 미상으로 둡니다.
EXTRA=[("audi_sedan","BB_20261113_134044.avi",91,150,1560,742,"Audi"),
       ("kia_new","BB_20261123_143347.avi",91,150,1530,710,"Kia"),
       ("hyundai_day","BB_20261123_100916.avi",529,585,547,754,"Hyundai"),
       ("porsche","BB_20261123_104026.avi",91,150,1015,754,"Porsche"),
       ("side","BB_20261123_121756.avi",529,579,135,736,None)]
def save(p,j):
    p.write_text(json.dumps(j,ensure_ascii=False,indent=1),encoding="utf8")
def read(p):
    return json.loads(p.read_text(encoding="utf8"))

def prepare(out):
    out.mkdir(parents=True,exist_ok=False)
    rows=[]
    for name,video,first,last,x,y,brand in EXTRA:
        dest=out/name
        dest.mkdir()
        import_module("055_measure_rear_lamps").track(dict(video=video,frames=[first,last],select=[x,y]),dest,False)
        t=read(dest/"track.json")
        cap=cv2.VideoCapture(str(ROOT/"videos"/video))
        cap.set(1,first-1)
        pool=[]
        try:
            for r in t["rows"]:
                ok,img=cap.read()
                if not ok:
                    raise OSError(video)
                if not r["box"]:
                    continue
                a,b,c,d=np.rint(r["box"]).astype(int)
                crop=img[b:d,a:c]
                gray=cv2.cvtColor(cv2.resize(crop,(128,96)),cv2.COLOR_BGR2GRAY)
                pool.append((cv2.Laplacian(gray,cv2.CV_32F).var()*min(1,crop.shape[1]/200),r))
        finally:
            cap.release()
        selected=[]
        for q,r in sorted(pool,key=lambda v:-v[0]):
            if all(abs(r["frame"]-s["frame"])>=5 for s in selected):
                selected.append(r)
            if len(selected)==5:
                break
        rows.append(dict(name=name,video=video,first=first,last=last,brand_truth=brand,
                         selected=sorted(selected,key=lambda r:r["frame"])))
    save(out/"extra.json",rows)

def tile(im,ds,policy,target,caption):
    im=im.copy()
    for d in ds:
        if d["owned"] and accepted([d],policy):
            x,y,X,Y=np.rint(d["box"]).astype(int)
            cv2.rectangle(im,(x,y),(X,Y),(30,210,80),2)
            cv2.putText(im,d["brand"],(x,max(14,y-3)),0,.48,(60,230,100),1)
    x,y,X,Y=target
    zoom=im[y:Y,x:X]
    view=np.zeros((250,420,3),np.uint8)
    h,w=zoom.shape[:2]
    scale=min(420/w,220/h)
    small=cv2.resize(zoom,(max(1,round(w*scale)),max(1,round(h*scale))))
    top=(220-small.shape[0])//2
    left=(420-small.shape[1])//2
    view[top:top+small.shape[0],left:left+small.shape[1]]=small
    cv2.putText(view,caption,(4,241),0,.5,(255,255,255),1)
    return view

def compare(args):
    if (args.output/"comparison.mp4").exists() or (args.output/"results.json").exists():
        raise FileExistsError("기존 실차 평가를 보존하려면 새 결과 폴더에서 prepare를 실행하세요.")
    args.output.mkdir(parents=True,exist_ok=True)
    policy=read_policy(args.policy,args.weights)
    detector=YOLO(str(args.weights))
    vehicles=YOLO(str(ROOT/"yolo26n.pt"))
    net,ck=restore(ROOT/"output/compcars_brand/train/best.pt")
    original=read(BASE/"drive_results.json")["cases"]
    extra=read((args.prepared or args.output)/"extra.json")
    results=[]
    movie=cv2.VideoWriter(str(args.output/"comparison.mp4"),cv2.VideoWriter_fourcc(*"mp4v"),2,(840,250))
    if not movie.isOpened():
        raise OSError("MP4 열기 실패")
    try:
        for ix,r in enumerate(original+extra):
            group="prior12" if ix<len(original) else "new"
            cap=cv2.VideoCapture(str(ROOT/"videos"/r["video"]))
            views=[]
            crops=[]
            records=[]
            states={k:TargetBrand() for k in ("full","crop")}
            try:
                for s in r["selected"]:
                    cap.set(1,s["frame"]-1)
                    ok,im=cap.read()
                    if not ok:
                        raise RuntimeError(r["video"])
                    a,b,c,d=np.maximum(np.rint(s["box"]).astype(int),0)
                    target=[int(v) for v in (a,b,c,d)]
                    crop=im[b:d,a:c]
                    crops.append(crop.copy())
                    if group=="prior12":
                        saved=cv2.imdecode(np.fromfile(BASE/s["file"],np.uint8),1)
                        if not np.array_equal(crop,saved):
                            raise ValueError("059 원본 crop 불일치")
                    cars=vehicles.predict(im,classes=[2,3,5,7],conf=.1,device=0,verbose=False)[0].boxes.xyxy.cpu().tolist()
                    # 원래 타깃에 해당하는 상자 한 개만 제거합니다. 겹치는 이웃 차량은 검사를 유지합니다.
                    closest=max(range(len(cars)),key=lambda i:iou(cars[i],target),default=None)
                    if closest is not None and iou(cars[closest],target)>=.5:
                        cars.pop(closest)
                    record=dict(frame=s["frame"],time=s["time"],track_id=s["track_id"],target=target,other_boxes=cars)
                    pair=[]
                    for mode in ("full","crop"):
                        ds,labels=inspect_target(detector,im,target,cars,policy,crop=mode=="crop")
                        state=states[mode].update(r["name"],s["frame"],labels)
                        record[mode]=dict(detections=ds,frame_labels=sorted(labels),display=state)
                        pair.append(tile(im,ds,policy,target,f"{mode}  {r['name']}  F{s['frame']}  {state}"))
                    view=np.hstack(pair)
                    views.append(view)
                    movie.write(view)
                    records.append(record)
            finally:
                cap.release()
            if group=="prior12":
                raw=r["raw"]
                mobile=r["display"]
                mobile_score=r["confidence"]
                votes=r["agreeing_frames"]
            else:
                probs,_=predict_crops(net,ck,crops)
                mean=probs.mean(0)
                k=int(mean.argmax())
                raw=ck["classes"][k]
                mobile_score=float(mean[k])
                votes=int((probs.argmax(1)==k).sum())
                clear=sum(im.shape[1]>=96 and im.shape[0]>=45 for im in crops)
                mobile=raw if mobile_score>=ck["threshold"] and votes>=.8*len(crops) and clear>=3 else "-"
            res=dict(group=group,name=r["name"],video=r["video"],truth=r["brand_truth"],mobile=mobile,mobile_top=raw,
                     mobile_confidence=mobile_score,mobile_agreeing_frames=votes,
                     full=states["full"].brand,crop=states["crop"].brand,
                     fusion=fuse(states["crop"].brand,mobile),weak_agreement=fuse(states["crop"].brand,raw),frames=records)
            results.append(res)
            save(args.output/"results.json",results)
            if views:
                cv2.imencode(".jpg",np.vstack(views))[1].tofile(args.output/(r["name"]+".jpg"))
    finally:
        movie.release()

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("stage",choices=["prepare","compare"])
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--prepared",type=Path,help="동일 프레임을 비교할 때 기존 prepare 결과를 재사용")
    p.add_argument("--policy",type=Path)
    p.add_argument("--weights",type=Path)
    args=p.parse_args()
    if args.stage=="prepare":
        prepare(args.output)
    else:
        if args.weights is None or args.policy is None:
            p.error("compare에는 --weights와 --policy가 필요합니다.")
        compare(args)
