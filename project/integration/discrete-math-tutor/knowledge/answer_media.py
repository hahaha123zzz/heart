"""复用 Q2 原图映射；模型图片是临时消息，记录只保存资源身份。"""
import os
import re

from knowledge.figures import get_figure, retrieve_figures


def selected_media(query, sources, *, asset_id=None):
    from knowledge.lightrag.retrieval import as_textbook_chunk
    chunks = [as_textbook_chunk(s) for s in sources if s.get('location', {}).get('source')]
    if asset_id:
        figure = get_figure(asset_id)
        # 工具参数偶尔返回图号而非资源 ID，只允许从当前原文匹配同名登记原图。
        figures = [figure] if figure else [f for f in retrieve_figures(asset_id, chunks) if f.label == asset_id]
        if not figures:
            raise ValueError('指定的教材原图 ID/图号无效，不能声称已读取像素。')
    else:
        figures = retrieve_figures(query, chunks)
    figures = [f for f in figures if f is not None and f.is_valid()]
    # 同号多来源需要澄清，不能无声选择其中一幅。
    if re.search(r'(?:图|表)\s*\d+[.．-]\d+', query) and len({f.label for f in figures}) < len(figures):
        return []
    output = []
    for figure in figures[:2]:
        source = next((s for s in sources if (s.get('chapter_id'), s.get('section_id')) ==
                       (figure.chapter_id, figure.section_id)), None)
        if source is None:
            continue
        item = figure.public()
        if source.get('document_id') != item.get('document_id') or source.get('version') != item.get('version'):
            continue
        item['model_saw_pixels'] = False
        from urllib.parse import quote
        item['image_url'] += f"?sha256={item['sha256']}&version={item['version']}&document_id={quote(item['document_id'], safe='')}"
        item['selection_ref'] = {'document_id': item['document_id'], 'version': item['version'],
            'chapter_id': figure.chapter_id, 'section_id': figure.section_id,
            'kind': 'text', 'rects': [], 'text': source.get('quote') or source['text'],
            'location_status': 'section'}
        output.append(item)
    return output


def current_media(refs):
    output = []
    for ref in refs:
        figure = get_figure(str(ref.get('id') or ''))
        if (figure and figure.is_valid() and figure.sha256 == ref.get('sha256')
                and figure.public().get('version') == ref.get('version')
                and figure.public().get('document_id') == ref.get('document_id')):
            output.append((ref, figure))
    return output[:2]


def model_message(refs):
    if os.getenv('LLM_VISION_ENABLED', '1') == '0':
        return None
    from llm.client import LLMClient
    verified = current_media(refs)
    if not verified:
        return None
    text = '以下是本轮真实教材原图，仅按可见像素解读；pending不是教师审核。正文按需使用 ![图题](media:资源ID)，不得编图片地址。\n'
    text += '\n'.join(f"{ref['id']}：{ref.get('label', '')}（{ref.get('review_status', 'pending')}）" for ref, _ in verified)
    message = LLMClient._with_images([{'role': 'user', 'content': text}],
                                    [figure.path for _, figure in verified])[0]
    message['_media_ids'] = [ref['id'] for ref, _ in verified]
    return message
