const assert=require('node:assert/strict');
const review=require('../frontend/learning-review.js');
const row={kind:'scheduled_review',review_id:'a'.repeat(32),revision:4,conversation_id:1,point:'<script>变量</script>',
 reason:'间隔已到期',status:'due',due_at:1793000000,allowed_actions:['start','defer','exec']};
const html=review.render([row]);
assert.ok(html.includes('北京时间')&&html.includes('现在复习')&&html.includes('延后一天'));
assert.ok(!html.includes('<script>')&&!html.includes('data-review-action="exec"')&&!html.includes('%'));
assert.ok(!review.render([{...row,status:'source_unavailable',allowed_actions:[]}]).includes('data-review-action='));
assert.ok(review.render([{kind:'learning_followup',point:'变量',reason:'建议回顾'}]).includes('非正式评分'));
let requests=[],fail=true;
review.bind({act:async payload=>{requests.push(payload);if(fail)throw Error('lost');return {reviews:[]}}});
review.render([row]);
(async()=>{
 assert.equal(await review.act(row.review_id,'start'),false);fail=false;
 await review.act(row.review_id,'start');assert.equal(requests[0].command_id,requests[1].command_id);
 await review.act(row.review_id,'defer');assert.notEqual(requests[1].command_id,requests[2].command_id);
 assert.equal(await review.act(row.review_id,'exec'),false);
 console.log('复习列表：时间、转义、动作白名单、旧建议、失败重试与独立命令通过');
})().catch(error=>{console.error(error);process.exitCode=1});
