const KEY='pnj-signup-v1'
export function emptyDraft(version){return {version,id:'',nickname:'',mbti:'',avoid:'',avatarId:'miho',answers:{},index:0,traits:null,screen:'form'}}
export function loadDraft(version){
  try {
    const saved=JSON.parse(sessionStorage.getItem(KEY))
    if(saved?.version===version)return {...emptyDraft(version),...saved}
  } catch {}
  return emptyDraft(version)
}
export function storeDraft({version,id,nickname,mbti,avoid,avatarId,answers,index,traits,screen}){
  sessionStorage.setItem(KEY,JSON.stringify({version,id,nickname,mbti,avoid,avatarId,answers,index,traits,screen}))
}
export function clearDraft(){sessionStorage.removeItem(KEY)}
