import {useEffect,useState} from 'react'
import {api,errorText,PREFIX,readDraft,tr} from './client'
import {HeroImage,Alert} from './shared'
import {Login,Signup} from './Auth'
import Profile from './Profile'
import Mood from './Mood'
import Trip from './Trip'
import {freshTrip} from './tripDraft'
import Results from './Results'

function initialLanguage(){try{return localStorage.getItem(PREFIX+'language')==='ko'?'ko':'en'}catch{return 'en'}}
export default function App(){
  const [lang,setLang]=useState(initialLanguage),t=tr(lang)
  const [page,setPage]=useState('loading'),[me,user]=useState(null),[previous,remember]=useState('mood'),[message,note]=useState(''),[error,fail]=useState(null)
  const [mood,setMood]=useState(null),[trip,setTrip]=useState(freshTrip),[result,setResult]=useState(null),[resultLang,setResultLang]=useState(null),[attempt,retry]=useState(0)
  function reset(){setMood(null);setTrip(freshTrip());setResult(null);setResultLang(null);remember('mood')}
  function showResults(r){
    const m=r.activeMood
    setMood(m);user(u=>({...u,currentMood:m,lastMood:m?.action==='skip'?u.lastMood:m}))
    setResult(r);setResultLang(lang);setPage('results');note('')
    const defaults=freshTrip(),filled={...defaults}
    for(const [k,v] of Object.entries(r.trip||{}))filled[k]=v??defaults[k]
    setTrip(filled)
  }
  function signedIn(data){reset();user(data);setPage('mood');note('');fail(null)}
  useEffect(()=>{let live=true
    api('/me').then(data=>{if(live)signedIn(data)}).catch(e=>{if(live){setPage(readDraft().screen?'signup':'home');if(e.status!==401)fail(e)}})
    return()=>{live=false}},[attempt])
  useEffect(()=>{document.documentElement.lang=lang;try{localStorage.setItem(PREFIX+'language',lang)}catch{}},[lang])
  useEffect(()=>{const expire=()=>{user(null);reset();setPage('login');note('expired')};window.addEventListener('planner-session-expired',expire);return()=>window.removeEventListener('planner-session-expired',expire)},[])
  useEffect(()=>{window.scrollTo(0,0)},[page])
  function changeLang(newLang){
    if(newLang===lang)return
    setLang(newLang)
  }
  async function logout(){try{await api('/logout','POST');user(null);reset();setPage('home');note('');fail(null)}catch(e){fail(e)}}
  return <><header className="bar"><div className="bar-inner"><button className="brand" aria-label={t('PnJ planner home','PnJ 플래너 홈')} onClick={()=>{if(me)setPage('mood');else if(page!=='signup')setPage('home')}}><span className="brand-icon" aria-hidden="true">✦</span><b>PnJ</b><span className="brand-sub">Seoul Planner</span></button>
    <nav aria-label={t('Main navigation','주 메뉴')}><div className="languages"><button aria-pressed={lang==='en'} onClick={()=>changeLang('en')}>EN</button><button aria-pressed={lang==='ko'} onClick={()=>changeLang('ko')}>한국어</button></div>
      {me?<><button className="nav-item" onClick={()=>{if(page!=='profile'){remember(page);setPage('profile')}else setPage(previous)}}>{page==='profile'?t('Planner','플래너'):t('My profile','마이페이지')}</button><button className="nav-item" onClick={logout}>{t('Sign out','로그아웃')}</button></>:page==='home'&&<button className="nav-item" onClick={()=>setPage('login')}>{t('Sign in','로그인')}</button>}</nav></div></header>
    <main className={'container page-'+page}><div className="mode"><i/> {t('Rules-based demo','규칙 기반 데모')}</div>
      {error&&<div><Alert>{errorText(error,t)}</Alert><button className="link" onClick={()=>{fail(null);retry(n=>n+1)}}>{t('Reconnect','다시 연결')}</button></div>}
      {page==='loading'&&<p role="status">{t('Opening planner…','플래너를 여는 중이에요…')}</p>}
      {page==='home'&&<section className="hero"><div className="hero-copy"><p className="eyebrow">{t('Seoul travel planner','서울 여행 플래너')}</p><h1>{t('Plan your','나만의')} <em>{t('Seoul','서울')}</em><br/>{t('itinerary.','여행 계획')}</h1>
        <p className="lede">{t('Build a Seoul itinerary around the places you want to explore, how you feel today, and the plans you already have.','가고 싶은 장소와 오늘의 마음, 이미 정해 둔 일정에 맞춰 서울 여행 코스를 만들어 보세요.')}</p>
        <div className="actions"><button className="primary" onClick={()=>setPage('signup')}>{t('Create an account','회원가입')} <span>↗</span></button><button className="text-btn" onClick={()=>setPage('login')}>{t('Sign in','로그인')} →</button></div></div><HeroImage t={t}/></section>}
      {page==='login'&&<Login t={t} onHome={()=>setPage('home')} onJoin={()=>setPage('signup')} onSuccess={signedIn} message={message==='registered'?t('Your account and questionnaire are saved. Sign in to start planning.','계정과 검사 결과를 저장했어요. 직접 로그인해 여행 계획을 시작해 주세요.'):message==='expired'?t('Your session expired. Please sign in again.','세션이 만료됐어요. 다시 로그인해 주세요.'):''}/>}
      {page==='signup'&&<Signup t={t} lang={lang} onCancel={()=>setPage('home')} onComplete={()=>{note('registered');setPage('login')}}/>}
      {page==='profile'&&me&&<Profile lang={lang} t={t} me={me} update={user} onBack={()=>setPage(previous)}/>}
      {page==='mood'&&me&&<Mood t={t} lang={lang} last={me.lastMood} onResult={showResults}/>}
      {page==='trip'&&me&&<Trip t={t} lang={lang} mood={mood} trip={trip} setTrip={setTrip} onBack={()=>setPage('results')} onResult={showResults}/>}
      {result&&['trip','results','profile','editMood'].includes(page)&&<div hidden={page!=='results'}><Results t={t} result={lang===resultLang?result:(result.alternate||result)} mood={mood} onMood={()=>setPage('editMood')} onBack={()=>setPage('trip')}/></div>}
      {page==='editMood'&&<><button className="back" onClick={()=>setPage('results')}>← {t('Back to experiences','추천으로 돌아가기')}</button><Mood t={t} lang={lang} initial={mood} trip={trip} onResult={showResults}/></>}
    </main><footer><span>PnJ · Seoul Planner</span><span>{t('Seoul, Republic of Korea','대한민국 서울')}</span></footer></>
}
