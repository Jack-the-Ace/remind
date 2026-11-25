# 060  Roboflow 배포본의 엠블럼 위치와 촬영 장면 중복을 검사합니다.
# 원본 JPG와 TXT를 읽고 유사 장면은 같은 분할에만 남깁니다.
# 다음 061 학습에 쓸 별도 사본, 클래스 통계, 원본과 정답 비교 15장을 만듭니다.
import argparse
from collections import Counter,defaultdict
from importlib import import_module
import hashlib
import json
import random
import re
import shutil
from pathlib import Path
import cv2
import numpy as np
import yaml
from scipy.spatial.distance import cdist

legacy=import_module("052_audit_lights_v4")
SOURCE=Path(r"C:\Users\mbc\Desktop\RedBox데이터셋\dataSet_roboflow_2 (차종 관련)")
SPLITS=("train","valid","test")
REQUEST=["hyundai","kia","genesis","bmw","mercedes","audi","chevrolet","renault","ssangyong","toyota","volkswagen","lexus"]

def save(path,obj):
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=1),encoding="utf8")

def review_viewpoints(root, out, items, used, names):
    # 원래 픽셀을 잘라 보기 편한 크기로 모읍니다. 촬영 방향은 이 표본을 사람이 확인합니다.
    import math
    def sheet(path, tiles, columns):
        if not tiles:
            return
        tiles = tiles.copy()
        tiles.extend(np.zeros_like(tiles[0]) for _ in range((-len(tiles)) % columns))
        image = np.vstack([np.hstack(tiles[k:k+columns]) for k in range(0,len(tiles),columns)])
        cv2.imencode(".jpg",image)[1].tofile(path)

    chosen = random.Random(1060).sample(used["train"], min(60,len(used["train"])))
    patches = []
    for number, index in enumerate(chosen,1):
        row = items[index]
        im = legacy.read(root / "train/images" / row["file"])
        if row["rows"]:
            cls,x,y,w,h = row["rows"][0]
            height,width = im.shape[:2]
            x,y = round(x*width),round(y*height)
            im = im[max(0,y-64):y+64,max(0,x-100):x+100]
        tile = cv2.resize(im,(150,96))
        cv2.putText(tile,str(number),(1,16),0,.5,(5,255,5),1)
        patches.append(tile)
    save(out/"viewpoint_sample.json",chosen)
    for start in range(0,len(patches),30):
        sheet(out/f"view_crops{start}.jpg",patches[start:start+30],6)

    patches = []
    for index in used["train"]:
        row = items[index]
        for cls,x,y,w,h in row["rows"]:
            if names[cls] != "kia":
                continue
            im = legacy.read(root / "train/images" / row["file"])
            height,width = im.shape[:2]
            left = max(0,math.floor((x-w/2)*width))
            right = min(width,math.ceil((x+w/2)*width))
            top = max(0,math.floor((y-h/2)*height))
            bottom = min(height,math.ceil((y+h/2)*height))
            badge = im[top:bottom,left:right]
            tile = np.zeros((77,105,3),np.uint8)
            tile[:55] = cv2.resize(badge,(105,55))
            cv2.putText(tile,f"{w*width:.0f}x{h*height:.0f} px",(2,72),0,.4,(255,255,255),1)
            patches.append(tile)
    sheet(out/"kia_emblems.jpg",patches,5)


