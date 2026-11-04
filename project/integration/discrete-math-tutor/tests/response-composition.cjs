const assert=require('node:assert/strict');
globalThis.window={};require('../frontend/chat-renderer.js');
const r={schema_version:'learning-response/v1',leading_text:'当前目标',reply:'当前目标\n\n第一段[1]\n\n第二段',blocks:[
 {block_id:'b1',status:'published',rendered_text:'第一段[1]'},
 {block_id:'b2',status:'published',rendered_text:'第二段'}]};
const html=window.renderLearningResponse(r,r.reply);
assert.ok(html.includes('data-response-block="b1"')&&html.includes('data-tutor-citation="1"'));
assert.ok(window.renderLearningResponse({...r,status:'partial'},r.reply).includes('讲解尚未全部完成'));
assert.equal((html.match(/第一段/g)||[]).length,1);
assert.equal(window.renderLearningResponse({...r,schema_version:'future'},r.reply),null);
assert.equal(window.renderLearningResponse(r,'其他正文'),null);
assert.equal(window.renderLearningResponse({...r,blocks:[...r.blocks,r.blocks[0]]},r.reply),null);
assert.equal(window.renderLearningResponse({...r,blocks:[{...r.blocks[0],block_id:'<script>'}]},r.reply),null);
const unsafe={...r,leading_text:'',reply:'<img src=x onerror=alert(1)>',blocks:[{block_id:'b1',status:'published',rendered_text:'<img src=x onerror=alert(1)>'}]};
assert.ok(!window.renderLearningResponse(unsafe,unsafe.reply).includes('<img'));
const snapshot={schema_version:'learning-response/v1',status:'complete',leading_text:'',reply:'原来的检查题？',blocks:[{
 block_id:'b1',status:'published',semantic_type:'check_question',content_origin:'host_snapshot',authority_ref:'q1',
 claims:[],rendered_text:'原来的检查题？'}]};
assert.equal((window.renderLearningResponse(snapshot,snapshot.reply).match(/原来的检查题/g)||[]).length,1);
assert.ok(!window.renderLearningResponse(snapshot,snapshot.reply).includes('q1'));
const typed={schema_version:'learning-response/v1',status:'complete',leading_text:'',reply:'比较段[1]\n\n步骤段\n\n小结段\n\n反例段',blocks:[
 {block_id:'b1',status:'published',semantic_type:'comparison',content_origin:'generated',rendered_text:'比较段[1]'},
 {block_id:'b2',status:'published',semantic_type:'procedure',content_origin:'generated',rendered_text:'步骤段'},
 {block_id:'b3',status:'published',semantic_type:'recap',content_origin:'generated',rendered_text:'小结段'},
 {block_id:'b4',status:'published',semantic_type:'counterexample',content_origin:'generated',rendered_text:'反例段'}]};
const typedHtml=window.renderLearningResponse(typed,typed.reply);
assert.ok(typedHtml.includes('response-comparison')&&typedHtml.includes('data-response-type="comparison"')&&typedHtml.includes('对照'));
assert.ok(typedHtml.includes('response-procedure')&&typedHtml.includes('步骤'));
assert.ok(typedHtml.includes('response-recap')&&!typedHtml.includes('>总结<'));
assert.ok(typedHtml.includes('response-counterexample')&&typedHtml.includes('边界'));
assert.equal((typedHtml.match(/比较段/g)||[]).length,1);
const host={...typed,blocks:typed.blocks.map(b=>({...b,content_origin:'host_snapshot'}))};
const hostHtml=window.renderLearningResponse(host,host.reply);
assert.ok(!hostHtml.includes('response-comparison')&&!hostHtml.includes('data-response-type'));
const unknown={...typed,reply:'未来段',blocks:[{block_id:'b1',status:'published',semantic_type:'future_type',content_origin:'generated',rendered_text:'未来段'}]};
assert.ok(!window.renderLearningResponse(unknown,unknown.reply).includes('data-response-type'));
console.log('内容块：同源正文、引用、类型/身份/重复检查、安全显示、语义展示与旧版本回退通过');
