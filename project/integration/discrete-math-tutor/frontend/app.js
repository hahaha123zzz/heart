"use strict";

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (ch) => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[ch]));
const course = window.TutorCourse || {id:'experimental-psychology-3',title:'实验心理学',page_label:'生成阅读版第',reading_map_url:'/api/course/reading-map'};
document.title=course.title+'学习平台';
$('.sidebar-brand strong').textContent=course.title;
const studentKey = course.id+'-demo-student';
let studentId = localStorage.getItem(studentKey);
if (!studentId) {
  studentId = "demo-" + (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random().toString(36).slice(2));
  localStorage.setItem(studentKey, studentId);
}

const state = { chapters: [], chapter: 1, section: 1, sectionData: null, contentTab: "text", openChapter: 1, quiz: null, chat: [], sending: false, view:"course" };
state.taskRecoveryNeeded=true;
const newRequestId = () => crypto.randomUUID();
const tabSessionKey = course.id+'-task-session';
let tabSessionId = sessionStorage.getItem(tabSessionKey) || newRequestId();
sessionStorage.setItem(tabSessionKey, tabSessionId);
// 新标签可能复制 sessionStorage；发现同编号的存活标签后，为新标签换编号。
const sessionChannel = typeof BroadcastChannel === 'function' ? new BroadcastChannel(course.id+'-task-tabs') : null;
const tabInstance = newRequestId();
sessionChannel?.addEventListener('message', ({data}) => {
  if(data.instance === tabInstance || data.session !== tabSessionId) return;
  if(data.type === 'hello') sessionChannel.postMessage({type:'occupied',session:tabSessionId,to:data.instance,instance:tabInstance});
  if(data.type === 'occupied' && data.to === tabInstance) {
    tabSessionId = newRequestId();sessionStorage.setItem(tabSessionKey,tabSessionId);
  }
});
sessionChannel?.postMessage({type:'hello',session:tabSessionId,instance:tabInstance});
const taskSessionReady = new Promise(resolve => setTimeout(resolve,150));
let interactionStyle;
function styleControl() {
  const key=course.id+'-interaction-style:'+studentId+':'+tabSessionId;
  if(interactionStyle?.key!==key)interactionStyle=new window.InteractionStyle(sessionStorage,key);
  return interactionStyle;
}
const preferenceFields=['answer_length','example_density','learning_pace','explanation_order','question_frequency','teaching_sequence','style_suggestions'];
function renderStyleSuggestion(message,index) {
  const suggestion=message.styleSuggestion;
  if(!suggestion || state.sending || message!==state.chat.at(-1))return '';
  return '<section class="style-suggestion" aria-label="交互风格建议"><strong>'+esc(suggestion.label)+'</strong><p>'+esc(suggestion.reason)+'</p><p>由你决定；忽略建议会保持当前设置。</p><label>生效范围 <select class="select-field" data-style-scope><option value="next">仅下一轮</option><option value="session">本次对话（当前标签）</option><option value="long">长期保存</option></select></label><div class="form-actions"><button type="button" class="secondary-button" data-style-apply="'+index+'">应用建议</button><button type="button" class="secondary-button" data-style-dismiss="'+index+'">暂不调整</button><button type="button" class="secondary-button" data-style-disable="'+index+'">关闭主动建议</button></div></section>';
}
function renderStyleStatus() {
  const control=styleControl();
  const active=control.data.once?'已设置：仅下一轮的临时风格':Object.keys(control.data.session).length?'已设置：本次对话的临时风格':'';
  $('#chat-style-status').textContent=active;
  $('#clear-chat-style').hidden=!active;
}
async function applyStyle(values,scope) {
  const owner=studentId,control=styleControl();
  if(scope==='long')await api(`/api/students/${encodeURIComponent(owner)}/preferences`,{method:'PUT',body:JSON.stringify(values)});
  if(owner!==studentId || localStorage.getItem(studentKey)!==owner || control!==styleControl())return false;
  control.apply(values,scope,newRequestId());
  for(const message of state.chat)message.styleSuggestion=null;
  renderStyleStatus();renderChat();return true;
}
window.addEventListener('storage', event => { if(event.key === studentKey) location.reload(); });

function renderClarification(message) {
  const task=state.clarification;
  const snapshot=message.sessionPlan || (message.taskId===task?.task_id?task?.q5_session_plan:null);
  const latest=snapshot?.plan_id && state.chat.findLast(m=>m.sessionPlan?.plan_id===snapshot.plan_id)===message;
  const plan=latest && state.sessionPlan?.plan_id===snapshot.plan_id && snapshot.status!=='draft'?state.sessionPlan:snapshot;
  const card=renderSessionPlan(plan);
  if(!task || message.taskId !== task.task_id || state.chat.findLast(m=>m.taskId===task.task_id)!==message) return card;
  return card+'<div class="task-clarification"><p>'+ (task.q5_session_plan?'可以确认这份安排，或直接输入时间、范围与教法的调整。':'正在补充上一个问题；也可以取消后重新提问。')+'</p>' +
    (task.clarification?.options || []).map((option,index)=>'<button type="button" class="secondary-button" data-task-option="'+index+'" '+(state.sending?'disabled':'')+'>'+esc(option.label)+'</button>').join(' ') +
    ' <button type="button" class="secondary-button" data-task-cancel '+(state.sending?'disabled':'')+'>取消本次问题</button></div>';
}

function renderSessionPlan(plan) {
  if(!plan?.items?.length)return '';
  const kinds={explain:'讲解',example:'例子',compare:'辨析',optional_check:'可选自测（不评分）',review:'回顾'};
  const labels={planned:'未开始',in_progress:'正在学习',explained:'已讲解',skipped:'已跳过',done:'已结束'};
  return '<section class="session-study-plan" aria-label="本次学习安排" data-session-plan="'+esc(plan.plan_id)+'">'+
    '<strong>本次安排 · '+esc(plan.request.goal)+'</strong>'+(state.sessionPlanSourceStatus==='stale'&&state.sessionPlan?.plan_id===plan.plan_id?'<p role="alert">教材来源或路径已变化，请重新安排；历史来源未升级。</p>':'')+'<p>预计 '+plan.items.reduce((sum,item)=>sum+item.estimated_minutes,0)+' 分钟'+
    (plan.request.time_budget_minutes?' / 预算 '+plan.request.time_budget_minutes+' 分钟':'（可调整的估算）')+' · '+esc({draft:'待确认',active:'进行中',paused:'已暂停',done:'本次已结束'}[plan.status]||'')+'</p><ol>'+
    plan.items.map(item=>'<li data-session-item="'+esc(item.item_id)+'" '+(item.item_id===plan.current_item_id?'aria-current="step"':'')+'><strong>'+esc(item.title)+'</strong> · '+item.estimated_minutes+' 分钟 · '+esc(labels[item.status])+
      '<p>'+esc(kinds[item.kind])+'；完成标准：'+esc(item.completion_criterion)+'</p><small>顺序理由：'+esc(item.order_reason)+'；教材：'+item.source_refs.map(ref=>esc(ref.title||'原文')+'（第'+ref.chapter_id+'章 · 第'+ref.section_id+'节）').join('、')+'</small></li>').join('')+
    '</ol>'+[...(plan.request.assumptions||[]),...(plan.omitted||[]).map(value=>'未纳入：'+value)].map(value=>'<p class="session-plan-note">'+esc(value)+'</p>').join('')+
    '<small>预计用时不等于实际学习时间；活动完成不代表掌握或长期路径完成。</small></section>';
}

async function restoreClarification() {
  await taskSessionReady;
  const owner=studentId;
  try {
    const result=await api('/api/chat/tasks/pending?student_id='+encodeURIComponent(owner)+'&session_id='+encodeURIComponent(tabSessionId));
    if(owner!==studentId) return;
    state.taskRecoveryNeeded=false;
    state.clarification=result.pending?.answer_status==='awaiting_clarification'?result.pending:null;
    const sessionResult=await api('/api/course/session-plan?student_id='+encodeURIComponent(owner)+'&session_id='+encodeURIComponent(tabSessionId));
    if(owner!==studentId)return;
    state.sessionPlan=sessionResult.session_plan;
    state.sessionPlanSourceStatus=sessionResult.source_status;
    if(state.clarification && !state.chat.some(m=>m.taskId===state.clarification.task_id))
      state.chat.push({role:'assistant',content:state.clarification.reply,taskId:state.clarification.task_id});
    $('#chat-error').textContent=result.notice || '';renderChat();
  } catch(error) {
    state.taskRecoveryNeeded=true;
    $('#chat-error').innerHTML=esc('问题恢复失败：'+error.message)+' <button type="button" class="secondary-button" data-task-restore>重新恢复</button>';
  }
}

async function cancelClarification() {
  const task=state.clarification;
  if(!task) return true;
  const result=await api('/api/chat/tasks/'+encodeURIComponent(task.task_id),{method:'DELETE',body:JSON.stringify({
    student_id:studentId,session_id:tabSessionId,task_revision:task.task_revision})});
  if(result.answer_status!=='task_cancelled') { toast(result.reply || '问题状态已变化，请重新恢复');await restoreClarification();return false; }
  state.clarification=null;renderChat();toast('本次问题已取消');return true;
}

