# 004  차량을 기억하는 시간 늘려 보기
# 다른 조건을 그대로 두고 track_buffer를 90으로 바꿔 효과를 비교합니다.
# 프로젝트의 야간 영상, yolo26n.pt와 기본 bytetrack.yaml을 읽습니다.
# buffer90.yaml과 buffer90.json을 만들어 기본 추적 결과와 대조합니다.

import json, yaml
from pathlib import Path
import cv2, ultralytics
from ultralytics import YOLO
out=Path('output/tracking_check'); cfg=yaml.safe_load((Path(ultralytics.__file__).parent/'cfg/trackers/bytetrack.yaml').read_text());print(cfg,flush=True)
cfg['track_buffer']=90
(out/'buffer90.yaml').write_text(yaml.safe_dump(cfg))
model=YOLO('yolo26n.pt'); cap=cv2.VideoCapture('videos/비접촉_사고유발_영상_밤.mp4'); rows=[]
while True:
 ok,f=cap.read()
 if not ok:break
 r=model.track(f,tracker=str(out/'buffer90.yaml'),persist=True,conf=.1,classes=[2,3,5,7],device='cpu',verbose=False)[0]
 rows.append([{'id':int(x.id[0]) if x.id is not None else None,'box':x.xyxy[0].tolist(),'conf':float(x.conf[0])} for x in r.boxes])
(out/'buffer90.json').write_text(json.dumps(rows));print('buffer90 complete',len(rows),flush=True)
