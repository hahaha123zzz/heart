"use strict";

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (ch) => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[ch]));
const studentKey = "discrete-math-demo-student";
let studentId = localStorage.getItem(studentKey);
if (!studentId) {
  studentId = "demo-" + (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random().toString(36).slice(2));
  localStorage.setItem(studentKey, studentId);
}

const state = { chapters: [], chapter: 1, section: 1, sectionData: null, contentTab: "text", openChapter: 1, quiz: null, chat: [], sending: false };

async function api(path, options = {}) {
  const response = await fetch(path, { headers: {"Content-Type":"application/json"}, cache:"no-store", ...options });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : `服务暂不可用（${response.status}）`);
  return body;
}
const post = (path, data) => api(path, {method:"POST", body:JSON.stringify(data)});

function toast(message) {
  const el = $("#toast");
  el.textContent = message; el.classList.add("show");
  clearTimeout(toast.timer); toast.timer = setTimeout(() => el.classList.remove("show"), 3300);
}

function showView(view) {
  $$(".view").forEach((el) => el.classList.toggle("active", el.id === `${view}-view`));
  $$(".nav-item").forEach((el) => el.classList.toggle("active", el.dataset.view === view));
  $("#hero").style.display = view === "home" ? "flex" : "none";
  window.scrollTo({top:0, behavior:"smooth"});
  if (view === "stats") refreshStats();
  if (view === "learning") refreshLearning();
  if (view === "settings") refreshPreferences();
  if (view === "quiz") loadQuiz();
  if (view === "chat") renderChat();
}

function renderTrees() {
  const html = state.chapters.map((chapter) => {
    const open = chapter.id === state.openChapter;
    const sections = chapter.sections.map((section) => `<button class="section-link ${state.chapter === chapter.id && state.section === section.id ? "active" : ""}" data-chapter="${chapter.id}" data-section="${section.id}"><span class="section-dot"></span><span>${esc(section.title)}</span></button>`).join("");
    return `<div class="chapter-group ${open ? "open" : ""}"><button class="chapter-toggle" data-open-chapter="${chapter.id}" aria-expanded="${open}"><span class="chevron">›</span><span>第${chapter.id}章&nbsp; ${esc(chapter.title)}</span></button><div class="chapter-sections">${sections}</div></div>`;
  }).join("");
  $("#course-tree").innerHTML = html;
  $("#course-tree-full").innerHTML = html;
  $("#quiz-chapter").innerHTML = state.chapters.map((c) => `<option value="${c.id}">第${c.id}章 · ${esc(c.title)}</option>`).join("");
  $("#quiz-chapter").value = String(state.chapter);
}

async function selectSection(chapter, section, {record=true} = {}) {
  const selection = (state.selection || 0) + 1; state.selection = selection;
  state.chapter = chapter; state.section = section; state.openChapter = chapter;
  state.contentTab = "text";
  $$("[data-content-tab]").forEach((el) => el.classList.toggle("active", el.dataset.contentTab === "text"));
  renderTrees();
  try {
    const data = await api(`/api/course/chapters/${chapter}/sections/${section}`);
    if (selection !== state.selection) return;
    state.sectionData = data;
    $("#content-subtitle").textContent = `第${chapter}章 · ${state.sectionData.title}`;
    $("#full-content-title").textContent = state.sectionData.title;
    $("#chat-topic").textContent = `当前知识点：${state.sectionData.title}`;
    renderContent();
    if (record) post("/api/course/views", {student_id:studentId, chapter_id:chapter, section_id:section}).then(refreshStats).catch(() => {});
  } catch (error) {
    toast(error.message);
  }
}

function formatParagraph(text) {
  return esc(text).replace(/\[公式或对象\]/g, '<span class="object-placeholder">[公式或对象未提取]</span>');
}

