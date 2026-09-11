// Report markdown renderer: classed headings, grouped lists, safe tables.
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
const ctx = vm.createContext({escapeHtml: (s) => String(s).replaceAll('<', '&lt;').replaceAll('>', '&gt;')});
vm.runInContext(extract('function renderMarkdown(', '\nfunction reportArticleHtml('), ctx);
test('markdown renders styled sections and strips table separators', () => {
  const html = ctx.renderMarkdown([
    '# 제목', '## 0. 총평', '- **굵게** 항목', '1. 번호 항목',
    '| A | B |', '|---|---:|', '| 1 | 2 |', '> 인용문', '---', '본문 `code` <script>alert(1)</script>',
  ].join('\n'));
  assert.match(html, /<h2 class="md-h1">제목<\/h2>/);
  assert.match(html, /<h3 class="md-h2">0\. 총평<\/h3>/);
  assert.match(html, /<ul class="md-list"><li><b>굵게<\/b> 항목<\/li><li>번호 항목<\/li><\/ul>/);
  assert.match(html, /<div class="md-table-wrap"><table class="md-table">/);
  assert.match(html, /<th>A<\/th><th>B<\/th>/);
  assert.doesNotMatch(html, /<th>---/);
  assert.match(html, /<td>1<\/td><td>2<\/td>/);
  assert.match(html, /<blockquote class="md-quote">인용문<\/blockquote>/);
  assert.match(html, /<hr class="md-hr">/);
  assert.match(html, /<code>code<\/code>/);
  assert.doesNotMatch(html, /<script>/);
  assert.match(html, /&lt;script&gt;alert\(1\)&lt;\/script&gt;/);
});
