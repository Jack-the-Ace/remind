# 066  사람이 고른 차량의 램프와 경계 관측을 함께 점검합니다.
# 055의 추적, 197 차선 모델과 056의 점멸 조건을 재사용하고 자동·육안 근거를 분리합니다.
# driving_review_cases.json의 원본 좌표를 읽어 다음 067에 전달할 프레임 기록을 남깁니다.
import argparse
import csv
import json
import hashlib
from collections import Counter
from importlib import import_module
from pathlib import Path
import cv2
import numpy as np
import torch
from ultralytics import YOLO
from rear_lamp_patterns import measure
from preview_lane_track_197 import load_lane_model, predict_lane, track_vehicles

review = import_module("056_verify_lamp_lane_events")
tracker = import_module("055_measure_rear_lamps")
root = Path(__file__).resolve().parent

def run(work, cases):
    device=torch.device("cuda:0")
    net=load_lane_model(review.lane.DEFAULT_MODEL,device)
    ticks=(torch.cuda.Event(enable_timing=True),torch.cuda.Event(enable_timing=True))
    for name,case in cases.items():
        with (root/"videos"/case["video"]).open("rb") as source:
            if hashlib.file_digest(source,"sha256").hexdigest()!=case["source_sha256"]:
                raise ValueError("다른 원본에는 차량과 차선을 다시 선택하세요.")
        folder=work/name
        folder.mkdir(parents=True,exist_ok=True)
        dest=folder/"lane_review.json"
        if dest.exists():
            raise FileExistsError(dest)
        if not (folder/"track.json").exists():
            tracker.track(case,folder,False)
        if not (folder/"analysis/patterns.json").exists():
            measure(case,folder)
        data=tracker.read(folder/"track.json")
        first,last=case["frames"]
        if data["video"]!=case["video"] or [r["frame"] for r in data["rows"]]!=list(range(first,last+1)):
            raise ValueError("추적 로그의 원본 또는 프레임 구간이 다릅니다.")
        patterns=tracker.read(folder/"analysis/patterns.json")
        with (folder/"analysis/frames.csv").open(encoding="utf-8-sig") as f:
            lamps=list(csv.DictReader(f))
        fps=data["fps"]
        cap=cv2.VideoCapture(str(root/"videos"/data["video"]))
        cap.set(1,case["frames"][0]-1)
        scale=np.array([640/cap.get(3),400/cap.get(4)])
        boundary=review.lane.Boundary(np.array(case["seed"])*np.tile(scale,2))
        state=review.lane.LaneBehavior(fps)
        yolo=YOLO(str(root/"yolo26n.pt"))
        ids=[i for i,v in yolo.names.items() if v in ("car","motorcycle","truck","bus")]
        rows=[]
        events=[]
        try:
            for row in data["rows"]:
                ok,im=cap.read()
                if not ok:raise OSError(data["video"])
                cars=track_vehicles(yolo,im,ids,0)
                boxes=[np.array(c["box"])*np.tile(scale,2) for c in cars]
                mask,_=predict_lane(net,im,device,review.lane.SIZE,ticks)
                status="tracking_hold"
                side=distance=support=None
                if row["box"]:
                    x,y,X,Y=row["box"]
                    boxes.append(np.array(row["box"])*np.tile(scale,2))
                    support=boundary.detect(mask,boxes)
                    status="boundary_missing"
                    if support is not None:
                        side,distance,status=boundary.classify(np.array([(x+X)/2,Y])*scale,support,boxes)
                f=row["frame"]
                seconds=review.lane.source_seconds(cap,f,fps)
                endpoints=boundary.endpoints(support,scale)
                for result in state.observe(f,seconds,row["box"],endpoints,status):
                    light=review.check_lamps(lamps,patterns,result["maneuver_start_frame"],f,result["to_side"],fps)
                    events.append(dict(frame=f,behavior=result,light=light))
                rows.append(dict(frame=f,seconds=seconds,status=status,side=side,distance=distance,
                                 boundary=endpoints,box=row["box"],track_id=row["track_id"]))
        finally:
            cap.release()
        a,b,side=case["reference"]
        light=review.check_lamps(lamps,patterns,a,b,side,fps)
        tracker.save(dest,dict(lane_rule_version=review.lane.LANE_RULE_VERSION,auto=events,reference=case["reference"],lamp_at_reference=light,
                               statuses=dict(Counter(r["status"] for r in rows)),frames=rows))
        print(name,events,light,flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--work",type=Path,required=True)
    run(p.parse_args().work,tracker.read(root/"driving_review_cases.json"))

