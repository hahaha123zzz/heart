// 受控目录检查：不调用模型或写入学习数据。
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'C:/Users/free/.agents/skills/playwright/node_modules/playwright');
const assert=require('node:assert/strict'),path=require('node:path');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.BROWSER_PATH || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 try {
  const page=await browser.newPage();
  let mode='pending',release;
  const catalog={enabled:true,capabilities:[{name:'chat',request_schema:{properties:{}}}],tools:[],resources:{}};
  await page.route('http://native-ui.test/**',async route=>{
   if(route.request().method()!=='POST')return route.fulfill({contentType:'text/html',body:'<div class="chat-composer"></div>'});
   if(mode==='pending')await new Promise(resolve=>release=resolve);
   if(mode==='timeout')return;
   await route.fulfill({status:mode==='error'?503:200,json:catalog});
  });
  await page.goto('http://native-ui.test/');
  const root=path.resolve(__dirname,'../frontend');
  await page.addStyleTag({content:'[hidden]{display:none!important}'});
  await page.addStyleTag({path:path.join(root,'native-ui.css')});
  await page.addScriptTag({path:path.join(root,'native-controls.js')});
  await page.evaluate(()=>TutorNativeControls.bindScope(()=>({student_id:'ui-test',session_id:'ui-test'})));
  await page.locator('summary').click();
  const refresh=page.getByRole('button',{name:'刷新可用能力'}),select=page.getByRole('combobox');
  await page.waitForFunction(()=>document.querySelector('[aria-busy=true]'));
  assert(await refresh.isDisabled());assert.equal(await select.count(),0);
  assert.equal(await page.locator('fieldset:visible').count(),0);
  assert((await page.locator('.native-controls-body').boundingBox()).height<160,'加载状态不应显示大块空表单');
  release();await refresh.waitFor();await page.waitForFunction(()=>!document.querySelector('[aria-busy=true]'));
  assert.equal(await select.inputValue(),'chat');assert.equal(await page.locator('fieldset:visible').count(),0);
  mode='error';await refresh.click();await page.getByRole('status').filter({hasText:'加载失败'}).waitFor();assert(await refresh.isEnabled());
  mode='timeout';await page.evaluate(()=>{const original=AbortSignal.timeout.bind(AbortSignal);AbortSignal.timeout=()=>original(30);});
  await refresh.click();await page.getByRole('status').filter({hasText:'超时'}).waitFor();assert(await refresh.isEnabled());
  mode='ready';await refresh.click();await page.waitForFunction(()=>document.querySelector('select').options.length===1 && !document.querySelector('[aria-busy=true]'));
  assert.equal(await select.inputValue(),'chat');
  catalog.capabilities=[];await refresh.click();await page.getByRole('status').filter({hasText:'暂无可用能力'}).waitFor();assert.equal(await select.count(),0);
  console.log('PASS: 加载时无空控件、刷新禁用、空分组隐藏、失败与超时可重试、空目录提示。');
 } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});

