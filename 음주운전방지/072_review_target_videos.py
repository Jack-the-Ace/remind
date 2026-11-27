# 072 · 선택 차량 두 대의 원본 시각, 차선 접촉, 등화와 차량 정보를 비교합니다.
# 006의 추적과 034의 시간 집계, 041의 HUD를 사용합니다. 처음 클릭한 차만 기록합니다.
# 원본 영상을 읽어 관측 JSON과 단독 재생 MP4를 만들고, 저장 프레임을 다시 대조합니다.
import argparse
from collections import Counter
from importlib import import_module
import json
from pathlib import Path

import cv2
import numpy as np
import torch
from ultralytics import YOLO

from track_preview import Target, video_digest
from preview_lane_track_197 import track_vehicles, predict_lane
from redbox_lane_geometry import ShortTargetMatch
from redbox_vehicle_info import VehicleInfo
from rear_lamp_patterns import rectangle, patch, levels, bouts

app=import_module("041_redbox_mvp")
lane=app.crossing_module
far=import_module("070_review_far_target")
media=import_module("067_render_driving_review")
ROOT=Path(__file__).resolve().parent
NAMES=("졸음운전4","테스트용1")
CLICKS=((329,237),(661,515))
OUT=ROOT/"output/mvp_review_pair"

def save(path,obj):
    path.write_text(json.dumps(obj,ensure_ascii=False,allow_nan=False),encoding="utf8")

def read(path):
    return json.loads(path.read_text(encoding="utf8"))

def track(k,out):
    cap=cv2.VideoCapture(str(ROOT/"videos"/(NAMES[k]+".mp4")))
    fps=cap.get(5)
    model,classes=app.new_tracker()
    target=Target()
    matcher=ShortTargetMatch()
    rows=[]
    while True:
        ok,image=cap.read()
        if not ok: break
        f=len(rows)+1
        x,y,X,Y=(175,145,595,330) if k==0 else (0,0,image.shape[1],image.shape[0])
        cars=track_vehicles(model,image[y:Y,x:X],classes,0)
        for car in cars:
            car["box"]=(np.array(car["box"])+[x,y,x,y]).tolist()
        if f==1:
            car=app.select_vehicle(cars,CLICKS[k])
            target.select(car,image,f)
        else:
            car=target.update(cars,image,f)
        sec=lane.source_seconds(cap,f,fps)
        car,source=matcher.update(image,car,cars,sec)
        small=cv2.resize(cv2.cvtColor(image[round(.60*image.shape[0]):],cv2.COLOR_BGR2GRAY),(160,64),interpolation=cv2.INTER_AREA)
        change=0 if f==1 else float(cv2.absdiff(small,previous).mean())
        previous=small
        rows.append(dict(frame=f,seconds=sec,car=car,cars=cars,track_source=source,change=change))
    if len(rows)!=round(cap.get(7)): raise ValueError('원본 프레임 누락')
    cap.release()
    save(out/(NAMES[k]+'_추적.json'),rows)
    print(NAMES[k],len(rows),sum(bool(r["car"]) for r in rows),flush=True)


def motion(k,out):
    from redbox_lane_geometry import recording_clock
    cap=cv2.VideoCapture(str(ROOT/'videos'/(NAMES[k]+'.mp4')))
    try: return recording_clock(cap,1,round(cap.get(7)),lane.source_seconds)
    finally: cap.release()

SOURCE_SHA=('4acd0a99a4566c944745517b1597fed40ae43ae77ffaeaa59a55681c5e2e53c3',
            '059c68a8f4ee9bfb405c2ef063a2ef24930e601dfb54920e28ebceb6bba77760')
def identity(k,rows):
    if video_digest(ROOT/'videos'/(NAMES[k]+'.mp4'))!=SOURCE_SHA[k]: raise ValueError('차량 선택을 검토한 원본과 다릅니다.')
    # 가림 뒤에는 원본에서 따로 재선택한 프레임만 허용합니다. 다른 영상에는 이 설정을 적용하지 않습니다.
    if k==0:
        for first,click in RESELECT.items():
            initial=rows[first-1]
            chosen=app.select_vehicle(initial['cars'],click)
            ident=chosen['id']
            for row in rows[first-1:]:
                matches=[c for c in row['cars'] if c['id']==ident]
                if len(matches)!=1: break
                row.update(car=matches[0],track_source='manual_reselection' if row['frame']==first else 'bytetrack_after_reselection')

