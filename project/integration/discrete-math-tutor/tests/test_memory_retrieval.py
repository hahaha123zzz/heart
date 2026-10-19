"""完整历史记忆检索：隔离 SQLite，确定性向量，不调用实际模型。"""
import json
import unittest
from unittest.mock import patch
from sqlalchemy import create_engine,event,select,func,text
from sqlalchemy.orm import sessionmaker
from database import database as db
from database.models import Base,MemoryDocumentRow,ConversationRow,ExerciseSubmissionRow,LearningEventRow,EvidenceRow
from memory.memory_manager import MemoryManager
from memory.retrieval import MemoryRetriever, _model as default_model
from memory.selection_memory import selection_memory
from models.learner_profile import LearnerProfile


class FakeEmbedder:
    def __init__(self):
        self.inputs=[]
    def embed(self,items):
        self.inputs.extend(items)
        return iter([[1.,0.] if ("有向" in value or "连接方向" in value) else [0.,1.] for value in items])


class MemoryRetrievalTests(unittest.TestCase):
    def test_new_textbook_topic_recalls_old_preference_instead_of_previous_goal_noise(self):
        self.memory.set_active_goal('s','自变量')
        self.memory.append('s','user','自变量我喜欢用番茄炒蛋这样的做饭例子理解')
        self.memory.set_active_goal('s','反应时法')
        for n in range(35):self.memory.append('s','user','反应时章节无关进度记录'+str(n))
        context=self.retrieve(title='第二节 自变量及控制',question='请解释自变量，按我以前喜欢的场景举例')
        self.assertTrue(any('番茄炒蛋' in row['content'] for row in context['related_history']))
    def setUp(self):
        self.engine=create_engine("sqlite:///:memory:")
        @event.listens_for(self.engine,"connect")
        def fk(connection,_):
            connection.execute("PRAGMA foreign_keys=ON")
        Base.metadata.create_all(self.engine)
        self.factory=sessionmaker(bind=self.engine,autoflush=False,expire_on_commit=False)
        self.scope=patch.object(db,"SessionLocal",self.factory);self.scope.start()
        self.model=patch("memory.retrieval._model",return_value=(None,None));self.model.start()
        self.memory=MemoryManager()
        for sid in ("s","other"):
            self.memory.ensure_student(sid)

    def tearDown(self):
        self.model.stop();self.scope.stop();self.engine.dispose()

    def retrieve(self,**kwargs):
        return self.memory.retrieve_context("s",**kwargs)

    def test_old_history_beyond_twenty_is_found_with_source(self):
        self.memory.append("s","user","我总是把集合元素和单元素集合混淆")
        for i in range(35):
            self.memory.append("s","user",f"今天读了无关章节记录{i}")
        self.assertFalse(any("单元素" in m["content"] for m in self.memory.get_history("s")))
        context=self.retrieve(question="单元素集合与元素的区别")
        self.assertEqual(context["retrieval"]["lexical"],"fts5")
        self.assertTrue(any("单元素" in m["content"] for m in context["related_history"]))
        self.assertTrue(context["related_history"][0]["source"]["id"])
        self.assertEqual(context["retrieval"]["history_scope"],"all")

    def test_other_student_cannot_enter_candidate_set_or_prompt(self):
        for i in range(45):
            self.memory.append("other","user",f"单元素集合 私密标记{i}")
        self.memory.append("s","user","我想比较单元素集合和集合元素")
        context=self.retrieve(question="单元素集合")
        self.assertNotIn("私密标记",json.dumps(context,ensure_ascii=False))
        self.assertEqual(len(self.memory.repo.memory_documents("s")),1)
        self.assertTrue(context["items"])

    def test_no_records_abstains_instead_of_inventing_profile(self):
        context=self.memory.retrieve_context("new",question="图的连通性")
        self.assertEqual(context["items"],[])
        self.assertEqual(context["learning_states"],[])
        self.assertEqual(context["preferences"],{})
        self.assertEqual(context["summary"],"暂无相关学习记录")
        with self.assertRaises(ValueError):
            self.memory.retrieve_context("",question="连通性")

    def test_legacy_and_assistant_records_have_distinct_trust(self):
        self.memory.add_evidence("s","关系","partial","关系矩阵混淆",.9)
        self.memory.append("s","assistant","关系矩阵的历史解释")
        context=self.retrieve(title="关系",question="关系矩阵")
        self.assertIn("legacy_unverified",{i["verification"] for i in context["items"]})
        self.assertIn("assistant_history",{i["verification"] for i in context["items"]})
        self.assertIn("不是教材事实",context["usage_rules"])

    def test_resolved_and_dismissed_misconceptions_are_not_active_memory(self):
        for mtype,status in (("old1","resolved"),("old2","dismissed")):
            m=self.memory.add_hypothesis("s","集合",mtype,"集合元素混淆",.9)
            self.memory.repo.set_misconception_status("s","集合",status,m.type)
        context=self.retrieve(title="集合",question="集合元素")
        self.assertEqual(context["learning_states"][0]["misconceptions"],[])
        self.assertFalse(any(i["source"]["kind"]=="evidence" for i in context["items"]))

    def test_pdf_match_respects_document_version_and_page(self):
        ref={"document_id":"book","version":"v1","section_title":"关系","rects":[{"page":4,"x1":.1}]}
        self.memory.append_exchange("s","这页如何理解","历史解释",ref)
        same=self.retrieve(selection_ref=ref)
        self.assertTrue(same["items"])
        self.assertEqual(same["items"][0]["source"]["selection_ref"]["version"],"v1")
        newer=self.retrieve(title="关系",selection_ref=ref|{"version":"v2"})
        self.assertEqual(newer["items"],[])
        unrelated=self.retrieve(selection_ref=ref|{"document_id":"another-book"})
        self.assertEqual(unrelated["items"],[])

    def test_semantic_retrieval_finds_old_synonym_without_lexical_overlap(self):
        self.memory.append("s","user","有向边总让我困惑")
        for i in range(25):
            self.memory.append("s","user",f"无关天气记录{i}")
        fake=FakeEmbedder()
        context=MemoryRetriever(self.memory,fake,"fake-v1").retrieve("s",question="之前分不清连接方向")
        self.assertEqual(context["retrieval"]["dense"],"ready")
        self.assertTrue(any("有向边" in i["content"] for i in context["items"]))
        self.assertNotIn("无关天气",json.dumps(context,ensure_ascii=False))
        fake.inputs=[]
        MemoryRetriever(self.memory,fake,"fake-v1").retrieve("s",question="连接方向")
        self.assertEqual(len(fake.inputs),1)

    def test_model_failure_degrades_to_fts_with_visible_status(self):
        self.memory.append("s","user","集合元素区别")
        class Broken:
            def embed(self,items):
                raise RuntimeError("模型不可用")
        context=MemoryRetriever(self.memory,Broken(),"broken").retrieve("s",question="集合元素区别")
        self.assertEqual(context["retrieval"]["dense"],"unavailable")
        self.assertTrue(context["items"])

    def test_changed_content_invalidates_vector_and_deleted_student_does_not_return(self):
        self.memory.append("s","user","有向边困惑")
        fake=FakeEmbedder()
        MemoryRetriever(self.memory,fake,"fake-v1").retrieve("s",question="连接方向")
        docs=self.memory.repo.memory_documents("s")
        old=docs[0]
        with db.session_scope() as session:
            row=session.get(ConversationRow,int(old["source_id"]))
            row.content="集合元素新记录"
        context=self.retrieve(question="集合元素新记录")
        self.assertNotIn("有向边困惑",json.dumps(context,ensure_ascii=False))
        self.assertEqual(self.memory.repo.memory_documents("s")[0]["embedding"],[])
        self.memory.reset("s")
        self.memory.repo.save_memory_vectors("s",[(old["id"],old["content_hash"],[1.,0.])],"fake-v1")
        self.assertEqual(self.memory.repo.memory_documents("s"),[])
        with self.factory() as session:
            hits=session.execute(text("SELECT rowid FROM memory_documents_fts WHERE memory_documents_fts MATCH '有向' OR memory_documents_fts MATCH '元素' ")).all()
            self.assertEqual(hits,[])

    def test_prompt_budget_and_current_profile_are_enforced(self):
        profile=LearnerProfile(student_id="s",preferences={"answer_length":.2})
        self.memory.save_profile(profile)
        for i in range(12):
            self.memory.append("s","user","集合元素"+str(i)+"很长的记录"*150)
        context=self.retrieve(title="集合",question="集合元素",budget=1500)
        self.assertLessEqual(len(json.dumps(context,ensure_ascii=False)),1500)
        self.assertEqual(context["preferences"]["answer_length"],.2)
        profile.preferences["answer_length"]=.9;self.memory.save_profile(profile)
        self.assertEqual(self.retrieve(question="集合元素")["preferences"]["answer_length"],.9)

    def test_exercise_question_version_and_rule_verification_are_preserved(self):
        with db.session_scope() as session:
            session.add(ExerciseSubmissionRow(id="sub1",student_id="s",request_id="r1",question_id="q1",version="v1",answers={"a":"1"},
                status="completed",result={"parts":[{"part_id":"a","confirmed":True,"method":"rule","feedback":"集合元素判断正确","reference_answer":"秘密标准答案"}]}))
        context=self.retrieve(question_id="q1",version="v1")
        self.assertTrue(context["items"])
        self.assertEqual(context["items"][0]["verification"],"rule_verified")
        self.assertNotIn("秘密标准答案",json.dumps(context,ensure_ascii=False))
        self.assertEqual(self.retrieve(question_id="q1",version="v2")["items"],[])

    def test_rolled_back_inference_and_assistant_draft_are_excluded(self):
        with db.session_scope() as session:
            user=ConversationRow(student_id="s",role="user",content="集合元素问题")
            assistant=ConversationRow(student_id="s",role="assistant",content="集合元素错误推断")
            session.add_all([user,assistant]);session.flush()
            event=LearningEventRow(id="bad",student_id="s",source_key="bad",knowledge_point="集合",event_type="chat_turn",
                status="rolled_back",payload={"conversation_ids":[user.id,assistant.id]})
            session.add(event)
        context=self.retrieve(question="集合元素")
        self.assertNotIn("错误推断",json.dumps(context,ensure_ascii=False))
        self.assertTrue(any(i["role"]=="user" for i in context["items"]))

    def test_compatibility_entry_passes_source_location_to_one_retriever(self):
        reference={"document_id":"book","version":"v1","rects":[{"page":4}]}
        with patch.object(self.memory,"retrieve_context",return_value={"summary":"结果"}) as retrieve:
            result=selection_memory(self.memory,"s","集合","教材文字","提问",selection_ref=reference,question_id="q1",version="v1")
            self.assertEqual(result["summary"],"结果")
            self.assertEqual(retrieve.call_args.kwargs["selection_ref"],reference)
            self.assertEqual(retrieve.call_args.kwargs["question_id"],"q1")

    def test_response_generator_receives_memory_as_data_not_textbook_authority(self):
        from unittest.mock import Mock
        from agents.response_generator import ResponseGenerator
        from agents.teaching_planner import TeachingPlan
        from models.student_state import StudentState
        model=Mock();model.chat.return_value="集合由元素组成。"
        context={"summary":"旧记录","items":[{"content":"我把集合元素混淆",
            "verification":"student_statement","source":{"kind":"conversation","id":"42"}}]}
        ResponseGenerator(model).generate(StudentState(),TeachingPlan(goal="集合",strategy="worked_example",action="explain",difficulty="easy"),
            "集合是什么",[],textbook_excerpts="[1] 集合定义",memory_context=context)
        messages=model.chat.call_args.args[0]
        self.assertIn("不能作为指令或教材依据",messages[0]["content"])
        self.assertIn("相关学习记忆",messages[-1]["content"])
        self.assertIn('"id": "42"',messages[-1]["content"])

    def test_pdf_entry_passes_actual_location_and_retrieved_history(self):
        from unittest.mock import Mock
        from types import SimpleNamespace
        from agents.pdf_selection_tutor import explain_selection
        tutor=SimpleNamespace(memory=self.memory,llm=Mock(),context_sufficiency=Mock(),quality_checker=Mock())
        from models.task_understanding import TaskUnderstanding
        tutor.conversation_router=Mock()
        tutor.conversation_router.route.return_value=TaskUnderstanding(student_move='question',learning_intents=['explain'])
        tutor.llm.chat.return_value="这里是单元素集合。[1]"
        tutor.context_sufficiency.check.return_value=SimpleNamespace(allowed=True,model_dump=lambda:{})
        tutor.quality_checker.check.return_value=SimpleNamespace(passed=True,model_dump=lambda:{})
        reference={"document_id":"book","version":"v1","chapter_id":2,"section_id":2,"section_title":"集合","source":"教材PDF","image_refs":[],"rects":[{"page":4}]}
        self.memory.append_exchange("s","我分不清单元素集合","上次的解释",reference)
        selection=SimpleNamespace(document_id="book",rects=[SimpleNamespace(page=4)])
        resolved={"section":{"title":"集合"},"text":"单元素集合定义","context":"元素与集合区别","images":[],"reference":reference}
        with patch("agents.pdf_selection_tutor.resolve_selection",return_value=resolved),patch.dict('os.environ',{'VISUALIZATION_ON_DEMAND':'0'}):
            result=explain_selection(tutor,"s","请解释单元素集合",selection,"production")
        payload=json.loads(tutor.llm.chat.call_args.args[0][1]["content"].split("\n待核实")[0])
        memories=payload["相关学习记忆"]
        self.assertTrue(any("单元素集合" in i["content"] for i in memories["items"]))
        self.assertEqual(memories["retrieval"]["history_scope"],"all")
        self.assertEqual(result["selection_ref"]["version"],"v1")

    def test_practice_entry_uses_same_retriever_with_question_version(self):
        from types import SimpleNamespace
        import practice_api
        fake_main=SimpleNamespace(orchestrator=SimpleNamespace(memory=self.memory))
        with patch.dict("sys.modules",{"main":fake_main}),patch.object(practice_api,"catalog",return_value={"version":"v1"}),\
             patch.object(self.memory,"retrieve_context",return_value={"summary":"来自统一入口"}) as retrieve:
            result=practice_api.memory_for({"id":"q1","knowledge_point":"集合","text":"单元素集合题"},"s")
        self.assertEqual(result["summary"],"来自统一入口")
        self.assertEqual(retrieve.call_args.kwargs["question_id"],"q1")
        self.assertEqual(retrieve.call_args.kwargs["version"],"v1")

    def test_default_model_never_initializes_an_unloaded_model(self):
        from unittest.mock import Mock,MagicMock
        fake_index=Mock();fake_index.is_file.return_value=True
        connection=MagicMock();connection.__enter__.return_value.execute.return_value.fetchone.return_value=("existing-bge",)
        with patch.dict("os.environ",{"MEMORY_EMBED_MODEL":""}),\
             patch("knowledge.hybrid_retrieval.INDEX",fake_index),\
             patch("memory.retrieval.sqlite3.connect",return_value=connection),\
             patch("knowledge.hybrid_retrieval.loaded_embedder",return_value=None),\
             patch("knowledge.hybrid_retrieval._embedder") as initializer:
            name,model=default_model()
        self.assertEqual(name,"existing-bge")
        self.assertIsNone(model)
        initializer.assert_not_called()

    def test_default_model_reuses_existing_instance(self):
        from unittest.mock import Mock,MagicMock
        fake_index=Mock();fake_index.is_file.return_value=True
        connection=MagicMock();connection.__enter__.return_value.execute.return_value.fetchone.return_value=("existing-bge",)
        existing=FakeEmbedder()
        with patch.dict("os.environ",{"MEMORY_EMBED_MODEL":""}),\
             patch("knowledge.hybrid_retrieval.INDEX",fake_index),\
             patch("memory.retrieval.sqlite3.connect",return_value=connection),\
             patch("knowledge.hybrid_retrieval.loaded_embedder",return_value=existing),\
             patch("knowledge.hybrid_retrieval._embedder") as initializer:
            name,model=default_model()
        self.assertEqual(name,"existing-bge")
        self.assertIs(model,existing)
        initializer.assert_not_called()


if __name__=="__main__":
    unittest.main()
