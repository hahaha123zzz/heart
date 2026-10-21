"""从真实教材选区生成标注的测试题；只使用显式官方DeepSeek配置。"""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--env-file', type=Path, required=True)
    parser.add_argument('--selection', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('输出已存在，不覆盖既有测试题')
    from dotenv import dotenv_values
    config = dotenv_values(args.env_file)
    endpoint = config.get('OPENAI_BASE_URL', '')
    if urlsplit(endpoint).scheme != 'https' or urlsplit(endpoint).netloc != 'api.deepseek.com':
        raise ValueError('测试题生成只允许DeepSeek官方端点')
    os.environ['DEEPTUTOR_LLM_ENABLED'] = '0'
    from knowledge.pdf_reader import PDFSelection, validate_selection, pdf_path, evidence_text
    from knowledge.course_config import COURSE_ID
    from knowledge.ai_practice_test import LABEL, load_catalog
    from llm.client import LLMClient
    raw = json.loads(args.selection.read_text(encoding='utf8'))
    selection = PDFSelection.model_validate({k: raw[k] for k in ('document_id','version','kind','rects')})
    record = validate_selection(selection)
    if hashlib.sha256(pdf_path(record).read_bytes()).hexdigest() != selection.version:
        raise ValueError('知识依据PDF已失效')
    context = evidence_text(selection.document_id, selection.version, selection.model_dump()['rects'])
    if len(context.strip()) < 30:
        raise ValueError('知识依据过少，不能生成题目')
    llm = LLMClient(api_key=config['DEEPSEEK_API_KEY'], base_url=endpoint,
                    model=config.get('DEEPSEEK_MODEL','deepseek-flash'), mock=False)
    api = llm._client_lazy(); api.max_retries = 0
    from openai.resources.chat.completions import Completions
    calls = []; original = Completions.create
    def measured(resource, *a, **kw):
        start = time.monotonic(); response = original(resource, *a, **kw)
        calls.append({'seconds':round(time.monotonic()-start,3), 'model':response.model,
                      'usage':response.usage.model_dump() if response.usage else None,
                      'finish_reason':response.choices[0].finish_reason})
        return response
    Completions.create = measured
    try:
        result = llm.chat_json([{'role':'system','content':'仅依据提供的教材段落生成3道中文问答测试题。不是教材原题，不编造段落之外的事实。三题分别考查事实、理解、依据说明。输出JSON {"questions":[{"title":"知识点","stem":"题干"}]}。不输出答案、评分或已审核声明。'},
            {'role':'user','content':context}], temperature=.1, max_tokens=1000, retries=0, timeout=60)
    finally:
        Completions.create = original
        api.close()
    if len(calls) != 1:
        raise ValueError('生成模型调用未完整记录')
    rows = result.get('questions', [])
    if len(rows) != 3 or any(not isinstance(r.get(k),str) or not 1 <= len(r[k]) <= 800 for r in rows for k in ('title','stem')):
        raise ValueError('模型未返回3道有效测试题')
    def block(text):
        return {'type':'paragraph','segments':[{'type':'text','text':text}]}
    questions = []
    for n, row in enumerate(rows,1):
        stem = [block(row['stem'])]
        questions.append({'id':f'ai-test-01-{n:03d}','origin':'ai_generated','test_only':True,
            'review_status':'unreviewed','chapter_id':record['chapter_id'],'section_id':raw['section_id'],
            'group_id':'AI测试','number':n,'knowledge_point':row['title'], 'text':LABEL+'\n'+row['stem'],
            'source_version':selection.version,'basis_selection':selection.model_dump(),
            'source':{'document_id':selection.document_id,'page':min(r.page for r in selection.rects),
                      'end_page':max(r.page for r in selection.rects),'role':'knowledge_basis_not_question_origin'},
            'shared_blocks':[block(LABEL+'。本题为生成题目，教材选区仅作为知识依据，不是教材原题。')],
            'parts':[{'id':'p1','label':'测试问答','type':'written','blocks':stem,'stem_blocks':stem}]})
    data={'schema':'ai-practice-test-v1','course_id':COURSE_ID,'origin':'ai_generated','test_only':True,
          'review_status':'unreviewed','generated_at':dt.datetime.now(dt.timezone.utc).isoformat(),
          'generation':{'endpoint':endpoint,'requested_model':llm.model,'calls':calls,'gateway_called':False,
                        'basis_text_sha256':hashlib.sha256(context.encode()).hexdigest()},'questions':questions}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    load_catalog(args.output,COURSE_ID)
    print(json.dumps({'questions':len(questions),'origin':'ai_generated','review_status':'unreviewed','calls':calls},ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(json.dumps({'status':'failed','error_type':type(exc).__name__}),file=sys.stderr)
        raise SystemExit(1)
