import assert from 'node:assert/strict'
import test from 'node:test'
import {freshTrip,withFiveDayExample} from '../src/tripDraft.js'
import {suggestions} from '../src/interpret.js'
const en=text=>text

test('Example preserves the existing stay, number of days and bookings',()=>{
  const booking={day:'2',label:'Lunch appointment',place:'Jongno',start:'',end:'',source:'user'}
  const week={...freshTrip(),days:'7',lodging:'Booked hotel',lodgingSource:'user',locked:[booking]}
  const result=withFiveDayExample(week,en)
  assert.equal(result.days,7)
  assert.equal(result.lodging,'Booked hotel')
  assert.equal(result.lodgingSource,'user')
  assert.deepEqual(result.locked,[booking,...[1,3].map(day=>({day,label:'Personal itinerary',place:'',start:'',end:'',source:'example'}))])
  assert.deepEqual(withFiveDayExample(result,en),result)
  assert.deepEqual(week.locked,[booking])
})
test('Example-only lodging and appointments retain provenance and no invented times',()=>{
  const result=withFiveDayExample(freshTrip(),en)
  assert.equal(result.days,5)
  assert.equal(result.lodgingSource,'example')
  assert.ok(result.locked.every(s=>s.source==='example' && !s.start && !s.end))
})
test('Bilingual keyword suggestions preserve a negated request',()=>{
  assert.deepEqual(suggestions('A forest walk, but no crowds').interests,['nature','walk'])
  assert.deepEqual(suggestions('A forest walk, but no crowds').avoid,['busy'])
  assert.deepEqual(suggestions('실내 활동만').indoor,'only')
  assert.deepEqual(suggestions('쇼핑은 피하고 싶어요').avoid,['shopping'])
})
