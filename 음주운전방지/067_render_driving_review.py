# 067  제출용 주행 HUD 영상. 원본 시각과 검증한 사건을 같은 프레임에 합성합니다.
# 065의 원본 지문, 066과 041·049·055의 추적 기록이 필요합니다.
# 자동 분석과 수동 확인을 분리해 저장하고 모든 MP4를 원본 프레임 순서와 다시 대조합니다.
import argparse
from collections import Counter
from importlib import import_module
import hashlib
import json
import math
import os
from tempfile import TemporaryDirectory
import shutil
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw
from ultralytics import YOLO

mvp=import_module("041_redbox_mvp")
ROOT=Path(__file__).resolve().parent
DEMOS=ROOT/"output/lane_video_197_mvp/demo_contact_v1"
LAMPS=ROOT/"output/lamp_cv/experiment"
DEFAULT=ROOT/"output/mvp_review_contact/cases"
EMPTY=dict(plate=None,color=None,vehicle_type=None)
MIX_SIZE=(1920,1080)
MIX_RATE=30
# 첫 두 수는 편집할 원본 범위입니다. 앞쪽 여유가 있으면 검출 후 타깃 선택을 보여 줍니다.
CASES=[
 ("ocr","자동분석/01_차량번호_추적",1036,1200,1051),
 ("truck","수동검증/02_정상차선변경_화물차",102,300,116),
 ("normal2","수동검증/03_정상차선변경_흰승용차",375,630,391),
 ("lights","램프위치지정/04_제동과_우측점멸",901,1071,916),
 ("stop-2","수동검증/05_정지선위반_정차차량",1,180,1),
 ("stop-3","수동검증/06_정지선위반_이륜차",751,948,751),
]
EXPECTED_SOURCE={
    "BB_20261123_133631.avi": "c8e201699d80b7f382a0c46fdbbbc04fce5b491bfd82c48c3140011a02c4cb7a",
    "BB_20261123_134949.avi": "473102839c74d4ea0233d817f61a05b23475ed9070f59a994a1e58aa2f761a48",
    "차선변경2_깜빡이_정당.mp4": "2c51489b4bc6e29b0f6fefb777efafb7d06e017c28e9e950b7bce47aba9ae8ad",
    "BB_20261122_173905.avi": "43a97651e769a04ef5fe6b3caed8445b465ba4712095dca46ddf85d70f1bd36a",
    "정지선위반2.avi": "c35e2d7770187a19acb47132e1c07b38ee9f43c618b8d24ae39bf5fb6a52bf99",
    "정지선위반3.avi": "4e2cfe4cbff7cb77ff76347819a68162247b9afa275c2903a4182d252016e4a4"
}

def read(p):
    return json.loads(p.read_text(encoding="utf8"))
def save(p,data):
    p.write_text(json.dumps(data,ensure_ascii=False,indent=1),encoding="utf8")
def stamp(f,fps):
    return (f-1)/fps

def inputs(key,work):
    if key in ("ocr","stop-2","stop-3"):
        folder=DEMOS/key
        meta=read(folder/"target.json")
        rows=[json.loads(line) for line in (folder/"frames.jsonl").read_text(encoding="utf8").splitlines()]
        return meta["video"],rows,meta["events"],meta.get("reviewed_stop_line"),meta["fps"]
    folder=LAMPS/"kialong" if key=="lights" else work/key
    info=read(folder/"track.json")
    rows=info["rows"]
    fps=info["fps"]
    events=[]
    if key=="lights":
        patt=read(folder/"analysis/patterns.json")
        for pair in patt["patterns"]:
            if pair["kind"]=="brake+right_indicator" and pair["brake_overlap"]:
                events.append(dict(frame=pair["last"],label="제동·우측 점멸",event_source="automatic_lamp_manual_roi",
                                   evidence=pair))
    else:
        result=read(folder/"lane_review.json")
        if result.get("lane_rule_version") != mvp.crossing_module.LANE_RULE_VERSION:
            raise ValueError("066으로 현재 차선침범 규칙의 관측 캐시를 먼저 생성하세요.")
        events.extend(dict(e["behavior"],event_source="automatic") for e in result["auto"]
                      if e["behavior"]["label"]=="차선침범")
        # 이 두 차의 차선 이동은 원본 프레임에서 사람이 확인했습니다.
        # 신호 사용 근거는 화물차의 측정 결과와 흰 승용차의 육안 관찰을 분리합니다.
        if key=="truck" and result["lamp_at_reference"]["status"]!="used":
            raise ValueError("화물차 점멸 근거가 없습니다.")
        start=200 if key=="truck" else 510
        event_frame=start+math.ceil(fps)
        if any(not r["box"] for r in rows if start<=r["frame"]<=event_frame):
            raise ValueError("차로 유지 중 추적 보류")
        events.append(dict(frame=event_frame,label="차선변경",event_source="manual_lane_measured_lamp" if key=="truck" else "manual_lane_manual_lamp",
                           stable_from=start,hold_seconds=(event_frame-start)/fps,
                           signal=("우측" if key=="truck" else "좌측"),lane_auto=result["auto"],
                           lamp_auto=result["lamp_at_reference"],visual_flashes=[428,450,471] if key=="normal2" else [130,150,172]))
    return info["video"],rows,sorted(events,key=lambda e:e["frame"]),None,fps

