"use strict";

window.GuidedVisualization={
 mount(host,initial){
  let guide=initial.guide,index=0,disposed=false,sourceRef=null;
  const controller=new AbortController();
  host.innerHTML='<section class="guided-visualization"><header><strong data-guide-title></strong><small data-guide-origin></small></header><div class="guided-canvas" role="img" aria-label="当前讲解步骤的图"></div><div class="guided-table"></div><div class="guided-explanation"><span data-guide-position></span><h3 data-guide-step-title></h3><p data-guide-text></p></div><footer><button type="button" data-guide-prev>上一步</button><button type="button" data-guide-next>下一步</button></footer><button type="button" class="guided-source" data-guide-source hidden></button></section>';
  const root=host.firstElementChild,canvas=root.querySelector('.guided-canvas'),table=root.querySelector('.guided-table');
  const comparison=document.createElement('div');comparison.className='guided-comparison';comparison.hidden=true;table.before(comparison);
  const figure=document.createElement('div');figure.className='psychology-figure';figure.hidden=true;table.before(figure);
  root.querySelector('[data-guide-position]').setAttribute('aria-live','polite');
  const cy=typeof window.cytoscape==='function'?window.cytoscape({container:canvas,layout:{name:'preset'},autoungrabify:true,userZoomingEnabled:false,userPanningEnabled:false,elements:[],
   style:[{selector:'node',style:{label:'data(label)','background-color':'#4779a8',color:'#fff','text-valign':'center',width:36,height:36}},
    {selector:'edge',style:{width:3,'line-color':'#899ba9','curve-style':'bezier','loop-direction':'-90deg','loop-sweep':'55deg'}},
    {selector:'edge.directed',style:{'target-arrow-shape':'triangle','target-arrow-color':'#899ba9'}},
    {selector:'edge.added',style:{'line-color':'#287868','target-arrow-color':'#287868','line-style':'dashed',label:'新增','font-size':11,'text-background-color':'#fff','text-background-opacity':.9}},
    {selector:'edge.missing',style:{width:3,'line-color':'#b24d44','target-arrow-color':'#b24d44','line-style':'dashed',label:'缺少（示意）','font-size':11,'text-background-color':'#fff','text-background-opacity':.95,'text-background-padding':3}},
    {selector:'edge.traversed',style:{width:5,'line-color':'#287868'}},
    {selector:'edge.annotated',style:{label:'data(annotation)','font-size':11,'text-background-color':'#fff','text-background-opacity':.95,'text-background-padding':3}},
    {selector:'node.annotated',style:{label:'data(displayLabel)','font-size':12,width:54,height:54}},
    {selector:'node.focus',style:{'background-color':'#287868','border-width':4,'border-color':'#8fc8ba'}},
    {selector:'node.warning',style:{'background-color':'#a33d36','border-width':4,'border-color':'#e2ada8'}},
    {selector:'node.diagram',style:{shape:'roundrectangle',width:150,height:54,'font-size':14,'text-wrap':'wrap','text-max-width':138}},
    {selector:'edge.focus',style:{width:6,'line-color':'#a26a22','target-arrow-color':'#a26a22'}}]}):null;
  const observer=cy?new ResizeObserver(()=>{if(!disposed&&!canvas.hidden){cy.resize();cy.fit(undefined,35);}}):null;observer?.observe(canvas);
  function render(){
   const frame=guide.frames[index];root.dataset.guideId=guide.id;root.dataset.step=index;root.dataset.stepId=frame.step_id||String(index);
   root.querySelector('[data-guide-title]').textContent=guide.title;
   root.querySelector('[data-guide-origin]').textContent=({textbook_example:'教材原例 · 分步讲解',teaching_example:'依据教材的辅助示例',user_example:'当前题目 · 分步讲解',legacy:'历史辅助示例 · 分步查看'})[frame.visual_origin||guide.origin]||'分步讲解';
   root.querySelector('[data-guide-position]').textContent='第 '+(index+1)+' / '+guide.frames.length+' 步';
   root.querySelector('[data-guide-step-title]').textContent=frame.title;root.querySelector('[data-guide-text]').textContent=frame.text;
   canvas.hidden=!frame.graph||!cy;canvas.style.height=frame.graph?.layout==='flow'||frame.graph?.layout==='tree'?Math.min(840,Math.max(340,frame.graph.nodes.length*95))+'px':'';table.replaceChildren();
   comparison.replaceChildren();comparison.hidden=!frame.comparison;
   window.PsychologyFigures?.render(figure,frame);
   if(frame.comparison){
    comparison.setAttribute('role','group');comparison.setAttribute('aria-label',frame.title);
    for(const panel of frame.comparison.panels){
     const section=document.createElement('section'),heading=document.createElement('h4'),list=document.createElement('dl');heading.textContent=panel.title;
     for(const item of panel.items){const field=document.createElement('div'),label=document.createElement('dt'),value=document.createElement('dd');
      field.className='comparison-field'+(['focus','warning'].includes(item.tone)?' '+item.tone:'');
      label.textContent=item.label;value.textContent=item.value;
      if(item.tone==='focus'||item.tone==='warning'){const mark=document.createElement('span');mark.className='comparison-mark';mark.textContent=item.tone==='warning'?'注意变化':'本步关注';label.append(mark);}
      field.append(label,value);list.append(field);
     }
     section.append(heading,list);comparison.append(section);
    }
    const note=document.createElement('p');note.className='comparison-note';note.textContent=frame.comparison.note;comparison.append(note);
   }
   if(frame.graph&&cy){let graph=frame.graph;const n=graph.nodes.length;
    // 为已保存的旧欧拉四步卡片补充画面提示，不改写历史答案。
    if(!graph.directed&&!graph.focus_nodes&&!graph.node_annotations){
     const degrees=Object.fromEntries(graph.nodes.map(node=>[node.id,graph.edges.reduce((d,e)=>d+Number(e.source===node.id)+Number(e.target===node.id),0)]));
     if(frame.title==='检查连通性'&&!frame.text.includes('不连通'))graph={...graph,focus:graph.edges.map(e=>e.id),focus_nodes:graph.nodes.map(n=>n.id)};
     if(frame.title==='检查顶点度数'||frame.title==='得到判定')graph={...graph,node_annotations:Object.fromEntries(Object.entries(degrees).map(([id,d])=>[id,'度 '+d])),warning_nodes:Object.keys(degrees).filter(id=>degrees[id]%2),focus_nodes:Object.keys(degrees).filter(id=>degrees[id]%2===0)};
    }
    cy.batch(()=>{cy.elements().remove();cy.add(graph.nodes.map((node,i)=>({data:{...node,displayLabel:node.label+(graph.node_annotations?.[node.id]?'\n'+graph.node_annotations[node.id]:'')},classes:[graph.layout?'diagram':'',graph.node_annotations?.[node.id]?'annotated':'',graph.focus_nodes?.includes(node.id)?'focus':'',graph.warning_nodes?.includes(node.id)?'warning':''].join(' '),position:graph.layout==='mapping'?{x:node.column?370:100,y:55+65*graph.nodes.filter((n,j)=>j<i&&n.column===node.column).length}:{x:150+105*Math.cos(-Math.PI/2+2*Math.PI*i/n),y:145+100*Math.sin(-Math.PI/2+2*Math.PI*i/n)}})));
     cy.add(graph.edges.map(edge=>({data:{...edge,annotation:graph.edge_annotations?.[edge.id]||''},classes:[graph.directed?'directed':'',graph.added?.includes(edge.id)?'added':'',graph.traversed?.includes(edge.id)?'traversed':'',graph.edge_annotations?.[edge.id]?'annotated':'',graph.focus?.includes(edge.id)?'focus':''].join(' ')})));
     cy.add((graph.missing_edges||[]).map(edge=>({data:edge,classes:'directed missing'})));});
    if(graph.layout==='flow'||graph.layout==='tree'){
     const depth=new Map(),queue=graph.nodes.filter(n=>!graph.edges.some(e=>e.target===n.id)).map(n=>n.id);
     if(!queue.length)queue.push(graph.nodes[0].id);for(const id of queue)depth.set(id,0);
     for(let i=0;i<queue.length;i++)for(const edge of graph.edges.filter(e=>e.source===queue[i]))if(!depth.has(edge.target)){depth.set(edge.target,depth.get(queue[i])+1);queue.push(edge.target);}
     const rows=new Map();for(const node of graph.nodes){const level=depth.get(node.id)??0;if(!rows.has(level))rows.set(level,[]);rows.get(level).push(node.id);}
     for(const [level,ids] of rows)ids.forEach((id,i)=>cy.getElementById(id).position({x:(i-(ids.length-1)/2)*180,y:level*95}));
    }
    requestAnimationFrame(()=>{if(!disposed&&!canvas.hidden){cy.resize();cy.fit(undefined,35);}});
   }
   root.querySelector('.guided-badges')?.remove();
   if(frame.badges?.length){const badges=document.createElement('div');badges.className='guided-badges';for(const badge of frame.badges){const item=document.createElement('span');item.className=['warning','good'].includes(badge.tone)?badge.tone:'neutral';item.textContent=badge.text;badges.append(item);}canvas.after(badges);}
   if(frame.table){const t=document.createElement('table'),head=document.createElement('thead'),row=document.createElement('tr');
    for(const label of frame.table.columns){const th=document.createElement('th');th.scope='col';th.textContent=label;row.append(th);}head.append(row);t.append(head);
    const body=document.createElement('tbody');frame.table.rows.forEach((values,i)=>{const tr=document.createElement('tr');if(i===frame.table.active_row)tr.className='active';if(i===frame.table.warning_row)tr.classList.add('warning');values.forEach((value,j)=>{const td=document.createElement('td');td.textContent=String(value);if(i===frame.table.active_row&&frame.table.focus_columns?.includes(j))td.className='focus-cell';if(value==='待检查')td.classList.add('pending-cell');tr.append(td);});body.append(tr);});t.append(body);table.append(t);}
   if(frame.sets){
    const sets=frame.sets,groups=[['仅属于 A',x=>sets.a.includes(x)&&!sets.b.includes(x)],['A ∩ B',x=>sets.a.includes(x)&&sets.b.includes(x)],['仅属于 B',x=>!sets.a.includes(x)&&sets.b.includes(x)],['U 中但不属于 A、B',x=>!sets.a.includes(x)&&!sets.b.includes(x)]];
    const panel=document.createElement('div');panel.className='guided-sets';
    for(const [label,test] of groups){const region=document.createElement('section'),heading=document.createElement('strong');heading.textContent=label;region.append(heading);const members=sets.universe.filter(test);for(const member of members){const token=document.createElement('span');token.className='guided-element'+(sets.selected.includes(member)?' selected':'')+(sets.focus===member?' focus':'');token.textContent=member;region.append(token);}if(!members.length){const empty=document.createElement('small');empty.textContent='∅';region.append(empty);}panel.append(region);}table.append(panel);
    const legend=document.createElement('p');legend.className='guided-set-legend';legend.textContent='U = {'+sets.universe.join('，')+'}；绿色表示本步保留的结果，橙色边框表示正在检查的元素。';table.append(legend);
   }
   if(frame.formula){const panel=document.createElement('div');panel.className='guided-formula';for(const [label,value] of [['原式',frame.formula.before],['本步结果',frame.formula.after]]){const box=document.createElement('section'),heading=document.createElement('strong'),math=document.createElement('div');heading.textContent=label;math.textContent='$$'+value+'$$';box.append(heading,math);panel.append(box);}table.append(panel);window.TextbookPDF?.renderMath(panel);}
   root.querySelector('[data-guide-prev]').disabled=index===0;root.querySelector('[data-guide-next]').textContent=index===guide.frames.length-1?'再看一遍':'下一步';
   const reference=frame.selection_ref||guide.selection_ref;
   sourceRef=reference?.selection_ref||reference;
   const source=root.querySelector('[data-guide-source]');source.hidden=!sourceRef;
   source.textContent=sourceRef?'教材出处：'+(frame.source_label||guide.source_label)+' · 第 '+sourceRef.rects[0].page+' 页 ↗':'';
  }
  root.addEventListener('click',event=>{if(event.target.closest('[data-guide-next]'))index=index===guide.frames.length-1?0:index+1;if(event.target.closest('[data-guide-prev]'))index=Math.max(0,index-1);
   if(event.target.closest('[data-guide-source]'))initial.onSource?.(sourceRef);render();},{signal:controller.signal});
  render();return{update(next){if(next.guide.id!==guide.id){guide=next.guide;index=0;render();}},dispose(){disposed=true;controller.abort();observer?.disconnect();cy?.destroy();}};
 },
 fromLegacy(artifact){
  const relation=artifact.pairs,graph=artifact.graph,table=artifact.rows;let frames=[];
  if(relation){const picture={directed:true,nodes:artifact.elements.map(a=>({id:a,label:a})),edges:relation.map(p=>({...p,id:p.source+p.target})),added:[],focus:[]};
   frames=[{title:'先看原关系',text:'箭头表示关系中的序偶，当前画面只读。',graph:picture}];
   if(artifact.evaluation)for(const [key,label] of Object.entries(artifact.properties)){const w=artifact.evaluation.witnesses[key];frames.push({title:'查看'+label+'性',text:artifact.evaluation.properties[key]?'当前关系满足'+label+'性。':'不满足'+label+'性。'+(w.missing.length?'缺少 '+w.missing.map(p=>'('+p.join(',')+')').join('、')+'。':'已有序偶违反该性质的条件。'),graph:{...picture,focus:(w?.present||[]).map(p=>p.join(''))}});}
  }else if(graph){const picture={directed:false,nodes:graph.nodes,edges:graph.edges.map(p=>({...p,id:p.source+'-'+p.target})),added:[],focus:[]};frames=[{title:'先看图',text:'查看这道历史辅助示例。',graph:picture}];if(Object.keys(artifact.evaluation.degrees||{}).length)frames.push({title:'查看度数',text:Object.entries(artifact.evaluation.degrees).map(([n,d])=>n+' 的度数为 '+d).join('；'),graph:picture});frames.push({title:'判定依据',text:artifact.evaluation.reason,graph:picture});
  }else if(table){frames=table.map((r,i)=>({title:'查看第 '+(i+1)+' 行',text:artifact.evaluation?(artifact.formula+' 的结果为'+(artifact.evaluation[r.id]?'真':'假')+'。'):'本题尚未提交，当前仅显示条件，不展开答案。',table:{columns:['p','q','公式结果'],rows:table.map(x=>[Number(x.assignment.p),Number(x.assignment.q),artifact.evaluation?Number(artifact.evaluation[x.id]):'待独立作答']),active_row:i}}));}
  return {id:'legacy-'+artifact.artifact_id+'-'+artifact.revision,title:relation?'关系性质讲解':graph?'欧拉图讲解':'真值表讲解',origin:'legacy',frames};
 }
};
