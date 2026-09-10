// OpenCode Zen catalog: every curated model must carry badge/tokens/desc,
// and ids shared with OpenRouter must show Zen prices under the opencode provider.
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
vm.runInContext(extract('const PROVIDER_LABELS = {', '\nfunction applyModelOptions(')
  + '\nglobalThis.__catalog = {PROVIDER_LABELS, PROVIDER_MODELS, MODEL_TOKEN_INFO, MODEL_TOKEN_INFO_OVERRIDES, modelTokenInfo};', ctx);
const {PROVIDER_LABELS, PROVIDER_MODELS, modelTokenInfo} = ctx.__catalog;
test('opencode catalog is complete and zen-priced', () => {
  assert.equal(PROVIDER_LABELS.opencode, 'OpenCode Zen');
  assert.equal(PROVIDER_MODELS.opencode.length, 8);
  for (const m of PROVIDER_MODELS.opencode) {
    const info = modelTokenInfo('opencode', m);
    assert(info && info.badge && info.tokens && info.desc, m);
    assert.match(info.tokens, /\$\d+\.\d{2} \/ 1M/, m);
  }
  assert.match(modelTokenInfo('opencode', 'deepseek/deepseek-v4-flash-0731').tokens, /\$0\.14/);
  assert.match(modelTokenInfo('openrouter', 'deepseek/deepseek-v4-flash-0731').tokens, /\$0\.07/);
  assert.match(modelTokenInfo('opencode', 'openai/gpt-5.6-luna').tokens, /\$0\.20/);
  assert.match(modelTokenInfo('opencode', 'google/gemini-3.7-flash').tokens, /\$1\.50/);
});
test('opencode go catalog matches the go gateway lineup', () => {
  assert.equal(PROVIDER_LABELS.opencode_go, 'OpenCode Go');
  assert.equal(PROVIDER_MODELS.opencode_go.length, 8);
  for (const m of PROVIDER_MODELS.opencode_go) {
    const info = modelTokenInfo('opencode_go', m);
    assert(info && info.badge && info.tokens && info.desc, m);
    assert.match(info.tokens, /\$\d+\.\d{2} \/ 1M/, m);
  }
  assert.match(modelTokenInfo('opencode_go', 'deepseek-v4-pro').tokens, /\$0\.66/);
  assert.match(modelTokenInfo('opencode_go', 'deepseek/deepseek-v4.1-flash').tokens, /\$0\.15/);
  assert.match(modelTokenInfo('opencode_go', 'minimax-m3').tokens, /\$0\.30/);
  assert.match(modelTokenInfo('opencode_go', 'muse-spark-1.3-contributor').tokens, /\$0\.10/);
  assert.match(modelTokenInfo('opencode_go', 'openai/gpt-5.6-luna').tokens, /\$0\.20/);
});
