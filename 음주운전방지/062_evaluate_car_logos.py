# 062  엠블럼 검출의 위치·브랜드를 검증하고 표시할 신뢰도 문턱을 고릅니다.
# 같은 클래스의 정답 상자와 IoU 0.5 이상일 때만 적중입니다.
# 검증으로 문턱을 저장한 다음 테스트를 열고, 작은 엠블럼과 미학습 브랜드의 오류도 남깁니다.
import argparse
import hashlib
from collections import Counter
from importlib import import_module
import json
import os
from pathlib import Path
import random
import cv2
import numpy as np
import yaml
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parent
os.environ["YOLO_OFFLINE"]="true"
os.environ["YOLO_CONFIG_DIR"]=str(ROOT/"output/emblem_v1/config")
from ultralytics import YOLO
from redbox_emblem import iou
raw=import_module("054_review_lights_v4")

def save(p,j):
    p.write_text(json.dumps(j,ensure_ascii=False,indent=1),encoding="utf8")
def native(net,data,out,s):
    result=net.val(data=str(data.resolve()),split=s,imgsz=640,batch=16,device=0,workers=0,
                   project=str(out.resolve()),name="ultra_"+s,plots=True,verbose=False)
    b=result.box
    stats=dict(precision=float(b.mp),recall=float(b.mr),macro_f1=float(b.f1.mean()),map50=float(b.map50),
               map50_95=float(b.map),confusion=result.confusion_matrix.matrix.tolist(),per_brand={})
    for i,c in enumerate(b.ap_class_index):
        stats["per_brand"][result.names[int(c)]]=dict(n=int(result.nt_per_class[c]),precision=float(b.p[i]),
              recall=float(b.r[i]),f1=float(b.f1[i]),map50=float(b.ap50[i]),map50_95=float(b.ap[i]))
    save(out/(s+"_metrics.json"),stats)
    return stats

def observations(net,root,split):
    obs=[]
    paths=sorted(p for p in (root/split/"images").iterdir() if p.suffix.lower() in {".jpg",".png"})
    batch=1 if paths and paths[0].suffix.lower()==".png" else 12
    for i in range(0,len(paths),batch):
        files=paths[i:i+batch]
        images=[cv2.imdecode(np.fromfile(f,np.uint8),1) for f in files]
        preds=net.predict(images,conf=.05,device=0,imgsz=640,verbose=False)
        for f,im,result in zip(files,images,preds):
            rows=raw.truth(root/split/"labels"/(f.stem+".txt"),im.shape[1],im.shape[0])
            gt=[dict(brand=net.names[c],box=box.tolist()) for c,box in rows]
            taken=set()
            pred=[]
            for x,y,X,Y,cf,c in sorted(result.boxes.data.cpu().tolist(),key=lambda v:-v[4]):
                cls=net.names[int(c)]
                box=[x,y,X,Y]
                score,idx=max([(iou(box,g["box"]),k) for k,g in enumerate(gt) if k not in taken and g["brand"]==cls],default=(0,None))
                match=idx if score>=.5 else None
                if match is not None:
                    taken.add(match)
                pred.append(dict(brand=cls,box=box,conf=cf,gt=match))
            obs.append(dict(file=f.name,gt=gt,pred=pred))
    return obs

def short_edge(box):
    return min(box[2]-box[0],box[3]-box[1])

