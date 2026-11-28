# 076 · 전방 영상의 직진 신호와 선택 차량의 정지선 초과 시간을 함께 확인합니다.
# 전방 AVI → 같은 SUV 추적 → 신호와 도색 관측 → 영상 시계로 1.5초마다 집계합니다.
# 결과에는 원본 음성을 넣습니다. 판독 근거는 영상 폴더 밖에 남깁니다.
from pathlib import Path
from importlib import import_module
import sys, json, cv2, numpy as np, hashlib, subprocess
from track_preview import Target
from preview_lane_track_197 import track_vehicles
app = import_module("041_redbox_mvp")
media = import_module("067_render_driving_review")
out = Path(__file__).resolve().parent / "output/mvp_review_redstop"
root = out.parents[1]
ids = ["133431","133631"]
def source(k):
    return root / "videos" / f"BB_20261123_{k}.avi"
def write(p,data):
    p.parent.mkdir(exist_ok=True,parents=True)
    p.write_text(json.dumps(data,ensure_ascii=False,separators=(",",":")),encoding="utf8")
def load(p):
    return json.loads(p.read_text(encoding="utf8"))
def track(k):
    first,point = (721,(990,712)) if k=="133431" else (1,(1030,790))
    model,classes=app.new_tracker()
    target=Target()
    rows=[]
    last=None
    with app.capture(source(k),"front") as cap:
        for f in range(1,int(cap.get(7))+1):
            ok,im=cap.read()
            if not ok: raise OSError(f)
            t=cap.get(cv2.CAP_PROP_POS_MSEC)/1000
            if k=="133431" and f>=first:
                crop=im[485:985,585:1465]
                cars=track_vehicles(model,crop,classes,0)
                for c in cars: c["box"]=(np.asarray(c["box"])+[585,485,585,485]).tolist()
            else:
                cars=track_vehicles(model,im,classes,0) if f>=first else []
            assist=False
            if f==first:
                car=app.select_vehicle(cars,point)
                if not car: raise ValueError((k,f,point,cars))
                target.select(car,im,f)
            else:
                car=target.update(cars,im,f) if f>first else None
            if k=="133431" and f>=first and car is None:
                # 원본에서 확인한 중앙 SUV의 위치 주변에 실제 검출 상자가 하나일 때만 재선택합니다.
                tp=[24,26,28,30,33,36,39,42,45,48,50,52,54,56,58,60]
                px=np.interp(t,tp,[991,981,989,994,990,973,965,972,972,985,1008,1010,1003,1013,1011,1016])
                py=np.interp(t,tp,[710,719,740,744,732,729,725,722,718,709,713,717,735,749,750,750])
                hits=[c for c in cars if c["id"] and c["box"][0]<px<c["box"][2] and c["box"][1]<py<c["box"][3]]
                if len(hits)==1:
                    car=hits[0]; target.select(car,im,f);assist=True
            # 상단 시각 문자를 뺀 전체 원본 화소가 완전히 동일한지 검사합니다.
            fingerprint=hashlib.blake2b(im[28:],digest_size=16).hexdigest()
            rows.append(dict(frame=f,seconds=t,box=car["box"] if car else None,id=car["id"] if car else None,guided_reselection=assist,duplicate=fingerprint==last))
            last=fingerprint
    write(out/(k+"_track.json"),rows)
if __name__=="__main__" and sys.argv[1]=="track":
    for key in sys.argv[2:] or ids:track(key)


from redbox_stop_line import locate_paint
from itertools import groupby

LABEL = "정지선위반"
def regions(k,t):
    # 전방 원본에서 기록한 직진 신호 머리와 동일 정지선의 위치. 사이 프레임은 보간한 뒤 실제 화소로 재검사합니다.
    if k=="133631":
        if t>41.5:return None
        return (1040,498,47,[(635,916),(1380,895)])
    if t<48:return None
    ts=[48,49,50,51,52,53,54,55,56,57,58,59,60]
    xs=[1019,1019,1012,1022,1026,1022,1023,1027,1032,1035,1039,1039,1040]
    ys=[636,630,620,606,588,569,541,518,496,490,497,498,499]
    line_y=[720,721,730,739,751,762,795,837,884,909,915,916,916]
    xp,yp,ly=[float(np.interp(t,ts,v)) for v in (xs,ys,line_y)]
    span=float(np.interp(t,[48,52,56,60],[108,150,260,365]))
    return xp,yp,float(np.interp(t,[48,54,58],[21,36,47])),[(1010-span,ly+2),(1010+span,ly-4)]

