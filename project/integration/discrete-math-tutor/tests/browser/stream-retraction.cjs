/* 现有页面的隔离流式验收；SR_URL/SR_OUTPUT 必填，故障必须由独立宿主注入。 */
const {chromium}=require('playwright');const fs=require('node:fs');const path=require('node:path');
const url=process.env.SR_URL,out=process.env.SR_OUTPUT;fs.mkdirSync(out,{recursive:true});
const cases=JSON.parse(process.env.SR_CASES||'[["concept","请解释教材里的自变量，不要出题。"],["figure14","给我解释一下图1-4，我有点看不懂"]]');
(async()=>{const browser=await chromium.launch({headless:false,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});const report={url,realModel:!process.env.SR_SCENARIO,faultInjection:!!process.env.SR_SCENARIO,attempts:[]};
let sharedContext,sharedPage;try{for(const [name,message,extra] of cases){const context=process.env.SR_REUSE_SESSION?(sharedContext??=await browser.newContext({extraHTTPHeaders:process.env.SR_SCENARIO?{'x-sr-scenario':process.env.SR_SCENARIO}:{}})):await browser.newContext({extraHTTPHeaders:process.env.SR_SCENARIO?{'x-sr-scenario':process.env.SR_SCENARIO}:{}});const page=process.env.SR_REUSE_SESSION?(sharedPage??=await context.newPage()):await context.newPage();let row={name,message,started:Date.now(),posts:0,errors:[]};
 const onError=e=>row.errors.push(e.message),onRequest=r=>{if(r.method()==='POST'&&r.url().endsWith('/api/chat/stream')){row.posts++;row.scenarioHeader=r.headers()['x-sr-scenario']||''}};page.on('pageerror',onError);page.on('request',onRequest);
 try{if(!page.url()||page.url()==='about:blank')await page.addInitScript(id=>localStorage.setItem('experimental-psychology-3-demo-student',id),('sr-'+path.basename(out)+'-'+name+'-'+Date.now()).slice(-60));
 await page.goto(url);await page.waitForFunction(()=>typeof state!=='undefined'&&!state.taskRecoveryNeeded&&state.chapters.length,null,{timeout:60000});
 await page.evaluate(()=>{window.srEvents=[];window.srBody=null;const fetch0=fetch;window.fetch=async(...args)=>{const response=await fetch0(...args);if(String(args[0]).endsWith('/api/chat/stream'))window.srBody=(async()=>{const reader=response.clone().body.getReader(),decoder=new TextDecoder();let all='',buffer='';while(true){const {done,value}=await reader.read();const text=decoder.decode(value,{stream:!done});all+=text;buffer+=text.replace(/\r/g,'');let index;while((index=buffer.indexOf('\n\n'))>=0){const frame=buffer.slice(0,index);buffer=buffer.slice(index+2);const lines=frame.split('\n');if(lines.some(x=>x==='event: progress')){try{srEvents.push({at:Date.now(),event:'progress',payload:JSON.parse(lines.filter(x=>x.startsWith('data:')).map(x=>x.slice(5).trimStart()).join('\n'))})}catch{}}}if(done)return all}})();return response};
 const apply=TutorChatTransport.applyDraft;TutorChatTransport.applyDraft=(m,e,d)=>{const accepted=apply(m,e,d);srEvents.push({at:Date.now(),event:e,...d,accepted,visibleText:m.content});return accepted};
 const stream=TutorChatTransport.streamChat;TutorChatTransport.streamChat=(data,progress,answer,draft)=>stream(data,p=>{srEvents.push({at:Date.now(),event:'progress',payload:p});progress?.(p)},answer,draft);
 });
 if(extra?.selection)await page.evaluate(selection=>state.pdfDraft=selection,extra.selection);
 if(process.env.SR_SCENARIO){const probe=await (await page.request.get(url+'/_sr/probes')).json();if(probe.test_hooks!==true||probe.scenario!==process.env.SR_SCENARIO)throw new Error('故障宿主/请求标记未生效，拒绝消耗真实模型调用');}
 await page.locator('#chat-input').fill(message);row.submitted=Date.now();await page.locator('#chat-form button[type=submit]').click();
 if(extra?.cancel){await page.waitForFunction(()=>srEvents.some(e=>e.event==='progress'&&e.payload.stage?.includes('tool_call')),null,{timeout:30000});const identity=await page.evaluate(()=>({id:state.chat.filter(m=>m.role==='assistant').at(-1).answerIdentity,studentId,session:tabSessionId}));const response=await page.request.delete(url+'/api/chat/tasks/'+identity.id.task_id,{data:{student_id:identity.studentId,session_id:identity.session,task_revision:identity.id.task_revision}});row.cancel=await response.json();}
 await page.waitForFunction(()=>!state.sending,null,{timeout:240000});
 Object.assign(row,await page.evaluate(async()=>({answer:state.chat.filter(m=>m.role==='assistant').at(-1),events:srEvents,body:await srBody,studentId,session:tabSessionId})));
 if(process.env.SR_SCENARIO){const probes=await (await page.request.get(url+'/_sr/probes')).json();row.probes=probes.probes.filter(p=>p.task_id===row.answer?.answerIdentity?.task_id);}
 row.draftDetails=await page.locator('.unpublished-draft').count();row.draftLinks=await page.locator('.unpublished-draft a').count();const payload=row.answer?.request?.payload;if(payload?.request_id){const response=await page.request.get(url+'/api/chat/requests/'+encodeURIComponent(payload.request_id)+'?student_id='+encodeURIComponent(payload.student_id)+'&session_id='+encodeURIComponent(payload.session_id));row.receiptStatus=response.status();row.receipt=await response.json();}row.finished=Date.now();row.seconds=(row.finished-row.submitted)/1000;
 fs.writeFileSync(path.join(out,name+'.sse'),row.body||'');delete row.body;
 await page.screenshot({path:path.join(out,name+'.png'),fullPage:true});
 const before=row.answer?.content;await page.reload();await page.waitForFunction(()=>!state.taskRecoveryNeeded,null,{timeout:60000});row.history=await page.evaluate(()=>state.chat.filter(m=>m.role==='assistant').at(-1)?.content);row.historyEqual=before===row.history;
 }catch(e){row.error=e.message;await page.screenshot({path:path.join(out,name+'-error.png'),fullPage:true}).catch(()=>{});}
 report.attempts.push(row);fs.writeFileSync(path.join(out,'report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify({name,status:row.answer?.answerState,seconds:row.seconds,posts:row.posts,error:row.error}));page.off('pageerror',onError);page.off('request',onRequest);if(!process.env.SR_REUSE_SESSION)await context.close();
} const assert=require('node:assert/strict');
 for(const row of report.attempts){
   assert.equal(row.error,undefined, row.name+': '+row.error);
   assert.equal(row.errors.length,0,row.name);
   assert.equal(row.posts,1,row.name+': 不得重复 POST');
   if(!process.env.SR_SCENARIO&&['concept','figure14','figure52'].includes(row.name)){
     assert.equal(row.answer.answerState,'saved',row.name);
     assert.equal(row.historyEqual,true,row.name);
     const deltas=row.events.filter(e=>e.event==='answer_delta'&&e.role==='answer'), checking=row.events.find(e=>e.event==='answer_state'&&e.state==='checking'&&e.role==='answer'&&e.round_id===deltas[0]?.round_id);
     assert.ok(deltas.length&&checking&&deltas[0].at<checking.at,row.name+': 正文必须在核验前真实流出');
     assert.equal(row.events.filter(e=>e.event==='answer_replace'&&!e.text).length,0,row.name+': 普通取证不清正文');
   }
   if(row.name==='figure52')assert.ok(row.answer.imageRefs.some(ref=>ref.id==='image-05-0004'&&ref.model_saw_pixels));
   if(row.name==='figure14')assert.ok(row.answer.imageRefs.some(ref=>ref.id==='image-01-0006'&&ref.model_saw_pixels));
   if(process.env.SR_SCENARIO==='partial'){
     assert.equal(row.answer.answerState,'interrupted');assert.equal(row.draftDetails,1);assert.equal(row.draftLinks,0);
     assert.equal(row.history,undefined);
   }
 }
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
