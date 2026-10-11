"""导出可审阅的证明单元与引用清单，不改动原混合检索索引。"""
import json
from pathlib import Path
from knowledge.proof_units import units_for, dependencies

def main():
    rows=[]
    for chapter in range(1,11):
        for unit in units_for(chapter).values():
            linked,unresolved=dependencies(unit)
            rows.append(dict(id=unit.id,label=unit.label,chapter_id=chapter,section_id=unit.section['id'],
                section=unit.section['title'],document_id=unit.record['document_id'],version=unit.record['version'],
                pages=unit.pages,rects=unit.rects,explicit_references=unit.refs,
                linked_references=[u.id for u in linked],unresolved_references=unresolved,
                omitted_steps=unit.omitted,truncated=unit.truncated,text_chars=len(unit.text)))
    target=Path(__file__).resolve().parents[1]/'artifacts/proof-units-audit.json'
    target.write_text(json.dumps(dict(relation_type='explicit_citation_not_mathematically_verified',units=rows),ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(dict(units=len(rows),theorems=sum(u['label'].startswith('定理') for u in rows),omitted=sum(u['omitted_steps'] for u in rows),linked=sum(len(u['linked_references']) for u in rows),truncated=sum(u['truncated'] for u in rows)),ensure_ascii=False))
if __name__=='__main__':main()
