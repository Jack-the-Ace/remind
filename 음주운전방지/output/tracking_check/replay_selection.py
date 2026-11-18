import json,cv2,sys
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from track_preview import Target
p=Path('output/tracking_check');rows=json.loads((p/'baseline.json').read_text());c=cv2.VideoCapture('videos/비접촉_사고유발_영상.mp4');t=Target();logs=[]
for i,ds in enumerate(rows):
 _,f=c.read()
 if i==0:t.select(next(d for d in ds if d['id']==1),f,1);d=next(d for d in ds if d['id']==1)
 else:d=t.update(ds,f,i+1)
 logs.append({'frame':i+1,'id':d['id'] if d else None,'box':d['box'] if d else None})
(p/sys.argv[1]).write_text(json.dumps(logs));runs=[]
for x in logs:
 if not runs or runs[-1][2]!=x['id']:runs.append([x['frame'],x['frame'],x['id']])
 else:runs[-1][1]=x['frame']
print(runs)
