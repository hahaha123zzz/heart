"""迁移只改变查询读取视图，不依赖旧目录、不放宽冻结输入校验。"""
import asyncio, json, tempfile, unittest
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from knowledge.lightrag import ingress, engine
from knowledge.lightrag.parse_types import ParsedDocument
from knowledge.lightrag.paths import bind_candidate_sidecars, sidecar_uri_for


class RelocationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.working = self.root/'index'
        self.name = 'chapter_01.generated.pdf'
        source = self.root/self.name
        source.write_bytes(b'fixture pdf')
        ingress.freeze_document(self.working, source, ParsedDocument(markdown='教材原文',
            blocks=[{'type':'text','text':'教材原文'}], engine='fixture'))
        self.directory = ingress.pending_root(self.working)/'__parsed__'/(self.name+'.parsed')
        self.directory.mkdir(parents=True)
        self.blocks = self.directory/(Path(self.name).stem+'.blocks.jsonl')
        self.blocks.write_text('{}\n', encoding='utf8')
        self.key = engine._document_id(self.name)
        self.row = {'file_path':self.name, 'parse_engine':'deeptutor', 'sidecar_location':
            sidecar_uri_for(self.directory).replace(self.root.as_posix(), self.root.as_posix()+'/不存在的旧目录')}
        # 历史URI指向根本不存在的位置，读取不得尝试访问它。
        self.rows = {self.key:self.row}
        async def get(key):return self.rows.get(key)
        async def get_many(keys):return [self.rows.get(key) for key in keys]
        self.rag = SimpleNamespace(full_docs=SimpleNamespace(get_by_id=get,get_by_ids=get_many))

    def test_single_batch_reads_local_and_do_not_mutate_storage(self):
        before = deepcopy(self.row)
        audit = bind_candidate_sidecars(self.rag, self.working)
        async def run():
            one = await self.rag.full_docs.get_by_id(self.key)
            many = await self.rag.full_docs.get_by_ids([self.key,'missing'])
            self.assertEqual(one['sidecar_location'],sidecar_uri_for(self.directory))
            self.assertEqual(many,[one,None])
            self.assertEqual(audit['documents'],[self.name])
        asyncio.run(run())
        self.assertEqual(self.row,before)

    def test_reject_remote_cross_document_and_bad_identity(self):
        bind_candidate_sidecars(self.rag,self.working)
        for updates in ({'sidecar_location':'https://example.test/__parsed__/'+self.name+'.parsed/'},
                        {'sidecar_location':'file:/old/__parsed__/another.pdf.parsed/'},
                        {'file_path':'../outside.pdf'}, {'parse_engine':'unknown'}):
            with self.subTest(updates=updates):
                old = dict(self.row);self.row.update(updates)
                with self.assertRaises((ingress.IngressError,engine.LightRagContractError)):
                    asyncio.run(self.rag.full_docs.get_by_id(self.key))
                self.row.clear();self.row.update(old)

    def test_missing_blocks_and_frozen_bundle_drift_fail(self):
        bind_candidate_sidecars(self.rag,self.working)
        self.blocks.unlink()
        with self.assertRaises((ingress.IngressError,FileNotFoundError)):
            asyncio.run(self.rag.full_docs.get_by_id(self.key))
        self.blocks.write_text('{}\n')
        bundle=ingress.bundles_root(self.working)/(self.name+'.bundle')
        (bundle/'markdown.utf8').write_text('drift')
        with self.assertRaisesRegex(ingress.IngressError,'Digest mismatch'):
            asyncio.run(self.rag.full_docs.get_by_id(self.key))

    def test_sidecar_hardlink_is_rejected(self):
        bind_candidate_sidecars(self.rag,self.working)
        self.blocks.unlink()
        other=self.root/'other';other.write_text('{}\n')
        self.blocks.hardlink_to(other)
        with self.assertRaises(ingress.IngressError):
            asyncio.run(self.rag.full_docs.get_by_id(self.key))

    def test_backend_explicit_source_root_keeps_manifest_provenance_and_hash_guard(self):
        from knowledge.lightrag.retrieval import LightRagBackend
        candidate=self.root/'candidate';candidate.mkdir();local=self.root/'local';local.mkdir()
        manifest={'source_root':'unavailable/old/book','files':{'manifest.json':'sha'},'course_id':'experimental-psychology-3'}
        (candidate/'input_manifest.json').write_text(json.dumps(manifest))
        (candidate/'progress.json').write_text(json.dumps({'state':'candidate_complete','chapters':{str(i):{'complete':True} for i in range(1,12)}}))
        (candidate/'index_files.json').write_text(json.dumps({'core':'sha'}))
        backend=LightRagBackend(candidate,authorized_course_ids={'experimental-psychology-3'},allow_candidate=True,source_root=local)
        with patch('knowledge.lightrag.retrieval.verify') as verify,patch('knowledge.lightrag.ingress._contained_regular_file',return_value=candidate/'core'),patch('knowledge.lightrag.retrieval.digest',return_value='sha'):
            self.assertEqual(backend.validate('experimental-psychology-3'),manifest)
            self.assertEqual(verify.call_args_list[-1].args[0],local)
            verify.side_effect=ingress.IngressError('drift')
            with self.assertRaisesRegex(ingress.IngressError,'drift'):backend.validate('experimental-psychology-3')
        self.assertEqual(json.loads((candidate/'input_manifest.json').read_text()),manifest)


if __name__=='__main__':unittest.main()
