// 改编自 LibreChat MemoryEmptyState，使用学生语言和项目样式。
export default function MemoryEmptyState({isFiltered=false}:{isFiltered?:boolean}) {
  return <p className="mt-3 text-sm text-muted-foreground">{isFiltered?'没有匹配内容。':'还没有内容。'}</p>;
}
