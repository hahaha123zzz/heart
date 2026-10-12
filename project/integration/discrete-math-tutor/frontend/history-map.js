"use strict";

// 历史问题可视化：只消费已保存的节点，打开页面绝不触发模型生成。
window.HistoryMap = (() => {
  const states = new WeakMap();
  const esc = value => String(value ?? "").replace(/[&<>"']/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[ch]));

  function transform(state) {
    state.plane.style.transform = `translate(${state.x}px, ${state.y}px) scale(${state.scale})`;
  }

  function layout(nodes, collapsed) {
    const byId = new Map(nodes.map(node => [node.id, node]));
    const children = new Map(nodes.map(node => [node.id, []]));
    for (const node of nodes) if (byId.has(node.parent_id) && node.parent_id !== node.id) children.get(node.parent_id).push(node);
    const roots = nodes.filter(node => !byId.has(node.parent_id) || node.parent_id === node.id);
    let row = 0, maxDepth = 0;
    const positions = new Map();
    function walk(node, depth) {
      maxDepth = Math.max(maxDepth, depth);
      const visible = collapsed.has(node.id) ? [] : children.get(node.id);
      let y;
      if (!visible.length) { y = 50 + row * 112; row++; }
      else { const ys = visible.map(child => walk(child, depth + 1)); y = (ys[0] + ys[ys.length - 1]) / 2; }
      positions.set(node.id, {x: 38 + depth * 290, y});
      return y;
    }
    roots.forEach(root => walk(root, 0));
    return {positions, children, width: (maxDepth + 1) * 290 + 80, height: Math.max(250, row * 112 + 60)};
  }

  function draw(state) {
    const {positions, children, width, height} = layout(state.nodes, state.collapsed);
    const edges = state.nodes.filter(node => positions.has(node.id) && positions.has(node.parent_id)).map(node => {
      const a = positions.get(node.parent_id), b = positions.get(node.id);
      return `<path d="M ${a.x + 226} ${a.y + 27} C ${a.x + 254} ${a.y + 27}, ${b.x - 28} ${b.y + 27}, ${b.x} ${b.y + 27}"/>`;
    }).join("");
    const cards = state.nodes.filter(node => positions.has(node.id)).map(node => {
      const p = positions.get(node.id), descendants = children.get(node.id).length;
      return `<div class="map-node" style="left:${p.x}px;top:${p.y}px"><button class="map-node-title" type="button" data-node-id="${node.id}" title="查看原始问答">${esc(node.title)}</button><div class="map-node-meta"><span>${Math.max(1, Math.floor(node.message_count / 2))} 轮问答</span>${descendants ? `<button class="map-fold" type="button" data-fold-id="${node.id}" aria-label="${state.collapsed.has(node.id) ? "展开" : "折叠"}分支" aria-expanded="${!state.collapsed.has(node.id)}">${state.collapsed.has(node.id) ? "+" : "−"} ${descendants}</button>` : ""}</div></div>`;
    }).join("");
    state.plane.style.width = width + "px"; state.plane.style.height = height + "px";
    state.plane.innerHTML = `<svg class="map-edges" width="${width}" height="${height}" aria-hidden="true">${edges}</svg>${cards}`;
    transform(state);
  }

  function render(element, nodes, onSelect) {
    let state = states.get(element);
    if (!state) {
      element.innerHTML = '<div class="map-toolbar"><button type="button" data-zoom="in" aria-label="放大">＋</button><button type="button" data-zoom="out" aria-label="缩小">－</button><span>拖动画布 · 滚轮缩放 · 点击问题查看问答</span></div><div class="map-plane"></div>';
      state = {element, plane: element.querySelector(".map-plane"), nodes: [], collapsed: new Set(), scale: 1, x: 20, y: 20, onSelect};
      states.set(element, state);
      element.addEventListener("click", event => {
        const title = event.target.closest("[data-node-id]");
        if (title) { state.onSelect(Number(title.dataset.nodeId)); return; }
        const fold = event.target.closest("[data-fold-id]");
        if (fold) { const id = Number(fold.dataset.foldId); state.collapsed.has(id) ? state.collapsed.delete(id) : state.collapsed.add(id); draw(state); return; }
        const zoom = event.target.closest("[data-zoom]");
        if (zoom) { state.scale = Math.max(.35, Math.min(2, state.scale * (zoom.dataset.zoom === "in" ? 1.2 : .83))); transform(state); }
      });
      element.addEventListener("wheel", event => { event.preventDefault(); state.scale = Math.max(.35, Math.min(2, state.scale * (event.deltaY < 0 ? 1.08 : .92))); transform(state); }, {passive:false});
      element.addEventListener("pointerdown", event => {
        if (event.target.closest("button")) return;
        state.drag = {x:event.clientX, y:event.clientY, ox:state.x, oy:state.y};
        element.setPointerCapture(event.pointerId);
      });
      element.addEventListener("pointermove", event => { if (!state.drag) return; state.x = state.drag.ox + event.clientX - state.drag.x; state.y = state.drag.oy + event.clientY - state.drag.y; transform(state); });
      element.addEventListener("pointerup", () => { state.drag = null; });
      element.addEventListener("pointercancel", () => { state.drag = null; });
    }
    state.onSelect = onSelect;
    const signature = JSON.stringify(nodes);
    if (state.signature === signature) return;
    state.signature = signature; state.nodes = nodes;
    draw(state);
    if (!nodes.length) state.plane.innerHTML = '<p class="map-empty">还没有整理出的历史问题。向助教提问后，这里会自动生成问题分支。</p>';
  }

  function reset(element) {
    const state = states.get(element);
    if (!state) return;
    state.x = 20; state.y = 20; state.scale = 1; transform(state);
  }

  function clear(element) {
    states.delete(element);
    element.innerHTML = "";
  }

  return {render, reset, clear};
})();
