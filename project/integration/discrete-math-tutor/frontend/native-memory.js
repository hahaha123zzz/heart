"use strict";
// 页面只编辑原生记忆文档；解析、存储及条目身份均由原生服务负责。
window.TutorNativeMemory = (() => {
  const panel=document.createElement('section');
  panel.id='native-memory-panel';panel.className='card page-panel';panel.hidden=true;
  panel.innerHTML='<h2>学习记忆</h2><p>查看和编辑已保存的记忆。在聊天的“能力与工具”中选择记忆引用，可用于后续回答。</p>'+
    '<label for="native-memory-document">记忆文档</label> <select id="native-memory-document" class="select-field"></select>'+
    '<textarea id="native-memory-content" rows="14" aria-label="记忆内容" style="width:100%;margin:16px 0;box-sizing:border-box"></textarea>'+
    '<div class="form-actions"><button type="button" class="primary-button" id="native-memory-save">保存记忆</button>'+
    '<button type="button" class="secondary-button" id="native-memory-reload">重新读取</button></div><p id="native-memory-status" role="status"></p>';
  const heading=document.querySelector('#settings-view .page-title');
  const title=heading.querySelector('h1'),intro=heading.querySelector('p');
  const oldTitle=title.textContent,oldIntro=intro.textContent;
  heading.after(panel);
  const select=panel.querySelector('select'),editor=panel.querySelector('textarea');
  const status=panel.querySelector('[role=status]'),save=panel.querySelector('#native-memory-save');
  const labels={recent:'近期记忆',profile:'个人资料',scope:'学习范围',preferences:'长期偏好',
    chat:'对话归纳',notebook:'笔记归纳',quiz:'练习归纳',kb:'资料归纳',book:'阅读归纳',partner:'协作归纳',cowriter:'写作归纳'};
  let scope=null,sequence=0,enabled=false;
  save.disabled=true;editor.disabled=true;
  const current=key=>scope && JSON.stringify(scope)===key;
  async function call(values,target=scope){
    const response=await fetch('/api/deeptutor/memory',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...target,...values})});
    const result=await response.json();
    if(!response.ok)throw new Error(typeof result.detail==='string'?result.detail:'记忆服务暂不可用');
    return result;
  }
  async function read(){
    if(!select.value)return;
    const key=JSON.stringify(scope),version=++sequence;
    editor.value='';status.textContent='正在读取记忆…';save.disabled=true;editor.disabled=true;
    try{
      const value=await call({action:'read',...JSON.parse(select.value)});
      if(!current(key)||version!==sequence)return;
      editor.value=value.content;status.textContent='';save.disabled=false;editor.disabled=false;
    }catch(error){if(current(key)&&version===sequence)status.textContent=error.message;}
  }
  select.addEventListener('change',read);
  panel.querySelector('#native-memory-reload').addEventListener('click',read);
  save.addEventListener('click',async()=>{
    if(save.disabled||!select.value)return;
    const key=JSON.stringify(scope),doc=select.value,content=editor.value,version=sequence;
    save.disabled=true;editor.disabled=true;status.textContent='正在保存记忆…';
    try{
      await call({action:'write',...JSON.parse(doc),content});
      window.dispatchEvent(new Event('native-memory-changed'));
      if(current(key)&&select.value===doc)status.textContent='记忆已保存；后续引用将读取更新后的内容。';
    }catch(error){if(current(key))status.textContent=error.message;}
    finally{if(current(key)&&version===sequence){save.disabled=false;editor.disabled=false;}}
  });
  return {
    get active(){return enabled;},
    async open(value){
      const key=JSON.stringify(value),changed=!current(key);
      scope={...value};panel.hidden=false;
      title.textContent='学习记忆';intro.textContent='管理已保存的个人资料、偏好与学习记录。';
      document.querySelector('#settings-form').hidden=true;
      document.querySelector('#memory-management').hidden=true;
      if(changed){editor.value='';select.replaceChildren();}
      status.textContent='正在读取记忆…';save.disabled=true;editor.disabled=true;
      try{
        const overview=await call({action:'overview'});
        if(!current(key))return true;
        if(overview.enabled===false){
          enabled=false;panel.hidden=true;title.textContent=oldTitle;intro.textContent=oldIntro;
          document.querySelector('#settings-form').hidden=false;
          document.querySelector('#memory-management').hidden=false;
          return false;
        }
        enabled=true;
        const selected=select.value;
        select.replaceChildren(...overview.docs.map(doc=>new Option((labels[doc.key]||doc.title||doc.key),JSON.stringify({layer:doc.layer,key:doc.key}))));
        if([...select.options].some(option=>option.value===selected))select.value=selected;
        else select.value=JSON.stringify({layer:'L3',key:'preferences'});
        await read();
      }catch(error){if(current(key))status.textContent=error.message;}
      return true;
    }
  };
})();
