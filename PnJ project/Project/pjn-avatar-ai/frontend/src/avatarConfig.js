const imageRoot = import.meta.env.BASE_URL + 'images/'

const phases = {idle:['곁에 있어','Here with you'],listening:['듣고 있어','Listening'],thinking:['생각 중…','Thinking…'],response:['이야기를 건네는 중','Sharing a suggestion']}
export const companions = {
  miho: {id: 'miho', phases:{...phases,idle:['반가워! 어디부터 살펴볼까?','Hello! Where shall we start?']},  ko: '미호', en: 'Miho', portrait: imageRoot + 'Avatar_Miho.png'},
  min:  {id: 'min', phases:{...phases,idle:['반가워. 함께 떠날 하루를 그려 볼까?','Welcome. Shall we picture a day out together?']},  ko: '민', en: 'Min', portrait: imageRoot + 'Avatar_Min.png'},
}

export function companionFor(id) {
  return id === 'min' ? companions.min : companions.miho
}
