import {empathy} from './Mood'
import {useEffect,useRef,useState} from 'react'
import {api,errorText,tags} from './client'
import {Alert,PhotoCredit,Field} from './shared'

function Photo({place,t}){
  const [failed,setFailed]=useState(false)
  return !place.photo?.src||failed?<span className="missing">{t('Photo unavailable','사진 미확보')}</span>:<img src={place.photo.src} alt={place.name||place.title} decoding="async" onError={()=>setFailed(true)}/>
}
function Handoff({payload,t}){
  const json=JSON.stringify(payload,null,2)
  const [url,setUrl]=useState(null)
  useEffect(()=>{const blobUrl=URL.createObjectURL(new Blob([json],{type:'application/json;charset=utf-8'}));setUrl(blobUrl);return()=>URL.revokeObjectURL(blobUrl)},[json])
  return <aside className="handoff"><h3>{t('Mia handoff preview','미아 인계용 JSON')}</h3><p>{t('Selected demo draft. Review and download the file. Nothing is sent to Mia.','선택한 데모 초안이에요. 내용을 확인하고 다운로드해 주세요. 미아 앱에 자동 전송하지 않아요.')}</p>
    {url&&<a className="primary" download={'pnj-'+(payload.planId||'mia-plan')+'.json'} href={url}>{t('Download JSON','JSON 다운로드')} ↓</a>}
    <details className="fold"><summary>{t('View structured JSON','구조화 JSON 확인')}</summary><pre tabIndex="0">{json}</pre></details></aside>
}

