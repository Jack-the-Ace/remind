# 070  멀리 있는 선택 차량의 추적과 차선 판독을 따로 검증합니다.
# 원본에서 고른 차량 한 점과 오른쪽 흰 경계를 사용합니다. 이후에는 매 프레임 모델 결과를 읽습니다.
# 전체 화면과 도로 확대 추적을 비교하고, 원본 화소와 차선 근거를 확인해 HUD와 기록을 만듭니다.
import argparse
from collections import Counter
from importlib import import_module
import json
from pathlib import Path

import cv2
import numpy as np
import torch
from ultralytics import YOLO
from PIL import Image

from redbox_lane_geometry import ShortTargetMatch
from track_preview import Target, video_digest
from preview_lane_track_197 import load_lane_model, predict_lane, track_vehicles

mvp = import_module("041_redbox_mvp")
lane = mvp.crossing_module
review = import_module("067_render_driving_review")
ROOT = Path(__file__).resolve().parent
VIDEO = ROOT / "videos/졸음운전3.mp4"
DIGEST = "b8c06d6cb5483c0ebf4d2cf23e887185fa2da4f55b30fb0a372380aaeff6c868"
DEFAULT = ROOT / "output/mvp_review_far"
NAME = "08_원거리_타깃_분석.mp4"
SELECT = (656, 558)
ROAD = (580, 505, 740, 601)
LANE_ROAD = (320, 455, 960, 684)
SEED = (700, 584, 812, 678)


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path, value):
    with path.open("x",encoding="utf-8") as file:
        json.dump(value,file,ensure_ascii=False,indent=1,allow_nan=False)


def track_one(model, target, image, roi, frame):
    x,y,X,Y = roi
    cars = track_vehicles(model,image[y:Y,x:X], [2,3,5,7],0)
    for car in cars:
        car["box"] = (np.asarray(car["box"]) + [x,y,x,y]).tolist()
    if frame == 1:
        choices = [d for d in cars if d["id"] is not None and d["box"][0] <= SELECT[0] <= d["box"][2]
                   and d["box"][1] <= SELECT[1] <= d["box"][3]]
        if choices:
            car = mvp.select_vehicle(choices,SELECT)
            target.select(car,image,frame)
            return car,cars
    return target.update(cars,image,frame),cars


def analyze(out):
    if video_digest(VIDEO) != DIGEST:
        raise ValueError("선택 차량과 기준선을 지정한 원본과 다릅니다.")
    device = torch.device("cuda:0")
    model = load_lane_model(lane.DEFAULT_MODEL,device)
    timing = tuple(torch.cuda.Event(enable_timing=True) for _ in range(2))
    detectors = [YOLO(str(ROOT/"yolo26n.pt")) for _ in range(2)]
    targets = [Target(),Target()]
    x,y,X,Y = LANE_ROAD
    origin = np.array([x,y])
    scale = np.array(lane.SIZE)/[X-x,Y-y]
    boundary = lane.Boundary(((np.array(SEED).reshape(2,2)-origin)*scale).ravel())
    cap = cv2.VideoCapture(str(VIDEO))
    w,h,n,fps = [cap.get(k) for k in (3,4,7,5)]
    rows = []
    try:
        for f in range(1,int(n)+1):
            ok,image = cap.read()
            if not ok:
                raise OSError(f"F{f} 원본 읽기 오류")
            # 두 추적기는 같은 첫 프레임의 같은 점을 선택합니다. 서로의 ID와 상태를 공유하지 않습니다.
            whole,wide = track_one(detectors[0],targets[0],image,(0,0,int(w),int(h)),f)
            vehicle,local = track_one(detectors[1],targets[1],image,ROAD,f)
            mask,_ = predict_lane(model,image[y:Y,x:X],device,lane.SIZE,timing)
            boxes = [(np.asarray(c["box"])-np.tile(origin,2))*np.tile(scale,2) for c in wide+local]
            support = boundary.detect(mask,boxes)
            endpoints = boundary.endpoints(support,scale)
            if endpoints is not None:
                endpoints = (np.asarray(endpoints)+origin).tolist()
            box = vehicle["box"] if vehicle else None
            status = "tracking_hold" if box is None else "boundary_missing"
            gap = None
            if box and support is not None:
                point = (np.array([(box[0]+box[2])/2,box[3]])-origin)*scale
                _,_,status = boundary.classify(point,support,boxes)
                gap = float(np.min(np.abs(support-point[1]))/scale[1])
            # 후반에 새로 들어오는 차와 원래 상자를 비교할 수 있도록 주변 검출도 보관합니다.
            rows.append(dict(frame=f,seconds=lane.source_seconds(cap,f,fps),box=box,
                             track_id=vehicle["id"] if vehicle else None,wide_target=whole,boundary=endpoints,
                             lane_observation=status,support_gap_px=gap,other_boxes=wide+local))
    finally:
        cap.release()
    save(out/"observations.json",dict(source_sha256=DIGEST,video=VIDEO.name,source_size=[int(w),int(h)],
                                      fps=fps,selection=SELECT,track_roi=ROAD,lane_roi=LANE_ROAD,
                                      seed=SEED,frames=rows))


