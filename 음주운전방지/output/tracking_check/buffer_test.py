import json, yaml
from pathlib import Path
import cv2, ultralytics
from ultralytics import YOLO
out=Path('output/tracking_check'); cfg=yaml.safe_load((Path(ultralytics.__file__).parent/'cfg/trackers/bytetrack.yaml').read_text());print(cfg,flush=True)
cfg['track_buffer']=90
(out/'buffer90.yaml').write_text(yaml.safe_dump(cfg))
model=YOLO('yolo26n.pt'); cap=cv2.VideoCapture('videos/비접촉_사고유발_영상.mp4'); rows=[]
while True:
 ok,f=cap.read()
 if not ok:break
 r=model.track(f,tracker=str(out/'buffer90.yaml'),persist=True,conf=.1,classes=[2,3,5,7],device='cpu',verbose=False)[0]
 rows.append([{'id':int(x.id[0]) if x.id is not None else None,'box':x.xyxy[0].tolist(),'conf':float(x.conf[0])} for x in r.boxes])
(out/'buffer90.json').write_text(json.dumps(rows));print('buffer90 complete',len(rows),flush=True)
