"""从原生持久事件恢复已交付题卡，供原版 ContextBuilder 读取。"""
from functools import wraps
import json

from .native_delivery import public_quiz


def install_question_history():
    from deeptutor.services.session.sqlite_store import SQLiteSessionStore
    from . import learning_tool_adapter

    original = SQLiteSessionStore.get_messages_for_context
    if getattr(original, '_heart_question_history', False):
        return

    @wraps(original)
    async def get_messages(store, session_id, leaf_message_id=None):
        rows = await original(store, session_id, leaf_message_id=leaf_message_id)
        current = learning_tool_adapter.current_learning_context()
        if current is None or current.session_id != session_id:
            return rows
        output = []
        for row in rows:
            if row.get('role') == 'assistant' and not row.get('metadata', {}).get('model_turn'):
                trace = await store.get_message_trace(session_id, row['id'], limit=1)
                if trace and trace.get('turn_id'):
                    turn = await store.get_turn(trace['turn_id'])
                    if turn and turn['status'] == 'completed' and turn['capability'] == 'deep_question':
                        events = await store.get_turn_events(trace['turn_id'])
                        result = next((e.get('metadata') or {} for e in reversed(events)
                                       if e.get('type') == 'result'), {})
                        if result.get('summary') is not None and result.get('mode') != 'followup':
                            try:
                                quiz = public_quiz(result)
                            except ValueError:
                                pass
                            else:
                                # 题卡来自已持久化结果；不让探索阶段的前言冒充最终交付。
                                content = quiz['response'] + '\n已交付题卡：\n' + json.dumps(
                                    quiz['summary']['results'], ensure_ascii=False)
                                row = {**row, 'content': content}
            output.append(row)
        return output

    get_messages._heart_question_history = True
    SQLiteSessionStore.get_messages_for_context = get_messages
