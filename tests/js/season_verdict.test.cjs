const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('src/kr_quant/web/static/app.js', 'utf8');
const ctx = vm.createContext({escapeHtml: value => String(value).replaceAll('<', '&lt;')});
vm.runInContext(source.slice(source.indexOf('function seasonPlainVerdict('), source.indexOf('function appendSeasonHoldoutPanel(')), ctx);
test('weak current evidence is not an event cancellation or forecast', () => {
  const v = ctx.seasonPlainVerdict({current_status: 'BROKEN', current_confirmation_evidence: ['3개월 수익률 -15.4%', '퀀트 점수 19.6'], current_confirmation_missing: ['수급']});
  assert.match(v.title, /단독 판단 보류/);
  assert.match(v.reason, /-15%.*48점/);
  assert.match(v.reason, /취소나 향후 하락을 확인한 것은 아닙니다/);
  assert.match(v.evidence, /-15.4%/);
  assert.equal(v.missing, '수급');
  assert.match(ctx.seasonPlainVerdict({}).title, /자료 부족/);
});
test('zero diagnostic folds show conclusion, not empty result cards', () => {
  const html = ctx.seasonEmptyDiagnostic({summary: {diagnostic_count: 0}, folds: [2023,2024,2025].map(test_year => ({test_year,status:'INSUFFICIENT_TRAIN'}))});
  assert.match(html, /독립 연도 비교는 아직 불가/);
  assert.match(html, /신규 상장/);
  assert(!html.includes('season-holdout-fold'));
  assert(!html.includes('50bps'));
  assert.equal(ctx.seasonEmptyDiagnostic({summary:{diagnostic_count:1}}), '');
  assert.match(ctx.seasonEmptyDiagnostic({summary:{diagnostic_count:0},folds:[{test_year:2025,status:'PRICE_PATH_MISSING'}]}), /전략 실패라는 뜻은 아닙니다/);
});
