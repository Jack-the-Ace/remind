# 058  후면 사진으로 차량 브랜드를 학습하고 처음 보는 모델 ID로 검증합니다.
# 057 목록과 ImageNet V1을 사용해 분류층부터 학습하고 뒤쪽 특징층을 조금씩 바꿉니다.
# 검증으로 해상도와 보류 기준을 정한 뒤 테스트를 한 번 평가하고 059에 최적 모델을 넘깁니다.
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
from time import perf_counter
import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import torch
from torch.nn import functional as F
from redbox_brand import letterbox, load_rows, network, probabilities, tensor

ROOT=Path(__file__).resolve().parent
WEIGHTS=ROOT/"output/lane_transfer_197/weights/mobilenet_v3_large-8738ca79.pth"

def write(path,obj):path.write_text(json.dumps(obj,indent=1,ensure_ascii=False),encoding="utf8")

def scores(y,p,classes):
    cm=np.zeros((len(classes),len(classes)),int)
    np.add.at(cm,(np.asarray(y),p.argmax(1).numpy()),1)
    recall=cm.diagonal()/np.maximum(1,cm.sum(1));precision=cm.diagonal()/np.maximum(1,cm.sum(0))
    f1=2*recall*precision/np.maximum(1e-12,recall+precision)
    return dict(acc=float(cm.trace()/cm.sum()),macro_f1=float(f1.mean()),precision=float(precision.mean()),
                recall=float(recall.mean()),confusion=cm.tolist(),classes={c:dict(n=int(cm[i].sum()),
                acc=recall[i],precision=precision[i],f1=f1[i]) for i,c in enumerate(classes)})

def openset(y,p,u,t):
    right=p.argmax(1)==y
    accept=p.max(1).values>=t;reject=u.max(1).values<t
    return dict(threshold=t,known=len(y),unknown=len(u),known_accept=float(accept.float().mean()),
                known_correct_accepted=float((right&accept).float().mean()),
                accepted_accuracy=float(right[accept].float().mean()) if accept.any() else None,
                unknown_reject=float(reject.float().mean()),unknown_false_accept=int((~reject).sum()))

def learn_epoch(net,x,y,opt,weights,batch,rng,scaler,tune):
    net.train();net.features.eval()
    if tune:
        for layer in net.features[-4:]:layer.train()
    perm=torch.randperm(len(x));loss_sum=correct=0
    for ids in perm.split(batch):
        img=tensor(x[ids]);target=y[ids].cuda()
        # 차체 색은 조금만 바꾸고 가끔 작게 줄였다 키워 먼 차량의 흐림을 흉내냅니다.
        if rng.random()<.25:
            small=F.avg_pool2d(img,rng.choice((2,3)))
            img=F.interpolate(small,size=img.shape[-2:],mode="bilinear",align_corners=False)
        img=img*rng.uniform(.9,1.1)+rng.uniform(-.19,.19)
        opt.zero_grad(set_to_none=True)
        with torch.autocast("cuda"):
            pred=net(img);loss=F.cross_entropy(pred,target,weight=weights,label_smoothing=.035)
        scaler.scale(loss).backward();scaler.step(opt);scaler.update()
        loss_sum+=float(loss.detach())*len(ids);correct+=int((pred.argmax(1)==target).sum())
    return loss_sum/len(x),correct/len(x)

