const assert=require('node:assert/strict');
const cards=require('../frontend/learning-cards.js');
const question={schema:'learning-cards/v2',kind:'assessment_question',card_id:'q',revision:4,title:'教材测评',
 question:{prompt:'选择自变量',question_type:'choice',options:[{id:'A',label:'A',body:'<img onerror=alert(1)>'}]},
 allowed_actions:['submit_answer','request_hint'],status:'registered'};
assert.ok(cards.render([question]).includes('测评动作尚未启用'));
let calls=[],fail=true;
cards.bind({onAction:async payload=>{calls.push(payload);if(fail)throw Error('模拟断线');return {learning_cards:[question]}}});
const html=cards.render([question]);
assert.ok(!html.includes('<img')&&html.includes('&lt;img')&&html.includes('<fieldset>')&&html.includes('data-card-action="submit_answer"'));
assert.ok(!html.includes('data-card-action="grade"'));
const notice={textContent:''},buttons=[{disabled:false}];
const element={dataset:{learningCard:'q'},querySelector:()=>notice,querySelectorAll:()=>buttons};
(async()=>{
 assert.equal(await cards.submit(element,'submit_answer',{text:'A'}),false);
 assert.equal(buttons[0].disabled,false);assert.equal(notice.textContent,'模拟断线');
 fail=false;await cards.submit(element,'submit_answer',{text:'A'});
 assert.equal(calls[0].command_id,calls[1].command_id);
 await cards.submit(element,'request_hint',{text:''});
 assert.notEqual(calls[1].command_id,calls[2].command_id);
 const restored=cards.render([{...question,status:'graded',learner_answer:'A',allowed_actions:[],assessment:{is_correct:true,verification:'reviewed'}}]);
 assert.ok(restored.includes(' checked disabled')&&restored.includes('本次作答正确')&&!restored.includes('data-card-action="submit_answer"'));
 assert.ok(cards.render([{...question,status:'abandoned',disposition:'defer',allowed_actions:[]}]).includes('已延后'));
 assert.ok(cards.render([{...question,question:{...question.question,prompt:'字'.repeat(1500)}}]).includes('字'.repeat(1500)));
 console.log('题卡：类型、转义、已登记动作、失败重开、命令重试、独立操作及作答恢复通过');
})().catch(error=>{console.error(error);process.exitCode=1});
