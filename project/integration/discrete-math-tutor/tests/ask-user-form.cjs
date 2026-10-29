const assert=require('node:assert/strict');
require('../frontend/ask-user-form.js');
const form=globalThis.TutorAskUser;
const questions=[{id:'a',prompt:'<学习目标>',options:[{label:'概念'},{label:'计算'}],allow_free_text:false},
 {id:'b',prompt:'方式',multi_select:true,options:[{label:'例子'},{label:'对比'}],allow_free_text:true}];
assert.deepEqual(form.questions({mode:'ask_user',questions}),questions);
assert.throws(()=>form.answers(questions,{a:{selected:[0]}}),/每一个/);
assert.throws(()=>form.answers(questions,{a:{selected:[0,1]},b:{text:'其他'}}),/单选/);
const draft={a:{selected:[1]},b:{selected:[0,1],text:'先简单讲'}};
assert.deepEqual(form.answers(questions,draft),[{questionId:'a',text:'计算'},{questionId:'b',text:'例子；对比；先简单讲'}]);
const html=form.render(questions,draft,false);
assert.ok(html.includes('&lt;学习目标&gt;')&&!html.includes('<学习目标>'));
assert.ok(html.includes('type="radio"')&&html.includes('type="checkbox"'));
assert.equal((html.match(/data-ask-text/g)||[]).length,1);
assert.ok(form.render(questions,draft,true).includes('fieldset disabled'));
console.log('多问题卡片：问题身份、完整性、单选、多选、自由文本、转义及锁定通过');
