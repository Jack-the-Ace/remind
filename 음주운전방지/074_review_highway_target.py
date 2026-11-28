# 074 · 멀어지는 검은 승용차의 차선 접촉과 후미등을 관찰합니다.
# 원본, YOLO26, 197 차선 가중치로 검출과 도색 근거를 먼저 저장합니다.
# 선택한 차량과 같은 경계의 접촉 시간으로 사건을 만들고 공통 HUD로 합성합니다.
# 결과 MP4를 다시 열어 타깃, 사건 시각과 집계를 검토합니다.
import argparse
from collections import Counter
from importlib import import_module
from pathlib import Path

import cv2
import numpy as np
import torch
from PIL import Image

from track_preview import Target, video_digest
from preview_lane_track_197 import predict_lane, track_vehicles
from redbox_lane_geometry import ShortTargetMatch, PaintCurve, recording_clock
from redbox_vehicle_info import VehicleInfo
from rear_lamp_patterns import levels, rectangle, patch

pair = import_module("072_review_target_videos")
app = pair.app
lane = pair.lane
ROOT = pair.ROOT
VIDEO = ROOT / "videos/음주운전2.mp4"
DIGEST = "cb14f1a7a5a3278801ea7b8dd9c351088236c9b5fed45fe442f3931fcd8503cf"
FILENAME = "음주운전2_분석.mp4"
DEFAULT = ROOT / "output/mvp_review_drive2"


def prepare(out):
    # 작은 차와 점선이 있는 도로를 별도로 확대합니다. 결과 좌표는 항상 원본 기준입니다.
    tracker, classes = app.new_tracker()
    net = app.lane()
    device = torch.device("cuda:0")
    timing = tuple(torch.cuda.Event(enable_timing=True) for _ in range(2))
    cap = cv2.VideoCapture(str(VIDEO))
    fps = cap.get(cv2.CAP_PROP_FPS)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    masks = out / "masks"
    masks.mkdir(exist_ok=True)
    rows = []
    try:
        for f in range(1, total+1):
            ok, frame = cap.read()
            if not ok: raise OSError(f)
            cars = track_vehicles(tracker, frame, classes, 0)
            h,w = frame.shape[:2]
            full = np.zeros((h,w),np.uint8)
            for x,y,X,Y in [(0,205,w,h),(555,265,1020,430)]:
                mask,_ = predict_lane(net, frame[y:Y,x:X], device, lane.SIZE, timing)
                tile = cv2.resize(mask, (X-x,Y-y), interpolation=cv2.INTER_NEAREST)
                full[y:Y,x:X] |= cv2.dilate(tile,np.ones((3,3),np.uint8))
            cv2.imencode(".png",full*255)[1].tofile(masks/f"{f}.png")
            rows.append(dict(frame=f, seconds=lane.source_seconds(cap,f,fps), cars=cars))
        if cap.read()[0]: raise ValueError("원본 프레임 수 불일치")
    finally:
        cap.release()
    pair.save(out/"차량검출.json",rows)
    cap=cv2.VideoCapture(str(VIDEO))
    try:
        pair.save(out/"주행시계.json",recording_clock(cap,1,total,lane.source_seconds))
    finally:
        cap.release()


def local_detections(out):
    tracker, classes = app.new_tracker()
    rows = []
    cap = cv2.VideoCapture(str(VIDEO))
    try:
        for f in range(1, int(cap.get(7))+1):
            ok, frame = cap.read()
            if not ok: raise OSError(f)
            # 후방 차량·하늘을 제외하고 앞 도로를 원본 화소에서 잘라 먼 차량도 검출합니다.
            x,y,X,Y = 555,195,1020,425
            cars = track_vehicles(tracker,frame[y:Y,x:X],classes,0) if f >= 241 else []
            for car in cars:
                car["box"] = (np.array(car["box"])+[x,y,x,y]).tolist()
            rows.append(cars)
    finally:
        cap.release()
    pair.save(out/"원거리검출.json",rows)



def overlap(a, b):
    a,b = np.asarray(a),np.asarray(b)
    area = np.prod(np.maximum(0,np.minimum(a[2:],b[2:])-np.maximum(a[:2],b[:2])))
    return float(area/max(1,np.prod(a[2:]-a[:2])+np.prod(b[2:]-b[:2])-area))