async function api(path, options = {}) {
  const response = await fetch(path, { headers: {"Content-Type":"application/json"}, cache:"no-store", ...options });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) { const error=new Error(typeof body.detail === "string" ? body.detail : `服务暂不可用（${response.status}）`);error.status=response.status;throw error; }
  return body;
}
const post = (path, data) => api(path, {method:"POST", body:JSON.stringify(data)});

function toast(message) {
  const el = $("#toast");
  el.textContent = message; el.classList.add("show");
  clearTimeout(toast.timer); toast.timer = setTimeout(() => el.classList.remove("show"), 3300);
}

function showView(view, options={}) {
  if(view==='stats')view='learning';
  if(view==='chat'){Workspace.showHelp(null);Workspace.setPane('chat');$('#chat-input').focus();return;}
  if(state.view==='quiz'&&view!=='quiz')window.ExercisePractice?.save().catch(()=>{});
  state.view=view;
  $$('.view').forEach(el=>el.classList.toggle('active',el.id===view+'-view'));
  $$('.nav-item').forEach(el=>el.classList.toggle('active',el.dataset.view===view));
  Workspace.onView(view);
  if(view==='stats')refreshStats();
  if(view==='learning'){refreshLearning();refreshStats();}
  if(view==='home')refreshLearning();
  if(view==='settings'){refreshPreferences();if($('#memory-management').open)refreshMemory();}
  if(view==='quiz'&&options.load!==false)loadQuiz(state.quizChapter||state.chapter);
  if(view==='course')requestAnimationFrame(syncPDFReader);
}

function renderTrees() {
  const html = state.chapters.map((chapter) => {
    const open = chapter.id === state.openChapter;
    const sections = chapter.sections.map((section) => `<button class="section-link ${state.chapter === chapter.id && state.section === section.id ? "active" : ""}" data-chapter="${chapter.id}" data-section="${section.id}"><span class="section-dot"></span><span>${esc(section.title)}</span></button>`).join("");
    return `<div class="chapter-group ${open ? "open" : ""}"><button class="chapter-toggle" data-open-chapter="${chapter.id}" aria-expanded="${open}"><span class="chevron">›</span><span>第${chapter.id}章&nbsp; ${esc(chapter.title)}</span></button><div class="chapter-sections">${sections}</div></div>`;
  }).join("");
  $("#course-tree").innerHTML = html;

  $("#quiz-chapter").innerHTML = state.chapters.map((c) => `<option value="${c.id}">第${c.id}章 · ${esc(c.title)}</option>`).join("");
  $("#quiz-chapter").value = String(state.quizChapter || state.chapter);
}

async function selectSection(chapter, section, {record=true,restore=false} = {}) {
  const selection = (state.selection || 0) + 1; state.selection = selection;
  // 请求成功前保留实际展示章节，防止目录显示已跳转而教材仍停在旧页。
  state.openChapter = chapter;
  renderTrees();
  for (const selector of ["#chapter-content"]) {
    const container = $(selector);
    container.querySelector(".course-navigation-loading")?.remove();
    container.setAttribute("aria-busy", "true");
    container.insertAdjacentHTML("beforeend", '<div class="course-navigation-loading" role="status">正在跳转教材…</div>');
  }
  try {
    const data = await api(`/api/course/chapters/${chapter}/sections/${section}`);
    if (selection !== state.selection) return;
    state.chapter = chapter; state.section = section; state.openChapter = chapter;
    state.contentTab = "text"; state.pdfFocus = null;
    state.sectionData = data;
    $$("[data-content-tab]").forEach(el => el.classList.toggle("active", el.dataset.contentTab === "text"));
    renderTrees();
    $("#content-subtitle").textContent = (/^第\d+章/.test(state.sectionData.title)?state.sectionData.title:`第${chapter}章 · ${state.sectionData.title}`);
    Workspace.chapterChanged();
    $("#chat-topic").textContent = `当前知识点：${state.sectionData.title}`;
    state.restoreReading=restore;
    renderContent();
    if (record) post("/api/course/views", {student_id:studentId, chapter_id:chapter, section_id:section}).then(refreshStats).catch(() => {});
    return true;
  } catch (error) {
    if (selection !== state.selection) return;
    toast(error.message);
    return false;
  } finally {
    if (selection === state.selection) {
      for (const selector of ["#chapter-content"]) {
        const container = $(selector);
        container.removeAttribute("aria-busy");
        container.querySelector(".course-navigation-loading")?.remove();
      }
    }
  }
}

function formatParagraph(text) {
  return esc(text).replace(/\[公式或对象\]/g, '<span class="object-placeholder">[公式或对象未提取]</span>');
}

function renderFigure(figure, options = {}) {
  const url = String(figure.image_url || "");
  if (!/^\/api\/figures\/(?:figure-\d+-\d+|formula-\d+-\d+|image-\d+-\d+)\/image(?:\?sha256=[a-f0-9]{64}&version=[a-f0-9]{64}&document_id=[A-Za-z0-9%:_.-]+)?$/.test(url)) return "";
  const label = String(figure.label || "").replace(/插图对象\s*\d+/g, "教材插图").replace(/公式对象\s*\d+/g, "教材公式");
  const rawCaption = String(figure.caption || "").replace(/Word 锚点 \d+，/g, "");
  const caption = rawCaption.startsWith(label) ? rawCaption.slice(label.length).replace(/^[：:\s]+/, '') : rawCaption;
  return `<figure class="textbook-figure"><a href="${esc(url)}" target="_blank" rel="noopener noreferrer"><img src="${esc(url)}" alt="${esc(options.showCaption === false ? label : label + "：" + caption)}" loading="lazy"></a>${options.showCaption === false ? "" : `<figcaption><strong>${esc(label)}</strong> ${esc(caption)}<small>来源：${esc(figure.source)}${figure.review_status === 'pending' ? ' · 待审核' : ''}</small>${figure.selection_ref ? `<button type="button" data-tutor-media="${esc(figure.id)}">返回教材</button>` : ''}</figcaption>`}</figure>`;
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
    return renderFigure(asset, {showCaption:false});
  }).join("");
}

