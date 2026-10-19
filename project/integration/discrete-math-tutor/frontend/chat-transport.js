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

  async function readEvents(response, onProgress, onAnswer) {
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
        }
        if (done) break;
      }
      if (!result) throw new Error("连接已中断。已开始的回答会继续保存，稍后可恢复对话记录。");
      return result;
    } finally {
      await reader.cancel().catch(() => {});
      reader.releaseLock();
    }
  }

  async function streamChat(data, onProgress, onAnswer) {
    try {
      const response = await fetch("/api/chat/stream", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(data)});
      return await readEvents(response, onProgress, onAnswer);
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
      if (!restored.result) throw original;
      if (!restored.event_replay_enabled) return restored.result;
      params.set("task_revision", String(restored.task_revision));
      const response = await fetch("/api/chat/tasks/" + encodeURIComponent(restored.task_id) + "/events?" + params, {cache:"no-store"});
      return await readEvents(response, onProgress, onAnswer);
    }
  }

  return {streamChat};
})();
