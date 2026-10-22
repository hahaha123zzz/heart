const {chromium}=require('playwright'),fs=require('node:fs'),assert=require('node:assert/strict');
const url=process.env.UX_TEST_URL||'http://127.0.0.1:8012',out=process.env.UX_OUTPUT;
// 需要/_edges隔离故障夹具，不得运行于正式服务。
assert(['127.0.0.1','localhost'].includes(new URL(url).hostname)&&out);
(async()=>{
 const browser=await chromium.launch({headless:false,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'}),report=[];
 try{for(const mode of (process.env.EDGE_CASES||'partial,cancel,timeout,late').split(',')){
  const context=await browser.newContext(),page=await context.newPage();let posts=0;const row={mode,start:Date.now()};report.push(row);
  page.on('request',r=>{if(r.method()==='POST'&&r.url().endsWith('/api/chat/stream'))posts++;});
  await page.addInitScript(id=>localStorage.setItem('experimental-psychology-3-demo-student',id),'edge-'+mode);
  try{
   await page.goto(url);await page.waitForFunction(()=>typeof state!=='undefined'&&!state.taskRecoveryNeeded&&state.chapters.length,null,{timeout:60000});
   const scope=await page.evaluate(()=>({student_id:studentId,session_id:tabSessionId}));
   assert((await page.request.post(url+'/_edges/seed',{data:scope})).ok());
   row.before=await(await page.request.get(url+'/_joint/q5-state?'+new URLSearchParams(scope))).json();
   await page.request.post(url+'/_edges/control',{data:{mode}});
   await page.evaluate(()=>{
    window.edgeIdentity=null;window.edgeFirst=null;window.edgeBody=null;window.edgeRequest=null;
    const apply=TutorChatTransport.applyDraft;TutorChatTransport.applyDraft=(m,e,d)=>{if(d.task_id)edgeIdentity={task_id:d.task_id,task_revision:d.task_revision};if(e==='answer_delta'&&d.text&&!edgeFirst)edgeFirst=Date.now();return apply(m,e,d);};
    const original=fetch;window.fetch=async(...args)=>{if(String(args[0]).endsWith('/api/chat/stream')){edgeRequest=JSON.parse(args[1].body).request_id;const response=await original(...args);edgeBody=response.clone().text();return response;}return original(...args);};
   });
   const text=mode==='partial'?'第一章的实验程序和第二章的火星玄武岩晶体结构有哪些联系？':mode==='cancel'?'第一章的实验程序的事先准备工作和第二章的自变量控制的操作要求有哪些联系？':mode==='timeout'?'第一章的实验程序的实施过程和第二章的自变量控制的执行要求有哪些联系？':'第一章的实验程序和第二章的自变量控制有哪些联系？';
   await page.locator('#chat-input').fill(text);await page.locator('#chat-form button[type=submit]').click();
   if(mode==='cancel'||mode==='late'){
    const deadline=Date.now()+120000;let ready=false;
    while(Date.now()<deadline){
     const status=await(await page.request.get(url+'/_edges/status')).json();
     const starts=status.events.filter(e=>e.event==='sdk_start').length,ends=status.events.filter(e=>e.event==='sdk_end').length;
     if((mode==='cancel'?starts>ends:status.events.some(e=>e.event==='late_hold'))&&await page.evaluate(()=>Boolean(edgeIdentity))){row.cancelObserved=status;ready=true;break;}
     await page.waitForTimeout(40);
    }
    assert(ready,'必须观察到正在进行的真实native SDK或实际返回后延迟结果');
    const identity=await page.evaluate(()=>edgeIdentity);row.cancelAt=Date.now();
    row.cancel=await(await page.request.delete(url+'/api/chat/tasks/'+identity.task_id,{data:{...scope,task_revision:identity.task_revision}})).json();
    assert.equal(row.cancel.answer_status,'task_cancelled');
    if(mode==='late')await page.request.post(url+'/_edges/control',{data:{release:true}});
   }
   await page.waitForFunction(()=>!state.sending,null,{timeout:300000});
   Object.assign(row,await page.evaluate(async()=>({message:state.chat.filter(m=>m.role==='assistant').at(-1),body:await edgeBody,firstDraft:edgeFirst,requestId:edgeRequest})));
   row.seconds=(Date.now()-row.start)/1000;row.posts=posts;assert.equal(posts,1);
   fs.writeFileSync(out+'/'+mode+'.sse',row.body||'');
   await page.waitForTimeout(1500);
   row.native=await(await page.request.get(url+'/_edges/status')).json();
   row.after=await(await page.request.get(url+'/_joint/q5-state?'+new URLSearchParams(scope))).json();
   row.history=await(await page.request.get(url+'/api/students/'+scope.student_id+'/conversation')).json();
   assert.deepEqual(row.before,row.after,'插问/取消/故障不得修改Q5状态');
   if(mode==='partial'){
    const result=JSON.parse(row.body.split('event: done\ndata: ').at(-1).trim());
    assert.equal(result.retrieval_coverage?.status,'partial');assert.equal(result.retrieval_coverage.supplemental_calls,1);
    assert.equal(result.retrieval_coverage.retrieval_calls,3);assert(result.backend_calls.every(c=>c.actual_backend==='lightrag'&&['success','no_evidence'].includes(c.status)&&!c.fallback));
    assert(result.reply.includes('玄武岩')&&/缺|未|没有|不能/.test(result.reply));
    assert.equal(result.answer_status,'answered');assert(result.pdf_references.length>0);
    assert(result.pdf_references.every(r=>r.selection_ref.chapter_id===1));
    assert(await page.locator('[data-tutor-citation]').count()>0,'已覆盖部分须有有效上标');
   }else{
    assert.equal(row.history.filter(m=>m.role==='assistant').length,0,'失败或取消结果不得保存');
    assert(row.native.events.some(e=>e.event==='finalize_end'),'必须确认native实际清理结束');
    if(mode==='late')assert(row.native.events.some(e=>e.event==='late_return'&&e.source_count>0),'必须实际交回晚到原文');
    else assert(row.native.events.some(e=>e.event==='query_end'&&e.status===(mode==='timeout'?'TimeoutError':'CancelledError')));
    assert.equal(row.native.events.filter(e=>e.event==='sdk_start').length,row.native.events.filter(e=>e.event==='sdk_end').length,'实际SDK调用必须退出');
   }
   await page.reload();await page.waitForFunction(()=>!state.taskRecoveryNeeded,null,{timeout:60000});
   row.restored=await page.evaluate(()=>state.chat.filter(m=>m.role==='assistant').at(-1)?.content);
   if(mode!=='partial')assert.equal(row.restored,undefined);
   else assert.equal(row.restored,row.message.content,'partial正文刷新恢复一致');
   await page.screenshot({path:out+'/'+mode+'.png',fullPage:true});row.passed=true;
   console.log(JSON.stringify({mode,seconds:row.seconds,status:row.message?.answerState,passed:true}));
  }catch(error){row.error=error.message;row.passed=false;console.error(mode,error.message);process.exitCode=1;}
  finally{fs.writeFileSync(out+'/edges.json',JSON.stringify(report,null,2));await context.close();}
 }}finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