def spans(rows, key, fps):
    from itertools import groupby
    answer=[]
    for value, group in groupby(rows,key):
        part=list(group)
        answer.append(dict(state=value,first=part[0]["frame"],last=part[-1]["frame"],
                           start_s=part[0]["seconds"],end_s_exclusive=part[-1]["seconds"]+1/fps))
    return answer


def compose(source,row,events):
    # 공통 HUD를 투명하게 그린 뒤 글자·상자가 있는 화소만 원본에 합성합니다.
    layer=mvp.draw_hud(source,row,"recorded",overlay_only=True)
    mvp.draw_event_floats(layer,events,row["seconds"])
    rgba=np.asarray(layer.resize((source.shape[1],source.shape[0]),Image.Resampling.BILINEAR))
    y,x=np.nonzero(rgba[:,:,3])
    alpha=rgba[y,x,3,None].astype(np.uint16)
    out=source.copy()
    out[y,x]=(rgba[y,x,2::-1].astype(np.uint16)*alpha+source[y,x].astype(np.uint16)*(255-alpha)+127)//255
    return out


def controlled():
    # 실제 영상에 없는 '기록 후 판독 공백, 같은 차의 복귀'도 동일한 게이트로 시험합니다.
    def simulate(states):
        gate=lane.LaneReadability(30)
        events=[]
        for i,(position,raw) in enumerate(states):
            box={"left":[0,0,8,20],"contact":[5,0,15,20]}[position]
            found,state=gate.update(i+1,i/30,box,[[10,0],[10,30]],"observed",raw)
            assert not found or (state["counting"] and state["notice"]=="ready")
            events.extend(found)
        return [e["frame"] for e in events]
    left=("left","ready")
    touch=("contact","ready")
    observations=[left]*12+[touch]*55+[("contact","small")]*21+[touch]*46+[left]*12
    result=simulate(observations)
    assert result==[58,134], result
    short=simulate([left]*12+[touch]*12+[left]*12)
    exact=simulate([left]*12+[touch]*90+[left]*12)
    assert short==[25] and exact==[58,103]
    return dict(pause_resume_frames=result,first_contact_after_gap=89,short_return_frames=short,
                three_seconds_and_return_frames=exact)


