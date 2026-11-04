(function(root){
 'use strict';
 const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const text=value=>typeof value==='string'&&value.length<=1200;
 const prose=value=>esc(value.replace(/\[\d+\]/g,''));
 const refs=indices=>Array.isArray(indices)?[...new Set(indices.filter(n=>Number.isInteger(n)&&n>0))].slice(0,6).map(n=>'<sup><button type="button" data-tutor-citation="'+n+'" aria-label="查看来源 '+n+'">'+n+'</button></sup>').join(''):'';
 let handlers={};const known=new Map(),submissions=new Map(),expansions=new Map();
 const id=()=>root.crypto?.randomUUID?.()||String(Date.now())+Math.random().toString(36).slice(2);
 function question(card){
  const q=card.question;if(!q||typeof q.prompt!=='string'||q.prompt.length>2000||!Array.isArray(q.options)||q.options.length>8)return '';
  const actions=Array.isArray(card.allowed_actions)?card.allowed_actions:[],available=typeof handlers.onAction==='function';
  const disabled=!available||submissions.get(card.card_id)?.sending;
  const button=(action,label)=>actions.includes(action)?'<button type="button" data-card-action="'+action+'"'+(disabled?' disabled':'')+'>'+label+'</button>':'';
  const options=q.question_type==='choice'?q.options.map(o=>'<label><input type="radio" name="card-answer-'+esc(card.card_id)+'" value="'+esc(o.id)+'"'+(card.learner_answer===o.id?' checked':'')+(actions.includes('submit_answer')?'':' disabled')+'> '+esc(o.label)+' · '+esc(o.body)+'</label>').join(''):'<label>你的回答<textarea data-card-answer rows="3" maxlength="4000"'+(actions.includes('submit_answer')?'':' disabled')+'>'+esc(card.learner_answer||'')+'</textarea></label>';
  const verdict=card.status==='graded'?'<p>'+(card.assessment?.verification==='voided'?'本次评分已作废':card.assessment?.is_correct===true?'本次作答正确':card.assessment?.is_correct===false?'本次作答需继续复核':'本次未评分')+'</p>':card.status==='answered'?'<p>作答已保存'+(q.question_type==='open'?'，等待 rubric 复核':'')+'。</p>':card.status==='abandoned'?'<p>'+(card.disposition==='defer'?'已延后':'本题已结束')+'，未计成绩。</p>':'';
  return '<section class="learning-card" data-learning-card="'+esc(card.card_id)+'" data-card-revision="'+card.revision+'" data-card-schema="learning-cards/v2" data-card-kind="assessment_question"><h4>'+esc(card.title)+'</h4><p>'+prose(q.prompt)+'</p><fieldset><legend>作答</legend>'+options+'</fieldset><div class="learning-card-actions">'+button('submit_answer','提交答案')+button('grade','核验评分')+button('request_hint','请求提示')+button('view_explanation','查看完整解释')+button('defer','延后')+button('skip','跳过')+button('return_path','返回学习路径')+'</div>'+verdict+(card.feedback?.text?'<p class="learning-card-feedback">'+prose(card.feedback.text)+'</p>':'')+'<p role="status" aria-live="polite" data-card-notice>'+(!available?'测评动作尚未启用。':'')+'</p></section>';
 }
 function render(cards,context={}){
  if(!Array.isArray(cards))return '';
  return cards.slice(0,4).map(card=>{
   if(!['learning-cards/v1','learning-cards/v2'].includes(card?.schema)||!text(card.title)||!text(card.card_id)||!Number.isInteger(card.revision))return '';
   if(card.kind==='learning_progress')return '';
   known.set(card.card_id,{card,context});if(known.size>200)known.delete(known.keys().next().value);
   if(card.kind==='assessment_question')return card.schema==='learning-cards/v2'?question(card):'';
   let expanded=[];
   try{expanded=JSON.parse(root.sessionStorage?.getItem('learning-card:'+card.card_id+':'+card.revision)||'[]');if(!Array.isArray(expanded))expanded=[]}catch{}
   const open=index=>Array.isArray(card.expanded)?(card.expanded.includes(index)?' open':''):(expanded[index]===true?' open':'');
   let body='';
   if(card.kind==='learning_progress'){
    if(typeof card.explained!=='boolean'||typeof card.pending!=='boolean'||!Number.isInteger(card.formative_attempts)||card.formative_attempts<0)return '';
    const evidence=card.evidence_summary;
    body='<p>'+(card.explained?'已讲解':'正在学习')+(card.pending?' · 有一道待答检查':'')+'</p><p>'+(evidence?'已核验证据 '+Number(evidence.reviewed||0)+' 条；独立 '+Number(evidence.independent||0)+' 条，辅助 '+Number(evidence.assisted||0)+' 条。':card.formative_attempts?'已记录 '+card.formative_attempts+' 次辅助反馈，待独立验证。':'暂无作答证据。')+'</p>';
    const help=card.assistance,notes=[];
    if(help&&Number.isInteger(help.max_hint_level)&&help.max_hint_level>0&&help.max_hint_level<=3)notes.push('提示已用至第 '+help.max_hint_level+' 级');
    if(help?.full_explanation_seen===true)notes.push('已查看完整解释');
    if(notes.length)body+='<p>'+notes.join(' · ')+'。后续作答仍为辅助记录。</p>';
   }else if(card.kind==='step_reveal'){
    if(!Array.isArray(card.steps)||card.steps.length<2||card.steps.length>6||!card.steps.every(step=>text(step.title)&&text(step.body)))return '';
    body=card.steps.map((step,i)=>'<details'+open(i+1)+'><summary>第 '+(i+1)+' 步 · '+esc(step.title)+'</summary><p>'+prose(step.body)+refs(step.source_indices)+'</p></details>').join('');
   }else if(card.kind==='concept_comparison'){
    if(!Array.isArray(card.labels)||card.labels.length!==2||!card.labels.every(text)||!Array.isArray(card.rows)||card.rows.length<1||card.rows.length>6||!card.rows.every(row=>text(row.aspect)&&text(row.left)&&text(row.right)))return '';
    body='<div class="learning-card-table"><table><thead><tr><th scope="col">比较角度</th>'+card.labels.map(label=>'<th scope="col">'+esc(label)+'</th>').join('')+'</tr></thead><tbody>'+card.rows.map(row=>'<tr><th scope="row">'+esc(row.aspect)+refs(row.source_indices)+'</th><td><p>'+prose(row.left)+'</p></td><td><p>'+prose(row.right)+'</p></td></tr>').join('')+'</tbody></table></div>';
   }else return '';
   return '<details class="learning-card" data-learning-card="'+esc(card.card_id)+'" data-card-revision="'+card.revision+'" data-card-kind="'+card.kind+'"'+open(0)+'><summary>'+esc(card.title)+'</summary>'+body+'<p role="status" aria-live="polite" data-card-notice></p></details>';
  }).join('');
 }
 const notice=(element,message)=>{const p=element.querySelector('[data-card-notice]');if(p)p.textContent=message};
 async function submit(element,action,extra={}){
  const entry=known.get(element.dataset.learningCard);if(!entry)return false;
  const key=JSON.stringify([action,extra]);let state=submissions.get(entry.card.card_id);
  if(state?.sending)return false;
  if(!state||state.key!==key)state={key,command_id:id()};
  state.sending=true;submissions.set(entry.card.card_id,state);
  element.querySelectorAll('[data-card-action]').forEach(button=>button.disabled=true);notice(element,'正在保存…');
  try{
   const result=await handlers.onAction({...entry,action,command_id:state.command_id,base_revision:entry.card.revision,...extra});
   if(result===false||!Array.isArray(result?.learning_cards))throw new Error('操作未确认，请重试');
   state.sending=false;submissions.delete(entry.card.card_id);notice(element,'已保存');return result;
  }catch(error){state.sending=false;if(error.status===409){submissions.delete(entry.card.card_id);if(error.cardState)handlers.onUpdate?.(error.cardState,entry)}element.querySelectorAll('[data-card-action]').forEach(button=>button.disabled=false);notice(element,error.message||'未能确认操作，请重试');return false}
 }
 root.LearningCards={render,bind:options=>{handlers=options||{}},submit};
 root.document?.addEventListener('click',async event=>{
  const button=event.target.closest?.('[data-card-action]');if(!button)return;
  const element=button.closest('.learning-card'),entry=known.get(element?.dataset.learningCard);if(!entry||!handlers.onAction)return;
  const action=button.dataset.cardAction,text=action==='submit_answer'?(element.querySelector('input:checked')?.value||element.querySelector('[data-card-answer]')?.value||''):'';
  if(action==='submit_answer'&&!text.trim()){notice(element,'请先选择选项或填写回答');return}
  const result=await submit(element,action,{text});if(result)handlers.onUpdate?.(result,entry);
 });
 root.document?.addEventListener('toggle',event=>{
  const card=event.target.closest?.('.learning-card');if(!card)return;
  try{root.sessionStorage.setItem('learning-card:'+card.dataset.learningCard+':'+card.dataset.cardRevision,JSON.stringify([card,...card.querySelectorAll('details')].map(detail=>detail.open)))}catch{}
  const entry=known.get(card.dataset.learningCard);if(!entry||!entry.card.allowed_actions?.includes('set_expanded'))return;
  const persist=entry.card.schema==='learning-cards/v2'?handlers.onAction:handlers.onExpand;if(!persist)return;
  const desired=[card,...card.querySelectorAll('details')].flatMap((detail,i)=>detail.open?[i]:[]);
  if(JSON.stringify(desired)===JSON.stringify(entry.card.expanded||[]))return;
  clearTimeout(expansions.get(entry.card.card_id));
  expansions.set(entry.card.card_id,setTimeout(async()=>{
   expansions.delete(entry.card.card_id);
   try{
    const result=await persist({...entry,action:'set_expanded',expanded:desired,command_id:id(),base_revision:entry.card.schema==='learning-cards/v2'?entry.card.revision:entry.card.view_revision||0});
    if(!Array.isArray(result?.learning_cards))throw new Error('展开状态未确认');
    result.learning_cards.forEach(updated=>{const old=known.get(updated.card_id);if(old){old.card=updated;handlers.onPersist?.(updated,old.context)}});
    const saved=known.get(entry.card.card_id)?.card;
    if(Array.isArray(saved?.expanded))[card,...card.querySelectorAll('details')].forEach((detail,i)=>{detail.open=saved.expanded.includes(i)});
    notice(card,'展开状态已保存');
   }catch(error){notice(card,error.message||'展开状态未保存，请重试')}
  },80));
 },true);
 if(typeof module!=='undefined')module.exports=root.LearningCards;
})(typeof window==='undefined'?globalThis:window);
