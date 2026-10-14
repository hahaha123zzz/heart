"""教材绑定的只读步骤卡片；审核素材与数学计算决定画面。"""
import hashlib,re,unicodedata
from pathlib import Path
from knowledge.proof_units import units_for
from knowledge.pdf_reader import PDFSelection,resolve_selection
from models.relation import RelationSpec
from models.visualization import GraphSpec
from visualization.relation_closure import build_closure
from visualization.relation_validator import template_spec,evaluate_relation
from visualization.euler_guide import euler_frames

VERSIONS={9:'d8a1946a9a3b0a69f987e8ca1cf8f991aec33bf1a9afbfa2d82e9b5ce0d39fc1',
    4:'1f2163e36ef3b3fce40a5c267e192ccbe92b118b95b2bcf1324ecd134bc3e9ab',
    7:'f19cfaef9be00fc45e0285660618530f6305ec7b45a7e00d31f28e31452af2f1'}
NAMES={'reflexive':'自反','irreflexive':'反自反','symmetric':'对称','antisymmetric':'反对称','transitive':'传递'}


def relation_frame(title,text,pairs,labels=None,added=(),focus=(),missing=(),focus_nodes=(),warning=False):
    return {'title':title,'text':text,'graph':{'directed':True,'nodes':[{'id':a,'label':(labels or {}).get(a,a)} for a in 'abc'],
        'edges':[dict(p,id=p['source']+p['target']) for p in pairs],
        'added':[p['source']+p['target'] for p in added],'focus':[p['source']+p['target'] for p in focus],
        'focus_nodes':list(focus_nodes),'warning_nodes':list(focus_nodes) if warning else [],
        'missing_edges':[dict(p,id='missing-'+p['source']+p['target']) for p in missing]}}


def closure_frames(spec,kinds,labels):
    original=spec.model_dump()['pairs'];frames=[relation_frame('先看原关系','箭头表示原题给出的序偶。后续只加入目标性质必需的边。',original,labels)]
    translate=lambda text:text.translate(str.maketrans(labels))
    for kind in kinds:
        result=build_closure(spec,kind);added=[]
        for step in result['steps']:
            node=step['added_pair']['source']
            frames.append(relation_frame(result['label']+'：先检查条件',translate(step['reason'])+' 红色虚线是目前缺少的关系，不属于当前关系。',step['before_pairs'],labels,added,step['premises'],[step['added_pair']],
                focus_nodes=[node] if kind=='reflexive' else sorted({p[k] for p in step['premises'] for k in ('source','target')})))
            frames[-1]['badges']=[{'text':'橙色：推导依据','tone':'neutral'},{'text':'红色虚线：缺少，尚未加入','tone':'warning'}]
            added.append(step['added_pair'])
            frames.append(relation_frame(result['label']+'：补入一条边',translate(step['reason']),step['after_pairs'],labels,added,step['premises']))
            frames[-1]['badges']=[{'text':'绿色虚线：已补入 '+str(len(added))+' 条关系','tone':'good'}]
        frames.append(relation_frame(result['label']+'的结果','新增 '+str(result['added_count'])+' 条边。结果包含原关系，并且是满足该性质的最小扩充。',result['final_pairs'],labels,added,focus_nodes='abc'))
    return frames


def choose_anchor(sources,chapter,label):
    unit=units_for(chapter).get(label)
    if not unit or unit.truncated or unit.record['version']!=VERSIONS[chapter]:return None
    index=next((i for i,s in enumerate(sources) if s.chapter_id==chapter and s.section_id==unit.section['id']
        and Path(s.source).stem==Path(unit.record['source']).stem),None)
    if index is None:return None
    selected=resolve_selection(PDFSelection(document_id=unit.record['document_id'],version=unit.record['version'],kind='text',rects=list(unit.rects[:2])))
    return index,selected['reference']|{'origin':'retrieval','location_kind':'numbered_unit'},unit