def signature(im):
    return cv2.resize(im,(96,54),interpolation=cv2.INTER_AREA)
def letterbox(im):
    w,h=MIX_SIZE
    scale=min(w/im.shape[1],h/im.shape[0])
    a,b=round(im.shape[1]*scale),round(im.shape[0]*scale)
    out=np.zeros((h,w,3),np.uint8)
    x,y=(w-a)//2,(h-b)//2
    out[y:y+b,x:x+a]=cv2.resize(im,(a,b),interpolation=cv2.INTER_AREA if scale<1 else cv2.INTER_LINEAR)
    return out
def writer(path,fps,size):
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():raise FileExistsError(path)
    # Windows H.264 인코더가 한글 경로를 열지 못해 ASCII 임시 경로에서 인코딩합니다.
    scratch=TemporaryDirectory(prefix="rb_h264_",dir="output")
    temporary=Path(scratch.name)/"video.mp4"
    enc=cv2.VideoWriter(os.path.relpath(temporary),cv2.CAP_MSMF,cv2.VideoWriter_fourcc(*"H264"),fps,size)
    if not enc.isOpened():
        scratch.cleanup()
        raise RuntimeError("Windows H.264 인코더를 열 수 없습니다.")
    class Output:
        write=staticmethod(enc.write)
        def release(self):
            enc.release()
            if path.exists():raise FileExistsError(path)
            shutil.move(str(temporary),str(path))
            scratch.cleanup()
    return Output()

def verify(path,sigs,size,rate):
    cap=cv2.VideoCapture(str(path))
    actual=cap.get(5)
    errors=[]
    try:
        if not cap.isOpened() or abs(actual-rate)>.02:raise ValueError((path,actual,rate))
        for s in sigs:
            ok,img=cap.read()
            if not ok or img.shape[:2]!=size[::-1]:raise ValueError((path,len(errors)))
            errors.append(float(np.abs(signature(img).astype(float)-s).mean()))
        if cap.read()[0] or not errors or max(errors)>10:raise ValueError((path,len(errors),max(errors,default=0)))
    finally:cap.release()
    return dict(decoded=len(errors),fps=actual,size=size,max_frame_mean_absolute_error=max(errors),duration=len(errors)/actual)

