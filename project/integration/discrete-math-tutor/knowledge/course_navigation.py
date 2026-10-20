"""先解析教材位置，再读取正文；导航位置与掌握状态相互独立。"""
from dataclasses import asdict
import hashlib
import json
import re

from knowledge.course import chapters
from knowledge.course_config import PSYCHOLOGY, PSYCHOLOGY_DIR
from knowledge.local_rag.syllabus import SyllabusUnit
from knowledge.pdf_reader import document_for_chapter, pdf_path
from knowledge.psychology_retrieval import HEADING, _group
from knowledge.source_mapping import source_spans
from knowledge.textbook import TextbookChunk, terms_for


def _number(value):
    if value.isdecimal():
        return int(value)
    digits = {char: i for i, char in enumerate('零一二三四五六七八九')}
    if value == '十':
        return 10
    if value.startswith('十') and len(value) == 2:
        return 10 + digits.get(value[1], 0)
    return digits.get(value)


def _depth(text):
    return 1 if re.match(r'^[一二三四五六七八九十]+、', text) else 2 if text.startswith('(') else 3


def outline():
    """目录顺序只来自已发布章/节和正文标题，不生成隐式知识路径。"""
    result = []
    for chapter in chapters():
        path = PSYCHOLOGY_DIR / 'chapters' / f'chapter_{chapter["id"]:02d}' / 'document.json'
        raw = path.read_bytes()
        document = json.loads(raw)
        record = document_for_chapter(chapter['id'])
        version = hashlib.sha256(raw).hexdigest() + ':' + record['version']
        for section in chapter['sections']:
            blocks = [b for b in document['blocks'] if b.get('section_id') == section['id']]
            headings = [(i, b) for i, b in enumerate(blocks)
                        if len(b['text'].strip()) <= 65 and HEADING.match(b['text'].strip())]
            # 父标题不再作为重复教学点，保留正文中可定位的叶子标题。
            leaves = [(i, b) for pos, (i, b) in enumerate(headings)
                      if pos + 1 == len(headings)
                      or _depth(headings[pos + 1][1]['text'].strip()) <= _depth(b['text'].strip())]
            if not leaves and blocks:
                leaves = [(0, blocks[0])]
            for position, (index, block) in enumerate(leaves):
                title = HEADING.sub('', block['text'].strip()).strip() if headings else section['title']
                unit = SyllabusUnit(id=f'ch{chapter["id"]}:s{section["id"]}:b{block["block_index"]}',
                    position=len(result), title=title, topics=[section['title']])
                group = _group(blocks, index) if headings else blocks
                # 章/节入口同时带上首个标题前的导言，避免仅有标题而无正文。
                if position == 0:
                    group = blocks[:index] + group
                result.append(asdict(unit) | {'chapter_id': chapter['id'], 'section_id': section['id'],
                    'chapter_title': chapter['title'], 'section_title': section['title'],
                    'version': version, 'blocks': group, 'source': document['source'],
                    'page': next(s['page'] for s in record['sections'] if s['id'] == section['id'])})
    return result


