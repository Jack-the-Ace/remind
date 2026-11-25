# PnJ · 미호와 민, 나의 여행 동반자

React/Vite와 FastAPI로 실행하는 로컬 시연 앱입니다. 회원가입 때 답한 여행 성향과 오늘 대화에서 말한 기분·여행 희망을 바탕으로 세 가지 코스를 제안합니다.

## 팀원에게 임시 HTTPS 링크 공유하기

1. 프로젝트 루트의 **share_start.bat**을 더블클릭합니다. 전용 화면을 빌드한 뒤 앱, 설문 API, 외부 HTTPS 상태를 확인하고 링크를 표시합니다. 링크는 클립보드와 `.runtime/share/url.txt`에도 저장되며 기본 브라우저에서 열립니다.
2. 팀원에게 링크를 전달합니다. 링크를 아는 사람은 누구나 접속할 수 있습니다. 가상 아이디·닉네임과 시연 전용 비밀번호로 가입해 20문항부터 체험합니다.
3. 이 PC를 켜 두고 인터넷 연결을 유지하세요. 배치 창은 닫아도 됩니다. 공유 중 다시 실행하면 기존 링크를 표시합니다.
4. **share_stop.bat**을 더블클릭하면 공유 터널과 공유 서버만 종료됩니다. 계정과 추천 기록은 `.runtime/share/demo.sqlite3`에 남습니다. 재시작 후 새 주소를 전달하세요.

공유용 FastAPI가 화면과 API를 함께 제공합니다. 공유 서버는 127.0.0.1:18743에서 수신하고 cloudflared가 여기에 연결합니다. 공유기 포트 포워딩이나 Windows 방화벽 변경은 필요하지 않습니다. 외부 시연은 Demo Mode 전용입니다. 로컬 개발 환경은 기존 start.bat와 stop.bat로 관리합니다.

이 PC에서는 공식 Windows x64 실행 파일을 `.runtime/share/cloudflared.exe`에 설치했습니다. 다른 PC에서는 먼저 프로젝트 의존성을 설치하세요. 실행기는 PATH의 cloudflared를 우선 사용하며, 설치되지 않은 x64 PC에서는 공식 GitHub 릴리스의 SHA-256을 대조한 뒤 프로젝트 안에 설치합니다. 오류 원인은 배치 창과 `.runtime/share/`의 build.log, origin.error.log, tunnel.error.log에서 확인하세요. 포트 충돌 시 기존 프로세스를 유지하고 중단합니다. 임시 링크는 고정 주소나 가동시간을 보장하지 않습니다. [Cloudflare Quick Tunnel 안내](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/)

## Windows에서 실행하기

설치된 프로젝트에서는 이 폴더의 **start.bat**을 실행하세요. 기본 브라우저가 http://127.0.0.1:5173/ 을 열고, FastAPI 상태는 http://127.0.0.1:8000/api/health 에서 확인할 수 있습니다. 서버 종료는 **stop.bat**입니다. 다른 프로그램이 포트를 사용하면 기존 프로세스를 그대로 두고 오류를 표시합니다. 다른 포트로 열 때는 프로젝트 루트에서 `start.bat 8014 5175`를 실행하세요. 오류 로그는 `.runtime/backend.error.log`, `.runtime/frontend.error.log`에 있습니다.

의존성이 없는 PC에서는 Python과 Node.js/npm을 설치한 뒤 프로젝트 루트에서 다음을 실행하세요. 배치는 현재 폴더를 기준으로 경로를 계산합니다.

```powershell
python -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
npm --prefix frontend ci
.\start.bat
```

## 시연 순서

1. 회원가입에서 아이디·비밀번호·닉네임을 입력하고 미호 또는 민을 고른 뒤 **심리 테스트로 이동**을 선택합니다. 기본 동반자는 미호이며 MBTI와 회피 조건은 선택사항입니다.
2. 동반자의 인사를 클릭하거나 Enter로 넘기고 20문항에 답합니다. 검사 완료 후 **회원가입 계속**으로 돌아와 성향을 확인하고 **회원가입 완료**를 누릅니다.
3. 직접 로그인하고 Demo Mode에서 오늘의 기분을 보냅니다. 공감과 질문 뒤에 여행 희망을 입력합니다. 목적지나 날짜는 자유입니다.
4. 세 카드 중 하나를 선택하고 기본 P, 반반, 파워 J 사이를 전환합니다. 추천을 다시 확인하려면 이전 추천 기록을 엽니다. 마이페이지에서 기본정보 수정·재검사가 가능합니다.
5. 메인의 **여행 동반자 변경** 또는 마이페이지에서 새 동반자를 선택하면 계정에 바로 저장됩니다. 재로그인해도 선택이 유지됩니다.

## 저장 및 공급자

- 회원 계정·설문과 본인 추천 기록은 서버의 `backend/data/pnj.sqlite3`에 저장합니다. 비밀번호에는 계정별 솔트와 PBKDF2-HMAC-SHA256을 적용합니다. HttpOnly 세션의 수명은 8시간입니다. 가입 중 비밀번호만 메모리에 두므로 새로고침 후 다시 입력해야 합니다.
- 기본 Demo Mode는 API 키 없이 작동합니다. 자체 설문의 다섯 영역과 한국어·영어 표현을 이용해 여행 콘셉트의 순위를 매깁니다. 실제 시설의 접근성, 주차·예약 가능 여부는 방문 전에 확인해야 합니다.
- OpenAI를 선택하면 서버가 `backend/.env` 또는 서버 환경변수의 `OPENAI_API_KEY`, `OPENAI_MODEL`을 사용합니다. 기분 단계와 코스 단계는 각각 실제 호출입니다. 오류가 나면 현재 입력으로 재시도하거나 모드를 바꾼 뒤 요청하세요.
- 기존 브라우저 키 `pnj-avatar-lab-v1`의 가상 프로필·기록은 보존합니다. 소유 계정을 확인할 수 없어 신규 계정에 자동 가져오지 않습니다.
- 여행 코스 응답의 `courses[].id`, `name`, `stops`와 `avoid`를 다음 경로 모듈에 전달할 수 있습니다. 각 응답에 `mode`, `id`, `day`가 있으며 추천 기록은 방문 이력과 구분합니다.

검증 명령은 backend에서 `.\.venv\Scripts\python.exe -m pytest -q`, frontend에서 `npm run build`입니다. 실제 검증 결과와 다음 확인 지점은 `IMPLEMENTATION_STATUS.md`에 있습니다.
