"""显式执行的小型真实模型验收；只发送自建教材夹具和合成偏好，不读取学生库。"""
from pathlib import Path
import argparse
import json
import os
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--env-file', required=True)
    parser.add_argument('--case', choices=['all', 'outline', 'personal_state', 'textbook'], default='all')
    args = parser.parse_args()
    from dotenv import dotenv_values
    values = dotenv_values(args.env_file)
    from llm.client import LLMClient
    from llm.execution_budget import ExecutionBudget, current_budget
    from agents.agent_loop import LocalAgentLoop, LoopRequest
    from agents.q3_tools import build_registry
    from agents.tools.first_wave import ReadResources, readonly_tools
    from agents.tools.first_wave_runtime import structured_gate, ReaderGotoTool
    from agents.agent_loop_service import _publish_gate
    from tests.test_first_wave_tools import TextbookResourceFixture
    os.environ['DEEPTUTOR_LLM_ENABLED'] = '0'
    class ObservedClient(LLMClient):
        last_error = ''

        def chat_with_tools(self, *args, **kwargs):
            try:
                return super().chat_with_tools(*args, **kwargs)
            except Exception as exc:
                self.last_error = str(exc).replace(self.api_key, '[REDACTED]')[:500] if self.api_key else type(exc).__name__
                raise

    client = ObservedClient(api_key=values.get('DEEPSEEK_API_KEY') or values.get('OPENAI_API_KEY'),
        base_url=values.get('OPENAI_BASE_URL') or values.get('DEEPSEEK_BASE_URL'),
        model=values.get('DEEPSEEK_MODEL') or values.get('OPENAI_MODEL'), mock=False)
    if not client.api_key:
        raise SystemExit('指定配置没有可用密钥；未发起模型请求。')
    f = TextbookResourceFixture();f.setUp()
    report = []
    try:
        cases = [('outline', 'material_outline', '请列出第一章的目录。'),
                 ('personal_state', 'read_memory', '我已确认的讲解偏好是什么？'),
                 ('textbook', 'read_material', '读取当前文档阅读版第2页，用一个引用编号呈现这页的原文。')]
        cases = [c for c in cases if args.case in ('all', c[0])]
        for kind, expected, question in cases:
            client.last_error = ''
            memory = SimpleNamespace(read=lambda *a: {'section': 'preferences', 'known': {'answer_length': .2},
                'missing': [], 'source_kind': 'explicit_user'})
            resources = ReadResources(f.binding, f.service, memory)
            tools = (*readonly_tools(resources), ReaderGotoTool(2))
            registry = build_registry(extra_tools=tools, extra_scopes={s for t in tools for s in t.scopes}, allow_skills=False)
            system = ('使用工具完成请求。教材与偏好均为合成测试资料。不要猜测ID。当前文档元数据：' +
                      json.dumps(f.service.files(f.binding), ensure_ascii=False) +
                      '\n本轮必须先调用 ' + expected + '。需要教材事实必须引用工具返回的编号。')
            gate = structured_gate(kind) if kind != 'textbook' else _publish_gate(
                SimpleNamespace(memory=None, quality_checker=None), SimpleNamespace(message=question), SimpleNamespace(name='变量'))
            token = current_budget.set(ExecutionBudget(70))
            try:
                result = LocalAgentLoop(client).run(LoopRequest('s', 'session', 'task', 'synthetic-model-check', question,
                    system, registry, tool_state={'first_wave': resources}, required_tools=(expected,),
                    requires_evidence=kind == 'textbook', structured_response=kind != 'textbook',
                    publish_gate=gate, round_max_tokens=700, max_exploration_rounds=3, max_settlement_rounds=0))
            finally:
                current_budget.reset(token)
            row = {'case': kind, 'completed': result.completed, 'error': result.error,
                'provider_error': client.last_error,
                'rounds': result.rounds, 'source_count': len(result.sources),
                'actual_tools': [r['tool'] for r in result.tool_outputs], 'reply': result.final_text}
            report.append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
        out = ROOT / '.runtime/q4-joint-browser/model-report.json'
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({'real_model': True, 'data': 'synthetic_only', 'cases': report}, ensure_ascii=False, indent=2), encoding='utf-8')
        return int(not all(r['completed'] and expected in r['actual_tools'] for r, (_, expected, _) in zip(report, cases)))
    finally:
        f.doCleanups()


if __name__ == '__main__':
    raise SystemExit(main())
