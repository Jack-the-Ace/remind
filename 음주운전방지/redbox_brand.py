# CompCars 브랜드 실험의 공통 전처리와 추론 함수입니다.
# 원본 비율을 유지한 차량 사진을 ImageNet 기준으로 바꿔 브랜드별 점수를 얻습니다.
# 낮은 신뢰도는 확인 불가로 남깁니다. 이 모듈은 MVP와 분리되어 있습니다.
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import cv2
import numpy as np
import torch
from torch import nn
from torchvision.models import mobilenet_v3_large

def letterbox(bgr,size):
    h,w=bgr.shape[:2]
    scale=size/max(h,w)
    H,W=max(1,round(h*scale)),max(1,round(w*scale))
    small=cv2.resize(bgr,(W,H),interpolation=cv2.INTER_AREA if scale<1 else cv2.INTER_LINEAR)
    canvas=np.full((size,size,3),(124,116,104),np.uint8)
    top,left=(size-H)//2,(size-W)//2
    canvas[top:top+H,left:left+W]=cv2.cvtColor(small,cv2.COLOR_BGR2RGB)
    return canvas

def load_rows(root,rows,size,mode="crop"):
    # 각 사진은 메모리에만 작게 담습니다. 원본 폴더에 캐시나 사본을 쓰지 않습니다.
    buf=np.empty((len(rows),size,size,3),np.uint8)
    def one(i):
        row=rows[i]
        im=cv2.imdecode(np.fromfile(root/"image"/row["path"],np.uint8),
                        cv2.IMREAD_COLOR|cv2.IMREAD_IGNORE_ORIENTATION)
        x,y,X,Y=row["box"]
        if mode=="background":im[y:Y,x:X]=[104,116,124]
        elif mode!="full":im=im[y:Y,x:X]
        if mode=="gray":im=cv2.cvtColor(cv2.cvtColor(im,cv2.COLOR_BGR2GRAY),cv2.COLOR_GRAY2BGR)
        if mode=="color":im[:]=np.median(im.reshape(-1,3),axis=0).astype(np.uint8)
        buf[i]=letterbox(im,size)
    with ThreadPoolExecutor(8) as pool:
        for _ in pool.map(one,range(len(rows))):pass
    return torch.from_numpy(buf)

def tensor(images):
    x=images.to("cuda").permute(0,3,1,2).float()/255
    return (x-x.new_tensor([.485,.456,.406])[None,:,None,None])/x.new_tensor([.229,.224,.225])[None,:,None,None]

def network(classes,pretrained=None):
    net=mobilenet_v3_large(weights=None)
    if pretrained is not None:net.load_state_dict(torch.load(pretrained,map_location="cpu",weights_only=True))
    net.classifier[-1]=nn.Linear(net.classifier[-1].in_features,len(classes))
    return net.cuda().to(memory_format=torch.channels_last)

@torch.inference_mode()
def probabilities(net,images,batch=48):
    net.eval()
    result=[]
    for part in images.split(batch):
        with torch.autocast("cuda"):out=net(tensor(part))
        result.append(out.float().softmax(1).cpu())
    return torch.cat(result)

def restore(path):
    record=torch.load(path,map_location="cpu",weights_only=True)
    net=network(record["classes"]);net.load_state_dict(record["state"]);net.eval()
    return net,record

def predict_crops(net,record,crops):
    images=torch.from_numpy(np.stack([letterbox(im,record["size"]) for im in crops]))
    p=probabilities(net,images)
    return p,["-" if float(v.max())<record["threshold"] else record["classes"][int(v.argmax())] for v in p]