def verify_saved(path,rows,events,fps):
    # 저장본 자체에서 대상을 찾는 표시, 두 가지 안내, 타깃 상자와 TOTAL을 대조합니다.
    cap=cv2.VideoCapture(str(path))
    source=cv2.VideoCapture(str(VIDEO))
    probes={1,len(rows),*range(1,len(rows)+1,30),*range(1071,len(rows)+1,4)}
    for event in events:
        probes.update(f for off in (-1,0,15,30,45,60,61) if 1<=(f:=event["frame"]+off)<=len(rows))
    for prev,cur in zip(rows,rows[1:]):
        if prev["lane_readability"]["notice"]!=cur["lane_readability"]["notice"]:
            probes.update([prev["frame"],cur["frame"]])
    checks=[]
    try:
        for f in sorted(probes):
            cap.set(1,f-1)
            source.set(1,f-1)
            ok,saved=cap.read()
            good,raw=source.read()
            if not ok or not good:
                raise ValueError(f"F{f} 탐색 실패")
            row=rows[f-1]
            notice=row["lane_readability"]["notice"]
            arrived=[e for e in events if e["frame"]<=f]
            expected=compose(raw,row,arrived)
            def compare(variant,region):
                alt=compose(raw,variant,arrived)[region].astype(np.int16)
                wanted=expected[region].astype(np.int16)
                encoded=saved[region].astype(np.int16)
                mask=np.max(np.abs(wanted-alt),axis=2)>55
                if not mask.any():
                    raise ValueError(f"F{f} 대조 화소 없음")
                right=float(np.abs(encoded[mask]-wanted[mask]).mean())
                wrong=float(np.abs(encoded[mask]-alt[mask]).mean())
                if right+4>=wrong:
                    raise ValueError(f"F{f} 저장된 HUD 불일치 {right:.1f} / {wrong:.1f}")
                return round(wrong-right,2)
            other="unclear" if notice in {"small","search","ready","checking"} else "small"
            mistaken=dict(row,lane_readability=dict(row["lane_readability"],notice=other))
            label=compare(mistaken,np.s_[500:640,:560])
            counts=dict(row["event_counts"])
            counts["차선침범"]=counts.get("차선침범",0)+1
            total=compare(dict(row,event_counts=counts),np.s_[55:142,790:])
            draw_box=row["box"] and notice!="search" and row["lane_readability"]["raw"]!="search"
            altbox=None if draw_box else [631,546,651,566]
            alternative=dict(row,box=altbox,lane_readability=dict(row["lane_readability"],notice="ready",raw="ready"))
            target=compare(alternative,np.s_[485:601,580:755])
            checks.append(dict(frame=f,notice=notice,label_pixel_margin=label,total_pixel_margin=total,
                               box_pixel_margin=target))
    finally:
        cap.release()
        source.release()
    return checks


