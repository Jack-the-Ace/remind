# 020  주행 구간 단위로 파일 이동하기
# 같은 폴더를 반복 조회하는 비용을 줄이려고 구간 단위로 모아 확인합니다.
# inventory.sqlite의 이동 계획과 당시 파일 상태를 대조합니다.
# JPG·JSON을 실제로 옮긴 뒤 move_results_complete.csv에 남겨 검산합니다.

# 같은 구간의 파일 상태는 디렉터리 목록에서 한꺼번에 확인합니다.
# 원본 데이터는 삭제하지 않고 기존 계획에 있는 두 파일만 rename합니다.
import os,stat,sqlite3,csv,json,itertools
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
OUT=Path(__file__).resolve().parent;ROOT=Path(r'C:\Users\mbc\Desktop\RedBox데이터셋').resolve();MATCHED=ROOT/'matched'

def snapshot(folder):
 try:
  with os.scandir(folder) as entries:
   return {e.name:(e.stat(follow_symlinks=False).st_size,e.stat(follow_symlinks=False).st_mtime_ns) if e.is_file(follow_symlinks=False) and not e.is_symlink() else 'not_regular' for e in entries}
 except FileNotFoundError:return {}

def group_work(rows):
 result=[]
 try:
  segment=rows[0][4]
  if segment in ('','.','..') or '/' in segment or '\\' in segment:raise RuntimeError('구간명 범위 오류')
  destination=MATCHED/segment
  if not destination.resolve().is_relative_to(MATCHED):raise RuntimeError('목적지 범위 오류')
  sources=set()
  for a,b,x,y,seg,*meta in rows:
   aa,bb,xx,yy=map(Path,[a,b,x,y])
   if seg!=segment or xx!=destination/aa.name or yy!=destination/bb.name:raise RuntimeError('계획 목적지 불일치')
   sources.update([aa.parent,bb.parent])
  for folder in sources:
   resolved=folder.resolve()
   if not resolved.is_relative_to(ROOT) or resolved.is_relative_to(MATCHED) or resolved.drive.lower()!=destination.drive.lower():raise RuntimeError('원본 범위/드라이브 오류')
  states={folder:snapshot(folder) for folder in sources};states[destination]=snapshot(destination)
  destination.mkdir(parents=True,exist_ok=True)
  for a,b,x,y,seg,sz1,tm1,sz2,tm2 in rows:
   aa,bb,xx,yy=map(Path,[a,b,x,y]);sa=states[aa.parent].get(aa.name);sb=states[bb.parent].get(bb.name);dx=states[destination].get(xx.name);dy=states[destination].get(yy.name);ma,mb=(sz1,tm1),(sz2,tm2)
   try:
    if sa is None and sb is None and dx==ma and dy==mb:
     result.append([a,b,x,y,seg,'moved','이전 실행 이동 확인']);continue
    if (sa is not None and dx is not None) or (sb is not None and dy is not None):result.append([a,b,x,y,seg,'skipped','목적지 파일 존재']);continue
    if (sa if sa is not None else dx)!=ma or (sb if sb is not None else dy)!=mb:raise RuntimeError('검사 후 원본 변경 또는 파일 없음')
    did_jpg=False
    if sa is not None:aa.rename(xx);did_jpg=True
    try:
     if sb is not None:bb.rename(yy)
    except Exception:
     if did_jpg:xx.rename(aa)
     raise
    states[aa.parent].pop(aa.name,None);states[bb.parent].pop(bb.name,None);states[destination][xx.name]=ma;states[destination][yy.name]=mb
    result.append([a,b,x,y,seg,'moved',''])
   except Exception as e:result.append([a,b,x,y,seg,'error',str(e)])
  # 이동한 각 파일이 새 폴더에 있으며 옛 경로에는 없는지 실제로 다시 확인합니다.
  after={folder:snapshot(folder) for folder in sources};after[destination]=snapshot(destination)
  expected={row[0]:((row[5],row[6]),(row[7],row[8])) for row in rows}
  for r in result:
   if r[5]!='moved':continue
   aa,bb,xx,yy=map(Path,r[:4]);ma,mb=expected[r[0]]
   if after[destination].get(xx.name)!=ma or after[destination].get(yy.name)!=mb or aa.name in after[aa.parent] or bb.name in after[bb.parent]:r[5:]=['error','이동 후 상태 검사 실패']
 except Exception as e:
  recorded={r[0] for r in result}
  result.extend([*r[:5],'error',str(e)] for r in rows if r[0] not in recorded)
 return result

if __name__=='__main__':
 c=sqlite3.connect(OUT/'inventory.sqlite');q='SELECT p.*,j.size,j.mtime,l.size,l.mtime FROM plans p JOIN files j ON j.path=p.jpg JOIN files l ON l.path=p.json ORDER BY p.segment';groups=(list(g) for _,g in itertools.groupby(c.execute(q),key=lambda r:r[4]));counts={'moved':0,'skipped':0,'error':0};next_report=10000
 with (OUT/'move_results_complete.csv').open('w',encoding='utf-8-sig',newline='') as f,ThreadPoolExecutor(max_workers=8) as pool:
  w=csv.writer(f);w.writerow(['old_jpg','old_json','new_jpg','new_json','segment','status','detail'])
  while batch:=list(itertools.islice(groups,200)):
   for results in pool.map(group_work,batch):
    for r in results:w.writerow(r);counts[r[5]]+=1
   f.flush()
   if sum(counts.values())>=next_report:print(counts,flush=True);next_report=sum(counts.values())+10000
 summary=dict(moved_pairs=counts['moved'],skipped_pairs=counts['skipped'],move_errors=counts['error']);(OUT/'move_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8');print('FINAL',summary,flush=True)
