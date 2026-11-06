"""已核对的教材主题包；只匹配明确的一般概念讲解，不替换学生实验。"""
import hashlib
import json
import re
from pathlib import Path

from knowledge.course_config import PSYCHOLOGY, PSYCHOLOGY_DIR
from knowledge.pdf_reader import document_for_chapter
from knowledge.citation_locations import locate_source, section_reference
from knowledge.textbook import TextbookChunk

ROOT = Path(__file__).parent / 'presets'
TOPICS = {
    'variables': ('自变量', '因变量', '额外变量', '混淆变量'),
    'designs': ('被试间设计', '被试内设计', '混合设计'),
    'signal_detection': ('信号检测', '判准', '判断标准', '辨别力', '感受性', 'ROC', '击中率', '虚报率'),
    'spatial_cue': ('空间线索', '有效线索', '无效线索'),
}
LOCATIONS = {'variables': {(2, 2), (2, 3), (2, 4)}, 'designs': {(4, 1), (5, 1), (5, 5)},
             'signal_detection': {(7, 3)}, 'spatial_cue': {(9, 2)}}
# 主题匹配不再要求“每个字都在白名单里”；只拦明确不该用预制图的问法。
SIMPLE_DEF = re.compile(r'^(?:(?:什么是|何为)[^，。；;!?！？]{1,20}|'
                        r'[^，。；;!?！？]{1,20}(?:是什么|的含义|的定义))[？?]?$')
CUSTOM = re.compile(r'我的实验|我想设计|假设我|自定义|解释.{0,12}实验|'
                    r'SOA\s*=|\d+\s*毫秒|\d+\s*ms|'
                    r'用.{0,10}例子|举个.{0,10}例子|做饭例子')
NO_DIAGRAM = re.compile(r'不要图解|不用图解|无需图解|不要画图|不需要图|不要可视化|不用可视化')
PAGE_OR_FIGURE = re.compile(r'第\d+章第\d+页|第\d+页|教材图\d|图\d+[-－]\d+')


def match_topic(message, reply, sources, execution):
    targets = getattr(execution, 'targets', [])
    if getattr(execution, 'target_refs', []) and (not targets or any(
        target.get('kind') not in ('pdf_selection', 'section') for target in targets
    )):
        return None
    question = re.sub(r'(?:只讲解|只讲|先讲解|先讲|不(?:要|用|需要)(?:再)?出题|无需出题|别(?:再)?出题)', '', message)
    question = re.sub(r'[\s，。！？、；：,.!?;:]', '', question)
    if (SIMPLE_DEF.fullmatch(question)
            or CUSTOM.search(question)
            or NO_DIAGRAM.search(question)
            or PAGE_OR_FIGURE.search(question)):
        return None
    signal_overview = bool(re.search(r'信号检测|ROC', question, re.I) and
                           re.search(r'讲解|解释|理解|原理|关系|为什么|怎样|如何|怎么', question))
    matches = [name for name, terms in TOPICS.items()
               if sum(term.casefold() in question.casefold() and term.casefold() in reply.casefold()
                      for term in terms) >= (1 if name == 'spatial_cue' or name == 'signal_detection' and signal_overview else 2)]
    if len(matches) != 1:
        return None
    topic = matches[0]
    locations = LOCATIONS[topic]
    for target in targets:
        if target.get('kind') == 'section':
            section = re.fullmatch(r'section:(\d+):(\d+)', target.get('id', ''))
            if section is None or tuple(map(int, section.groups())) not in locations:
                return None
    for source in sources:
        if (source.chapter_id, source.section_id) not in locations:
            continue
        record = document_for_chapter(source.chapter_id)
        if record and Path(source.source).stem == Path(record['source']).stem:
            return topic
    return None


def build_preset(message, reply, sources, execution, *, turn_id):
    if not PSYCHOLOGY:
        return None
    topic = match_topic(message, reply, sources, execution)
    if topic is None:
        return None
    pack = json.loads((ROOT / (topic + '.json')).read_text(encoding='utf-8'))
    references = {}
    for key, anchor in pack['sources'].items():
        record = document_for_chapter(anchor['chapter_id'])
        if not record or record['version'] != anchor['pdf_version']:
            return None
        path = PSYCHOLOGY_DIR / 'chapters' / f"chapter_{anchor['chapter_id']:02d}" / 'document.json'
        blocks = json.loads(path.read_text(encoding='utf-8'))['blocks']
        block = next((b for b in blocks if b['block_index'] == anchor['block_index']), None)
        if not block or block['section_id'] != anchor['section_id'] or hashlib.sha256(
            block['text'].encode()).hexdigest() != anchor['text_sha256']:
            return None
        chunk = TextbookChunk(record['source'], block['section'], block['text'], frozenset(),
                              chapter_id=anchor['chapter_id'], section_id=anchor['section_id'],
                              block_start=anchor['block_index'])
        located = locate_source(chunk, allow_section=False)
        if not located:
            return None
        references[key] = (located['selection_ref'], block['section'])
    frames = []
    for frame in pack['frames']:
        if 'signal' in frame:
            from visualization.psychology_figures import signal_figure
            frame['signal'] = signal_figure(frame['signal'])
        reference, label = references[frame.pop('source')]
        frames.append(frame | {'selection_ref': reference, 'source_label': label,
                               'visual_origin': 'teaching_example'})
    reference = frames[0]['selection_ref']
    return {'schema_version': 2, 'id': hashlib.sha256((turn_id + pack['id'] + pack['version']).encode()).hexdigest()[:24],
            'title': pack['title'], 'origin': 'teaching_example', 'frames': frames,
            'chapter_id': reference['chapter_id'], 'section_id': reference['section_id'],
            'selection_ref': reference, 'source_label': frames[0]['source_label'],
            'generation': {'method': 'textbook-preset', 'preset_id': pack['id'],
                           'version': pack['version'], 'validation': 'pinned-text-and-pdf-anchors'}}


