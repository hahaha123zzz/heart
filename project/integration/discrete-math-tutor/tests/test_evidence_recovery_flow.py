import unittest
from unittest.mock import patch
from agents.context_sufficiency import EvidenceDecision
from agents.quality_checker import QualityResult
from knowledge.textbook import TextbookChunk
import tests.test_quality_guard as fixtures


class ExplanationRecoveryTests(unittest.TestCase):
    def run_recovery(self,allowed):
        tutor=fixtures.QualityGuardTests().tutor([QualityResult(passed=True)] if allowed else [])
        tutor.response_generator.generate.side_effect=['根据完整教材解释角色与控制缺口。']
        first=TextbookChunk('教材','实验者偏差','双盲角色定义',frozenset(),chunk_id='one')
        extra=TextbookChunk('教材','实验者偏差','单盲程序无法控制实验者偏差',frozenset(),chunk_id='two')
        before=EvidenceDecision(status='partial',source_ids=['1'],missing=['单盲的控制局限'],reason='缺少控制机制')
        after=EvidenceDecision(status='sufficient',source_ids=['1','2'],reason='机制与定义已补全') if allowed else before
        tutor.context_sufficiency.check.side_effect=[before,after]
        with patch('orchestrator.retrieve_course',side_effect=[[first],[extra]]) as retrieve,patch('orchestrator.retrieve_figures',return_value=[]),patch('orchestrator.expand_proof_sources',return_value=([first],None)),patch('orchestrator.enrich_sources',side_effect=lambda items,*args:(items,None)):
            result=tutor.handle_turn('guard-test','只瞒被试为什么不够？')
        self.assertEqual(retrieve.call_count,2)
        self.assertEqual(tutor.context_sufficiency.check.call_count,2)
        evidence=tutor.context_sufficiency.check.call_args.args[1]
        self.assertEqual([(row['id'],row['text']) for row in evidence],[('1',first.text),('2',extra.text)])
        return tutor,result

    def test_explanation_generates_only_after_recovered_evidence_is_accepted(self):
        tutor,result=self.run_recovery(True)
        self.assertEqual(result['answer_status'],'answered')
        tutor.response_generator.generate.assert_called_once()
        tutor.memory.commit_learning_turn.assert_called_once()

    def test_still_missing_stops_without_generation_or_progress(self):
        tutor,result=self.run_recovery(False)
        self.assertEqual(result['answer_status'],'evidence_rejected')
        self.assertFalse(result['step_advanced'])
        tutor.response_generator.generate.assert_not_called()
        tutor.memory.commit_learning_turn.assert_not_called()
        tutor.state_updater.update.assert_not_called()

