"""按需渲染目录：AI提供本题数据，固定代码计算与绘制步骤。"""
import itertools
from pydantic import BaseModel, ConfigDict, Field
from models.visualization import GraphSpec
from models.relation import RelationSpec
from visualization.euler_guide import euler_frames
from visualization.textbook_guides import closure_frames, relation_frame
from visualization.relation_validator import evaluate_relation
from knowledge.course_config import PSYCHOLOGY

CATALOG = {
    'euler': ('finite-structures', '无向简单图的欧拉判定', '{nodes:[{id:"v1",label:"v1"}],edges:[{source:"v1",target:"v2"}]}'),
    'relation': ('finite-structures', '三元素关系性质或闭包', '{pairs:[{source:"a",target:"b"}],kind:"transitive",mode:"closure"或"property"}；元素固定a,b,c'),
    'truth_table': ('finite-structures', '双变量基本逻辑真值表', '{operator:"and"或"or"或"implies"或"iff",p_label:"p的含义",q_label:"q的含义"}'),
    'sets': ('finite-structures', '有限集合运算与元素归属', '{universe:["1","2","3"],a:["1","2"],b:["2"],operation:"union"或"intersection"或"difference"或"complement"}'),
    'mapping': ('finite-structures', '有限函数的映射、单射和满射', '{domain:["a","b"],codomain:["1","2"],pairs:[["a","1"],["b","2"]]}'),
    'tree': ('reasoning-diagrams', '计数分支、归纳结构、树形解释', '{nodes:[{id:"n1",label:"起点",parent:null}],steps:[{node:"n1",text:"解释"}]}；必须是有根树'),
    'formula': ('reasoning-diagrams', '公式逐步推导与规则说明', '{steps:[{before:"LaTeX原式",after:"LaTeX结果",rule:"本步规则"}]}'),
    'flow': ('reasoning-diagrams', '证明、知识联系、方法判定流程', '{nodes:[{id:"n1",label:"前提"}],edges:[{source:"n1",target:"n2",label:"依据"}],steps:[{node:"n1",text:"解释"}]}'),
}
if PSYCHOLOGY:
    CATALOG={
        'experiment_flow':('experimental-design','实验程序、被试分组和变量控制流程','{nodes:[{id:"n1",label:"确定变量"}],edges:[{source:"n1",target:"n2",label:"下一步"}],steps:[{node:"n1",text:"解释本步"}]}'),
        'variable_map':('experimental-design','自变量、因变量、额外变量的角色与控制关系','{nodes:[{id:"iv",label:"自变量：操纵条件"}],edges:[{source:"iv",target:"dv",label:"拟检验的影响，不等于已证明因果"}],steps:[{node:"iv",text:"说明变量角色"}]}'),
        'design_matrix':('experimental-design','实验条件、被试分组或区组分配的矩阵','{columns:["区组","条件A","条件B"],rows:[["区组1","被试1","被试2"]],steps:[{row:0,columns:[1,2],text:"不同被试分别接受不同水平"}]}'),
    }


