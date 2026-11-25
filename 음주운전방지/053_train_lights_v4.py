# 053  기존 YOLO26n으로 차량 등화 상태 학습하기
# 052에서 분리한 데이터와 프로젝트의 사전학습 가중치를 사용합니다.
# 좌우 반전과 색상 증강을 끄고 640픽셀로 학습한 뒤 검증 점수로 모델을 고릅니다.
# 새 실행 폴더의 best.pt와 검증 결과를 054의 독립 영상 실습에서 읽습니다.
import argparse
import json
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.environ["YOLO_OFFLINE"] = "true"
os.environ["YOLO_CONFIG_DIR"] = str(ROOT / "output/roboflow_v4/config")
os.environ["WANDB_MODE"] = "disabled"
os.environ["MPLBACKEND"] = "Agg"

import torch
from ultralytics import YOLO


def train(args):
    out = args.output.resolve()
    if out.exists():
        raise FileExistsError(f"새 출력 경로를 지정하세요: {out}")
    if not torch.cuda.is_available() or not args.weights.is_file() or not args.data.is_file():
        raise RuntimeError("CUDA, 로컬 가중치, 052 데이터 경로를 확인하세요.")
    torch.set_num_threads(4)
    model = YOLO(str(args.weights))
    def record_epoch(trainer):
        box=trainer.validator.metrics.box
        if len(box.f1):
            with (out/"epoch_f1.jsonl").open("a",encoding="utf-8") as log:
                log.write(json.dumps(dict(epoch=trainer.epoch+1,macro_f1=float(box.f1.mean())))+"\n")
    model.add_callback("on_model_save",record_epoch)
    start = time.perf_counter()
    model.train(data=str(args.data.resolve()), project=str(out.parent), name=out.name, exist_ok=True,
                epochs=args.epochs, batch=args.batch, imgsz=640, device=0, workers=0,
                optimizer="AdamW", lr0=.001, seed=52, patience=0, warmup_epochs=min(1,args.epochs/5),
                fliplr=0, flipud=0, hsv_h=0, hsv_s=0, hsv_v=0, bgr=0, mosaic=0, close_mosaic=0,
                mixup=0, cutmix=0, copy_paste=0, scale=0, translate=0, augmentations=[],
                plots=True, cache=False, verbose=False)
    elapsed = time.perf_counter()-start
    # best.pt를 다시 읽어 선택된 모델의 클래스별 점수와 혼동행렬을 별도 저장합니다.
    best=YOLO(str(out/"weights/best.pt"))
    result=best.val(data=str(args.data.resolve()),split="val",imgsz=640,batch=args.batch,device=0,
                    workers=0,project=str(out),name="best_valid",plots=True,verbose=False)
    box=result.box
    classes={}
    for k,c in enumerate(box.ap_class_index):
        classes[result.names[int(c)]]=dict(precision=float(box.p[k]),recall=float(box.r[k]),f1=float(box.f1[k]),
                                         map50=float(box.ap50[k]),map50_95=float(box.ap[k]))
    summary=dict(gpu=torch.cuda.get_device_name(0),epochs=args.epochs,batch=args.batch,train_seconds=elapsed,
                 precision=float(box.mp),recall=float(box.mr),macro_f1=float(box.f1.mean()),
                 map50=float(box.map50),map50_95=float(box.map),by_class=classes,
                 gt_per_class=result.nt_per_class.tolist(),confusion=result.confusion_matrix.matrix.tolist())
    (out/"best_valid_metrics.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print("검증 결과 저장",out,"초",round(elapsed,1))


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--data",type=Path,required=True)
    parser.add_argument("--weights",type=Path,default=ROOT/"yolo26n.pt")
    parser.add_argument("--epochs",type=int,default=20)
    parser.add_argument("--batch",type=int,default=8)
    parser.add_argument("--output",type=Path,required=True)
    train(parser.parse_args())
