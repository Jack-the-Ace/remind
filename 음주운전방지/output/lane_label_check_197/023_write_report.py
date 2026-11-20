# 023  197번과 628번의 라벨 범위 비교하기
# 사진에 보이는 좌우 차선과 실제 라벨을 대조해 학습 후보를 고릅니다.
# selected_pairs.json과 같은 다섯 장의 육안 판독 메모를 사용합니다.
# sample_check.csv와 점검결과_197.md를 저장해 마스크 설계에 참고합니다.

import json,csv
from pathlib import Path
out=Path('output/lane_label_check_197');rows=json.loads((out/'selected_pairs.json').read_text())
notes=[
('고가도로 옆 진입로','좌우 흰 경계선 2개가 도색을 따라 표시됨. 뚜렷한 좌우 경계 누락은 발견하지 못함.','먼 합류 지점은 선이 모여 세밀한 구분이 어려움. 가로 감속 표시는 차선 누락으로 세지 않음.'),
('방음벽 옆 다차로·차량 밀집','가까운 왼쪽 차로 구분선과 오른쪽 선들, 주변 차로 선이 표시됨. 뚜렷한 근거리 선의 큰 누락은 발견하지 못함.','검은 차 등 차량 위로 선이 이어지는 구간은 실제 가려진 도색 정합을 확인하기 어려움.'),
('도심 교차로','양옆에 보이는 선들을 표시. 정지선 1개는 빨강, 오른쪽 횡단보도 영역 1개는 파랑 테두리로 구분됨.','앞 SUV·트럭에 가린 내 차로의 연속 경계와 먼 점선은 확인 어려움. 교차로의 무도색 부분을 누락으로 세지 않음.'),
('공사 가시설 사이 차로','좌우 노란 가장자리와 가운데 흰 점선 경로, 가시설 밖 주변 선들을 표시. 근거리 뚜렷한 좌우 선의 큰 누락은 발견하지 못함.','점선의 빈 간격에도 선이 이어지고 공사 구조물에 가려진 구간이 있어 그 부분의 실제 도색은 확인 어려움.'),
('수목·대형차가 있는 굽은 도로','중앙 노란 선과 좌우 흰 가장자리 선 3개가 곡선을 따라 표시됨. 뚜렷하게 보이는 주요 선의 큰 누락은 발견하지 못함.','대형차 뒤로 가려진 중앙선·왼쪽 가장자리 및 먼 곡선 끝은 확인 어려움.')]
for r,(scene,seen,hard) in zip(rows,notes):r.update(scene=scene,visual_check=seen,uncertain=hard)
(out/'selected_pairs.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
with (out/'sample_check.csv').open('w',encoding='utf-8-sig',newline='') as f:
 w=csv.writer(f);w.writerow(['사진명','장면','차선 객체 수','정지선','횡단보도','육안 확인','확인 어려움','JPG 경로','JSON 경로','결과 경로'])
 for r in rows:w.writerow([Path(r['jpg']).name,r['scene'],r['classes'].get('traffic_lane',0),r['classes'].get('stop_line',0),r['classes'].get('crosswalk',0),r['visual_check'],r['uncertain'],r['jpg'],r['json'],r['result']])
report='''# AI Hub 197 로컬 샘플 확인

## 짝과 실제 구조

폴더: C:\\Users\\mbc\\Desktop\\RedBox데이터셋\\dataSetSn_197 (차선_횡단보도인지(수도권))

원천데이터/1900_1200/daylight JPG 1,200장, 라벨링데이터/1900_1200/daylight JSON 1,200개를 발견했다. 각 JSON의 image.file_name과 실제 JPG 이름을 대조한 결과 유일한 쌍 1,200개, 짝 없음·중복·JSON 읽기 오류 0개. 모든 사진을 디코딩해 본 결과라는 뜻은 아니며 실제 이미지 좌표 검증은 선택한 5장에 대해 수행했다. 대응 라벨이 이미 있으므로 이 묶음을 위해 추가로 받을 라벨은 없다. 전체 경로 목록은 pairs.json.

실제 예시 구조:
```json
{"image":{"file_name":"2215110.jpg","image_size":[1200,1920]},"annotations":[{"class":"traffic_lane","attributes":[{"code":"lane_color","value":"white"},{"code":"lane_type","value":"solid"}],"category":"polyline","data":[{"x":439,"y":1198},{"x":962,"y":635},{"x":1020,"y":623}]}]}
```

image_size는 [높이,너비]. 선택한 5장의 실제 크기는 모두 1920×1200이었으며 선언 크기와 같았다. 폴더명 1900_1200의 1900을 좌표 너비로 가정하지 않았다. traffic_lane과 stop_line은 polyline으로 끝을 닫지 않고 순서대로 선 연결. crosswalk는 polygon으로 닫힌 테두리만 그림. 범례는 차선 초록, 정지선 빨강, 횡단보도 파랑. 원본 픽셀 좌표를 그대로 사용하며 스케일 보정은 하지 않았다.

전체 JSON에서 traffic_lane 7,014개, stop_line 98개, crosswalk 104개 객체를 확인했다. 이는 물리적 차선의 개수가 아니라 라벨 객체 개수다.

## 직접 확인한 5장

5장의 원본/표시 결과를 같은 크기로 나란히 비교했고, 공사 구간은 원본 해상도의 표시 이미지도 열어 확인했다. 선택한 차선 30개, 정지선 1개, 횡단보도 1개를 모두 그렸다. 선 좌표는 도색의 위치·곡률과 대체로 맞지만 정확도를 수치 평가한 것은 아니다.

| 사진 | 장면 | 차선 / 정지선 / 횡단보도 | 육안 확인 | 확인 어려움 |
|---|---|---|---|---|
'''
for r in rows:report+=f"| {Path(r['jpg']).name} | {r['scene']} | {r['classes'].get('traffic_lane',0)} / {r['classes'].get('stop_line',0)} / {r['classes'].get('crosswalk',0)} | {r['visual_check']} | {r['uncertain']} |\n"
report+='''
## 628과 비교한 판단

지난 628의 9장은 POLYGONS 영역 라벨 총 11개였고, 눈에 띄는 다른 차선은 JSON에 없었다. 이번 197의 5장은 여러 좌우 차선과 주변 경계가 함께 라벨링되어 있어, 주요 차로 경계를 배우는 후보로는 628보다 더 적합해 보인다. 이 비교는 서로 다른 장면과 표본 수에 대한 육안 점검이며 전체 데이터셋의 완전성을 증명하지 않는다.

197을 레드박스의 '차선 경로/차로 경계' 학습 후보로 우선 검토하는 것을 권한다. 다만 점선 빈 간격이나 차량 가림을 연결하는 polyline이 있으므로, 라벨을 그대로 칠해 '보이는 페인트 픽셀'의 정답으로 간주해서는 안 된다. 628 폴리곤과 197 폴리라인은 같은 형태의 정답이 아니어서 단순 합치기도 피해야 한다. 중심선/경계 경로를 목표로 할지, 도색 영역 분할을 목표로 할지 정한 뒤 변환 방식을 결정해야 한다. 이번 범위에서는 학습용 변환·학습·원본 변경은 하지 않았다. 사용 가능 범위는 제공된 daylight 묶음의 표본 확인까지며 야간 등 다른 조건의 품질은 확인하지 않았다.

## 코드와 결과

프로젝트 022_preview_lane_label_197.py: JPG와 JSON 경로를 인수로 받아 data의 좌표를 OpenCV 선으로 그린다. 좌표 읽기·polyline과 polygon의 차이·크기 기준을 쉬운 한국어 주석으로 설명했다.

결과: 2215110_preview.jpg, 2215332_preview.jpg, 6677338_preview.jpg, 6722342_preview.jpg, 6750398_preview.jpg.
원본/결과 비교: 같은 번호의 _compare.jpg.
전체 짝 목록: pairs.json. 선택 경로와 판정: selected_pairs.json, sample_check.csv. 구조·클래스 집계: inventory.json.

실행 예:
```powershell
python 022_preview_lane_label_197.py "C:\\Users\\mbc\\Desktop\\RedBox데이터셋\\dataSetSn_197 (차선_횡단보도인지(수도권))\\원천데이터\\1900_1200\\daylight\\2215110.jpg" "C:\\Users\\mbc\\Desktop\\RedBox데이터셋\\dataSetSn_197 (차선_횡단보도인지(수도권))\\라벨링데이터\\1900_1200\\daylight\\2215110.json"
```
'''
(out/'점검결과_197.md').write_text(report,encoding='utf-8');print('보고서·샘플 판정 CSV 저장 완료')
