const {chromium}=require('playwright'),assert=require('node:assert/strict');
const BASE=process.env.PSYCHOLOGY_PREVIEW_URL||'http://127.0.0.1:8001';
(async()=>{
const browser=await chromium.launch({headless:false,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
try{const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
await page.goto(BASE+'/textbook-preview/psychology');await page.locator('.pdf-reader .textLayer').first().waitFor({timeout:30000});
assert.equal(await page.locator('#sections button').count(),3);
await page.locator('#sections button').nth(2).click();await page.locator('.Highlight__part').first().waitFor();
assert.equal(await page.locator('.Highlight__part').first().evaluate(e=>e.closest('.page').dataset.pageNumber),'14');
const highlight=await page.locator('.Highlight__part').first().boundingBox(),surface=await page.locator('.pdf-surface').boundingBox();assert(highlight.y>=surface.y&&highlight.y<surface.y+surface.height);
await page.locator('#query').fill('什么是单因素随机区组设计');const answer=page.waitForResponse(r=>r.url().includes('/psychology/search?'));await page.locator('#search button').click();const hits=await(await answer).json();const targetPage=hits[0].reference.rects[0].page;await page.locator('.hit').first().waitFor({timeout:60000});
assert.match(await page.locator('.hit').first().innerText(),/区组/);await page.locator('.hit button').first().click();
await page.waitForFunction(n=>document.querySelector('.Highlight__part')?.closest('.page')?.dataset.pageNumber===String(n),targetPage);await page.locator('.Highlight__part').first().waitFor();
const table=await page.request.get(BASE+'/api/textbook-preview/psychology/search?'+new URLSearchParams({q:'表4-6'}));const tables=await table.json();assert(tables.some(h=>h.kind==='table'&&h.text.includes('表4-6')&&h.reference.location_kind==='table_caption'));
// 浏览器只模拟模型最终响应，引用使用真实检索锚点；真实模型验收由独立脚本完成。
await page.route('**/api/textbook-preview/psychology/ask',async route=>{assert.equal(route.request().postDataJSON().question,'解释区组设计');await route.fulfill({json:{status:'completed',answer:'**随机区组设计**控制个体差异。[1] <script>坏代码</script>',reason:'引用与教材一致',citations:[{id:'1',...hits[0]}]}});});
await page.locator('#question').fill('解释区组设计');await page.locator('#submit-question').click();await page.locator('#answer .citation').waitFor();
assert.equal(await page.locator('#answer strong').innerText(),'随机区组设计');assert.equal(await page.locator('#answer script').count(),0);assert.equal(await page.locator('#qa-process').evaluate(e=>e.open),false);assert.equal(await page.locator('#submit-question').isEnabled(),true);
await page.locator('#sections button').nth(2).click();await page.waitForFunction(()=>document.querySelector('.Highlight__part')?.closest('.page')?.dataset.pageNumber==='14');
await page.locator('#answer .citation').click();await page.waitForFunction(n=>document.querySelector('.Highlight__part')?.closest('.page')?.dataset.pageNumber===String(n),targetPage);
await page.screenshot({path:'artifacts/psychology-preview.png'});
await page.setViewportSize({width:390,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
assert.deepEqual(errors,[]);console.log('PASS: 样章导航、真实检索、问答强调与安全渲染、处理记录折叠、回答引用跨页跳转高亮、移动端宽度');
}finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
