/* 实际 Markdown 构建产物 + 本地原图；不调用模型，不代替像素发送验收。 */
const {chromium}=require('playwright');const fs=require('fs');const path=require('path');const assert=require('node:assert/strict');
const root=process.env.UX_PROJECT||'E:/项目/heart/project/integration/discrete-math-tutor';
const out=path.join(root,'.runtime/response-experience/20261020/ux4-media');
(async()=>{const fixture=JSON.parse(fs.readFileSync(path.join(out,'fixture.json'),'utf8'));assert.equal(fixture.media.length,1);
const media=fixture.media[0];const browser=await chromium.launch({headless:false,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
const checks=[];
try{const page=await browser.newPage({viewport:{width:375,height:812}});const external=[];
await page.route('**/api/figures/**',route=>route.fulfill({contentType:'image/jpeg',body:fs.readFileSync(fixture.path)}));
page.on('request',req=>{if(req.url().includes('example.org'))external.push(req.url());});
await page.setContent('<base href="http://127.0.0.1:8012/"><meta charset="utf-8">');
await page.addStyleTag({path:path.join(root,'frontend/pdf-reader/reader.css')});
await page.addStyleTag({path:path.join(root,'frontend/tutor-markdown/tutor-markdown.css')});
await page.addScriptTag({path:path.join(root,'frontend/tutor-markdown/tutor-markdown.js')});
const text=`图示解释。[1]\n\n![教材原图](media:${media.id})\n\n![未知](media:unknown) ![外链](https://example.org/x.png)`;
await page.evaluate(({media,text})=>{document.body.innerHTML='<main style="max-width:375px"></main>';document.querySelector('main').innerHTML=TutorMarkdown.render(text,{media:[media]});},{media,text});
const img=page.locator('.answer-media img');await img.waitFor();await page.waitForFunction(()=>document.querySelector('.answer-media img').naturalWidth>0);
assert.equal(await page.locator('img').count(),1);assert.equal(await img.getAttribute('src'),media.image_url);assert.match(await page.locator('.answer-media-caption').textContent(),/待审核/);checks.push('绑定原图、pending、未知与外链隔离');
assert.equal(await page.locator('[data-tutor-media]').getAttribute('data-tutor-media'),media.id);checks.push('返回教材按钮携带本条原图身份');
assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);assert.deepEqual(external,[]);checks.push('375px 与零外链请求');
await page.screenshot({path:path.join(out,'media-mobile.png'),fullPage:true});
const rendered=await page.locator('main').innerHTML();
await page.evaluate(({media,text})=>document.querySelector('main').innerHTML=TutorMarkdown.render(text,{media:[media]}),{media:JSON.parse(JSON.stringify(media)),text});
assert.equal(await page.locator('main').innerHTML(),rendered);checks.push('序列化历史重放一致');
await page.evaluate(({media,text})=>document.querySelector('main').innerHTML=TutorMarkdown.render(text,{media:[{...media,version:'0'.repeat(64)}]}),{media,text});
assert.equal(await page.locator('img').count(),0);assert.match(await page.locator('main').textContent(),/图示解释/);checks.push('身份不匹配不加载，正文保留');
}finally{fs.writeFileSync(path.join(out,'browser.json'),JSON.stringify({checks},null,2));await browser.close();}
console.log('PASS',checks.length,checks.join('；'));
})().catch(e=>{console.error(e);process.exitCode=1});
