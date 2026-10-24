"""Q3 任务级暂停/接续/重复答复/取消验证。"""
import tempfile
import unittest
from unittest.mock import Mock, patch

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from agents.task_service import TaskService
from database import database as db
from database.learning_tasks import LearningTaskRepository
from database.models import Base
from memory.memory_manager import MemoryManager
from models.chat_request import ChatRequest
from agents.agent_loop_service import run_agent_loop_turn
from agents.q3_navigation import StubLearningNavigator
from llm.client import ChatToolCall, ChatToolResult
from tests.test_q3_agent_loop import ScriptedLLM, final_round, tool_round


class LiveLoopExecutor:
    def __init__(self, llm, memory):
        self.llm = llm
        self.memory = memory
        self.navigator = StubLearningNavigator()
        self.calls = []

    def __call__(self, request, context, resolved, intercept, guard, progress, *, previous=None):
        self.calls.append(previous)
        from types import SimpleNamespace
        orchestrator = SimpleNamespace(llm=self.llm, memory=self.memory, quality_checker=None)
        return run_agent_loop_turn(
            orchestrator=orchestrator, request=request, context=context, guard=guard,
            progress=progress, previous=previous, navigator=self.navigator,
            publish_gate=lambda text, result: (True, ""), llm=self.llm)



class PausedExecutor:
    def __init__(self):
        self.calls = []

    def __call__(self, request, context, resolved, intercept, guard, progress, *, previous=None):
        self.calls.append({"message": request.message, "previous": previous})
        if previous is None:
            state = {
                "protocol_version": 1,
                "messages": [
                    {"role": "system", "content": "system"},
                    {"role": "user", "content": request.message},
                    {"role": "assistant", "content": "", "tool_calls": [
                        {"id": "ask", "type": "function",
                         "function": {"name": "ask_user", "arguments": "{}"}}]},
                    {"role": "tool", "tool_call_id": "ask", "content": "waiting"},
                ],
                "pending_tool_call_id": "ask",
                "pending_question": {"intro": None, "questions": [
                    {"id": "q1", "prompt": "你指哪种设计？", "options": [],
                     "header": None, "multi_select": False, "allow_free_text": True,
                     "placeholder": None}]},
                "rounds": 1, "exploration_rounds": 1, "settlement_rounds": 0,
                "tool_steps": 1, "sources": [], "target": None,
            }
            return {
                "reply": "你指哪种设计？",
                "answer_status": "awaiting_clarification",
                "clarification": {"mode": "ask_user", "ask_user": state["pending_question"],
                                  "questions": state["pending_question"]["questions"]},
                "loop_paused": True,
                "loop_state": state,
                "routing": {"status": "ok", "intent": "continue"},
                "step_advanced": False,
            }
        self.asserted_previous = previous
        return {"reply": "按被试内设计解释。", "answer_status": "answered",
                "loop_events": [], "routing": {"status": "ok"}, "step_advanced": False}


