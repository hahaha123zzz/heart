"""固定教材资产的安装与加载；普通重启只核对小记录和文件大小。"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import datetime
from pathlib import Path

FORMAT = 1
RECORD = 'assets.json'


class AssetsMismatch(RuntimeError):
    """教材资产与当前教材、索引或发行不一致。"""


def _digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _control(candidate):
    return {name: _digest(candidate / name) for name in
            ('input_manifest.json', 'progress.json', 'index_files.json', 'policy.json', 'source_map.json')}


def _existing_record(root):
    for name in (RECORD, 'assets.previous.json'):
        path = Path(root) / name
        if path.is_file():
            try:
                return json.loads(path.read_text(encoding='utf-8'))
            except ValueError:
                continue
    return None


def assets_root():
    value = os.getenv('HEART_TEXTBOOK_ASSETS')
    if value:
        return Path(value)
    home = os.getenv('DEEPTUTOR_HOME')
    return Path(home).parent / 'textbook-assets' if home else Path('.runtime/textbook-assets')


def install(root, textbook, candidate, *, release_id, source_map, citation_builder=None,
            image_terms=None):
    """完整核对教材、冻结输入和活动索引后一次性发布；失败保留上一份记录。"""
    from knowledge.lightrag.course_input import inventory, verify, verify_active

    root = Path(root)
    textbook = Path(textbook).resolve(strict=True)
    candidate = Path(candidate).resolve(strict=True)
    manifest = json.loads((candidate / 'input_manifest.json').read_text(encoding='utf-8'))
    root.mkdir(parents=True, exist_ok=True)
    published_input = root / 'input'
    if (candidate / 'input').is_dir():
        verify(candidate / 'input', manifest['files'])
        shutil.copytree(candidate / 'input', published_input, dirs_exist_ok=True)
        frozen_files = dict(manifest['files'])
        frozen_sizes = {rel: (published_input / rel).stat().st_size for rel in manifest['files']}
    else:
        # 冻结输入已移出在线目录；复用上一次已核验的副本和来源映射。
        prior = _existing_record(root)
        if (prior is None or prior.get('candidate') != str(candidate)
                or prior.get('control') != _control(candidate)):
            raise AssetsMismatch('冻结输入已移出且没有可复用的安装记录，请从原始输入重新安装教材资产')
        frozen_files = prior['frozen']['files']
        frozen_sizes = prior['frozen']['sizes']
        if source_map is None:
            source_map = prior['source_map']
        for relative, expected in frozen_sizes.items():
            file = published_input / relative
            if not file.is_file() or file.stat().st_size != expected:
                raise AssetsMismatch('已发布的冻结输入缺失或已变化：' + relative)
    hashes = inventory(textbook)
    extras = verify_active(textbook, manifest['files'])
    sizes = {rel: (textbook / rel).stat().st_size for rel in hashes}
    citation = root / 'citations.sqlite3'
    pending = root / ('citations.' + os.urandom(8).hex() + '.sqlite3')
    try:
        (citation_builder or _build_citation)(pending, textbook)
        citation_size = pending.stat().st_size
        os.replace(pending, citation)
    finally:
        pending.unlink(missing_ok=True)
    record = {
        'format': FORMAT,
        'release_id': release_id,
        'candidate': str(candidate),
        'textbook_root': str(textbook),
        'control': _control(candidate),
        'textbook': {'files': hashes, 'sizes': sizes},
        'frozen': {'files': frozen_files, 'sizes': frozen_sizes},
        'input_root': str(published_input),
        'host_extras': {'count': len(extras), 'sha256': _digest_of(extras)},
        'citation': {'path': str(citation), 'sha256': _digest(citation), 'size': citation_size},
        'image_terms': dict(image_terms or {}),
        'source_map': source_map,
        'created_at': datetime.now().astimezone().isoformat(timespec='seconds'),
    }
    target = root / RECORD
    if target.is_file():
        (root / 'assets.previous.json').write_bytes(target.read_bytes())
    pending = root / (RECORD + '.tmp')
    pending.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(pending, target)
    return record


def build_image_terms():
    from knowledge.figures import load_figures
    from knowledge.textbook import terms_for

    return {figure.id: sorted(terms_for(figure.caption + ' ' + figure.context))
            for figure in load_figures()}


def _build_citation(target, textbook):
    from knowledge.citation_index import build_index

    build_index(target, textbook)


def _digest_of(extras):
    from knowledge.lightrag.course_input import _fingerprint

    return _fingerprint(extras)


def load(root, textbook, candidate):
    """没有安装记录时返回 None（退回完整扫描）；记录存在但不一致时明确失败。"""
    path = Path(root) / RECORD
    if not path.is_file():
        return None
    record = json.loads(path.read_text(encoding='utf-8'))
    if record.get('format') != FORMAT:
        raise AssetsMismatch('教材资产格式不支持，请重新安装教材资产')
    textbook = Path(textbook).resolve(strict=True)
    candidate = Path(candidate).resolve(strict=True)
    if record.get('textbook_root') != str(textbook) or record.get('candidate') != str(candidate):
        raise AssetsMismatch('教材资产与当前教材或 LightRAG 索引路径不一致，请重新安装教材资产')
    input_root = Path(record.get('input_root') or '')
    if input_root.resolve() != (Path(root) / 'input').resolve():
        raise AssetsMismatch('教材资产的冻结输入位置无效，请重新安装教材资产')
    if record.get('control') != _control(candidate):
        raise AssetsMismatch('教材资产与当前 LightRAG 索引不一致，请重新安装教材资产')
    citation = record.get('citation') or {}
    citation_path = Path(citation.get('path') or '')
    if not citation.get('path') or not citation_path.is_file() or citation_path.stat().st_size != citation.get('size'):
        raise AssetsMismatch('教材资产缺少引用坐标索引，请重新安装教材资产')
    for label, base, sizes in (
            ('教材', textbook, record['textbook']['sizes']),
            ('冻结输入', input_root, record['frozen']['sizes'])):
        for relative, expected in sizes.items():
            file = base / relative
            if not file.is_file() or file.stat().st_size != expected:
                raise AssetsMismatch(f'{label}资产缺失或已变化：{relative}；请重新安装教材资产')
    return record
