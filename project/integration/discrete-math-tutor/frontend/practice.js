"use strict";
// 与教材阅读共用学生身份；每个异步结果都绑定题目和请求编号。
window.ExercisePractice=(()=>{
 if(window.MathfieldElement){MathfieldElement.fontsDirectory='/static/mathlive/fonts';MathfieldElement.soundsDirectory='/static/mathlive/sounds';}
 const P={chapter:null,index:null,data:null,seq:0,answers:{},saved:{},saveChain:Promise.resolve(),dirty:false,saveTimer:null,filters:{group:'',status:''},pollToken:0,help:{},busy:false};
 const types={choice:'选择',fill:'填空',expression:'公式计算',proof:'证明',graph:'构图',matrix:'矩阵 / 真值表',judgement:'判断',written:'问答'};
 const statuses={new:'未作答',draft:'草稿',queued:'等待批改',grading:'批改中',completed:'已反馈',failed:'需重试'};
 const param=()=>'?student_id='+encodeURIComponent(studentId);
 const host=()=>$('#quiz-area');
 function announce(text){const e=$('#practice-save-status');if(e)e.textContent=text;}
 function blocks(bs){return (bs||[]).map(renderBlock).join('');}
 function snapshot(){return JSON.parse(JSON.stringify(P.answers));}
 function filled(a){if(typeof a==='string')return !!a.trim();if(Array.isArray(a))return a.some(filled);if(a&&typeof a==='object'&&'nodes' in a)return !!a.nodes.length||filled(a.note);return a&&typeof a==='object'?Object.entries(a).some(([k,v])=>!['directed','id','x','y','label'].includes(k)&&filled(v)):false;}
 async function save(){
  clearTimeout(P.saveTimer);
  if(!P.data||!P.dirty)return P.saveChain;
  const qid=P.data.question.id,version=P.data.version,answers=snapshot(),serial=JSON.stringify(answers);P.dirty=false;
  // 本地副本先保存，网络恢复后可继续；按顺序写服务端，避免旧草稿覆盖新答案。
  localStorage.setItem('exercise-draft:'+studentId+':'+qid,JSON.stringify({version,answers}));
  P.saveChain=P.saveChain.catch(()=>{}).then(async()=>{
   try{await api('/api/practice/questions/'+qid+'/draft',{method:'PUT',body:JSON.stringify({student_id:studentId,version,answers})});
    const local=JSON.parse(localStorage.getItem('exercise-draft:'+studentId+':'+qid)||'null');
    if(local&&JSON.stringify(local.answers)===serial)localStorage.removeItem('exercise-draft:'+studentId+':'+qid);
    if(P.data?.question.id===qid&&JSON.stringify(P.answers)===serial){announce('草稿已保存');P.saved=answers;}}
   catch(e){if(P.data?.question.id===qid){P.dirty=true;announce('本地已保存，服务端保存失败：'+e.message);}throw e;}
  });return P.saveChain;
 }
 function changed(){P.dirty=true;announce('正在保存…');clearTimeout(P.saveTimer);P.saveTimer=setTimeout(()=>save().catch(()=>{}),650);updateIndex('draft');}
 function updateIndex(status,submission){
  const i=P.index?.questions.find(q=>q.id===P.data?.question.id);
  if(i){i.status=status;if(submission)i.submission=submission;renderList();}
 }
 function renderList(){
  const list=$('#practice-question-list');if(!list||!P.index)return;
  const qs=P.index.questions.filter(q=>(!P.filters.group||q.group_id===P.filters.group)&&(!P.filters.status||q.status===P.filters.status));
  list.innerHTML=qs.length?qs.map(q=>'<button type="button" data-practice-question="'+q.id+'" class="practice-question-link '+(P.data?.question.id===q.id?'selected':'')+'"><span>练习 '+esc(q.group_id)+' · 第 '+q.number+' 题</span><small>'+q.part_count+' 小题 · '+q.types.map(t=>types[t]).join('、')+'</small><em>'+statuses[q.status]+'</em></button>').join(''):'<p class="resource-note">当前筛选没有题目。</p>';
  const done=P.index.questions.filter(q=>q.status==='completed').length;
  $('#practice-count').textContent=done+' / '+P.index.questions.length+' 题已提交';
 }
 async function load(chapter,section=null){
  if(P.data)await save().catch(()=>{});
  const seq=++P.seq;P.pollToken++;P.chapter=chapter;P.data=null;P.answers={};P.dirty=false;P.filters={group:'',status:''};
  state.quizChapter=chapter;$('#quiz-chapter').value=String(chapter);
  $('#textbook-exercises').innerHTML='';$('#textbook-exercises').hidden=true;
  host().innerHTML='<div class="resource-note" role="status">正在加载教材习题…</div>';
  try{
   const index=await api('/api/practice/chapters/'+chapter+param());if(seq!==P.seq)return;
   P.index=index;
   host().innerHTML='<div class="practice-summary"><strong>本章 '+index.questions.length+' 道题 · '+index.total_parts+' 个小题</strong><span id="practice-count"></span></div><div class="practice-workspace"><aside class="practice-sidebar"><label for="practice-group">练习组</label><select id="practice-group" class="select-field"><option value="">全部练习</option>'+[...new Set(index.questions.map(q=>q.group_id))].map(g=>'<option>'+g+'</option>').join('')+'</select><label for="practice-filter">作答状态</label><select id="practice-filter" class="select-field"><option value="">全部状态</option><option value="new">未作答</option><option value="draft">草稿</option><option value="completed">已反馈</option><option value="failed">需重试</option></select><nav id="practice-question-list" aria-label="教材题目列表"></nav></aside><article id="practice-question" aria-live="polite"></article></div>';
   const title=state.chapters.find(c=>c.id===chapter)?.sections.find(s=>s.id===section)?.title||'';const group=title.match(/^(\d+\.\d+)/)?.[1];if(group&&index.questions.some(q=>q.group_id===group)){P.filters.group=group;$('#practice-group').value=group;}
   renderList();const groupQuestions=index.questions.filter(q=>!P.filters.group||q.group_id===P.filters.group);await open(groupQuestions.find(q=>q.status==='draft')?.id||groupQuestions[0].id);
  }catch(e){if(seq===P.seq)host().innerHTML='<div class="resource-note">'+esc(e.message)+'<button type="button" data-practice-reload>重新加载</button></div>';}
 }
 async function open(qid){
  await save().catch(()=>{});const seq=++P.seq;P.pollToken++;P.busy=false;
  const area=$('#practice-question');if(!area)return;area.innerHTML='<p class="resource-note" role="status">正在读取题目和草稿…</p>';
  try{
   const data=await api('/api/practice/questions/'+qid+param());if(seq!==P.seq)return;
   P.data=data;P.answers=JSON.parse(JSON.stringify(data.answers));P.saved=JSON.parse(JSON.stringify(data.answers));P.help={};for(const k of Object.keys(graphUI))delete graphUI[k];
   const local=JSON.parse(localStorage.getItem('exercise-draft:'+studentId+':'+qid)||'null');
   if(local?.version===data.version&&JSON.stringify(local.answers)!==JSON.stringify(data.answers)){P.answers=local.answers;P.dirty=true;}
   renderQuestion();renderList();$('#practice-question').scrollIntoView({block:'start',behavior:'instant'});if(P.dirty)save().catch(()=>{});
   const last=data.history[0];if(last&&['queued','grading'].includes(last.status))poll(last,++P.pollToken);
  }catch(e){if(seq===P.seq)area.innerHTML='<div class="resource-note">'+esc(e.message)+'</div>';}
 }
 function mathField(pid,key,value='',index=''){
  return '<math-field data-answer-part="'+pid+'" data-answer-key="'+key+'" data-answer-index="'+index+'" aria-label="'+esc(key==='fill'?'填空 '+(Number(index)+1):'数学公式')+'" math-virtual-keyboard-policy="manual">'+esc(value)+'</math-field>';
 }
 function widget(p,a){
  const pid=p.id;
  if(p.type==='choice')return '<div class="practice-options">'+p.options.map(o=>'<label class="quiz-option"><input type="'+(p.multiple?'checkbox':'radio')+'" name="practice-'+pid+'" data-answer-part="'+pid+'" data-answer-key="choice" value="'+o.key+'" '+((a||[]).includes(o.key)?'checked':'')+'><span><strong>'+o.key+'.</strong>'+blocks(o.blocks)+'</span></label>').join('')+'</div>';
  if(p.type==='judgement')return '<div class="practice-options">'+[['true','正确'],['false','错误']].map(([v,t])=>'<label class="quiz-option"><input type="radio" name="practice-'+pid+'" data-answer-part="'+pid+'" data-answer-key="judgement" value="'+v+'" '+(a===v?'checked':'')+'>'+t+'</label>').join('')+'</div>';
  if(p.type==='fill')return '<div class="practice-blanks">'+Array.from({length:Array.isArray(a)?a.length:p.blank_count},(_,i)=>'<label>第 '+(i+1)+' 空'+mathField(pid,'fill',a?.[i]||'',i)+'</label>').join('')+'</div><small>可输入数值、集合、数学表达式；各空按题面顺序填写。</small>'+(p.grader==='rule'?'':'<div class="part-actions"><button type="button" class="secondary-button" data-fill-add="'+pid+'">增加一空</button><button type="button" class="secondary-button" data-fill-remove="'+pid+'">删除最后一空</button></div>');
  if(p.type==='matrix'){
   const fmt=p.answer_format;const cells=a?.cells||Array.from({length:fmt?.rows||2},()=>Array(fmt?.cols||2).fill(''));return (fmt?'<p class="resource-note">'+esc(fmt.instruction)+'</p>':'')+ '<div class="matrix-tools"><label>行 <input type="number" min="1" max="15" value="'+cells.length+'" data-grid-rows="'+pid+'"></label><label>列 <input type="number" min="1" max="15" value="'+cells[0].length+'" data-grid-cols="'+pid+'"></label><button type="button" class="secondary-button" data-grid-resize="'+pid+'">调整表格</button></div><div class="answer-grid-wrap"><table class="answer-grid">'+cells.map((r,i)=>'<tr>'+r.map((v,j)=>'<td><input aria-label="第'+(i+1)+'行第'+(j+1)+'列" data-answer-part="'+pid+'" data-answer-key="cell" data-row="'+i+'" data-col="'+j+'" value="'+esc(v)+'"></td>').join('')+'</tr>').join('')+'</table></div><label>列名、推导或补充说明<textarea data-answer-part="'+pid+'" data-answer-key="note" rows="3">'+esc(a?.note||'')+'</textarea></label>';
  }
  if(p.type==='graph')return '<div class="graph-tools"><button type="button" class="secondary-button" data-graph-mode="'+pid+':node">添加顶点</button><button type="button" class="secondary-button" data-graph-mode="'+pid+':edge">连接两点</button><button type="button" class="secondary-button" data-graph-undo="'+pid+'">撤销一步</button><label><input type="checkbox" data-answer-part="'+pid+'" data-answer-key="directed" '+(a?.directed?'checked':'')+'>有向图</label></div><p class="graph-instruction" id="graph-tip-'+pid+'">点击空白处添加顶点；连接模式下依次点击两个顶点。</p><svg class="answer-graph" data-graph="'+pid+'" viewBox="0 0 600 300" role="img" aria-label="构图作答画布"></svg><label>图的定义、顶点名称与补充说明<textarea data-answer-part="'+pid+'" data-answer-key="note" rows="3">'+esc(a?.note||'')+'</textarea></label>';
  return '<label>'+ (p.type==='proof'?'证明过程 / 推导步骤':'答案 / 推导说明')+'<textarea data-answer-part="'+pid+'" data-answer-key="text" rows="'+(p.type==='proof'?6:3)+'" placeholder="写出你的思路和步骤">'+esc(a?.text||'')+'</textarea></label><label>公式输入'+mathField(pid,'latex',a?.latex||'')+'</label>';
 }
 function renderQuestion(){
  const q=P.data.question;
  $('#practice-question').innerHTML='<header class="exercise-title"><span>练习 '+esc(q.group_id)+' · 第 '+q.number+' 题</span><h2>'+esc(q.knowledge_point)+'</h2><span class="source-label">原教材第 '+q.source.page+(q.source.end_page!==q.source.page?'—'+q.source.end_page:'')+' 页 · 题号按教材保留</span><button type="button" class="secondary-button" data-practice-reading>回教材复习</button><span id="practice-save-status" role="status">草稿已加载</span></header>'+blocks(q.shared_blocks)+q.parts.map(p=>'<section class="interactive-part" data-part="'+p.id+'"><div class="part-heading"><h3>'+esc(p.label)+'</h3><span>'+types[p.type]+'</span><small>'+ (p.grader==='rule'?'规则判分':'AI 辅助批改')+'</small></div><div class="exercise-stem">'+blocks(p.stem_blocks)+'</div><div class="answer-widget">'+widget(p,P.answers[p.id])+'</div><div class="part-actions"><button type="button" class="secondary-button" data-practice-hint="'+p.id+'">提示</button><button type="button" class="secondary-button" data-practice-explain="'+p.id+'">AI 讲解</button></div><div id="help-'+p.id+'" class="exercise-help" aria-live="polite"></div><div id="feedback-'+p.id+'" class="exercise-feedback"></div></section>').join('')+'<footer class="practice-actions"><button type="button" class="primary-button" data-practice-submit>提交已作答的小题</button><button type="button" class="secondary-button" data-practice-save>保存草稿</button><button type="button" class="secondary-button" data-practice-redo>重做本题</button><button type="button" class="secondary-button" data-practice-next>下一题 →</button><div id="practice-submit-status" role="status"></div></footer><details class="practice-history"><summary>历次提交记录</summary><div id="practice-history"></div></details>';
  if(window.MathfieldElement){MathfieldElement.fontsDirectory='/static/mathlive/fonts';MathfieldElement.soundsDirectory='/static/mathlive/sounds';}
  q.parts.filter(p=>p.type==='matrix'||p.type==='graph').forEach(p=>{if(!P.answers[p.id])P.answers[p.id]=p.type==='matrix'?{cells:Array.from({length:p.answer_format?.rows||2},()=>Array(p.answer_format?.cols||2).fill('')),note:''}:{nodes:[],edges:[],directed:false,note:''};if(p.type==='graph')drawGraph(p.id);});
  for(const p of q.parts){const h=(P.data.help_history||[]).find(h=>h.part_id===p.id);const level=Math.max(0,...(P.data.help_history||[]).filter(h=>h.part_id===p.id&&h.action==='hint').map(h=>h.level));P.help[p.id]={busy:false,level};if(h){const target=$('#help-'+p.id);target.innerHTML='<strong>已保存的'+(h.action==='hint'?'提示 '+h.level+'/3':'AI 讲解')+'</strong><p>'+esc(h.response.reply)+'</p>';window.TextbookPDF?.renderMath(target);}}
  if(P.data.history[0])feedback(P.data.history[0]);renderHistory();
 }
 function renderHistory(){const el=$('#practice-history');if(!el)return;el.innerHTML=P.data.history.length?P.data.history.map(s=>'<div class="history-entry"><button type="button" data-practice-history="'+s.id+'">'+esc(new Date(s.created_at+'Z').toLocaleString())+' · '+statuses[s.status]+'</button></div>').join(''):'<p>还没有提交记录。</p>';}
 function feedback(sub){
  if(!P.data||sub.question_id!==P.data.question.id)return;
  for(const p of P.data.question.parts){const el=$('#feedback-'+p.id);if(el){el.innerHTML='';el.className='exercise-feedback';}}
  if(sub.status==='failed'){$('#practice-submit-status').textContent=sub.result.error;return;}
  if(sub.status!=='completed'){$('#practice-submit-status').textContent=sub.status==='queued'?'已保存提交，等待批改…':'正在核对作答与教材…';return;}
  const v={correct:'正确',incorrect:'需要改正',partial:'部分正确',uncertain:'待核对'};
  for(const r of sub.result.parts){const el=$('#feedback-'+r.part_id);if(!el)continue;el.classList.add(r.verdict);el.innerHTML='<strong>'+v[r.verdict]+' · '+(r.confirmed?'规则判分':r.method==='rule'?'规则无法确定，待核对':'AI 建议，尚未人工核对')+(r.score!==null?' · '+r.score+' 分':'')+'</strong><p>'+esc(r.feedback)+'</p>'+((r.steps||[]).length?'<ol>'+r.steps.map(s=>'<li>'+esc(s)+'</li>').join('')+'</ol>':'')+((r.criteria||[]).length?'<ul class="rubric-feedback">'+r.criteria.map(c=>'<li><strong>'+esc(c.label)+' '+c.score+'/'+c.max_score+'</strong> '+esc(c.feedback)+'</li>').join('')+'</ul>':'')+'<details><summary>查看参考解答</summary><div>'+esc(Array.isArray(r.reference_answer)?r.reference_answer.join('、'):r.reference_answer)+'</div></details>';window.TextbookPDF?.renderMath(el);}
  $('#practice-submit-status').textContent='已反馈 '+sub.result.answered_parts+' / '+sub.result.total_parts+' 个小题'+(sub.result.needs_review?'；部分反馈尚未确认，请结合具体步骤核对。':'；规则判分已完成。')+' 反馈针对本次提交的答案；修改草稿后需重新提交。';
 }
 async function poll(sub,token){
  feedback(sub);
  while(['queued','grading'].includes(sub.status)){
   await new Promise(r=>setTimeout(r,1400));if(token!==P.pollToken)return;
   try{sub=await api('/api/practice/submissions/'+sub.id+param());}catch(e){$('#practice-submit-status').textContent='暂时无法读取批改进度，可重新打开本题恢复。';return;}
   if(token!==P.pollToken)return;feedback(sub);
  }
  updateIndex(sub.status,sub);P.busy=false;const b=$('[data-practice-submit]');if(b)b.disabled=false;
  P.data.history=[sub,...P.data.history.filter(s=>s.id!==sub.id)];renderHistory();refreshStats();
 }
 async function submit(){
  if(P.busy)return;if(!Object.values(P.answers).some(filled)){toast('请先完成至少一个小题');return;}
  P.busy=true;const qid=P.data.question.id,version=P.data.version,answers=snapshot();$('[data-practice-submit]').disabled=true;
  try{
   await save();const storageKey='exercise-submit:'+studentId+':'+qid;const cached=JSON.parse(localStorage.getItem(storageKey)||'null');const serial=JSON.stringify(answers);const request_id=cached?.serial===serial?cached.id:crypto.randomUUID();localStorage.setItem(storageKey,JSON.stringify({id:request_id,serial}));
   const s=await post('/api/practice/questions/'+qid+'/submit',{student_id:studentId,version,answers,request_id});localStorage.removeItem(storageKey);
   if(P.data?.question.id!==qid)return;updateIndex(s.status,s);poll(s,++P.pollToken);
  }catch(e){if(P.data?.question.id===qid){P.busy=false;$('[data-practice-submit]').disabled=false;$('#practice-submit-status').textContent=e.message;}}
 }
 async function help(pid,action){
  const qid=P.data.question.id,seq=P.seq,version=P.data.version,answers=snapshot(),target=$('#help-'+pid);if(P.help[pid]?.busy)return;
  const level=action==='hint'?Math.min(3,(P.help[pid]?.level||0)+1):1;P.help[pid]={busy:true,level};target.innerHTML='<p role="status">正在读取教材和你的相关学习记录…</p>';
  try{await save();const r=await post('/api/practice/questions/'+qid+'/help',{student_id:studentId,version,answers,part_id:pid,action,level});
   if(seq!==P.seq)return;target.innerHTML='<strong>'+ (action==='hint'?'提示 '+level+'/3':'AI 讲解')+'</strong><p>'+esc(r.reply)+'</p><small>'+esc(r.memory_summary)+'</small>';window.TextbookPDF?.renderMath(target);
  }catch(e){if(seq===P.seq)target.textContent=e.message;}finally{if(seq===P.seq)P.help[pid]={busy:false,level};}
 }
 function input(e){
  const el=e.target.closest?.('[data-answer-part]');if(!el||!P.data)return;const pid=el.dataset.answerPart,k=el.dataset.answerKey,p=P.data.question.parts.find(p=>p.id===pid);if(!p)return;
  if(k==='choice')P.answers[pid]=[...host().querySelectorAll('[data-answer-part="'+pid+'"][data-answer-key="choice"]:checked')].map(e=>e.value);
  else if(k==='judgement')P.answers[pid]=el.value;
  else if(k==='fill'){if(!Array.isArray(P.answers[pid]))P.answers[pid]=Array(p.blank_count).fill('');P.answers[pid][Number(el.dataset.answerIndex)]=el.value;}
  else if(k==='cell'){P.answers[pid].cells[Number(el.dataset.row)][Number(el.dataset.col)]=el.value;}
  else {if(!P.answers[pid])P.answers[pid]={};P.answers[pid][k]=k==='directed'?el.checked:el.value;if(k==='directed')drawGraph(pid);}
  changed();
 }
 const graphUI={};
 function drawGraph(pid){const svg=$('[data-graph="'+pid+'"]'),a=P.answers[pid];if(!svg||!a)return;
  svg.innerHTML='<defs><marker id="arrow-'+pid+'" markerWidth="9" markerHeight="9" refX="23" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8" fill="#557ad8"/></marker></defs>'+a.edges.map(([x,y])=>{const n=a.nodes.find(n=>n.id===x),m=a.nodes.find(n=>n.id===y);return x===y?'<path d="M '+(n.x*600)+' '+(n.y*300-12)+' a 18 18 0 1 1 1 0" fill="none" stroke="#557ad8" stroke-width="2"/>':'<line x1="'+n.x*600+'" y1="'+n.y*300+'" x2="'+m.x*600+'" y2="'+m.y*300+'" stroke="#557ad8" stroke-width="2" '+(a.directed?'marker-end="url(#arrow-'+pid+')"':'')+'/>';}).join('')+a.nodes.map(n=>'<g data-node="'+n.id+'"><circle cx="'+n.x*600+'" cy="'+n.y*300+'" r="15" fill="'+(graphUI[pid]?.first===n.id?'#ffd88e':'#e1eaff')+'" stroke="#557ad8" stroke-width="2"/><text x="'+n.x*600+'" y="'+(n.y*300+5)+'" text-anchor="middle" font-size="12">'+esc(n.label)+'</text></g>').join('');
 }
 function graphClick(e,svg){const pid=svg.dataset.graph,a=P.answers[pid],g=graphUI[pid]||(graphUI[pid]={mode:'node',undo:[]});const n=e.target.closest('[data-node]');
  if(g.mode==='edge'){if(!n){g.first=null;drawGraph(pid);return;}if(!g.first){g.first=n.dataset.node;drawGraph(pid);return;}if(a.edges.length>=200){toast('最多 200 条边');return;}g.undo.push(JSON.parse(JSON.stringify(a)));a.edges.push([g.first,n.dataset.node]);g.first=null;}
  else {if(n)return;if(a.nodes.length>=60){toast('最多 60 个顶点');return;}g.undo.push(JSON.parse(JSON.stringify(a)));const box=svg.getBoundingClientRect();const next=Math.max(0,...a.nodes.map(n=>Number(n.id.slice(1))))+1;a.nodes.push({id:'n'+next,label:'v'+next,x:Math.min(.96,Math.max(.04,(e.clientX-box.left)/box.width)),y:Math.min(.94,Math.max(.06,(e.clientY-box.top)/box.height))});}
  drawGraph(pid);changed();
 }
 document.addEventListener('input',input);
 document.addEventListener('change',e=>{if(e.target.id==='practice-group'){P.filters.group=e.target.value;renderList();}if(e.target.id==='practice-filter'){P.filters.status=e.target.value;renderList();}});
 document.addEventListener('click',async e=>{
  const el=e.target.closest('button,svg');if(!el)return;
  if(el.dataset.exerciseReview){showView('quiz');await load(Number(el.dataset.reviewChapter));await open(el.dataset.exerciseReview);return;}
  if(el.dataset.practiceQuestion){await open(el.dataset.practiceQuestion);return;}
  if(el.hasAttribute('data-practice-reload')){load(P.chapter);return;}
  if(!P.data)return;
  if(el.hasAttribute('data-practice-submit')){submit();return;}
  if(el.hasAttribute('data-practice-save')){save().then(()=>announce('草稿已保存')).catch(e=>toast(e.message));return;}
  if(el.dataset.practiceHint){help(el.dataset.practiceHint,'hint');return;}
  if(el.dataset.practiceExplain){help(el.dataset.practiceExplain,'explain');return;}
  if(el.hasAttribute('data-practice-reading')){await save().catch(()=>{});await selectSection(P.data.question.chapter_id,P.data.question.section_id,{record:false});showView('course');return;}
  if(el.hasAttribute('data-practice-next')){const i=P.index.questions.findIndex(q=>q.id===P.data.question.id);if(P.index.questions[i+1])open(P.index.questions[i+1].id);else toast('已到本章最后一题');return;}
  if(el.hasAttribute('data-practice-redo')){if(P.busy){toast('请等待本次批改结束再重做');return;}P.answers={};P.help={};renderQuestion();for(const f of $$('.exercise-feedback'))f.innerHTML='';$('#practice-submit-status').textContent='已开始新一轮作答；历次提交保留。';changed();return;}
  if(el.dataset.practiceHistory){const s=P.data.history.find(s=>s.id===el.dataset.practiceHistory);if(s)feedback(s);return;}
  if(el.dataset.fillAdd||el.dataset.fillRemove){const pid=el.dataset.fillAdd||el.dataset.fillRemove,p=P.data.question.parts.find(p=>p.id===pid);const a=P.answers[pid]||(P.answers[pid]=Array(p.blank_count).fill(''));if(el.dataset.fillAdd&&a.length<20)a.push('');if(el.dataset.fillRemove&&a.length>1)a.pop();renderQuestion();changed();return;}
  if(el.dataset.gridResize){const pid=el.dataset.gridResize,rows=Math.max(1,Math.min(15,Number($('[data-grid-rows="'+pid+'"]').value)||2)),cols=Math.max(1,Math.min(15,Number($('[data-grid-cols="'+pid+'"]').value)||2)),a=P.answers[pid];a.cells=Array.from({length:rows},(_,i)=>Array.from({length:cols},(_,j)=>a.cells[i]?.[j]||''));renderQuestion();changed();return;}
  if(el.dataset.graphMode){const [pid,mode]=el.dataset.graphMode.split(':');graphUI[pid]={...(graphUI[pid]||{undo:[]}),mode,first:null};$('#graph-tip-'+pid).textContent=mode==='node'?'点击空白处添加顶点。':'依次点击两个顶点连接；重复连接表示重边。';drawGraph(pid);return;}
  if(el.dataset.graphUndo){const pid=el.dataset.graphUndo,a=graphUI[pid]?.undo.pop();if(a){P.answers[pid]=a;drawGraph(pid);changed();}return;}
  const svg=e.target.closest('svg[data-graph]');if(svg)graphClick(e,svg);
 });
 window.addEventListener('beforeunload',()=>{if(P.data&&P.dirty)localStorage.setItem('exercise-draft:'+studentId+':'+P.data.question.id,JSON.stringify({version:P.data.version,answers:P.answers}));});
 return {load,save};
})();
