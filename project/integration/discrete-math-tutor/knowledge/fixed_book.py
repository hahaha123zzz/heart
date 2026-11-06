"""固定教材的进程资源；修改教材或模型配置后必须重启服务。"""
from __future__ import annotations

import asyncio
import contextvars
from copy import deepcopy
from dataclasses import replace
from functools import lru_cache
import hashlib
import os
from pathlib import Path
import time


def enabled():
    return os.getenv('FIXED_BOOK_RETRIEVAL_ENABLED', '0') == '1'


runtime = None


def active():
    return runtime if enabled() and runtime is not None and runtime.ready else None


def digest(path):
    path = Path(path)
    state = active()
    if state and hasattr(state, 'source_root') and path.absolute().is_relative_to(state.source_root.absolute()):
        from knowledge.lightrag.ingress import _contained_regular_file
        path = _contained_regular_file(state.source_root, path, label='fixed course resource')
    if state and str(path.resolve()) in state.hashes:
        if not path.is_file():
            raise FileNotFoundError(path.name)
        return state.hashes[str(path.resolve())]
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


class ResidentGraph:
    """SDK 队列回调使用当前查询的 context，避免捕获首轮用户和取消令牌。"""
    def __init__(self, backend, embedding, roles):
        self.backend, self.embedding, self.roles = backend, embedding, roles
        self.rag = None
        self.request = None

    @lru_cache(maxsize=256)
    def keywords(self, query):
        # 缓存属于该实例的教材/模型快照；只匹配图中已有实体，不猜新术语。
        text = ' '.join(query.split()).casefold()
        found = []
        for entity in self.backend.entity_terms:
            term = entity.casefold()
            if term in text and not any(term in old.casefold() for old in found):
                found.append(entity)
                if len(found) == 8:
                    break
        return tuple(found)

    def dispatch(self, name):
        async def invoke(*args, **kwargs):
            request = self.request
            if request is None:
                raise RuntimeError('LightRAG 回调没有所属请求')
            callback = request['callbacks'][name]
            # SDK 的长期队列任务不能继承首次调用时的预算/用户 context。
            task = asyncio.create_task(callback(*args, **kwargs), context=request['context'].copy())
            return await task
        return invoke

    async def start(self):
        from knowledge.lightrag import engine
        from lightrag.utils import EmbeddingFunc
        adapters = {role: self.dispatch(role) for role in self.roles}
        adapters['embedding'] = EmbeddingFunc(embedding_dim=self.embedding.dim,
            max_token_size=self.embedding.max_tokens, func=self.dispatch('embedding'))
        self.rag = engine.build_rag(self.backend.candidate / 'index', query_roles=self.roles,
            embedding_config=self.embedding, query_only=True, adapters=adapters)
        try:
            await engine.initialize(self.rag)
            from knowledge.lightrag.paths import bind_candidate_sidecars
            self.sidecars = bind_candidate_sidecars(self.rag, self.backend.candidate / 'index')
            from knowledge.lightrag.ingress import load_verified_bundle, _contained_regular_file
            from lightrag.utils_pipeline import sidecar_modality_path
            import json
            self.provenance = {}
            working = self.backend.candidate / 'index'
            for name in self.backend.source_map:
                manifest, bundle = load_verified_bundle(working, name)
                raw = json.loads((bundle / manifest['blocks']['path']).read_text(encoding='utf8'))
                full = await self.rag.full_docs.get_by_id(engine._document_id(name))
                modalities = {}
                for kind in ('drawings', 'tables', 'equations'):
                    sidecar = sidecar_modality_path((full or {}).get('sidecar_location'), kind)
                    # 某章没有该类素材时，SDK 仍返回预期文件名。
                    if sidecar and (Path(sidecar).exists() or Path(sidecar).is_symlink()):
                        path = _contained_regular_file(working, Path(sidecar), label='startup sidecar')
                        modalities[kind] = json.loads(path.read_text(encoding='utf8')).get(kind,{})
                self.provenance[name] = {'raw':raw,'modalities':modalities}
        except BaseException:
            await engine.finalize(self.rag, cancel_pending=True)
            self.rag = None
            raise

    async def query(self, query, mode, metrics, bridge):
        from knowledge.lightrag.config import build_embedding_func, build_llm_model_func
        from knowledge.lightrag import engine
        from knowledge.lightrag.retrieval import attach_provenance
        if self.request is not None:
            raise RuntimeError('共享图谱查询必须持有查询所有权')
        callbacks = {role: build_llm_model_func(io_bridge=bridge,
            llm_config=replace(call.config, metrics=metrics), owner=call.owner)
            for role, call in self.roles.items()}
        callbacks['embedding'] = build_embedding_func(embedding_config=replace(self.embedding, metrics=metrics))
        self.request = {'callbacks': callbacks, 'context': contextvars.copy_context()}
        try:
            before = self.keywords.cache_info().hits
            with metrics.timed('keyword.rules'):
                keywords = self.keywords(' '.join(query.split()))
            metrics.stages.append({'stage':'keyword.policy', 'source':'graph_entities' if keywords else 'sdk_extraction',
                'cache_hit':self.keywords.cache_info().hits > before, 'count':len(keywords)})
            with metrics.timed('native.query', includes_children=True):
                _, records = await engine.query_with_sources(self.rag, query, mode, keywords=keywords)
            return await attach_provenance(self.rag, self.backend.candidate / 'index', records, prepared=self.provenance)
        finally:
            self.request = None

    async def close(self):
        self.keywords.cache_clear()
        if self.rag is not None:
            from knowledge.lightrag import engine
            await engine.finalize(self.rag, cancel_pending=True)
            self.rag = None


