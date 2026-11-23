from copy import deepcopy
import pytest

def test_explicit_canonical_ids_keep_identity_but_names_never_infer_ids(monkeypatch):
    from integrations.deeptutor import catalog_binding as binding
    from deeptutor.learning import topic_generation as native
    monkeypatch.setattr(binding,'confirmed_catalog',lambda:({'kc-3-1':{'name':'相关设计'}},'version'))
    monkeypatch.setattr(native,'materialize_modules',native.materialize_modules)
    binding.install_catalog_binding()
    raw=[{'name':'教材模块','knowledge_points':[{'id':'kc-3-1','name':'相关设计','type':'concept'}]}]
    result=native.materialize_modules('path',raw,strict=True)
    assert result[0].knowledge_points[0].id=='kc-3-1'
    raw[0]['knowledge_points'][0].pop('id')
    assert native.materialize_modules('path',raw,strict=True)[0].knowledge_points[0].id!='kc-3-1'

def test_invalid_duplicate_or_renamed_canonical_claims_are_rejected(monkeypatch):
    from integrations.deeptutor import catalog_binding as binding
    from deeptutor.learning import topic_generation as native
    monkeypatch.setattr(binding,'confirmed_catalog',lambda:({'kc-3-1':{'name':'相关设计'}},'version'))
    monkeypatch.setattr(native,'materialize_modules',native.materialize_modules)
    binding.install_catalog_binding()
    for points in [[{'id':'kc-3-1','name':'另一概念'}],[{'id':'kc-other','name':'相关设计'}],[{'id':'kc-3-1','name':'相关设计'}]*2]:
        with pytest.raises(native.TopicGenerationError):native.materialize_modules('path',[{'name':'模块','knowledge_points':points}],strict=True)


def test_graph_file_source_and_canonical_id_survive_topic_api(monkeypatch, tmp_path):
    import asyncio
    from integrations.deeptutor import catalog_binding as binding
    from deeptutor.learning import topic_generation as native
    from deeptutor.api.routers import mastery_path as api
    from deeptutor.learning.storage import LearningStore
    monkeypatch.setattr(binding, 'confirmed_catalog', lambda: ({'kc-3-1': {'name': '相关设计'}}, 'version'))
    monkeypatch.setattr(native, 'materialize_modules', native.materialize_modules)
    binding.install_catalog_binding()
    store = LearningStore(tmp_path)
    monkeypatch.setattr(api, 'LearningStore', lambda: store)
    request = api.ConfirmTopicRequest(name='相关设计', goal='学习相关设计', sources=[{
        'client_ref': 'graph-source', 'kind': 'file', 'source_id': 'chapter-3',
        'label': '第三章教材原文', 'excerpt': '相关不能直接证明因果。',
    }], modules=[{'name': '相关设计', 'knowledge_points': [{
        'id': 'kc-3-1', 'name': '相关设计', 'type': 'concept', 'topic_source_refs': ['graph-source'],
    }]}])
    result = asyncio.run(api.create_topic(request))
    assert 'kc-3-1' in str(result)
    assert 'chapter-3' in str(result)