class VisualPlan(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    template: str = Field(max_length=30)
    title: str = Field(min_length=1, max_length=80)
    source_index: int = Field(ge=0)
    evidence_quote: str = Field(min_length=4, max_length=300)
    origin: str = Field(pattern='^(textbook_example|user_example|teaching_example)$')
    payload: dict


def text(value, limit=160):
    if not isinstance(value, str) or not value.strip() or len(value)>limit:
        raise ValueError('文字为空或超过长度限制')
    return value


def strings(value, maximum=16):
    if not isinstance(value,list) or not 1<=len(value)<=maximum:
        raise ValueError('元素列表为空或超出范围')
    result=[text(x,30) for x in value]
    if len(set(result))!=len(result):raise ValueError('元素重复')
    return result


def keys(value, allowed):
    if not isinstance(value,dict) or set(value)!=set(allowed):
        raise ValueError('字段应为：'+','.join(allowed))


def structure(payload, tree=False):
    keys(payload, ['nodes','steps'] if tree else ['nodes','edges','steps'])
    nodes=payload['nodes']; steps=payload['steps']
    if not isinstance(nodes,list) or not 1<=len(nodes)<=16:raise ValueError('节点应为1至16个')
    ids=[]; clean=[]; edges=[]
    for n in nodes:
        keys(n,['id','label','parent'] if tree else ['id','label'])
        ident=text(n['id'],24); ids.append(ident); clean.append({'id':ident,'label':text(n['label'],48)})
    if len(set(ids))!=len(ids):raise ValueError('节点ID重复')
    raw=[{'source':n['parent'],'target':n['id'],'label':''} for n in nodes if n['parent'] is not None] if tree else payload['edges']
    if not isinstance(raw,list) or len(raw)>30:raise ValueError('边数超过30')
    for i,e in enumerate(raw):
        keys(e,['source','target','label'])
        if e['source'] not in ids or e['target'] not in ids:raise ValueError('边引用未知节点')
        edges.append(dict(e,id='edge-'+str(i),annotation=text(e['label'],80) if e['label'] else ''))
    import networkx as nx
    graph=nx.DiGraph();graph.add_nodes_from(ids);graph.add_edges_from((e['source'],e['target']) for e in edges)
    if tree and (len([n for n in nodes if n['parent'] is None])!=1 or not nx.is_arborescence(graph)):
        raise ValueError('树必须有唯一根节点且全部节点可达，无循环')
    if not isinstance(steps,list) or not 1<=len(steps)<=16:raise ValueError('步骤应为1至16个')
    picture={'directed':True,'nodes':clean,'edges':edges,'layout':'tree' if tree else 'flow',
             'edge_annotations':{e['id']:e['annotation'] for e in edges if e['annotation']}}
    frames=[]
    for s in steps:
        keys(s,['node','text'])
        if s['node'] not in ids:raise ValueError('步骤引用未知节点')
        frames.append({'title':next(n['label'] for n in clean if n['id']==s['node']), 'text':text(s['text'],500),
                       'graph':picture|{'focus_nodes':[s['node']],'focus':[e['id'] for e in edges if e['target']==s['node']]}})
    return frames


def render_plan(plan):
    p=plan.payload; name=plan.template
    if name not in CATALOG:raise ValueError('模板不属于当前教材')
    if name in {'experiment_flow','variable_map'}:return structure(p)
    if name=='design_matrix':
        keys(p,['columns','rows','steps']);columns=strings(p['columns'],8);rows=p['rows'];steps=p['steps']
        if not isinstance(rows,list) or not 1<=len(rows)<=12:raise ValueError('矩阵须为1至12行')
        for row in rows:
            if not isinstance(row,list) or len(row)!=len(columns):raise ValueError('矩阵列数不一致')
            for cell in row:text(cell,100)
        if not isinstance(steps,list) or not 1<=len(steps)<=16:raise ValueError('矩阵步骤须为1至16步')
        frames=[]
        for step in steps:
            keys(step,['row','columns','text']);index=step['row'];focus=step['columns']
            if type(index) is not int or not 0<=index<len(rows):raise ValueError('矩阵行索引无效')
            if not isinstance(focus,list) or not focus or any(type(i) is not int or not 0<=i<len(columns) for i in focus):raise ValueError('矩阵列索引无效')
            frames.append({'title':'查看'+rows[index][0],'text':text(step['text'],500),
                'table':{'columns':columns,'rows':rows,'active_row':index,'focus_columns':focus}})
        return frames
    if name=='euler':return euler_frames(GraphSpec.model_validate(p))
    if name=='relation':
        keys(p,['pairs','kind','mode']); spec=RelationSpec(pairs=p['pairs'])
        if p['kind'] not in {'reflexive','irreflexive','symmetric','antisymmetric','transitive'}:raise ValueError('关系性质无效')
        if p['mode']=='closure':return closure_frames(spec,[p['kind']],dict(zip('abc','abc')))
        if p['mode']!='property':raise ValueError('关系mode无效')
        result=evaluate_relation(spec); w=result['witnesses'][p['kind']]; pairs=spec.model_dump()['pairs']
        present=[{'source':a,'target':b} for a,b in w['present']] if w else pairs
        missing=[{'source':a,'target':b} for a,b in w['missing']] if w else []
        return [relation_frame('先看原关系','箭头表示本题的序偶。',pairs),
            relation_frame('核对 '+p['kind'],'不满足所选性质；红色虚线仅表示缺少，未加入原关系。' if w else '完整检查有限论域，满足所选性质。',pairs,focus=present,missing=missing,focus_nodes='abc',warning=bool(w))]
    if name=='truth_table':
        keys(p,['operator','p_label','q_label']);text(p['p_label']);text(p['q_label'])
        operations={'and':('∧',lambda a,b:a and b),'or':('∨',lambda a,b:a or b),'implies':('→',lambda a,b:not a or b),'iff':('↔',lambda a,b:a==b)}
        if p['operator'] not in operations:raise ValueError('逻辑运算不支持')
        symbol,calculate=operations[p['operator']]; rows=[['真' if a else '假','真' if b else '假','真' if calculate(a,b) else '假'] for a,b in itertools.product([True,False],repeat=2)]
        frames=[]
        for i,row in enumerate(rows):
            for reveal in (False,True):
                shown=[[a,b,r if j<i or (j==i and reveal) else '待检查'] for j,(a,b,r) in enumerate(rows)]
                frames.append({'title':'第 '+str(i+1)+' 行：'+('结果' if reveal else '条件'),
                    'text':p['p_label']+' 为'+row[0]+'；'+p['q_label']+' 为'+row[1]+('。本行结果为'+row[2]+'。' if reveal else '。先核对条件。'),
                    'table':{'columns':['p','q','p'+symbol+'q'],'rows':shown,'active_row':i,'focus_columns':[2] if reveal else [0,1], 'warning_row':i if reveal and row[2]=='假' else -1}})
        return frames
    if name=='sets':
        keys(p,['universe','a','b','operation']); universe=strings(p['universe'])
        def subset(raw):
            if not isinstance(raw,list):raise ValueError('集合必须使用元素数组')
            values=strings(raw) if raw else []
            if not set(values)<=set(universe):raise ValueError('集合元素不属于论域')
            return set(values)
        a,b=subset(p['a']),subset(p['b']);op=p['operation']
        if op not in {'union','intersection','difference','complement'}:raise ValueError('集合运算无效')
        selected={'union':a|b,'intersection':a&b,'difference':a-b,'complement':set(universe)-a}[op]
        picture={'universe':universe,'a':list(a),'b':list(b),'selected':[]}
        frames=[{'title':'看清集合条件','text':'U是固定论域；A、B中的元素来自本题。','sets':picture}]
        for member in universe:
            frames.append({'title':'检查元素 '+member,'text':member+(' 属于' if member in a else ' 不属于')+' A，'+('属于' if member in b else '不属于')+' B；'+('保留在结果中。' if member in selected else '不进入结果。'),
                'sets':picture|{'focus':member,'selected':[member] if member in selected else []}})
        frames.append({'title':'集合运算的结果','text':'结果 = {'+'，'.join(m for m in universe if m in selected)+'}。','sets':picture|{'selected':[m for m in universe if m in selected]}})
        return frames
    if name=='mapping':
        keys(p,['domain','codomain','pairs']);domain=strings(p['domain']);codomain=strings(p['codomain']);pairs=p['pairs']
        if not isinstance(pairs,list) or len(pairs)!=len(domain):raise ValueError('函数须为每个定义域元素给出一个映射')
        for pair in pairs:
            if not isinstance(pair,list) or len(pair)!=2 or pair[0] not in domain or pair[1] not in codomain:raise ValueError('映射端点无效')
        if len({a for a,b in pairs})!=len(domain):raise ValueError('定义域元素须恰有一个像')
        nodes=[{'id':'d'+str(i),'label':x,'column':0} for i,x in enumerate(domain)]+[{'id':'c'+str(i),'label':x,'column':1} for i,x in enumerate(codomain)]
        edges=[{'id':'map'+str(i),'source':'d'+str(domain.index(a)),'target':'c'+str(codomain.index(b))} for i,(a,b) in enumerate(pairs)]
        picture={'directed':True,'layout':'mapping','nodes':nodes,'edges':edges}
        frames=[{'title':'先看定义域与陪域','text':'左侧是定义域，右侧是陪域，每个输入只有一个像。','graph':picture}]
        for i,(a,b) in enumerate(pairs):frames.append({'title':a+' 的像','text':a+' → '+b,'graph':picture|{'focus':['map'+str(i)],'focus_nodes':[edges[i]['source'],edges[i]['target']]}})
        injective=len({b for a,b in pairs})==len(domain);surjective=set(b for a,b in pairs)==set(codomain)
        frames.append({'title':'检查单射与满射','text':('单射：不同输入的像不重复。' if injective else '不是单射：有不同输入映到相同输出。')+('满射：陪域中每个元素都有原像。' if surjective else '不是满射：陪域中有元素没有原像。'),
            'graph':picture|{'warning_nodes':['c'+str(i) for i,x in enumerate(codomain) if sum(b==x for a,b in pairs)!=1]},
            'badges':[{'text':'单射' if injective else '非单射','tone':'good' if injective else 'warning'},{'text':'满射' if surjective else '非满射','tone':'good' if surjective else 'warning'}]})
        return frames
    if name in {'tree','flow'}:return structure(p,tree=name=='tree')
    if name=='formula':
        keys(p,['steps']);steps=p['steps']
        if not isinstance(steps,list) or not 1<=len(steps)<=12:raise ValueError('公式步骤须为1至12步')
        frames=[]
        for i,s in enumerate(steps):
            keys(s,['before','after','rule'])
            frames.append({'title':'推导第 '+str(i+1)+' 步','text':text(s['rule'],400),'formula':{'before':text(s['before'],1000),'after':text(s['after'],1000)}})
        return frames
    raise ValueError('模板不存在')
