'use strict';
// Each workspace retains its own width preference, with a stacked mobile layout.
for (const grid of document.querySelectorAll('.panel,.settings-grid')) {
  const left = grid.firstElementChild, right = grid.lastElementChild;
  const divider = document.createElement('div');
  divider.className = 'pane-divider'; divider.tabIndex = 0;
  divider.setAttribute('role','separator'); divider.setAttribute('aria-orientation','vertical');
  divider.setAttribute('aria-label','調整右側面板寬度');
  divider.title = '拖拉調整寬度；方向鍵調整；雙擊恢復預設';
  grid.insertBefore(divider,right); grid.classList.add('resizable-grid');
  const initial = grid.classList.contains('settings-grid') ? 62 : 50;
  const gutter = grid.classList.contains('settings-grid') ? 24 : 12;
  const storageKey = 'privacy-pane-width:' + grid.id;
  let percentage = initial, dragging = null;
  try { const saved = Number(localStorage.getItem(storageKey)); if(saved>0 && saved<100) percentage=saved; } catch {}
  function update(value, persist=false) {
    const width = grid.getBoundingClientRect().width;
    if(width<=0 || matchMedia('(max-width:760px)').matches) return;
    const minimum = Math.min(240,(width-gutter)/2);
    percentage = Math.max(100*minimum/width,Math.min(value,100*(width-gutter-minimum)/width));
    grid.style.setProperty('--left-pane',percentage+'%');
    divider.setAttribute('aria-valuemin',String(Math.round(100*minimum/width)));
    divider.setAttribute('aria-valuemax',String(Math.round(100*(width-gutter-minimum)/width)));
    divider.setAttribute('aria-valuenow',String(Math.round(percentage)));
    divider.setAttribute('aria-valuetext',`右側寬度約 ${Math.round(100-percentage-100*gutter/width)}%`);
    if(persist) try { localStorage.setItem(storageKey,String(percentage)); } catch {}
  }
  divider.addEventListener('pointerdown',event=>{
    if(event.button!==0) return;
    event.preventDefault(); divider.focus();
    dragging={x:event.clientX,left:left.getBoundingClientRect().width};
    divider.setPointerCapture(event.pointerId); document.body.classList.add('resizing-panes');
  });
  divider.addEventListener('pointermove',event=>{
    if(dragging) update(100*(dragging.left+event.clientX-dragging.x)/grid.getBoundingClientRect().width);
  });
  function finish() {
    if(!dragging) return;
    dragging=null; document.body.classList.remove('resizing-panes'); update(percentage,true);
  }
  for(const event of ['pointerup','pointercancel','lostpointercapture']) divider.addEventListener(event,finish);
  divider.addEventListener('keydown',event=>{
    const values={ArrowLeft:percentage-2,ArrowRight:percentage+2,Home:0,End:100};
    if(Object.hasOwn(values,event.key)){event.preventDefault();update(values[event.key],true);}
  });
  divider.addEventListener('dblclick',()=>update(initial,true));
  new ResizeObserver(()=>update(percentage)).observe(grid);
  update(percentage);
}
