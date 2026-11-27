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



class PaintCurve:
    """선택한 흰 도색을 원본 행마다 찾아 점선 사이의 도로 경계를 이어 봅니다."""
    def __init__(self, points):
        a=np.asarray(points,float)
        self.low=float(a[:,1].min())
        self.high=float(a[:,1].max())
        self.poly=np.polyfit(a[:,1],a[:,0],min(2,len(a)-1))
        self.recent=[]
        self.last_call=0
        self.call=0

    def measure(self, image, mask, vehicles, box):
        self.call+=1
        h,w=image.shape[:2]
        step=max(2,round(h/200))
        lo=max(0,round(self.low-.20*(self.high-self.low)))
        hi=min(h-1,round(self.high+.34*(self.high-self.low)))
        ys=np.arange(lo,hi,step)
        old=np.polyval(self.poly,ys)
        radius=max(10,round(w*.023))
        offsets=np.arange(-radius,radius+1)
        xs=np.clip(np.rint(old).astype(int)[:,None]+offsets,0,w-1)
        stretch=np.clip((ys-self.low)/(self.high-self.low),0,1)
        stride=np.rint((.003+.008*stretch)*w).astype(int)[:,None]
        y=ys[:,None]
        sample=image[y,xs].astype(float)
        # 양옆 노면보다 밝고 색차가 작은 흰 페인트만 허용합니다. 분홍·초록 유도선은 제외합니다.
        brightness=sample.mean(2)
        before=image[y,np.maximum(0,xs-stride)].mean(2)
        after=image[y,np.minimum(w-1,xs+stride)].mean(2)
        contrast=brightness-np.maximum(before,after)
        good=(contrast>=8)&(np.ptp(sample,axis=2)<np.maximum(16,brightness*.14))
        for car in vehicles:
            a,b,A,B=car['box']
            good &= ~((y>=b-1)&(y<=B+1)&(xs>=a-1)&(xs<=A+1))
        votes=mask[y,xs]!=0
        score=np.minimum(65,contrast)-.48*np.abs(offsets)+12*votes
        score[~good]=-999
        ix=np.argmax(score,axis=1)
        row=np.arange(len(ys))
        keep=good[row,ix]
        yy=ys[keep]; xx=xs[row,ix][keep]; net=votes[row,ix][keep]
        if len(yy)<6: return None
        # 1차 적합 뒤 잔차가 큰 횡방향 화살표·다른 도색을 빼고 다시 곡선을 구합니다.
        degree=2 if len(yy)>12 and np.ptp(yy)>.62*(self.high-self.low) else 1
        for _ in range(2):
            if len(yy)<6 or np.ptp(yy)<.24*(self.high-self.low): return None
            fit=np.polyfit(yy,xx,degree)
            valid=np.abs(np.polyval(fit,yy)-xx)<=max(2.6,w*.005)
            yy,xx,net=yy[valid],xx[valid],net[valid]
        if len(yy)<6 or np.ptp(yy)<.24*(self.high-self.low) or net.sum()<2: return None
        fit=np.polyfit(yy,xx,degree)
        base=np.linspace(self.low,self.high,5)
        # 도색이 모인 구간 밖으로는 곡률을 그대로 연장하지 않습니다.
        def projected(t):
            z=np.clip(t,yy.min(),yy.max())
            return np.polyval(fit,z)+(t-z)*np.polyval(np.polyder(fit),z)
        proposed=projected(base)
        delta=proposed-np.polyval(self.poly,base)
        self.poly=np.polyfit(base,np.polyval(self.poly,base)+np.clip(delta,-radius*.60,radius*.60),2)
        if box is None: return None
        left,top,right,bottom=box
        gap=float(np.min(abs(yy-bottom)))
        height=bottom-top
        if gap>max(15,min(h*.10,height*1.3)): return None
        residual=float(np.median(abs(projected(yy)-xx)))
        at=float(projected(bottom))
        # 급커브에서는 먼 도색의 접선이 바퀴 위치를 빗나갑니다. 차 바로 아래 실제 도색으로 다시 맞춥니다.
        near_y=np.arange(max(1,int(np.ceil(bottom))+1), min(h-1,int(bottom+max(30,min(.095*h,2.4*height)))))
        local=[]
        for ny in near_y:
            center=projected(ny)
            rad=max(8,min(.85*(right-left),.033*w))
            start=max(1,int(center-rad))
            end=min(w-1,int(center+rad)+1)
            if start>=end: continue
            xx0=np.arange(start,end)
            stride=max(3,round(w*.004))
            a=image[ny,xx0].astype(float)
            level=a.mean(1)
            score=level-np.maximum(image[ny,np.maximum(0,xx0-stride)].mean(1),
                                    image[ny,np.minimum(w-1,xx0+stride)].mean(1))
            eligible=(score>=7)&(np.ptp(a,axis=1)<np.maximum(16,level*.14))
            for v in vehicles:
                l,t,r,b=v['box']
                if t-1<=ny<=b+1: eligible &= (xx0<l-1)|(xx0>r+1)
            if not eligible.any(): continue
            rank=np.where(eligible,score.clip(0,60)-.48*abs(xx0-center)+5*(mask[ny,xx0]>0),-1e6)
            ix=rank.argmax()
            local.append((ny,xx0[ix]))
        if len(local)>=8:
            ly,lx=np.asarray(local).T
            # 같은 대시의 양쪽 가장자리나 반사광 한 점이 아니라 연속된 다수의 행을 요구합니다.
            smooth=np.abs(np.diff(lx))<=3.2*np.diff(ly)
            keep=np.r_[smooth,True]&np.r_[True,smooth]
            ly,lx=ly[keep],lx[keep]
            if len(ly)>=8 and np.ptp(ly)>=10:
                dy=ly-bottom
                degree=2 if len(ly)>=13 and np.ptp(dy)>=21 else 1
                coef=np.polyfit(dy,lx,degree,w=1/(1+dy/max(12,height)))
                errors=abs(np.polyval(coef,dy)-lx)
                good=errors<=max(2.2,2*np.median(errors))
                if good.sum()>=7 and np.ptp(dy[good])>=9:
                    coef=np.polyfit(dy[good],lx[good],degree if good.sum()>10 else 1)
                    near=float(dy[good].min())
                    if near<=max(7,.55*height) and abs(coef[-1]-at)<=rad:
                        at=float(coef[-1])
                        gap=near
                        residual=float(np.median(abs(np.polyval(coef,dy[good])-lx[good])))
                        split=float(dy[good].max())
                        original_projection=projected
                        projected=lambda t: np.where(t-bottom<=split,np.polyval(coef,t-bottom),original_projection(t))
        # 한 프레임의 다른 페인트 조각으로 차가 선을 왕복한 것처럼 보이지 않게 합니다.
        if self.last_call!=self.call-1: self.recent.clear()
        self.last_call=self.call
        span=max(1,right-left)
        self.recent=(self.recent+[(at-left)/span])[-5:]
        at=left+span*float(np.median(self.recent))
        error=1+residual+.12*gap
        inset=max(1.,.045*(right-left))
        pos=('left' if right<at-error else 'right' if left>at+error else
             'contact' if left+inset+error<at<right-inset-error else None)
        points=np.unique(np.r_[bottom,np.linspace(max(bottom,yy.min()),max(bottom+1,yy.max()),8)])
        line=np.column_stack([projected(points),points])
        line[0,0]=at
        return dict(points=line.tolist(),position=pos,
                    x_at_bottom=at,gap_px=gap,residual_px=residual,native_rows=len(yy),model_rows=int(net.sum()))


