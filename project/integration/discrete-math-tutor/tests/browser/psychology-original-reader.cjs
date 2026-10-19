const {chromium}=require('playwright'),assert=require('node:assert/strict');
const BASE=process.env.PSYCHOLOGY_ORIGINAL_URL||'http://127.0.0.1:8002';
(async()=>{
 const browser=await chromium.launch({headless:false,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 try{
  const page=await browser.newPage({viewport:{width:1500,height:1060}}),errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.addInitScript(()=>{localStorage.setItem('discrete-math-demo-student','old-math-student');localStorage.setItem('discrete-workspace:old-math-student',JSON.stringify({lastReading:{chapter:7,section:7}}));});
  await page.goto(BASE);await page.locator('#chapter-content canvas').first().waitFor({timeout:30000});
  assert.equal(await page.title(),'实验心理学学习平台');assert.equal(await page.locator('.sidebar-brand strong').innerText(),'实验心理学');
  assert.equal(await page.evaluate(()=>state.chapters.length),11);assert.equal(await page.evaluate(()=>state.chapter),1);assert.notEqual(await page.evaluate(()=>studentId),'old-math-student');
  await page.locator('#course-tree [data-open-chapter="11"]').click();await page.locator('#course-tree [data-chapter="11"][data-section="3"]').click();
  await page.locator('#chapter-content [data-document="experimental-psychology-3:chapter-11"] canvas').first().waitFor({timeout:30000});
  const response=await page.request.get(BASE+'/api/course/chapters/11/sections/3'),section=await response.json();
  assert.equal(await page.evaluate(()=>state.chapter),11);assert.equal(await page.evaluate(()=>state.section),3);
  const target=section.pdf.section.page;
  await page.waitForFunction(n=>Number(document.querySelector('#chapter-content [aria-label="PDF 页码"]').value)>=n,target);
  await page.locator('#course-tree [data-open-chapter="1"]').click();await page.locator('#course-tree [data-chapter="1"][data-section="1"]').click();
  await page.locator('#chapter-content [data-document="experimental-psychology-3:chapter-01"] canvas').first().waitFor();
  const location=await page.request.post(BASE+'/api/course/citation-location',{data:{source:section.source+' / '+section.title,response:'教材说明[1]'}});assert.equal(location.status(),200);
  const reference=(await location.json()).selection_ref;
  await page.evaluate(({section,reference})=>{state.chat=[{renderKey:'course-citation-test',role:'assistant',content:'**阅读方法**请核对教材。[1]',sources:[section.source+' / '+section.title],pdfReferences:[{source_index:0,selection_ref:reference}]}];renderChat();},{section,reference});
  await page.locator('[data-source-citation]').first().click();
  await page.locator('#chapter-content .Highlight__part').first().waitFor({timeout:20000});
  assert.equal(await page.locator('#chapter-content .Highlight__part').first().evaluate(e=>e.closest('.page').dataset.pageNumber),String(reference.rects[0].page));
  assert.equal(await page.evaluate(()=>state.chapter),11);
  await page.locator('#primary-nav [data-view="quiz"]').click();await page.locator('#quiz-chapter').selectOption('11');
  await page.waitForFunction(()=>document.querySelector('#quiz-view').textContent.includes('未发现独立习题栏'));
  assert(!/欧拉|真值表|集合代数|离散数学/.test(await page.locator('body').innerText()));
  await page.screenshot({path:'artifacts/psychology-original-reader.png'});
  assert.deepEqual(errors,[]);console.log('PASS: 原页面心理学名称、11章跨章导航、旧阅读状态隔离、回答引用跨章高亮、旧题库隔离');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1)});
