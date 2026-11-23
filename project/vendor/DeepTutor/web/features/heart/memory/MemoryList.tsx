// 改编自 LibreChat MemoryList；H 的稳定条目 ID 是列表与删除的唯一地址。
import MemoryCard from './MemoryCard';
import MemoryEmptyState from './MemoryEmptyState';
import type {MemoryEntry} from './types';
export default function MemoryList({memories,disabled,isFiltered=false,label,onDelete}:{memories:MemoryEntry[];disabled:boolean;isFiltered?:boolean;label:string;onDelete:(memory:MemoryEntry)=>Promise<void>}) {
  if(!memories.length)return <MemoryEmptyState isFiltered={isFiltered}/>;
  return <div className="mt-3 space-y-2" role="list" aria-label={label}>{memories.map(memory=><div key={memory.id} role="listitem"><MemoryCard memory={memory} disabled={disabled} onDelete={()=>onDelete(memory)}/></div>)}</div>;
}
