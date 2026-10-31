// 使用独立验收服务；NODE_PATH 可指向本机已安装的 Playwright。
const {chromium} = require('playwright');
const fs = require('node:fs/promises');
const path = require('node:path');
const assert = require('node:assert/strict');

async function main() {
  const [base, output] = process.argv.slice(2);
  if (!base || !output) throw new Error('用法：node scripts/check_input_labels_page.cjs http://127.0.0.1:隔离端口 输出目录');
  const url = new URL(base);
  assert.ok(['127.0.0.1','localhost'].includes(url.hostname) && url.port && url.port !== '8000', '仅允许独立本机验收端口');
  const out = path.resolve(output);
  await fs.mkdir(out, {recursive:true});
  const browser = await chromium.launch({headless:false});
  const context = await browser.newContext();
  const report = {base, passed:false, requests:[], turns:[], pageErrors:[]};
  await context.tracing.start({screenshots:true, snapshots:true});
  const page = await context.newPage();
  // 应用会缓存 streamChat 引用，须在 transport 脚本赋值时完成包装。
  await page.addInitScript(() => {
    window.__labelChecks = [];
    let transport;
    Object.defineProperty(window, 'TutorChatTransport', {configurable:true,
      get() { return transport; },
      set(value) {
        transport = value;
        const original = value.streamChat;
        value.streamChat = async (...args) => {
          try {
            const result = await original(...args);
            window.__labelChecks.push(result);
            return result;
          } catch (error) {
            window.__labelChecks.push({answer_status:'transport_error', error:String(error)});
            throw error;
          }
        };
      },
    });
  });
  page.on('pageerror', error => report.pageErrors.push(error.message));
  page.on('request', request => {
    if (request.method() === 'POST' && new URL(request.url()).pathname === '/api/chat/stream') {
      const body = request.postDataJSON();
      report.requests.push({request_id:body.request_id, message:body.message});
    }
  });
  try {
    await page.goto(url.href);
    // taskRecoveryNeeded 在章节、历史与待办恢复完成前为 true。
    await page.waitForFunction(() => typeof state !== 'undefined' && !state.taskRecoveryNeeded && !state.sending);
    for (const message of ['请结合教材解释实验法和观察法的区别。', '我还是分不清这两个概念']) {
      const index = report.turns.length;
      await page.waitForFunction(() => !state.sending && !state.taskRecoveryNeeded);
      await page.getByRole('textbox', {name:'向助教提问'}).fill(message);
      const posted = page.waitForRequest(request => request.method() === 'POST' &&
        new URL(request.url()).pathname === '/api/chat/stream' && request.postDataJSON().message === message, {timeout:10000});
      await page.getByRole('button', {name:'发送消息'}).click();
      const request = await posted;
      await page.waitForFunction(n => window.__labelChecks.length > n, index, {timeout:120000});
      await page.waitForFunction(() => !state.sending);
      const result = await page.evaluate(n => window.__labelChecks[n], index);
      report.turns.push({request_id:request.postDataJSON().request_id, status:result.answer_status,
        strategy:result.teaching?.last_strategy, six_dim:result.input_understanding?.six_dim,
        sources:(result.textbook_sources || []).length});
      assert.equal(result.answer_status, 'answered');
      const prefix = String(result.reply || '').replace(/[*#\[\]]/g, '').slice(0,12);
      report.turns[index].renderedPrefix = prefix;
      assert.ok(prefix.length);
      await page.waitForFunction(text => document.querySelector('#chat-messages').innerText.replace(/[*#\[\]]/g,'').includes(text), prefix);
    }
    assert.equal(report.turns[1].six_dim?.learner_state?.difficulty_locus?.value, 'discrimination');
    await page.reload();
    await page.waitForFunction(text => !state.taskRecoveryNeeded &&
      document.querySelector('#chat-messages').innerText.replace(/[*#\[\]]/g,'').includes(text), report.turns[1].renderedPrefix);
    const originalSession = await page.evaluate(() => tabSessionId);
    const other = await context.newPage();
    other.on('pageerror', error => report.pageErrors.push(error.message));
    await other.goto(url.href);
    await other.waitForFunction(() => typeof state !== 'undefined' && !state.taskRecoveryNeeded);
    report.sessionIsolation = await other.evaluate(() => ({session:tabSessionId,
      messages:state.chat.length, hasPending:!!state.clarification}));
    assert.notEqual(report.sessionIsolation.session, originalSession);
    assert.equal(report.sessionIsolation.messages, 0);
    assert.equal(report.sessionIsolation.hasPending, false);
    await other.close();
    assert.equal(report.pageErrors.length, 0);
    report.passed = true;
  } catch (error) {
    report.error = String(error.stack || error);
    report.visibleText = await page.locator('body').innerText().catch(() => 'unavailable');
    process.exitCode = 1;
  } finally {
    await page.screenshot({path:path.join(out,'page.png'), fullPage:true}).catch(() => {});
    await context.tracing.stop({path:path.join(out,'trace.zip')});
    await fs.writeFile(path.join(out,'report.json'), JSON.stringify(report,null,2));
    await browser.close();
    console.log(JSON.stringify({passed:report.passed, requests:report.requests.length, out, error:report.error}));
  }
}
main().catch(error => {console.error(error); process.exitCode=1;});
