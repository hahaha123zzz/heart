"""图论试点：确定性数学、隔离 SQLite、真实本地 ASGI。"""
import os
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select, delete
from database.database import session_scope
from database.models import Student, ConversationRow, VisualizationRow, VisualizationOperationRow
from models.visualization import GraphSpec, GraphOperation, CreateVisualization
from visualization.graph_validator import evaluate_graph
from visualization.service import VisualizationService, VisualizationError, POINT
from visualization_api import router
from tests import test_memory_jobs as fixtures


def spec(count, pairs):
    return GraphSpec(nodes=[{'id':f'v{i}', 'label':f'v{i}'} for i in range(1,count+1)],
        edges=[{'source':f'v{a}','target':f'v{b}'} for a,b in pairs])


class GraphMathTests(unittest.TestCase):
    def test_cycle_and_diagonal(self):
        edges=[(1,2),(2,3),(3,4),(4,1)]
        self.assertTrue(evaluate_graph(spec(4,edges))['has_euler_circuit'])
        result=evaluate_graph(spec(4,edges+[(1,3)]))
        self.assertFalse(result['has_euler_circuit'])
        self.assertTrue(result['has_open_euler_path'])
        self.assertEqual(result['odd_vertices'],['v1','v3'])

    def test_path_and_four_odd_vertices(self):
        self.assertTrue(evaluate_graph(spec(4,[(1,2),(2,3),(3,4)]))['has_open_euler_path'])
        self.assertFalse(evaluate_graph(spec(4,[(1,2),(1,3),(1,4)]))['has_euler_trail'])

    def test_even_degrees_do_not_replace_connectedness(self):
        result=evaluate_graph(spec(6,[(1,2),(2,3),(3,1),(4,5),(5,6),(6,4)]))
        self.assertEqual(result['odd_vertices'],[])
        self.assertFalse(result['connected'])
        self.assertFalse(result['has_euler_trail'])

    def test_textbook_isolates_and_zero_edges(self):
        self.assertFalse(evaluate_graph(spec(4,[(1,2),(2,3),(3,1)]))['has_euler_trail'])
        self.assertFalse(evaluate_graph(spec(4,[]))['has_euler_trail'])
        self.assertTrue(evaluate_graph(spec(1,[]))['has_euler_circuit'])

    def test_reject_non_simple_and_invalid_spec(self):
        for pairs in [[(1,1)],[(1,2),(2,1)],[(1,5)]]:
            with self.subTest(pairs=pairs),self.assertRaises(ValidationError): spec(4,pairs)
        with self.assertRaises(ValidationError):spec(13,[])
        with self.assertRaises(ValidationError):GraphSpec(nodes=[],edges=[])
        with self.assertRaises(ValidationError):GraphSpec.model_validate({'nodes':[{'id':'v1','label':'1'}],'edges':[],'code':'alert(1)'})


