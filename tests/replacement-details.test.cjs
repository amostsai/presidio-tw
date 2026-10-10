const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

class Element {
  constructor(tag) { this.tag = tag; this.children = []; this.listeners = {}; }
  append(...nodes) { this.children.push(...nodes); }
  addEventListener(name, handler) { this.listeners[name] = handler; }
  contains(node) { return this === node || this.children.some(child => child.contains(node)); }
  blur() {}
}
function render(entries) {
  const document = {createElement: tag => new Element(tag), activeElement: null};
  const context = vm.createContext({document, TextDecoder,
    atob: data => Buffer.from(data,'base64').toString('binary')});
  const source = fs.readFileSync('static/app.js','utf8');
  vm.runInContext(source.slice(source.indexOf('function stat('), source.indexOf('function warning(')), context);
  const container = new Element('div');
  context.container = container;
  context.mapping = Buffer.from(JSON.stringify({entries})).toString('base64');
  vm.runInContext('replacementStat(container, 3, mapping)', context);
  return {container, document};
}
test('replacement details show Unicode originals and exact tokens as text', () => {
  const {container} = render([
    {entity:'PERSON', original:'王小明', token:'[[PERSON_abcd1234_0001]]'},
    {entity:'CUSTOM', original:'<img onerror=alert(1)>', token:'[[CUSTOM_abcd1234_0002]]'},
  ]);
  const details = container.children[0];
  assert.equal(details.tag, 'details');
  assert.equal(details.children[0].children[0].textContent, '3');
  const list = details.children[1].children[1];
  assert.equal(list.children.length, 2);
  assert.equal(list.children[0].children[0].textContent, '王小明');
  assert.equal(list.children[0].children[1].textContent, '[[PERSON_abcd1234_0001]]');
  assert.equal(list.children[1].children[0].textContent, '<img onerror=alert(1)>');
  details.listeners.mouseenter(); assert.equal(details.open, true);
  details.listeners.mouseleave(); assert.equal(details.open, false);
  details.open = true;
  details.listeners.keydown({key:'Escape', preventDefault() {}});
  assert.equal(details.open, false);
});
test('empty replacement details explain that nothing was replaced', () => {
  const {container} = render([]);
  assert.equal(container.children[0].children[1].children[1].textContent, '沒有替換任何詞。');
});
