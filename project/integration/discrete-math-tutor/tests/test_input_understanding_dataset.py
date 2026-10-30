"""独立工程标注集；预期只在断言端，不能进入模型或运行提示。"""
import csv
from pathlib import Path
import unittest
from models.chat_request import ChatRequest
from models.task_context import TaskContext
from agents.input_understanding.service import understand
from agents.input_understanding.references import introduced_objects
from agents.input_understanding.decision import decide
from tests.test_adaptive_tutoring import prior


class InputDatasetTests(unittest.TestCase):
    def test_100_curated_rule_and_binding_cases(self):
        path=Path(__file__).parent/'fixtures/input_understanding_v1.tsv'
        with path.open(encoding='utf8') as file:
            cases=list(csv.DictReader(file,delimiter='\t'))
        self.assertEqual(len(cases),100)
        self.assertEqual(len({(case['text'],case['context']) for case in cases}),100)
        for index,case in enumerate(cases,1):
            with self.subTest(case=index,text=case['text']):
                context=TaskContext(student_id='dataset',session_id='isolated',message=case['text'],input_mode='active')
                if case['context']=='pending':
                    context.tutoring=prior(pending=True)
                    question=context.tutoring['progress']['pending_question']
                    question['question_type']='choice'
                    question['options']=[{'label':'A','body':'背景音乐'},{'label':'B','body':'阅读成绩'},{'label':'C','body':'年龄'}]
                elif case['context'] in ('example','ambiguous'):
                    text='例子一：研究者安排光照强度。'
                    if case['context']=='ambiguous':text+='\n\n例子二：研究者安排睡眠时长。'
                    context.reference_objects=introduced_objects('verified-fixture',text)
                elif case['context']=='plan':
                    context.session_study_plan=dict(plan_id='p',revision=3,current_item_id='a',items=[])
                request=ChatRequest(student_id='dataset',session_id='isolated',request_id='case-'+str(index),message=case['text'])
                turn=understand(context,request)
                actions=[t.action for t in turn.tasks]
                if case['action'].startswith('!'):self.assertNotIn(case['action'][1:],actions)
                else:self.assertEqual(actions,case['action'].split('+'))
                if case['constraint']:self.assertIn(case['constraint'],turn.tasks[0].constraints)
                if case['context']=='ambiguous':self.assertEqual(decide(turn).status,'clarify')
                if case['context']=='example':self.assertEqual(turn.tasks[0].target_ref,'mention')
                self.assertEqual(turn.model_calls,0)


if __name__=='__main__':unittest.main()
