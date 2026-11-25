# 059  같은 차의 여러 후면 사진에서 브랜드와 트렁크 글자를 따로 읽습니다.
# 블랙박스 원본과 058 체크포인트를 사용합니다. 055 추적 결과를 재사용하거나 새로 추적합니다.
# 선명한 프레임을 고르고 프레임별 확률·보류 이유·OCR 원문을 남겨 사람이 확인합니다.
import argparse
from collections import Counter
from importlib import import_module
import json
from pathlib import Path
import re
import cv2
import numpy as np
from redbox_brand import restore,predict_crops,letterbox
from redbox_vehicle_info import WindowsOCR

ROOT=Path(__file__).resolve().parent
# 예측을 보기 전에 원본 엠블럼·레터링을 확인했습니다. null은 정확도 분모에서 제외합니다.
CASES=[
 ("junction","BB_20261123_133631.avi",930,1200,1030,750,"Hyundai","TUCSON"),
 ("sun","BB_20261122_141908.avi",1,175,1010,760,"BMW",None),
 ("merge","BB_20261123_121651.avi",1,140,600,800,"Volkswagen",None),
 ("leftsedan","BB_20261123_100656.avi",1,170,575,790,"Hyundai","SONATA"),
 ("kia_suv","BB_20261122_172259.avi",991,1070,1380,743,"Kia",None),
 ("genesis_sedan","BB_20261122_172259.avi",271,350,1490,755,"Genesis",None),
 ("genesis_ev","BB_20261123_150759.avi",271,335,748,747,"Genesis",None),
 ("hyundai_truck","BB_20261123_102613.avi",331,395,1266,715,"Hyundai",None),
 ("night","음주운전1.mp4",225,340,635,260,None,None),
 ("garage","BB_20261122_171859.avi",1013,1218,932,733,None,None),
 ("white","지시등위반1.mp4",1,270,1040,610,"Mercedes-Benz",None),
]
BADGES={"TUCSON","SONATA","K5","AVANTE","520I","E300","G80","GV60","A6","TIGUAN",
        "PASSAT","SORENTO","CARNIVAL","SANTAFE","GRANDEUR","KONA","SPORTAGE","520D","E220","RAY"}

def save(path,obj):path.write_text(json.dumps(obj,ensure_ascii=False,indent=1),encoding="utf8")

def prepare(out):
    out.mkdir(parents=True,exist_ok=False)
    tracking=import_module("055_measure_rear_lamps")
    review=[]
    for name,video,first,last,x,y,brand,badge in CASES:
        dest=out/name;dest.mkdir()
        previous=ROOT/"output/lamp_cv/experiment"/name/"track.json"
        info=json.loads(previous.read_text(encoding="utf8")) if previous.exists() else {}
        if info.get("video")==video and info["rows"][0]["frame"]==first and info["rows"][-1]["frame"]==last:
            source="055 stored target"
        else:
            source="055 new target"
            try:tracking.track(dict(video=video,frames=[first,last],select=[x,y]),dest,False)
            except ValueError as e:
                review.append(dict(name=name,video=video,error=str(e)));continue
            info=json.loads((dest/"track.json").read_text(encoding="utf8"))
        cap=cv2.VideoCapture(str(ROOT/"videos"/video));cap.set(1,first-1)
        options=[]
        try:
            for r in info["rows"]:
                ok,frame=cap.read()
                if not ok:raise RuntimeError(f"{video} F{r['frame']} 읽기 실패")
                if not r["box"]:continue
                x1,y1,x2,y2=np.rint(r["box"]).astype(int);im=frame[max(0,y1):y2,max(0,x1):x2]
                if min(im.shape[:2])<8:continue
                gray=cv2.cvtColor(cv2.resize(im,(128,96)),cv2.COLOR_BGR2GRAY)
                # 같은 영상 구간 안에서 해상도와 윤곽 선명도를 함께 비교합니다.
                quality=np.log1p(cv2.Laplacian(gray,cv2.CV_32F).var())*min(1,im.shape[1]/200)
                options.append((float(quality),r,im.copy()))
        finally:cap.release()
        windows=[(name,first,last)] if name!="white" else [("white_near",1,75),("white_far",190,270)]
        for key,a,b in windows:
            selected=[]
            for q,r,im in sorted(options,key=lambda item:-item[0]):
                f=r["frame"]
                if a<=f<=b and all(abs(f-row["frame"])>=5 for row in selected):
                    filename=f"{name}/F{f}.png";cv2.imencode(".png",im)[1].tofile(out/filename)
                    selected.append(dict(**r,file=filename,width=im.shape[1],height=im.shape[0],sharpness=q))
                    if len(selected)==5:break
            review.append(dict(name=key,video=video,first=a,last=b,brand_truth=brand,model_truth=badge,
                tracking_source=source,tracked=sum(a<=r["frame"]<=b and bool(r["box"]) for r in info["rows"]),
                selected=sorted(selected,key=lambda r:r["frame"])))
    save(out/"review.json",review)

