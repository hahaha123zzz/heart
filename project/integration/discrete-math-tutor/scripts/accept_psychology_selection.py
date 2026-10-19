"""用合成学生验收原PDF选中文字提问，不读取真实学生历史。"""
import json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.accept_psychology_original_pipeline import BoundedClient
from orchestrator import TutorOrchestrator
from knowledge.pdf_reader import PDFSelection,document_for_chapter,resolve_selection
from agents.pdf_selection_tutor import explain_selection

def main():
    tutor=TutorOrchestrator(llm=BoundedClient());record=document_for_chapter(2);section=record['sections'][1]
    rect=section['rect']|{'x1':.14,'x2':.84,'y2':min(.95,section['rect']['y2']+.12)}
    selection=PDFSelection(document_id=record['document_id'],version=record['version'],kind='text',rects=[rect])
    resolved=resolve_selection(selection)
    result=explain_selection(tutor,'psych-selection-'+str(time.time_ns()),'请解释我选中教材里的自变量含义，并引用本次选区。',selection,'test',resolved_selection=resolved)
    (ROOT/'artifacts/psychology-selection-acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    print(json.dumps({'status':result.get('answer_status'),'reply':result.get('reply'),'document':result.get('selection_ref',{}).get('document_id')},ensure_ascii=False))
    assert result.get('answer_status')=='answered' and result.get('selection_ref',{}).get('document_id')==record['document_id']

if __name__=='__main__':main()
