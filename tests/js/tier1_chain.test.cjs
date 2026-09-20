// Tier1 chain configurator: four hops map to tier1_* settings fields.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('src/kr_quant/web/static/app.js', 'utf8');
function extract(start, end) {
  const from = source.indexOf(start);
  const to = source.indexOf(end, from + start.length);
  assert(from >= 0 && to > from);
  return source.slice(from, to);
}
const ctx = vm.createContext({});
vm.runInContext(extract('const TIER1_SLOTS = [', '\nfunction paintAiArchitectureCard(')
  + '\nglobalThis.__tier1 = {TIER1_SLOTS, saveTier1Config};', ctx);
const {TIER1_SLOTS, saveTier1Config} = ctx.__tier1;
test('tier1 slots cover all four hops', () => {
  assert.equal(TIER1_SLOTS.map((s) => s.key).join(','), 'routine,routine_paid,analysis,analysis_pro');
  for (const s of TIER1_SLOTS) {
    assert.match(s.provId, /^tier1-/);
    assert.match(s.modelId, /^tier1-/);
  }
});
test('tier1 save posts tier1_* fields', async () => {
  const values = {
    'tier1-routine-provider': 'opencode_go', 'tier1-routine-model': 'deepseek/deepseek-v4.1-flash',
    'tier1-routine-paid-provider': 'openrouter', 'tier1-routine-paid-model': 'deepseek/deepseek-v4-flash-0731',
    'tier1-analysis-provider': 'xai', 'tier1-analysis-model': 'grok-4.6',
    'tier1-analysis-pro-provider': 'openrouter', 'tier1-analysis-pro-model': 'deepseek/deepseek-v4-pro-0813',
  };
  const seen = {};
  const tctx = vm.createContext({
    document: {getElementById: (id) => ({value: values[id] ?? ''})},
    $: () => ({textContent: ''}),
    api: async (url, opts) => {
      seen.url = url;
      seen.body = JSON.parse(opts.body);
      return {tier1: {}};
    },
    renderTier1Config: () => {},
    renderConnections: () => ({catch() {}}),
  });
  vm.runInContext(extract('const TIER1_SLOTS = [', '\nfunction paintAiArchitectureCard('), tctx);
  await tctx.saveTier1Config();
  assert.equal(seen.url, '/api/settings');
  assert.equal(JSON.stringify(seen.body), JSON.stringify({
    tier1_routine_provider: 'opencode_go', tier1_routine_model: 'deepseek/deepseek-v4.1-flash',
    tier1_routine_paid_provider: 'openrouter', tier1_routine_paid_model: 'deepseek/deepseek-v4-flash-0731',
    tier1_analysis_provider: 'xai', tier1_analysis_model: 'grok-4.6',
    tier1_analysis_pro_provider: 'openrouter', tier1_analysis_pro_model: 'deepseek/deepseek-v4-pro-0813',
  }));
});

test('opencode_go tier1 select includes muse-spark-1.3-contributor', () => {
  const mctx = vm.createContext({
    document: {
      createElement: (tag) => ({ tag, value: '', textContent: '', title: '' }),
    },
  });
  vm.runInContext(
    extract('const PROVIDER_LABELS = {', '\nfunction paintAiArchitectureCard(') +
    '\nglobalThis.__m = {fillTier1ModelSelect, PROVIDER_MODELS};',
    mctx
  );
  const {fillTier1ModelSelect, PROVIDER_MODELS} = mctx.__m;

  const mockSelect = {
    children: [],
    appendChild(opt) { this.children.push(opt); },
    set innerHTML(val) { this.children = []; },
    value: '',
  };

  assert(PROVIDER_MODELS.opencode_go.includes('muse-spark-1.3-contributor'));
  fillTier1ModelSelect(mockSelect, 'opencode_go', 'muse-spark-1.3-contributor');
  const goOptions = mockSelect.children.map((o) => o.value);
  assert(goOptions.includes('muse-spark-1.3-contributor'));
  assert.equal(mockSelect.value, 'muse-spark-1.3-contributor');
});
