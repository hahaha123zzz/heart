const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');

const BASE = process.env.BASE_URL || 'http://127.0.0.1:8000';
const REAL_V02 = process.env.T3_2_REAL_V02 || '';

const response = {
  schema_version: 'learning-response/v1', status: 'complete', leading_text: '',
  reply: '比较段[1]\n\n步骤段\n\n小结段\n\n反例段',
  blocks: [
    { block_id: 'b1', status: 'published', semantic_type: 'comparison', content_origin: 'generated', rendered_text: '比较段[1]' },
    { block_id: 'b2', status: 'published', semantic_type: 'procedure', content_origin: 'generated', rendered_text: '步骤段' },
    { block_id: 'b3', status: 'published', semantic_type: 'recap', content_origin: 'generated', rendered_text: '小结段' },
    { block_id: 'b4', status: 'published', semantic_type: 'counterexample', content_origin: 'generated', rendered_text: '反例段' },
  ],
};
const host = {
  schema_version: 'learning-response/v1', status: 'complete', leading_text: '', reply: '宿主比较段',
  blocks: [{ block_id: 'b1', status: 'published', semantic_type: 'comparison', content_origin: 'host_snapshot', authority_ref: 'q1', claims: [], rendered_text: '宿主比较段' }],
};
const guide = {
  id: 'guide-s2', title: '步骤保持测试',
  frames: [
    { title: '第一步', text: '甲', table: { columns: ['列'], rows: [['一']], active_row: 0, focus_columns: [0] } },
    { title: '第二步', text: '乙', table: { columns: ['列'], rows: [['一'], ['二']], active_row: 1, focus_columns: [0] } },
  ],
  selection_ref: { chapter_id: 1, section_id: 1, rects: [{ page: 1 }] },
};

(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.goto(BASE, { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(1500);

    await page.evaluate(({ response, host }) => {
      state.chat = [
        { renderKey: 't3-2-typed', role: 'assistant', content: response.reply, learningResponse: response, answerState: 'answered' },
        { renderKey: 't3-2-host', role: 'assistant', content: host.reply, learningResponse: host, answerState: 'answered' },
      ];
      renderChat(); showView('chat');
    }, { response, host });

    const root = page.locator('#chat-messages');
    await root.locator('.response-comparison').first().waitFor();
    assert.equal(await root.locator('.response-comparison').count(), 1);
    assert.equal(await root.locator('.response-procedure').count(), 1);
    assert.equal(await root.locator('.response-recap').count(), 1);
    assert.equal(await root.locator('.response-counterexample').count(), 1);
    assert.ok((await root.locator('.response-comparison .response-block-label').innerText()).includes('对照'));
    assert.ok((await root.locator('.response-procedure .response-block-label').innerText()).includes('步骤'));
    assert.ok((await root.locator('.response-counterexample .response-block-label').innerText()).includes('边界'));
    assert.equal(await root.locator('.response-comparison [data-tutor-citation]').count(), 1);
    assert.equal((await root.locator('.response-comparison').innerText()).split('比较段').length - 1, 1);
    assert.equal(await root.locator('.response-comparison').evaluateAll(nodes => nodes.filter(n => n.textContent.includes('宿主比较段')).length), 0);
    assert.deepEqual(errors, []);

    await page.evaluate((guide) => {
      state.chat = [{ renderKey: 'guide-step', role: 'assistant', content: '带图讲解', guide }];
      renderChat(); showView('chat');
    }, guide);
    const guideRoot = page.locator('.guided-visualization').first();
    await guideRoot.waitFor();
    assert.equal(await guideRoot.getAttribute('data-step'), '0');
    await guideRoot.locator('[data-guide-next]').click();
    assert.equal(await guideRoot.getAttribute('data-step'), '1');
    await page.evaluate(() => {
      state.chat[0].content = '带图讲解（正文更新）';
      renderChat(); showView('chat');
    });
    assert.equal(await page.locator('.guided-visualization').first().getAttribute('data-step'), '1');

    const partial = { schema_version: 'learning-response/v1', status: 'partial', leading_text: '', reply: '第一段',
      blocks: [{ block_id: 'b1', status: 'published', semantic_type: 'comparison', content_origin: 'generated', rendered_text: '第一段' }] };
    const final = { schema_version: 'learning-response/v1', status: 'complete', leading_text: '', reply: '第一段\n\n第二段',
      blocks: [
        { block_id: 'b1', status: 'published', semantic_type: 'comparison', content_origin: 'generated', rendered_text: '第一段' },
        { block_id: 'b2', status: 'published', semantic_type: 'procedure', content_origin: 'generated', rendered_text: '第二段' }] };
    await page.evaluate((partial) => {
      state.chat = [{ renderKey: 'partial-final', role: 'assistant', content: partial.reply, learningResponse: partial, answerState: 'partial' }];
      renderChat(); showView('chat');
    }, partial);
    await page.locator('.response-comparison').first().waitFor();
    await page.evaluate((final) => {
      Object.assign(state.chat[0], { content: final.reply, learningResponse: final, answerState: 'answered' });
      renderChat(); showView('chat');
    }, final);
    assert.equal(await page.locator('.response-procedure').count(), 1);
    assert.equal((await page.locator('#chat-messages').innerText()).split('第一段').length - 1, 1);

    const history = await page.evaluate((final) => messagesFromHistory([{ id: 123, role: 'assistant', content: final.reply,
      selection_ref: { learning_response: final } }]), final);
    assert.equal(history[0].learningResponse.schema_version, 'learning-response/v1');

    await page.setViewportSize({ width: 390, height: 844 });
    await page.evaluate((response) => {
      state.chat = [{ renderKey: 'narrow', role: 'assistant', content: response.reply, learningResponse: response, answerState: 'answered' }];
      renderChat(); showView('chat');
    }, response);
    const overflow = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, inner: window.innerWidth }));
    assert.ok(overflow.scroll <= overflow.inner + 1, JSON.stringify(overflow));
    const citation = page.locator('.response-comparison [data-tutor-citation]').first();
    await citation.focus();
    assert.equal(await page.evaluate(() => document.activeElement?.hasAttribute('data-tutor-citation')), true);

    if (REAL_V02 && fs.existsSync(REAL_V02)) {
      await page.setViewportSize({ width: 1440, height: 1000 });
      const v02 = JSON.parse(fs.readFileSync(REAL_V02, 'utf8'));
      await page.evaluate((v02) => {
        state.chat = [{ renderKey: 'v02-real', role: 'assistant', content: v02.reply, learningResponse: v02.learning_response, answerState: 'answered' }];
        renderChat(); showView('chat');
      }, v02);
      await page.locator('.response-comparison').first().waitFor();
      assert.ok((await page.locator('.response-comparison').innerText()).includes('对照'));
    }

    console.log('PASS: T3.2 typed blocks, host_snapshot fallback, guide step preservation, partial→final, history, narrow viewport, keyboard focus');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exit(1); });
