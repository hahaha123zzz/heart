/* 真实页面/PDF.js，隔离API夹具；不调用模型或正式学生库。 */
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(process.env.Q4_APP_ROOT||'.'),out=path.resolve(process.env.Q4_BROWSER_OUTPUT||'.runtime/q4-joint-browser');
const fixture=JSON.parse(fs.readFileSync(path.join(out,'fixture.json'),'utf8'));
module.exports=(async()=>{
 const browser=await chromium.launch({headless:false,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 const page=await browser.newPage({viewport:{width:1500,height:950}});let acknowledgements=[],errors=[],requests=[];
 page.on('pageerror',e=>errors.push(e.message));
 try{
  await page.route('**/*',async route=>{
   const request=route.request(),u=new URL(request.url()),p=u.pathname;
   if(p.startsWith('/api/')){
    requests.push(p);let data={};
    if(p==='/api/course/chapters')data=fixture.chapters;
    else if(p.includes('/sections/'))data=fixture.section;
    else if(p.endsWith('/file'))return route.fulfill({contentType:'application/pdf',body:fs.readFileSync(path.join(out,'reader.pdf'))});
    else if(p==='/api/course/reading-map')data={chapters:[],by_id:{}};
    else if(p==='/api/chat/tasks/pending')data={pending:null};
    else if(p.includes('session-plan'))data={session_plan:null};
    else if(p.endsWith('/conversation'))data=acknowledgements.length?[{id:1,role:'assistant',content:'已请求打开教材阅读版第2页，页面到达后再确认。',reader_actions:[fixture.action]}]:[];
    else if(p.endsWith('/history')||p.includes('/history?'))data=[];
    else if(p.includes('preferences'))data={};
    else if(p.endsWith('/reader-receipt')){data=JSON.parse(request.postData());acknowledgements.push(data);}
    else if(p==='/api/chat/stream'){
     const body=JSON.parse(request.postData()),action={...fixture.action,session_id:body.session_id};
     const result={task_id:action.task_id,task_revision:3,answer_status:'answered',reply:'已请求打开教材阅读版第2页，页面到达后再确认。',reader_actions:[action],pdf_references:[],textbook_sources:[]};
     return route.fulfill({contentType:'text/event-stream',body:'event: reader_action\ndata: '+JSON.stringify({...action,task_revision:3})+'\n\nevent: done\ndata: '+JSON.stringify(result)+'\n\n'});
    }
    return route.fulfill({json:data});
   }
   const target=p==='/'?path.join(root,'frontend/index.html'):path.join(root,'frontend',decodeURIComponent(p.replace(/^\/static\//,'')));
   if(!target.startsWith(path.join(root,'frontend'))||!fs.existsSync(target))return route.fulfill({status:404,body:''});
   const ext=path.extname(target),types={'.js':'text/javascript','.mjs':'text/javascript','.css':'text/css','.html':'text/html','.svg':'image/svg+xml'};
   return route.fulfill({contentType:types[ext]||'application/octet-stream',body:fs.readFileSync(target)});
  });
  await page.goto('http://127.0.0.1:8037/');
  await page.waitForFunction(()=>typeof state!=='undefined'&&!state.taskRecoveryNeeded&&actualReaderPosition?.page===1,null,{timeout:30000});
  await page.locator('#chat-input').fill('带我到教材第2页');await page.locator('#chat-form button[type=submit]').click();
  await page.waitForFunction(()=>!state.sending,null,{timeout:25000});
  assert.equal(acknowledgements.length,1,JSON.stringify({errors,requests,acknowledgements}));
  assert.equal(acknowledgements[0].status,'applied',JSON.stringify(acknowledgements));
  assert.equal(acknowledgements[0].page,2);
  const position=await page.evaluate(()=>actualReaderPosition);assert.equal(position.page,2);
  await page.screenshot({path:path.join(out,'reader-goto.png'),fullPage:true});
  await page.reload();await page.waitForFunction(()=>!state.taskRecoveryNeeded);
  assert.equal(acknowledgements.length,1,'刷新不能重放自动跳页');
  assert.deepEqual(errors,[]);
  const report={kind:'isolated_browser_real_pdfjs_mock_api',position,acknowledgements,errors,requests};
  fs.writeFileSync(path.join(out,'report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify({status:'passed',page:position.page,receipts:acknowledgements.length}));
 }catch(e){await page.screenshot({path:path.join(out,'failed.png'),fullPage:true});console.error(JSON.stringify({errors,requests,acknowledgements}));throw e;}
 finally{await browser.close();}
})();
