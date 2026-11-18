# 현재 스크립트를 그대로 실행하고 관찰용 기록만 덧붙입니다. 설정은 바꾸지 않습니다.
import inspect, textwrap, json, runpy, sys, hashlib
from pathlib import Path
import cv2
import numpy as np
from ultralytics import YOLO
root=Path.cwd();sys.path.insert(0,str(root));import track_preview as app
out=root/'output/tracking_check'; records=[];raw=[];tracked=[]
def record(self,n,d,reason,**extra):
 records.append(dict(frame=n,last_accepted=self.last_frame,gap=n-self.last_frame,candidate_id=d['id'] if d else None,box=d['box'] if d else None,reason=reason,**extra))
src=textwrap.dedent(inspect.getsource(app.Target.update))
src=src.replace('if gap > 30:\n        return None','if gap > 30:\n        for d in (detections or [None]): record(self, number, d, "30프레임 초과")\n        return None')
src=src.replace("if d['id'] is None:\n            continue", "if d['id'] is None:\n            record(self, number, d, 'ID 없음')\n            continue")
src=src.replace('if np.any(ratio < .5) or np.any(ratio > 2) or distance > min(1.4, .65 + gap * .04):\n            continue','if np.any(ratio < .5) or np.any(ratio > 2) or distance > min(1.4, .65 + gap * .04):\n            record(self, number, d, "위치·크기 조건", ratio=ratio.tolist(), distance=float(distance), limit=min(1.4, .65+gap*.04))\n            continue')
src=src.replace('if look is None or self.look is None:\n            continue','if look is None or self.look is None:\n            record(self, number, d, "외형·색상 점수", unavailable=True)\n            continue')
src=src.replace('if shape < (.15 if same_id else .20) or color < (.45 if same_id else .70):\n            continue','if shape < (.15 if same_id else .20) or color < (.45 if same_id else .70):\n            record(self, number, d, "외형·색상 점수", shape=shape, color=float(color), shape_limit=.15 if same_id else .20, color_limit=.45 if same_id else .70)\n            continue')
src=src.replace('self.pending, self.streak = None, 0\n        return None','for score, d in candidates: record(self, number, d, "후보끼리 점수가 비슷함", score=score)\n        self.pending, self.streak = None, 0\n        return None',1)
src=src.replace('if self.streak < 3:\n            return None','if self.streak < 3:\n            record(self, number, d, "새 ID가 3프레임 연속 확인되지 않음", streak=self.streak)\n            return None')
src=src.replace("b = np.array(d['box'])\n    movement", "record(self, number, d, '채택')\n    b = np.array(d['box'])\n    movement")
ns=dict(app.__dict__,record=record);exec(src,ns);app.Target.update=ns['update'];(out/'diagnostic_update.py').write_text(src,encoding='utf-8')
original=YOLO.track
registered=False

def capture(predictor):
 # 추적기가 결과를 덮어쓰기 전에 YOLO의 원래 검출 상자를 복사합니다.
 raw.append([dict(box=b.xyxy[0].tolist(),conf=float(b.conf[0]),cls=int(b.cls[0])) for b in predictor.results[0].boxes])
def track(self,*a,**kw):
 global registered
 if not registered:
  self.add_callback('on_predict_postprocess_end',capture);registered=True
 r=original(self,*a,**kw)
 tracked.append([dict(box=b.xyxy[0].tolist(),id=int(b.id[0]) if b.id is not None else None,conf=float(b.conf[0])) for b in r[0].boxes])
 return r
YOLO.track=track
sys.argv=['track_preview.py','--headless','--select','690','560','--log',str(out/'diagnostic_final.json')]
app.main()
for name,data in [('diagnostic_candidates',records),('diagnostic_raw',raw),('diagnostic_tracks',tracked)]:
 (out/f'{name}.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
print('frames',len(raw),len(tracked));print('timeout first',next(x for x in records if x['reason']=='30프레임 초과'))
for n in [528,529,530,531,532,540,541,542,543,558,559]:
 print('FRAME',n,'RAW',raw[n-1],'TRACK',tracked[n-1]);print('DECISIONS',[x for x in records if x['frame']==n])
