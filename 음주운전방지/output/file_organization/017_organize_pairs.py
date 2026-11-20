# 017  628번 원본과 라벨의 이동 계획 세우기
# 같은 이름이 여럿일 수 있어 유일한 쌍만 골라 경로를 먼저 기록합니다.
# 정리 전 원천·라벨 폴더에서 plan으로 목록을 만듭니다. move는 실제 이동입니다.
# inventory.sqlite와 move_plan.csv가 다음 실습의 입력입니다.

# 원본 파일을 삭제하지 않고 유일한 JPG/JSON 쌍만 같은 드라이브에서 이동합니다.
import argparse,csv,json,os,sqlite3,time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
ROOT=Path(r'C:\Users\mbc\Desktop\RedBox데이터셋').resolve()
OUT=Path(__file__).resolve().parent
DB=OUT/'inventory.sqlite'

def csvfile(name,header):
 f=(OUT/name).open('w',encoding='utf-8-sig',newline='');w=csv.writer(f);w.writerow(header);return f,w

def inspect_file(item):
 kind,path=item
 try:
  s=path.stat()
  if kind=='json':
   with path.open('r',encoding='utf-8-sig') as f: doc=json.load(f)
   value=doc['data_set_info']['sourceValue']
   if not isinstance(value,str) or not value.strip():raise ValueError('sourceValue가 비어 있거나 문자열이 아님')
   name=value.replace('\\','/').rsplit('/',1)[-1]
   if not name.lower().endswith(('.jpg','.jpeg')):raise ValueError('sourceValue가 JPG를 가리키지 않음')
  else:
   name=path.name
   with path.open('rb') as f:
    if f.read(2)!=b'\xff\xd8':raise ValueError('JPG 시작 바이트가 아님')
  return kind,str(path),name,path.parent.name,s.st_size,s.st_mtime_ns,''
 except Exception as e:return kind,str(path),path.name if kind=='jpg' else None,path.parent.name,None,None,f'{type(e).__name__}: {e}'

