"""实际 PDF 核验、编号重映射与历史兼容，不连接在线模型。"""
from copy import deepcopy
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch

from tests import test_grounded_citations as fixtures
from knowledge.grounded_citations import EvidenceBundle, CitationGroundingError, choose_evidence, references_for_display, settings


class PublicationTests(unittest.TestCase):
    setUp=fixtures.GroundingTests.setUp
    bundle=fixtures.GroundingTests.bundle
    locate=fixtures.GroundingTests.locate

    def test_sparse_citations_are_compacted_in_body_refs_and_claims(self):
        base=self.bundle()
        bundle=EvidenceBundle(base.sources*3,base.evidence*3,base.backgrounds)
        response,sources,refs=bundle.publish('条件成立。[3]')
        self.assertEqual(response,'条件成立。[1]')
        self.assertEqual(len(sources),1)
        self.assertEqual(refs[0]['source_index'],0)
        self.assertEqual(refs[0]['evidence']['claims'][0]['markers'],[1])
        self.assertEqual(refs[0]['evidence']['verification'],'source_verified')
        self.assertEqual(refs[0]['evidence']['page'],refs[0]['selection_ref']['rects'][0]['page'])
        self.assertEqual(refs[0]['selection_ref']['page'],refs[0]['evidence']['page'])
        self.assertEqual(bundle.publish('Condition[3] and explanation.')[0],'Condition[1] and explanation.')

    def test_new_reference_carries_release_identity_and_status(self):
        ref=self.bundle().references('条件[1]')[0]
        self.assertEqual(len(ref['evidence']['textbook_release']),64)
        self.assertEqual(ref['selection_ref']['textbook_release'],ref['evidence']['textbook_release'])
        self.assertEqual(ref['selection_ref']['release_status'],ref['evidence']['release_status'])
        self.assertFalse(ref['evidence']['release_ready'])

    def test_same_version_and_range_with_different_ids_deduplicates(self):
        base=self.bundle()
        other=dict(base.evidence[0],evidence_id='another-retrieval-id')
        response,sources,refs=EvidenceBundle(base.sources*2,[base.evidence[0],other],[]).publish('条件。[1][2]，仍必要。[2]')
        self.assertEqual(response,'条件。[1]，仍必要。[1]')
        self.assertEqual(len(refs),1)
        self.assertEqual(len(refs[0]['evidence']['claims']),2)

    def test_same_version_and_range_with_different_quotes_deduplicates(self):
        base=self.bundle()
        other=dict(base.evidence[0],quote='The first condition is necessary.')
        response,sources,refs=EvidenceBundle(base.sources*2,[base.evidence[0],other],[]).publish('条件。[1][2]')
        self.assertEqual(response,'条件。[1]')
        self.assertEqual(len(refs),1)

    def test_different_quotes_in_same_section_remain_distinct(self):
        first=self.bundle();second=self.bundle('The final condition must also hold.',4)
        response,sources,refs=EvidenceBundle(first.sources+second.sources,first.evidence+second.evidence,[]).publish('条件一。[1]条件二。[2]')
        self.assertEqual(response,'条件一。[1]条件二。[2]')
        self.assertEqual(len(refs),2)
        self.assertNotEqual(refs[0]['evidence']['quote'],refs[1]['evidence']['quote'])

    def test_fabricated_quote_is_rejected_not_upgraded_to_section(self):
        bundle=self.bundle();bundle.evidence[0]['quote']='Invented source content.'
        with self.assertRaisesRegex(CitationGroundingError,'不属于'):
            bundle.publish('伪结论[1]')

    def test_uncited_checked_question_has_no_reference_cards(self):
        self.assertEqual(self.bundle().publish('哪个条件未满足？',allow_uncited_question=True),('哪个条件未满足？',[],[]))

    def test_live_pdf_verification_uses_same_protocol_without_building_index(self):
        def select(messages,**kwargs):
            candidates=json.loads(messages[1]['content'])['candidates']
            return {'evidence_ids':[candidates[0]['evidence_id']]}
        with patch('knowledge.citation_index.PSYCHOLOGY_DIR',self.root):
            bundle=choose_evidence(SimpleNamespace(chat_json=select),'解释条件',self.bundle().sources,'live')
            reply,sources,refs=bundle.publish('必要条件。[1]')
        self.assertEqual(refs[0]['evidence']['location_status'],'exact')
        self.assertTrue(refs[0]['evidence']['selections'])
        self.assertEqual(refs[0]['selection_ref']['grounding_schema'],'citation-grounding-v1')

    def test_live_block_mapping_preserves_unique_and_ambiguous_offsets(self):
        from knowledge.citation_index import LiveCitationIndex
        with patch('knowledge.citation_index.PSYCHOLOGY_DIR',self.root):
            index=LiveCitationIndex()
            blocks=index.blocks(self.record['document_id'])
            unique=next(b for b in blocks if b['block_id']==0)
            repeated=next(b for b in blocks if b['block_id']==1)
            text=index.document(self.record['document_id'],self.record['version'])['text']
        self.assertEqual(unique['status'],'exact')
        from knowledge.grounding_text import normalized
        self.assertEqual(normalized(text[unique['start']:unique['end']]),normalized(self.quote))
        self.assertEqual(repeated['status'],'ambiguous')

    def test_stale_projection_preserves_original_history_and_version(self):
        refs=self.bundle().references('条件[1]');original=deepcopy(refs)
        self.pdf.write_bytes(self.pdf.read_bytes()+b'changed')
        projected=references_for_display(refs)
        self.assertEqual(projected[0]['evidence']['location_status'],'stale')
        self.assertEqual(projected[0]['selection_ref']['rects'],[])
        self.assertEqual(projected[0]['evidence']['document_version'],original[0]['evidence']['document_version'])
        self.assertEqual(refs,original)

    def test_legacy_history_is_not_falsely_upgraded(self):
        refs=[{'source_index':0,'selection_ref':{'document_id':'old','version':'old','rects':[]}}]
        self.assertEqual(references_for_display(refs),refs)
        self.assertNotIn('evidence',refs[0])

    def test_selection_without_verifiable_evidence_returns_explicit_rejection(self):
        from agents.pdf_selection_tutor import explain_selection
        from models.task_context import TaskContext,TaskObject
        from models.task_understanding import TaskUnderstanding
        from models.student_state import StudentState
        tutor=SimpleNamespace(memory=Mock(),llm=Mock(),conversation_router=Mock(),context_sufficiency=Mock())
        tutor.memory.read_version.return_value=('v',0)
        tutor.memory.get_state.return_value=StudentState(student_id='s')
        tutor.conversation_router.route.return_value=TaskUnderstanding(student_move='question',learning_intents=['explain'])
        tutor.context_sufficiency.check.return_value=SimpleNamespace(allowed=True)
        context=TaskContext(student_id='s',message='解释选区',objects=[TaskObject(id='selected',kind='pdf_selection',
            title='条件',chapter_id=1,section_id=1)])
        resolved={'section':{'title':'条件'},'text':self.quote,'context':self.quote,'images':[],
                  'reference':self.bundle().references('结论[1]')[0]['selection_ref']}
        with patch('knowledge.grounded_citations.settings',return_value='live'),patch(
                'knowledge.grounded_citations.selection_evidence',side_effect=CitationGroundingError('未找到引句')),patch(
                'agents.pdf_selection_tutor.selection_memory',return_value={'preferences':{},'summary':''}):
            result=explain_selection(tutor,'s','解释选区',SimpleNamespace(),'production',task_context=context,resolved_selection=resolved)
        self.assertEqual(result['answer_status'],'quality_rejected')
        self.assertEqual(result['pdf_references'],[])
        self.assertIsNone(result['selection_ref'])
        tutor.llm.chat.assert_not_called()

    def test_default_is_live_and_explicit_off_retains_rollback(self):
        with patch.dict('os.environ',{},clear=True),patch('knowledge.grounded_citations.POINTER',self.root/'missing.json'):
            self.assertEqual(settings(),'live')
            with patch.dict('os.environ',{'CITATION_GROUNDING_MODE':'off'}):
                self.assertIsNone(settings())

    def test_storage_history_and_task_replay_keep_the_same_compacted_record(self):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from database import database as db
        from database.models import Base
        from agents.task_service import TaskService
        from memory.memory_manager import MemoryManager
        from models.chat_request import ChatRequest
        from models.task_understanding import TaskUnderstanding
        reply,sources,refs=self.bundle().publish('必要条件[1]')
        reference=refs[0]['selection_ref']|{'pdf_references':refs,'textbook_sources':['fixture.docx／条件']}
        engine=create_engine('sqlite:///'+str(self.root/'history.sqlite3').replace('\\','/'))
        Base.metadata.create_all(engine)
        calls=[]
        try:
            with patch.object(db,'SessionLocal',sessionmaker(bind=engine,expire_on_commit=False)):
                memory=MemoryManager();service=TaskService(SimpleNamespace(memory=memory))
                request=ChatRequest(student_id='publication',session_id='tab',request_id='r1',message='解释条件')
                def execute(request,context,resolved,intercept,guard,progress):
                    calls.append(1)
                    intercept(TaskUnderstanding(student_move='question',learning_intents=['explain']),context)
                    memory.append_exchange(request.student_id,request.message,reply,selection_ref=reference,task_guard=guard)
                    return {'reply':reply,'answer_status':'answered','pdf_references':refs,'textbook_sources':['fixture.docx／条件']}
                first=service.run(request,execute)
                replay=service.run(request,execute)
                history=memory.repo.get_conversation_with_figures('publication')[-1]
                self.assertEqual(first,replay)
                self.assertEqual(calls,[1])
                self.assertEqual(history['content'],reply)
                self.assertEqual(history['selection_ref'],reference)
                self.pdf.write_bytes(self.pdf.read_bytes()+b'changed')
                stale=service.run(request,execute)
                self.assertEqual(stale['pdf_references'][0]['evidence']['location_status'],'stale')
                self.assertEqual(memory.repo.get_conversation_with_figures('publication')[-1]['selection_ref'],reference)
        finally:
            engine.dispose()


if __name__=='__main__':
    unittest.main()
