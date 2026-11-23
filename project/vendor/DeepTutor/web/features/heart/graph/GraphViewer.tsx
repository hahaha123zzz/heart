"use client";
import { Component, useState, useEffect, type ReactNode } from 'react'
import { SigmaContainer, useCamera } from '@react-sigma/core'
import type { Settings as SigmaSettings } from 'sigma/settings'
import { EdgeArrowProgram, EdgeLineProgram, EdgeRectangleProgram, NodePointProgram, NodeCircleProgram } from 'sigma/rendering'
import { NodeBorderProgram } from '@sigma/node-border'
import { EdgeCurvedArrowProgram, createEdgeCurveProgram } from '@sigma/edge-curve'
import GraphControl from './GraphControl'
import FocusOnNode from './FocusOnNode'
import { useGraphStore } from './store'
import { labelColorDarkTheme,labelColorLightTheme,edgeColorDarkTheme } from './constants'
import '@react-sigma/core/lib/style.css'
const createSigmaSettings = (
  isDarkTheme: boolean,
  enableEdgeEvents: boolean
): Partial<SigmaSettings> => ({
  allowInvalidContainer: true,
  // Nodes use the border program so every node gets a white ring (the
  // @sigma/node-border default reads `borderColor` for the ring, `color` for
  // the fill; ring thickness is a fixed 10% of the radius). Single GPU draw
  // call -- cheap even at 70k+ nodes. (Earlier "border blanks the canvas"
  // reports were actually the fetch effect never firing -- once that was
  // fixed, the border program rendered fine.)
  defaultNodeType: 'border',
  // 'rect' (EdgeRectangleProgram) draws straight quads that RESPECT the edge
  // size attribute; EdgeLineProgram renders fixed ~1px GL lines and ignores
  // size entirely. Rectangles are still far cheaper than tessellated curves.
  defaultEdgeType: 'rect',
  renderEdgeLabels: false,
  // Skip edge rendering while panning/zooming - big win on large graphs.
  hideEdgesOnMove: true,
  edgeProgramClasses: {
    rect: EdgeRectangleProgram,
    line: EdgeLineProgram,
    arrow: EdgeArrowProgram,
    curvedArrow: EdgeCurvedArrowProgram,
    // kept registered for backward compatibility with edges that still
    // carry type: 'curvedNoArrow'
    curvedNoArrow: createEdgeCurveProgram()
  },
  nodeProgramClasses: {
    point: NodePointProgram,
    default: NodePointProgram,
    circle: NodeCircleProgram,
    border: NodeBorderProgram
  },
  labelGridCellSize: 60,
  labelRenderedSizeThreshold: 12,
  // Off by default (edge picking renders edges to an extra buffer every frame —
  // costly on large graphs); turning on the "Edge Events" setting rebuilds the
  // instance with the picking buffer so edges become hover/click-selectable.
  enableEdgeEvents,
  // Without per-edge reducers (disabled when nothing is focused), edges with
  // no color attribute fall back to this.
  defaultEdgeColor: isDarkTheme ? edgeColorDarkTheme : '#d3d3d3',
  labelColor: {
    color: isDarkTheme ? labelColorDarkTheme : labelColorLightTheme,
    attribute: 'labelColor'
  },
  edgeLabelColor: {
    color: isDarkTheme ? labelColorDarkTheme : labelColorLightTheme,
    attribute: 'labelColor'
  },
  edgeLabelSize: 8,
  labelSize: 12
})


const studentSettings=createSigmaSettings(false,true)
class CanvasBoundary extends Component<{children:ReactNode},{failed:boolean}> {
  state={failed:false}
  static getDerivedStateFromError(){return {failed:true}}
  render(){return this.state.failed?<p role="status" className="p-5 text-sm">图形视图不可用，请使用下方概念列表查看、搜索和打开详情。</p>:this.props.children}
}
function ZoomControl(){
  const {zoomIn,zoomOut,reset}=useCamera({duration:200,factor:1.5})
  return <div className="absolute bottom-3 left-3 z-10 flex gap-2 rounded-lg border border-border bg-background p-2 text-sm"><button aria-label="放大图谱" onClick={()=>zoomIn()}>＋</button><button aria-label="缩小图谱" onClick={()=>zoomOut()}>－</button><button onClick={()=>reset()}>适应视图</button></div>
}
export default function GraphViewer(){
  const [webgl,setWebgl]=useState<boolean|null>(null)
  const selected=useGraphStore.use.selectedNode();const move=useGraphStore.use.moveToSelectedNode();const graph=useGraphStore.use.sigmaGraph()
  useEffect(()=>{try{const gl=document.createElement('canvas').getContext('webgl2');setWebgl(Boolean(gl));gl?.getExtension('WEBGL_lose_context')?.loseContext()}catch{setWebgl(false)}},[])
  if(!graph?.order)return null
  if(webgl===false)return <p role="status" className="rounded-lg border border-border p-5 text-sm">WebGL 不可用，请使用概念列表查看和选择节点。</p>
  if(webgl===null)return <p role="status">正在准备图形视图…</p>
  return <CanvasBoundary><div className="relative h-[440px] min-w-0 overflow-hidden rounded-xl border border-border" aria-label="教材概念关系图"><SigmaContainer settings={studentSettings} style={{height:'100%',width:'100%',background:'#fff'}}><GraphControl/><FocusOnNode node={selected} move={move}/><ZoomControl/></SigmaContainer></div></CanvasBoundary>
}
