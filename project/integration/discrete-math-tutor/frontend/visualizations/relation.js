"use strict";

window.RelationView={
  mount(host,initial){
    let data=initial.artifact,busy=false,pending=null,dirty=false,disposed=false,selected={source:'a',target:'b'},activeStep=null,evidenceSteps=[];
    const controller=new AbortController(),scope=initial.scope,request=initial.request;let closureView=null;
    host.innerHTML='<section class="interactive-relation" aria-label="关系图与矩阵辅助示例"><header><strong>关系图与矩阵</strong><small>辅助实例 · 不是教材原图</small></header>'+
      '<p>A={a,b,c}。矩阵行是起点，列是终点；对角线表示自环。探索时点击矩阵格切换关系，测评时仅选中；修改关系会清空未提交的性质判断。</p>'+
      '<div class="relation-canvas" role="img" aria-label="可拖动的有向关系图"></div><div class="relation-pair-controls"><label>起点<select data-relation-source></select></label><label>终点<select data-relation-target></select></label><button type="button" data-relation-toggle>切换所选关系</button></div>'+
      '<div class="answer-grid-wrap"><table class="relation-matrix"><caption>关系矩阵：行 → 列</caption><thead></thead><tbody></tbody></table></div><p data-relation-selection></p>'+
      '<label>关注性质<select data-relation-property></select></label><p data-relation-result></p><button type="button" data-relation-closure>关系闭包预览</button><div data-relation-closure-host hidden></div>'+
      '<div data-relation-evidence-panel hidden><p class="relation-evidence-legend"><span>实线 / 已有：关系中的边</span><span>虚线 / 缺失：反例要求但未存在的边</span><span>检查格：性质涉及的矩阵位置</span></p><div class="relation-evidence-steps" data-relation-steps role="group" aria-label="逐项查看图与矩阵依据"></div><p data-relation-evidence-detail aria-live="polite"></p></div>'+
      '<form><strong>判断这张关系的五种性质</strong><div data-relation-answers></div><label>理由（选填，不自动评分）<textarea data-relation-explanation maxlength="1200" rows="2"></textarea></label>'+
      '<div class="relation-actions"><button type="button" data-relation-save>保存草稿</button><button type="submit" data-relation-submit>提交判断</button><button type="button" data-relation-correction hidden>订正这道题</button></div></form>'+
      '<div class="relation-actions"><button type="button" data-relation-hint>提示所选性质</button><button type="button" data-relation-explain>解释所选关系与性质</button><button type="button" data-relation-assessment>做一道新关系练习</button></div><p data-relation-status role="status"></p><button type="button" data-relation-retry hidden>重试保存</button><p data-relation-feedback></p></section>';
    const root=host.firstElementChild,form=root.querySelector('form'),status=root.querySelector('[data-relation-status]'),source=root.querySelector('[data-relation-source]'),target=root.querySelector('[data-relation-target]'),property=root.querySelector('[data-relation-property]');
    for(const element of data.elements){source.add(new Option(element,element));target.add(new Option(element,element));}
    target.value='b';
    for(const [key,label] of Object.entries(data.properties)){
      property.add(new Option(label,key));
      const field=document.createElement('label');field.textContent=label+'性';const select=document.createElement('select');select.dataset.relationAnswer=key;
      for(const [value,text] of [['','请选择'],['1','满足'],['0','不满足']])select.add(new Option(text,value));
      const feedback=document.createElement('span');feedback.dataset.relationCheck=key;field.append(select,feedback);root.querySelector('[data-relation-answers]').append(field);
    }
    property.value='transitive';
    const head=document.createElement('tr');head.append(document.createElement('th'));
    for(const element of data.elements){const th=document.createElement('th');th.scope='col';th.textContent=element;head.append(th);}root.querySelector('thead').append(head);
    for(const a of data.elements){const tr=document.createElement('tr'),th=document.createElement('th');th.scope='row';th.textContent=a;tr.append(th);
      for(const b of data.elements){const td=document.createElement('td'),button=document.createElement('button');button.type='button';button.dataset.relationPair=a+b;button.setAttribute('aria-label','关系 ('+a+','+b+')');td.append(button);tr.append(td);}root.querySelector('tbody').append(tr);}
    let cy=null,observer=null;
    if(typeof window.cytoscape==='function'){
      cy=window.cytoscape({container:root.querySelector('.relation-canvas'),layout:{name:'preset'},minZoom:.3,maxZoom:3,
        style:[{selector:'node',style:{label:'data(label)','background-color':'#4779a8',color:'#fff','text-valign':'center',width:34,height:34}},
          {selector:'edge',style:{width:3,'line-color':'#8296a9','target-arrow-color':'#8296a9','target-arrow-shape':'triangle','curve-style':'bezier','loop-direction':'-90deg','loop-sweep':'55deg'}},
          {selector:'edge.evidence-present',style:{'line-color':'#287868','target-arrow-color':'#287868',width:5}},
          {selector:'edge.evidence-missing',style:{'line-color':'#ba4f46','target-arrow-color':'#ba4f46','line-style':'dashed',label:'缺失','font-size':11,'text-background-color':'#fff','text-background-opacity':.9,'text-background-padding':3,'text-rotation':'autorotate'}},
          {selector:'edge.selected-pair',style:{width:5,'underlay-color':'#c06b34','underlay-opacity':.2,'underlay-padding':4}}],elements:[]});
      observer=new ResizeObserver(()=>{if(!disposed){cy.resize();cy.fit(undefined,35);}});observer.observe(root.querySelector('.relation-canvas'));
      cy.on('tap','edge',event=>selectPair(event.target.data('source'),event.target.data('target')));
      cy.on('dragfree','node',()=>{
        if(dirty){status.textContent='请先保存性质判断草稿，再拖动布局。';show(data);return;}
        persist('operations',{operation:'layout',positions:Object.fromEntries(cy.nodes().map(node=>[node.id(),node.position()])),expected_layout_revision:data.layout_revision});
      });
    }else{root.querySelector('.relation-canvas').hidden=true;status.textContent='图引擎未加载，仍可使用下方矩阵。';}
    function selectPair(a,b){selected={source:a,target:b};source.value=a;target.value=b;
      root.querySelector('[data-relation-selection]').textContent='选中：('+a+','+b+')，对应 '+a+' → '+b+'。';
      root.querySelectorAll('[data-relation-pair]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.relationPair===a+b)));
      if(cy){cy.edges().removeClass('selected-pair');cy.getElementById('r-'+a+b).addClass('selected-pair');cy.getElementById('missing-'+a+b).addClass('selected-pair');}}
    function controls(){const locked=busy||!!pending||data.readonly;
      root.querySelectorAll('button,input,select,textarea').forEach(el=>{if(!el.closest('.relation-closure'))el.disabled=locked;});
      root.querySelector('[data-relation-toggle]').disabled=locked||data.mode==='assessment'||!!data.feedback;
      form.querySelectorAll('select,textarea,[data-relation-save],[data-relation-submit]').forEach(el=>el.disabled=locked||!!data.feedback||!!closureView);
      root.querySelector('[data-relation-retry]').hidden=!pending||busy||data.readonly;root.querySelector('[data-relation-retry]').disabled=busy||data.readonly;
      cy?.autoungrabify(locked||dirty);}
    const pairText=pair=>'('+pair.join(',')+')';
    const uniquePairs=pairs=>[...new Map(pairs.map(pair=>[pair.join(''),pair])).values()];
    function successfulSteps(key){
      const elements=data.elements,pairs=data.pairs.map(pair=>[pair.source,pair.target]),has=(a,b)=>pairs.some(pair=>pair[0]===a&&pair[1]===b);
      if(key==='reflexive'||key==='irreflexive')return elements.map(a=>({text:'检查自环 '+pairText([a,a])+(has(a,a)?'：已存在':'：矩阵值为 0'),present:has(a,a)?[[a,a]]:[],missing:[],scope:[[a,a]]}));
      if(key==='symmetric')return pairs.filter(([a,b])=>elements.indexOf(a)<=elements.indexOf(b)).map(([a,b])=>({text:a===b?'检查自环 '+pairText([a,a]):'检查反向关系 '+pairText([a,b])+' 与 '+pairText([b,a]),present:uniquePairs([[a,b],[b,a]]),missing:[],scope:[]}));
      if(key==='antisymmetric')return elements.flatMap((a,i)=>elements.slice(i+1).map(b=>({text:'检查不同元素 '+a+'、'+b+'：没有同时存在的两条反向边',present:[[a,b],[b,a]].filter(([x,y])=>has(x,y)),missing:[],scope:[[a,b],[b,a]]})));
      return elements.flatMap(a=>elements.flatMap(b=>elements.filter(c=>has(a,b)&&has(b,c)).map(c=>({text:'检查 '+a+' → '+b+' → '+c+'，以及结论 '+pairText([a,c]),present:uniquePairs([[a,b],[b,c],[a,c]]),missing:[],scope:[]}))));
    }
    function renderEvidence(){
      const evaluation=closureView?null:data.evaluation,key=property.value,panel=root.querySelector('[data-relation-evidence-panel]'),stepsHost=root.querySelector('[data-relation-steps]');
      panel.hidden=!evaluation;stepsHost.replaceChildren();evidenceSteps=[];
      const witness=evaluation?.witnesses[key];
      if(witness){
        evidenceSteps=witness.present.map((pair,index)=>({text:'已有依据 '+(index+1)+'：'+pairText(pair),present:[pair],missing:[],scope:[]}))
          .concat(witness.missing.map(pair=>({text:'缺失关系：'+pairText(pair),present:[],missing:[pair],scope:[]})));
      }else if(evaluation)evidenceSteps=successfulSteps(key);
      if(activeStep!==null&&!evidenceSteps[activeStep])activeStep=null;
      const all={present:uniquePairs(evidenceSteps.flatMap(step=>step.present)),missing:uniquePairs(evidenceSteps.flatMap(step=>step.missing)),scope:uniquePairs(evidenceSteps.flatMap(step=>step.scope))};
      if(evaluation&&key==='transitive'&&!witness&&!evidenceSteps.length)all.scope=data.elements.flatMap(a=>data.elements.map(b=>[a,b]));
      const shown=evaluation?(activeStep===null?all:evidenceSteps[activeStep]):{present:[],missing:[],scope:[]};
      for(const button of root.querySelectorAll('[data-relation-pair]')){
        const pair=button.dataset.relationPair,role=shown.missing.some(p=>p.join('')===pair)?'missing':shown.present.some(p=>p.join('')===pair)?'present':shown.scope.some(p=>p.join('')===pair)?'scope':null;
        if(role)button.dataset.relationEvidence=role;else delete button.dataset.relationEvidence;
        const value=data.matrix[data.elements.indexOf(pair[0])][data.elements.indexOf(pair[1])];
        button.setAttribute('aria-label','关系 ('+pair[0]+','+pair[1]+')，值 '+value+(role==='missing'?'，反例中的缺失关系':role==='present'?'，已有依据':role==='scope'?'，当前性质检查位置':''));
      }
      if(cy)cy.batch(()=>{
        cy.edges('.evidence-missing').remove();cy.edges().removeClass('evidence-present');
        for(const pair of shown.present)cy.getElementById('r-'+pair.join('')).addClass('evidence-present');
        for(const [a,b] of shown.missing)if(!data.pairs.some(pair=>pair.source===a&&pair.target===b))cy.add({data:{id:'missing-'+a+b,source:a,target:b},classes:'evidence-missing'});
      });
      if(evaluation){
        const addStep=(index,text)=>{const button=document.createElement('button');button.type='button';button.dataset.relationStep=String(index);button.textContent=text;button.setAttribute('aria-pressed',String(index===(activeStep??-1)));stepsHost.append(button);};
        addStep(-1,witness?'查看完整反例':'查看全部检查位置');evidenceSteps.forEach((step,index)=>addStep(index,step.text));
      }
      root.querySelector('[data-relation-evidence-detail]').textContent=!evaluation?'':activeStep!==null?evidenceSteps[activeStep].text:
        witness?'点击各项依据可在图和矩阵中单独查看。虚线仅表示缺失关系，矩阵仍为 0。':key==='transitive'&&!evidenceSteps.length?'当前没有首尾相接的两条关系；已检查固定三元素论域上的全部 27 组元素。':'标记显示该性质的检查位置；成立结论来自固定三元素论域的完整核验。';
      selectPair(selected.source,selected.target);
    }
    function renderResult(){const key=property.value,evaluation=data.evaluation;
      const paragraph=root.querySelector('[data-relation-result]');
      if(!evaluation){paragraph.textContent='提交后显示性质结论与反例。';renderEvidence();return;}
      const witness=evaluation.witnesses[key];
      paragraph.textContent=data.properties[key]+'性：'+(evaluation.properties[key]?'满足（已检查固定论域上的全部相关指派）。':'不满足。'+
        (witness.present.length?'已有 '+witness.present.map(pair=>'('+pair.join(',')+')').join('、')+'。':'')+
        (witness.missing.length?'缺少 '+witness.missing.map(pair=>'('+pair.join(',')+')').join('、')+'。':''));renderEvidence();}
    function show(next){if(next.revision!==data.revision){activeStep=null;if(closureView){closureView.dispose();closureView=null;root.querySelector('[data-relation-closure-host]').hidden=true;}}else closureView?.update(next);data=next;dirty=false;root.dataset.artifactId=data.artifact_id;root.dataset.revision=data.revision;root.dataset.layoutRevision=data.layout_revision;root.dataset.mode=data.mode;
      if(cy)cy.batch(()=>{for(const element of data.elements){if(cy.getElementById(element).empty())cy.add({data:{id:element,label:element},position:data.layout[element]});else cy.getElementById(element).position(data.layout[element]);}
        cy.edges().remove();cy.add(data.pairs.map(pair=>({data:{id:'r-'+pair.source+pair.target,...pair}})));});
      for(let i=0;i<data.elements.length;i++)for(let j=0;j<data.elements.length;j++){const button=root.querySelector('[data-relation-pair="'+data.elements[i]+data.elements[j]+'"]');button.textContent=String(data.matrix[i][j]);}
      for(const key of Object.keys(data.properties)){const value=data.draft.values[key];form.querySelector('[data-relation-answer="'+key+'"]').value=value===null?'':value?'1':'0';root.querySelector('[data-relation-check="'+key+'"]').textContent=data.feedback?(data.feedback.checks[key]?'正确':'需要修改'):'';}
      form.querySelector('[data-relation-explanation]').value=data.draft.explanation;
      form.querySelector('strong').textContent=data.correction_of?'订正五种性质（按辅助作答记录）':'判断这张关系的五种性质';
      root.querySelector('[data-relation-submit]').textContent=data.feedback?'已提交':data.correction_of?'提交订正':'提交判断';
      root.querySelector('[data-relation-correction]').hidden=!data.feedback;
      root.querySelector('[data-relation-explain]').hidden=data.mode==='assessment'&&!data.feedback;
      root.querySelector('[data-relation-closure]').hidden=(data.mode==='assessment'&&!data.feedback)||data.readonly;
      root.querySelector('[data-relation-feedback]').textContent=data.feedback?(data.feedback.correct?'五项判断全部正确。':'请检查需要修改的性质。')+(data.feedback.independent?'已记录独立作答证据。':'已记录辅助作答证据。')+'文字解释未评分，不自动更新掌握度。':data.correction_of?'已保留原判断，本次订正按辅助作答记录。':'';
      selectPair(selected.source,selected.target);renderResult();controls();}
    function answers(){return{values:Object.fromEntries([...form.querySelectorAll('[data-relation-answer]')].map(el=>[el.dataset.relationAnswer,el.value===''?null:el.value==='1'])),explanation:form.querySelector('[data-relation-explanation]').value};}
    async function persist(kind,fields,retry=false){if(disposed||busy||data.readonly)return false;
      if(!retry){if(pending)return false;pending={kind,body:{...scope,request_id:crypto.randomUUID(),expected_revision:data.revision,...fields}};}
      if(!pending)return false;busy=true;controls();status.textContent='正在保存…';
      try{await request('/api/relations/'+encodeURIComponent(data.artifact_id)+'/'+pending.kind,{method:'POST',body:JSON.stringify(pending.body),signal:controller.signal});
        const next=await request('/api/relations/'+encodeURIComponent(data.artifact_id)+'?'+new URLSearchParams(scope),{signal:controller.signal});
        if(disposed)return false;pending=null;show(next);initial.onChange?.(data);status.textContent=data.feedback?'作答已保存':'状态已保存';return true;
      }catch(error){if(disposed)return false;if(error.status&&error.status<500){pending=null;try{show(await request('/api/relations/'+encodeURIComponent(data.artifact_id)+'?'+new URLSearchParams(scope),{signal:controller.signal}));initial.onChange?.(data);}catch{data={...data,readonly:true};}}
        status.textContent=error.message+(pending?'；点击重试保存，重复请求不会重复记录。':'');return false;
      }finally{if(!disposed){busy=false;controls();}}}
    async function saveDraft(){return persist('draft',answers());}
    async function ask(action){if(busy||pending||data.readonly)return;if(dirty&&!await saveDraft())return;initial.onQuestion?.(data,property.value,{...selected},action);}
    function closeClosure(){closureView?.dispose();closureView=null;root.querySelector('[data-relation-closure-host]').hidden=true;renderEvidence();controls();}
    async function openClosure(focus={kind:'transitive',step:0}){
      if(busy||pending||data.readonly)return false;
      if(dirty){status.textContent='请先保存性质判断草稿，再打开闭包预览。';return false;}
      if(data.mode==='assessment'&&!data.feedback){status.textContent='请先提交独立判断，再查看闭包。';return false;}
      const host=root.querySelector('[data-relation-closure-host]');host.hidden=false;
      if(!closureView)closureView=window.RelationClosure.mount(host,{artifact:data,scope,request,onClose:closeClosure,
        onQuestion:(current,kind,step)=>initial.onClosureQuestion?.(current,kind,step)});
      renderEvidence();controls();return closureView.focus(focus);
    }
    function toggle(){if(data.mode==='assessment'||data.feedback||busy||pending||data.readonly)return;
      const present=data.pairs.some(pair=>pair.source===selected.source&&pair.target===selected.target);
      persist('operations',{operation:'set_pair',pair:{...selected},present:!present});}
    root.addEventListener('change',event=>{if(event.target===source||event.target===target)selectPair(source.value,target.value);if(event.target===property){closeClosure();activeStep=null;renderResult();controls();}},{signal:controller.signal});
    root.addEventListener('relation-focus',event=>{
      const focus=event.detail;
      if(disposed||busy||pending){focus.error='关系正在保存，请稍后查看。';return;}
      if(focus.revision!==data.revision){focus.error='关系已变化，这条回答对应旧版本，请按当前关系重新提问。';return;}
      if(!Object.hasOwn(data.properties,focus.property)){focus.error='未找到回答对应的性质。';return;}
      if(focus.closure){event.preventDefault();openClosure(focus.closure).then(ok=>{if(ok)root.querySelector('.closure-canvas').scrollIntoView({block:'center'});});return;}
      closeClosure();
      property.value=focus.property;activeStep=null;renderResult();
      if(focus.selected_pair&&data.elements.includes(focus.selected_pair.source)&&data.elements.includes(focus.selected_pair.target))selectPair(focus.selected_pair.source,focus.selected_pair.target);
      controls();event.preventDefault();root.querySelector('.relation-canvas').scrollIntoView({block:'center'});
    },{signal:controller.signal});
    form.addEventListener('input',event=>{if(event.target.matches('select,textarea')){dirty=true;status.textContent='判断尚未保存；可保存草稿或直接提交。';controls();}},{signal:controller.signal});
    form.addEventListener('submit',event=>{event.preventDefault();const values=answers();if(Object.values(values.values).some(value=>value===null)){status.textContent='请判断全部五种性质后再提交。';return;}persist('submissions',values);},{signal:controller.signal});
    root.addEventListener('click',event=>{
      if(event.target.closest('[data-relation-closure]')){openClosure();return;}
      const step=event.target.closest('[data-relation-step]');if(step){activeStep=Number(step.dataset.relationStep);if(activeStep<0)activeStep=null;renderEvidence();controls();return;}
      const pair=event.target.closest('[data-relation-pair]');if(pair){selectPair(pair.dataset.relationPair[0],pair.dataset.relationPair[1]);if(data.mode==='explore'&&!data.feedback)toggle();}
      if(event.target.closest('[data-relation-toggle]'))toggle();
      if(event.target.closest('[data-relation-save]'))saveDraft();
      if(event.target.closest('[data-relation-retry]'))persist(null,null,true);
      if(event.target.closest('[data-relation-hint]'))ask('hint');
      if(event.target.closest('[data-relation-explain]'))ask('explain');
      if(event.target.closest('[data-relation-assessment]')&&!busy&&!pending&&!data.readonly)initial.onAssessment?.();
      if(event.target.closest('[data-relation-correction]')&&!busy&&!pending&&!data.readonly)initial.onCorrection?.(data);
    },{signal:controller.signal});
    show(data);cy?.fit(undefined,35);
    return{update(next){const incoming=next.artifact;if(!disposed&&!busy&&!pending&&!dirty&&(incoming.revision>data.revision||incoming.layout_revision>data.layout_revision||incoming.readonly!==data.readonly))show(incoming);},dispose(){disposed=true;closureView?.dispose();controller.abort();observer?.disconnect();cy?.destroy();}};
  },
};
