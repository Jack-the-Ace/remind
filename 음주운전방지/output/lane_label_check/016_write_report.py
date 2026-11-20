# 016  628번에서 표시되지 않은 선 정리하기
# 추출한 라벨 수와 직접 본 장면을 함께 두어 누락 이유를 확인합니다.
# 아홉 장의 manifest.json과 당시 같은 장면에서 남긴 판독 내용을 씁니다.
# 점검결과.md와 summary.csv를 저장해 197번 자료와 비교합니다.

from pathlib import Path
import json,csv
out=Path('output/lane_label_check');rows=json.loads((out/'manifest.json').read_text())
observations=[
('차량 아래 오른쪽 파란 선 구간','왼쪽 파란 선, 가운데 노란 이중선, 다른 흰 차선','차량에 가린 파란 선 연속 구간'),
('오른쪽 파란 선과 그 앞쪽 흰 점선 구간','왼쪽 파란 선, 가운데 노란 이중선, 오른쪽의 다른 흰 선','검은 차량에 가린 도색'),
('오른쪽 가장자리 선과 택시 왼쪽 파란 선','화면 왼쪽의 다른 흰 차선','택시·앞차에 가린 파란 선 부분'),
('오토바이 아래로 이어지는 가운데 흰 선','오른쪽 흰 경계선, 왼쪽 노란 가장자리 선','오토바이에 가린 선의 끝부분'),
('내 차로 왼쪽 흰 선','오른쪽 흰 차선, 왼쪽 다른 흰 차선','앞차 모자이크 아래 선'),
('검은 승용차 오른쪽 흰 선','왼쪽 흰 점선, 오른쪽 노란 가장자리 선','검은 차 아래 도색'),
('왼쪽 노란 이중 중앙선 영역','가운데 흰 점선, 오른쪽 노란 가장자리 선','중앙선을 밟은 차 아래 부분'),
('오른쪽 노란 가장자리 선(lane_shoulder)','왼쪽 노란 이중선, 반대편 흰 차선','앞 흰 SUV 아래 선'),
('왼쪽 노란 이중 중앙선 영역','가운데 흰 점선','맞은편 차량에 가린 중앙선')]
report='''# 차선 라벨 샘플 9쌍 점검

BLUE/WHITE/YELLOW에서 각 3개, 서로 다른 video_id의 사진 9개를 점검했다. 원천 TS1/TS3와 라벨 TL2/A에 있는 샘플이며 데이터 전체의 무작위 통계 표본은 아니다. JSON sourceValue의 마지막 JPG 파일명과 실제 원천 JPG 이름을 대조했다. 원본 JPG·JSON은 읽기만 했다. 전체 경로와 JSON의 모든 객체 종류는 manifest.json에 있다.

## 방법과 코드 누락 확인

기존 014_preview_lane_label.py는 data_set_info.data[*].value.extra.value == lane을 고른다. 그 필터와 별도로 object_Label의 lane 관련 키가 있는 객체도 찾아 비교했다. 모든 JSON을 재귀적으로 훑어 points가 있는 다른 위치도 확인했다. 좌표 객체는 모두 data 목록 안에 있었고, 차선 후보 수와 기존 필터 수가 9장 모두 같았다. 모든 차선 좌표는 POLYGONS이며 원본 크기 범위 내였다. 총 11개 영역을 반투명 fillPoly와 닫힌 polylines로 전부 그렸다. 이 9장 안에서 JSON에는 있지만 코드가 그리지 않은 차선 라벨은 0개다.

015_check_samples.py가 기존 코드의 그리기 방식을 사용해 각각 별도 파일로 저장한다. compare_*.jpg는 왼쪽 원본/오른쪽 결과의 나란히 보기다. 9장의 비교 이미지를 직접 열어 확인했다. 표시색은 구분용이며 실제 도색색과 같지 않다. 정지선·횡단보도·화살표는 차선 누락 집계에 넣지 않았다. 이 결과는 사람이 그리지 않은 모든 선의 정확한 개수를 새로 세거나 새 정답을 만든 것이 아니다.

## 사진별 점검

| 사진명 | JSON의 차선 라벨(영역 개수) | 표시된 선 | 눈으로 보이는 미표시 차선 | 빠진 이유 / 판단 어려운 부분 |
|---|---|---|---|---|
'''
for r,(shown,missing,uncertain) in zip(rows,observations):
 labels=', '.join(f'{k} ×{v}' for k,v in r['lane_labels'].items());name=Path(r['jpg']).name
 report+=f'| {name} | {labels} | {shown} | {missing} | JSON에 라벨 없음. {uncertain}은 확인 어려움. |\n'
 r.update(marked_visible=shown,unmarked_visible=missing,missing_reason='JSON에 라벨 없음',uncertain=uncertain,code_missing_count=0)
