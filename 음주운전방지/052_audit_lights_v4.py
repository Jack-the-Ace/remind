# 052  방향지시등 데이터에서 차량 상자와 촬영 장면 확인하기
# V4의 이미지와 YOLO 라벨을 읽고 원본 번호, 해시, 비슷한 화면을 대조합니다.
# 다른 분할과 장면이 겹치면 테스트와 검증을 우선 보존하고 겹친 학습 자료를 빼냅니다.
# 새 출력 폴더에 학습용 사본과 조사 기록을 남겨 053에서 사용합니다.
import argparse
import hashlib
import json
import re
import shutil
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np
import yaml
from scipy.spatial.distance import cdist

SPLITS = ("train", "valid", "test")


def read(path):
    return cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def picture(image, rows, names):
    canvas = image.copy()
    h,w = canvas.shape[:2]
    for cls,x,y,bw,bh in rows:
        a,b,c,d = int((x-bw/2)*w),int((y-bh/2)*h),int((x+bw/2)*w),int((y+bh/2)*h)
        color = (50,230,70) if cls==6 else (40,190,255)
        cv2.rectangle(canvas,(a,b),(c,d),color,2)
        cv2.putText(canvas,names[cls],(max(0,a),max(15,b-2)),0,.53,(0,0,0),3)
        cv2.putText(canvas,names[cls],(max(0,a),max(15,b-2)),0,.53,color,1)
    return canvas


def labels(path):
    rows = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if not line.strip():
            continue
        cls,x,y,w,h = map(float,line.split())
        if not cls.is_integer() or not 0<=cls<7 or not all(0<=v<=1 for v in (x,y,w,h)) or min(w,h)<=0:
            raise ValueError(f"잘못된 YOLO 좌표: {path}")
        rows.append((int(cls),x,y,w,h))
    return rows


