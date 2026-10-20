"""从原件标题层级选择教材目标；编号段落不自动成为知识点。"""
from functools import lru_cache
import re
import xml.etree.ElementTree as ET
import zipfile

from knowledge.psychology_retrieval import HEADING

SCHEMA = 'word-heading-targets-v1'
W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'


@lru_cache(maxsize=24)
def word_headings(path, version):
    """version 由调用方的实际原件哈希绑定；只解析，不写回 DOCX。"""
    with zipfile.ZipFile(path) as archive:
        body = ET.fromstring(archive.read('word/document.xml')).find(W + 'body')
        styles = ET.fromstring(archive.read('word/styles.xml')) if 'word/styles.xml' in archive.namelist() else []
    style_map = {item.get(W + 'styleId'): item for item in styles}

    def level(properties, seen=()):
        if properties is None:
            return None
        value = properties.find(W + 'outlineLvl')
        if value is not None:
            return int(value.get(W + 'val'))
        style = properties.find(W + 'pStyle')
        key = style.get(W + 'val') if style is not None else None
        if key in style_map and key not in seen:
            node = style_map[key]
            parent = node.find(W + 'basedOn')
            inherited = level(node.find(W + 'pPr'), seen + (key,))
            if inherited is not None:
                return inherited
            if parent is not None:
                proxy = ET.Element(W + 'pPr')
                ET.SubElement(proxy, W + 'pStyle', {W + 'val': parent.get(W + 'val')})
                return level(proxy, seen + (key,))
        return None

    return {index: {'level': value, 'text': ''.join(part.text or '' for part in node.iter(W + 't'))}
            for index, node in enumerate(body)
            if (value := level(node.find(W + 'pPr'))) is not None and value < 9}


def extract_targets(blocks, headings, section_title):
    """返回有实际块范围的目标和全部编号标题的分类审计。"""
    nodes = []
    audit = []
    for index, block in enumerate(blocks):
        text = block['text'].strip()
        if not HEADING.match(text):
            continue
        title = HEADING.sub('', text).strip()
        original = headings.get(block['block_index'])
        reason = None
        if not original:
            reason = 'numbered_body'  # 实验步骤、拓展阅读或引用材料中的编号。
        elif ''.join(original['text'].split()) != ''.join(text.split()):
            reason = 'source_alignment_mismatch'
        elif len(title) > 65 or re.search(r'[。；;]|\(略\)|（略）', title):
            reason = 'descriptive_sentence'
        elif re.search(r'教材|本书|本章', title):
            reason = 'course_introduction'
        row = {'block_index': block['block_index'], 'source_title': text, 'title': title,
               'classification': reason or 'heading', 'review_required': bool(reason), 'index': index}
        audit.append(row)
        if original:
            nodes.append(row | {'level': original['level']})

    targets = []
    for position, node in enumerate(nodes):
        end = next((other['index'] for other in nodes[position + 1:] if other['level'] <= node['level']), len(blocks))
        ancestors = [other for other in nodes[:position] if other['index'] < node['index']
                     and other['level'] < node['level'] and not any(
                         following['level'] <= other['level'] for following in nodes
                         if other['index'] < following['index'] < node['index'])]
        blocked = any(parent['classification'] in ('course_introduction', 'descriptive_sentence') for parent in ancestors)
        children = [child for child in nodes[position + 1:] if child['index'] < end]
        if node['classification'] != 'heading' or blocked:
            if blocked:
                next(row for row in audit if row['index'] == node['index'])['classification'] = 'introduction_child'
            continue
        if any(child['classification'] == 'heading' for child in children):
            continue
        group = blocks[node['index']:end]
        aside = next((i for i, block in enumerate(group[1:], 1) if block['text'].strip() in
                      ('拓展阅读', '推荐阅读', '本章重点', '概念术语')), len(group))
        group = group[:aside]
        if not any(block['kind'] == 'table' or len(block['text'].strip()) > 12 for block in group[1:]):
            next(row for row in audit if row['index'] == node['index']).update(
                classification='heading_without_body', review_required=True)
            continue
        title = node['title']
        if len(title) <= 3 or title in ('实验方法', '实验程序', '实验材料与仪器', '结果分析与讨论'):
            title = (ancestors[-1]['title'] if ancestors else section_title) + '：' + title
        targets.append({'title': title, 'index': node['index'], 'blocks': group,
                        'source_title': node['source_title'], 'parent_titles': [parent['title'] for parent in ancestors]})
        next(row for row in audit if row['index'] == node['index'])['classification'] = 'teaching_target'
    return targets, [{key: value for key, value in row.items() if key != 'index'} for row in audit]
