"""按教材定义9.5核验有限关系；反例必须来自当前序偶集合。"""
import networkx as nx
from models.relation import RelationSpec

ELEMENTS = ('a','b','c')
PROPERTIES = {'reflexive':'自反', 'irreflexive':'反自反', 'symmetric':'对称',
              'antisymmetric':'反对称', 'transitive':'传递'}
TEMPLATES = {'r1':[], 'r2':[('a','a'),('b','b'),('c','c')],
             'r3':[('a','b'),('b','c')], 'r4':[('a','b'),('b','c'),('a','c')],
             'r5':[('a','b'),('b','a')]}


def template_spec(identifier):
    return RelationSpec(pairs=[{'source':a,'target':b} for a,b in TEMPLATES[identifier]])


def evaluate_relation(spec):
    graph=nx.DiGraph()
    graph.add_nodes_from(ELEMENTS)
    graph.add_edges_from((pair.source,pair.target) for pair in spec.pairs)
    witnesses={key:None for key in PROPERTIES}
    for x in ELEMENTS:
        if not graph.has_edge(x,x) and witnesses['reflexive'] is None:
            witnesses['reflexive']={'missing':[[x,x]],'present':[]}
        if graph.has_edge(x,x) and witnesses['irreflexive'] is None:
            witnesses['irreflexive']={'missing':[],'present':[[x,x]]}
        for y in ELEMENTS:
            if graph.has_edge(x,y) and not graph.has_edge(y,x) and witnesses['symmetric'] is None:
                witnesses['symmetric']={'present':[[x,y]],'missing':[[y,x]]}
            if x != y and graph.has_edge(x,y) and graph.has_edge(y,x) and witnesses['antisymmetric'] is None:
                witnesses['antisymmetric']={'present':[[x,y],[y,x]],'missing':[]}
            for z in ELEMENTS:
                if graph.has_edge(x,y) and graph.has_edge(y,z) and not graph.has_edge(x,z) and witnesses['transitive'] is None:
                    witnesses['transitive']={'present':[[x,y],[y,z]],'missing':[[x,z]],'triple':[x,y,z]}
    return {'semantics':'textbook-definition-9.5-v1',
            'properties':{key:witnesses[key] is None for key in PROPERTIES}, 'witnesses':witnesses}


def matrix(spec):
    pairs={(pair.source,pair.target) for pair in spec.pairs}
    return [[int((source,target) in pairs) for target in ELEMENTS] for source in ELEMENTS]
