// 改编自 LibreChat MemoryCardActions；首版仅保留删除，弹窗沿用宿主。
import { useState } from 'react';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import type { MemoryEntry } from './types';
export default function MemoryCardActions({memory, disabled, onDelete}: {memory:MemoryEntry; disabled:boolean; onDelete:()=>Promise<void>}) {
  const [open,setOpen]=useState(false);
  return <><button type="button" disabled={disabled} aria-label={`删除${memory.text}`} onClick={()=>setOpen(true)} className="shrink-0 rounded-md border border-border px-2 py-1 text-xs disabled:opacity-50">删除</button>
    <ConfirmDialog open={open} title="删除这条记忆？" confirmLabel="确认删除" cancelLabel="取消" busy={disabled} tone="danger" onCancel={()=>setOpen(false)} onConfirm={()=>void onDelete().finally(()=>setOpen(false))}>
      <p className="break-words">{memory.text}</p><p className="mt-2">删除后，后续辅导不再读取这条记忆。原始学习记录不受影响。</p>
    </ConfirmDialog></>;
}
