"""已发布教材的只读适配：目录/read_target/PDF正文/Q2定位，不建立第二套索引。"""
import hashlib
import json

from agents.q3_navigation import SourceRef
from agents.tools.first_wave import ReadFailure
from agents.tools.first_wave_contracts import TEXT_LIMIT


class CourseReadService:
    def check(self, binding):
        from knowledge.course_config import COURSE_ID
        from knowledge.course_release import validate
        from knowledge.pdf_reader import documents
        if COURSE_ID != binding.course_id:
            raise ReadFailure('binding_mismatch', '教材课程绑定已失效。')
        validate(binding.release_id)
        current = {(d['document_id'], d['version']) for d in documents()}
        if not binding.documents or not set(binding.documents) <= current:
            raise ReadFailure('stale_version', '授权文档版本已失效。')

    def _documents(self, binding):
        from knowledge.pdf_reader import documents
        return [d for d in documents() if (d['document_id'], d['version']) in binding.documents]

    def files(self, binding):
        # manifest中的PDF记录才是公开文档，不枚举磁盘，绝不暴露部署文件。
        return [{'document_id': d['document_id'], 'version': d['version'],
                 'name': d['title'] + '.pdf', 'chapter_id': d['chapter_id'], 'page_count': d['page_count'],
                 'page_basis': 'generated_reader'} for d in self._documents(binding)]

    def verify_source(self, binding, source):
        """登记时重核实际范围，不能把任意source_index字符串升级成教材证据。"""
        from knowledge.citation_index import LiveCitationIndex
        evidence = source['location']['evidence']
        block_id = evidence.get('source_block_id')
        if block_id is None:
            value, rows = self._pages(binding, {'document_id': source['document_id'],
                'version': source['version'], 'page': source['page']}, lambda: None)
            if len(rows) != 1 or rows[0]['text'] != source['text'] or evidence.get('location_status') != 'page':
                raise ReadFailure('unverified_source', '页级原文范围不匹配。')
            return
        index = LiveCitationIndex()
        try:
            blocks = index.blocks(source['document_id'], block_id, block_id)
            start, end = evidence.get('block_start'), evidence.get('block_end')
            if (not blocks or type(start) is not int or type(end) is not int or
                not 0 <= start < end <= len(blocks[0]['text']) or
                blocks[0]['text'][start:end] != source['text'] or
                blocks[0]['section_id'] != source['section_id']):
                raise ReadFailure('unverified_source', '段落原文范围不匹配。')
            located = index.locate(source['document_id'], source['version'], source['text'], block_id=block_id)
            if evidence.get('location_status') == 'section':
                from knowledge.grounding_text import normalized
                valid = (not evidence.get('rects') and normalized(source['text']) in
                         index.document(source['document_id'], source['version'])['folded'])
            else:
                valid = (evidence.get('location_status') == 'exact' and located['status'] == 'exact'
                         and located['rects'] == evidence.get('rects'))
            if not valid:
                raise ReadFailure('unverified_source', '段落没有可核对的当前原页坐标。')
        finally:
            index.close()

    def _units(self, binding):
        from knowledge.course_navigation import outline
        chapters = {d['chapter_id'] for d in self._documents(binding)}
        return [u for u in outline() if u['chapter_id'] in chapters and u.get('source_valid')]

    def outline(self, binding):
        return [{k: u[k] for k in ('id', 'title', 'chapter_id', 'section_id',
            'chapter_title', 'section_title', 'version', 'page')} for u in self._units(binding)]

    @staticmethod
    def _source(record, quote, *, block_id=None, start=None, end=None, section_id=None,
                page=None, rects=(), status='exact'):
        key = hashlib.sha256(json.dumps([record['document_id'], record['version'],
            block_id, start, end, page, quote], ensure_ascii=False).encode()).hexdigest()
        evidence = {'evidence_id': key, 'retrieval_source_id': 'readonly:' + key,
            'document_id': record['document_id'], 'document_version': record['version'],
            'source_block_id': block_id, 'block_start': start, 'block_end': end,
            'section_id': section_id, 'quote': quote, 'location_status': status,
            'rects': list(rects), 'page': page,
            'degradation_reason': '按阅读版页读取；未声明精确段落高亮' if status == 'page' else None}
        section = next((s for s in record['sections'] if s['id'] == section_id), {})
        return SourceRef(key, record['document_id'], quote, record['version'],
            record['chapter_id'], section_id, page, quote,
            location={'origin': 'q2_readonly', 'source': record['source'],
                'source_file': record['source'], 'section': section.get('title', ''),
                'kind': 'paragraph', 'asset_ids': [], 'block_start': block_id, 'block_end': block_id,
                'block_char_start': start, 'block_char_end': end, 'document_version': record['version'],
                'source_spans': [] if block_id is None else [{'block_id': block_id,
                    'block_start': start, 'block_end': end, 'text_start': 0, 'text_end': len(quote)}],
                'evidence': evidence}).to_dict()

    def _blocks(self, record, blocks, check_cancelled, *, char_offset=0):
        from knowledge.citation_index import LiveCitationIndex
        index = LiveCitationIndex()
        sources, used = [], 0
        continuation = None
        try:
            for position, block in enumerate(blocks):
                check_cancelled()
                start = char_offset if position == 0 else 0
                if start >= len(block['text']):
                    raise ReadFailure('invalid_range', '段内偏移超出原文范围。')
                remaining = TEXT_LIMIT - used - (1 if sources else 0)
                if remaining <= 0 or len(sources) >= 24:
                    continuation = {'block_id': block['block_id'], 'char_offset': 0}
                    break
                quote = block['text'][start:start + remaining]
                if not quote.strip():
                    continue
                located = index.locate(record['document_id'], record['version'], quote,
                                       block_id=block['block_id'])
                if located['status'] != 'exact':
                    raise ReadFailure('unlocated', '目标原文无法唯一映射到教材原页，请按页读取。')
                page = min(r['page'] for r in located['rects'])
                sources.append(self._source(record, quote, block_id=block['block_id'], start=start,
                    end=start + len(quote), section_id=block['section_id'], page=page, rects=located['rects']))
                used += len(quote) + (1 if len(sources) > 1 else 0)
                if start + len(quote) < len(block['text']):
                    continuation = {'block_id': block['block_id'], 'char_offset': start + len(quote)}
                    break
        finally:
            index.close()
        if not sources:
            raise ReadFailure('no_text', '该范围没有可核验文字，未读取图像像素。')
        return {'text': '\n'.join(s['text'] for s in sources), 'truncated': continuation is not None,
                'continuation': continuation, 'range': [s['location']['evidence'] | {'quote': None, 'rects': []}
                                                       for s in sources]}, sources

    def read_material(self, binding, args, check_cancelled):
        if 'unit_id' not in args:
            return self._pages(binding, args, check_cancelled)
        from knowledge.course_navigation import read_target
        from knowledge.citation_index import LiveCitationIndex
        unit = next((u for u in self._units(binding) if u['id'] == args['unit_id']), None)
        if unit is None:
            raise ReadFailure('unknown_unit', '目标不属于当前授权教材目录。')
        read_target(unit)  # 复用现有目录、源文件与PDF版本校验，不使用导航写接口。
        record = next(d for d in self._documents(binding) if d['chapter_id'] == unit['chapter_id'])
        index = LiveCitationIndex()
        try:
            blocks = [b for b in index.blocks(record['document_id'], min(unit['source_block_ids']),
                                             max(unit['source_block_ids']))
                      if b['block_id'] in unit['source_block_ids']]
        finally:
            index.close()
        offset = args.get('block_offset', 0)
        if offset >= len(blocks):
            raise ReadFailure('invalid_range', '目标段落偏移超出范围。')
        value, sources = self._blocks(record, blocks[offset:], check_cancelled,
                                     char_offset=args.get('char_offset', 0))
        if value['continuation']:
            pointer = value['continuation']
            value['continuation'] = {'unit_id': unit['id'],
                'block_offset': next(i for i, b in enumerate(blocks) if b['block_id'] == pointer['block_id']),
                'char_offset': pointer['char_offset']}
        return dict(value, unit_id=unit['id'], unit_version=unit['version']), sources

    def _pages(self, binding, args, check_cancelled):
        from knowledge.pdf_reader import evidence_text
        record = next(d for d in self._documents(binding) if d['document_id'] == args['document_id'])
        start, end = args['page'], args.get('end_page', args['page'])
        if start < 1 or end > record['page_count']:
            raise ReadFailure('invalid_range', '页码超出当前阅读版文档。')
        sources, total, continuation = [], 0, None
        for page in range(start, end + 1):
            check_cancelled()
            text = evidence_text(record['document_id'], record['version'],
                                 [dict(page=page, x1=0, y1=y, x2=1, y2=y + .5) for y in (0, .5)])
            remaining = TEXT_LIMIT - total - (1 if sources else 0)
            if len(text) > remaining:
                # 页级证据保留整页；不把裁掉半页的引句冒充完整页。
                continuation = {'document_id': record['document_id'], 'version': record['version'], 'page': page}
                break
            if not text.strip():
                continue
            sections = [s for s in record['sections'] if s['page'] <= page]
            section = sections[-1] if sections else record['sections'][0]
            sources.append(self._source(record, text, section_id=section['id'], page=page, status='page'))
            total += len(text) + (1 if len(sources) > 1 else 0)
        if not sources:
            raise ReadFailure('no_text', '该页无可提取文字或单页超过预算，请缩小到目录目标；未读取图像像素。')
        return {'text': '\n'.join(s['text'] for s in sources), 'truncated': continuation is not None,
            'continuation': continuation, 'requested_pages': [start, end],
            'read_pages': [s['page'] for s in sources], 'page_basis': 'generated_reader'}, sources

    def read_source(self, binding, source, check_cancelled):
        record = next(d for d in self._documents(binding) if d['document_id'] == source['document_id'])
        evidence = source['location']['evidence']
        block_id = evidence.get('source_block_id')
        if block_id is None:
            return self._pages(binding, {'document_id': record['document_id'], 'version': record['version'],
                                        'page': source['page']}, check_cancelled)
        from knowledge.citation_index import LiveCitationIndex
        index = LiveCitationIndex()
        try:
            blocks = [b for b in index.blocks(record['document_id'], max(0, block_id - 1), block_id + 1)
                      if b['section_id'] == source['section_id']]
        finally:
            index.close()
        return self._blocks(record, blocks, check_cancelled)
