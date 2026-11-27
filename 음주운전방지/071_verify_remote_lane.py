# 071 · 원거리 차선 판독에서 어느 경계를 확인했는지 검사합니다.
# 변경 전후 같은 원본의 프레임별 JSON을 받아 양쪽·한쪽·보류를 따로 셉니다.
# 실제 영상의 사건·플로팅 표시와 통제 입력의 시간 규칙을 검사해 제출 검증 기록으로 남깁니다.
import argparse
from collections import Counter
from importlib import import_module
import json
from pathlib import Path

import cv2
import numpy as np

demo = import_module("070_review_far_target")
lane = demo.lane
FOCUS = [(4,7),(9,10),(17,18),(30,33)]


def counters(rows):
    notices = Counter(r["lane_readability"]["notice"] for r in rows)
    positions = Counter(len(r["lane_readability"].get("positions",{})) for r in rows)
    return dict(frames=len(rows), located=sum(r["identity_visible"] for r in rows),
                countable=sum(r["lane_readability"]["counting"] for r in rows),
                both=positions[2], one=positions[1], notice=notices)


def legacy_reasons(rows):
    reasons=Counter()
    for row in rows:
        q=row["lane_readability"]
        m=q["metrics"]
        if q["raw"]=="small":
            reason="min_box" if "clearance_px" not in m else "edge_margin"
        elif q["raw"]=="search":
            reason="no_box" if not row["box"] else "identity_occlusion"
        elif q["raw"]=="unclear":
            if m.get("foreground_cover",0)>=.35:
                reason="foreground_cover"
            elif row["lane_observation"] not in ("observed","near_boundary"):
                reason=row["lane_observation"]
            elif "paint_rows" in m:
                reason="native_paint"
            else:
                reason="detail_or_support_gap"
        else:
            reason=q["raw"]
        reasons[reason]+=1
    return reasons


def clocks():
    cases=[
        ("3초 연속", "C"*91, 2), ("4.5초 연속","C"*136,3), ("6초 연속","C"*181,4),
        ("짧은 복귀 3회","L"*5+("C"*12+"L"*2)*3,3),
        ("3초 복귀 2회","L"*5+("C"*90+"L"*2)*2,4),
        ("정확히 1.5초 후 복귀","L"*5+"C"*45+"L",1),
        ("2초 복귀 2회","L"*5+("C"*60+"L"*2)*2,2),
        ("첫 두 접촉의 근거가 약한 뒤 첫 차로 관측","CCLLL",0),
        ("직접 근거가 선명한 한 프레임 접촉","LLLSLL",1),
        ("차체·경계 연속 관측, 오차 띠 통과 후 짧은 복귀","L"*8+"~"*10+"C"*5+"~"*8+"L"*3,1),
        ("접촉 없이 근접만 했다가 복귀","L"*8+"~"*10+"L"*3,0),
        ("2프레임 미확인 시간 제외","C"*30+"??"+"C"*16,0),
        ("2프레임 공백 후 관측된 접촉 시간만 합산","C"*30+"??"+"C"*17,1),
        ("긴 추적 공백이 있으면 재시작","C"*35+"X"*4+"C"*30,0),
    ]
    result=[]
    for name,seq,total in cases:
        clock=lane.MeasuredBoundary(30)
        events=[]
        for i,token in enumerate(seq):
            position={"L":"left","S":"contact","C":"contact"}.get(token)
            events.extend(clock.update(i+1,i/30,position,token!="X",token=="~",token=="S"))
        times=[e["time_s"] for e in events]
        if len(times)!=total:
            raise AssertionError((name,total,times))
        result.append(dict(case=name,expected=total,actual=len(events),times=times))
    return result


def inspect_floats(video,rows,events):
    # 실제 MP4 화소가 올바른 문구 쪽에 가까운지, 반대로 문구를 넣거나 뺀 화면과 비교합니다.
    saved=cv2.VideoCapture(str(video))
    raw=cv2.VideoCapture(str(demo.VIDEO))
    checks=[]
    try:
        for event in events:
            for offset in (-1,0,15,30,45,60):
                frame=event["frame"]+offset
                if not 1<=frame<=len(rows):
                    continue
                row=rows[frame-1]
                raw.set(1,frame-1)
                saved.set(1,frame-1)
                good,src=raw.read()
                ok,encoded=saved.read()
                if not ok or not good: raise OSError(frame)
                shown=[e for e in events if e["frame"]<=frame]
                expected=demo.compose(src,row,shown)
                on=0<=round(row["seconds"]-event["time_s"],8)<2
                other=[e for e in shown if e is not event]
                if not on: other=other+[dict(event,time_s=row["seconds"])]
                wrong=demo.compose(src,row,other)
                pixels=np.max(cv2.absdiff(expected,wrong),axis=2)>45
                if not pixels.any(): raise AssertionError((frame,"비교할 화소 없음"))
                diff=float(cv2.absdiff(encoded,wrong)[pixels].mean()-cv2.absdiff(encoded,expected)[pixels].mean())
                if diff<=4: raise AssertionError((frame,diff))
                checks.append(dict(frame=frame,seconds=row["seconds"],floating=on,
                                   total=row["event_counts"],pixel_margin=round(diff,2)))
    finally:
        saved.release()
        raw.release()
    return checks


def main():
    cli=argparse.ArgumentParser()
    cli.add_argument("--baseline",type=Path,required=True)
    cli.add_argument("--result",type=Path,required=True)
    cli.add_argument("--out",type=Path,required=True)
    args=cli.parse_args()
    old=demo.read(args.baseline)
    new=demo.read(args.result)
    video=args.result.parent/new["output"]
    if not video.is_file() and args.result.parent.name=="검증기록":
        video=args.result.parent.parent/new["output"]
    if not old["source_sha256"]==new["source_sha256"]==demo.video_digest(demo.VIDEO):
        raise ValueError("원본 영상 지문 불일치")
    if new["output_sha256"]!=demo.video_digest(video): raise ValueError("MP4 지문 불일치")
    before,after=old["frames"],new["frames"]
    if [(r["frame"],r["seconds"]) for r in before]!=[(r["frame"],r["seconds"]) for r in after]:
        raise ValueError("비교할 원본 프레임 불일치")
    replay=lane.analyze_contact_rows(after,new["encoding"]["fps"])
    keys=("frame","time_s","label","track_id","boundary_side")
    if [[e.get(k) for k in keys] for e in replay]!=[[e.get(k) for k in keys] for e in new["events"]]:
        raise ValueError("공통 집계 재생과 저장된 사건 불일치")
    counts=Counter()
    by_frame={}
    for e in replay: by_frame.setdefault(e["frame"],[]).append(e)
    for row in after:
        counts.update(e["label"] for e in by_frame.get(row["frame"],[]))
        if counts!=Counter(row["event_counts"]): raise ValueError(("TOTAL 불일치",row["frame"]))
    focus=[]
    for s,t in FOCUS:
        select=lambda rows:[r for r in rows if s<=r["seconds"]<t]
        focus.append(dict(start_s=s,end_s=t,old=counters(select(before)),new=counters(select(after))))
    report=dict(before=counters(before),after=counters(after),focus=focus,
                old_first_condition=legacy_reasons(before),
                new_reason=Counter(r["lane_readability"]["reason"] for r in after),
                read_edges=Counter("+".join(sorted(r["lane_readability"]["positions"])) or "none" for r in after),
                controlled=clocks(),events=replay,floating=inspect_floats(video,after,new["events"]))
    demo.save(args.out,report)
    print("원본·사건·누적·애니메이션 검증 통과", report["after"], flush=True)


if __name__=="__main__":
    main()

