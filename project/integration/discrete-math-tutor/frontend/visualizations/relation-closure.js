"use strict";

// 闭包为只读预览，所有序偶和补边步骤来自后台。
window.RelationClosure={mount(host,initial){
 let artifact=initial.artifact,preview=null,step=0,loading=false,disposed=false,loadId=0;
 const controller=new AbortController(),labels={reflexive:'自反闭包',symmetric:'对称闭包',transitive:'传递闭包'};
 host.innerHTML='<section class="relation-closure" aria-label="关系闭包只读预览"><header><strong>闭包预览 · 原关系保留</strong><button type="button" data-closure-close>退出预览</button></header><label>闭包类型<select data-closure-kind></select></label><div class="closure-canvas" role="img" aria-label="当前闭包步骤的关系图"></div><p>灰色实线为原关系，绿色虚线为新增边。矩阵中的 0 → 1 表示补入关系。</p><table class="relation-matrix closure-matrix"><thead></thead><tbody></tbody></table><div class="relation-actions"><button type="button" data-closure-original>原关系</button><button type="button" data-closure-prev>上一步</button><button type="button" data-closure-next>下一步</button><button type="button" data-closure-final>最终结果</button><button type="button" data-closure-ask>解释这一步</button></div><p data-closure-step aria-live="polite"></p><p data-closure-status role="status"></p></section>';
 const root=host.firstElementChild,kind=root.querySelector('[data-closure-kind]'),status=root.querySelector('[data-closure-status]');
 for(const [key,label] of Object.entries(labels))kind.add(new Option(label,key));kind.value='transitive';
 const head=document.createElement('tr');head.append(document.createElement('th'));
 for(const a of artifact.elements){const cell=document.createElement('th');cell.scope='col';cell.textContent=a;head.append(cell);}root.querySelector('thead').append(head);
 for(const a of artifact.elements){const row=document.createElement('tr'),head=document.createElement('th');head.scope='row';head.textContent=a;row.append(head);
  for(const b of artifact.elements){const cell=document.createElement('td');cell.dataset.closureCell=a+b;row.append(cell);}root.querySelector('tbody').append(row);}
 const cy=typeof window.cytoscape==='function'?window.cytoscape({container:root.querySelector('.closure-canvas'),layout:{name:'preset'},autoungrabify:true,elements:[],style:[
  {selector:'node',style:{label:'data(label)','background-color':'#4779a8',color:'#fff','text-valign':'center',width:34,height:34}},
  {selector:'edge',style:{width:3,'line-color':'#8296a9','target-arrow-color':'#8296a9','target-arrow-shape':'triangle','curve-style':'bezier','loop-direction':'-90deg','loop-sweep':'55deg'}},
  {selector:'edge.added',style:{'line-color':'#287868','target-arrow-color':'#287868','line-style':'dashed',label:'新增','font-size':11,'text-background-color':'#fff','text-background-opacity':.9,'text-rotation':'autorotate'}},
  {selector:'edge.premise',style:{width:5,'line-color':'#b87a31','target-arrow-color':'#b87a31'}}]}):null;
 const observer=cy?new ResizeObserver(()=>{if(!disposed){cy.resize();cy.fit(undefined,30);}}):null;observer?.observe(root.querySelector('.closure-canvas'));
 if(!cy)root.querySelector('.closure-canvas').hidden=true;
 function controls(){root.querySelectorAll('button,select').forEach(el=>el.disabled=loading||artifact.readonly);root.querySelector('[data-closure-close]').disabled=false;
  root.querySelector('[data-closure-prev]').disabled=loading||!preview||step===0;root.querySelector('[data-closure-next]').disabled=loading||!preview||step===preview.steps.length;
  root.querySelector('[data-closure-ask]').disabled=loading||!preview||artifact.readonly;}
 function render(){root.dataset.step=step;root.dataset.kind=kind.value;root.dataset.revision=artifact.revision;
  const entry=step?preview?.steps[step-1]:null,pairs=entry?.after_pairs||artifact.pairs,original=new Set(artifact.pairs.map(p=>p.source+p.target)),current=new Set(pairs.map(p=>p.source+p.target));
  for(const cell of root.querySelectorAll('[data-closure-cell]')){const id=cell.dataset.closureCell,before=original.has(id),after=current.has(id);cell.textContent=before===after?String(Number(after)):'0 → 1';cell.classList.toggle('closure-added',!before&&after);}
  if(cy)cy.batch(()=>{cy.elements().remove();cy.add(artifact.elements.map(a=>({data:{id:a,label:a},position:artifact.layout[a]})));cy.add(pairs.map(p=>({data:{id:'c-'+p.source+p.target,...p},classes:original.has(p.source+p.target)?'':'added'})));for(const p of entry?.premises||[])cy.getElementById('c-'+p.source+p.target).addClass('premise');});
  root.querySelector('[data-closure-step]').textContent=!preview?'正在读取闭包…':step===0?'原关系，尚未补边。'+(preview.steps.length?'共需补入 '+preview.steps.length+' 条边。':'原关系已经具有该性质，新增边为 0。'):
   '第 '+step+' / '+preview.steps.length+' 步：'+entry.reason+(step===preview.steps.length?' 已得到包含原关系的最小'+preview.label+'。':' 当前为中间扩充关系。');controls();}
 async function load(nextKind,targetStep=0,expectedEpoch=null){const id=++loadId;loading=true;preview=null;kind.value=nextKind;step=0;status.textContent='正在核对闭包…';render();
  try{const result=await initial.request('/api/relations/'+encodeURIComponent(artifact.artifact_id)+'/closure',{method:'POST',body:JSON.stringify({...initial.scope,expected_revision:artifact.revision,kind:nextKind}),signal:controller.signal});
   if(disposed||id!==loadId)return false;
   if(expectedEpoch!==null&&result.epoch!==expectedEpoch)throw new Error('该闭包学习记忆已删除，请重新提问。');
   if(!Number.isInteger(targetStep)||targetStep<0||targetStep>result.steps.length)throw new Error('回答对应的闭包步骤不存在。');
   preview=result;step=targetStep;status.textContent='只读预览，原关系与作答保留。';return true;
  }catch(error){if(!disposed&&id===loadId)status.textContent=error.message;return false;}
  finally{if(!disposed&&id===loadId){loading=false;render();cy?.fit(undefined,30);}}}
 root.addEventListener('change',event=>{if(event.target===kind)load(kind.value);},{signal:controller.signal});
 root.addEventListener('click',event=>{if(event.target.closest('[data-closure-close]')){initial.onClose();return;}if(loading||!preview)return;
  if(event.target.closest('[data-closure-original]'))step=0;if(event.target.closest('[data-closure-prev]'))step=Math.max(0,step-1);
  if(event.target.closest('[data-closure-next]'))step=Math.min(preview.steps.length,step+1);if(event.target.closest('[data-closure-final]'))step=preview.steps.length;
  if(event.target.closest('[data-closure-ask]'))initial.onQuestion(artifact,kind.value,step);render();},{signal:controller.signal});
 render();return{focus:focus=>load(focus.kind,focus.step,focus.epoch??null),update(next){if(next.revision!==artifact.revision){initial.onClose();return;}artifact=next;render();},dispose(){disposed=true;loadId++;controller.abort();observer?.disconnect();cy?.destroy();host.replaceChildren();}};
}};
