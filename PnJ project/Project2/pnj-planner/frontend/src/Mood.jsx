import {useState} from 'react'
import {api,errorText,tags} from './client'
import {Field,Choices,Alert,BusyLabel} from './shared'

export const questions=[
  ['mood',['How are you feeling?','지금 기분은 어때요?'],{tired:['Tired','지쳤어요'],restless:['Restless','답답해요'],happy:['Happy','즐거워요'],curious:['Curious','호기심이 생겨요'],calm:['Calm','차분해요'],low:['Low','기운이 없어요']}],
  ['goal',['What would you like from today?','오늘 무엇을 얻고 싶나요?'],{rest:['A break','휴식'],discover:['Discovery','새로운 발견'],connect:['Connection','교류'],learn:['Learning','배움']}],
  ['atmosphere',['What atmosphere sounds good?','어떤 분위기가 좋을까요?'],{quiet:['Quiet','조용한 곳'],lively:['Lively','활기찬 곳'],green:['Green spaces','푸른 자연'],indoor:['Indoors','실내']}],
  ['activity',['How active would you like to be?','원하는 활동량은 어느 정도인가요?'],{low:['Gentle','가볍게'],medium:['Moderate','적당히'],high:['Active','활동적으로']}]
]
function moodLabel(key,t){for(const [, ,options] of questions){if(options[key])return t(...options[key])} return tags[key]?t(...tags[key]):''}
function pastSummary(last,t){
  return [...Object.entries(last.choices||{}).map(([q,v])=>{const label=questions.find(([key])=>key===q)?.[2][v];return label?t(...label):''}),...(last.tags||[]).map(tag=>moodLabel(tag,t))].filter(Boolean).join(' · ')
}
export function empathy(m,t){
  if(!m||m.action==='skip')return t('Let’s start with your everyday preferences.','평소 성향을 바탕으로 서울에서 해볼 만한 경험을 골랐어요.')
  const lines={
    tired:['Sounds like a tiring day. Pick whichever experience feels easiest today.','오늘 많이 지쳤군요. 가장 부담 없이 느껴지는 경험부터 골라 봐요.'],
    happy:['It’s lovely to hear you’re feeling good. See which outing catches your eye.','기분 좋은 하루군요. 마음이 가는 서울 나들이를 골라 보세요.'],
    restless:['Feeling stuck can be uncomfortable. You can decide what sounds good as you browse.','답답한 마음이 들었군요. 천천히 둘러보면서 끌리는 쪽을 골라도 좋아요.'],
    calm:['A calm day sounds lovely. Take your time choosing.','차분한 하루군요. 천천히 둘러보세요.'],
    curious:['Let’s give that curiosity somewhere to go.','호기심이 생긴 날이군요. 어떤 경험이 눈에 들어오나요?'],
    low:['Thanks for sharing. Choose at your own pace.','마음을 들려줘서 고마워요. 부담 없이 골라 봐요.']}
  return t(...(lines[m.choices?.mood]||['You can decide as you go. Start with something that catches your eye.','오늘은 미리 정하지 않아도 괜찮아요. 마음이 가는 쪽부터 골라 봐요.']))
}
export default function Mood({t,lang,last,onResult,initial,trip={}}){
  const [feeling,pick]=useState(initial?.choices?.mood||''),[raw,type]=useState('')
  const [adjusted,adjust]=useState(initial?.tags||[]),[busy,loading]=useState(false),[error,fail]=useState(null)
  async function submit(action){
    if(busy)return
    loading(true);fail(null)
    const choices={...initial?.choices};delete choices.mood
    if(feeling)choices.mood=feeling
    try{
      const checkIn=action==='new'?{action,text:raw,choices,tags:adjusted,editedFromId:initial?.id}:{action}
      const result=await api('/plans','POST',{language:lang,trip,checkIn})
      onResult(result)
    }catch(e){fail(e)}finally{loading(false)}
  }
  return <section className="sheet"><h1>{initial?t('Adjust your check-in','오늘 마음 다시 맞추기'):t('How are you feeling today?','오늘은 어떤 마음인가요?')}</h1>
    <Field label={t('A few words about today','오늘의 기분 한마디')}><textarea maxLength={800} value={raw} onChange={e=>type(e.target.value)} placeholder={t('I’m tired and would love a gentle break…','오늘 너무 지쳤어. 편하게 쉬고 싶어…')}/></Field>
    <Choices label={t('Optional mood','기분 선택 (선택)')} value={feeling} onChange={pick} options={Object.entries(questions[0][2]).map(([k,l])=>[k,t(...l)])}/>
    {initial&&<div className="panel-info"><p>{t('Choose the experiences that fit today.','오늘 마음에 맞는 경험만 골라 주세요.')}</p><Choices multiple label={t('Experience cues','추천에 반영할 경험')} options={Object.entries(tags).map(([k,l])=>[k,t(...l)])} value={adjusted} onChange={adjust}/></div>}
    <Alert>{errorText(error,t)}</Alert><div className="actions"><button className="primary" disabled={busy||(!initial&&!raw.trim()&&!feeling&&!adjusted.length&&!Object.keys(initial?.choices||{}).length)} onClick={()=>submit('new')}><BusyLabel busy={busy} t={t}>{t('Find experiences for me','지금 마음으로 추천받기')}</BusyLabel></button>
    <button className="secondary" disabled={busy} onClick={()=>submit('skip')}>{t('Skip mood and explore','기분 없이 추천받기')}</button></div>
    <small>{t('This local demo keeps a short interpretation. Your original message is discarded.','규칙 기반 데모가 추천에 쓴 요약만 남겨요. 입력한 문장은 저장하지 않아요.')}</small>
    {last&&!initial&&<div className="previous"><strong>{t('Previous check-in','지난 답변')}</strong><p>{new Date(last.reusedFrom||last.confirmedAt).toLocaleString(lang==='ko'?'ko-KR':'en-GB')} · {pastSummary(last,t)||t('Open to ideas','어울리는 경험 찾기')}</p><button className="link" disabled={busy} onClick={()=>submit('reuse')}>{t('Use my previous answers','지난 답과 같아요')}</button></div>}</section>
}
