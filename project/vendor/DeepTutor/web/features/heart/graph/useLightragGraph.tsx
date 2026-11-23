import { UndirectedGraph } from 'graphology'
import { useEffect, useState } from 'react'
import { apiFetch } from '@/lib/api'
import { useGraphStore, RawGraph } from './store'
import { resolveNodeColor, DEFAULT_NODE_COLOR } from './graphColor'
import { hasEdgeSafe, addUndirectedEdgeSafe } from './graphEdgeSafety'
import type { GraphPayload } from './types'
const NODE_BORDER_COLOR = '#FFFFFF'
const hashNodeIdToPosition = (id: string): { x: number; y: number } => {
  let h1 = 0xdeadbeef ^ id.length
  let h2 = 0x41c6ce57 ^ id.length
  for (let i = 0; i < id.length; i++) {
    const ch = id.charCodeAt(i)
    h1 = Math.imul(h1 ^ ch, 2654435761)
    h2 = Math.imul(h2 ^ ch, 1597334677)
  }
  h1 = Math.imul(h1 ^ (h1 >>> 16), 2246822507) ^ Math.imul(h2 ^ (h2 >>> 13), 3266489909)
  h2 = Math.imul(h2 ^ (h2 >>> 16), 2246822507) ^ Math.imul(h1 ^ (h1 >>> 13), 3266489909)
  return { x: (h1 >>> 0) / 4294967296, y: (h2 >>> 0) / 4294967296 }
}

// Yield to the browser WITHOUT setTimeout's nested-timer clamp.
// `await setTimeout(0)` in a loop is clamped to >= 4ms per call by the HTML
// spec once timers nest more than 5 deep, so batched yielding via setTimeout
// adds (items / batchSize) * 4ms of pure idle time on top of the real work.
// scheduler.yield() (where available) or a MessageChannel message resolves in
// microseconds instead.
const yieldToBrowser = (): Promise<void> => {
  const scheduler = (globalThis as { scheduler?: { yield?: () => Promise<void> } }).scheduler
  if (scheduler?.yield) return scheduler.yield()
  return new Promise<void>((resolve) => {
    const { port1, port2 } = new MessageChannel()
    port1.onmessage = () => {
      port1.close()
      resolve()
    }
    port2.postMessage(null)
  })
}

// Cooperative time-slicing: run synchronously until the frame budget is spent,
// then yield ONCE. Keeps the page responsive while wasting almost no time.
const FRAME_BUDGET_MS = 12
const CHECK_EVERY = 256 // power of two; performance.now() is sampled sparsely

// Per-type node colors, performance-safe. The original implementation
// resolved the palette (and potentially wrote to the zustand store) ONCE PER
// NODE; this resolver calls resolveNodeColor once per DISTINCT entity type
// (graphs have dozens of types, not thousands of them) and commits the
// type->color map to the store in a single write, which also keeps the
// Legend functional.
const createTypeColorResolver = () => {
  let typeColorMap = useGraphStore.getState().typeColorMap
  const cache = new Map<string, string>()
  let mapUpdated = false

  return {
    colorFor(entityType: unknown): string {
      // entity_type is untrusted graph data and may be a non-string; keep the
      // cache key a string and let resolveNodeColor handle the raw value.
      const key = typeof entityType === 'string' ? entityType : ''
      let color = cache.get(key)
      if (color === undefined) {
        const resolved = resolveNodeColor(entityType, typeColorMap)
        if (resolved.updated) {
          typeColorMap = resolved.map
          mapUpdated = true
        }
        color = resolved.color || DEFAULT_NODE_COLOR
        cache.set(key, color)
      }
      return color
    },
    commit() {
      if (mapUpdated) {
        useGraphStore.setState({ typeColorMap })
        mapUpdated = false
      }
    }
  }
}

// Parse an edge's `weight` property into a finite number, preserving a
// legitimate 0. `Number(x) || 1` would coerce a real weight of 0 (the thinnest
// edge) to 1; use a finite check so 0 survives and only undefined/NaN fall back.
const parseEdgeWeight = (properties: Record<string, unknown> | undefined): number => {
  const w = Number(properties?.weight)
  return Number.isFinite(w) ? w : 1
}

// Build a node label defensively: a malformed payload node missing its
// `labels` array must not throw (labels.join) and abort the whole graph build
// — fall back to the node id so the rest of the graph still renders.
const safeNodeLabel = (labels: unknown, fallbackId: string): string =>
  Array.isArray(labels) ? labels.join(', ') : fallbackId

export type NodeType = {
  x: number
  y: number
  label: string
  size: number
  color: string
  highlighted?: boolean
}
export type EdgeType = {
  label: string
  originalWeight?: number
  size?: number
  color?: string
  hidden?: boolean
}

