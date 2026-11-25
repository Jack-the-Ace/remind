import {useId, useState} from 'react'
import {companions} from './avatarConfig'
import {api, errorText} from './client'
import './companions.css'

export function AvatarSelector({avatarId, lang, onChange, disabled=false}) {
  const name = useId()
  return <fieldset className="companions" disabled={disabled}>
    <legend>{lang==='ko'?'나의 여행 동반자 선택':'Choose your travel companion'}</legend>
    <div className="companion-options">{Object.values(companions).map(a =>
      <label key={a.id} className="companion-option">
        <input type="radio" name={name} value={a.id} checked={avatarId===a.id} onChange={()=>onChange(a.id)}/>
        <span className="companion-tile" data-portrait={a.id}>
          <span className="companion-picture"><img src={a.portrait} alt="" width="1086" height="1448"/></span>
          <span className="companion-caption">{lang==='ko'?a.ko+' ('+a.en+')':a.en}
            <span aria-hidden="true" className="companion-check">{avatarId===a.id?'✓':''}</span>
          </span>
        </span>
      </label>
    )}</div>
  </fieldset>
}

export function SavedAvatarSelector({user, lang, onSaved, disabled=false}) {
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  async function change(avatarId) {
    setError('')
    setSaving(true)
    try {
      const saved = await api('me/avatar','PUT',{avatarId})
      onSaved(user.id, saved.avatarId)
    } catch (e) {
      setError(errorText(e.message,lang))
    } finally {
      setSaving(false)
    }
  }
  return <div className="saved-companion">
    <AvatarSelector avatarId={user.avatarId} lang={lang} onChange={change} disabled={saving||disabled}/>
    {saving&&<small role="status">{lang==='ko'?'저장 중…':'Saving…'}</small>}
    {error&&<p className="error" role="alert">{error}</p>}
  </div>
}
