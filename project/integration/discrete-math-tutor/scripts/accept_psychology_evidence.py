"""固定心理学证据对照；逐项保存真实模型结论，不修改学习画像。"""
import argparse
import json
from pathlib import Path
from agents.context_sufficiency import ContextSufficiency
from agents.course_prompts import GATE
from llm.client import LLMClient
from knowledge.evidence_recovery import recover_evidence
from knowledge.textbook import load_textbook, TextbookChunk, terms_for
from knowledge.psychology_retrieval import retrieve

BASE=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--baseline',action='store_true')
    parser.add_argument('--repeat',type=int,default=2,choices=range(1,4))
    args=parser.parse_args()
    cases=json.loads((BASE/'tests/data/answer_flow/psychology_evidence_gate.json').read_text(encoding='utf-8'))['cases']
    snapshot=json.loads((BASE/'artifacts/evidence-gate-baseline-snapshot-20261016.json').read_text(encoding='utf-8'))
    gate=ContextSufficiency(LLMClient(mock=False),system=snapshot['system'] if args.baseline else GATE)
    report={'baseline':args.baseline,'repeat':args.repeat,'system':gate.system,'results':[]}
    output=BASE/'artifacts'/('psychology-evidence-baseline-20261016.json' if args.baseline else 'psychology-evidence-final-20261016.json')
    for attempt in range(args.repeat):
        for case in cases:
            decision=gate.check(case['question'],case['evidence'],hint_only=case.get('hint_only',False))
            initial=decision.model_dump()
            recovery=None
            # 仅实际检索快照运行补检索；受控缺失证据用例保持原证据，以验证拒绝边界。
            if not args.baseline and case.get('recover_from_course') and not decision.allowed:
                sources=[TextbookChunk(source=e['source'],section=e.get('section',''),text=e['text'],terms=terms_for(e['text']),
                    chunk_id=e.get('chunk_id')) for e in case['evidence']]
                recovered=recover_evidence(case['question'],sources,load_textbook(),decision,retrieve,max_sources=9)
                if len(recovered)>len(sources):
                    evidence=[{'id':str(i),'source':c.source,'section':c.section,'text':c.text} for i,c in enumerate(recovered,1)]
                    recovery={'before':len(sources),'after':len(recovered),'evidence':evidence}
                    decision=gate.check(case['question'],evidence,hint_only=case.get('hint_only',False))
            correct=decision.allowed if case['expected']=='sufficient' else not decision.allowed and decision.status!='unavailable'
            report['results'].append({'case':case['id'],'attempt':attempt+1,'expected':case['expected'],
                'initial_decision':initial,'recovery':recovery,'decision':decision.model_dump(),'correct':correct})
            report['correct']=sum(row['correct'] for row in report['results'])
            report['total']=len(report['results'])
            output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            print(case['id'],attempt+1,decision.status,'PASS' if correct else 'FAIL',flush=True)
    print(f"{report['correct']}/{report['total']}",flush=True)
    return 0 if report['correct']==report['total'] else 1


if __name__=='__main__':raise SystemExit(main())
