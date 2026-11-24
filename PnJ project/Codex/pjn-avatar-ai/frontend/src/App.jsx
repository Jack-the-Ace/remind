import { useEffect, useMemo, useState } from 'react'
import { copy } from './copy'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const STORAGE = 'pnj-avatar-lab-v1'

function loadState() { try { return JSON.parse(localStorage.getItem(STORAGE)) || {} } catch { return {} } }
function Field({ label, value, onChange, placeholder, area = false }) { const Tag = area ? 'textarea' : 'input'; return <label className="field"><span>{label}</span><Tag value={value || ''} placeholder={placeholder} onChange={e => onChange(e.target.value)} rows={area ? 3 : undefined} /></label> }
function Avatar({ t }) { return <section className="avatar-card"><div className="avatar" aria-label="PnJ avatar"><span>✦</span><div className="face">◡</div></div><div><strong>{t.avatarName}</strong><p>{t.avatarText}</p></div></section> }

export default function App() {
  const saved = useMemo(loadState, [])
  const [lang, setLang] = useState(saved.lang || 'ko')
  const [users, setUsers] = useState(saved.users || [])
  const [userId, setUserId] = useState(saved.userId || '')
  const [profile, setProfile] = useState(null)
  const [mood, setMood] = useState('')
  const [result, setResult] = useState(null)
  const [results, setResults] = useState(saved.results || [])
  const [editing, setEditing] = useState(false)
  const [status, setStatus] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const t = copy[lang]

  useEffect(() => {
    if (!users.length) fetch(`${API}/api/seed-users`).then(r => r.ok ? r.json() : Promise.reject()).then(data => { setUsers(data); setUserId(data[0].id); setProfile(data[0]) }).catch(() => setError('서버에 연결할 수 없습니다. FastAPI 서버를 실행했는지 확인해주세요.'))
  }, [])
  useEffect(() => { localStorage.setItem(STORAGE, JSON.stringify({ lang, users, userId, results })) }, [lang, users, userId, results])
  useEffect(() => { const next = users.find(u => u.id === userId); if (next) { setProfile(structuredClone(next)); setEditing(false); setResult(null); setMood('') } }, [userId])
  const update = (key, value) => setProfile(p => ({ ...p, [key]: value }))
  const updateHistory = (index, key, value) => setProfile(p => ({ ...p, history: p.history.map((item, i) => i === index ? { ...item, [key]: value } : item) }))
  const addHistory = () => setProfile(p => ({ ...p, history: [...(p.history || []), { title: '', destination: '', theme: '', selected: null, satisfaction: null, note: '' }] }))
  const removeHistory = index => setProfile(p => ({ ...p, history: p.history.filter((_, i) => i !== index) }))
  const pick = id => setUserId(id)
  const saveProfile = () => {
    if (!profile.name.trim() || !profile.personalityNotes.trim() || !profile.travelPreferences.trim()) return setStatus(t.required)
    const cleaned = { ...profile, history: profile.history.filter(item => item.title.trim()) }
    setProfile(cleaned); setUsers(all => all.map(u => u.id === cleaned.id ? cleaned : u)); setStatus(t.saved); setEditing(false)
  }
  const request = async () => {
    if (!mood.trim()) return setError(t.emptyMood)
    setBusy(true); setError(''); setStatus(t.loading)
    try {
      const response = await fetch(`${API}/api/recommendations`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ profile, mood, language: lang }) })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail?.message || 'Request failed')
      const entry = { id: crypto.randomUUID(), at: new Date().toLocaleString(lang === 'ko' ? 'ko-KR' : 'en-US'), mood, recommendation: data.recommendation, model: data.model, profileName: profile.name }
      setResult(entry); setResults(all => [entry, ...all].slice(0, 12)); setStatus('')
    } catch (e) { setError(e.message || 'Unknown API error'); setStatus('') } finally { setBusy(false) }
  }
  const prior = results.filter(r => r.id !== result?.id && r.profileName === profile?.name)
  if (!profile) return <main className="shell"><p className="loading">Loading profiles…</p>{error && <p className="error">{error}</p>}</main>
  return <main className="shell"><header><div><p className="eyebrow">{t.eyebrow}</p><h1>{t.title.split('\n').map((line, i) => <span key={i}>{line}<br /></span>)}</h1><p className="lede">{t.subtitle}</p></div><div className="language" aria-label={t.language}><button className={lang === 'ko' ? 'active' : ''} onClick={() => setLang('ko')}>KO</button><button className={lang === 'en' ? 'active' : ''} onClick={() => setLang('en')}>EN</button></div></header>
    <Avatar t={t} />
    <section className="panel"><div className="panel-head"><h2>{t.profile}</h2><button className="text-button" onClick={() => setEditing(x => !x)}>{editing ? '×' : t.editProfile}</button></div><label className="field"><span>{t.selectUser}</span><select value={userId} onChange={e => pick(e.target.value)}>{users.map(u => <option key={u.id} value={u.id}>{u.name}</option>)}</select></label>
      <p className="notice">ⓘ {t.fictional}</p>
      {editing ? <div className="profile-form"><Field label={t.name} value={profile.name} onChange={v => update('name', v)} /><Field label={t.age} value={profile.ageRange} onChange={v => update('ageRange', v)} /><Field label={t.mbti} value={profile.mbti} onChange={v => update('mbti', v)} /><Field label={t.personality} value={profile.personalityNotes} onChange={v => update('personalityNotes', v)} area /><Field label={t.preferences} value={profile.travelPreferences} onChange={v => update('travelPreferences', v)} area /><Field label={t.avoid} value={profile.avoidConditions} onChange={v => update('avoidConditions', v)} area /><div className="history editor"><h3>{t.history}</h3>{profile.history.map((item, i) => <div className="history-edit" key={i}><Field label={t.historyLabel} value={item.title} onChange={v => updateHistory(i, 'title', v)} /><Field label={t.destination} value={item.destination} onChange={v => updateHistory(i, 'destination', v)} /><Field label={t.theme} value={item.theme} onChange={v => updateHistory(i, 'theme', v)} /><Field label={`${t.selected} / ${t.notSelected}`} value={item.selected === null ? '' : item.selected ? 'yes' : 'no'} onChange={v => updateHistory(i, 'selected', v === '' ? null : v.toLowerCase() === 'yes')} placeholder="yes / no" /><Field label={`${t.satisfaction} (1–5)`} value={item.satisfaction ?? ''} onChange={v => updateHistory(i, 'satisfaction', v ? Number(v) : null)} /><Field label="Note" value={item.note} onChange={v => updateHistory(i, 'note', v)} area /><button className="remove" onClick={() => removeHistory(i)}>×</button></div>)}<button className="add-history" onClick={addHistory}>+ {t.historyLabel}</button></div><button className="secondary" onClick={saveProfile}>{t.save}</button></div> : <div className="snapshot"><div><b>{t.personality}</b><p>{profile.personalityNotes}</p></div><div className="meta"><span>{profile.ageRange || '—'}</span><span>{profile.mbti || 'MBTI —'}</span></div><div><b>{t.preferences}</b><p>{profile.travelPreferences}</p></div><div><b>{t.avoid}</b><p>{profile.avoidConditions || '—'}</p></div></div>}
      <div className="history"><h3>{t.history}</h3>{profile.history?.length ? profile.history.map((h, i) => <div className="history-item" key={i}><b>{h.title}</b><p>{h.destination} · {h.theme}</p><small>{h.selected ? t.selected : t.notSelected}{h.satisfaction ? ` · ${t.satisfaction} ${'★'.repeat(h.satisfaction)}` : ''}{h.note ? ` · ${h.note}` : ''}</small></div>) : <p className="empty">{t.noHistory}</p>}</div>
    </section>
    <section className="panel mood"><h2>{t.mood}</h2><textarea value={mood} onChange={e => setMood(e.target.value)} placeholder={t.moodPlaceholder} rows="4" /><button className="primary" disabled={busy} onClick={request}>{busy ? t.asking : t.ask}</button>{status && <p className="status">{status}</p>}{error && <div className="error"><b>{t.error}</b><br />{error}</div>}</section>
    {result && <Result entry={result} t={t} />}
    <section className="previous"><h2>{t.previous}</h2>{prior.length ? prior.slice(0, 3).map(entry => <button className="prior" key={entry.id} onClick={() => setResult(entry)}><span>{entry.at}</span><b>{entry.mood}</b><small>{entry.recommendation.travelTheme}</small></button>) : <p className="empty">{t.noResults}</p>}</section>
  </main>
}

function Result({ entry, t }) { const r = entry.recommendation; return <section className="result"><div className="result-top"><span className="pill">{t.result}</span><small>{t.model}: {entry.model}</small></div><div className="speech"><p>{r.empathyMessage}</p><p>{r.moodSummary}</p></div><div className="theme"><span>{t.theme}</span><h2>{r.travelTheme}</h2></div><div className="cards">{r.recommendedDestinations.map((d, i) => <article key={i}><span>0{i + 1}</span><h3>{d.name}</h3><p className="region">{d.region}</p><p>{d.reason}</p><small>{r.recommendationReasons[i]}</small></article>)}</div><div className="result-grid"><Info title={t.activities} items={r.preferredActivities} /><Info title={t.keptAway} items={r.avoidConditions} /><div><h3>{t.changed}</h3><p>{r.changeFromPrevious}</p></div><div><h3>{t.confidence}</h3><p>{r.confidenceNotes}</p></div></div></section> }
function Info({ title, items }) { return <div><h3>{title}</h3><div className="chips">{items.length ? items.map((x, i) => <span key={i}>{x}</span>) : <span>—</span>}</div></div> }
