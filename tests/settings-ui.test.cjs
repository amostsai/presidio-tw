const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

test('switching rule methods preserves deliberate empty lists and custom fields', () => {
  const controls = new Map();
  const context = vm.createContext({structuredClone,
    $: id => { if (!controls.has(id)) controls.set(id, {}); return controls.get(id); },
    document: {querySelectorAll: () => []},
    window: {addEventListener: () => {}},
  });
  vm.runInContext(fs.readFileSync('static/settings.js','utf8'),context);
  vm.runInContext(`
    markSettingsDirty = () => {};
    renderRules = () => {};
    const rule = {entity:'PERSON', patterns:[{regex:'王.+',score:.8,custom:'keep'}], deny_list:['王小明'], custom:'preserved'};
    changeMethod(rule,'pattern'); changeMethod(rule,'both');
    rule.deny_list = [];
    changeMethod(rule,'pattern'); changeMethod(rule,'both');
    result = JSON.stringify(rule);
  `,context);
  const result = JSON.parse(context.result);
  assert.deepEqual(result.deny_list, []);
  assert.equal(result.custom, 'preserved');
  assert.equal(result.patterns[0].custom, 'keep');
});

test('exclusion scope choices include new custom rule and model entities', () => {
  const controls = new Map();
  const context = vm.createContext({structuredClone,
    $: id => { if (!controls.has(id)) controls.set(id, {}); return controls.get(id); },
    document: {querySelectorAll: () => []}, window: {addEventListener: () => {}},
  });
  vm.runInContext(fs.readFileSync('static/settings.js','utf8'),context);
  vm.runInContext(`
    privacyState.choices = {entity_choices:[{value:'PERSON',label:'姓名'}]};
    privacyState.draft = {rules:[{entity:'CUSTOM_NEW',name:'新清單'}],ner:{mapping:{PERSON:'CUSTOM_NER'}}};
    result = JSON.stringify(exclusionScopeChoices());
  `,context);
  assert.deepEqual(JSON.parse(context.result).map(c=>c.value), ['*','PERSON','CUSTOM_NEW','CUSTOM_NER']);
});