def score(obs,thresholds,only=None):
    tp=fp=gt=shown=positive=hit_image=bad_images=negative=negative_fp=0
    sizes=[Counter() for _ in range(3)]
    def bucket(box):
        return int(np.searchsorted([12,24],short_edge(box),side="right"))
    for r in obs:
        truths=[g for g in r["gt"] if only is None or g["brand"]==only]
        predictions=[d for d in r["pred"] if (only is None or d["brand"]==only) and
                     d["brand"] in thresholds and thresholds[d["brand"]] is not None and d["conf"]>=thresholds[d["brand"]]]
        for g in truths:
            sizes[bucket(g["box"])]["gt"]+=1
        hits=0
        for d in predictions:
            if d["gt"] is None:
                sizes[bucket(d["box"])]["fp"]+=1
                fp+=1
            else:
                sizes[bucket(r["gt"][d["gt"]]["box"])]["tp"]+=1
                tp+=1
                hits+=1
        gt+=len(truths)
        shown+=bool(predictions)
        positive+=bool(truths)
        hit_image+=bool(hits)
        bad_images+=bool(len(predictions)>hits)
        negative+=not truths
        negative_fp+=bool(not truths and predictions)
    return dict(gt=gt,tp=tp,fp=fp,precision=tp/(tp+fp) if tp+fp else None,recall=tp/gt if gt else None,
           images=len(obs),display_images=shown,coverage=shown/len(obs),positive_images=positive,images_with_hit=hit_image,
           correct_display_fraction=(shown-bad_images)/shown if shown else None,
           images_with_fp=bad_images,negative_images=negative,negative_images_with_fp=negative_fp,size_bins=sizes)

def panels(obs,root,split,out,policy):
    rng=random.Random(62)
    examples=obs[:]
    rng.shuffle(examples)
    chosen=[]
    seen=set()
    for r in examples:
        if len(chosen)>=12:
            break
        brands={g["brand"] for g in r["gt"]}
        if not brands-seen and len(seen)<len(policy) and len(chosen)>=3:
            continue
        chosen.append(r)
        seen|=brands
    for r in examples:
        if len(chosen)>=12:
            break
        if r not in chosen:
            chosen.append(r)
    for i,r in enumerate(chosen):
        im=cv2.imdecode(np.fromfile(root/split/"images"/r["file"],np.uint8),1)
        a=im.copy()
        b=im.copy()
        for canvas,rows in ((a,r["gt"]),(b,[d for d in r["pred"] if policy[d["brand"]] is not None and d["conf"]>=policy[d["brand"]]])):
            for d in rows:
                x,y,X,Y=np.rint(d["box"]).astype(int)
                color=(40,210,60) if canvas is a else (0,186,255)
                cv2.rectangle(canvas,(x,y),(X,Y),color,2)
                cv2.putText(canvas,d["brand"],(x,max(15,y-3)),0,.52,color,2)
        for canvas,title in ((a,"Ground truth"),(b,"Selected display threshold")):
            cv2.putText(canvas,title,(7,23),0,.7,(255,255,255),2)
        cv2.imencode(".jpg",np.hstack([a,b]))[1].tofile(out/f"{split}_pair_{i+1:02d}.jpg")
    save(out/(split+"_example_files.json"),[r["file"] for r in chosen])

def compare_vehicle_crops(net, root, observations, policy, output):
    """검증 정답으로 어느 차를 비교할지 고정하고 전체 화면과 차량 crop을 비교합니다."""
    from redbox_emblem import owned

    cars = YOLO(str(ROOT / "yolo26n.pt"))
    targets = observations.copy()
    random.Random(620).shuffle(targets)
    counts = Counter()
    examples = []
    for row in targets:
        if len(row["gt"]) != 1:
            continue
        gt = row["gt"][0]
        brand = gt["brand"]
        if counts[brand] >= 15:
            continue
        counts[brand] += 1
        image = cv2.imdecode(np.fromfile(root / "valid/images" / row["file"], np.uint8), 1)
        result = cars.predict(image, classes=[2, 3, 5, 7], conf=.1, device=0, verbose=False)[0]
        boxes = np.rint(result.boxes.xyxy.cpu().numpy()).astype(int)
        # 어느 차의 표식인지 하나로 정할 수 있는 사진만 양쪽 방식에 똑같이 씁니다.
        hosts = [list(box) for box in boxes if owned(gt["box"], box, [])]
        if len(hosts) != 1:
            continue
        a, b, c, d = hosts[0]
        crop = image[b:d, a:c]
        other = [box for box in boxes if not np.array_equal(box, hosts[0])]
        offset = np.array([a, b, a, b])
        result = net.predict(crop, imgsz=640, conf=.05, device=0, verbose=False)[0]
        local = []
        for x, y, xx, yy, confidence, cls in result.boxes.data.cpu().tolist():
            local.append(dict(box=([x, y, xx, yy] + offset).tolist(),
                              conf=confidence, brand=result.names[int(cls)]))
        item = dict(file=row["file"], truth=brand, vehicle=[int(v) for v in hosts[0]], gt_box=gt["box"])
        for mode, proposed in (("full", row["pred"]), ("crop", local)):
            displayed = [det for det in proposed if owned(det["box"], hosts[0], other)
                         and policy[det["brand"]] is not None and det["conf"] >= policy[det["brand"]]]
            hits = [det for det in displayed if det["brand"] == brand and iou(gt["box"], det["box"]) >= .5]
            item[mode] = dict(displayed=len(displayed), correct=int(bool(hits)),
                              false=len(displayed)-int(bool(hits)))
        examples.append(item)
    save(output / "validation_crop_check.json", dict(attempted=dict(counts), examples=examples))