function ScheduleInfo({stop,t}){
  const hours=stop.openingHours
  if(hours?.status!=='published_regular_schedule')return <small>{t('Hours for your visit remain unconfirmed.','방문일 운영 시간은 미확인이에요.')}</small>
  const slots=[[t('Tue–Thu','화~목'),hours.tueThu],[t('Fri','금'),hours.friday],[t('Weekend / holiday','주말·공휴일'),hours.weekendHoliday?.all],[t('Weekend / holiday, summer','주말·공휴일 하절기'),hours.weekendHoliday?.summer],[t('Weekend / holiday, winter','주말·공휴일 동절기'),hours.weekendHoliday?.winter]].filter(([,v])=>Array.isArray(v))
  const weekdays=t('Monday,Tuesday,Wednesday,Thursday,Friday,Saturday,Sunday','월요일,화요일,수요일,목요일,금요일,토요일,일요일').split(',')
  const closed=[...(hours.closed?.weekday||[]).map(index=>weekdays[index]),...(hours.closed?.monthDay||[])]
  return <details className="fold"><summary>{t('Published gallery hours','공식 전시실 정규 운영 시간')}</summary><ul>{slots.map(([label,v])=><li key={label}>{label} · {v.join('–')}</li>)}
    {closed.length>0&&<li>{t('Regular closures','정기 휴관')} · {closed.join(', ')}</li>}</ul><p>{t('Last entry','입장 마감')} · {hours.lastAdmissionBeforeCloseMinutes} {t('minutes before closing','분 전')}</p><a href={hours.source} target="_blank" rel="noreferrer">{t('Official schedule','공식 운영 안내')} ↗</a> · {hours.checkedOn}<p>{t('Check exceptions on your visit date.','방문일 임시 변경은 다시 확인해 주세요.')}</p></details>
}
function Detail({course,t,refBox}){
  const [selectionReason,setSelectionReason]=useState('')
  const [mode,setMode]=useState('P'),[error,fail]=useState(null),[busy,loading]=useState(false),[payload,select]=useState(null)
  const [feedback,open]=useState(''),[reason,setReason]=useState(''),[rating,setRating]=useState(''),[saved,setSaved]=useState('')
  async function choose(){if(busy)return;loading(true);fail(null)
    try{const data=await api('/plans/'+encodeURIComponent(course.id)+'/select?language='+course.language,'POST',{reason:selectionReason||null,detailMode:mode});select(data)}catch(e){fail(e)}finally{loading(false)}}
  const chosen=payload?.language===course.language?{...payload,detailMode:mode}:null
  async function submit(e){e.preventDefault();if(busy)return;loading(true);fail(null)
    try{const body={kind:feedback};if(feedback==='reject'&&reason.trim())body.reason=reason.trim();if(feedback==='visit'&&rating)body.satisfaction=Number(rating)
      await api('/plans/'+encodeURIComponent(course.id)+'/feedback','POST',body);setSaved(feedback);open('')}
    catch(e){fail(e)}finally{loading(false)}}
  return <section ref={refBox} tabIndex="-1" className="sheet detail" data-course-id={course.courseId||course.id}>
    <p className="eyebrow">{course.region}</p><h2>{course.title}</h2><p className="lede">{course.summary}</p>
    {course.reasons?.length>0&&<details className="fold"><summary>{t('Why this course?','이 코스를 추천한 이유')}</summary><ul>{course.reasons.map((r,i)=><li key={i}>{r}</li>)}</ul></details>}
    <div className="switch" role="group" aria-label={t('Itinerary detail','계획 상세도')}>{[['P',t('P · Overview','P · 한눈에')],['PnJ',t('PnJ · Guided','PnJ · 균형 있게')],['J',t('J · Detailed','J · 자세히')]].map(([id,label])=><button aria-pressed={mode===id} key={id} onClick={()=>setMode(id)}>{label}</button>)}</div>
    {mode==='J'&&(course.conditions.days==null||!course.conditions.startPoint)&&<p className="panel-info">{t('For a timed plan, which day and starting point would work for you? You can leave both open.','시간을 정한다면 어느 날, 어디에서 출발하고 싶나요? 지금은 둘 다 비워 둬도 좋아요.')}</p>}
    {course.days.map(d=><article className="day" key={d.day??'flexible'}><h3>{d.day==null?t('A loose route','가볍게 즐기는 순서'):'DAY '+String(d.day).padStart(2,'0')} <small>{d.date||t('Date open','날짜 미정')}</small></h3>
      {!!d.locked.length&&<ul className="locked-list">{d.locked.map((s,i)=><li key={i}><strong>{s.source==='example'?t('Example commitment','시연용 고정 일정'):t('Locked','확정')} · {s.label}</strong> {s.place} {s.start||s.end?[s.start||'…',s.end||'…'].join(' – '):t('Time unconfirmed','시각 미정')}</li>)}</ul>}
      <ol className="stops">{d.stops.map((p,i)=><li data-place-id={p.id} key={p.id+'-'+i}><div className="thumb"><Photo place={p} t={t}/></div><div><h4>{p.name}</h4><p>{(p.activities||[]).join(' · ')}</p>
      {mode==='J'&&<><ScheduleInfo stop={p} t={t}/>{p.source&&<div><a className="link" href={p.source} target="_blank" rel="noreferrer">{t('Official visitor information','공식 방문 안내')} ↗</a> · {p.checkedOn}</div>}
        <small>{t('Basic admission','기본 입장료')} · {p.admission?.basicKrw==null?t('Unconfirmed','미확인'):p.admission.basicKrw.toLocaleString()+' KRW'}</small></>}</div></li>)}</ol>
      {!!d.notes?.[mode]?.length&&<ul className="notes">{d.notes[mode].map((n,i)=><li key={i}>{n}</li>)}</ul>}
      {mode==='J'&&d.transfers?.length>0&&<details className="fold"><summary>{t('Transfers to verify','확인할 이동 구간')}</summary><ul>{d.transfers.map((leg,i)=><li key={i}>{leg.from} → {leg.to} · {t('Travel time unconfirmed','이동 시간 미확인')}</li>)}</ul></details>}
    </article>)}
    {mode==='J'&&course.costs&&<div className="panel-info"><strong>{t('Admission and trip costs','입장료 및 여행 경비')}</strong><p>{t('Subtotal of known basic admission fees','확인된 기본 입장료 소계')} · {course.costs.knownBasicAdmissionSubtotal==null?t('Unknown','미확인'):course.costs.knownBasicAdmissionSubtotal.toLocaleString()+' KRW'}</p><p>{t('Whole-trip total is unknown. Check unconfirmed admissions, transport, meals, and any lodging or extras.','여행 총액은 미확인이에요. 미확인 입장료와 교통·식사·숙박·추가 구매 비용은 따로 확인해 주세요.')}</p></div>}
    {!!course.checks?.length&&<aside className="checks"><h3>{t('Check before you go','출발 전 확인')}</h3><ul>{course.checks.map((c,i)=><li key={i}>{c}</li>)}</ul></aside>}
    <details className="fold"><summary>{t('Place sources and photo credits','장소 출처와 사진 크레딧')}</summary>
      {Array.from(new Map(course.days.flatMap(d=>d.stops).map(p=>[p.id,p])).values()).map(p=><div className="source" key={p.id}><strong>{p.name}</strong>{p.source&&<a href={p.source} target="_blank" rel="noreferrer">{t('Place information','장소 정보')} ↗</a>} {p.checkedOn}<PhotoCredit photo={p.photo} t={t}/></div>)}</details>
    <details className="fold"><summary>{t('Add a reason for choosing this course (optional)','이 코스를 고른 이유 남기기 (선택)')}</summary><Field label={t('My reason for Mia','미아에게 전할 선택 이유')}><input maxLength={180} value={selectionReason} disabled={!!chosen} onChange={e=>setSelectionReason(e.target.value)}/></Field></details>
    <div className="actions"><button className="primary" disabled={busy||!!chosen} onClick={choose}>{chosen?t('Plan selected','선택한 계획'):t('Select plan for Mia','이 계획을 미아 인계용으로 선택')} →</button>
    <button className="secondary" disabled={busy} onClick={()=>{open('reject');setSaved('')}}>{t('Reject this itinerary','이 코스 거절')}</button><button className="link" disabled={busy} onClick={()=>{open('visit');setSaved('')}}>{t('Record an actual visit','실제 방문 기록')}</button></div>
    {feedback&&<form className="panel-info" onSubmit={submit}>{feedback==='reject'?<Field label={t('Reason for rejecting (optional)','거절 이유 (선택)')}><input maxLength={180} value={reason} onChange={e=>setReason(e.target.value)}/></Field>:<Field label={t('I visited this course. My satisfaction was…','실제로 방문했어요. 만족도는…')}><select value={rating} onChange={e=>setRating(e.target.value)}><option value="">{t('Leave unrated','별점 생략')}</option>{[1,2,3,4,5].map(v=><option key={v} value={v}>{v} / 5</option>)}</select></Field>}
    <button className="secondary" disabled={busy}>{t('Save feedback','기록 저장')}</button> <button type="button" className="link" onClick={()=>open('')}>{t('Cancel','취소')}</button></form>}
    {saved&&<p role="status" className="notice">{saved==='visit'?t('Your actual visit was recorded.','실제 방문 기록을 저장했어요.'):t('Your rejection was recorded.','거절 기록을 저장했어요.')}</p>}<Alert>{errorText(error,t)}</Alert>
    {chosen&&<Handoff payload={chosen} t={t}/>}</section>
}
export default function Results({result,onBack,onMood,mood,t}){
  const [id,focus]=useState(null),box=useRef(null),chosen=result.courses.find(c=>c.id===id)
  function show(id){focus(id);requestAnimationFrame(()=>{box.current?.focus({preventScroll:true});box.current?.scrollIntoView({block:'start'})})}
  return <><section className="result-head"><h1>{t('Your Seoul itineraries','나를 위한 서울 코스')}</h1><p className="lede">{empathy(mood,t)}</p>
    {mood?.action==='reuse'&&mood.reusedFrom&&<p className="muted">{t('Using your answers from','다시 사용한 답변의 기준 시각')} · {new Date(mood.reusedFrom).toLocaleString(t('en-GB','ko-KR'),{timeZone:'Asia/Seoul',timeZoneName:'short'})}</p>}
    {!!mood?.tags?.length&&<p className="muted">{t('What we picked up','이렇게 이해했어요')} · {mood.tags.filter(k=>tags[k]).map(k=>t(...tags[k])).join(' · ')}</p>}
    <div className="actions"><button className="secondary" onClick={onBack}>{t('Refine trip conditions','조건 더 맞추기')}</button><button className="link" onClick={onMood}>{t('Adjust mood interpretation','기분 해석 수정')}</button></div>
    {result.notices?.length>0&&<ul className="notice">{result.notices.map((n,i)=><li key={i}>{n}</li>)}</ul>}</section>
    {!result.courses.length&&<div className="sheet"><h2>{result.matchStatus==='no_activity_match'?t('No matching activity in the catalogue yet','아직 이 활동에 맞는 후보가 없어요'):t('No courses meet these requirements','조건에 맞는 코스가 없어요')}</h2>{result.matchStatus!=='no_activity_match'&&<p>{t('Review the constraints above and change only those that are flexible.','위 안내를 보고 조정 가능한 조건만 바꿔 주세요.')}</p>}<button className="secondary" onClick={onBack}>{t('Review conditions','조건 다시 확인')}</button></div>}
    <div className="cards">{result.courses.map((c,i)=><article className={'card'+(id===c.id?' selected':'')} key={c.id}><div className="card-pic"><Photo place={c} t={t}/><span>TOP {i+1}</span></div>
    <div className="card-body"><p className="eyebrow">{c.activityMatch && (c.activityMatch.level==='area' ? t('Area alternative','권역 대안') : t('Direct match','직접 일치'))}{c.activityMatch && ' · '}{c.region}</p><h2>{c.summary}</h2><p>{c.days.flatMap(d=>d.stops.map(p=>p.name)).slice(0,3).join(' → ')}</p>{c.conditionMatch?.pending?.length>0&&<small>{c.conditionMatch.pending[0]}</small>}{c.reasons?.length>0&&<ul>{c.reasons.slice(0,3).map((r,j)=><li key={j}>{r}</li>)}</ul>}<button className="card-open" aria-expanded={id===c.id} onClick={()=>show(c.id)}>{t('View itinerary','코스 자세히 보기')} <span>↘</span></button></div></article>)}</div>
    {result.courses.length>0&&<details className="photo-details"><summary>{t('Photo credits','사진 크레딧')}</summary>{result.courses.filter(c=>c.photo).map(c=><div key={c.id}>{c.title} <PhotoCredit photo={c.photo} t={t}/></div>)}</details>}
    {chosen&&<Detail course={chosen} key={chosen.id} t={t} refBox={box}/>}</>
}
