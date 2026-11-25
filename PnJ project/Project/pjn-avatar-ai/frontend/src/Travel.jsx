import {useEffect,useRef,useState} from 'react'
import {api,errorText} from './client'
import CourseView from './CourseView'
import {companionFor} from './avatarConfig'

function localDay(){return new Date().toLocaleDateString('sv-SE')}
export default function Travel({lang,companion,onPhase}){
  const [mode,setMode]=useState('demo'),[mood,setMood]=useState(''),[wish,setWish]=useState('')
  const [turn,setTurn]=useState(null),[result,setResult]=useState(null),[records,setRecords]=useState([])
  const [busy,setBusy]=useState(false),[err,setErr]=useState(''),[clarify,setClarify]=useState('')
  const [day,setDay]=useState(localDay)
  const pending=useRef(false)
  const t=(k,e)=>lang==='ko'?k:e
  const [typing,setTyping]=useState(false)
  useEffect(()=>{onPhase(busy?'thinking':typing?'listening':(turn||result)?'response':'idle')},[busy,typing,turn,result,onPhase])
  useEffect(()=>()=>onPhase('idle'),[onPhase])
  function reset(){setMood('');setWish('');setTurn(null);setResult(null);setErr('');setClarify('')}
  useEffect(()=>{api('me/history').then(setRecords).catch(e=>setErr(e.message))},[])
  useEffect(()=>{function check(){if(day!==localDay()){reset();setDay(localDay())}}
    const timer=setInterval(check,15000);window.addEventListener('focus',check)
    return ()=>{clearInterval(timer);window.removeEventListener('focus',check)}
  },[day])
  async function send(e){
    e.preventDefault()
    if(pending.current)return
    pending.current=true;setBusy(true);setErr('');setClarify('');setResult(null)
    try{
      if(day!==localDay()){reset();setDay(localDay());return}
      if(!turn){setTurn(await api('travel/mood','POST',{mood,mode,language:lang}));return}
      const next=await api('travel/courses','POST',{turn:turn.turn,wish,mode,language:lang})
      if(next.clarification)setClarify(next.clarification)
      else {setResult(next);setRecords(old=>[next,...old].slice(0,20))}
    }catch(e){if(e.message==='NEW_MOOD')reset();setErr(e.message)}finally{pending.current=false;setBusy(false)}
  }
  function onFeedback(tripId,courseId,value){
    const update=r=>r?.id===tripId?{...r,feedback:{...r.feedback,[courseId]:value}}:r
    setResult(update);setRecords(items=>items.map(update))
  }
  async function onAlternative(old,exclude){
    if(pending.current)return
    pending.current=true;setBusy(true);setClarify('');setErr('')
    try{
      const fresh=await api('travel/mood','POST',{mood:old.mood,language:lang,mode})
      setMood(old.mood);setWish(old.wish);setTurn(fresh)
      const next=await api('travel/courses','POST',{turn:fresh.turn,wish:old.wish,exclude,language:lang,mode})
      if(next.clarification)setClarify(next.clarification)
      else {setResult(next);setRecords(items=>[next,...items].slice(0,20))}
    }catch(e){setErr(e.message)}finally{pending.current=false;setBusy(false)}
  }
  return <><form className="panel mood" onSubmit={send}>
    <div className="panel-head"><h2>{turn?t('원하는 여행','Your travel wish'):t('오늘의 기분','Today’s mood')}</h2>
      <select className="mode" aria-label={t('추천 모드','Provider')} disabled={busy||import.meta.env.MODE==='share'} value={mode} onChange={e=>{setMode(e.target.value);setErr('')}}><option value="demo">Demo Mode</option>{import.meta.env.MODE!=='share'&&<option value="ai">OpenAI</option>}</select></div>
    {turn&&<div className="speech"><small>{companionFor(turn.avatarId ?? companion.id)[lang]} · {turn.mode==='demo'?'Demo':'OpenAI'}</small><p>{turn.message}</p><b>{t('이번 여행은 어떻게 보내고 싶어? 바라는 점을 알려 주면 어울리는 곳을 찾아볼게.','What would you like from this trip? Tell me what you have in mind and I’ll suggest a few places.')}</b></div>}
    <label className="field">{turn?t('여행 희망','Travel wish'):t('지금 어떤 기분인가요?','How are you feeling?')}
      <textarea onFocus={()=>setTyping(true)} onBlur={()=>setTyping(false)} key={turn?'wish':'mood'} maxLength={500} required rows="3" value={turn?wish:mood} onChange={e=>(turn?setWish:setMood)(e.target.value)} placeholder={turn?t('아직 모르겠어도 괜찮아요.','It’s okay to be unsure.'):t('오늘 있었던 일이나 느낀 마음','A moment or feeling from today')}/></label>
    <button className="primary" disabled={busy||!(turn?wish:mood).trim()}>{busy?t('잠시만요…','One moment…'):turn?t('여행 Top 3 보기','Suggest three trips'):t(companion.ko+'에게 말하기','Tell '+companion.en)}</button>
    {turn&&<button type="button" disabled={busy} className="text-button" onClick={reset}>{t('기분 새로 입력','Start with a new mood')}</button>}
    {clarify&&<p role="status" className="notice">{clarify}</p>}{err&&<p role="alert" className="error">{err==='NEW_MOOD'?t('오늘의 기분을 다시 입력해주세요.','Please enter today’s mood again.'):errorText(err,lang)}</p>}</form>
    {result&&<CourseView key={result.id} {...{result,lang,onFeedback,onAlternative}} companion={result.avatarId ? companionFor(result.avatarId) : {ko:"여행 동반자",en:"Your companion"}}/>}
    <section className="previous"><h2>{t('이전 추천 기록','Previous suggestions')}</h2>{records.length?records.map(r=><button className="prior" key={r.id} onClick={()=>setResult(r)}><span>{r.day} · {r.mode==='demo'?'Demo':'OpenAI'}</span><b>{r.wish}</b><small>{r.courses.map(c=>c.name).join(' · ')}</small></button>):<p className="empty">{t('첫 추천을 받으면 여기에 저장돼요.','Your first recommendation will appear here.')}</p>}</section></>
}