def final_test(net, data, root, names, policy, out):
    native(net,data,out,"test")
    tests=observations(net,root,"test")
    save(out/"test_detections.json",tests)
    save(out/"test_operating.json",dict(selected=score(tests,policy),per_brand={b:score(tests,policy,b) for b in names}))
    panels(tests,root,"test",out,policy)


def main(args):
    out=args.output
    cfg=yaml.safe_load(args.data.read_text(encoding="utf8"))
    root=Path(cfg["path"])
    names=cfg["names"]
    net=YOLO(str(args.weights))
    weight_hash=hashlib.sha256(args.weights.read_bytes()).hexdigest()
    if args.final_test:
        frozen=json.loads((out/"policy.json").read_text(encoding="utf8"))
        if frozen["weights_sha256"]!=weight_hash or (out/"test_metrics.json").exists():
            raise ValueError("검증에 사용한 가중치와 최초 테스트 결과 경로를 확인하세요.")
        final_test(net,args.data,root,names,frozen["per_class"],out)
        return
    out.mkdir(parents=True,exist_ok=False)
    native(net,args.data,out,"val")
    val=observations(net,root,"valid")
    save(out/"valid_detections.json",val)
    grid=[round(x/100,2) for x in range(10,100,2)]
    curve=[dict(threshold=t,**score(val,dict.fromkeys(names,t))) for t in grid]
    policy={}
    for name in names:
        acceptable=[]
        for t in grid:
            s=score(val,{name:t},name)
            if s["tp"]>=6 and s["precision"]>=.95:
                acceptable.append(t)
        policy[name]=min(acceptable,default=None)
    save(out/"policy.json",dict(source="validation only",minimum_tp=6,precision_goal=.95,per_class=policy,weights_sha256=weight_hash))
    save(out/"valid_operating.json",dict(selected=score(val,policy),curve=curve,per_brand={b:score(val,policy,b) for b in names}))
    panels(val,root,"valid",out,policy)
    if not args.validation_only:
        final_test(net,args.data,root,names,policy,out)
    native(net,args.data,out,"train")
    if not args.vehicle_crops:
        compare_vehicle_crops(net,root,val,policy,out)
    elif args.reference_data is not None:
        reference=Path(yaml.safe_load(args.reference_data.read_text(encoding="utf8"))["path"])
        baseline_views=observations(net,reference,"valid")
        compare_vehicle_crops(net,reference,baseline_views,policy,out)
    fig,ax=plt.subplots(figsize=(8,4),layout="constrained")
    for k in ("precision","coverage","recall"):
        ax.plot(grid,[r[k] for r in curve],label=k)
    ax.set(xlabel="Global confidence threshold | validation",ylabel="Fraction",ylim=(0,1.03))
    ax.legend()
    ax.grid(alpha=.24)
    fig.savefig(out/"confidence_coverage.png",dpi=150)
    plt.close(fig)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--weights",type=Path,required=True)
    p.add_argument("--data",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--reference-data",type=Path,help="같은 전체 화면과 차량 crop 검증용 060 data.yaml")
    p.add_argument("--vehicle-crops",action="store_true",help="원래부터 차량 crop인 평가 세트")
    group=p.add_mutually_exclusive_group()
    group.add_argument("--validation-only",action="store_true")
    group.add_argument("--final-test",action="store_true",help="먼저 저장한 검증 문턱과 동일한 가중치로 테스트")
    main(p.parse_args())
