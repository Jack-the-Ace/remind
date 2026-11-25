import { useState } from 'react'
import {flushSync} from 'react-dom'

import {companionFor} from './avatarConfig'

const introduction = (avatar) => [
  [`안녕하세요, 여러분과 여행 관련 고민을 함께 생각할, "${avatar.ko}"입니다.`, `Hello! I’m ${avatar.en}, here to think through your travel questions with you.`],
  ['지금부터 심리 테스트를 시작하겠습니다.', 'Let’s begin the travel personality survey.'],
  ['앞으로 우리의 여행 스타일을 정할 중요한 내용이니까, 솔직하게 대답해주세요!', 'Your answers will shape our travel style, so choose what feels true to you!'],
]
const completion = [
  ['기본 심리 테스트가 완료되었습니다!', 'Your travel personality survey is complete!'],
  ['다시 회원가입 페이지로 돌아가서 회원가입을 완료해주세요!', 'Return to the sign-up form to finish creating your account!'],
]
export function Avatar({avatarId,size='main',lang='ko'}) {
  const avatar = companionFor(avatarId)
  return <div className={'miho '+size} data-avatar={avatar.id}><div className="miho-pose">
    <img src={avatar.portrait} alt={avatar[lang]} width="1086" height="1448"/>
    <i className="lid left" aria-hidden="true"/><i className="lid right" aria-hidden="true"/>
  </div></div>
}
export function Scene({avatarId,lang,finish,onNext}){
  const [line,setLine]=useState(0)
  const lines=finish?completion:introduction(companionFor(avatarId))
  const last=finish && line===lines.length-1
  function advance(){
    if(line+1<lines.length){setLine(line+1);return}
    if(finish)return
    if(document.startViewTransition && !matchMedia('(prefers-reduced-motion: reduce)').matches){
      document.startViewTransition(()=>flushSync(onNext))
    }else onNext()
  }
  return <section className="scene">
    <button autoFocus className="scene-stage" onClick={advance} disabled={last}>
      <Avatar size="large" {...{avatarId,lang}}/><strong aria-live="polite">{lines[line][lang==='ko'?0:1]}</strong>
      {!last && <small>{lang==='ko'?'화면을 눌러 계속':'Tap to continue'}</small>}
    </button>
    {last && <button autoFocus className="primary float" onClick={onNext}>{lang==='ko'?'회원가입 계속':'Continue sign-up'}</button>}
  </section>
}