def bridge(k,rows):
    # 양끝 상자에서 얻은 차체 무늬가 현재 원본의 같은 위치에서 모두 맞을 때만 짧은 공백을 복구합니다.
    cap=cv2.VideoCapture(str(source(k)))
    try:
        for missing,group in groupby(range(len(rows)),lambda i:rows[i]["box"] is None):
            seq=list(group);a,b=seq[0]-1,seq[-1]+1
            if not missing or len(seq)>9 or a<0 or b>=len(rows):continue
            boxes=[np.array(rows[j]["box"]) for j in (a,b)]
            if np.max(abs(boxes[0]-boxes[1]))>24:continue
            cap.set(1,a)
            imgs=[]
            for j in range(a,b+1):
                ok,im=cap.read()
                if not ok:raise OSError(j)
                imgs.append(cv2.cvtColor(im,cv2.COLOR_BGR2GRAY))
            def patch(image,box):
                x,y,X,Y=np.rint(box).astype(int)
                dx=(X-x)//6;dy=(Y-y)//6
                return cv2.resize(image[y+dy:Y-dy,x+dx:X-dx],(60,40))
            refs=[patch(imgs[0],boxes[0]),patch(imgs[-1],boxes[-1])]
            for j in seq:
                frac=(j-a)/(b-a);box=(1-frac)*boxes[0]+frac*boxes[1]
                sample=patch(imgs[j-a],box)
                scores=[float(cv2.matchTemplate(sample,ref,cv2.TM_CCOEFF_NORMED)[0,0]) for ref in refs]
                if min(scores)>.82:
                    rows[j].update(box=box.tolist(),bridge_scores=scores,id=rows[a]["id"])
    finally:
        cap.release()

def native_paint(im,box,prior):
    # 멀리 있는 가는 정지선은 원본 해상도에서 차량 양옆의 연속 도색을 확인합니다.
    a,b,c,d=box;xs=np.r_[np.arange(int(a)-55,int(a)-8),np.arange(int(c)+8,int(c)+55)]
    yp=np.interp(xs,*np.asarray(prior).T).round().astype(int)
    vals=[]
    for delta in range(-14,15):
        y=yp+delta
        center=im[y,xs].mean(1)
        road=(im[y-5,xs].mean(1)+im[y+5,xs].mean(1))*.5
        support=(center>90)&(center-road>12)&(np.ptp(im[y,xs],axis=1)<70)
        frac=min(support[:47].mean(),support[47:].mean())
        if frac>.50:vals.append((frac-.009*abs(delta),delta))
    if vals:
        return (np.array(prior)+[0,max(vals)[1]]).tolist()

