/* 工作台布局与阅读位置；不更改学生学习数据。 */
window.Workspace=(()=>{
 let ready=false,ratio=.6,collapsed=false,readerOpen=false,pane='chat',lastPage=null,helpGuide=null;
 const storageKey=()=> (window.TutorCourse?.id||'experimental-psychology-3')+':workspace:'+studentId;
 const read=()=>{try{return JSON.parse(localStorage.getItem(storageKey())||'{}');}catch{return {};}};
 function persist(values){try{localStorage.setItem(storageKey(),JSON.stringify({...read(),...values}));}catch{}}
 function setPane(value){pane=value;document.body.classList.toggle('chat-mode',value==='chat');document.querySelectorAll('[data-mobile-pane]').forEach(b=>b.classList.toggle('active',b.dataset.mobilePane===value));}
 function setCollapsed(value,save=true){collapsed=value;document.querySelector('#app-shell').classList.toggle('sidebar-collapsed',value);document.querySelectorAll('[data-sidebar-toggle]').forEach(b=>{b.setAttribute('aria-expanded',String(!value));b.setAttribute('aria-label',value?'展开对话列表':'收起对话列表');b.title=value?'展开对话列表':'收起对话列表';});if(save)persist({collapsed:value});requestAnimationFrame(applyRatio);}
 function applyRatio(){const host=document.querySelector('#workspace-content');if(!host)return;const available=host.clientWidth-8;const min=420,max=available-340;const width=available>=760?Math.max(min,Math.min(max,available*ratio)):available*.6;host.style.setProperty('--reader-width',width+'px');document.querySelector('#workspace-divider').setAttribute('aria-valuenow',String(Math.round(ratio*100)));}
 function setReaderOpen(value){readerOpen=value;document.body.classList.toggle('reader-open',value);const button=document.querySelector('#reader-toggle');button.setAttribute('aria-expanded',String(value));button.querySelector('span').textContent=value?'收起教材':'打开教材';if(!value)setDirectoryOpen(false);const suggestions=document.querySelector('#learning-suggestions'),form=document.querySelector('#chat-form');if(value)form.before(suggestions);else form.after(suggestions);setPane(value?'content':'chat');requestAnimationFrame(()=>{applyRatio();window.dispatchEvent(new Event('resize'));if(value)window.dispatchEvent(new Event('workspace-reader-open'));});}
 function setDirectoryOpen(value){document.body.classList.toggle('directory-open',value);document.querySelectorAll('[data-directory-toggle]').forEach(button=>button.setAttribute('aria-expanded',String(value)));}
 const suggestionKey=()=>storageKey()+':suggestions-dismissed';
 function dismissSuggestions(){document.querySelector('#learning-suggestions').hidden=true;try{sessionStorage.setItem(suggestionKey(),'1');}catch{}}
 function chatChanged(){const empty=!state.chat.length;document.body.classList.toggle('conversation-empty',empty);document.querySelector('#chat-welcome').hidden=!empty;if(!empty)dismissSuggestions();}
 function setRatio(value){ratio=Math.max(.5,Math.min(.7,value));persist({ratio});applyRatio();}
 function closeNav(){document.body.classList.remove('nav-open');document.querySelector('#nav-backdrop').hidden=true;}
 function bind(){if(ready)return;ready=true;const saved=read();ratio=Number.isFinite(saved.ratio)?Math.max(.5,Math.min(.7,saved.ratio)):.6;setCollapsed(false,false);document.querySelector('#chat-input').value=saved.chatDraft||'';
 document.querySelectorAll('[data-sidebar-toggle]').forEach(b=>{if(!b.querySelector('svg'))b.innerHTML='<svg><use href="#i-list"/></svg>';});
 document.querySelectorAll('.sidebar .nav-item').forEach(button=>{const label=button.textContent.trim();button.title=label;button.setAttribute('aria-label',label);});
 document.querySelector('#reader-toggle').addEventListener('click',()=>setReaderOpen(!readerOpen));
 document.querySelectorAll('[data-reader-close]').forEach(button=>button.addEventListener('click',()=>{setReaderOpen(false);document.querySelector('#reader-toggle').focus();}));
 document.querySelectorAll('[data-directory-toggle]').forEach(button=>button.addEventListener('click',()=>setDirectoryOpen(!document.body.classList.contains('directory-open'))));
 // 目录按钮跟随 PDF 工具栏：有工具栏时放进工具栏，否则回到阅读区标题栏。
 const placeDirectoryToggle=()=>{const button=document.querySelector('#course-view .directory-toggle');if(!button)return;const host=document.querySelector('#chapter-content .pdf-toolbar')||document.querySelector('#course-view>.workspace-header');if(button.parentElement!==host)host.appendChild(button);};
 placeDirectoryToggle();const hasToolbar=n=>n.nodeType===1&&(typeof n.matches==='function'&&n.matches('.pdf-toolbar')||typeof n.querySelector==='function'&&!!n.querySelector('.pdf-toolbar'));
 new MutationObserver(list=>{if(list.some(m=>[...m.addedNodes,...m.removedNodes].some(n=>hasToolbar(n)||n.nodeType===1&&n.classList?.contains('directory-toggle'))))placeDirectoryToggle();}).observe(document.querySelector('#chapter-content'),{childList:true,subtree:true});
 window.addEventListener('workspace-reader-open',placeDirectoryToggle);
 document.addEventListener('keydown',event=>{if(event.key==='Escape'){setDirectoryOpen(false);closeNav();}});
 document.querySelector('#dismiss-suggestions').addEventListener('click',dismissSuggestions);
 try{document.querySelector('#learning-suggestions').hidden=sessionStorage.getItem(suggestionKey())==='1';}catch{}
 document.querySelectorAll('[data-study-prompt]').forEach(button=>button.addEventListener('click',()=>{if(state.sending)return;const target=state.sectionData?.title||window.TutorCourse?.title||'当前教材';const prompts={plan:'我今天想学习'+target+'。请先结合我的学习记录和已有教材，帮我安排本次学习的目标、重点和步骤；如果缺少必要信息，请先问我，计划确认后再开始。',continue:'请结合教材和当前学习位置，继续学习'+target+'。先简单衔接已讲内容，再讲下一个适合学习的知识点；如果还没有学习记录，请从基础开始。',review:'我想复习之前学过的内容。请根据真实学习记录，建议现在最值得回顾的知识点和原因；没有记录时请先和我确定复习范围，不要假设我已经学过。'};const input=document.querySelector('#chat-input');input.value=prompts[button.dataset.studyPrompt];input.dispatchEvent(new Event('input'));input.focus();}));
 setReaderOpen(false);chatChanged();
 document.querySelector('#chat-input').addEventListener('input',e=>persist({chatDraft:e.target.value}));
 document.querySelectorAll('[data-sidebar-toggle]').forEach(b=>b.addEventListener('click',()=>{if(window.innerWidth<1024){document.querySelector('#mobile-nav-toggle').click();}else setCollapsed(!collapsed);}));
 document.querySelector('#mobile-nav-toggle').addEventListener('click',()=>{document.body.classList.toggle('nav-open');document.querySelector('#nav-backdrop').hidden=!document.body.classList.contains('nav-open');});
 document.querySelector('#nav-backdrop').addEventListener('click',closeNav);
 document.querySelectorAll('[data-mobile-pane]').forEach(b=>b.addEventListener('click',()=>{if(b.dataset.mobilePane==='content'&&state.view==='course')setReaderOpen(true);else setPane(b.dataset.mobilePane);}));
 document.querySelectorAll('[data-layout-ratio]').forEach(b=>b.addEventListener('click',()=>{setRatio(Number(b.dataset.layoutRatio));b.closest('details').open=false;}));
 const divider=document.querySelector('#workspace-divider');let drag=false;
 divider.addEventListener('pointerdown',e=>{drag=true;divider.setPointerCapture(e.pointerId);document.body.classList.add('resizing');e.preventDefault();});
 divider.addEventListener('pointermove',e=>{if(!drag)return;const box=document.querySelector('#workspace-content').getBoundingClientRect();setRatio((e.clientX-box.left)/(box.width-8));});
 const end=()=>{drag=false;document.body.classList.remove('resizing');};divider.addEventListener('pointerup',end);divider.addEventListener('pointercancel',end);
 divider.addEventListener('keydown',e=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(e.key)){e.preventDefault();setRatio(e.key==='Home'?.5:e.key==='End'?.7:ratio+(e.key==='ArrowLeft'?-.02:.02));}});
 window.addEventListener('resize',()=>{applyRatio();if(window.innerWidth>=1024)closeNav();});
 window.addEventListener('pdf-position',e=>{const p=e.detail;if(p.chapter!==state.chapter||p.version!==state.sectionData?.pdf?.version)return;lastPage=p;persist({lastReading:p,positions:{...(read().positions||{}),[p.document_id+':'+p.version]:p}});const location=document.querySelector('#reading-location');if(location)location.textContent=(window.TutorCourse?.page_label||'教材第')+' '+p.page+' 页';const resume=document.querySelector('#resume-location');if(resume)resume.textContent=(window.TutorCourse?.page_label||'教材第')+' '+p.page+' 页';});
 document.querySelector('#return-chat').addEventListener('click',()=>showHelp(null));
 document.querySelector('#chat-input').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();document.querySelector('#chat-form').requestSubmit();}});
 applyRatio();
 }
 function onView(view){closeNav();setDirectoryOpen(false);setPane(view==='course'&&!readerOpen?'chat':'content');document.body.dataset.workspaceView=view;const slot=document.querySelector('#practice-nav-slot');slot.hidden=view!=='quiz';document.querySelector('#course-panel-body').hidden=view==='quiz'||localStorage.getItem((window.TutorCourse?.id||'experimental-psychology-3')+'-course-collapsed')==='true';document.querySelector('#directory-title').textContent=view==='quiz'?'教材习题':'章节目录';document.querySelector('#course-collapse').hidden=view==='quiz';if(view!=='quiz')showHelp(null);applyRatio();}
 function chapterChanged(){const s=state.sectionData;if(!s)return;document.querySelector('#conversation-title').textContent=s.title||'学习';lastPage=null;}
 function resumeFor(metadata){const value=(read().positions||{})[metadata.document_id+':'+metadata.version];return value?.section===state.section?value:null;}
 function lastReading(){return read().lastReading;}
 function clearDraft(){persist({chatDraft:''});}
 function showHelp(html,title='当前题目讲解',guide=null){helpGuide?.dispose();helpGuide=null;const panel=document.querySelector('#practice-help-panel');panel.hidden=html===null;document.querySelector('#chat-panel').classList.toggle('practice-help-active',html!==null);if(html!==null){document.querySelector('#practice-help-title').textContent=title;document.querySelector('#practice-help-content').innerHTML=html;window.TextbookPDF?.renderMath(document.querySelector('#practice-help-content'));if(guide&&window.GuidedVisualization){const holder=document.createElement('div');document.querySelector('#practice-help-content').append(holder);helpGuide=window.GuidedVisualization.mount(holder,{guide,onSource:ref=>openGuideSource(guide,ref)});}if(state.view!=='quiz')setPane('chat');}}
 return {bind,onView,setPane,setRatio,setReaderOpen,chatChanged,dismissSuggestions,chapterChanged,resumeFor,lastReading,clearDraft,showHelp};
})();