def _pinned_reference(anchor):
    record = document_for_chapter(anchor['chapter_id'])
    if not record or record['version'] != anchor['pdf_version']:
        return None
    path = PSYCHOLOGY_DIR / 'chapters' / f"chapter_{anchor['chapter_id']:02d}" / 'document.json'
    blocks = json.loads(path.read_text(encoding='utf-8'))['blocks']
    block = next((item for item in blocks if item['block_index'] == anchor['block_index']), None)
    if (not block or block['section_id'] != anchor['section_id']
            or hashlib.sha256(block['text'].encode()).hexdigest() != anchor['text_sha256']):
        return None
    chunk = TextbookChunk(record['source'], block['section'], block['text'], frozenset(),
                          chapter_id=anchor['chapter_id'], section_id=anchor['section_id'],
                          block_start=anchor['block_index'])
    located = locate_source(chunk, allow_section=False)
    if located:
        return located['selection_ref'], block['section'], 'paragraph_anchor', block['text']
    return (section_reference(anchor['chapter_id'], anchor['section_id']), block['section'],
            'section_heading', block['text'])


def _deck(turn_id, title, frames, references, *, method, version):
    first, label, _ = references[0][:3]
    return {'schema_version': 2,
            'id': hashlib.sha256((turn_id + method + version).encode()).hexdigest()[:24],
            'title': title, 'origin': 'textbook_example',
            'chapter_id': first['chapter_id'], 'section_id': first['section_id'],
            'selection_ref': first, 'source_label': label,
            'frames': frames,
            'generation': {'method': method, 'version': version,
                           'validation': 'pinned-text-and-pdf-anchors'}}


def build_method_selection_guide(message, sources, execution, *, turn_id):
    """为教材明示的观察、相关、实验方法比较提供固定且可追溯的图解。"""
    question = ''.join(message.split())
    if not all(term in question for term in ('观察法', '相关研究', '实验法')) or not sources:
        return None
    targets = getattr(execution, 'targets', [])
    if getattr(execution, 'target_refs', []) and (not targets or any(
        target.get('kind') not in ('pdf_selection', 'section') for target in targets
    )):
        return None
    if any(target.get('kind') == 'section' and target.get('id') not in {'section:1:1', 'section:3:1'}
           for target in targets):
        return None

    anchors = [
        {'chapter_id': 1, 'section_id': 1, 'block_index': 15,
         'pdf_version': '34f4dfc2dd1418397cbc35aa4a2c0b404a11102cf919287b6fd2bfa5be021c7e',
         'text_sha256': '0ac5056c2642a9c20c48718c257fe27e650358b2513e61a4aa202fcc209f4a6f'},
        {'chapter_id': 3, 'section_id': 1, 'block_index': 166,
         'pdf_version': '88df6987e161067aee4cdcb419e4b356467fa352dc88549eb168abbd17cd4089',
         'text_sha256': '17cc4c386ab774ecc4a59856970ba8b6a827ae49e0da097bc8a944f8cc6dfa91'},
        {'chapter_id': 3, 'section_id': 1, 'block_index': 171,
         'pdf_version': '88df6987e161067aee4cdcb419e4b356467fa352dc88549eb168abbd17cd4089',
         'text_sha256': '826c900dfc839849f4c2870c8431c3719f86430ed0b17135bdb950190ecdd6aa'},
        {'chapter_id': 3, 'section_id': 1, 'block_index': 168,
         'pdf_version': '88df6987e161067aee4cdcb419e4b356467fa352dc88549eb168abbd17cd4089',
         'text_sha256': '8f7f7e2b4e2db1f73183bc0c284bdf0cddd5d43c62f53670f950e63e2e620b2d'},
    ]
    references = [_pinned_reference(anchor) for anchor in anchors]
    if any(reference is None for reference in references):
        return None
    from visualization.templates import VisualPlan, render_plan
    plan = VisualPlan(template='design_matrix', title='观察、相关与实验：怎样选择？',
        source_index=0, evidence_quote=references[0][3][:300], origin='textbook_example',
        payload={'columns': ['方法', '适用情形', '结论边界'],
                 'rows': [
                     ['观察法', '系统描述自然发生的行为', '不干预；能记录自然情境，难以排除观察干扰'],
                     ['相关研究', '研究自然存在、难以操纵的变量关系', '可发现关联；单凭相关不能确定因果'],
                     ['实验法', '问题涉及因果，且可合乎伦理地操纵和控制变量', '操纵条件并控制其他条件，以检验因果假设']],
                 'steps': [
                     {'row': 0, 'columns': [0, 1], 'text': '先系统记录自然发生的行为，帮助描述现象、发现值得研究的变量。'},
                     {'row': 1, 'columns': [0, 2], 'text': '相关设计能说明变量共同变化，但不能单独证明其中一个变量造成另一个变量变化。'},
                     {'row': 1, 'columns': [0, 1], 'text': '若操纵变量会造成严重伤害，教材指出应选择相关研究，并遵守伦理边界。'},
                     {'row': 2, 'columns': [0, 2], 'text': '当研究要检验因果、关键条件可操纵且符合伦理时，用实验法分离变量作用。'}]})
    frames = render_plan(plan)
    anchor_indices = [0, 1, 2, 3]
    for index, (frame, anchor_index) in enumerate(zip(frames, anchor_indices)):
        reference, label, location, _ = references[anchor_index]
        frame.update(selection_ref=reference, source_label=label,
                     visual_origin='textbook_example', evidence_location=location)
    return _deck(turn_id, plan.title, frames, references, method='textbook-method-selection',
                 version='experimental-psychology-3:method-selection-v1')