def render(out):
    from tempfile import TemporaryDirectory
    analysis=read(out/"observations.json")
    if video_digest(VIDEO)!=DIGEST or analysis["source_sha256"]!=DIGEST or tuple(analysis["track_roi"])!=ROAD:
        raise ValueError("원본 또는 추적 설정 불일치")
    rows=analysis["frames"]
    fps=analysis["fps"]
    size=tuple(analysis["source_size"])
    video=out/NAME
    proof=out/"08_원거리_검증.json"
    if video.exists() or proof.exists():
        raise FileExistsError("결과를 저장할 새 폴더를 사용하세요.")
    assessor=lane.SceneLaneAnalysis(fps, SEED)
    continuity=ShortTargetMatch()
    device=torch.device("cuda:0")
    local_model=load_lane_model(lane.DEFAULT_MODEL,device)
    times=tuple(torch.cuda.Event(enable_timing=True) for _ in range(2))
    def local_mask(crop):
        return predict_lane(local_model,crop,device,(384,240),times)[0]
    cap=cv2.VideoCapture(str(VIDEO))
    events=[]
    counts=Counter()
    signatures=[]
    try:
        with TemporaryDirectory(dir=out) as scratch:
            staged=Path(scratch)/"checked.mp4"
            writer=review.writer(staged,fps,size)
            try:
                for f,row in enumerate(rows,1):
                    ok,image=cap.read()
                    if not ok or f!=row["frame"] or abs(row["seconds"]-lane.source_seconds(cap,f,fps))>.001:
                        raise ValueError(f"F{f} 원본과 기록 불일치")
                    box=row["box"]
                    status=row["lane_observation"]
                    vehicle=dict(id=row["track_id"],box=box) if box else None
                    row["detector_box"]=box
                    vehicle,track_source=continuity.update(image,vehicle,row["other_boxes"],row["seconds"])
                    box=vehicle["box"] if vehicle else None
                    row.update(box=box,track_id=vehicle["id"] if vehicle else None,track_source=track_source)
                    found,reading=assessor.evaluate(f,row["seconds"],image,box,row["boundary"],status,
                                                    row["support_gap_px"],row["other_boxes"],local_mask)
                    raw=reading["raw"]
                    for event in found:
                        idx=len(events)+1
                        event.update(incident_id=f"far-{idx}",track_id=row["track_id"],source_video=VIDEO.name,
                                     event_source="automatic",hud_anchor=mvp.event_position(box,*size))
                        events.append(mvp.set_float_slot(event,events))
                        counts[event["label"]]+=1
                    row.update(lane_readability=reading,status=status,status_text="선택 차량 관찰 중",
                               vehicle_info=dict(plate=None,color="밝은색",vehicle_type="승용차"),
                               event_counts=dict(counts),position=reading.get("positions",{}).get(assessor.geometry.primary),
                               contact_start_s=assessor.clocks[assessor.geometry.primary].first_contact,identity_visible=box is not None and raw!="search",
                               hud_box=box if box and raw!="search" and reading["notice"]!="search" else None)
                    composed=compose(image,row,events)
                    signatures.append(review.signature(composed))
                    writer.write(composed)
                if cap.read()[0]:
                    raise ValueError("추적 기록 뒤에 원본 프레임이 더 있습니다.")
            finally:
                writer.release()
            decoded=review.verify(staged,signatures,size,fps)
            pixel_checks=verify_saved(staged,rows,events,fps)
            # JSON을 재생 순서대로 다시 집계해 저장 영상의 사건 시각과 대조합니다.
            replay=lane.analyze_contact_rows(rows,fps)
            key=lambda e:(e["frame"],e["time_s"],e["label"],e["track_id"])
            if list(map(key,replay))!=list(map(key,events)):
                raise ValueError("재생용 사건과 분석 기록 불일치")
            staged.rename(video)
    finally:
        cap.release()
    read_state=lambda r:r["lane_readability"]["notice"]
    bool_count=lambda field:sum(bool(r[field]) for r in rows)
    report=dict(video=VIDEO.name,source_sha256=DIGEST,output=NAME,output_sha256=video_digest(video),
                encoding=decoded,selection=dict(frame=1,point=SELECT,target="원거리 밝은색 승용차",source="manual_selection"),
                tracking=dict(weights="yolo26n.pt",device="RTX 3060 Ti",tracker="bytetrack.yaml",persist=True,
                              conf=.1,input_size=640,roi=ROAD,accepted_boxes=bool_count("detector_box"), native_template=sum(r["track_source"]=="native_template" for r in rows),
                              identity_visible=bool_count("identity_visible"),hud_boxes=bool_count("hud_box")),
                lane=dict(model=lane.DEFAULT_MODEL.name,input_size=lane.SIZE,roi=LANE_ROAD,seed=SEED,
                          rule=lane.LANE_RULE_VERSION,standard_readability=lane.READABILITY_RULES,
                          geometry_version="local-native-paired-v2",
                          local_size=[384,240], meaning="원본 도색과 모델이 지지하는 양쪽 경계를 독립 판독합니다. 한쪽만 읽힌 프레임은 개별 경계에만 적용합니다."),
                notice_text=dict(mvp.LANE_MESSAGES,search="선택 차량을 찾는 중",title="차선 판독 불가"),
                counts=dict(counts),events=events,notices=spans(rows,read_state,fps),
                counting=spans(rows,lambda r:r["lane_readability"]["counting"],fps),
                identity=spans(rows,lambda r:r["identity_visible"],fps),controlled=controlled(),
                verified_samples=pixel_checks,frames=rows)
    save(proof,report)
    print(video,decoded,report["tracking"],dict(counts),flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--out",type=Path,default=DEFAULT/"final")
    parser.add_argument("--mode",choices=["all","analyze","render"],default="all")
    args=parser.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    if args.mode in ("all","analyze"):
        if (args.out/"observations.json").exists():
            parser.error("관측 파일이 이미 있습니다. --mode render 또는 새 --out을 사용하세요.")
        analyze(args.out)
    if args.mode in ("all","render"):
        render(args.out)
