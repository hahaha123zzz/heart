(function(root){
 'use strict';
 const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const labels={start:'现在复习',defer:'延后一天',finish:'确认完成',return:'返回原学习'};
 const statuses={due:'已到期',upcoming:'已安排',deferred:'已延后',active:'复习中',source_unavailable:'待核对'};
 const known=new Map(),pending=new Map();let handlers={};
 function render(items){
  if(!Array.isArray(items)||!items.length)return '<div class="resource-note">暂时没有回顾建议或待订正记录。继续学习或完成练习后再来看看。</div>';
  return items.map(item=>{
   if(item.kind==='scheduled_review'){
    if(typeof item.review_id!=='string'||!/^[a-f0-9]{32}$/.test(item.review_id)||!Number.isInteger(item.revision))return '';
    known.set(item.review_id,item);if(known.size>200)known.delete(known.keys().next().value);
    const moment=(item.deferred_until||item.due_at)*1000;
    const date=Number.isFinite(moment)?new Date(moment).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai'}):'时间待核对';
    const actions=Array.isArray(item.allowed_actions)?item.allowed_actions.filter(a=>labels[a]):[];
    return '<div class="review-item" data-scheduled-review="'+item.review_id+'"><div><strong>'+esc(item.point)+'</strong><p>'+esc(item.reason)+'</p><small>正式复习 · '+esc(statuses[item.status]||'待核对')+' · '+esc(date)+'（北京时间）</small></div><div class="review-actions">'+actions.map(action=>'<button type="button" data-review-action="'+action+'" data-review-id="'+item.review_id+'">'+(action==='start'&&item.status==='upcoming'?'提前复习':labels[action])+'</button>').join('')+'<small role="status" aria-live="polite" data-review-notice></small></div></div>';
   }
   return '<div class="review-item"><div><strong>'+esc(item.point)+'</strong><p>'+esc(item.reason)+'</p>'+(item.kind==='learning_followup'?'<small>回顾建议 · 非正式评分</small>':'')+(item.location_label?'<small>'+esc(item.location_label)+'</small>':'')+'</div>'+(item.kind==='review_unavailable'?'':item.question_id?'<button data-exercise-review="'+esc(item.question_id)+'" data-review-chapter="'+esc(item.chapter_id)+'">回到这道题</button>':'<button data-review="'+esc(item.point)+'">'+(item.kind==='learning_followup'?'回顾这个知识点':'请助教带我复习')+'</button>')+'</div>';
  }).join('');
 }
 async function act(reviewId,action){
  const row=known.get(reviewId);if(!row||!labels[action]||!row.allowed_actions?.includes(action)||!handlers.act)return false;
  let state=pending.get(reviewId);if(state?.sending)return false;
  if(!state||state.action!==action)state={action,payload:{conversation_id:row.conversation_id,review_id:reviewId,
   action,command_id:root.crypto?.randomUUID?.()||String(Date.now())+Math.random().toString(36).slice(2),base_revision:row.revision,delay_hours:24}};
  state.sending=true;pending.set(reviewId,state);let conflicted=false;
  const elements=root.document?.querySelectorAll('[data-scheduled-review="'+reviewId+'"]')||[];
  const notify=message=>elements.forEach(el=>{const out=el.querySelector('[data-review-notice]');if(out)out.textContent=message});
  elements.forEach(el=>el.querySelectorAll('button').forEach(b=>b.disabled=true));notify('正在保存…');
  try{
   const result=await handlers.act(state.payload);if(!result||!Array.isArray(result.reviews))throw Error('操作未确认，请重试');
   state.sending=false;pending.delete(reviewId);notify('已保存');await handlers.onUpdate?.(result);return result;
  }catch(error){state.sending=false;if(error.status===409){pending.delete(reviewId);conflicted=!!handlers.onConflict;handlers.onConflict?.()}notify(error.message||'操作未确认，请重试');return false}
  finally{if(!conflicted)elements.forEach(el=>el.querySelectorAll('button').forEach(b=>b.disabled=false))}
 }
 root.LearningReview={render,act,bind:options=>{handlers=options||{}}};
 root.document?.addEventListener('click',event=>{const b=event.target.closest?.('[data-review-action]');if(b)act(b.dataset.reviewId,b.dataset.reviewAction)});
 if(typeof module!=='undefined')module.exports=root.LearningReview;
})(typeof window==='undefined'?globalThis:window);
