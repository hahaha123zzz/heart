"use strict";

// 固定辅助图；数学结论来自后端，不在浏览器重新推断。
window.EulerGraph = {
  fromQuestion(text) {
    // 仅还原用户明确提供的四顶点边集，或首个已审核的四节点环实例。
    const first=String(text).split(/[。！？\n]/)[0];
    const pairs=[...first.matchAll(/\b(v[1-9]\d?)\s*[-−—]\s*(v[1-9]\d?)\b/gi)].map(m=>({source:m[1].toLowerCase(),target:m[2].toLowerCase()}));
    const ids=['v1','v2','v3','v4'];let edges;
    if(/四节点环/.test(first) && /(?:增加|添加)\s*v1\s*[-−—]\s*v3/i.test(first) && !/不要|不增加|不添加/.test(first)) {
      edges=[{source:'v1',target:'v2'},{source:'v2',target:'v3'},{source:'v3',target:'v4'},{source:'v4',target:'v1'},{source:'v1',target:'v3'}];
    } else if(/顶点为/.test(first) && /边为/.test(first) && pairs.length &&
      ids.every(id=>new RegExp('\\b'+id+'\\b','i').test(first.split('边为')[0])) &&
      [...first.split('边为')[0].matchAll(/\bv\d+\b/gi)].every(m=>ids.includes(m[0].toLowerCase())) &&
      pairs.every(pair=>ids.includes(pair.source)&&ids.includes(pair.target))) edges=pairs;
    else return null;
    return {nodes:ids.map(id=>({id,label:id})),edges};
  },
  mount(host, initial) {
    let data = initial.artifact, disposed = false, busy = false, pendingRequest = null, pendingSubmit = null;
    const request = initial.request;
    const scope = initial.scope;
    const controller = new AbortController();
    host.innerHTML = '<section class="interactive-graph" aria-label="欧拉通路与回路辅助示例">'+
      '<header><strong>欧拉通路与回路</strong><small>辅助示例 · 不是教材原图</small></header>'+
      '<p>拖动顶点调整布局，或选两个顶点增删边，观察度数与连通性。</p>'+
      '<div class="graph-canvas" role="img" aria-label="可拖动的无向图"></div>'+
      '<div class="graph-controls"><label>起点<select data-graph-source aria-label="边的起点"></select></label>'+
      '<label>终点<select data-graph-target aria-label="边的终点"></select></label>'+
      '<button type="button" data-graph-add>添加边</button><button type="button" data-graph-remove>删除边</button></div>'+
      '<p class="graph-result"></p><p class="graph-degrees"></p><small class="graph-convention">按教材定义 7.18、定理 7.11/7.12，要求遍历所有顶点和边。</small>'+
      '<p class="graph-status" role="status"></p><button type="button" data-graph-retry hidden>重试保存</button></section>';
    const root = host.firstElementChild;
    const canvas = root.querySelector('.graph-canvas');
    const status = root.querySelector('.graph-status');
    const source = root.querySelector('[data-graph-source]');
    const target = root.querySelector('[data-graph-target]');
    const askHost=document.createElement('div');askHost.className='graph-question-actions';
    askHost.innerHTML='<button type="button" data-graph-explain>解释当前图</button><button type="button" data-graph-hint>只给第一步提示</button><button type="button" data-graph-assessment>做一道新图练习</button>';
    root.append(askHost);
    const form=document.createElement('form');form.className='graph-assessment-form';form.hidden=data.mode!=='assessment';
    form.innerHTML='<strong>先独立判断这张图</strong><p>填写每个顶点的度数，再检查连通性与欧拉性质。提交后查看反馈；请求提示后按辅助作答记录。</p><div data-graph-answers></div>'+
      '<label>图是否连通<select data-graph-connected required><option value="">请选择</option><option value="yes">连通</option><option value="no">不连通</option></select></label>'+
      '<label>我的判定<select data-graph-prediction required><option value="">请选择</option><option value="circuit">有欧拉回路</option><option value="open_path">只有非闭合欧拉通路</option><option value="neither">两者都没有</option></select></label>'+
      '<label>判断理由（选填，保留原文）<textarea data-graph-explanation maxlength="1200" rows="2"></textarea></label><button type="submit" data-graph-submit>提交判断</button><button type="button" data-graph-correction hidden>订正这道题</button><p data-graph-feedback role="status"></p>';
    for(const node of data.graph.nodes) {
      const label=document.createElement('label');label.textContent=node.label+' 的度数';
      const input=document.createElement('input');input.type='number';input.min='0';input.max='11';input.step='1';input.required=true;input.dataset.graphDegree=node.id;
      label.append(input);form.querySelector('[data-graph-answers]').append(label);
    }
    root.append(form);
    // 订正草稿来自服务端保存的原作答，仅在组件首次挂载时预填。
    const draft=data.attempt?.correction?.answers;
    if(draft) {
      for(const [id,value] of Object.entries(draft.degrees)) form.querySelector('[data-graph-degree="'+id+'"]').value=value;
      form.querySelector('[data-graph-connected]').value=draft.connected?'yes':'no';
      form.querySelector('[data-graph-prediction]').value=draft.prediction;
      form.querySelector('[data-graph-explanation]').value=draft.explanation;
    }
    for (const node of data.graph.nodes) {
      source.add(new Option(node.label, node.id));target.add(new Option(node.label, node.id));
    }
    target.selectedIndex = Math.min(1, target.options.length - 1);
    if (typeof window.cytoscape !== 'function') throw new Error('图形库未加载，请刷新页面');
    const cy = window.cytoscape({container:canvas, layout:{name:'preset'}, minZoom:0.3,maxZoom:3,
      style:[{selector:'node',style:{'background-color':'#4779a8','label':'data(label)','color':'#fff','text-valign':'center','width':34,'height':34}},
        {selector:'edge',style:{'width':3,'line-color':'#8296a9','curve-style':'straight'}}], elements:[]});
    const observer = new ResizeObserver(()=>{if(!disposed){cy.resize();cy.fit(undefined,35);}});
    observer.observe(canvas);

    function show(next) {
      data = next;
      cy.batch(()=>{
        // 节点保留；仅边集和已确认的布局更新，避免重建图实例。
        for (const node of data.graph.nodes) {
          if(cy.getElementById(node.id).empty()) cy.add({data:node,position:data.layout[node.id]});
          else cy.getElementById(node.id).position(data.layout[node.id]);
        }
        cy.edges().remove();
        cy.add(data.graph.edges.map(edge=>({data:{id:'e-'+edge.source+'-'+edge.target,...edge}})));
      });
      root.querySelector('.graph-result').textContent = data.evaluation.reason;
      root.querySelector('.graph-degrees').textContent = '顶点度数：'+Object.entries(data.evaluation.degrees).map(([id,d])=>id+' = '+d).join('；')+
        '。奇度顶点：'+(data.evaluation.odd_vertices.join('、') || '无')+'。';
      const hiddenAnswer=data.mode==='hint' || (data.mode==='assessment' && !data.attempt?.submitted);
      root.querySelector('.graph-degrees').hidden = hiddenAnswer;
      root.querySelector('.graph-convention').hidden = hiddenAnswer;
      root.querySelector('.graph-controls').hidden = data.mode==='assessment';
      askHost.querySelector('[data-graph-explain]').hidden=data.mode==='hint' || (data.mode==='assessment' && !data.attempt?.submitted);
      form.querySelector('strong').textContent=data.attempt?.correction?'订正这道题（按辅助作答记录）':'先独立判断这张图';
      form.querySelector('[data-graph-submit]').textContent=data.attempt?.submitted?'已提交':data.attempt?.correction?'提交订正':'提交判断';
      form.querySelector('[data-graph-correction]').hidden=!data.attempt?.submitted;
      if(data.attempt?.feedback) {
        const feedback=data.attempt.feedback;
        form.querySelector('[data-graph-feedback]').textContent=(feedback.correct?'结构化判断全部正确。':'请对照反馈检查：'+Object.entries(feedback.checks).map(([key,value])=>({degrees:'度数',connected:'连通性',prediction:'欧拉性质'})[key]+(value?'正确':'需要修改')).join('；')+'。')+
          (feedback.independent?'已记录本次独立作答证据。':'已记录本次辅助作答证据。')+'文字理由已保留，未自动评分；本次不自动更新掌握度。';
        for(const [id,value] of Object.entries(feedback.answers.degrees)) form.querySelector('[data-graph-degree="'+id+'"]').value=value;
        form.querySelector('[data-graph-connected]').value=feedback.answers.connected?'yes':'no';
        form.querySelector('[data-graph-prediction]').value=feedback.answers.prediction;
        form.querySelector('[data-graph-explanation]').value=feedback.answers.explanation;
      }
      root.dataset.revision = data.revision;
      root.dataset.artifactId = data.artifact_id;
      root.dataset.layoutRevision = data.layout_revision;
      root.dataset.mode = data.mode;
      controls();
    }
    function controls() {
      const locked=busy || !!pendingRequest || !!pendingSubmit || data.readonly;
      root.querySelectorAll('.graph-controls button, .graph-controls select').forEach(el=>el.disabled=locked || data.mode==='assessment');
      cy.autoungrabify(locked);
      root.querySelector('[data-graph-retry]').hidden = (!pendingRequest && !pendingSubmit) || busy || data.readonly;
      askHost.querySelectorAll('button').forEach(button=>button.disabled=locked);
      form.querySelectorAll('input,select,textarea,button').forEach(el=>el.disabled=locked || !!data.attempt?.submitted);
      form.querySelector('[data-graph-correction]').disabled=locked;
    }
    async function save(fields, retry = false) {
      if(disposed || busy || data.readonly) return;
      if(!retry) pendingRequest={...scope,request_id:crypto.randomUUID(),expected_revision:data.revision,...fields};
      if(!pendingRequest) return;
      busy=true;controls();status.textContent='正在保存…';
      try {
        await request('/api/visualizations/'+encodeURIComponent(data.artifact_id)+'/operations',
          {method:'POST',body:JSON.stringify(pendingRequest),signal:controller.signal});
        // 收据可能来自早前请求；再读取当前状态，避免覆盖其他标签的更新。
        const next=await request('/api/visualizations/'+encodeURIComponent(data.artifact_id)+'?'+new URLSearchParams(scope),{signal:controller.signal});
        if(disposed) return;
        pendingRequest=null;show(next);status.textContent='已保存 · 图版本 '+data.revision;
        initial.onChange?.(data);
      } catch(error) {
        if(disposed) return;
        if(error.status && error.status < 500) {
          pendingRequest=null;
          try {show(await request('/api/visualizations/'+encodeURIComponent(data.artifact_id)+'?'+new URLSearchParams(scope),{signal:controller.signal}));}
          catch {data={...data,readonly:true};}
        }
        status.textContent=error.message+(pendingRequest?'；请重试保存，或刷新读取已保存状态。':'');
      } finally {if(!disposed){busy=false;controls();}}
    }
    async function submit(retry=false) {
      if(disposed || busy || data.readonly || data.attempt?.submitted) return;
      if(!retry) {
        if(!form.reportValidity()) return;
        pendingSubmit={...scope,request_id:crypto.randomUUID(),expected_revision:data.revision,
          degrees:Object.fromEntries([...form.querySelectorAll('[data-graph-degree]')].map(input=>[input.dataset.graphDegree,Number(input.value)])),
          connected:form.querySelector('[data-graph-connected]').value==='yes',
          prediction:form.querySelector('[data-graph-prediction]').value,explanation:form.querySelector('[data-graph-explanation]').value.trim()};
      }
      if(!pendingSubmit) return;
      busy=true;controls();status.textContent='正在提交判断…';
      try {
        await request('/api/visualizations/'+encodeURIComponent(data.artifact_id)+'/submissions',
          {method:'POST',body:JSON.stringify(pendingSubmit),signal:controller.signal});
        const next=await request('/api/visualizations/'+encodeURIComponent(data.artifact_id)+'?'+new URLSearchParams(scope),{signal:controller.signal});
        if(disposed) return;
        pendingSubmit=null;show(next);initial.onChange?.(data);status.textContent='作答已保存';
      } catch(error) {
        if(disposed) return;
        if(error.status && error.status<500) {
          pendingSubmit=null;
          try {show(await request('/api/visualizations/'+encodeURIComponent(data.artifact_id)+'?'+new URLSearchParams(scope),{signal:controller.signal}));initial.onChange?.(data);}
          catch {data={...data,readonly:true};}
        }
        status.textContent=error.message+(pendingSubmit?'；请重试提交，重复请求不会重复记分。':'');
      } finally {if(!disposed){busy=false;controls();}}
    }
    form.addEventListener('submit',event=>{event.preventDefault();submit();},{signal:controller.signal});
    root.addEventListener('click',event=>{
      if(event.target.closest('[data-graph-correction]')) {
        if(!busy && !pendingRequest && !pendingSubmit && !data.readonly && data.attempt?.submitted) initial.onCorrection?.(data);
        return;
      }
      if(event.target.closest('[data-graph-assessment]')) {
        if(!busy && !pendingRequest && !pendingSubmit && !data.readonly) initial.onAssessment?.();
        return;
      }
      if(event.target.closest('[data-graph-explain], [data-graph-hint]')) {
        if(busy || pendingRequest || pendingSubmit || data.readonly) return;
        initial.onQuestion?.(data, event.target.closest('[data-graph-hint]')?'hint':'explain');
        return;
      }
      if(event.target.closest('[data-graph-retry]')) {if(pendingSubmit) submit(true);else save(null,true);}
      if(event.target.closest('[data-graph-add], [data-graph-remove]')) {
        if(source.value===target.value){status.textContent='请选择两个不同顶点；首版不支持自环。';return;}
        save({operation:event.target.closest('[data-graph-add]')?'add_edge':'remove_edge',source:source.value,target:target.value});
      }
    },{signal:controller.signal});
    cy.on('dragfree','node',()=>{
      const positions=Object.fromEntries(cy.nodes().map(node=>[node.id(),node.position()]));
      save({operation:'layout',positions,expected_layout_revision:data.layout_revision});
    });
    show(data);cy.fit(undefined,35);
    if(data.readonly) status.textContent='互动功能暂未开放，当前图只读。';
    return {
      update(next){
        const incoming=next.artifact;
        if(!disposed && !busy && !pendingRequest && !pendingSubmit && incoming.revision>=data.revision && incoming.layout_revision>=data.layout_revision &&
          (incoming.revision>data.revision || incoming.layout_revision>data.layout_revision || incoming.readonly!==data.readonly || incoming.attempt?.submitted!==data.attempt?.submitted)) show(incoming);
      },
      dispose(){disposed=true;controller.abort();observer.disconnect();cy.destroy();},
    };
  },
};
