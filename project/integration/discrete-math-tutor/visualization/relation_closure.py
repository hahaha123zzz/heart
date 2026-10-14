"""教材定义9.6的最小扩充；逐步依据由当前关系确定。"""
import networkx as nx
from models.relation import RelationSpec
from visualization.relation_validator import ELEMENTS,matrix,evaluate_relation

LABELS={'reflexive':'自反闭包','symmetric':'对称闭包','transitive':'传递闭包'}


def as_spec(pairs):
    return RelationSpec(pairs=[{'source':a,'target':b} for a,b in sorted(pairs)])


def build_closure(spec,kind):
    if kind not in LABELS:raise ValueError('闭包类型无效')
    original={(p.source,p.target) for p in spec.pairs};current=set(original);steps=[]
    def add(pair,premises,reason):
        if pair in current:return
        before=as_spec(current).model_dump()['pairs'];current.add(pair);after=as_spec(current)
        steps.append({'number':len(steps)+1,'added_pair':{'source':pair[0],'target':pair[1]},
            'premises':[{'source':a,'target':b} for a,b in premises],'reason':reason,
            'before_pairs':before,'after_pairs':after.model_dump()['pairs'],'matrix':matrix(after)})
    if kind=='reflexive':
        for a in ELEMENTS:add((a,a),[],f'自反性要求论域中的 {a} 与自身相关，补入 ({a},{a})。')
    elif kind=='symmetric':
        for a,b in sorted(original):add((b,a),[(a,b)],f'已有 ({a},{b})，对称性要求逆序偶 ({b},{a})。')
    else:
        while True:
            witness=next(((a,b,c) for a in ELEMENTS for b in ELEMENTS for c in ELEMENTS
                if (a,b) in current and (b,c) in current and (a,c) not in current),None)
            if witness is None:break
            a,b,c=witness
            add((a,c),[(a,b),(b,c)],f'已有 ({a},{b}) 和 ({b},{c})，传递性要求 ({a},{c})。')
        graph=nx.DiGraph();graph.add_nodes_from(ELEMENTS);graph.add_edges_from(original)
        if current!=set(nx.transitive_closure(graph,reflexive=False).edges()):
            raise RuntimeError('传递闭包与独立可达性核验不一致')
    final=as_spec(current)
    if not original.issubset(current) or not evaluate_relation(final)['properties'][kind]:
        raise RuntimeError('闭包核验失败')
    return {'kind':kind,'label':LABELS[kind],'elements':list(ELEMENTS),'original_pairs':spec.model_dump()['pairs'],
        'original_matrix':matrix(spec),'final_pairs':final.model_dump()['pairs'],'final_matrix':matrix(final),
        'steps':steps,'added_count':len(steps),'validator_version':'textbook-definition-9.6-v1'}
