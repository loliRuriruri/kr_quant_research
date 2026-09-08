const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('src/kr_quant/web/static/app.js','utf8');
const env=vm.createContext({escapeHtml:String});
vm.runInContext(source.slice(source.indexOf('function aiUsageBadge('),source.indexOf('async function loadDashTier1Briefing(')),env);
test('only confirmed AI gets a small badge; cache does not change provenance',()=>{
  for(const res of [{},{ai_generated:false},{ai_generated:'true'},{ai_generated:true,status:'DETERMINISTIC_FALLBACK'},{ai_generated:true,status:'UNAVAILABLE'}]) assert.equal(env.aiUsageBadge(res),'');
  assert.match(env.aiUsageBadge({ai_generated:true,status:'GENERATED',cache:{hit:true}}),/>AI<\/span>/);
  assert.match(env.aiUsageBadge({ai_generated:true}),/aria-label=/);
});
test('shared meta uses badge and is idempotent',()=>{
  let html=''; let inserted=false;
  const card={querySelector:()=>inserted,insertAdjacentHTML:(_,s)=>{html+=s;inserted=true;}};
  const container={querySelector:()=>card};
  env.appendTier1Meta(container,{ai_generated:false,status:'INSUFFICIENT_EVIDENCE'});
  assert(!html.includes('ai-usage-badge')); assert(html.includes('AI 생성 미확인'));
  const first=html; env.appendTier1Meta(container,{ai_generated:true}); assert.equal(html,first);
});
