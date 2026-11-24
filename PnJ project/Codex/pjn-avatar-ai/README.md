# PnJ 개인화 AI 아바타 검증 앱

개인 성향, 현재 기분, 과거 추천 이력을 한 요청에 담아 실제 LLM이 여행 방향을 제안하는 로컬 검증용 앱입니다. DB나 로그인 없이 브라우저 LocalStorage를 사용합니다.

## 빠른 실행

1. `backend/.env.example`를 `backend/.env`로 복사하고 `OPENAI_API_KEY`를 입력합니다. 키는 브라우저나 Git에 넣지 않습니다.
2. PowerShell 창 1:
   ```powershell
   cd backend
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   uvicorn app.main:app --reload --port 8000
   ```
3. PowerShell 창 2:
   ```powershell
   cd frontend
   npm install
   npm run dev
   ```
4. 출력되는 Vite 주소(통상 `http://localhost:5173`)를 엽니다.

## 구성

- `backend/`: FastAPI + OpenAI API. `/api/recommendations`는 실제 LLM 호출만 수행하며, 키/모델/API 오류 시 응답을 꾸며내지 않고 오류를 돌려줍니다.
- `frontend/`: React/Vite 단일 페이지. 세 명의 가상 프로필을 시작값으로 제공하고 수정본·추천 이력을 LocalStorage에 저장합니다.
- `backend/tests/`: 프롬프트 안전 규칙과 API 오류 응답의 최소 단위 테스트입니다.

## 연동 계약

`POST /api/recommendations`의 요청에는 `profile`, `mood`, `language`를 넣고, 응답의 `recommendation` 객체를 경로 탐색 시스템에 그대로 넘길 수 있습니다. 특히 `recommendedDestinations`, `preferredActivities`, `avoidConditions`는 목적지/조건 레이어로 분리되어 있습니다.

## 제한

지도·경로·교통·예산·GPS·음성·아바타 변경·회원가입은 의도적으로 포함하지 않았습니다. 심리 결과는 검증된 진단이 아닌 테스트용 가상 페르소나 데이터입니다.
