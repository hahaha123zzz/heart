"""生成实验心理学课程占位资源（manifest/pdf_manifest/11章 document+pdf_locations/kc_registry）。"""
import json, hashlib
from pathlib import Path

COURSE = Path('knowledge/courses/experimental-psychology-3')
(COURSE / 'chapters').mkdir(parents=True, exist_ok=True)

CHAPTERS = [
    ('实验心理学概述', '实验心理学', ['实验法', '观察法', '相关法', '心理物理学', '冯特', '艾宾浩斯', '费希纳', '实验范式']),
    ('实验研究的基本问题', '实验研究', ['自变量', '因变量', '额外变量', '信度', '效度', '随机化', '操作定义', '实验效度']),
    ('实验中的变量控制', '变量控制', ['额外变量控制', '平衡方法', '拉丁方设计', '抵消平衡', '双盲程序', '安慰剂效应', '实验者效应', '要求特征']),
    ('被试间设计', '被试间设计', ['被试间设计', '随机分组', '匹配设计', '配对组设计', '组间设计', '个体差异', '被试数量', '处理组']),
    ('被试内设计', '被试内设计', ['被试内设计', '顺序效应', '练习效应', '疲劳效应', ' counterbalancing', 'ABBA设计', '组内设计', '个体差异控制']),
    ('混合设计', '混合设计', ['混合设计', '组间因素', '组内因素', '裂区设计', '准实验设计', '小样本设计', '单被试设计', '实验处理']),
    ('反应时', '反应时', ['反应时', '简单反应时', '选择反应时', '辨别反应时', '唐德斯减法', '加因素法', '速度准确性权衡', '开窗实验']),
    ('心理物理学方法', '心理物理学', ['感觉阈限', '最小可觉差', '极限法', '平均差误法', '恒定刺激法', '信号检测论', '辨别力指标', '信号ROC曲线']),
    ('知觉实验', '知觉实验', ['知觉恒常性', '大小知觉', '深度知觉', '运动知觉', '错觉', '吉布森视崖实验', '轮廓与图形组织', '知觉组织']),
    ('记忆实验', '记忆实验', ['记忆实验', '系列位置效应', '首因效应', '近因效应', '自由回忆', '再认', '内隐记忆', '加工深度']),
    ('情绪实验', '情绪实验', ['情绪研究方法', '主观报告', '情绪生理指标', '皮肤电反应', '情绪启动', '国际情绪图片系统', '面部表情', '情绪调节']),
]

CN_NUM = '一二三四五六七八九十'
def cn(n): return CN_NUM[n-1]

manifest_chapters, pdf_manifest = [], []
for idx, (title, keyword, terms) in enumerate(CHAPTERS, 1):
    sections_manifest, sections_locations = [], []
    blocks = []
    bi = 0
    for s in range(1, 9):
        if s == 1:
            head = f'一、{keyword}的含义'
            body = (f'什么是{keyword}？{keyword}是实验心理学研究的核心内容之一。'
                    f'{keyword}的研究采用科学的实验方法，通过操纵自变量、控制额外变量、测量因变量来揭示心理规律。'
                    f'研究者关心的主要问题是：{keyword}在什么条件下发生变化，其变化遵循怎样的规律。'
                    f'常见的相关概念包括：' + '、'.join(terms) + '。')
        elif s == 2:
            head = f'二、{keyword}的研究方法'
            body = (f'研究{keyword}主要采用实验法和测验法。实验研究者先提出假设，再通过操作定义把抽象概念转化为可测量指标，'
                    f'并保证测量的信度和效度。随机化分组与平衡设计是控制额外变量的基本手段，'
                    f'例如随机分组、匹配设计和抵消平衡。实验结果必须经过重复验证才具有说服力。')
        elif s == 3:
            head = f'三、{keyword}的经典实验'
            body = (f'关于{keyword}的经典实验包括多个著名研究范式。这些实验的共同特点是：操纵自变量、控制额外变量、'
                    f'客观记录因变量指标。例如在{terms[0]}的研究中，实验者将被试随机分配到不同处理组，'
                    f'比较各组在任务表现上的差异，从而推断因果关系。这类实验范式至今仍被广泛使用。')
        else:
            head = f'{cn(s) if s <= 10 else str(s)}、{keyword}的{["应用","测量","数据分析","影响因素","研究进展","争议"][s-4]}'
            body = (f'本节讨论{keyword}的进一步内容。{keyword}受多种因素影响，包括刺激特性、被试状态和实验情境。'
                    f'数据分析时要注意统计检验力与效应量，并区分显著性与实际意义。'
                    f'{terms[min(s-1, len(terms)-1)]}是本节的重要概念，{keyword}的应用也扩展到了教育、工程与人机交互领域。')
        sections_manifest.append({'id': s, 'title': f'{idx}.{s} {head.split("、",1)[1]}'})
        page = (idx-1)*32 + s*3
        sections_locations.append({'id': s, 'title': head, 'generated_page': page})
        blocks.append({'block_index': bi, 'section': head, 'section_id': s, 'kind': 'text', 'text': head, 'image_ids': []}); bi += 1
        blocks.append({'block_index': bi, 'section': head, 'section_id': s, 'kind': 'text', 'text': body, 'image_ids': []}); bi += 1
        blocks.append({'block_index': bi, 'section': head, 'section_id': s, 'kind': 'text',
                       'text': f'小结：{keyword}的概念、方法与经典实验是本章的重点。{terms[0]}与{terms[1]}常一起考查。'
                               f'理解{keyword}需要结合具体实验情境，避免机械记忆。', 'image_ids': []}); bi += 1
    manifest_chapters.append({'id': idx, 'title': title, 'sections': sections_manifest})
    pdf_manifest.append({'chapter_id': idx, 'title': title, 'sections': sections_locations})
    ch_dir = COURSE / 'chapters' / f'chapter_{idx:02d}'
    ch_dir.mkdir(parents=True, exist_ok=True)
    (ch_dir / 'document.json').write_text(json.dumps(
        {'chapter_id': idx, 'source': f'实验心理学（第3版）/第{idx}章 {title}', 'blocks': blocks}, ensure_ascii=False), encoding='utf-8')
    (ch_dir / 'pdf_locations.json').write_text(json.dumps(
        {'source': f'实验心理学（第3版）/第{idx}章 {title}', 'sections': sections_locations}, ensure_ascii=False), encoding='utf-8')

manifest = {'course_id': 'experimental-psychology-3', 'version': 'placeholder-v1', 'title': '实验心理学（第3版）',
            'chapters': manifest_chapters}
# 去掉 source.docx 引用（course_release 读取 source 可选字段）
(COURSE / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False), encoding='utf-8')
(COURSE / 'pdf_manifest.json').write_text(json.dumps(pdf_manifest, ensure_ascii=False), encoding='utf-8')
(COURSE / 'kc_registry.json').write_text(json.dumps(
    {'schema': 'kc-registry-v1', 'course_id': 'experimental-psychology-3', 'version': 'placeholder-v1',
     'sources': [], 'knowledge_components': [], 'relations': [], 'target_mappings': []}, ensure_ascii=False), encoding='utf-8')
print('chapters:', len(manifest_chapters), '| blocks ch1:', len(blocks))