def final_test(net,classes,size,threshold,root,groups,out):
    te=groups["test"];ty=torch.tensor([classes.index(r["brand"]) for r in te]);tp=probabilities(net,load_rows(root,te,size))
    tu=probabilities(net,load_rows(root,groups["unknown_test"],size))
    final=scores(ty,tp,classes);op=openset(ty,tp,tu,threshold)
    write(out/"test_predictions.json",[dict(path=r["path"],truth=r["brand"],raw=classes[int(prob.argmax())],
          confidence=float(prob.max()),display=classes[int(prob.argmax())] if prob.max()>=threshold else "-")
          for rows,probs in [(te,tp),(groups["unknown_test"],tu)] for r,prob in zip(rows,probs)])
    fig,ax=plt.subplots(figsize=(8,7),layout="constrained");cm=np.array(final["confusion"])
    ax.imshow(cm/np.maximum(1,cm.sum(1))[:,None],cmap="Blues",vmin=0,vmax=1)
    for i,j in np.ndindex(cm.shape):ax.text(j,i,str(cm[i,j]),ha="center",va="center",color="white" if cm[i,j]>cm[i].sum()*.5 else "black")
    ax.set_xticks(range(len(classes)),classes,rotation=55,ha="right");ax.set_yticks(range(len(classes)),classes)
    ax.set(xlabel="Prediction",ylabel="True brand",title="Held-out model IDs | final test")
    fig.savefig(out/"confusion.png",dpi=150);plt.close(fig)
    # 같은 브랜드의 정답과 오답을 한 줄에 놓고 후면 사진과 차량 상자를 확인합니다.
    tiles=[]
    for idx,brand in enumerate(classes):
        pair=[]
        for correct in (True,False):
            matches=[i for i,r in enumerate(te) if r["brand"]==brand and (int(tp[i].argmax())==idx)==correct]
            tile=np.zeros((146,255,3),np.uint8)
            if matches:
                i=matches[len(matches)//2];r=te[i]
                im=cv2.imdecode(np.fromfile(root/"image"/r["path"],np.uint8),cv2.IMREAD_COLOR|cv2.IMREAD_IGNORE_ORIENTATION)
                x,y,X,Y=r["box"];cv2.rectangle(im,(x,y),(X-1,Y-1),(20,205,90),max(2,im.shape[0]//160))
                tile[:116,69:185]=letterbox(im,116)[:,:,::-1]
                cv2.putText(tile,f"{brand} > {classes[int(tp[i].argmax())]}",(3,136),0,.44,(245,245,245),1)
            pair.append(tile)
        tiles.append(np.hstack(pair))
    cv2.imencode(".jpg",np.vstack(tiles))[1].tofile(out/"test_examples.jpg")
    return final,op

def train(args):
    start=perf_counter();out=args.output;out.mkdir(parents=True,exist_ok=False)
    if not torch.cuda.is_available():raise RuntimeError("CUDA 필요")
    cv2.setNumThreads(1);torch.set_num_threads(4);torch.manual_seed(197);rng=random.Random(197)
    digest=hashlib.sha256(WEIGHTS.read_bytes()).hexdigest()
    if not digest.startswith("8738ca79"):raise ValueError("ImageNet V1 해시 불일치")
    split=json.loads((args.audit/"split.json").read_text(encoding="utf8"));root=Path(split["data"])
    manifest=json.loads((args.audit/"manifest.json").read_text(encoding="utf8"))
    groups={k:[r for r in manifest if r["split"]==k] for k in split["counts"]}
    classes=sorted(split["by_brand"])
    def labels(rows):return torch.tensor([classes.index(r["brand"]) for r in rows])
    tr,va=groups["train"],groups["val"]
    x=load_rows(root,tr,224);v=load_rows(root,va,224)
    y=labels(tr);vy=labels(va)
    weights=torch.bincount(y).float().rsqrt().cuda();weights/=weights.mean()
    def setup():
        net=network(classes,WEIGHTS);net.features.requires_grad_(False)
        opt=torch.optim.AdamW([{"params":net.classifier.parameters(),"lr":.0006},
             {"params":net.features[-4:].parameters(),"lr":.00018}],weight_decay=.001)
        return net,opt,torch.amp.GradScaler("cuda")
    net,opt,scaler=setup();sample=torch.cat([torch.where(y==i)[0][:12] for i in range(len(classes))])
    t=perf_counter();smoke=learn_epoch(net,x[sample],y[sample],opt,weights,args.batch,rng,scaler,False)
    write(out/"smoke.json",dict(n=len(sample),loss=smoke[0],accuracy=smoke[1],seconds=perf_counter()-t,
          val_output=list(probabilities(net,v[:8]).shape),device=torch.cuda.get_device_name(0)))
    del net,opt,scaler
    torch.manual_seed(197);rng.seed(197);net,opt,scaler=setup()
    history=[];best=-1;best_epoch=0;begin=perf_counter()
    for ep in range(1,args.epochs+1):
        t=perf_counter()
        if ep==3:net.features[-4:].requires_grad_(True)
        if ep in (10,16):
            for g in opt.param_groups:g["lr"]*=.5
        loss,acc=learn_epoch(net,x,y,opt,weights,args.batch,rng,scaler,ep>=3)
        p=probabilities(net,v,args.batch);metric=scores(vy,p,classes)
        val_loss=float(F.nll_loss(p.clamp_min(1e-9).log(),vy,weight=weights.cpu()))
        row=dict(epoch=ep,train_loss=loss,train_acc=acc,val_loss=val_loss,
                 val_acc=metric["acc"],val_macro_f1=metric["macro_f1"],seconds=perf_counter()-t)
        history.append(row);write(out/"history.json",history);print(row,flush=True)
        if metric["macro_f1"]>best:
            best=metric["macro_f1"];best_epoch=ep
            torch.save(dict(classes=classes,state=net.state_dict(),size=224,epoch=ep,initial_sha256=digest),
                       out/"best.pt")
        elif ep-best_epoch>=5:break
    elapsed=perf_counter()-begin;del x
    ck=torch.load(out/"best.pt",map_location="cpu",weights_only=True);net.load_state_dict(ck["state"])
    # 같은 가중치에서 원본 상자를 다시 크게 읽어 작은 표식의 해상도 영향을 대조합니다.
    v224=probabilities(net,v);del v
    v320=probabilities(net,load_rows(root,va,320))
    candidates={224:scores(vy,v224,classes),320:scores(vy,v320,classes)}
    size=max(candidates,key=lambda s:candidates[s]["macro_f1"]);p=v224 if size==224 else v320
    u=probabilities(net,load_rows(root,groups["unknown_val"],size))
    grid=[openset(vy,p,u,float(t)) for t in np.arange(.2,1,.01)]
    # 알려진 브랜드 정답 유지와 미학습 브랜드 거절을 같은 비중으로 봅니다.
    operating=max(grid,key=lambda z:z["known_correct_accepted"]+z["unknown_reject"])
    ck.update(size=size,threshold=operating["threshold"]);torch.save(ck,out/"best.pt")
    write(out/"selection.json",dict(resolutions=candidates,validation_unknown=operating,threshold_curve=grid))
    # 체크포인트와 문턱을 저장한 다음에만 최종 테스트 사진을 불러옵니다.
    tr_final=probabilities(net,load_rows(root,tr,size))
    final,op=final_test(net,classes,size,ck["threshold"],root,groups,out)
    controls={};subset=[];rand=random.Random(197)
    for c in classes:
        brandrows=[r for r in va if r["brand"]==c];rand.shuffle(brandrows);subset+=brandrows[:25]
    for mode in ("crop","gray","color","full","background"):
        controls[mode]=scores(labels(subset),probabilities(net,load_rows(root,subset,size,mode)),classes)
    write(out/"results.json",dict(device=torch.cuda.get_device_name(0),batch=args.batch,seed=197,
          train_seconds=elapsed,overall_seconds=perf_counter()-start,epochs=len(history),best_epoch=best_epoch,
          size=size,peak_cuda_mb=torch.cuda.max_memory_allocated()/2**20,train=scores(y,tr_final,classes),
          validation=candidates[size],test=final,test_unknown=op,validation_controls=controls,
          control_paths=[r["path"] for r in subset]))
    fig,ax=plt.subplots(1,2,figsize=(11,4),layout="constrained")
    for key in ("train_loss","val_loss"):ax[0].plot([r["epoch"] for r in history],[r[key] for r in history],label=key)
    for key in ("train_acc","val_acc","val_macro_f1"):ax[1].plot([r["epoch"] for r in history],[r[key] for r in history],label=key)
    for a in ax:a.set_xlabel("Epoch");a.legend();a.grid(alpha=.2)
    fig.savefig(out/"learning.png",dpi=150);plt.close(fig)

if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--audit",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True);parser.add_argument("--epochs",type=int,default=20)
    parser.add_argument("--batch",type=int,default=64);train(parser.parse_args())
