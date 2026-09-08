const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
test('season card has four sections and retains legacy response compatibility', async()=>{
  const source=fs.readFileSync('src/kr_quant/web/static/app.js','utf8');
  const container={innerHTML:''};
  const env=vm.createContext({$:()=>container,api:async()=>({ok:true,headline:'관찰',seasonality_brief:'근거',sample_caution:'주의',key_catalysts:[]}),
    renderTier1Unavailable:()=>true,escapeHtml:String,appendTier1Meta:()=>{},setTimeout,clearTimeout});
  vm.runInContext(source.slice(source.indexOf('async function loadSeasonalityTier1Briefing('),source.indexOf('async function loadTradeTier1Briefing(')),env);
  await env.loadSeasonalityTier1Briefing();
  for(const label of ['결론 ·','근거 ·','주의점 ·','다음 확인 ·']) assert(container.innerHTML.includes(label));
  assert(!container.innerHTML.includes('30개년'));
  assert(container.innerHTML.includes('이전 형식'));
});

test('pending request is not duplicated; slow notice and failure clear correctly', async()=>{
  const source=fs.readFileSync('src/kr_quant/web/static/app.js','utf8');
  const container={innerHTML:''}; let reject, timer, calls=0, cleared=false;
  const env=vm.createContext({$:()=>container,api:()=>{calls++;return new Promise((_,r)=>reject=r);},
    renderTier1Unavailable:()=>{container.innerHTML='unavailable';return false;},escapeHtml:String,
    appendTier1Meta:()=>{},setTimeout:fn=>{timer=fn;return 1;},clearTimeout:()=>{cleared=true;}});
  vm.runInContext(source.slice(source.indexOf('async function loadSeasonalityTier1Briefing('),source.indexOf('async function loadTradeTier1Briefing(')),env);
  const pending=env.loadSeasonalityTier1Briefing();
  await env.loadSeasonalityTier1Briefing(); assert.equal(calls,1);
  timer(); assert(container.innerHTML.includes('응답이 지연'));
  reject(new Error('offline')); await pending;
  assert.equal(container.innerHTML,'unavailable'); assert.equal(container._tier1Pending,false); assert(cleared);
});
