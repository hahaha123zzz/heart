import itertools,unittest
from pydantic import ValidationError
from models.relation import RelationSpec,ClosurePreview,RelationTarget
from visualization.relation_closure import build_closure
from visualization.relation import CLOSURE_POINT,target_key
from visualization.relation_validator import evaluate_relation
from visualization.service import VisualizationError
from tests.test_relation import RelationTests


class ClosureMathTests(unittest.TestCase):
    def test_all_relations_minimality_and_step_dependencies(self):
        universe=list(itertools.product('abc',repeat=2));cases=[]
        for mask in range(512):
            pairs={p for i,p in enumerate(universe) if mask&(1<<i)}
            spec=RelationSpec(pairs=[{'source':a,'target':b} for a,b in sorted(pairs)])
            cases.append((pairs,spec,evaluate_relation(spec)['properties']))
        for original,spec,_ in cases:
            for kind in ('reflexive','symmetric','transitive'):
                result=build_closure(spec,kind);final={(p['source'],p['target']) for p in result['final_pairs']}
                self.assertTrue(original<=final)
                for larger,_,properties in cases:
                    if original<=larger and properties[kind]:self.assertTrue(final<=larger,(original,kind,larger))
                current=set(original)
                for step in result['steps']:
                    self.assertEqual(current,{(p['source'],p['target']) for p in step['before_pairs']})
                    added=(step['added_pair']['source'],step['added_pair']['target']);self.assertNotIn(added,current)
                    self.assertTrue(all((p['source'],p['target']) in current for p in step['premises']))
                    current.add(added)
                    self.assertEqual(current,{(p['source'],p['target']) for p in step['after_pairs']})
                self.assertEqual(current,final)
    def test_cycle_loops_and_empty_positive_path_semantics(self):
        spec=RelationSpec(pairs=[{'source':'a','target':'b'},{'source':'b','target':'a'}])
        result=build_closure(spec,'transitive');pairs={(p['source'],p['target']) for p in result['final_pairs']}
        self.assertIn(('a','a'),pairs);self.assertIn(('b','b'),pairs);self.assertNotIn(('c','c'),pairs)
        self.assertEqual(build_closure(RelationSpec(pairs=[]),'transitive')['added_count'],0)


class ClosureAccessTests(unittest.TestCase):
    setUp=RelationTests.setUp
    tearDown=RelationTests.tearDown
    target=RelationTests.target
    assessment=RelationTests.assessment
    answer=RelationTests.answer
    operation=RelationTests.operation
    def preview(self,**updates):
        return ClosurePreview(**dict({'student_id':'s','session_id':'tab','expected_revision':1,'kind':'transitive'},**updates))
    def test_preview_is_read_only_and_rejects_unsubmitted_and_scope(self):
        result=self.relations.closure_preview(self.identifier,self.preview())
        self.assertEqual(result['added_count'],1)
        self.assertEqual(self.relations.get(self.identifier,'s','tab'),self.artifact)
        for updates in ({'session_id':'other'},{'expected_revision':2}):
            with self.assertRaises(VisualizationError):self.relations.closure_preview(self.identifier,self.preview(**updates))
        self.assessment()
        with self.assertRaises(VisualizationError):self.relations.closure_preview(self.identifier,self.preview())
        with self.assertRaises(VisualizationError):self.relations.snapshot(self.target(closure={'kind':'transitive','step':1}),'s','tab')
        self.relations.submit(self.identifier,self.answer())
        self.assertEqual(self.relations.closure_preview(self.identifier,self.preview(expected_revision=2))['added_count'],1)
    def test_closure_task_anchor_steps_guard_and_forgetting(self):
        from agents.task_context_builder import TaskContextBuilder
        from agents.task_execution import build_execution
        from agents.task_service import TaskService
        from models.chat_request import ChatRequest
        from types import SimpleNamespace
        target=self.target(closure={'kind':'transitive','step':1})
        tasks=TaskService(SimpleNamespace(memory=self.memory))
        context,_,_=tasks._context(ChatRequest(student_id='s',session_id='tab',request_id='closure-question',message='解释这一步',relation_target=target))
        self.assertEqual(context.knowledge_point,CLOSURE_POINT);self.assertEqual(context.objects[0].section_id,5)
        self.assertIn(':closure:transitive:1',target_key(context.relation_snapshot))
        execution=build_execution(context.message,TaskContextBuilder.button_task(context,'explain'),context)
        self.assertIn('定义9.6',execution.retrieval_query)
        self.assertEqual(context.relation_snapshot['closure']['added_pair'],{'source':'a','target':'c'})
        self.memory.repo.record_event('s','closure-test',CLOSURE_POINT,'learning_observation',{'note':'测试闭包学习记录'})
        self.memory.repo.forget_learning_point('s',CLOSURE_POINT)
        with self.assertRaises(VisualizationError):self.relations.guard_snapshot(context.relation_snapshot,'s','tab')
        with self.assertRaises(VisualizationError):self.relations.snapshot(self.target(closure={'kind':'transitive','step':2}),'s','tab')
        with self.assertRaises(ValidationError):RelationTarget(artifact_id=self.identifier,expected_revision=1,property='symmetric',closure={'kind':'transitive','step':1})
