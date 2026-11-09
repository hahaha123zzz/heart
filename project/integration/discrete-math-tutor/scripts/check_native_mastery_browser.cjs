// 实际构建产物与原生题卡组件验证；不冒充模型/后端判分验收。
const {chromium}=require('C:/Users/free/.agents/skills/playwright/node_modules/playwright');
const assert=require('node:assert/strict'),path=require('node:path'),fs=require('node:fs');
(async()=>{
 const root=path.resolve(__dirname,'../frontend');
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 try {
  const page=await browser.newPage(),errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.route('http://native-card.test/**',route=>{
   const url=new URL(route.request().url());
   if(url.pathname==='/')return route.fulfill({contentType:'text/html',body:'<meta charset="utf-8"><div id="card"></div>'});
   const file=path.resolve(root,'.'+url.pathname.replace(/^\/static/,''));
   if(!file.startsWith(root+path.sep))return route.abort();
   return route.fulfill({path:file,contentType:file.endsWith('.js')?'application/javascript; charset=utf-8':undefined});
  });
  await page.goto('http://native-card.test/');
  await page.addScriptTag({url:'http://native-card.test/static/vendor/deeptutor-renderers/viewer.js'});
  await page.evaluate(()=>{
   window.calls=[];
   window.data={mastery_events:[{type:'tool_result',metadata:{tool_metadata:{mastery_question:{
    question_id:'q1',prompt:'哪项是自变量？',question_type:'choice',objective:{id:'p1',name:'变量'},
    options:[{label:'A',body:'操纵的条件'},{label:'B',body:'测量结果'}],allow_free_text:true,attempt:1}}}}],
    onMasteryAnswer:(id,text)=>{window.calls.push({action:'answer',id,text});return false;},
    onMasterySkip:id=>{window.calls.push({action:'skip',id});return false;}};
   window.instance=TutorNativeViewer.mount(document.querySelector('#card'),window.data);
  });
  await page.getByRole('button').filter({hasText:'操纵的条件'}).click();
  const submit=page.getByRole('button',{name:/^(提交|提交答案|Submit)$/});
  await submit.click();
  await page.waitForFunction(()=>window.calls.length===1);
  assert.deepEqual(await page.evaluate(()=>window.calls[0]),{action:'answer',id:'q1',text:'A'});
  await page.getByRole('button',{name:/跳过这|跳过此|Skip this one/}).click();
  await page.waitForFunction(()=>window.calls.length===2);
  assert.deepEqual(await page.evaluate(()=>window.calls[1]),{action:'skip',id:'q1'});
  await page.evaluate(()=>{
   window.data.masteryMessages=[{events:[...window.data.mastery_events,{type:'tool_result',metadata:{tool_metadata:{
    mastery_grade:{result:{question_id:'q1',is_correct:true,learner_answer:'A',correct_label:'A',explanation:'原生判定已恢复'}}}}}]}];
   window.instance.dispose();
   window.instance=TutorNativeViewer.mount(document.querySelector('#card'),window.data);
  });
  await page.getByText('原生判定已恢复').waitFor();
  assert.equal(await submit.count(),0);
  assert.deepEqual(errors,[]);
  const run=path.resolve(__dirname,'../.runtime/native-mastery-browser',new Date().toISOString().replace(/[:.]/g,'-'));
  fs.mkdirSync(run,{recursive:true});
  await page.screenshot({path:path.join(run,'card.png')});
  fs.writeFileSync(path.join(run,'report.json'),JSON.stringify({passed:true,scope:'原生组件/回调/恢复，非模型判分',checks:['answer_callback','skip_callback','grade_restore','no_page_errors']},null,2));
  console.log(JSON.stringify({passed:true,report:path.join(run,'report.json')}));
 } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