def plate_detail(k,out,rows,clock):
    # 차량 안에서 번호판의 작은 테두리를 다시 찾고, 문자 영역만 기존 두 OCR 엔진으로 읽어 봅니다.
    if k!=1: return
    from redbox_vehicle_info import WindowsOCR,PLATE_CHARACTERS,PLATE
    reader,_=app.ocr()
    windows=WindowsOCR()
    cap=cv2.VideoCapture(str(ROOT/'videos'/(NAMES[k]+'.mp4')))
    samples=[]
    previous=-10
    try:
        for row,obs in zip(rows,clock):
            f=row['frame'];t=row['seconds']
            if not 29.5<=t<=32.5 or obs['duplicate'] or not row['car'] or f-previous<2: continue
            previous=f
            cap.set(1,f-1);ok,im=cap.read()
            if not ok: raise OSError(f)
            x,y,X,Y=np.rint(row['car']['box']).astype(int)
            g=cv2.cvtColor(im[max(0,y):Y,max(0,x):X],cv2.COLOR_BGR2GRAY)
            h,w=g.shape
            contours=cv2.findContours(cv2.Canny(g,18,55),cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)[0]
            found=[]
            for contour in contours:
                a,b,A,B=cv2.boundingRect(contour)
                if not (.10*w<A<.21*w and 1.8<A/B<5 and .33*h<b<.48*h and .08*w<a<.42*w): continue
                found.append((abs((b+B/2)/h-.45)+abs(A/w-.14),a,b,A,B))
            if not found: continue
            _,a,b,A,B=min(found)
            text=g[b+2:b+B-2,a+2:a+A-2]
            if text.size==0:continue
            guesses=[]
            for v in [text,cv2.createCLAHE(2,(4,2)).apply(text)]:
                guesses.append(windows.read(v))
                if reader:
                    words=reader.recognize(cv2.resize(v,None,fx=4,fy=4,interpolation=cv2.INTER_CUBIC),allowlist=PLATE_CHARACTERS)
                    guesses.extend(word[1] for word in words)
            samples.append(dict(frame=f,seconds=t,region=list(map(int,(x+a,y+b,x+a+A,y+b+B))),raw=guesses,
                                full=sorted(set(w for w in guesses if PLATE.fullmatch(w)))))
    finally:
        windows.close();cap.release()
    save(out/(NAMES[k]+'_번호판영역.json'),samples)

def vehicle_evidence(k,out,rows,clock):
    import re
    from redbox_brand import restore,predict_crops
    from redbox_emblem import read_policy,inspect_target,TargetBrand
    badge=import_module('059_review_compcars_video')
    reader,state=app.ocr()
    info=VehicleInfo(reader)
    cap=cv2.VideoCapture(str(ROOT/'videos'/(NAMES[k]+'.mp4')))
    evidence=[]
    colors=VehicleInfo()
    brand='-'
    model_name='-'
    word_votes=Counter()
    if k==1:
        weights=ROOT/'output/emblem_v1/crop_training/main/weights/best.pt'
        detector=YOLO(str(weights))
        policy=read_policy(ROOT/'output/emblem_v1/crop_eval/policy.json',weights)
        accumulator=TargetBrand()
        net,ck=restore(ROOT/'output/compcars_brand/train/best.pt')
    snapshots=[]
    last_read=-100
    recent_plate=None
    try:
        for row,obs in zip(rows,clock):
            ok,image=cap.read();assert ok
            f=row['frame'];car=row['car'];sec=row['seconds']
            if car and not obs['duplicate'] and f%6==1:
                colors.sample(image,car,f)
            info_now=colors.snapshot()
            # 후면이 크게 보이는 지정 구간에서는 서로 다른 원본 관측을 촘촘히 비교합니다.
            if car and not obs['duplicate'] and (k==0 or sec>=29.5) and f-last_read>=2 and sec<=32.5:
                last_read=f
                if recent_plate is None:
                    info.sample(image,car,f)
                    if info.ocr_frames and info.ocr_frames[-1]['frame']==f:
                        evidence.append(dict(kind='plate',frame=f,seconds=sec,**{'matches':info.ocr_frames[-1]['matches']}))
                    recent_plate=info.plate_candidate()
                if k==1 and (not any(e['kind']=='brand' for e in evidence) or
                             f-max(e['frame'] for e in evidence if e['kind']=='brand')>=6):
                    box=car['box'];x,y,X,Y=np.rint(box).astype(int)
                    crop=image[max(0,y):Y,max(0,x):X]
                    proposals,labels=inspect_target(detector,image,box,[c['box'] for c in row['cars'] if c['id']!=car['id']],policy)
                    brand=accumulator.update('selected',f,labels)
                    prob,_=predict_crops(net,ck,[crop])
                    mobile=ck['classes'][int(prob[0].argmax())]
                    words=badge.read_badges(reader,info.windows_ocr,crop) if info.windows_ocr else []
                    hits=set()
                    for word in words:
                        hits.update(badge.BADGES.intersection(re.findall(r'[A-Z0-9]+',word['text'].upper())))
                    word_votes.update(hits)
                    known=[w for w,n in word_votes.items() if n>=2]
                    model_name=known[0] if len(known)==1 else '-'
                    evidence.append(dict(kind='brand',frame=f,seconds=sec,emblems=proposals,accepted=sorted(labels),
                                         design_top=mobile,design_conf=float(prob[0].max()),badge_words=words))
            info_now.update(plate=recent_plate,brand=brand,model_name=model_name)
            snapshots.append(info_now)
    finally:
        cap.release()
        if info.windows_ocr: info.windows_ocr.close()
    save(out/(NAMES[k]+'_차량정보.json'),dict(engine=state,observations=evidence,frames=snapshots))

