"""已知双盲错误专项；真值固定为原文块235/236及生成阅读版19—20页。"""
import argparse,hashlib,json
from pathlib import Path
from knowledge.citation_index import CitationIndex
from knowledge.course_config import PSYCHOLOGY_DIR
from knowledge.grounded_citations import EvidenceBundle
from knowledge.grounding_text import normalized
from knowledge.pdf_reader import documents,evidence_text
from knowledge.textbook import TextbookChunk,load_textbook
from knowledge.psychology_retrieval import retrieve
from knowledge.citation_locations import locate_source


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--index',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if args.output.exists():raise ValueError('报告已存在，不覆盖')
    record=next(r for r in documents() if r['chapter_id']==2)
    doc=json.loads((PSYCHOLOGY_DIR/'chapters/chapter_02/document.json').read_text(encoding='utf-8'))
    index=CitationIndex(args.index);sources=[];evidence=[]
    try:
        for block_id,pages in ((235,[19,20]),(236,[20])):
            block=next(b for b in doc['blocks'] if b['block_index']==block_id)
            located=index.locate(record['document_id'],record['version'],block['text'],block_id=block_id)
            assert located['status']=='exact' and sorted({r['page'] for r in located['rects']})==pages
            sources.append(TextbookChunk(record['source'],block['section'],block['text'],frozenset(),chapter_id=2,
                section_id=block['section_id'],block_start=block_id,block_end=block_id))
            evidence.append({'evidence_id':hashlib.sha256(block['text'].encode()).hexdigest(),'retrieval_source_id':str(block_id),
                'document_id':record['document_id'],'document_version':record['version'],'source_block_id':block_id,
                'section_id':block['section_id'],'quote':block['text'],'location_status':'exact','rects':located['rects']})
        references=EvidenceBundle(sources,evidence,sources).references('双盲使被试和执行实验人员均不知处理，控制要求特征与实验者偏差。[1]\n药物例子通过分工和药片编号实施。[2]')
        for ref in references:
            item=ref['evidence'];rendered='\n'.join(evidence_text(record['document_id'],record['version'],s['rects']) for s in item['selections'])
            assert normalized(item['quote']) in normalized(rendered)
        old=[locate_source(s,'双盲控制要求特征与实验者偏差[1]') for s in retrieve('双盲实验如何控制要求特征与实验者偏差',load_textbook())]
        result={'method':'固定原文/页码与真实PDF字形机器核验；非模型语义验收、非教师审核',
            'known_failure':'原链路截图落在方法标题、因变量定义；新链路必须展示双盲定义全文及药物控制原文',
            'references':references,'legacy_retrieval_references':old}
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print('PASS：定义19—20页、实例20页；3个分段裁图，完整原文未丢失')
    finally:index.close()


if __name__=='__main__':main()
