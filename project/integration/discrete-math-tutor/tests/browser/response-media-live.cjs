/* 已保存真实模型回答的隔离页面复验；不再生成答案。 */
const {chromium}=require('playwright');
const fs=require('node:fs');const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:false,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 const checks=[];const out=process.env.UX_OUTPUT;const url=process.env.UX_TEST_URL||'http://127.0.0.1:8012';
 try{
  const page=await browser.newPage({viewport:{width:375,height:812}});let generations=0;
  page.on('request',r=>{if(r.method()==='POST'&&r.url().endsWith('/api/chat/stream'))generations++;});
  await page.addInitScript(()=>localStorage.setItem('experimental-psychology-3-demo-student','response-ux-real-media-inline'));
  await page.goto(url);await page.waitForFunction(()=>typeof state!=='undefined'&&!state.taskRecoveryNeeded&&state.chat.some(m=>m.imageRefs?.length),null,{timeout:60000});
  await page.locator('[data-mobile-pane="chat"]').click();
  const media=await page.evaluate(()=>state.chat.find(m=>m.imageRefs?.length).imageRefs[0]);
  assert.ok(media.model_saw_pixels&&media.visual_quality_checked);assert.equal(media.review_status,'pending');
  const img=page.locator('#chat-messages .answer-media img');await img.waitFor();
  await page.waitForFunction(()=>document.querySelector('#chat-messages .answer-media img')?.naturalWidth>0);
  assert.equal(await img.count(),1);assert.equal(await img.getAttribute('src'),media.image_url);checks.push('真实历史恢复同一张原图，正文内嵌且pending');
  assert.equal(await page.locator('#chat-messages .grounded-evidence,#chat-messages .message-source').count(),0);
  await page.locator('#chat-messages [data-tutor-citation]').first().click();await page.locator('.citation-popover:popover-open').waitFor();
  assert.ok((await page.locator('.citation-popover blockquote').textContent()).length);await page.keyboard.press('Escape');checks.push('正文上标打开实际原文，无底部引用清单');
  await page.locator('#chat-messages [data-tutor-media]').click();
  await page.waitForFunction(()=>state.chapter===5&&state.section===3,null,{timeout:30000});
  checks.push('返回真实第五章第三节，不声称精确原图区域');
  const status=await page.evaluate(async imageUrl=>(await fetch(imageUrl.replace(/sha256=[a-f0-9]{64}/,'sha256='+'0'.repeat(64)))).status,media.image_url);
  assert.equal(status,410);checks.push('媒体身份变更返回410');
  await page.reload();await page.waitForFunction(()=>!state.taskRecoveryNeeded&&state.chat.some(m=>m.imageRefs?.length),null,{timeout:60000});
  await page.locator('[data-mobile-pane="chat"]').click();
  await page.waitForFunction(()=>document.querySelector('#chat-messages .answer-media img')?.naturalWidth>0);
  assert.equal(generations,0);checks.push('再次刷新原图恢复，零额外生成请求');
  await page.screenshot({path:out+'/media-live.png',fullPage:true});
 }finally{fs.writeFileSync(out+'/media-live.json',JSON.stringify({checks},null,2));await browser.close();}
 console.log('PASS',checks);
})().catch(e=>{console.error(e);process.exitCode=1;});