def render(work,out):
    out.mkdir(parents=True,exist_ok=False)
    proof=out/"검증기록"
    proof.mkdir()
    mvp.EVENT_COLORS["제동·우측 점멸"]=mvp.HUD_GREEN
    inventory=read(work/"inventory.json")
    detector=YOLO(str(ROOT/"yolo26n.pt"))
    mixpath=out/"00_RedBox_종합시연.mp4"
    mix=writer(mixpath,MIX_RATE,MIX_SIZE)
    mixsigs=[]
    results=[]
    try:
        for key,name,first,last,selected in CASES:
            source,rows,events,line,fps=inputs(key,work)
            path=ROOT/"videos"/source
            with path.open("rb") as stream:
                if not hashlib.file_digest(stream,"sha256").hexdigest()==inventory[source]["sha256"]==EXPECTED_SOURCE[source]:
                    raise ValueError("원본 변경 "+source)
            lookup={r["frame"]:r for r in rows}
            cap=cv2.VideoCapture(str(path))
            w,h=int(cap.get(3)),int(cap.get(4))
            if abs(cap.get(5)-fps)>.0001:raise ValueError(source)
            cap.set(1,first-1)
            video=out/(name+".mp4")
            enc=writer(video,fps,(w,h))
            sigs=[]
            counts=Counter()
            active=[]
            log=[]
            tick_frames=set()
            # 타깃이 바뀌는 장면 경계에서 누적값과 차량 정보를 모두 초기화합니다.
            for e in events:
                f=e["frame"]
                if not first<=f<=last or not lookup[f]["box"]:raise ValueError(e)
                tick_frames.update([f-1,f,f+round(.8*fps),f+math.ceil(2*fps)])
            if len({(e["frame"],e["label"]) for e in events})!=len(events):raise ValueError("중복 사건")
            cues={first,selected,last,*tick_frames}
            if key=="ocr":cues.update([1120,1121])
            snapshots=[]
            mix_start=len(mixsigs)
            try:
                for f in range(first,last+1):
                    ok,img=cap.read()
                    if not ok:raise ValueError((source,f))
                    time=stamp(f,fps)
                    r=lookup.get(f,{}) if f>=selected else {}
                    box=r.get("box")
                    info=r.get("vehicle_info") or EMPTY.copy()
                    if box and key in ("truck","normal2","lights"):
                        # 사람이 직접 확인한 형태와 색상은 결과 기록에서 OCR·모델 출력과 구분합니다.
                        info=dict(plate=None,color={"normal2":"흰색","truck":"흰색","lights":None}[key],
                                  vehicle_type={"truck":"화물차","normal2":"승용차","lights":"SUV"}[key])
                    for i,e in enumerate(events):
                        if f==e["frame"]:
                            event=dict(e,id=e.get("incident_id",f"{key}-{f}-{i}"),time_s=e.get("time_s",time),
                                       track_id=r["track_id"],hud_anchor=mvp.event_position(box,w,h))
                            active.append(mvp.set_float_slot(event,active))
                            counts[e["label"]]+=1
                    phase="차량 검출 중" if f<selected else "선택 차량 추적 중" if box else "추적 보류"
                    if box and key in ("normal2","truck"):phase+=" · "+("좌측" if key=="normal2" else "우측")+" 등화 관찰"
                    if box and key=="truck" and 184<=f<231:
                        phase="우측 지시등 점멸 확인 · 새 차로 유지 관찰"
                    if box and key=="normal2" and 475<=f<540:
                        phase="좌측 점멸 육안 확인 · 새 차로 유지 관찰"
                    if box and key=="lights":
                        phase="후미등 관찰" if f<1010 else "제동·우측 점멸 기록"
                    if box and r.get("track_id") is not None:
                        phase+=f"  |  ID {r['track_id']}"
                    last_label=active[-1]["label"] if active and time-active[-1]["time_s"]<2 else None
                    row=dict(seconds=time,vehicle_info=info,box=box,boundary=r.get("boundary"),event_counts=dict(counts),
                             status_text=phase,verdict=last_label if last_label=="정지선 위반" else None)
                    if r.get("lane_readability"):
                        row["lane_readability"]=r["lane_readability"]
                    if line:row["stop_line"]=dict(line=[line[:2],line[2:]])
                    layer=mvp.draw_hud(img,row,"recorded",overlay_only=True)
                    draw=ImageDraw.Draw(layer)
                    if f<selected:
                        det=detector.predict(img,classes=[2,3,5,7],conf=.25,device=0,verbose=False)[0]
                        for x,y,X,Y in det.boxes.xyxy.cpu().tolist():
                            draw.rectangle((x*layer.width/w,y*layer.height/h,X*layer.width/w,Y*layer.height/h),outline=mvp.HUD_GREEN,width=1)
                    tag=("수동 검증 시연 · 차로·점멸 확인" if key=="normal2" else "수동 검증 시연 · 차로 확인" if key=="truck"
                         else "수동 검증 시연 · 정차 구간 지정" if key.startswith("stop") else "수동 검증 시연 · 램프 위치 지정" if key=="lights" else "")
                    if tag:mvp.hud_text(draw,layer.width-18,layer.height-37,[(tag,mvp.HUD_WHITE)],13,align="right")
                    mvp.draw_event_floats(layer,active,time)
                    # 투명 레이어만 확대해 원본 차량과 도로의 해상도를 유지합니다.
                    overlay=np.asarray(layer.resize((w,h),Image.Resampling.BILINEAR))
                    alpha=overlay[:,:,3]
                    yy,xx=np.nonzero(alpha)
                    rgb=overlay[yy,xx,2::-1].astype(np.uint16)
                    aa=alpha[yy,xx,None].astype(np.uint16)
                    img[yy,xx]=(rgb*aa+img[yy,xx].astype(np.uint16)*(255-aa)+127)//255
                    enc.write(img)
                    sigs.append(signature(img))
                    # 짧은 클립 안에서 입력 한 장에 출력 한 장을 유지합니다.
                    canvas=letterbox(img)
                    mix.write(canvas)
                    mixsigs.append(signature(canvas))
                    if f in cues:
                        snapshots.append((f,cv2.resize(img,(768,round(768*h/w)))))
                    log.append(dict(frame=f,seconds=time,clip_frame=f-first+1,track_id=r.get("track_id"),box=box,
                                    info=info,counts=dict(counts),floating=[e["id"] for e in active if 0<=round(time-e["time_s"],9)<2]))
            finally:
                enc.release()
                cap.release()
            check=verify(video,sigs,(w,h),fps)
            # 서버에서 그린 화면뿐 아니라 압축한 파일의 같은 시점을 다시 꺼내 확인합니다.
            reader=cv2.VideoCapture(str(video))
            try:
                for f,snap in snapshots:
                    reader.set(1,f-first)
                    ok,frame=reader.read()
                    if not ok:raise ValueError("검증 화면 불러오기 실패")
                    reduced=cv2.resize(frame,(snap.shape[1],snap.shape[0]))
                    if cv2.absdiff(snap,reduced).mean()>15:raise ValueError("HUD 프레임 불일치")
                    cv2.imencode(".jpg",reduced)[1].tofile(proof/f"{key}_F{f}.jpg")
            finally:reader.release()
            save(proof/(key+"_frames.json"),log)
            report=dict(file=name+".mp4",source=source,source_sha256=inventory[source]["sha256"],
                        first=first,last=last,selected=selected,source_fps=fps,composite_first=mix_start+1,
                        composite_last=len(mixsigs),events=active,final_counts=dict(counts),verified=check,
                        info_source="사람이 확인한 색상·형태" if key in ("normal2","truck","lights") else "041 자동 분석",brand=None,model_name=None)
            results.append(report)
            print(name,check,dict(counts),flush=True)
        # 07은 빠른 시연의 검수된 프레임과 사건 기록을 그대로 이어 붙입니다.
        folder=DEMOS/"drowsy-2"
        data=read(folder/"target.json")
        if data["lane_rule_version"]!=mvp.crossing_module.LANE_RULE_VERSION or data["fps"]!=MIX_RATE:
            raise ValueError("07 시연 캐시를 먼저 갱신하세요.")
        name="07_졸음운전_예측.mp4"
        shutil.copyfile(folder/"hud.mp4",out/name)
        cap=cv2.VideoCapture(str(out/name))
        first=len(mixsigs)+1
        try:
            while True:
                ok,img=cap.read()
                if not ok:break
                canvas=letterbox(img)
                mix.write(canvas)
                mixsigs.append(signature(canvas))
        finally:
            cap.release()
        if len(mixsigs)-first+1!=data["analyzed_frames"]:
            raise ValueError("07 복합 영상 프레임 수 불일치")
        rows=[json.loads(x) for x in (folder/"frames.jsonl").read_text(encoding="utf-8").splitlines()]
        save(proof/"drowsy-2_frames.json",[dict(frame=r["frame"],seconds=r["seconds"],counts=r["event_counts"],
                                                floating=r["floating_ids"]) for r in rows])
        results.append(dict(file=name,source=data["video"],source_sha256=data["source_sha256"],first=1,
                            last=data["end_frame"],selected=1,source_fps=data["fps"],composite_first=first,
                            composite_last=len(mixsigs),events=data["events"],final_counts=data["event_counts"],
                            verified=dict(decoded=len(rows))))
    finally:mix.release()
    check=verify(mixpath,mixsigs,MIX_SIZE,MIX_RATE)
    save(proof/"media.json",dict(clips=results,composite=check,composite_file=mixpath.name))
    print("종합",check,flush=True)

