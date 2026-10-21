/* 当前隔离宿主真实页面；模型/数据库配置由隔离启动器提供。 */
const {chromium}=require('playwright');const fs=require('node:fs');const path=require('node:path');const assert=require('node:assert/strict');
const url=process.env.UX_TEST_URL||'http://127.0.0.1:8012',out=process.env.UX_OUTPUT;
(async()=>{
 const browser=await chromium.launch({headless:false,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 const report={isolated:true,cases:[]};
 async function run(name,steps){
  const context=await browser.newContext();const page=await context.newPage();let posts=0;
  page.on('request',r=>{if(r.method()==='POST'&&r.url().endsWith('/api/chat/stream'))posts++;});
  await page.addInitScript(id=>localStorage.setItem('experimental-psychology-3-demo-student',id),'joint-'+name);
  if(process.env.UX_REUSE_SESSION)await page.addInitScript(id=>sessionStorage.setItem('experimental-psychology-3-task-session',id),process.env.UX_REUSE_SESSION);
  try{
   await page.goto(url);await page.waitForFunction(()=>typeof state!=='undefined'&&!state.taskRecoveryNeeded&&state.chapters.length,null,{timeout:60000});
   if(name==='media'){
    const scope=await page.evaluate(()=>({student_id:studentId,session_id:tabSessionId}));
    const seeded=await page.request.post(url+'/_joint/seed-media',{data:scope});assert.ok(seeded.ok());
   }
   await page.evaluate(()=>{
    window.jointBodies=[];window.jointDeltas=[];window.jointFirstPaint=null;const fetch0=fetch;
    window.fetch=async(...args)=>{const response=await fetch0(...args);if(String(args[0]).endsWith('/api/chat/stream'))jointBodies.push(response.clone().text());return response;};
    const apply=TutorChatTransport.applyDraft;TutorChatTransport.applyDraft=(m,e,d)=>{const ok=apply(m,e,d);if(e==='answer_delta'&&ok)jointDeltas.push({at:Date.now(),...d});return ok;};
    new MutationObserver(()=>{if(!jointFirstPaint&&state.chat.some(m=>m.pending&&m.answerState==='generating'&&m.content&&document.querySelector(`[data-message-key="${m.renderKey}"] [data-message-part="content"]`)?.textContent.trim()))jointFirstPaint=Date.now();}).observe(document.querySelector('#chat-messages'),{subtree:true,childList:true,characterData:true});
   });
   for(const step of steps){
    if(step.selection)await page.evaluate(selection=>state.pdfDraft=selection,step.selection);
    await page.evaluate(()=>window.jointFirstPaint=null);
    const start=Date.now();await page.locator('#chat-input').fill(step.text);await page.locator('#chat-form button[type=submit]').click();
    await page.waitForFunction(()=>!state.sending,null,{timeout:600000});
    const data=await page.evaluate(async()=>({message:state.chat.filter(m=>m.role==='assistant').at(-1),body:await jointBodies.at(-1),deltas:jointDeltas,firstDraftPaint:jointFirstPaint,studentId,session:tabSessionId}));
    const row={name:step.name,start,seconds:(Date.now()-start)/1000,...data,posts};report.cases.push(row);
    fs.writeFileSync(out+'/'+step.name+'.sse',data.body||'');
    const stateResponse=await page.request.get(url+'/_joint/q5-state?student_id='+encodeURIComponent(data.studentId)+'&session_id='+encodeURIComponent(data.session));row.q5=await stateResponse.json();
    fs.writeFileSync(out+'/flow.json',JSON.stringify(report,null,2));console.log(JSON.stringify({name:step.name,seconds:row.seconds,status:data.message?.answerState,reply:data.message?.content?.slice(0,100)}));
   }
   const before=await page.evaluate(()=>state.chat.filter(m=>m.role==='assistant').at(-1)?.content);
   await page.screenshot({path:out+'/'+name+'.png',fullPage:true});await page.reload();await page.waitForFunction(()=>!state.taskRecoveryNeeded,null,{timeout:60000});
   const after=await page.evaluate(()=>state.chat.filter(m=>m.role==='assistant').at(-1)?.content);
   report.cases.at(-1).reloadEqual=before===after;assert.equal(before,after);
  }catch(error){report.cases.push({name,error:error.message,posts});console.error(name,error.message);process.exitCode=1;}
  finally{fs.writeFileSync(out+'/flow.json',JSON.stringify(report,null,2));await context.close();}
 }
 try{
  const which=process.env.UX_FLOW||'q5';
  if(which==='q5'||which==='q5-ask')await run('q5',[
   {name:'q5-plan',text:'制定第一章的学习计划'},
   {name:'q5-confirm',text:'确认计划，开始学习'},
   {name:'q5-cross',text:'第一章的实验程序和第二章的自变量控制有哪些联系？'},
   {name:'q5-return',text:'返回原目标，继续讲解原来的知识点'},
   {name:'q5-next',text:'我懂了，下一部分'},
   ...(which==='q5-ask'?[{name:'bound-ask-pause',text:'请先用问题卡确认当前目标要简短解释还是详细解释，等我选择后继续。'},
    {name:'bound-ask-resume',text:'简短解释，请继续原任务。'}]:[])]);
  if(which==='media')await run('media',[{name:'media-tool',text:'请解释图5-2中的实验设计，并在正文展示原图，不要出题。'}]);
  if(which==='pdf'){
   const selection=JSON.parse(fs.readFileSync(path.resolve(out,'../lr-selection.json'),'utf8'));
   await run('pdf',[{name:'pdf-explain',text:'解释这段教材，不要出题。',selection},
    {name:'pdf-followup',text:'没听懂，请换一种简单说法。'}]);
  }
  if(which==='ask')await run('ask',[{name:'ask-pause',text:'学习第一章。请先用问题卡确认我想要简短解释还是详细解释，等我回答后继续。'},
   {name:'ask-resume',text:'简短解释，请继续。'}]);
  if(which==='ask-bound')await run('q5',[
   {name:'bound-topic-pause',text:'请先用问题卡确认我现在想听“我思故我在”还是“心身二元论”，等我选后再继续讲解。'},
   {name:'bound-topic-resume',text:'先解释我思故我在，简短一点。'}]);
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
