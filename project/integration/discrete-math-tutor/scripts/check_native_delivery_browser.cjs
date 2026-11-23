// 连接隔离的真实宿主与原生 worker，验证实际聊天表单和 PDF 跳转回执。
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'C:/Users/free/.agents/skills/playwright/node_modules/playwright');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const base=process.argv[2],output=process.argv[3],live=process.env.NATIVE_DELIVERY_LIVE==='1',readerOnly=process.env.NATIVE_DELIVERY_READER_ONLY==='1';
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 const report={scope:live?'真实模型与真实宿主/原生链路':'本机受控模型',checks:[],errors:[]};
 try {
  const context=await browser.newContext({viewport:{width:1440,height:1000}});
  await context.addInitScript(()=>{
   localStorage.setItem('experimental-psychology-3-demo-student','browser-delivery');
   sessionStorage.setItem('experimental-psychology-3-task-session','browser-session');
  });
  const page=await context.newPage();page.on('pageerror',error=>report.errors.push(error.message));
  await page.goto(base,{waitUntil:'domcontentloaded'});
  await page.waitForFunction(()=>typeof state!=='undefined' && !state.initializing,{},{timeout:90000});
  await page.locator('.native-controls summary').click();
  const capability=page.getByRole('combobox',{name:'选择能力'});
  await page.waitForFunction(()=>document.querySelector('.native-controls select')?.options.length===11,{},{timeout:90000});
  if(!readerOnly){
  await capability.selectOption('deep_question');
  await page.locator('#chat-input').fill(live?'请直接生成一道实验心理学自变量和因变量的基础单选题，四个选项。只出一道题，无需询问偏好。':'CHAIN_QUIZ：生成一道自变量和因变量的选择题');
  await page.locator('#chat-form').evaluate(form=>form.requestSubmit());
  await page.waitForFunction(()=>document.querySelector('.native-quiz-question') ||
    (!state.sending && state.chat.filter(m=>m.role==='assistant').at(-1)?.failed),{},{timeout:240000});
  const failure=await page.evaluate(()=>state.chat.filter(m=>m.role==='assistant').at(-1)?.failed
    ? state.chat.filter(m=>m.role==='assistant').at(-1).content : null);
  if(failure){report.failure=failure;throw new Error('出题未成功交付：'+failure);}
  await page.locator('.native-quiz-question').first().waitFor({timeout:10000});
  const text=await page.locator('.native-quiz-question').first().innerText();
  assert(text.includes('自变量') && (live?text.length>40:text.includes('由研究者主动操纵')),text);
  report.quiz_text=text;
  const quiz=await page.evaluate(()=>state.chat.filter(m=>m.nativeResult?.summary).at(-1)?.nativeResult);
  report.quiz_result=quiz;
  if(live){assert(quiz?.summary?.success);assert(!JSON.stringify(quiz.summary).includes('correct_answer'));assert(!JSON.stringify(quiz.summary).includes('explanation'));}
  assert(!(await page.content()).includes('私有解析'));
  report.checks.push('real_chat_form_native_question_card_without_answer_key');
  await page.waitForFunction(()=>!state.sending);
  }
  await capability.selectOption('immersive_reading');
  await page.locator('#reader-toggle').click();
  await page.waitForFunction(()=>window.TextbookPDF && typeof actualReaderPosition!=='undefined' && actualReaderPosition?.page,{},{timeout:90000});
  const acknowledgement=page.waitForResponse(response=>response.url().includes('/reader-receipt') && response.request().method()==='POST',{timeout:240000});
  await page.locator('#chat-input').fill(live?'请立即调用 reader_goto，把当前教材翻到 PDF 第2页（locator=2）。只需完成翻页，不需要解释教材。':'CHAIN_GOTO：请翻到教材第2页');
  await page.locator('#chat-form').evaluate(form=>form.requestSubmit());
  const response=await acknowledgement;const receipt=await response.json();
  report.receipt=receipt;
  assert.equal(response.status(),200);assert.equal(receipt.status,'applied',JSON.stringify(receipt));
  assert.equal(receipt.page,2);
  const position=await page.evaluate(()=>actualReaderPosition);
  assert.equal(position.page,2);report.position=position;
  report.checks.push('native_reader_goto_reaches_actual_pdf_page_and_saved_receipt');
  if(live && !readerOnly){
   await page.waitForFunction(()=>!state.sending,{},{timeout:240000});
   const history=await page.evaluate(async()=>{const r=await fetch(conversationHistoryUrl());return r.json();});
   report.history=history;
   assert(history.some(row=>row.role==='assistant' && row.selection_ref?.native_result?.summary?.success),'题目未保存到历史');
   await page.reload({waitUntil:'domcontentloaded'});
   await page.locator('.native-quiz-question').first().waitFor({timeout:90000});
   assert((await page.locator('.native-quiz-question').first().innerText()).includes('自变量'));
   report.checks.push('real_model_question_history_restores_card');
  }
  assert.deepEqual(report.errors,[]);
  await page.screenshot({path:path.join(output,'delivery.png'),fullPage:true});
  report.passed=true;
 } finally {
  fs.writeFileSync(path.join(output,'browser.json'),JSON.stringify(report,null,2));
  await browser.close();console.log(JSON.stringify({scope:report.scope,passed:report.passed||false,checks:report.checks,errors:report.errors,receipt:report.receipt}));
 }
})().catch(error=>{console.error(error);process.exitCode=1;});
