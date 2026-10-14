"""复用 NetworkX；遵循教材定义7.18的全顶点连通约定。"""
import networkx as nx
from models.visualization import GraphSpec

SEMANTICS = 'textbook-definition-7.18-v1'


def evaluate_graph(spec: GraphSpec) -> dict:
    graph = nx.Graph()
    graph.add_nodes_from(node.id for node in spec.nodes)
    graph.add_edges_from((edge.source, edge.target) for edge in spec.edges)
    degrees = dict(graph.degree())
    odd = [node for node, degree in degrees.items() if degree % 2]
    connected = nx.is_connected(graph)
    # 本书显式允许单个孤立顶点；固定四节点模板不产生这一特例。
    circuit = nx.is_eulerian(graph)
    open_path = connected and len(odd) == 2
    trail = circuit or open_path
    if circuit:
        reason = '单个孤立顶点属于教材定义中的特例。' if not spec.edges else '图连通且每个顶点的度均为偶数，有欧拉回路。'
    elif open_path:
        reason = '图连通且恰有两个奇度顶点，有非闭合欧拉通路，但没有欧拉回路。'
    elif not connected:
        reason = '图不连通，不满足教材要求的遍历所有顶点与边的条件。'
    else:
        reason = '奇度顶点超过两个，既没有欧拉回路，也没有欧拉通路。'
    return {'semantics': SEMANTICS, 'degrees': degrees, 'odd_vertices': odd,
            'isolated_vertices': list(nx.isolates(graph)), 'connected': connected,
            'has_euler_circuit': circuit, 'has_open_euler_path': open_path,
            'has_euler_trail': trail, 'reason': reason}
