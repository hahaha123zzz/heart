const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');

(async () => {
 const browser = await chromium.launch({headless:true});
 try {
  const page = await browser.newPage({viewport:{width:390,height:850},acceptDownloads:true});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.setContent('<main id="guide"></main>');
  for(const file of ['frontend/vendor/cytoscape/cytoscape.min.js','frontend/visualizations/drawio-export.js','frontend/visualizations/guided.js'])
   await page.addScriptTag({path:path.resolve(file)});
  for(const file of ['frontend/styles.css','frontend/workspace.css','frontend/visualizations/presets.css','frontend/visualizations/learning-skills.css'])
   await page.addStyleTag({path:path.resolve(file)});
  await page.evaluate(()=>{
   const graph={layout:'flow',directed:true,nodes:[{id:'a',label:'自变量'},{id:'b',label:'因变量'}],edges:[{id:'e',source:'a',target:'b',annotation:'拟检验影响'}]};
   const options=[{label:'改变条件',node:'a',feedback:'关注操纵条件'},{label:'观察结果',node:'b',feedback:'关注测量反应'}];
   window.fixture={id:'interactive',title:'探索变量',origin:'teaching_example',frames:['先想一想','探索','概念','挑战'].map((title,i)=>({title,text:'比较两个角色',graph,learning_skill:'interactive-educator',...(i===2?{}:{interaction:{options}})}))};
   window.component=GuidedVisualization.mount(document.querySelector('#guide'),{guide:fixture});
  });
  await page.getByRole('button',{name:'观察结果',exact:true}).click();
  assert.equal(await page.getByRole('button',{name:'观察结果',exact:true}).getAttribute('aria-pressed'),'true');
  assert.match(await page.locator('.guided-interaction').innerText(),/关注测量反应/);
  assert.equal(await page.evaluate(()=>document.querySelector('.guided-canvas')._cyreg.cy.getElementById('b').hasClass('focus')),true);
  await page.getByRole('button',{name:'下一步',exact:true}).click();
  await page.getByRole('button',{name:'上一步',exact:true}).click();
  assert.equal(await page.getByRole('button',{name:'观察结果',exact:true}).getAttribute('aria-pressed'),'true');
  await page.evaluate(()=>component.update({guide:{...fixture,id:'drawio',frames:fixture.frames.map(f=>({...f,interaction:undefined,learning_skill:'drawio'}))}}));
  const download=page.waitForEvent('download');
  await page.getByRole('button',{name:'下载可编辑关系图 (.drawio)',exact:true}).click();
  assert.equal((await download).suggestedFilename(),'教材关系图.drawio');
  const xml = await page.evaluate(()=>{
   const text=DrawioExport.serialize('图 " <script>',{nodes:[{id:'a',label:'<img src=x onerror=alert(1)>'},{id:'b',label:'因变量'}],edges:[{source:'a',target:'b',label:'条件 & 结果'}]});
   const doc=new DOMParser().parseFromString(text,'application/xml');
   return {errors:doc.querySelectorAll('parsererror').length,nodes:doc.querySelectorAll('mxCell[vertex="1"]').length,label:doc.querySelector('mxCell[vertex="1"]').getAttribute('value')};
  });
  assert.equal(xml.errors,0);assert.equal(xml.nodes,2);assert.match(xml.label,/<img/);
  await page.evaluate(()=>{component.dispose();document.querySelector('#guide').replaceChildren();component=GuidedVisualization.mount(document.querySelector('#guide'),{guide:JSON.parse(JSON.stringify(fixture))});});
  assert.equal(await page.locator('[data-guide-title]').innerText(),'探索变量');
  if(process.env.LEARNING_VISUAL_LIVE_DIR){
   const directory=process.env.LEARNING_VISUAL_LIVE_DIR;
   const generated=[...JSON.parse(fs.readFileSync(path.join(directory,'live3.json'),'utf8')),
                    ...JSON.parse(fs.readFileSync(path.join(directory,'live4.json'),'utf8'))].filter(item=>item.passed);
   assert.equal(generated.length,3);
   for(const item of generated){
    await page.evaluate(guide=>{component.update({guide});},item.guide);
    assert.equal(await page.locator('[data-guide-title]').innerText(),item.guide.title);
    const skill=item.guide.frames[0].learning_skill;
    if(skill==='interactive-educator'){
     await page.getByRole('button',{name:item.guide.frames[0].interaction.options[0].label,exact:true}).click();
     assert.equal(await page.locator('.guided-interaction p').innerText(),item.guide.frames[0].interaction.options[0].feedback);
    }
    await page.screenshot({path:path.join(directory,skill+'.png'),fullPage:true});
   }
  }
  assert.deepEqual(errors,[]);
  console.log('PASS: 情境反馈、节点关注切换、步骤返回、DrawIO下载/XML转义、序列化重挂载；无浏览器异常');
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
