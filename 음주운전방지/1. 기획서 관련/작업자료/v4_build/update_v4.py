import pathlib,zipfile,re,html,hashlib,xml.etree.ElementTree as E,json
B=pathlib.Path(__file__).resolve().parent
ROOT=B.parents[1]
src=ROOT/'산출물/AI_위험주행_차량추적_11월_기획서_초안_v3.pptx'
dst=src.with_name(src.name.replace('_v3.pptx','_v4.pptx'))
before=hashlib.sha256(src.read_bytes()).hexdigest()
replacements={
1:{'ROAD':'레드박스','WATCH':'(RedBox)','컴퓨터 비전 AI 서비스 기획':'컴퓨터 비전 AI 서비스 기획 · 과제용 가칭'},
6:{'추적 중':'선택 차량 추적','추가 검토':'이벤트 검토','신고 검토':'신고 검토','법적 위반 확정 아님':'기준 충족 시 신고 검토'},
7:{'차량 검출부터 이벤트 분석까지':'차량 추적과 차선 기반 이벤트 분석','차량 검출':'차량 검출 후보','차선 Segmentation':'차선 위치 인식','OpenCV + 시간 규칙':'차로·경계·시간 집계','수업 코드 재활용 · 차선 모델은 실제 파인튜닝':'11월: 차선 위치 학습 우선 · 종류 구분은 검증 후 확장'},
8:{'차선 데이터를 라벨링하고, 실제로 학습합니다':'차선 위치 학습 우선, 종류 구분은 검증 후 확장','미확보 시 300장':'대안 300장 목표','2클래스 차선':'차선 / 배경 이진','[흰색·노란색 실선·점선의':'[차선 색·종류 속성을 보존한'},
9:{'11월 실행 범위: 한 PC의 로컬 웹':'업로드 · 실행·진행 확인 · 추적·분석 · 결과 검토 · 저장','입력·차량 선택':'업로드·차량 선택','분석 작업 관리':'실행·진행 상태','클립·JSON/CSV':'결과 확인·저장'},
10:{'자동 이벤트 1종 + 3색·횟수':'자동 이벤트 1종·중복 방지'},
11:{'2026년 11월 · 주 개발 1명 / 팀원 1명 검토·시연 지원':'2026년 11월 · 1인 개발 / OLIGO-K 전 팀장: 자문·시연 지원','기획·환경':'기획·코딩 착수','11.16 제출':'PDF·Context 제출','라벨 확보':'추적 기반 구현','데이터 미확보 시, 허가 영상 300장 대안으로 전환':'데이터 지연 시 허가 영상 300장 대안 검토'},
14:{'불법주차 등 독립 탐지':'불법주차·투기 등 검토'}
}
common_note='레드박스(RedBox)는 과제용 가칭이며 정식 상표가 확정된 것은 아니다.'
events='''상태 기준: 초록은 사람이 선택한 차량을 추적 중인 상태다. 주황은 위험 의심 이벤트가 발생해 추가 검토가 필요한 상태다. 빨강은 검증된 반복 위험 의심 패턴이 기준을 충족했을 때의 신고 검토 단계다. 현재 반복 패턴과 임계값은 검증 전이므로, 검증 전 결과를 검증 완료 상태나 법적 위반 확정으로 표시하지 않는다. 회색은 추적 상실·차선 불명확 등 판단 보류 상태다. 색상과 상태 문구를 함께 표시한다.
경계 교차 0.5초, 6초 내 교대 접근 3회, 안정 복귀 2초는 모두 검증 전 초기 가설이다. validation에서 조정하고 독립 test 전에 고정한다. 정상 차선 변경을 위반으로 단정하지 않는다. 이벤트는 조건 진입부터 종료까지 한 구간으로 묶어 한 번 집계하고, 프레임마다 재집계하지 않는다. 안정 복귀 조건을 충족하기 전에는 같은 이벤트를 새 건으로 세지 않는다. 추적 상실·대상 재선택 시 집계 상태를 초기화하고 판단 보류 구간은 근거 없이 이어 붙이지 않는다.
방향지시등 없이 차량너비의 1.5배 이상 좌우 이동하는 패턴은 향후 실험 아이디어로만 보존한다. 방향지시등 관측 가능성·원근·자차 운동·차량너비 추정부터 검증해야 하며, 현재 확정 알고리즘이나 11월 필수 기능에 포함하지 않는다.'''
notes={
1:common_note,
3:'개발은 본인 혼자 수행한다. 이전 OLIGO-K 프로젝트 팀장은 아이디어 자문과 최종 시연 지원 역할이며 공동 개발자가 아니다.',
6:events,
7:'''11월 우선순위는 차선 위치 인식 모델을 실제 학습하고 선택 차량 추적과 연결하는 것이다. 차선/배경 이진 Segmentation의 출력만으로 흰색·노란색 및 실선·점선을 모두 구별할 수 없다. 색·종류는 원본 라벨 속성을 보존하되, 별도 속성 모델 또는 후처리의 검증 가능한 범위에서만 확장한다.
분석 순서: 차선 검출 → 같은 진행 방향 경계를 대응시켜 대상 차량이 속한 차로 추정 → 대상 박스 하단 중심과 차선 경계의 교차 분석 → 원본 영상 시각 기준 지속시간·횟수 집계. 박스 하단 중심은 접지점의 근사이며 가림·원근·자차 움직임 때문에 오차가 생긴다. 경계 대응이나 차로 추정 신뢰도가 부족하면 분석을 보류한다.
차선이 불분명할 때 마지막 차선 위치와 주변 차량 배열은 보조 정보로만 사용하며 현재 차선의 확정 근거로 대체하지 않는다. 신뢰도가 부족하면 HOLD/LOST와 사유를 표시하고 사람의 재검토·재선택을 기다린다.
YOLO Nano·ByteTrack·DeepLabV3-MobileNetV3는 구현 후보와 계획이다. 모델 파일·가중치 접근·라이선스·라이브러리 호환성·실제 샘플 추론이 확인되기 전에는 사용 가능 또는 학습 완료로 단정하지 않는다.
'''+events,
8:'''차선/배경 이진 모델은 차선 위치를 학습하는 모델이며 차선 색과 실선·점선 종류를 직접 분류하는 모델이 아니다. 사진 영역의 색·종류 표시는 라벨 속성 보존 예시이며 모델의 속성 분류 성과를 뜻하지 않는다.
착수 전 데이터 승인·실제 다운로드·라벨 파일 정합성·사용 조건과 후보 모델 가중치·호환성을 확인한다. AI Hub 197·196, BDD100K, KITTI Tracking, CULane은 후보이며 이번 보완 작업에서 실제 확보나 사용 가능 여부를 새로 검증한 것은 아니다. 각 데이터의 task·라벨·사용 범위가 다르므로 차선 학습과 추적 평가를 구분한다.
승인·다운로드 지연 시 권리가 확인된 소규모 샘플로 라벨 변환, 학습 1회 실행, 가중치 저장·재추론 경로부터 점검한다. 이후 조건이 맞는 대체 공개 차선 subset 또는 허가 영상 직접 라벨링으로 전환한다. 기존 300장 fallback은 확보 완료 수량이 아닌 목표다. 표본 부족을 공개하고 일반화 성능을 과장하지 않되 실제 학습 자체는 11월에 수행한다. 환경·데이터 점검은 11월 15~16일 첫 코딩 착수 전에 가능한 범위에서 병행한다.''',
9:'''실제 사용자 흐름: React에서 영상 업로드·정지 화면 차량 선택 → FastAPI로 분석 실행 및 진행 상태·실패 사유 확인 → Python worker에서 YOLO/ByteTrack 추적·차선 모델/OpenCV 이벤트 분석 → React에서 시각별 결과와 근거 검토·오탐 제외 → 클립·JSON/CSV·SQLite 기록 저장. 결과 확인과 저장 요청은 React UI에서 수행하고 실제 저장 처리는 백엔드가 담당한다. 기존 구조와 11월 한 PC 로컬 실행 범위를 유지한다.''',
10:events+'''
필수 일정: 11월 16일 기획서 PDF 및 개발 Context .md 제출. 11월 30일 딥러닝 학습과 컴퓨터 비전을 실제 활용한 작동 가능한 콘텐츠 완성. 12월 22일 기능 고도화 및 2PC 모의 관제 연동 시연. 11월 필수 우선순위는 차량 추적·차선 모델 실제 학습·위험 의심 이벤트 분석이며 12월로 미루지 않는다. 이번 작업에서 PDF를 생성한다는 뜻은 아니다.''',
11:'''개발자는 본인 1명이다. 이전 OLIGO-K 프로젝트 팀장은 아이디어 자문과 최종 시연만 지원하며 공동 개발자가 아니다.
일정 보정: 11월 15~16일 전후 첫 코드 작성을 시작할 계획이다. 그전에 기획 정리와 함께 데이터 승인 신청·허가 샘플 확보·환경/GPU·후보 모델 가중치 접근 및 호환성 확인을 가능한 범위에서 병행한다. 첫 코딩에서는 작은 입력·추론 경로부터 확인하고 11월 17~20일 선택·지속 추적 기반을 구현한다. 실제 가용시간과 환경은 아직 확인이 필요하다.
11월 16일 기획서 PDF 및 개발 Context .md 제출, 11월 30일 실제 학습·차량 추적·차선 분석·위험 의심 이벤트가 작동하는 콘텐츠 완성, 12월 22일 고도화 및 2PC 모의 관제 연동 시연 일정을 유지한다. 데이터 대안 결정은 11월 18일까지 기다리지 않고 착수 전부터 병행하며 미확보 시 허가 영상 기반 300장 목표나 조건이 맞는 공개 subset을 검토한다.''',
12:'2PC 모의 관제는 12월 22일 고도화·연동 시연 목표다. 11월의 한 PC 차량 추적·차선 학습·이벤트 분석과 구분한다. 실제 경찰 또는 공공 CCTV 접근 권한이나 협약이 확보된 것으로 표현하지 않는다.',
13:'모바일·음성 신고 등은 장기 비전이며 11월 PC 사후 분석의 구현 완료 기능이 아니다. 차선 또는 추적 근거가 부족하면 자동 판단과 집계를 보류하고 사람이 검토한다.',
14:common_note+' 모바일 앱·음성 신고·불법주차·투기 등 추가 신고 기능과 경찰청 협력은 장기 구상이다. 11월 실제 구현 범위와 구분하며 경찰청과 현재 확정된 협약은 없다.'
}
rx=re.compile(r'(<a:t\b[^>]*>)(.*?)(</a:t>)',re.S)
changed=[]
with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst,'x',compression=zipfile.ZIP_DEFLATED) as zout:
 for info in zin.infolist():
  data=zin.read(info.filename); m=re.fullmatch(r'ppt/(slides/slide|notesSlides/notesSlide)(\d+)\.xml',info.filename)
  if m:
   num=int(m[2]);is_note=m[1].startswith('notes');original=data.decode('utf8');first=[True]
   def edit(match):
    t=html.unescape(match[2]);t=t.replace('ROAD WATCH','레드박스(RedBox)')
    if is_note:
     t=t.replace('일부를 팀원이 교차 검토한다.','개발자가 라벨 일부를 재검토한다.')
     t=t.replace('팀원은 아이디어 검토 및 정답 일부 교차 검토를 지원할 수 있으나 프로그램 개발은 본인이 맡는다.','이전 OLIGO-K 프로젝트 팀장은 아이디어 자문과 최종 시연을 지원하며 개발은 본인이 혼자 맡는다.')
     t=t.replace('팀원 1명','자문·시연 지원자 1명')
     t=t.replace('11/12~16은 기획·데이터 접근 확인이며 이번 요청에서 개발 코드는 작성하지 않는다.','11/12~16 기획·데이터·환경 점검과 병행해 11/15~16 전후 첫 코딩을 시작할 계획이다.')
     if num==11:t=t.replace('11/17~30 55h 개발+10h 버퍼는 가용시간 가정이다.','기존 약 55h 개발+10h 버퍼는 가용시간 가정이며 코딩 착수일 보정에 맞춰 조정한다.')
     if first[0] and num in notes:t=notes[num]+'\n\n'+t
    else:t=replacements.get(num,{}).get(t,t)
    first[0]=False
    return match[1]+html.escape(t,quote=False)+match[3]
   new=rx.sub(edit,original);data=new.encode('utf8')
   if data!=zin.read(info.filename):changed.append(info.filename)
   assert rx.sub('<TEXT>',original)==rx.sub('<TEXT>',new),'Non-text XML changed'
  zout.writestr(info,data)