class FixedBookRuntime:
    def __init__(self):
        self.ready = False
        self.hashes = {}
        self.backend = None
        self.started = time.monotonic()

    async def start(self):
        from knowledge.course_config import PSYCHOLOGY_DIR, COURSE_ID
        self.source_root = PSYCHOLOGY_DIR
        from knowledge.lightrag.course_input import inventory
        from knowledge.lightrag.retrieval import LightRagBackend
        from knowledge.lightrag.pipeline import embedding_config
        from knowledge.lightrag.roles import resolve_query_roles, query_binding
        from knowledge.lightrag.worker import run_in_worker_loop
        from knowledge.lightrag import storage
        from knowledge.course_release import validate
        if not os.getenv('LIGHTRAG_CANDIDATE_PATH'):
            raise RuntimeError('固定教材启动缺少 LIGHTRAG_CANDIDATE_PATH')
        self.backend = LightRagBackend(os.environ['LIGHTRAG_CANDIDATE_PATH'],
            authorized_course_ids={COURSE_ID}, allow_candidate=os.getenv('LIGHTRAG_ALLOW_CANDIDATE') == '1',
            source_root=PSYCHOLOGY_DIR)
        snapshot = {}
        self.backend.manifest = await asyncio.to_thread(self.backend.validate, COURSE_ID, snapshot=snapshot)
        self.backend.startup_snapshot = snapshot
        self.backend.source_map = await asyncio.to_thread(self.backend.load_source_map)
        from knowledge.lightrag.course_input import visual_inventory
        self.backend.visual_map = (await asyncio.to_thread(visual_inventory, self.backend.candidate / 'input'))[0]
        self.release = await asyncio.to_thread(validate)
        from knowledge.course_navigation import outline
        self.outline = await asyncio.to_thread(outline)
        from knowledge.source_visuals import load_visuals
        self.visuals = {v.id: v for v in (await asyncio.to_thread(load_visuals))[0]}
        files = await asyncio.to_thread(inventory, PSYCHOLOGY_DIR)
        self.hashes = {str((PSYCHOLOGY_DIR / name).resolve()): sha for name, sha in files.items()}
        # 坐标索引是衍生数据，独立保存，不修改教材或已封存图谱。
        from knowledge.citation_index import build_index
        from knowledge.grounded_citations import settings
        self.citation_path = settings()
        if self.citation_path == 'live':
            self.citation_path = Path('.runtime/fixed-book') / self.release['release_id'] / 'citations.sqlite3'
            if not self.citation_path.is_file():
                from uuid import uuid4
                pending = self.citation_path.with_name(uuid4().hex + '.sqlite3')
                try:
                    await asyncio.to_thread(build_index, pending, PSYCHOLOGY_DIR)
                    os.replace(pending, self.citation_path)
                finally:
                    pending.unlink(missing_ok=True)
            self.citation_path = self.citation_path.resolve()
        import json
        self.policy = json.loads((self.backend.candidate / 'policy.json').read_text(encoding='utf8'))
        embedding = await embedding_config()
        storage.require_compatible_embedding(self.backend.candidate / 'index', embedding)
        self.roles = resolve_query_roles()
        self.model_binding = query_binding(self.policy, self.roles)
        from knowledge.lightrag import engine
        entity_file = self.backend.candidate / 'index' / engine.workspace_for(self.backend.candidate / 'index') / 'vdb_entities.json'
        entities = json.loads(entity_file.read_text(encoding='utf8'))['data']
        self.backend.entity_terms = tuple(sorted({e['entity_name'] for e in entities
            if isinstance(e.get('entity_name'), str) and 2 <= len(e['entity_name']) <= 80}, key=lambda s:(-len(s), s)))
        self.backend.resident = ResidentGraph(self.backend, embedding, self.roles)
        await run_in_worker_loop(lambda _: self.backend.resident.start())
        self.ready = True
        try:
            # 快速路径同样预热，缓存签名从本次完整核验中取得。
            from knowledge.local_rag.course_retrieval import warm
            await asyncio.to_thread(warm)
            from knowledge.hybrid_retrieval import _reranker_on_device
            from knowledge.inference_runtime import configured_device
            await asyncio.to_thread(_reranker_on_device, 'BAAI/bge-reranker-base', configured_device('RERANK'))
            from knowledge.local_rag.course_retrieval import retrieve
            await asyncio.to_thread(retrieve, '自变量是什么', limit=4)
            from llm.transport import borrow
            client = self.roles['query'].config.client
            with borrow(client.api_key, client.base_url):
                pass
            from knowledge.figures import load_figures
            from knowledge.textbook import terms_for
            self.image_terms = {f.id: terms_for(f.caption + ' ' + f.context)
                                for f in await asyncio.to_thread(load_figures)}
        except BaseException:
            await self.close()
            raise
        self.start_seconds = time.monotonic() - self.started

    async def close(self):
        self.ready = False
        if self.backend and getattr(self.backend, 'resident', None):
            from knowledge.lightrag.worker import run_in_worker_loop
            await run_in_worker_loop(lambda _: self.backend.resident.close())

    def binding(self):
        return deepcopy({k: self.release[k] for k in ('release_id', 'status', 'ready', 'gaps')})


