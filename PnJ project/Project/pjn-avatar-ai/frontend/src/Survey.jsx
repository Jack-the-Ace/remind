import {useState} from 'react'
import {Avatar} from './Avatar'
import {api,errorText} from './client'

export default function Survey({definition,answers,index,onIndex,onChange,onDone,onBack,lang,avatarId}){
  const [notice,setNotice]=useState('')
  const [busy,setBusy]=useState(false)
  const i=lang==='ko'?0:1, t=(ko,en)=>i?en:ko
  const questions=definition.questions, q=questions[index], value=answers[q.id]
  async function next(){
    if(value==null){setNotice(t('이 문항의 답을 선택해주세요.','Choose an answer for this question.'));return}
    setNotice('')
    if(index+1<questions.length){onIndex(index+1);return}
    const missing=questions.findIndex(item=>answers[item.id]==null)
    if(missing>=0){onIndex(missing);return}
    setBusy(true)
    try {await onDone(await api('survey/score','POST',{version:definition.version,answers}))}
    catch(e){setNotice(errorText(e,lang)+' '+t('응답은 그대로입니다. 검사 완료를 다시 눌러주세요.','Your answers are still here. Press Finish survey to retry.'))}finally{setBusy(false)}
  }
  return <section className="panel survey"><header><div><p className="eyebrow">TRAVEL STYLE</p><h2>{t('심리 테스트','Travel personality survey')}</h2></div><Avatar size="mini" {...{avatarId,lang}}/></header>
    <p>{t('여행 개인화를 위한 자체 성향 설문입니다.','An original survey for travel personalization.')}</p>
    <label>{index+1} / {questions.length}<progress value={Object.keys(answers).length} max={questions.length}/></label>
    <fieldset key={q.id} disabled={busy}><legend>{q.prompt[i]}</legend>{q.choices.map((choice,n)=><label className="choice" key={n}><input type="radio" name={q.id} checked={value===n} onChange={()=>{onChange({...answers,[q.id]:n});setNotice('')}}/>{choice[i]}</label>)}</fieldset>
    {notice && <p role="alert">{notice}</p>}
    <div className="actions"><button disabled={busy||index===0} onClick={()=>{onIndex(index-1);setNotice('')}}>{t('이전','Previous')}</button><button className="primary" disabled={busy} onClick={next}>{index===questions.length-1?t('검사 완료','Finish survey'):t('다음','Next')}</button></div>
    <button className="text-button" disabled={busy} onClick={onBack}>{t('입력 화면으로 돌아가기','Back to form')}</button></section>
}
