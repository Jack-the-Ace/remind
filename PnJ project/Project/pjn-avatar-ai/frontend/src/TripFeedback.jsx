import {useState} from 'react'
import {api,errorText} from './client'

export default function TripFeedback({course,result,lang,onFeedback,onAlternative}){
  const t=(k,e)=>lang==='ko'?k:e
  const saved=result.feedback?.[course.id]||{}
  const [reason,setReason]=useState(saved.reason||''),[rating,setRating]=useState(saved.rating||'')
  const [busy,setBusy]=useState(false),[error,setError]=useState('')
  async function send(action){
    setBusy(true);setError('')
    try{
      const feedback=await api('me/trips/'+result.id+'/'+course.id+'/feedback','PUT',{action,reason:action==='reject'?reason||null:null,rating:action==='visit'&&rating?Number(rating):null})
      onFeedback(result.id,course.id,feedback)
      if(action==='reject')await onAlternative(result,course.id)
    }catch(e){setError(errorText(e.message,lang))}finally{setBusy(false)}
  }
  return <fieldset className="trip-feedback" disabled={busy}><legend>{t('이 여행은 어때요?','How does this trip feel?')}</legend>
    {saved.decision&&<p role="status">{saved.decision==='like'?t('마음에 드는 여행으로 저장했어요.','Saved as liked.'):t('거절한 여행으로 저장했어요.','Saved as declined.')}</p>}
    <button onClick={()=>send('like')}>{t('이 여행이 마음에 들어요','I like this trip')}</button>
    <label>{t('거절 이유 (선택)','Reason for declining (optional)')}<select value={reason} onChange={e=>setReason(e.target.value)}>
    {[['','—'],['crowds',t('사람이 많을 것 같아요','It may be crowded')],['walking',t('너무 많이 걸어야 해요','Too much walking')],['been',t('이전에 가본 곳이에요','Been there before')],['new',t('새로운 경험을 원해요','I want a new experience')],['taste',t('제 취향과 달라요','Not my taste')]].map(([v,s])=><option key={v} value={v}>{s}</option>)}</select></label>
    <button onClick={()=>send('reject')}>{t('다른 여행을 추천해주세요','Suggest a different trip')}</button>
    <details><summary>{t('실제 방문 기록','Actual visit')}</summary><label>{t('방문 후 만족도 (선택)','Satisfaction after visiting (optional)')}<select value={rating} onChange={e=>setRating(e.target.value)}><option value="">—</option>{[1,2,3,4,5].map(n=><option key={n}>{n}</option>)}</select></label><button onClick={()=>send('visit')}>{t('직접 방문했어요 · 저장','I visited · Save')}</button></details>
    {saved.visited&&<small>{t('방문 기록 있음','Visit recorded')} {saved.rating&&saved.rating+'/5'}</small>}
    {error&&<p role="alert">{error}</p>}</fieldset>
}
