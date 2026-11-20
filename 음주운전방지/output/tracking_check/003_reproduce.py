# 003  수정 전 추적 결과 기록하기
# 차량 선택 기능을 넣기 전 상태를 다시 비교할 수 있게 남깁니다.
# 프로젝트에서 실행하면 002가 같은 야간 영상과 가중치로 추적합니다.
# 프레임별 상자와 ID를 baseline.json에 쓰고 구간별 비교 사진을 만듭니다.

import json, runpy
from pathlib import Path
import cv2
from ultralytics import YOLO
from PIL import Image, ImageDraw
root=Path.cwd(); out=root/'output/tracking_check'
rows=[]; old=YOLO.track

def track(self,*a,**kw):
    r=old(self,*a,**kw); b=r[0].boxes
    rows.append([{'id':int(x.id[0]) if x.id is not None else None,'box':x.xyxy[0].tolist(),'conf':float(x.conf[0])} for x in b])
    return r
YOLO.track=track
cv2.imshow=lambda *a:None
cv2.waitKey=lambda *a:-1
runpy.run_path(str(out/'002_track_preview_before.py'),run_name='__main__')
(out/'baseline.json').write_text(json.dumps(rows))
cap=cv2.VideoCapture(str(root/'videos/비접촉_사고유발_영상_밤.mp4'))
for page,start in enumerate(range(0,len(rows),180)):
    sheet=Image.new('RGB',(1440,6*280))
    for j,n in enumerate(range(start,min(start+180,len(rows)),10)):
        cap.set(cv2.CAP_PROP_POS_FRAMES,n); ok,frame=cap.read()
        if not ok:continue
        for d in rows[n]:
            x1,y1,x2,y2=map(int,d['box']); cv2.rectangle(frame,(x1,y1),(x2,y2),(0,0,255),3);cv2.putText(frame,str(d['id']),(x1,y1-6),0,1,(0,255,255),2)
        im=Image.fromarray(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB)).resize((480,252)); sheet.paste(im,((j%3)*480,(j//3)*280)); ImageDraw.Draw(sheet).text(((j%3)*480+5,(j//3)*280+254),f'Frame {n+1} / {n/30:.2f}s',fill='white')
    sheet.save(out/f'baseline_sheet_{page}.jpg')
cap.release()
print('baseline frames',len(rows),flush=True)
