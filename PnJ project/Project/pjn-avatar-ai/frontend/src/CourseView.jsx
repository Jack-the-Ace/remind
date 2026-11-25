import {useRef, useState} from 'react'
import './trip.css'
import TripFeedback from './TripFeedback'

function Photo({place, lang}) {
  const [failed, setFailed] = useState(false)
  if (!place?.photo?.src || failed) {
    return <span className="trip-photo-missing">{lang === 'ko' ? '사진 미확보' : 'Photo unavailable'}</span>
  }
  return <img decoding="async" src={place.photo.src} alt={place.name} onError={() => setFailed(true)} />
}

function Credits({places, lang}) {
  const photos = places.filter(p => p.photo)
  if (!photos.length) return null
  return <details className="trip-credits"><summary>{lang === 'ko' ? '사진 출처와 이용 조건' : 'Photo credits and licenses'}</summary>
    {photos.map(p => <p key={p.id}>{p.name} · {p.photo.author} · <a href={p.photo.source} target="_blank" rel="noreferrer">Wikimedia Commons</a> · <a href={p.photo.licenseUrl} target="_blank" rel="noreferrer">{p.photo.license}</a> · {lang==='ko' ? '화면용 축소 및 비율 맞춤' : 'Resized and cropped for display'}</p>)}
  </details>
}

function CourseDetail({course, result, lang, detailRef, companion,onFeedback,onAlternative}) {
  const [level, setLevel] = useState('p')
  const t = (ko, en) => lang === 'ko' ? ko : en
  // Previously saved concept-only routes retain their original activity sequence.
  const places = course.places || [course]
  const days = course.days || [[{placeId: course.id, activities: course.stops}]]
  return <section ref={detailRef} tabIndex={-1} className="trip-detail" data-course={course.id} aria-label={course.name}>
    <div className="trip-hero"><div className="trip-hero-photo"><Photo key={course.id} place={places[0]} lang={lang}/></div>
      <div className="trip-hero-copy"><span>{course.region}</span><h3>{course.name}</h3><p>{course.description}</p>
        <strong>{t(companion.ko+'의 추천 이유', 'Why '+companion.en+' picked it')}</strong><p>{course.reason}</p>{course.profileReason&&<p>{course.profileReason}</p>}
        {course.match?.area>0&&<p>{t(result.lodgingBase+' 숙소 희망을 고려해 같은 구 또는 인접 권역을 먼저 골랐어.', 'Your requested lodging base near '+result.lodgingBase+' influenced the area ranking.')}</p>}</div></div>
    <div className="trip-plan">
      {course.basis&&<dl className="trip-basis">{Object.entries(course.basis).map(([key,value])=><div key={key}><dt>{{wish:t('이번 여행 희망','Travel wish'),mood:t('오늘의 기분','Current mood'),survey:t('평소 성향','Survey preferences'),history:t('과거 기록','Past suggestions and feedback'),visit:t('방문 기록','Visit history')}[key]}</dt><dd>{value}</dd></div>)}</dl>}<div className="levels">{[['p',t('기본 P 보기','Basic P view')],['mix',t('P와 J 반반이면...','Half P, half J…')],['j',t('파워 J에게','For a power J')]].map(([k,label]) =>
      <button key={k} aria-pressed={level===k} onClick={()=>setLevel(k)}>{label}</button>)}</div>
      {level==='j' && <p className="notice">{t('아래 시간은 출발 시각을 정하지 않은 예시예요. 이동시간은 방문 당일 확인해 주세요.', 'Times below are examples without a fixed departure. Check transfers on the day.')}</p>}
      {days.map((day, di) => <section className="trip-day" key={di}><h4>DAY {di+1}</h4>
        {!day.length&&<p>{t('자유 일정이에요. 숙소 근처에서 쉬거나 앞선 날의 활동을 이 날로 옮겨도 좋아요.','Leave this day open. Rest near your lodging or move an earlier activity here.')}</p>}
        {day.map(step => {
          const p = places.find(p=>p.id===step.placeId)
          return <div className="trip-stop" key={step.placeId}>
            {p && <div className="trip-stop-photo"><Photo key={p.id} place={p} lang={lang}/></div>}
            <div><h5>{p?.name || course.name}</h5><ol>{step.activities.map((a,i)=><li key={a}>{a}
              {level==='mix'&&<small>{i===0?t('핵심 일정','Main activity'):t('선택 활동 · 자유시간으로 바꿔도 좋아요.','Optional activity · swap for free time.')}</small>}
              {level==='j'&&<small>{p?.timeGuide==='programme' ? t('공연 시작·종료 시각과 입장 마감은 예매한 회차를 확인하세요.','Use the booked performance times and check the last entry time.') : p?.timeGuide==='walk'&&i===0 ? t('산책 예시 20~35분 · 컨디션에 따라 짧게 돌아오세요.','Example walk · 20–35 min, with the option to turn back early.') : i===0?t('체류 예시 25–40분','Example visit · 25–40 min'):t('체류 예시 10–20분','Example visit · 10–20 min')}</small>}</li>)}</ol>
              {level==='mix'&&<p>{t('자유시간 · 마음에 드는 곳에 더 머물거나 다음 활동을 건너뛰세요.','Free time · linger here or skip the next activity.')}</p>}
              {level==='j'&&<p>{t('이동 전에는 10~15분 정도 쉴 여유를 두세요. 늦어지면 마지막 활동을 다음 기회로 미뤄도 좋아요.','Leave about 10–15 minutes to rest before setting off. If you run late, save the last activity for another day.')}</p>}
              {level==='mix'&&<small>{p?.setting==='outdoor' ? t('비가 오거나 피곤하면 야외 일정은 미루고 쉬어 가세요.','If it rains or you feel tired, save the outdoor stop for later.') : t('관람할 공간을 하나만 골라도 좋아요. 남은 시간은 비워 두세요.','Pick just one area to explore and leave the rest of the time open.')}</small>}
              {level==='j'&&p?.address&&<small>{p.accessNote} {t('주소','Local address')} · {p.address}</small>}
              {p?.source&&<a href={p.source} target="_blank" rel="noreferrer">{t('공식 장소 안내','Official visitor information')} ↗</a>}</div></div>
        })}
        {di<days.length-1 && <p className="trip-night">{result.lodgingBase ? t(result.lodgingBase+' 근처 숙소로 복귀 · 예약 및 이동 확인 필요','Return to lodging near '+result.lodgingBase+' · confirm booking and transfer') : t('숙소에서 쉬기 · 위치와 예약 확인 필요','Rest at your lodging · confirm location and booking')}</p>}
      </section>)}
      {(result.checks?.length>0 || result.avoid) && <aside className="trip-check"><h4>{t('여행 전 확인할 조건','Before you go')}</h4>
        <p>{t('오늘의 기분','Your mood')} · {result.mood}</p><p>{t('입력한 여행 희망','Your request')} · {result.wish}</p>{result.avoid&&<p>{t('피하고 싶은 조건','Saved limits')} · {result.avoid}</p>}
        <ul>{result.checks?.map(c=><li key={c}>{c}</li>)}</ul></aside>}
      <TripFeedback {...{result,course,lang,onFeedback,onAlternative}}/>
      <Credits places={places} lang={lang}/>
    </div>
  </section>
}

