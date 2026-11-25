# 057  CompCars의 원본과 라벨을 대조하고 후면 브랜드 실험용 목록을 만듭니다.
# README의 1부터 시작하는 차량 좌표를 Python 구간으로 바꿉니다.
# 사진을 복사하지 않고 경로와 좌표를 저장해 다음 058 학습에 넘깁니다.
import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import random
from pathlib import Path
import cv2
import numpy as np
from scipy.io import loadmat

ROOT=Path(__file__).resolve().parent
DEFAULT=Path(r"C:\Users\mbc\Desktop\RedBox데이터셋\dataSet_CompCars (차종식별)\data")
NAMES={"Hyundai":"Hyundai","KIA":"Kia","BWM":"BMW","Benz":"Mercedes-Benz","Audi":"Audi",
       "Chevy":"Chevrolet","Renault":"Renault","Shuanglong":"SsangYong","Toyota":"Toyota",
       "Volkswagen":"Volkswagen","Lexus":"Lexus"}

def write(path,obj):
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=1),encoding="utf8")

def fingerprint(gray):
    small=cv2.resize(gray,(32,32),interpolation=cv2.INTER_AREA)
    block=cv2.dct(small.astype(np.float32))[:8,:8].ravel()
    return int.from_bytes(np.packbits(block>np.median(block[1:])).tobytes(),"big")

def separate_model_names(rows):
    # 서로 다른 ID라도 제조사와 모델명이 같으면 평가에서 제외합니다(Sportage / SPORTAGE).
    seen=set();removed=[]
    for split in ("train","val","test"):
        group=[r for r in rows if r["split"]==split]
        def key(r):return r["brand"]," ".join(r["model"].casefold().split())
        removed.extend(r["path"] for r in group if r["model"] and key(r) in seen)
        seen.update(key(r) for r in group if r["model"])
    # 미학습 브랜드의 검증·테스트에도 SAAB / Saab 같은 표기 차이가 있습니다.
    calibration={r["brand"].strip().casefold() for r in rows if r["split"]=="unknown_val"}
    removed.extend(r["path"] for r in rows if r["split"]=="unknown_test" and
                   r["brand"].strip().casefold() in calibration)
    exclude=set(removed)
    return [r for r in rows if r["path"] not in exclude],removed

def verify_manifest(rows):
    paths=[r["path"] for r in rows]
    assert len(paths)==len(set(paths))
    ownership={};unseen=defaultdict(set)
    for r in rows:
        s=r["split"]
        if s in ("train","val","unknown_val"):assert r["official"]!="test"
        if s.startswith("unknown"):
            unseen[s].add(r["brand"].casefold())
            continue
        for k in (("id",r["model_id"]),("name",r["brand"],r["model"].strip().casefold())):
            if k[0]=="name" and not k[-1]:continue
            assert ownership.setdefault(k,s)==s,k
    assert not unseen["unknown_test"]&unseen["unknown_val"]
    return dict(paths=len(paths),duplicate_paths=0,shared_model_ids=0,shared_model_names=0,
                shared_unknown_brands=0,official_test_used_for_fitting_or_calibration=0)