async def start():
    global runtime
    if not enabled():
        return
    from knowledge.course_config import PSYCHOLOGY
    if not PSYCHOLOGY:
        raise RuntimeError('固定教材模式仅适用于当前心理学教材')
    runtime = FixedBookRuntime()
    try:
        await runtime.start()
    except BaseException:
        await runtime.close()
        runtime = None
        raise


async def stop():
    global runtime
    if runtime:
        await runtime.close()
        runtime = None


def rule_evidence(question, sources):
    from knowledge.grounded_citations import choose_evidence
    from knowledge.lightrag.retrieval import as_textbook_chunk
    state = active()
    if state is None:
        raise RuntimeError('retrieval_not_ready')
    def select(payload):
        for item in payload['candidates']:
            if 'retrieval_source_index' in item:
                item['retrieval_score']=sources[item['retrieval_source_index']].location.get('retrieval_score')
        return select_evidence(payload)
    return choose_evidence(None, question, [as_textbook_chunk(s.to_dict()) for s in sources],
                           state.citation_path, selection_fn=select)


def search_query(message):
    import re
    original = message.split('\n补充说明：', 1)[0]
    matches = re.findall(r'(?:解释|讲解|介绍)(?:一下)?([^，。！？?；;\n]{2,60})', original)
    if matches and not re.match(r'^(?:这个|这段|刚才|原来|当前|上面)', matches[-1]):
        return matches[-1].strip()
    return original


def select_evidence(payload):
    from knowledge.textbook import terms_for
    question = search_query(payload["question"])
    terms = terms_for(question)
    import re
    topic = re.sub(r'^(?:请|给我|帮我)?(?:解释|讲解|介绍)(?:一下)?|是什么[？?。]*$|^什么是', '', question).strip(' ，。？！?')
    def relevance(item):
        return 10 * bool(topic and topic in item['quote']) + len(terms & terms_for(item['quote']))
    def rank(item):
        return (0 if item.get('selected_target') else 1, -relevance(item),
                -(item.get('retrieval_score') or 0), item.get('retrieval_source_index',0),
                -min(len(item['quote']),400))
    ranked = sorted(payload['candidates'], key=rank)
    relevant = [item for item in ranked if item.get('selected_target') or relevance(item)]
    # 无关键词的追问保留最佳上下文；不以无关条目补满三条。
    chosen = []; seen = set()
    for item in relevant or ranked[:1]:
        identity = item['quote']
        if identity not in seen:
            chosen.append(item['evidence_id']);seen.add(identity)
        if len(chosen) == 3:
            break
    return {'evidence_ids':chosen}
