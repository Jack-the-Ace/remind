# 055가 사용하는 후미등 측정 함수입니다. 원본 픽셀에서 색과 밝기를 읽습니다.
# 사람이 후면에서 확인한 기준점을 추적 상자에 맞추고, 연속된 관측 안에서만 점멸을 찾습니다.
# 표와 그래프로 어떤 램프가 실제 판단에 쓰였는지 다시 볼 수 있습니다.
import csv
import json
from pathlib import Path

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.ndimage import median_filter

ROOT = Path(__file__).resolve().parent
SIDES = ("left", "right", "center")


def rectangle(cx, cy, rw, rh, w, h):
    return (max(0, round((cx-rw/2)*w)), max(0, round((cy-rh/2)*h)),
            min(w, round((cx+rw/2)*w)), min(h, round((cy+rh/2)*h)))


def patch(img, rect):
    x,y,X,Y = rect
    return img[y:Y, x:X]


def levels(region, body):
    # 차체의 중간 밝기를 빼면 카메라 전체가 밝아질 때 받는 영향을 줄일 수 있습니다.
    hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
    hue,sat,val = cv2.split(hsv)
    b,g,r = cv2.split(region.astype(float))
    red = ((hue <= 10) | (hue >= 169)) & (sat >= 70) & (val >= 70)
    amber = (hue >= 8) & (hue <= 35) & (sat >= 65) & (val >= 90)
    reference = float(np.median(body.max(axis=2)))
    # 작은 발광부가 렌즈 일부만 채울 수 있어 가장 밝은 쪽의 분위수도 구합니다.
    # 노란 차체·붉은 렌즈 자체로는 사용을 판정하지 않습니다.
    amber_signal = np.maximum(0, np.minimum(r,g)-b) * (g/255) * (r/255)
    red_signal = np.maximum(0, r-np.minimum(g,b)) * (r/255)**2
    angle = hue.astype(float)*np.pi/90
    hue_mean = np.angle(np.sum(sat * np.exp(1j*angle))) * 90/np.pi % 180
    return {k:round(float(v),3) for k,v in dict(
        R=r.mean(), G=g.mean(), B=b.mean(), H=hue_mean, S=sat.mean(), V=val.mean(),
        relative=np.percentile(val,85)-reference, body=reference,
        green_contrast=np.median(g)-reference,
        red_fraction=red.mean(), amber_fraction=amber.mean(),
        amber=np.percentile(amber_signal,90), red=np.percentile(red_signal,85),
        overexposed=np.mean((region.min(axis=2)>242))).items()}


def runs(mask):
    d=np.diff(np.r_[False,mask,False].astype(int))
    return list(zip(np.flatnonzero(d==1),np.flatnonzero(d==-1)))


def bouts(rows, side, fps):
    # 끊긴 구간을 이어 붙이면 가림 전후 밝기 차이가 가짜 점멸이 됩니다.
    ok=[r.get(side+"_valid",False) for r in rows]
    spans=[]
    for i,j in runs(ok):
        if j-i < 1.25*fps:
            continue
        brightness=np.array([r[side+"_relative"] for r in rows[i:j]])
        green=np.array([r[side+"_green_contrast"] for r in rows[i:j]])
        for channel,threshold in (("green_contrast",38),("relative",37),("amber",20),("red",37)):
            a=median_filter([r[side+"_"+channel] for r in rows[i:j]],size=3,mode="nearest")
            # 하얗게 포화되는 황색등은 녹색 채널 변화도 큽니다. 유색광이 있는 렌즈만 봅니다.
            if channel in ("green_contrast","relative") and np.median([r[side+"_red_fraction"]+
                    r[side+"_amber_fraction"] for r in rows[i:j]])<.18:
                continue
            # 켜질 때와 꺼질 때 다른 문턱을 써서 한 번의 점등 안의 잡음을 두 번 세지 않습니다.
            low,high=np.percentile(a,[15,85])
            if high-low<threshold:continue
            gates=low+np.array([.34,.64])*(high-low)
            start=None
            saw_off=False
            series=[]
            for idx,value in enumerate(a):
                if value<=gates[0]:
                    saw_off=True
                if start is None:
                    if saw_off and value>=gates[1]:start=idx
                    continue
                finished=value<=gates[0]
                if not finished and idx+1<len(a):continue
                end=idx-1 if finished else idx
                duration=(end-start+1)/fps
                pad=max(2,round(.19*fps))
                outside=np.r_[max(0,start-pad):start,end+1:min(len(a),end+1+pad)]
                lit=channel=="green_contrast" or (outside.size and max(
                    np.median(v[start:end+1])-np.median(v[outside]) for v in (brightness,green))>=8)
                if .075<=duration<=.9 and lit:
                    peak=start+int(np.argmax(a[start:end+1]))
                    series.append(dict(first=rows[i+start]["frame"],last=rows[i+end]["frame"],
                                       peak=rows[i+peak]["frame"],duration=round(duration,3),
                                       end_observed=bool(finished)))
                start=None
            # 최소 세 번의 점등과 일정한 두 간격이 필요합니다.
            group=[]
            for item in series:
                if group and not .36 <= (item["first"]-group[-1]["first"])/fps <= 1.45:
                    group=[]
                group.append(item)
                if len(group)>=3:
                    periods=np.diff([s["first"] for s in group])/fps
                    if np.ptp(periods)>.32:
                        group=group[-2:]
                        continue
                    record=dict(side=side,channel=channel,first=group[0]["first"],last=item["last"],
                                periods_s=periods.round(3).tolist(),pulses=group.copy())
                    if spans and spans[-1]["channel"]==channel and spans[-1]["first"]==record["first"]:
                        spans[-1]=record
                    else: spans.append(record)
    return spans