def road_thumbnail(image):
    h,w=image.shape[:2]
    gray=cv2.cvtColor(image[round(.48*h):round(.95*h),round(.02*w):round(.97*w)],cv2.COLOR_BGR2GRAY)
    small=cv2.resize(gray,(180,90),interpolation=cv2.INTER_AREA).astype(np.float32)
    # 플레이어가 화면 전체를 어둡게 해도 노면 무늬의 이동을 비교할 수 있게 합니다.
    return (small-small.mean())/max(1.,small.std())

def recording_clock(cap,start,end,source_seconds):
    cap.set(1,start-1)
    stamps=[]
    difference=[]
    anchor=None
    for f in range(start,end+1):
        ok,im=cap.read()
        if not ok: raise OSError(f)
        thumb=road_thumbnail(im)
        d=1. if anchor is None else float(np.mean(np.abs(thumb-anchor)))
        difference.append(d)
        if d>=.043: anchor=thumb
        stamps.append(source_seconds(cap,f,cap.get(5)))
    fps=cap.get(5)
    if not cap.set(1,start-1): raise OSError("원본 시작 프레임 탐색 실패")
    duplicate=np.array(difference)<.043
    freeze=np.zeros(len(stamps),bool)
    changes=np.diff(np.r_[False,duplicate,False].astype(int))
    for i,j in zip(np.flatnonzero(changes==1),np.flatnonzero(changes==-1)):
        # 촬영차까지 멈춰 있는 일반 정차는 제외하지 않습니다. 전후 도로 화면의 이동도 함께 요구합니다.
        context=round(1.5*fps)
        before=np.asarray(difference[max(1,i-context):i])
        after=np.asarray(difference[j:j+context])
        if j-i>=round(.20*fps) and (before>.065).sum()>=2 and (after>.065).sum()>=2:
            freeze[i:j]=True
    drive=np.array(stamps)-np.cumsum(np.r_[0.,np.diff(stamps)]*freeze)
    return [dict(duplicate=bool(d),freeze=bool(f),drive_s=float(t),scene_delta=round(delta,4))
            for d,f,t,delta in zip(duplicate,freeze,drive,difference)]

