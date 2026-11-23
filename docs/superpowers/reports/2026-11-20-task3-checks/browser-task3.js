const { chromium, expect } = require("playwright/test");
const fs = require("node:fs");
const base = process.env.HEART_BROWSER_URL;
const reading = JSON.parse(process.env.HEART_BROWSER_READING);
const report = { checks: [], pageErrors: [], sockets: [], socketEvents: [], consoleErrors: [], httpFailures: [] };
const restricted = new Set([
  "capabilities/registered", "dashboard/suggestions", "partner-groups", "partners",
  "settings", "settings/chat-attachments", "settings/workspace/registrations",
  "settings/workspace/resources", "subagents/connections", "subagents/settings",
  "system/update", "tools",
].map(path => "/api/" + path));
const restrictedRequests = [];
const fast = { timeout: 60000 };
async function check(label, fn) {
  try {
    await fn(); report.checks.push(label); console.log("PASS " + label);
  } catch(error) {
    (report.failures ||= []).push({label,error:String(error.stack||error)});
    console.log('FAIL '+label+' '+error.message); process.exitCode=1;
  }
}
async function logIn(page, owner, password) {
  await page.goto(base + "/settings/model");
  await expect(page).toHaveURL(/\/login/, fast);
  await page.locator("#username").fill(owner);
  await page.locator("#password").fill(password);
  await page.locator("button[type=submit]").click();
  await expect(page).toHaveURL(/\/settings\/model/, fast);
}
async function send(page, question, answer) {
  const composer = page.locator("textarea:visible,[contenteditable=true]:visible").last();
  await expect(composer).toBeEditable(fast);
  await composer.fill(question);
  await composer.press("Enter");
  await expect(page.getByText(answer, { exact: false }).first()).toBeVisible(fast);
}
(async () => {
  const browser = await chromium.launch({ headless: false });
  const [first, second] = await Promise.all(
    [1, 2].map(() => browser.newContext({ locale: "zh-CN", viewport: { width: 1440, height: 1000 } })),
  );
  const a = await first.newPage();
  const b = await second.newPage();
  for (const page of [a,b]) {
    page.on("pageerror", error => report.pageErrors.push(error.message));
    page.on("websocket", socket => {
      const url = new URL(socket.url());
      if (url.pathname !== "/ws") return;
      report.sockets.push(url.host);
      socket.on("socketerror", error => report.socketEvents.push(["socketerror", error]));
      socket.on("framereceived", frame => {
        try {
          const event = JSON.parse(frame.payload.toString());
          if (report.socketEvents.length < 50) report.socketEvents.push([event.type, event.error_code || null]);
        } catch {}
      });
    });
    page.on("console", message => {
      if (message.type() === "error") report.consoleErrors.push(message.text().slice(0, 250));
    });
    page.on("request", request => {
      const path = new URL(request.url()).pathname;
      if (restricted.has(path)) restrictedRequests.push(path);
    });
    page.on("response", response => {
      const url = new URL(response.url());
      if (response.status() >= 400 && url.pathname.startsWith("/api/"))
        report.httpFailures.push([url.pathname, response.status()]);
    });
  }
  a.setDefaultNavigationTimeout(150000);
  b.setDefaultNavigationTimeout(150000);
  let active = a;
  try {
    await check("anonymous page and worker HTTP boundary", async () => {
      await a.goto(base + "/chat");
      await expect(a).toHaveURL(/\/login/, fast);
      expect((await first.request.get(base + "/api/reading/materials")).status()).toBe(401);
      expect((await first.request.get(process.env.HEART_BROWSER_WORKER + "/api/reading/materials")).status()).toBe(401);
    });
    await check("two real browser logins and no-Key reading, chat guidance, and distinct masked model settings", async () => {
      for (const [index, page, context] of [[0,a,first],[1,b,second]]) {
        active = page;
        await logIn(page, Object.keys(reading)[index], JSON.parse(process.env.HEART_BROWSER_PASSWORDS)[index]);
        expect(await (await context.request.get(base + "/api/heart/model")).json()).toEqual({ configured: false });
        if (index === 0) {
          await page.goto(base + "/learning/reading/" + Object.values(reading)[0].workspace_id);
          await expect(page.locator("canvas").first()).toBeVisible(fast);
          await page.goto(base + "/settings/model");
        } else {
          await page.goto(base + "/chat");
          await expect(page.getByRole("link", { name: "配置个人模型后开始辅导" })).toBeVisible(fast);
          await page.goto(base + "/settings/model");
        }
        await page.getByLabel(/Base URL/).fill("https://1.1.1.1/v1", fast);
        await page.getByLabel("模型名称").fill(index ? "review-beta" : "review-alpha");
        const testKey = index ? "local-beta-fixture" : "local-alpha-fixture";
        await page.getByLabel("API Key").fill(testKey);
        await page.getByRole("button", { name: "保存", exact: true }).click();
        await expect(page.getByText(/已保存，后续对话/)).toBeVisible(fast);
        const stored = await (await context.request.get(base + "/api/heart/model")).json();
        expect(stored.model).toBe(index ? "review-beta" : "review-alpha");
        expect(JSON.stringify(stored)).not.toContain(testKey);
      }
    });

    await check("three navigation entries and sidebar collapse/restore", async () => {
      active = a;
      await a.goto(base + "/chat");
      for (const path of ['/chat','/learning','/settings']) await expect(a.locator('aside a[href="'+path+'"]').first()).toBeVisible(fast);
      await a.getByRole('button',{name:/^(收起侧边栏|Collapse sidebar)$/}).click();
      await expect(a.getByRole('button',{name:/^(展开侧边栏|Expand sidebar)$/})).toBeVisible();
      await a.reload();
      await a.getByRole('button',{name:/^(展开侧边栏|Expand sidebar)$/}).click();
      await expect(a.getByRole('link',{name:'我的学习',exact:true}).first()).toBeVisible();
    });
    await check("retired routes return HTTP 404 with an authenticated cookie", async () => {
      report.retired = {};
      for (const path of ['/partners','/partners/groups/new','/kanban','/co-writer','/whisper','/space/cli-apps','/space/mcp','/space/personas','/space/skills','/admin/users','/register','/session-handoff']) {
        const response=await first.request.get(base+path); report.retired[path]=response.status(); expect(response.status(),path).toBe(404);
      }
    });
    await check("real chat, activity drawer, session rename/pin/delete and cancel", async () => {
      await a.goto(base+'/chat');
      await send(a,'任务三会话菜单检查','已收到你的教材问题。');
      await a.getByRole('button',{name:/^(会话活动、附件与预览|Activity)$/}).click();
      await expect(a.getByRole('dialog')).toBeVisible(fast);
      report.drawerText=(await a.getByRole('dialog').innerText()).slice(-2500);
      await a.getByRole('button',{name:/^(Close viewer|关闭预览|关闭查看器)$/}).click();
      const actions=a.getByRole('button',{name:/^(聊天操作|Conversation actions)$/}).first();
      await actions.click();
      await a.getByRole('menuitem',{name:/^(重命名对话|Rename chat)$/}).click();
      const title=a.locator('aside input:visible').first();
      await title.fill('任务三可删除会话'); await title.press('Enter');
      await expect(a.getByText('任务三可删除会话',{exact:true}).first()).toBeVisible();
      await actions.click();
      const pin=a.getByRole('menuitem',{name:/^(置顶|Pin)$/});
      await pin.click();
      await actions.click(); await expect(a.getByRole('menuitem',{name:/^(取消置顶|Unpin)$/})).toBeVisible();
      await a.keyboard.press('Escape');
      a.once('dialog',d=>d.dismiss());
      await actions.click(); await a.getByRole('menuitem',{name:/^(删除对话|Delete chat)$/}).click();
      await expect(a.getByText('任务三可删除会话',{exact:true}).first()).toBeVisible();
      a.once('dialog',d=>d.accept());
      await actions.click(); await a.getByRole('menuitem',{name:/^(删除对话|Delete chat)$/}).click();
      await expect(a.getByText('任务三可删除会话',{exact:true})).toHaveCount(0,fast);
    });
    await check("authorized reading context and material picker without personal import", async () => {
      await a.goto(base+'/learning/reading/'+Object.values(reading)[0].workspace_id);
      await expect(a.locator('canvas').first()).toBeVisible(fast);
      await a.getByRole('button',{name:/^(添加资料|Add material)$/}).click();
      await expect(a.getByRole('button',{name:/选择已授权教材/})).toBeVisible(fast);
      const picker=a.getByRole('button',{name:/选择已授权教材/}).locator('xpath=ancestor::div[contains(@class,"max-w-xl")][1]');
      expect(await picker.locator('input[type=file]').count()).toBe(0);
      expect(await picker.getByPlaceholder(/https?:/).count()).toBe(0);
      await picker.getByRole('button',{name:/选择已授权教材/}).click();
      await expect(picker.getByPlaceholder(/Search your library|搜索.*资料|搜索.*库/)).toBeVisible(fast);
      await expect(picker.locator('.max-h-44 button').first()).toBeVisible(fast);
      await picker.getByRole('button',{name:/^(Close|关闭)$/}).first().click();
      await a.goto(base+'/learning/reading/materials');
      await expect(a.getByRole('button',{name:/^(Upload material|上传资料|上传材料|上传教材)$/})).toHaveCount(0);
      expect((await first.request.post(base+'/api/reading/materials',{multipart:{file:{name:'denied.txt',mimeType:'text/plain',buffer:Buffer.from('test')}}})).status()).toBe(403);
    });
    await check("learning reading/path/practice entry points and screenshot input survive", async () => {
      report.learning = {};
      for (const path of ['/learning','/learning/reading','/learning/mastery','/learning/practice']) {
        const response=await a.goto(base+path); expect(response.status(),path).toBe(200);
        await expect(a.locator('main').first()).toBeVisible(fast);
        report.learning[path]=(await a.locator('main').first().innerText()).slice(0,800);
      }
      await a.goto(base+'/chat');
      await expect(a.locator('textarea:visible,[contenteditable=true]:visible').last()).toBeEditable(fast);
      const inputs=await a.locator('input[type=file]').evaluateAll(nodes=>nodes.map(n=>n.accept));
      report.screenshotInputs=inputs;
      await a.getByRole('button',{name:/^(Select model|选择模型)$/}).click();
      await expect(a.getByRole('button',{name:/review-alpha.*\|/})).toBeVisible(fast);
      await a.getByRole('button',{name:/review-alpha.*\|/}).click();
      expect(inputs.some(s=>/image|\.png/.test(s))).toBe(true);
      const bad=await a.locator('a[href]').evaluateAll(nodes=>nodes.map(n=>n.getAttribute('href')).filter(s=>/^\/(partners|kanban|co-writer|whisper|space\/(cli-apps|mcp|personas|skills)|admin|register|session-handoff)(\/|$)/.test(s)));
      expect(bad).toEqual([]);
      expect(report.pageErrors).toEqual([]);
    });
  } catch (error) {
    report.error=String(error.stack||error);
    report.body=(await active.locator('body').innerText()).slice(-10000);
    report.buttons=await active.getByRole('button').evaluateAll(nodes=>nodes.map(n=>({label:n.getAttribute('aria-label'),text:n.textContent})).slice(0,70));
    process.exitCode=1;
  } finally {
    fs.writeFileSync(process.env.HEART_BROWSER_REPORT,JSON.stringify(report,null,2));
    console.log(JSON.stringify({checks:report.checks,error:report.error,pageErrors:report.pageErrors}));
    await browser.close();
  }
})();
