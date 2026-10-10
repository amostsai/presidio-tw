'use strict';
const privacyState = {draft:null, revision:null, choices:null, loaded:false, dirty:false, busy:false};
const modeStash = new WeakMap();
const cloneSetting = value => structuredClone(value);
const splitLines = text => text.split(/\r?\n/).map(s => s.trim()).filter(Boolean);
const scoreChoices = [{value:1,label:'最高（1.00）'},{value:.95,label:'高（0.95）'},{value:.9,label:'較高（0.90）'},{value:.85,label:'標準（0.85）'},{value:.7,label:'較低（0.70）'}];
function element(tag, className, text) { const node=document.createElement(tag); if(className) node.className=className; if(text!==undefined) node.textContent=text; return node; }
function option(select,value,label) { const node=element('option','',label); node.value=String(value); select.append(node); }
function populateSelect(select, choices, value, customLabel='目前自訂值') {
  select.replaceChildren(); choices.forEach(c=>option(select,c.value,c.label));
  if(!choices.some(c=>String(c.value)===String(value))) option(select,value,customLabel);
  select.value=String(value);
}
function scoreSelect(value, onChange, mixed=false) {
  const select=element('select'); populateSelect(select, mixed?[{value:'mixed',label:'各格式分數不同（保留）'},...scoreChoices]:scoreChoices, mixed?'mixed':value, `自訂（${value}）`);
  select.onchange=()=>{ if(select.value!=='mixed') onChange(Number(select.value)); }; return select;
}
function field(labelText, input) { const label=element('label','',labelText); label.append(input); return label; }
function textInput(value,onChange) { const input=element('input'); input.type='text'; input.value=value??''; input.oninput=()=>onChange(input.value); return input; }
function toggle(labelText, checked, onChange) {
  const label=element('label','toggle'); const input=element('input'); input.type='checkbox'; input.setAttribute('role','switch'); input.checked=checked;
  input.onchange=()=>onChange(input.checked); label.append(input,element('span'),element('b','',labelText)); return label;
}
function setSettingsBusy(busy) {
  privacyState.busy=busy;
  for(const id of ['settings-save','settings-reload','settings-test','settings-add','settings-exclusion-add']) $(id).disabled=busy || !privacyState.loaded || (id==='settings-save'&&!privacyState.dirty);
  $('settings-rule-list').inert=busy; $('model-types').inert=busy;
  $('settings-exclusion-list').inert=busy;
  $('settings-ner-enabled').disabled=busy;
  $('settings-template').disabled=busy;
  for(const control of document.querySelectorAll('#settings-panel .advanced input,#settings-panel .advanced select')) control.disabled=busy;
}
function markSettingsDirty() {
  privacyState.dirty=true; $('settings-dirty').textContent='有未儲存的修改'; $('settings-dirty').classList.add('unsaved');
  setSettingsBusy(privacyState.busy);
  $('settings-test-output').hidden=true;
  status('settings-test','');
  if(privacyState.loaded) {renderConflictWarnings();refreshExclusionScopes();}
}
function markedSaved() {
  privacyState.dirty=false; $('settings-dirty').textContent='已儲存'; $('settings-dirty').classList.remove('unsaved'); setSettingsBusy(false);
}
function ruleCount() { $('settings-rule-count').textContent=privacyState.draft.rules.length+' 個規則'; }
function dataTypeSelect(current, onChange, allowNone=false) {
  const select=element('select'); const choices=privacyState.choices.entity_choices;
  if(allowNone) option(select,'','不辨識此類型');
  choices.forEach(c=>option(select,c.value,c.label));
  if(current&&!choices.some(c=>c.value===current)) option(select,current,'自訂資料（目前設定）');
  option(select,'__custom__','其他／自訂資料'); select.value=current || '';
  select.onchange=()=>{
    let value=select.value;
    if(value==='__custom__') {
      value='CUSTOM_'+crypto.randomUUID().replaceAll('-','').slice(0,8).toUpperCase();
      option(select,value,'自訂資料'); select.value=value;
    }
    onChange(value);
  }; return select;
}
function renderModels() {
  const ner=privacyState.draft.ner, mapping=ner.mapping;
  $('settings-ner-enabled').checked=ner.enabled===true;
  $('settings-ner-enabled').onchange=()=>{
    ner.enabled=$('settings-ner-enabled').checked;
    if(ner.enabled&&!Object.keys(ner.mapping).length) ner.mapping.PERSON='PERSON';
    markSettingsDirty(); renderModels();
  };
  const groups=[{label:'姓名',keys:['PERSON'],target:'PERSON'},{label:'組織',keys:['ORG'],target:'ORGANIZATION'},{label:'地點／地址',keys:['GPE','LOC'],target:'LOCATION'}];
  $('model-types').replaceChildren();
  for(const group of groups) {
    const label=element('label'); const input=element('input'); input.type='checkbox'; input.checked=group.keys.some(key=>Boolean(mapping[key]));
    input.onchange=()=>{
      for(const key of group.keys) { if(input.checked) mapping[key] ||= group.target; else delete mapping[key]; }
      if(!Object.keys(mapping).length) ner.enabled=false;
      markSettingsDirty(); renderModels();
    }; label.append(input,element('span','',group.label)); $('model-types').append(label);
  }
  populateSelect($('settings-model'),[{value:'ckiplab/bert-base-chinese-ner',label:'預設繁體中文模型（CKIP BERT）'}],ner.model_name??'ckiplab/bert-base-chinese-ner','目前自訂模型');
  $('settings-model').onchange=()=>{ner.model_name=$('settings-model').value;markSettingsDirty();};
  populateSelect($('settings-device'),[{value:-1,label:'CPU（通用，建議）'},{value:0,label:'GPU 0（需要 CUDA）'}],ner.device??-1,`目前裝置（${ner.device}）`);
  $('settings-device').onchange=()=>{ner.device=Number($('settings-device').value);markSettingsDirty();};
  populateSelect($('settings-ner-score'),scoreChoices,ner.score??.85,`目前自訂（${ner.score}）`);
  $('settings-ner-score').onchange=()=>{ner.score=Number($('settings-ner-score').value);markSettingsDirty();};
  $('settings-chunk').value=ner.chunk_size??400; $('settings-overlap').value=ner.overlap??64;
  for(const [id,key] of [['settings-chunk','chunk_size'],['settings-overlap','overlap']]) $(id).oninput=()=>{ner[key]=Number($(id).value);markSettingsDirty();};
  $('settings-mappings').replaceChildren();
  const sources=new Map([['PERSON','姓名標籤'],['ORG','組織標籤'],['GPE','行政區域標籤'],['LOC','地理位置標籤']]);
  for(const key of Object.keys(mapping)) if(!sources.has(key)) sources.set(key,key+'（自訂模型標籤）');
  for(const [source,label] of sources) {
    const select=dataTypeSelect(mapping[source]||'',value=>{
      if(value) mapping[source]=value; else delete mapping[source];
      if(!Object.keys(mapping).length) ner.enabled=false;
      markSettingsDirty(); renderModels();
    },true);
    $('settings-mappings').append(field(label+' → 保護類型',select));
  }
}
function ruleMethod(rule) {
  const hasPatterns=Boolean(rule.patterns?.length), hasList=Boolean(rule.deny_list?.length)||Object.hasOwn(rule,'deny_list');
  return hasPatterns&&hasList?'both':hasList?'list':'pattern';
}
function changeMethod(rule,method) {
  const stash=modeStash.get(rule)||{};
  if(Object.hasOwn(rule,'patterns')) stash.patterns=cloneSetting(rule.patterns);
  if(Object.hasOwn(rule,'deny_list')) stash.deny_list=cloneSetting(rule.deny_list);
  modeStash.set(rule,stash);
  if(method==='pattern') { delete rule.deny_list; rule.patterns ||= stash.patterns || [{regex:'',score:.85}]; }
  if(method==='list') { delete rule.patterns; rule.deny_list ||= stash.deny_list || []; }
  if(method==='both') { rule.patterns ||= stash.patterns || [{regex:'',score:.85}]; rule.deny_list ||= stash.deny_list || []; }
  markSettingsDirty(); renderRules();
}
function exclusionConflicts(config) {
  const conflicts=new Set();
  for(const group of config.exclusions||[]) {
    const excluded=new Set(group.words.map(w=>w.toLocaleLowerCase()));
    for(const rule of config.rules) {
      if(rule.enabled===false || group.entity && group.entity!=='*' && group.entity!==rule.entity) continue;
      for(const word of rule.deny_list||[]) if(excluded.has(word.toLocaleLowerCase())) conflicts.add(word);
    }
  }
  return [...conflicts];
}
function renderConflictWarnings() {
  const words=exclusionConflicts(privacyState.draft);
  $('settings-conflicts').replaceChildren();
  if(words.length) $('settings-conflicts').append(element('p','',`同時出現在納入與排除清單：${words.join('、')}。排除優先，這些內容會保留原文。`));
}
function exclusionScopeChoices() {
  const choices=[{value:'*',label:'全部辨識類型'},...privacyState.choices.entity_choices];
  const add=(value,label)=>{if(!choices.some(c=>c.value===value))choices.push({value,label});};
  for(const rule of privacyState.draft.rules) add(rule.entity,rule.name+'（自訂類型）');
  for(const target of Object.values(privacyState.draft.ner.mapping)) add(target,'模型自訂類型：'+target);
  return choices;
}
function refreshExclusionScopes() {
  const choices=exclusionScopeChoices();
  $('settings-exclusion-list').querySelectorAll('select').forEach((select,index)=>{
    const group=privacyState.draft.exclusions?.[index];
    if(group) populateSelect(select,choices,group.entity||'*','目前自訂類型');
  });
}
function renderExclusions() {
  const holder=$('settings-exclusion-list'); holder.replaceChildren();
  const groups=privacyState.draft.exclusions||[];
  if(!groups.length) holder.append(element('p','fineprint','尚未設定排除清單。'));
  groups.forEach((group,index)=>{
    const box=element('div','settings-exclusion');
    const scope=element('select'); const choices=exclusionScopeChoices();
    populateSelect(scope,choices,group.entity||'*','目前自訂類型');
    scope.setAttribute('aria-label',`排除清單 ${index+1} 適用類型`);
    scope.onchange=()=>{group.entity=scope.value;markSettingsDirty();};
    const textarea=element('textarea'); textarea.rows=3;textarea.value=group.words.join('\n');textarea.placeholder='每行一筆要保留的姓名或文字';
    textarea.setAttribute('aria-label',`排除清單 ${index+1} 內容`);
    textarea.oninput=()=>{group.words=splitLines(textarea.value);markSettingsDirty();};
    const remove=element('button','danger-button','移除此排除清單');remove.type='button';
    remove.onclick=()=>{if(confirm('移除此排除清單？儲存後才會生效。')){privacyState.draft.exclusions.splice(index,1);markSettingsDirty();renderExclusions();}};
    const actions=element('div','rule-actions'); actions.append(remove);
    box.append(field('適用類型',scope),field('保留原文（每行一筆）',textarea),actions);holder.append(box);
  });
  renderConflictWarnings();
}
function renderPatterns(rule,details) {
  const holder=element('div'); details.append(holder);
  if(Object.hasOwn(rule,'field_keys')||Object.hasOwn(rule,'json_keys')) {
    const keys=element('textarea'); keys.rows=3; keys.value=(rule.field_keys||rule.json_keys||[]).join('\n');
    keys.oninput=()=>{rule.field_keys=splitLines(keys.value);markSettingsDirty();};
    holder.append(field('結構化資料欄位名稱（每行一筆）',keys),element('p','fineprint','適用 CSV／Excel／Word 表格的標題、JSON 鍵名與 XML 標籤或屬性；標題保留，對應內容套用此規則。'));
    const valueFormat=element('textarea'); valueFormat.rows=2; valueFormat.value=rule.field_value_regex||rule.json_value_regex||'';
    valueFormat.oninput=()=>{rule.field_value_regex=valueFormat.value;markSettingsDirty();};
    holder.append(field('欄位內容格式（正則，進階）',valueFormat));
  }
  (rule.patterns||[]).forEach((pattern,index)=>{
    const box=element('div','pattern-card'); const heading=element('div','pattern-header');
    heading.append(element('strong','',`格式 ${index+1}`));
    const remove=element('button','danger-button','移除此格式'); remove.type='button'; remove.onclick=()=>{rule.patterns.splice(index,1);markSettingsDirty();renderRules();};
    heading.append(remove); box.append(heading);
    const regex=element('textarea'); regex.rows=2; regex.value=pattern.regex||''; regex.placeholder='進階：輸入正則表達式'; regex.oninput=()=>{pattern.regex=regex.value;markSettingsDirty();};
    box.append(field('格式比對式（正則）',regex));
    const grid=element('div','field-grid'); grid.append(field('格式名稱（選填）',textInput(pattern.name||'',v=>{if(v)pattern.name=v;else delete pattern.name;markSettingsDirty();})),field('此格式的優先程度',scoreSelect(pattern.score??.8,v=>{pattern.score=v;markSettingsDirty();})));
    box.append(grid); holder.append(box);
  });
  const add=element('button','quiet','＋ 新增格式比對式'); add.type='button'; add.onclick=()=>{(rule.patterns||=[]).push({regex:'',score:.85});markSettingsDirty();renderRules();}; holder.append(add);
}
function renderRules() {
  const list=$('settings-rule-list'); list.replaceChildren(); ruleCount();
  if(!privacyState.draft.rules.length) list.append(element('div','rule-empty','還沒有格式規則。從上方選擇範本，新增第一個規則。'));
  privacyState.draft.rules.forEach((rule,index)=>{
    const card=element('div','privacy-rule'+(rule.enabled===false?' disabled':''));
    const header=element('div','rule-header'); const name=textInput(rule.name,value=>{rule.name=value;markSettingsDirty();}); name.setAttribute('aria-label',`規則 ${index+1} 名稱`);
    header.append(name,toggle('啟用',rule.enabled!==false,value=>{rule.enabled=value;card.classList.toggle('disabled',!value);markSettingsDirty();})); card.append(header);
    const fields=element('div','rule-fields'); const method=element('select'); populateSelect(method,[{value:'pattern',label:'格式規則（例如手機、證號）'},{value:'list',label:'指定清單（每行一筆）'},{value:'both',label:'格式規則＋指定清單'}],ruleMethod(rule));
    method.onchange=()=>changeMethod(rule,method.value);
    fields.append(field('資料類型',dataTypeSelect(rule.entity,v=>{rule.entity=v;markSettingsDirty();})),field('辨識方式',method));
    const validator=element('select'); populateSelect(validator,privacyState.choices.validators,rule.validator||''); validator.onchange=()=>{if(validator.value)rule.validator=validator.value;else delete rule.validator;markSettingsDirty();};
    fields.append(field('校驗方式',validator));
    const scores=(rule.patterns||[]).map(p=>p.score??.8); if(Object.hasOwn(rule,'deny_list'))scores.push(rule.deny_list_score??.9);
    const mixed=new Set(scores).size>1;
    fields.append(field('比對優先程度',scoreSelect(scores[0]??.85,value=>{for(const p of rule.patterns||[])p.score=value;if(Object.hasOwn(rule,'deny_list'))rule.deny_list_score=value;markSettingsDirty();},mixed)));
    card.append(fields);
    if(Object.hasOwn(rule,'deny_list')) {
      const container=element('div','rule-list-input'); const textarea=element('textarea'); textarea.rows=4; textarea.value=rule.deny_list.join('\n'); textarea.placeholder='王小明\n李小華\n每行一筆，不需要引號或逗號';
      textarea.setAttribute('aria-label',`規則 ${index+1} 指定清單`); textarea.oninput=()=>{rule.deny_list=splitLines(textarea.value);markSettingsDirty();};
      container.append(field('指定姓名／關鍵字（每行一筆）',textarea)); card.append(container);
      const matchMode=element('select');populateSelect(matchMode,[{value:'word',label:'完整英數字詞（建議）'},{value:'substring',label:'任意子字串（進階，可能誤判）'}],rule.deny_list_match||'word');
      matchMode.onchange=()=>{rule.deny_list_match=matchMode.value;markSettingsDirty();};
      container.append(field('清單比對方式',matchMode),element('p','fineprint','英文不分大小寫。完整英數字詞不會把 EXAMPLE 比對到 exampled；中文姓名可連在句子中。'));
    }
    const advanced=element('details','advanced'); advanced.append(element('summary','','進階設定（一般使用者可略過）'));
    if(rule.patterns) renderPatterns(rule,advanced);
    const context=element('textarea'); context.rows=2; context.value=(rule.context||[]).join('\n'); context.placeholder='例如：手機、電話（每行一個）'; context.oninput=()=>{rule.context=splitLines(context.value);markSettingsDirty();};
    advanced.append(field('上下文提示詞（只增加優先分數，不是必要條件）',context));
    advanced.append(field('代碼類型（大寫英文，通常不必修改）',textInput(rule.entity,v=>{rule.entity=v;markSettingsDirty();})));
    card.append(advanced);
    const actions=element('div','rule-actions'); const remove=element('button','danger-button','移除規則'); remove.type='button'; remove.onclick=()=>{if(confirm(`移除「${rule.name||'未命名規則'}」？儲存後才會生效。`)){privacyState.draft.rules.splice(index,1);markSettingsDirty();renderRules();}}; actions.append(remove); card.append(actions); list.append(card);
  });
}
function renderSettings() {
  renderModels(); renderRules(); renderExclusions();
  const select=$('settings-template'); select.replaceChildren();
  privacyState.choices.templates.forEach(t=>option(select,t.id,t.rule.name));
  option(select,'custom','自訂格式規則（進階）');
  function describe() { const t=privacyState.choices.templates.find(t=>t.id===select.value); $('template-description').textContent=t?.description || '需要自行輸入正則表達式；一般使用者建議選擇現成範本或指定清單。'; }
  select.onchange=describe; describe();
}
async function settingsRequest(path,body) {
  const response=await fetch(path,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(body)});
  const data=await response.json();
  if(!response.ok) throw new Error(typeof data.detail==='string'?data.detail:'設定資料不完整，請檢查欄位。');
  return data;
}
async function loadPrivacySettings(force=false) {
  if(privacyState.busy||privacyState.loaded&&!force)return;
  if(force&&privacyState.dirty&&!confirm('重新載入會放棄未儲存的修改，要繼續嗎？'))return;
  setSettingsBusy(true); status('settings','正在載入隱私設定…');
  try {
    const response=await fetch('/api/privacy-settings',{cache:'no-store'}); const data=await response.json();
    if(!response.ok)throw new Error(data.detail);
    privacyState.draft=cloneSetting(data.config); privacyState.revision=data.revision; privacyState.choices=data; privacyState.loaded=true;
    renderSettings(); markedSaved(); status('settings',''); $('settings-test-output').hidden=true; status('settings-test','');
  } catch(error) {status('settings','設定載入失敗：'+error.message,true);}
  finally{setSettingsBusy(false);}
}
$('settings-add').onclick=()=>{
  const template=privacyState.choices.templates.find(t=>t.id===$('settings-template').value);
  const rule=template?cloneSetting(template.rule):{name:'自訂格式規則',entity:'CUSTOM',enabled:true,patterns:[{regex:'',score:.85}]};
  const base=rule.name; let count=2; while(privacyState.draft.rules.some(r=>r.name===rule.name))rule.name=base+`（${count++}）`;
  if(rule.entity==='CUSTOM')rule.entity='CUSTOM_'+crypto.randomUUID().replaceAll('-','').slice(0,8).toUpperCase();
  privacyState.draft.rules.push(rule); markSettingsDirty(); renderRules();
  const last=$('settings-rule-list').lastElementChild;
  if(Object.hasOwn(rule,'deny_list'))last.querySelector('.rule-list-input textarea').focus();
  else if(!template){last.querySelector('details').open=true;last.querySelector('textarea').focus();}
};
$('settings-reload').onclick=()=>loadPrivacySettings(true);
$('settings-exclusion-add').onclick=()=>{
  (privacyState.draft.exclusions||=[]).push({entity:'*',words:[]});
  markSettingsDirty();renderExclusions();$('settings-exclusion-list').lastElementChild.querySelector('textarea').focus();
};
$('settings-save').onclick=async()=>{
  if(!privacyState.loaded||privacyState.busy)return;
  setSettingsBusy(true);status('settings','正在驗證並儲存…');
  try {
    const data=await settingsRequest('/api/privacy-settings',{config:privacyState.draft,revision:privacyState.revision});
    privacyState.draft=cloneSetting(data.config);privacyState.revision=data.revision;renderSettings();markedSaved();
    await refreshRecognitionOptions();status('settings',data.message); 
  }catch(error){status('settings',error.message,true);}
  finally{setSettingsBusy(false);}
};
$('settings-test').onclick=async()=>{
  if(!privacyState.loaded||privacyState.busy)return;
  const text=$('settings-sample').value;
  if(!text.trim())return status('settings-test','請先輸入測試文字。',true);
  setSettingsBusy(true);$('settings-test-output').hidden=true;status('settings-test','正在測試目前草稿…首次模型載入可能需要較久。');
  try {
    const data=await settingsRequest('/api/privacy-settings/test',{config:privacyState.draft,text});
    $('settings-test-preview').textContent=data.preview;$('settings-test-matches').replaceChildren();
    for(const match of data.matches){const row=element('tr');for(const value of [privacyState.choices.entity_choices.find(c=>c.value===match.entity)?.label||'自訂資料',match.text,match.score.toFixed(2)])row.append(element('td','',value));$('settings-test-matches').append(row);}
    $('settings-test-output').hidden=false;status('settings-test',`找到 ${data.matches.length} 筆敏感內容。這次測試不會儲存設定。`);
  }catch(error){status('settings-test',error.message,true);}
  finally{setSettingsBusy(false);}
};
setSettingsBusy(false);
window.addEventListener('beforeunload',event=>{if(privacyState.dirty){event.preventDefault();event.returnValue='';}});
