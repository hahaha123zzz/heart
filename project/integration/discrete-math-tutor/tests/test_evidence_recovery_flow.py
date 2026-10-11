import unittest
from unittest.mock import patch
from agents.context_sufficiency import EvidenceDecision
from agents.quality_checker import QualityResult
from knowledge.textbook import TextbookChunk
import tests.test_quality_guard as fixtures

class RecoveryFlowTests(unittest.TestCase):
    def test_recheck_uses_full_question_and_stable_ids_before_publication(self):
        tutor=fixtures.QualityGuardTests().tutor([QualityResult(passed=True)])
        tutor.response_generator.generate.side_effect=['这个结论不成立']
        first=TextbookChunk('教材','握手','总度数为偶数',frozenset(),chunk_id=1)
        extra=TextbookChunk('教材','欧拉','欧拉回路定义',frozenset(),chunk_id=2)
        tutor.context_sufficiency.check.side_effect=[EvidenceDecision(status='partial',source_ids=['1'],missing=['欧拉回路定义'],reason='缺少定义'),EvidenceDecision(status='sufficient',source_ids=['1','2'],reason='可验证反例')]
        question='所有图都有欧拉回路是否成立？'
        with patch('orchestrator.retrieve_hybrid',side_effect=[[first],[extra]]),patch('orchestrator.retrieve_figures',return_value=[]),patch('orchestrator.expand_proof_sources',return_value=([first],None)),patch('orchestrator.enrich_sources',return_value=([first],None)):
            result=tutor.handle_turn('guard-test',question)
        self.assertEqual(result['answer_status'],'answered')
        self.assertEqual(tutor.context_sufficiency.check.call_count,2)
        args=tutor.context_sufficiency.check.call_args.args
        self.assertEqual(args[0],question)
        self.assertEqual([(e['id'],e['text']) for e in args[1]],[('1',first.text),('2',extra.text)])
    def test_still_missing_evidence_stops_after_one_recovery_without_progress_writes(self):
        tutor=fixtures.QualityGuardTests().tutor([])
        source=TextbookChunk('教材','小节','原依据',frozenset(),chunk_id=1)
        extra=TextbookChunk('教材','小节','补充依据',frozenset(),chunk_id=2)
        tutor.context_sufficiency.check.return_value=EvidenceDecision(status='partial',source_ids=['1'],missing=['关键定义'],reason='仍不足')
        with patch('orchestrator.retrieve_hybrid',side_effect=[[source],[extra]]) as retrieve,patch('orchestrator.retrieve_figures',return_value=[]),patch('orchestrator.expand_proof_sources',return_value=([source],None)),patch('orchestrator.enrich_sources',return_value=([source],None)):
            result=tutor.handle_turn('guard-test','结论是否成立？')
        self.assertEqual(retrieve.call_count,2)
        self.assertEqual(tutor.context_sufficiency.check.call_count,2)
        self.assertEqual(result['evidence_check']['status'],'partial')
        tutor.memory.snapshot.assert_not_called()
        tutor.response_generator.generate.assert_not_called()
        tutor.state_updater.update.assert_not_called()
        tutor.memory.save_state.assert_not_called()
        tutor.memory.set_active_goal.assert_not_called()
    def test_ordinary_definition_reference_is_saved_with_history(self):
        from knowledge.proof_units import units_for
        unit=units_for(9)['定义9.7']
        source=TextbookChunk('第9章关系（新）.txt',unit.section['title'],'定义9.7 等价关系要求三条性质',frozenset(),chapter_id=9,section_id=unit.section['id'])
        tutor=fixtures.QualityGuardTests().tutor([QualityResult(passed=True)])
        tutor.response_generator.generate.side_effect=['R不是等价关系[1]。']
        with patch('orchestrator.retrieve_hybrid',return_value=[source]),patch('orchestrator.retrieve_figures',return_value=[]),patch('orchestrator.expand_proof_sources',return_value=([source],None)),patch('orchestrator.enrich_sources',return_value=([source],None)):
            result=tutor.handle_turn('guard-test','这个关系是否等价？')
        reference=result['pdf_references'][0]
        self.assertEqual(reference['selection_ref']['rects'][0]['page'],17)
        assistant=tutor.memory.append.call_args_list[-1]
        stored=assistant.kwargs['selection_ref']
        self.assertEqual(stored['pdf_references'],result['pdf_references'])
        self.assertEqual(stored['textbook_sources'],result['textbook_sources'])