// Create a new graph instance with the raw graph data
export const createSigmaGraph = async (rawGraph: RawGraph | null): Promise<UndirectedGraph | null> => {
  if (!rawGraph || !rawGraph.nodes.length) return null

  const graph = new UndirectedGraph()
  const typeColors = createTypeColorResolver()
  let sliceStart = performance.now()

  const nodes = rawGraph.nodes
  for (let i = 0; i < nodes.length; i++) {
    // Yield only when ~12ms of real work has accumulated, not every N items.
    if ((i & (CHECK_EVERY - 1)) === 0 && performance.now() - sliceStart > FRAME_BUDGET_MS) {
      await yieldToBrowser()
      sliceStart = performance.now()
    }

    const rawNode = nodes[i]
    // Defensive: a duplicate id in the payload would make addNode throw
    if (graph.hasNode(rawNode.id)) continue

    const { x, y } = hashNodeIdToPosition(rawNode.id)
    rawNode.color = typeColors.colorFor(rawNode.properties?.entity_type)

    graph.addNode(rawNode.id, {
      label: safeNodeLabel(rawNode.labels, rawNode.id),
      color: rawNode.color,
      x,
      y,
      size: rawNode.size,
      borderColor: NODE_BORDER_COLOR
    })
  }

  // Single store write for the whole build (keeps the Legend in sync)
  typeColors.commit()

  rawGraph.edgeDynamicIdMap = Object.create(null) as Record<string, number>
  let skippedEdges = 0

  const edges = rawGraph.edges
  for (let i = 0; i < edges.length; i++) {
    if ((i & (CHECK_EVERY - 1)) === 0 && performance.now() - sliceStart > FRAME_BUDGET_MS) {
      await yieldToBrowser()
      sliceStart = performance.now()
    }

    const rawEdge = edges[i]
    // Truncated BFS responses contain many dangling/duplicate edges. Three
    // cheap hash lookups beat a thrown-and-caught exception per bad edge
    // (exception throw/stack capture is orders of magnitude more expensive).
    if (
      !graph.hasNode(rawEdge.source) ||
      !graph.hasNode(rawEdge.target) ||
      hasEdgeSafe(graph, rawEdge.source, rawEdge.target)
    ) {
      continue
    }

    // `rawEdge.type` is the storage-level relationship type ("DIRECTED" for
    // every edge); the human-readable relation name is properties.keywords.
    // originalWeight feeds GraphControl's thickness scaling.
    const attributes = {
      label: (rawEdge.properties?.keywords as string | undefined) || undefined,
      originalWeight: parseEdgeWeight(rawEdge.properties)
    }
    const dynamicId = addUndirectedEdgeSafe(graph, rawEdge.source, rawEdge.target, attributes)
    if (dynamicId === null) {
      skippedEdges++
      continue
    }
    rawEdge.dynamicId = dynamicId
    rawGraph.edgeDynamicIdMap[rawEdge.dynamicId] = i
  }

  if (skippedEdges > 0) {
    console.warn(`[useLightragGraph] ${skippedEdges} edges could not be added to the graph`)
  }

  return graph
}


export default function useLightragGraph(url: string, owner: string | null) {
  const [data,setData]=useState<GraphPayload>();const [loaded,setLoaded]=useState('');const ownerKey=String(owner)+':'+url;const [error,setError]=useState('');const [loading,setLoading]=useState(true)
  useEffect(()=>{
    const controller=new AbortController();useGraphStore.getState().reset();setData(undefined);setError('');setLoading(true)
    if(!owner){setLoading(false);return ()=>controller.abort()}
    async function load(){
      try{
        const response=await apiFetch(url,{signal:controller.signal,cache:'no-store'});if(!response.ok)throw new Error(response.status===409?'教材图谱版本已变化，请刷新。':'图谱加载失败，请重试。')
        const value=await response.json() as GraphPayload;if(controller.signal.aborted)return
        const raw=new RawGraph();raw.nodes=value.nodes.map(n=>({id:n.id,labels:[n.id],properties:{entity_type:n.type},degree:0,size:8}));raw.edges=value.edges.map((e,i)=>({id:String(i),source:e.source,target:e.target,properties:{weight:e.weight,keywords:'教材关联'}}))
        raw.nodes.forEach((n,i)=>{raw.nodeIdMap[n.id]=i});raw.edges.forEach((e,i)=>{raw.edgeIdMap[e.id]=i;if(raw.getNode(e.source))raw.getNode(e.source).degree++;if(raw.getNode(e.target))raw.getNode(e.target).degree++})
        const graph=await createSigmaGraph(raw);if(controller.signal.aborted)return
        if(graph)for(const node of value.nodes)graph.setNodeAttribute(node.id,'color',stateColor(node.state.kind))
        useGraphStore.setState({rawGraph:raw,sigmaGraph:graph,graphEdgeCount:graph?.size??0});setData(value);setLoaded(ownerKey)
      }catch(reason){if(!controller.signal.aborted)setError(reason instanceof Error?reason.message:'图谱加载失败，请重试。')}
      finally{if(!controller.signal.aborted)setLoading(false)}
    }
    void load();return ()=>{controller.abort();useGraphStore.getState().reset()}
  },[url,owner])
  return {data:loaded===ownerKey?data:undefined,error,loading:loading||(Boolean(owner)&&loaded!==ownerKey&&!error)}
}
export const stateColor=(kind:string)=>({mastered:'#23856b',not_mastered:'#bd7b35',unknown:'#607084',ambiguous:'#9259a6',unmapped:'#b5bcc5',version_unavailable:'#b5bcc5'}[kind]??'#b5bcc5')
