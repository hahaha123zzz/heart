import json
from pathlib import Path
from types import SimpleNamespace
from knowledge.pdf_reader import PDFSelection
from agents.pdf_selection_tutor import explain_selection
from agents.quality_checker import QualityChecker
from memory.memory_manager import MemoryManager
from llm.client import LLMClient
records=[]
llm=LLMClient();checker=QualityChecker(llm);memory=MemoryManager()
def check(*args,**kwargs):
 result=checker.check(*args,**kwargs)
 records.append({'reply':args[0],'length':len(args[0]),'quality':result.model_dump()})
 Path('artifacts/pdf-reader/image-quality-diagnostic.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
 return result
proxy=SimpleNamespace(llm=llm,memory=memory,quality_checker=SimpleNamespace(check=check))
selection=PDFSelection.model_validate_json(Path('artifacts/pdf-reader/image-selection.json').read_text())
try:
 result=explain_selection(proxy,'pdf-real-diagnostic','请解释圈选图中的粗边表示什么，以及它们与匹配的关系。',selection,'test')
 print(json.dumps(result,ensure_ascii=False))
except Exception as error: print(type(error).__name__)
