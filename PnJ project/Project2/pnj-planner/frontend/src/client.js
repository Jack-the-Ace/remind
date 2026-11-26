export const PREFIX = 'pnj-planner.v1.'
export const tr = lang => (en, ko) => lang === 'ko' ? ko : en

export async function api(path, method='GET', body) {
  let response
  try {
    response = await fetch('/api'+path, {
      method, credentials:'same-origin', headers:body ? {'Content-Type':'application/json'} : {},
      body:body ? JSON.stringify(body) : undefined
    })
  } catch {
    const error = new Error('NETWORK')
    error.status = 0
    throw error
  }
  const data = await response.json().catch(()=>({}))
  if (!response.ok) {
    const detail = data.detail
    const error = new Error(typeof detail === 'string' ? detail : Array.isArray(detail) ? detail.map(e=>e.loc.slice(1).join('.')+' '+e.msg).join(', ') : 'HTTP '+response.status)
    error.status=response.status
    error.fields=data.fields||[]
    if (response.status === 401 && !['/me','/login'].includes(path)) window.dispatchEvent(new Event('planner-session-expired'))
    throw error
  }
  return data
}

export function readDraft() {
  try {return JSON.parse(sessionStorage.getItem(PREFIX+'signup')) || {}} catch {return {}}
}
export function saveDraft(draft) {
  try {sessionStorage.setItem(PREFIX+'signup', JSON.stringify(draft))} catch { /* In-memory form stays available. */ }
}
export function clearDraft() {try {sessionStorage.removeItem(PREFIX+'signup')} catch {}}

export function errorText(error, t) {
  if (!error) return ''
  const known = {
    NETWORK:t('Could not reach the planner. Check that start.bat is running and try again.','플래너에 연결할 수 없어요. start.bat 실행 상태를 확인하고 다시 시도해 주세요.'),
    401:t('Check your sign-in details.','아이디와 비밀번호를 확인해 주세요.'),
    USERNAME_TAKEN:t('This username is taken. Change the username and submit again. Your answers are saved.','이미 사용 중인 아이디예요. 아이디만 바꾸고 다시 가입해 주세요. 검사 응답은 유지돼요.'),
    INVALID_FIELDS:t('Check the highlighted field names and try again.','다음 항목의 입력값을 확인해 주세요.')+' '+(error.fields||[]).join(', '),
    SURVEY_VERSION:t('Reload the questionnaire to use the current version.','검사 버전이 변경됐어요. 새로고침해 현재 문항을 확인해 주세요.'),
    SURVEY_INCOMPLETE:t('Please answer every question.','모든 문항에 응답해 주세요.'),
    EMPTY_MOOD:t('Choose a response or skip the check-in.','답을 선택하거나 기분 입력을 생략해 주세요.'),
    NO_PREVIOUS_MOOD:t('There are no previous answers to reuse.','재사용할 이전 답변이 없어요.'),
    PLAN_NOT_FOUND:t('This plan could not be found for your account.','이 계정에 저장된 계획을 찾을 수 없어요.')
  }
  return known[error.message] || known[error.status] || (t('Request failed','요청을 처리하지 못했어요')+' ('+(error.status||'—')+') · '+error.message)
}
export const axisNames = {
  novelty:['New experiences','새로운 경험'], social:['Social activities','다른 사람과의 교류'], structure:['Structured plans','구체적인 계획'],
  activity:['An active day','활동적인 하루'],crowds:['Comfort with crowds','혼잡한 환경 허용'], learning:['Culture and learning','문화와 배움'],
  food:['Trying new food','새로운 음식 시도'],trend:['Current trends','트렌드 관심'],timeOfDay:['Later hours','늦은 시간대'],pace:['A leisurely pace','여유 있는 진행']
}
export const scoreNames = {extraversion:['Extraversion','외향성'],agreeableness:['Agreeableness','우호성'],conscientiousness:['Conscientiousness','성실성'],neuroticism:['Neuroticism','신경성'],imagination:['Intellect / imagination','지성·상상력']}
export const tags = {
  club:['Clubbing','클럽에서 놀기'], dance:['Dancing','직접 춤추기'], music:['Music','음악'], nightlife:['Nightlife','밤 문화'],
  bookclub:['Book groups','독서 모임'], fanclub:['Fan clubs','팬 모임'],
  solo:['Independent time','혼자 보내는 시간'],
  nature:['Nature','자연'],rest:['Rest','휴식'],quiet:['Quiet settings','차분한 분위기'],art:['Art','미술'],culture:['Culture','문화'],
  history:['History','역사'],shopping:['Shopping','쇼핑'],kpop:['K-pop','K-팝'],food:['Food','음식'],night:['Night views','야경'],
  photo:['Photography','사진'],market:['Markets','시장'],walk:['Walking','걷기'],active:['Active experiences','활동적인 체험'],
  social:['Social activities','교류'],busy:['Bustling places','북적이는 곳'],new:['Something new','새로운 경험'],indoor:['Indoors','실내'],outdoor:['Outdoors','야외']
}
