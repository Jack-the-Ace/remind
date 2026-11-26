# PnJ Seoul Planner

가입할 때 저장한 성향과 오늘의 마음 한마디로 서울 경험 세 가지를 제안하는 한영 로컬 웹앱입니다. 회원가입부터 미아 인계용 JSON 다운로드까지 인터넷 연결이나 API 키 없이 시연할 수 있습니다.

## Windows에서 시작하기

이 폴더는 `Project2\pnj-planner`입니다. 설치가 끝난 PC에서는 **start.bat**을 더블클릭하고 [플래너 열기](http://127.0.0.1:5186/)로 접속하세요. **stop.bat**으로 종료합니다.

새 PC의 첫 설치에는 Python 3.11 이상, Node.js 22.12 이상과 npm, 패키지 설치용 인터넷 연결이 필요합니다. 이 폴더를 PowerShell로 열고 다음 명령을 실행하세요.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
npm.cmd --prefix frontend ci
.\start.bat
```

실행기는 새 프런트엔드를 빌드하고 FastAPI가 화면·사진·API를 같은 로컬 주소에서 제공합니다. 앱과 현재 검사 정의가 응답하면 브라우저를 엽니다. 같은 서버가 실행 중이면 해당 창을 다시 엽니다. 포트를 다른 프로그램이 사용 중이면 그 사실을 표시합니다. 실패 시 배치 창과 `.runtime/build.error.log`, `.runtime/server.error.log`를 확인하세요. 실행 기록은 `.runtime/server.json`에 있습니다.

계정 DB 기본 위치는 `.runtime/planner.sqlite3`입니다. 배치의 설정은 프로세스 환경변수로 전달합니다. `.env.example`에는 예시만 있습니다. 이 앱은 기존 PnJ의 설정 파일을 읽지 않습니다.

## 시연 순서

1. **회원가입**에서 필수 PnJ 성향 검사 24문항을 완료하고 가입을 확정한 뒤 직접 로그인합니다. MBTI와 기본정보는 선택 사항입니다. 탭을 새로고침하면 응답과 문항 위치가 복원되며 비밀번호만 다시 입력합니다.
2. **오늘은 어떤 마음인가요?**에 “오늘 너무 지쳤어. 그냥 편하게 쉬고 싶어.”를 쓰고 **지금 마음으로 추천받기**를 누릅니다. 칩·여행 날짜·기간·예산은 모두 비워도 됩니다. **기분 없이 추천받기**와 **지난 답과 같아요**도 바로 결과로 이어집니다.
3. 공감 문장 아래 경험 카드를 비교합니다. 주요 장소와 느슨한 순서를 보고 코스를 열면 **P → PnJ → J**를 자유롭게 바꿀 수 있습니다. **기분 해석 수정**에서 데모가 읽은 활동을 바꾸거나 **조건 더 맞추기**에서 숙소·예산·약속 등을 추가할 수 있습니다.
4. 부분 일정은 조건 화면의 **확정 일정 및 약속 → 5일 예시 사용**에서 확인합니다. 직접 입력한 약속을 보존한 채 빈 날을 채웁니다.
5. **이 계획을 미아 인계용으로 선택**을 누르면 JSON을 확인하고 내려받을 수 있습니다. 원하는 경우 선택 이유를 함께 남깁니다. 실제 방문과 만족도는 직접 기록합니다.

기간 미정이면 날짜가 배정되지 않은 간략 코스를 제안합니다. 예산을 입력하면 확인된 기본 관람료와 미확인 전체 비용을 구분합니다. 이동 시간이나 총비용 확인이 더 필요한 경험에는 안내가 붙습니다. 명시한 회피 장소, 실내 필수 조건과 충돌하거나 알려진 비용만으로 상한을 넘는 후보는 제외됩니다.

기존 Mini-IPIP 회원도 곧바로 추천을 받을 수 있습니다. 새 검사로 갱신하려면 **마이페이지 → PnJ 검사 다시 하기**를 사용하세요. 서버는 새 응답을 채점하고 기존 검사 기록을 별도로 보관합니다.

## 테스트

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-test.txt
Push-Location backend
..\.venv\Scripts\python.exe -m pytest -q
Pop-Location
node --test frontend/tests/tripDraft.test.js
```

실제 Chrome으로 전체 흐름을 다시 검사하려면 새 플래너를 종료한 뒤 전용 QA DB를 지정하세요. 기존 PnJ의 실행기는 사용할 필요가 없습니다.

```powershell
.\stop.bat
$env:PNJ_PLANNER_DB = '.runtime/qa-browser.sqlite3'
$env:PNJ_PLANNER_NO_BROWSER = '1'
.\start.bat
.\.venv\Scripts\python.exe backend\tests\browser_flow.py --qa-db .runtime\qa-browser.sqlite3
.\stop.bat
Remove-Item Env:PNJ_PLANNER_DB, Env:PNJ_PLANNER_NO_BROWSER
.\start.bat
```

## 추천 근거 확인

서버는 검산된 2025년 서울관광 실태조사 집계로 개인 신호가 동률인 후보를 구분합니다. 사용자 입력은 기존과 같습니다. 공개 통계의 엑셀이나 API 키 없이 실행할 수 있습니다. 미아 인계 JSON에는 추천 당시의 검사 버전·점수와 현재 선택한 상세도가 담깁니다.

집계 재생성 명령과 원자료의 분모는 [데이터 출처](DATA_SOURCES.md)에, 특성별 적용 위치와 통제 비교 수치는 [추천 계산 근거](ALGORITHM_EVIDENCE.md)에 있습니다. 자동 검사는 위 pytest 명령에 포함됩니다. [설계](ARCHITECTURE.md) · [실행 검증 기록](IMPLEMENTATION_STATUS.md)
