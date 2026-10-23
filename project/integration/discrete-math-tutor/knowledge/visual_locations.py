"""只读原图导航：像素一致或独立核对的位置；不改变资产审核/发布状态。"""
from __future__ import annotations
from functools import lru_cache
import hashlib
import io
import json
import re
from pathlib import Path
import fitz
from PIL import Image
from knowledge import pdf_reader, source_visuals

REVIEWED = Path(__file__).with_name('visual_locations_reviewed.json')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pixels(data):
    with Image.open(io.BytesIO(data)) as image:
        rgba = image.convert('RGBA')
        background = Image.new('RGBA', rgba.size, 'white')
        rgb = Image.alpha_composite(background, rgba).convert('RGB')
        return hashlib.sha256(str(rgb.size).encode() + rgb.tobytes()).hexdigest()


@lru_cache(maxsize=12)
def pdf_images(path, version):
    # 调用方每次先校验真实 PDF 哈希；缓存只含当前内容版本的像素与位置。
    output = []
    with fitz.open(path) as pdf:
        for number, page in enumerate(pdf, 1):
            for item in page.get_images(full=True):
                xref, mask = item[:2]
                if mask:
                    image = fitz.Pixmap(fitz.Pixmap(pdf, xref), fitz.Pixmap(pdf, mask)).tobytes('png')
                else:
                    image = pdf.extract_image(xref)['image']
                identity = pixels(image)
                for rect in page.get_image_rects(xref):
                    box = rect * page.rotation_matrix
                    bounds = page.rect
                    normalized = dict(page=number, x1=max(0, box.x0/bounds.width), y1=max(0, box.y0/bounds.height),
                                      x2=min(1, box.x1/bounds.width), y2=min(1, box.y1/bounds.height))
                    if normalized['x2'] > normalized['x1'] and normalized['y2'] > normalized['y1']:
                        entry = dict(rect=normalized, pixel_sha256=identity, xref=xref)
                        if entry not in output:
                            output.append(entry)
    return output


def current_document(document_id):
    from knowledge.course_config import PSYCHOLOGY
    manifest = pdf_reader.PSYCHOLOGY_DIR/'pdf_manifest.json' if PSYCHOLOGY else pdf_reader.ROOT/'manifest.json'
    return next((row for row in json.loads(manifest.read_bytes()) if row['document_id'] == document_id), None)


def section_at(record, rect):
    preceding = [s for s in record['sections'] if (s['page'], s['y']) <= (rect['page'], rect['y1']+.015)]
    return preceding[-1]['id'] if preceding else record['sections'][0]['id']


def reference(record, visual, rects, status):
    return dict(document_id=record['document_id'], version=record['version'], chapter_id=visual.chapter_id,
                section_id=visual.section_id, kind='area' if status == 'exact' else 'text', rects=rects,
                text=visual.labels[0] if visual.labels else visual.section, location_status=status)


def caption_matches(record, visual):
    # 只接受原资产上下文中独占一行的完整图注，拒绝正文中同号提及。
    compact = lambda text: re.sub(r'\s+', '', text).replace('．', '.').replace('—', '-')
    captions = {compact(line) for line in visual.context.splitlines()
                if any(re.match(r'^'+re.escape(label)+r'\s+\S', line.strip()) for label in visual.labels)
                and len(line) < 160}
    if not captions:
        return []
    result = []
    with fitz.open(pdf_reader.pdf_path(record)) as pdf:
        for number, page in enumerate(pdf, 1):
            for block in page.get_text('dict')['blocks']:
                for line in block.get('lines', []):
                    if compact(''.join(span['text'] for span in line['spans'])) not in captions:
                        continue
                    box = fitz.Rect(line['bbox']) * page.rotation_matrix
                    result.append(dict(page=number, x1=max(0, box.x0/page.rect.width), y1=max(0, box.y0/page.rect.height),
                                       x2=min(1, box.x1/page.rect.width), y2=min(1, box.y1/page.rect.height)))
    return result


def resolve_figure(asset_id, sha256, document_id, version):
    result = dict(status='unavailable', basis='原图不存在或登记无法核验', selection_ref=None)
    try:
        record = current_document(document_id)
        if not record or record['version'] != version or digest(pdf_reader.pdf_path(record)) != version:
            return result | dict(status='stale', basis='教材版本或 PDF 文件已失效')
        if record.get('course_id') != 'experimental-psychology-3':
            return result
        visual = source_visuals.get_visual(asset_id)
        if not visual:
            return result
        if visual.sha256 != sha256 or visual.chapter_id != record['chapter_id']:
            return result | dict(status='stale', basis='保存的原图哈希或所属文档不一致')
        result.update(asset_id=asset_id, sha256=sha256, document_id=document_id, version=version,
                      chapter_id=visual.chapter_id, section_id=visual.section_id, review_status=visual.review_status)
        images = pdf_images(str(pdf_reader.pdf_path(record)), version)
        asset_pixels = pixels(visual.path.read_bytes())
        matches = [item['rect'] for item in images if item['pixel_sha256'] == asset_pixels]
        basis = 'decoded_pixels_equal'
        if not matches and REVIEWED.is_file():
            rows = json.loads(REVIEWED.read_bytes())
            for row in rows:
                if (row['asset_id'], row['asset_sha256'], row['document_id'], row['version']) != (asset_id, sha256, document_id, version):
                    continue
                # 已核对映射也要验证 PDF 中对应图片像素与区域，拒绝任意坐标。
                matches = [item['rect'] for item in images if item['pixel_sha256'] == row['pdf_pixel_sha256'] and item['rect'] == row['rect']]
                basis = 'reviewed_transcoded_image'
                break
        status = 'exact'
        if not matches:
            matches = caption_matches(record, visual)
            status, basis = 'caption', 'complete_caption_line'
        unique = list({json.dumps(rect, sort_keys=True):rect for rect in matches}.values())
        if unique:
            candidates = [rect for rect in unique if section_at(record, rect) == visual.section_id]
            if len(candidates) != 1:
                return result | dict(status='ambiguous', basis='同图多处出现或资产小节与实际位置不符', candidates=unique)
            rect = dict(candidates[0])
            return result | dict(status=status, basis=basis, page=rect['page'], rects=[rect],
                                 selection_ref=reference(record, visual, [rect], status))
        if any(s['id'] == visual.section_id and s.get('verified') for s in record['sections']):
            return result | dict(status='section', basis='无法核验精确原图或完整图注位置，仅打开已登记小节',
                                 selection_ref=reference(record, visual, [], 'section'))
        return result
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, IndexError, Image.DecompressionBombError):
        return result | dict(status='unavailable', basis='原图位置读取失败，不使用缓存旧位置', selection_ref=None)
