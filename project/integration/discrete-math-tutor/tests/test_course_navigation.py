"""真实教材目录和隔离任务库验证；模型输出仅用于测试事务边界。"""
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from agents.task_service import TaskService
from database import database as db
from database.learning_tasks import LearningTaskRepository
from database.models import Base
from knowledge.course_navigation import intent, outline, read_target, resolve
from memory.memory_manager import MemoryManager
from models.chat_request import ChatRequest
from models.task_context import ReaderLocation
from models.task_understanding import TaskUnderstanding
from models.student_state import StudentState


class NavigationTests(unittest.TestCase):
    def test_chapter_aliases_resolve_identically_and_override_reader(self):
        values = [resolve(q, reader_location=ReaderLocation(chapter_id=2, section_id=1)) for q in
                  ('我想要学习教材第一章的内容', '学习第1章', '学习实验心理学概论')]
        self.assertEqual(len({v['id'] for v in values}), 1)
        self.assertEqual(values[0]['chapter_id'], 1)
        source = read_target(values[0])[0]
        self.assertGreater(len(source.text), 100)
        self.assertTrue(source.source_spans)
        from knowledge.citation_locations import complete_pdf_references
        references = complete_pdf_references([source], '教材解释[1]', [])
        self.assertTrue(references)
        self.assertEqual(references[0]['selection_ref']['chapter_id'], 1)
        self.assertFalse(values[0]['covered'])
        self.assertFalse(values[0]['explained'])

    def test_next_target_selected_before_reading(self):
        first = resolve('学习第一章')
        second = resolve('继续下一个知识点', cursor=first)
        self.assertNotEqual(first['id'], second['id'])
        self.assertGreater(second['position'], first['position'])
        self.assertNotIn('下一个知识点', read_target(second)[0].text)

    def test_no_path_cannot_invent_next_concept(self):
        self.assertEqual(resolve('自变量学完了，继续下一个知识点')['status'], 'clarify')

    def test_same_topic_messages_are_not_navigation(self):
        for message in ('没听懂', '再解释一次', '继续这个例子', '下一步推导', '先不进入下一章',
                        '不要换到下一个知识点', '第一章自变量是什么', '比较第一章和第二章',
                        '我想学习第一章的自变量', '讲解第一章的实验程序', '下一个知识点是什么意思'):
            with self.subTest(message=message):
                self.assertIsNone(intent(message))

    def test_section_and_chapter_have_different_scope(self):
        first = resolve('学习第一章')
        section = resolve('继续下一节', cursor=first)
        chapter = resolve('继续下一章', cursor=first)
        self.assertEqual((section['chapter_id'], section['section_id']), (1, 2))
        self.assertEqual((chapter['chapter_id'], chapter['section_id']), (2, 1))

    def test_stale_version_does_not_fall_back_to_reader(self):
        first = dict(resolve('学习第一章'), version='stale')
        self.assertEqual(resolve('下一节', cursor=first,
            reader_location=ReaderLocation(chapter_id=1, section_id=1))['status'], 'clarify')

    def test_path_end_is_not_evidence_failure(self):
        last = [u for u in outline() if u['chapter_id'] == 1][-1]
        self.assertEqual(resolve('下一个知识点', cursor=last)['status'], 'complete')

    def test_invalid_chapter_is_not_silently_replaced(self):
        self.assertEqual(resolve('学习第99章')['status'], 'clarify')

    def test_changed_pdf_is_rejected(self):
        with patch('knowledge.course_navigation.pdf_path') as path:
            path.return_value.read_bytes.return_value = b'changed'
            with self.assertRaisesRegex(ValueError, '原件已变化'):
                read_target(resolve('学习第一章'))

    def test_navigation_budget_is_shared_and_does_not_expand_simplification(self):
        from agents.reply_budget import reply_budget
        from agents.task_execution import TaskExecution
        execution = TaskExecution(learning_intents=['explain'],
            targets=[{'kind': 'course_navigation', 'mode': 'start'}])
        self.assertEqual(reply_budget('学习第一章', execution=execution).maximum, 360)
        execution.targets[0]['mode'] = 'repeat'
        self.assertEqual(reply_budget('没听懂', execution=execution).maximum, 260)
        execution.learning_intents = ['hint']
        execution.targets[0]['mode'] = 'start'
        self.assertEqual(reply_budget('只给提示', execution=execution).maximum, 260)

    def test_host_orchestrator_uses_resolved_source_without_search_or_mastery_plan(self):
        from tests import test_quality_guard
        from agents.quality_checker import QualityResult
        tutor = test_quality_guard.QualityGuardTests().tutor([QualityResult(passed=True)])
        tutor.response_generator.generate.side_effect = None
        tutor.response_generator.generate.return_value = '实验心理学使用实验方法研究心理现象。[1]'
        with patch('orchestrator.retrieve_course', side_effect=AssertionError('导航不应搜索口令')):
            result = tutor.handle_turn('guard-test', '我想要学习教材第一章的内容')
        self.assertEqual(result['answer_status'], 'answered')
        self.assertTrue(result['pdf_references'])
        self.assertEqual(result['response_path'], 'direct_answer')
        tutor.lesson_planner.create.assert_not_called()
        self.assertIsNone(tutor.memory.commit_learning_turn.call_args.kwargs['lesson_plan'])


class NavigationTaskTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = create_engine('sqlite:///' + self.temp.name.replace('\\', '/') + '/test.db')
        @event.listens_for(self.engine, 'connect')
        def fk(connection, _):
            connection.execute('PRAGMA foreign_keys=ON')
        Base.metadata.create_all(self.engine)
        self.factory = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)
        self.patch = patch.object(db, 'SessionLocal', self.factory)
        self.patch.start()
        self.memory = MemoryManager()
        self.repo = LearningTaskRepository()
        self.service = TaskService(SimpleNamespace(memory=self.memory), self.repo)
        self.contexts = []

    def tearDown(self):
        self.patch.stop()
        self.engine.dispose()
        self.temp.cleanup()

    def run_turn(self, message, request_id, *, status='answered', after_start=None, session_id='tab', **kwargs):
        request = ChatRequest(student_id='nav', message=message, request_id=request_id, session_id=session_id, **kwargs)
        def execute(request, context, resolved, intercept, guard, progress):
            self.contexts.append(context)
            stopped = intercept(TaskUnderstanding(student_move='question', learning_intents=['explain']), context)
            if stopped:
                return stopped
            if after_start:
                after_start(context)
            guard()
            return {'reply': '有来源的解释', 'answer_status': status, 'knowledge_point': context.knowledge_point,
                    'memory_commit': {'status': 'committed'}, 'step_advanced': False}
        return self.service.run(request, execute)

    def test_replay_does_not_advance_twice_and_service_recreation_resumes(self):
        first = self.run_turn('学习第一章', 'a')
        repeated = self.run_turn('学习第一章', 'a')
        self.assertEqual(first, repeated)
        self.assertEqual(len(self.contexts), 1)
        self.service = TaskService(SimpleNamespace(memory=self.memory), LearningTaskRepository())
        second = self.run_turn('继续下一个知识点', 'b')
        self.assertNotEqual(first['course_navigation']['id'], second['course_navigation']['id'])
        self.assertTrue(second['course_navigation']['explained'])
        self.assertFalse(second['course_navigation']['covered'])
        self.assertEqual(self.memory.get_state('nav', second['knowledge_point']).mastery,
                         StudentState(student_id='nav').mastery)

    def test_failed_explanation_does_not_move_cursor(self):
        first = self.run_turn('学习第一章', 'a')
        self.run_turn('下一个知识点', 'b', status='quality_rejected')
        retry = self.run_turn('下一个知识点', 'c')
        self.assertEqual(self.contexts[-1].course_navigation['id'], self.contexts[-2].course_navigation['id'])
        self.assertNotEqual(first['course_navigation']['id'], retry['course_navigation']['id'])

    def test_explicit_chapter_wins_over_reader(self):
        self.run_turn('学习第一章', 'a', reader_location={'chapter_id': 2, 'section_id': 1})
        self.assertEqual(self.contexts[-1].course_navigation['chapter_id'], 1)

    def test_simplify_keeps_current_target_despite_reader_elsewhere(self):
        first = self.run_turn('学习第一章', 'a')
        second = self.run_turn('没听懂，请换个说法', 'b', reader_location={'chapter_id': 2, 'section_id': 1})
        self.assertEqual(first['course_navigation']['id'], second['course_navigation']['id'])
        self.assertEqual(self.contexts[-1].course_navigation['mode'], 'repeat')

    def test_explicit_new_topic_is_not_forced_to_old_navigation(self):
        self.run_turn('学习第一章', 'a')
        self.run_turn('再解释一下因变量', 'b')
        self.assertIsNone(self.contexts[-1].course_navigation)

    def test_other_session_has_no_cursor(self):
        self.run_turn('学习第一章', 'a')
        self.run_turn('下一个知识点', 'b', session_id='other')
        self.assertEqual(self.contexts[-1].course_navigation['status'], 'clarify')

    def test_deleted_point_does_not_resurrect_navigation(self):
        first = self.run_turn('学习第一章', 'a')
        self.memory.forget_point('nav', first['knowledge_point'])
        self.run_turn('下一个知识点', 'b')
        self.assertEqual(self.contexts[-1].course_navigation['status'], 'clarify')

    def test_cancelled_late_result_does_not_publish_cursor(self):
        def cancel(context):
            rows = self.repo.recent('nav', 'tab', limit=12)
            self.assertEqual(rows, [])
            from sqlalchemy import select
            from database.models import LearningTaskRow
            with self.factory() as session:
                task = session.scalar(select(LearningTaskRow))
                task_id, revision = task.id, task.revision
            self.repo.cancel('nav', 'tab', task_id, revision)
        result = self.run_turn('学习第一章', 'a', after_start=cancel)
        self.assertEqual(result['answer_status'], 'task_conflict')
        self.assertNotIn('course_navigation', result)
        self.run_turn('下一个知识点', 'b')
        self.assertEqual(self.contexts[-1].course_navigation['status'], 'clarify')

    def test_document_change_during_execution_blocks_result(self):
        with patch('knowledge.course_navigation.validate', side_effect=ValueError('教材已更新')):
            result = self.run_turn('学习第一章', 'a')
        self.assertEqual(result['answer_status'], 'document_changed')
        self.assertEqual(self.repo.recent('nav', 'tab'), [])
        repeated = self.run_turn('学习第一章', 'a')
        self.assertEqual(repeated['answer_status'], 'document_changed')


if __name__ == '__main__':
    unittest.main()
