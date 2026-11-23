import { create } from 'zustand'
import type { UndirectedGraph } from 'graphology'
import type Sigma from 'sigma'
import type { NodeType, EdgeType } from './useLightragGraph'
import { createSelectors } from './selectors'
export type RawNodeType = { id: string; labels: string[]; properties: Record<string, unknown>; size: number; degree: number; color?: string }
export type RawEdgeType = { id: string; source: string; target: string; properties: Record<string, unknown>; dynamicId?: string }
export class RawGraph {
  nodes: RawNodeType[] = []
  edges: RawEdgeType[] = []
  nodeIdMap: Record<string, number> = Object.create(null)
  edgeIdMap: Record<string, number> = Object.create(null)
  edgeDynamicIdMap: Record<string, number> = Object.create(null)
  getNode = (id: string) => this.nodes[this.nodeIdMap[id]]
  getEdge = (id: string) => this.edges[this.edgeDynamicIdMap[id]]
}
type Supervisor = { kill: () => void }
type State = {
  selectedNode: string | null; focusedNode: string | null; selectedEdge: string | null; focusedEdge: string | null; moveToSelectedNode: boolean
  sigmaGraph: UndirectedGraph | null; rawGraph: RawGraph | null; sigmaInstance: Sigma<NodeType, EdgeType> | null; graphEdgeCount: number; isLayoutComputing: boolean
  typeColorMap: Map<string,string>; activeLayoutSupervisor: Supervisor | null
  setSelectedNode: (id: string | null, move?: boolean) => void; setFocusedNode: (id: string | null) => void; setSelectedEdge: (id: string | null) => void; setFocusedEdge: (id: string | null) => void
  setMoveToSelectedNode: (move: boolean) => void; clearSelection: () => void; setSigmaInstance: (instance: Sigma<NodeType, EdgeType> | null) => void
  setActiveLayoutSupervisor: (handle: Supervisor | null) => void; releaseLayoutSupervisor: (handle: Supervisor | null) => void; setIsLayoutComputing: (value: boolean) => void
  reset: () => void
}
export const useGraphStore = createSelectors(create<State>((set,get) => ({
  selectedNode:null,focusedNode:null,selectedEdge:null,focusedEdge:null,moveToSelectedNode:false,sigmaGraph:null,rawGraph:null,sigmaInstance:null,graphEdgeCount:0,isLayoutComputing:false,typeColorMap:new Map(),activeLayoutSupervisor:null,
  setSelectedNode:(id,move=false)=>set({selectedNode:id,moveToSelectedNode:move}),setFocusedNode:id=>set({focusedNode:id}),setSelectedEdge:id=>set({selectedEdge:id}),setFocusedEdge:id=>set({focusedEdge:id}),
  setMoveToSelectedNode:move=>set({moveToSelectedNode:move}),clearSelection:()=>set({selectedNode:null,focusedNode:null,selectedEdge:null,focusedEdge:null}),setSigmaInstance:instance=>set({sigmaInstance:instance}),
  setActiveLayoutSupervisor:next=>{const prev=get().activeLayoutSupervisor;if(prev&&prev!==next)try{prev.kill()}catch{/* worker 已结束 */}set({activeLayoutSupervisor:next})},
  releaseLayoutSupervisor:handle=>{if(get().activeLayoutSupervisor===handle)get().setActiveLayoutSupervisor(null);else try{handle?.kill()}catch{/* worker 已结束 */}},setIsLayoutComputing:value=>set({isLayoutComputing:value}),
  reset:()=>{get().setActiveLayoutSupervisor(null);set({selectedNode:null,focusedNode:null,selectedEdge:null,focusedEdge:null,moveToSelectedNode:false,sigmaGraph:null,rawGraph:null,sigmaInstance:null,graphEdgeCount:0,typeColorMap:new Map(),isLayoutComputing:false})},
})))