def observations(k):
    rows=load(out/(k+"_track.json"))
    if k=="133431":bridge(k,rows)
    with app.capture(source(k),"front") as cap:
        for r in rows:
            ok,im=cap.read()
            if not ok:raise OSError(r["frame"])
            region=regions(k,r["seconds"])
            r.update(lamp="unknown",line=None,beyond=None)
            if not region:continue
            x,y,offset,endpoints=region
            x,y=int(x),int(y)
            crop=im[y-17:y+18,x-15:x+int(offset)+16]
            hue,sat,val=cv2.split(cv2.cvtColor(crop,cv2.COLOR_BGR2HSV))
            mid=15+int(offset*.53)
            def colors(h,s,v,split):
                lit=(s>90)&(v>115)
                band=h[:,:split]; hits=lit[:,:split]
                red=int(np.count_nonzero(hits & ((band<9)|(band>167))))
                amber=int(np.count_nonzero(hits & (band>=10)&(band<34)))
                green=int(np.count_nonzero(lit[:,split:]&(h[:,split:]>67)&(h[:,split:]<100)))
                state="red" if red>=4 and red>amber*.65 and green<4 else "green" if green>=4 and red<4 else "amber" if amber>=5 and amber>red*1.8 else "unknown"
                return state,[red,amber,green]
            label,counts=colors(hue,sat,val,mid)
            r.update(lamp=label,lamp_counts=counts,signal_source="near")
            # 같은 직진 방향에서 두 신호가 함께 녹색으로 바뀌는 것을 확인했습니다.
            # 가까운 LED가 검게 찍힌 프레임은 건너편 같은 방향 신호의 실제 화소로 재검사합니다.
            if label=="unknown" and (k=="133631" or r["seconds"]>=52):
                st=r["seconds"]
                farx,fary=(1107,603) if k=="133631" else (
                    round(np.interp(st,[52,53,54,55,56,57,58,60],[1079,1080,1087,1096,1105,1107,1107,1107])),
                    round(np.interp(st,[52,53,54,55,56,57,58,60],[630,624,612,606,602,600,604,603])))
                h,s,v=cv2.split(cv2.cvtColor(im[fary-9:fary+10,farx-7:farx+26],cv2.COLOR_BGR2HSV))
                # 청색 도로 표지는 제외하고 실제 적색 렌즈의 작은 창을 읽습니다.
                redhits=int(np.count_nonzero((s[:,:15]>95)&(v[:,:15]>105)&((h[:,:15]<9)|(h[:,:15]>168))))
                if redhits>=4:r.update(lamp="red",signal_source="far",far_red_pixels=redhits)
            if not r["box"]:continue
            small=cv2.resize(im,(960,544),interpolation=cv2.INTER_AREA)
            box=np.array(r["box"])/2
            found=locate_paint(small,np.array(endpoints)/2,[box],9,None)
            fine=native_paint(im,r["box"],endpoints) if k=="133431" else None
            if fine is not None:line=np.array(fine)
            elif found is not None:line=found[0]*2
            else:continue
            r["line"]=line.tolist()
            a,b,c,d=r["box"]
            paint_y=np.interp((a+c)/2,line[:,0],line[:,1])
            # 이 후면 시점에서 보이는 양쪽 도색이 차 뒤쪽 바퀴 높이를 지나는지 대조합니다.
            # 정차·접근 장면 모두 원본에서 도색이 차체 뒤쪽에 걸린 위치를 확인했습니다.
            if k=="133631":
                r["beyond"]=bool(tight_pose(r["box"]) and paint_y>=d-.15*(d-b))
            else:
                # 두 측면의 정지선이 뒤범퍼 높이까지 이어지면 앞부분은 이미 선 건너에 있습니다.
                # 이 구간의 원본에서 뒷바퀴·횡단보도 관계를 대조한 보수적인 하단 범위를 씁니다.
                if d-b>=48 and paint_y>=d-.12*(d-b):
                    r["beyond"]=True
                elif paint_y<d-.30*(d-b):
                    r["beyond"]=False
                # 뒤쪽 경계를 벗어났다는 관측만으로 앞부분까지 선 앞으로 복귀했다고 할 수 없습니다.
                # 차체·도색 오차 범위 안이면 기존 None(판독 공백)을 유지합니다.
    for _,group in groupby(range(len(rows)),lambda i:rows[i]["lamp"]=="unknown"):
        ix=list(group);a,b=ix[0],ix[-1]
        if rows[a]["lamp"]=="unknown" and a>0 and b+1<len(rows) and (b-a+2)/30<=.65 and rows[a-1]["lamp"]==rows[b+1]["lamp"]:
            for i in ix:
                rows[i]["lamp"]=rows[a-1]["lamp"];rows[i]["lamp_inferred"]=True
    return rows

def tight_pose(box):
    a,b,c,d=box
    return abs((a+c)/2-1029)<45 and abs(d-929)<26 and c-a>330

def tally(rows):
    # 차량의 속도는 타이머에 사용하지 않습니다. 복제 프레임이나 판독 공백의 시간은 더하지 않습니다.
    events=[];elapsed=0.;intervals=0;last_seen=None;previous=False
    for r in rows:
        t=r["seconds"]
        active=r["lamp"]=="red" and r["beyond"] is True and bool(r["box"])
        clear=r["lamp"] in ("green","amber") or r["beyond"] is False
        if clear or last_seen is not None and t-last_seen>.16:
            elapsed=0.;intervals=0
        if active:
            if previous and not r["duplicate"]:
                elapsed+=t-last_seen
            while elapsed+1e-8>=(intervals+1)*1.5:
                intervals+=1
                e=dict(frame=r["frame"],time_s=t,label=LABEL,track_id=r["id"],hud_anchor=app.event_position(r["box"],1920,1088))
                events.append(app.set_float_slot(e,events))
            last_seen=t
        previous=active
        r.update(active=active,timer=elapsed if active else None,total=len(events))
    return events

if __name__=="__main__" and sys.argv[1]=="observe":
    for key in sys.argv[2:] or ids:
        rows=observations(key);events=tally(rows)
        write(out/(key+"_analysis.json"),dict(rows=rows,events=events))
        print(key,[(e["frame"],round(e["time_s"],2)) for e in events],flush=True)


