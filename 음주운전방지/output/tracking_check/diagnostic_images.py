import json,cv2
from pathlib import Path
from PIL import Image,ImageDraw
p=Path('output/tracking_check');raw=json.loads((p/'diagnostic_raw.json').read_text());tr=json.loads((p/'diagnostic_tracks.json').read_text());fi=json.loads((p/'diagnostic_final.json').read_text());c=cv2.VideoCapture('videos/비접촉_사고유발_영상.mp4')
for page,start in enumerate(range(528,543,5)):
 s=Image.new('RGB',(1920,5*240))
 for row,n in enumerate(range(start,start+5)):
  c.set(cv2.CAP_PROP_POS_FRAMES,n-1);ok,f=c.read()
  for col,ds in enumerate([[],raw[n-1],tr[n-1],[fi[n-1]] if fi[n-1]['box'] else []]):
   pic=f.copy()
   for d in ds:
    a,b,x,y=map(int,d['box']);cv2.rectangle(pic,(a,b),(x,y),(0,255,255),2);label=f"{d.get('id', '-')}: {d.get('conf',0):.3f}";cv2.putText(pic,label,(a,max(20,b-7)),0,.65,(0,255,255),2)
   im=Image.fromarray(cv2.cvtColor(pic[440:800,650:1450],cv2.COLOR_BGR2RGB)).resize((480,216));s.paste(im,(col*480,row*240));caption=['RAW VIDEO','YOLO conf=.1','ByteTrack','SELECTED' if ds else 'TARGET LOST'][col];ImageDraw.Draw(s).text((col*480+3,row*240+218),f'F{n} {(n-1)/30:.3f}s {caption}',fill='white')
 s.save(p/f'diagnostic_compare_{page}.jpg')
print('images saved')
