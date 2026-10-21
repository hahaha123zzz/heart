/* 标注的AI生成题、真实现有练习入口；须由独立服务/数据库提供。 */
const {chromium}=require('playwright');const fs=require('node:fs');const assert=require('node:assert/strict');
const url=process.env.UX_TEST_URL||'http://127.0.0.1:8012',out=process.env.UX_OUTPUT;
(async()=>{
 const browser=await chromium.launch({headless:false,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 const report={input_origin:'ai_generated',test_only:true,cases:[]};let posts=0;
 try{
  const context=await browser.newContext({viewport:{width:390,height:844}});const page=await context.newPage();
  await page.addInitScript(()=>localStorage.setItem('experimental-psychology-3-demo-student','ai-practice-isolated'));
  page.on('request',r=>{if(r.method()==='POST'&&r.url().endsWith('/api/chat/stream'))posts++;});
  async function openPractice(){
   await page.waitForFunction(()=>!state.taskRecoveryNeeded&&state.sectionData,null,{timeout:60000});
   await page.locator('#course-view [data-start-practice="reading"]').click();
   await page.locator('#practice-question .source-label').waitFor();
  }
  await page.goto(url);await openPractice();
  assert.equal(await page.locator('#practice-question-list button').count(),3);
  assert.match(await page.locator('#practice-question .source-label').innerText(),/AI生成.*测试用.*未人工审核.*非教材原题/);
  assert.equal(await page.locator('[data-practice-submit]').isDisabled(),true);
  assert.equal(await page.locator('#practice-question').getByText(/题号按教材保留/).count(),0);
  await page.evaluate(()=>{
   window.aiBodies=[];window.aiFirst=null;const original=fetch;
   window.fetch=async(...args)=>{const response=await original(...args);if(String(args[0]).endsWith('/api/chat/stream'))aiBodies.push(response.clone().text());return response;};
   const apply=TutorChatTransport.applyDraft;TutorChatTransport.applyDraft=(...args)=>{const accepted=apply(...args);if(accepted&&args[1]==='answer_delta'&&!aiFirst)aiFirst=Date.now();return accepted;};
  });
  const draft='我认为关键是采用自然科学方法研究心理现象，还不能确定具体标志事件。';
  await page.locator('[data-answer-key="text"]').fill(draft);
  await page.locator('[data-practice-save]').click();
  await page.waitForFunction(()=>document.querySelector('#practice-save-status')?.textContent==='草稿已保存');
  const scope=await page.evaluate(()=>({student_id:studentId}));
  const index=await (await page.request.get(url+'/api/practice/chapters/1?student_id='+scope.student_id)).json();
  const blocked=await page.request.post(url+'/api/practice/questions/'+index.questions[0].id+'/submit',{data:{...scope,version:index.version,answers:{p1:{text:draft}},request_id:'ai-no-grade-123'}});
  assert.equal(blocked.status(),409);
  for(const action of ['hint','explain']){
   await page.evaluate(()=>window.aiFirst=null);const started=Date.now();
   const response=page.waitForResponse(r=>r.url().endsWith('/api/chat/stream')&&r.request().method()==='POST');
   await page.locator('[data-practice-'+action+'="p1"]').click();await response;
   const body=await page.evaluate(async()=>await aiBodies.at(-1));
   const done=body.split(/\r?\n\r?\n/).filter(frame=>frame.includes('event: done')).at(-1);
   assert.ok(done,'缺少最终收据');const result=JSON.parse(done.split(/\r?\n/).filter(l=>l.startsWith('data:')).map(l=>l.slice(5).trimStart()).join('\n'));
   const row={action,seconds:(Date.now()-started)/1000,first_delta_seconds:await page.evaluate(start=>aiFirst?(aiFirst-start)/1000:null,started),result};report.cases.push(row);
   fs.writeFileSync(out+'/'+action+'.sse',body);fs.writeFileSync(out+'/practice-live.json',JSON.stringify(report,null,2));
   assert.equal(result.answer_status,'answered');assert.match(result.reply,/AI生成.*测试用.*未人工审核/);
   assert.ok(result.pdf_references?.length);assert.equal(result.step_advanced,false);
   await page.waitForFunction(()=>document.querySelector('#help-p1 strong')?.textContent==='AI 讲解'||document.querySelector('#help-p1 strong')?.textContent.startsWith('提示 '));
  }
  await page.screenshot({path:out+'/practice.png',fullPage:true});
  await page.reload();await openPractice();
  assert.equal(await page.locator('[data-answer-key="text"]').inputValue(),draft);
  await page.waitForFunction(()=>document.querySelector('#help-p1')?.textContent.includes('已保存的AI 讲解'));
  assert.match(await page.locator('#practice-question .source-label').innerText(),/AI生成/);
  assert.equal(posts,2);report.refresh_restored=true;report.generation_posts=posts;report.submission_blocked=blocked.status();
  const history=await (await page.request.get(url+'/api/practice/questions/'+index.questions[0].id+'?student_id='+scope.student_id)).json();
  assert.equal(history.history.length,0);assert.equal(history.help_history.length,2);report.formal_submissions=0;
  await page.screenshot({path:out+'/practice-refresh.png',fullPage:true});
  fs.writeFileSync(out+'/practice-live.json',JSON.stringify(report,null,2));console.log('PASS：AI来源标注、真实提示/讲解、有效引用、禁正式评分、草稿/辅导刷新恢复，生成请求2次');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
