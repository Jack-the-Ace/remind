import {useEffect,useState} from 'react'
import {api,errorText,traitText} from './client'
import {loadDraft,storeDraft,clearDraft} from './draft'
import {Scene} from './Avatar'
import {AvatarSelector} from './AvatarSelector'
import Survey from './Survey'

export function ProfileFields({data,change,t}){
  const types=['']
  for(const a of 'IE')for(const b of 'NS')for(const c of 'FT')for(const d of 'JP')types.push(a+b+c+d)
  return <>
    <label className="field">{t('닉네임','Nickname')}<input required maxLength={40} value={data.nickname} onChange={e=>change({nickname:e.target.value})}/></label>
    <label className="field">{t('MBTI (선택)','MBTI (optional)')}<select value={data.mbti} onChange={e=>change({mbti:e.target.value})}>{types.map(x=><option key={x} value={x}>{x||'—'}</option>)}</select></label>
    <label className="field">{t('피하고 싶은 조건 (선택)','Conditions to avoid (optional)')}<input maxLength={300} value={data.avoid} onChange={e=>change({avoid:e.target.value})}/></label>
  </>
}
export function Signup({definition,lang,onReturn}){
  const [d,setD]=useState(()=>loadDraft(definition.version))
  const [pw,setPw]=useState(''),[confirm,setConfirm]=useState('')
  const [err,setErr]=useState(''),[busy,setBusy]=useState(false)
  const t=(ko,en)=>lang==='ko'?ko:en
  function change(fields){setD(old=>({...old,...fields}))}
  useEffect(()=>{storeDraft(d)},[d])
  function leave(done){clearDraft();onReturn(done)}
  async function submit(e){
    e.preventDefault();setErr('')
    if(!d.nickname.trim()){setErr(t('닉네임을 입력해주세요.','Enter a nickname.'));return}
    if(pw!==confirm){setErr(t('비밀번호 확인이 일치하지 않습니다.','Passwords must match.'));return}
    if(!d.traits){change({screen:'intro'});return}
    setBusy(true)
    try {await api('signup','POST',{id:d.id,password:pw,nickname:d.nickname,mbti:d.mbti,avoid:d.avoid,avatarId:d.avatarId,survey:{version:d.version,answers:d.answers}});leave(true)}
    catch(e){setErr(errorText(e.message,lang))}finally{setBusy(false)}
  }
  if(d.screen==='intro'||d.screen==='done')return <Scene key={d.screen} avatarId={d.avatarId} finish={d.screen==='done'} lang={lang} onNext={()=>change({screen:d.screen==='intro'?'survey':'form'})}/>
  if(d.screen==='survey')return <Survey avatarId={d.avatarId} definition={definition} lang={lang} answers={d.answers} index={d.index} onIndex={index=>change({index})} onChange={answers=>change({answers,traits:null})} onDone={traits=>change({traits,screen:'done'})} onBack={()=>change({screen:'form'})}/>
  return <form className="panel" onSubmit={submit}><h2>{t('회원가입','Create an account')}</h2>
    <label className="field">{t('아이디 (영문 소문자·숫자·_·-, 3~32자)','ID (3–32 lowercase letters, digits, _ or -)')}<input autoComplete="username" required pattern="[a-z0-9_\x2d]{3,32}" value={d.id} onChange={e=>change({id:e.target.value})}/></label>
    <label className="field">{t('비밀번호 (8자 이상)','Password (8 or more characters)')}<input type="password" autoComplete="new-password" required minLength={8} maxLength={128} value={pw} onChange={e=>setPw(e.target.value)}/></label>
    <label className="field">{t('비밀번호 확인','Confirm password')}<input type="password" autoComplete="new-password" required value={confirm} onChange={e=>setConfirm(e.target.value)}/></label>
    <small>{t('새로고침하면 비밀번호만 다시 입력해주세요.','After refreshing, enter your password again.')}</small>
    <ProfileFields data={d} change={change} t={t}/>
    <AvatarSelector avatarId={d.avatarId} lang={lang} onChange={avatarId=>change({avatarId})} disabled={busy}/>
    {d.traits && <div className="notice"><b>{t('심리테스트 완료','Survey complete')}</b><p>{traitText(d.traits,lang)}</p><button type="button" disabled={busy} onClick={()=>change({screen:'intro',index:0,traits:null})}>{t('다시 검사','Retake survey')}</button></div>}
    {err && <p className="error" role="alert">{err}</p>}
    <button className="primary" disabled={busy}>{d.traits?t('회원가입 완료','Finish sign-up'):t('심리 테스트로 이동','Start survey')}</button>
    <button type="button" className="text-button" disabled={busy} onClick={()=>leave(false)}>{t('가입 취소','Cancel sign-up')}</button></form>
}
export function Login({lang,onLogin,onSignup,message}){
  const [err,setErr]=useState(''),[busy,setBusy]=useState(false)
  const t=(ko,en)=>lang==='ko'?ko:en
  async function submit(e){
    e.preventDefault();const data=Object.fromEntries(new FormData(e.currentTarget));setBusy(true)
    try{onLogin(await api('login','POST',data))}catch(e){setErr(errorText(e.message,lang))}finally{setBusy(false)}
  }
  return <form className="panel" onSubmit={submit}><h2>{t('로그인','Sign in')}</h2>{message && <p className="notice">{message}</p>}
    <label className="field">{t('아이디','ID')}<input required name="id" autoComplete="username"/></label>
    <label className="field">{t('비밀번호','Password')}<input required name="password" type="password" autoComplete="current-password"/></label>
    {err&&<p className="error" role="alert">{err}</p>}
    <button className="primary" disabled={busy}>{t('로그인','Sign in')}</button><button type="button" className="secondary" onClick={onSignup}>{t('회원가입','Create account')}</button></form>
}
