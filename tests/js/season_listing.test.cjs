// Dependency-free tests execute the actual browser functions in an isolated VM.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync('src/kr_quant/web/static/app.js', 'utf8');
function extract(start, end) {
  const from = source.indexOf(start);
  const to = source.indexOf(end, from + start.length);
  assert(from >= 0 && to > from);
  return source.slice(from, to);
}

(async () => {
  const narrative = vm.createContext({});
  vm.runInContext(extract('function seasonFailureObservations(', '\nfunction renderDiscDeepPlaybook('), narrative);
  const notes = narrative.seasonFailureObservations({years_track: [
    {year: 2020, return: -.2}, {year: 2021, return: 0}, {year: 2022, return: null},
    {year: 2023, return: .1}], failed_analysis: ['UNSUPPORTED_CAUSE']});
  assert.equal(notes.length, 2);
  assert(notes[0].text.includes('원인 미확인') && notes[1].text.includes('보합'));
  assert(!JSON.stringify(notes).includes('UNSUPPORTED_CAUSE'));
  const requests = [];
  const ctx = vm.createContext({URLSearchParams, encodeURIComponent, api: async path => {
    requests.push(path);
    return {patterns: [{signal_id: 'wrong', playbook: {bad: true}},
      {signal_id: 'chosen', playbook: {correct: true}}]};
  }});
  vm.runInContext(extract('async function resolveSeasonListDetail(', '\nasync function openSeasonListRegistration('), ctx);
  const row = {detail_required: true, ticker: '005930', signal_id: 'chosen', generation_id: 'g', lookback_years: 0};
  const detail = await ctx.resolveSeasonListDetail(row);
  assert.equal(detail.playbook.correct, true);
  assert.equal(detail.lookback_years, 0);
  assert.match(requests[0], /lookback_years=0&generation_id=g/);
  await assert.rejects(ctx.resolveSeasonListDetail({...row, signal_id: 'missing'}));
  const full = {ticker: '005930', playbook: {full: true}};
  assert.equal(await ctx.resolveSeasonListDetail(full), full);

  // A slow previous filter must never overwrite the more recent request.
  const pending = [];
  const applied = [];
  const tbody = {innerHTML: '', closest: () => ({parentElement: {}}), querySelectorAll: () => []};
  const count = {textContent: ''};
  const env = vm.createContext({URLSearchParams,
    $: selector => selector === '#discovery-ranked-body' ? tbody : selector === '#discovery-count-val' ? count : null,
    document: {getElementById: () => null},
    seasonalitySearchQuery: () => '', currentV11Horizon: 90, currentV11Lookback: 0,
    currentV11ExcludeExpired: true, discoveryListRequest: 0, discoveryRows: [],
    api: path => new Promise(resolve => pending.push({path, resolve})),
    setSeasonalityAsOf: value => applied.push(value.id), renderSeasonPager: () => {}, escapeHtml: String,
  });
  vm.runInContext(extract('async function loadDiscoveryRanked(', '\nasync function loadAIExplanations('), env);
  const older = env.loadDiscoveryRanked();
  const newer = env.loadDiscoveryRanked();
  pending[1].resolve({id: 'new', rows: [], count: 0});
  await newer;
  pending[0].resolve({id: 'old', rows: [], count: 99});
  await older;
  assert.deepEqual(applied, ['new']);
  assert.equal(count.textContent, '0개');
  assert.match(pending[0].path, /view=summary&offset=0&limit=50/);
  console.log('season listing JS: exact detail, period=0, missing signal, full-row compatibility, stale response PASS');
})().catch(error => {console.error(error); process.exitCode = 1;});
