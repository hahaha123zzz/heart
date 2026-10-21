/* 隔离页面与 API 替身：验证真实 app.js，不连接学生数据库或模型。 */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const http=require('node:http');
const ROOT=process.env.TASK_TEST_ROOT || 'E:/项目/heart/project/integration/discrete-math-tutor';
(async()=>{
 let delayed=false,delayedClosed=false,delayedRequests=0,releaseFinal;
 const server=http.createServer((req,res)=>{
  const url=new URL(req.url,'http://localhost');
  if(url.pathname==='/api/chat/stream'){
   delayedRequests++;req.resume();
   const identity={task_id:'delayed-task',task_revision:1,answer_id:'delayed-answer',round_id:1};
   const frame=(event,data)=>`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
   res.writeHead(200,{'Content-Type':'text/event-stream; charset=utf-8','Cache-Control':'no-cache'});
   res.flushHeaders();
   res.write(frame('answer_state',{...identity,seq:1,state:'generating'}));
   res.write(frame('answer_delta',{...identity,seq:2,text:'延迟关闭前可读。'}));
   // 只由浏览器确认正文可见后释放，证明不是响应结束后的播放动画。
   releaseFinal=()=>{delayedClosed=true;res.end(frame('done',{answer_status:'answered',reply:'延迟关闭前可读。完整收尾。',...identity}));};
   return;
  }
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
 let browser; let rejectEvidence=false; let recoverStream=false; let deletedRecovery=false; let generationRequests=0;
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
   else if(url.pathname.startsWith('/api/chat/requests/')){
    if(deletedRecovery){await route.fulfill({status:410,json:{detail:{message:'相关记忆已删除'}}});return;}
    value={task_id:'recover-task',task_revision:3,status:'completed',event_replay_enabled:true,result:{answer_status:'answered',reply:'恢复后的回答 [1]'}};
   }
   else if(url.pathname==='/api/chat/tasks/recover-task/events'){
    const result={answer_status:'answered',reply:'恢复后的回答 [1]',textbook_sources:['图的定义'],task_id:'recover-task',task_revision:3};
    await route.fulfill({body:'id: recover-task:3:1\nevent: sources\ndata: {"sources":[]}\n\nid: recover-task:3:2\nevent: done\ndata: '+JSON.stringify(result)+'\n\n',contentType:'text/event-stream'});return;
   }
   else if(url.pathname==='/api/chat/stream'){
    if(delayed){await route.continue();return;}
    generationRequests++;
    if(recoverStream){await route.fulfill({body:'event: progress\ndata: {"order":1,"label":"保存","status":"running"}\n\n',contentType:'text/event-stream'});return;}
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
   const renderer=window.TutorMarkdown.render;window.markdownRenderCalls=0;
   window.TutorMarkdown.render=(...args)=>{markdownRenderCalls++;return renderer(...args);};
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
  assert.equal(await page.evaluate(()=>markdownRenderCalls),1);
  console.log('PASS：20 次进度更新和最终回答保留组件、焦点与折叠状态，正文变化才重渲染公式');

  await page.locator('#chat-input').fill('追加问题');await page.locator('#chat-form').evaluate(form=>form.requestSubmit());
  await page.waitForFunction(()=>!state.sending && state.chat.length===3);
  assert.equal(await page.evaluate(()=>testInput.isConnected && testCounts.mount===1),true);
  assert.equal(await page.locator('.message-source').count(),0);
  await page.locator('.message.assistant').last().locator('[data-tutor-citation="1"]').click();
  assert.equal(await page.locator('.citation-title').textContent(),'图的定义');
  await page.keyboard.press('Escape');
  const styles=await page.evaluate(()=>({
   assistant:getComputedStyle(document.querySelector('.message.assistant [data-message-part="content"] p')).whiteSpace,
   user:getComputedStyle(document.querySelector('.message.user [data-message-part="content"] p')).marginBottom,
  }));
  assert.deepEqual(styles,{assistant:'normal',user:'0px'});
  console.log('PASS：实际流式发送、追加消息和教材引用保留旧组件');
  rejectEvidence=true;
  await page.locator('#chat-input').fill('验证证据不足');await page.locator('#chat-form').evaluate(form=>form.requestSubmit());
  await page.waitForFunction(()=>!state.sending && state.chat.length===5);
  assert.equal(await page.evaluate(()=>state.chat.at(-1).failed),true);
  assert.match(await page.locator('.message.assistant').last().textContent(),/处理未完成/);
  console.log('PASS：证据拒绝的真实流式结果显示处理未完成');

  recoverStream=true;rejectEvidence=false;
  const beforeRecovery=generationRequests;
  await page.locator('#chat-input').fill('断线后恢复');await page.locator('#chat-form').evaluate(form=>form.requestSubmit());
  await page.waitForFunction(()=>!state.sending && state.chat.length===7);
  assert.equal(await page.evaluate(()=>state.chat.at(-1).content),'恢复后的回答 [1]');
  assert.equal(await page.evaluate(()=>state.chat.at(-1).failed),false);
  assert.equal(generationRequests,beforeRecovery+1);
  deletedRecovery=true;
  await page.locator('#chat-input').fill('已删除的回合');await page.locator('#chat-form').evaluate(form=>form.requestSubmit());
  await page.waitForFunction(()=>!state.sending && state.chat.length===9);
  assert.equal(await page.evaluate(()=>state.chat.at(-1).content),'相关记忆已删除');
  assert.equal(await page.evaluate(()=>state.chat.at(-1).failed),true);
  console.log('PASS：断线后真实页面重放带游标事件，生成请求仅一次；删除后的回合拒绝恢复');

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
  assert.equal(await page.evaluate(()=>typeof window.TutorMarkdown?.render),'function');
  const rich = [
   '##随机分配', '', '甲**关键变量**乙，==控制条件==，~~旧方案~~。', '',
   '1. 明确自变量', '2. 控制无关变量', '', '- [x] 已核验', '- [ ] 待复核', '',
   '| 变量 | 含义 |', '| --- | --- |', '| 处理 | 实验条件 |', '',
   '> 先考虑如何分组。', '', '```python', 'print("**保持代码**", "[2]", "$x$")', '```', '',
   '```', 'single_line()', '```', '',
   '行内公式 $x=[1,2]$ 和 \\(a^2+b^2\\)，教材依据 [1]。', '',
   '$$', '\\frac{a}{b} = c', '$$', '',
   '[安全链接](https://example.com/a?q=1) [危险链接](javascript:alert%281%29)', '',
   '[工作区链接](/api/files/remove) ![外部图片](https://example.com/tracker.png)', '',
   '<img src="https://example.com/html-image.png" onerror="window.__markdownXSS=1">',
   '<script>window.__markdownXSS=1</script>', '',
  ].join('\n');
  const mediaRequests=[];
  page.on('request',request=>{if(request.url().includes('example.com'))mediaRequests.push(request.url());});
  await page.evaluate(content=>{
   state.chat=[{renderKey:'markdown-a',role:'assistant',content,sources:['第一条证据']},
    {renderKey:'markdown-b',role:'assistant',content:'第二条回答 [1]，无对应来源 [99]。',sources:['第二条证据']}];
   renderChat();
  },rich);
  const markdown=page.locator('[data-message-key="markdown-a"] .tutor-markdown');
  assert.equal(await markdown.locator('h2').textContent(),'随机分配');
  assert.equal(await markdown.locator('strong').first().textContent(),'关键变量');
  assert.equal(await markdown.locator('mark').textContent(),'控制条件');
  assert.equal(await markdown.locator('del').textContent(),'旧方案');
  assert.equal(await markdown.locator('ol > li').count(),2);
  assert.equal(await markdown.locator('input[disabled]').count(),2);
  assert.equal(await markdown.locator('table td').count(),2);
  assert.equal((await markdown.locator('blockquote').textContent()).trim(),'先考虑如何分组。');
  assert.equal(await markdown.locator('pre code').count(),2);
  assert.match(await markdown.locator('pre').first().textContent(),/\*\*保持代码\*\*.*\[2\].*\$x\$/);
  assert.equal(await markdown.locator('pre strong, pre .katex, pre .citation-group').count(),0);
  assert.equal(await markdown.locator('.katex').count(),3);
  assert.equal(await markdown.locator('.katex-display').count(),1,await markdown.innerHTML());
  assert.equal(await markdown.locator('.citation-group').count(),1);
  assert.equal(await markdown.locator('img, script, iframe, svg').count(),0);
  assert.equal(await page.evaluate(()=>window.__markdownXSS),undefined);
  assert.equal(await markdown.getByText('危险链接',{exact:true}).getAttribute('href'),null);
  assert.equal(await markdown.getByText('工作区链接',{exact:true}).getAttribute('href'),null);
  assert.equal(await markdown.getByText('安全链接',{exact:true}).getAttribute('rel'),'noopener noreferrer');
  assert.equal(await markdown.getByText('安全链接',{exact:true}).getAttribute('target'),'_blank');
  assert.deepEqual(mediaRequests,[]);
  assert.equal(await page.evaluate(()=>state.chat[0].content),rich);
  await page.locator('[data-message-key="markdown-b"] .citation-group button').first().click();
  assert.equal(await page.locator('.citation-title').textContent(),'第二条证据');
  await page.locator('[data-message-key="markdown-b"] .citation-group button').last().click();
  assert.equal(await page.locator('.citation-popover [data-source-citation]').count(),0);
  await markdown.locator('.citation-group button').click();
  assert.equal(await page.locator('.citation-title').textContent(),'第一条证据');
  console.log('PASS：真实上游 Markdown、GFM、中文强调、代码、公式、安全边界及同消息引用');

  await page.evaluate(()=>{
   const first=chatRenderer.rows.get('markdown-a');window.keptMath=first.element.querySelector('.katex');
   state.chat[0].progress=[{order:1,label:'检索',status:'running'}];renderChat();
  });
  assert.equal(await page.evaluate(()=>keptMath.isConnected),true);
  await page.setViewportSize({width:390,height:844});
  await page.locator('[data-mobile-pane="chat"]').click();
  await page.evaluate(()=>{state.chat[0].content+='\n\n| 长表头 | 内容 |\n| --- | --- |\n| '+ '长单词'.repeat(100) +' | 内容 |\n\n```\n'+ 'long_token_'.repeat(100) +'\n```';renderChat();});
  const narrow=await markdown.evaluate(el=>({width:el.getBoundingClientRect().width,overflow:document.documentElement.scrollWidth>innerWidth+1}));
  assert.ok(narrow.width>0 && narrow.width<=390,JSON.stringify(narrow));
  assert.equal(narrow.overflow,false);
  const screenshot=process.env.CHAT_TEST_SCREENSHOT;
  if(screenshot)await page.screenshot({path:screenshot,fullPage:true});
  console.log('PASS：进度更新保留已排版公式，390px 长表格/代码不撑破页面');
  await page.evaluate(async()=>{await import('/static/pdf-reader/reader.js');});
  const compatibility=await page.evaluate(()=>{
   const host=document.createElement('section');host.className='exercise-help';document.body.append(host);
   try {
    const content=String.raw`提示：$x+1$，依据 [1]。`;
    host.innerHTML=window.renderTutorAnswer(content)+window.renderPracticeReferences({reply:content,textbook_sources:['练习证据']},'fixture')+'<p class="legacy-formula">旧公式 $a+b$</p>';
    const math=host.querySelector('.tutor-markdown');const before=math.innerHTML;const formula=math.querySelector('.katex');
    window.TextbookPDF.renderMath(host);
    window.TextbookPDF.renderMath(math.querySelector('p'));
    const original=window.ExercisePractice;
    window.ExercisePractice={citationMessage:()=>({content,sources:['练习证据'],pdfReferences:[]})};
    host.querySelector('.citation-group button').click();
    const practiceClicks=document.querySelector('.citation-title')?.textContent==='练习证据'?1:0;
    window.ExercisePractice=original;
    const unsafe=document.createElement('div');
    unsafe.innerHTML=window.renderTutorAnswer(String.raw`$\href{javascript:alert(1)}{危险}$ $\includegraphics{https://example.com/tex.png}$`);
    return {preserved:math.innerHTML===before && formula.isConnected,
      legacyMath:host.querySelectorAll('.legacy-formula .katex').length,practiceClicks,
      unsafeMedia:unsafe.querySelectorAll('img,iframe,script,a[href^="javascript:"]').length};
   }finally{host.remove();}
  });
  assert.deepEqual(compatibility,{preserved:true,legacyMath:1,practiceClicks:1,unsafeMedia:0});
  console.log('PASS：真实阅读器不重复排版富文本，原公式与练习反馈引用保持兼容');
  delayed=true;recoverStream=false;deletedRecovery=false;rejectEvidence=false;
  await page.reload();await page.waitForFunction(()=>!state.taskRecoveryNeeded && state.sectionData);
  await page.locator('[data-mobile-pane="chat"]').click();
  await page.locator('#chat-input').fill('验证真实HTTP流在结束前显示');
  await page.locator('#chat-form').evaluate(form=>form.requestSubmit());
  await page.waitForFunction(()=>state.sending && state.chat.at(-1)?.pending && state.chat.at(-1)?.content==='延迟关闭前可读。');
  assert.equal(await page.locator('.message.assistant').last().getByText('延迟关闭前可读。',{exact:true}).isVisible(),true);
  assert.equal(delayedClosed,false);assert.equal(delayedRequests,1);
  const beforeClose=Date.now();releaseFinal();
  await page.waitForFunction(()=>!state.sending && state.chat.at(-1)?.content==='延迟关闭前可读。完整收尾。');
  assert.equal(delayedRequests,1);
  if(process.env.UX_OUTPUT)fs.writeFileSync(path.join(process.env.UX_OUTPUT,'delayed-close.json'),JSON.stringify({fixture:true,model_called:false,http_stream:true,visible_before_close:true,first_visible:beforeClose,completed:Date.now(),generation_requests:delayedRequests},null,2));
  console.log('PASS：真实HTTP响应未结束时正文已可见，浏览器确认后才收尾，生成请求一次');
  assert.deepEqual(errors,[]);console.log('浏览器检查全部通过');
 }finally{if(releaseFinal&&!delayedClosed)releaseFinal();await browser?.close();await new Promise(resolve=>server.close(resolve));}
})().catch(error=>{console.error(error);process.exitCode=1;});
