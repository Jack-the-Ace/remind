# 019  중간에 멈춘 파일 이동 재개하기
# 원본과 목적지 상태를 대조해 이미 옮긴 쌍도 구분합니다.
# 당시의 inventory.sqlite, 원천·라벨 폴더와 같은 드라이브의 matched를 씁니다.
# 쌍을 실제로 이동하고 move_results_final.csv에 처리 상태를 남깁니다.

# 이동 계획 CSV/DB를 기준으로 재개합니다. 각 쌍은 독립적으로 처리하며 기존 파일은 덮어쓰지 않습니다.
import csv,json,sqlite3,os,stat,itertools
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
OUT=Path(__file__).resolve().parent; ROOT=Path(r'C:\Users\mbc\Desktop\RedBox데이터셋').resolve(); MATCHED=ROOT/'matched';parents={}

def checked_parent(p,inside):
 key=str(p)
 if key not in parents:parents[key]=p.resolve()
 if not parents[key].is_relative_to(inside):raise RuntimeError('허용된 디렉터리 밖의 경로')
 return parents[key]
def info(p):
 try:
  s=p.lstat()
  if stat.S_ISLNK(s.st_mode) or not stat.S_ISREG(s.st_mode):raise RuntimeError('일반 파일이 아닌 경로')
  return (s.st_size,s.st_mtime_ns)
 except FileNotFoundError:return None

def one(row):
 a,b,x,y,segment,sz1,tm1,sz2,tm2=row
 try:
  aa,bb,xx,yy=map(Path,[a,b,x,y]); expected=MATCHED/segment
  # 주행 구간과 실제 목적지가 일치하며 모든 절대 경로가 지정 루트 안인지 검증합니다.
  if segment in ('','.','..') or '/' in segment or '\\' in segment:raise RuntimeError('잘못된 구간명')
  if xx.parent!=expected or yy.parent!=expected or xx.name!=aa.name or yy.name!=bb.name:raise RuntimeError('계획 목적지 불일치')
  for s in (aa,bb):
   checked_parent(s.parent,ROOT)
   if (parents[str(s.parent)]/s.name).is_relative_to(MATCHED):raise RuntimeError('원본이 matched 안에 있음')
  checked_parent(expected,MATCHED)
  if xx.drive.lower()!=aa.drive.lower() or yy.drive.lower()!=bb.drive.lower():raise RuntimeError('드라이브 불일치')
  sa,sb,dx,dy=info(aa),info(bb),info(xx),info(yy);ma,mb=(sz1,tm1),(sz2,tm2)
  # 중단 직전에 이미 이동된 쌍은 검증만 합니다.
  if sa is None and sb is None and dx==ma and dy==mb:return [a,b,x,y,segment,'moved','이전 실행 이동 확인']
  if (dx is not None and sa is not None) or (dy is not None and sb is not None):return [a,b,x,y,segment,'skipped','목적지 파일 존재']
  if (sa if sa is not None else dx)!=ma or (sb if sb is not None else dy)!=mb:raise RuntimeError('파일이 없거나 검사 후 크기/시간이 변경됨')
  expected.mkdir(parents=True,exist_ok=True)
  # Windows rename은 목적지에 파일이 생겨도 덮어쓰지 않습니다.
  did_jpg=False
  if sa is not None:aa.rename(xx);did_jpg=True
  try:
   if sb is not None:bb.rename(yy)
  except Exception:
   if did_jpg:xx.rename(aa)
   raise
  if info(xx)!=ma or info(yy)!=mb or aa.exists() or bb.exists():raise RuntimeError('이동 후 검증 실패')
  return [a,b,x,y,segment,'moved','']
 except Exception as e:return [a,b,x,y,segment,'error',f'{type(e).__name__}: {e}']

if __name__=='__main__':
 c=sqlite3.connect(OUT/'inventory.sqlite');query='SELECT p.*,j.size,j.mtime,l.size,l.mtime FROM plans p JOIN files j ON j.path=p.jpg JOIN files l ON l.path=p.json';rows=iter(c.execute(query));counts={'moved':0,'skipped':0,'error':0}
 with (OUT/'move_results_final.csv').open('w',encoding='utf-8-sig',newline='') as f,ThreadPoolExecutor(max_workers=8) as pool:
  w=csv.writer(f);w.writerow(['old_jpg','old_json','new_jpg','new_json','segment','status','detail'])
  while batch:=list(itertools.islice(rows,1000)):
   for r in pool.map(one,batch):w.writerow(r);counts[r[5]]+=1
   f.flush()
   if sum(counts.values())%10000==0:print(counts,flush=True)
 summary=dict(moved_pairs=counts['moved'],skipped_pairs=counts['skipped'],move_errors=counts['error']);(OUT/'move_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8');print('FINAL',summary,flush=True)
