export function freshTrip() {
  return {
    days:'', startDate:'', lodging:'', lodgingSource:null, startPoint:'', returnPoint:'',
    companions:'', transport:'', diet:'', walking:'any', budgetKrw:'', indoor:'any',
    weather:'unknown', interests:[], mustVisit:[], avoid:[], locked:[], availableMinutes:'', avoidHeights:false
  }
}

export function withFiveDayExample(trip, t) {
  const existingDays = new Set(trip.locked.map(segment => Number(segment.day)))
  const examples = [1,2,3].filter(day => !existingDays.has(day)).map(day => ({
    day, label:t('Personal itinerary','개인 일정'), place:'', start:'', end:'', source:'example'
  }))
  return {
    ...trip, days:Math.max(5, Number(trip.days)||1), locked:[...trip.locked, ...examples],
    lodging:trip.lodging || t('Example lodging in Seoul','서울 숙소 예시'),
    lodgingSource:trip.lodging ? (trip.lodgingSource || 'user') : 'example'
  }
}
