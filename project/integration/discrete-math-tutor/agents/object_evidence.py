"""明确对象的在线取证适配；读到OMML不能跳过现有Q2原文与语义核验。"""
import re

OBJECT_ID = re.compile(r'experimental-psychology-3:chapter-(?:0[1-9]|1[01]):(?:b\d+|omml-\d+)\b')


def requested_objects(message):
    ids = list(dict.fromkeys(OBJECT_ID.findall(message)))
    if len(ids) > 2:
        raise ValueError('单轮最多读取两个教材表格或公式对象')
    return ids


def read_requested_objects(ids, check):
    from knowledge.evidence_objects import ObjectReadRequest, read_object
    from knowledge.pdf_reader import document
    sources, identities = {}, []
    for identity in ids:
        check()
        record = document(identity.rsplit(':', 1)[0])
        if not record:
            raise ValueError('请求的教材对象没有当前文档登记')
        result = read_object(ObjectReadRequest(document_id=record['document_id'], version=record['version'],
            object_id=identity, kind='formula' if ':omml-' in identity else 'table'))
        for source in result['sources']:
            sources[source.source_id] = source
            if source.location.get('object_id') == identity:
                identities.append(source)
        if not any(s.location.get('object_id') == identity for s in result['sources']):
            raise ValueError('请求的教材对象没有可读取的原文')
        check()
    return list(sources.values()), identities


def missing_objects(expected, selected):
    missing = []
    for source in expected:
        spans = []
        for result in selected:
            evidence = result.location.get('evidence', {})
            if ((result.document_id, result.version, result.section_id) == (source.document_id, source.version, source.section_id)
                    and evidence.get('source_block_id') == source.location['block_start']):
                start, end = evidence.get('block_start'), evidence.get('block_end')
                if (type(start) is not int or type(end) is not int or not 0 <= start < end <= len(source.text)
                        or source.text[start:end] != result.text):
                    raise ValueError('对象核验后的原文范围不一致')
                spans.append((start, end))
        cursor = 0
        for start, end in sorted(spans):
            if source.text[cursor:start].strip():
                break
            cursor = max(cursor, end)
        if source.text[cursor:].strip():
            missing.append(source.location['object_id'])
    return missing
