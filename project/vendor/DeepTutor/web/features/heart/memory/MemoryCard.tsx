// 改编自 LibreChat MemoryCard；保留两行卡片结构，来源和时间仅使用 H 真实字段。
import MemoryCardActions from './MemoryCardActions';
import type { MemoryEntry } from './types';
const sourceLabel=(source:string)=>({explicit_user:'你主动添加',student_statement:'学生自述',learning_inference:'学习记录自动整理（待确认）'}[source]??'来源尚未确认');
export default function MemoryCard({memory,disabled,onDelete}:{memory:MemoryEntry;disabled:boolean;onDelete:()=>Promise<void>}) {
  const date=memory.created_at?new Date(memory.created_at+(/[zZ]|[+-]\d\d:\d\d$/.test(memory.created_at)?'':'Z')):null;
  return <div className="group min-w-0 rounded-lg px-3 py-2.5 hover:bg-muted">
    <div className="flex items-start gap-2"><span className="min-w-0 flex-1 whitespace-pre-wrap break-words text-sm font-medium">{memory.text}</span><MemoryCardActions memory={memory} disabled={disabled} onDelete={onDelete}/></div>
    <div className="mt-1 text-sm"><details><summary className="cursor-pointer">查看详情</summary>
      {memory.source&&<p className="mt-2">来源：{sourceLabel(memory.source)}</p>}
      {date&&!Number.isNaN(date.getTime())&&<time className="mt-1 block text-xs text-muted-foreground" dateTime={memory.created_at}>添加时间：{date.toLocaleString('zh-CN')}</time>}
      <p className="mt-2 text-muted-foreground">记忆用于调整辅导方式，不代表已通过知识点测评。</p>
    </details></div>
  </div>;
}