def read_badges(reader,windows,im):
    # 번호판 전용 글자 제한을 풀어 기존 로컬 OCR 엔진으로 뒤쪽 글씨를 읽습니다.
    h,w=im.shape[:2];ans=[]
    if w<96 or h<45:return ans
    for x,X in ((0,.47),(.53,1),(.27,.73)):
        band=im[int(.32*h):int(.83*h),int(x*w):int(X*w)]
        if not band.size:continue
        gray=cv2.cvtColor(band,cv2.COLOR_BGR2GRAY)
        ans.append(dict(engine="windows",text=windows.read(gray)))
        if reader:
            for _,word,conf in reader.readtext(band,allowlist="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789",
                    mag_ratio=2,min_size=6,text_threshold=.42,low_text=.23):
                ans.append(dict(engine="easyocr",text=word,confidence=float(conf)))
    return ans

def infer(args):
    import torch
    net,ck=restore(args.weights);classes=ck["classes"]
    reader,ocr_state=import_module("041_redbox_mvp").ocr()
    windows=WindowsOCR();rows=json.loads((args.output/"review.json").read_text(encoding="utf8"))
    tiles=[]
    try:
        for r in rows:
            samples=r.get("selected",[])
            if not samples:continue
            crops=[cv2.imdecode(np.fromfile(args.output/s["file"],np.uint8),1) for s in samples]
            probs,display=predict_crops(net,ck,crops)
            mean=probs.mean(0);top=int(mean.argmax());votes=int((probs.argmax(1)==top).sum())
            quality=sum(s["width"]>=96 and s["height"]>=45 for s in samples)
            accepted=len(crops)>=3 and votes>=.8*len(crops) and mean[top]>=ck["threshold"] and quality>=3
            r.update(display=classes[top] if accepted else "-",raw=classes[top],confidence=float(mean[top]),
                     agreeing_frames=votes,large_enough=quality,threshold=ck["threshold"])
            tokens=Counter()
            for s,im,pr,one in zip(samples,crops,probs,display):
                s["probabilities"]=dict(zip(classes,pr.tolist()));s["single_threshold_display"]=one
                words=read_badges(reader,windows,im);s["ocr"]=words
                # 모델명 후보는 사전과 정확하게 맞고 여러 프레임에서 반복될 때만 표시합니다.
                hits=set()
                for w in words:
                    line=w["text"].upper()
                    hits.update(BADGES.intersection(re.findall(r"[A-Z0-9]+",line)))
                    if re.sub(r"\s+","",line) in BADGES:hits.add(re.sub(r"\s+","",line))
                tokens.update(hits)
            choices=[w for w,n in tokens.items() if n>=2]
            r["model_display"]=choices[0] if len(choices)==1 else "-"
            r["model_votes"]=dict(tokens)
            panel=np.zeros((170,275,3),np.uint8)
            panel[:130,65:195]=letterbox(crops[len(crops)//2],130)[:,:,::-1]
            cv2.putText(panel,r["name"],(5,144),0,.43,(255,255,255),1)
            cv2.putText(panel,f"{r['brand_truth'] or '?'} > {r['display']} ({r['confidence']:.2f})",(5,162),0,.45,(100,230,255),1)
            tiles.append(panel)
    finally:windows.close()
    save(args.output/"drive_results.json",dict(ocr=ocr_state,classes=classes,cases=rows))
    while len(tiles)%3:tiles.append(np.zeros_like(tiles[0]))
    cv2.imencode(".jpg",np.vstack([np.hstack(tiles[i:i+3]) for i in range(0,len(tiles),3)]))[1].tofile(args.output/"drive_comparison.jpg")

def badge_control(out):
    # 글자 위치를 사람이 짚으면 읽히는지도 따로 시험합니다. 자동 읽기 결과에는 합산하지 않습니다.
    regions={"junction":(.147,.531,.307,.606),"leftsedan":(.09,.422,.322,.51)}
    reader,_=import_module("041_redbox_mvp").ocr()
    windows=WindowsOCR();report=[]
    try:
        for r in json.loads((out/"review.json").read_text(encoding="utf8")):
            if r["name"] not in regions:continue
            x,y,X,Y=regions[r["name"]];votes=Counter();observations=[]
            for s in r["selected"]:
                im=cv2.imdecode(np.fromfile(out/s["file"],np.uint8),0);h,w=im.shape
                roi=im[round(h*y):round(h*Y),round(w*x):round(w*X)]
                words=[windows.read(roi)]
                large=cv2.resize(roi,None,fx=4,fy=4,interpolation=cv2.INTER_CUBIC)
                for variant in (large,cv2.createCLAHE(2,(3,2)).apply(large)):
                    if reader:
                        words+=reader.recognize(variant,allowlist="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789",
                                               detail=0,reformat=False)
                found={re.sub(r"[^A-Z0-9]","",word.upper()) for word in words}&BADGES
                votes.update(found);observations.append(dict(frame=s["frame"],native_size=[roi.shape[1],roi.shape[0]],raw=words))
            report.append(dict(case=r["name"],truth=r["model_truth"],votes=dict(votes),observations=observations))
    finally:windows.close()
    save(out/"badge_control.json",report)

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("stage",choices=("prepare","infer","badge-control"));p.add_argument("--output",type=Path,required=True)
    p.add_argument("--weights",type=Path,default=ROOT/"output/compcars_brand/train/best.pt")
    args=p.parse_args()
    if args.stage=="prepare":prepare(args.output)
    elif args.stage=="infer":infer(args)
    else:badge_control(args.output)