function renderBlock(block) {
  if (block.type === "paragraph") return `<div class="textbook-paragraph">${renderSegments(block.segments)}</div>`;
  if (block.type === "image") return renderFigure(block.asset, {showCaption:false});
  if (block.type === "table") return `<div class="textbook-table-wrap" tabindex="0" aria-label="教材表格，可横向滚动"><table class="textbook-table"><tbody>${block.rows.map((row) => `<tr>${row.filter(c => !c.hidden).map(c => `<td colspan="${Number(c.colspan) || 1}" rowspan="${Number(c.rowspan) || 1}">${c.paragraphs.map(p => `<div>${renderSegments(p)}</div>`).join("")}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
  return "";
}

function renderProgress(message) {
  const stages = message.progress || [];
  const elapsed = Math.round(((message.finishedAt || Date.now()) - message.startedAt) / 1000);
  const current = stages.at(-1);
  const answerLabel={generating:'正在生成（未核验）',retrieving:'正在读取教材依据（未保存）',checking:'正在核验（未保存）',saved:'已保存',rejected:'本轮未发布'}[message.answerState];
  const title = message.pending ? (answerLabel || current?.label || "正在连接助教") : message.answerSaved && message.networkFailed ? "文字已保存，图解待恢复" : message.failed ? "处理未完成" : message.answerState==='awaiting_clarification' ? '等待补充或确认' : message.answerState==='saved' ? '已保存' : "已完成";
  return `<div class="turn-progress ${message.failed ? "failed" : ""}"><div class="progress-heading" role="status"><span class="${message.pending ? "progress-spinner" : "progress-check"}">${message.pending ? "" : message.failed ? "!" : "✓"}</span><strong>${esc(title)}</strong><span class="progress-elapsed" data-start="${message.startedAt}" data-finished="${message.finishedAt || ""}">${elapsed} 秒</span></div>${message.pending ? `<div class="progress-detail">${esc(current?.detail || "请求已发出，等待服务响应")}</div>` : ""}<details><summary>处理记录（点击展开）</summary><ol>${stages.map(p => `<li class="${p.status}"><span>${p.status === "completed" ? "✓" : message.failed ? "!" : "·"}</span><div><strong>${esc(p.label)}</strong><small>${esc(p.detail)}</small></div></li>`).join("")}</ol></details></div>`;
}

function selectionPayload(ref) {
  return ref ? {document_id:ref.document_id, version:ref.version, kind:ref.kind, rects:ref.rects, text:ref.text || ""} : undefined;
}
function renderPDFReference(ref, index, referenceIndex = -1, label = "", selectionIndex = -1) {
  if (!ref?.rects?.length) return "";
  const pages = [...new Set((ref.rects || []).map(rect => rect.page))];
  return `<button type="button" class="pdf-citation" data-pdf-citation="${index}" data-pdf-reference="${referenceIndex}" data-evidence-selection="${selectionIndex}">${label ? esc(label) + " · " : ""}教材第 ${esc(pages.join("、"))} 页 · ${esc(ref.section_title || "选中内容")} ↗</button>`;
}
function renderChatReferences(message, index) {
  // 旧记录没有行内编号时仍可按需查看，不在正文下展开来源。
  const sources=message.sources || (message.source?[message.source]:[]);
  return sources.length && !/\[\d+\]/.test(message.content || '')
    ? `<button type="button" class="legacy-citation" data-legacy-citations="${esc(message.renderKey ? 'message:'+message.renderKey : index)}">查看旧来源（未核验）</button>` : '';
}
window.renderPracticeReferences=(result,partId)=>`<span hidden data-exercise-citation="${esc(partId)}"></span>`;
let citationPopover;
function showCitation(message, key, sourceIndex, trigger) {
  citationPopover?.remove();
  const panel=document.createElement('section');
  panel.className='citation-popover';panel.setAttribute('popover','auto');panel.setAttribute('role','dialog');
  panel.setAttribute('aria-label','教材来源');
  const sources=message?.sources || (message?.source?[message.source]:[]);
  const item=message?.pdfReferences?.find(ref=>ref.source_index===sourceIndex);
  const evidence=item?.evidence;
  const source=sources[sourceIndex];
  const known=Number.isInteger(sourceIndex)&&sourceIndex>=0&&(source||item);
  const stale=evidence?.location_status==='stale';
  const status=evidence ? ({exact:'精确证据',page:'页级来源，无文字高亮',section:'小节位置，无精确高亮',stale:'来源版本已失效'}[evidence.location_status] || '无法精确定位') : '旧引用，未按新证据协议核验';
  panel.innerHTML=`<header><h3>${known?'来源 '+(sourceIndex+1):'来源暂不可用'}</h3><button type="button" data-close-citation aria-label="关闭来源">×</button></header>`+
    (sourceIndex===null?sources.map((source,i)=>`<p><button type="button" data-choose-legacy="${i}">${i+1}. ${esc(source)}</button></p>`).join(''):known?`<p class="citation-title">${esc(source || item.label || '教材')}</p><p>${esc(status)}</p>`+
      (evidence?.quote?`<blockquote>${esc(evidence.quote)}</blockquote>`:'')+
      (item?.selection_ref?.version?`<details><summary>教材版本</summary><code>${esc(item.selection_ref.version)}</code></details>`:'')+
      (stale?'<p>这条回答保存的教材版本已失效，不能跳转到新版冒充原证据。</p>':`<button type="button" class="primary-button" data-source-citation="${esc(key)}" data-source-index="${sourceIndex}">打开教材</button>`)
      : `<p>${message?.pending?'来源仍在核验，完成后可查看。':'这条回答没有对应编号的来源，未跳转到其他证据。'}</p>`);
  document.body.append(panel);citationPopover=panel;
  panel.querySelector('[data-close-citation]').onclick=()=>panel.hidePopover();
  panel.querySelectorAll('[data-choose-legacy]').forEach(button=>button.onclick=()=>showCitation(message,key,Number(button.dataset.chooseLegacy),trigger));
  panel.addEventListener('toggle',event=>{if(event.newState==='closed'&&trigger?.isConnected)trigger.focus();});
  panel.showPopover();panel.querySelector('[data-close-citation]').focus();
}
function showInlineCitation(trigger){
  const scope=trigger.closest('.message,.exercise-help,.exercise-feedback');
  const practice=scope?.querySelector('[data-exercise-citation]');
  const key=practice?'exercise:'+encodeURIComponent(practice.dataset.exerciseCitation):
    'message:'+scope?.dataset.messageKey;
  showCitation(citationMessage(key),key,Number(trigger.dataset.tutorCitation)-1,trigger);
}
function citationMessage(key){
  if(String(key).startsWith('message:'))return state.chat.find(message=>message.renderKey===String(key).slice(8));
  return String(key).startsWith('exercise:') ? window.ExercisePractice?.citationMessage(decodeURIComponent(String(key).slice(9))) : state.chat[Number(key)];
}
function renderSelectionDraft() {
  const ref=state.pdfDraft;
  const exercise=state.exerciseDraft;
  const html=exercise ? `<div class="selection-draft"><div><strong>${esc(exercise.title)}</strong><button type="button" data-clear-exercise aria-label="移除小题引用">×</button></div><p>提问将针对这道小题和已保存的作答。切换题目不会自动更换引用。</p></div>` : ref ? `<div class="selection-draft"><div><strong>已引用教材第 ${esc(ref.rects[0].page)} 页</strong><button type="button" data-clear-selection aria-label="移除教材引用">×</button></div><p>${esc(ref.text?.slice(0,160) || "所选图、公式或表格区域")}</p>${ref.kind==="area" && ref.image_refs?.[0] ? `<img src="${esc(ref.image_refs[0].image_url)}" alt="教材选区预览">` : ""}<small>本轮附带教材上下文与相关学习记录</small></div>` : "";
  $$(".chat-selection-host").forEach(el=>el.innerHTML=html);
}
async function prepareExerciseQuestion(draft) {
  if(state.sending || state.taskRecoveryNeeded) {toast('请等待当前问题结束或恢复后再选择小题');return false;}
  state.sending=true;
  try {
    if(state.clarification && !await cancelClarification()) return false;
    state.exerciseDraft=structuredClone(draft);state.pdfDraft=null;renderSelectionDraft();
    Workspace.showHelp(null);Workspace.setPane('chat');
    $('#chat-input').value='请针对这道小题给我一个提示，不要直接给完整答案。';
    $('#chat-input').dispatchEvent(new Event('input'));$('#chat-input').focus();return true;
  } finally {state.sending=false;renderChat();}
}
async function askPDFSelection(selection) {
  try {
    toast("正在定位教材选区…");
    const ref=await post("/api/pdf/selection/preview",selection);
    state.exerciseDraft=null;state.pdfDraft=ref; renderSelectionDraft();
    Workspace.showHelp(null);Workspace.setPane("chat");
    const input=$("#chat-input");
    input.value=selection.kind==="text"?"请解释我选中的这段内容。":"请解释我圈选的图、公式或表格。";
    input.dispatchEvent(new Event("input"));input.focus(); toast("选区已加入提问，可修改问题后发送");
  } catch(error) { toast(error.message); }
}
function readingMetadata(metadata) {
  const split=state.practiceCatalog?.[metadata.chapter_id];
  if(!split || split.source_version!==metadata.version) return metadata;
  const page=split.page_map.indexOf(metadata.section.page)+1;
  if(!page) return metadata;
  return {...metadata,url:split.reading_url,page_count:split.page_map.length,page_map:split.page_map,
    section:{...metadata.section,page}};
}

function startPractice(origin) {
  const chapter=origin==="ai" ? (state.pdfDraft?.chapter_id || state.chapter) : state.chapter;
  state.quizChapter=chapter;
  state.practiceTargetSection=origin==="ai" ? (state.pdfDraft?.section_id || state.section) : state.section;
  showView("quiz");
}

function syncPDFReader() {
  if(!window.TextbookPDF||!state.sectionData?.pdf)return;
  const host=$('#chapter-content .pdf-reader-host');
  if(host&&state.contentTab==='text'){
    const metadata=readingMetadata(state.sectionData.pdf);
    const focus=state.pdfFocus;
    if(focus && (focus.document_id!==metadata.document_id || focus.version!==metadata.version)){
      state.pdfFocus=null;toast('该引用的教材版本已失效，请重新提问');return;
    }
    const resume=focus?.page && !focus.rects?.length ? {page:focus.page,y:0,scale:'page-width'} : state.restoreReading?Workspace.resumeFor(metadata):null;
    window.TextbookPDF.mount(host,{...metadata,resume},state.pdfFocus,askPDFSelection);
  }
}

window.addEventListener("pdf-reader-ready",()=>{syncPDFReader();chatRenderer?.refreshMath();renderChat();});

const streamChat = window.TutorChatTransport.streamChat;

function renderContent() {
  const original = state.sectionData;
  if (!original) return;
  // 正文之外的笔记和例题线索也只取练习标题之前的讲解内容。
  const exerciseHeading=/^\s*练\s*习\s*\d+\s*\.\s*\d+\s*$/;
  const blockIndex=(original.blocks || []).findIndex(block=>exerciseHeading.test((block.segments || []).map(part=>part.text || "").join("")));
  const paragraphs=(original.content || "").split("\n");
  const lineIndex=paragraphs.findIndex(line=>exerciseHeading.test(line));
  const item={...original,content:paragraphs.slice(0,lineIndex<0?undefined:lineIndex).join("\n"),
    blocks:blockIndex<0?original.blocks:original.blocks.slice(0,blockIndex)};
  const lines = (item.content || "").split(/\n+/).map((line) => line.trim()).filter(Boolean);
  let html = `<h3>${esc(item.title)}</h3>`;
  if (state.contentTab === "text") {
    html += item.blocks?.length ? item.blocks.map(renderBlock).join("") : lines.map(line => `<p>${formatParagraph(line)}</p>`).join("");
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

  const usePDF=state.contentTab==="text" && Boolean(item.pdf);
  for(const selector of ["#chapter-content"]) {
    const container=$(selector); container.classList.toggle("pdf-active",usePDF);
    if(!usePDF||!container.querySelector('.pdf-reader-host')) {
      container.querySelectorAll('.pdf-reader-host').forEach(host=>window.TextbookPDF?.unmount(host));
      container.innerHTML=usePDF?'<div class="pdf-reader-host"></div>':html;
    }
  }
  syncPDFReader();
}

function messagesFromHistory(history) {
  return history.map((m) => ({conversationId:m.id,renderKey:m.id != null ? 'conversation:'+studentId+':'+m.id : newRequestId(),role:m.role,content:m.content,sources:m.textbook_sources || [],pdfReferences:m.pdf_references || [],imageRefs:m.image_refs || (m.selection_ref?.image_refs || []).filter(image=>image.image_url?.startsWith("/api/figures/")),selectionRef:m.selection_ref,sessionPlan:m.selection_ref?.session_study_plan,relationContext:m.selection_ref?.relation_context,guide:m.role==="assistant"?m.selection_ref?.guided_visualization:undefined,pdfImageRefs:m.role==="assistant"?(m.selection_ref?.image_refs || []).filter(image=>!image.image_url?.startsWith("/api/figures/")):[]}));
}

const graphArtifacts = new Map();
const tableArtifacts = new Map();
const relationArtifacts = new Map();
let relationCreateRequest;
async function restoreRelations(){
  try{const artifacts=await api('/api/relations?'+new URLSearchParams({student_id:studentId,session_id:tabSessionId}));
    if(!Array.isArray(artifacts))return;relationArtifacts.clear();artifacts.forEach(artifact=>relationArtifacts.set(artifact.conversation_id,artifact));renderChat();
  }catch{ /* 历史文字保持兼容。 */ }
}
async function openRelation(mode='explore',correctionOf=null){
  const button=$('#open-relation');if(state.sending||button.disabled)return;button.disabled=true;
  try{await taskSessionReady;const capability=await api('/api/relations/capabilities?'+new URLSearchParams({student_id:studentId}));if(!capability.enabled)return;
    relationCreateRequest ??= {student_id:studentId,session_id:tabSessionId,request_id:newRequestId(),expected_epoch:capability.epoch,
      template_id:$('#relation-template').value,mode,...(correctionOf?{correction_of:correctionOf}:{})};
    const artifact=await post('/api/relations',relationCreateRequest);relationCreateRequest=null;relationArtifacts.set(artifact.conversation_id,artifact);
    if(!state.chat.some(message=>message.conversationId===artifact.conversation_id))state.chat.push(...messagesFromHistory([{id:artifact.conversation_id,role:'assistant',content:
      artifact.correction_of?'订正关系性质：修改原判断后提交，本次按辅助作答记录。':'关系图与矩阵辅助示例：A={a,b,c}。行是起点，列是终点；选中关系或性质可以提问。'}]));
    renderChat();showView('chat');chatRenderer.rows.get('conversation:'+studentId+':'+artifact.conversation_id)?.element.scrollIntoView({block:'nearest'});
  }catch(error){if(error.status&&error.status<500)relationCreateRequest=null;toast(error.message);}finally{button.disabled=false;}
}
let tableCreateRequest;
async function restoreTables() {
  try {
    const artifacts=await api('/api/truth-tables?'+new URLSearchParams({student_id:studentId,session_id:tabSessionId}));
    if(!Array.isArray(artifacts))return;
    tableArtifacts.clear();artifacts.forEach(artifact=>tableArtifacts.set(artifact.conversation_id,artifact));renderChat();
  }catch{ /* 保持旧版文字历史兼容。 */ }
}
async function openTruthTable(template='implies',correctionOf=null) {
  const button=$('#open-truth-table');
  if(state.sending||button.disabled)return;
  button.disabled=true;
  try {
    await taskSessionReady;
    const capability=await api('/api/truth-tables/capabilities?'+new URLSearchParams({student_id:studentId}));
    if(!capability.enabled)return;
    tableCreateRequest ??= {student_id:studentId,session_id:tabSessionId,request_id:newRequestId(),expected_epoch:capability.epoch,
      template_id:template,mode:'assessment',...(correctionOf?{correction_of:correctionOf}:{})};
    const artifact=await post('/api/truth-tables',tableCreateRequest);tableCreateRequest=null;
    tableArtifacts.set(artifact.conversation_id,artifact);
    if(!state.chat.some(message=>message.conversationId===artifact.conversation_id))state.chat.push(...messagesFromHistory([{id:artifact.conversation_id,role:'assistant',content:
      artifact.correction_of?'订正真值表：修改原答案后再次提交，按辅助作答记录。':'真值表辅助练习：'+artifact.formula+'。填写每行结果；选中一行可以向 AI 提问。'}]));
    renderChat();showView('chat');
    chatRenderer.rows.get('conversation:'+studentId+':'+artifact.conversation_id)?.element.scrollIntoView({block:'nearest'});
  }catch(error){if(error.status&&error.status<500)tableCreateRequest=null;toast(error.message);}
  finally{button.disabled=false;}
}
let graphCreateRequest;
async function restoreGraphs() {
  await restoreRelations();
  await restoreTables();
  try {
    const artifacts=await api('/api/visualizations?'+new URLSearchParams({student_id:studentId,session_id:tabSessionId}));
    if(!Array.isArray(artifacts)) return;
    graphArtifacts.clear();
    artifacts.forEach(artifact=>graphArtifacts.set(artifact.conversation_id,artifact));
    renderChat();
  } catch { /* 旧后端不提供互动接口时，文字历史仍可阅读。 */ }
}

async function refreshGraphCapability() {
  const button=$('#open-euler-graph');
  if(!button) return;
  try {
    const capability=await api('/api/visualizations/capabilities?'+new URLSearchParams({student_id:studentId}));
    button.hidden=!capability.enabled;
    $('#open-truth-table').hidden=!capability.enabled;
    $('#truth-table-template').hidden=!capability.enabled;
    $('#open-relation').hidden=!capability.enabled;
    $('#relation-template').hidden=!capability.enabled;
  } catch {button.hidden=true;}
}

async function openEulerGraph(graph=null, forQuestion=false, mode='explore', correctionOf=null) {
  const button=$('#open-euler-graph');
  if((state.sending && !forQuestion) || button.disabled) return;
  button.disabled=true;
  try {
    await taskSessionReady;
    const capability=await api('/api/visualizations/capabilities?'+new URLSearchParams({student_id:studentId}));
    if(!capability.enabled) return null;
    graphCreateRequest ??= {student_id:studentId,session_id:tabSessionId,request_id:newRequestId(),expected_epoch:capability.epoch,template_id:'euler-cycle-v1',mode,...(graph?{graph}:{}),...(correctionOf?{correction_of:correctionOf}:{})};
    const artifact=await post('/api/visualizations',graphCreateRequest);
    graphCreateRequest=null;
    graphArtifacts.set(artifact.conversation_id,artifact);
    if(!state.chat.some(message=>message.conversationId===artifact.conversation_id)) {
      const rows=messagesFromHistory([{id:artifact.conversation_id,role:'assistant',content:artifact.attempt?.correction?'订正这道图题：已保留原作答，请修改后重新提交。订正按辅助作答记录。':'辅助示例：欧拉通路与回路。增删边，观察度数与连通性。此图不是教材原图。'}]);
      if(state.sending) state.chat.splice(Math.max(0,state.chat.length-2),0,...rows);
      else state.chat.push(...rows);
    }
    renderChat();showView('chat');
    const row=chatRenderer.rows.get('conversation:'+studentId+':'+artifact.conversation_id);
    row?.element.scrollIntoView({block:'nearest'});
    return artifact;
  } catch(error) {
    if(error.status && error.status<500) graphCreateRequest=null;
    toast(error.message);
  } finally {button.disabled=false;}
}

const emptyChatMessage = {renderKey:'empty',role:'assistant',content:'选一节教材开始阅读。你可以划选文字或圈选图、公式，再向我提问。'};
const answerMarkup = new WeakMap();
function renderAnswerContent(message) {
  if (!message.content) return '';
  if (message.role !== 'assistant') return '<p>'+esc(message.content)+'</p>';
  const previous=answerMarkup.get(message);
  const streaming=message.answerState==='generating';
  const media=JSON.stringify(message.imageRefs || []);
  if (previous?.content===message.content && previous.streaming===streaming && previous.media===media && previous.renderer===window.TutorMarkdown) return previous.html;
  const html=window.renderTutorAnswer(message.content,{streaming,media:message.imageRefs || []});
  // 进度变化不重新解析整条正文；消息删除后缓存随对象释放。
  answerMarkup.set(message,{content:message.content,streaming,media,renderer:window.TutorMarkdown,html});
  return html;
}
let chatRenderer;
function renderChat() {
  const messages=state.chat.length?state.chat:[emptyChatMessage];
  const el=$('#chat-messages');const nearBottom=el.scrollHeight-el.scrollTop-el.clientHeight<100;
  chatRenderer ??= new window.ChatMessageRenderer(el, p => window.TextbookPDF?.renderMath(p));
  chatRenderer.render(messages.map((m,index)=>({key:m.renderKey ??= newRequestId(),role:m.role,parts:{
    progress:m.startedAt?renderProgress(m):'',
    object:m.objectLabel?'<small>针对：'+esc(m.objectLabel)+'</small>':'',
    content:renderAnswerContent(m),
    references:renderChatReferences(m,index),clarification:renderClarification(m),style:renderStyleSuggestion(m,index),
    memory:m.memorySummary?'<div class="memory-summary">'+esc(m.memorySummary)+'</div>':'',
    figures:(m.role==='assistant'?(m.imageRefs||[]):[]).filter(image=>!m.content?.includes('(media:'+image.id+')')).map(image=>
      image.sha256 && image.version && image.document_id && image.image_url?.includes('?sha256=')
        ? renderFigure(image) : '<small>历史图片缺少版本绑定，保留原回答文字。</small>').join(''),
    retry:m.failed&&m.request?'<button type="button" class="secondary-button retry-message" data-retry-message="'+index+'">'+(m.networkFailed?'重试原请求':'重新提问')+'</button>':'',
  }})));
  for(const message of messages) {
    if(message.role!=='assistant'||!window.GuidedVisualization)continue;
    const artifact=relationArtifacts.get(message.conversationId)||tableArtifacts.get(message.conversationId)||graphArtifacts.get(message.conversationId);
    const guide=message.guide||(artifact?window.GuidedVisualization.fromLegacy(artifact):null);
    if(!guide?.frames?.length)continue;
    try{chatRenderer.attachComponent(message.renderKey,'guided',window.GuidedVisualization,{guide,
      onSource:reference=>openGuideSource(guide,reference)
    });}catch(error){$('#chat-error').textContent='分步讲解加载失败：'+error.message;}
  }
  // 用户查看上方内容时，新消息也不强制拉回底部。
  if(nearBottom)el.scrollTop=el.scrollHeight;
}

async function openGuideSource(guide,reference){
  try{
    if(guide.exercise_target){showView('quiz');await window.ExercisePractice.openTarget(guide.exercise_target);return;}
    const ok=await selectSection(reference.chapter_id,reference.section_id,{record:false});
    if(ok){state.pdfFocus=reference;showView('course');syncPDFReader();}
  }catch(error){toast(error.message);}
}

async function sendMessage(message, options={}) {
  const text = message.trim();
  if (!text || state.sending) return;
  if(state.taskRecoveryNeeded) { toast('请先恢复问题状态，再继续提问');return; }
  await taskSessionReady;
  if(state.sending) return;
  const selection=options.visualization || options.truthTable || options.relation ? null : options.payload ? options.selection : state.pdfDraft;
  const exercise=options.visualization || options.truthTable || options.relation ? null : options.payload ? options.exercise : state.exerciseDraft;
  state.sending = true;
  $$(".chat-input button").forEach(button => button.disabled = true);
  $("#chat-error").textContent = "";
  const pending = {role:"assistant", content:"", pending:true, startedAt:Date.now(), progress:[], request:{text,selection,exercise}};
  const styleSnapshot=styleControl().snapshot();
  const owner = studentId;
  const isCurrent = () => owner === studentId && localStorage.getItem(studentKey) === owner && state.chat.includes(pending);
  function showAnswer(result, finished) {
    if (!isCurrent()) return;
    if(result.answer_status==='answered')styleControl().consume(pending.request.styleOnceId);
    if(finished)pending.styleSuggestion=styleControl().observe(result);
    renderStyleStatus();
    Object.assign(pending, {taskId:result.task_id, conversationId:result.conversation_id, pending:!finished, networkFailed:false,
      answerSettled:true,answerState:result.answer_status==='answered'?'saved':result.answer_status==='awaiting_clarification'?'awaiting_clarification':'rejected',
      failed:['quality_rejected','task_failed','evidence_rejected','visualization_changed','visualization_unavailable','q5_error','session_plan_changed'].includes(result.answer_status),
      content:result.reply || "助教暂时没有返回内容。",
      sources:result.textbook_sources || [], pdfReferences:result.pdf_references || [], imageRefs:result.image_refs || [],
      selectionRef:result.selection_ref, pdfImageRefs:result.pdf_image_refs || [], memorySummary:result.memory_summary,
      sessionPlan:result.q5_session_plan || result.session_plan || result.q5_status?.session_plan,
      relationContext:result.answer_status==='answered'?result.relation_context:undefined,
      guide:result.answer_status==='answered'||(!result.answer_status&&result.guided_visualization)?result.guided_visualization:undefined});
    state.sessionPlan=result.session_plan || result.q5_status?.session_plan || state.sessionPlan;
    if(result.session_plan || result.q5_status?.session_plan)state.sessionPlanSourceStatus='current';
    if (finished) pending.finishedAt = Date.now();
    else pending.answerSaved = true;
    renderChat();
  }
  state.chat.push({role:"user", content:text, selectionRef:selection,objectLabel:exercise?.title || selection?.section_title}, pending);
  renderChat();
  const timer = setInterval(() => {
    $$(".progress-elapsed").forEach(el => {
      if (!el.dataset.finished) el.textContent = `${Math.round((Date.now() - Number(el.dataset.start))/1000)} 秒`;
    });
  }, 1000);
  try {
    let visualization=options.visualization;
    const truthTable=options.truthTable;
    const relation=options.relation;
    const objectKey=JSON.stringify({selection:selectionPayload(selection),exercise:exercise?.target,visualization,truthTable,relation});
    if((selection || exercise || visualization || truthTable || relation) && state.clarification && !options.payload && !options.selectedOption &&
        objectKey!==state.clarificationObject && !await cancelClarification()) throw new Error('请确认当前问题后重试');
    const task=state.clarification;
    if(exercise && !options.payload) await window.ExercisePractice?.flushTarget(exercise.target);
    const payload=options.payload || {student_id:studentId, account_type:"test", message:text,
      session_id:tabSessionId,request_id:newRequestId(),
      style_overrides:styleSnapshot.values,
      ...(task?{task_id:task.task_id,task_revision:task.task_revision}:{}),
      ...(options.selectedOption?{selected_option:options.selectedOption}:{}),
      learning_goal:exercise?.knowledgePoint || selection?.section_title || state.sectionData?.title || course.title,
      // 补充旧任务时使用服务端原对象；当前阅读位置不能覆盖已选澄清选项。
      reader_location:task || selection || exercise || visualization || truthTable || relation ? undefined : (state.sectionData ? {chapter_id:state.chapter, section_id:state.section} : undefined),
      selection:task ? undefined : selectionPayload(selection),exercise_target:task ? undefined : exercise?.target,
      visualization_target:task ? undefined : visualization,truth_table_target:task ? undefined : truthTable,relation_target:task ? undefined : relation};
    if(payload.relation_target)pending.objectLabel='当前关系 · '+payload.relation_target.property+' · 版本 '+payload.relation_target.expected_revision;
    if(payload.truth_table_target)pending.objectLabel='当前真值表 · 指派 '+payload.truth_table_target.row_id+' · 版本 '+payload.truth_table_target.expected_revision;
    if(payload.visualization_target) pending.objectLabel='当前辅助图 · 版本 '+payload.visualization_target.expected_revision;
    pending.request.payload=payload;
    pending.request.styleOnceId=options.styleOnceId || (!options.payload?styleSnapshot.onceId:undefined);
    const result = await streamChat(payload, progress => {
        if (!isCurrent()) return;
        const index = pending.progress.findIndex(item => item.order === progress.order);
        if (index >= 0) pending.progress[index] = progress;
        else pending.progress.push(progress);
        renderChat();
      }, result => showAnswer(result, false), (event,data)=>{
        if(!isCurrent()||!window.TutorChatTransport.applyDraft(pending,event,data))return;
        // 合并同一动画帧的 SDK 分片，保留稳定消息节点和滚动位置。
        if(!pending.draftFrame)pending.draftFrame=requestAnimationFrame(()=>{
          pending.draftFrame=null;if(isCurrent())renderChat();
        });
      });
    if (!isCurrent()) return;
    state.clarification=result.answer_status==='awaiting_clarification'?result:null;
    state.clarificationObject=state.clarification?objectKey:null;
    showAnswer(result, true); refreshStats();
    if(['task_conflict','task_expired','task_not_found','task_busy','request_conflict','memory_deleted','invalid_option','task_disabled'].includes(result.answer_status)) await restoreClarification();
  } catch (error) {
    if (!isCurrent()) return;
    Object.assign(pending, {pending:false, answerSettled:true,answerState:pending.answerSaved?'saved':'rejected',failed:!pending.answerSaved, networkFailed:!!pending.request.payload && (!error.status || error.status>=500), finishedAt:Date.now()});
    if (!pending.answerSaved) pending.content = error.message;
    renderChat();
    $("#chat-error").textContent = error.message;

    toast(pending.answerSaved ? "文字已保存，图解连接中断；稍后刷新可查看" : "本次回答未完成，处理记录已保留");
  } finally {
    clearInterval(timer);
    state.sending = false;
    $$(".chat-input button").forEach(button => button.disabled = false);
    renderChat();
  }
}

async function loadQuiz(chapter=state.quizChapter||state.chapter){const section=state.practiceTargetSection;state.practiceTargetSection=null;return window.ExercisePractice?.resume(chapter,section);}

async function submitQuiz(form) {
  const quiz=state.quiz;
  if(!quiz)return;
  const answers = {};
  for (const q of quiz.questions) {
    const checked = form.querySelector(`input[name="${q.id}"]:checked`);
    if (!checked) { toast("请完成每道题再提交"); return; }
    answers[q.id] = Number(checked.value);
  }
  const button = form.querySelector("button[type=submit]"); button.disabled = true;
  try {
    const result = await post(`/api/course/chapters/${quiz.chapter_id}/quiz`, {student_id:studentId, answers});
    const detail = result.items.map((item, index) => `<div class="answer-feedback ${item.is_correct ? "" : "wrong"}">${index + 1}. ${item.is_correct ? "回答正确" : `正确答案：${esc(quiz.questions[index].options[item.correct])}`} · ${esc(item.explanation)}</div>`).join("");
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
      ["规则判分平均分", data.exercise_stats?.confirmed_average == null ? "暂无规则评分" : `${data.exercise_stats.confirmed_average} 分`],
      ["教材作答", `${data.exercise_stats?.answered_parts || 0} 个小题`],
      ["答疑次数", `${data.chat_turns} 次`],
    ];
    $("#stats-summary").innerHTML = metrics.map(([label,value]) => `<div class="summary-tile"><span>${label}</span><strong>${esc(value)}</strong></div>`).join("");
    const maxCount = Math.max(1, ...data.activity.map((d) => d.count));
    $("#activity-chart").innerHTML = data.activity.map((d) => `<div class="day-bar"><span>${d.count}</span><div class="bar-track"><div class="bar-fill" style="height:${Math.max(2,Math.round(d.count/maxCount*100))}%"></div></div><span>${esc(d.day.slice(5))}</span></div>`).join("");
    $("#chapter-scores").innerHTML = data.chapter_scores.length ? data.chapter_scores.map((row) => `<div class="score-row"><span>${esc(row.title)}</span><div class="score-track"><div class="score-fill" style="width:${row.score}%"></div></div><strong>${row.score} 分</strong></div>`).join("") : '<div class="resource-note">尚无基础自测成绩。教材逐题作答进度和规则评分见上方；AI 参考评分保存在各题反馈中。</div>';
    const knowledge = data.knowledge || [];
    const errors = data.common_errors || [];
    $("#knowledge-mastery").innerHTML = knowledge.length ? knowledge.map((row) => `<div class="score-row"><span>${esc(row.point)}</span><div class="score-track"><div class="score-fill" style="width:${Math.round(row.mastery*100)}%"></div></div><strong>${Math.round(row.mastery*100)}%</strong></div>`).join("") : '<div class="resource-note">完成答疑或练习后，会逐步形成知识掌握估计（未校准）。</div>';
    $("#common-errors").innerHTML = errors.length ? errors.map((row) => `<div class="history-item"><small>第${row.chapter_id}章 · 错 ${row.wrong_count} 次</small><p>${esc(row.question)}</p><p>参考答案：${esc(row.correct_option)}</p>${row.question_id ? `<button type="button" class="secondary-button" data-exercise-review="${esc(row.question_id)}" data-review-chapter="${row.chapter_id}">回到这道题</button>` : ""}</div>`).join("") : '<div class="resource-note">目前还没有错题记录。</div>';
  } catch (error) { toast(`统计暂不可用：${error.message}`); }
}

async function refreshLearning() {
  try {
    const [review, history] = await Promise.all([
      api(`/api/students/${encodeURIComponent(studentId)}/review`),
      api(`/api/students/${encodeURIComponent(studentId)}/conversation`),
    ]);
    $("#review-list").innerHTML = review.length ? review.map((item) => `<div class="review-item"><div><strong>${esc(item.point)}</strong><p>${esc(item.reason)}</p></div>${item.question_id ? `<button data-exercise-review="${esc(item.question_id)}" data-review-chapter="${item.chapter_id}">回到这道题</button>` : `<button data-review="${esc(item.point)}">请助教带我复习</button>`}</div>`).join("") : '<div class="resource-note">暂时没有识别到需要复习的难点。继续学习或完成测验后再来看看。</div>';
    $('#home-review-list').innerHTML=$('#review-list').innerHTML;
    $("#history-list").innerHTML = history.length ? history.slice(-16).reverse().map((m) => `<div class="history-item"><small>${m.role === "user" ? "我" : "助教"}</small><p>${esc(m.content)}</p>${(m.role==='assistant'?(m.image_refs || []):[]).map(renderFigure).join("")}</div>`).join("") : '<div class="resource-note">还没有对话记录。向助教提一个问题吧。</div>';
  } catch (error) { toast(`学习记录暂不可用：${error.message}`); }
}

async function refreshPreferences() {
  try {
    const values = await api(`/api/students/${encodeURIComponent(studentId)}/preferences`);
    const form = $("#settings-form");
    const effective={...values,...styleControl().snapshot().values};
    for (const name of preferenceFields) {
      const field = form.elements.namedItem(name);
      const value=effective[name] ?? (name==='style_suggestions'?1:0.5);
      field.value = String(name==='style_suggestions'?(value<.34?0:1):(value<.34?0:value>.66?1:.5));
    }
  } catch (error) { toast(error.message); }
}

async function savePreferences(form) {
  const data = Object.fromEntries(preferenceFields.map((name) => [name, Number(form.elements.namedItem(name).value)]));
  const scope=form.elements.namedItem('preference_scope').value;
  try {
    if(!await applyStyle(data,scope))return;
    $("#settings-status").textContent = scope==='long'?"已长期保存，下一轮起生效":scope==='next'?"已确认，仅下一轮生效":"已确认，本次对话生效（当前标签）";
    if ($("#memory-management").open) refreshMemory();
    toast("风格设置已确认");
  } catch (error) { $("#settings-status").textContent = error.message; }
}


function applyCourseCollapse(){
 const collapsed=localStorage.getItem(course.id+'-course-collapsed')==='true';
 $('#course-panel-body').hidden=collapsed||state.view==='quiz';
 const b=$('#course-collapse');b.setAttribute('aria-expanded',String(!collapsed));b.setAttribute('aria-label',collapsed?'展开章节目录':'收起章节目录');b.textContent=collapsed?'›':'⌄';
}

function bindEvents() {
  $("#course-collapse").addEventListener("click", () => {
    const collapsed = $("#course-panel-body").hidden;
    localStorage.setItem(course.id+'-course-collapsed', String(!collapsed));
    applyCourseCollapse();
  });
  document.addEventListener("click", (event) => {
    const styleButton=event.target.closest('[data-style-apply],[data-style-dismiss],[data-style-disable]');
    if(styleButton){
      if(state.sending)return;
      const index=Number(styleButton.dataset.styleApply ?? styleButton.dataset.styleDismiss ?? styleButton.dataset.styleDisable);
      const message=state.chat[index];
      if(!message?.styleSuggestion || message!==state.chat.at(-1))return;
      const card=styleButton.closest('.style-suggestion');
      card.querySelectorAll('button').forEach(button=>button.disabled=true);
      (async()=>{
        if(styleButton.hasAttribute('data-style-apply')){
          if(!await applyStyle(message.styleSuggestion.values,card.querySelector('[data-style-scope]').value))return;
          toast('已确认，从下一轮起按所选范围应用');
        }else if(styleButton.hasAttribute('data-style-disable')){
          if(!await applyStyle({style_suggestions:0},'long'))return;
          toast('已关闭主动建议，可在个性化设置中重新开启');
        }else styleControl().dismiss();
        message.styleSuggestion=null;renderChat();
      })().catch(error=>{toast(error.message);card.querySelectorAll('button').forEach(button=>button.disabled=false);});
      return;
    }
    const relationFocus=event.target.closest('[data-relation-focus]');
    if(relationFocus){
      const context=state.chat[Number(relationFocus.dataset.relationFocus)]?.relationContext;
      if(!context)return;
      const root=[...document.querySelectorAll('.interactive-relation')].find(element=>element.dataset.artifactId===context.artifact_id);
      if(!root){toast('未找到这张关系图，它可能已删除或不在当前会话，请重新打开后提问。');return;}
      const detail={...context};
      const focused=!root.dispatchEvent(new CustomEvent('relation-focus',{detail,cancelable:true}));
      if(!focused)toast(detail.error || '暂时无法查看这张图的依据。');
      return;
    }
    const inlineCitation=event.target.closest('[data-tutor-citation]');
    const mediaButton=event.target.closest('[data-tutor-media]');
    if(mediaButton){
      const key=mediaButton.closest('[data-message-key]')?.dataset.messageKey;
      const image=citationMessage('message:'+key)?.imageRefs?.find(item=>item.id===mediaButton.dataset.tutorMedia);
      if(image?.selection_ref){
        (async()=>{
          const checked=await post('/api/course/citation-state',{reference:{selection_ref:image.selection_ref}});
          if(checked.stale)throw new Error('原图对应的教材版本已失效');
          if(await selectSection(image.chapter_id,image.section_id,{record:false})){
            state.pdfFocus=image.selection_ref;showView('course');syncPDFReader();
            if(!image.selection_ref.rects?.length)toast('已打开教材小节，未提供精确原图区域');
          }
        })().catch(error=>toast(error.message));
      }
      return;
    }
    if(inlineCitation){event.preventDefault();showInlineCitation(inlineCitation);return;}
    const legacy=event.target.closest('[data-legacy-citations]');
    if(legacy){const key=legacy.dataset.legacyCitations;const message=citationMessage(key);showCitation(message,key,null,legacy);return;}
    const sourceCitation=event.target.closest('[data-source-citation]');
    if(sourceCitation){
      const message=citationMessage(sourceCitation.dataset.sourceCitation);
      const sourceIndex=Number(sourceCitation.dataset.sourceIndex);
      if(!message||sourceCitation.disabled)return;
      sourceCitation.disabled=true;
      (async()=>{
        const item=message.pdfReferences?.find(item=>item.source_index===sourceIndex);
        if(item){const checked=await post('/api/course/citation-state',{reference:item});if(checked.stale)throw new Error('保存的教材版本已失效，请重新提问核验');}
        let reference=item?.selection_ref;
        if(!reference){
          const source=(message.sources || (message.source?[message.source]:[]))[sourceIndex];
          const located=await api('/api/course/citation-location',{method:'POST',body:JSON.stringify({source,response:String(message.content||'').slice(0,30000)})});
          reference=located.selection_ref;
          message.pdfReferences ||= [];
          message.pdfReferences.push({source_index:sourceIndex,...located});
        }
        if(!reference)throw new Error('该来源无法定位');
        const ok=await selectSection(reference.chapter_id,reference.section_id,{record:false});
        if(!ok)return;
        state.pdfFocus=reference;showView('course');syncPDFReader();
        if(!reference.rects?.length)toast(reference.location_kind==='page'?'已打开来源页，没有精确文字高亮':'已打开教材小节，没有精确证据位置');
        else if(reference.location_kind==='section_heading')toast('旧引用仅记录了小节标题，不代表结论的精确原文');
      })().catch(error=>toast(error.message)).finally(()=>{sourceCitation.disabled=false;});
      return;
    }
    const practice=event.target.closest("[data-start-practice]");
    if(practice){startPractice(practice.dataset.startPractice);return;}
    const clear=event.target.closest("[data-clear-selection]");
    if(clear){state.pdfDraft=null;renderSelectionDraft();return;}
    const citation=event.target.closest("[data-pdf-citation]");
    if(citation){
      const message=citationMessage(citation.dataset.pdfCitation);
      const referenceIndex=Number(citation.dataset.pdfReference ?? -1);
      const item=referenceIndex>=0 ? message?.pdfReferences?.[referenceIndex] : null;
      const selectionIndex=Number(citation.dataset.evidenceSelection ?? -1);
      const ref=selectionIndex>=0 ? item?.evidence?.selections?.[selectionIndex] : item?.selection_ref || message?.selectionRef;
      if(ref) selectSection(ref.chapter_id,ref.section_id,{record:false}).then(ok=>{if(!ok)return;state.pdfFocus=ref;showView("course");syncPDFReader();}).catch(error=>toast(error.message));
      return;
    }
    const retry=event.target.closest('[data-retry-message]');
    if(retry){const old=state.chat[Number(retry.dataset.retryMessage)],request=old?.request;if(request&&!state.sending){if(old.networkFailed){sendMessage(request.text,{payload:request.payload,styleOnceId:request.styleOnceId,selection:request.selection,exercise:request.exercise});return;}state.exerciseDraft=request.exercise;state.pdfDraft=request.selection;renderSelectionDraft();$('#chat-input').value=request.text;$('#chat-input').dispatchEvent(new Event('input'));showView('chat');}return;}
    if(event.target.closest('[data-clear-exercise]')) {if(!state.sending){state.sending=true;cancelClarification().then(ok=>{if(ok){state.exerciseDraft=null;renderSelectionDraft();}}).catch(error=>toast(error.message)).finally(()=>{state.sending=false;renderChat();});}return;}
    if(event.target.closest('[data-task-restore]')) {restoreClarification();return;}
    if(event.target.closest('[data-task-cancel]')) {if(!state.sending){state.sending=true;renderChat();cancelClarification().catch(error=>toast(error.message)).finally(()=>{state.sending=false;renderChat();});}return;}
    const taskOption=event.target.closest('[data-task-option]');
    if(taskOption) {const option=state.clarification?.clarification?.options?.[Number(taskOption.dataset.taskOption)];if(option&&!state.sending)sendMessage(option.label,{selectedOption:option.id});return;}
    const nav = event.target.closest("[data-view]");
    if (nav) { showView(nav.dataset.view); return; }
    const toggle = event.target.closest("[data-open-chapter]");
    if (toggle) { const number = Number(toggle.dataset.openChapter); state.openChapter = state.openChapter === number ? 0 : number; renderTrees(); return; }
    const section = event.target.closest("[data-chapter][data-section]");
    if (section) { showView("course");selectSection(Number(section.dataset.chapter), Number(section.dataset.section)); return; }
    const prompt = event.target.closest("[data-prompt]");
    if (prompt) { const input = $("#chat-input"); input.value = prompt.dataset.prompt; input.focus(); return; }
    const review = event.target.closest("[data-review]");
    if (review) { showView("chat"); $("#chat-input").value = `请帮我复习${review.dataset.review}，先出一道简单的问题检查我`; $("#chat-input").focus(); return; }
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
  for (const [formSelector,inputSelector] of [["#chat-form","#chat-input"]]) {
    $(formSelector).addEventListener("submit", (event) => { event.preventDefault(); if (state.sending) return; if(state.taskRecoveryNeeded){toast('请先恢复问题状态，再继续提问');return;} const input = $(inputSelector); const value = input.value; input.value = "";Workspace.clearDraft();Workspace.showHelp(null); sendMessage(value); });
  }
  $("#quiz-chapter").addEventListener("change", (event) => { loadQuiz(Number(event.target.value)); });
  $("#quiz-area").addEventListener("submit", (event) => { if (event.target.id === "quiz-form") { event.preventDefault(); submitQuiz(event.target); } });
  $("#settings-form").addEventListener("submit", (event) => { event.preventDefault(); savePreferences(event.target); });
  $("#search-form").addEventListener("submit", async (event) => {
    event.preventDefault(); const value = $("#global-search").value.trim(); if (!value) return;
    try {
      const results = await api(`/api/course/search?q=${encodeURIComponent(value)}`);
      const match = results[0];
      if (match) { await selectSection(match.chapter_id, match.section_id); showView("course"); toast(`已找到：${match.title}`); }
      else { showView("chat"); $("#chat-input").value = value; $("#chat-input").focus(); toast("教材暂未匹配到；你可以直接问助教"); }
    } catch (error) { toast(`搜索失败：${error.message}`); }
  });
}

async function init() {
  Workspace.bind();bindEvents(); applyCourseCollapse(); renderChat();
  try {
    const [chapters,catalog]=await Promise.all([api("/api/course/chapters"),api(course.reading_map_url)]);
    state.chapters=chapters;state.practiceCatalog=catalog;
    renderTrees();
    const last=Workspace.lastReading();
    const resume=state.chapters.find(c=>c.id===last?.chapter)?.sections.find(s=>s.id===last?.section);
    if(resume)await selectSection(last.chapter,last.section,{record:false,restore:true});
    else if(state.chapters[0]?.sections[0])await selectSection(state.chapters[0].id,state.chapters[0].sections[0].id,{record:false});
  } catch (error) { $("#course-tree").textContent = `教材读取失败：${error.message}`; toast(error.message); }
  try {
    const history = await api(`/api/students/${encodeURIComponent(studentId)}/conversation`);
    state.chat = messagesFromHistory(history); renderChat();
  } catch { /* New local demo student has no history. */ }
  await restoreClarification();
  await restoreGraphs();
  await refreshGraphCapability();
  refreshStats();
}

init();
$('#open-euler-graph')?.addEventListener('click',()=>openEulerGraph());
$('#open-truth-table')?.addEventListener('click',()=>openTruthTable($('#truth-table-template').value));
$('#open-relation')?.addEventListener('click',()=>openRelation());


let memoryRequest = 0;
const memoryBase = () => '/api/students/' + encodeURIComponent(studentId) + '/memory';
const preferenceNames = {answer_length:'回答长度', example_density:'举例频率', learning_pace:'学习节奏',explanation_order:'讲解顺序',question_frequency:'追问频率',teaching_sequence:'讲练顺序',style_suggestions:'主动风格建议'};
const misconceptionNames = {hypothesis:'候选判断', supported:'有支持记录', confirmed:'多次支持', dismissed:'已否认', resolved:'已纠正'};
async function refreshMemory(point) {
  const request = ++memoryRequest;
  let overviewLoaded=false;
  $('#memory-status').textContent = '正在读取记忆…';
  try {
    const overview = await api(memoryBase());
    overviewLoaded=true;
    if (request !== memoryRequest) return;
    $('#memory-preferences').innerHTML = overview.preferences.map((item) => '<div class="history-item"><strong>' + esc(preferenceNames[item.key] || item.key) + '</strong>：' + esc(item.value) + '<small> · ' + (item.source === 'explicit_user' ? '你保存的设置' : '旧记录，来源未核实') + '</small>' + (preferenceNames[item.key] ? ' <button type="button" class="secondary-button" data-forget-pref="' + esc(item.key) + '">清除这个偏好</button>' : '') + '</div>').join('') || '<p>尚未保存明确偏好。</p>';
    const selected = point || $('#memory-point').value;
    const target = overview.points.includes(selected) ? selected : overview.points[0];
    $('#memory-point').innerHTML = overview.points.map((name) => '<option value="' + esc(name) + '" ' + (name === target ? 'selected' : '') + '>' + esc(name) + '</option>').join('');
    $('#memory-forget-point').disabled = !target;
    if (!target) { $('#memory-detail').innerHTML = '<p>暂无知识点学习记忆。</p>'; $('#memory-status').textContent = ''; return; }
    const data = await api(memoryBase() + '?point=' + encodeURIComponent(target));
    if (request !== memoryRequest) return;
    const detail = data.detail;
    const skills = (detail.skills || []).map((item) => '<div class="review-item"><strong>' + esc(item.name) + '</strong><p>技能估计：' + Math.round(item.mastery_estimate * 100) + '% · 独立小题：' + item.independent_items + ' · ' + (item.needs_review ? '待复习，错误原因需诊断' : '当前记录中这些小题已答对') + '</p><small>未校准；只反映已映射规则小题，不表示全章已掌握。</small>' + item.sources.map((source) => '<small>来源：' + esc(source.question_id) + '/' + esc(source.part_id) + ' · 事件 ' + esc(source.event_id) + '</small>').join('') + '</div>').join('');
    const misconceptions = detail.misconceptions.map((item) => '<div class="review-item"><strong>' + esc(item.description) + '</strong><small>误区 #' + item.id + ' · ' + esc(misconceptionNames[item.status] || item.status) + '</small>' + (['hypothesis','supported','confirmed'].includes(item.status) ? '<form data-memory-correction="' + item.id + '"><label>这个判断不符合你的情况？<textarea name="note" maxlength="1000" required placeholder="说明哪里不符合你的情况"></textarea></label><button class="secondary-button" type="submit">提交更正</button></form>' : '') + '</div>').join('');
    const evidence = detail.evidence.map((item) => '<div class="history-item"><small>证据 #' + item.id + ' · ' + (item.verification === 'student_statement' ? '你的陈述' : item.verification === 'rule_verified' ? '规则核验' : '尚未独立核实') + ' · 来源事件 ' + esc(item.event_id || '旧记录，来源不明') + '</small><p>' + esc(item.content) + '</p>' + (item.source_quote ? '<p>学生原文：' + esc(item.source_quote) + '</p>' : '') + '</div>').join('');
    const events = detail.events.map((item) => '<div class="history-item"><small>事件 ' + esc(item.id) + ' · ' + esc(item.type) + '</small><p>' + esc(item.content || '作答记录，详情保留在练习页面') + '</p></div>').join('');
    const summaries = detail.background_memory.map((item) => '<div class="history-item"><small>候选摘要 #' + item.id + ' · 来源事件 ' + esc(item.event_id) + '</small>' + item.content.notes.map((note) => '<p>' + esc(note.quote) + '</p><small>原文事件：' + esc(note.event_id) + '</small>').join('') + (item.content.reflection ? '<p>观察：' + esc(item.content.reflection.reason) + '</p>' : '') + '</div>').join('');
    $('#memory-detail').innerHTML = '<p>当前掌握估计：' + Math.round(detail.state.mastery * 100) + '%（未校准，不能视为已学会的概率）。</p><h3>规则练习技能</h3>' + (skills || '<p>暂无符合条件的独立规则题技能测量。</p>') + '<h3>误区判断</h3>' + (misconceptions || '<p>暂无误区判断。</p>') + '<details><summary>最近证据与来源（最多 20 条）</summary>' + (evidence || '<p>暂无证据。</p>') + '</details><details><summary>最近学习事件（最多 20 条）</summary>' + events + '</details><p>有效后台摘要：' + detail.background_memory.length + ' 条。摘要是候选历史，不作为能力或教材依据。</p><details><summary>查看摘要正文与来源</summary>' + (summaries || '<p>暂无有效摘要。</p>') + '</details>';
    $('#memory-status').textContent = overview.scope;
  } catch (error) {
    if(request!==memoryRequest)return;
    if(!overviewLoaded&&error.status===404){
      $('#memory-preferences').innerHTML='<p>尚未保存明确偏好。</p>';
      $('#memory-point').innerHTML='';$('#memory-forget-point').disabled=true;
      $('#memory-detail').innerHTML='<p>暂无知识点学习记忆。阅读、提问或完成练习后，可以在这里查看记录。</p>';
      $('#memory-status').textContent='';
    }else $('#memory-status').textContent=error.message;
  }
}
$('#memory-management').addEventListener('toggle', () => { if ($('#memory-management').open) refreshMemory(); });
$('#memory-refresh').addEventListener('click', () => refreshMemory());
$('#memory-point').addEventListener('change', () => refreshMemory($('#memory-point').value));
$('#memory-preferences').addEventListener('click', async (event) => {
  const button = event.target.closest('[data-forget-pref]');
  if (!button) return;
  button.disabled = true;
  try { await api(memoryBase() + '/preferences/' + encodeURIComponent(button.dataset.forgetPref), {method:'DELETE'}); await refreshPreferences(); await refreshMemory(); }
  catch (error) { $('#memory-status').textContent = error.message; button.disabled = false; }
});
$('#memory-detail').addEventListener('submit', async (event) => {
  const form = event.target.closest('[data-memory-correction]');
  if (!form) return;
  event.preventDefault();
  const note = form.elements.note.value.trim();
  if (!note) { $('#memory-status').textContent = '请填写更正说明。'; return; }
  const button = form.querySelector('button'); button.disabled = true;
  try { await post(memoryBase() + '/misconceptions/' + form.dataset.memoryCorrection + '/correction', {note}); await refreshMemory(); }
  catch (error) { $('#memory-status').textContent = error.message; button.disabled = false; }
});
$('#memory-forget-point').addEventListener('click', async (event) => {
  const point = $('#memory-point').value;
  if (!point) return;
  if (state.sending) { toast('请等待本轮回答结束后再删除记忆。'); return; }
  if (!window.confirm('删除“' + point + '”的学习记忆？对应对话、判断和摘要会移除，练习成绩保留。此操作无法撤销。')) return;
  const button = event.target; button.disabled = true;
  try {
    await api(memoryBase() + '/points?point=' + encodeURIComponent(point), {method:'DELETE'});
    // 先移除本地旧对话，再从后台恢复未被删除的记录。
    state.chat = []; state.clarification=null;state.taskRecoveryNeeded=true;graphArtifacts.clear();graphCreateRequest=null;tableArtifacts.clear();tableCreateRequest=null;relationArtifacts.clear();relationCreateRequest=null;renderChat();
    await refreshMemory();refreshStats();refreshLearning();
    try {
      const history = await api('/api/students/' + encodeURIComponent(studentId) + '/conversation');
      // 等待期间若已开始新提问，保留当前流式回答。
      if (!state.sending) { state.chat = messagesFromHistory(history); renderChat();await restoreGraphs(); }
      toast('已删除该知识点的学习记忆');
    } catch {
      toast('记忆已删除；剩余对话读取失败，请刷新页面查看');
    }
    await restoreClarification();
  }
  catch (error) { $('#memory-status').textContent = error.message; button.disabled = false; }
});

$('#clear-chat-style').addEventListener('click',()=>{if(state.sending){toast('请等待本轮回答结束');return;}styleControl().clear();renderStyleStatus();refreshPreferences();toast('已恢复长期风格设置');});
renderStyleStatus();
