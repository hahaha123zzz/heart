/* 真实公共SDK流的取消/断线；使用官方端点与Q2精确范围，不冒充网关检索验收。 */
const {chromium}=require('playwright');const fs=require('node:fs');const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:false,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 const report=[];const out=process.env.UX_OUTPUT;const url=process.env.UX_TEST_URL||'http://127.0.0.1:8012';
 try{for(const mode of ['cancel','disconnect']){
  const context=await browser.newContext();const page=await context.newPage();let posts=0;
  page.on('request',r=>{if(r.method()==='POST'&&r.url().endsWith('/api/chat/stream'))posts++;});
  await page.addInitScript(id=>localStorage.setItem('experimental-psychology-3-demo-student',id),'joint-'+mode);
  try{
   await page.goto(url);await page.waitForFunction(()=>typeof state!=='undefined'&&!state.taskRecoveryNeeded&&state.chapters.length,null,{timeout:60000});
   await page.evaluate(mode=>{
    window.faultHit=false;window.cancelResult=null;window.jointRequestId=null;const originalFetch=fetch;
    window.fetch=async(...args)=>{
     if(String(args[0]).endsWith('/api/chat/stream'))jointRequestId=JSON.parse(args[1].body).request_id;
     const response=await originalFetch(...args);
     if(mode!=='disconnect'||faultHit||!String(args[0]).endsWith('/api/chat/stream'))return response;
     const reader=response.body.getReader(),decoder=new TextDecoder();let text='';
     return new Response(new ReadableStream({async pull(controller){
      const next=await reader.read();if(next.done){controller.close();return;}
      text+=decoder.decode(next.value,{stream:true});
      if(!faultHit&&text.includes('event: answer_delta')){faultHit=true;await reader.cancel();controller.error(new TypeError('隔离验收：主动关闭真实SSE连接'));return;}
      controller.enqueue(next.value);
     }}),{status:response.status,headers:response.headers});
    };
    const apply=TutorChatTransport.applyDraft;
    TutorChatTransport.applyDraft=(m,event,data)=>{
     const accepted=apply(m,event,data);
     if(mode==='cancel'&&!faultHit&&accepted&&event==='answer_delta'){
      faultHit=true;window.cancelResult=originalFetch('/api/chat/tasks/'+encodeURIComponent(data.task_id),
       {method:'DELETE',headers:{'Content-Type':'application/json'},body:JSON.stringify({student_id:studentId,session_id:tabSessionId,task_revision:data.task_revision})}).then(r=>r.json());
     }return accepted;
    };
   },mode);
   const start=Date.now();await page.locator('#chat-input').fill('学习第一章');await page.locator('#chat-form button[type=submit]').click();
   await page.waitForFunction(()=>!state.sending,null,{timeout:300000});
   const data=await page.evaluate(async()=>({faultHit,cancel:await cancelResult,message:state.chat.filter(m=>m.role==='assistant').at(-1),studentId,session:tabSessionId,requestId:jointRequestId}));
   let receipt=null;
   if(mode==='disconnect')for(let i=0;i<60;i++){
    const res=await page.request.get(url+'/api/chat/requests/'+encodeURIComponent(data.requestId)+'?student_id='+encodeURIComponent(data.studentId)+'&session_id='+encodeURIComponent(data.session));
    if(res.ok()){receipt=await res.json();if(receipt.result)break;}
    await page.waitForTimeout(1000);
   }
   const history=await (await page.request.get(url+'/api/students/'+data.studentId+'/conversation')).json();
   const row={mode,start,seconds:(Date.now()-start)/1000,posts,...data,receipt,history};report.push(row);
   fs.writeFileSync(out+'/public-recovery.json',JSON.stringify(report,null,2));
   assert.ok(data.faultHit,'必须实际收到增量后才注入故障');assert.equal(posts,1,'不得重新生成');
   if(mode==='cancel'){
    assert.equal(data.cancel.answer_status,'task_cancelled');
    assert.equal(history.filter(m=>m.role==='assistant').length,0,'取消草稿不得保存');
   }else assert.equal(receipt?.result?.answer_status,'answered','断线后只读等待原收据完成，不重开生成');
   await page.reload();await page.waitForFunction(()=>!state.taskRecoveryNeeded,null,{timeout:60000});
   row.restored=await page.evaluate(()=>state.chat.filter(m=>m.role==='assistant').at(-1)?.content);
   if(mode==='cancel')assert.equal(row.restored,undefined,'刷新不得复活取消草稿');
   if(mode==='disconnect')assert.equal(row.restored,receipt.result.reply);
   await page.screenshot({path:out+'/'+mode+'.png',fullPage:true});console.log('PASS',mode,row.seconds,posts,data.message.answerState);
  }catch(error){report.push({mode,error:error.message,posts});console.error(mode,error.message);process.exitCode=1;}
  finally{fs.writeFileSync(out+'/public-recovery.json',JSON.stringify(report,null,2));await context.close();}
 }}finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
