import json,cv2
from pathlib import Path
from PIL import Image,ImageDraw
p=Path('output/tracking_check'); final=json.loads((p/'final.json').read_text());ref=json.loads((p/'reference_boxes.json').read_text());base=json.loads((p/'baseline.json').read_text());c=cv2.VideoCapture('videos/비접촉_사고유발_영상.mp4')
for page,ns in enumerate([[1,205,240,421,439,528],[531,542,567,571,580,606]]):
 s=Image.new('RGB',(1440,6*245))
 for j,n in enumerate(ns):
  c.set(cv2.CAP_PROP_POS_FRAMES,n-1);_,f=c.read()
  for side in range(2):
   pic=f.copy();ds=base[n-1] if side==0 else ([final[n-1]] if final[n-1]['box'] else [])
   for d in ds:
    a,b,x,y=map(int,d['box']);cv2.rectangle(pic,(a,b),(x,y),(0,0,255) if side==0 else (0,255,255),3);cv2.putText(pic,str(d['id']),(a,b-6),0,1,(0,255,255),2)
   im=Image.fromarray(cv2.cvtColor(pic[440:820,400:1600],cv2.COLOR_BGR2RGB)).resize((720,220));s.paste(im,(side*720,j*245));lab=f'F{n} {(n-1)/30:.2f}s '+('BEFORE' if side==0 else ('AFTER / TARGET LOST' if not ds else 'AFTER'))
   ImageDraw.Draw(s).text((side*720+4,j*245+222),lab,fill='white')
 s.save(p/f'comparison_{page}.jpg')
print('final',len(final),'missing1-606',sum(x['box'] is None for x in final[:606]))
