export default function Questionnaire({spec,index,answers,lang,t,onAnswer,onMove,onFinish,onBack}) {
  const q=spec.items[index], total=spec.items.length
  const answered=spec.items.filter(item=>Number.isInteger(answers[item.id]) && answers[item.id]>=1 && answers[item.id]<=5).length
  const options=[[5,t('Strongly agree','매우 그렇다')],[4,t('Agree','그렇다')],[3,t('Neutral','보통')],[2,t('Disagree','아니다')],[1,t('Strongly disagree','매우 아니다')]]
  return <section className="sheet quiz" data-question-id={q.id}>
    <button className="back" onClick={onBack}>← {t('Back','돌아가기')}</button>
    <p key={q.id+'-'+lang} translate="no" className="eyebrow">{t('Travel personality','여행 성향 검사')+' · '+(index+1)+' / '+total}</p>
    <progress aria-label={t('Answers completed','응답 완료율')} value={answered} max={total}/>
    <h1 key={q.id+lang} className="question">{q.text[lang]}</h1>
    <div className="answers">{options.map(([value,label])=><button key={value} aria-pressed={answers[q.id]===value} onClick={()=>onAnswer(q.id,value)}><b>{value}</b>{label}</button>)}</div>
    <div className="actions"><button className="secondary" disabled={!index} onClick={()=>onMove(index-1)}>{t('Previous','이전')}</button>
    <button className="primary" disabled={!answers[q.id] || (index===total-1 && answered!==total)} onClick={()=>index===total-1?onFinish():onMove(index+1)}>{index===total-1?t('Finish questionnaire','검사 완료'):t('Next','다음')} →</button></div>
    <small>{t('PnJ short questionnaire using public IPIP items. Korean wording is a review translation.','IPIP 공개 문항을 선별한 PnJ 단축 설문입니다. 한국어는 검토용 번역입니다.')}</small></section>
}
