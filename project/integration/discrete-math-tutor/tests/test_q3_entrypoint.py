"""Q3 feature flag must select the local loop only for plain chat."""
import importlib
import os
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from database import database as db
from database.models import Base
from memory.memory_manager import MemoryManager
from models.chat_request import ChatRequest
from models.task_context import TaskContext


class Q3EntrypointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.previous = sys.modules.pop("main", None)
        cls.temp = tempfile.TemporaryDirectory()
        cls.engine = create_engine(
            "sqlite:///" + cls.temp.name.replace("\\", "/") + "/entry.db",
            connect_args={"check_same_thread": False})

        @event.listens_for(cls.engine, "connect")
        def fk(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(cls.engine)
        cls.db_patch = patch.object(
            db, "SessionLocal",
            sessionmaker(bind=cls.engine, autoflush=False, expire_on_commit=False))
        cls.db_patch.start()
        cls.tutor = Mock()
        cls.tutor.memory = MemoryManager()
        cls.tutor.handle_turn.return_value = {"reply": "旧链路"}
        with patch("orchestrator.TutorOrchestrator", return_value=cls.tutor), \
                patch("database.database.init_db"), \
                patch("practice_api.recover_interrupted_submissions"):
            cls.module = importlib.import_module("main")

    @classmethod
    def tearDownClass(cls):
        cls.db_patch.stop(); cls.engine.dispose(); cls.temp.cleanup()
        sys.modules.pop("main", None)
        if cls.previous is not None:
            sys.modules["main"] = cls.previous

    def test_plain_chat_uses_local_loop_when_enabled(self):
        request = ChatRequest(student_id="s", session_id="legacy", request_id="r",
                              message="解释自变量")
        context = TaskContext(student_id="s", message=request.message,
                              knowledge_point="自变量")
        with patch.dict(os.environ, LOCAL_AGENT_LOOP_ENABLED="1"), \
                patch("agents.agent_loop_service.run_agent_loop_turn",
                      return_value={"reply": "Q3", "answer_status": "answered"}) as run:
            result = self.module._execute_task_turn(
                request, context, None, None, lambda: None, None)
        self.assertEqual(result["reply"], "Q3")
        self.assertIsNone(run.call_args.kwargs["previous"])

    def test_plain_chat_keeps_old_path_when_disabled(self):
        request = ChatRequest(student_id="s", session_id="legacy", request_id="r",
                              message="解释自变量")
        context = TaskContext(student_id="s", message=request.message,
                              knowledge_point="自变量")
        with patch.dict(os.environ, LOCAL_AGENT_LOOP_ENABLED="0"):
            result = self.module._execute_task_turn(
                request, context, None, None, lambda: None, None)
        self.assertEqual(result["reply"], "旧链路")
        self.tutor.handle_turn.assert_called_once()

    def test_selection_does_not_enter_local_loop(self):
        from knowledge.pdf_reader import PDFSelection
        request = ChatRequest(
            student_id="s", session_id="legacy", request_id="r",
            message="解释选中内容",
            selection=PDFSelection(
                document_id="experimental-psychology-3:chapter-01",
                version="a" * 64, kind="text",
                rects=[{"page": 1, "x1": .1, "y1": .1, "x2": .2, "y2": .2}]))
        context = TaskContext(student_id="s", message=request.message)
        with patch.dict(os.environ, LOCAL_AGENT_LOOP_ENABLED="1", SELECTED_TEXT_AGENT_LOOP_ENABLED="0"), \
                patch("agents.agent_loop_service.run_agent_loop_turn") as run, \
                patch("agents.pdf_selection_tutor.explain_selection",
                      return_value={"reply": "选区"}) as selection:
            result = self.module._execute_task_turn(
                request, context, {"reference": {}}, None, lambda: None, None)
        self.assertEqual(result["reply"], "选区")
        run.assert_not_called()
        selection.assert_called_once()

    def test_text_selection_enters_shared_loop_when_adapter_enabled(self):
        request = ChatRequest(student_id='s', message='解释选中内容', selection={
            'document_id':'chapter-02','version':'a'*64,'kind':'text',
            'rects':[{'page':1,'x1':.1,'y1':.1,'x2':.2,'y2':.2}]})
        context = TaskContext(student_id='s', message=request.message)
        with patch.dict(os.environ, LOCAL_AGENT_LOOP_ENABLED='1', SELECTED_TEXT_AGENT_LOOP_ENABLED='1'), \
             patch('agents.agent_loop_service.run_agent_loop_turn',return_value={'reply':'shared'}) as run:
            result = self.module._execute_task_turn(request,context,{'server':'resolved'},None,lambda:None,None)
        self.assertEqual(result['reply'],'shared')
        self.assertEqual(run.call_args.kwargs['resolved'],{'server':'resolved'})

    def test_area_selection_stays_on_original_pipeline_even_when_text_flag_enabled(self):
        request = ChatRequest(student_id='s', message='解释图片', selection={
            'document_id':'chapter-02','version':'a'*64,'kind':'area',
            'rects':[{'page':1,'x1':.1,'y1':.1,'x2':.2,'y2':.2}]})
        context = TaskContext(student_id='s', message=request.message)
        with patch.dict(os.environ, LOCAL_AGENT_LOOP_ENABLED='1', SELECTED_TEXT_AGENT_LOOP_ENABLED='1'), \
             patch('agents.agent_loop_service.run_agent_loop_turn') as run, \
             patch('agents.pdf_selection_tutor.explain_selection',return_value={'reply':'area'}):
            result = self.module._execute_task_turn(request,context,{},None,lambda:None,None)
        self.assertEqual(result['reply'],'area')
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
