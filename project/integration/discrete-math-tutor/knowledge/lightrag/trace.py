"""只记录教材来源身份、阶段与排除原因，不记录凭据。"""
import time

def source_row(source):
    row=source.to_dict() if hasattr(source,'to_dict') else source
    loc=row.get('location') or {}
    return {k:v for k,v in {
        'source_id':row.get('source_id') if row.get('document_id') else row.get('chunk_id'),
        'sdk_chunk_ids':loc.get('sdk_chunk_ids',[]),'chapter_id':row.get('chapter_id'),
        'document_id':row.get('document_id'),'version':row.get('version'),
        'block_id':loc.get('block_start'),'range':[loc.get('block_char_start'),loc.get('block_char_end')],
        'subproblems':loc.get('retrieval_requirements',[]),'score':row.get('score')}.items() if v is not None}

def stage(trace,name,before,after,reason,**metadata):
    if trace is None:return
    from collections import Counter
    kept=Counter(str(source_row(s).get('source_id')) for s in after);rows=[]
    for source in before:
        row=source_row(source);key=str(row.get('source_id'));accepted=kept[key]>0
        if accepted:kept[key]-=1
        rows.append(dict(row,accepted=accepted,exclusion_reason=None if accepted else reason))
    trace.append({'stage':name,'at_monotonic':time.monotonic(),**metadata,'rows':rows})
