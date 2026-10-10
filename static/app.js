'use strict';
const $ = id => document.getElementById(id);
const urls = { mask: [], restore: [] };
let restoredText = '';
const status = (mode, text, error = false) => { $(mode+'-status').textContent = text; $(mode+'-status').classList.toggle('error', error); };
function release(mode) { urls[mode].forEach(URL.revokeObjectURL); urls[mode] = []; if(mode === 'mask') $('mask-summary').replaceChildren(); }
function download(mode, id, data, type, name) {
  const raw = atob(data), bytes = Uint8Array.from(raw, c => c.charCodeAt(0));
  const url = URL.createObjectURL(new Blob([bytes], {type}));
  urls[mode].push(url); $(id).href = url; $(id).download = name;
}
function stat(container, value, label) {
  const box = document.createElement('div'); box.className = 'stat';
  const strong = document.createElement('strong'), small = document.createElement('span');
  strong.textContent = String(value); small.textContent = label; box.append(strong, small); container.append(box);
}
function replacementStat(container, count, mapping) {
  const entries = JSON.parse(new TextDecoder().decode(Uint8Array.from(atob(mapping), c => c.charCodeAt(0)))).entries;
  const box = document.createElement('details'); box.className = 'stat replacement-stat';
  const summary = document.createElement('summary');
  const strong = document.createElement('strong'), label = document.createElement('span');
  strong.textContent = String(count); label.textContent = '已替換的敏感內容';
  summary.append(strong, label);
  const popup = document.createElement('div'); popup.className = 'replacement-tooltip';
  const heading = document.createElement('p'); heading.textContent = '已替換詞彙 → 還原代碼';
  popup.append(heading);
  if(entries.length) {
    const list = document.createElement('ul');
    for(const entry of entries) {
      const item = document.createElement('li');
      const original = document.createElement('b'), token = document.createElement('code');
      original.textContent = entry.original; token.textContent = entry.token;
      item.append(original, token); list.append(item);
    }
    popup.append(list);
  } else {
    const empty = document.createElement('p'); empty.textContent = '沒有替換任何詞。'; popup.append(empty);
  }
  box.append(summary, popup);
  box.addEventListener('mouseenter', () => { box.open = true; });
  box.addEventListener('mouseleave', () => { if(!box.contains(document.activeElement)) box.open = false; });
  box.addEventListener('focusin', () => { box.open = true; });
  box.addEventListener('focusout', event => { if(!box.contains(event.relatedTarget)) box.open = false; });
  box.addEventListener('keydown', event => {
    if(event.key === 'Escape') { box.open = false; summary.blur(); event.preventDefault(); }
  });
  container.append(box);
}
function warning(mode, text) { const p = document.createElement('p'); p.textContent = text; $(mode+'-warnings').append(p); }
function switchMode(mode) {
  for (const m of ['mask','restore','settings']) { $(m+'-panel').hidden = m !== mode; $('tab-'+m).classList.toggle('active',m === mode); $('tab-'+m).setAttribute('aria-selected',String(m === mode)); }
}
$('tab-mask').onclick = () => switchMode('mask'); $('tab-restore').onclick = () => switchMode('restore');
$('tab-settings').onclick = () => { switchMode('settings'); loadPrivacySettings(); };
for (const id of ['mask-file','restore-file','mapping-file']) {
  const input = $(id), label = $(id+'-name'); const original = label.textContent;
  input.addEventListener('change', () => { label.textContent = input.files[0]?.name || original; });
  const zone = document.querySelector('[data-drop="'+id+'"]');
  zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('drag-over'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
  zone.addEventListener('drop', e => { e.preventDefault(); zone.classList.remove('drag-over'); if(e.dataTransfer.files.length === 1) { input.files = e.dataTransfer.files; input.dispatchEvent(new Event('change')); } });
}
for (const button of document.querySelectorAll('[data-clear]')) {
  button.onclick = () => { const mode = button.dataset.clear; $(mode+'-text').value = ''; $(mode+'-file').value = ''; $(mode+'-file').dispatchEvent(new Event('change')); if(mode === 'restore') { $('mapping-file').value = ''; $('mapping-file').dispatchEvent(new Event('change')); } release(mode); $(mode+'-result').hidden = true; $(mode+'-empty').hidden = false; status(mode,''); };
}
async function process(mode, event) {
  event.preventDefault();
  const form = $(mode+'-form'), file = $(mode+'-file').files[0], text = $(mode+'-text').value;
  if(Boolean(file) === Boolean(text.trim())) return status(mode,'請擇一上傳檔案或貼上非空白文字。',true);
  if(file && file.size > 10*1024*1024) return status(mode,'檔案超過 10 MiB，請分割後再處理。',true);
  if(mode === 'restore' && !$('mapping-file').files[0]) return status(mode,'請選擇對應的還原檔。',true);
  const data = new FormData(form);
  if(!file) data.delete('file'); else data.delete('text');
  if(mode === 'mask' && !data.getAll('entities').length) return status(mode,'請至少選擇一個辨識項目。',true);
  release(mode); $(mode+'-result').hidden = true; $(mode+'-empty').hidden = true;
  $(mode+'-submit').disabled = true;
  status(mode, mode === 'mask' ? '正在辨識並替換敏感內容…首次載入模型可能需要較久。' : '正在比對還原檔並復原內容…');
  try {
    const response = await fetch('/api/'+(mode === 'mask' ? 'anonymize' : 'restore'), {method:'POST',body:data});
    const result = await response.json();
    if(!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : '輸入資料不完整，請檢查檔案與欄位。');
    $(mode+'-summary').replaceChildren(); $(mode+'-warnings').replaceChildren();
    if(mode === 'mask') {
      replacementStat($('mask-summary'),result.report.matched_count,result.mapping); stat($('mask-summary'),result.report.unique_count,'唯一還原代碼');
      for(const [entity,count] of Object.entries(result.report.entities)) stat($('mask-summary'),count,entity);
      download(mode,'mapping-download',result.mapping,'application/json',result.mapping_filename);
      if(result.report.matched_count === 0) warning(mode,'未辨識到敏感內容。請確認選取的規則，並自行檢查文件中尚未處理的範圍。');
    } else {
      stat($('restore-summary'),result.report.restored_count,'已復原的代碼'); stat($('restore-summary'),result.report.unresolved_tokens.length,'無法識別的代碼');
      if(result.report.unresolved_tokens.length) warning(mode,'以下代碼不在還原檔中或已被 AI 改動，保留原樣：'+result.report.unresolved_tokens.join('、'));
      if(result.report.restored_count === 0) warning(mode,'沒有找到可復原的代碼。請檢查回覆與還原檔是否對應。');
      restoredText = result.preview; $('copy-restored').hidden = !restoredText || result.preview_truncated;
    }
    download(mode,mode+'-download',result.content,result.media_type,result.filename);
    $(mode+'-preview').textContent = result.preview; $(mode+'-preview').hidden = !result.preview;
    if(result.preview_truncated) warning(mode,'預覽僅顯示前 100,000 字元；下載檔包含完整內容。');
    result.warnings.forEach(w => warning(mode,w));
    $(mode+'-result').hidden = false;
    status(mode,mode === 'mask' ? '處理完成。請分別下載脫敏檔及還原檔。' : '復原完成。請確認結果後下載。');
  } catch(error) { status(mode,error.message || '連線失敗，請確認服務仍在執行。',true); }
  finally { $(mode+'-submit').disabled = false; }
}
$('mask-form').onsubmit = e => process('mask',e); $('restore-form').onsubmit = e => process('restore',e);
async function copy(text,mode) { try { await navigator.clipboard.writeText(text); status(mode,'已複製到剪貼簿。'); } catch { status(mode,'瀏覽器無法使用剪貼簿，請直接選取文字複製。',true); } }
$('copy-prompt').onclick = () => copy('請處理以下內容。所有 [[…]] 形式的代碼代表原始資料，請逐字完整保留（包含大小寫、底線及括號），不要翻譯、拆開、改寫或補造代碼。','mask');
$('copy-restored').onclick = () => copy(restoredText,'restore');
async function refreshRecognitionOptions() {
  const previous = new Map(Array.from(document.querySelectorAll('#rules input')).map(input => [input.value,input.checked]));
  try {
    const response = await fetch('/api/config', {cache:'no-store'});
    const cfg = await response.json();
    if(!response.ok) throw new Error(cfg.detail);
    $('rules').replaceChildren();
    for(const entity of cfg.entities) {
      const label = document.createElement('label'); label.className='rule';
      const input=document.createElement('input'); input.type='checkbox'; input.name='entities'; input.value=entity; input.checked=previous.has(entity)?previous.get(entity):true;
      const text=document.createElement('span'); text.textContent=cfg.labels[entity] || entity;
      label.append(input,text); $('rules').append(label);
    }
    $('ner-note').textContent=cfg.ner_enabled ? '姓名／地點等由 CKIP 模型辨識；初次使用可能需要載入或下載模型。規則來源：隱私設定。' : '目前使用格式與指定清單，模型辨識已停用。';
    $('mask-submit').disabled = !cfg.entities.length;
    if(!cfg.entities.length) status('mask','尚未啟用任何規則，請至「隱私設定」新增或啟用辨識項目。',true);
    else status('mask','');
  } catch(e) { status('mask','設定載入失敗：'+e.message,true); $('mask-submit').disabled=true; }
}
refreshRecognitionOptions();
window.addEventListener('beforeunload', () => { release('mask'); release('restore'); });
