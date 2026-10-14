/* 工作台布局与阅读位置；不更改学生学习数据。 */
window.Workspace=(()=>{
 let ready=false,ratio=.6,collapsed=false,pane='content',lastPage=null,helpGuide=null;
 const storageKey=()=> 'discrete-workspace:'+studentId;
 const read=()=>{try{return JSON.parse(localStorage.getItem(storageKey())||'{}');}catch{return {};}};
 function persist(values){try{localStorage.setItem(storageKey(),JSON.stringify({...read(),...values}));}catch{}}
 function setPane(value){pane=value;document.body.classList.toggle('chat-mode',value==='chat');document.querySelectorAll('[data-mobile-pane]').forEach(b=>b.classList.toggle('active',b.dataset.mobilePane===value));}
 function setCollapsed(value,save=true){collapsed=value;document.querySelector('#app-shell').classList.toggle('sidebar-collapsed',value);const b=document.querySelector('#sidebar-toggle');b.textContent=value?'›':'‹';b.setAttribute('aria-expanded',String(!value));b.setAttribute('aria-label',value?'展开导航':'收起导航');if(save)persist({collapsed:value});requestAnimationFrame(applyRatio);}
 function applyRatio(){const host=document.querySelector('#workspace-content');if(!host)return;const available=host.clientWidth-8;if(window.innerWidth>=1024&&available<920&&!collapsed){setCollapsed(true,false);return;}const min=560,max=available-360;const width=available>=920?Math.max(min,Math.min(max,available*ratio)):available*.6;host.style.setProperty('--reader-width',width+'px');document.querySelector('#workspace-divider').setAttribute('aria-valuenow',String(Math.round(ratio*100)));}
 function setRatio(value){ratio=Math.max(.5,Math.min(.7,value));persist({ratio});applyRatio();}
 function closeNav(){document.body.classList.remove('nav-open');document.querySelector('#nav-backdrop').hidden=true;}
 function bind(){if(ready)return;ready=true;const saved=read();ratio=Number.isFinite(saved.ratio)?Math.max(.5,Math.min(.7,saved.ratio)):.6;setCollapsed(saved.collapsed??(window.innerWidth<1280),false);document.querySelector('#chat-input').value=saved.chatDraft||'';
 document.querySelector('#chat-input').addEventListener('input',e=>persist({chatDraft:e.target.value}));
 document.querySelector('#sidebar-toggle').addEventListener('click',()=>{if(window.innerWidth<1024)closeNav();else setCollapsed(!collapsed);});
 document.querySelector('#mobile-nav-toggle').addEventListener('click',()=>{document.body.classList.toggle('nav-open');document.querySelector('#nav-backdrop').hidden=!document.body.classList.contains('nav-open');});
 document.querySelector('#nav-backdrop').addEventListener('click',closeNav);
 document.querySelectorAll('[data-mobile-pane]').forEach(b=>b.addEventListener('click',()=>setPane(b.dataset.mobilePane)));
 document.querySelectorAll('[data-layout-ratio]').forEach(b=>b.addEventListener('click',()=>{setRatio(Number(b.dataset.layoutRatio));b.closest('details').open=false;}));
 const divider=document.querySelector('#workspace-divider');let drag=false;
 divider.addEventListener('pointerdown',e=>{drag=true;divider.setPointerCapture(e.pointerId);document.body.classList.add('resizing');e.preventDefault();});
 divider.addEventListener('pointermove',e=>{if(!drag)return;const box=document.querySelector('#workspace-content').getBoundingClientRect();setRatio((e.clientX-box.left)/(box.width-8));});
 const end=()=>{drag=false;document.body.classList.remove('resizing');};divider.addEventListener('pointerup',end);divider.addEventListener('pointercancel',end);
 divider.addEventListener('keydown',e=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(e.key)){e.preventDefault();setRatio(e.key==='Home'?.5:e.key==='End'?.7:ratio+(e.key==='ArrowLeft'?-.02:.02));}});
 window.addEventListener('resize',()=>{applyRatio();if(window.innerWidth>=1024)closeNav();});
 window.addEventListener('pdf-position',e=>{const p=e.detail;if(p.chapter!==state.chapter||p.version!==state.sectionData?.pdf?.version)return;lastPage=p;persist({lastReading:p,positions:{...(read().positions||{}),[p.document_id+':'+p.version]:p}});const location=document.querySelector('#reading-location');if(location)location.textContent='原教材第 '+p.page+' 页';const resume=document.querySelector('#resume-location');if(resume)resume.textContent='原教材第 '+p.page+' 页';});
 document.querySelector('#materials-info').addEventListener('click',()=>toast('课件文件尚未提供；现有教材、重点笔记和例题线索可正常阅读。'));
 document.querySelector('#return-chat').addEventListener('click',()=>showHelp(null));
 document.querySelector('#chat-input').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();document.querySelector('#chat-form').requestSubmit();}});
 applyRatio();
 }
 function onView(view){closeNav();setPane('content');document.body.dataset.workspaceView=view;const slot=document.querySelector('#practice-nav-slot');slot.hidden=view!=='quiz';document.querySelector('#course-panel-body').hidden=view==='quiz'||localStorage.getItem('discrete-math-course-collapsed')==='true';document.querySelector('#directory-title').textContent=view==='quiz'?'教材习题':'章节目录';document.querySelector('#course-collapse').hidden=view==='quiz';if(view!=='quiz')showHelp(null);applyRatio();}
 function chapterChanged(){const s=state.sectionData;if(!s)return;document.querySelector('#resume-title').textContent='第'+state.chapter+'章 · '+s.title;document.querySelector('#resume-location').textContent='可从当前阅读位置继续';document.querySelector('#conversation-title').textContent=s.title||'教材答疑';lastPage=null;}
 function resumeFor(metadata){const value=(read().positions||{})[metadata.document_id+':'+metadata.version];return value?.section===state.section?value:null;}
 function lastReading(){return read().lastReading;}
 function clearDraft(){persist({chatDraft:''});}
 function showHelp(html,title='当前题目讲解',guide=null){helpGuide?.dispose();helpGuide=null;const panel=document.querySelector('#practice-help-panel');panel.hidden=html===null;document.querySelector('#chat-panel').classList.toggle('practice-help-active',html!==null);if(html!==null){document.querySelector('#practice-help-title').textContent=title;document.querySelector('#practice-help-content').innerHTML=html;window.TextbookPDF?.renderMath(document.querySelector('#practice-help-content'));if(guide&&window.GuidedVisualization){const holder=document.createElement('div');document.querySelector('#practice-help-content').append(holder);helpGuide=window.GuidedVisualization.mount(holder,{guide,onSource:ref=>openGuideSource(guide,ref)});}if(state.view!=='quiz')setPane('chat');}}
 return {bind,onView,setPane,setRatio,chapterChanged,resumeFor,lastReading,clearDraft,showHelp};
})();
