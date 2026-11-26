# 원거리 차선 분석 · 차량 하단 좌우 폭과 실제 도색을 원본 좌표에서 비교합니다.
# 작은 차 주변을 기존 차선 모델로 다시 읽고, 원본의 밝은 도색과 맞는 직선만 사용합니다.
# 매 프레임 경계별 지지점과 오차를 남겨 HUD와 사건 기록에서 같은 결과를 사용합니다.
import cv2
import numpy as np


def road_roi(shape, box):
    h,w=shape[:2]
    x,y,X,Y=box
    sw=min(w,max(224,round(16*(X-x))))
    sh=min(h,max(120,round(8*(Y-y))))
    left=int(np.clip(round((x+X-sw)/2),0,w-sw))
    top=int(np.clip(round(Y-.35*sh),0,h-sh))
    return left,top,left+sw,top+sh


def line_x(points,y):
    (a,b),(A,B)=points
    return a+(A-a)*(y-b)/(B-b)


def native_lanes(image, box, mask, roi, vehicles, previous):
    """모델 마스크와 실제 도색의 가느다란 밝기 봉우리가 함께 지지하는 두 경계를 찾습니다."""
    x0,y0,X,Y=roi
    x,y,r,b=box
    w,h=r-x,b-y
    center=(x+r)/2-x0
    bottom=b-y0
    gray=cv2.cvtColor(image[y0:Y,x0:X],cv2.COLOR_BGR2GRAY)
    mh,mw=gray.shape
    binary=cv2.resize(mask,(mw,mh),interpolation=cv2.INTER_NEAREST)
    nearby=cv2.dilate(binary,np.ones((5,7),np.uint8))
    # 양옆 노면보다 밝은 화소만 남깁니다. 차체, 그림자 경계, 가드레일의 넓은 면을 제외합니다.
    stride=max(3,min(9,round(.22*w)))
    g=gray.astype(np.int16)
    strength=np.zeros_like(g)
    strength[:,stride:-stride]=g[:,stride:-stride]-np.maximum(g[:,:-2*stride],g[:,2*stride:])
    paint=(strength>=9).astype(np.uint8)
    paint[:max(0,int(np.ceil(bottom)))]=0
    paint[min(mh,int(bottom+max(38,3.2*h))) :]=0
    for car in vehicles:
        a,c,A,C=car['box']
        if C < b+2:
            continue
        i,j=max(0,int(a)-x0),max(0,int(c)-y0)
        I,J=min(mw,int(np.ceil(A))-x0+1),min(mh,int(np.ceil(C))-y0+1)
        if i<I and j<J:
            paint[j:J,i:I]=0
    # Hough는 초기 방향만 제안합니다. 채택할 때는 원본 행마다 지지점을 다시 검사합니다.
    lines=cv2.HoughLinesP(paint,1,np.pi/180,8,minLineLength=max(10,round(.72*h)),maxLineGap=max(7,round(.65*h)))
    candidates={k:[] for k in ('left','right')}
    if lines is not None:
        for a,c,A,C in lines.reshape(-1,4):
            if C==c: continue
            slope=(A-a)/(C-c)
            side='left' if slope<0 else 'right'
            if .22<=abs(slope)<=3.4:
                candidates[side].append((float(a+(bottom-c)*slope),float(slope)))
    ys,xs=np.nonzero(paint)
    result={}
    for side,lines in candidates.items():
        prior=previous.get(side)
        if prior:
            p=prior['points']
            lines.append((line_x(p,b)-x0,(p[1][0]-p[0][0])/(p[1][1]-p[0][1])))
        best=None
        for base,slope in lines:
            oriented=(base-center)*(1 if side=='right' else -1)
            if not -.75*w<=oriented<=2.7*w: continue
            keep=np.abs(xs-base-(ys-bottom)*slope)<2.6
            if keep.sum()<10: continue
            xx,yy=xs[keep],ys[keep]
            rows,idx,cnt=np.unique(yy,return_index=True,return_counts=True)
            if len(rows)<8 or np.ptp(rows)<max(13,.9*h): continue
            centers=np.add.reduceat(xx,idx)/cnt
            a,d=np.polyfit(rows-bottom,centers,1)
            if not .22<=a*(1 if side=='right' else -1)<=3.4: continue
            model_votes=int(nearby[rows,np.clip(centers.round().astype(int),0,mw-1)].sum())
            old_delta=abs(line_x(prior['points'],b)-x0-d) if prior else float('inf')
            # 점선 사이에서는 짧은 외삽을 허용하되, 긴 외삽과 현재 도색이 없는 프레임은 보류합니다.
            gap=max(0.,float(rows[0]-bottom))
            if gap>max(11,.95*h): continue
            if model_votes<max(4,.19*len(rows)) and not (old_delta<=2.3 and prior['misses']<2): continue
            resid=float(np.median(np.abs(centers-(a*(rows-bottom)+d))))
            if resid>1.5: continue
            score=(min(30,len(rows))+.4*min(28,model_votes)-1.7*gap-1.5*resid
                   -.20*abs(d-center)-min(8,old_delta)*.4)
            if best is None or score>best[0]:
                yy0,yy1=float(rows[0]+y0),float(rows[-1]+y0)
                pts=[[float(x0+d+(yy0-b)*a),yy0],[float(x0+d+(yy1-b)*a),yy1]]
                best=(score,dict(points=pts,x_at_bottom=float(x0+d),native_rows=len(rows),model_rows=model_votes,
                                 gap_px=round(gap,2),residual_px=round(resid,2),misses=0 if model_votes>=max(4,.19*len(rows)) else (prior['misses']+1)))
        if best:
            result[side]=best[1]
    return result


