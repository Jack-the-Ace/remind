import Questionnaire from './Questionnaire'
import {useEffect,useState} from 'react'
import {api,clearDraft,readDraft,saveDraft,errorText} from './client'
import {Field,Alert,BusyLabel} from './shared'

export const profileFields={
  ageGroup:['Age group','연령대'],gender:['Gender','성별'],nationality:['Nationality','국적'],residenceCountry:['Country of residence','현재 거주국'],
  hometown:['Home city','고향 도시'],maritalStatus:['Marital status','혼인 여부'],language:['Language you use','사용 언어'],countriesVisited:['Countries visited (count)','방문 국가 수'],
  preferredCountry:['Favourite country to visit','선호하는 여행 국가'],seoulVisits:['Previous visits to Seoul','서울 방문 경험'],mbti:['MBTI','MBTI']
}
export function Login({onSuccess,onJoin,onHome,t,message}) {
  const [username,setName]=useState(''),[password,setPassword]=useState(''),[busy,loading]=useState(false),[error,fail]=useState(null)
  async function submit(e){e.preventDefault();if(busy)return;loading(true);fail(null)
    try {const me=await api('/login','POST',{username,password});onSuccess(me)} catch(e){fail(e)} finally {loading(false)}}
  return <section className="sheet compact"><button className="back" onClick={onHome}>← {t('Home','홈')}</button><h1>{t('Welcome back','다시 만나 반가워요')}</h1>
    {message&&<p className="notice" role="status">{message}</p>}
    <form onSubmit={submit}><Field label={t('Username','아이디')}><input autoComplete="username" required value={username} onChange={e=>setName(e.target.value)}/></Field>
    <Field label={t('Password','비밀번호')}><input type="password" autoComplete="current-password" required value={password} onChange={e=>setPassword(e.target.value)}/></Field>
    <Alert>{errorText(error,t)}</Alert><button className="primary" disabled={busy}><BusyLabel busy={busy} t={t}>{t('Sign in','로그인')}</BusyLabel></button></form>
    <button className="link" onClick={onJoin}>{t('Create an account','회원가입하기')}</button></section>
}