function renderFigure(figure) {
  const url = String(figure.image_url || "");
  if (!/^\/api\/figures\/(?:figure-\d+-\d+|formula-\d+-\d+|image-\d+-\d+)\/image$/.test(url)) return "";
  const label = String(figure.label || "").replace(/插图对象\s*\d+/g, "教材插图").replace(/公式对象\s*\d+/g, "教材公式");
  const caption = String(figure.caption || "").replace(/Word 锚点 \d+，/g, "");
  return `<figure class="textbook-figure"><a href="${esc(url)}" target="_blank" rel="noopener noreferrer"><img src="${esc(url)}" alt="${esc(label)}：${esc(caption)}" loading="lazy"></a><figcaption><strong>${esc(label)}</strong> ${esc(caption)}<small>来源：${esc(figure.source)}</small></figcaption></figure>`;
}


function renderSegments(parts) {
  return (parts || []).map((part) => {
    if (part.type === "text") return esc(part.text);
    if (part.type === "symbol" && ["Symbol","Wingdings","Wingdings 2","Wingdings 3","Webdings"].includes(part.font)) return `<span class="word-symbol" style="font-family: '${esc(part.font)}'">${esc(part.text)}</span>`;
    if (part.type === "superscript") return `<sup>${renderSegments(part.segments)}</sup>`;
    if (part.type === "subscript") return `<sub>${renderSegments(part.segments)}</sub>`;
    const asset = part.asset;
    if (!asset || !/^\/api\/figures\/(?:figure|formula|image)-\d+-\d+\/image$/.test(asset.image_url || "")) return "";
    if (part.type === "formula") {
      const height = Math.max(18, Math.min(160, Number(part.height) || 30));
      return `<a class="inline-formula" href="${esc(asset.image_url)}" target="_blank" rel="noopener noreferrer" title="教材原公式，点击放大"><img src="${esc(asset.image_url)}" alt="教材原公式" style="height:${height}px" loading="lazy"></a>`;
    }
    return renderFigure(asset);
  }).join("");
}

