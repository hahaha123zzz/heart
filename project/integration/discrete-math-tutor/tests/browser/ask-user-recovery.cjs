const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const ROOT=process.env.RECOVERY_ROOT||'E:/项目/heart/project/integration/discrete-math-tutor';
const BASE_URL=process.env.RECOVERY_URL||'http://127.0.0.1:8043';
(async()=>{
 const browser=await chromium.launch({headless:false,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 try{
 const context=await browser.newContext();let pending=null,requests=[],fail=true;const errors=[];
 const card={answer_status:'awaiting_clarification',reply:'请回答两个问题',task_id:'multi-browser',task_revision:1,clarification:{mode:'ask_user',options:[],questions:[
 {id:'goal',prompt:'你想学习什么？',allow_free_text:false,options:[{label:'概念'},{label:'计算'}]},
 {id:'style',prompt:'希望怎样解释？',multi_select:true,allow_free_text:true,options:[{label:'例子'},{label:'对比'}]}]}};
 await context.route('**/api/**',async route=>{
  const req=route.request(),url=new URL(req.url());let data={};
  if(url.pathname==='/api/course/chapters')data=[{id:1,title:'第一章',sections:[{id:1,title:'实验心理学'}]}];
  else if(url.pathname.includes('/sections/'))data={title:'实验心理学',content:'教材测试正文',blocks:[]};
  else if(url.pathname.endsWith('/conversation'))data=[];
  else if(url.pathname.endsWith('/dashboard'))data={activity:[],chapter_scores:[],chapters:[]};
  else if(url.pathname==='/api/chat/tasks/pending')data={pending};
  else if(url.pathname==='/api/chat/stream'){
   const body=req.postDataJSON();requests.push(body);
   if(body.answers&&fail){await route.fulfill({status:503,json:{detail:'受控响应丢失'}});return;}
   data=body.answers?{answer_status:'answered',reply:'按你的两个回答继续讲解',task_id:card.task_id,task_revision:2}:card;
   pending=body.answers?null:card;
   await route.fulfill({contentType:'text/event-stream',body:'event: done\ndata: '+JSON.stringify(data)+'\n\n'});return;
  }
  await route.fulfill({json:data});
 });
 const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
 const ready=()=>page.waitForFunction(()=>!state.taskRecoveryNeeded&&state.sectionData!==null);
 await page.goto(BASE_URL);await ready();await page.evaluate(()=>showView('chat'));
 await page.locator('#chat-input').fill('请用问题卡确认两个信息');await page.locator('#chat-form').evaluate(f=>f.requestSubmit());
 await page.waitForFunction(()=>!state.sending&&state.clarification);
 assert.equal(await page.locator('.task-clarification fieldset').count(),2);
 await page.locator('[data-ask-question="0"][data-ask-option="1"]').check();
 await page.locator('[data-ask-question="1"][data-ask-option="0"]').check();
 await page.locator('[data-ask-question="1"][data-ask-option="1"]').check();
 await page.locator('[data-ask-text]').fill('先简单讲');
 await page.reload();await ready();await page.evaluate(()=>showView('chat'));
 assert.equal(await page.locator('.task-clarification input:checked').count(),3);
 assert.equal(await page.locator('[data-ask-text]').inputValue(),'先简单讲');
 await page.locator('[data-ask-submit]').focus();await page.keyboard.press('Enter');
 await page.waitForFunction(()=>!state.sending&&state.chat.at(-1).networkFailed);
 assert.equal(await page.locator('.task-clarification input:checked').count(),3);
 const first=requests.at(-1);assert.deepEqual(first.answers,[{questionId:'goal',text:'计算'},{questionId:'style',text:'例子；对比；先简单讲'}]);
 fail=false;await page.locator('[data-retry-message]').last().click();
 await page.waitForFunction(()=>!state.sending&&!state.clarification);
 assert.equal(requests.at(-1).request_id,first.request_id);
 assert.equal(await page.locator('[data-ask-submit]').count(),0);
 assert.deepEqual(errors,[]);
 const report={passed:true,layer:'browser_api_fixture',cases:['two questions','single/multiple/free text','refresh preserves picks','keyboard submit','503 preserves picks','same request retry','resolved hides card'],page_errors:errors};
 fs.writeFileSync(ROOT+'/.runtime/ta5/recovery-browser.json',JSON.stringify(report,null,2));
 console.log(JSON.stringify(report));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
