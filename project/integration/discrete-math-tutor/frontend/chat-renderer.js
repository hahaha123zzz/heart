"use strict";

// shortcut: 仅支持短语强调与行内代码，需要完整 Markdown 时接入经过审核的解析器。
window.renderTutorAnswer = text => {
  const escape = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const tokens = /\$\$[\s\S]*?\$\$|\$[^$\n]+\$|\\\([\s\S]*?\\\)|\\\[[\s\S]*?\\\]|`[^`\n]+`|\*\*[^*\n]+\*\*|==[^=\n]+==/g;
  let result='', end=0;
  for (const match of String(text).matchAll(tokens)) {
    result+=escape(String(text).slice(end,match.index));
    const token=match[0];
    if(token.startsWith('**'))result+='<strong>'+escape(token.slice(2,-2))+'</strong>';
    else if(token.startsWith('=='))result+='<mark>'+escape(token.slice(2,-2))+'</mark>';
    else if(token.startsWith('`'))result+='<code>'+escape(token.slice(1,-1))+'</code>';
    else result+=escape(token);
    end=match.index+token.length;
  }
  return '<p class="answer-text">'+result+escape(String(text).slice(end))+'</p>';
};

// 按稳定消息键更新文字区域，互动组件拥有独立生命周期。
window.ChatMessageRenderer = class ChatMessageRenderer {
  constructor(container, renderMath) {
    this.container = container;
    this.renderMath = renderMath;
    this.rows = new Map();
  }

  render(messages) {
    const keys = new Set(messages.map(message => message.key));
    if (keys.size !== messages.length) throw new Error('聊天消息键重复');
    for (const [key, row] of this.rows) {
      if (!keys.has(key)) {
        for (const component of row.components.values()) {
          try { component.dispose?.(); } catch (error) { console.error('互动组件释放失败', error); }
        }
        row.element.remove();
        this.rows.delete(key);
      }
    }
    messages.forEach((message, index) => {
      let row = this.rows.get(message.key);
      if (!row) {
        const element = document.createElement('div');
        element.dataset.messageKey = message.key;
        const body = document.createElement('div');
        body.className = 'message-body';
        element.append(body);
        row = {element, body, slots:new Map(), components:new Map()};
        for (const name of Object.keys(message.parts)) {
          const slot = document.createElement('div');
          slot.dataset.messagePart = name;
          slot.style.display = 'contents';
          body.append(slot);
          row.slots.set(name, {element:slot, html:null});
        }
        row.componentHost = document.createElement('div');
        row.componentHost.className = 'message-components';
        row.componentHost.hidden = true;
        body.append(row.componentHost);
        this.rows.set(message.key, row);
      }
      row.element.className = 'message ' + (message.role === 'user' ? 'user' : 'assistant');
      for (const [name, html] of Object.entries(message.parts)) {
        const slot = row.slots.get(name);
        if (slot.html === html) continue;
        // 保留用户打开的处理记录/原文折叠状态。
        const expanded = [...slot.element.querySelectorAll('details')].map(el => el.open);
        slot.element.innerHTML = html;
        slot.html = html;
        slot.element.querySelectorAll('details').forEach((el, i) => {
          if (i < expanded.length) el.open = expanded[i];
        });
        if (name === 'content') slot.element.querySelectorAll('p').forEach(el => this.renderMath?.(el));
      }
      const position = this.container.children[index];
      if (position !== row.element) this.container.insertBefore(row.element, position || null);
    });
  }

  // 只由审核过的本地组件调用；不执行模型提供的代码。
  attachComponent(messageKey, componentKey, adapter, data) {
    const row = this.rows.get(messageKey);
    if (!row) throw new Error('聊天消息不存在');
    const existing = row.components.get(componentKey);
    if (existing) { existing.update?.(data); return; }
    const host = document.createElement('div');
    row.componentHost.append(host);
    try {
      const instance = adapter.mount(host, data);
      row.components.set(componentKey, {
        update: next => instance?.update?.(next),
        dispose: () => { try { instance?.dispose?.(); } finally { host.remove(); } },
      });
      row.componentHost.hidden = false;
    } catch (error) { host.remove(); throw error; }
  }

  refreshMath() {
    for (const row of this.rows.values()) {
      row.slots.get('content')?.element.querySelectorAll('p').forEach(el => this.renderMath?.(el));
    }
  }

  dispose() { this.render([]); }
};
