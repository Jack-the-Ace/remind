import {useEffect,useState} from 'react'
import {api,errorText,traitText} from './client'
import {copy} from './copy'
import {Signup,Login} from './Auth'
import Profile from './Profile'
import Travel from './Travel'
import {Avatar} from './Avatar'
import {SavedAvatarSelector} from './AvatarSelector'
import {companionFor} from './avatarConfig'
import './journey.css'

export default function App(){
  const [lang,setLang]=useState(()=>localStorage.getItem('pnj-lang')==='en'?'en':'ko')
  const [user,setUser]=useState(null),[definition,setDefinition]=useState(null)
  const [page,setPage]=useState(()=>sessionStorage.getItem('pnj-signup-v1')?'signup':'login')
  const [message,setMessage]=useState(''),[error,setError]=useState(''),[ready,setReady]=useState(false)
  const t=(ko,en)=>lang==='ko'?ko:en
  useEffect(()=>{document.documentElement.lang=lang;localStorage.setItem('pnj-lang',lang)},[lang])
  useEffect(()=>{
    let active=true
    async function boot(){
      try{
        const def=await api('survey')
        const me=await api('me').catch(e=>{if(e.message==='LOGIN_REQUIRED')return null;throw e})
        if(active){setDefinition(def);setUser(me);setReady(true)}
      }catch(e){if(active)setError(e.message)}
    }
    function expired(){setUser(null);setPage('login');setMessage('expired')}
    boot();window.addEventListener('pnj-expired',expired)
    return ()=>{active=false;window.removeEventListener('pnj-expired',expired)}
  },[])
  async function logout(){try{await api('logout','POST');setUser(null);setPage('login');setMessage('')}catch(e){setError(e.message)}}
  function avatarSaved(owner, avatarId){
    setUser(current=>current?.id===owner?{...current,avatarId}:current)
  }
  function profileSaved(profile){
    setUser(current=>current?.id===profile.id?{...profile,avatarId:current.avatarId}:current)
  }
  const [phase,setPhase]=useState('idle')
  const companion=companionFor(user?.avatarId)
  return <main className="shell"><header><div><p className="eyebrow">{copy[lang].eyebrow}</p><h1>{copy[lang].title}</h1></div><div className="language">{['ko','en'].map(v=><button key={v} className={lang===v?'active':''} onClick={()=>setLang(v)}>{v.toUpperCase()}</button>)}</div></header>
    {import.meta.env.MODE==='share'&&<p className="notice">{t('팀 공유용 데모입니다. 아이디·닉네임·대화에는 가상의 정보를 입력하고, 테스트 전용 비밀번호를 사용해 주세요.','Team demo. Use a fictional ID, nickname and conversation details, plus a demo-only password.')}</p>}
    {error&&<p className="error">{errorText(error,lang)} <button onClick={()=>location.reload()}>{t('다시 시도','Retry')}</button></p>}
    {!ready?<p>{t('불러오는 중…','Loading…')}</p>:!user?page==='signup'?<Signup definition={definition} lang={lang} onReturn={done=>{setPage('login');setMessage(done?'created':'')}}/>:
    <Login lang={lang} message={message==='created'?t('가입을 완료했습니다. 로그인해주세요.','Account created. Please sign in.'):message==='expired'?errorText('LOGIN_REQUIRED',lang):''} onLogin={u=>{setUser(u);setPage('home');setMessage('')}} onSignup={()=>setPage('signup')}/>:
    <><nav><button onClick={()=>setPage(page==='profile'?'home':'profile')}>{page==='profile'?t('메인','Home'):t('마이페이지','My profile')}</button><button onClick={logout}>{t('로그아웃','Sign out')}</button></nav>
    {page==='profile'?<Profile {...{user,definition,lang}} onSave={profileSaved} onAvatarSaved={avatarSaved} onBack={()=>setPage('home')}/>:
    <><section className="avatar-card"><Avatar avatarId={user.avatarId} lang={lang}/><div><strong>{companion[lang]}</strong><small className={'companion-phase '+phase} role="status">{companion.phases[phase][lang==='en'?1:0]}</small><p>{user.nickname} · {traitText(user.traits,lang)}</p></div></section>
    <details className="companion-switch"><summary>{t('여행 동반자 변경','Change travel companion')}</summary>
      <SavedAvatarSelector user={user} lang={lang} onSaved={avatarSaved}/></details>
    <Travel key={user.id} lang={lang} companion={companion} onPhase={setPhase}/></>}</>}
  </main>
}
