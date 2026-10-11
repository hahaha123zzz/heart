"""完整证明路线的受控真实生成验证，不能代替 API 召回测试。"""
import json
from pathlib import Path
from dataclasses import replace
from agents.response_generator import ResponseGenerator
from agents.quality_checker import QualityChecker
from agents.teaching_planner import TeachingPlan
from models.student_state import StudentState
from llm.client import LLMClient
from knowledge.proof_units import units_for, expand_proof_sources, _chunk
from knowledge.textbook import format_excerpts
base=Path(__file__).resolve().parents[1]
row=json.loads((base/'artifacts/long-proofs-final-gpu.json').read_text(encoding='utf8'))[0]
unit=units_for(8)['定理8.11']
sources,bundle=expand_proof_sources([replace(_chunk(unit),text=unit.label+' 原始正文')],row['case']['question'])
state=StudentState.model_validate(row['response']['student_state'])
plan=TeachingPlan.model_validate(row['response']['teaching_plan'])
plan.goal=f"解释{unit.label}的证明及学生指定步骤"
llm=LLMClient()
attempts=[]
feedback=None
for attempt in range(2):
    reply=ResponseGenerator(llm).generate(state,plan,row['case']['question'],[],instructional_move='direct_explanation',
        lesson_text='先用一句话概述完整证明的主要路线，包含分情况与换色，再展开一小步，说明后续尚未展开。',feedback=feedback,
        textbook_excerpts=format_excerpts(sources),figure_images=bundle.supplement.images)
    quality=QualityChecker(llm).check(reply,state,plan,row['case']['question'],textbook_excerpts=format_excerpts(sources),figure_images=bundle.supplement.images)
    attempts.append(dict(reply=reply,quality=quality.model_dump()))
    if quality.passed: break
    feedback='；'.join(quality.issues)+'。'+quality.suggestions
result=dict(mode='controlled_generation_not_retrieval',reply=reply,characters=len(reply),quality=quality.model_dump(),proof=bundle.public(),attempts=attempts)
(base/'artifacts/proof-overview-controlled.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(result,ensure_ascii=False),flush=True)
