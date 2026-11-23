import React from 'react'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import KnowledgeGraph from '@/features/heart/KnowledgeGraph'
import { useGraphStore } from '@/features/heart/graph/store'
const mocks=vi.hoisted(()=>({query:'chapter=3',fetch:vi.fn(),replace:vi.fn(),push:vi.fn()}))
vi.mock('next/navigation',()=>({useSearchParams:()=>new URLSearchParams(mocks.query),useRouter:()=>({replace:mocks.replace,push:mocks.push}),usePathname:()=>'/learning/graph'}))
vi.mock('next/dynamic',()=>({default:()=>()=> <p>图形视图测试边界</p>}))
vi.mock('@/hooks/useAuthStatus',()=>({useAuthStatus:()=>({userId:'student-a',statusAvailable:true,loading:false})}))
vi.mock('@/lib/api',()=>({apiFetch:mocks.fetch,apiUrl:(url:string)=>url}))
vi.mock('@/features/heart/ChapterProgress',()=>({ChapterProgress:()=>null}))
vi.mock('react-i18next',()=>({useTranslation:()=>({t:(key:string)=>key,i18n:{language:'zh'}})}))
const payload={course_id:'experimental-psychology-3',release_id:'version',release_status:'approved_isolated_snapshot',catalog_version:'catalog',mapping_version:'mapping',catalog_available:true,nodes:[{id:'相关设计',type:'概念',description:'教材说明',chapter:3,state:{kind:'unknown',mapping_status:'confirmed',knowledge_point_id:'kc-3-1',objective_id:'kc-3-1',snapshot:null,sync_pending:true}}],edges:[],truncated:true,edges_truncated:false,limit:80,chapter:3,document:{id:'doc',version:'pdf-version',chapter:3}}
beforeEach(()=>{vi.clearAllMocks();mocks.query='chapter=3';useGraphStore.getState().reset();mocks.fetch.mockImplementation(async(url:string)=>new Response(JSON.stringify(url.startsWith('/api/graph/node')?{...payload,node:payload.nodes[0],sources:[{id:'source',text:'可核对原文',file:'chapter_03.generated.pdf',heading:'相关设计'}],mappings:[{id:'M004',kc_id:'kc-3-1',objective_id:'kc-3-1',document_version:'pdf-version'}]}:payload)))})
it('keeps unknown and pending statuses explicit and reads details only on selection',async()=>{
 render(<KnowledgeGraph/>);expect(await screen.findByText(/部分显示/)).toBeInTheDocument();expect(mocks.fetch.mock.calls.some(([url])=>String(url).includes('/node?'))).toBe(false)
 fireEvent.click(screen.getByRole('button',{name:/相关设计.*无已同步测评/}));expect(await screen.findByText('教材说明')).toBeInTheDocument();expect(screen.getByText(/当前仍为上次同步记录/)).toBeInTheDocument();expect(screen.getByRole('link',{name:'打开本章教材 PDF'})).toHaveAttribute('href',expect.stringContaining('release_id=version'));expect(screen.getByRole('button',{name:'练习此知识点'})).toBeInTheDocument()
 expect(mocks.fetch.mock.calls.some(([url])=>String(url).includes('/node?'))).toBe(true)
})
it('shows a request error and can refresh to an actual empty graph',async()=>{
 mocks.fetch.mockResolvedValueOnce(new Response('{}',{status:503}));render(<KnowledgeGraph/>);expect(await screen.findByRole('alert')).toHaveTextContent('图谱加载失败')
 mocks.fetch.mockResolvedValue(new Response(JSON.stringify({...payload,nodes:[],truncated:false})));fireEvent.click(screen.getByRole('button',{name:'刷新图谱与状态'}));expect(await screen.findByText(/当前范围暂无图谱节点/)).toBeInTheDocument()
})
it('aborts replaced scopes and ignores the late previous response',async()=>{
 let release!:(value:Response)=>void;const pending=new Promise<Response>(resolve=>{release=resolve});mocks.fetch.mockReturnValueOnce(pending)
 const view=render(<KnowledgeGraph/>);const oldSignal=mocks.fetch.mock.calls[0][1].signal as AbortSignal
 mocks.query='chapter=4';view.rerender(<KnowledgeGraph/>);expect(oldSignal.aborted).toBe(true)
 await waitFor(()=>expect(screen.getByRole('button',{name:/相关设计/})).toBeInTheDocument())
 await act(async()=>{release(new Response(JSON.stringify({...payload,nodes:[{...payload.nodes[0],id:'迟到的旧图'}]})));await pending})
 expect(screen.queryByText('迟到的旧图')).toBeNull()
})
