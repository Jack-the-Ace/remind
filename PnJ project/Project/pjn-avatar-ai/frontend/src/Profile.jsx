import {useState} from 'react'
import {api,errorText,traitText} from './client'
import {ProfileFields} from './Auth'
import {SavedAvatarSelector} from './AvatarSelector'
import Survey from './Survey'

export default function Profile({user,definition,lang,onSave,onAvatarSaved,onBack}){
  const [draft,setDraft]=useState(user),[survey,setSurvey]=useState(false)
  const [answers,setAnswers]=useState(user.survey?.answers||{}),[index,setIndex]=useState(0)
  const [notice,setNotice]=useState(''),[busy,setBusy]=useState(false)
  const t=(k,e)=>lang==='ko'?k:e
  if(survey)return <Survey avatarId={user.avatarId} {...{definition,lang,answers,index}} onChange={setAnswers} onIndex={setIndex} onBack={()=>setSurvey(false)} onDone={async()=>{
    onSave(await api('me/survey','PUT',{version:definition.version,answers}));setSurvey(false)
    setNotice(t('새 성향을 저장했습니다.','New travel style saved.'))
  }}/>
  return <form className="panel" onSubmit={async e=>{e.preventDefault();setBusy(true);try{onSave(await api('me','PUT',{nickname:draft.nickname,avoid:draft.avoid,mbti:draft.mbti}));setNotice(t('저장했습니다.','Saved.'))}catch(e){setNotice(errorText(e.message,lang))}finally{setBusy(false)}}}>
    <h2>{t('마이페이지','My profile')} · {user.id}</h2><ProfileFields data={draft} change={patch=>setDraft({...draft,...patch})} t={t}/>
    <SavedAvatarSelector user={user} lang={lang} onSaved={onAvatarSaved} disabled={busy}/>
    <p>{traitText(user.traits,lang)}</p>
    {Object.keys(user.strengths||{}).length>0&&<section className="survey-strength"><h3>{t('내 여행 성향','My travel preferences')}</h3>
      <small>{t('자체 여행 설문에서 선택한 횟수예요. 임상검사 점수나 확률이 아니에요.','Counts from our travel survey, not clinical scores or probabilities.')}</small>
      {Object.entries(user.strengths).map(([dim,group])=><section key={dim}><h4>{({company:t('동행','Company'),novelty:t('새로움','Novelty'),pace:t('속도','Pace'),setting:t('환경','Setting'),plan:t('계획','Planning')})[dim]} {user.traits[dim]?.length>1?t('· 균형형','· Balanced'):''}</h4>
        {Object.entries(group).map(([tag,n])=><div key={tag}>{traitText({dim:[tag]},lang)} <meter min="0" max="4" value={n}/> {n}/4</div>)}</section>)}</section>}<p role="status">{notice}</p>
    <button className="primary" disabled={busy}>{t('기본정보 저장','Save profile')}</button>
    <button type="button" onClick={()=>setSurvey(true)}>{t('다시 검사','Retake survey')}</button>
    <button type="button" onClick={onBack}>{t('메인으로','Back to travel')}</button></form>
}
