"use client";
import dynamic from 'next/dynamic'
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { useEffect, useState } from 'react'
import { apiFetch } from '@/lib/api'
import { useAuthStatus } from '@/hooks/useAuthStatus'
import { LearningShell } from '@/components/learning/LearningShell'
import { setPendingPrompt } from '@/lib/pending-prompt'
import { ChapterProgress } from './ChapterProgress'
import { AssessmentEvidence } from './AssessmentEvidence'
import useLightragGraph, { stateColor } from './graph/useLightragGraph'
import { useGraphStore } from './graph/store'
import { stateLabel, type NodeDetail } from './graph/types'
const GraphViewer=dynamic(()=>import('./graph/GraphViewer'),{ssr:false,loading:()=> <p role="status">正在加载图形组件…</p>})
const button='rounded-lg border border-border px-3 py-2 text-sm disabled:opacity-50'
export default function KnowledgeGraph(){
  const router=useRouter(),params=useSearchParams(),auth=useAuthStatus()
  const chapterValue=Number(params.get('chapter')||1),chapter=chapterValue>=1&&chapterValue<=10?chapterValue:1
  const query=params.get('q')||'',focus=params.get('focus')||''
  const [draft,setDraft]=useState(query),[revision,setRevision]=useState(0),[filter,setFilter]=useState('all')
  const [detail,setDetail]=useState<NodeDetail>(),[detailError,setDetailError]=useState(''),[detailRevision,setDetailRevision]=useState(0)
  const [actionError,setActionError]=useState(''),[busy,setBusy]=useState(false)
  const url='/api/graph/subgraph?'+new URLSearchParams({chapter:String(chapter),q:query,focus,limit:'80',refresh:String(revision)})
  const {data,error,loading}=useLightragGraph(url,auth.statusAvailable?auth.userId:null)
  const selected=useGraphStore.use.selectedNode()
  const requestedNode=params.get('node')||''
  useEffect(()=>{if(data&&requestedNode&&data.nodes.some(n=>n.id===requestedNode))useGraphStore.getState().setSelectedNode(requestedNode,true)},[data,requestedNode])
  useEffect(()=>{if(selected&&selected!==requestedNode){const next=new URLSearchParams(params.toString());next.set('node',selected);router.replace('/learning/graph?'+next.toString(),{scroll:false})}},[selected,requestedNode,params,router])
  useEffect(()=>setDraft(query),[query])
  const navigate=(changes:Record<string,string>)=>{const next=new URLSearchParams(params.toString());for(const [k,v] of Object.entries(changes)){if(v)next.set(k,v);else next.delete(k)}router.replace('/learning/graph?'+next.toString(),{scroll:false})}
  useEffect(()=>{
    const controller=new AbortController();setDetail(undefined);setDetailError('');setActionError('')
    if(!selected||!data)return ()=>controller.abort()
    const p=new URLSearchParams({id:selected,chapter:String(chapter),release_id:data.release_id})
    apiFetch('/api/graph/node?'+p,{signal:controller.signal,cache:'no-store'}).then(async response=>{if(!response.ok)throw new Error('节点详情读取失败，请重试。');return response.json() as Promise<NodeDetail>}).then(value=>{if(!controller.signal.aborted)setDetail(value)}).catch(reason=>{if(!controller.signal.aborted)setDetailError(String(reason.message||reason))})
    return ()=>controller.abort()
  },[selected,data,chapter,detailRevision])
  const guidance=async(practice=false)=>{
    if(!detail||busy)return;setBusy(true);setActionError('')
    try{
      const kc=detail.node.state.knowledge_point_id
      if(!kc){setPendingPrompt(`请根据《离散数学》第${chapter}章讲解“${selected}”。该实体尚无唯一确认的知识点映射，仅作讲解，不计入掌握。`,'chat');router.push('/chat');return}
      const source=detail.sources.map(s=>s.text).join('\n').slice(0,7500)
      const response=await apiFetch('/api/mastery-paths/topics',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:selected,goal:`${practice?'练习':'学习'}《离散数学》第${chapter}章的${selected}`,sources:[{client_ref:'graph-source',kind:'file',source_id:detail.document.id,label:`第${chapter}章教材原文`,excerpt:source,metadata:{document_id:detail.document.id,version:detail.document.version,graph_release_id:detail.release_id,mapping_version:detail.mapping_version}}],modules:[{name:selected,knowledge_points:[{id:kc,name:selected,type:'concept',topic_source_refs:['graph-source']}]}]})})
      if(!response.ok)throw new Error('辅导路径创建失败，请重试。')
      const topic=await response.json();setPendingPrompt(`请${practice?'围绕这个知识点出一道题，等我作答后按教材依据反馈':'依据教材讲解这个知识点，先了解我已经会什么'}。知识点 ID：${kc}。`,'mastery_path');router.push('/learning/mastery/'+encodeURIComponent(topic.path_id)+'/sessions')
    }catch(reason){setActionError(reason instanceof Error?reason.message:'无法打开辅导，请重试。')}finally{setBusy(false)}
  }
  const filtered=data?.nodes.filter(n=>filter==='all'||(filter==='due'?n.state.review_due:n.state.kind===filter))??[]
  return <LearningShell title="教材知识图谱" subtitle="教材结构由固定图谱提供；学习状态只展示当前账号已同步的厂家结论，关联关系不代表先修或掌握。">
    <div className="flex flex-wrap items-end gap-3">
      <label className="text-sm">章节<select aria-label="章节" value={chapter} onChange={e=>navigate({chapter:e.target.value,q:'',focus:'',node:''})} className={'ml-2 '+button}>{Array.from({length:10},(_,i)=><option key={i+1} value={i+1}>第 {i+1} 章</option>)}</select></label>
      <form className="flex min-w-0 flex-wrap gap-2" onSubmit={e=>{e.preventDefault();navigate({q:draft,focus:''})}}><input aria-label="搜索概念" value={draft} onChange={e=>setDraft(e.target.value)} maxLength={64} className={'min-w-0 max-w-full '+button}/><button className={button}>搜索</button></form>
      <button className={button} onClick={()=>setRevision(v=>v+1)}>刷新图谱与状态</button>
      {focus&&<button className={button} onClick={()=>navigate({focus:''})}>返回章节范围</button>}
    </div>
    {loading&&<p role="status" className="my-3">正在读取教材图谱与当前学习状态…</p>}
    {error&&<p role="alert" className="my-3">{error}</p>}
    {data&&<>
      {data.release_status==='approved_isolated_snapshot'&&<p className="my-3 text-sm text-muted-foreground">当前为已批准的隔离验收快照，正式教材服务未切换。</p>}
      {!data.catalog_available&&<p role="alert">目录或映射版本不可核对，节点不展示为已掌握。</p>}
      {(data.truncated||data.edges_truncated)&&<p role="status" className="my-3 text-sm">部分显示：当前最多 {data.limit} 个节点、600 条关联，请缩小章节或概念范围。</p>}
      {!data.nodes.length&&<p className="my-5">当前范围暂无图谱节点。请更换章节或搜索条件。</p>}
      <div className="my-4 flex flex-wrap gap-3 text-xs" aria-label="图谱状态图例">{['mastered','not_mastered','unknown','unmapped','ambiguous'].map(kind=><span key={kind} className="inline-flex items-center gap-1"><span className="h-3 w-3 rounded-full" style={{background:stateColor(kind)}}/>{stateLabel(kind)}</span>)}</div>
      <div className="grid min-w-0 gap-4 lg:grid-cols-[minmax(0,1fr)_320px]"><section className="min-w-0"><GraphViewer/>
        <div className="my-3 flex flex-wrap items-center justify-between gap-2"><h2 className="font-semibold">概念列表（可替代图形操作）</h2><label className="text-sm">显示状态<select aria-label="筛选学习状态" value={filter} onChange={e=>setFilter(e.target.value)} className={'ml-2 '+button}>{[['all','全部'],['mastered','厂家已掌握'],['unknown','无测评记录'],['unmapped','未映射'],['ambiguous','歧义映射'],['due','到期复习']].map(([v,l])=><option key={v} value={v}>{l}</option>)}</select></label></div>
        <ul className="max-h-80 divide-y divide-border overflow-y-auto rounded-lg border border-border" aria-label="教材概念列表">{filtered.map(n=><li key={n.id}><button type="button" aria-pressed={selected===n.id} onClick={()=>useGraphStore.getState().setSelectedNode(n.id,true)} className="w-full px-3 py-3 text-left text-sm hover:bg-muted"><span className="font-medium">{n.id}</span><span className="mt-1 block text-xs text-muted-foreground">{stateLabel(n.state.kind)}{n.state.review_due?'；已到复习时间':''}{n.state.sync_pending?'；有新结果待同步':''}{n.state.sync_blocked?'；新结果同步受阻':''}</span></button></li>)}</ul>
        {!filtered.length&&data.nodes.length>0&&<p className="mt-3 text-sm">本次已加载范围没有符合条件的节点。</p>}
      </section><aside className="min-w-0 break-words rounded-xl border border-border p-4" aria-label="节点详情">
        {!selected?<p>在图形或概念列表中选择节点。</p>:detailError?<><p role="alert">{detailError}</p><button className={button} onClick={()=>setDetailRevision(v=>v+1)}>重试节点详情</button></>:!detail?<p role="status">正在读取节点证据…</p>:<div className="space-y-3 text-sm"><h2 className="text-lg font-semibold">{detail.node.id}</h2><p>{detail.node.description||'暂无实体说明。'}</p><p>{stateLabel(detail.node.state.kind)}</p>{detail.node.state.review_due&&<p>厂家记录的复习时间已到。</p>}{detail.node.state.sync_pending&&<p>有新的厂家结果待同步；当前仍为上次同步记录。</p>}{detail.node.state.sync_blocked&&<p>新结果同步受阻；请勿把上次状态当作最新结论。</p>}
          {detail.node.state.snapshot&&<p>上次同步：{new Date(detail.node.state.snapshot.synced_at).toLocaleString('zh-CN')}{detail.node.state.snapshot.next_review_at&&<>；厂家复习时间：{new Date(detail.node.state.snapshot.next_review_at).toLocaleString('zh-CN')}</>}</p>}
          {detail.node.state.snapshot?.job_id&&<AssessmentEvidence jobId={detail.node.state.snapshot.job_id}/> }
          {detail.mappings.map(m=><p key={m.id}>确认映射 {m.id}：{m.kc_id} → 目标 {m.objective_id}</p>)}
          <details><summary className="cursor-pointer">查看原文依据与版本</summary><p className="mt-2 break-all text-xs">图谱 {detail.release_id}<br/>目录 {detail.catalog_version}<br/>映射 {detail.mapping_version}<br/>教材 {detail.document.version}</p>{detail.sources.map(s=><blockquote key={s.id} className="my-3 whitespace-pre-wrap border-l-2 border-border pl-3 text-xs">{s.heading}\n{s.text}</blockquote>)}</details>
          <div className="flex flex-wrap gap-2"><button disabled={busy} className={button} onClick={()=>void guidance(false)}>{busy?'正在打开…':'按此概念辅导'}</button>{detail.node.state.mapping_status==='confirmed'&&<button disabled={busy} className={button} onClick={()=>void guidance(true)}>练习此知识点</button>}<button className={button} onClick={()=>navigate({focus:detail.node.id,q:''})}>聚焦邻近概念</button><a href={'/api/graph/document?'+new URLSearchParams({chapter:String(chapter),release_id:detail.release_id})} target="_blank" rel="noopener noreferrer" className={button}>打开本章教材 PDF</a>{detail.node.state.knowledge_point_id&&<Link className={button} href={"/learning/practice?"+new URLSearchParams({knowledge_point_id:detail.node.state.knowledge_point_id,return_to:"/learning/graph?"+params.toString()})}>查看相关练习与复习</Link>}<Link href="/learning/journal" className={button}>学习档案与证据</Link></div>{actionError&&<p role="alert">{actionError}</p>}
          <p className="text-xs text-muted-foreground">教材原文仅作为依据展示；未映射或歧义节点保持未知，不由关联推断成绩。</p>
        </div>}
      </aside></div>
      <details className="mt-4 rounded-lg border border-border p-3 text-sm"><summary>本次教材关联（不代表先修关系）</summary><ul>{data.edges.map((e,i)=><li key={i} className="my-2">{e.source} — {e.target}：{e.description||'教材关联，未声明关系类型。'}</li>)}</ul></details>
    </>}
    <ChapterProgress key={chapter+':'+revision} chapter={chapter}/>
  </LearningShell>
}
