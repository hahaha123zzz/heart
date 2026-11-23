import { beforeEach, expect, it } from 'vitest'
import { RawGraph, useGraphStore } from '@/features/heart/graph/store'
import { createSigmaGraph } from '@/features/heart/graph/useLightragGraph'
beforeEach(()=>useGraphStore.getState().reset())
it('keeps real entity names safe and discards duplicate and dangling edges',async()=>{
 const raw=new RawGraph();raw.nodes=['正常','constructor','hasOwnProperty','__proto__'].map(id=>({id,labels:[id],properties:{entity_type:'概念'},size:8,degree:0}))
 raw.edges=[{source:'正常',target:'constructor'},{source:'正常',target:'constructor'},{source:'正常',target:'hasOwnProperty'},{source:'正常',target:'__proto__'},{source:'missing',target:'正常'}].map((e,i)=>({...e,id:String(i),properties:{weight:0}}))
 const graph=await createSigmaGraph(raw);expect(graph?.order).toBe(4);expect(graph?.size).toBe(3);expect(graph?.edges().map(e=>graph.getEdgeAttribute(e,'originalWeight'))).toEqual([0,0,0])
})
it('uses stable positions and treats empty data as empty',async()=>{
 const raw=new RawGraph();raw.nodes=[{id:'甲',labels:['甲'],properties:{},size:8,degree:0}]
 const a=await createSigmaGraph(raw),b=await createSigmaGraph(raw);expect(a?.getNodeAttribute('甲','x')).toBe(b?.getNodeAttribute('甲','x'));expect(await createSigmaGraph(new RawGraph())).toBeNull()
})
it('releases the active native layout when graph scope changes',()=>{
 let killed=0;useGraphStore.getState().setActiveLayoutSupervisor({kill:()=>killed++});useGraphStore.getState().reset();expect(killed).toBe(1);expect(useGraphStore.getState().selectedNode).toBeNull()
})