def verify_timeline(out):
    # 출력된 두 영상의 동일 시점과 저장 후의 사건·플로팅·TOTAL을 독립적으로 대조합니다.
    proof=out/"검증기록"
    manifest=read(proof/"media.json")
    composite=cv2.VideoCapture(str(out/manifest["composite_file"]))
    results=[]
    montage=[]
    seen_ids=set()
    pos=0
    try:
        for clip in manifest["clips"]:
            events=clip["events"]
            key="drowsy-2" if clip["file"]=="07_졸음운전_예측.mp4" else next(key for key,name,*_ in CASES if name+".mp4"==clip["file"])
            log=read(proof/(key+"_frames.json"))
            fps=clip["source_fps"]
            expected_length=clip["last"]-clip["first"]+1
            if not len(log)==clip["verified"]["decoded"]==expected_length or clip["composite_first"]!=pos+1:
                raise ValueError("구간 프레임 수 불일치")
            for e in events:
                event_id=e.get("id",e.get("incident_id"))
                if event_id in seen_ids:raise ValueError("같은 사건을 두 번 기록했습니다.")
                seen_ids.add(event_id)
            for i,r in enumerate(log):
                f=clip["first"]+i
                if r["frame"]!=f or abs(r["seconds"]-stamp(f,fps))>1e-7:raise ValueError("시각 불일치")
                arrived=[e for e in events if e["frame"]<=f]
                counts=dict(Counter(e["label"] for e in arrived))
                floating=[e.get("id",e.get("incident_id")) for e in arrived if round(stamp(f,fps)-e["time_s"],9)<2]
                if counts!=r["counts"] or floating!=r["floating"]:raise ValueError("화면 누적값 불일치")
            if log[-1]["counts"]!=clip["final_counts"]:raise ValueError("마지막 TOTAL 오류")
            cap=cv2.VideoCapture(str(out/clip["file"]))
            frames={clip["first"],clip["last"],clip["selected"]}
            for e in events:frames.update([e["frame"]-1,e["frame"],e["frame"]+round(fps),e["frame"]+math.ceil(2*fps)])
            sample=events[0]["frame"]+round(.55*fps) if events else 1121
            frames.add(sample)
            loss=[]
            try:
                for f in sorted(frames):
                    if not clip["first"]<=f<=clip["last"]:continue
                    cap.set(1,f-clip["first"])
                    composite.set(1,pos+f-clip["first"])
                    ok,one=cap.read()
                    good,mix=composite.read()
                    if not ok or not good:raise ValueError("완성 영상 탐색 실패")
                    diff=float(cv2.absdiff(signature(letterbox(one)),signature(mix)).mean())
                    if diff>8:raise ValueError((clip["file"],f,diff))
                    loss.append(diff)
                    if f==sample:montage.append(cv2.resize(mix,(480,270)))
            finally:cap.release()
            results.append(dict(file=clip["file"],checked_log_frames=len(log),checked_encoded_pairs=len(loss),
                                max_composite_difference=max(loss),event_ids=[e.get("id",e.get("incident_id")) for e in events]))
            pos+=len(log)
        if pos!=manifest["composite"]["decoded"]:raise ValueError("종합 파일 길이 불일치")
    finally:composite.release()
    if montage:
        if len(montage)%2:montage.append(np.zeros_like(montage[0]))
        photo=np.vstack([np.hstack(montage[i:i+2]) for i in range(0,len(montage),2)])
        cv2.imencode(".jpg",photo)[1].tofile(proof/"최종_재생화면.jpg")
    save(proof/"동기검증.json",dict(clips=results,composite_frames=pos,unique_events=len(seen_ids)))

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--work",type=Path,default=DEFAULT)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--verify-only",action="store_true")
    args=p.parse_args()
    if not args.verify_only:
        render(args.work,args.output)
    verify_timeline(args.output)

