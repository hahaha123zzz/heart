"""现有A/B取证组件的离线只读采集；不运行聊天、图谱升级或学生写入。"""
import argparse
from dataclasses import replace
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.build_layer4_benchmark import digest
from scripts.evaluate_layer4_benchmark import validate, score


def attach_provenance(chunk, blocks):
    from agents.q3_navigation import source_from_chunk
    from knowledge.source_mapping import source_spans
    source = source_from_chunk(chunk, 0)
    selected = [b for b in blocks if chunk.block_start is not None and chunk.block_end is not None
                and chunk.block_start <= b['block_index'] <= chunk.block_end]
    spans = source_spans(selected, chunk.text)
    return replace(source, location={**source.location, 'source_spans': list(spans),
                                    'mapping_basis': 'actual_text_overlap_in_returned_block_range'})


def collect(case, chapter_blocks, retrieve):
    from agents.course_search import explicit_chapters
    from agents.q3_navigation import SourceRef
    query = case['question']
    trace = {}
    if case['category'] == 'selection':
        # 选区本来就是请求上下文；不把预期原文或块ID传给检索器。
        from knowledge.pdf_reader import evidence_text
        selection = case['supports'][0]
        text = evidence_text(selection['document_id'], selection['version'], selection['rects'])
        from knowledge.source_mapping import source_spans
        spans = source_spans(chapter_blocks[selection['chapter_id']], text)
        source = SourceRef('selection:' + case['id'], selection['document_id'], text,
                           version=selection['version'], chapter_id=selection['chapter_id'],
                           location={'source_spans': list(spans), 'origin': 'reader_selection'})
        return [source.to_dict()], {'method': 'existing_evidence_text', 'route': 'A_selection', 'llm_calls': 0}
    if case['category'] == 'image':
        from knowledge.figures import get_figure
        from knowledge.figure_reading import read_figure
        from knowledge.answer_media import selected_media
        match = re.search(r'image-\d{2}-\d{4}', query)
        figure = get_figure(match.group()) if match else None
        chunks = read_figure(figure) if figure else []
        sources = [attach_provenance(chunk, chapter_blocks[chunk.chapter_id]) for chunk in chunks]
        media = selected_media(query, [s.to_dict() for s in sources], asset_id=match.group()) if sources else []
        return [replace(s, image_refs=media).to_dict() for s in sources], {
            'method': 'existing_named_figure_reader', 'route': 'A_named_image', 'llm_calls': 0,
            'model_saw_pixels': False, 'image_location_status': [m.get('location_status') for m in media]}
    chapters = explicit_chapters(query)
    preferred = next(iter(chapters)) if len(chapters) == 1 else None
    chunks = retrieve(query, limit=6, trace=trace, chapter_id=preferred)
    sources = [attach_provenance(chunk, chapter_blocks[chunk.chapter_id]).to_dict() for chunk in chunks]
    return sources, {'method': 'existing_local_llamaindex', 'route': 'B_single_query_baseline',
                     'preferred_chapter_from_question': preferred, 'retrieval': trace,
                     'graph_upgrade_exercised': False, 'llm_calls': 0}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--data', type=Path, required=True)
    p.add_argument('--course-dir', type=Path, required=True)
    p.add_argument('--cache-dir', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--max-cases', type=int)
    args = p.parse_args()
    if args.output.exists():
        raise ValueError('采集目录已存在，不能覆盖')
    if args.max_cases is not None and not 1 <= args.max_cases <= 48:
        raise ValueError('max_cases范围1—48')
    os.environ.update(TUTOR_COURSE='experimental-psychology-3', FIXED_BOOK_RETRIEVAL_ENABLED='0',
                      RAG_RETRIEVAL_PROFILE='hybrid', RAG_RERANK_MODEL='BAAI/bge-reranker-base',
                      RAG_RERANK_MIN_PROBABILITY='0.15', RAG_RERANK_TOP_K='40',
                      RAG_EMBED_DEVICE='cuda', RAG_RERANK_DEVICE='cuda',
                      FASTEMBED_CACHE_PATH=str(args.cache_dir.resolve()), HF_HUB_OFFLINE='1',
                      TRANSFORMERS_OFFLINE='1', OMP_NUM_THREADS='2', MKL_NUM_THREADS='2')
    from knowledge.course_config import PSYCHOLOGY_DIR
    if args.course_dir.resolve() != PSYCHOLOGY_DIR.resolve():
        raise ValueError('必须使用独立worktree默认教材目录，不能重定向业务模块')
    from knowledge.local_rag.course_retrieval import retrieve
    from knowledge.pdf_reader import documents
    from knowledge.inference_runtime import runtime_status
    data = json.loads(args.data.read_text(encoding='utf-8'))
    validation = validate(data, args.course_dir)
    index = args.course_dir/'rag_index.sqlite3'
    index_hash = digest(index)
    app = Path(__file__).resolve().parents[1]
    tracked = ['scripts/collect_layer4_baseline.py', 'scripts/evaluate_layer4_benchmark.py',
               'knowledge/local_rag/course_retrieval.py', 'knowledge/local_rag/retrievers.py',
               'knowledge/local_rag/rerank.py', 'knowledge/hybrid_retrieval.py',
               'agents/q3_navigation.py', 'knowledge/source_mapping.py',
               'knowledge/visual_locations.py', 'knowledge/figure_reading.py', 'knowledge/answer_media.py']
    implementation = {name: digest(app/name) for name in tracked}
    chapters = {r['chapter_id']: json.loads((args.course_dir/'chapters'/f"chapter_{r['chapter_id']:02d}"/'document.json').read_text(encoding='utf-8'))['blocks']
                for r in documents()}
    args.output.mkdir(parents=True)
    header = {'benchmark_sha256': digest(args.data), 'index_sha256': index_hash,
              'base_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
              'implementation_sha256': implementation, 'source_validation': validation,
              'scope': 'offline existing A/B components, not full CourseSearch/LightRAG/chat acceptance'}
    (args.output/'manifest.json').write_text(json.dumps(header, ensure_ascii=False, indent=2), encoding='utf-8', newline='\n')
    rows = []
    selected = [c for c in data['cases'] if c['supports']]
    if args.max_cases is not None:
        selected = selected[:args.max_cases]
    for case in selected:
        started = time.monotonic()
        try:
            sources, trace = collect(case, chapters, retrieve)
            row = {'case_id': case['id'], 'category': case['category'], 'status': 'retrieved' if sources else 'empty',
                   'sources': sources, 'trace': trace}
        except Exception as exc:
            row = {'case_id': case['id'], 'category': case['category'], 'status': 'failed',
                   'sources': [], 'error': f'{type(exc).__name__}: {exc}'}
        row['seconds'] = time.monotonic()-started
        rows.append(row)
        with (args.output/'runs.jsonl').open('a', encoding='utf-8', newline='\n') as stream:
            stream.write(json.dumps(row, ensure_ascii=False)+'\n')
        print(json.dumps({k: row[k] for k in ('case_id', 'status', 'seconds')}, ensure_ascii=False), flush=True)
    validate(data, args.course_dir)
    if digest(index) != index_hash:
        raise ValueError('检索期间原索引变化')
    if any(digest(app/name) != value for name, value in implementation.items()):
        raise ValueError('采集期间执行源码变化，不能作为稳定验收')
    report = {'manifest': header, 'runtime': runtime_status(), 'index_unchanged': True,
              'diagnostic': score(data, rows), 'runs': rows, 'llm_calls': 0}
    for name, value in (('runs.json', rows), ('report.json', report)):
        (args.output/name).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8', newline='\n')
    print(json.dumps({'completed': len(rows), 'failed': sum(r['status'] == 'failed' for r in rows),
                      'anchor_recall': report['diagnostic']['anchor_recall'], 'runtime': runtime_status()}, ensure_ascii=False))
    if any(r['status'] == 'failed' for r in rows):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