def track(out):
    full = pair.read(out/"차량검출.json")
    local = pair.read(out/"원거리검출.json")
    wide, near = Target(), Target()
    backup = ShortTargetMatch()
    cap = cv2.VideoCapture(str(VIDEO))
    result = []
    agreement = []
    try:
        for row, detail in zip(full,local,strict=True):
            f,t,cars = row["frame"],row["seconds"],row["cars"]
            ok,image = cap.read()
            if not ok: raise OSError(f)
            if f == 29:
                selected = app.select_vehicle(cars,(155,400))
                wide.select(selected,image,f)
            else:
                selected = wide.update(cars,image,f)
            small = near.update(detail,image,f)
            # 확대 검출기가 이미 확인한 같은 상자와 세 프레임 연속 겹칠 때만 넘겨받습니다.
            if small is None and selected:
                matching = [c for c in detail if c["id"] and overlap(c["box"],selected["box"])>.70]
                if len(matching)==1:
                    agreement.append((f,matching[0]["id"]))
                    agreement=agreement[-3:]
                    if len(agreement)==3 and agreement[0]==(f-2,matching[0]["id"]) and agreement[1]==(f-1,matching[0]["id"]):
                        small=matching[0]
                        near.select(small,image,f)
                else:
                    agreement.clear()
            use_crop = small and (not selected or selected["box"][2]-selected["box"][0]<150)
            car = small if use_crop else selected
            detector = "road_crop" if use_crop else "full"
            neighbors = list(detail if use_crop else cars)
            if use_crop:
                neighbors += [d for d in cars if all(overlap(d["box"],n["box"])<.4 for n in detail)]
            car,kind = backup.update(image,car,neighbors,t)
            result.append(dict(frame=f,seconds=t,car=car,cars=neighbors,track_source=kind,
                               detector=detector if kind == "detector" else None,wide=selected,local=small))
    finally:
        cap.release()
    pair.save(out/"선택추적.json",result)
    print("추적", Counter(r["detector"] or r["track_source"] for r in result), flush=True)



# F1의 같은 두 점선을 원본에서 지정합니다. 차가 있는 쪽 경계는 촬영차의 왼쪽 점선입니다.
SEEDS = {"left":[(831,329),(769,360),(590,456)],
         "right":[(936,332),(961,359),(1050,450)]}


def balance_road(frame, mask):
    # 해질녘 흰 도색도 노랗게 보입니다. 모델이 찾은 밝은 도색에서 조명의 색만 추정합니다.
    sample = frame[325::3,::3]
    values = sample[(mask[325::3,::3]>0) & (sample.mean(2)>100)]
    if len(values)<20:
        return frame
    paint = np.median(values[values.mean(1)>=np.percentile(values.mean(1),60)],axis=0)
    gains = np.clip(paint.mean()/np.maximum(1,paint),.78,1.32)
    lut = np.clip(np.arange(256)[:,None] * gains,0,255).astype(np.uint8)
    return cv2.LUT(frame,lut.reshape(256,1,3))


def lamps(image, box, f, freeze, *, center_lenses=True):
    sample={"frame":f}
    if not box or freeze:
        return sample
    x,y,X,Y=np.rint(box).astype(int)
    crop=image[max(0,y):Y,max(0,x):X]
    h,w=crop.shape[:2]
    if w<65 or h<40 or x<3 or Y>=image.shape[0]-4:
        return sample
    # 옆모습에서 후면으로 변할 때의 렌즈 중심은 원본 크롭에서 확인했습니다.
    scale=[65,100,160,300,420]
    right=np.interp(w,scale,[.77,.72,.68,.63,.60])
    left=np.interp(w,scale,[.13,.105,.075,.075,.065])
    cy=np.interp(w,scale,[.48,.48,.47,.48,.47])
    body=patch(crop,rectangle(.48,.64,.22,.11,w,h))
    for side,cx in (("left",left),("right",right)):
        lens_x,lens_y=cx,cy
        if center_lenses:
            # 상자가 몇 픽셀 흔들려도 어두운 차체가 밝기 표본 안으로 들어오지 않도록,
            # 지정한 렌즈 주변의 적색 렌즈·발광부 중심을 원본에서 다시 찾습니다.
            a,b,A,B=rectangle(cx,cy,.23,.29,w,h)
            blue,green,red=np.moveaxis(crop[b:B,a:A].astype(float),2,0)
            signal=np.maximum(0,red-blue-27)*np.maximum(0,red-80)
            signal[signal<np.max(signal)*.45]=0
            yy,xx=np.indices(signal.shape)
            if signal.sum()<1000:
                # 렌즈 위치를 재확인할 수 없는 화면은 미사용의 근거가 되지 않습니다.
                continue
            lens_x=(a+np.average(xx,weights=signal)+.5)/w
            lens_y=(b+np.average(yy,weights=signal)+.5)/h
        rect=rectangle(lens_x,lens_y,.12,.16,w,h)
        lens=patch(crop,rect)
        if min(lens.shape[:2])<4: continue
        sample[side+"_valid"]=True
        sample[side+"_region"]=list(map(int,(x+rect[0],y+rect[1],x+rect[2],y+rect[3])))
        sample.update({side+"_"+k:v for k,v in levels(lens,body).items()})
    return sample


