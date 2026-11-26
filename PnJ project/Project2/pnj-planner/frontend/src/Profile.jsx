import Questionnaire from './Questionnaire'
import {useState} from 'react'
import {api,axisNames,scoreNames,errorText} from './client'
import {Alert} from './shared'
import {profileFields} from './Auth'

export default function Profile({me,t,lang,update,onBack}){
  const direct=()=>Object.fromEntries(Object.entries(me.preferences).map(([k,p])=>[k,p.source==='direct'?p.value:'']))
  const [values,edit]=useState(direct),[busy,loading]=useState(false),[error,fail]=useState(null),[saved,setSaved]=useState(false)
  const [spec,setSpec]=useState(null),[index,move]=useState(0),[answers,respond]=useState({})
  async function begin(){try{fail(null);setSpec(await api('/survey'));move(0);respond({})}catch(e){fail(e)}}
  async function finish(){
    if(busy)return
    loading(true);fail(null)
    try{update(await api('/survey','PUT',{version:spec.version,answers,language:lang}));setSpec(null)}
    catch(e){fail(e)}finally{loading(false)}
  }
  if(spec)return <><Questionnaire {...{spec,index,answers,lang,t}} onMove={move} onBack={()=>setSpec(null)} onAnswer={(id,v)=>respond({...answers,[id]:v})} onFinish={finish}/><Alert>{errorText(error,t)}</Alert></>
  const current=me.survey.current
  async function save(e){e.preventDefault();if(busy)return;loading(true);fail(null)
    try{const next=await api('/preferences','PUT',{values:Object.fromEntries(Object.entries(values).map(([k,v])=>[k,v===''?null:Number(v)]))});update(next);setSaved(true)}
    catch(e){fail(e)}finally{loading(false)}}
  return <section className="sheet"><button className="back" onClick={onBack}>← {t('Back to planner','플래너로 돌아가기')}</button><h1>{t('My profile','마이페이지')}</h1><p className="lede">{me.username} · {me.survey?.version}</p>
    {Object.values(me.profile).some(v=>v!=null&&v!=='')&&<details className="fold"><summary>{t('Saved background details','저장한 기본정보')}</summary><dl className="score-list">{Object.entries(profileFields).filter(([k])=>me.profile[k]!=null&&me.profile[k]!=='').map(([k,label])=><div key={k}><dt>{t(...label)}</dt><dd>{me.profile[k]}</dd></div>)}</dl></details>}
    <h2>{t('Personality results','성격검사 결과')}</h2><p>{current?t('Each trait has its own 0–100 score on this PnJ short questionnaire.','PnJ 단축 설문의 각 특성을 독립적인 0~100점으로 표시해요.'):t('Your original Mini-IPIP results are saved. You may take the new PnJ questionnaire whenever you like.','기존 Mini-IPIP 결과를 보관하고 있어요. 원할 때 새 PnJ 검사로 갱신할 수 있어요.')}</p>
    <dl className="score-list">{Object.entries(me.scores).map(([k,value])=><div key={k}><dt>{current?me.survey.facets[k]?.[lang]:t(...scoreNames[k])}</dt><dd><meter min={current?0:4} max={current?100:20} value={value}/> {value} / {current?100:20}</dd></div>)}</dl>
    <button className="secondary" onClick={begin}>{t('Take the PnJ questionnaire','PnJ 검사 다시 하기')}</button>
    <h2>{t('Travel preferences','추천용 여행 선호')}</h2><p>{t('Confirm the preferences that matter to you. Direct answers take priority over tentative suggestions. Leave any others open.','중요한 선호만 직접 확인해 주세요. 직접 입력한 답은 성격에서 제안한 임시 선호보다 우선해요.')}</p>
    <form onSubmit={save}><div className="axis-grid">{Object.entries(axisNames).map(([k,l])=>{
      const pref=me.preferences[k],hint=pref?.source==='personality'?t('Tentative suggestion','성격 기반 임시 제안')+' · '+pref.value+'/5':pref?.source==='direct'?t('Confirmed by you','직접 확인'):t('Unconfirmed','미확인')
      return <label className="axis" key={k}><strong>{t(...l)}</strong><small>{hint}</small><select value={values[k]??''} onChange={e=>{edit({...values,[k]:e.target.value});setSaved(false)}}><option value="">{t('No direct answer','직접 응답 없음')}</option>{[1,2,3,4,5].map(n=><option key={n} value={n}>{n}{n===1?t(' · Low',' · 낮음'):n===5?t(' · High',' · 높음'):''}</option>)}</select></label>
    })}</div><Alert>{errorText(error,t)}</Alert><div className="actions"><button className="primary" disabled={busy}>{t('Save preferences','선호 저장')}</button>{saved&&<span role="status">{t('Preferences saved.','선호를 저장했어요.')}</span>}</div></form></section>
}