function renderBlock(block) {
  if (block.type === "paragraph") return `<div class="textbook-paragraph">${renderSegments(block.segments)}</div>`;
  if (block.type === "image") return renderFigure(block.asset);
  if (block.type === "table") return `<div class="textbook-table-wrap" tabindex="0" aria-label="教材表格，可横向滚动"><table class="textbook-table"><tbody>${block.rows.map((row) => `<tr>${row.filter(c => !c.hidden).map(c => `<td colspan="${Number(c.colspan) || 1}" rowspan="${Number(c.rowspan) || 1}">${c.paragraphs.map(p => `<div>${renderSegments(p)}</div>`).join("")}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
  return "";
}

function renderProgress(message) {
  const stages = message.progress || [];
  const elapsed = Math.round(((message.finishedAt || Date.now()) - message.startedAt) / 1000);
  const current = stages.at(-1);
  const title = message.pending ? (current?.label || "正在连接助教") : message.failed ? "处理未完成" : "已完成";
  return `<div class="turn-progress ${message.failed ? "failed" : ""}"><div class="progress-heading" role="status"><span class="${message.pending ? "progress-spinner" : "progress-check"}">${message.pending ? "" : message.failed ? "!" : "✓"}</span><strong>${esc(title)}</strong><span class="progress-elapsed" data-start="${message.startedAt}" data-finished="${message.finishedAt || ""}">${elapsed} 秒</span></div>${message.pending ? `<div class="progress-detail">${esc(current?.detail || "请求已发出，等待服务响应")}</div>` : ""}<details ${message.pending ? "open" : ""}><summary>处理记录</summary><ol>${stages.map(p => `<li class="${p.status}"><span>${p.status === "completed" ? "✓" : message.failed ? "!" : "·"}</span><div><strong>${esc(p.label)}</strong><small>${esc(p.detail)}</small></div></li>`).join("")}</ol></details></div>`;
}

async function streamChat(data, onProgress) {
  const response = await fetch("/api/chat/stream", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(data)});
  if (!response.ok || !response.body) throw new Error(`服务暂不可用（${response.status}）`);
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "", result = null;
  function parseFrame(frame) {
    const lines = frame.split("\n");
    const event = lines.find(line => line.startsWith("event:"))?.slice(6).trim();
    const raw = lines.filter(line => line.startsWith("data:")).map(line => line.slice(5).trimStart()).join("\n");
    if (!raw) return;
    const payload = JSON.parse(raw);
    if (event === "progress") onProgress(payload);
    if (event === "done") result = payload;
    if (event === "error") throw new Error(payload.message || "本次回答失败");
  }
  try {
    while (true) {
      const {value, done} = await reader.read();
      buffer += decoder.decode(value, {stream: !done});
      let boundary;
      while ((boundary = buffer.indexOf("\n\n")) >= 0) {
        parseFrame(buffer.slice(0, boundary).replace(/\r/g, ""));
        buffer = buffer.slice(boundary + 2);
      }
      if (done) break;
    }
    if (!result) throw new Error("连接已中断。已开始的回答会继续保存，稍后刷新可查看对话记录。");
    return result;
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}

function renderContent() {
  const item = state.sectionData;
  if (!item) return;
  const lines = (item.content || "").split(/\n+/).map((line) => line.trim()).filter(Boolean);
  let html = `<h3>${esc(item.title)}</h3><div class="source-line">来源：${esc(item.source)} · 教材原文与图表</div>`;
  if (state.contentTab === "text") {
    html += item.blocks?.length ? item.blocks.map(renderBlock).join("") : lines.map(line => `<p>${formatParagraph(line)}</p>`).join("");
    html += `<div class="resource-note"><strong>教材资源说明</strong>${esc(item.figure_note)}</div>`;
  } else if (state.contentTab === "notes" || state.contentTab === "examples") {
    const pattern = state.contentTab === "notes" ? /定义|定理|性质|概念/ : /例[0-9一二三四五六七八九十：:. ]|例如/;
    const found = lines.filter((line) => pattern.test(line)).slice(0, 8);
    const blocks = (item.blocks || []).filter(block => block.type === 'paragraph' && pattern.test((block.segments || []).filter(p=>p.type==='text').map(p=>p.text).join(''))).slice(0,8);
    if (blocks.length) html += blocks.map(renderBlock).join('');
    else {
    html += found.length ? found.map((line) => `<p class="text-highlight">${formatParagraph(line.slice(0, 500))}</p>`).join("") : `<div class="resource-note">本小节暂未识别出${state.contentTab === "notes" ? "定义或定理" : "例题"}段落；请切回教材内容阅读原文。</div>`;
    }
  } else {
    html += `<div class="resource-note"><strong>学完来检查一下</strong>本章测验会自动评分，并把结果加入你的个人学习统计。</div><p><button class="primary-button" data-view="quiz">进入第${state.chapter}章测验 →</button></p>`;
  }
  $("#chapter-content").innerHTML = html;
  $("#chapter-content-full").innerHTML = html;
}

function renderChat() {
  const messages = state.chat.length ? state.chat : [{role:"assistant",content:"你好！遇到抽象概念不用着急。选一节教材，或者直接告诉我你哪里不明白。"}];
  const html = messages.map((m) => `<div class="message ${m.role === "user" ? "user" : "assistant"}"><span class="message-avatar ${m.role === "user" ? "human" : "ai"}">${m.role === "user" ? "我" : "✦"}</span><div class="message-body">${m.startedAt ? renderProgress(m) : ""}${m.content ? `<p>${esc(m.content)}</p>` : ""}${m.source ? `<div class="message-source">教材：${esc(m.source)}</div>` : ""}${(m.imageRefs || []).map(renderFigure).join("")}</div></div>`).join("");
  for (const selector of ["#chat-messages", "#chat-page-messages"]) {
    const el = $(selector); el.innerHTML = html; el.scrollTop = el.scrollHeight;
  }
}


async function sendMessage(message) {
  const text = message.trim();
  if (!text || state.sending) return;
  state.sending = true;
  $$(".chat-input button").forEach(button => button.disabled = true);
  $("#chat-error").textContent = ""; $("#chat-page-error").textContent = "";
  const pending = {role:"assistant", content:"", pending:true, startedAt:Date.now(), progress:[]};
  state.chat.push({role:"user", content:text}, pending);
  renderChat();
  const timer = setInterval(() => {
    $$(".progress-elapsed").forEach(el => {
      if (!el.dataset.finished) el.textContent = `${Math.round((Date.now() - Number(el.dataset.start))/1000)} 秒`;
    });
  }, 1000);
  try {
    const result = await streamChat({student_id:studentId, account_type:"test", message:text,
      learning_goal:state.sectionData?.title || "图的基本概念"}, progress => {
        const index = pending.progress.findIndex(item => item.order === progress.order);
        if (index >= 0) pending.progress[index] = progress;
        else pending.progress.push(progress);
        renderChat();
      });
    Object.assign(pending, {pending:false, finishedAt:Date.now(),
      content:result.reply || "助教暂时没有返回内容。",
      source:result.textbook_sources?.[0] || "", imageRefs:result.image_refs || []});
    renderChat(); refreshStats();
  } catch (error) {
    Object.assign(pending, {pending:false, failed:true, finishedAt:Date.now(), content:error.message});
    renderChat();
    $("#chat-error").textContent = error.message;
    $("#chat-page-error").textContent = error.message;
    toast("本次回答未完成，处理记录已保留");
  } finally {
    clearInterval(timer);
    state.sending = false;
    $$(".chat-input button").forEach(button => button.disabled = false);
  }
}

async function loadQuiz() {
  $("#quiz-chapter").value = String(state.chapter);
  try {
    state.quiz = await api(`/api/course/chapters/${state.chapter}/quiz`);
    $("#quiz-area").innerHTML = `<form id="quiz-form">${state.quiz.questions.map((q, index) => `<div class="quiz-question"><h3>${index + 1}. ${esc(q.question)}</h3>${q.options.map((option, value) => `<label class="quiz-option"><input type="radio" name="${esc(q.id)}" value="${value}" required> ${esc(option)}</label>`).join("")}</div>`).join("")}<button class="primary-button" type="submit">提交并查看评分</button></form>`;
  } catch (error) {
    $("#quiz-area").innerHTML = `<div class="resource-note">${esc(error.message)}</div>`;
  }
}

async function submitQuiz(form) {
  const answers = {};
  for (const q of state.quiz.questions) {
    const checked = form.querySelector(`input[name="${q.id}"]:checked`);
    if (!checked) { toast("请完成每道题再提交"); return; }
    answers[q.id] = Number(checked.value);
  }
  const button = form.querySelector("button[type=submit]"); button.disabled = true;
  try {
    const result = await post(`/api/course/chapters/${state.chapter}/quiz`, {student_id:studentId, answers});
    const detail = result.items.map((item, index) => `<div class="answer-feedback ${item.is_correct ? "" : "wrong"}">${index + 1}. ${item.is_correct ? "回答正确" : `正确答案：${esc(state.quiz.questions[index].options[item.correct])}`} · ${esc(item.explanation)}</div>`).join("");
    form.insertAdjacentHTML("beforeend", `<div class="quiz-result">本章测验得分：<strong>${result.score} 分</strong><p>错题可在下方查看解释。</p>${detail}</div>`);
    form.querySelectorAll("input").forEach((input) => input.disabled = true);
    button.textContent = "已提交";
    refreshStats();
  } catch (error) { toast(error.message); button.disabled = false; }
}

async function refreshStats() {
  try {
    const data = await api(`/api/students/${encodeURIComponent(studentId)}/dashboard`);
    const metrics = [
      ["已读章节", `${data.viewed_chapters} / 10`],
      ["测验平均分", data.average_best_score === null ? "未测验" : `${data.average_best_score} 分`],
      ["完成章节", `${data.completed_chapters} / 10`],
      ["答疑次数", `${data.chat_turns} 次`],
    ];
    $("#home-stats").innerHTML = metrics.map(([label,value]) => `<div class="mini-stat"><span>${label}</span><strong>${esc(value)}</strong></div>`).join("");
    $("#stats-summary").innerHTML = metrics.map(([label,value]) => `<div class="summary-tile"><span>${label}</span><strong>${esc(value)}</strong></div>`).join("");
    const maxCount = Math.max(1, ...data.activity.map((d) => d.count));
    $("#activity-chart").innerHTML = data.activity.map((d) => `<div class="day-bar"><span>${d.count}</span><div class="bar-track"><div class="bar-fill" style="height:${Math.max(2,Math.round(d.count/maxCount*100))}%"></div></div><span>${esc(d.day.slice(5))}</span></div>`).join("");
    $("#chapter-scores").innerHTML = data.chapter_scores.length ? data.chapter_scores.map((row) => `<div class="score-row"><span>${esc(row.title)}</span><div class="score-track"><div class="score-fill" style="width:${row.score}%"></div></div><strong>${row.score} 分</strong></div>`).join("") : '<div class="resource-note">还没有测验记录。完成一章练习后，这里会显示真实成绩。</div>';
    const knowledge = data.knowledge || [];
    const errors = data.common_errors || [];
    $("#knowledge-mastery").innerHTML = knowledge.length ? knowledge.map((row) => `<div class="score-row"><span>${esc(row.point)}</span><div class="score-track"><div class="score-fill" style="width:${Math.round(row.mastery*100)}%"></div></div><strong>${Math.round(row.mastery*100)}%</strong></div>`).join("") : '<div class="resource-note">完成答疑或练习后，会逐步形成知识掌握记录。</div>';
    $("#common-errors").innerHTML = errors.length ? errors.map((row) => `<div class="history-item"><small>第${row.chapter_id}章 · 错 ${row.wrong_count} 次</small><p>${esc(row.question)}</p><p>正确选项：${esc(row.correct_option)}</p></div>`).join("") : '<div class="resource-note">目前还没有错题记录。</div>';
  } catch (error) { toast(`统计暂不可用：${error.message}`); }
}

async function refreshLearning() {
  try {
    const [review, history] = await Promise.all([
      api(`/api/students/${encodeURIComponent(studentId)}/review`),
      api(`/api/students/${encodeURIComponent(studentId)}/conversation`),
    ]);
    $("#review-list").innerHTML = review.length ? review.map((item) => `<div class="review-item"><div><strong>${esc(item.point)}</strong><p>${esc(item.reason)}</p></div><button data-review="${esc(item.point)}">请助教带我复习</button></div>`).join("") : '<div class="resource-note">暂时没有识别到需要复习的难点。继续学习或完成测验后再来看看。</div>';
    $("#history-list").innerHTML = history.length ? history.slice(-16).reverse().map((m) => `<div class="history-item"><small>${m.role === "user" ? "我" : "助教"}</small><p>${esc(m.content)}</p>${(m.image_refs || []).map(renderFigure).join("")}</div>`).join("") : '<div class="resource-note">还没有对话记录。向助教提一个问题吧。</div>';
  } catch (error) { toast(`学习记录暂不可用：${error.message}`); }
}

async function refreshPreferences() {
  try {
    const values = await api(`/api/students/${encodeURIComponent(studentId)}/preferences`);
    const form = $("#settings-form");
    for (const name of ["answer_length","example_density","learning_pace"]) {
      const field = form.elements.namedItem(name);
      field.value = String(values[name] ?? 0.5);
    }
  } catch (error) { toast(error.message); }
}

async function savePreferences(form) {
  const data = Object.fromEntries(["answer_length","example_density","learning_pace"].map((name) => [name, Number(form.elements.namedItem(name).value)]));
  try {
    await api(`/api/students/${encodeURIComponent(studentId)}/preferences`, {method:"PUT", body:JSON.stringify(data)});
    $("#settings-status").textContent = "已保存，下一轮对话起生效";
    toast("偏好已保存");
  } catch (error) { $("#settings-status").textContent = error.message; }
}

function bindEvents() {
  document.addEventListener("click", (event) => {
    const nav = event.target.closest("[data-view]");
    if (nav) { showView(nav.dataset.view); return; }
    const toggle = event.target.closest("[data-open-chapter]");
    if (toggle) { const number = Number(toggle.dataset.openChapter); state.openChapter = state.openChapter === number ? 0 : number; renderTrees(); return; }
    const section = event.target.closest("[data-chapter][data-section]");
    if (section) { selectSection(Number(section.dataset.chapter), Number(section.dataset.section)); return; }
    const prompt = event.target.closest("[data-prompt]");
    if (prompt) { const input = $(".view.active #chat-page-input") || $("#chat-input"); input.value = prompt.dataset.prompt; input.focus(); return; }
    const review = event.target.closest("[data-review]");
    if (review) { showView("chat"); $("#chat-page-input").value = `请帮我复习${review.dataset.review}，先出一道简单的问题检查我`; $("#chat-page-input").focus(); return; }
    const courseTab = event.target.closest("[data-course-tab]");
    if (courseTab) {
      $$("[data-course-tab]").forEach((el) => el.classList.toggle("active", el === courseTab));
      if (courseTab.dataset.courseTab === "chapters") renderTrees();
      if (courseTab.dataset.courseTab === "materials") $("#course-tree").innerHTML = '<div class="resource-note"><strong>课件资料尚未提供</strong>目前已有十章教材正文、公式、表格和插图。课件文件需要另行提供，平台不会显示不存在的文件。</div>';
      if (courseTab.dataset.courseTab === "quiz") showView("quiz");
      return;
    }
    const contentTab = event.target.closest("[data-content-tab]");
    if (contentTab) { state.contentTab = contentTab.dataset.contentTab; $$("[data-content-tab]").forEach((el) => el.classList.toggle("active", el === contentTab)); renderContent(); }
  });
  for (const [formSelector,inputSelector] of [["#chat-form","#chat-input"],["#chat-page-form","#chat-page-input"]]) {
    $(formSelector).addEventListener("submit", (event) => { event.preventDefault(); if (state.sending) return; const input = $(inputSelector); const value = input.value; input.value = ""; sendMessage(value); });
  }
  $("#quiz-chapter").addEventListener("change", (event) => { state.chapter = Number(event.target.value); loadQuiz(); });
  $("#quiz-area").addEventListener("submit", (event) => { if (event.target.id === "quiz-form") { event.preventDefault(); submitQuiz(event.target); } });
  $("#settings-form").addEventListener("submit", (event) => { event.preventDefault(); savePreferences(event.target); });
  $("#search-form").addEventListener("submit", async (event) => {
    event.preventDefault(); const value = $("#global-search").value.trim(); if (!value) return;
    try {
      const results = await api(`/api/course/search?q=${encodeURIComponent(value)}`);
      const match = results[0];
      if (match) { await selectSection(match.chapter_id, match.section_id); showView("course"); toast(`已找到：${match.title}`); }
      else { showView("chat"); $("#chat-page-input").value = value; $("#chat-page-input").focus(); toast("教材暂未匹配到；你可以直接问助教"); }
    } catch (error) { toast(`搜索失败：${error.message}`); }
  });
}

async function init() {
  bindEvents(); renderChat();
  try {
    state.chapters = await api("/api/course/chapters");
    renderTrees();
    if (state.chapters[0]?.sections[0]) await selectSection(state.chapters[0].id, state.chapters[0].sections[0].id, {record:false});
  } catch (error) { $("#course-tree").textContent = `教材读取失败：${error.message}`; toast(error.message); }
  try {
    const history = await api(`/api/students/${encodeURIComponent(studentId)}/conversation`);
    state.chat = history.map((m) => ({role:m.role,content:m.content,imageRefs:m.image_refs || []})); renderChat();
  } catch { /* New local demo student has no history. */ }
  refreshStats();
}

init();
