const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../static/app.js'), 'utf8');
const functions = ['dragHtml', 'place'].map(name => source.split('\n').find(line => line.startsWith(`function ${name}(`))).join('\n');

test('overlapping photo targets remain reachable and identical boxes accept either tag', () => {
  const options = [
    { id: 1, label: 'apple', box: [.45, .45, .24, .36] },
    { id: 2, label: 'green', box: [0, 0, 1, 1] },
    { id: 3, label: 'stem', box: [.18, .13, .12, .12] },
    { id: 4, label: 'cluster', box: [0, 0, 1, 1] },
  ];
  const S = { exercise: { options }, placements: new Set(), dragSelected: null };
  const context = vm.createContext({ S, esc: String, toast() {}, render() {} });
  vm.runInContext(functions, context);
  const html = context.dragHtml({ options, image: { url: '/image' } });
  const priority = id => Number(html.match(new RegExp(`data-zone="${id}"[^>]*z-index:(\\d+)`))[1]);
  assert.ok(priority(3) > priority(1));
  assert.ok(priority(1) > priority(4));
  S.dragSelected = 2;
  context.place(4);
  assert.deepEqual([...S.placements], [2]);
  S.dragSelected = 1;
  context.place(3);
  assert.deepEqual([...S.placements], [2]);
  S.dragSelected = 1;
  context.place(1);
  assert.deepEqual([...S.placements], [2, 1]);
  assert.equal(S.dragSelected, null);
});
