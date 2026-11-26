export function Field({label,hint,children,wide=false}) {
  return <label className={'field'+(wide?' wide':'')}><span>{label}</span>{children}{hint&&<small>{hint}</small>}</label>
}
export function Choices({options,value,onChange,multiple=false,label}) {
  return <div className="chips" role="group" aria-label={label}>{options.map(([key,name])=>{
    const on=multiple?value.includes(key):value===key
    return <button type="button" className={on?'chip on':'chip'} aria-pressed={on} key={key}
      onClick={()=>onChange(multiple ? (on ? value.filter(item=>item!==key):[...value,key]) : (on?'':key))}>{name}</button>
  })}</div>
}
export function Alert({children}) {return children ? <p className="error" role="alert">{children}</p>:null}
export function BusyLabel({busy,children,t}) {return busy?t('Please wait…','잠시만 기다려 주세요…'):children}

const palace = {name:['Gyeongbokgung Palace','경복궁 근정전'],src:'/photos/gyeongbok.jpg',author:'Basile Morin',
  source:'https://commons.wikimedia.org/wiki/File:Front_view_of_the_Imperial_Throne_Hall_Geunjeongjeon_at_Gyeongbokgung_Palace_with_blue_sky_in_Seoul.jpg',
  license:'CC BY-SA 4.0',licenseUrl:'https://creativecommons.org/licenses/by-sa/4.0/'}
export function PhotoCredit({photo,t}) {
  return photo&&<small className="credit">{photo.author} · <a href={photo.source} target="_blank" rel="noreferrer" title={photo.title}>Wikimedia Commons</a> · <a href={photo.licenseUrl} target="_blank" rel="noreferrer">{photo.license}</a> · {t('Resized JPEG, cropped to fit','JPEG 축소·화면 맞춤')}</small>
}
export function HeroImage({t}) {return <figure className="palace"><img src={palace.src} alt={t(...palace.name)}/><figcaption><span>{t(...palace.name)}</span><PhotoCredit photo={palace} t={t}/></figcaption></figure>}
export function Steps({step,t}) {
  const labels=[t('Check-in','기분 확인'),t('Trip details','여행 조건'),t('Itineraries','추천 코스')]
  return <nav className="steps" aria-label={t('Planner progress','여행 계획 진행 단계')}>{labels.map((l,i)=><span key={i} aria-current={i===step?'step':undefined}><b>{i+1}</b>{l}</span>)}</nav>
}
