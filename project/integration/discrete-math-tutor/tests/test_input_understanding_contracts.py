"""协议拒绝错误动作/身份/依赖，保留原话与作用范围。"""
import unittest
from pydantic import ValidationError
from models.input_understanding import ContextHeader, GroundedTurn, InputEnvelope, ObjectReference, ScopedDirective, TaskFrame
from agents.input_understanding.rules import normalize, choice_submission, explanation_before_resume, resume_requested,non_submission


def envelope(raw='解释这个'):
    text, positions = normalize(raw)
    return InputEnvelope(request_id='r', raw_text=raw, normalized_text=text, source_positions=positions)


def question_turn(**changes):
    return GroundedTurn(**(dict(envelope=envelope(), context=ContextHeader(student_id='s',session_id='x',
        course_id='c',pending_question_id='q',pending_owner='host_formative'),
        references=[ObjectReference(ref_id='pending',kind='pending_question',canonical_id='q',status='resolved',origin='task')]) | changes))


class InputContractTests(unittest.TestCase):
    def test_normalization_preserves_formula_negation_and_positions(self):
        value=envelope('  不要\n改写 p<0.05 和因变量  ')
        self.assertEqual(value.normalized_text,'不要 改写 p<0.05 和因变量')
        with self.assertRaises(ValidationError):
            InputEnvelope(**(value.model_dump()|{'normalized_text':value.normalized_text.replace('<','>')}))

    def test_dependencies_and_reference_identity_are_validated(self):
        good=question_turn(tasks=[TaskFrame(task_frame_id='t1',action='explain_content',query='操作性定义'),
            TaskFrame(task_frame_id='t2',action='resume_pending_question',target_ref='pending',depends_on=['t1'])])
        self.assertTrue(good.explain_then_resume)
        for tasks in ([TaskFrame(task_frame_id='t',action='explain_content',depends_on=['t'])],
                      [TaskFrame(task_frame_id='t',action='explain_content',target_ref='made-up')]):
            with self.assertRaises(ValidationError):question_turn(tasks=tasks)

    def test_submission_requires_current_question(self):
        with self.assertRaises(ValidationError):
            question_turn(tasks=[TaskFrame(task_frame_id='t',action='submit_student_answer')])
        with self.assertRaises(ValidationError):
            TaskFrame(task_frame_id='t',action='answer')

    def test_long_term_scope_must_require_confirmation_and_literal_quote(self):
        with self.assertRaises(ValidationError):
            ScopedDirective(scope='persistent',key='answer_length',value=1.,quote='以后详细一点')
        directive=ScopedDirective(scope='persistent',key='answer_length',value=1.,quote='以后详细一点',requires_confirmation=True)
        with self.assertRaises(ValidationError):question_turn(directives=[directive])

    def test_unsupported_fields_versions_and_boolean_types_rejected(self):
        with self.assertRaises(ValidationError):
            InputEnvelope(**(envelope().model_dump()|{'schema_version':2}))
        with self.assertRaises(ValidationError):
            ScopedDirective(scope='turn',key='no_questions',value='true',quote='不要出题')
        with self.assertRaises(ValidationError):
            TaskFrame(task_frame_id='t',action='explain_content',approved=True)

    def test_conflicting_scoped_directives_cannot_silently_overwrite(self):
        value=envelope('以后详细一点，但是以后简短一点')
        directives=[ScopedDirective(scope='persistent',key='answer_length',value=v,quote=q,requires_confirmation=True)
                    for v,q in ((1.,'以后详细一点'),(0.,'以后简短一点'))]
        with self.assertRaises(ValidationError):question_turn(envelope=value,directives=directives)

    def test_negated_choice_and_question_are_not_answers(self):
        options={'A':'自变量','B':'因变量','C':'额外变量'}
        self.assertEqual(choice_submission('我选 B',options),'B')
        for text in ('我不选 B','不是 B','为什么 B 不对？','B 或 C','先解释B，再回原题',
                     '我不选择 B','我还没有选 B','我选 B 但不提交','我不认为选项 B','不是选项 B'):
            self.assertEqual(choice_submission(text,options),'',text)
            self.assertTrue(non_submission(text),text)

    def test_compound_resume_preserves_order_and_negation(self):
        self.assertEqual(explanation_before_resume('先解释“操作性定义”这个词，再回到原来的题，不要替我作答。'),'操作性定义')
        self.assertTrue(resume_requested('回到原题'))
        self.assertFalse(resume_requested('不要回到原题，先解释操作性定义'))
        self.assertFalse(non_submission('自变量是研究者操纵的条件或因素。'))

    def test_chapter_overview_action_and_route(self):
        from agents.input_understanding import ontology
        from agents.input_understanding.service import understand
        from models.chat_request import ChatRequest
        from models.task_context import TaskContext
        message='我想学习第一章的主要内容'
        context=TaskContext(student_id='s',session_id='x',message=message,input_mode='active')
        turn=understand(context,ChatRequest(student_id='s',session_id='x',request_id='r',message=message))
        self.assertEqual(turn.tasks[0].action,'chapter_overview')
        self.assertEqual(turn.route.kind,'chapter_overview')
        self.assertEqual(turn.route.chapter_id,1)
        self.assertEqual(ontology.intent_for('chapter_overview'),'learning_management')
        self.assertEqual(ontology.intent_for('section_overview'),'learning_management')

    def test_saved_old_turn_without_route_still_validates(self):
        data=question_turn(tasks=[TaskFrame(task_frame_id='t1',action='explain_content',query='自变量')]).model_dump()
        data.pop('route',None)
        self.assertIsNone(GroundedTurn.model_validate(data).route)


if __name__=='__main__':unittest.main()
