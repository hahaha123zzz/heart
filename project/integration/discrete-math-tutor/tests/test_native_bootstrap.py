"""原生启动不装配旧教学主体，未迁入口仍按需可用。"""
from contextlib import ExitStack
from types import SimpleNamespace
import unittest
from unittest.mock import patch, Mock
from orchestrator import TutorOrchestrator


class NativeBootstrapTests(unittest.TestCase):
    def test_native_construction_skips_legacy_and_old_entry_initializes_once(self):
        names=('ContextSufficiency','ConversationRouter','LessonPlanner','EvidenceExtractor',
               'MisconceptionResolver','StateAnalyzer','TeachingPlanner','StrategyRouter',
               'QuestionDesigner','ResponseGenerator','QualityChecker','StateUpdater','TutorErrorDetector')
        factories={name:Mock(return_value=object()) for name in names}
        memory=SimpleNamespace(accounts=SimpleNamespace(cleanup_after_code_update=lambda:0))
        with ExitStack() as stack:
            stack.enter_context(patch('orchestrator.init_db'))
            stack.enter_context(patch.multiple('orchestrator',**factories))
            textbook=stack.enter_context(patch('orchestrator.load_textbook',return_value=[]))
            tutor=TutorOrchestrator(llm=SimpleNamespace(),memory=memory,load_legacy=False)
            self.assertTrue(all(mock.call_count==0 for mock in factories.values()))
            self.assertNotIn('quality_checker',tutor.__dict__)
            self.assertIs(tutor.quality_checker,factories['QualityChecker'].return_value)
            self.assertIs(tutor.conversation_router,factories['ConversationRouter'].return_value)
            self.assertTrue(all(mock.call_count==1 for mock in factories.values()))
            textbook.assert_called_once()