def intent(message):
    text = ''.join(message.split())
    if re.search(r'(?:不要|不用|别|暂不|先不|不想).{0,6}(?:下一|换章|换节|继续|接下来|下一步)', text):
        return None
    if re.search(r'(?:知识点|下一章|下一节)(?:是什么|的意思|什么意思)', text):
        return None
    # “下一步推导/继续这个例子/继续讲刚才的”仍指向当前对象，不是教材推进。
    if re.search(r'下一步(?:推导|证明|计算|怎么做|如何|的思路)|'
                 r'继续(?:这个|刚才|上面|这一|该)(?:的)?(?:例子|证明|推导|题|内容)?|'
                 r'(?:继续|接着)(?:讲|解释|说)(?:这个|刚才|上面|这一)', text):
        return None
    for mode, pattern in [('chapter', r'(?:下(?:一|1)章|下一章节)'),
                          ('section', r'(?:下(?:一|1)节|下一个小节)'),
                          ('topic', r'(?:下一个?知识点|下一(?:个)?(?:知识点|主题)|下一个内容)')]:
        if re.search(pattern, text):
            return mode
    # “我懂了，下一部分/下一步/继续/接下来”是路径推进；无路径时由 resolve 澄清。
    if re.search(r'下一部分|下一步|接下来', text):
        return 'next'
    if re.fullmatch(r'(?:我懂了|明白了|懂了|好的|可以|嗯|行)?[，,。！？\s]*'
                    r'(?:继续|继续学习|继续学|接着学习|接着学|往下学|往下学习)[。！？\s]*', text):
        return 'next'
    # 章节中的具体内容提问仍交给普通识别；章节导学要求才走目录入口。
    chapter_match = re.search(r'第[一二三四五六七八九十零\d]+章', text)
    named = next((chapter['title'] for chapter in chapters() if chapter['title'] in text), None) if PSYCHOLOGY else None
    if re.search(r'学|带我|从头|开始|讲解|介绍', text) and (chapter_match or named):
        suffix = text.split(named, 1)[1] if named else text[chapter_match.end():]
        if re.fullmatch(r'(?:的|内容|全部|从头|开始|学习|讲解|吧|[，。！？])*', suffix):
            return 'start'
    return None


def previous_cursor(recent, memory, student_id):
    for row in reversed(recent):
        result = row['result']
        if result.get('answer_status') != 'answered':
            continue
        cursor = result.get('course_navigation')
        if cursor and row.get('epoch') == memory.repo.memory_epoch(student_id, row['knowledge_point']):
            return cursor
        # 已明确换到其他对象后，旧目录不能自动成为新对象的路径。
        return None
    return None


def _cursor(unit, *, mode, explained):
    return {key: value for key, value in unit.items() if key not in ('blocks', 'source', 'page')} | {
        'status': 'ready', 'mode': mode, 'path_kind': 'textbook_heading_order',
        'explained': explained, 'covered': False}


def _candidate(unit):
    return {key: unit.get(key) for key in
            ('id', 'title', 'chapter_id', 'section_id', 'chapter_title', 'section_title', 'position', 'version')}


def _flat(text):
    return ''.join(str(text or '').split())


def bind_result(result):
    """Bind an ordinary/selection answer to the real outline location it used.

    Returns ``None`` when the answer has no verifiable textbook reference, a
    ``ready`` cursor when one outline unit is identifiable, and a ``clarify``
    cursor when the answer spans locations or the location is not unique.
    """
    references = []
    selection = result.get('selection_ref')
    if isinstance(selection, dict):
        references.append(selection)
    for item in result.get('pdf_references') or []:
        if isinstance(item, dict) and isinstance(item.get('selection_ref'), dict):
            references.append(item['selection_ref'])
    references = [item for item in references
                  if item.get('chapter_id') and item.get('section_id')]
    if not references:
        return None
    pairs = {(int(item['chapter_id']), int(item['section_id'])) for item in references}
    units = outline()
    if len(pairs) > 1:
        candidates = [_candidate(unit) for unit in units
                      if (unit['chapter_id'], unit['section_id']) in pairs][:6]
        return {'status': 'clarify', 'mode': 'bind', 'path_kind': 'textbook_heading_order',
                'explained': True, 'reply': '这次回答涉及多个教材小节。请说明要从哪一节继续。',
                'candidates': candidates}
    pair = next(iter(pairs))
    section_units = [unit for unit in units
                     if (unit['chapter_id'], unit['section_id']) == pair]
    if not section_units:
        return None
    texts = [_flat(item.get('quote') or item.get('text') or '') for item in references]
    scored = []
    for unit in section_units:
        blocks = [_flat(block.get('text', '')) for block in unit.get('blocks', [])]
        score = sum(min(len(text), len(block)) for text in texts if text
                    for block in blocks if block and (text in block or block in text))
        scored.append((score, unit['position'], unit))
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    if len(scored) > 1 and scored[0][0] == scored[1][0] == 0:
        candidates = [_candidate(unit) for _, _, unit in scored[:6]]
        return {'status': 'clarify', 'mode': 'bind', 'path_kind': 'textbook_heading_order',
                'explained': True, 'reply': '这次回答对应的教材位置不唯一。请说明要从哪一部分继续。',
                'candidates': candidates}
    return _cursor(scored[0][2], mode='bind', explained=True)