def fit(img,w,h):
    tile=np.zeros((h,w,3),np.uint8)
    if img is None or not img.size: return tile
    scale=min(w/img.shape[1],h/img.shape[0])
    W,H=max(1,round(img.shape[1]*scale)),max(1,round(img.shape[0]*scale))
    x,y=(w-W)//2,(h-H)//2
    tile[y:y+H,x:x+W]=cv2.resize(img,(W,H),interpolation=cv2.INTER_NEAREST if scale>1 else cv2.INTER_AREA)
    return tile


def plot(rows, path, title):
    fig,axs=plt.subplots(4,1,figsize=(11,9),sharex=True,layout="constrained")
    t=[r["time"] for r in rows]
    for side,col in zip(SIDES,("#1475bd","#d36a05","#7857a8")):
        for ax,key in zip(axs,("relative","red_fraction","amber_fraction","red")):
            ax.plot(t,[r.get(side+"_"+key,np.nan) if r.get(side+"_valid") else np.nan for r in rows],
                    color=col,label=side,linewidth=1.3)
    for ax,y in zip(axs,("Lamp V85 - body V50","Red pixel fraction","Amber pixel fraction","Red emission score")):
        ax.set_ylabel(y); ax.grid(alpha=.23)
    axs[0].legend(ncols=3);axs[0].set_title(title)
    axs[-1].set_xlabel("Original video time (s) | gaps = insufficient observation")
    fig.savefig(path,dpi=140);plt.close(fig)


def evidence(rows, fps):
    flashes={s:bouts(rows,s,fps) for s in SIDES[:2]}
    # 제동은 양쪽과 중앙 보조등에서 모두 밝은 상태와 어두운 상태가 관찰될 때만 인정합니다.
    brakes=[]
    for i,j in runs([all(r.get(s+"_valid",False) for s in SIDES) for r in rows]):
        if j-i<fps: continue
        a=np.array([[r.get(s+"_brake",r[s+"_red"]) for s in SIDES] for r in rows[i:j]])
        a=median_filter(a,size=(5,1),mode="nearest")
        lo,hi=np.percentile(a,[5,85],axis=0)
        if np.any(hi-lo < [20,20,25]): continue
        on=(a>lo+.46*(hi-lo)).all(axis=1)
        off=(a<lo+.34*(hi-lo)).all(axis=1)
        if not any(b-a>=.20*fps for a,b in runs(off)):continue
        for k,l in runs(on):
            if l-k>=.55*fps:
                brakes.append([rows[i+k]["frame"],rows[i+l-1]["frame"]])
    labels=[]
    for side,other in (("left","right"),("right","left")):
        for f in flashes[side]:
            start,end=f["first"],f["last"]
            # 흰 차체가 측정 칸으로 들어와도 밝기만 오를 수 있습니다.
            # 밝기만 검출한 경우에는 색을 보는 채널에서도 세 번 같은 시점에 켜져야 합니다.
            if f["channel"]=="relative" and not any(
                g["channel"]!="relative" and sum(any(abs(a["first"]-b["first"])<=.14*fps for b in g["pulses"])
                    for a in f["pulses"])>=3 for g in flashes[side]):
                continue
            window=[r for r in rows if start<=r["frame"]<=end]
            if not all(r.get(other+"_valid") for r in window):continue
            opposite=[g for g in flashes[other] if min(g["last"],end)>=max(g["first"],start)]
            # 동시 점멸을 판정할 때는 각 점등 시작의 시차도 확인합니다.
            sync=any(sum(any(abs(a["first"]-b["first"])<=.14*fps for b in g["pulses"])
                         for a in f["pulses"])>=3 for g in opposite)
            if opposite and not sync: continue
            if sync and side=="right":continue
            kind="hazards" if sync else side+"_indicator"
            overlaps=[[max(start,a),min(end,b)] for a,b in brakes if min(end,b)-max(start,a)>=.45*fps]
            if overlaps:
                kind="brake+"+kind
            e=dict(kind=kind,first=start,last=end,channel=f["channel"],brake_overlap=overlaps)
            if not any(x["kind"]==kind and min(x["last"],end)>=max(x["first"],start) for x in labels):
                labels.append(e)
    return dict(flashes=flashes,brake_intervals=brakes,patterns=labels)