def filename(k):
    return f"BB_20261123_{k}_정지선위반_분석_11.28.mp4"

def ffmpeg():
    import shutil
    found=shutil.which("ffmpeg") or next(iter((out/"tools").rglob("ffmpeg*.exe")),None)
    if not found:raise RuntimeError("FFmpeg를 설치하거나 PATH를 지정하세요.")
    return str(found)

def render(k,destination=out):
    far=import_module("070_review_far_target")
    data=load(out/(k+"_analysis.json"));rows=data["rows"];events=data["events"]
    destination.mkdir(exist_ok=True)
    path=destination/filename(k)
    if path.exists():raise FileExistsError(path)
    history=root/"output/lane_video_197_stopline_20261124/chrome_final/jobs/bc3b5cf4e40e/frames.jsonl"
    old=[json.loads(s) for s in history.read_text(encoding="utf8").splitlines()]
    plate_reads=[(v["seconds"],v["vehicle_info"]["plate"]) for v in old if v["vehicle_info"]["plate"]]
    base=dict(plate=None,color=None,vehicle_type=None)
    sig=[];probes=set([1,720,1100,1111,1113,1170,1650,1800]); checks_hud={}
    for e in events:probes.update(e["frame"]+delta for delta in (-1,0,30,45,60))
    with app.capture(source(k),"front") as cap:
        fps=cap.get(5);duration=len(rows)/fps
        cmd=[ffmpeg(),"-hide_banner","-loglevel","error","-n","-f","rawvideo","-pix_fmt","bgr24","-s","1920x1088","-r",str(fps),"-i","pipe:0","-i",str(source(k)),"-map","0:v","-map","1:a:0","-c:v","libx264","-preset","veryfast","-crf","17","-pix_fmt","yuv420p","-af",f"atrim=end={duration:.9f}","-c:a","aac","-b:a","96k","-movflags","+faststart",str(path)]
        proc=subprocess.Popen(cmd,stdin=subprocess.PIPE)
        try:
            for r in rows:
                ok,im=cap.read()
                if not ok:raise OSError(r["frame"])
                if r["box"]:
                    base.update(color="진회색 계열",vehicle_type="SUV")
                if k=="133631" and plate_reads and r["seconds"]>=plate_reads[0][0]:
                    base["plate"]=plate_reads[0][1]
                state=("정지선위반 지속  %.2f초"%r["timer"] if r["active"] else
                       "직진 녹색 신호" if r["lamp"]=="green" else
                       "정지선 초과 판독 보류" if r["lamp"]=="red" else "직진 신호 · 정지선 관측 대기")
                hud=dict(r,vehicle_info=base,verdict=LABEL if r["active"] else None,
                         event_counts={LABEL:r["total"]},status="observed" if r["box"] else "tracking_hold",
                         status_text=state,stop_line={"line":r["line"]},boundary=None)
                painted=far.compose(im,hud,events[:r["total"]])
                sig.append(media.signature(painted))
                if r["frame"] in probes:
                    # 실제 저장된 영상에서 상단 TOTAL, 하단 시계, 차량 주변 플로팅을 영역별로 비교합니다.
                    checks_hud[r["frame"]]=[media.signature(painted[y:Y,x:X]) for x,y,X,Y in
                        [(1030,0,1920,230),(0,870,850,1060),(300,220,1820,910)]]
                proc.stdin.write(painted.tobytes())
        finally:
            proc.stdin.close()
            if proc.wait():raise RuntimeError("FFmpeg 출력 실패")
    report=media.verify(path,sig,(1920,1088),fps)
    cap=cv2.VideoCapture(str(path))
    hud_checks=[]
    try:
        for frame,refs in checks_hud.items():
            cap.set(1,frame-1);ok,im=cap.read()
            if not ok:raise IOError(frame)
            errors=[float(np.abs(media.signature(im[y:Y,x:X]).astype(float)-ref).mean()) for ref,(x,y,X,Y) in
                    zip(refs,[(1030,0,1920,230),(0,870,850,1060),(300,220,1820,910)])]
            if max(errors)>6:raise ValueError((frame,errors))
            hud_checks.append([frame,errors])
    finally:
        cap.release()
    report["hud_checks"]=hud_checks
    # 시작·중간·끝에서 원본 PCM과 AAC를 다시 풀어 시간 이동량을 측정합니다.
    def pcm(file):
        command=[ffmpeg(),"-loglevel","error","-i",str(file),"-map","0:a:0","-f","s16le","-ac","1","-ar","16000","pipe:1"]
        return np.frombuffer(subprocess.check_output(command),np.int16)
    audio=pcm(path);original=pcm(source(k))
    from scipy.signal import correlate
    checks=[]
    for t in (1,15,30,45,58):
        pos=t*16000
        a=original[pos:pos+8000].astype(float);b=audio[pos-1000:pos+9000].astype(float)
        c=correlate(b,a,mode="valid");lag=int(np.argmax(c))-1000
        corr=np.corrcoef(a,b[1000+lag:9000+lag])[0,1]
        if abs(lag)>16 or corr<.80: raise ValueError(("음성 동기",t,lag,corr))
        checks.append([t,lag,round(corr,4)])
    report.update(audio_checks=checks,source_audio_samples=len(original),saved_audio_samples=len(audio))
    write(out/(k+"_verify.json"),report)
    cap=cv2.VideoCapture(str(path))
    for i in sorted({1,1800,1171 if k=="133631" else 1600}|{e["frame"] for e in events[:2]}):
        cap.set(1,i-1);ok,im=cap.read()
        if not ok:raise IOError(i)
        cv2.imencode(".jpg",cv2.resize(im,(960,544)))[1].tofile(out/f"{k}_HUD_F{i}.jpg")
    cap.release()
    print(path,report,flush=True)

