"use strict";

window.TruthTable = {
  mount(host, initial) {
    let data=initial.artifact, busy=false, disposed=false, pending=null, dirty=false;
    const controller=new AbortController();
    const scope=initial.scope, request=initial.request;
    host.innerHTML='<section class="interactive-truth-table" aria-label="真值表辅助练习"><header><strong></strong><small>辅助练习 · 不是教材原表</small></header>'+
      '<p>填写每行公式的真值。选中一行后，可以请求提示或解释。未提交测评只提供提示。</p>'+
      '<form><div class="answer-grid-wrap"><table><caption>双变量公式真值表</caption><thead><tr><th scope="col">选中行</th><th scope="col">p</th><th scope="col">q</th><th scope="col">公式结果</th><th scope="col">反馈</th></tr></thead><tbody></tbody></table></div>'+
      '<label>推导说明（选填，不自动评分）<textarea data-table-explanation maxlength="1200" rows="2"></textarea></label>'+
      '<div class="table-actions"><button type="button" data-table-save>保存草稿</button><button type="submit" data-table-submit>提交判断</button><button type="button" data-table-correction hidden>订正这道题</button></div></form>'+
      '<div class="table-actions"><button type="button" data-table-hint>提示选中行</button><button type="button" data-table-explain>解释选中行</button></div>'+
      '<p data-table-status role="status"></p><button type="button" data-table-retry hidden>重试保存</button><p data-table-feedback></p></section>';
    const root=host.firstElementChild, form=root.querySelector('form'), status=root.querySelector('[data-table-status]');
    for(const row of data.rows) {
      const tr=document.createElement('tr');
      const selection=document.createElement('td'), radio=document.createElement('input');
      radio.type='radio';radio.name='truth-row-'+data.artifact_id;radio.value=row.id;radio.checked=row.id==='10';
      radio.setAttribute('aria-label','选中 p='+Number(row.assignment.p)+' q='+Number(row.assignment.q)+' 行');selection.append(radio);tr.append(selection);
      for(const atom of ['p','q']) {const td=document.createElement('td');td.textContent=row.assignment[atom]?'真 (1)':'假 (0)';tr.append(td);}
      const answer=document.createElement('td'), select=document.createElement('select');select.dataset.tableRow=row.id;
      select.setAttribute('aria-label','p='+Number(row.assignment.p)+' q='+Number(row.assignment.q)+' 的公式结果');
      for(const [value,label] of [['','请选择'],['1','真 (1)'],['0','假 (0)']]) select.add(new Option(label,value));
      answer.append(select);tr.append(answer);const feedback=document.createElement('td');feedback.dataset.tableCheck=row.id;tr.append(feedback);
      root.querySelector('tbody').append(tr);
    }
    function controls() {
      const locked=busy||!!pending||data.readonly;
      root.querySelectorAll('button,input,select,textarea').forEach(el=>el.disabled=locked);
      form.querySelectorAll('select,textarea,[data-table-save],[data-table-submit]').forEach(el=>el.disabled=locked||!!data.feedback);
      root.querySelector('[data-table-retry]').hidden=!pending||busy||data.readonly;
      root.querySelector('[data-table-retry]').disabled=busy||data.readonly;
    }
    function show(next) {
      data=next;dirty=false;root.dataset.artifactId=data.artifact_id;root.dataset.revision=data.revision;
      root.querySelector('strong').textContent=(data.correction_of?'订正真值表：':'真值表：')+data.formula;
      for(const row of data.rows) {
        const value=data.draft.values[row.id];form.querySelector('[data-table-row="'+row.id+'"]').value=value===null?'':value?'1':'0';
        const check=root.querySelector('[data-table-check="'+row.id+'"]');
        check.textContent=data.feedback?(data.feedback.checks[row.id]?'正确':'需要修改')+' · 应为 '+(data.evaluation[row.id]?'真':'假'):
          data.evaluation?'结果：'+(data.evaluation[row.id]?'真':'假'):'提交后显示';
      }
      form.querySelector('[data-table-explanation]').value=data.draft.explanation;
      root.querySelector('[data-table-correction]').hidden=!data.feedback;
      root.querySelector('[data-table-submit]').textContent=data.feedback?'已提交':data.correction_of?'提交订正':'提交判断';
      root.querySelector('[data-table-explain]').hidden=data.mode==='assessment'&&!data.feedback;
      root.querySelector('[data-table-feedback]').textContent=data.feedback?
        (data.feedback.correct?'各行真值全部正确。':'请检查标为“需要修改”的行。')+(data.feedback.independent?'已记录独立作答证据。':'已记录辅助作答证据。')+'文字解释未自动评分，不自动更新掌握度。':
        data.correction_of?'已查看原反馈，本次订正按辅助作答记录。':'';
      controls();
    }
    function answers() {return {values:Object.fromEntries([...form.querySelectorAll('[data-table-row]')].map(el=>[el.dataset.tableRow,el.value===''?null:el.value==='1'])),explanation:form.querySelector('[data-table-explanation]').value};}
    async function save(kind='draft',retry=false) {
      if(disposed||busy||data.readonly||data.feedback)return false;
      if(!retry) {
        if(pending)return false;
        const values=answers();
        if(kind==='submissions'&&Object.values(values.values).some(value=>value===null)){status.textContent='请填写全部四行后再提交。';return false;}
        pending={kind,body:{...scope,request_id:crypto.randomUUID(),expected_revision:data.revision,...values}};
      }
      if(!pending)return false;
      busy=true;controls();status.textContent='正在保存…';
      try {
        await request('/api/truth-tables/'+encodeURIComponent(data.artifact_id)+'/'+pending.kind,{method:'POST',body:JSON.stringify(pending.body),signal:controller.signal});
        const next=await request('/api/truth-tables/'+encodeURIComponent(data.artifact_id)+'?'+new URLSearchParams(scope),{signal:controller.signal});
        if(disposed)return false;
        pending=null;show(next);initial.onChange?.(data);status.textContent=data.feedback?'作答已保存':'草稿已保存';return true;
      } catch(error) {
        if(disposed)return false;
        if(error.status&&error.status<500) {
          pending=null;
          try{show(await request('/api/truth-tables/'+encodeURIComponent(data.artifact_id)+'?'+new URLSearchParams(scope),{signal:controller.signal}));initial.onChange?.(data);}
          catch{data={...data,readonly:true};}
        }
        status.textContent=error.message+(pending?'；点击重试保存，重复请求不会重复记录。':'');return false;
      } finally{if(!disposed){busy=false;controls();}}
    }
    async function ask(action) {
      if(busy||pending||data.readonly)return;
      if(dirty&&!await save())return;
      const selected=root.querySelector('input[type="radio"]:checked');
      if(selected)initial.onQuestion?.(data,selected.value,action);
    }
    form.addEventListener('input',event=>{if(event.target.matches('select,textarea')){dirty=true;status.textContent='尚未保存；可保存草稿，或直接提交。';}},{signal:controller.signal});
    form.addEventListener('submit',event=>{event.preventDefault();save('submissions');},{signal:controller.signal});
    root.addEventListener('click',event=>{
      if(event.target.closest('[data-table-save]'))save();
      if(event.target.closest('[data-table-retry]'))save('draft',true);
      if(event.target.closest('[data-table-correction]')&&!busy&&!pending&&!data.readonly)initial.onCorrection?.(data);
      if(event.target.closest('[data-table-hint]'))ask('hint');
      if(event.target.closest('[data-table-explain]'))ask('explain');
    },{signal:controller.signal});
    show(data);
    return {update(next){if(!disposed&&!busy&&!pending&&!dirty&&(next.artifact.revision>data.revision||next.artifact.readonly!==data.readonly))show(next.artifact);},dispose(){disposed=true;controller.abort();}};
  },
};
