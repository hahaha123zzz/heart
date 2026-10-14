"""欧拉判定的只读画面状态，复用数学验证器。"""
import networkx as nx
from visualization.graph_validator import evaluate_graph


def euler_frames(spec):
    result = evaluate_graph(spec)
    graph = nx.Graph()
    graph.add_nodes_from(n.id for n in spec.nodes)
    graph.add_edges_from((e.source, e.target) for e in spec.edges)
    picture = {'directed': False, 'nodes': [n.model_dump() for n in spec.nodes],
               'edges': [dict(e.model_dump(), id=e.source+'-'+e.target) for e in spec.edges], 'focus': []}
    frames = [{'title': '先看图', 'text': '先检查连通性，再检查每个顶点的度数。', 'graph': picture}]
    for number, component in enumerate(nx.connected_components(graph), 1):
        nodes = [n for n in graph if n in component]
        edges = [e['id'] for e in picture['edges'] if e['source'] in component]
        frames.append({'title': '检查连通性',
            'text': '从 '+nodes[0]+' 出发，可以到达所有顶点，图连通。' if result['connected'] else '高亮第 '+str(number)+' 个连通分量：'+'、'.join(nodes)+'。不同分量之间没有路径。',
            'graph': picture | {'focus': edges, 'focus_nodes': nodes},
            'badges': [{'text': '连通' if result['connected'] else '分量 '+str(number), 'tone': 'good' if result['connected'] else 'warning'}]})
    degree_badges = [{'text': n+'：'+str(d)+(' 奇' if d % 2 else ' 偶'), 'tone': 'warning' if d % 2 else 'good'} for n, d in result['degrees'].items()]
    for node, degree in result['degrees'].items():
        incident = [e['id'] for e in picture['edges'] if node in (e['source'], e['target'])]
        frames.append({'title': '检查 '+node+' 的度数',
            'text': '高亮与 '+node+' 关联的边；自环计两次。度数为 '+str(degree)+'，是'+('奇数，不满足偶度条件。' if degree % 2 else '偶数。'),
            'graph': picture | {'focus': incident, 'focus_nodes': [node], 'warning_nodes': [node] if degree % 2 else [], 'node_annotations': {node: '度 '+str(degree)}}, 'badges': degree_badges})
    frames.append({'title': '得到判定', 'text': result['reason'],
        'graph': picture | {'focus_nodes': list(graph) if result['has_euler_circuit'] else [], 'warning_nodes': result['odd_vertices'], 'node_annotations': {n: '度 '+str(d) for n,d in result['degrees'].items()}},
        'badges': [{'text': '连通' if result['connected'] else '不连通', 'tone': 'good' if result['connected'] else 'warning'}]+degree_badges})
    if result['has_euler_circuit'] and spec.edges:
        route = list(nx.eulerian_circuit(graph, source=spec.nodes[0].id))
        visited, labels, walk = [], {}, [route[0][0]]
        for number, (a,b) in enumerate(route, 1):
            edge = next(e['id'] for e in picture['edges'] if {e['source'],e['target']} == {a,b})
            visited.append(edge); labels[edge] = str(number)+' · '+a+'→'+b; walk.append(b)
            frames.append({'title': '沿回路走第 '+str(number)+' 条边',
                'text': ' → '.join(walk)+('。回到起点，每条边恰好经过一次。' if number == len(route) else '。绿色边已走过，橙色边是本步经过的边。'),
                'graph': picture | {'traversed': list(visited), 'focus': [edge], 'focus_nodes': [b], 'edge_annotations': dict(labels)},
                'badges': [{'text': '已经过 '+str(number)+' / '+str(len(route))+' 条边', 'tone': 'good'}]})
    return frames
