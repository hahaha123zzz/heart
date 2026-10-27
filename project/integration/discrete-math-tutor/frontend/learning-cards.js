(function(root){
 'use strict';
 const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const text=value=>typeof value==='string'&&value.length<=1200;
 const prose=value=>esc(value.replace(/\[\d+\]/g,''));
 const refs=indices=>Array.isArray(indices)?[...new Set(indices.filter(n=>Number.isInteger(n)&&n>0))].slice(0,6).map(n=>'<sup><button type="button" data-tutor-citation="'+n+'" aria-label="查看来源 '+n+'">'+n+'</button></sup>').join(''):'';
 function render(cards){
  if(!Array.isArray(cards))return '';
  return cards.slice(0,3).map(card=>{
   if(card?.schema!=='learning-cards/v1'||!text(card.title)||!text(card.card_id)||!Number.isInteger(card.revision))return '';
   let expanded=[];
   try{expanded=JSON.parse(root.sessionStorage?.getItem('learning-card:'+card.card_id+':'+card.revision)||'[]');if(!Array.isArray(expanded))expanded=[]}catch{}
   const open=index=>expanded[index]===true?' open':'';
   let body='';
   if(card.kind==='learning_progress'){
    if(typeof card.explained!=='boolean'||typeof card.pending!=='boolean'||!Number.isInteger(card.formative_attempts)||card.formative_attempts<0)return '';
    body='<p>'+(card.explained?'已讲解':'正在学习')+(card.pending?' · 有一道待答检查':'')+'</p><p>'+(card.formative_attempts?'已记录 '+card.formative_attempts+' 次辅助反馈，待独立验证。':'暂无作答证据。')+'</p>';
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
   return '<details class="learning-card" data-learning-card="'+esc(card.card_id)+'" data-card-revision="'+card.revision+'" data-card-kind="'+card.kind+'"'+open(0)+'><summary>'+(card.kind==='learning_progress'?'学习记录 · ':'')+esc(card.title)+'</summary>'+body+'</details>';
  }).join('');
 }
 root.LearningCards={render};
 root.document?.addEventListener('toggle',event=>{
  const card=event.target.closest?.('.learning-card');if(!card)return;
  try{root.sessionStorage.setItem('learning-card:'+card.dataset.learningCard+':'+card.dataset.cardRevision,JSON.stringify([card,...card.querySelectorAll('details')].map(detail=>detail.open)))}catch{}
 },true);
 if(typeof module!=='undefined')module.exports={render};
})(typeof window==='undefined'?globalThis:window);
