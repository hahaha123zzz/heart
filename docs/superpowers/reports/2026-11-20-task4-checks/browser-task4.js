const {chromium,expect}=require('playwright/test');
const fs=require('node:fs');
const base=process.env.HEART_BROWSER_URL;
const reading=Object.values(JSON.parse(process.env.HEART_BROWSER_READING))[0];
const fixture=Object.values(JSON.parse(process.env.HEART_BROWSER_FIXTURES))[0];
const quote=process.env.HEART_BROWSER_QUOTE;
const report={checks:[],failures:[],pageErrors:[],turns:[],geometry:[]};
const fast={timeout:90000};
let page,context;
async function check(label,fn){try{await fn();report.checks.push(label);console.log('PASS '+label);}catch(error){report.failures.push({label,error:String(error.stack||error),body:(await page.locator('body').innerText()).slice(-6000)});console.log('FAIL '+label+' '+error.message);process.exitCode=1;}finally{fs.writeFileSync(process.env.HEART_BROWSER_REPORT,JSON.stringify(report,null,2));}}
async function ready(){await expect(page.locator('[data-reader-unit="1"] .textLayer span').first()).toBeAttached(fast);}
async function select(cross=false){
  await ready();
  return await page.evaluate(({cross})=>{
    const first=document.querySelector('[data-reader-unit="1"] .textLayer');
    const second=document.querySelector('[data-reader-unit="2"] .textLayer');
    const starts=[...first.querySelectorAll('span')].filter(s=>/[\u4e00-\u9fff]/.test(s.textContent));
    const ends=cross?[...second.querySelectorAll('span')].filter(s=>/[\u4e00-\u9fff]/.test(s.textContent)):starts;
    const a=cross?starts[starts.length-2]:starts[1];const b=cross?ends[1]:starts[2];
    const range=document.createRange();range.setStart(a.firstChild,0);range.setEnd(b.firstChild,b.textContent.length);
    const selection=window.getSelection();selection.removeAllRanges();selection.addRange(range);
    const rects=[...range.getClientRects()].map(r=>({x:r.x,y:r.y,width:r.width,height:r.height}));
    first.dispatchEvent(new MouseEvent('mouseup',{bubbles:true}));
    return {text:selection.toString(),rects};
  },{cross});
}
async function ask(cross=false){await select(cross);await page.getByRole('button',{name:/^(Ask about this|向助教提问|就此提问|询问此内容)$/}).click();await expect(page.getByRole('button',{name:/^(Remove quoted passage|移除引用段落|删除引用段落|移除引用的段落)$/})).toBeVisible(fast);}
async function openMaterial(id){const response=await context.request.put(`${base}/api/reading/workspaces/${reading.workspace_id}/materials/${id}/active`);expect(response.ok()).toBe(true);await page.goto(base+'/learning/reading/'+reading.workspace_id);await ready();}
(async()=>{
 const browser=await chromium.launch({headless:false});context=await browser.newContext({locale:'zh-CN',viewport:{width:1440,height:1000}});page=await context.newPage();page.setDefaultNavigationTimeout(150000);
 page.on('pageerror',error=>report.pageErrors.push(error.message));
 page.on('websocket',socket=>socket.on('framesent',frame=>{try{const text=frame.payload.toString();if(text.includes('reading_viewport'))report.turns.push(JSON.parse(text));}catch{}}));
 try{
  await page.goto(base+'/settings/model');await page.locator('#username').fill(Object.keys(JSON.parse(process.env.HEART_BROWSER_READING))[0]);await page.locator('#password').fill(JSON.parse(process.env.HEART_BROWSER_PASSWORDS)[0]);await page.locator('button[type=submit]').click();await expect(page).toHaveURL(/\/settings\/model/,fast);
  await page.getByLabel(/Base URL/).fill('https://1.1.1.1/v1');await page.getByLabel('模型名称').fill('review-alpha');await page.getByLabel('API Key').fill('local-alpha-fixture');await page.getByRole('button',{name:'保存',exact:true}).click();await expect(page.getByText(/已保存，后续对话/)).toBeVisible(fast);
  await check('native document identity, immutable version and non-identity page map',async()=>{
   const info=await(await context.request.get(base+'/api/reading/materials/'+reading.active_material_id)).json();
   expect(info.document_id).toBe(reading.materials[0].document_id);expect(info.version).toBe(reading.materials[0].version);expect(info.page_map['1']).toBe(1);
   const geometry=await(await context.request.get(base+'/api/reading/materials/'+fixture)).json();expect(geometry.page_map).toEqual({'1':7,'2':11,'3':13,'4':17});report.identity={document_id:info.document_id,version:info.version,page_map:geometry.page_map};
  });
  await openMaterial(reading.active_material_id);
  await check('Chinese selection, edge-clamped menu, Escape cancellation and removing a pending quote',async()=>{
   const selected=await select();expect(selected.text).toMatch(/[\u4e00-\u9fff]/);
   const pop=page.getByRole('dialog',{name:/Annotate selection|批注选区|标注选区|标注所选内容/});await expect(pop).toBeVisible(fast);const box=await pop.boundingBox();expect(box.x).toBeGreaterThanOrEqual(0);expect(box.x+box.width).toBeLessThanOrEqual(1441);
   await page.keyboard.press('Escape');await expect(pop).toBeHidden();
   await ask();await page.getByRole('button',{name:/^(Remove quoted passage|移除引用段落|删除引用段落|移除引用的段落)$/}).click();await expect(page.getByRole('button',{name:/^(Remove quoted passage|移除引用段落|删除引用段落|移除引用的段落)$/})).toHaveCount(0);
   expect(report.turns.length).toBe(0);
  });
  await check('cross-page selection asks through the original composer and returns a verified region citation',async()=>{
   await expect(page.locator('[data-reader-unit="2"] .textLayer span').first()).toBeAttached(fast);
   await ask(true);
   const composer=page.locator('textarea:visible,[contenteditable=true]:visible').last();await composer.fill('请解释我选中的跨页内容，并给出一个明确标注的补充例子。');await composer.press('Enter');
   await expect(page.getByText('补充解释（非教材结论）：这是帮助理解的生活例子，不计入教材掌握。',{exact:false}).first()).toBeVisible(fast);
   const citation=page.locator('a[href^="#dt-material-"][href*="?quote="]').first();await expect(citation).toBeVisible(fast);const href=await citation.getAttribute('href');expect(href).toContain('-revision-1-locator-1');expect(decodeURIComponent(href)).toContain(quote);await citation.click();await expect(page.locator('[data-reader-unit="1"] .dt-reader-flash').first()).toBeVisible(fast);
   const serialized=JSON.stringify(report.turns);expect(serialized).toContain('selection_pages');expect(serialized).toContain('"locator":2');report.citation=href;
   await page.reload();await ready();await expect(page.locator('a[href^="#dt-material-"][href*="?quote="]').first()).toBeVisible(fast);
  });
  await check('rotation and crop-box geometry stay normalized, with browser zoom and position restoration',async()=>{
   await openMaterial(fixture);await page.getByRole('button',{name:/^(Collapse contents|收起目录)$/}).click().catch(()=>{});
   for(const locator of [1,2,3,4]){
    const unit=page.locator(`[data-reader-unit="${locator}"]`);await unit.scrollIntoViewIfNeeded();await expect(unit.locator('.textLayer span').first()).toBeAttached(fast);
    const result=await unit.evaluate(element=>{const layer=element.querySelector('.textLayer');const span=[...layer.querySelectorAll('span')].find(s=>/[\u4e00-\u9fff]/.test(s.textContent));const range=document.createRange();range.selectNodeContents(span);const box=element.getBoundingClientRect();return {width:box.width,height:box.height,rects:[...range.getClientRects()].map(r=>[(r.left-box.left)/box.width,(r.top-box.top)/box.height,(r.right-box.left)/box.width,(r.bottom-box.top)/box.height])};});
    expect(result.rects.length).toBeGreaterThan(0);for(const rect of result.rects)for(const coordinate of rect)expect(coordinate).toBeGreaterThanOrEqual(-0.02);for(const rect of result.rects)for(const coordinate of rect)expect(coordinate).toBeLessThanOrEqual(1.02);report.geometry.push({rotation:(locator-1)*90,...result});
   }
   const client=await context.newCDPSession(page);await client.send('Emulation.setPageScaleFactor',{pageScaleFactor:1.25});await expect(page.locator('[data-reader-unit="4"] canvas')).toBeVisible();await client.send('Emulation.setPageScaleFactor',{pageScaleFactor:1});
   await page.locator('[data-reader-unit="2"]').evaluate(el=>el.scrollIntoView({block:'start'}));
   await expect.poll(async()=>{const result=await context.request.get(base+'/api/reading/materials/'+fixture+'/position');return (await result.json()).locator;},{timeout:20000}).toBe(2);
   await page.reload();await expect(page.locator('[data-reader-unit="2"] canvas')).toBeVisible(fast);
  });
  await check('material switching invalidates the pending quote and outdated revision links fail explicitly',async()=>{
   await openMaterial(reading.active_material_id);await ask();await openMaterial(fixture);await expect(page.getByRole('button',{name:/Remove quoted passage|移除引用段落|删除引用段落|移除引用的段落/})).toHaveCount(0);
   await page.evaluate(id=>{const a=document.createElement('a');a.href='#dt-material-'+id+'-revision-999-locator-1';a.textContent='stale citation';document.body.append(a);a.click();},fixture);
   await expect(page.getByText(/older material revision|旧.*版本/).first()).toBeVisible(fast);
  });

  await check('read aloud uses verified material text and can stop browser speech fallback',async()=>{
   await openMaterial(reading.active_material_id);
   await page.route('**/api/reading/materials/*/read-aloud',route=>route.fulfill({status:503,contentType:'application/json',body:'{"detail":"fixture: platform speech not configured"}'}));
   await page.evaluate(()=>{window.__task4Speech=[];Object.defineProperty(window.speechSynthesis,'speak',{configurable:true,value:utterance=>window.__task4Speech.push(utterance.text)});});
   await page.getByRole('button',{name:/^(Read this page aloud|Read aloud|朗读|朗读本页|朗读此页)$/}).click();
   await expect.poll(()=>page.evaluate(()=>window.__task4Speech.length),{timeout:30000}).toBeGreaterThan(0);
   expect(await page.evaluate(()=>window.__task4Speech[0])).toMatch(/[\u4e00-\u9fff]/);
   await page.getByRole('button',{name:/^(Stop reading aloud|停止朗读)$/}).click();
   await expect(page.getByRole('button',{name:/^(Read this page aloud|Read aloud|朗读|朗读本页|朗读此页)$/})).toBeVisible();
   report.speech='verified backend unit plus browser speech boundary fixture; physical audio not checked';
  });
  await check('contents search, 390px selection sheet and keyboard close',async()=>{
   await openMaterial(reading.active_material_id);await page.setViewportSize({width:390,height:844});
   const expand=page.getByRole('button',{name:/^(Expand contents|展开目录)$/});if(await expand.isVisible())await expand.click();
   const search=page.getByPlaceholder(/Search materials and contents|搜索资料和目录|搜索资料与目录/);await expect(search).toBeVisible(fast);await search.fill('chapter_01');await search.fill('');
   const close=page.getByRole('button',{name:/^(Close contents|关闭目录)$/});if(await close.isVisible())await close.click();
   await select();const pop=page.getByRole('dialog',{name:/Annotate selection|批注选区|标注选区|标注所选内容/});await expect(pop).toBeVisible(fast);const box=await pop.boundingBox();expect(box.x).toBeGreaterThanOrEqual(0);expect(box.x+box.width).toBeLessThanOrEqual(391);await page.keyboard.press('Escape');await expect(pop).toBeHidden();expect(report.pageErrors).toEqual([]);
  });
 }catch(error){report.error=String(error.stack||error);process.exitCode=1;}finally{fs.writeFileSync(process.env.HEART_BROWSER_REPORT,JSON.stringify(report,null,2));console.log(JSON.stringify({checks:report.checks,failures:report.failures.map(x=>({label:x.label,error:x.error})),error:report.error,pageErrors:report.pageErrors}));await browser.close();}
})();