def relation(box, fit):
    # 바퀴를 분해할 수 없는 영상에서는 박스 전체 폭과 안쪽 예상 접지 폭을 함께 사용합니다.
    # 오차 띠에만 닿은 경우에는 접촉 또는 복귀로 확정하지 않습니다.
    left,top,right,bottom=box
    w=right-left
    x=fit['x_at_bottom']
    uncertainty=1.+fit['residual_px']+.11*fit['gap_px']
    if x>right+uncertainty: return 'left'
    if x<left-uncertainty: return 'right'
    inset=max(1.0,.08*w)+uncertainty
    if left+inset<=x<=right-inset and fit['gap_px']<=max(4,.26*(bottom-top)):
        return 'contact'
    return None



class ShortTargetMatch:
    """최대 두 프레임 동안 원본 차량 무늬가 이동했는지 재확인합니다."""
    def __init__(self):
        self.last=None
        self.age=0

    def update(self, image, vehicle, vehicles, seconds):
        gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
        kind='detector' if vehicle else 'missing'
        if not vehicle and self.last and self.age<2:
            old,car,when=self.last
            x,y,X,Y=np.rint(car['box']).astype(int)
            h,w=gray.shape
            # 큰 차의 재연결은 원래 추적기에 맡깁니다.
            if (0<=x<X<=w and 0<=y<Y<=h and 6<X-x<48 and Y-y>5 and 0<seconds-when<=.08):
                template=old[y:Y,x:X]
                a,b=max(0,x-5),max(0,y-5)
                scores=cv2.matchTemplate(gray[b:min(h,Y+5),a:min(w,X+5)],template,cv2.TM_CCOEFF_NORMED)
                _,value,_,(u,v)=cv2.minMaxLoc(scores)
                dx,dy=a+u-x,b+v-y
                testmask=np.ones_like(scores,bool)
                testmask[max(0,v-1):v+2,max(0,u-1):u+2]=False
                peak=float(np.max(scores[testmask])) if testmask.any() else 1.
                # 반대 방향에서도 같은 위치로 돌아오는지 검사해 배경과 가까운 다른 차를 걸러냅니다.
                if template.std()>9 and value>=.89 and value-peak>.055 and max(abs(dx),abs(dy))<=4:
                    patch=gray[y+dy:Y+dy,x+dx:X+dx]
                    reverse=cv2.matchTemplate(old[b:min(h,Y+5),a:min(w,X+5)],patch,cv2.TM_CCOEFF_NORMED)
                    _,back,_,(rx,ry)=cv2.minMaxLoc(reverse)
                    predicted=(np.asarray(car['box'])+[dx,dy,dx,dy]).tolist()
                    conflict=any(B>Y+4 and l<X+dx and A>x+dx and t<Y+dy
                                 for l,t,A,B in (entry['box'] for entry in vehicles))
                    if back>=.89 and max(abs(a+rx-x),abs(b+ry-y))<=1 and not conflict:
                        vehicle=dict(car,box=predicted)
                        kind='native_template'
        self.age=self.age+1 if kind=='native_template' else 0
        self.last=(gray,vehicle,seconds) if vehicle else None
        return vehicle,kind


class RoadGeometry:
    def __init__(self, seed):
        self.seed=np.asarray(seed).reshape(2,2).tolist()
        self.primary='right' if (self.seed[1][0]-self.seed[0][0])/(self.seed[1][1]-self.seed[0][1])>0 else 'left'
        self.previous={}
        self.frame=None
        self.last_primary=None

    def measure(self, number, image, box, endpoints, vehicles, model_mask):
        if self.frame!=number-1:
            self.previous={}
            self.last_primary=None
        self.frame=number
        roi=road_roi(image.shape,box)
        x,y,X,Y=roi
        mask=model_mask(image[y:Y,x:X])
        fits=native_lanes(image,box,mask,roi,vehicles,self.previous)
        w=box[2]-box[0]
        bottom=box[3]
        # 원래 지정한 경계와 같은 선인지 먼저 확인합니다. 다른 차선으로 점프한 후보는 버립니다.
        ref=endpoints or (self.last_primary or self.seed)
        main=fits.get(self.primary)
        if main and abs(main['x_at_bottom']-line_x(ref,bottom))>max(8,.60*w):
            fits.pop(self.primary)
            main=None
        if main:
            self.last_primary=main['points']
        other='left' if self.primary=='right' else 'right'
        if other in fits:
            primary_x=main['x_at_bottom'] if main else line_x(ref,bottom)
            width=(primary_x-fits[other]['x_at_bottom'])*(1 if other=='left' else -1)
            if not .85*w<width<5*w:
                fits.pop(other)
        self.previous=fits
        for fit in fits.values():
            fit['position']=relation(box,fit)
        return dict(roi=roi,primary=self.primary,edges=fits)