export function Signup({t,lang,onCancel,onComplete}) {
  const [draft,setDraft]=useState(readDraft),[password,pw]=useState(''),[confirm,pw2]=useState('')
  const [spec,setSpec]=useState(null),[error,fail]=useState(null),[hint,setHint]=useState(''),[busy,loading]=useState(false)
  const [retry,bump]=useState(0)
  const [screen,setScreen]=useState(()=>readDraft().screen==='survey'?'survey':'account')
  const username=draft.username||'',profile=draft.profile||{},answers=draft.answers||{}, idx=Math.max(0,Math.min(Number(draft.index)||0,(spec?.items.length||1)-1))
  const complete=spec&&draft.version===spec.version&&spec.items.every(q=>answers[q.id]>=1&&answers[q.id]<=5)&&draft.finished
  useEffect(()=>{let active=true;api('/survey').then(data=>{if(active){setSpec(data);setDraft(d=>d.version===data.version?d:{...d,answers:{},version:data.version,finished:false,index:0})}}).catch(e=>active&&fail(e));return()=>{active=false}},[retry])
  useEffect(()=>{saveDraft({...draft,screen})},[draft,screen])
  function patch(value){setDraft(d=>({...d,...value}));setHint('');fail(null)}
  function cancel(){clearDraft();onCancel()}
  async function submit(e){
    e.preventDefault();if(busy||!spec)return
    if(password!==confirm){setHint(t('The passwords differ. Please re-enter them.','비밀번호가 일치하지 않아요. 다시 입력해 주세요.'));return}
    if(!complete){setScreen('survey');return}
    loading(true);fail(null)
    try{await api('/signup','POST',{username,password,profile:{...profile,countriesVisited:profile.countriesVisited===''||profile.countriesVisited==null?null:Number(profile.countriesVisited)},language:lang,version:spec.version,answers});clearDraft();onComplete()}
    catch(ex){fail(ex)}finally{loading(false)}
  }
  if(screen==='survey'&&spec)return <Questionnaire {...{spec,answers,lang,t}} index={idx}
    onBack={()=>setScreen('account')} onMove={index=>patch({index})}
    onAnswer={(id,value)=>patch({answers:{...answers,[id]:value},finished:false})}
    onFinish={()=>{patch({finished:true});setScreen('account')}}/>
  return <section className="sheet account"><button className="back" onClick={cancel}>← {t('Cancel sign-up','가입 취소')}</button><h1>{t('Create your account','계정 만들기')}</h1>
    <p className="lede">{t('Save your personality profile and build Seoul itineraries around your own preferences.','평소 성격과 직접 고른 선호를 저장하고 나에게 맞는 서울 코스를 만들어 보세요.')}</p>
    <form onSubmit={submit}><div className="form-grid"><Field wide label={t('Username','아이디')} hint={t('3–32 letters, numbers, underscores or hyphens.','글자·숫자·밑줄·하이픈을 사용해 3~32자로 입력해 주세요.')}><input required minLength={3} maxLength={32} autoComplete="username" value={username} onChange={e=>patch({username:e.target.value})}/></Field>
    <Field label={t('Password','비밀번호')} hint={t('At least 8 characters.','8자 이상 입력해 주세요.')}><input required minLength={8} maxLength={128} type="password" autoComplete="new-password" value={password} onChange={e=>pw(e.target.value)}/></Field>
    <Field label={t('Confirm password','비밀번호 확인')}><input required minLength={8} maxLength={128} type="password" autoComplete="new-password" value={confirm} onChange={e=>pw2(e.target.value)}/></Field></div>
    <details className="fold"><summary>{t('Optional background','선택 입력 · 기본정보')}</summary><p>{t('All fields are optional. Country of residence can help choose a visitor survey group when experiences otherwise match equally well.','모두 비워 둬도 돼요. 개인 취향에 비슷하게 맞는 경험이 여럿이면, 거주국을 기준으로 서울 방문객의 활동 기록을 참고할 수 있어요.')}</p>
      <div className="form-grid">{Object.entries(profileFields).map(([key,l])=><Field label={t(...l)} key={key}><input type={key==='countriesVisited'?'number':'text'} min="0" max={key==='countriesVisited'?300:undefined} pattern={key==='mbti'?'[EeIi][NnSs][FfTt][JjPp]':undefined} maxLength={key==='mbti'?4:100} value={profile[key]??''} onChange={e=>patch({profile:{...profile,[key]:e.target.value}})}/></Field>)}</div></details>
    <div className="panel-info"><strong>{complete?t('Questionnaire complete','성격검사 완료'):t('Your personality questionnaire','일반 성격검사')}</strong><p>{spec&&t(spec.items.length+' questions on '+Object.keys(spec.facets).length+' traits. ',Object.keys(spec.facets).length+'가지 특성을 살펴보는 '+spec.items.length+'문항이에요. ')}{t('PnJ uses a short selection of public IPIP items. You can edit your travel preferences later.','공개 IPIP 문항을 선별한 PnJ 단축 설문으로, 여행 선호는 나중에 자유롭게 수정할 수 있어요.')}</p>
    {spec&&Object.keys(answers).length>0&&<span>{Object.keys(answers).length} / {spec.items.length}</span>} {complete&&<button className="link" type="button" onClick={()=>{patch({index:0});setScreen('survey')}}>{t('Review answers','응답 검토')}</button>}</div>
    <p className="muted small">{t('Refreshing keeps your answers in this tab. Re-enter your password afterward.','새로고침해도 이 탭에서 응답은 유지돼요. 비밀번호만 다시 입력해 주세요.')}</p>
    <Alert>{hint||errorText(error,t)}</Alert>{!spec&&error&&<button type="button" onClick={()=>{fail(null);bump(n=>n+1)}}>{t('Reload questionnaire','문항 다시 불러오기')}</button>}
    <button className="primary" disabled={!spec||busy}><BusyLabel busy={busy} t={t}>{complete?t('Complete registration','회원가입 완료'):t('Start questionnaire','성격검사 시작하기')} →</BusyLabel></button></form></section>
}
