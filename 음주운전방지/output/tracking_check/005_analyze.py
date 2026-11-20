# 005  상자와 추적 번호가 빠진 구간 세기
# 눈으로 확인한 번호의 상자 사이를 보간해 비교할 위치를 정합니다.
# baseline.json과 buffer90.json에서 첫 606프레임을 비교합니다.
# reference_boxes.json과 두 설정의 타깃 기록을 남겨 선택 결과와 대조합니다.

import json
from pathlib import Path
p=Path('output/tracking_check');b=json.loads((p/'baseline.json').read_text());v=json.loads((p/'buffer90.json').read_text());ids={1,13,17,58,63,66}
anchors={i:next(d['box'] for d in ds if d['id'] in ids) for i,ds in enumerate(b) if any(d['id'] in ids for d in ds)}
def iou(a,b):
 x=max(0,min(a[2],b[2])-max(a[0],b[0]));y=max(0,min(a[3],b[3])-max(a[1],b[1]));q=x*y;return q/((a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-q+1e-6)
truth=[]
for i in range(606):
 if i in anchors:t=anchors[i]
 else:
  lo=max(k for k in anchors if k<i); hi=min(k for k in anchors if k>i); t=[a+(c-a)*(i-lo)/(hi-lo) for a,c in zip(anchors[lo],anchors[hi])]
 truth.append(t)
(p/'reference_boxes.json').write_text(json.dumps(truth))
for label,rows in [('baseline',b),('buffer90',v)]:
 states=[]
 for i,t in enumerate(truth):
  ds=[d for d in rows[i] if iou(t,d['box'])>.35]; d=max(ds,key=lambda d:iou(t,d['box'])) if ds else None;states.append(d)
 (p/f'{label}_target.json').write_text(json.dumps(states))
 print(label,'box missing',sum(d is None for d in states),'ID missing',sum(d is None or d['id'] is None for d in states))
 runs=[]
 for i,d in enumerate(states):
  k=d['id'] if d else 'NO BOX'
  if not runs or runs[-1][2]!=k:runs.append([i+1,i+1,k])
  else:runs[-1][1]=i+1
 print(runs)