RESELECT={436:(405,220),734:(330,230)}

# 시작점은 원본에서 직접 고른 도색입니다. 시간이나 차량 위치를 사건 조건으로 쓰지 않습니다.
SEEDS=(
    {'left':[(303,248),(237,284),(154,345)],'right':[(344,249),(380,276),(466,327)]},
    {'divider':[(704,539),(617,586),(468,680)],'outside':[(803,543),(849,590),(992,678)]},
)

def cache_masks(k,out):
    device=torch.device('cuda:0')
    model=app.lane()
    timing=tuple(torch.cuda.Event(enable_timing=True) for _ in range(2))
    cap=cv2.VideoCapture(str(ROOT/'videos'/(NAMES[k]+'.mp4')))
    folder=out/('mask'+str(k))
    folder.mkdir(exist_ok=True)
    for f in range(1,round(cap.get(7))+1):
        ok,im=cap.read()
        if not ok: raise OSError(f)
        top=round(im.shape[0]*(.5 if k==0 else .58))
        mask,_=predict_lane(model,im[top:],device,lane.SIZE,timing)
        cv2.imencode('.png',mask*255)[1].tofile(folder/f'{f}.png')
    cap.release()

def lamp_measure(image,box,f,k):
    row={'frame':f}
    if box is None: return row
    x,y,X,Y=np.rint(box).astype(int)
    crop=image[max(0,y):Y,max(0,x):X]
    h,w=crop.shape[:2]
    if min(w,h)<20: return row
    body=patch(crop,rectangle(.50,.71,.33,.14,w,h))
    for side,cx in [('left',.14),('right',.73 if k==1 else .84)]:
        lamp=patch(crop,rectangle(cx,.43,.13,.14,w,h))
        if min(lamp.shape[:2])<3 or not body.size: continue
        row[side+'_valid']=True
        row.update({side+'_'+key:value for key,value in levels(lamp,body).items()})
    return row


def analyze(k,out):
    from redbox_lane_geometry import PaintCurve
    rows=read(out/(NAMES[k]+'_추적.json'))
    identity(k,rows)
    clock=read(out/(NAMES[k]+'_시계.json'))
    info=read(out/(NAMES[k]+'_차량정보.json'))['frames']
    cap=cv2.VideoCapture(str(ROOT/'videos'/(NAMES[k]+'.mp4')))
    fps=cap.get(5)
    curves={('left','right')[i]:PaintCurve(pts) for i,pts in enumerate(SEEDS[k].values())}
    assessor=lane.SceneLaneAnalysis(fps,[[0,0],[1,1]])
    events=[]
    counts=Counter()
    frames=[]
    lamps=[]
    for row,obs,metadata in zip(rows,clock,info):
        ok,im=cap.read()
        if not ok: raise OSError(row['frame'])
        f=row['frame'];t=row['seconds']
        box=row['car']['box'] if row['car'] else None
        if k==1 and f==586:
            # 분기점에 새로 드러난 흰 점선을 선택합니다. 바깥 실선과 사건을 연결하지 않습니다.
            curves['right']=PaintCurve([(870,545),(889,575),(1013,690)])
        mask_file=out/('mask'+str(k))/f'{f}.png'
        mask=cv2.imdecode(np.fromfile(mask_file,np.uint8),0)
        h,w=im.shape[:2];y=round(h*(.5 if k==0 else .58))
        full=np.zeros((h,w),np.uint8)
        full[y:]=cv2.dilate(cv2.resize(mask,(w,h-y),interpolation=cv2.INTER_NEAREST),np.ones((5,5),np.uint8))
        found,reading=assessor.evaluate_curves(f,t,im,box,row['cars'],full,curves,obs,'right' if k==1 and f==586 else None)
        timer=reading['contact_seconds']
        for e in found:
            e.update(frame=f,confirmed_frame=f,time_s=t,track_id=row['car']['id'],
                     event_source='automatic',hud_anchor=app.event_position(box,im.shape[1],im.shape[0]))
            events.append(app.set_float_slot(e,events));counts[e['label']]+=1
        lamps.append(lamp_measure(im,box if reading['visible'] else None,f,k))
        frames.append(dict(frame=f,seconds=t,box=box,track_id=row['car']['id'] if box else None,
                           track_source=row['track_source'],boundary=None,status='observed' if box else 'tracking_hold',
                           status_text='선택 차량 관찰 중',vehicle_info=metadata,event_counts=dict(counts),
                           lane_readability=reading,contact_seconds=None if timer is None else round(timer,3),**obs))
    cap.release()
    detected=[]
    for side in ('left','right'):
        for begin in range(0,len(lamps),30):
            detected.extend(bouts(lamps[begin:begin+150],side,fps))
    save(out/(NAMES[k]+'_등화.json'),dict(samples=lamps,bouts=detected))
    save(out/(NAMES[k]+'_분석.json'),dict(video=NAMES[k]+'.mp4',source_sha256=video_digest(ROOT/'videos'/(NAMES[k]+'.mp4')),
                                       fps=fps,events=events,counts=dict(counts),frames=frames,initial_click=CLICKS[k],
                                       boundary_seeds=SEEDS[k],reselection=RESELECT if k==0 else {}))
    print(NAMES[k],[(e['frame'],e['label'],e['reason']) for e in events],flush=True)


