const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
test('season card has four sections and retains legacy response compatibility', async()=>{
  const source=fs.readFileSync('src/kr_quant/web/static/app.js','utf8');
  const container={innerHTML:''};
  const env=vm.createContext({$:()=>container,api:async()=>({ok:true,headline:'관찰',seasonality_brief:'근거',sample_caution:'주의',key_catalysts:[]}),
    renderTier1Unavailable:()=>true,escapeHtml:String,appendTier1Meta:()=>{}});
  vm.runInContext(source.slice(source.indexOf('async function loadSeasonalityTier1Briefing('),source.indexOf('async function loadTradeTier1Briefing(')),env);
  await env.loadSeasonalityTier1Briefing();
  for(const label of ['결론 ·','근거 ·','주의점 ·','다음 확인 ·']) assert(container.innerHTML.includes(label));
  assert(!container.innerHTML.includes('30개년'));
  assert(container.innerHTML.includes('이전 형식'));
});
