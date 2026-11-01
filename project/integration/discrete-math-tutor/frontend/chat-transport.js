"use strict";

window.TutorChatTransport = (() => {
  async function check(response) {
    if (response.ok && response.body) return response;
    const body = await response.json().catch(() => ({}));
    const message = typeof body.detail === "string" ? body.detail : body.detail?.message;
    const error = new Error(message || `服务暂不可用（${response.status}）`);
    error.status = response.status;
    throw error;
  }

  async function readEvents(response, onProgress, onAnswer, onDraft) {
    await check(response);
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "", result = null;
    function parseFrame(frame) {
      const lines = frame.split("\n");
      const event = lines.find(line => line.startsWith("event:"))?.slice(6).trim();
      const raw = lines.filter(line => line.startsWith("data:")).map(line => line.slice(5).trimStart()).join("\n");
      if (!raw) return;
      const payload = JSON.parse(raw);
      if (event === "progress") onProgress?.(payload);
      if (event === "answer") onAnswer?.(payload);
      if (['answer_delta','answer_replace','answer_state','answer_blocks','reader_action'].includes(event)) onDraft?.(event,payload);
      if (event === "done") result = payload;
      if (event === "error") throw new Error(payload.message || "本次回答失败");
    }
    try {
      while (true) {
        const {value, done} = await reader.read();
        buffer += decoder.decode(value, {stream: !done}).replace(/\r/g, "");
        let boundary;
        while ((boundary = buffer.indexOf("\n\n")) >= 0) {
          parseFrame(buffer.slice(0, boundary));
          buffer = buffer.slice(boundary + 2);
          if (result !== null) return result;
        }
        if (done) {
          if(buffer.trim())parseFrame(buffer);
          break;
        }
      }
      if (!result) throw new Error("连接已中断。已开始的回答会继续保存，稍后可恢复对话记录。");
      return result;
    } finally {
      await reader.cancel().catch(() => {});
      reader.releaseLock();
    }
  }

  async function streamChat(data, onProgress, onAnswer, onDraft) {
    try {
      const response = await fetch("/api/chat/stream", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(data)});
      return await readEvents(response, onProgress, onAnswer, onDraft);
    } catch (original) {
      if (!data.request_id || (original.status && original.status < 500)) throw original;
      const params = new URLSearchParams({student_id: data.student_id, session_id: data.session_id || "legacy"});
      let restored;
      try {
        const response = await fetch("/api/chat/requests/" + encodeURIComponent(data.request_id) + "?" + params, {cache:"no-store"});
        await check(response);
        restored = await response.json();
      } catch (error) {
        if ([403, 409, 410].includes(error.status)) throw error;
        throw original;
      }
      if (!restored.result && restored.composition_partial)return {...restored.composition_partial,composition_partial:restored.composition_partial,_transportRecovered:true};
      if (!restored.result) throw original;
      if (!restored.event_replay_enabled) return {...restored.result, _transportRecovered:true};
      params.set("task_revision", String(restored.task_revision));
      const response = await fetch("/api/chat/tasks/" + encodeURIComponent(restored.task_id) + "/events?" + params, {cache:"no-store"});
      return {...await readEvents(response, onProgress, onAnswer), _transportRecovered:true};
    }
  }

  async function compositionPending(student_id,session_id) {
    const params=new URLSearchParams({student_id,session_id});
    const response=await fetch('/api/chat/composition/pending?'+params,{cache:'no-store'});
    // 静态资源可能先于后端更新；旧服务没有可选C3入口时保留原对话流程。
    if([404,503].includes(response.status))return {pending:null};
    await check(response);return response.json();
  }

  function applyDraft(message, event, data) {
    if(message.answerSettled || message.answerState==='cancelled' || !data || !['answer_delta','answer_replace','answer_state','answer_blocks'].includes(event))return false;
    if(typeof data.answer_id!=='string'||!data.answer_id||typeof data.task_id!=='string'||!data.task_id||
       !Number.isInteger(data.task_revision)||!Number.isInteger(data.round_id)||!Number.isInteger(data.seq))return false;
    const identity=message.answerIdentity;
    if(identity && (identity.answer_id!==data.answer_id || identity.task_id!==data.task_id || identity.task_revision!==data.task_revision))return false;
    if(data.seq<=(message.answerSeq||0)||data.round_id<(message.answerRound||0))return false;
    if(event==='answer_delta'&&(message.answerState!=='generating'||message.answerRound!==data.round_id||typeof data.text!=='string'))return false;
    if(event==='answer_replace'&&typeof data.text!=='string')return false;
    if(event==='answer_state'&&!['generating','retrieving','checking','partial','saved','rejected','interrupted','incomplete','timeout','cancelled'].includes(data.state))return false;
    if(data.role && !['progress','answer'].includes(data.role))return false;
    if(event==='answer_blocks') {
      const p=data.publication,r=p?.learning_response;
      if(p?.answer_status!=='partial_answer'||r?.schema_version!=='learning-response/v1'||r.reply!==p.reply||!r.blocks?.length||
         r.blocks.some(b=>b.status!=='published'||typeof b.rendered_text!=='string')||
         [r.leading_text,...r.blocks.map(b=>b.rendered_text)].filter(Boolean).join('\n\n')!==p.reply||
         (message.committedContent&&!p.reply.startsWith(message.committedContent)))return false;
      Object.assign(message,{content:p.reply,committedContent:p.reply,blocksCommitted:true,learningResponse:r,
        pdfReferences:p.pdf_references||[],sources:p.textbook_sources||[],answerState:'partial',
        taskId:data.task_id,compositionResume:{task_id:data.task_id,task_revision:data.task_revision}});
    }
    if(data.role && !['progress','answer'].includes(data.role))return false;
    message.answerIdentity??={answer_id:data.answer_id,task_id:data.task_id,task_revision:data.task_revision};
    message.answerSeq=data.seq;message.answerRound=data.round_id;
    if(event==='answer_blocks')return true;
    if(data.role==='progress') {
      if(event==='answer_state' && data.state==='retrieving')message.answerState='retrieving';
      return true;
    }
    if(event==='answer_delta') {
      if(message.contentRound!==data.round_id && data.role==='answer')message.content='';
      message.contentRound=data.round_id;
      message.content+=data.text;
    }
    if(event==='answer_replace' && (data.authoritative || data.target_round_id===undefined ||
        data.target_round_id===message.contentRound))message.content=data.text;
    if(event==='answer_state')message.answerState=data.state;
    return true;
  }
  function renderUnpublished(text) {
    if(!text)return '';
    const safe=String(text).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    return '<details class="unpublished-draft"><summary>未完成草稿（未核验、未保存）</summary><pre style="white-space:pre-wrap">'+safe+'</pre></details>';
  }
  return {streamChat,applyDraft,renderUnpublished,compositionPending};
})();
