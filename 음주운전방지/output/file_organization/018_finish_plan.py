# 018  기존 조사 목록으로 이동 계획 완성하기
# 대량 파일을 다시 읽는 시간을 줄이기 위해 SQLite 목록을 재사용합니다.
# 정리 도중 저장한 inventory.sqlite와 아직 이동 전인 폴더가 필요합니다.
# 계획과 제외 사유 CSV를 만든 뒤 이동 재개에 사용합니다.

# 이미 검사한 목록을 재사용해 이동 계획을 일괄 생성합니다. 원본 파일에는 손대지 않습니다.
import sqlite3,csv,json
from pathlib import Path
out=Path(__file__).resolve().parent;root=Path(r'C:\Users\mbc\Desktop\RedBox데이터셋').resolve();matched=root/'matched'
c=sqlite3.connect(out/'inventory.sqlite');c.execute('PRAGMA synchronous=NORMAL')
assert not matched.exists(), '목적지에 기존 파일이 있으면 충돌 검사를 다시 해야 합니다.'
case_conflicts=c.execute('SELECT COUNT(*) FROM (SELECT lower(name) FROM counts GROUP BY lower(name) HAVING COUNT(*)>1)').fetchone()[0]
# Windows 파일명 비교에 맞춰 대소문자만 다른 참조도 같은 이름으로 집계합니다.
if case_conflicts:
 c.executescript("DROP INDEX names; UPDATE files SET name=lower(name) WHERE name IS NOT NULL; CREATE INDEX names ON files(name,kind); DROP TABLE counts; CREATE TABLE counts AS SELECT name,SUM(kind='jpg') nj,SUM(kind='json') nl FROM files WHERE name IS NOT NULL GROUP BY name; CREATE INDEX count_names ON counts(name);")
 for kind in ['jpg','json']:
  with (out/('unmatched_'+kind+'.csv')).open('w',encoding='utf-8-sig',newline='') as f:
   w=csv.writer(f);w.writerow(['path','jpg_name']);w.writerows(c.execute("SELECT f.path,f.name FROM files f JOIN counts c USING(name) WHERE f.kind=? AND f.error='' AND "+('c.nl=0' if kind=='jpg' else 'c.nj=0'),(kind,)))
 with (out/'duplicates.csv').open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.writer(f);w.writerow(['kind','path','jpg_name','same_name_jpg_count','referencing_json_count']);w.writerows(c.execute('SELECT f.kind,f.path,f.name,c.nj,c.nl FROM files f JOIN counts c USING(name) WHERE c.nj>1 OR c.nl>1'))
 print('대소문자 차이 반영 완료',case_conflicts,flush=True)
def dest(segment,source):
 if segment in ('','.','..') or '/' in segment or '\\' in segment:raise ValueError('구간명 오류')
 return str(matched/segment/source.rsplit('\\',1)[-1])
c.create_function('dest',2,dest)
c.execute('DELETE FROM plans');c.execute('DELETE FROM destinations')
c.execute('''INSERT INTO plans SELECT j.path,l.path,dest(j.segment,j.path),dest(j.segment,l.path),j.segment FROM files j JOIN counts c ON j.name=c.name JOIN files l ON l.name=j.name AND l.kind='json' WHERE j.kind='jpg' AND j.error='' AND l.error='' AND c.nj=1 AND c.nl=1''');c.commit()
# 계획끼리 이름이 충돌하는 경우에도 어느 파일도 먼저 이동하지 않습니다.
c.execute('CREATE TEMP TABLE clashes AS SELECT p,COUNT(*) n FROM (SELECT dest_jpg p FROM plans UNION ALL SELECT dest_json p FROM plans) GROUP BY p HAVING n>1')
clashes=c.execute('SELECT COUNT(*) FROM clashes').fetchone()[0];assert clashes==0,'계획 내부 목적지 이름 충돌'
partial=out/'move_plan.csv'
if partial.exists():partial.rename(out/'move_plan.partial.csv')
with partial.open('w',encoding='utf-8-sig',newline='') as f:
 w=csv.writer(f);w.writerow(['old_jpg','old_json','new_jpg','new_json','segment']);w.writerows(c.execute('SELECT * FROM plans'))
with (out/'skipped.csv').open('w',encoding='utf-8-sig',newline='') as f:csv.writer(f).writerow(['jpg','json','new_jpg','new_json','reason'])
with (out/'held_by_error.csv').open('w',encoding='utf-8-sig',newline='') as f:
 w=csv.writer(f);w.writerow(['kind','path','jpg_name','reason']);w.writerows(c.execute("SELECT a.kind,a.path,a.name,'짝 파일에 읽기 오류' FROM files a WHERE a.error='' AND EXISTS(SELECT 1 FROM files b WHERE a.name=b.name AND b.kind!=a.kind AND b.error!='')"))
summary={'scanned_files':c.execute('SELECT COUNT(*) FROM files').fetchone()[0],'jpg_files':c.execute("SELECT COUNT(*) FROM files WHERE kind='jpg'").fetchone()[0],'json_files':c.execute("SELECT COUNT(*) FROM files WHERE kind='json'").fetchone()[0],'planned_pairs':c.execute('SELECT COUNT(*) FROM plans').fetchone()[0],'destination_skipped_pairs':0,'unmatched_jpg':c.execute("SELECT COUNT(*) FROM files f JOIN counts c USING(name) WHERE f.kind='jpg' AND f.error='' AND c.nl=0").fetchone()[0],'unmatched_json':c.execute("SELECT COUNT(*) FROM files f JOIN counts c USING(name) WHERE f.kind='json' AND f.error='' AND c.nj=0").fetchone()[0],'duplicate_name_groups':c.execute('SELECT COUNT(*) FROM counts WHERE nj>1 OR nl>1').fetchone()[0],'duplicate_files':c.execute('SELECT COUNT(*) FROM files f JOIN counts c USING(name) WHERE c.nj>1 OR c.nl>1').fetchone()[0],'file_errors':c.execute("SELECT COUNT(*) FROM files WHERE error!=''").fetchone()[0],'held_by_error':c.execute("SELECT COUNT(*) FROM files a WHERE a.error='' AND EXISTS(SELECT 1 FROM files b WHERE a.name=b.name AND b.kind!=a.kind AND b.error!='')").fetchone()[0],'segments':c.execute('SELECT COUNT(DISTINCT segment) FROM plans').fetchone()[0]}
(out/'plan_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(summary,ensure_ascii=False),flush=True)