def resolve(message, *, cursor=None, reader_location=None):
    mode = intent(message)
    if not PSYCHOLOGY or mode is None:
        return None
    if cursor and cursor.get('status') == 'clarify' and mode in ('next', 'topic', 'section', 'chapter'):
        return dict(cursor)
    units = outline()
    if mode == 'start':
        text = ''.join(message.split())
        match = re.search(r'第([一二三四五六七八九十零\d]+)章', text)
        chapter_id = _number(match[1]) if match else None
        if match and not any(u['chapter_id'] == chapter_id for u in units):
            return {'status': 'clarify', 'reply': '教材中没有这一章，请选择现有章节。'}
        if not match:
            matches = {u['chapter_id'] for u in units if u['chapter_title'] in text}
            if len(matches) == 1:
                chapter_id = matches.pop()
        candidates = [u for u in units if u['chapter_id'] == chapter_id]
        if not candidates:
            return {'status': 'clarify', 'reply': '请说明要学习的教材章号或完整章节名称。'}
        target = candidates[0]
    else:
        current = next((u for u in units if cursor and u['id'] == cursor.get('id')
                        and u['version'] == cursor.get('version')), None)
        if current is None and cursor is None and mode in ('section', 'chapter') and reader_location:
            current = next((u for u in units if u['chapter_id'] == reader_location.chapter_id
                            and u['section_id'] == reader_location.section_id), None)
        if current is None:
            return {'status': 'clarify', 'reply': '还没有可确认的学习路径和当前位置。请先说明章节或选择要学习的小节。'}
        candidates = [u for u in units if u['position'] > current['position']]
        if mode in ('topic', 'next'):
            # 本阶段路径为当前章的真实标题顺序；不推断跨章概念关系。
            candidates = [u for u in candidates if u['chapter_id'] == current['chapter_id']]
        elif mode == 'section':
            candidates = [u for u in candidates if (u['chapter_id'], u['section_id']) !=
                          (current['chapter_id'], current['section_id'])]
        else:
            candidates = [u for u in candidates if u['chapter_id'] != current['chapter_id']]
        if not candidates:
            return {'status': 'complete', 'reply': '当前范围已到末尾。可以复习本章，或明确选择下一章继续学习。'}
        target = candidates[0]
    return {key: value for key, value in target.items() if key not in ('blocks', 'source', 'page')} | {
        'status': 'ready', 'mode': mode, 'path_kind': 'textbook_heading_order', 'explained': False}


def validate(target):
    unit = next((u for u in outline() if u['id'] == target['id'] and u['version'] == target['version']), None)
    if unit is None:
        raise ValueError('教材目录或正文已更新，请重新选择章节')
    record = document_for_chapter(unit['chapter_id'])
    if hashlib.sha256(pdf_path(record).read_bytes()).hexdigest() != record['version']:
        raise ValueError('教材原件已变化，请重新建立页码索引')
    return unit


def read_target(target):
    unit = validate(target)
    blocks = unit['blocks']
    text = '\n'.join(b['text'] if b['kind'] != 'table' else '\n'.join(' | '.join(row) for row in b['rows'])
                     for b in blocks)[:6000]
    return [TextbookChunk(source=unit['source'], section=unit['section_title'],
        text=text, terms=terms_for(text), section_id=unit['section_id'], chapter_id=unit['chapter_id'],
        chunk_id='navigation:' + unit['id'], parent_id='navigation:' + unit['id'], page=unit['page'],
        block_start=blocks[0]['block_index'], block_end=blocks[-1]['block_index'],
        source_spans=source_spans(blocks, text))]