def analyze(out):
    from rear_lamp_patterns import evidence
    tracks = pair.read(out/"선택추적.json")
    clock = pair.read(out/"주행시계.json")
    reader,ocr_state = app.ocr()
    info = VehicleInfo(reader)
    curves={side:PaintCurve(pts) for side,pts in SEEDS.items()}
    scene=lane.SceneLaneAnalysis(30,[[0,0],[1,1]])
    frames,events,observations,original_lamps,ocr_reads=[],[],[],[],[]
    cap=cv2.VideoCapture(str(VIDEO))
    try:
        for r,tick in zip(tracks,clock,strict=True):
            ok,image=cap.read()
            if not ok: raise OSError(r["frame"])
            f,t,car=r["frame"],r["seconds"],r["car"]
            box=car["box"] if car else None
            if car and f%8==0 and not tick["duplicate"]:
                info.sample(image,car,f)
                if info.ocr_frames and info.ocr_frames[-1]["frame"]==f:
                    ocr_reads.append(info.ocr_frames[-1])
            mask=cv2.imdecode(np.fromfile(out/"masks"/f"{f}.png",np.uint8),0)
            corrected=balance_road(image,mask)
            cropped=bool(box and box[3]>=image.shape[0]-5)
            # 아래쪽 접점이 화면 밖이면 상자만 그립니다. 공백 동안의 시간은 집계하지 않습니다.
            quality_box=None if cropped else box
            found,reading=scene.evaluate_curves(f,t,corrected,quality_box,r["cars"],mask,curves,tick)
            if cropped:
                reading.update(raw="unclear",notice="unclear",reason="road_contact_outside_frame")
            elif not reading["counting"]:
                reading["reason"]=("target_missing" if not box else "foreground_or_blur" if not reading["visible"]
                                   else "uncertain_footprint" if reading["geometry"]["edges"] else "no_supported_paint")
            # 목표 차량이 걸친 점선은 촬영차의 왼쪽 경계입니다. 다른 선만 보일 때
            # 타깃 접촉 시간이 0초인 것처럼 표시하지 않습니다.
            primary = reading["geometry"]["edges"].get("left") or {}
            reading["target_edge_reason"] = ("observed" if reading["positions"].get("left")
                else reading.get("reason") or ("inside_error_band" if primary else "no_supported_paint"))
            if "left" not in reading["positions"] and "contact" not in reading["positions"].values():
                reading["contact_seconds"]=None
            for e in found:
                e.update(frame=f,confirmed_frame=f,time_s=t,track_id=car["id"],selection_id="black_sedan",
                         event_source="automatic",hud_anchor=app.event_position(box,image.shape[1],image.shape[0]))
                events.append(e)
            lamp_box=box if reading["visible"] else None
            observations.append(lamps(image,lamp_box,f,tick["freeze"]))
            original_lamps.append(lamps(image,lamp_box,f,tick["freeze"],center_lenses=False))
            frames.append(dict(frame=f,seconds=t,box=box,track_id=car["id"] if car else None,
                          selection_id="black_sedan",track_source=r["track_source"],detector=r["detector"],
                          status="observed" if car else "tracking_hold",
                          status_text="선택 차량 관찰 중" if car else "선택 차량을 찾는 중",
                          vehicle_info=dict(info.snapshot(),brand=None,model_name=None),boundary=None,
                          lane_readability=reading,contact_seconds=reading["contact_seconds"],**tick))
    finally:
        cap.release()
        if info.windows_ocr: info.windows_ocr.close()
    def scan(samples):
        records=[]
        for i in range(0,len(samples),30):
            for record in evidence(samples[i:i+150],30)["patterns"]:
                if record not in records: records.append(record)
        return records
    patterns=scan(observations)
    signal=import_module("056_verify_lamp_lane_events")
    checks=[]
    usable=[dict(r,left_valid=str(bool(r.get("left_valid"))),right_valid=str(bool(r.get("right_valid")))) for r in observations]
    routed=[]
    for e in events:
        if e["label"]=="차선변경":
            direction=e["to_side"]
            start=e["maneuver_start_frame"] or e["frame"]
            check=signal.check_lamps(usable,{"patterns":patterns},start,e["frame"],direction,30)
            checks.append(dict(frame=e["frame"],direction=direction,**check))
            if check["status"]=="unknown": continue
            if check["status"]=="unused": e=dict(e,label="지시등위반")
        routed.append(app.set_float_slot(dict(e),routed))
    counts=Counter()
    for row in frames:
        counts.update(e["label"] for e in routed if e["frame"]==row["frame"])
        row["event_counts"]=dict(counts)
    pair.save(out/"후미등.json",dict(samples=observations,patterns=patterns,
                                before_alignment=scan(original_lamps),lane_checks=checks))
    pair.save(out/"분석.json",dict(video=VIDEO.name,source_sha256=DIGEST,seed_frame=29,first_click=[155,400],
              manual_reselections=[],lane_seeds=SEEDS,frames=frames,events=routed,geometry_events=events,
              counts=dict(counts),ocr=dict(status=ocr_state,samples=ocr_reads)))
    print("최종 사건", [(e['frame'],e['label'],e['reason']) for e in routed], flush=True)