class RecoveryFlowTests(unittest.TestCase):
    def test_recovered_formula_is_enriched_before_recheck(self):
        tutor=fixtures.QualityGuardTests().tutor([QualityResult(passed=True)])
        tutor.response_generator.generate.side_effect=['根据补全原页解释。']
        first=TextbookChunk('教材','小节','原文',frozenset(),chunk_id=1)
        extra=TextbookChunk('教材','小节','定理9.14 公式缺失',frozenset(),chunk_id=2)
        enriched=TextbookChunk('教材','小节','定理9.14 经原页补全的公式',frozenset(),chunk_id=2)
        tutor.context_sufficiency.check.side_effect=[EvidenceDecision(status='partial',missing=['定理9.14'],reason='缺少公式'),EvidenceDecision(status='sufficient',source_ids=['1','2'],reason='已补全')]
        with patch('orchestrator.retrieve_hybrid',side_effect=[[first],[extra]]),patch('orchestrator.retrieve_figures',return_value=[]),patch('orchestrator.expand_proof_sources',return_value=([first],None)),patch('orchestrator.enrich_sources',side_effect=[([first],None),([enriched],None)]) as enrich:
            result=tutor.handle_turn('guard-test','请结合教材解释这个定理')
        self.assertEqual(enrich.call_args.args[1],'解释定理9.14')
        self.assertEqual(tutor.context_sufficiency.check.call_args.args[1][1]['text'],enriched.text)
        self.assertEqual(result['answer_status'],'answered')
    def test_closure_step_uses_closure_evidence_and_saved_navigation(self):
        from models.task_context import TaskContext,TaskObject
        from models.task_understanding import TaskUnderstanding
        from visualization.relation_closure import build_closure
        from visualization.relation_validator import template_spec,evaluate_relation
        from knowledge.proof_units import units_for
        closure=build_closure(template_spec('r3'),'transitive');step=closure['steps'][0]
        snapshot={'artifact_id':'closure-test','revision':1,'epoch':0,'property':'transitive','selected_pair':None,
            'pairs':closure['original_pairs'],'elements':['a','b','c'],'evaluation':evaluate_relation(template_spec('r3')),'answer_scope':'full',
            'closure':{'kind':'transitive','step':1,'epoch':0,'step_count':1,'current_pairs':step['after_pairs'],'reason':step['reason'],'premises':step['premises'],'added_pair':step['added_pair']}}
        context=TaskContext(student_id='guard-test',message='解释闭包这一步',knowledge_point='9.1.4  关系特性闭包',relation_snapshot=snapshot,
            objects=[TaskObject(id='relation:closure-test:closure:transitive:1',kind='relation',title='闭包步骤',text=step['reason'],chapter_id=9,section_id=5)])
        tutor=fixtures.QualityGuardTests().tutor([QualityResult(passed=True)])
        tutor.conversation_router.route.return_value=TaskUnderstanding(intent='continue',learning_intents=['explain'])
        tutor.response_generator.generate.side_effect=['本步骤补入(a,c)，依据定义9.6[1]。']
        tutor.memory.get_lesson_plan.return_value.goal=context.knowledge_point
        unit=units_for(9)['定义9.6'];source=TextbookChunk('第9章关系（新）.txt',unit.section['title'],'定义9.6 最小闭包',frozenset(),chapter_id=9,section_id=5)
        with patch('orchestrator.retrieve_hybrid',return_value=[source]),patch('orchestrator.expand_proof_sources',return_value=([source],None)),patch('orchestrator.enrich_sources',side_effect=lambda items,*args:(items,None)):
            result=tutor.handle_turn('guard-test',context.message,task_context=context)
        self.assertEqual(result['answer_status'],'answered')
        self.assertEqual(result['pdf_references'][0]['selection_ref']['rects'][0]['page'],11)
        stored=tutor.memory.commit_learning_turn.call_args.kwargs['selection_ref']
        self.assertEqual(stored['relation_context']['closure'],{'kind':'transitive','step':1,'epoch':0})
        generated=str(tutor.response_generator.generate.call_args)
        self.assertIn('current_pairs',generated)
        self.assertNotIn('selected_result',generated)
        self.assertNotIn('selected_witness',generated)
    def test_relation_navigation_survives_history_without_storing_answers(self):
        from models.task_context import TaskContext,TaskObject
        from models.task_understanding import TaskUnderstanding
        from visualization.relation_validator import evaluate_relation,template_spec
        tutor=fixtures.QualityGuardTests().tutor([QualityResult(passed=True)])
        tutor.conversation_router.route.return_value=TaskUnderstanding(intent='continue',learning_intents=['explain'])
        tutor.response_generator.generate.side_effect=['先检查相接的两条关系。']
        context=TaskContext(student_id='guard-test',message='解释当前关系',knowledge_point='9.1.3 关系的基本特性',
            objects=[TaskObject(id='relation:relation-test:transitive:ac',kind='relation',title='当前关系',text='R={(a,b),(b,c)}',chapter_id=9,section_id=4)],relation_snapshot={
            'artifact_id':'relation-test','revision':3,'epoch':0,'property':'transitive','selected_pair':{'source':'a','target':'c'},
            'pairs':template_spec('r3').model_dump()['pairs'],'elements':['a','b','c'],'evaluation':evaluate_relation(template_spec('r3')),'answer_scope':'hint'})
        tutor.memory.get_lesson_plan.return_value.goal=context.knowledge_point
        source=TextbookChunk('教材','关系','已核验的定义背景',frozenset())
        with patch('orchestrator.retrieve_hybrid',return_value=[source]),patch('orchestrator.expand_proof_sources',return_value=([source],None)),patch('orchestrator.enrich_sources',side_effect=lambda items,*args:(items,None)):
            result=tutor.handle_turn('guard-test',context.message,task_context=context)
        self.assertEqual(result['answer_status'],'answered')
        stored=tutor.memory.commit_learning_turn.call_args.kwargs['selection_ref']
        self.assertEqual(stored['relation_context']['artifact_id'],'relation-test')
        self.assertEqual(stored['relation_context']['revision'],3)
        self.assertEqual(stored['relation_context']['selected_pair'],{'source':'a','target':'c'})
        self.assertNotIn('evaluation',stored['relation_context'])
        self.assertNotIn('pairs',stored['relation_context'])
        self.assertEqual(stored['pdf_references'],[])
    def test_recheck_uses_full_question_and_stable_ids_before_publication(self):
        tutor=fixtures.QualityGuardTests().tutor([QualityResult(passed=True)])
        tutor.response_generator.generate.side_effect=['这个结论不成立']
        first=TextbookChunk('教材','握手','总度数为偶数',frozenset(),chunk_id=1)
        extra=TextbookChunk('教材','欧拉','欧拉回路定义',frozenset(),chunk_id=2)
        tutor.context_sufficiency.check.side_effect=[EvidenceDecision(status='partial',source_ids=['1'],missing=['欧拉回路定义'],reason='缺少定义'),EvidenceDecision(status='sufficient',source_ids=['1','2'],reason='可验证反例')]
        question='所有图都有欧拉回路是否成立？'
        with patch('orchestrator.retrieve_hybrid',side_effect=[[first],[extra]]),patch('orchestrator.retrieve_figures',return_value=[]),patch('orchestrator.expand_proof_sources',return_value=([first],None)),patch('orchestrator.enrich_sources',side_effect=lambda items,*args:(items,None)):
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
        with patch('orchestrator.retrieve_hybrid',side_effect=[[source],[extra]]) as retrieve,patch('orchestrator.retrieve_figures',return_value=[]),patch('orchestrator.expand_proof_sources',return_value=([source],None)),patch('orchestrator.enrich_sources',side_effect=lambda items,*args:(items,None)):
            result=tutor.handle_turn('guard-test','结论是否成立？')
        self.assertEqual(retrieve.call_count,2)
        self.assertEqual(tutor.context_sufficiency.check.call_count,2)
        self.assertEqual(result['evidence_check']['status'],'partial')
        self.assertEqual(result['answer_status'],'evidence_rejected')
        self.assertFalse(result['step_advanced'])
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
        with patch('orchestrator.retrieve_hybrid',return_value=[source]),patch('orchestrator.retrieve_figures',return_value=[]),patch('orchestrator.expand_proof_sources',return_value=([source],None)),patch('orchestrator.enrich_sources',side_effect=lambda items,*args:(items,None)):
            result=tutor.handle_turn('guard-test','这个关系是否等价？')
        reference=result['pdf_references'][0]
        self.assertEqual(reference['selection_ref']['rects'][0]['page'],17)
        # 引用随学习事件一次性提交，旧 append 路径已由事务接口替代。
        tutor.memory.commit_learning_turn.assert_called_once()
        stored=tutor.memory.commit_learning_turn.call_args.kwargs['selection_ref']
        self.assertEqual(stored['pdf_references'],result['pdf_references'])
        self.assertEqual(stored['textbook_sources'],result['textbook_sources'])
