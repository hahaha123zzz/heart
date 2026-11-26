"""阶段 0：合成历史下的上下文读取与摘要触发计时（不调用模型）。"""
import json
import statistics
import sys
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.conversation_context import build_history


def rows(count, summary_up_to=None, long=False):
    filler = ('教材原文说明：自变量是研究者主动操纵的变量，控制变量保持恒定，'
              '因变量随自变量的变化而变化，实验设计需要区分三者并记录操作定义。') if long else ''
    items = []
    for index in range(count):
        role = 'user' if index % 2 == 0 else 'assistant'
        turn = index // 2 + 1
        content = (f'第{turn}问：自变量和控制变量有什么区别？{filler}' if role == 'user'
                   else f'第{turn}答：自变量由研究者主动操纵，控制变量保持恒定。{filler}')
        item = {'id': index + 1, 'role': role, 'content': content}
        if summary_up_to is not None and index == count - 1:
            item['metadata'] = {'context_summary': {
                'compressed_summary': '[对话摘要] 前段是自变量与控制变量的定义练习。',
                'summary_up_to_msg_id': summary_up_to}}
        items.append(item)
    return items


def measure(history):
    calls = []
    def spy(older):
        calls.append(len(older))
        return '[对话摘要] 新摘要'
    result = build_history(history, model='deepseek-flash', context_window=16000, summarizer=spy,
                           llm=SimpleNamespace(model='deepseek-flash'))
    return {'rows_in': len(history), 'rows_out': len(result.history),
            'summary_chars': len(result.summary), 'summary_calls': len(calls),
            'tokens': result.token_count, 'dropped': result.dropped_messages}


def main():
    cases = {
        'short_12': rows(12),
        'long_320_with_summary': rows(320, summary_up_to=308, long=True),
        'long_320_trigger_summary': rows(320, long=True),
    }
    output = {}
    for name, history in cases.items():
        samples = []
        last = None
        for _ in range(7):
            began = time.perf_counter()
            last = measure(history)
            samples.append(round((time.perf_counter() - began) * 1000, 2))
        output[name] = {**last, 'milliseconds': samples, 'median_ms': statistics.median(samples)}
    print(json.dumps({'branch_coverage': 'host adapter ignores leaf_message_id; not measured',
                      'cases': output}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