def contact_spans(data):
    from itertools import groupby
    spans=[]
    for side in ("left","right"):
        def phase(row):
            if not row["box"]: return "추적 보류"
            if row["freeze"]: return "녹화 정지"
            edge=row["lane_readability"]["geometry"]["edges"].get(side)
            return (edge or {}).get("position") or "판독 보류"
        for state,group in groupby(data["frames"],phase):
            part=list(group)
            first,last=part[0],part[-1]
            spans.append(dict(boundary=side,state=state,first_frame=first["frame"],last_frame=last["frame"],
                              source_first_s=first["seconds"],source_last_s=last["seconds"],
                              drive_first_s=first["drive_s"],drive_last_s=last["drive_s"],
                              events=[{"frame":e["frame"],"reason":e["reason"]} for e in data["events"]
                                      if e["boundary_side"]==side and first["frame"]<=e["frame"]<=last["frame"]]))
    return spans

def render(k,out,destination=None):
    destination=out if destination is None else destination
    destination.mkdir(parents=True,exist_ok=True)
    data=read(out/(NAMES[k]+'_분석.json'))
    rows=data['frames'];events=data['events']
    cap=cv2.VideoCapture(str(ROOT/'videos'/(NAMES[k]+'.mp4')))
    fps=cap.get(5);size=(round(cap.get(3)),round(cap.get(4)))
    if video_digest(ROOT/'videos'/(NAMES[k]+'.mp4'))!=data['source_sha256']: raise ValueError('원본 변경')
    path=destination/(NAMES[k]+'_분석.mp4')
    writer=media.writer(path,fps,size)
    sigs=[];before=[]
    compare=destination/(NAMES[k]+'_비포애프터.mp4')
    second=None
    try:
        if k: second=media.writer(compare,fps,(size[0]*2,size[1]))
        for row in rows:
            ok,original=cap.read()
            if not ok or abs(row['seconds']-lane.source_seconds(cap,row['frame'],fps))>.001: raise OSError(row['frame'])
            shown=far.compose(original,row,[e for e in events if e['frame']<=row['frame']])
            sigs.append(media.signature(shown))
            writer.write(shown)
            if second:
                before.append(media.signature(original))
                second.write(np.hstack((original,shown)))
        if cap.read()[0]: raise ValueError('기록 누락')
    finally:
        writer.release()
        if second: second.release()
        cap.release()
    stats=media.verify(path,sigs,size,fps)
    if k:
        # 좌우 모두 같은 원본 프레임 번호를 사용했는지 저장 후 매 프레임을 검사합니다.
        cap=cv2.VideoCapture(str(compare))
        errors=[]
        for f,(left,right) in enumerate(zip(before,sigs),1):
            ok,im=cap.read()
            if not ok or im.shape[:2]!=(size[1],size[0]*2): raise OSError(f)
            errors.append([float(cv2.absdiff(media.signature(half),sig).mean()) for half,sig in
                           zip(np.hsplit(im,2),(left,right))])
        if cap.read()[0] or abs(cap.get(5)-fps)>.01 or np.max(errors)>10: raise ValueError('좌우 동기화 불일치')
        stats['side_by_side']=dict(frames=len(errors),size=[size[0]*2,size[1]],fps=fps,
                                    max_mean_error_per_half=np.max(errors,axis=0).tolist(),sha256=video_digest(compare))
        cap.release()
    stats['sha256']=video_digest(path)
    stats['per_boundary_intervals']=contact_spans(data)
    stats['hud_pixels']=inspect_saved(k,out,data,path)
    reproduced=lane.analyze_contact_rows(rows,fps)
    signature=lambda e:(e['label'],e['frame'],e['track_id'],e['boundary_side'])
    if list(map(signature,events))!=list(map(signature,reproduced)): raise AssertionError('사건 재생 불일치')
    counts=Counter()
    for row in rows:
        counts.update(e['label'] for e in events if e['frame']==row['frame'])
        if dict(counts)!=row['event_counts']: raise AssertionError(('TOTAL',row['frame']))
    stats['controls']=import_module('040_verify_lane_crossing_recovery_197').verify_contact_intervals()
    stats['measured_controls']=import_module('071_verify_remote_lane').clocks()
    stats['contact_and_readability_spans']=far.spans(rows,lambda r:('freeze' if r['freeze'] else
                  '/'.join(s+'='+str(e['position']) for s,e in r['lane_readability']['geometry']['edges'].items())
                  or ('search' if not r['box'] else 'unreadable')),fps)
    save(destination/(NAMES[k]+'_검수.json'),stats)
    print(path,stats['decoded'],flush=True)

