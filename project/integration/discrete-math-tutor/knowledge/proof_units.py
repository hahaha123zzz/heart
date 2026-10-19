"""编号证明单元：PDF 边界、显式前置引用与可追溯证据扩展。"""
from __future__ import annotations
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path
import hashlib
import logging
import re
import fitz
from knowledge.pdf_reader import document_for_chapter, pdf_path, PDFSelection, resolve_selection
from knowledge.pdf_evidence import PdfSupplement, compact, _lines
from knowledge.textbook import TextbookChunk, terms_for

REF = re.compile(r'(定义|定理|引理|推论|命题|例)\s*(\d+)\s*[.．]\s*(\d+)(?![A-Za-z0-9])')
PROOF_QUERY = re.compile(r'证明|反证|推导|为何|为什么|解释|说明')
COMMENT = re.compile(r'^(?:的|中|常被|常称|就是|证毕|推得|告诉|之逆|还可|也可|、|[）)])')


def key(match):
    return f'{match[1]}{int(match[2])}.{int(match[3])}'


@dataclass(frozen=True)
class Unit:
    id: str
    label: str
    chapter: int
    section: dict
    record: dict
    lines: tuple
    rects: tuple
    refs: tuple
    omitted: bool
    truncated: bool
    @property
    def text(self):
        return '\n'.join(f'[PDF第{n}页] {t}' for n, _, t in self.lines)
    @property
    def pages(self):
        return sorted({n for n, _, _ in self.lines})


@lru_cache(maxsize=16)
def _scan(chapter, version):
    record = document_for_chapter(chapter)
    units = {}
    with fitz.open(pdf_path(record)) as pdf:
        for i, section in enumerate(record['sections']):
            if not section.get('verified'): continue
            following = record['sections'][i+1] if i+1 < len(record['sections']) else None
            entries = []
            for n in range(section['page'], (following['page'] if following else len(pdf))+1):
                for y, text, _ in _lines(pdf[n-1]):
                    if y < .07 or y > .91: continue
                    if (n,y) < (section['page'], section['y']-.008): continue
                    if following and (n,y) >= (following['page'], following['y']-.008): continue
                    entries.append((n,y,text))
            starts=[]
            seen=set()
            in_exercise=False
            for pos, (n,y,text) in enumerate(entries):
                if re.fullmatch(r'(?:练习|习题)\s*\d+(?:[.．]\d+)?', compact(text)):
                    starts.append((pos, None)); in_exercise=True
                if in_exercise: continue
                m=REF.match(text)
                if not m or int(m[2]) != chapter: continue
                label=key(m)
                tail=text[m.end():].lstrip()
                if label in seen or COMMENT.match(tail): continue
                seen.add(label)
                starts.append((pos,label))
            for j, (pos,label) in enumerate(starts):
                if label is None: continue
                end=starts[j+1][0] if j+1<len(starts) else len(entries)
                lines=entries[pos:end]
                # 非常长的异常单元显式标记，不能称其为完整证明。
                truncated=bool(lines and lines[-1][0]-lines[0][0] >= 8)
                lines=[line for line in lines if line[0] < lines[0][0]+8]
                if not lines: continue
                rects=[]
                for n in sorted({line[0] for line in lines}):
                    ys=[y for page,y,_ in lines if page==n]
                    next_y=next((y for page,y,_ in entries[end:] if page==n), .9)
                    y1=max(.07,min(ys)-.008)
                    y2=min(.9,next_y-.008)
                    if y2-y1>=.015: rects.append(dict(page=n,x1=.11,y1=y1,x2=.9,y2=y2))
                text='\n'.join(t for _,_,t in lines)
                refs=tuple(dict.fromkeys(key(m) for m in REF.finditer(text) if key(m)!=label))
                omitted=bool(re.search(r'留给读者|读者自行|请读者.*完成|读者自证|证明.*极容易|证明同样.*简单|仿上可证|证明略|证略',text))
                unit=Unit(f'ch{chapter}:{label}',label,chapter,section,record,tuple(lines),tuple(rects),refs,omitted,truncated)
                # 一个章节内出现重号时拒绝含糊地覆盖首个单元。
                if label not in units: units[label]=unit
    return units


def units_for(chapter):
    record=document_for_chapter(chapter)
    if not record or hashlib.sha256(pdf_path(record).read_bytes()).hexdigest()!=record['version']:
        raise ValueError('教材版本不一致，不能扩展证明')
    return _scan(chapter,record['version'])


def _before(first, second):
    return (first.chapter, first.lines[0][0], first.lines[0][1]) < (second.chapter, second.lines[0][0], second.lines[0][1])


def dependencies(unit):
    linked=[]; unresolved=[]
    for label in unit.refs:
        m=REF.fullmatch(label)
        candidate=units_for(int(m[2])).get(label) if m and 1<=int(m[2])<=10 else None
        if candidate and _before(candidate,unit): linked.append(candidate)
        else: unresolved.append(label)
    return linked,unresolved


def focus_pages(unit,query):
    # 优先匹配显式蕴含方向；只定位原文，不改写数学内容。
    direction=re.search(r'[（(](\d+)[）)]\s*(?:⇒|→|=>|推出|蕴涵)\s*[（(](\d+)[）)]',query)
    if direction:
        pattern=re.compile(r'[（(]'+direction[1]+r'[）)]\s*[⇒→]\s*[（(]'+direction[2]+r'[）)]')
        # 定理开头的总路线不是该方向的详细证明。
        candidates=[n for n,_,t in unit.lines if pattern.search(t) and len(pattern.sub('',t).strip())>5]
        if candidates: return [candidates[-1]]
    terms=terms_for(query)-terms_for(unit.label)-terms_for('定理证明完整过程解释为什么')
    scores={n:sum(len(terms & terms_for(t)) for page,_,t in unit.lines if page==n) for n in unit.pages}
    best=max(unit.pages,key=lambda n:scores[n])
    if re.search(r'这一步|这一段|该步骤',query): return [best]
    pages=unit.pages
    start=max(0,min(pages.index(best),len(pages)-2))
    return pages[start:start+2]


