"""三个上游技能的宿主适配：只生成数据，复用已有图解和证据发布。"""
import re

GRAPH = '{nodes:[{id:"n1",label:"概念"},{id:"n2",label:"概念二"}],edges:[{source:"n1",target:"n2",label:"关系性质"}],steps:[{node:"n1",text:"本步解释"},{node:"n2",text:"解释联系"}]}'
CATALOG = {
    'drawio_relation': ('drawio', '可编辑的章节关系图、概念图或流程图；每条连线说明关系，不把顺序视为因果', GRAPH),
    'visual_explainer': ('visual-explainer', '逐步展开的图文解释；每幅图有解释其含义的说明', GRAPH),
    'interactive_educator': ('interactive-educator', '困惑→探索→概念→挑战，选择不同情境查看画面和反馈；不是正式测评',
        '{nodes:[{id:"n1",label:"概念"},{id:"n2",label:"实例"}],edges:[{source:"n1",target:"n2",label:"例示，非因果"}],puzzle:{prompt:"直觉问题",options:[{label:"情境A",node:"n1",feedback:"情境A的具体现象"},{label:"情境B",node:"n2",feedback:"情境B的不同现象"}]},explore:{prompt:"比较什么",options:[同上]},concept:{title:"核心概念",text:"解释刚才现象的关键联系"},challenge:{prompt:"换一个情境",graph:{nodes:[{id:"c1",label:"新情境对象一"},{id:"c2",label:"新情境对象二"}],edges:[]},options:[{label:"新情境一",node:"c1",feedback:"解释"},{label:"新情境二",node:"c2",feedback:"解释"}]}}；edges只使用source/target/label，不能使用from/to。每阶段可附graph覆盖原图，换情境必须同时换图和options.node。options必须是2至4项真实JSON对象，不能写“同上”。'),
}


def declined(message):
    return bool(re.search(r'只(?:要|用|需)(?:纯)?文字|(?:不要|不用|无需|别)(?:任何|再|生成|画|做)*(?:图解|关系图|概念图|流程图|思维导图|图片|图表|图|可视化)', message))


def requested_skill(message):
    """只对明确的可视化请求启用；通用自动补图仍由原开关控制。"""
    message = message.lower()
    if declined(message):
        return None
    message = re.sub(r'(?:不要|不用|无需|别)(?:再|给我|生成|画|做|使用|用)*[^。！？；，,;!?]{0,30}(?:图解|关系图|概念图|流程图|思维导图|drawio|draw\.io|visual[ -]explainer|交互课程|交互式讲解|交互式课程|interactive[ -]educator)', '', message)
    if re.search(r'/aha\b|/3b1b\b|interactive[ -]educator|交互式(?:讲解|课程)|交互课程', message):
        return 'interactive_educator'
    if re.search(r'可视化|visuali[sz]ation|visual[ -]explainer|分步图文|图文讲解|(?:用|做|生成|画|给|展示|看看|查看).{0,12}(?:图解)', message):
        return 'visual_explainer'
    if re.search(r'draw\.?io|(?:画|做|生成|给|展示|看看|查看).{0,20}(?:关系图|概念图|流程图|思维导图)', message):
        return 'drawio_relation'
    return None


def enabled_for(message):
    import os
    return not declined(message) and (os.getenv('VISUALIZATION_ON_DEMAND', '0') == '1' or requested_skill(message) is not None)


def render(name, payload):
    from visualization.templates import structure, keys, text
    if name != 'interactive_educator':
        frames = structure(payload)
    else:
        keys(payload, ['nodes', 'edges', 'puzzle', 'explore', 'concept', 'challenge'])
        nodes = payload['nodes']
        if not isinstance(nodes, list) or not nodes:
            raise ValueError('交互课程缺少概念节点')
        picture = structure({'nodes': nodes, 'edges': payload['edges'],
                             'steps': [{'node': nodes[0]['id'], 'text': '探索概念'}]})[0]['graph']
        frames = []
        for stage, title in [('puzzle', '先想一想'), ('explore', '动手探索'),
                             ('concept', '发现概念'), ('challenge', '迁移挑战')]:
            data = payload[stage]
            stage_picture = picture
            if isinstance(data, dict) and 'graph' in data:
                keys(data['graph'], ['nodes', 'edges'])
                stage_nodes = data['graph']['nodes']
                if not isinstance(stage_nodes, list) or not stage_nodes:
                    raise ValueError('阶段图缺少概念节点')
                stage_picture = structure(data['graph'] | {'steps': [
                    {'node': stage_nodes[0]['id'], 'text': '比较当前情境'}]})[0]['graph']
            fields = ['graph'] if isinstance(data, dict) and 'graph' in data else []
            if stage == 'concept':
                keys(data, ['title', 'text', *fields])
                frames.append({'title': text(data['title'], 80), 'text': text(data['text'], 500), 'graph': stage_picture})
                continue
            keys(data, ['prompt', 'options', *fields])
            options = data['options']
            if not isinstance(options, list) or not 2 <= len(options) <= 4:
                raise ValueError('每个探索阶段需要2至4个情境')
            clean = []
            for option in options:
                keys(option, ['label', 'node', 'feedback'])
                if option['node'] not in {n['id'] for n in stage_picture['nodes']}:
                    raise ValueError('交互情境引用未知概念')
                clean.append({'label': text(option['label'], 80), 'node': option['node'],
                              'feedback': text(option['feedback'], 500)})
            if len({o['label'] for o in clean}) != len(clean):
                raise ValueError('交互情境不得重复')
            frames.append({'title': title, 'text': text(data['prompt'], 500), 'graph': stage_picture,
                           'interaction': {'options': clean}})
    for frame in frames:
        frame['learning_skill'] = CATALOG[name][0]
    return frames