class TaskLoopPersistenceTests(unittest.TestCase):
    def test_fresh_executor_cancellation_uses_claimed_task_identity(self):
        from sqlalchemy import select
        from database.database import session_scope
        from database.models import LearningTaskRow
        from agents import task_cancellation
        request = ChatRequest(student_id='s', request_id='fresh-native-cancel', message='解释条件')
        def execute(effective, context, resolved, intercept, guard, progress):
            with session_scope() as session:
                task = session.execute(select(LearningTaskRow).where(
                    LearningTaskRow.student_id == 's')).scalar_one()
                self.assertEqual(effective.task_id, task.id)
                self.assertEqual(effective.task_revision, task.revision)
                token = task_cancellation.register(effective.task_id)
                try:
                    self.assertTrue(task_cancellation.cancel(task.id))
                    self.assertTrue(token.is_cancelled())
                finally:
                    task_cancellation.release(task.id)
            return {'reply': '已取消', 'answer_status': 'task_cancelled', 'step_advanced': False}
        result = self.service.run(request, execute)
        self.assertEqual(result['answer_status'], 'task_cancelled')
        self.assertIsNone(request.task_id)

    def test_answered_interjection_does_not_record_q5_explained_or_advance(self):
        q5=Mock();q5.has_path.return_value=True;q5.is_understood.return_value=False
        q5.is_plan_request.return_value=False;q5.is_adjust.return_value=False
        q5.sessions.current.return_value=None;q5.session_snapshot=None
        q5.status.return_value={'path_id':'path','plan_confirmed':True,'mode':'study','current':{'name':'当前目标'}}
        def executor(request,context,resolved,intercept,guard,progress,*,previous=None,q5_binding=None):
            self.assertIs(q5_binding,q5)
            return {'reply':'双方原文的局部解释','answer_status':'answered',
                    'learning_interjection':True,'step_advanced':False}
        with patch('agents.q5_runtime.q5_enabled',return_value=True),patch('agents.q5_runtime.Q5Runtime',return_value=q5):
            result=self.service.run(ChatRequest(student_id='s',request_id='side',
                message='第一章的实验程序和第二章的自变量控制有哪些联系？'),executor)
        self.assertEqual(result['answer_status'],'answered')
        q5.record_explained.assert_not_called();q5.advance_understood.assert_not_called()

    def test_planning_failure_before_execution_guard_releases_claimed_task(self):
        q5=Mock();q5.is_plan_request.return_value=True;q5.is_adjust.return_value=False
        q5.sessions.current.return_value=None;q5.session_snapshot=None
        q5.propose_session.side_effect=TypeError('planning contract failure')
        with patch('agents.q5_runtime.q5_enabled',return_value=True),patch('agents.q5_runtime.Q5Runtime',return_value=q5):
            with self.assertRaisesRegex(TypeError,'planning contract failure'):
                self.service.run(ChatRequest(student_id='s',request_id='plan-failure',
                    message='帮我安排本次学习'),Mock())
        from sqlalchemy import select
        from database.database import session_scope
        from database.models import LearningTaskRow
        with session_scope() as session:
            row=session.scalar(select(LearningTaskRow).where(LearningTaskRow.student_id=='s'))
            self.assertEqual(row.status,'failed')

    def test_practice_button_preserves_hint_level_and_saves_help_once(self):
        from agents.exercise_task_tutor import explain_exercise
        from models.task_context import TaskContext, TaskObject
        from sqlalchemy import select
        from database.models import ExerciseHelpRow
        from database.database import session_scope
        version='a'*64;target={'question_id':'fixture-question','part_id':'p1','version':version}
        request=ChatRequest(student_id='s',message='只给提示',exercise_target=target,exercise_help='hint',exercise_hint_level=3)
        context=TaskContext(student_id='s',message=request.message,knowledge_point='实验条件',objects=[
            TaskObject(id=f'exercise:fixture-question:p1:{version}',kind='exercise_part',title='夹具小题',chapter_id=1,section_id=1)])
        catalog={'version':version,'by_id':{'fixture-question':{'id':'fixture-question','knowledge_point':'实验条件','parts':[{'id':'p1'}]}}}
        self.tutor.memory=self.memory
        with patch('practice_api.catalog',return_value=catalog),patch('practice_api.ai_parts',return_value={'reply':'只提示关键条件'}) as model:
            result=explain_exercise(self.tutor,request,context,lambda *_:None,lambda:None)
        self.assertEqual(result['answer_status'],'answered');self.assertFalse(result['step_advanced'])
        self.assertEqual(model.call_args.args[4:6],('hint',3))
        self.assertTrue(model.call_args.kwargs['task_execution'].hint_only)
        with session_scope() as session:
            rows=session.scalars(select(ExerciseHelpRow).where(ExerciseHelpRow.student_id=='s')).all()
            self.assertEqual(len(rows),1);self.assertEqual(rows[0].level,3)
        self.tutor.conversation_router.route.assert_not_called()

    def test_cancel_after_first_delta_closes_sdk_and_never_saves_draft(self):
        from llm.client import LLMClient, LLMError
        from llm.answer_events import answer_kwargs
        from tests.test_answer_stream import chunk, Stream
        client=LLMClient(api_key='test',mock=False);sdk=Mock();sdk.with_options.return_value=sdk;client._client=sdk
        stream=Stream([chunk('草稿'),chunk('晚到正文','stop')]);sdk.chat.completions.create.return_value=stream
        events=[]
        def emit(event,data):
            events.append((event,data))
            if event=='answer_delta':self.repository.cancel('s','legacy',data['task_id'],data['task_revision'])
        def execute(request,context,resolved,intercept,guard,progress):
            reply=client.chat([{'role':'user','content':request.message}],**answer_kwargs())
            self.fail('取消后的模型结果不得返回执行器')
        with self.assertRaises(LLMError):self.service.run(
            ChatRequest(student_id='s',request_id='cancel-stream',message='解释条件'),execute,answer_event=emit)
        self.assertTrue(stream.closed)
        self.assertEqual([d['text'] for e,d in events if e=='answer_delta'],['草稿'])
        self.assertEqual(self.memory.repo.get_conversation('s'),[])
        self.assertFalse(any(d.get('state')=='saved' for e,d in events))

    def test_sdk_drafts_are_ephemeral_and_receipt_is_authoritative(self):
        from llm.client import LLMClient
        from llm.answer_events import answer_kwargs
        from tests.test_answer_stream import chunk, Stream
        events=[];client=LLMClient(api_key='test',mock=False)
        sdk=Mock();sdk.with_options.return_value=sdk;client._client=sdk
        stream=Stream([chunk('草稿'),chunk('结束[1]','stop')]);sdk.chat.completions.create.return_value=stream
        def execute(request,context,resolved,intercept,guard,progress):
            text=client.chat([{'role':'user','content':request.message}],**answer_kwargs())
            self.assertNotIn('草稿',str(self.memory.repo.get_conversation('s')))
            conversation=self.memory.append_exchange('s',request.message,text,
                expected_point=context.knowledge_point,task_guard=guard)
            return {'reply':text,'answer_status':'answered','memory_commit':{'status':'committed'},'conversation_id':conversation,'step_advanced':False}
        request=ChatRequest(student_id='s',session_id='legacy',request_id='stream-test',message='解释实验条件')
        result=self.service.run(request,execute,answer_event=lambda event,data:events.append((event,data)))
        self.assertTrue(stream.closed);self.assertEqual(events[-1][1]['state'],'saved')
        self.assertEqual(events[-2][1]['text'],result['reply'])
        self.assertTrue(any(e=='answer_delta' for e,_ in events))
        self.assertEqual(self.memory.repo.get_conversation('s')[-1]['content'],result['reply'])
        before=len(events);self.assertEqual(self.service.run(request,execute,answer_event=lambda e,d:events.append((e,d)))['reply'],result['reply'])
        self.assertEqual(len(events),before);sdk.chat.completions.create.assert_called_once()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = create_engine(
            "sqlite:///" + self.temp.name.replace("\\", "/") + "/q3.db",
            connect_args={"check_same_thread": False})

        @event.listens_for(self.engine, "connect")
        def fk(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(self.engine)
        self.db_patch = patch.object(
            db, "SessionLocal",
            sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False))
        self.db_patch.start()
        self.memory = MemoryManager()
        self.memory.ensure_student("s", account_type="test")
        self.tutor = Mock()
        self.tutor.memory = self.memory
        self.repository = LearningTaskRepository()
        policy = Mock()
        policy.enabled.return_value = True
        policy.can_clarify.return_value = True
        policy.context = True
        self.service = TaskService(self.tutor, repository=self.repository, policy=policy)

    def tearDown(self):
        self.db_patch.stop()
        self.engine.dispose()
        self.temp.cleanup()

    def test_pause_then_resume_uses_same_task_and_raw_answer(self):
        executor = PausedExecutor()
        first = self.service.run(
            ChatRequest(student_id="s", session_id="legacy", request_id="r1",
                        message="请比较这两种设计。"), executor)
        self.assertEqual(first["answer_status"], "awaiting_clarification")
        self.assertTrue(first["loop_paused"])
        pending = self.repository.pending("s", "legacy")
        self.assertEqual(pending["id"], first["task_id"])
        self.assertEqual(pending["context"]["loop_state"]["pending_tool_call_id"], "ask")

        second = self.service.run(
            ChatRequest(student_id="s", session_id="legacy", request_id="r2",
                        task_id=first["task_id"], task_revision=first["task_revision"],
                        message="被试内设计"), executor)
        self.assertEqual(second["answer_status"], "answered")
        self.assertEqual(executor.asserted_previous["_resume_answer"], "被试内设计")
        self.assertEqual(executor.asserted_previous["context"]["loop_state"]["pending_tool_call_id"], "ask")

    def test_repeating_answered_task_does_not_execute_again(self):
        executor = PausedExecutor()
        first = self.service.run(
            ChatRequest(student_id="s", session_id="legacy", request_id="r1",
                        message="请比较这两种设计。"), executor)
        self.service.run(
            ChatRequest(student_id="s", session_id="legacy", request_id="r2",
                        task_id=first["task_id"], task_revision=first["task_revision"],
                        message="被试内设计"), executor)
        calls = len(executor.calls)
        duplicate = self.service.run(
            ChatRequest(student_id="s", session_id="legacy", request_id="r3",
                        task_id=first["task_id"], task_revision=first["task_revision"],
                        message="被试内设计"), executor)
        self.assertEqual(duplicate["answer_status"], "task_conflict")
        self.assertEqual(len(executor.calls), calls)

    def test_agent_loop_service_pauses_and_resumes_through_task_service(self):
        llm = ScriptedLLM([
            tool_round(("ask_user", {"questions": [{"id": "q1", "prompt": "你指哪种设计？"}]})),
            final_round("按被试内设计解释。"),
        ])
        executor = LiveLoopExecutor(llm, self.memory)
        first = self.service.run(
            ChatRequest(student_id="s", session_id="legacy", request_id="r1",
                        message="请比较这两种设计。"), executor)
        self.assertEqual(first["answer_status"], "awaiting_clarification")
        self.assertEqual(first["clarification"]["mode"], "ask_user")
        second = self.service.run(
            ChatRequest(student_id="s", session_id="legacy", request_id="r2",
                        task_id=first["task_id"], task_revision=first["task_revision"],
                        message="被试内设计"), executor)
        self.assertEqual(second["answer_status"], "answered")
        self.assertEqual(second["reply"], "按被试内设计解释。")
        self.assertIsNotNone(second["conversation_id"])
        history = self.memory.get_history("s")
        self.assertTrue(any("按被试内设计解释" in row["content"] for row in history))
        self.assertEqual(executor.calls[1]["_resume_answer"], "被试内设计")
        resumed_messages = second["loop_state"]["messages"]
        tool_message = next(message for message in resumed_messages
                            if message.get("role") == "tool")
        self.assertIn("被试内设计", tool_message["content"])

    def test_ask_user_option_click_resumes_with_label(self):
        llm = ScriptedLLM([
            tool_round(("ask_user", {"questions": [{"id": "q1", "prompt": "你指哪种设计？",
                "options": [{"label": "被试间设计"}, {"label": "被试内设计"}]}]})),
            final_round("按被试内设计解释。"),
        ])
        executor = LiveLoopExecutor(llm, self.memory)
        first = self.service.run(
            ChatRequest(student_id="s", session_id="legacy", request_id="r1",
                        message="请比较这两种设计。"), executor)
        self.assertEqual([option["label"] for option in first["clarification"]["options"]],
                         ["被试间设计", "被试内设计"])
        second = self.service.run(
            ChatRequest(student_id="s", session_id="legacy", request_id="r2",
                        task_id=first["task_id"], task_revision=first["task_revision"],
                        message="第一个", selected_option="q1:1"), executor)
        self.assertEqual(second["answer_status"], "answered")
        self.assertEqual(executor.calls[1]["_resume_answer"], "被试内设计")
        tool_message = next(message for message in second["loop_state"]["messages"]
                            if message.get("role") == "tool")
        self.assertIn("被试内设计", tool_message["content"])
        self.assertIn("你指哪种设计", tool_message["content"])

    def test_cancelled_paused_task_cannot_resume(self):
        executor = PausedExecutor()
        first = self.service.run(
            ChatRequest(student_id="s", session_id="legacy", request_id="r1",
                        message="请比较这两种设计。"), executor)
        self.repository.cancel("s", "legacy", first["task_id"], first["task_revision"])
        calls = len(executor.calls)
        result = self.service.run(
            ChatRequest(student_id="s", session_id="legacy", request_id="r2",
                        task_id=first["task_id"], task_revision=first["task_revision"],
                        message="被试内设计"), executor)
        self.assertEqual(result["answer_status"], "task_conflict")
        self.assertEqual(len(executor.calls), calls)


if __name__ == "__main__":
    unittest.main()