def build_chapter_map_guide(message, sources, execution, *, turn_id):
    """从已发布课程目录生成章节知识树；目录顺序不解释成先修或因果。"""
    question = ''.join(message.split())
    match = re.search(r'第([一二三四五六七八九十\d]+)章', question)
    if not match and not re.search(r'第[一二三四五六七八九十\d]+[节小]', question):
        match = re.search(r'第([一二三四五六七八九十\d]+)(?:的)?'
                          r'(?:思维导图|导图|知识框架|框架图|结构图|章节框架|整章结构)', question)
    if not match or not re.search(r'梳理|整理|关系|框架|地图|结构|思维导图|导图', question) or not sources:
        return None
    number = match.group(1)
    chapter_id = int(number) if number.isdecimal() else '一二三四五六七八九十'.find(number) + 1
    if chapter_id < 1:
        return None
    from knowledge.course import get_chapter
    from knowledge.course_navigation import outline
    from visualization.drawio_render import attach_images
    from visualization.templates import structure
    chapter = get_chapter(chapter_id)
    if not chapter or not 1 <= len(chapter['sections']) <= 15:
        return None

    def label(value):
        value = ' '.join(str(value or '').split()) or '知识点'
        return value[:47] + '…' if len(value) > 48 else value

    units = [unit for unit in outline() if unit['chapter_id'] == chapter_id]
    by_section = {}
    for unit in units:
        by_section.setdefault(unit['section_id'], []).append(unit)

    references = [section_reference(chapter_id, section['id']) for section in chapter['sections']]
    root = f'chapter-{chapter_id}'
    sections = [{'id': f'section-{section["id"]}', 'label': label(section['title']),
                 'parent': root} for section in chapter['sections']]
    overview = structure({'nodes': [{'id': root, 'label': label(f'第{chapter_id}章 {chapter["title"]}'), 'parent': None}]
                          + sections,
                          'steps': [{'node': root, 'text': f'本章共{len(chapter["sections"])}节；'
                                                         '后续按节展开教材知识点。'}]}, tree=True)[0]
    overview.update(title=f'第{chapter_id}章总览', selection_ref=references[0],
                    source_label=chapter['sections'][0]['title'],
                    visual_origin='textbook_example', evidence_location='section_heading')
    frames = [overview]

    for section, reference in zip(chapter['sections'], references):
        points = by_section.get(section['id'], [])
        chunks = [points[i:i + 14] for i in range(0, len(points), 14)] or [[]]
        for part, chunk in enumerate(chunks, 1):
            nodes = [{'id': root, 'label': label(f'第{chapter_id}章 {chapter["title"]}'), 'parent': None},
                     {'id': f'section-{section["id"]}', 'label': label(section['title']), 'parent': root}]
            nodes += [{'id': f'point-{i}', 'label': label(unit['title']),
                       'parent': f'section-{section["id"]}'} for i, unit in enumerate(chunk, 1)]
            suffix = f'（{part}/{len(chunks)}）' if len(chunks) > 1 else ''
            frame = structure({'nodes': nodes, 'steps': [{
                'node': f'section-{section["id"]}',
                'text': f'本节共{len(points)}个知识点；图中是本组{len(chunk)}个。'}]}, tree=True)[0]
            frame.update(title=f'{section["title"]}{suffix}', selection_ref=reference,
                         source_label=section['title'], visual_origin='textbook_example',
                         evidence_location='section_heading')
            frames.append(frame)

    attach_images(frames)
    return _deck(turn_id, f'第{chapter_id}章知识结构', frames,
                 [(references[0], chapter['sections'][0]['title'], 'section_heading')],
                 method='textbook-outline-map', version=f'{chapter_id}:{chapter["title"]}:{len(units)}')