def main(root,out):
    cv2.setNumThreads(2)
    cfg=yaml.safe_load((root/"data.yaml").read_text(encoding="utf8"))
    names=cfg["names"]
    out.mkdir(parents=True,exist_ok=False)
    items=[]
    errors=[]
    counts={}
    hashes=[]
    thumb=[]
    features=[]
    orb=cv2.ORB_create(300)
    for s in SPLITS:
        images=sorted((root/s/"images").glob("*"))
        labels={p.stem:p for p in (root/s/"labels").glob("*.txt")}
        objects=Counter()
        sizes=[]
        empty=0
        for p in images:
            try:
                lab=labels.pop(p.stem)
                im=legacy.read(p)
                if im is None or (p.suffix.lower() in (".jpeg",".jpg") and not p.read_bytes().rstrip(b"\0\r\n ").endswith(b"\xff\xd9")):
                    raise ValueError("damaged")
                h,w=im.shape[:2]
                rows=[]
                for line in lab.read_text(encoding="utf-8-sig").splitlines():
                    if not line.strip():
                        continue
                    k,x,y,bw,bh=map(float,line.split())
                    if not k.is_integer() or not 0<=k<len(names) or not (0<bw<=1 and 0<bh<=1 and x-bw/2>=-.001 and y-bh/2>=-.001 and x+bw/2<=1.001 and y+bh/2<=1.001):
                        raise ValueError("label bounds")
                    rows.append([int(k),x,y,bw,bh])
                objects.update(names[r[0]] for r in rows)
                sizes.extend([[r[3]*w,r[4]*h] for r in rows])
                empty+=not rows
                small=cv2.resize(cv2.cvtColor(im,cv2.COLOR_BGR2GRAY),(256,256),interpolation=cv2.INTER_AREA)
                g=cv2.resize(small,(32,32),interpolation=cv2.INTER_AREA)
                d=cv2.dct(g.astype(np.float32))[:8,:8].ravel()[1:]
                hashes.append(d>np.median(d))
                thumb.append(g.ravel())
                kp,desc=orb.detectAndCompute(small,None)
                features.append((np.float32([k.pt for k in kp]),desc))
                items.append(dict(split=s,file=p.name,rows=rows,wh=[w,h],digest=hashlib.sha256(im.tobytes()).hexdigest(),source=p.stem.split(".rf.")[0]))
            except Exception as e:
                errors.append([s,p.name,repr(e)])
        errors.extend([s,f.name,"missing image"] for f in labels.values())
        counts[s]=dict(images=len(images),labels=len(list((root/s/"labels").glob("*.txt"))),empty=empty,objects=objects,
                        wh_percentiles=np.percentile(sizes,[0,10,25,50,75,90,100],axis=0).tolist())
    n=len(items)
    parent=list(range(n))
    edges=[]
    seen={}
    def group(i):
        while i!=parent[i]:
            parent[i]=parent[parent[i]]
            i=parent[i]
        return i
    def link(i,j,reason):
        edges.append([i,j,reason])
        parent[group(j)]=group(i)
    for i,r in enumerate(items):
        for k in ("digest","source"):
            key=k,r[k]
            if key in seen:
                link(i,seen[key],k)
            else:
                seen[key]=i
    hd=cdist(hashes,hashes,"hamming")*63
    mad=cdist(thumb,thumb,"cityblock")/1024
    pairs=set()
    for i in range(n):
        for j in set(np.argsort(hd[i])[:6])|set(np.argsort(mad[i])[:6])|set(np.where(hd[i]<=7)[0]):
            if i!=j:
                pairs.add(tuple(sorted((i,int(j)))))
    # 숫자 이름은 인접 번호도 비교합니다. 번호만으로 같은 차량이라고 가정하지 않습니다.
    numbered=sorted((int(r["source"].split("_")[0]),i) for i,r in enumerate(items) if re.fullmatch(r"\d+_jpg",r["source"]))
    for pos,(num,i) in enumerate(numbered):
        for num2,j in numbered[pos+1:pos+5]:
            if num2-num<=12:
                pairs.add(tuple(sorted((i,j))))
    bf=cv2.BFMatcher(cv2.NORM_HAMMING)
    for i,j in sorted(pairs):
        if group(i)==group(j):
            continue
        if hd[i,j]<=6 and mad[i,j]<=14:
            link(i,j,"hash+pixel")
            continue
        a,da=features[i]
        b,db=features[j]
        if da is None or db is None or min(len(da),len(db))<18:
            continue
        good=[m for m,k in bf.knnMatch(da,db,k=2) if m.distance<.72*k.distance]
        if len(good)<18:
            continue
        u=np.float32([a[m.queryIdx] for m in good])
        v=np.float32([b[m.trainIdx] for m in good])
        _,mask=cv2.findHomography(u,v,cv2.RANSAC,3)
        if mask is not None:
            keep=mask.ravel().astype(bool)
            if keep.sum()>=17 and keep.mean()>=.67 and np.ptp(u[keep],axis=0).min()>40:
                link(i,j,"scene")
    families=defaultdict(list)
    for i in range(n):
        families[group(i)].append(i)
    safe=defaultdict(list)
    excluded=[]
    cross=[]
    for family in families.values():
        partitions={items[i]["split"] for i in family}
        keep=next(s for s in reversed(SPLITS) if s in partitions)
        if len(partitions)>1:
            cross.append(family)
        exact=set()
        for i in family:
            r=items[i]
            r["group"]=min(family)
            if r["split"]!=keep or r["digest"] in exact:
                excluded.append(i)
                continue
            safe[keep].append(i)
            exact.add(r["digest"])
    def positive(s,b):
        return sum(any(names[row[0]]==b for row in items[i]["rows"]) for i in safe[s])
    # 학습·검증 자료로만 대상을 고릅니다. 희소 클래스는 미학습 브랜드로 시험합니다.
    classes=[b for b in REQUEST if positive("train",b)>=20 and positive("valid",b)>=4]
    rng=random.Random(60)
    remap={names.index(b):k for k,b in enumerate(classes)}
    used={}
    for s in SPLITS:
        paths=sorted(safe[s])
        rng.shuffle(paths)
        paths=[i for i in paths if not any(names[row[0]]=="che" for row in items[i]["rows"])]
        if s=="train":
            buckets=defaultdict(list)
            for i in paths:
                bs={names[row[0]] for row in items[i]["rows"] if row[0] in remap}
                buckets["negative" if not bs else "toyota" if bs=={"toyota"} else "other"].append(i)
            cap=3*int(np.median([positive(s,b) for b in classes]))
            pos=buckets["other"]+buckets["toyota"][:cap]
            paths=pos+buckets["negative"][:len(pos)//3]
        used[s]=paths
        for sub in ("images","labels"):
            (out/s/sub).mkdir(parents=True)
        for i in paths:
            r=items[i]
            p=root/s/"images"/r["file"]
            shutil.copyfile(p,out/s/"images"/p.name)
            keep=[[remap[row[0]],*row[1:]] for row in r["rows"] if row[0] in remap]
            (out/s/"labels"/(p.stem+".txt")).write_text("".join(" ".join(map(str,row))+"\n" for row in keep),encoding="utf8")
    (out/"data.yaml").write_text(yaml.safe_dump(dict(path=out.resolve().as_posix(),train="train/images",val="valid/images",test="test/images",names=classes)),encoding="utf8")
    chosen=[]
    pictures=[]
    (out/"samples").mkdir()
    for brand in (classes+["kia","kia","hyundai","bmw","toyota","mercedes","chevrolet"])[:15]:
        options=[i for i in used["train"] if i not in chosen and any(names[r[0]]==brand for r in items[i]["rows"])]
        if not options:
            continue
        i=rng.choice(options)
        chosen.append(i)
        r=items[i]
        im=legacy.read(root/"train/images"/r["file"])
        annotated=legacy.picture(im,r["rows"],names)
        cv2.imencode(".jpg",np.hstack([im,annotated]))[1].tofile(out/"samples"/f"{len(chosen):02d}_{brand}.jpg")
        tile=cv2.resize(annotated,(240,220))
        cv2.putText(tile,f"{len(chosen)} {brand}",(2,216),0,.53,(0,220,255),2)
        pictures.append(tile)
    if len(pictures)==15:
        cv2.imencode(".jpg",np.vstack([np.hstack(pictures[k:k+5]) for k in (0,5,10)]))[1].tofile(out/"samples.jpg")
    save(out/"audit.json",dict(config=cfg,counts=counts,errors=errors,classes=classes,items=items,similarity_edges=edges,
         cross_groups=cross,excluded_group=excluded,used=used,samples=chosen))
    review_viewpoints(root,out,items,used,names)
    print(classes,{s:len(v) for s,v in used.items()},"cross",len(cross),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--data",type=Path,default=SOURCE)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    main(args.data,args.output)
