"""Render the in-chat knowledge tree with draw.io Desktop instead of Cytoscape."""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import time
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / 'frontend' / 'visualizations' / 'drawio'
BUILD_DIR = ROOT / '.cache' / 'drawio-build'
URL_PREFIX = '/static/visualizations/drawio'


def _executable() -> str | None:
    candidates = [
        os.environ.get('DRAWIO_EXECUTABLE'),
        shutil.which('draw.io'),
        shutil.which('drawio'),
        str(Path(os.environ.get('LOCALAPPDATA', '')) / 'Programs' / 'draw.io' / 'draw.io.exe'),
        r'C:\Program Files\draw.io\draw.io.exe',
    ]
    return next((path for path in candidates if path and Path(path).is_file()), None)


def _style(depth: int) -> str:
    common = ('rounded=1;whiteSpace=wrap;html=1;fontFamily=Microsoft YaHei;'
              'align=center;verticalAlign=middle;strokeWidth=1;')
    if depth == 0:
        return common + ('fillColor=#23425b;fontColor=#ffffff;strokeColor=none;'
                         'fontSize=20;fontStyle=1;')
    if depth == 1:
        return common + ('fillColor=#3f7f8f;fontColor=#ffffff;strokeColor=none;'
                         'fontSize=15;fontStyle=1;')
    return common + ('fillColor=#eef4f7;fontColor=#23425b;strokeColor=#9eb7c5;'
                     'fontSize=14;')


def _layout(graph: dict) -> tuple[dict, dict, int, int]:
    nodes = graph.get('nodes') or []
    edges = graph.get('edges') or []
    ids = [str(node['id']) for node in nodes]
    if not ids:
        return {}, {}, 400, 300
    children = {node_id: [] for node_id in ids}
    incoming = set()
    for edge in edges:
        source, target = str(edge.get('source')), str(edge.get('target'))
        if source in children and target in children:
            children[source].append(target)
            incoming.add(target)
    roots = [node_id for node_id in ids if node_id not in incoming]
    root = roots[0] if roots else ids[0]
    positions, depth = {}, {}
    cursor = [40]

    def place(node_id: str, level: int) -> float:
        depth[node_id] = level
        kids = children.get(node_id, [])
        if not kids:
            y = cursor[0]
            cursor[0] += 78
        else:
            ys = [place(kid, level + 1) for kid in kids]
            y = (min(ys) + max(ys)) / 2
        positions[node_id] = (40 + level * 300, y)
        return y

    place(root, 0)
    # Cycles or disconnected nodes still need a position.
    for node_id in ids:
        positions.setdefault(node_id, (40, cursor[0]))
        depth.setdefault(node_id, 0)
    widths = {node_id: 280 if depth[node_id] == 0 else 250 for node_id in ids}
    heights = {node_id: 64 if depth[node_id] == 0 else (60 if depth[node_id] == 1 else 64)
               for node_id in ids}
    width = max(positions[node_id][0] + widths[node_id] for node_id in ids) + 40
    height = max(positions[node_id][1] + heights[node_id] for node_id in ids) + 40
    return positions, depth, int(width), int(height)


def _xml(frame: dict) -> tuple[str, int, int] | None:
    graph = frame.get('graph')
    if not graph or not graph.get('nodes'):
        return None
    positions, depth, width, height = _layout(graph)
    ids = {str(node['id']): f'n{i}' for i, node in enumerate(graph['nodes'])}
    widths = {nid: 280 if level == 0 else 250 for nid, level in depth.items()}
    heights = {nid: 64 if level == 0 else (60 if level == 1 else 64)
               for nid, level in depth.items()}
    cells = []
    for node in graph['nodes']:
        node_id = str(node['id'])
        x, y = positions[node_id]
        label = escape(str(node.get('label') or ''))
        cells.append(
            f'<mxCell id="{ids[node_id]}" value="{label}" style="{_style(depth[node_id])}" '
            f'vertex="1" parent="1"><mxGeometry x="{x:.0f}" y="{y:.0f}" '
            f'width="{widths[node_id]}" height="{heights[node_id]}" as="geometry"/></mxCell>')
    for index, edge in enumerate(graph.get('edges') or []):
        source, target = ids.get(str(edge.get('source'))), ids.get(str(edge.get('target')))
        if not source or not target:
            continue
        cells.append(
            f'<mxCell id="e{index}" style="edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;'
            f'strokeColor=#9eb7c5;strokeWidth=2;endArrow=none;'
            f'exitX=1;exitY=0.5;entryX=0;entryY=0.5;" edge="1" parent="1" '
            f'source="{source}" target="{target}"><mxGeometry relative="1" as="geometry"/></mxCell>')
    title = escape(str(frame.get('title') or '知识结构'))
    xml = (
        '<mxfile host="app.diagrams.net" agent="tutor" version="30.4.1" type="device">'
        f'<diagram id="knowledge-map" name={quoteattr(title)}>'
        f'<mxGraphModel dx="1200" dy="800" grid="0" guides="1" tooltips="1" connect="1" '
        f'arrows="1" fold="1" page="0" pageScale="1" pageWidth="{width}" pageHeight="{height}" '
        f'math="0" shadow="0" background="#ffffff"><root><mxCell id="0"/><mxCell id="1" parent="0"/>'
        + ''.join(cells)
        + '</root></mxGraphModel></diagram></mxfile>')
    return xml, width, height


def _wait_for(paths: list[Path], timeout: float = 90) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if all(path.is_file() and path.stat().st_size > 0 for path in paths):
            return True
        time.sleep(0.4)
    return all(path.is_file() and path.stat().st_size > 0 for path in paths)


def attach_images(frames: list[dict]) -> bool:
    """Attach a draw.io-exported PNG to each frame; leave graphs as fallback."""
    executable = _executable()
    if not executable:
        return False
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    pending: list[tuple[dict, Path, Path]] = []
    for frame in frames:
        built = _xml(frame)
        if built is None:
            continue
        xml, _, _ = built
        digest = hashlib.sha256(xml.encode('utf-8')).hexdigest()[:20]
        png = OUTPUT_DIR / f'{digest}.png'
        source = BUILD_DIR / f'{digest}.drawio'
        frame['_drawio_png'] = png
        frame['_drawio_source'] = source
        if not png.is_file():
            source.write_text(xml, encoding='utf-8')
            pending.append((frame, source, png))
    if pending:
        command = [executable, '--export', '--format', 'png', '--theme', 'light',
                   '--border', '24', '--disable-update', '--output', str(OUTPUT_DIR),
                   *(str(source) for _, source, _ in pending)]
        try:
            subprocess.run(command, check=False, timeout=20,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (OSError, subprocess.TimeoutExpired):
            return False
        if not _wait_for([png for _, _, png in pending]):
            return False
    for frame in frames:
        png = frame.pop('_drawio_png', None)
        frame.pop('_drawio_source', None)
        if png and png.is_file():
            frame['image'] = {'url': f'{URL_PREFIX}/{png.name}',
                              'alt': frame.get('title') or '章节知识结构'}
    return any(frame.get('image') for frame in frames)
