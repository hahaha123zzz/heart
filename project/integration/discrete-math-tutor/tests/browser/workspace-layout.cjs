/* 在隔离数据库、已登记 workspace-ui 历史会话的服务上运行。模型回复使用 SSE 夹具。 */
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const BASE = process.env.BASE_URL || 'http://127.0.0.1:8066';
const OUT = '.runtime/workspace-layout';

(async () => {
  fs.mkdirSync(OUT, {recursive:true});
  const browser = await chromium.launch({headless:true});
  const results = [], errors = [];
  const check = async (name, action) => {await action();results.push(name);};
  try {
    const context = await browser.newContext({viewport:{width:1440,height:960}});
    await context.addInitScript(() => localStorage.setItem('experimental-psychology-3-demo-student','workspace-ui'));
    const page = await context.newPage();
    page.on('pageerror', error => errors.push(error.message));
    let pdfRequests = 0, sends = 0;
    page.on('request',request=>{if(/\/api\/.*pdf|\.pdf(?:\?|$)/.test(request.url()))pdfRequests++;});
    await page.route('**/api/chat/stream',async route=>{
      sends++;
      if(sends===2)return route.fulfill({status:422,contentType:'application/json',body:JSON.stringify({detail:'测试发送失败'})});
      const result={answer_status:'answered',reply:'这是浏览器交互测试回复。',textbook_sources:[],pdf_references:[]};
      await route.fulfill({contentType:'text/event-stream',body:'event: done\ndata: '+JSON.stringify(result)+'\n\n'});
    });
    const ready = async () => page.waitForFunction(()=>!state.initializing&&!state.taskRecoveryNeeded);
    await page.goto(BASE);await ready();
    await check('默认收起、单一学习入口、无搜索入口',async()=>{
      assert.equal(await page.locator('#reader-toggle').getAttribute('aria-expanded'),'false');
      assert.equal(await page.locator('#primary-nav [data-view=home]').count(),0);
      assert.equal(await page.locator('#search-form').count(),0);
      assert.equal(await page.locator('#main-content').isVisible(),false);
      assert.equal(pdfRequests,0);
    });
    await check('建议填入草稿、不自动发送、上下位置共用',async()=>{
      await page.click('[data-study-prompt=plan]');
      assert.match(await page.inputValue('#chat-input'),/目标、重点和步骤/);
      assert.equal(sends,0);
      assert.equal(await page.evaluate(()=>document.querySelector('#chat-form').nextElementSibling.id),'learning-suggestions');
      await page.click('#reader-toggle');
      assert.equal(await page.evaluate(()=>document.querySelector('#chat-form').previousElementSibling.id),'learning-suggestions');
      await page.waitForSelector('.pdf-surface .page');
    });
    await check('教材反复收起展开不重载，保留 Canvas、页码和缩放',async()=>{
      await page.fill('input[aria-label="PDF 页码"]','3');
      await page.locator('input[aria-label="PDF 页码"]').press('Enter');
      await page.selectOption('select[aria-label="PDF 缩放"]','1.25');
      await page.waitForTimeout(800);
      await page.evaluate(()=>window.layoutCanvas=document.querySelector('.pdf-surface canvas'));
      const before=pdfRequests;
      for(let index=0;index<10;index++){
        await page.click('#reader-toggle');await page.click('#reader-toggle');
      }
      await page.waitForTimeout(700);
      assert.equal(pdfRequests,before);
      assert.equal(await page.evaluate(()=>window.layoutCanvas===document.querySelector('.pdf-surface canvas')),true);
      assert.equal(await page.inputValue('input[aria-label="PDF 页码"]'),'3');
      assert.equal(await page.inputValue('select[aria-label="PDF 缩放"]'),'1.25');
      await page.click('[data-directory-toggle]');
      assert.equal(await page.locator('#course-tree').isVisible(),true);
      await page.keyboard.press('Escape');
      assert.equal(await page.locator('#course-tree').isVisible(),false);
      await page.screenshot({path:OUT+'/desktop-open.png'});
    });
    await check('关闭建议跨展开状态、刷新及新会话保持隐藏',async()=>{
      await page.click('#dismiss-suggestions');await page.click('#reader-toggle');
      assert.equal(await page.locator('#learning-suggestions').isVisible(),false);
      await page.reload();await ready();
      assert.equal(await page.locator('#learning-suggestions').isVisible(),false);
      await page.click('#new-chat');
      page.once('dialog',dialog=>dialog.accept());
      assert.equal(await page.locator('#learning-suggestions').isVisible(),false);
    });
    await check('真实历史会话切换、身份与刷新恢复',async()=>{
      await page.click('[data-session-id="layout-history-a"]');
      await page.waitForFunction(()=>!state.switchingConversation&&state.chat.length===2);
      assert.match(await page.locator('#chat-messages').innerText(),/什么是自变量/);
      assert.equal(await page.evaluate(()=>tabSessionId),'layout-history-a');
      await page.reload();await ready();
      assert.match(await page.locator('#chat-messages').innerText(),/什么是自变量/);
      await page.click('[data-session-id="layout-history-b"]');
      await page.waitForFunction(()=>!state.switchingConversation&&tabSessionId==='layout-history-b');
      assert.match(await page.locator('#chat-messages').innerText(),/今天学习实验设计/);
    });
    await check('显式打开同一历史会话不会被跨标签重新编号',async()=>{
      const second=await context.newPage();await second.goto(BASE);
      await second.waitForFunction(()=>!state.initializing);
      await second.click('[data-session-id="layout-history-b"]');
      await second.waitForFunction(()=>!state.switchingConversation&&tabSessionId==='layout-history-b');
      await page.waitForTimeout(220);
      assert.equal(await page.evaluate(()=>tabSessionId),'layout-history-b');
      await second.close();
    });
    await check('教材收起时点击上标来源可展开并定位（来源状态夹具）',async()=>{
      await page.route('**/api/course/citation-state',route=>route.fulfill({json:{stale:false}}));
      await page.evaluate(()=>{
        Workspace.setReaderOpen(false);
        const pdf=state.sectionData.pdf;
        state.chat.push({role:'assistant',content:'引用跳转测试[1]',sources:['当前教材'],pdfReferences:[{
          source_index:0,evidence:{location_status:'page'},selection_ref:{
            document_id:pdf.document_id,version:pdf.version,chapter_id:state.chapter,
            section_id:state.section,page:3,rects:[],location_kind:'page',
          },
        }]});renderChat();
      });
      await page.locator('[data-tutor-citation="1"]').last().click();
      await page.click('[data-source-citation]');
      await page.waitForFunction(()=>document.body.classList.contains('reader-open')&&state.pdfFocus?.page===3);
      await page.waitForFunction(()=>document.querySelector('input[aria-label="PDF 页码"]')?.value==='3');
      await page.unroute('**/api/course/citation-state');
      await page.locator('[data-close-citation]').click();
    });
    await check('生成中阻止切换、首次发送隐藏建议、失败不重新显示',async()=>{
      await page.click('#new-chat');
      await page.evaluate(()=>{sessionStorage.removeItem('experimental-psychology-3:workspace:workspace-ui:suggestions-dismissed');});
      await page.reload();await ready();
      assert.equal(await page.locator('#learning-suggestions').isVisible(),true);
      await page.fill('#chat-input','测试学习建议收起');await page.click('#chat-form [type=submit]');
      await page.waitForFunction(()=>!state.sending);
      assert.equal(sends,1);
      assert.equal(await page.locator('#learning-suggestions').isVisible(),false);
      await page.evaluate(()=>state.sending=true);
      await page.click('[data-session-id="layout-history-a"]');
      assert.notEqual(await page.evaluate(()=>tabSessionId),'layout-history-a');
      await page.evaluate(()=>state.sending=false);
      await page.fill('#chat-input','测试失败保留');await page.click('#chat-form [type=submit]');
      await page.waitForFunction(()=>!state.sending);
      assert.equal(sends,2);
      assert.equal(await page.locator('#learning-suggestions').isVisible(),false);
    });
    await check('375px 窄屏、列表抽屉及移动教材切换',async()=>{
      await page.setViewportSize({width:375,height:812});
      await page.click('#mobile-nav-toggle');
      assert.equal(await page.locator('#conversation-sidebar').isVisible(),true);
      await page.keyboard.press('Escape');
      assert.equal(await page.locator('#conversation-sidebar').isVisible(),false);
      await page.click('[data-mobile-pane=content]');
      assert.equal(await page.locator('#main-content').isVisible(),true);
      await page.click('[data-mobile-pane=chat]');
      assert.equal(await page.locator('#chat-panel').isVisible(),true);
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
      await page.screenshot({path:OUT+'/mobile.png'});
    });
    await check('新标签空白会话可重新显示建议',async()=>{
      const fresh=await context.newPage();await fresh.goto(BASE);
      await fresh.waitForFunction(()=>!state.initializing);
      assert.equal(await fresh.locator('#learning-suggestions').isVisible(),true);
      assert.equal(await fresh.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
      await fresh.screenshot({path:OUT+'/desktop-closed.png'});
      await fresh.close();
    });
    await check('设置、学习记录入口不受教材折叠影响',async()=>{
      await page.setViewportSize({width:1440,height:960});
      await page.click('[data-view=settings]');
      assert.equal(await page.locator('#settings-view').isVisible(),true);
      await page.click('[data-view=learning]');
      assert.equal(await page.locator('#learning-view').isVisible(),true);
      await page.click('#primary-nav [data-view=quiz]');
      assert.equal(await page.locator('#quiz-view').isVisible(),true);
      await page.click('#quiz-view [data-directory-toggle]');
      assert.equal(await page.locator('#practice-nav-slot').isVisible(),true);
      await page.keyboard.press('Escape');
      await page.click('#primary-nav [data-view=course]');
    });
    assert.deepEqual(errors,[]);
    fs.writeFileSync(OUT+'/browser-results.json',JSON.stringify({passed:results,errors,model:'SSE fixture; no real LLM calls'},null,2));
    console.log(JSON.stringify({passed:results,errors},null,2));
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exit(1);});
