"""同一冻结样本：明确对象直读、实际问题中的引用片段分别召回；不使用金标构造查询。"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.collect_layer4_baseline import collect as baseline_collect, attach_provenance, main


def collect(case, chapter_blocks, retrieve):
    query = case['question']
    if case['category'] in ('table', 'formula'):
        from knowledge.evidence_objects import ObjectReadRequest, read_object
        from knowledge.pdf_reader import document
        pattern = r'experimental-psychology-3:chapter-(?:0[1-9]|1[01]):(?:b\d+|omml-\d+)'
        match = re.search(pattern, query)
        if match:
            identity = match.group()
            record = document(identity.rsplit(':', 1)[0])
            if not record:
                raise ValueError('unknown_requested_document')
            result = read_object(ObjectReadRequest(document_id=record['document_id'], version=record['version'],
                                 object_id=identity, kind=case['category']))
            return [s.to_dict() for s in result['sources']], {
                'method': 'version_bound_original_object', 'route': 'A_object', 'llm_calls': 0,
                'object_id_from_question': identity, 'payload': result['payload'],
                'semantic_verified': False, 'model_saw_pixels': False}
    excerpts = re.findall('“([^”]+)”', query)
    if len(excerpts) > 1 and case['category'] in ('comparison', 'experiment', 'cross_chapter'):
        from agents.course_search import explicit_chapters
        chapters = explicit_chapters(query)
        preferred = next(iter(chapters)) if len(chapters) == 1 else None
        sources, traces = {}, []
        # 两侧分别占最多3个位置，防止第一侧挤掉另一侧；不因分数高就声明语义覆盖。
        for excerpt in excerpts[:2]:
            trace = {}
            chunks = retrieve(excerpt.rstrip('…'), limit=3, trace=trace, chapter_id=preferred)
            for chunk in chunks:
                source = attach_provenance(chunk, chapter_blocks[chunk.chapter_id])
                sources[source.source_id] = source.to_dict()
            traces.append({'query': excerpt.rstrip('…'), 'retrieval': trace})
        return list(sources.values()), {'method': 'separate_quoted_requirements', 'route': 'B_bounded_requirements',
                                      'requirements': traces, 'semantic_verified': False, 'llm_calls': 0}
    return baseline_collect(case, chapter_blocks, retrieve)


if __name__ == '__main__':
    main(collect_fn=collect, implementation_files=['scripts/collect_layer4_stage3.py',
         'knowledge/evidence_objects.py', 'agents/tools/evidence_requirements.py'])
