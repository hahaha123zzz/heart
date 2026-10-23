const {chromium}=require('playwright');
const {createServer}=require('node:http');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const ROOT=path.resolve(__dirname,'../..');
const SOURCE=process.env.READER_FIXTURE_SOURCE||'http://127.0.0.1:8000';
const OUT=path.resolve(process.env.READER_WHEEL_ARTIFACTS||path.join(ROOT,'artifacts/reader-wheel',new Date().toISOString().replace(/[:.]/g,'-')));
(async()=>{
 fs.mkdirSync(OUT,{recursive:true});console.log('证据目录',OUT);
 const fixtures=new Map(),attempts=[],errors=[],requests=[],events=[];
 async function capture(url){const response=await fetch(SOURCE+url);assert(response.ok,url);const data=Buffer.from(await response.arrayBuffer());fixtures.set(url,{data,type:response.headers.get('content-type')});return JSON.parse(data);}
 const chapters=await capture('/api/course/chapters');await capture('/api/course/reading-map');
 for(const chapter of chapters.slice(0,2)){
  const section=await capture(`/api/course/chapters/${chapter.id}/sections/1`);
  const response=await fetch(SOURCE+section.pdf.url);assert(response.ok);
  fixtures.set(section.pdf.url,{data:Buffer.from(await response.arrayBuffer()),type:'application/pdf'});
 }
 const server=createServer((req,res)=>{
  const url=new URL(req.url,'http://localhost'),key=decodeURI(url.pathname);
  requests.push({method:req.method,path:key});
  const fixture=fixtures.get(key)||fixtures.get(url.pathname);
  if(fixture){res.writeHead(200,{'Content-Type':fixture.type});res.end(fixture.data);return;}
  if(key.startsWith('/api/')){
   let value={};if(key.endsWith('/conversation'))value=[];
   else if(key.endsWith('/dashboard'))value={activity:[],chapter_scores:[],chapters:[]};
   else if(key.endsWith('/capabilities'))value={enabled:false};
   else if(key.endsWith('/pending'))value={pending:null};
   else if(key.endsWith('/citation-state'))value={stale:false};
   res.writeHead(200,{'Content-Type':'application/json'});res.end(JSON.stringify(value));return;
  }
  const file=key==='/'?path.join(ROOT,'frontend/index.html'):path.resolve(ROOT,'frontend',key.replace(/^\/static\//,''));
  if(!file.startsWith(path.join(ROOT,'frontend')+path.sep)||!fs.existsSync(file)||!fs.statSync(file).isFile()){res.writeHead(404);res.end();return;}
  res.setHeader('Content-Type',({'.js':'text/javascript','.mjs':'text/javascript','.css':'text/css','.html':'text/html','.svg':'image/svg+xml','.pdf':'application/pdf'})[path.extname(file)]||'application/octet-stream');fs.createReadStream(file).pipe(res);
 });
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const BASE=`http://127.0.0.1:${server.address().port}`;
 let browser,context,page;
 try{
  browser=await chromium.launch({headless:false,executablePath:process.env.BROWSER_PATH||'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
  context=await browser.newContext({viewport:{width:1550,height:1050}});await context.tracing.start({screenshots:true,snapshots:true,sources:true});
  await context.exposeFunction('recordReaderWheel',event=>events.push(event));
  await context.addInitScript(()=>{
   localStorage.setItem('experimental-psychology-3-demo-student','reader-wheel-isolated-student');
   window.wheelEvidence=[];
   window.addEventListener('pdf-position',e=>{const event={kind:'position',...e.detail};window.wheelEvidence.push(event);window.recordReaderWheel(event);});
  });
  page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
  const input=()=>page.locator('#chapter-content [aria-label="PDF 页码"]');
  const container=()=>page.locator('#chapter-content .PdfHighlighter');
  const number=async()=>Number(await input().inputValue());
  const expectPage=async n=>page.waitForFunction(n=>Number(document.querySelector('#chapter-content [aria-label="PDF 页码"]')?.value)===n,n);
  const idle=()=>page.waitForTimeout(350); // 明确分隔独立手势，非页面就绪等待。
  const dispatch=async(extra={})=>container().evaluate((el,extra)=>{const e=new WheelEvent('wheel',{deltaY:120,bubbles:true,cancelable:true,...extra});el.dispatchEvent(e);const event={kind:'wheel',...extra,prevented:e.defaultPrevented};window.wheelEvidence.push(event);window.recordReaderWheel(event);return e.defaultPrevented;},extra);
  async function check(name,fn){const start=Date.now();try{await fn();attempts.push({name,pass:true,ms:Date.now()-start});console.log('PASS',name);}catch(error){attempts.push({name,pass:false,error:error.stack,ms:Date.now()-start});throw error;}}
  await page.goto(BASE);await page.locator('#chapter-content canvas').first().waitFor();await expectPage(1);
  await check('正文中部 CDP 滚轮上下翻页，不必到边缘',async()=>{
   const box=await container().boundingBox();await page.mouse.move(box.x+box.width/2,box.y+box.height/2);
   await page.mouse.wheel(0,120);await expectPage(2);await idle();await page.mouse.wheel(0,-120);await expectPage(1);
  });
  await check('触控板小幅累计与 2 秒惯性连续序列仅一页',async()=>{
   await idle();const maxGap=await container().evaluate(async el=>{
    let last=performance.now(),maxGap=0;
    for(let i=0;i<80;i++){const now=performance.now();maxGap=Math.max(maxGap,now-last);last=now;el.dispatchEvent(new WheelEvent('wheel',{deltaY:i<40?3:1,bubbles:true,cancelable:true}));await new Promise(resolve=>setTimeout(resolve,25));}
    const event={kind:'continuous-gesture',events:80,maxGap};window.wheelEvidence.push(event);window.recordReaderWheel(event);return maxGap;
   });assert(maxGap<280,'事件序列本身必须连续，避免测试宿主通信停顿制造新手势');await expectPage(2);
   await idle();await dispatch();await expectPage(3);
  });
  await check('工具栏按钮及输入；首尾不越界，不推动外层或推进章节',async()=>{
   await page.getByRole('button',{name:'上一页',exact:true}).click();await expectPage(2);
   await input().fill('1');await expectPage(1);await idle();const outer=await page.evaluate(()=>({y:scrollY,chapter:state.chapter,section:state.section}));
   await dispatch({deltaY:-120});await expectPage(1);assert.deepEqual(await page.evaluate(()=>({y:scrollY,chapter:state.chapter,section:state.section})),outer);
   const count=await page.evaluate(()=>state.sectionData.pdf.page_count);await input().fill(String(count));await expectPage(count);await idle();await dispatch();await expectPage(count);
   await input().fill('2');await expectPage(2);
  });
  await check('目录聊天外层及工具栏未拦截；修饰键与横向不翻页',async()=>{
   const n=await number();
   for(const selector of ['#course-tree','#chat-input','body','.pdf-toolbar']){
    assert.equal(await page.locator(selector).evaluate(el=>{const e=new WheelEvent('wheel',{deltaY:10,bubbles:true,cancelable:true});el.dispatchEvent(e);return e.defaultPrevented;}),false);
   }
   assert.equal(await input().evaluate(el=>{const e=new WheelEvent('wheel',{deltaY:10,bubbles:true,cancelable:true});el.dispatchEvent(e);return e.defaultPrevented;}),false);
   for(const extra of [{ctrlKey:true},{metaKey:true},{shiftKey:true},{deltaX:150}]){await idle();assert.equal(await dispatch(extra),false);}
   assert.equal(await number(),n);
  });
  await check('目录和右侧聊天实际 CDP 滚动保持独立',async()=>{
   const n=await number();
   await page.evaluate(()=>{const chat=document.querySelector('#chat-messages');chat.innerHTML='<p>局部滚动验收</p>'.repeat(100);chat.scrollTop=0;document.querySelector('#course-panel-body').scrollTop=0;});
   for(const selector of ['#course-panel-body','#chat-messages']){
    const region=page.locator(selector),box=await region.boundingBox();await page.mouse.move(box.x+box.width/2,box.y+box.height/2);await page.mouse.wheel(0,150);
    await page.waitForFunction(selector=>document.querySelector(selector).scrollTop>0,selector);assert.equal(await number(),n);
   }
   await page.evaluate(()=>renderChat());
  });
  await check('真实文字层选区及菜单活跃不翻页，取消后可翻页',async()=>{
   await page.waitForFunction(()=>document.querySelector('.page[data-page-number="2"] .textLayer span')?.textContent);
   await page.evaluate(()=>{const node=document.querySelector('.page[data-page-number="2"] .textLayer span').firstChild;const range=document.createRange();range.selectNodeContents(node);const selection=getSelection();selection.removeAllRanges();selection.addRange(range);});
   await page.locator('.pdf-selection-menu').waitFor();await idle();assert.equal(await dispatch({deltaY:3}),false);assert.equal(await number(),2);
   await page.locator('.pdf-selection-menu').getByRole('button',{name:'取消'}).click();await idle();await dispatch();await expectPage(3);
  });
  await check('鼠标区域圈选拖动和菜单不翻页，取消恢复',async()=>{
   await page.getByRole('button',{name:'框选图 / 公式'}).click();const box=await container().boundingBox();
   await page.mouse.move(box.x+100,box.y+100);await page.mouse.down();await page.mouse.move(box.x+240,box.y+180,{steps:5});
   await idle();assert.equal(await dispatch({deltaY:3}),false);assert.equal(await number(),3);await page.mouse.up();
   await page.locator('.pdf-selection-menu').waitFor();await idle();assert.equal(await dispatch({deltaY:3}),false);
   await page.locator('.pdf-selection-menu').getByRole('button',{name:'取消'}).click();await page.getByRole('button',{name:'退出框选'}).click();
  });
  await check('引用坐标跳转高亮保留，随后可滚轮翻页',async()=>{
   await page.evaluate(()=>{const m=state.sectionData.pdf;state.pdfFocus={document_id:m.document_id,version:m.version,kind:'text',text:m.section.title,rects:[m.section.rect]};syncPDFReader();});
   await expectPage(1);const highlight=page.locator('#chapter-content .Highlight__part').first();await highlight.waitFor();
   const h=await highlight.boundingBox(),body=await container().boundingBox();assert(h.y>=body.y&&h.y<body.y+body.height,'真实章节标题引用应定位到可见正文');
   await page.screenshot({path:path.join(OUT,'citation.png')});await idle();await dispatch();await expectPage(2);
  });
  await check('200% 缩放后滚动条可访问页下半部分，滚轮仍直接翻页',async()=>{
   await page.getByLabel('PDF 缩放').selectOption('2');
   await page.waitForFunction(()=>document.querySelector('.page[data-page-number="2"]').clientHeight>document.querySelector('.PdfHighlighter').clientHeight);
   const result=await container().evaluate(el=>{const p=el.querySelector('.page[data-page-number="2"]');el.scrollTop=p.offsetTop+p.clientHeight-el.clientHeight-10;return {overflow:getComputedStyle(el).overflowY,height:p.clientHeight,viewport:el.clientHeight,lower:el.scrollTop>p.offsetTop};});
   assert.equal(result.overflow,'auto');assert(result.lower);await expectPage(2);await page.screenshot({path:path.join(OUT,'zoom-lower-half.png')});
   await idle();await dispatch();await expectPage(3);
  });
  await check('现有 pdf-position / Workspace 刷新恢复页码和缩放',async()=>{
   await page.waitForFunction(()=>Workspace.resumeFor(state.sectionData.pdf)?.page===3);
   await page.reload();await page.locator('#chapter-content canvas').first().waitFor();await expectPage(3);assert.equal(await page.getByLabel('PDF 缩放').inputValue(),'2');
  });
  await check('换章与重复挂载后单个滚轮仅翻一页；page_map沿用来源页',async()=>{
   await page.evaluate(()=>selectSection(2,1,{record:false}));await page.locator('[data-document="experimental-psychology-3:chapter-02"] canvas').first().waitFor();await expectPage(1);
   await page.evaluate(()=>{for(let i=0;i<5;i++)syncPDFReader();});await idle();await dispatch();await expectPage(2);
   await page.evaluate(()=>{const host=document.querySelector('#chapter-content .pdf-reader-host');TextbookPDF.unmount(host);const pdf=state.sectionData.pdf;state.sectionData.pdf={...pdf,page_map:Array.from({length:pdf.page_count},(_,i)=>i+101)};syncPDFReader();});
   await page.locator('[data-document="experimental-psychology-3:chapter-02"] canvas').first().waitFor();await expectPage(1);await idle();await dispatch();await expectPage(2);
   await page.waitForFunction(()=>document.querySelector('.pdf-source-page')?.textContent.includes('102'));
   await page.waitForFunction(()=>wheelEvidence.some(e=>e.kind==='position'&&e.page===102));
  });
  assert.deepEqual(errors,[]);await page.screenshot({path:path.join(OUT,'final.png')});
 }finally{
  if(page){fs.writeFileSync(path.join(OUT,'events.json'),JSON.stringify(events,null,2));await page.screenshot({path:path.join(OUT,'last-state.png')}).catch(()=>{});}
  fs.writeFileSync(path.join(OUT,'results.json'),JSON.stringify({base:BASE,source:SOURCE,isolatedStudent:'reader-wheel-isolated-student',database:'none: all non-course APIs stubbed in isolated server; no writes forwarded',attempts,errors,requests,readerSHA256:crypto.createHash('sha256').update(fs.readFileSync(path.join(ROOT,'frontend/pdf-reader/reader.js'))).digest('hex'),pdfs:[...fixtures.entries()].filter(([k])=>k.endsWith('/file')).map(([url,v])=>({url,sha256:crypto.createHash('sha256').update(v.data).digest('hex')}))},null,2));
  await context?.tracing.stop({path:path.join(OUT,'trace.zip')});await browser?.close();await new Promise(resolve=>server.close(resolve));
 }
})().catch(error=>{console.error(error);process.exitCode=1;});
