"""唯一回合路由表：规则优先，复用已校验的导航、计划与工具目的判断。"""
import unittest
from agents.input_understanding.route import classify_route
from agents.input_understanding.service import understand
from models.chat_request import ChatRequest
from models.input_understanding import ObjectReference, GroundedTurn
from models.task_context import TaskContext

PENDING = {'progress': {'pending_question': {'question_id': 'q', 'prompt': '哪个是自变量？',
    'options': [{'label': 'A', 'body': '自变量'}, {'label': 'B', 'body': '因变量'}]}}}
FIGURE = ObjectReference(ref_id='history-figure', kind='figure', canonical_id='image-1',
    status='resolved', origin='history', version='f' * 64, title='图5-2')

CASES = [
    ("我想学习第一章的主要内容", "chapter_overview", "chapter", 1, "textbook"),
    ("第一章讲什么", "chapter_overview", "chapter", 1, "textbook"),
    ("第一章第一节讲什么", "section_overview", "section", 1, "textbook"),
    ("什么是实验心理学", "concept_answer", "kp", None, "textbook"),
    ("比较观察法和实验法", "comparison", "kp", None, "textbook"),
    ("教材有几本", "catalog", "course", None, "catalog"),
    ("列出教材文件清单", "catalog", "course", None, "catalog"),
    ("教材中与他相关的内容有哪些，我想学习", "clarify", "none", None, "textbook"),
    ("帮我制定第一章的学习计划", "learning_plan", "chapter", 1, "textbook"),
    ("今天怎么安排", "learning_plan", "none", None, "textbook"),
    ("我选 B", "exercise", "pending", None, "textbook"),
    ("不要出题，只讲第一章主要内容", "chapter_overview", "chapter", 1, "textbook"),
    ("刚才那个图", "reader_action", "figure", None, "reader_action"),
    ("这个呢", "clarify", "none", None, "textbook"),
]


def route(message, *, tutoring=None, reference_objects=()):
    context = TaskContext(student_id='s', session_id='x', message=message, knowledge_point='自变量',
        input_mode='active', tutoring=tutoring or {}, reference_objects=list(reference_objects))
    request = ChatRequest(student_id='s', session_id='x', request_id='r', message=message)
    return classify_route(understand(context, request), context)


def bound_claim(message='教材中与他相关的内容有哪些，我想学习', query='与费希纳相关的内容'):
    """理解层已把“他”绑定到一条已校验历史片段。"""
    context = TaskContext(student_id='s', session_id='x', message=message,
        knowledge_point='自变量', input_mode='active')
    request = ChatRequest(student_id='s', session_id='x', request_id='r', message=message)
    value = understand(context, request).model_dump()
    value['route'] = None  # simulate a later binding; route is re-derived from the bound turn
    value['references'] = [ObjectReference(ref_id='history-claim', kind='assistant_claim',
        canonical_id='turn:1:0:12:abc', status='resolved', origin='history',
        title='费希纳', quote=query).model_dump()]
    value['tasks'][0]['target_ref'] = 'history-claim'
    value['tasks'][0]['query'] = query
    value['resolution_status'] = 'resolved'
    return GroundedTurn.model_validate(value), context


