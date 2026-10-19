"""已核对的教材主题包；只匹配明确的一般概念讲解，不替换学生实验。"""
import hashlib
import json
import re
from pathlib import Path

from knowledge.course_config import PSYCHOLOGY, PSYCHOLOGY_DIR
from knowledge.pdf_reader import document_for_chapter
from knowledge.citation_locations import locate_source
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
# shortcut: 首批只匹配这些一般概念问法，其他表达回退按需生成，积累真实漏配后扩展。
GENERAL = re.compile(r'信号检测论|信号检测|判断标准|判准|辨别力|感受性|ROC|击中率|虚报率|'
                     r'视觉空间线索|空间线索|无效线索|有效线索|线索有效性|范式|条件|'
                     r'曲线|原理|含义|以及|中|里|变化|改变|一起|之间|关系|这|对|它|被试间|被试内|混合|设计|自变量|因变量|额外变量|混淆变量|'
                     r'图解|示意图|请|帮我|给我|结合|根据|教材|课本|这里|这段|内容|用|通俗|简单|详细|直观|'
                     r'说明|解释|介绍|讲解|讲讲|理解|比较|区分|区别|不同|什么|怎么|如何|怎样|'
                     r'为什么|干扰|影响|结论|实验|举例|例子|和|与|及|并|有|是|的|一下|分别|各自|会|能', re.I)


def match_topic(message, reply, sources, execution):
    targets = getattr(execution, 'targets', [])
    if getattr(execution, 'target_refs', []) and (not targets or any(
        target.get('kind') not in ('pdf_selection', 'section') for target in targets
    )):
        return None
    question = re.sub(r'[\s，。！？、；：,.!?;:]', '', message)
    if GENERAL.sub('', question):
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
