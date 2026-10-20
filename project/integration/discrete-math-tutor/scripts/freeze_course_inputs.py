"""冻结全 11 章 LightRAG 输入和来源清单；不建图、不发布、不读取凭据。"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
COURSE = ROOT / 'knowledge/courses/experimental-psychology-3'
SCHEMA = 'full-course-inputs-v1'
import sys
sys.path.insert(0, str(ROOT))
from knowledge.source_visuals import DECORATIONS


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_path(root, relative):
    path = root / relative
    if Path(relative).is_absolute() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('输入路径越出课程目录：' + str(relative))
    return path


def identity(files):
    return hashlib.sha256(json.dumps(files, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def inventory(root):
    manifest = json.loads((root / 'manifest.json').read_bytes())
    if sorted(chapter['id'] for chapter in manifest['chapters']) != list(range(1, 12)):
        raise ValueError('必须提供完整 11 章；不以单章试点替代全书输入')
    pdfs = json.loads((root / 'pdf_manifest.json').read_bytes())
    files = {}

    def add(relative, kind, expected=None):
        path = safe_path(root, relative)
        digest = sha(path)
        if expected and digest != expected:
            raise ValueError('输入文件哈希不一致：' + str(relative))
        key = path.relative_to(root).as_posix()
        files[key] = {'path': key, 'kind': kind, 'size': path.stat().st_size, 'sha256': digest}
        return digest

    for name in ('manifest.json', 'pdf_manifest.json', 'import_report.json'):
        add(name, 'course_metadata')
    chapters = []
    assets = []
    for chapter in manifest['chapters']:
        number = chapter['id']
        relative = Path('chapters') / f'chapter_{number:02d}'
        directory = root / relative
        source = next(item for item in manifest['full_import']['chapters'] if item['chapter_id'] == number)
        source_sha = add(source['docx'], 'original_docx', source['source_sha256'])
        document_sha = add(relative / 'document.json', 'parsed_blocks')
        document = json.loads((directory / 'document.json').read_bytes())
        if document.get('docx_sha256') != source_sha:
            raise ValueError(f'第 {number} 章解析块不属于当前原件')
        pdf = next(item for item in pdfs if item['chapter_id'] == number)
        pdf_sha = add(relative / f'chapter_{number:02d}.generated.pdf', 'generated_pdf', pdf['version'])
        add(relative / 'assets.json', 'asset_mapping')
        for name in ('chunks.jsonl', 'text.txt', 'formulas.json', 'pdf_locations.json', 'word_pages.json'):
            add(relative / name, 'parsed_sidecar')
        rows = json.loads((directory / 'assets.json').read_bytes())
        with zipfile.ZipFile(safe_path(root, source['docx'])) as package:
            for asset in rows:
                asset_path = relative / asset['filename']
                digest = add(asset_path, 'original_asset', asset['sha256'])
                if asset['source_sha256'] != source_sha:
                    raise ValueError('资产属于不同源文件：' + asset['id'])
                original_sha = hashlib.sha256(package.read(asset['package_part'])).hexdigest()
                if original_sha != digest:
                    raise ValueError('资产与 DOCX 嵌入原件不一致：' + asset['id'])
                with Image.open(root / asset_path) as image:
                    width, height = image.size
                decoration = DECORATIONS.get(digest)
                filtered = height < 80 or width / height > 12
                disposition = 'exclude_decoration' if decoration else 'exclude_unresolved' if filtered else 'candidate_pending_review'
                assets.append({
                    'id': asset['id'], 'chapter_id': number, 'section_id': asset.get('section_id'),
                    'block_index': asset.get('block_index'), 'occurrences': asset.get('occurrences') or [],
                    'path': asset_path.as_posix(), 'sha256': digest, 'source_sha256': source_sha,
                    'package_part': asset['package_part'], 'package_sha256': original_sha,
                    'width': width, 'height': height, 'review_status': asset['review_status'],
                    'disposition': disposition, 'visual_inspection': decoration,
                    'recovery': ('not_a_missing_knowledge_image' if decoration else
                                 'requires_original_replacement' if filtered else 'original_bytes_present'),
                    'knowledge_evidence_allowed': False,
                })
        chapters.append({'chapter_id': number, 'title': chapter['title'],
            'sections': chapter['sections'], 'source_path': source['docx'], 'source_sha256': source_sha,
            'document_sha256': document_sha, 'pdf_document_id': pdf['document_id'],
            'pdf_sha256': pdf_sha, 'blocks': len(document['blocks']), 'assets': len(rows)})
    file_list = sorted(files.values(), key=lambda item: item['path'])
    return {'schema': SCHEMA, 'course_id': manifest['course_id'], 'course_status': manifest['status'],
        'ready': False, 'snapshot_id': identity(file_list), 'files': file_list, 'chapters': chapters,
        'assets': assets, 'asset_counts': dict(Counter(item['disposition'] for item in assets)),
        'existing_index': {'sha256': sha(root / 'rag_index.sqlite3'), 'included': False, 'mode': 'read_only_reference'},
        'policy': '全 11 章文本/表格/公式进入独立候选建图；pending 原图只可作为待审核候选，'
                  '排除装饰图和未解决缺口，不以文件存在宣称发布就绪。'}


def verify(snapshot):
    report = json.loads((snapshot / 'input_manifest.json').read_bytes())
    if report['schema'] != SCHEMA or identity(report['files']) != report['snapshot_id']:
        raise ValueError('快照清单身份无效')
    if sorted(chapter['chapter_id'] for chapter in report['chapters']) != list(range(1, 12)):
        raise ValueError('快照不含完整 11 章')
    for item in report['files']:
        path = safe_path(snapshot / 'course', item['path'])
        if path.stat().st_size != item['size'] or sha(path) != item['sha256']:
            raise ValueError('冻结输入已变化：' + item['path'])
    return report


def freeze(root, destination):
    report = inventory(root)
    destination.mkdir(parents=True, exist_ok=False)
    for item in report['files']:
        source = safe_path(root, item['path'])
        target = safe_path(destination / 'course', item['path'])
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    (destination / 'input_manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8', newline='\n')
    verify(destination)
    for item in report['files']:
        if sha(safe_path(root, item['path'])) != item['sha256']:
            raise ValueError('冻结期间源输入已变化，请另建快照重试')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=COURSE)
    operation = parser.add_mutually_exclusive_group(required=True)
    operation.add_argument('--output', type=Path)
    operation.add_argument('--verify', type=Path)
    args = parser.parse_args()
    report = verify(args.verify) if args.verify else freeze(args.source, args.output)
    print(json.dumps({'snapshot_id': report['snapshot_id'], 'chapters': len(report['chapters']),
                      'files': len(report['files']), 'assets': report['asset_counts'], 'ready': report['ready']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