# Only package/text checks. No rendering, image export, PDF or GUI.
ns={'a':'http://schemas.openxmlformats.org/drawingml/2006/main','p':'http://schemas.openxmlformats.org/presentationml/2006/main'}
with zipfile.ZipFile(src) as a,zipfile.ZipFile(dst) as z:
 assert z.testzip() is None
 assert a.namelist()==z.namelist()
 assert sum(bool(re.fullmatch(r'ppt/slides/slide\d+\.xml',n)) for n in z.namelist())==14
 assert sum(bool(re.fullmatch(r'ppt/notesSlides/notesSlide\d+\.xml',n)) for n in z.namelist())==14
 ph=0
 for n in z.namelist():
  if n.endswith('.xml'):E.fromstring(z.read(n))
  if re.fullmatch(r'ppt/slides/slide\d+\.xml',n):
   r=E.fromstring(z.read(n));ph+=sum(q.get('name','').startswith('PHOTO_') and not q.get('name','').startswith('PHOTO_LABEL_') for q in r.findall('.//p:cNvPr',ns))
  if n not in changed:assert a.read(n)==z.read(n)
  if re.fullmatch(r'ppt/(slides/slide|notesSlides/notesSlide)\d+\.xml',n):
   assert 'ROAD WATCH' not in z.read(n).decode('utf8')
 assert ph==8
assert hashlib.sha256(src.read_bytes()).hexdigest()==before
print(json.dumps({'saved':str(dst),'slides':14,'notes':14,'image_regions':8,'source_unchanged':True,'non_text_xml_unchanged':True,'bytes':dst.stat().st_size},ensure_ascii=True,indent=2))
