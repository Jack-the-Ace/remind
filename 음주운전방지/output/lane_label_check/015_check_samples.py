# 015  628번 세 색상에서 아홉 장 비교하기
# 사진 속 선을 놓친 것인지 JSON에 좌표가 없는 것인지 확인합니다.
# BLUE·WHITE·YELLOW 세 쌍씩 원본 사진과 JSON을 짝지어 읽습니다.
# 비교 JPG와 manifest.json을 output/lane_label_check에 저장해 판독에 씁니다.

# 원본은 읽기만 하고 9쌍의 라벨 목록과 미리보기만 만듭니다.
from pathlib import Path
from collections import Counter
import json,cv2,numpy as np
root=Path(r'C:\Users\mbc\Desktop\RedBox데이터셋');out=Path('output/lane_label_check');records=[]
def sample_pairs():
    if (root / '원천').is_dir():
        for cat, ts in [('BLUE', 'TS1'), ('WHITE', 'TS3'), ('YELLOW', 'TS3')]:
            folders = sorted((root / '원천' / ts / cat).iterdir())
            for number, index in enumerate([0, len(folders)//3, 2*len(folders)//3], 1):
                folder = folders[index]
                jpg = next(folder.glob('*.jpg'))
                label = root / '라벨/TL2/A' / cat / folder.name / (jpg.stem + '.json')
                yield cat, number, jpg, label
        return

    # 정리한 뒤에도 보고서에서 눈으로 확인한 아홉 장을 그대로 사용합니다.
    catalog = Path(__file__).with_name('manifest.json')
    counts = Counter()
    for row in json.loads(catalog.read_text(encoding='utf-8')):
        cat = row['category']
        counts[cat] += 1
        old = Path(row['jpg'])
        jpg = root / 'dataSetSn_628 (차로위반 영상 데이터)' / old.parent.name / old.name
        yield cat, counts[cat], jpg, jpg.with_suffix('.json')


for cat, j, jp, lp in sample_pairs():
  doc=json.loads(lp.read_text(encoding='utf-8-sig'));info=doc['data_set_info'];src=info['sourceValue'].replace('\\','/').split('/')[-1]
  assert jp.name==src
  data=[o['value'] for o in info['data']];lanes=[v for v in data if v.get('extra',{}).get('value')=='lane'];all_lane=[v for v in data if v.get('extra',{}).get('value')=='lane' or any('lane' in key.lower() for key in v.get('object_Label',{}))]
  img=cv2.imdecode(np.frombuffer(jp.read_bytes(),np.uint8),cv2.IMREAD_COLOR);over=img.copy();pts=[]
  for v in lanes:
   assert v['annotation']=='POLYGONS';a=np.array([[p['x'],p['y']] for p in v['points']]);assert np.isfinite(a).all() and (a>=0).all() and (a[:,0]<=img.shape[1]).all() and (a[:,1]<=img.shape[0]).all();pts.append(np.rint(a).astype(np.int32))
  colors=[(0,255,255),(0,255,0),(255,180,0),(255,0,255)]
  for i,a in enumerate(pts):cv2.fillPoly(over,[a],colors[i%4])
  result=cv2.addWeighted(over,.3,img,.7,0)
  for i,a in enumerate(pts):
   cv2.polylines(result,[a],True,colors[i%4],2);x,y=a[0];cv2.putText(result,f"{i+1}: {lanes[i]['object_Label']['lane_type']}",(max(0,min(int(x),img.shape[1]-350)),max(25,int(y)-10)),0,.7,colors[i%4],2)
  name=f'{cat}_{j}_{jp.stem}.jpg';cv2.imencode('.jpg',result)[1].tofile(str(out/name))
  # 원본과 결과를 같은 크기로 나란히 두고 직접 비교할 자료입니다.
  compare=np.hstack([cv2.resize(img,(960,540)),cv2.resize(result,(960,540))]);cv2.imencode('.jpg',compare)[1].tofile(str(out/f'compare_{cat}_{j}.jpg'))
  rec=dict(category=cat,jpg=str(jp),json=str(lp),sourceValue=info['sourceValue'],output=str(out/name),shape=list(img.shape),lane_count=len(lanes),all_lane_count=len(all_lane),lane_labels=dict(Counter(v['object_Label']['lane_type'] for v in lanes)),attributes=[v['object_Label'] for v in lanes],all_objects=[dict(extra=v.get('extra'),label=v.get('object_Label'),annotation=v.get('annotation')) for v in data]);records.append(rec)
  print(jp.name,rec['lane_labels'],'all_lane',len(all_lane),'drawn',len(lanes),flush=True)
(out/'manifest.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
