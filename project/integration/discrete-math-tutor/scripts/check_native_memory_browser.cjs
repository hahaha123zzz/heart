// 原生记忆真实页面、原生存储与真实模型；不替换工具或模型结果。
const {chromium}=require('C:/Users/free/.agents/skills/playwright/node_modules/playwright');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const base=process.argv[2],output=process.argv[3];
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 const report={scope:'真实Edge/真实原生记忆/真实模型',checks:[],errors:[]};
 let page;
 try{
  const context=await browser.newContext({viewport:{width:1440,height:1000}});
  await context.addInitScript(()=>{
   localStorage.setItem('experimental-psychology-3-demo-student','browser-delivery');
   sessionStorage.setItem('experimental-psychology-3-task-session','memory-browser-session');
  });
  page=await context.newPage();page.on('pageerror',error=>report.errors.push(error.message));
  await page.goto(base,{waitUntil:'domcontentloaded'});
  await page.waitForFunction(()=>typeof state!=='undefined'&&!state.initializing,{},{timeout:90000});
  await page.locator('.sidebar-footer [data-view="settings"]').click();
  const editor=page.locator('#native-memory-content'),save=page.locator('#native-memory-save');
  await editor.waitFor();await page.waitForFunction(()=>!document.querySelector('#native-memory-save').disabled,{},{timeout:90000});
  const content='偏好：先给结论，再给一个例子；用简短中文。偏好标记 MEMORY_BROWSER_PREF_V1。';
  await editor.fill(content);await save.click();
  await page.locator('#native-memory-status').filter({hasText:'记忆已保存'}).waitFor({timeout:90000});
  report.checks.push('settings_ui_writes_original_memory_store');
  const read=await page.evaluate(async()=>{
   const response=await fetch('/api/deeptutor/memory',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({student_id:'browser-delivery',session_id:'memory-other-session',action:'read',layer:'L3',key:'preferences'})});
   if(!response.ok)throw new Error(await response.text());return response.json();
  });
  assert.equal(read.content,content);report.checks.push('same_user_other_session_reads_same_native_preference');
  await page.reload({waitUntil:'domcontentloaded'});
  await page.waitForFunction(()=>typeof state!=='undefined'&&!state.initializing,{},{timeout:90000});
  await page.locator('.sidebar-footer [data-view="settings"]').click();
  await page.waitForFunction(()=>document.querySelector('#native-memory-content')?.value.includes('MEMORY_BROWSER_PREF_V1'),{},{timeout:90000});
  report.checks.push('memory_editor_restores_after_reload');
  await page.locator('[data-view="course"]').first().click();
  await page.locator('.native-controls summary').click();
  await page.locator('input[name="memory_references"][value="preferences"]').check({timeout:90000});
  await page.locator('#chat-input').fill('请先调用 read_memory 读取我的长期偏好，告诉我保存的偏好标记。只回答标记，不要检索教材或联网。');
  await page.locator('#chat-form').evaluate(form=>form.requestSubmit());
  await page.waitForFunction(()=>!state.sending&&state.chat.some(message=>message.role==='assistant'&&message.answerSettled),{},{timeout:240000});
  report.answer=await page.evaluate(()=>state.chat.filter(message=>message.role==='assistant').at(-1).content);
  assert(report.answer.includes('MEMORY_BROWSER_PREF_V1'),report.answer);
  report.checks.push('real_model_uses_selected_native_memory');
  await page.locator('.sidebar-footer [data-view="settings"]').click();
  await page.waitForFunction(()=>!document.querySelector('#native-memory-save').disabled,{},{timeout:90000});
  const other=await page.evaluate(async()=>{
   const headers={'Content-Type':'application/json'};
   await fetch('/api/accounts/test',{method:'POST',headers,body:JSON.stringify({student_id:'memory-other-user',ttl_hours:1})});
   const response=await fetch('/api/deeptutor/memory',{method:'POST',headers,
    body:JSON.stringify({student_id:'memory-other-user',session_id:'other',action:'read',layer:'L3',key:'preferences'})});
   if(!response.ok)throw new Error(await response.text());return response.json();
  });
  assert((await editor.inputValue()).includes('MEMORY_BROWSER_PREF_V1'),'隔离检查时A仍应持有偏好');
  assert(!other.content.includes('MEMORY_BROWSER_PREF_V1'));report.checks.push('other_actor_has_distinct_native_memory');
  await editor.fill('');await save.click();
  await page.locator('#native-memory-status').filter({hasText:'记忆已保存'}).waitFor({timeout:90000});
  await page.locator('#native-memory-reload').click();
  await page.waitForFunction(()=>!document.querySelector('#native-memory-save').disabled,{},{timeout:90000});
  assert.equal(await editor.inputValue(),'');report.checks.push('cleared_memory_readback_is_empty');
  assert.deepEqual(report.errors,[]);
  await page.screenshot({path:path.join(output,'memory.png'),fullPage:true});report.passed=true;
 }finally{
  if(page&&!report.passed){
   report.memory_status=await page.locator('#native-memory-status').textContent().catch(()=>null);
   report.documents=await page.locator('#native-memory-document option').allTextContents().catch(()=>[]);
   await page.screenshot({path:path.join(output,'memory-failed.png'),fullPage:true}).catch(()=>{});
  }
  fs.writeFileSync(path.join(output,'memory-browser.json'),JSON.stringify(report,null,2));
  await browser.close();console.log(JSON.stringify(report));
 }
})().catch(error=>{console.error(error);process.exitCode=1;});
