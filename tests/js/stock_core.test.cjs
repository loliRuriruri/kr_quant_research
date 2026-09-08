const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const source = fs.readFileSync('src/kr_quant/web/static/app.js', 'utf8');
const ctx = vm.createContext({escapeHtml: s => String(s).replaceAll('<','&lt;')});
vm.runInContext(source.slice(source.indexOf('function stockCoreMarkup('),source.indexOf('async function openStock(')),ctx);
test('preview preserves zero vs missing and discloses delayed sections',()=>{
  const html = ctx.stockCoreMarkup({row:{ticker:'105560',company:'<test>',value_score:0,per:null},as_of:'2026-09-07'});
  assert(html.includes('&lt;test>'));
  assert(html.includes('<h3>0</h3>'));
  assert(html.includes('자료 없음'));
  assert(html.includes('2026-09-07'));
  assert(html.includes('실시간 가격이 아닙니다'));
  assert(html.includes('기업 개요·지배구조, 뉴스·외부 시세, 기술 분석·수급·공시'));
});

test('late preview cannot replace another stock; full failure keeps core with retry', async()=>{
  const nodes = new Map();
  const node = key => {
    if (!nodes.has(key)) nodes.set(key,{innerHTML:'',textContent:'',style:{},classList:{contains:()=>false},addEventListener:()=>{}});
    return nodes.get(key);
  };
  const pending = [];
  const env = vm.createContext({$:node, padTicker: x=>String(x).padStart(6,'0'),stockDrawerRequest:0,
    openDrawerUi:()=>{},publicShareMode:false,escapeHtml:String,
    stockCoreMarkup: d=>d.row.company,
    api:path=>new Promise((resolve,reject)=>pending.push({path,resolve,reject}))});
  const start=source.indexOf('async function openStock(');
  vm.runInContext(source.slice(start,source.indexOf('\nasync function loadTier1StockInsights(',start)),env);
  const first=env.openStock('105560');
  const second=env.openStock('005930');
  pending[0].resolve({row:{ticker:'105560',company:'OLD'}});
  await Promise.resolve();
  assert.notEqual(node('#drawer-body').innerHTML,'OLD');
  pending[2].resolve({row:{ticker:'005930',company:'NEW'}});
  await Promise.resolve();
  assert.equal(node('#drawer-body').innerHTML,'NEW');
  pending[1].reject(new Error('old failed'));
  pending[3].reject(new Error('provider timeout'));
  await Promise.all([first,second]);
  assert.equal(node('#drawer-body').innerHTML,'NEW');
  assert.match(node('#stock-enrichment-status').innerHTML,/다시 조회/);
});