report+='''
YELLOW의 38599 사진은 folder=YELLOW지만 JSON lane_type은 lane_shoulder다. 폴더명은 실제 차선 라벨 이름을 대신할 수 없다. 복선도 하나의 POLYGONS 객체로 표시될 수 있어 물리적인 페인트 줄 수와 영역 라벨 개수는 다르다. 가려진 구간을 폴리곤이 통과하더라도 그 부분의 실제 도색 정합은 확인 어려움으로 분리했다.

## 판단

이 9장 기준으로 628을 '화면의 모든 차선'을 검출/분할하는 학습 정답으로 바로 쓰는 것은 권하지 않는다. 샘플에서 보이는 다른 차선이 정답에서 빠져 있어, 미라벨 영역을 전부 배경으로 학습시키면 실제 차선을 배경으로 잘못 가르칠 가능성이 있다. 이는 샘플 점검에 근거한 추론이며 데이터셋 전체가 같은 규칙이라고 확정한 것은 아니다. 일부 위반 관련 선만 대상으로 했을 가능성은 있지만 공식 라벨링 지침을 확인하지 못했으므로 확정하지 않는다.

AI Hub 197번 샘플도 비교한 뒤 학습 데이터를 선택하는 것이 좋다. 비교할 것은 보이는 모든 차선의 라벨 범위, 좌우 경계·점선·복선 표현, 가림 처리, 선 좌표/영역 좌표 형식, 레드박스 블랙박스 시점과의 일치다. 이번에는 197 샘플을 다운로드하거나 실제 검사하지 않았고, 197이 더 완전하다고 단정하지 않는다. 공식 사이트 628/197 상세 페이지는 조회를 시도했으나 이 실행의 웹 도구에서 접근 오류가 났다. 결론은 로컬 9쌍 검사에 근거한다.

628은 라벨이 있는 특정 선을 확인하는 실습이나 범위를 한정한 실험 후보로 남길 수 있다. 전체 차선 모델의 학습을 시작하기 전에는 라벨 지침 확인과 197의 동일 방식 샘플 비교가 필요하다. 이번 작업에서 학습·변환·재라벨링은 하지 않았다.

## 결과와 재현

- 실제 결과 JPG: BLUE_1~3_*.jpg, WHITE_1~3_*.jpg, YELLOW_1~3_*.jpg (총 9장)
- 원본/결과 비교: compare_BLUE_1~3.jpg, compare_WHITE_1~3.jpg, compare_YELLOW_1~3.jpg
- 각 JPG·JSON 전체 경로와 라벨 속성: manifest.json
- 요약 표: summary.csv

프로젝트 폴더에서 python output/lane_label_check/015_check_samples.py
'''
(out/'점검결과.md').write_text(report,encoding='utf-8');(out/'manifest.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
with (out/'summary.csv').open('w',encoding='utf-8-sig',newline='') as f:
 w=csv.writer(f);w.writerow(['사진명','JSON 차선 라벨','그린 개수','표시된 선','미표시 선','빠진 이유','확인 어려움','코드 누락','JPG 경로','JSON 경로','결과 경로'])
 for r in rows:w.writerow([Path(r['jpg']).name,json.dumps(r['lane_labels'],ensure_ascii=False),r['lane_count'],r['marked_visible'],r['unmarked_visible'],r['missing_reason'],r['uncertain'],0,r['jpg'],r['json'],r['output']])
print('9쌍 / 차선 11개 / 코드 누락 0개. 보고서와 CSV 저장 완료.')
