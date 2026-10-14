/* 隔离静态页面 + API替身，不连接真实后端或模型。 */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const http=require('node:http');
const ROOT=process.env.TASK_TEST_ROOT || 'E:/项目/heart/project/integration/discrete-math-tutor';
(async()=>{
 const server=http.createServer((req,res)=>{
  const url=new URL(req.url,'http://localhost');
  const relative=url.pathname==='/'?'index.html':url.pathname.replace(/^\/static\//,'');
  const file=path.resolve(ROOT,'frontend',relative);
  if(!file.startsWith(path.resolve(ROOT,'frontend')+path.sep)){res.writeHead(404);res.end();return;}
  try{
   let content=fs.readFileSync(file);
   if(relative==='index.html')content=Buffer.from(content.toString().replace(/<script[^>]*(?:mathlive|type="module")[^>]*><\/script>/g,''));
   res.setHeader('Content-Type',relative.endsWith('.js')?'application/javascript':relative.endsWith('.css')?'text/css':relative.endsWith('.json')?'application/json':'text/html');res.end(content);
  }catch{res.writeHead(404);res.end();}
 });
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const BASE_URL='http://127.0.0.1:'+server.address().port;
 const browser=await chromium.launch({headless:false,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 try{
  const context=await browser.newContext();
  const requests=[],pending=new Map(),errors=[];let mode='clarify',recoverFail=false,counter=0,saveFail=false;
  const clarification=(id,revision=1)=>({answer_status:'awaiting_clarification',reply:'你指的是哪个对象？',task_id:id,task_revision:revision,
    clarification:{options:[{id:'obj-one',label:'<img src=x onerror=alert(1)> 图7.11'},{id:'obj-two',label:'定理7.4'}]}});
  await context.route('**/api/**',async route=>{
   const request=route.request(),url=new URL(request.url()),body=request.postDataJSON();let value={};
   if(url.pathname==='/api/course/chapters')value=[{id:1,title:'集合',sections:[{id:1,title:'集合概念'},{id:2,title:'集合运算'}]}];
   else if(url.pathname.includes('/sections/'))value={title:'集合概念',content:'定义1.1 集合。',blocks:[]};
   else if(url.pathname.endsWith('/conversation'))value=[];
   else if(url.pathname.endsWith('/dashboard'))value={activity:[],chapter_scores:[],chapters:[]};
   else if(url.pathname.startsWith('/api/practice/chapters/'))value={total_parts:2,questions:[{id:'fixture-q1',group_id:'1.1',number:1,part_count:2,types:['judgement'],status:'new'}]};
   else if(url.pathname.endsWith('/draft')){
    requests.push({draft:body});if(saveFail){await route.fulfill({status:503,json:{detail:'模拟草稿保存失败'}});return;}value={};
   }else if(url.pathname.startsWith('/api/practice/questions/'))value={version:'1'.repeat(64),answers:{},history:[],help_history:[],question:{id:'fixture-q1',group_id:'1.1',number:1,chapter_id:1,section_id:1,knowledge_point:'集合',source:{page:2,end_page:2},shared_blocks:[],parts:[{id:'p1',label:'小题一',type:'judgement',grader:'rule',stem_blocks:[]},{id:'p2',label:'小题二',type:'judgement',grader:'rule',stem_blocks:[]}]}};
   else if(url.pathname==='/api/chat/tasks/pending'){
    if(recoverFail){await route.fulfill({status:503,json:{detail:'模拟恢复失败'}});return;}
    value={pending:pending.get(url.searchParams.get('student_id')+':'+url.searchParams.get('session_id')) || null};
   }else if(request.method()==='DELETE'){
    requests.push({cancel:body});pending.delete(body.student_id+':'+body.session_id);value={answer_status:'task_cancelled',reply:'已取消'};
   }else if(url.pathname==='/api/chat/stream'){
    requests.push(body);
    if(mode==='invalid'){await route.fulfill({status:422,json:{detail:'题目版本已变化，请重新加载本题'}});return;}
    if(mode==='disconnect'){await route.fulfill({body:'event: progress\ndata: {"order":1,"stage":"retrieving","label":"检索"}\n\n',contentType:'text/event-stream'});return;}
    if(mode==='clarify'){value=clarification('task-'+(++counter));pending.set(body.student_id+':'+body.session_id,value);}
    else if(mode==='conflict'){value={answer_status:'task_expired',reply:'任务已过期'};pending.delete(body.student_id+':'+body.session_id);}
    else{value={answer_status:'answered',reply:'这是解释',task_id:body.task_id || 'done',task_revision:2};pending.delete(body.student_id+':'+body.session_id);}
    await route.fulfill({body:'event: done\ndata: '+JSON.stringify(value)+'\n\n',contentType:'text/event-stream'});return;
   }
   await route.fulfill({json:value});
  });
  const page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));
  const ready=async p=>{await p.waitForFunction(()=>state.taskRecoveryNeeded===false && state.sectionData!==null);};
  const send=async text=>{await page.locator('#chat-input').fill(text);await page.locator('#chat-form').evaluate(form=>form.requestSubmit());await page.waitForFunction(()=>state.sending===false);};
  await page.goto(BASE_URL);await ready(page);
  await send('这个怎么理解？');
  assert.equal(await page.locator('[data-task-option]').count(),2);
  assert.equal(await page.locator('.task-clarification img').count(),0);
  const first=requests.find(r=>r.message);assert(first.session_id && first.request_id);
  mode='complete';await page.locator('[data-task-option="1"]').focus();await page.keyboard.press('Enter');
  await page.waitForFunction(()=>state.sending===false && state.clarification===null);
  const reply=requests.filter(r=>r.message).at(-1);assert.equal(reply.selected_option,'obj-two');assert.equal(reply.task_id,'task-1');assert.equal(reply.task_revision,1);
  assert.equal(reply.reader_location,undefined);assert.equal(reply.selection,undefined);
  console.log('PASS：键盘选择、任务版本及标签转义');
  mode='clarify';await send('还有这个？');const session=await page.evaluate(()=>tabSessionId);
  await page.reload();await ready(page);assert.equal(await page.evaluate(()=>tabSessionId),session);assert.equal(await page.locator('[data-task-cancel]').count(),1);
  const other=await context.newPage();await other.addInitScript(id=>sessionStorage.setItem('discrete-math-task-session',id),session);
  await other.goto(BASE_URL);await ready(other);assert.notEqual(await other.evaluate(()=>tabSessionId),session);assert.equal(await other.locator('[data-task-cancel]').count(),0);
  await other.close();console.log('PASS：刷新恢复及复制标签会话隔离');
  await page.locator('[data-task-cancel]').click();await page.waitForFunction(()=>!state.sending && !state.clarification);assert(requests.some(r=>r.cancel?.session_id===session));
  mode='clarify';await send('新问题');assert.equal(requests.filter(r=>r.message).at(-1).task_id,undefined);
  mode='complete';await send('我指的是定义');assert(requests.filter(r=>r.message).at(-1).task_id);console.log('PASS：取消后新问题及自由文本补充');
  mode='disconnect';await send('测试连接中断');const lost=requests.filter(r=>r.message).at(-1);
  mode='complete';await page.locator('[data-retry-message]').last().click();await page.waitForFunction(()=>!state.sending);assert.deepEqual(requests.filter(r=>r.message).at(-1),lost);console.log('PASS：网络重试使用原始请求');
  mode='clarify';await send('待过期的问题');mode='conflict';await send('补充');assert.equal(await page.locator('[data-task-cancel]').count(),0);console.log('PASS：过期后恢复状态');
  recoverFail=true;await page.reload();await page.locator('[data-task-restore]').waitFor();const count=requests.length;
  await send('不能误接任务');assert.equal(requests.length,count);
  recoverFail=false;await page.locator('[data-task-restore]').click();await ready(page);console.log('PASS：恢复失败阻断与重试恢复');
  mode='clarify';await send('等待选择');
  await page.evaluate(()=>{state.pdfDraft={document_id:'new-pdf',version:'v1',kind:'text',rects:[{page:1}],text:'新的选区',section_title:'新选区'};});
  mode='complete';await send('请解释新选区');
  assert(requests.at(-2).cancel);assert.equal(requests.at(-1).task_id,undefined);assert.equal(requests.at(-1).selection.document_id,'new-pdf');
  await page.evaluate(()=>{state.pdfDraft=null;});console.log('PASS：重新圈选先取消旧任务');
  await page.evaluate(()=>showView('quiz'));await page.locator('[data-practice-ask="p1"]').waitFor();
  await page.locator('[data-answer-part="p1"][value="true"]').check();
  await page.locator('[data-practice-ask="p1"]').click();await page.waitForFunction(()=>state.exerciseDraft?.target.part_id==='p1');
  assert(requests.some(r=>r.draft?.answers.p1==='true'));
  await page.locator('[data-practice-part="p2"]').click();
  mode='clarify';await send('只给提示');let partRequest=requests.filter(r=>r.message).at(-1);
  assert.deepEqual(partRequest.exercise_target,{question_id:'fixture-q1',part_id:'p1',version:'1'.repeat(64)});assert.equal(partRequest.selection,undefined);assert.equal(partRequest.reader_location,undefined);
  assert((await page.locator('.selection-draft').innerText()).includes('小题一'));
  await page.locator('[data-practice-ask="p2"]').click();await page.waitForFunction(()=>state.exerciseDraft?.target.part_id==='p2');assert(requests.at(-1).cancel);
  await page.locator('[data-answer-part="p2"][value="false"]').check();
  mode='complete';await send('解释当前小题');assert.equal(requests.filter(r=>r.message).at(-1).exercise_target.part_id,'p2');
  assert.equal(requests.filter(r=>r.draft).at(-1).draft.answers.p2,'false');
  mode='invalid';await send('测试旧题目版本');assert.equal(await page.locator('[data-retry-message]').last().innerText(),'重新提问');
  assert.equal(await page.evaluate(()=>state.chat.at(-1).networkFailed),false);mode='complete';
  await page.locator('[data-clear-exercise]').click();await page.waitForFunction(()=>!state.sending && !state.exerciseDraft);
  console.log('PASS：实际小题入口保存草稿、固定对象及显式更换/移除');
  saveFail=true;await page.locator('[data-answer-part="p2"][value="true"]').check();await page.locator('[data-practice-ask="p2"]').click();
  await page.waitForFunction(()=>document.querySelector('#toast').textContent.includes('无法准备小题提问'));
  assert.equal(await page.evaluate(()=>!!state.exerciseDraft),false);
  saveFail=false;await page.locator('[data-practice-ask="p2"]').click();await page.waitForFunction(()=>state.exerciseDraft?.target.part_id==='p2');
  await page.locator('[data-clear-exercise]').click();await page.waitForFunction(()=>!state.exerciseDraft);
  console.log('PASS：草稿保存失败不附带小题，重试成功后恢复');
  mode='clarify';await send('等待账户切换');
  const changer=await context.newPage();await changer.goto(BASE_URL);await ready(changer);
  await changer.evaluate(()=>localStorage.setItem('discrete-math-demo-student','test-new-account'));
  await page.waitForFunction(()=>studentId==='test-new-account' && !state.taskRecoveryNeeded);
  assert.equal(await page.locator('[data-task-cancel]').count(),0);await changer.close();console.log('PASS：切换账户清除旧任务界面');
  assert.deepEqual(errors,[]);console.log('浏览器检查全部通过');
 }finally{await browser.close();await new Promise(resolve=>server.close(resolve));}
})().catch(error=>{console.error(error);process.exitCode=1;});
