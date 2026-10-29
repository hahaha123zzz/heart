const assert=require('node:assert/strict');
const data=new Map();globalThis.sessionStorage={getItem:k=>data.get(k)||null,setItem:(k,v)=>data.set(k,v),removeItem:k=>data.delete(k)};
const file=require.resolve('../frontend/learning-review.js');
const row={kind:'scheduled_review',review_id:'b'.repeat(32),revision:4,conversation_id:1,point:'变量',reason:'到期',status:'active',allowed_actions:['finish']};
let calls=[],owner='student:session',fail=true;
function load(){delete require.cache[file];const view=require(file);view.bind({storageKey:()=>owner,act:async p=>{calls.push(p);if(fail)throw Object.assign(Error('response lost'),{status:503});return {reviews:[]}}});view.render([row]);return view;}
(async()=>{
 await load().act(row.review_id,'finish');assert.equal(data.size,1);
 fail=false;await load().act(row.review_id,'finish');
 assert.equal(calls[0].command_id,calls[1].command_id);assert.equal(data.size,0);
 fail=true;await load().act(row.review_id,'finish');const previous=calls.at(-1).command_id;
 owner='other:session';await load().act(row.review_id,'finish');assert.notEqual(calls.at(-1).command_id,previous);
 console.log('复习命令：丢响应、刷新后沿用命令 ID、成功清理、账户隔离通过');
})().catch(e=>{console.error(e);process.exitCode=1});
