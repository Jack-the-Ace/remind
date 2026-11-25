# 056  흰 승용차의 차선 이동과 후미등 관측 구간을 대조합니다.
# 입력은 055의 흰 차 결과, 원본 영상과 640 차선 가중치입니다.
# 두 경계를 각각 따라가며 034의 행동 판정과 원본에서 읽은 시간 범위를 따로 저장합니다.
# 출력은 실험용 JSON입니다. 같은 이동은 한 번만 세며 HUD에 값을 보내지 않습니다.
import argparse
import csv
import json
import math
from collections import Counter
from importlib import import_module
from pathlib import Path

import cv2
import numpy as np
import torch
from ultralytics import YOLO

from preview_lane_track_197 import load_lane_model, predict_lane, track_vehicles

ROOT=Path(__file__).resolve().parent
lane=import_module("034_detect_lane_crossing_197")


def check_lamps(rows,patterns,start,end,direction,fps):
    # 한 프레임의 소등은 증거가 아닙니다. 이동 전 2초와 이동 뒤 0.5초도 함께 확인합니다.
    first=start-math.ceil(2*fps);last=end+math.ceil(.5*fps)
    section=[r for r in rows if first<=int(r["frame"])<=last]
    usable=[r for r in section if all(r.get(s+"_valid")=="True" for s in ("left","right"))]
    result=dict(first=first,last=last,available=len(section),usable=len(usable),status="unknown")
    matches=[p for p in patterns["patterns"] if p["last"]>=first and p["first"]<=end]
    if matches and all(p["kind"] in (direction+"_indicator","brake+"+direction+"_indicator") for p in matches):
        # 점멸이 해당 차선 이동 가까이 이어졌을 때만 사용하는 방향과 연결합니다.
        maneuver=[r for r in usable if start<=int(r["frame"])<=end]
        if any(p["last"]>=start-math.ceil(fps) for p in matches) and len(maneuver)==end-start+1:
            result["status"]="used";return result
    if matches:
        result["reason"]="direction or coverage unclear";return result
    if len(usable)!=last-first+1:
        result["reason"]="insufficient continuous bilateral view";return result
    # 양쪽의 적색·황색 세기와 상대 밝기가 모두 안정해야 미사용을 검토합니다.
    for side in ("left","right"):
        for channel,limit in (("amber",15),("red",24),("relative",24),("green_contrast",28)):
            a=np.array([float(r[side+"_"+channel]) for r in usable])
            if np.ptp(a)>limit:
                result["reason"]="unresolved light or exposure changes";return result
    result["status"]="unused"
    return result


def route(events,key,label,light):
    if key in events:return
    if label=="차선침범": text,color="차선침범","red"
    elif label=="차선변경" and light=="used":text,color="차선변경","green"
    elif label=="차선변경" and light=="unused":text,color="지시등위반","red"
    else:return
    events[key]=dict(label=text,color=color,floating=f"+{text}1")


def rules_check():
    result={}
    for key,label,light in [(1,"차선변경","used"),(2,"차선변경","unused"),(2,"차선변경","used"),
                             (3,"차선변경","unknown"),(4,"차선침범","unknown")]:
        route(result,key,label,light)
    assert [e["label"] for e in result.values()]==["차선변경","지시등위반","차선침범"]
    return result


