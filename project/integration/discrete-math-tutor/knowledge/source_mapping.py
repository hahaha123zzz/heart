"""检索文字到原始段落的可验证范围；父块展开后必须重新计算。"""
from knowledge.grounding_text import normalized_with_map,normalized


def block_text(block):
    return '\n'.join(' '.join(row) for row in block['rows']) if block['kind']=='table' else block['text']


def source_spans(blocks,text):
    # 表格分隔符是索引序列化格式，不属于原书单元格中的字符。
    text=text.replace(' | ','   ')
    folded,positions=normalized_with_map(text)
    result=[]
    for block in blocks:
        original=block_text(block)
        needle,mapping=normalized_with_map(original)
        if not needle:continue
        found=folded.find(needle)
        if found>=0 and folded.find(needle,found+1)<0:
            result.append({'block_id':block['block_index'],'block_start':0,'block_end':len(original),
                'text_start':positions[found],'text_end':positions[found+len(needle)-1]+1})
            continue
        # 切块或父块预算可能仅留下半段；保留实际交集，不能声称包含完整段落。
        if len(folded)>=12:
            found=needle.find(folded)
            if found>=0 and needle.find(folded,found+1)<0:
                result.append({'block_id':block['block_index'],'block_start':mapping[found],
                    'block_end':mapping[found+len(folded)-1]+1,'text_start':0,'text_end':len(text)})
                continue
        # 多段切块的首尾可落在段内；只接纳两侧都触及边界的唯一连续交集。
        overlaps=[]
        a=needle.find(folded[:12]) if len(folded)>=12 else -1
        if a>=0 and needle.find(folded[:12],a+1)<0 and folded.startswith(needle[a:]):
            overlaps.append((a,0,len(needle)-a))
        b=folded.find(needle[:12]) if len(needle)>=12 else -1
        if b>=0 and folded.find(needle[:12],b+1)<0 and needle.startswith(folded[b:]):
            overlaps.append((0,b,len(folded)-b))
        for a,b,size in overlaps:
            result.append({'block_id':block['block_index'],'block_start':mapping[a],
                'block_end':mapping[a+size-1]+1,'text_start':positions[b],'text_end':positions[b+size-1]+1})
    return tuple(result)
