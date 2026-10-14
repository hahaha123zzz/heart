/* 真实教材步骤与Cytoscape；模型回复为替身，数据库隔离。 */
const {chromium}=require('playwright'),{spawn}=require('node:child_process'),assert=require('node:assert/strict');
const ROOT=process.env.TASK_TEST_ROOT||'E:/项目/heart/project/integration/discrete-math-tutor';
(async()=>{
 const child=spawn(ROOT+'/.venv-gpu/Scripts/python.exe',['-X','utf8','-u',ROOT+'/scripts/serve_visualization_acceptance.py'],{cwd:ROOT,windowsHide:true,stdio:['ignore','pipe','pipe']});
 let browser,BASE_URL,stderr='';child.stderr.on('data',b=>stderr+=b.toString());
 try{
  BASE_URL=await new Promise((resolve,reject)=>{let output='';const timer=setTimeout(()=>reject(new Error(stderr)),30000);child.stdout.on('data',b=>{output+=b.toString();for(const line of output.split('\n'))try{const value=JSON.parse(line);if(value.url){clearTimeout(timer);resolve(value.url);}}catch{}});child.on('exit',()=>reject(new Error(stderr)));});
  browser=await chromium.launch({headless:false,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
  const context=await browser.newContext({viewport:{width:1440,height:1000}});
  const guide=await(await context.request.get(BASE_URL+'/__test__/guide')).json();let history=[];
  await context.route('**/api/**',async route=>{
   const pathname=new URL(route.request().url()).pathname;
   if(pathname==='/api/chat/stream'){
    const body=route.request().postDataJSON();assert.equal(body.visualization_target,undefined);assert.equal(body.relation_target,undefined);
    const result=body.message.includes('例9.8')?{reply:'依据教材讲解这个例子。',answer_status:'answered',guided_visualization:guide}:{reply:'你好。',answer_status:'answered'};
    await route.fulfill({body:'event: done\ndata: '+JSON.stringify(result)+'\n\n',contentType:'text/event-stream'});return;
   }
   if(pathname.startsWith('/api/relations')||pathname.startsWith('/api/visualizations')||pathname.startsWith('/api/truth-tables')){await route.continue();return;}
   let value={};
   if(pathname==='/api/course/chapters')value=[{id:9,title:'关系',sections:[{id:5,title:'9.1.4 关系特性闭包'}]}];
   else if(pathname.includes('/sections/'))value={title:'9.1.4 关系特性闭包',content:'定义9.6',blocks:[]};
   else if(pathname.endsWith('/conversation'))value=history;
   else if(pathname.endsWith('/dashboard'))value={activity:[],chapter_scores:[],chapters:[]};
   else if(pathname.endsWith('/pending'))value={pending:null};
   await route.fulfill({json:value});
  });
  const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));await page.goto(BASE_URL);await page.waitForLoadState('networkidle');
  assert.equal(await page.locator('#open-euler-graph,#open-truth-table,#open-relation,#truth-table-template,#relation-template').count(),0);
  assert.equal(await page.locator('.guided-visualization').count(),0);
  await page.locator('#chat-input').fill('请讲解例9.8 R2的传递闭包');await page.locator('#chat-form').evaluate(form=>form.requestSubmit());
  const card=page.locator('.guided-visualization');await card.waitFor();
  assert.equal(await card.locator('input,select,textarea').count(),0);
  assert.equal(await card.locator('footer button').count(),2);
  const cy=await card.locator('.guided-canvas').evaluate(el=>({locked:el._cyreg.cy.autoungrabify(),zoom:el._cyreg.cy.userZoomingEnabled(),pan:el._cyreg.cy.userPanningEnabled(),labels:el._cyreg.cy.nodes().map(n=>n.data('label'))}));
  assert.deepEqual(cy,{locked:true,zoom:false,pan:false,labels:['1','2','3']});
  await card.locator('[data-guide-next]').click();assert.equal(await card.getAttribute('data-step'),'1');
  await page.evaluate(()=>{renderChat();renderChat();});assert.equal(await card.getAttribute('data-step'),'1');
  for(let step=1;step<guide.frames.length-1;step++)await card.locator('[data-guide-next]').click();
  assert.match(await card.locator('[data-guide-text]').textContent(),/新增 2 条边/);
  await card.locator('[data-guide-next]').click();assert.equal(await card.getAttribute('data-step'),'0');
  await page.locator('#chat-input').fill('你好');await page.locator('#chat-form').evaluate(form=>form.requestSubmit());await page.waitForFunction(()=>!state.sending);
  assert.equal(await page.locator('.guided-visualization').count(),1);
  history=[{id:101,role:'assistant',content:'教材例题讲解。',selection_ref:{guided_visualization:guide}}];
  await page.reload();await card.waitFor();assert.match(await card.locator('[data-guide-title]').textContent(),/例9.8/);
  const scope=await page.evaluate(()=>({student_id:studentId,session_id:tabSessionId}));
  const artifact=await(await context.request.post(BASE_URL+'/api/relations',{data:{...scope,request_id:'old-history',expected_epoch:0,template_id:'r3',mode:'explore'}})).json();
  history.push({id:artifact.conversation_id,role:'assistant',content:'历史关系示例。'});
  await page.reload();await page.waitForFunction(()=>document.querySelectorAll('.guided-visualization').length===2);
  assert.equal(await page.locator('.interactive-relation input,.interactive-relation select,[data-relation-toggle]').count(),0);
  assert.deepEqual(errors,[]);
  await page.locator('.guided-visualization').first().screenshot({path:ROOT+'/artifacts/guided-teaching.png'});
  console.log('PASS：无预制工具栏；教材场景随回答显示；只读图与下一步；普通问候不增加卡片；重绘及历史恢复；旧组件只读化');
 }finally{await browser?.close();if(BASE_URL)await fetch(BASE_URL+'/__test__/shutdown',{method:'POST'}).catch(()=>{});if(child.exitCode===null)await new Promise(resolve=>{const timer=setTimeout(()=>{child.kill();resolve();},5000);child.once('exit',()=>{clearTimeout(timer);resolve();});});}
})().catch(e=>{console.error(e);process.exitCode=1;});
