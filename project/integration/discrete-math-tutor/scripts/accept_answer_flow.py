"""固定心理学问题的真实模型基线；只写临时学生库，报告保留原始失败。"""
import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--case', action='append', dest='case_ids')
    parser.add_argument('--baseline', action='store_true', help='仅禁用直接解释分流，其余保持当前执行链路')
    parser.add_argument('--visualization', action='store_true', help='开启真实图解，并追加变量比较、设计比较和流程图案例')
    args = parser.parse_args()
    cases = json.loads((ROOT/'tests/data/answer_flow/psychology.json').read_text(encoding='utf-8'))
    if args.visualization:
        cases += [
            {'id': 'visual_variables', 'message': '请结合教材解释自变量和因变量的区别，并说明额外变量为什么会干扰结论。',
             'required': '变量区分正确，先保存文字；有图解时来源及历史恢复完整'},
            {'id': 'visual_designs', 'message': '被试间设计、被试内设计和混合设计有什么区别？请结合教材和图解说明。',
             'required': '三种设计区分正确，不混淆每人一个与多个水平'},
            {'id': 'visual_custom_flow', 'message': '请用一个辅助示例解释双盲实验的实施流程，配合分步图解并引用教材。',
             'required': '辅助示例明确标注，双盲角色正确；模型图解通过校验后发布'},
            {'id': 'visual_original_missing', 'message': '请严格复现教材图4-999的原图，并解释图中所有数值；不要辅助示例或替代图。',
             'required': '没有对应原图或数据时必须拒绝，不得用辅助图解替代'},
        ]
    if args.case_ids:
        unknown = set(args.case_ids) - {case['id'] for case in cases}
        if unknown:
            parser.error('未知案例：' + ', '.join(sorted(unknown)))
        cases = [case for case in cases if case['id'] in args.case_ids]
    if args.output.exists():
        parser.error('报告已存在，请使用新文件名以保留此前结果')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(ROOT))
    with tempfile.TemporaryDirectory(prefix='answer-flow-') as directory:
        os.environ.update(TUTOR_COURSE='experimental-psychology-3', LLM_MOCK='0',
                          DATABASE_URL='sqlite:///'+str(Path(directory)/'learning.db'),
                          COURSE_DATABASE_URL='sqlite:///'+str(Path(directory)/'psychology.db'),
                          MEMORY_WORKER_ENABLED='0', VISUALIZATION_ON_DEMAND='1' if args.visualization else '0')
        from llm.client import LLMClient
        from agents.task_execution import TaskExecution
        from models.chat_request import ChatRequest
        from database.database import engine
        if engine.url.get_backend_name() != 'sqlite' or Path(engine.url.database).resolve().parent != Path(directory).resolve():
            raise RuntimeError('验收只允许使用本次临时数据库')
        calls = []
        original = LLMClient.chat

        def measured(client, messages, *positional, **options):
            started = time.monotonic()
            system = str(messages[0].get('content', '')) if messages else ''
            agent = system.split(']')[0]+']' if system.startswith('[AGENT:') else 'course-model'
            record = {'agent': agent, 'status': 'failed'}
            calls.append(record)
            options.setdefault('timeout', 30)
            try:
                result = original(client, messages, *positional, **options)
                record['status'] = 'returned'
                if agent in ('[AGENT:response_generator]', '[AGENT:quality_checker]'):
                    record['generated_text'] = result
                return result
            finally:
                record['seconds'] = round(time.monotonic()-started, 3)

        LLMClient.chat = measured
        original_selection = TaskExecution.can_answer_directly
        if args.baseline:
            TaskExecution.can_answer_directly = lambda *args: False
        report = {'method': '原API执行器含TaskService；真实模型；固定教材问题；各案例独立合成学生；临时SQLite；计时从进入API执行器开始，不含网络/浏览器绘制；不等同学习收益测量',
                  'visualization': args.visualization,
                  'baseline': args.baseline, 'cases': []}
        try:
            from main import orchestrator as tutor, _run_turn
            report['model'] = tutor.llm.model
            report['mock'] = tutor.llm.mock
            if tutor.llm.mock:
                raise RuntimeError('真实验收禁止使用模拟模型')
            for case in cases:
                sid = 'answer-flow-'+case['id']
                tutor.memory.ensure_student(sid)
                tutor.memory.set_active_goal(sid, '随机区组设计' if case.get('history') else '实验心理学的研究方法')
                for entry in case.get('history', []):
                    tutor.memory.append(sid, entry['role'], entry['content'])
                before = {point: tutor.memory.get_state(sid, point).model_dump()
                          for point in tutor.memory.list_knowledge_points(sid)}
                calls.clear()
                stages = []
                started = time.monotonic()

                def progress(stage, label, detail=''):
                    now = time.monotonic()
                    if stages:
                        stages[-1]['seconds'] = round(now-started-stages[-1]['start_seconds'], 3)
                    stages.append({'stage': stage, 'start_seconds': round(now-started, 3)})

                print('开始：'+case['id'], flush=True)
                row = {'id': case['id'], 'question': case['message'], 'required': case['required'], 'states_before': before}
                def answer_ready(answer):
                    row['text_ready_seconds'] = round(time.monotonic()-started, 3)
                    row['calls_before_text'] = len(calls)
                    row['early_answer'] = answer
                    history = tutor.memory.repo.get_conversation_with_figures(sid)
                    row['text_durable_before_visual'] = any(item['id'] == answer['conversation_id'] and
                        item['content'] == answer['reply'] for item in history)
                    assert row['text_durable_before_visual'], '提前展示前必须已保存文字'
                    print(json.dumps({'id': case['id'], 'event': 'answer', 'seconds': row['text_ready_seconds']}, ensure_ascii=False), flush=True)

                try:
                    request = ChatRequest(student_id=sid, message=case['message'], account_type='production',
                        session_id='answer-flow-'+case['id'], request_id='answer-flow-'+case['id'])
                    result = _run_turn(request, progress, answer_ready=answer_ready)
                    row['result'] = result
                    row['state_after'] = tutor.memory.get_state(sid, result.get('knowledge_point', '')).model_dump()
                    if args.visualization and result.get('answer_status') == 'answered':
                        history = tutor.memory.repo.get_conversation_with_figures(sid)
                        stored = next((item for item in history if item['id'] == result.get('conversation_id')), None)
                        row['guide_restores_from_history'] = bool(stored) and (stored.get('selection_ref') or {}).get('guided_visualization') == result.get('guided_visualization')
                        assert row['guide_restores_from_history'], '历史必须包含同一回答及最终图解'
                        row['history_count'] = len(history)
                        previous_calls = len(calls)
                        replay = _run_turn(request)
                        row['replay_matches'] = replay == result
                        row['replay_added_model_calls'] = len(calls)-previous_calls
                        row['replay_added_messages'] = len(tutor.memory.repo.get_conversation_with_figures(sid))-len(history)
                        assert row['replay_matches'] and row['replay_added_model_calls'] == 0 and row['replay_added_messages'] == 0, '重试必须重放最终结果'

                except Exception as exc:
                    row['error_type'] = type(exc).__name__
                elapsed = time.monotonic()-started
                if stages:
                    stages[-1]['seconds'] = round(elapsed-stages[-1]['start_seconds'], 3)
                row.update(seconds=round(elapsed, 3), model_calls=list(calls), stages=stages)
                report['cases'].append(row)
                args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
                print(json.dumps({'id': case['id'], 'status': row.get('result', {}).get('answer_status', row.get('error_type')),
                                  'calls': len(calls), 'seconds': row['seconds'], 'text_ready': row.get('text_ready_seconds'),
                                  'visualization': row.get('result', {}).get('visualization_status'), 'error': row.get('error_type')}, ensure_ascii=False), flush=True)
        finally:
            LLMClient.chat = original
            TaskExecution.can_answer_directly = original_selection
            engine.dispose()


if __name__ == '__main__':
    main()
