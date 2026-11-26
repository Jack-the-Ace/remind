// Small, auditable bilingual vocabulary. Suggestions have no effect until confirmed in the form.
const terms={
  nature:/forest|greenery|nature|woodland|숲|자연/i,quiet:/quiet|peaceful|calm place|조용|한적/i,
  rest:/relax|take a break|\brest\b|쉬고|휴식|힐링/i,history:/historic|history|palace|역사|고궁|궁궐/i,
  culture:/culture|cultural|문화/i,shopping:/shopping|쇼핑/i,kpop:/k[ -]?pop|케이팝|아이돌/i,
  food:/food|음식|맛집/i,night:/night view|야경/i,photo:/photograph|사진/i,
  market:/market|시장/i,art:/exhibit|galler|art museum|전시|미술/i,walk:/\bwalk(ing)?\b|stroll|산책/i,
  new:/something new|discover|새로운|색다른/i,indoor:/indoors?|실내/i,outdoor:/outdoors?|야외/i
}
export function suggestions(text){
  if(!text.trim())return {interests:[],avoid:[],indoor:null}
  // Clauses with negation require manual confirmation, instead of turning them into a positive interest.
  const parts=text.split(/[.!?\n,;]|\bbut\b|하지만|대신/iu)
  const interests=new Set(),avoid=new Set()
  for(const part of parts){
    const negative=/\b(no|not|avoid|without|don.t|skip)\b|싫|피하|피하고|제외|말고|원치|원하지|않/.test(part.toLowerCase())
    for(const [k,re] of Object.entries(terms))if(re.test(part))(negative?avoid:interests).add(k)
    if(/crowd|bustling|혼잡|붐비|붐비는|북적/i.test(part))(negative||/붐비지|덜 붐비|한산/.test(part)?avoid:interests).add('busy')
  }
  return {interests:[...interests].filter(k=>!avoid.has(k)),avoid:[...avoid],indoor:/(indoor(s)? only|only indoors?|실내\s*(만|활동만))/.test(text.toLowerCase())?'only':null}
}
