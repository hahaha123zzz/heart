const assert=require('node:assert/strict');
const Style=require('../frontend/interaction-style.js');
const items=new Map(),storage={getItem:key=>items.get(key),setItem:(key,value)=>items.set(key,value)};
let style=new Style(storage,'student:a:tab1');
const suggested={values:{learning_pace:0},label:'慢一点'};
const answer=id=>({task_id:id,answer_status:'answered',style_suggestion:suggested});
assert.equal(style.observe(answer('1')),suggested);
assert.deepEqual(style.snapshot().values,{}); // 看到建议不代表同意。
style.dismiss();
assert.equal(style.observe(answer('1')),null); // 重放不推进冷却。
for(let i=2;i<=6;i++)assert.equal(style.observe(answer(String(i))),null);
assert.equal(style.observe(answer('7')),suggested);
style.apply({answer_length:0},'next','once1');
style=new Style(storage,'student:a:tab1');
assert.deepEqual(style.snapshot().values,{answer_length:0});
style.consume('wrong-request');assert.equal(style.snapshot().onceId,'once1');
style.consume('once1');assert.deepEqual(style.snapshot().values,{});
style.apply({learning_pace:0,question_frequency:0},'session','session1');
style.apply({learning_pace:1},'next','once2');
assert.deepEqual(style.snapshot().values,{learning_pace:1,question_frequency:0});
style.consume('once2');assert.deepEqual(style.snapshot().values,{learning_pace:0,question_frequency:0});
style.apply({answer_length:1},'next','once3');
style.apply({style_suggestions:0},'long');
assert.equal(style.snapshot().onceId,'once3'); // 关闭建议不清除其他已确认风格。
style.apply({learning_pace:1},'long');
assert.deepEqual(style.snapshot().values,{question_frequency:0,answer_length:1});
assert.deepEqual(new Style(storage,'student:a:tab2').snapshot().values,{});
assert.deepEqual(new Style(storage,'student:b:tab1').snapshot().values,{});
style.clear();assert.deepEqual(style.snapshot().values,{});
console.log('交互风格确认、单轮消费、冷却、刷新与学生/会话隔离检查通过');
