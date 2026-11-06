/* escapeXml: bahayonghang/drawio-skills @ 2aa612ef9d5b65179eeebe7ab33f97f39d2315b4; MIT. See visualization/skills/drawio/LICENSE. */
"use strict";
window.DrawioExport = (() => {
function escapeXml(str) {
  if (!str) return ''
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}
function serialize(title, graph) {
  const value = text => escapeXml(String(text).replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/g, ''));
  const ids = new Map(graph.nodes.map((node, i) => [node.id, 'node-' + i]));
  const nodes = graph.nodes.map((node, i) => '<mxCell id="'+ids.get(node.id)+'" value="'+value(node.label)+'" vertex="1" parent="1" style="rounded=1;whiteSpace=wrap;html=0;fillColor=#f5f7f8;strokeColor=#7f939e;"><mxGeometry x="'+(60+(i%3)*250)+'" y="'+(60+Math.floor(i/3)*140)+'" width="180" height="70" as="geometry"/></mxCell>');
  const edges = graph.edges.map((edge, i) => '<mxCell id="edge-'+i+'" value="'+value(edge.annotation||edge.label||'')+'" edge="1" parent="1" source="'+ids.get(edge.source)+'" target="'+ids.get(edge.target)+'" style="edgeStyle=orthogonalEdgeStyle;rounded=1;html=0;endArrow=classic;"><mxGeometry relative="1" as="geometry"/></mxCell>');
  return '<?xml version="1.0" encoding="UTF-8"?><mxfile host="app.diagrams.net"><diagram name="'+value(title)+'"><mxGraphModel><root><mxCell id="0"/><mxCell id="1" parent="0"/>'+nodes.join('')+edges.join('')+'</root></mxGraphModel></diagram></mxfile>';
}
return {serialize, download(title, graph) {
  const url = URL.createObjectURL(new Blob([serialize(title, graph)], {type:'application/xml;charset=utf-8'}));
  const link = document.createElement('a');link.href=url;link.download='教材关系图.drawio';link.click();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
}};
})();
