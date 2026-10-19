const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../frontend/chat-transport.js'), 'utf8');
const payload = {student_id:'student', session_id:'tab', request_id:'request', message:'问题'};
const frame = (event, data, prefix='') => `${prefix}event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
const json = (value, status=200) => new Response(JSON.stringify(value), {status, headers:{'Content-Type':'application/json'}});
function harness(responses) {
  const calls = [];
  const fetch = async (...args) => {
    calls.push(args);
    assert.ok(responses.length, '不能重复提交生成请求');
    const result = responses.shift();
    if (result instanceof Error) throw result;
    return result;
  };
  const sandbox = {window:{}, fetch, TextDecoder, URLSearchParams};
  vm.runInNewContext(source, sandbox);
  return {chat:sandbox.window.TutorChatTransport.streamChat, calls};
}

test('兼容带 id 的 SSE、CRLF、跨字节分片以及提前保存的回答', async () => {
  const body = frame('progress', {stage:'checking'}) + frame('answer', {reply:'已保存'}) + frame('done', {reply:'完整回答'}, 'id: task:3:2\n');
  const bytes = new TextEncoder().encode(body.replace(/\n/g, '\r\n'));
  const stream = new ReadableStream({start(controller) {
    for (let offset=0; offset<bytes.length; offset+=5) controller.enqueue(bytes.slice(offset, offset+5));
    controller.close();
  }});
  const {chat, calls} = harness([new Response(stream)]);
  const progress=[], answers=[];
  const result = await chat(payload, x=>progress.push(x), x=>answers.push(x));
  assert.equal(result.reply, '完整回答');
  assert.equal(progress.length, 1);
  assert.equal(answers[0].reply, '已保存');
  assert.equal(calls.length, 1);
});

test('断线后通过请求编号定位回合并重放持久化事件，只提交一次', async () => {
  const {chat, calls} = harness([
    new Response(frame('progress', {stage:'saving'})),
    json({task_id:'task', task_revision:3, result:{reply:'已保存'}, event_replay_enabled:true}),
    new Response(frame('sources', {sources:[]}) + frame('done', {reply:'恢复的回答'}, 'id: task:3:2\n')),
  ]);
  assert.equal((await chat(payload)).reply, '恢复的回答');
  assert.equal(calls.filter(([,options])=>options.method==='POST').length, 1);
  assert.match(calls[1][0], /\/requests\/request\?/);
  assert.match(calls[2][0], /\/tasks\/task\/events\?.*task_revision=3/);
});

test('未开启上游事件时仍可恢复宿主已保存收据', async () => {
  const {chat, calls} = harness([new TypeError('network'), json({result:{reply:'宿主收据'}, event_replay_enabled:false})]);
  assert.equal((await chat(payload)).reply, '宿主收据');
  assert.equal(calls.length, 2);
});

test('输入被拒绝时不发恢复请求', async () => {
  const {chat, calls} = harness([json({detail:'选区无效'}, 422)]);
  await assert.rejects(chat(payload), /选区无效/);
  assert.equal(calls.length, 1);
});

test('已删除的回合不会从旧的部分回答恢复', async () => {
  const {chat, calls} = harness([new Response(frame('answer', {reply:'旧回答'})), json({detail:{message:'相关记忆已删除'}}, 410)]);
  await assert.rejects(chat(payload), /相关记忆已删除/);
  assert.equal(calls.length, 2);
});

test('仍在执行时不重新生成，也不轮询到无限等待', async () => {
  const {chat, calls} = harness([new Response(''), json({result:null, status:'executing'})]);
  await assert.rejects(chat(payload), /连接已中断/);
  assert.equal(calls.length, 2);
});

test('事件恢复失败时不绕过校验显示先前读取的正文', async () => {
  const {chat, calls} = harness([new Response(''), json({task_id:'task', task_revision:3,
    result:{reply:'旧的收据快照'}, event_replay_enabled:true}), json({detail:{message:'任务已取消'}}, 410)]);
  await assert.rejects(chat(payload), /任务已取消/);
  assert.equal(calls.length, 3);
});

test('请求尚未入库时保留原错误，不自动再次提交', async () => {
  const {chat, calls} = harness([new TypeError('offline'), json({detail:'请求不存在'}, 404)]);
  await assert.rejects(chat(payload), /offline/);
  assert.equal(calls.length, 2);
});
