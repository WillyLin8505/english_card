const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../static/app.js'), 'utf8');
const fn = source.split('\n').find(line => line.startsWith('function blockedReasonsHtml('));
const context = vm.createContext({
  good: v => typeof v === 'string' && !!v.trim(),
  esc: v => String(v).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))
});
vm.runInContext(fn, context);
test('unavailable preview shows actual reasons safely, without duplicates', () => {
  const result = context.blockedReasonsHtml({reasons:['沒有這個義項的圖片','遮罩後仍有答案','沒有這個義項的圖片','<img src=x onerror=alert(1)>',null]});
  assert.match(result, /沒有這個義項的圖片/);
  assert.match(result, /遮罩後仍有答案/);
  assert.equal((result.match(/沒有這個義項的圖片/g) || []).length, 1);
  assert.ok(!result.includes('<img'));
  assert.match(result, /&lt;img/);
});
test('missing or malformed reasons get a readable fallback', () => {
  for (const exercise of [null, {}, {reasons:null}, {reasons:'bad'}, {reasons:['',null]}]) {
    assert.match(context.blockedReasonsHtml(exercise), /請切換詞義或詞條/);
  }
});
