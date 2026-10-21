/* 实际 SDK→SSE→现有页面；模型配置与隔离库由启动器提供。 */
const {chromium}=require('playwright');const fs=require('fs');const assert=require('node:assert/strict');
const URL=process.env.UX_TEST_URL||'http://127.0.0.1:8012';const out=process.env.UX_OUTPUT;
const cases=JSON.parse(process.env.UX_CASES||'[["concept","请解释教材里的自变量，不要出题。"],["comparison","比较被试内设计与被试间设计，使用对照表，不要出题。"],["formula","请解释韦伯定律的公式和各符号的含义，不要出题。"],["table","请用表格比较自变量、因变量与额外变量，不要出题。"],["planning","请详细制定第一章四节的学习计划，按节列出目标、活动、教材来源和完成标准，不要出题。"]]');
(async()=>{const browser=await chromium.launch({headless:false,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});const report={synthetic:true,rows:[]};
try{for(const [name,message,extra] of cases){const context=await browser.newContext();const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
await page.addInitScript(id=>localStorage.setItem('experimental-psychology-3-demo-student',id),'response-ux-'+name);
await page.goto(URL);await page.waitForFunction(()=>typeof state!=='undefined'&&!state.taskRecoveryNeeded&&state.chapters.length,null,{timeout:60000});
await page.evaluate(()=>{window.draftEvents=[];window.firstDraftPaint=null;
 window.streamBody=null;const originalFetch=window.fetch;window.fetch=async(...args)=>{const response=await originalFetch(...args);if(String(args[0]).endsWith('/api/chat/stream'))window.streamBody=response.clone().text();return response};
 const apply=TutorChatTransport.applyDraft;TutorChatTransport.applyDraft=(m,e,d)=>{const accepted=apply(m,e,d);draftEvents.push({at:Date.now(),event:e,...d,accepted});return accepted};
 new MutationObserver(()=>{if(!firstDraftPaint&&state.chat.some(m=>m.answerState==='generating'&&m.content&&document.querySelector(`[data-message-key="${m.renderKey}"] [data-message-part="content"]`)?.textContent.trim()))firstDraftPaint=Date.now()}).observe(document.querySelector('#chat-messages'),{childList:true,subtree:true,characterData:true});
});
if(extra)await page.evaluate(extra=>{if(extra.selection)state.pdfDraft=extra.selection;},extra);
await page.locator('#chat-input').fill(message);const start=Date.now();const response=page.waitForResponse(r=>r.url().endsWith('/api/chat/stream')&&r.request().method()==='POST',{timeout:240000});
await page.locator('#chat-form button[type=submit]').click();const res=await response;await page.waitForFunction(()=>!state.sending,null,{timeout:240000});const body=await page.evaluate(()=>streamBody);
const data=await page.evaluate(()=>({answer:state.chat.filter(m=>m.role==='assistant').at(-1),events:draftEvents,firstDraftPaint}));
fs.writeFileSync(out+'/'+name+'.sse',body);await page.screenshot({path:out+'/'+name+'.png',fullPage:true});
await page.reload();await page.waitForFunction(()=>!state.taskRecoveryNeeded,null,{timeout:60000});
const history=await page.evaluate(()=>state.chat.filter(m=>m.role==='assistant').at(-1)?.content);
const row={name,start,seconds:(data.answer.finishedAt-start)/1000,withReloadSeconds:(Date.now()-start)/1000,http:res.status(),...data,history,pageErrors:errors};report.rows.push(row);fs.writeFileSync(out+'/report.json',JSON.stringify(report,null,2));
assert.equal(errors.length,0);if(data.answer.answerState==='saved'){assert.equal(history,data.answer.content);assert.ok(data.events.some(e=>e.event==='answer_delta'&&e.accepted));assert.ok(data.firstDraftPaint);}
console.log(JSON.stringify({name,seconds:row.seconds,firstDraftPaint:data.firstDraftPaint,status:data.answer.answerState,replyLength:data.answer.content.length}));await context.close();
}}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1});
