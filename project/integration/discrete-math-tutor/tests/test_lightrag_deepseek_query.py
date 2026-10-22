"""仅允许显式、同模型的官方查询迁移；不伪改建图策略或开放抽取。"""
import asyncio
import copy
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from knowledge.lightrag.roles import resolve_query_roles, query_binding
from knowledge.lightrag import engine
from knowledge.lightrag.config import HostEmbedding


class OfficialQueryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'ds.env'
        self.write('https://api.deepseek.com')
    def write(self, endpoint, key='fixture-not-real'):
        self.path.write_text('DEEPSEEK_API_KEY='+key+'\nOPENAI_BASE_URL='+endpoint+'\nDEEPSEEK_MODEL=deepseek-flash\n',encoding='utf8')
    def roles(self):
        with patch.dict(os.environ,LIGHTRAG_QUERY_ENV_FILE=str(self.path)):
            return resolve_query_roles()
    def old_policy(self,calls):
        result={'extract':dict(calls['extract'].config.identity)}
        result['extract']['endpoint']='https://cn.chatapi.app/v1'
        return result
    def test_explicit_official_override_keeps_index_identity_separate(self):
        calls=self.roles();expected=self.old_policy(calls);original=copy.deepcopy(expected)
        with patch.dict(os.environ,LIGHTRAG_QUERY_ENV_FILE=str(self.path)):
            binding=query_binding(expected,calls)
        self.assertEqual(expected,original)
        self.assertEqual(binding['mode'],'official_deepseek_query')
        self.assertEqual(binding['indexed_extract']['endpoint'],'https://cn.chatapi.app/v1')
        self.assertEqual(binding['query']['endpoint'],'https://api.deepseek.com')
        self.assertTrue(binding['query_only']);self.assertFalse(calls['query'].config.client.mock)
    def test_no_explicit_override_still_rejects_endpoint_change(self):
        calls=self.roles()
        with patch.dict(os.environ,LIGHTRAG_QUERY_ENV_FILE=''),self.assertRaises(RuntimeError):
            query_binding(self.old_policy(calls),calls)
    def test_model_or_parameters_cannot_migrate_with_endpoint(self):
        calls=self.roles()
        for key,value in [('model','another-model'),('temperature',.9),('thinking','provider_default')]:
            expected=self.old_policy(calls);expected['extract'][key]=value
            with self.subTest(key=key),patch.dict(os.environ,LIGHTRAG_QUERY_ENV_FILE=str(self.path)),self.assertRaises(RuntimeError):
                query_binding(expected,calls)
    def test_config_cannot_send_key_to_gateway_or_fall_back_to_project_key(self):
        for endpoint in ['https://cn.chatapi.app/v1','http://api.deepseek.com','https://api.deepseek.com.evil/v1','https://api.deepseek.com?token=x']:
            self.write(endpoint)
            with self.subTest(endpoint=endpoint),self.assertRaises(ValueError):self.roles()
        self.write('https://api.deepseek.com',key='')
        with patch.dict(os.environ,DEEPSEEK_API_KEY='project-fixture'),self.assertRaises(ValueError):self.roles()
    def test_query_instance_cannot_extract_or_accept_indexing_snapshot(self):
        calls=self.roles()
        with patch.object(engine,'_controlled_class',return_value=SimpleNamespace):
            rag=engine.build_rag(Path(self.temp.name),query_roles=calls,embedding_config=HostEmbedding(),query_only=True)
        with self.assertRaisesRegex(engine.LightRagContractError,'禁止抽取'):
            asyncio.run(rag.role_llm_configs['extract'].func('must not call provider'))
        with self.assertRaises(engine.LightRagContractError):
            engine.build_rag(Path(self.temp.name),indexing_snapshot=object(),query_only=True)


if __name__=='__main__':unittest.main()
