"""固定 SDK 的 Windows sidecar URI 兼容适配。"""
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit
import os

def sidecar_uri_for(directory):
    path=Path(directory).resolve(strict=True)
    # 1.5.7 的 resolver 只读取 urlsplit(...).path；不能把盘符写入 netloc。
    return ("file:"+quote(path.as_posix(),safe="/:")+"/") if os.name=="nt" else path.as_uri()+"/"


def bind_candidate_sidecars(rag, working_dir):
    """查询实例按已核验文档身份读本地sidecar，保留冻结存储中的历史URI。"""
    from .engine import _document_id
    from .ingress import IngressError, load_verified_bundle, pending_root, _contained_regular_file
    from lightrag.utils_pipeline import parsed_artifact_dir_for, sidecar_blocks_path, sidecar_modality_path
    working = Path(working_dir)
    audit = {'mode': 'candidate_local_read_view', 'documents': []}
    def view(key, row):
        if not isinstance(row, dict) or not row.get('sidecar_location'):
            return row
        name = row.get('file_path')
        if (not isinstance(name, str) or Path(name).name != name or '\\' in name
                or _document_id(name) != key or row.get('parse_engine') != 'deeptutor'):
            raise IngressError('查询sidecar文档身份不符')
        uri = urlsplit(row['sidecar_location'])
        old = Path(unquote(uri.path).replace('\\', '/').rstrip('/'))
        if uri.scheme != 'file' or uri.netloc or uri.query or uri.fragment or old.name != name+'.parsed' or old.parent.name != '__parsed__':
            raise IngressError('查询sidecar历史URI不符合冻结文档身份')
        load_verified_bundle(working, name)
        directory = parsed_artifact_dir_for(name, parent_hint=pending_root(working))
        if directory.name != old.name:
            raise IngressError('查询sidecar目录冲突')
        _contained_regular_file(working, directory/(Path(name).stem+'.blocks.jsonl'), label='query sidecar blocks')
        local_uri = sidecar_uri_for(directory)
        blocks = sidecar_blocks_path(local_uri)
        if not blocks or Path(blocks).name != Path(name).stem+'.blocks.jsonl':
            raise IngressError('查询sidecar解析块缺失或身份不符')
        _contained_regular_file(working, Path(blocks), label='query sidecar blocks')
        for modality in ('drawings', 'tables', 'equations'):
            path = Path(sidecar_modality_path(local_uri, modality))
            if path.exists() or path.is_symlink():
                _contained_regular_file(working, path, label='query sidecar '+modality)
        if name not in audit['documents']:
            audit['documents'].append(name)
        return dict(row, sidecar_location=local_uri)
    get = rag.full_docs.get_by_id
    async def get_local(key):
        return view(key, await get(key))
    rag.full_docs.get_by_id = get_local
    if hasattr(rag.full_docs, 'get_by_ids'):
        get_many = rag.full_docs.get_by_ids
        async def get_many_local(keys):
            rows = await get_many(keys)
            if len(rows) != len(keys):
                raise IngressError('查询sidecar批量文档数不符')
            return [view(key, row) for key, row in zip(keys, rows)]
        rag.full_docs.get_by_ids = get_many_local
    return audit
