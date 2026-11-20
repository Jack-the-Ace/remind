# 021  파일 정리 결과 검산하기
# 계획 건수만 믿지 않고 이동 후의 폴더와 표본 쌍을 다시 확인합니다.
# 정리 직후의 원천·라벨·matched와 plan_summary.json, move_summary.json이 필요합니다.
# verification.json과 정리결과.md에 파일 수와 표본 확인 결과를 남깁니다.

# 이동을 마친 뒤 실제 디렉터리에서 파일 수를 다시 셉니다.
import os,json,csv,sqlite3
from pathlib import Path
ROOT=Path(r'C:\Users\mbc\Desktop\RedBox데이터셋');OUT=Path(__file__).resolve().parent
plan=json.loads((OUT/'plan_summary.json').read_text(encoding='utf-8'));move=json.loads((OUT/'move_summary.json').read_text(encoding='utf-8'));result={}
for sub in ['원천','라벨','matched']:
 counts={'jpg':0,'json':0,'files':0,'segments':0}
 for folder,dirs,files in os.walk(ROOT/sub):
  if sub=='matched' and folder!=str(ROOT/sub) and files:counts['segments']+=1
  for name in files:
   counts['files']+=1
   if name.lower().endswith(('.jpg','.jpeg')):counts['jpg']+=1
   elif name.lower().endswith('.json'):counts['json']+=1
 result[sub]=counts
assert result['matched']['jpg']==move['moved_pairs']==result['matched']['json']
assert result['원천']['jpg']+result['matched']['jpg']==plan['jpg_files']
assert result['라벨']['json']+result['matched']['json']==plan['json_files']
assert result['matched']['segments']==plan['segments']
c=sqlite3.connect(OUT/'inventory.sqlite')
samples=[]
for row in c.execute('SELECT dest_jpg,dest_json FROM plans LIMIT 9'):
 a,b=map(Path,row);doc=json.loads(b.read_text(encoding='utf-8-sig'));name=doc['data_set_info']['sourceValue'].replace('\\','/').split('/')[-1];assert name.casefold()==a.name.casefold();samples.append(dict(jpg=str(a),json=str(b)))
result['sample_pairs']=samples;result['status']='PASS'
(OUT/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
summary=[['실제 이동 쌍',move['moved_pairs']],['주행 구간',plan['segments']],['짝 없는 JPG',plan['unmatched_jpg']],['짝 없는 JSON',plan['unmatched_json']],['중복 이름 묶음',plan['duplicate_name_groups']],['중복 관련 파일',plan['duplicate_files']],['읽기/형식 오류 파일',plan['file_errors']],['오류 짝 때문에 보류한 파일',plan['held_by_error']],['목적지 충돌 건너뜀 쌍',move['skipped_pairs']],['이동 오류 쌍',move['move_errors']]]
with (OUT/'summary.csv').open('w',encoding='utf-8-sig',newline='') as f:
 w=csv.writer(f);w.writerow(['항목','개수']);w.writerows(summary)
notes='''# 파일 정리 결과

이동 전 move_plan.csv에 기존 JPG·JSON 경로와 새 경로를 기록했다. 실제 완료 기록은 move_results_complete.csv이며 중간 실행 기록과 구분한다.

매칭은 JSON의 data_set_info.sourceValue에서 마지막 JPG 이름을 추출해 Windows 파일명 비교처럼 대소문자를 무시했다. 대소문자만 다른 참조 63건도 반영했다. 파일의 실제 이름은 바꾸지 않았다. 원천 JPG의 기존 부모 폴더 이름을 matched 아래 주행 구간 이름으로 유지했다.

파일 삭제나 덮어쓰기는 하지 않았다. 짝 없는 파일·중복·읽기 오류 파일은 이동하지 않았다. 오류 JPG와 연결된 정상 JSON도 함께 보류했다. JPG는 파일 열기와 JPEG 시작 바이트를 확인했으며, 전체 사진을 모두 디코딩해 손상 여부를 검사한 것은 아니다.

- move_plan.csv: 이동 전 계획 (기존/새 경로)
- move_results_complete.csv: 전체 실제 이동 결과 (최종 기록)
- unmatched_jpg.csv / unmatched_json.csv: 반대편 파일명이 없는 목록
- duplicates.csv: 같은 이름 JPG 또는 같은 JPG를 가리키는 JSON의 중복 목록
- errors.csv: 읽기·JSON 구조·JPG 시작 바이트 오류 목록
- held_by_error.csv: 짝 파일의 오류 때문에 함께 보류한 목록
- skipped.csv: 이동 계획 단계의 목적지 충돌 목록. 실행 단계 건너뜀은 move_results_complete.csv에서 status=skipped로 확인.
- summary.csv: 최종 수량
- verification.json: 이동 후 실제 폴더 파일 수 검증 및 새 경로의 표본 9쌍 확인

원래 주행 구간 폴더 중 비어 있는 폴더도 삭제하지 않았다. 이전 실습의 원본 경로는 변경되므로 move_plan.csv 또는 최종 이동 기록에서 새 경로를 찾을 수 있다.
'''
(OUT/'정리결과.md').write_text(notes,encoding='utf-8')
print(json.dumps(result,ensure_ascii=False),flush=True)
