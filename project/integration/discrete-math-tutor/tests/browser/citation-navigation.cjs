/* 真实 PDF.js 与教材接口；不发送 AI 问题，不读取学生历史。 */
const {chromium}=require('playwright');
const {spawn}=require('node:child_process');
const assert=require('node:assert/strict');
const ROOT=process.env.TASK_TEST_ROOT||'E:/项目/heart/project/integration/discrete-math-tutor';
(async()=>{
 const child=spawn(ROOT+'/.venv-gpu/Scripts/python.exe',['-X','utf8','-u',ROOT+'/artifacts/serve-citation-acceptance.py'],{cwd:ROOT,windowsHide:true,stdio:['ignore','pipe','pipe']});
 let browser,BASE_URL,stderr='';child.stderr.on('data',data=>stderr+=data.toString());
 try{
  BASE_URL=await new Promise((resolve,reject)=>{let output='';const timer=setTimeout(()=>reject(new Error(stderr)),30000);child.stdout.on('data',data=>{output+=data.toString();for(const line of output.split('\n')){try{const value=JSON.parse(line);if(value.url){clearTimeout(timer);resolve(value.url);}}catch{}}});child.on('exit',()=>reject(new Error(stderr)));});
  browser=await chromium.launch({headless:false,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
  const context=await browser.newContext({viewport:{width:1500,height:1000}});
  await context.route('**/api/**',async route=>{
   const pathname=new URL(route.request().url()).pathname;
   if(pathname.startsWith('/api/course/')||pathname.startsWith('/api/pdf/')){await route.continue();return;}
   let value={};if(pathname.endsWith('/conversation'))value=[];
   else if(pathname.endsWith('/dashboard'))value={activity:[],chapter_scores:[],chapters:[]};
   else if(pathname.endsWith('/capabilities'))value={enabled:false};
   else if(pathname.endsWith('/pending'))value={pending:null};
   await route.fulfill({json:value});
  });
  const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  page.on('console',message=>{if(message.type()==='error')console.log('浏览器 console:',message.text());});
  page.on('requestfailed',request=>console.log('请求失败:',request.url(),request.failure()));
  await page.goto(BASE_URL);
  try{await page.waitForFunction(()=>state.sectionData?.pdf&&window.TextbookPDF);}catch(error){console.log('启动诊断',await page.evaluate(()=>({tree:document.querySelector('#course-tree').textContent,toast:document.querySelector('#toast').textContent,pdf:state.sectionData?.pdf,reader:typeof window.TextbookPDF})),errors,stderr);throw error;}
  await page.waitForLoadState('networkidle');
  // 重现截图：只有来源和小节起页、没有坐标，也没有[1]引用标记。
  await page.evaluate(()=>{state.chat=[{renderKey:'citation-old',role:'assistant',content:'先找首尾相接的序偶。',sources:['第9章关系（新）.txt／9.1.3 关系的基本特性（PDF第8页起）'],pdfReferences:[]}];showView('chat');renderChat();});
  await page.locator('[data-source-citation="0"]').click();
  await page.waitForFunction(()=>state.pdfFocus?.location_kind==='section_heading');
  await page.locator('.pdf-reader[data-document="chapter-09"] .Highlight__part').first().waitFor({state:'visible'});
  assert.equal(await page.evaluate(()=>state.chapter),9);
  assert.equal(await page.evaluate(()=>state.pdfFocus.rects[0].page),8);
  const heading=page.locator('.pdf-reader[data-document="chapter-09"] .Highlight__part').first();
  const headingBox=await heading.boundingBox();const surfaceBox=await page.locator('.pdf-reader[data-document="chapter-09"] .pdf-surface').boundingBox();
  assert(headingBox.y>=surfaceBox.y&&headingBox.y<surfaceBox.y+surfaceBox.height,'小节标题高亮应在当前视口');
  console.log('PASS：无坐标/无[1]的旧来源可点击，跨章跳到第8页并高亮小节标题');
  // 旧引用带定义编号：应优先定位定义，不仅打开小节。
  await page.evaluate(()=>{state.chat=[{renderKey:'citation-defined',role:'assistant',content:'根据定义9.5，若xRy且yRz，则应有xRz。[1]',sources:['第9章关系（新）.txt／9.1.3 关系的基本特性（PDF第8页起）'],pdfReferences:[]}];showView('chat');renderChat();});
  await page.locator('[data-source-citation="0"]').click();
  await page.waitForFunction(()=>state.pdfFocus?.location_kind==='numbered_unit');
  await page.locator('.pdf-reader[data-document="chapter-09"] .Highlight__part').first().waitFor({state:'visible'});
  assert.match(await page.evaluate(()=>state.pdfFocus.text),/定义9\.5/);
  console.log('PASS：旧来源按回答中的定义9.5解析真实段落，自动高亮');
  // 已有结构化坐标：来源文字和原跳转按钮均可用。
  await page.evaluate(()=>{renderChat();showView('chat');});
  await page.locator('[data-pdf-citation="0"]').click();
  await page.waitForFunction(()=>state.view==='course');
  await page.locator('.pdf-reader[data-document="chapter-09"] .Highlight__part').first().waitFor({state:'visible'});
  const bad=await context.request.post(BASE_URL+'/api/course/citation-location',{data:{source:'其他教材.txt／9.1.3 关系的基本特性'}});assert.equal(bad.status(),422);
  assert.deepEqual(errors,[]);
  await page.screenshot({path:ROOT+'/artifacts/citation-navigation.png'});
  console.log('PASS：已有坐标按钮可重复跳转，非法来源拒绝，页面无异常');
 }finally{await browser?.close();if(BASE_URL)await fetch(BASE_URL+'/__test__/shutdown',{method:'POST'}).catch(()=>{});if(child.exitCode===null)await new Promise(resolve=>{const timer=setTimeout(()=>{child.kill();resolve();},5000);child.once('exit',()=>{clearTimeout(timer);resolve();});});}
})().catch(error=>{console.error(error);process.exitCode=1;});
