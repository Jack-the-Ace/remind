class ApiError extends Error {
  constructor(code, method, path, status) {
    super(code)
    this.request = method + ' /api/' + path
    this.status = status
  }
}

export async function api(path, method = 'GET', data) {
  let r
  try {
    r = await fetch('/api/' + path, {
      method, credentials: 'same-origin', cache: 'no-store',
      headers: data ? { 'Content-Type': 'application/json' } : {},
      body: data ? JSON.stringify(data) : undefined,
    })
  } catch { throw new ApiError('OFFLINE', method, path, null) }
  if (!r.ok) {
    const body = await r.json().catch(() => ({}))
    if (r.status === 401 && path !== 'login' && !(path==='me' && method==='GET')) window.dispatchEvent(new Event('pnj-expired'))
    const code = typeof body.detail === 'string' ? body.detail : body.detail?.code
    throw new ApiError(Object.hasOwn(errors, code) ? code : 'HTTP_' + r.status, method, path, r.status)
  }
  try { return await r.json() }
  catch { throw new ApiError('INVALID_RESPONSE', method, path, r.status) }
}
const errors = {
  OFFLINE:['앱 서버에서 응답을 받지 못했습니다. start.bat을 실행한 뒤 이 탭에서 다시 시도해주세요.','No response from the app server. Run start.bat and retry in this tab.'],
  HTTP_502:['앱 서버가 백엔드에서 정상 응답을 받지 못했습니다. start.bat을 실행하고 .runtime/frontend.error.log를 확인해주세요.','The app could not get a valid backend response. Run start.bat and check .runtime/frontend.error.log.'],
  INVALID_RESPONSE:['API가 JSON 대신 다른 형식으로 응답했습니다. start.bat이 연 주소와 프록시 설정을 확인해주세요.','The API returned an unexpected format. Check the URL opened by start.bat and the proxy configuration.'],
  INVALID_CHOICE:['선택지 범위를 벗어난 답이 있습니다. 해당 문항의 답을 다시 선택해주세요.','An answer is outside its question’s choices. Select that answer again.'],
  INVALID_INPUT:['입력 형식과 길이를 확인해주세요.','Check the format and length of your entries.'],
  ID_TAKEN:['이미 사용 중인 아이디입니다. 아이디를 바꿔 다시 가입해주세요.','That ID is taken. Choose another and retry.'],
  INVALID_LOGIN:['아이디와 비밀번호를 확인해주세요.','Check your ID and password.'],
  LOGIN_REQUIRED:['세션이 만료되었습니다. 다시 로그인해주세요.','Your session expired. Please sign in again.'],
  NEW_MOOD:['오늘의 기분을 다시 입력해주세요.','Please enter today’s mood again.'],
  SURVEY_INCOMPLETE:['현재 버전의 모든 문항에 답해주세요.','Answer all questions in the current survey.'],
  AI_ERROR:['AI 연결 또는 응답 오류입니다. 다시 시도하거나 데모를 선택해주세요.','AI request failed. Retry or choose Demo.'],
  AI_LIMIT:['OpenAI가 원인을 특정하지 않은 429를 반환했습니다. 잠시 후 재시도하거나 Demo Mode를 선택해주세요.','OpenAI returned an unspecified 429. Try later or select Demo Mode.'],
  AI_QUOTA:['OpenAI API 사용 가능 할당량이 부족합니다. 연결된 조직의 Billing 잔액과 Limits를 확인하거나 Demo Mode를 선택해주세요.','OpenAI API quota is unavailable. Check the organization’s billing balance and usage limits, or select Demo Mode.'],
  AI_CREDITS:['연결된 OpenAI 조직의 API 크레딧 잔액이 소진됐습니다. Billing에서 잔액을 충전한 뒤 다시 시도하거나 Demo Mode를 선택해주세요.','The connected OpenAI organization has no API credits remaining. Add credits in Billing and retry, or select Demo Mode.'],
  AI_SPEND:['OpenAI API 지출 한도에 도달했습니다. 조직의 사용 한도를 확인하거나 Demo Mode를 선택해주세요.','The API spending limit was reached. Check organization limits or select Demo Mode.'],
  AI_TOKENS:['토큰 처리량 한도에 도달했습니다. 잠시 후 다시 시도해주세요.','Token throughput limit reached. Please retry later.'],
  AI_REQUESTS:['요청 빈도 한도에 도달했습니다. 잠시 후 다시 시도해주세요.','Request frequency limit reached. Please retry later.'],
  AI_RATE:['일시적인 API 호출 한도입니다. 잠시 후 다시 시도해주세요.','Temporary API rate limit. Please retry later.'],
  AI_ACCESS:['지정한 OpenAI 모델과 접근 권한을 확인해주세요.','Check the configured OpenAI model and access permissions.'],
  AI_SCHEMA:['OpenAI가 요청한 JSON 응답 형식을 거절했습니다.','OpenAI rejected the requested JSON response schema.'],
  AI_KEY:['서버의 OpenAI 키 설정을 확인하거나 Demo Mode를 선택해주세요.','Check the OpenAI key on the server or choose Demo Mode.'],
}
export function errorText(error,lang) {
  const code = typeof error === 'string' ? error : error.message
  const i = lang === 'en' ? 1 : 0
  const message = errors[code]?.[i] ?? [
    '요청이 실패했습니다. .runtime/backend.log 및 backend.error.log를 확인해주세요.',
    'Request failed. Check .runtime/backend.log and backend.error.log.',
  ][i]
  if (error instanceof ApiError) {
    const status = error.status ? 'HTTP ' + error.status : ['HTTP 응답 없음','no HTTP response'][i]
    return message + ' (' + error.request + ', ' + status + ')'
  }
  return code.startsWith('HTTP_') ? message + ' (HTTP ' + code.slice(5) + ')' : message
}
const labels = {
  solo:['혼자만의 시간','Solo time'], social:['함께하는 활동','Shared activities'], rest:['느긋한 휴식','Rest'], active:['활동적인 여행','Activity'],
  familiar:['익숙한 분위기','Familiar places'],new:['새로운 경험','Discovery'],nature:['자연','Nature'],city:['도시','City'],culture:['문화','Culture'],
  flex:['자유시간','Flexibility'],planned:['계획적인 순서','Structure'],
}
export const traitText = (traits,lang) => Object.values(traits || {}).map(tags=>tags.map(tag=>labels[tag]?.[lang==='en'?1:0] || tag).join(' / ')).join(' · ')
