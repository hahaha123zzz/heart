const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
const BASE=process.env.PSYCHOLOGY_ORIGINAL_URL||'http://127.0.0.1:8002';
const cases=JSON.parse(fs.readFileSync(process.env.PSYCHOLOGY_GUIDES_FILE||'artifacts/psychology-visualization-acceptance.json','utf8'));
(async()=>{
 const browser=await chromium.launch({headless:false,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 try{
  const page=await browser.newPage({viewport:{width:1500,height:1060}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(BASE);await page.locator('#chapter-content canvas').first().waitFor({timeout:30000});
  for(let number=0;number<cases.length;number++){
   const guide=cases[number].guide;
   await page.evaluate(({guide,number})=>{state.chat=[{renderKey:'psy-guide-'+number,role:'assistant',content:'下面结合教材分步讲解。',guide}];renderChat();showView('chat');},{guide,number});
   const root=page.locator('.guided-visualization').first();await root.waitFor();assert.equal(await root.getAttribute('data-step'),'0');
   if(guide.frames[0].table){
    assert.equal(await root.locator('tbody tr.active').innerText(),guide.frames[0].table.rows[0].join('\t'));
    await root.locator('[data-guide-next]').click();assert.equal(await root.getAttribute('data-step'),'1');
    assert.equal(await root.locator('tbody tr.active').innerText(),guide.frames[1].table.rows[1].join('\t'));
    assert((await root.locator('.focus-cell').count())>0);
   }else{
    await root.locator('.guided-canvas canvas').first().waitFor();await root.scrollIntoViewIfNeeded();
    const before=await root.locator('.guided-canvas').screenshot();await root.locator('[data-guide-next]').click();
    assert.equal(await root.getAttribute('data-step'),'1');const after=await root.locator('.guided-canvas').screenshot();assert(!before.equals(after),'翻步后图形高亮没有改变');
   }
   await root.locator('[data-guide-prev]').click();assert.equal(await root.getAttribute('data-step'),'0');
   assert.equal(await root.locator('input,select,textarea').count(),0);
   const pageNumber=guide.frames[0].selection_ref.rects[0].page;
   await root.locator('[data-guide-source]').click();await page.locator('#chapter-content .Highlight__part').first().waitFor({timeout:20000});
   assert.equal(await page.locator('#chapter-content .Highlight__part').first().evaluate(e=>Number(e.closest('.page').dataset.pageNumber)),pageNumber);
  }
  await page.screenshot({path:'artifacts/psychology-guided-visualization.png'});
  assert.deepEqual(errors,[]);console.log('PASS: 真实生成图解在原对话中展示、翻步改变节点/矩阵高亮、无需参数编辑、来源跳转高亮');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
