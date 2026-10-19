"""Q2本地检索实测：只读教材与已有模型，不启动DeepTutor或聊天模型。"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--query', action='append')
    parser.add_argument('--require-rerank', action='store_true')
    args = parser.parse_args()
    # 使用已缓存模型，不在评估中隐式下载权重或占用现有服务GPU。
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['RAG_EMBED_DEVICE'] = 'cpu'
    os.environ['RAG_RERANK_DEVICE'] = 'cpu'
    os.environ['RAG_RETRIEVAL_ENGINE'] = 'local_llamaindex'
    from knowledge.course_config import COURSE_ID, PSYCHOLOGY_DIR
    from knowledge.local_rag.course_retrieval import retrieve, index_signature
    from knowledge.psychology_retrieval import retrieve as retrieve_course
    from knowledge.pdf_reader import document_for_chapter, pdf_path

    run = ROOT / '.runtime/local-rag-checks' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + secrets.token_hex(3))
    run.mkdir(parents=True)
    index = PSYCHOLOGY_DIR / 'rag_index.sqlite3'
    before = index_signature(index)
    queries = args.query or ['什么是自变量', '被试内设计和被试间设计有什么区别', '内部效度与外部效度有什么区别', '火星表面玄武岩的晶体结构']
    expected = {'什么是自变量': ['自变量'], '被试内设计和被试间设计有什么区别': ['被试内', '被试间'],
        '内部效度与外部效度有什么区别': ['内部效度', '外部效度'], '火星表面玄武岩的晶体结构': []}
    records = []; failed = False
    for query in queries:
        trace = {}; started = time.monotonic()
        record = {'query': query}
        try:
            hits = retrieve(query, trace=trace)
            projected = retrieve_course(query, [])
            sources = []
            for hit in projected:
                document = document_for_chapter(hit.chapter_id)
                if document is None or hashlib.sha256(pdf_path(document).read_bytes()).hexdigest() != document['version']:
                    raise ValueError('来源PDF与发布版本不一致')
                if not hit.source_spans: raise ValueError('来源未映射到实际原文范围')
                sources.append({'chunk_id': hit.chunk_id, 'chapter_id': hit.chapter_id, 'page': hit.page,
                    'document_id': document['document_id'], 'document_version': document['version'],
                    'block_start': hit.block_start, 'block_end': hit.block_end, 'source_spans': hit.source_spans})
            record.update(status='passed', trace=trace, raw_ids=[hit.chunk_id for hit in hits], sources=sources,
                excerpts=[hit.text[:1000] for hit in projected])
            if query in expected:
                terms = expected[query]
                if not terms and (hits or projected): raise ValueError('教材外查询未拒绝')
                if terms and (not hits or any(not any(term in hit.text for hit in projected) for term in terms)):
                    raise ValueError('必需的概念来源没有完整覆盖')
                record['expectation_checked'] = True
            if args.require_rerank and trace.get('candidates') and trace.get('rerank_status') != 'applied':
                raise ValueError('要求真实重排，但本轮实际使用了降级检索')
        except Exception as error:
            record.update(status='failed', trace=trace, error_type=type(error).__name__, error=str(error))
            failed = True
        record['seconds'] = round(time.monotonic() - started, 3)
        records.append(record)
        print(query, record['status'], record['seconds'], trace.get('effective_profile'), trace.get('rerank_status'), flush=True)
    after = index_signature(index)
    failed |= before != after
    report = {'course_id': COURSE_ID, 'engine': 'local_llamaindex', 'index_before': before, 'index_after': after,
        'index_unchanged': before == after, 'llm_calls': 0, 'cases': records, 'passed': not failed,
        'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (run / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('report:', run / 'report.json', flush=True)
    return int(failed)


if __name__ == '__main__': raise SystemExit(main())
