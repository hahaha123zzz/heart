const assert=require('node:assert/strict');
globalThis.window={};require('../frontend/chat-renderer.js');
const r={schema_version:'learning-response/v1',leading_text:'当前目标',reply:'当前目标\n\n第一段[1]\n\n第二段',blocks:[
 {block_id:'b1',status:'published',rendered_text:'第一段[1]'},
 {block_id:'b2',status:'published',rendered_text:'第二段'}]};
const html=window.renderLearningResponse(r,r.reply);
assert.ok(html.includes('data-response-block="b1"')&&html.includes('data-tutor-citation="1"'));
assert.ok(window.renderLearningResponse({...r,status:'partial'},r.reply).includes('部分补充内容暂不可用'));
assert.equal((html.match(/第一段/g)||[]).length,1);
assert.equal(window.renderLearningResponse({...r,schema_version:'future'},r.reply),null);
assert.equal(window.renderLearningResponse(r,'其他正文'),null);
assert.equal(window.renderLearningResponse({...r,blocks:[...r.blocks,r.blocks[0]]},r.reply),null);
assert.equal(window.renderLearningResponse({...r,blocks:[{...r.blocks[0],block_id:'<script>'}]},r.reply),null);
const unsafe={...r,leading_text:'',reply:'<img src=x onerror=alert(1)>',blocks:[{block_id:'b1',status:'published',rendered_text:'<img src=x onerror=alert(1)>'}]};
assert.ok(!window.renderLearningResponse(unsafe,unsafe.reply).includes('<img'));
console.log('内容块：同源正文、引用、类型/身份/重复检查、安全显示与旧版本回退通过');
