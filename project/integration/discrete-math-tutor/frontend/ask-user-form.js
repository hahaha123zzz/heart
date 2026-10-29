"use strict";

// 按 DeepTutor AskUserOptions 的 questions/问题 ID 契约适配；不依赖 React。
(function (root) {
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function questions(clarification) {
    return clarification?.mode === 'ask_user' ? (clarification.ask_user?.questions || clarification.questions || []) : [];
  }
  function answers(items, draft) {
    return items.map(q => {
      const value = draft[q.id] || {};
      const selected = (value.selected || []).filter(i => Number.isInteger(i) && q.options?.[i]);
      if (!q.multi_select && selected.length > 1) throw new Error('单选问题只能选择一项');
      const parts = selected.map(i => q.options[i].label);
      if (q.allow_free_text !== false && value.text?.trim()) parts.push(value.text.trim());
      if (!parts.length) throw new Error('请回答每一个问题后提交');
      return {questionId:q.id, text:parts.join('；')};
    });
  }
  function render(items, draft, disabled) {
    return items.map((q, index) => {
      const value = draft[q.id] || {};
      return '<fieldset '+(disabled?'disabled':'')+'><legend>'+esc(q.header || '问题 '+(index+1))+'：'+esc(q.prompt)+'</legend>'+
        (q.options || []).map((option, i) => '<label style="display:block"><input type="'+(q.multi_select?'checkbox':'radio')+'" name="ask-'+index+'" data-ask-question="'+index+'" data-ask-option="'+i+'" '+((value.selected||[]).includes(i)?'checked':'')+'> '+esc(option.label)+(option.description?' — '+esc(option.description):'')+'</label>').join('')+
        (q.allow_free_text !== false?'<label>补充回答<textarea maxlength="2000" data-ask-question="'+index+'" data-ask-text aria-label="'+esc(q.prompt)+'">'+esc(value.text || '')+'</textarea></label>':'')+'</fieldset>';
    }).join('')+'<button type="button" class="secondary-button" data-ask-submit '+(disabled?'disabled':'')+'>提交全部回答</button>';
  }
  root.TutorAskUser = {questions, answers, render};
})(typeof window === 'undefined' ? globalThis : window);