def render(out):
    data=pair.read(out/"분석.json")
    rows,events=data["frames"],data["events"]
    if data["source_sha256"]!=video_digest(VIDEO): raise ValueError("원본과 기록 불일치")
    path=out/FILENAME
    app.EVENT_COLORS.setdefault("지시등위반",app.HUD_RED)
    cap=cv2.VideoCapture(str(VIDEO))
    fps=cap.get(5)
    size=(round(cap.get(3)),round(cap.get(4)))
    writer=pair.media.writer(path,fps,size)
    signatures=[]
    counts=Counter()
    try:
        for r in rows:
            ok,frame=cap.read()
            if not ok or abs(lane.source_seconds(cap,r["frame"],fps)-r["seconds"])>.001:
                raise ValueError(("원본 시각",r["frame"]))
            arrived=[e for e in events if e["frame"]<=r["frame"]]
            counts.update(e["label"] for e in arrived if e["frame"]==r["frame"])
            if dict(counts)!=r["event_counts"]: raise ValueError("TOTAL 불일치")
            hud=pair.far.compose(frame,r,arrived)
            signatures.append(pair.media.signature(hud))
            writer.write(hud)
        if cap.read()[0]: raise ValueError("원본 끝까지 처리되지 않았습니다.")
    finally:
        writer.release()
        cap.release()
    check=pair.media.verify(path,signatures,size,fps)
    check["sha256"]=video_digest(path)
    check["controlled"]=import_module("040_verify_lane_crossing_recovery_197").verify_contact_intervals()
    again=lane.analyze_contact_rows(rows,fps)
    signature=lambda e:(e["label"],e["frame"],e["track_id"],e["boundary_side"])
    if list(map(signature,again))!=list(map(signature,data["geometry_events"])):
        raise AssertionError("차선 사건 재검사 실패")
    check["hud"]=inspect_pixels(out,rows,events)
    pair.save(out/"검수.json",check)
    print(path,check["decoded"],check["sha256"],flush=True)


