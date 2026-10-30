'use strict';
const $ = id => document.getElementById(id);
let cy, selected = null, selectionRequest = 0, searchRequest = 0, graphRequest = 0;
async function api(path) {
  const response = await fetch('/api/graph/' + path);
  if (!response.ok) throw new Error('读取失败（' + response.status + '），请检查来源或服务日志。');
  return response.json();
}
function el(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}
function status(text) { $('status').textContent = text; }
function arrange() {
  const layout = cy.layout({name: 'cose', animate: false, randomize: true, nodeRepulsion: 800000,
    idealEdgeLength: 100, numIter: 500, padding: 40});
  const done = layout.promiseOn('layoutstop');
  layout.run();
  return done;
}
async function loadGraph(name = null, append = false) {
  const request = ++graphRequest;
  status('正在读取关系…');
  try {
    const data = await api('neighborhood?limit=60' + (name === null ? '' : '&name=' + encodeURIComponent(name)));
    if (request !== graphRequest) return;
    const incoming = data.elements.filter(item => !cy.getElementById(item.data.id).length);
    if (append && cy.nodes().length + incoming.filter(item => !item.data.source).length > 350) append = false;
    if (!append) cy.elements().remove();
    cy.add(append ? incoming : data.elements);
    await arrange();
    if (request !== graphRequest) return;
    status('当前显示 ' + cy.nodes().length + ' 个实体、' + cy.edges().length + ' 条关系。' +
      (data.truncated ? '本次仅显示关联度较高的 ' + data.shown + '/' + data.total + ' 个实体；其余可搜索。' : '可点击节点继续探索。'));
  } catch (error) { if (request === graphRequest) status(error.message); }
}
async function detail(name = null, edge = null) {
  const request = ++selectionRequest;
  selected = name;
  $('expand').hidden = true;
  $('detail-title').textContent = '读取详情…';
  $('detail-content').replaceChildren();
  try {
    const data = await api('detail?' + (name !== null ? 'name=' + encodeURIComponent(name) : 'edge=' + edge));
    if (request !== selectionRequest) return;
    $('detail-title').textContent = data.title;
    $('expand').hidden = name === null;
    const body = $('detail-content');
    body.append(el('h3', '自动抽取摘要 · 待核对'));
    for (const text of data.descriptions) body.append(el('p', text, 'description'));
    if (!data.descriptions.length) body.append(el('p', '此条目没有摘要。', 'muted'));
    body.append(el('h3', '教材来源 · 按候选版本核验'));
    for (const source of data.sources) {
      const card = el('div', undefined, 'source-card');
      card.append(el('strong', '第 ' + source.chapter + ' 章 · ' + source.title));
      card.append(el('small', '版本 ' + source.version.slice(0, 16)));
      if (source.available) {
        const link = el('a', '打开整章 PDF ↗');
        link.href = '/api/graph/pdf/' + encodeURIComponent(source.file);
        link.target = '_blank'; link.rel = 'noopener'; card.append(link);
      } else card.append(el('p', '来源缺失或版本失效，已停用链接。', 'muted'));
      body.append(card);
    }
    if (!data.sources.length) body.append(el('p', '没有可确认的教材映射，请勿据此作事实判断。', 'muted'));
    body.append(el('h3', '检索片段 · ' + data.source_count + ' 个来源标识'));
    body.append(el('p', '至多显示前 8 个片段。以下内容与上方图谱摘要分开，未自动升级为逐句核验的证据。', 'muted'));
    for (const snippet of data.snippets) {
      const box = el('details');
      box.append(el('summary', snippet.file + ' · ' + snippet.id));
      box.append(el('p', snippet.text, 'snippet')); body.append(box);
    }
    if (name !== null) {
      const nearby = await api('neighborhood?name=' + encodeURIComponent(name));
      if (request !== selectionRequest) return;
      body.append(el('h3', '相邻实体 · 可点击浏览'));
      for (const item of nearby.elements.filter(item => !item.data.source && item.data.id !== name)) {
        const button = el('button', item.data.label, 'neighbor');
        button.onclick = () => focus(item.data.id); body.append(button);
      }
    }
  } catch (error) { if (request === selectionRequest) $('detail-title').textContent = error.message; }
}
async function focus(name) {
  await Promise.all([loadGraph(name), detail(name)]);
  if (selected === name) cy.nodes().filter(n => n.id() === name).select();
}
async function search() {
  const request = ++searchRequest;
  const q = $('search').value.trim();
  $('results').replaceChildren();
  if (!q) { $('search-status').textContent = '请输入实体名称。'; return; }
  $('search-status').textContent = '正在搜索…';
  try {
    const results = await api('search?q=' + encodeURIComponent(q));
    if (request !== searchRequest) return;
    $('search-status').textContent = results.length ? '找到 ' + results.length + ' 个匹配（最多显示 30 个）' : '未找到实体，试试更短的概念名称。';
    for (const result of results) {
      const button = el('button', result.name, 'result');
      button.append(el('small', result.type + ' · ' + result.degree + ' 条关系'));
      button.onclick = () => focus(result.name); $('results').append(button);
    }
  } catch (error) { if (request === searchRequest) $('search-status').textContent = error.message; }
}
async function init() {
  try {
    cy = cytoscape({container: $('graph'), minZoom: .1, maxZoom: 4, style: [
      {selector: 'node', style: {'background-color': '#509183', 'label': 'data(label)', 'color': '#294c43',
        'font-size': 11, 'text-valign': 'bottom', 'text-margin-y': 7, 'text-wrap': 'ellipsis', 'text-max-width': 115,
        'width': 'mapData(degree, 1, 400, 18, 48)', 'height': 'mapData(degree, 1, 400, 18, 48)',
        'border-width': 2, 'border-color': '#fff'}},
      {selector: 'edge', style: {'width': 1, 'line-color': '#b5cbc1', 'opacity': .65, 'curve-style': 'bezier'}},
      {selector: ':selected', style: {'background-color': '#d99545', 'line-color': '#c27d28', 'border-width': 3,
        'border-color': '#ad6f25', 'opacity': 1}}
    ]});
    cy.on('tap', 'node', event => detail(event.target.id()));
    cy.on('tap', 'edge', event => detail(null, Number(event.target.id().slice(5))));
    $('search-form').onsubmit = event => { event.preventDefault(); search(); };
    document.querySelectorAll('[data-query]').forEach(button => button.onclick = () => { $('search').value = button.dataset.query; search(); });
    $('expand').onclick = () => { if (selected !== null) loadGraph(selected, true); };
    $('overview').onclick = () => loadGraph();
    $('fit').onclick = () => cy.fit(undefined, 40);
    $('layout').onclick = arrange;
    $('zoom-in').onclick = () => cy.zoom({level: cy.zoom() * 1.3, renderedPosition: {x: cy.width()/2, y: cy.height()/2}});
    $('zoom-out').onclick = () => cy.zoom({level: cy.zoom() / 1.3, renderedPosition: {x: cy.width()/2, y: cy.height()/2}});
    const data = await api('summary');
    $('summary').textContent = data.nodes.toLocaleString() + ' 个实体 / ' + data.edges.toLocaleString() + ' 条关系 / ' + data.documents + ' 章教材';
    $('identity').textContent = '图谱 SHA256 ' + data.graph_sha256.slice(0, 16);
    await loadGraph();
  } catch (error) { status(error.message); }
}
init();
