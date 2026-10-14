"""服务端只读构建任务对象，不采纳客户端预览文字或能力标签。"""
import hashlib
import json
import math
from knowledge.course import get_section
from knowledge.pdf_reader import resolve_selection, document
from models.task_context import TaskContext, TaskObject


class TaskContextBuilder:
    def build(self, *, student_id, message, knowledge_point="", history=(), known_points=(),
              reader_location=None, selection=None, exercise_target=None,
              session_id="legacy", request_id=None, resolved_selection=None, preferences=None,
              visualization_target=None, mark_graph_assisted=True, truth_table_target=None, relation_target=None):
        objects = []
        graph_snapshot = None
        truth_table_snapshot = None
        relation_snapshot = None
        if relation_target is not None:
            from visualization.relation import RelationService, POINT as RELATION_POINT,CLOSURE_POINT,target_key
            from visualization.relation_validator import PROPERTIES
            relation_snapshot=RelationService().snapshot(relation_target,student_id,session_id,mark_assisted=mark_graph_assisted)
            snapshot=relation_snapshot
            text='论域 A={a,b,c}；R={'+','.join('('+p['source']+','+p['target']+')' for p in snapshot['pairs'])+'}；关注'+PROPERTIES[snapshot['property']]+'性。'
            if snapshot['selected_pair']:text+='选中序偶：('+snapshot['selected_pair']['source']+','+snapshot['selected_pair']['target']+')。'
            closure=snapshot.get('closure')
            if closure:text+='正在查看'+closure['label']+'第'+str(closure['step'])+'步；'+closure['reason']
            objects.append(TaskObject(id=target_key(snapshot),kind='relation',title=(CLOSURE_POINT if closure else RELATION_POINT)+'（辅助关系，'+PROPERTIES[snapshot['property']]+'）',
                text=text,chapter_id=9,section_id=5 if closure else 4,version=str(snapshot['revision'])))
        if truth_table_target is not None:
            from visualization.truth_table import TruthTableService, POINT as TABLE_POINT
            truth_table_snapshot = TruthTableService().snapshot(truth_table_target, student_id, session_id,
                mark_assisted=mark_graph_assisted)
            snapshot = truth_table_snapshot
            text = '公式：'+snapshot['formula']+'；当前行：'+', '.join(key+'='+str(int(value)) for key,value in snapshot['assignment'].items())+'。'
            objects.append(TaskObject(id='truth-table:'+snapshot['artifact_id']+':'+snapshot['row_id'], kind='truth_table',
                title=TABLE_POINT+'（辅助真值表 '+snapshot['formula']+'，指派 '+snapshot['row_id']+'）',
                text=text, chapter_id=4, section_id=3, version=str(snapshot['revision'])))
        if visualization_target is not None:
            from visualization.service import VisualizationService, POINT
            graph_snapshot = VisualizationService().snapshot(visualization_target, student_id, session_id,
                mark_assisted=mark_graph_assisted)
            graph = graph_snapshot['graph']
            text = '顶点：' + '、'.join(n['id'] for n in graph['nodes']) + '。边：' + '、'.join(e['source']+'-'+e['target'] for e in graph['edges']) + '。'
            objects.append(TaskObject(id='visualization:'+graph_snapshot['artifact_id'], kind='visualization',
                title=POINT+'（辅助图，'+str(len(graph['edges']))+' 条边）', text=text, chapter_id=7, section_id=7,
                version=str(graph_snapshot['revision'])))
        if selection is not None and exercise_target is not None:
            raise ValueError("教材选区与练习小题不能同时作为目标")
        if reader_location is not None:
            section = get_section(reader_location.chapter_id, reader_location.section_id)
            if section is None:
                raise ValueError("教材章节或小节不存在")
            record = document(f"chapter-{reader_location.chapter_id:02d}")
            objects.append(TaskObject(id=f"section:{reader_location.chapter_id}:{reader_location.section_id}",
                kind="section", title=section["title"][:200], text=section["content"][:1000],
                chapter_id=reader_location.chapter_id, section_id=reader_location.section_id,
                version=record["version"] if record else ""))
        if selection is not None:
            # resolved_selection 只能由服务端定位调用链传入，不在请求模型中暴露。
            resolved = resolved_selection if resolved_selection is not None else resolve_selection(selection)
            reference = resolved["reference"]
            key = hashlib.sha256(json.dumps({"document_id": reference["document_id"],
                "version": reference["version"], "rects": reference["rects"]}, sort_keys=True).encode()).hexdigest()
            objects.append(TaskObject(id="selection:" + key, kind="pdf_selection",
                title=reference["section_title"][:200], text=resolved["text"][:1800],
                chapter_id=reference["chapter_id"], section_id=reference["section_id"], version=reference["version"]))
            if reader_location is not None and reader_location.chapter_id != reference["chapter_id"]:
                raise ValueError("选区与教材章节不一致，请重新选择")
        if exercise_target is not None:
            from practice_api import catalog
            from knowledge.exercise_text import block_text
            data = catalog()
            if exercise_target.version != data["version"]:
                raise ValueError("题库已更新，请重新选择题目")
            question = data["by_id"].get(exercise_target.question_id)
            part = next((p for p in question["parts"] if p["id"] == exercise_target.part_id), None) if question else None
            if part is None:
                raise ValueError("练习题或小题不存在")
            record = document(question["source"]["document_id"])
            if record is None or record["version"] != question["source_version"]:
                raise ValueError("习题教材版本已更新")
            if reader_location is not None and reader_location.chapter_id != question["chapter_id"]:
                raise ValueError("练习与教材章节不一致")
            # 仅读共享条件与该小题，不读取答案、他人草稿或评分记录。
            text = "\n".join(block_text(b) for b in question.get("shared_blocks", []) + part["blocks"])
            objects.append(TaskObject(id=f"exercise:{question['id']}:{part['id']}:{data['version']}",
                kind="exercise_part", title=(question["knowledge_point"] + " " + part["label"])[:200],
                text=text[:1800], chapter_id=question["chapter_id"], section_id=question["section_id"], version=data["version"]))
        safe_preferences = {k: float(v) for k, v in (preferences or {}).items()
            if k in ("answer_length", "example_density", "learning_pace") and type(v) in (int, float)
            and math.isfinite(v) and 0 <= v <= 1}
        bounded_history = [{"role": row["role"], "content": row["content"][:1200]}
            for row in list(history)[-4:] if row.get("role") in ("user", "assistant") and isinstance(row.get("content"), str)]
        return TaskContext(student_id=student_id, session_id=session_id, request_id=request_id,
            message=message, knowledge_point=knowledge_point[:200], history=bounded_history,
            known_points=[p[:128] for p in list(known_points)[-20:] if isinstance(p, str)],
            objects=objects, preferences=safe_preferences, graph_snapshot=graph_snapshot, truth_table_snapshot=truth_table_snapshot,relation_snapshot=relation_snapshot)

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