class TurnRouterTests(unittest.TestCase):
    def test_figure_explanation_does_not_become_page_navigation(self):
        for message in ('解释刚才那个图', '不要执行教材页面跳转，只解释刚才那个图',
                        '不要跳转或打开页面，说明刚才那个图的步骤'):
            with self.subTest(message=message):
                value = route(message, reference_objects=[FIGURE])
                self.assertEqual(value.tool_purpose, 'textbook')
                self.assertNotEqual(value.kind, 'reader_action')
        self.assertEqual(route('不要跳转，只解释自变量').tool_purpose, 'textbook')
        self.assertEqual(route('不要跳转第一页，打开第二页').tool_purpose, 'reader_action')
        from agents.input_understanding.route import reader_requested
        from agents.tools.first_wave_runtime import purpose
        for message in ('不要执行教材页面跳转，只解释图5-2', '不用打开第三页', '别定位到那里'):
            self.assertFalse(reader_requested(message))
            self.assertEqual(purpose(message), 'textbook')

    def test_route_table(self):
        for message, kind, scope, chapter_id, purpose in CASES:
            extra = {'tutoring': PENDING} if message == '我选 B' else {}
            if message == '刚才那个图':
                extra['reference_objects'] = (FIGURE,)
            with self.subTest(message=message):
                value = route(message, **extra)
                self.assertEqual(value.kind, kind)
                self.assertEqual(value.scope, scope)
                self.assertEqual(value.chapter_id, chapter_id)
                self.assertEqual(value.tool_purpose, purpose)
                self.assertEqual(value.source, 'rule')

    def test_bare_chapter_mention_repeats_overview_not_next_heading(self):
        context = TaskContext(student_id='s', session_id='x', message='第一章', input_mode='active',
            course_navigation={'status': 'ready', 'chapter_id': 1, 'id': 'ch1:s1:b6',
                               'title': '实验心理学的含义'})
        request = ChatRequest(student_id='s', session_id='x', request_id='r', message='第一章')
        value = classify_route(understand(context, request), context)
        self.assertEqual(value.kind, 'chapter_overview')
        self.assertEqual(value.navigation_mode, 'repeat')
        self.assertEqual(value.target_id, 'chapter:1')

    def test_bare_chapter_without_previous_cursor_is_overview(self):
        value = route('第一章')
        self.assertEqual(value.kind, 'chapter_overview')
        self.assertEqual(value.navigation_mode, 'overview')
        self.assertEqual(value.target_id, 'chapter:1')

    def test_chapter_overview_query_is_structural_not_the_raw_pronoun_sentence(self):
        value = route('我想学习第一章的主要内容')
        self.assertEqual(value.target_id, 'chapter:1')
        self.assertEqual(value.navigation_mode, 'overview')
        self.assertIn('实验心理学概论', value.query)
        self.assertIn('第一节', value.query)
        self.assertNotIn('主要内容', value.query)

    def test_section_overview_names_the_resolved_section(self):
        value = route('第一章第一节讲什么')
        self.assertEqual((value.chapter_id, value.section_id), (1, 1))
        self.assertEqual(value.target_id, 'section:1:1')
        self.assertIn('实验心理学的研究对象', value.name)

    def test_content_question_is_not_catalog(self):
        value = route('教材中与他相关的内容有哪些，我想学习')
        self.assertNotEqual(value.tool_purpose, 'catalog')
        self.assertEqual(value.kind, 'clarify')

    def test_explicit_file_count_stays_catalog(self):
        self.assertEqual(route('教材有几本').tool_purpose, 'catalog')

    def test_bound_reference_suppresses_the_pronoun_clarify(self):
        turn, context = bound_claim()
        value = classify_route(turn, context)
        self.assertEqual(value.kind, 'concept_answer')
        self.assertNotEqual(value.reason, 'unresolved_reference')

    def test_unbound_pronoun_still_clarifies(self):
        self.assertEqual(route('教材中与他相关的内容有哪些，我想学习').kind, 'clarify')

    def test_understand_attaches_the_route_to_the_turn(self):
        message = '我想学习第一章的主要内容'
        context = TaskContext(student_id='s', session_id='x', message=message, input_mode='active')
        request = ChatRequest(student_id='s', session_id='x', request_id='r', message=message)
        context.input_understanding = understand(context, request)
        self.assertEqual(context.input_understanding.route.kind, 'chapter_overview')
        self.assertEqual(context.input_understanding.route.chapter_id, 1)
        self.assertEqual(context.input_understanding.tasks[0].action, 'chapter_overview')

    def test_turn_constraints_are_carried_into_the_route(self):
        value = route('不要出题，只讲第一章主要内容')
        self.assertIn('no_questions', value.constraints)

    def test_apply_route_sets_chapter_target_and_clears_old_navigation(self):
        from models.input_understanding import TurnRoute
        from models.task_context import apply_route
        context = TaskContext(student_id='s', session_id='x', message='我想学习第一章',
                              input_mode='active', course_navigation={'status': 'ready', 'title': '旧目标'})
        apply_route(context, TurnRoute(kind='chapter_overview', scope='chapter', chapter_id=1,
            target_id='chapter:1', name='实验心理学概论', reason='test'))
        self.assertEqual(context.turn_route['kind'], 'chapter_overview')
        self.assertEqual(context.activity_target['target_id'], 'chapter:1')
        self.assertEqual(context.activity_target['chapter_id'], 1)
        self.assertIsNone(context.activity_target['section_id'])
        self.assertIsNone(context.course_navigation)
        self.assertNotIn('turn_route', context.prompt_payload())


if __name__ == '__main__':
    unittest.main()
