// 多来源引用渲染回归：无需浏览器和外部 API。
const fs=require('node:fs');const path=require('node:path');const vm=require('node:vm');const assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..');const code=fs.readFileSync(path.join(root,'frontend/app.js'),'utf8');
const context={esc:value=>String(value??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]))};vm.createContext(context);
vm.runInContext(code.slice(code.indexOf('function renderPDFReference('),code.indexOf('function renderSelectionDraft()')),context);
const selection=(page)=>({rects:[{page}],section_title:'教材小节',image_refs:[{image_url:'/crop-'+page,label:'第'+page+'页'}]});
const message={content:'主证明[1]，前置定理[3]。',sources:['主证明','无关背景','前置定理'],pdfReferences:[{source_index:0,label:'定理7.7',selection_ref:selection(10)},{source_index:2,label:'定理7.2',selection_ref:selection(4)}]};
const html=context.renderChatReferences(message,5);assert.ok(html.includes('[3] 教材：前置定理'));assert.ok(html.includes('教材第 4 页'));assert.ok(html.includes('教材第 10 页'));assert.ok(html.includes('data-pdf-reference="1"'));assert.ok(!html.includes('无关背景'));
const onlyPrerequisite=context.renderChatReferences({...message,content:'前置定理[3]'},5);assert.ok(onlyPrerequisite.includes('教材第 10 页'));assert.ok(onlyPrerequisite.includes('教材第 4 页'));
assert.ok(context.renderChatReferences({selectionRef:selection(2)},1).includes('教材第 2 页'));
assert.ok(context.renderChatReferences({content:'解释[1]',sources:['<script>']},1).includes('&lt;script&gt;'));
console.log('多引用序号、两个页码、背景过滤、旧选区和转义：全部通过');