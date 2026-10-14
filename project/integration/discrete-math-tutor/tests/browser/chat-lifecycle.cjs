/* 隔离页面与 API 替身：验证真实 app.js，不连接学生数据库或模型。 */
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
   res.setHeader('Content-Type',relative.endsWith('.js')?'application/javascript':relative.endsWith('.css')?'text/css':'text/html');res.end(content);
  }catch{res.writeHead(404);res.end();}
 });
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const BASE_URL=process.env.CHAT_TEST_URL || 'http://127.0.0.1:'+server.address().port;
 let browser; let rejectEvidence=false;
 try{
  browser=await chromium.launch({headless:false,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
  const context=await browser.newContext();
  await context.route('**/api/**',async route=>{
   const url=new URL(route.request().url());let value={};
   if(url.pathname==='/api/course/chapters')value=[{id:1,title:'集合',sections:[{id:1,title:'集合概念'}]}];
   else if(url.pathname.includes('/sections/'))value={title:'集合概念',content:'定义1.1 集合。',blocks:[]};
   else if(url.pathname.endsWith('/conversation'))value=[{id:101,role:'assistant',content:'测试消息 $p\\land q$'}];
   else if(url.pathname.endsWith('/dashboard'))value={activity:[],chapter_scores:[],chapters:[]};
   else if(url.pathname==='/api/chat/tasks/pending')value={pending:null};
   else if(url.pathname==='/api/chat/stream'){
    const result=rejectEvidence
     ? {answer_status:'evidence_rejected',reply:'教材证据不足，暂不发布回答',step_advanced:false}
     : {answer_status:'answered',reply:'完成回答 [1]',textbook_sources:['图的定义']};
    await route.fulfill({body:'event: progress\ndata: '+JSON.stringify({order:1,label:'检索',detail:'处理中',status:'running'})+'\n\nevent: done\ndata: '+JSON.stringify(result)+'\n\n',contentType:'text/event-stream'});return;
   }
   await route.fulfill({json:value});
  });
  const page=await context.newPage();const errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.goto(BASE_URL);
  await page.waitForFunction(()=>!state.taskRecoveryNeeded && state.sectionData && state.chat[0]?.conversationId===101);
  await page.evaluate(()=>{
   window.testCounts={mount:0,update:0,dispose:0,math:0};
   window.TextbookPDF={renderMath:p=>{testCounts.math++;p.dataset.math='rendered';}};
   chatRenderer.refreshMath();
   const key=state.chat[0].renderKey;
   window.testKey=key;window.testRow=chatRenderer.rows.get(key).element;
   window.testParagraph=testRow.querySelector('[data-message-part="content"] p');
   window.testAdapter={mount(host){
    testCounts.mount++;const input=document.createElement('input');input.value='学生修改的状态';host.append(input);
    window.testInput=input;
    return {update(){testCounts.update++;},dispose(){testCounts.dispose++;}};
   }};
   chatRenderer.attachComponent(key,'fixture',testAdapter,{});
  });
  await page.locator('.message-components input').focus();
  const check=await page.evaluate(()=>{
   const m=state.chat[0];m.startedAt=Date.now();m.pending=true;m.progress=[];
   for(let i=0;i<20;i++){m.progress=[{order:1,label:'检索',detail:'进度 '+i,status:'running'}];renderChat();}
   const focusKept=document.activeElement===testInput;
   testRow.querySelector('details').open=false;
   m.progress[0].detail='新进度';renderChat();
   const collapsed=!testRow.querySelector('details').open;
   m.pending=false;m.finishedAt=Date.now();m.content='最后的内容 $p$';renderChat();
   chatRenderer.attachComponent(testKey,'fixture',testAdapter,{});
   return {sameRow:chatRenderer.rows.get(testKey).element===testRow,sameInput:testInput.isConnected,
    inputValue:testInput.value,focusKept,collapsed,counts:{...testCounts}};
  });
  assert.equal(check.sameRow,true);assert.equal(check.sameInput,true);assert.equal(check.focusKept,true);
  assert.equal(check.inputValue,'学生修改的状态');assert.equal(check.collapsed,true);
  assert.deepEqual(check.counts,{mount:1,update:1,dispose:0,math:2});
  console.log('PASS：20 次进度更新和最终回答保留组件、焦点与折叠状态，正文变化才重渲染公式');

  await page.locator('#chat-input').fill('追加问题');await page.locator('#chat-form').evaluate(form=>form.requestSubmit());
  await page.waitForFunction(()=>!state.sending && state.chat.length===3);
  assert.equal(await page.evaluate(()=>testInput.isConnected && testCounts.mount===1),true);
  assert.equal(await page.locator('.message-source').last().textContent(),'[1] 教材：图的定义');
  const styles=await page.evaluate(()=>({
   assistant:getComputedStyle(document.querySelector('.message.assistant [data-message-part="content"] p')).whiteSpace,
   user:getComputedStyle(document.querySelector('.message.user [data-message-part="content"] p')).marginBottom,
  }));
  assert.deepEqual(styles,{assistant:'pre-wrap',user:'0px'});
  console.log('PASS：实际流式发送、追加消息和教材引用保留旧组件');
  rejectEvidence=true;
  await page.locator('#chat-input').fill('验证证据不足');await page.locator('#chat-form').evaluate(form=>form.requestSubmit());
  await page.waitForFunction(()=>!state.sending && state.chat.length===5);
  assert.equal(await page.evaluate(()=>state.chat.at(-1).failed),true);
  assert.match(await page.locator('.message.assistant').last().textContent(),/处理未完成/);
  console.log('PASS：证据拒绝的真实流式结果显示处理未完成');

  const checks=await page.evaluate(()=>{
   // 重排后引用索引应同步，历史 ID 应保持；模拟页面视图切换。
   showView('learning');showView('course');
   const kept=testInput.isConnected;
   state.chat.reverse();renderChat();
   const reordered=document.querySelector('#chat-messages').lastElementChild===testRow;
   const stable=messagesFromHistory([{id:101,role:'assistant',content:'重复'}])[0].renderKey===testKey;
   const identical=messagesFromHistory([{id:201,role:'assistant',content:'相同'},{id:202,role:'assistant',content:'相同'}]);
   const distinct=identical[0].renderKey!==identical[1].renderKey;
   const m=state.chat.find(row=>row.renderKey===testKey);
   m.content='<img src=x onerror=alert(1)>';renderChat();
   const escaped=!testRow.querySelector('[data-message-part="content"] img');
   const el=document.querySelector('#chat-messages');el.style.height='160px';el.style.flex='none';
   state.chat=Array.from({length:20},(_,i)=>({role:'assistant',content:'长消息 '.repeat(50),renderKey:'scroll-'+i}));renderChat();
   const disposed=testCounts.dispose;
   el.scrollTop=0;state.chat.push({role:'assistant',content:'最新消息'});renderChat();
   const scrollStayed=el.scrollTop===0 && el.scrollHeight>el.clientHeight+100;
   el.scrollTop=el.scrollHeight;state.chat.push({role:'assistant',content:'跟随底部'});renderChat();
   const bottom=el.scrollHeight-el.scrollTop-el.clientHeight<2;
   state.chat=[];renderChat();renderChat();
   return {kept,reordered,stable,distinct,escaped,disposed,scrollStayed,bottom,disposeOnce:testCounts.dispose===1,
    empty:document.querySelectorAll('#chat-messages > .message').length===1};
  });
  assert.deepEqual(checks,{kept:true,reordered:true,stable:true,distinct:true,escaped:true,disposed:1,scrollStayed:true,bottom:true,disposeOnce:true,empty:true});
  console.log('PASS：视图切换、重排、稳定历史 ID、转义、滚动和组件一次释放');
  await page.reload();await page.waitForFunction(()=>state.chat[0]?.conversationId===101);
  assert.equal(await page.evaluate(()=>state.chat[0].renderKey),await page.evaluate(()=>messagesFromHistory([{id:101}])[0].renderKey));
  assert.deepEqual(errors,[]);console.log('浏览器检查全部通过');
 }finally{await browser?.close();await new Promise(resolve=>server.close(resolve));}
})().catch(error=>{console.error(error);process.exitCode=1;});
