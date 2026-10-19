const {chromium}=require('playwright');
const fs=require('fs'),assert=require('assert/strict');
const ROOT=process.env.TASK_TEST_ROOT||'E:/项目/heart/project/integration/discrete-math-tutor';
const BASE=process.env.PRESET_TEST_URL||'http://127.0.0.1:8000';
const PREFIX=process.env.PRESET_ARTIFACT_PREFIX||'psychology-preset';
const cases=JSON.parse(fs.readFileSync(process.env.PRESET_CASES_FILE||ROOT+'/artifacts/psychology-preset-acceptance.json','utf8'));
(async()=>{
 const browser=await chromium.launch({headless:false,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 const report={method:'真实原页面、合成回答与已校验预制包；未调用外部模型',cases:[]};
 try{
  const page=await browser.newPage({viewport:{width:1500,height:1060}}),errors=[];
  page.on('pageerror',e=>{errors.push(e.stack);console.log('PAGEERROR',e.stack);});
  await page.goto(BASE);await page.locator('#chapter-content canvas').first().waitFor({timeout:30000});await page.evaluate(()=>{const navigate=openGuideSource;openGuideSource=(...args)=>(window.presetNavigation=navigate(...args));});
  for(const width of [1500,390]){
   await page.setViewportSize({width,height:1060});
   for(let n=0;n<cases.length;n++){
    const guide=cases[n].guide;
    await page.evaluate(({guide,n,width})=>{state.chat=messagesFromHistory([{id:'preset-'+n+'-'+width,role:'assistant',content:'以下是依据教材的辅助示意。',selection_ref:{guided_visualization:guide}}]);renderChat();showView('chat');},{guide,n,width});
    const root=page.locator('.guided-visualization').first();await root.waitFor();
    const visual=root.locator(guide.frames[0].comparison?'.guided-comparison':'.psychology-figure');
    const pictures=[];let firstMarkup='';
    for(let step=0;step<guide.frames.length;step++){
     assert.equal(await root.getAttribute('data-step-id'),guide.frames[step].step_id);
     const canvas=visual;await canvas.scrollIntoViewIfNeeded();
     pictures.push(await canvas.screenshot());if(step===0)firstMarkup=await canvas.innerHTML();
     const expected=guide.frames[step].comparison;
     if(expected){
     assert.equal(await canvas.locator(':scope > section').count(),expected.panels.length);
     assert.equal(await canvas.locator('.comparison-field.warning').count(),expected.panels.flatMap(p=>p.items).filter(i=>i.tone==='warning').length);
     assert.equal(await canvas.locator('.comparison-field.focus').count(),expected.panels.flatMap(p=>p.items).filter(i=>i.tone==='focus').length);
     }else if(guide.frames[step].signal){
      const signal=guide.frames[step].signal;assert.equal(await canvas.getAttribute('data-phase'),String(signal.phase));
      assert.equal(await canvas.locator('.signal-outcomes').count(),signal.phase>=2?1:0);
      assert.equal(await canvas.locator('.psychology-roc').count(),signal.phase>=4?1:0);
      if(signal.phase>=2)assert((await canvas.locator('.signal-outcomes').innerText()).includes((signal.rates.hit*100).toFixed(1)+'%'));
     }else{
      const phase=guide.frames[step].spatial.phase;assert.equal(await canvas.getAttribute('data-phase'),phase);
      const positions=await canvas.locator('[data-target-position]').evaluateAll(els=>els.map(e=>e.dataset.targetPosition));
      assert.deepEqual(positions,phase==='valid'?['left']:phase==='invalid'?['right']:phase==='compare'?['left','right']:[]);
     }
     assert.equal(await root.locator('input,select,textarea').count(),0);
     assert.equal(await root.locator('button').count(),3);
     if(step<guide.frames.length-1)await root.locator('[data-guide-next]').click();
    }
    for(let i=1;i<pictures.length;i++)assert(!pictures[i].equals(pictures[i-1]),'翻步后画面未改变');
    await page.screenshot({path:ROOT+'/artifacts/'+PREFIX+'-'+n+'-'+width+'.png',fullPage:true});
    for(let step=guide.frames.length-2;step>=0;step--){await root.locator('[data-guide-prev]').click();assert.equal(await root.getAttribute('data-step-id'),guide.frames[step].step_id);}
    assert.equal(await root.locator('[data-guide-prev]').isDisabled(),true);
    assert.equal(await visual.innerHTML(),firstMarkup,'回到首步状态不一致');
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),'页面横向溢出');
    assert(await visual.evaluate(el=>el.scrollWidth<=el.clientWidth),'对照画面横向溢出');
    for(let step=0;step<guide.frames.length;step++){
     const ref=guide.frames[step].selection_ref;
     await root.locator('[data-guide-source]').click();await page.evaluate(()=>window.presetNavigation);
     await page.waitForFunction(({documentId,pageNumber})=>[...document.querySelectorAll('#chapter-content .Highlight__part')].some(el=>el.closest('[data-document]')?.dataset.document===documentId&&Number(el.closest('.page')?.dataset.pageNumber)===pageNumber),{documentId:ref.document_id,pageNumber:ref.rects[0].page},{timeout:20000});
     if(step<guide.frames.length-1){await page.evaluate(()=>showView('chat'));await root.locator('[data-guide-next]').click();}
    }
    report.cases.push({preset:guide.generation.preset_id,width,steps:guide.frames.length,visual_changes:'passed',reverse:'passed',source_highlights:'passed',history_replay:'passed',no_parameter_controls:'passed'});
   }
  }
  assert.deepEqual(errors,[]);report.page_errors=errors;
  fs.writeFileSync(ROOT+'/artifacts/'+PREFIX+'-browser-acceptance.json',JSON.stringify(report,null,2));
  console.log('PASS: 预制卡片桌面/窄屏、所有步骤画面变化、回退、历史回放与逐步教材高亮');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