def comparison(root):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(5,1,figsize=(12,12),layout="constrained")
    settings=[
        ("junction","Brake release | three red lamps","red",("left","right","center")),
        ("truckpass","Moving truck | right indicator","relative",("left","right")),
        ("cabref","Stationary car | manually registered reference","green_contrast",("left","right")),
        ("kialong","SUV | lower lamp vs central brake","green_contrast",("left","right","center")),
        ("white","White sedan | shaded ranges = visually reviewed lane crossings","relative",("left","right"))]
    for ax,(case,title,channel,sides) in zip(axes,settings):
        with (root/case/"analysis/frames.csv").open(encoding="utf-8-sig") as stream:
            rows=list(csv.DictReader(stream))
        t=[float(r["time"]) for r in rows]
        signals=json.loads((root/case/"analysis/patterns.json").read_text(encoding="utf8"))
        fps=signals["fps"]
        for side,color in zip(sides,("#1767a6","#c64d00","#518144")):
            y=[float(r[side+"_"+channel]) if r.get(side+"_valid")=="True" else np.nan for r in rows]
            ax.plot(t,y,color=color,label=side)
        for i,(first,last) in enumerate(signals["brake_intervals"]):
            ax.axvspan((first-1)/fps,last/fps,color="#9880b3",alpha=.17,label=None if i else "brake")
        for event in signals["patterns"]:
            side="left" if "left" in event["kind"] else "right"
            for group in signals["flashes"][side]:
                if group["first"]!=event["first"] or group["channel"]!=event["channel"]:continue
                for i,pulse in enumerate(group["pulses"]):
                    ax.axvspan((pulse["first"]-1)/fps,pulse["last"]/fps,color="#e2ad49",
                               alpha=.18,label=None if i else "lamp pulse")
        if case=="white":
            for ref in json.loads((root/case/"analysis/lanes.json").read_text(encoding="utf8"))["human_reference"]:
                ax.axvspan(*ref["seconds"],color="#939393",alpha=.22)
        ax.set_xlim(t[0],t[-1]);ax.set_title(title,loc="left");ax.grid(alpha=.22);ax.legend(ncols=3)
        ax.set_ylabel(channel);ax.set_xlabel("Original video time (s)")
    fig.savefig(root/"brake_vs_blink.png",dpi=145);plt.close(fig)
    # 실제 기록을 복사해 좌우 대칭인 경우만 따로 시험합니다. 원본 영상의 비상등 사례로 세지 않습니다.
    from rear_lamp_patterns import evidence
    truck=root/"truckpass"
    fps=json.loads((truck/"track.json").read_text(encoding="utf8"))["fps"]
    with (truck/"analysis/frames.csv").open(encoding="utf-8-sig") as stream:
        source=list(csv.DictReader(stream))
    mirror=[]
    for r in source:
        item={"frame":int(r["frame"])}
        for k,v in r.items():
            if not k.startswith("right_") or not v or k.endswith("_reason"):continue
            value=(v=="True") if k.endswith("_valid") else float(v)
            item[k]=item[k.replace("right_","left_",1)]=value
        mirror.append(item)
    cloned=evidence(mirror,fps)["patterns"]
    assert any(p["kind"]=="hazards" for p in cloned)
    # 충분히 보이는 일정한 램프 / 관측 한 장이 사라진 경우도 구분해야 합니다.
    quiet=[]
    for f in range(1,151):
        r={"frame":str(f)}
        for s in ("left","right"):
            for key in ("red","amber","relative","green_contrast"):r[s+"_"+key]="5"
            r[s+"_valid"]="True"
        quiet.append(r)
    clean=check_lamps(quiet,{"patterns":[]},80,110,"left",30)
    quiet[65]["left_valid"]="False"
    gap=check_lamps(quiet,{"patterns":[]},80,110,"left",30)
    assert clean["status"]=="unused" and gap["status"]=="unknown"
    checks=dict(source="copied_or_synthetic_only",hazards=cloned,quiet=clean,gap=gap,route=rules_check())
    (root/"rule_checks.json").write_text(json.dumps(checks,ensure_ascii=False,indent=1),encoding="utf8")


