"""服务端只读构建任务对象，不采纳客户端预览文字或能力标签。"""
import math
from models.task_context import TaskContext
from models.interaction_preferences import InteractionPreferences, turn_style_overrides
from agents.conversation_context import build_history


class TaskContextBuilder:
    def build(self, *, student_id, message, knowledge_point="", history=(), known_points=(),
              reader_location=None, selection=None, exercise_target=None,
              session_id="legacy", request_id=None, resolved_selection=None, preferences=None,
              visualization_target=None, mark_graph_assisted=True, truth_table_target=None, relation_target=None,
              history_budget_tokens=None):
        from knowledge.request_resources import resolve_resources
        resources = resolve_resources(student_id=student_id, session_id=session_id,
            reader_location=reader_location, selection=selection, exercise_target=exercise_target,
            visualization_target=visualization_target, truth_table_target=truth_table_target,
            relation_target=relation_target, mark_graph_assisted=mark_graph_assisted,
            resolved_selection=resolved_selection)
        objects = resources.objects
        graph_snapshot = resources.graph_snapshot
        truth_table_snapshot = resources.truth_table_snapshot
        relation_snapshot = resources.relation_snapshot
        safe_preferences = {k: float(v) for k, v in (preferences or {}).items()
            if k in InteractionPreferences.model_fields and type(v) in (int, float)
            and math.isfinite(v) and 0 <= v <= 1}
        safe_preferences.update(turn_style_overrides(message))
        history_pack = build_history(
            [row for row in history if row.get("role") in ("user", "assistant") and isinstance(row.get("content"), str)],
            budget_tokens=history_budget_tokens,
        )
        context = TaskContext(student_id=student_id, session_id=session_id, request_id=request_id,
            message=message, knowledge_point=knowledge_point[:200], history=history_pack.history,
            history_summary=history_pack.summary,
            known_points=[p[:128] for p in list(known_points)[-20:] if isinstance(p, str)],
            objects=objects, current_object_ids=[obj.id for obj in objects], preferences=safe_preferences, graph_snapshot=graph_snapshot, truth_table_snapshot=truth_table_snapshot,relation_snapshot=relation_snapshot)

        from agents.turn_context import assemble_turn
        assemble_turn(context, history_pack)
        return context

    @staticmethod
    def button_task(context, action):
        """明确对象按钮已给出动作，按校验后的对象构造任务，无模型调用。"""
        from models.task_understanding import TaskUnderstanding
        from visualization.relation import target_key
        targets = (['visualization:'+context.graph_snapshot['artifact_id']] if context.graph_snapshot else
                   ['truth-table:'+context.truth_table_snapshot['artifact_id']+':'+context.truth_table_snapshot['row_id']] if context.truth_table_snapshot else
                   [target_key(context.relation_snapshot)] if context.relation_snapshot else
                   [obj.id for obj in context.objects if obj.kind == 'exercise_part'])
        if action not in ("hint", "explain") or len(targets) != 1:
            raise ValueError("对象按钮动作或对象无效")
        return TaskUnderstanding(student_move="question", intent="continue", confidence=1.0,
            needs_context=True, learning_intents=[action], target_refs=targets,
            answer_constraints=["hint_only", "no_full_answer"] if action == "hint" else [],
            rewritten_query=context.message, reason="用户明确选择对象提问按钮")