def _chunk(unit, *, text=None):
    body=text or unit.text
    return TextbookChunk(source=str(Path(unit.record['source']).with_suffix('.txt').name),section=unit.section['title'],
        text=body,terms=terms_for(body),chapter_id=unit.chapter,section_id=unit.section['id'],
        chunk_id=unit.id,parent_id=unit.id,page=unit.pages[0])


@dataclass
class ProofEvidence:
    unit: Unit
    prerequisites: list
    unresolved: list
    supplement: PdfSupplement
    def public(self):
        return dict(unit_id=self.unit.id,label=self.unit.label,pages=self.unit.pages,
                    focus_pages=self.supplement.pages,
                    prerequisites=[dict(unit_id=u.id,label=u.label,pages=u.pages) for u in self.prerequisites],
                    relation_type='explicit_citation_not_mathematically_verified',unresolved_references=self.unresolved,omitted_steps=self.unit.omitted,truncated=self.unit.truncated)

    def public_references(self, sources):
        """为主证明、前置单元及补检索单元提供原始引用序号与跳转。"""
        refs=[dict(source_index=self.supplement.source_index,label=self.unit.label,
                   selection_ref=self.supplement.reference)]
        candidates = [(unit, next((i for i, source in enumerate(sources) if source.chunk_id == unit.id), None))
                      for unit in self.prerequisites]
        seen = {self.unit.id} | {unit.id for unit in self.prerequisites}
        # 补检索的新单元也提供跳转，但不将它伪称为原书显式前置引用。
        for index, source in enumerate(sources):
            heading = REF.match(source.text.lstrip())
            if not heading or not source.chapter_id or source.kind != 'text':
                continue
            try:
                unit = units_for(source.chapter_id).get(key(heading))
            except (OSError, ValueError, KeyError, RuntimeError):
                continue
            if not unit or unit.id in seen or unit.truncated:
                continue
            if unit.section['id'] != source.section_id or compact(unit.section['title']) != compact(source.section):
                continue
            if compact(source.source.removesuffix('.txt')) != compact(unit.record['source'].removesuffix('.doc')):
                continue
            seen.add(unit.id)
            candidates.append((unit, index))
        for unit, index in candidates:
            if index is None: continue
            try:
                selected=resolve_selection(PDFSelection(document_id=unit.record['document_id'],
                    version=unit.record['version'],kind='text',rects=list(unit.rects[:2])))
                refs.append(dict(source_index=index,label=unit.label,
                    selection_ref=selected['reference']|{'origin':'retrieval'}))
            except (OSError,ValueError,KeyError,RuntimeError) as exc:
                logging.getLogger(__name__).warning('前置引用预览失败：%s',type(exc).__name__)
        return refs


def expand_proof_sources(sources,query):
    """只扩展已召回的明确证明单元；新增前置资料不绕过充分性核验。"""
    targets=[key(m) for m in REF.finditer(query) if m[1] in ('定理','引理','命题','推论')]
    if len(set(targets))!=1 or not PROOF_QUERY.search(query): return sources,None
    label=targets[0]
    for index,source in enumerate(sources):
        heading=REF.match(source.text.lstrip())
        if not heading or key(heading)!=label or source.kind!='text' or not source.chapter_id: continue
        try:
            unit=units_for(source.chapter_id).get(label)
            if not unit or unit.section['id']!=source.section_id or compact(unit.section['title'])!=compact(source.section): continue
            if compact(source.source.removesuffix('.txt'))!=compact(unit.record['source'].removesuffix('.doc')): continue
            if unit.truncated or len(unit.text)>24000: return sources,None
            linked,unresolved=dependencies(unit)
            linked=linked[:2]
            pages=focus_pages(unit,query)
            rects=[r for r in unit.rects if r['page'] in pages]
            if not rects: return sources,None
            selection=resolve_selection(PDFSelection(document_id=unit.record['document_id'],version=unit.record['version'],kind='text',rects=rects))
            text='[经版本核验的完整编号单元；文字中的特殊数学字符须用附图核对]\n'+unit.text
            if unresolved: text+='\n[未关联或顺序在后的原文引用：'+ '、'.join(unresolved)+'；不能据此作为已建立前提。]'
            if unit.omitted: text+='\n[边界说明：教材存在留给读者完成的证明步骤；补充推导必须与原文区分。]'
            output=list(sources); output[index]=replace(source,text=text,terms=terms_for(text),page=unit.pages[0])
            existing={s.chunk_id for s in output}
            for dep in linked:
                if dep.id not in existing:
                    deptext='[原文显式引用过的单元：引用关系未经数学正确性确认，需核对，不能用待证结论替代]\n'+dep.text
                    # 不截断一个长前置证明冒充全部；只给有限资料并明确边界。
                    if len(deptext)>2400: deptext=deptext[:2400]+'\n[该前置单元仅提供开头，未展示完整证明。]'
                    output.append(_chunk(dep,text=deptext))
            supplement=PdfSupplement(selection['images'],selection['reference']|{'origin':'retrieval'},pages,index,'proof_unit')
            return output,ProofEvidence(unit,linked,unresolved,supplement)
        except (OSError,ValueError,KeyError,RuntimeError) as exc:
            logging.getLogger(__name__).warning('证明关联失败：%s',type(exc).__name__)
    return sources,None