def inspect_pixels(out,rows,events):
    # 저장 영상의 실제 화소가 맞는 HUD와 틀린 HUD 중 어느 쪽인지 대조합니다.
    probes={n:[] for n in (1,29,150,905,1230,len(rows))}
    for e in events:
        for shift in (-1,0,30,45,60):
            n=e["frame"]+shift
            if 1<=n<=len(rows): probes.setdefault(n,[]).append(e)
    source=cv2.VideoCapture(str(VIDEO))
    saved=cv2.VideoCapture(str(out/FILENAME))
    checks=[]
    counts=[]
    try:
        for n,tests in sorted(probes.items()):
            source.set(1,n-1)
            saved.set(1,n-1)
            ok,a=source.read()
            valid,b=saved.read()
            if not ok or not valid: raise OSError(n)
            row=rows[n-1]
            t=row["seconds"]
            past=[e for e in events if e["frame"]<=n]
            expected=pair.far.compose(a,row,past)
            def compare(alternate):
                pixels=np.max(cv2.absdiff(expected,alternate),axis=2)>40
                if not pixels.any(): raise AssertionError(("비교할 화소가 없습니다",n))
                value=(cv2.absdiff(b,alternate)[pixels].mean()-cv2.absdiff(b,expected)[pixels].mean())
                if value<2: raise AssertionError(("저장된 HUD 불일치",n,value))
                return round(float(value),2)
            c=dict(frame=n,timer=compare(pair.far.compose(a,dict(row,contact_seconds=91.79),past)),
                   total=compare(pair.far.compose(a,dict(row,event_counts={"차선침범":99}),past)),floating=[])
            if not row["box"] and row["lane_readability"]["notice"] == "ready":
                # 이전 안내가 잠깐 유지되더라도 차량 상자가 없으면 추적 보류라고 표시합니다.
                stale = dict(row, status_text="선택 차량 관찰 중")
                c["tracking_hold"] = compare(pair.far.compose(a,stale,past))
            for e in tests:
                active=(n>=e["frame"] and round(t-e["time_s"],8)<2)
                changed=[v for v in past if v!=e]
                if not active: changed.append(dict(e,time_s=t))
                c["floating"].append(dict(event=e["frame"],visible=active,margin=compare(pair.far.compose(a,row,changed))))
            checks.append(c)
            if n in {29,905,1230,len(rows)} or events and n in {events[0]["frame"],events[-1]["frame"]}:
                cv2.imencode(".jpg",b,[cv2.IMWRITE_JPEG_QUALITY,93])[1].tofile(out/f"HUD_F{n}.jpg")
                layer=app.draw_hud(a,row,"recorded",overlay_only=True)
                rgba=np.asarray(layer.resize((a.shape[1],a.shape[0]),Image.Resampling.BILINEAR))
                for side,half in [("left",slice(0,320)),("right",slice(-360,None))]:
                    band=rgba[:180,half]
                    mask=(band[:,:,3]==128)&(np.max(abs(band[:,:,:3].astype(int)-128),axis=2)<=1)
                    mask=cv2.erode(mask.astype(np.uint8),np.ones((5,5),np.uint8))>0
                    bg=a[:180,half][mask].astype(float); decoded=b[:180,half][mask].astype(float)
                    error=float(np.median(abs(decoded-(bg*.5+64))))
                    if not np.isfinite(error) or error>8: raise AssertionError(("패널 합성",n,side,error))
                    counts.append(dict(frame=n,side=side,background_pixel_error=error))
                if row["event_counts"]:
                    # 숫자·항목명은 같은 불투명 전경색으로 그린 뒤 H.264 색차 오차를 감안해 확인합니다.
                    band=rgba[:155,-355:];rgb=b[:155,-355:,::-1].astype(float)
                    red=(band[:,:,0]>=242)&(band[:,:,1]<78)&(band[:,:,2]<109)&(band[:,:,3]>=250)
                    if np.mean(rgb[:,:,0][red]>rgb[:,:,1][red]+30)<.90:
                        raise AssertionError(("빨간 HUD",n))
    finally:
        source.release()
        saved.release()
    return dict(probes=checks,panel_checks=counts,padding=app.HUD_PANEL_PADDING,
                palette=app.EVENT_COLORS,rgba=app.HUD_PANEL_RGBA)


if __name__=="__main__":
    cli=argparse.ArgumentParser()
    cli.add_argument("mode",choices=["all","prepare","local","track","analyze","render"])
    cli.add_argument("--out",type=Path,default=DEFAULT)
    args=cli.parse_args()
    if video_digest(VIDEO)!=DIGEST: raise ValueError("원본을 다시 확인하세요.")
    args.out.mkdir(parents=True,exist_ok=args.mode!="all")
    steps={"prepare":prepare,"local":local_detections,"track":track,"analyze":analyze,"render":render}
    if args.mode=="all":
        for step in steps.values(): step(args.out)
    else:
        steps[args.mode](args.out)

