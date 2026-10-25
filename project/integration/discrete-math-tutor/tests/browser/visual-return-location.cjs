const {chromium}=require('playwright'),fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const BASE=process.env.VISUAL_LOCATION_URL||'http://127.0.0.1:18981';
const ROOT=path.resolve(__dirname,'../..'),OUT=path.join(ROOT,'.runtime/visual-location/browser',new Date().toISOString().replace(/[:.]/g,'-'));
(async()=>{
 fs.mkdirSync(OUT,{recursive:true});console.log('evidence',OUT);
 const fixtures=await (await fetch(BASE+'/__test__/fixtures')).json();
 const history=()=>[{id:701,role:'assistant',content:`原图说明。[1]\n\n![教材原图](media:${fixtures.legacy.id})`,image_refs:[fixtures.legacy],textbook_sources:[]}];
 const attempts=[],errors=[],calls=[];let browser,context,page;
 async function check(name,fn){const start=Date.now();try{await fn();attempts.push({name,pass:true,ms:Date.now()-start});console.log('PASS',name);}catch(error){attempts.push({name,pass:false,error:error.stack});throw error;}}
 try{
  browser=await chromium.launch({headless:false,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});context=await browser.newContext({viewport:{width:1550,height:1050}});await context.tracing.start({screenshots:true,snapshots:true,sources:true});
  await context.addInitScript(()=>localStorage.setItem('experimental-psychology-3-demo-student','image-location-isolated-student'));
  await context.route('**/api/**',async route=>{
   const url=new URL(route.request().url()),p=url.pathname;
   if(p.startsWith('/api/course/')||p.startsWith('/api/pdf/')||p.startsWith('/api/figures/')){await route.continue();return;}
   let value={};if(p.endsWith('/conversation'))value=history();else if(p.endsWith('/dashboard'))value={activity:[],chapter_scores:[],chapters:[]};else if(p.endsWith('/pending'))value={pending:null};else if(p.endsWith('/capabilities'))value={enabled:false};
   await route.fulfill({json:value});
  });
  page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>calls.push({method:r.method(),url:r.url(),data:r.url().endsWith('/figure-location')?r.postDataJSON():null}));
  const displayed=()=>page.locator('#chapter-content [aria-label="PDF 页码"]');
  const button=id=>page.locator(`#chat-messages [data-tutor-media="${id}"]`);
  async function setMedia(media){await page.evaluate(media=>{state.chat=[{renderKey:'location-fixture',role:'assistant',content:'同一回答内原图。\n\n'+media.map(m=>'![教材原图](media:'+m.id+')').join('\n\n'),sources:[],imageRefs:media}];renderChat();},media);}
  async function located(media,displayPage=media.selection_ref.rects[0].page){
   await page.waitForFunction(({id,n})=>document.querySelector('#chapter-content .pdf-reader')?.dataset.document===id&&Number(document.querySelector('#chapter-content [aria-label="PDF 页码"]')?.value)===n,{id:media.document_id,n:displayPage});
   const h=page.locator('#chapter-content .AreaHighlight__part').first();await h.waitFor({timeout:30000});
   await page.waitForFunction(()=>{const e=document.querySelector('#chapter-content .AreaHighlight__part'),s=document.querySelector('#chapter-content .PdfHighlighter');if(!e||!s)return false;const a=e.getBoundingClientRect(),b=s.getBoundingClientRect();return Math.min(a.bottom,b.bottom)>Math.max(a.top,b.top)&&Math.min(a.right,b.right)>Math.max(a.left,b.left);});
  }
  await page.goto(BASE);await page.locator('#chapter-content canvas').first().waitFor();await button(fixtures.legacy.id).waitFor();
  await check('历史空rects凭保存身份定位图1-2第14页且原图高亮进入视口',async()=>{
   assert.equal(fixtures.legacy.selection_ref.rects.length,0);await button(fixtures.legacy.id).click();await located(fixtures.media[0]);assert.equal(await displayed().inputValue(),'14');
   assert.equal(await page.evaluate(()=>state.section),2);assert.equal(await page.evaluate(()=>state.chat[0].imageRefs[0].selection_ref.rects.length),0,'不能改写历史');
   await page.screenshot({path:path.join(OUT,'figure-1-2-page-14.png')});
  });
  await check('新回答保存区域、pending与像素标记不伪升级，同章两图各自定位',async()=>{
   assert.equal(fixtures.media[0].location_status,'exact');assert.equal(fixtures.media[0].model_saw_pixels,false);assert.equal(fixtures.media[0].review_status,'pending');
   await setMedia(fixtures.media.slice(0,2));await button(fixtures.media[1].id).click();await located(fixtures.media[1]);await button(fixtures.media[0].id).click();await located(fixtures.media[0]);
   assert.match(await page.locator('#chat-messages .answer-media-caption').first().textContent(),/待审核/);
  });
  await check('第7/8/9章图表跨章返回实际页和可见区域',async()=>{
   for(const media of fixtures.media.slice(2)){
    await setMedia([media]);await button(media.id).click();await located(media);await page.screenshot({path:path.join(OUT,media.id+'.png')});
   }
  });
  await check('放大与滚轮翻页后点击仍准确返回原图',async()=>{
   const media=fixtures.media[0];await setMedia([media]);await button(media.id).click();await located(media);await page.getByLabel('PDF 缩放').selectOption('2');
   const body=page.locator('#chapter-content .PdfHighlighter'),box=await body.boundingBox();await page.mouse.move(box.x+box.width/2,box.y+box.height/2);await page.waitForTimeout(350);await page.mouse.wheel(0,120);
   await page.waitForFunction(()=>document.querySelector('#chapter-content [aria-label="PDF 页码"]').value==='15');await button(media.id).click();await located(media);
  });
  await check('拆分页page_map只换算一次，原图14页映射显示1页',async()=>{
   const media=fixtures.media[0];await setMedia([media]);
   const file=route=>route.fulfill({contentType:'application/pdf',body:fs.readFileSync(path.join(ROOT,'.runtime/visual-location/split14-15.pdf'))});
   const section=async route=>{const response=await route.fetch();const data=await response.json();data.pdf={...data.pdf,url:'/__test__/split.pdf',page_count:2,page_map:[14,15],section:{...data.pdf.section,page:1,y:0}};await route.fulfill({json:data});};
   await context.route('**/__test__/split.pdf',file);await context.route('**/api/course/chapters/1/sections/2',section);
   await button(media.id).click();await located(media,1);assert.match(await page.locator('.pdf-source-page').textContent(),/14/);await page.screenshot({path:path.join(OUT,'split-page-map.png')});
   await context.unroute('**/api/course/chapters/1/sections/2',section);await context.unroute('**/__test__/split.pdf',file);
  });
  await check('快速连点晚到响应不覆盖最后一次导航',async()=>{
   await setMedia(fixtures.media.slice(0,2));let first=true;
   const handler=async route=>{const response=await route.fetch();if(first){first=false;await new Promise(r=>setTimeout(r,800));}await route.fulfill({response});};
   await context.route('**/api/course/figure-location',handler);
   await button(fixtures.media[0].id).click();await button(fixtures.media[1].id).click();await located(fixtures.media[1]);await page.waitForTimeout(1000);assert.equal(await displayed().inputValue(),'15');
   await context.unroute('**/api/course/figure-location',handler);
  });
  await check('陈旧版本/错误哈希/缺资产实际API受控拒绝，不升级到当前版本',async()=>{
   const m=fixtures.media[0],base={asset_id:m.id,sha256:m.sha256,document_id:m.document_id,version:m.version};
   for(const change of [{version:'0'.repeat(64)},{sha256:'0'.repeat(64)},{asset_id:'image-01-9999'}]){
    const response=await context.request.post(BASE+'/api/course/figure-location',{data:{...base,...change}}),data=await response.json();assert(['stale','unavailable'].includes(data.status));assert.equal(data.selection_ref,null);
   }
   assert.equal((await context.request.post(BASE+'/api/course/figure-location',{data:{asset_id:m.id}})).status(),422);
  });
  await check('接口错误不使用旧rects兜底；历史缺身份不发定位请求',async()=>{
   const m=fixtures.media[0];await setMedia([m]);const before=await displayed().inputValue();const handler=route=>route.fulfill({status:503,json:{detail:'isolated backend failure'}});await context.route('**/api/course/figure-location',handler);
   await button(m.id).click();await page.waitForFunction(()=>document.querySelector('#toast').textContent.includes('isolated backend failure'));assert.equal(await displayed().inputValue(),before);await context.unroute('**/api/course/figure-location',handler);
   await page.evaluate(()=>{state.chat[0].imageRefs[0].version='';});const count=calls.filter(c=>c.url.endsWith('/figure-location')).length;await button(m.id).click();await page.waitForFunction(()=>document.querySelector('#toast').textContent.includes('缺少完整身份'));assert.equal(calls.filter(c=>c.url.endsWith('/figure-location')).length,count);
  });
  await check('仅小节与图注诚实降级，歧义不导航',async()=>{
   for(const [status,label] of [['section','打开所在小节'],['caption','查看图注位置'],['ambiguous',null]]){
    const media=fixtures.media[0];await setMedia([media]);const before=await displayed().inputValue();
    const handler=route=>route.fulfill({json:{status,basis:'isolated '+status,chapter_id:1,section_id:2,selection_ref:status==='ambiguous'?null:{...media.selection_ref,kind:'text',rects:status==='section'?[]:media.selection_ref.rects,location_status:status}}});
    await context.route('**/api/course/figure-location',handler);await button(media.id).click();
    if(label){await page.waitForFunction(({id,label})=>document.querySelector('#chat-messages [data-tutor-media="'+id+'"]')?.textContent===label,{id:media.id,label});}
    else {await page.waitForFunction(()=>document.querySelector('#toast').textContent.includes('isolated ambiguous'));assert.equal(await displayed().inputValue(),before);}
    await context.unroute('**/api/course/figure-location',handler);
   }
  });
  await check('刷新恢复历史后再次定位，零新回答/学习推进请求',async()=>{
   await page.reload();await button(fixtures.legacy.id).waitFor();await button(fixtures.legacy.id).click();await located(fixtures.media[0]);
   assert.equal(calls.filter(c=>c.method==='POST'&&/\/api\/chat|\/api\/course\/views|learning.*advance|mastery/.test(c.url)).length,0);
   assert.deepEqual(errors,[]);await page.screenshot({path:path.join(OUT,'final.png')});
  });
 }finally{
  if(page)await page.screenshot({path:path.join(OUT,'last-state.png')}).catch(()=>{});
  fs.writeFileSync(path.join(OUT,'results.json'),JSON.stringify({base:BASE,attempts,errors,calls,models:'zero; new-answer selected_media uses deterministic source fixtures; no Q5 backend calls'},null,2));
  await context?.tracing.stop({path:path.join(OUT,'trace.zip')});await browser?.close();
 }
})().catch(error=>{console.error(error);process.exitCode=1;});
