"""关系摘要是有界关联候选；原文编号与证据卡仍归Q2。"""
import json
from dataclasses import replace

def relationship_context(records,sources,*,limit=12,max_chars=6000):
    if not 1<=limit<=24 or not 800<=max_chars<=12000:raise ValueError('关系上下文预算无效')
    refs=[s.to_dict() if hasattr(s,'to_dict') else s for s in sources]
    out={'schema':'lightrag-associations/v1','semantics':'association_candidates_only; not quotes, prerequisites, emphasis or mastery',
         'associations':[],'omitted':0}
    seen=set();items=[]
    for record in records:
        if record.get('kind') not in ('entity','relationship'):continue
        key=(record['kind'],record.get('relation_id') or record.get('entity_id'))
        if key in seen:continue
        seen.add(key);chunks=list(filter(None,record.get('source_id','').split('<SEP>')));links=[]
        for ref in refs:
            loc=ref.get('location') or {}
            if not ref.get('document_id') or not ref.get('version') or not loc.get('source_spans'):continue
            if not set(chunks).intersection(loc.get('sdk_chunk_ids',[])):continue
            links.append({'source_id':ref['source_id'],'document_id':ref['document_id'],'version':ref['version'],
              'chapter_id':ref.get('chapter_id'),'source_spans':loc['source_spans'],
              'textbook_release':loc.get('textbook_release'),'release_status':loc.get('release_status'),
              'sdk_chunk_ids':list(set(chunks).intersection(loc.get('sdk_chunk_ids',[])))})
        item={'kind':record['kind'],'id':key[1],'entity_ids':[record.get('src_id'),record.get('tgt_id')] if record['kind']=='relationship' else [record.get('entity_id')],
              'description':record.get('content','')[:320],'description_truncated':len(record.get('content',''))>320,
              'sdk_chunk_ids':chunks[:12],'sdk_chunk_count':len(chunks),'omitted_chunk_links':max(0,len(chunks)-12),
              'source_links':links[:3],'source_link_count':len(links),'omitted_source_links':max(0,len(links)-3),
              'evidence_eligible':False,'status':'linked_candidate_requires_claim_check' if links else 'requires_original_lookup'}
        items.append(item)
    # SDK先返回实体；优先展示有原文链接的关系，避免实体占满整个预算。
    items.sort(key=lambda r:(not r['source_links'],r['kind']!='relationship'))
    for item in items:
        out['associations'].append(item)
        if len(out['associations'])>limit or len(json.dumps(out,ensure_ascii=False))>max_chars-80:
            out['associations'].pop();out['omitted']+=1
    return out

def append_tool_context(result,context):
    if not result.success:return result
    if len(json.dumps(context,ensure_ascii=False))>12000:raise ValueError('关系与覆盖上下文超过工具预算')
    text='\n\n【关联候选与覆盖状态，非教材引文】\n'+json.dumps(context,ensure_ascii=False)
    return replace(result,content=result.content+text,metadata={**result.metadata,'retrieval_context':context})