def audit(root,out):
    config=yaml.safe_load((root/"data.yaml").read_text(encoding="utf-8"))
    names=config["names"]
    if config["roboflow"]["version"]!=4 or len(names)!=7:
        raise ValueError("V4 일곱 클래스 자료를 확인하세요.")
    out.mkdir(parents=True,exist_ok=False)
    by_id=defaultdict(list)
    counts={}
    exact=defaultdict(set)
    thumbs={}
    descriptors={}
    hashes={}
    orb=cv2.ORB_create(nfeatures=380)
    for split in SPLITS:
        images=sorted((root/split/"images").glob("*"))
        txt={l.stem:l for l in (root/split/"labels").glob("*.txt")}
        if {p.stem for p in images}!=set(txt) or len(images)!=len(txt):
            raise ValueError(f"짝 불일치: {split}")
        objects,positive=Counter(),Counter()
        empty=0
        for p in images:
            idx=int(re.fullmatch(r"Screenshot-(\d+)-_png\.rf\.[\w]+",p.stem).group(1))
            rows=labels(txt[p.stem])
            objects.update(row[0] for row in rows)
            positive.update({row[0] for row in rows})
            empty+=not rows
            image=read(p)
            if image.shape!=(640,640,3):
                raise ValueError(f"해상도 불일치: {p}")
            exact[hashlib.sha256(image.tobytes()).digest()].add(split)
            gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
            # 같은 번호의 3종 중 소금·후추 잡음이 가장 적은 사본을 장면 비교에 사용합니다.
            noise=float((cv2.absdiff(gray,cv2.medianBlur(gray,3))>60).mean())
            if not by_id[idx] or noise<min(item[0] for item in by_id[idx]):
                small=cv2.resize(gray,(320,320),interpolation=cv2.INTER_AREA)
                thumbs[idx]=cv2.resize(small,(32,32),interpolation=cv2.INTER_AREA)
                low=cv2.dct(thumbs[idx].astype(np.float32))[:8,:8].flatten()[1:]
                hashes[idx]=low>np.median(low)
                kp,des=orb.detectAndCompute(small,None)
                descriptors[idx]=(np.float32([k.pt for k in kp]),des)
            by_id[idx].append((noise,split,p,txt[p.stem],rows))
        counts[split]=dict(images=len(images),labels=len(txt),empty=empty,
                           per_class_images=[positive[i] for i in range(7)],
                           per_class_objects=[objects[i] for i in range(7)])
    ids=sorted(by_id)
    parent={i:i for i in ids}

    def group(i):
        while i!=parent[i]:
            parent[i]=parent[parent[i]]
            i=parent[i]
        return i

    # 다른 원본 번호도 앞뒤 화면 또는 시각적으로 가까운 화면이면 특징점 대응을 검사합니다.
    hd=cdist([hashes[i] for i in ids],[hashes[i] for i in ids],"hamming")*63
    mad=cdist([thumbs[i].ravel() for i in ids],[thumbs[i].ravel() for i in ids],"cityblock")/1024
    matcher=cv2.BFMatcher(cv2.NORM_HAMMING)
    pairs=set()
    for a,i in enumerate(ids):
        for b in {*np.argsort(mad[a])[:7], *np.argsort(hd[a])[:7],
                  *np.where((hd[a]<=8)|(mad[a]<=8))[0], *range(max(0,a-4),a)}:
            if a!=b:
                pairs.add(tuple(sorted((a,int(b)))))
    edges=[]
    for a,b in sorted(pairs):
        i,j=ids[a],ids[b]
        reason=None
        if hd[a,b]<=6 and mad[a,b]<=12:
            reason="hash+pixel"
        else:
            ka,da=descriptors[i]
            kb,db=descriptors[j]
            if da is None or db is None or min(len(da),len(db))<24:
                continue
            good=[m for m,n in matcher.knnMatch(da,db,k=2) if m.distance<.72*n.distance]
            if len(good)>=24:
                x=np.float32([ka[m.queryIdx] for m in good])
                y=np.float32([kb[m.trainIdx] for m in good])
                _,inliers=cv2.findHomography(x,y,cv2.RANSAC,3)
                if inliers is not None:
                    mask=inliers.ravel().astype(bool)
                    if mask.sum()>=20 and mask.mean()>=.65 and np.ptp(x[mask],axis=0).min()>55:
                        reason="scene_features"
        if reason:
            parent[group(j)]=group(i)
            edges.append((i,j,reason))
    families=defaultdict(list)
    for i in ids:
        families[group(i)].append(i)
    safe=defaultdict(list)
    excluded=[]
    for members in families.values():
        present={item[1] for i in members for item in by_id[i]}
        keep=next(s for s in reversed(SPLITS) if s in present)
        for i in members:
            for _,split,p,l,rows in by_id[i]:
                if split==keep:
                    safe[split].append((p,l,rows,i))
                else:
                    excluded.append([p.name,split,keep])
    for split in SPLITS:
        for sub in ["images","labels"]:
            (out/split/sub).mkdir(parents=True)
        for p,l,_,_ in safe[split]:
            shutil.copyfile(p,out/split/"images"/p.name)
            shutil.copyfile(l,out/split/"labels"/l.name)
    (out/"data.yaml").write_text(yaml.safe_dump(dict(path=out.resolve().as_posix(),train="train/images",
          val="valid/images",test="test/images",names=names)),encoding="utf-8")
    # 각 클래스가 보이는 원본과 정답을 나란히 두고, 확인에 쓰는 사진은 학습 폴더에서만 고릅니다.
    chosen=[]
    selected=set()
    for cls in [1,2,3,5,0,4,6,3,5,0]:
        items=sorted((v for i in ids for v in by_id[i] if v[1]=="train" and i not in selected
                      and any(r[0]==cls for r in v[4])), key=lambda v:(v[0],v[2].name))
        if items:
            _,_,p,_,rows=items[0]
            selected.add(int(p.name.split("-")[1]))
            im=read(p)
            pair=np.hstack([im,picture(im,rows,names)])
            cv2.imencode(".jpg",pair)[1].tofile(out/("sample_"+p.name))
            chosen.append(p.name)
    splits_of={i:{v[1] for v in by_id[i]} for i in ids}
    cross=[e for e in edges if len(splits_of[e[0]]|splits_of[e[1]])>1]
    report=dict(names=names,counts=counts,unique_source_names=len(ids),
                cross_exact_pixel_hashes=sum(len(s)>1 for s in exact.values()),
                cross_source_names=sum(len(s)>1 for s in splits_of.values()),
                groups=list(families.values()),cross_scene_pairs=cross,excluded=excluded,samples=chosen,
                safe={s:dict(images=len(safe[s]),sources=len({i for _,_,_,i in safe[s]}),
                             objects=[sum(row[0]==c for _,_,rows,_ in safe[s] for row in rows) for c in range(7)])
                      for s in SPLITS})
    write_json(out/"audit.json",report)
    print(counts,report["safe"],"cross_scene_pairs",len(cross))


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--data",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    cv2.setNumThreads(2)
    audit(args.data,args.output)