def inspect_saved(k,out,data,path):
    rows=data['frames'];events=data['events']
    raw=cv2.VideoCapture(str(ROOT/'videos'/(NAMES[k]+'.mp4')))
    mp4=cv2.VideoCapture(str(path))
    probes={}
    for e in events:
        for delta in (-1,0,30,45,60):
            n=e['frame']+delta
            if 1<=n<=len(rows): probes.setdefault(n,[]).append(e)
    for n in [1,rows[-1]['frame'], *( [380,400,436,718,734] if not k else [247,260,274,910,949,979])]:
        probes.setdefault(n,[])
    checks=[]
    try:
        for n,check_events in sorted(probes.items()):
            raw.set(1,n-1);mp4.set(1,n-1)
            ok,im=raw.read();valid,decoded=mp4.read()
            if not ok or not valid: raise OSError(n)
            row=rows[n-1];t=row['seconds'];shown=[e for e in events if e['frame']<=n]
            expected=far.compose(im,row,shown)
            def compare(other):
                pixels=np.max(cv2.absdiff(other,expected),axis=2)>40
                if not pixels.any(): raise AssertionError(('HUD 비교 화소',n))
                margin=float(cv2.absdiff(decoded,other)[pixels].mean()-cv2.absdiff(decoded,expected)[pixels].mean())
                if margin<=2: raise AssertionError(('HUD 화소 불일치',n,margin))
                return round(margin,2)
            wrong=far.compose(im,dict(row,contact_seconds=99.99),shown)
            timer=compare(wrong)
            plate=compare(far.compose(im,dict(row,vehicle_info=dict(row['vehicle_info'],plate='검수')),shown))
            total=compare(far.compose(im,dict(row,event_counts={'차선침범':99}),shown))
            floating=[]
            for e in check_events:
                on=(n>=e['frame'] and round(t-e['time_s'],8)<2)
                edited=[a for a in shown if a!=e]
                if not on: edited.append(dict(e,time_s=t))
                floating.append(dict(event_frame=e['frame'],on=on,margin=compare(far.compose(im,row,edited))))
            checks.append(dict(frame=n,timer=timer,total=total,plate=plate,float_checks=floating))
    finally:
        raw.release();mp4.release()
    return checks

if __name__=='__main__':
    cli=argparse.ArgumentParser()
    cli.add_argument('--out',type=Path,required=True)
    cli.add_argument('--mode',choices=['all','analyze','render'],default='all')
    args=cli.parse_args()
    args.out.mkdir(parents=True,exist_ok=args.mode!='all')
    for k in range(2):
        if args.mode=='all':
            track(k,args.out)
            cache_masks(k,args.out)
            rows=read(args.out/(NAMES[k]+'_추적.json'));identity(k,rows)
            clock=motion(k,args.out);save(args.out/(NAMES[k]+'_시계.json'),clock)
            vehicle_evidence(k,args.out,rows,clock)
            plate_detail(k,args.out,rows,clock)
        if args.mode!='render': analyze(k,args.out)
        if args.mode!='analyze': render(k,args.out)