def measure(case,out):
    cfg=case["lamps"]
    data=json.loads((out/"track.json").read_text(encoding="utf8"))
    cap=cv2.VideoCapture(str(ROOT/"videos"/case["video"]))
    fps=data["fps"];first=case["frames"][0]
    cap.set(cv2.CAP_PROP_POS_FRAMES,first-1)
    dest=out/"analysis";dest.mkdir(exist_ok=True)
    raw=cv2.VideoWriter(str(dest/"target.mp4"),cv2.VideoWriter_fourcc(*"mp4v"),fps,(640,360))
    writer=cv2.VideoWriter(str(dest/"lamps.mp4"),cv2.VideoWriter_fourcc(*"mp4v"),fps,(896,360))
    keys=np.array(cfg["anchors"],float)
    rows=[]
    try:
        if not all(v.isOpened() for v in (cap,raw,writer)): raise OSError("영상 열기 실패")
        for track in data["rows"]:
            ok,image=cap.read()
            if not ok:raise OSError("원본 프레임 읽기 실패")
            f=track["frame"];row={k:track[k] for k in ("frame","time","track_id")}
            car=None;zoom=[None]*3;boxes=[]
            if track["box"] is not None:
                car=patch(image,np.maximum(0,np.rint(track["box"]).astype(int)))
                h,w=car.shape[:2]
                xy=[np.interp(f,keys[:,0],keys[:,k]) for k in range(1,keys.shape[1])]
                body=patch(car,rectangle(*cfg["body"],w,h))
                for n,side in enumerate(SIDES[:len(xy)//2]):
                    rect=rectangle(*xy[n*2:n*2+2],*cfg["size"][n],w,h)
                    roi=patch(car,rect)
                    if not roi.size or not body.size:continue
                    zoom[n]=roi;boxes.append((n,rect))
                    metrics=levels(roi,body)
                    row.update({side+"_"+k:v for k,v in metrics.items()})
                    row[side+"_width"]=roi.shape[1];row[side+"_height"]=roi.shape[0]
                    # 가까운 차가 가리거나 렌즈가 너무 작으면 값을 남겨도 판정에는 쓰지 않습니다.
                    allowed=any(a<=f<=b for a,b in cfg["visible"].get(side,[]))
                    reason=("view" if not allowed else "resolution" if roi.shape[0]<5 or roi.shape[1]<9
                            else "clipping" if metrics["overexposed"]>.65 and
                            metrics["red_fraction"]+metrics["amber_fraction"]<.12 else "ok")
                    row[side+"_reason"]=reason;row[side+"_valid"]=reason=="ok"
                if "brake_anchors" in cfg and body.size:
                    # 이 차는 제동용 윗칸과 방향지시용 아랫칸이 분리되어 있습니다.
                    anchors=np.asarray(cfg["brake_anchors"])
                    for n,side in enumerate(SIDES[:2]):
                        cx,cy=[np.interp(f,anchors[:,0],anchors[:,k]) for k in (1+2*n,2+2*n)]
                        region=patch(car,rectangle(cx,cy,.062,.08,w,h))
                        if region.size:row[side+"_brake"]=levels(region,body)["G"]
                    if "center_G" in row:row["center_brake"]=row["center_G"]
            raw.write(fit(car,640,360))
            marked=car.copy() if car is not None else None
            colors=[(255,190,0),(0,145,255),(200,100,220)]
            for n,(x,y,X,Y) in boxes:cv2.rectangle(marked,(x,y),(X-1,Y-1),colors[n],1)
            canvas=np.zeros((360,896,3),np.uint8)
            canvas[:315,:550]=fit(marked,550,315)
            for n,side in enumerate(SIDES):
                canvas[n*105:n*105+102,552:]=fit(zoom[n],344,102)
                cv2.putText(canvas,side+" "+row.get(side+"_reason","hold"),(555,n*105+18),0,.50,colors[n],1)
            source=("MANUAL REFERENCE" if data.get("source")=="manual_reference_template" else
                    f"ID {row['track_id']}" if car is not None else "TRACK HOLD")
            cv2.putText(canvas,f"F{f}   {row['time']:.2f} s   {source}",(16,344),0,.72,(255,255,255),1)
            writer.write(canvas);rows.append(row)
    finally:
        cap.release();writer.release();raw.release()
    fields=list(dict.fromkeys(k for r in rows for k in r))
    with (dest/"frames.csv").open("w",newline="",encoding="utf-8-sig") as stream:
        table=csv.DictWriter(stream,fields);table.writeheader();table.writerows(rows)
    summary=evidence(rows,fps)
    summary["valid_frames"]={s:sum(bool(r.get(s+"_valid")) for r in rows) for s in SIDES}
    summary["fps"]=fps
    (dest/"patterns.json").write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding="utf8")
    plot(rows,dest/"signals.png",out.name)
