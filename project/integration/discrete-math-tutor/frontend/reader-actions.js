"use strict";
// 只消费本次已保存任务的动作；历史/恢复不自动执行。
window.TutorReaderActions = (() => {
  const seen = new Set();
  async function apply(action, result, {current, navigate, acknowledge}) {
    if (!action || action.status !== 'requested' || seen.has(action.action_id) ||
        result.reader_action_replay || result._transportRecovered || result.answer_status !== 'answered' ||
        action.task_id !== result.task_id || !Number.isInteger(result.task_revision)) return null;
    seen.add(action.action_id);
    let status = 'rejected', reason = '页面已切换、正在选区或当前任务已变化', observed = {};
    try {
      if (current()) {
        observed = await navigate(action, current);
        if (current() && observed.document_id === action.document_id &&
            observed.version === action.version && observed.page === action.page) {
          status = 'applied'; reason = '';
        } else reason = '阅读器未确认到达目标页';
      }
    } catch (error) { reason = String(error.message || error).slice(0, 200); }
    return acknowledge({...observed, action_id: action.action_id, task_revision: result.task_revision, status, reason});
  }
  return {apply};
})();