def audit(data,out):
    cv2.setNumThreads(1)
    mat=loadmat(data/"misc/make_model_name.mat",simplify_cells=True)
    makes=[str(x).strip() for x in mat["make_names"]]
    models=[str(x).strip() if isinstance(x,str) else "" for x in mat["model_names"]]
    official={}
    for split in ("train","test"):
        for line in (data/"train_test_split/classification"/(split+".txt")).read_text().splitlines():
            official[line.strip()]=split
    images={p.relative_to(data/"image").as_posix() for p in (data/"image").rglob("*.jpg")}
    labels={p.relative_to(data/"label").with_suffix(".jpg").as_posix() for p in (data/"label").rglob("*.txt")}
    errors=[(p,"missing_image") for p in sorted(labels-images)]
    def inspect(rel):
        try:
            blob=(data/"image"/rel).read_bytes()
            # 전체 원본을 디코딩해 크기와 JPEG 끝 표시를 검사합니다.
            im=cv2.imdecode(np.frombuffer(blob,np.uint8),cv2.IMREAD_GRAYSCALE|cv2.IMREAD_IGNORE_ORIENTATION)
            if im is None or not blob.rstrip(b"\0\r\n ").endswith(b"\xff\xd9"):raise ValueError("damaged_jpeg")
            if rel not in labels:raise ValueError("missing_label")
            lines=(data/"label"/Path(rel).with_suffix(".txt")).read_text().split()
            v,n,x,y,X,Y=map(int,lines)
            if v not in (-1,1,2,3,4,5) or n!=1:raise ValueError("invalid_label")
            if not (1<=x<X<=im.shape[1] and 1<=y<Y<=im.shape[0]):raise ValueError("invalid_box")
            mi,mo=map(int,rel.split("/")[:2])
            raw=makes[mi-1];name=NAMES.get(raw,raw)
            row=dict(path=rel,brand=name,raw_make=raw,model_id=mo,model=models[mo-1],
                     view=v,box=[x-1,y-1,X,Y],official=official.get(rel,"unlisted"))
            if v in (2,5):
                row.update(sha=hashlib.sha256(blob).hexdigest(),ph=fingerprint(im),
                           crop_ph=fingerprint(im[y-1:Y,x-1:X]))
            return row,None
        except Exception as e:return None,(rel,str(e))
    rear=[];counts=Counter();views=Counter()
    paths=sorted(images)
    with ThreadPoolExecutor(max_workers=10) as pool:
        for i in range(0,len(paths),1000):
            for row,err in pool.map(inspect,paths[i:i+1000]):
                if err:errors.append(err);continue
                views[row["view"]]+=1
                counts[(row["brand"],row["model_id"],row["model"],row["view"])]+=1
                if "sha" in row:rear.append(row)
            if i%10000==0:print("checked",i,flush=True)
    write(out/"inventory.json",dict(images=len(images),labels=len(labels),matched=len(images&labels),
          parts=sum(1 for _ in (data/"part").rglob("*.jpg")),view_counts=views,errors=errors,
          make_ids=makes,model_counts=[[*k,v] for k,v in sorted(counts.items())],
          official_counts=dict(Counter(official.values())),official_missing=sorted(set(official)-images)))
    # 여섯 조각 중 하나라도 같은 해시를 찾아 실제 해밍 거리 5 이하인지 대조합니다.
    parent=list(range(len(rear)))
    def root(i):
        while i!=parent[i]:
            parent[i]=parent[parent[i]];i=parent[i]
        return i
    buckets=defaultdict(list);digests={};exact=near=0
    for i,r in enumerate(rear):
        digest=r["sha"]
        if digest in digests:parent[root(i)]=root(digests[digest]);exact+=1
        digests[digest]=i
        for key in ("ph","crop_ph"):
            h=r[key];seen=set()
            for shift,bits in [(0,11),(11,11),(22,11),(33,11),(44,10),(54,10)]:
                bucket=buckets[(key,shift,(h>>shift)&((1<<bits)-1))]
                seen.update(bucket);bucket.append(i)
            for j in seen:
                if (h^rear[j][key]).bit_count()<=5 and root(j)!=root(i):
                    parent[root(i)]=root(j);near+=1
    groups=defaultdict(list)
    for i,r in enumerate(rear):groups[root(i)].append(r)
    keep=[];removed=[]
    for batch in groups.values():
        # 서로 다른 브랜드가 섞인 중복 묶음은 모두 보류합니다. 공식 테스트 사본을 우선 보존합니다.
        batch.sort(key=lambda r:(r["official"]!="test",r["path"]))
        clean=len({r["brand"] for r in batch})==1
        if clean:keep.append(batch[0])
        for r in batch[int(clean):]:removed.append([r["path"],batch[0]["path"],"duplicate" if clean else "brand_conflict"])
    write(out/"duplicates.json",dict(exact_extra=exact,near_unions=near,removed=removed))
    rng=random.Random(197);manifest=[];summary={};exclusions=[]
    for brand in sorted(set(NAMES.values())):
        rows=[r for r in keep if r["brand"]==brand]
        groups=defaultdict(list)
        for r in rows:groups[r["model_id"]].append(r)
        # 모델 ID 전체를 묶습니다. 공식 테스트 사진은 어느 경우에도 학습이나 검증으로 옮기지 않습니다.
        usable=[m for m,g in groups.items() if sum(r["official"]!="test" for r in g)>=8]
        rng.shuffle(usable)
        if len(usable)<4:exclusions.append([brand,"fewer than four model groups"]);continue
        candidates=sorted(usable,key=lambda m:-sum(r["official"]=="test" for r in groups[m]))
        # 여러 모델 그룹을 합쳐 각 홀드아웃을 근사합니다. 한 큰 그룹의 독점을 줄입니다.
        target=max(15,len(rows)*.12);test=set()
        for m in candidates:
            if len(usable)-len(test)<=3 or (test and sum(len(groups[k]) for k in test)>=target):break
            test.add(m)
        val=set()
        for m in usable:
            if m in test:continue
            if len(usable)-len(test)-len(val)<=2 or (val and sum(sum(r["official"]!="test" for r in groups[k]) for k in val)>=target):break
            val.add(m)
        result=[]
        for r in rows:
            split="test" if r["model_id"] in test else "val" if r["model_id"] in val else "train"
            if r["official"]=="test" and split!="test":continue
            result.append(dict(r,split=split))
        sizes=Counter(r["split"] for r in result)
        if min(sizes["val"],sizes["test"])<12 or sizes["train"]<40:
            exclusions.append([brand,dict(sizes)]);continue
        manifest+=result;summary[brand]=dict(sizes)
    # 미학습 브랜드도 브랜드 단위로 검증/최종 평가를 분리하고 한 브랜드당 20장으로 제한합니다.
    others=sorted({r["brand"] for r in keep}-set(NAMES.values()))
    rng.shuffle(others)
    for i,b in enumerate(others):
        split="unknown_val" if i%2 else "unknown_test"
        part=[r for r in keep if r["brand"]==b and (split=="unknown_test" or r["official"]!="test")]
        rng.shuffle(part);manifest.extend(dict(r,split=split) for r in part[:20])
    for r in manifest:
        for k in ("ph","crop_ph","sha"):r.pop(k,None)
    manifest,alias_removed=separate_model_names(manifest)
    summary={b:dict(Counter(r["split"] for r in manifest if r["brand"]==b)) for b in summary}
    write(out/"model_name_exclusions.json",alias_removed)
    write(out/"integrity.json",verify_manifest(manifest))
    write(out/"manifest.json",manifest)
    write(out/"split.json",dict(by_brand=summary,exclusions=exclusions,counts=Counter(r["split"] for r in manifest),
          rear=len(rear),deduplicated=len(keep),data=str(data.resolve()),seed=197))
    print(summary,flush=True)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--data",type=Path,default=DEFAULT);parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    audit(args.data,args.output)