if __name__=="__main__" and sys.argv[1]=="render":
    import argparse
    cli=argparse.ArgumentParser()
    cli.add_argument("keys",nargs="*")
    cli.add_argument("--destination",type=Path,default=out)
    args=cli.parse_args(sys.argv[2:])
    for key in args.keys or ids:render(key,args.destination)


def audit(k,path):
    # 저장된 실제 화소가 기록과 맞는지, 숫자·타이머·플로팅을 하나씩 바꾼 화면과 비교합니다.
    far=import_module("070_review_far_target")
    a=load(out/(k+"_analysis.json"));rows=a["rows"];events=a["events"]
    chosen=[events[0],events[1],events[-1]] if len(events)>1 else events
    results=[]
    cap=cv2.VideoCapture(str(path))
    with app.capture(source(k),"front") as raw:
        for e in chosen:
            for shift in [-1,0,30,45,61]:
                n=e["frame"]+shift
                if not 1<=n<=len(rows):continue
                r=rows[n-1];raw.set(1,n-1);cap.set(1,n-1)
                ok,a0=raw.read();ok2,b=cap.read()
                if not ok or not ok2:raise IOError(n)
                # 비교 대상은 우측 패널, 타이머와 플로팅 영역입니다. 좌측 차량정보는 양쪽에 동일하게 둡니다.
                ready=r["active"]
                hud=dict(r,vehicle_info=dict(color=None,vehicle_type=None,plate=None),verdict=LABEL if ready else None,
                         event_counts={LABEL:r["total"]},status="observed" if r["box"] else "tracking_hold",
                         status_text=("정지선위반 지속  %.2f초"%r["timer"] if ready else
                                      "직진 녹색 신호" if r["lamp"]=="green" else
                                      "정지선 초과 판독 보류" if r["lamp"]=="red" else "직진 신호 · 정지선 관측 대기"),
                         stop_line={"line":r["line"]},boundary=None)
                past=events[:r["total"]]; reference=far.compose(a0,hud,past)
                def check(alt):
                    mask=cv2.absdiff(reference,alt).max(2)>38
                    if not mask.any():raise AssertionError(("표시 차이 없음",n))
                    margin=cv2.absdiff(b,alt)[mask].mean()-cv2.absdiff(b,reference)[mask].mean()
                    if margin<4:raise AssertionError((n,float(margin)))
                    return round(float(margin),2)
                counts=check(far.compose(a0,dict(hud,event_counts={LABEL:r["total"]+9}),past))
                timer=check(far.compose(a0,dict(hud,status_text="비교 99.99초"),past)) if r["box"] else None
                visible=0<=r["seconds"]-e["time_s"]<2
                alt=[x for x in past if x!=e] if visible else past+[dict(e,time_s=r["seconds"])]
                floating=check(far.compose(a0,hud,alt))
                results.append(dict(frame=n,event=e["frame"],visible=visible,total=counts,timer=timer,floating=floating))
    cap.release()
    write(out/(k+"_pixels.json"),results)

if __name__=="__main__" and sys.argv[1]=="audit":
    key=sys.argv[2];audit(key,Path(sys.argv[3])/filename(key))

