// 真实教材/API/模型验收；必须显式指定隔离服务地址。
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const home=process.env.Q4_BROWSER_OUTPUT;assert.ok(home&&process.env.Q4_URL,'须明确指定隔离服务Q4_URL和报告目录Q4_BROWSER_OUTPUT');fs.mkdirSync(home,{recursive:true});const report={api:'real',textbook:'experimental-psychology-3',isolated_database:true,cases:[]};
(async()=>{
 const browser=await chromium.launch({headless:false,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 const context=await browser.newContext({viewport:{width:1500,height:950}}),page=await context.newPage();
 let errors=[],acks=[];
 page.on('pageerror',e=>errors.push(e.message));
 page.on('response',async r=>{if(r.url().endsWith('/reader-receipt'))acks.push({http:r.status(),body:await r.json()});});
 await page.addInitScript(()=>{const key='experimental-psychology-3-demo-student';if(!localStorage.getItem(key))localStorage.setItem(key,'q4-formal-'+Date.now());});
 try{
  await page.goto(process.env.Q4_URL);
  await page.waitForFunction(()=>typeof state!=='undefined'&&!state.taskRecoveryNeeded&&state.chapters.length,null,{timeout:60000});
  const cases=process.env.Q4_CASES_FILE?JSON.parse(fs.readFileSync(process.env.Q4_CASES_FILE,'utf8')):process.env.Q4_CASES?JSON.parse(process.env.Q4_CASES):[['outline','请列出第一章的目录。'],['catalog','当前教材有哪些文档？'],['memory','我的讲解偏好是什么？'],['reader','请打开第一章阅读版第2页。'],['concept','请结合教材解释自变量与因变量的区别，给出一个简单例子，并引用教材。不要出题。']];
  for(const [name,message] of cases){
   const row={name,message,started:Date.now()};let posts=0;const count=r=>{if(r.method()==='POST'&&r.url().endsWith('/api/chat/stream'))posts++};page.on('request',count);
   try{
    await page.locator('#chat-input').fill(message);await page.locator('#chat-form button[type=submit]').click();
    await page.waitForFunction(()=>!state.sending,null,{timeout:240000});
    Object.assign(row,await page.evaluate(()=>({answer:state.chat.filter(m=>m.role==='assistant').at(-1),position:state.pdfPosition})));
    if(name==='reader')await page.waitForTimeout(14000);
    row.acknowledgements=acks.slice();row.posts=posts;row.seconds=(Date.now()-row.started)/1000;
    await page.screenshot({path:path.join(home,name+'.png'),fullPage:true});
    assert.equal(row.answer.answerState,'saved',JSON.stringify({status:row.answer.answerState,content:row.answer.content}));
    assert.equal(posts,1);
    if(name==='reader')assert.ok(acks.some(a=>a.http===200&&a.body.status==='applied'),JSON.stringify(acks));
    if(name==='reader'&&process.env.Q4_REQUIRE_HIGHLIGHT){
     assert.ok(acks.at(-1).body.rects.length,'真实原文应有精确高亮坐标');
     row.visibleHighlights=await page.locator('.pdf-reader-host .Highlight__part').count();
     assert.ok(row.visibleHighlights>0,'PDF.js必须实际绘制高亮');
     const count=acks.length;await page.reload();await page.waitForFunction(()=>!state.taskRecoveryNeeded);
     assert.equal(await page.evaluate(()=>state.chat.filter(m=>m.role==='assistant').at(-1)?.content),row.answer.content,'同账户刷新应恢复同一条回答');
     await page.waitForTimeout(1500);assert.equal(acks.length,count,'恢复历史不得重新执行动作');row.reload_no_replay=true;
    }
    if(name==='memory'){assert.ok(row.answer.content.includes('偏好'));assert.equal(row.answer.pdfReferences?.length||0,0);}
    if(name==='concept')assert.ok(row.answer.pdfReferences?.length,'讲解必须有真实教材引用');
   }catch(e){row.error=e.message;}
   page.off('request',count);report.cases.push(row);fs.writeFileSync(path.join(home,'report.json'),JSON.stringify({...report,errors},null,2));
   console.log(JSON.stringify({name,status:row.answer?.answerState,seconds:row.seconds,error:row.error}));
  }
 }finally{await browser.close();}
 assert.ok(report.cases.length>0&&report.cases.every(r=>!r.error), '正式教材验收有失败，请查看 report.json');assert.equal(errors.length,0);
})().catch(e=>{console.error(e.message);process.exitCode=1});
