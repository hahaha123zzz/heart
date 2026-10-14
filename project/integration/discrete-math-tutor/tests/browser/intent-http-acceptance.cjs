/* 真实HTTP/PDF/练习联合验收，需先启动 serve_intent_acceptance.py。模型仍为夹具。 */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const BASE_URL=process.env.INTENT_ACCEPTANCE_URL || 'http://127.0.0.1:8767';
const ROOT=process.env.TASK_TEST_ROOT || 'E:/项目/heart/project/integration/discrete-math-tutor';
(async()=>{
 const browser=await chromium.launch({headless:false,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 const results=[],errors=[];let fixture=false;
 try{
  const context=await browser.newContext();const page=await context.newPage();
  const status=await context.request.get(BASE_URL+'/_acceptance/state');assert(status.ok());assert.equal((await status.json()).fixture,true);fixture=true;
  page.on('pageerror',e=>errors.push(e.message));
  const ready=async()=>{try{await page.waitForFunction(()=>!state.taskRecoveryNeeded && !!state.sectionData);}catch(error){console.error('初始化诊断',errors,await page.evaluate(()=>({recovery:state.taskRecoveryNeeded,section:!!state.sectionData,course:document.querySelector('#course-tree').textContent,error:document.querySelector('#chat-error').textContent})));throw error;}};
  // 使用页面自身SSE解码后的返回值；Edge无法稳定读取已cancel的流响应体。
  const observe=()=>page.evaluate(()=>{const original=streamChat;streamChat=async(...args)=>{try{const result=await original(...args);window.__httpResult=result;return result;}catch(error){window.__httpError=error.message;throw error;}};});
  const finished=async()=>{await page.waitForFunction(()=>!state.sending && (window.__httpResult || window.__httpError));const result=await page.evaluate(()=>({result:window.__httpResult,error:window.__httpError}));assert(!result.error,result.error);return result.result;};
  const reset=()=>page.evaluate(()=>{window.__httpResult=null;window.__httpError=null;});
  const send=async text=>{await reset();await page.locator('#chat-input').fill(text);await page.locator('#chat-form').evaluate(f=>f.requestSubmit());return finished();};
  await page.goto(BASE_URL);await ready();await observe();await page.locator('#chapter-content canvas').first().waitFor();
  await page.getByRole('button',{name:'框选图 / 公式',exact:true}).click();
  const canvas=await page.locator('#chapter-content canvas').first().boundingBox();
  const surface=await page.locator('#chapter-content .pdf-surface').boundingBox();
  const x=Math.max(canvas.x+80,surface.x+40),y=Math.max(canvas.y+120,surface.y+80);
  await page.mouse.move(x,y);await page.mouse.down();await page.mouse.move(x+140,y+70,{steps:8});await page.mouse.up();
  await page.getByRole('button',{name:'向 AI 提问',exact:true}).click();await page.waitForFunction(()=>!!state.pdfDraft);
  const draft=await page.evaluate(()=>structuredClone(state.pdfDraft));assert.equal(draft.kind,'area');
  const crop=await context.request.get(BASE_URL+draft.image_refs[0].image_url);assert(crop.ok());assert((await crop.body()).length>100);
  const pdf=await send('只给这个选区一个提示');assert.equal(pdf.quality_check.passed,true);assert.equal(pdf.task_execution.learning_intents[0],'hint');assert.equal(pdf.selection_ref.document_id,draft.document_id);assert.deepEqual(pdf.selection_ref.rects,draft.rects);assert.notEqual(pdf.step_advanced,true);
  results.push({case:'真实框选、裁图、提示和引用',passed:true,document:pdf.selection_ref.document_id,page:draft.rects[0].page});
  await page.getByRole('button',{name:'退出框选',exact:true}).click();
  const textBox=await page.evaluate(()=>{
   const view=document.querySelector('#chapter-content .pdf-surface').getBoundingClientRect();
   for(const span of document.querySelectorAll('#chapter-content .textLayer span:not(.markedContent)')){
    const box=span.getBoundingClientRect();
    if(span.textContent.trim().length>5 && box.width>30 && box.top>view.top+5 && box.bottom<view.bottom-5)
      return {x:box.x,y:box.y,width:box.width,height:box.height};
   }
  });assert(textBox,'没有可划选的PDF文字');
  await page.mouse.move(textBox.x+2,textBox.y+textBox.height/2);await page.mouse.down();await page.mouse.move(textBox.x+textBox.width-2,textBox.y+textBox.height/2,{steps:10});await page.mouse.up();
  await page.getByRole('button',{name:'向 AI 提问',exact:true}).click();await page.waitForFunction(()=>state.pdfDraft?.kind==='text');
  const textResult=await send('只给这段文字的提示');assert.equal(textResult.selection_ref.kind,'text');assert(textResult.selection_ref.text.trim());
  results.push({case:'真实文字划选、提问及文字引用',passed:true});
  const clarification=await send('请确认选区对象');assert.equal(clarification.answer_status,'awaiting_clarification');
  const task=clarification.task_id;await page.reload();await ready();await observe();assert.equal(await page.locator('[data-task-cancel]').count(),1);
  await reset();await page.locator('[data-task-option]').first().click();
  const resumed=await finished();assert.equal(resumed.task_id,task);assert(resumed.task_revision>clarification.task_revision);assert.equal(resumed.selection_ref.document_id,draft.document_id);
  results.push({case:'真实待澄清恢复、选择及原选区继续',passed:true});
  await page.evaluate(()=>{showView('quiz');});await page.locator('[data-practice-ask="p1"]').waitFor();
  // 第1章首题为真实选择题，分别保存两个小题作答，检查辅导仅接收p1。
  await page.locator('[data-answer-part="p1"][value="A"]').check();
  await page.locator('[data-practice-ask="p1"]').click();await page.waitForFunction(()=>state.exerciseDraft?.target.part_id==='p1');
  const exercise=await send('只给本小题一个提示');assert.equal(exercise.task_execution.learning_intents[0],'hint');assert.notEqual(exercise.step_advanced,true);assert.equal(exercise.answer_status,'answered');
  const observation=await (await context.request.get(BASE_URL+'/_acceptance/state')).json();
  const generation=observation.observations.filter(r=>r.kind==='exercise_generation').at(-1);assert.deepEqual(generation.parts,['p1']);assert.deepEqual(generation.answers,{p1:['A']});assert(generation.images>0);
  results.push({case:'真实题库、草稿、小题聊天及当前作答',passed:true,images:generation.images});
  const target=await page.evaluate(()=>state.exerciseDraft.target);
  const invalid=await context.request.post(BASE_URL+'/api/chat/stream',{data:{student_id:await page.evaluate(()=>studentId),message:'提示',exercise_target:{...target,version:'0'.repeat(64)}}});assert.equal(invalid.status(),422);
  results.push({case:'失效题目版本在SSE前拒绝',passed:true});
  await page.screenshot({path:path.join(ROOT,'docs/intent-research/阶段E联合验收.png'),fullPage:false});
  assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(ROOT,'docs/intent-research/阶段E联合验收.json'),JSON.stringify({model:'deterministic_fixture',real_http:true,real_pdf:true,real_database:'temporary',semantic_model_evaluation:false,results,pageerrors:errors},null,2));
  console.log(JSON.stringify(results));
 }finally{
  if(fixture)await (await browser.newContext()).request.post(BASE_URL+'/_acceptance/stop').catch(()=>{});
  await browser.close();
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