def verify(dest):
    data=json.loads((dest/"track.json").read_text(encoding="utf8"))
    patterns=json.loads((dest/"analysis/patterns.json").read_text(encoding="utf8"))
    with (dest/"analysis/frames.csv").open(encoding="utf-8-sig") as stream: rows=list(csv.DictReader(stream))
    # 좌표는 첫 프레임에 보이는 서로 다른 점선에서 골랐습니다. 이후 프레임은 모델로 갱신합니다.
    if data["video"]=="지시등위반1.mp4":
        seeds=[(679,598,804,663),(379,678,531,595)]
        reference=[(46,65,"left"),(190,240,"left")]
    elif data["video"]=="BB_20261123_134949.avi" and data["rows"][0]["frame"]==116:
        seeds=[(747,903,832,848)]
        reference=[(145,190,"right")]
    else:raise ValueError("이 장면은 원본에서 기준 경계와 판독 범위를 먼저 확인하세요.")
    model=load_lane_model(lane.DEFAULT_MODEL,torch.device("cuda:0"))
    yolo=YOLO(str(ROOT/"yolo26n.pt"));ids=[k for k,v in yolo.names.items() if v in ("car","bus","truck","motorcycle")]
    timing=(torch.cuda.Event(enable_timing=True),torch.cuda.Event(enable_timing=True))
    cap=cv2.VideoCapture(str(ROOT/"videos"/data["video"]));fps=data["fps"]
    cap.set(cv2.CAP_PROP_POS_FRAMES,data["rows"][0]["frame"]-1)
    scale=np.array([640/cap.get(3),400/cap.get(4)])
    states=[(lane.Boundary(seed*np.tile(scale,2)),lane.LaneBehavior(fps)) for seed in seeds]
    counts=[Counter() for _ in seeds];log=[];auto=[];events={}
    try:
        for row in data["rows"]:
            ok,im=cap.read()
            if not ok:raise OSError("원본 읽기 실패")
            f=row["frame"]
            mask,_=predict_lane(model,im,torch.device("cuda:0"),lane.SIZE,timing)
            cars=track_vehicles(yolo,im,ids,0)
            boxes=[np.array(c["box"])*np.tile(scale,2) for c in cars]
            if row["box"]:boxes.append(np.array(row["box"])*np.tile(scale,2))
            for n,(boundary,behavior) in enumerate(states,1):
                side=distance=None;status="tracking_hold"
                if row["box"]:
                    x,y,X,Y=row["box"];support=boundary.detect(mask,boxes)
                    status="boundary_missing"
                    if support is not None:
                        side,distance,status=boundary.classify(np.array([(x+X)/2,Y])*scale,support,boxes)
                event=behavior.update(f,side,status,distance)
                counts[n-1][status]+=1
                log.append(dict(frame=f,boundary=n,status=status,side=side,distance=distance))
                if event:
                    start=event["maneuver_start_frame"]
                    light=check_lamps(rows,patterns,start,f,event["to_side"],fps)
                    route(events,f'{n}-{start}',event["label"],light["status"])
                    auto.append(dict(boundary=n,**event,light=light))
    finally:cap.release()
    # 이 구간은 사람이 원본에서 전후 위치를 대조한 범위입니다. 자동 판정에 주입하지 않습니다.
    human=[]
    for start,end,direction in reference:
        light=check_lamps(rows,patterns,start,end,direction,fps)
        joined={}
        route(joined,str(start),"차선변경",light["status"])
        human.append(dict(first=start,last=end,seconds=[(start-1)/fps,(end-1)/fps],direction=direction,
                          light=light,reviewed_lane_plus_measured_lamp=joined))
    output=dict(seeds=seeds,human_reference=human,auto_behavior=auto,display_events=events,
                boundary_status=counts,synthetic_route_test=rules_check())
    for file,obj in [("lanes.json",output),("lane_frames.json",log)]:
        (dest/"analysis"/file).write_text(json.dumps(obj,indent=1,ensure_ascii=False),encoding="utf8")


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    modes=parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--case-dir",type=Path);modes.add_argument("--compare",type=Path)
    args=parser.parse_args()
    if args.case_dir:verify(args.case_dir)
    else:comparison(args.compare)
