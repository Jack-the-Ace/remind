import {useEffect,useState} from 'react'
import {api,errorText,tags} from './client'
import {Field,Choices,Alert,BusyLabel} from './shared'
import {empathy} from './Mood'
import {suggestions} from './interpret'
import {withFiveDayExample} from './tripDraft'

function Select({value,onChange,options}){return <select value={value} onChange={e=>onChange(e.target.value)}>{options.map(([k,v])=><option key={k} value={k}>{v}</option>)}</select>}
function PlacePick({title,items,selected,onChange,t}){
  return <div className="field"><label><span>{title}</span><select value="" onChange={e=>{if(e.target.value&&!selected.includes(e.target.value))onChange([...selected,e.target.value])}}><option value="">{t('Choose a place','장소 선택')}</option>{items.map(p=><option key={p.id} value={p.id} disabled={selected.includes(p.id)}>{p.name}</option>)}</select></label>
    {selected.map(id=><button type="button" className="chip on" key={id} onClick={()=>onChange(selected.filter(x=>x!==id))}>{items.find(x=>x.id===id)?.name||id} ×</button>)}</div>
}
export default function Trip({t,lang,mood,trip,setTrip,onBack,onResult}){
  const [wish,setWish]=useState(''),[error,fail]=useState(null),[busy,loading]=useState(false),[places,setPlaces]=useState([]),[placesError,setPlacesError]=useState(null),[reload,retry]=useState(0)
  const patch=(key,value)=>setTrip(d=>({...d,[key]:value}))
  useEffect(()=>{let live=true;setPlacesError(null);api('/places?language='+lang).then(r=>live&&setPlaces(r)).catch(e=>live&&setPlacesError(e));return()=>{live=false}},[lang,reload])
  const names=Object.entries(tags).map(([k,l])=>[k,t(...l)])
  const avoidOptions=[...names,['alcohol',t('Alcohol','음주')]]
  const isAvoidTag=k=>k==='alcohol'||k in tags
  const avoidTags=trip.avoid.filter(isAvoidTag),avoidIds=trip.avoid.filter(k=>!isAvoidTag(k))
  const preview=wish.trim()?suggestions(wish):null
  function addLock(){patch('locked',[...trip.locked,{day:1,label:'',place:'',start:'',end:'',source:'user'}])}
  function editLock(i,key,value){patch('locked',trip.locked.map((x,j)=>i===j?{...x,[key]:value}:x))}
  function example(){setTrip(d=>withFiveDayExample(d,t))}
  async function submit(e){e.preventDefault();if(busy)return;loading(true);fail(null)
    try{const body={...trip,startDate:trip.startDate||null,budgetKrw:trip.budgetKrw===''?null:Number(trip.budgetKrw),availableMinutes:trip.availableMinutes===''?null:Number(trip.availableMinutes),days:trip.days===''?null:Number(trip.days),locked:trip.locked.map(l=>({...l,day:Number(l.day),start:l.start||null,end:l.end||null}))}
      const result=await api('/plans','POST',{language:lang,trip:body,moodId:mood?.id,wishText:wish});onResult(result)}
    catch(e){fail(e)} finally{loading(false)}}
  return <section className="sheet"><button className="back" onClick={onBack}>← {t('Back to experiences','추천으로 돌아가기')}</button>
    <h1>{t('Shape your Seoul trip','어떤 서울 여행을 할까요?')}</h1><p className="lede">{empathy(mood,t)}</p>
    <form onSubmit={submit}><Field label={t('What kind of trip would you like?','원하는 여행을 들려주세요')} hint={t('Optional. Recognised wishes apply when you find itineraries. You can refine them again after seeing the results.','입력한 희망은 코스 찾기를 누르면 반영돼요. 결과를 본 뒤 조건을 다시 조정할 수 있어요.')}><textarea value={wish} maxLength={800} onChange={e=>{setWish(e.target.value)}} placeholder={t('For example, a quiet afternoon exploring local history…','예: 조용한 분위기에서 서울의 역사를 만나고 싶어요.')}/></Field>
    {preview?.interests.length>0&&<p className="muted">{t('Suggested interests','파악한 관심사')} · {preview.interests.map(k=>t(...tags[k])).join(' · ')}</p>}
    <h2>{t('Interests for this trip','이번 여행에서 원하는 경험')}</h2><Choices multiple label={t('Travel interests','이번 여행 희망')} options={names} value={trip.interests} onChange={v=>patch('interests',v)}/>
    <h2>{t('Time and place','기간과 장소')}</h2><div className="form-grid"><Field label={t('Days in Seoul','서울 체류 일수')}><input type="number" min="1" max="14" value={trip.days} onChange={e=>patch('days',e.target.value)}/></Field>
      <Field label={t('Start date (optional)','시작 날짜 (미정 가능)')}><input type="date" value={trip.startDate} onChange={e=>patch('startDate',e.target.value)}/></Field>
      <Field wide label={t('Lodging or neighbourhood','숙소 또는 숙박 지역')} hint={trip.lodgingSource==='example'?t('Example lodging. Replace it with your own base.','시연용 숙소예요. 실제 숙소가 정해지면 바꿔 주세요.'):null}><input value={trip.lodging} maxLength={160} onChange={e=>{const v=e.target.value;setTrip(d=>({...d,lodging:v,lodgingSource:v?'user':null}))}}/></Field></div>
    <details className="fold"><summary>{t('Travel conditions and must-visits','이동·식사 조건 및 꼭 갈 곳')}</summary>
      <div className="form-grid">
        {[['startPoint',['Starting point','출발 지점']],['returnPoint',['Return point','복귀 지점']],['companions',['Travelling with','동행']],['transport',['Transport needs','교통수단']]].map(([k,l])=><Field key={k} label={t(...l)}><input value={trip[k]} maxLength={k==='companions'||k==='transport'?100:160} onChange={e=>patch(k,e.target.value)}/></Field>)}
        <Field label={t('Whole-trip spending cap (KRW)','여행 총예산 상한 (원)')} hint={t('Optional, in KRW for one traveller over the whole trip. The subtotal covers known basic admissions.','1인 기준 여행 전체 금액이에요. 비워 둬도 돼요. 현재 소계에는 확인된 기본 입장료만 포함해요.')}><input type="number" min="0" max="100000000" value={trip.budgetKrw} onChange={e=>patch('budgetKrw',e.target.value)}/></Field>
        <Field label={t('Total time available (minutes)','여행 전체 가용 시간 (분)')}><input type="number" min="1" max="20160" value={trip.availableMinutes} onChange={e=>patch('availableMinutes',e.target.value)}/></Field>
        <Field label={t('Indoor activities','실내 활동 조건')}><Select value={trip.indoor} onChange={v=>patch('indoor',v)} options={[['any',t('No preference','상관없어요')],['prefer',t('Prefer indoors','가급적 실내')],['only',t('Indoors only','실내 활동만')]]}/></Field>
        <Field label={t('Walking requirements','보행 조건')}><Select value={trip.walking} onChange={v=>patch('walking',v)} options={[['any',t('No stated limit','제약 없음')],['low',t('Low walking demand','적은 보행량')],['stepFree',t('Verified step-free route required','검증된 무단차 경로 필수')]]}/></Field>
        <Field wide label={t('Dietary restrictions or allergies','식사 제한·알레르기')}><input value={trip.diet} maxLength={200} onChange={e=>patch('diet',e.target.value)}/></Field>
        <Field label={t('Weather test scenario','검증용 날씨 시나리오')} hint={t('Simulated conditions. Live weather is not connected.','검증용 가상 조건이에요. 실시간 예보는 미연동이에요.')}><Select value={trip.weather} onChange={v=>patch('weather',v)} options={[['unknown',t('Unknown','미확인')],['rain',t('Simulated rain','가상 비')],['clear',t('Simulated clear skies','가상 맑음')]]}/></Field>
        <label className="check"><input type="checkbox" checked={trip.avoidHeights} onChange={e=>patch('avoidHeights',e.target.checked)}/>{t('Must avoid heights','높은 곳은 반드시 피하기')}</label>
        <PlacePick t={t} title={t('Must-visit places','필수 방문 장소')} items={places} selected={trip.mustVisit} onChange={v=>patch('mustVisit',v)}/>
        <PlacePick t={t} title={t('Places to avoid','피할 장소')} items={places} selected={avoidIds} onChange={v=>patch('avoid',[...avoidTags,...v])}/>
      </div>
      {placesError&&<div><Alert>{errorText(placesError,t)}</Alert><button type="button" onClick={()=>retry(n=>n+1)}>{t('Reload places','장소 다시 불러오기')}</button></div>}
      <h3>{t('Experiences to avoid','반드시 피할 경험')}</h3><Choices multiple label={t('Experiences to avoid','회피 경험')} options={avoidOptions} value={avoidTags} onChange={v=>patch('avoid',[...avoidIds,...v])}/>
    </details>
    <details className="fold"><summary>{t('Locked days and appointments','확정 일정 및 약속')}{trip.locked.length?' ('+trip.locked.length+')':''}</summary>
      <p>{t('Keep your bookings. If a time is unknown, leave it blank. You can start with a five-day example that reserves days 1–3.','확정한 일정은 그대로 유지해요. 시각이 미정이면 비워 두세요. 5일 중 1~3일을 고정한 예시를 불러올 수도 있어요.')}</p>
      <button type="button" className="secondary" onClick={example}>{t('Use 5-day example','4박 5일 예시 적용')}</button>
      {trip.locked.map((l,i)=><div className="lock" key={i}>{l.source==='example'&&<small>{t('Example commitment','시연용 고정 일정')}</small>}<div className="form-grid"><Field label={t('Day','여행 일차')}><input required type="number" min="1" max={trip.days} value={l.day} onChange={e=>editLock(i,'day',e.target.value)}/></Field>
      <Field label={t('Appointment','확정한 일정')}><input required value={l.label} maxLength={150} onChange={e=>editLock(i,'label',e.target.value)}/></Field>
      <Field wide label={t('Location','약속 장소')}><input value={l.place} maxLength={150} onChange={e=>editLock(i,'place',e.target.value)}/></Field>
      {[['start',['Start time','시작 시각']],['end',['End time','종료 시각']]].map(([k,lab])=><Field key={k} label={t(...lab)}><input type="time" value={l[k]||''} onChange={e=>editLock(i,k,e.target.value)}/></Field>)}</div>
      <button type="button" className="link" onClick={()=>patch('locked',trip.locked.filter((_,j)=>j!==i))}>{t('Remove appointment','이 일정 삭제')}</button></div>)}
      <button type="button" className="link" onClick={addLock}>+ {t('Add a locked segment','고정 일정 추가')}</button></details>
    <details className="fold"><summary>{t('Data used in this demo','데모 데이터 안내')}</summary>
      <p>{t('Places have source links. When personal preferences leave a tie, the planner can refer to activities reported by visitors in the 2025 Seoul survey. Weather is a test scenario.','장소별 출처를 확인할 수 있어요. 개인 선호로 우열을 가리기 어려울 때는 2025년 서울 방문객이 경험한 활동도 참고해요. 날씨는 검증용 시나리오예요.')}</p></details>
    <Alert>{errorText(error,t)}</Alert><button className="primary" disabled={busy}><BusyLabel busy={busy} t={t}>{t('Find itineraries','추천 코스 찾기')} →</BusyLabel></button></form></section>
}