def plan():
 if DB.exists():raise RuntimeError('기존 검사 DB가 있습니다. 이전 기록을 확인하세요.')
 conn=sqlite3.connect(DB);conn.executescript('CREATE TABLE files(kind TEXT,path TEXT PRIMARY KEY,name TEXT,segment TEXT,size INTEGER,mtime INTEGER,error TEXT); CREATE TABLE plans(jpg TEXT,json TEXT,dest_jpg TEXT,dest_json TEXT,segment TEXT); CREATE TABLE destinations(path TEXT PRIMARY KEY);')
 ef,ew=csvfile('errors.csv',['kind','path','error']);n=0
 def walk():
  for kind,sub,ext in [('jpg','원천',('.jpg','.jpeg')),('json','라벨',('.json',))]:
   for folder,dirs,files in os.walk(ROOT/sub,onerror=lambda e:ew.writerow(['directory',e.filename,str(e)])):
    for name in files:
     if name.lower().endswith(ext):yield kind,Path(folder)/name
 with ThreadPoolExecutor(max_workers=8) as pool:
  # 동시에 읽되 목록 전체를 메모리에 쌓지 않도록 1000개씩 처리합니다.
  import itertools
  items=iter(walk())
  while batch:=list(itertools.islice(items,1000)):
   for r in pool.map(inspect_file,batch):
    conn.execute('INSERT INTO files VALUES(?,?,?,?,?,?,?)',r)
    if r[-1]:ew.writerow([r[0],r[1],r[-1]])
    n+=1
   conn.commit()
   if n%10000==0:print('검사 파일',n,flush=True)
 ef.close()
 conn.executescript('CREATE INDEX names ON files(name,kind); CREATE TABLE counts AS SELECT name,SUM(kind="jpg") AS nj,SUM(kind="json") AS nl FROM files WHERE name IS NOT NULL GROUP BY name; CREATE INDEX count_names ON counts(name);')
 df,dw=csvfile('duplicates.csv',['kind','path','jpg_name','same_name_jpg_count','referencing_json_count'])
 for r in conn.execute('SELECT f.kind,f.path,f.name,c.nj,c.nl FROM files f JOIN counts c USING(name) WHERE c.nj>1 OR c.nl>1'):dw.writerow(r)
 df.close()
 for kind in ['jpg','json']:
  f,w=csvfile('unmatched_'+kind+'.csv',['path','jpg_name'])
  for r in conn.execute('SELECT f.path,f.name FROM files f JOIN counts c USING(name) WHERE f.kind=? AND f.error="" AND '+('c.nl=0' if kind=='jpg' else 'c.nj=0'),(kind,)):w.writerow(r)
  f.close()
 pf,pw=csvfile('move_plan.csv',['old_jpg','old_json','new_jpg','new_json','segment'])
 sf,sw=csvfile('skipped.csv',['jpg','json','new_jpg','new_json','reason']);planned=skipped=0
 sql='SELECT j.path,l.path,j.segment FROM files j JOIN counts c ON j.name=c.name JOIN files l ON l.name=j.name AND l.kind="json" WHERE j.kind="jpg" AND j.error="" AND l.error="" AND c.nj=1 AND c.nl=1'
 for a,b,segment in conn.execute(sql):
  destination=(ROOT/'matched'/segment).resolve()
  if not destination.is_relative_to(ROOT/'matched'):raise RuntimeError('목적지 범위 오류')
  x,y=destination/Path(a).name,destination/Path(b).name
  row=[a,b,str(x),str(y),segment]
  if x.exists() or y.exists():sw.writerow(row[:4]+['목적지 파일 존재']);skipped+=1;continue
  try:
   conn.execute('SAVEPOINT reserve');conn.execute('INSERT INTO destinations VALUES(?)',(str(x),));conn.execute('INSERT INTO destinations VALUES(?)',(str(y),));conn.execute('RELEASE reserve')
  except sqlite3.IntegrityError:
   conn.execute('ROLLBACK TO reserve');conn.execute('RELEASE reserve');sw.writerow(row[:4]+['계획 내 목적지 중복']);skipped+=1;continue
  conn.execute('INSERT INTO plans VALUES(?,?,?,?,?)',row);pw.writerow(row);planned+=1
 pf.close();sf.close();conn.commit()
 summary={'scanned_files':n,'jpg_files':conn.execute('SELECT COUNT(*) FROM files WHERE kind="jpg"').fetchone()[0],'json_files':conn.execute('SELECT COUNT(*) FROM files WHERE kind="json"').fetchone()[0],'planned_pairs':planned,'destination_skipped_pairs':skipped,'unmatched_jpg':conn.execute('SELECT COUNT(*) FROM files f JOIN counts c USING(name) WHERE f.kind="jpg" AND f.error="" AND c.nl=0').fetchone()[0],'unmatched_json':conn.execute('SELECT COUNT(*) FROM files f JOIN counts c USING(name) WHERE f.kind="json" AND f.error="" AND c.nj=0').fetchone()[0],'duplicate_name_groups':conn.execute('SELECT COUNT(*) FROM counts WHERE nj>1 OR nl>1').fetchone()[0],'duplicate_files':conn.execute('SELECT COUNT(*) FROM files f JOIN counts c USING(name) WHERE c.nj>1 OR c.nl>1').fetchone()[0],'file_errors':conn.execute('SELECT COUNT(*) FROM files WHERE error!=""').fetchone()[0]}
 (OUT/'plan_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(summary,ensure_ascii=False),flush=True);conn.close()

def move():
 # 계획 CSV를 완성한 다음에만 이동합니다. Windows rename은 기존 파일을 덮어쓰지 않습니다.
 conn=sqlite3.connect(DB)
 if (OUT/'move_results.csv').exists():raise RuntimeError('이미 이동 기록이 있습니다. 중복 실행을 멈춥니다.')
 f,w=csvfile('move_results.csv',['old_jpg','old_json','new_jpg','new_json','segment','status','detail'])
 moved=skipped=errors=0
 for a,b,x,y,segment in conn.execute('SELECT * FROM plans'):
  paths=list(map(Path,[a,b,x,y]));aa,bb,xx,yy=paths
  try:
   for source in (aa,bb):
    if not source.resolve().is_relative_to(ROOT) or source.resolve().is_relative_to(ROOT/'matched'):raise RuntimeError('원본 범위 오류')
    old=conn.execute('SELECT size,mtime FROM files WHERE path=?',(str(source),)).fetchone();now=source.stat()
    if old!=(now.st_size,now.st_mtime_ns):raise RuntimeError('검사 후 원본이 변경됨')
   for destination in (xx,yy):
    if not destination.resolve().is_relative_to(ROOT/'matched') or destination.drive.lower()!=aa.drive.lower():raise RuntimeError('목적지 또는 드라이브 오류')
   if xx.exists() or yy.exists():
    w.writerow([a,b,x,y,segment,'skipped','목적지 파일 존재']);skipped+=1;continue
   xx.parent.mkdir(parents=True,exist_ok=True)
   aa.rename(xx)
   try:bb.rename(yy)
   except Exception:
    xx.rename(aa);raise
   if not xx.is_file() or not yy.is_file() or aa.exists() or bb.exists():raise RuntimeError('이동 후 경로 검사 실패')
   w.writerow([a,b,x,y,segment,'moved','']);moved+=1
  except Exception as e:
   w.writerow([a,b,x,y,segment,'error',str(e)]);errors+=1
  if (moved+skipped+errors)%1000==0:f.flush();print('이동',moved,'건너뜀',skipped,'오류',errors,flush=True)
 f.close();summary=dict(moved_pairs=moved,skipped_pairs=skipped,move_errors=errors);(OUT/'move_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8');print(summary,flush=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('mode',choices=['plan','move']);a=p.parse_args();plan() if a.mode=='plan' else move()
