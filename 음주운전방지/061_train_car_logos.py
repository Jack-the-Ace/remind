# 061  자동차 엠블럼을 찾는 YOLO26n 전이학습입니다.
# 060의 별도 분할과 기존 yolo26n.pt로 시험 한 회전 후 같은 초기 가중치에서 본학습합니다.
# 글자의 좌우 방향을 유지하며, 최적·마지막 모델과 회전별 곡선을 062 평가로 넘깁니다.
import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import time

ROOT=Path(__file__).resolve().parent
os.environ["YOLO_OFFLINE"]="true"
os.environ["YOLO_CONFIG_DIR"]=str(ROOT/"output/emblem_v1/config")
os.environ["WANDB_MODE"]="disabled"
os.environ["MPLBACKEND"]="Agg"
import cv2
import torch
from ultralytics import YOLO

def mild_camera(sample):
    # 확률이 낮은 약한 흐림·JPEG 변환만 적용하고 위치 좌표와 원본 파일은 유지합니다.
    draw=random.random()
    if draw<.07:
        sample["img"]=cv2.GaussianBlur(sample["img"],(3,3),.65)
    elif draw<.14:
        ok,data=cv2.imencode(".jpg",sample["img"],[cv2.IMWRITE_JPEG_QUALITY,random.randint(78,94)])
        if ok:
            sample["img"]=cv2.imdecode(data,cv2.IMREAD_COLOR)
    return sample

def run(args):
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA 필요")
    args.output.mkdir(parents=True,exist_ok=False)
    torch.set_num_threads(4)
    for name,epochs in [("smoke",1),("main",args.epochs)]:
        model=YOLO(str(args.weights))
        def attach(trainer):
            trainer.train_loader.dataset.transforms.transforms.insert(-1,mild_camera)
        model.add_callback("on_train_start",attach)
        t=time.perf_counter()
        model.train(data=str(args.data.resolve()),imgsz=640,device=0,batch=args.batch,workers=0,epochs=epochs,
            project=str(args.output.resolve()),name=name,seed=60,fliplr=0,flipud=0,hsv_v=.13,hsv_s=.05,hsv_h=0,
            mosaic=0,close_mosaic=0,mixup=0,copy_paste=0,cutmix=0,degrees=0,translate=.025,scale=.08,
            augmentations=[],optimizer="AdamW",lr0=.001,patience=6,warmup_epochs=1,cache=False,plots=True,verbose=False)
        out=args.output/name
        for fn in ("best.pt","last.pt"):
            if not (out/"weights"/fn).is_file():
                raise RuntimeError("체크포인트 누락")
        (out/"runtime.json").write_text(json.dumps(dict(seconds=time.perf_counter()-t,gpu=torch.cuda.get_device_name(0),
            peak_mb=torch.cuda.max_memory_allocated()/2**20,initial_sha256=hashlib.sha256(args.weights.read_bytes()).hexdigest(),
            epochs=len((out/"results.csv").read_text().splitlines())-1,batch=args.batch),indent=1),encoding="utf8")
        del model
        torch.cuda.empty_cache()

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--data",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--epochs",type=int,default=30)
    p.add_argument("--batch",type=int,default=16)
    p.add_argument("--weights",type=Path,default=ROOT/"yolo26n.pt")
    run(p.parse_args())