def build_textbook_guide(message,response,sources,execution,*,turn_id=''):
    """只在已通过核验的讲解之后调用；提示和测评不展开答案。"""
    message=unicodedata.normalize('NFKC',message)
    if execution.hint_only or any(i in execution.learning_intents for i in ('practice','check_answer','check_understanding')):return None
    if re.search(r'只.*提示|不要.*(?:答案|结论)|检查理解|出.*题|测验|测评',message):return None
    chapters={s.chapter_id for s in sources};topic=message+' '+response
    chapter=label=title=origin=None;frames=[]
    explicit=re.findall(r'例\s*(\d+)\s*[.．]\s*(\d+)',message)
    if explicit and any((a,b) not in [('9','8'),('4','6')] for a,b in explicit):return None
    if 9 in chapters and re.search(r'闭包|例\s*9[.．]8',topic):
        chapter=9;is_example=bool(re.search(r'例\s*9[.．]8',message));label='例9.8' if is_example else '定义9.6'
        if is_example:
            # 教材第11页原例，保留原来的数字标签。
            name=re.search(r'R\s*[_]?\s*(\d+)',message,re.I)
            if name and name[1] not in ('1','2','3'):return None
            number=int(name[1]) if name else 1
            seeds={1:[('a','b'),('b','a'),('a','c'),('a','a')],2:[('a','b'),('b','a')],3:[('a','b')]}
            spec=RelationSpec(pairs=[{'source':a,'target':b} for a,b in seeds[number]])
            labels=dict(zip('abc','123'));title='例9.8 · R'+str(number)+'的闭包';origin='textbook_example'
        else:
            if re.search(r'R\s*[=＝]|论域|集合\s*A\s*[=＝]',message):return None
            spec=template_spec('r3');labels=dict(zip('abc','abc'));title='理解关系闭包';origin='teaching_example'
        kinds=[k for k in ('reflexive','symmetric','transitive') if NAMES[k]+'闭包' in message]
        frames=closure_frames(spec,kinds or ['reflexive','symmetric','transitive'],labels)
    elif 9 in chapters and re.search(r'自反|对称|传递性|关系.*传递',topic):
        if explicit or re.search(r'R\s*[=＝]|论域|集合\s*A\s*[=＝]',message):return None
        chapter=9;label='定义9.5';origin='teaching_example'
        key=next((k for k in ('antisymmetric','irreflexive','reflexive','symmetric','transitive') if NAMES[k] in message),'transitive')
        spec=template_spec('r2' if key in ('reflexive','irreflexive','antisymmetric') else 'r3');pairs=spec.model_dump()['pairs']
        result=evaluate_relation(spec);w=result['witnesses'][key];title='理解'+NAMES[key]+'性'
        frames=[relation_frame('先看这个辅助例子','论域为 {a,b,c}，箭头表示关系中的序偶。',pairs)]
        if w:
            present=[{'source':a,'target':b} for a,b in w['present']]
            reason='已有 '+ '、'.join('('+a+','+b+')' for a,b in w['present'])+'。' if present else '检查每个元素的自环。'
            reason+=('但缺少 '+ '、'.join('('+a+','+b+')' for a,b in w['missing'])+'。') if w['missing'] else '这些边违反了所选性质的条件。'
            missing=[{'source':a,'target':b} for a,b in w['missing']]
            nodes=sorted({p[k] for p in present+missing for k in ('source','target')})
            frames.append(relation_frame('检查性质要求',reason+(' 红色虚线仅标示缺少的关系，没有向原关系添加边。' if missing else ''),pairs,focus=present,missing=missing,focus_nodes=nodes,warning=True))
            frames[-1]['badges']=[{'text':'缺少所需关系' if missing else '已有关系违反条件','tone':'warning'}]
        else:
            for node in 'abc':
                relevant=[p for p in pairs if node in (p['source'],p['target'])]
                conditions={'reflexive':'检查自环：('+node+','+node+') 已存在。','antisymmetric':'检查与 '+node+' 有关的边：没有与不同顶点同时互相指向。'}
                frames.append(relation_frame('检查顶点 '+node,conditions.get(key,'检查与 '+node+' 有关的关系，满足'+NAMES[key]+'性的条件。'),pairs,focus=relevant,focus_nodes=[node]))
        frames.append(relation_frame('得到结论','当前辅助关系'+('满足' if result['properties'][key] else '不满足')+NAMES[key]+'性。结论来自教材定义和完整有限检查。',pairs,
            focus=present if w else pairs,missing=missing if w else [],focus_nodes=nodes if w else 'abc',warning=bool(w)))
        frames[-1]['badges']=[{'text':('满足' if not w else '不满足')+NAMES[key]+'性','tone':'good' if not w else 'warning'}]
    elif 4 in chapters and re.search(r'蕴涵|蕴含|p\s*(?:→|->)\s*q|例\s*4[.．]6',topic):
        chapter=4;label='例4.6';origin='textbook_example';title='例4.6 · 用诺言理解蕴涵'
        rows=[['真','真','真'],['真','假','假'],['假','真','真'],['假','假','真']]
        cases=['我有车，也去接你，诺言兑现。','我有车，却没有去接你，这是违背诺言的情形。','我没有车，却仍去接你，没有违反“有车就去”的诺言。','我没有车，也没去接你，没有违反这个条件诺言。']
        frames=[{'title':'先读教材的条件诺言','text':'p 表示“我有车”，q 表示“我去接你”。p→q 表示“如果我有车，那么我去接你”。','table':{'columns':['p','q','p→q'],'rows':[[p,q,'待检查'] for p,q,r in rows],'active_row':-1}}]
        for i,case in enumerate(cases):
            before=[[p,q,r if j<i else '待检查'] for j,(p,q,r) in enumerate(rows)]
            after=[[p,q,r if j<=i else '待检查'] for j,(p,q,r) in enumerate(rows)]
            frames.append({'title':'第 '+str(i+1)+' 种情况：先看条件','text':'本行 p 为'+rows[i][0]+'，q 为'+rows[i][1]+'。先看是否满足“有车”这个前提，再检查是否去接你。',
                'table':{'columns':['p','q','p→q'],'rows':before,'active_row':i,'focus_columns':[0,1]},
                'badges':[{'text':'p：'+rows[i][0],'tone':'neutral'},{'text':'q：'+rows[i][1],'tone':'neutral'}]})
            frames.append({'title':'第 '+str(i+1)+' 种情况：得到结果','text':case,
                'table':{'columns':['p','q','p→q'],'rows':after,'active_row':i,'focus_columns':[2],'warning_row':i if i==1 else -1},
                'badges':[{'text':'p→q 为'+rows[i][2]+('：唯一违背诺言的情况' if i==1 else ''),'tone':'warning' if i==1 else 'good'}]})
    elif 7 in chapters and re.search(r'欧拉|一笔画',topic):
        if explicit or re.search(r'图\s*7[.．]\d+|有向图|入度|出度',message):return None
        chapter=7;label='定理7.11';origin='teaching_example';title='理解欧拉回路的判定'
        requested=re.search(r'边为\s*([^。！？\n]+)',message)
        if requested:
            raw=re.findall(r'\b(v\d+)\s*[-−—]\s*(v\d+)\b',requested[1],re.I)
            if not raw:return None
            nodes=sorted({m.lower() for m in re.findall(r'\bv\d+\b',message)},key=lambda n:int(n[1:]))
            graph=GraphSpec(nodes=[{'id':n,'label':n} for n in nodes],edges=[{'source':a.lower(),'target':b.lower()} for a,b in raw])
            title='当前图的欧拉回路判定';origin='user_example'
        else:
            graph=GraphSpec(nodes=[{'id':'v'+str(i),'label':'v'+str(i)} for i in range(1,5)],edges=[{'source':'v1','target':'v2'},{'source':'v2','target':'v3'},{'source':'v3','target':'v4'},{'source':'v4','target':'v1'}])
        frames=euler_frames(graph)
    if not frames:return None
    anchored=choose_anchor(sources,chapter,label)
    if not anchored:return None
    index,reference,unit=anchored
    return {'id':hashlib.sha256((turn_id+'|'+title+'|'+unit.record['version']).encode()).hexdigest()[:24],
        'schema_version':1,'title':title,'origin':origin,'chapter_id':chapter,'section_id':unit.section['id'],
        'source_label':label,'source_index':index,'selection_ref':reference,'frames':frames}