export default function CourseView({result,lang,companion,onFeedback,onAlternative}) {
  const [selected, select] = useState(null)
  const detailRef = useRef(null)
  const t = (ko,en) => lang==='ko'?ko:en
  const course = result.courses.find(c=>c.id===selected)
  function choose(id) {
    select(id)
    requestAnimationFrame(()=>detailRef.current?.focus())
  }
  return <section className="result trip-results"><div className="trip-heading"><div><h2>{t(companion.ko+'의 여행 추천',companion.en+'’s travel picks')} <span>Top 3</span></h2></div>
    <small>{result.mode==='demo'?'Demo Mode':'OpenAI'}</small></div>
    <div className="trip-cards">{result.courses.map((c,i)=><button className="trip-card" key={c.id} aria-pressed={selected===c.id} onClick={()=>choose(c.id)}>
      <span className="trip-cover"><Photo place={c} lang={lang}/><b className="trip-rank">TOP {i+1}</b></span>
      <span className="trip-body"><small>{c.region}</small><strong>{c.name}</strong><span className="trip-concept">{c.description}</span>
        <span className="trip-reason">{c.reason}</span>{c.basis?.history&&<small>{c.basis.history}</small>}<span className="trip-activity">{c.places?.[0]?.activities?.[1] || c.stops[c.stops.length-1]}</span>
        <span className="trip-open">{t('자세히 보기','View itinerary')} <span aria-hidden="true">↗</span></span></span>
    </button>)}</div>
    <Credits places={result.courses} lang={lang}/>
    {course&&<CourseDetail key={course.id} {...{course,result,lang,detailRef,companion,onFeedback,onAlternative}}/>}
  </section>
}