class VisualizationTests(unittest.TestCase):
    def setUp(self):
        fixtures.MemoryJobTests.setUp(self)
        self.env=patch.dict(os.environ,{'VISUALIZATION_ROLLOUT':'test','VISUALIZATION_STUDENT_ALLOWLIST':''})
        self.env.start()
        with session_scope() as session:session.get(Student,'s').account_type='test'
        self.service=VisualizationService()
        app=FastAPI();app.include_router(router);self.client=TestClient(app)

    def tearDown(self):
        self.client.close();self.env.stop();fixtures.MemoryJobTests.tearDown(self)

    def create(self, request_id='create-1', epoch=0, student='s', session='tab'):
        return self.service.create(CreateVisualization(student_id=student,session_id=session,request_id=request_id,expected_epoch=epoch))

    def op(self, **values):
        return GraphOperation(student_id='s',session_id='tab',request_id='op-1',expected_revision=1,
                              **{'operation':'add_edge','source':'v1','target':'v3',**values})

    def count(self, model):
        with session_scope() as session:return len(session.scalars(select(model)).all())

    def test_atomic_create_message_and_idempotency(self):
        artifact=self.create()
        self.assertEqual(self.create()['artifact_id'],artifact['artifact_id'])
        self.assertEqual(self.count(VisualizationRow),1)
        self.assertEqual(self.count(ConversationRow),1)
        with session_scope() as session:self.assertEqual(session.get(ConversationRow,artifact['conversation_id']).role,'assistant')
        self.assertEqual(artifact['origin'],'auxiliary_example')
        self.assertTrue(artifact['evaluation']['has_euler_circuit'])
        with self.assertRaises(VisualizationError):self.create(epoch=1)

    def test_first_open_creates_new_test_account_atomically(self):
        artifact=self.create(student='brand-new')
        self.assertEqual(self.memory.repo.get_account_type('brand-new'),'test')
        self.assertEqual(self.service.get(artifact['artifact_id'],'brand-new','tab')['revision'],1)

    def test_operation_idempotency_and_payload_conflict(self):
        artifact=self.create();identifier=artifact['artifact_id']
        after=self.service.operate(identifier,self.op())
        self.assertEqual(after['revision'],2)
        self.assertTrue(after['evaluation']['has_open_euler_path'])
        self.assertEqual(self.service.operate(identifier,self.op()),after)
        self.assertEqual(self.count(VisualizationOperationRow),1)
        with self.assertRaises(VisualizationError) as caught:self.service.operate(identifier,self.op(target='v4'))
        self.assertEqual(caught.exception.status,409)

    def test_stale_revision_and_invalid_edges_no_changes(self):
        identifier=self.create()['artifact_id']
        for pair in [('v1','v1'),('v1','v9'),('v1','v2')]:
            with self.subTest(pair=pair),self.assertRaises(VisualizationError):self.service.operate(identifier,self.op(source=pair[0],target=pair[1]))
        self.assertEqual(self.service.get(identifier,'s','tab')['revision'],1)
        self.service.operate(identifier,self.op())
        with self.assertRaises(VisualizationError):self.service.operate(identifier,GraphOperation(student_id='s',session_id='tab',request_id='op-2',expected_revision=1,operation='remove_edge',source='v1',target='v3'))

    def test_layout_does_not_change_math_revision(self):
        artifact=self.create();positions={key:{'x':value['x']+40,'y':value['y']} for key,value in artifact['layout'].items()}
        request=GraphOperation(student_id='s',session_id='tab',request_id='layout-1',expected_revision=1,
            operation='layout',positions=positions,expected_layout_revision=1)
        after=self.service.operate(artifact['artifact_id'],request)
        self.assertEqual(after['revision'],1);self.assertEqual(after['layout_revision'],2)
        self.assertEqual(after['evaluation'],artifact['evaluation'])
        self.assertEqual(self.service.get(artifact['artifact_id'],'s','tab')['layout'],positions)
        stale=request.model_copy(update={'request_id':'layout-2'})
        with self.assertRaises(VisualizationError):self.service.operate(artifact['artifact_id'],stale)

    def test_layout_reject_unknown_nodes_and_nonfinite(self):
        artifact=self.create()
        req=GraphOperation(student_id='s',session_id='tab',request_id='layout',expected_revision=1,operation='layout',
            positions={'v9':{'x':0.,'y':1.}},expected_layout_revision=1)
        with self.assertRaises(VisualizationError):self.service.operate(artifact['artifact_id'],req)
        with self.assertRaises(ValidationError):req.model_validate({**req.model_dump(),'positions':{'v1':{'x':float('inf'),'y':1.}}})

    def test_scope_rejects_other_student_and_session(self):
        identifier=self.create()['artifact_id']
        for student, session in [('other','tab'),('s','other')]:
            with self.subTest(student=student,session=session),self.assertRaises(VisualizationError) as caught:self.service.get(identifier,student,session)
            self.assertEqual(caught.exception.status,404)
        self.assertEqual(self.service.list('s','other'),[])

    def test_feature_off_readonly_and_no_write(self):
        artifact=self.create()
        with patch.dict(os.environ,{'VISUALIZATION_ROLLOUT':'off'}):
            self.assertTrue(self.service.get(artifact['artifact_id'],'s','tab')['readonly'])
            with self.assertRaises(VisualizationError):self.service.operate(artifact['artifact_id'],self.op())
            with self.assertRaises(VisualizationError):self.create('new')

    def test_production_cannot_claim_test_and_allowlist_is_server_side(self):
        self.memory.ensure_student('prod')
        self.assertFalse(self.service.enabled('prod'))
        with self.assertRaises(VisualizationError):self.create(student='prod')
        with patch.dict(os.environ,{'VISUALIZATION_ROLLOUT':'allowlist','VISUALIZATION_STUDENT_ALLOWLIST':'s'}):
            self.assertTrue(self.service.enabled('s'));self.assertFalse(self.service.enabled('other'))

    def test_delete_message_cascades_artifact_and_receipts(self):
        artifact=self.create();self.service.operate(artifact['artifact_id'],self.op())
        with session_scope() as session:session.execute(delete(ConversationRow).where(ConversationRow.id==artifact['conversation_id']))
        self.assertEqual(self.count(VisualizationRow),0);self.assertEqual(self.count(VisualizationOperationRow),0)

    def test_delete_student_cascades(self):
        artifact=self.create();self.service.operate(artifact['artifact_id'],self.op())
        self.memory.repo.delete_student('s')
        self.assertEqual(self.count(VisualizationRow),0);self.assertEqual(self.count(VisualizationOperationRow),0)

    def test_forget_point_blocks_delayed_create_and_preserves_other_point(self):
        artifact=self.create();self.service.operate(artifact['artifact_id'],self.op())
        self.memory.repo.append_conversation('s','assistant','其他知识点')
        self.memory.repo.forget_learning_point('s',POINT)
        self.assertEqual(self.count(VisualizationRow),0);self.assertEqual(self.count(VisualizationOperationRow),0)
        self.assertEqual(self.count(ConversationRow),1)
        with self.assertRaises(VisualizationError):self.create()
        with self.assertRaises(VisualizationError):self.service.operate(artifact['artifact_id'],self.op())
        self.assertEqual(self.create('fresh',epoch=1)['revision'],1)

    def test_concurrent_revision_has_one_winner(self):
        identifier=self.create()['artifact_id'];barrier=threading.Barrier(2)
        def change(index):
            barrier.wait()
            req=GraphOperation(student_id='s',session_id='tab',request_id=f'concurrent-{index}',expected_revision=1,
                operation='add_edge',source='v1' if index==1 else 'v2',target='v3' if index==1 else 'v4')
            try:return VisualizationService().operate(identifier,req)['revision']
            except VisualizationError as exc:return exc.status
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(change,[1,2]))
        self.assertEqual(sorted(results),[2,409]);self.assertEqual(self.count(VisualizationOperationRow),1)

    def test_http_validation_and_restore(self):
        payload={'student_id':'s','session_id':'tab','request_id':'http','expected_epoch':0}
        response=self.client.post('/api/visualizations',json=payload);self.assertEqual(response.status_code,200)
        artifact=response.json()
        restored=self.client.get('/api/visualizations',params={'student_id':'s','session_id':'tab'})
        self.assertEqual(restored.json(),[artifact])
        self.assertEqual(self.client.post('/api/visualizations',json={**payload,'code':'alert(1)'}).status_code,422)
        self.assertEqual(self.client.get('/api/visualizations/'+artifact['artifact_id'],params={'student_id':'other','session_id':'tab'}).status_code,404)

    def test_graph_operations_do_not_raise_mastery(self):
        before=self.memory.get_state('s',POINT).mastery
        artifact=self.create();self.service.operate(artifact['artifact_id'],self.op())
        self.assertEqual(self.memory.get_state('s',POINT).mastery,before)


if __name__=='__main__':unittest.main()
