"""当前 PDF 版本的字符位置与结构化原文对齐；只读访问已构建索引。"""
import hashlib
import json
import sqlite3
import zlib
from functools import lru_cache
from contextlib import closing
from pathlib import Path
import fitz
from knowledge.grounding_text import NORMALIZATION,normalized, normalized_with_map, selection_ranges
from knowledge.course_config import PSYCHOLOGY_DIR

SCHEMA = 'citation-grounding-v1'
POINTER = PSYCHOLOGY_DIR / 'citation_index.json'


def _rectangles(glyphs):
    lines = {}
    for page, line, x1, y1, x2, y2 in glyphs:
        key = (page, line)
        if key not in lines:
            lines[key] = [x1, y1, x2, y2]
        else:
            box = lines[key]
            box[:] = [min(box[0], x1), min(box[1], y1), max(box[2], x2), max(box[3], y2)]
    return [dict(page=page, x1=max(0, box[0]-.0005), y1=max(0, box[1]-.0005),
                 x2=min(1, box[2]+.0005), y2=min(1, box[3]+.0005)) for (page, _), box in lines.items()]


def pdf_characters(path):
    text, glyphs, pages = [], [], []
    with fitz.open(path) as pdf:
        for number, page in enumerate(pdf, 1):
            matrix=page.rotation_matrix
            width,height=page.rect.width,page.rect.height
            pages.append({'page': number, 'rotation': page.rotation, 'width': width, 'height': height})
            line_id = 0
            for block in page.get_text('rawdict', sort=True)['blocks']:
                for line in block.get('lines', []):
                    line_id += 1
                    for span in line['spans']:
                        for char in span['chars']:
                            # 原始坐标属于未旋转页面，先转到 PDF.js 展示的可见页面坐标。
                            rect = fitz.Rect(char['bbox']) * matrix
                            for character in char['c']:
                                text.append(character)
                                glyphs.append([number, line_id, rect.x0/width, rect.y0/height,
                                               rect.x1/width, rect.y1/height])
                    text.append('\n');glyphs.append(None)
    return ''.join(text), glyphs, pages


def build_index(target, course_dir=PSYCHOLOGY_DIR):
    """target 必须是新文件；构建不能覆盖服务使用的文件。"""
    target = Path(target)
    if target.exists():
        raise ValueError('构建目标已存在，请使用新的构建目录')
    target.parent.mkdir(parents=True, exist_ok=True)
    registry = json.loads((course_dir/'pdf_manifest.json').read_text(encoding='utf-8'))
    report = {'schema': SCHEMA, 'documents': [], 'blocks': 0, 'exact': 0, 'ambiguous': 0, 'unmatched': 0}
    with closing(sqlite3.connect(target)) as db,db:
        db.executescript('''CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
          CREATE TABLE documents(id TEXT PRIMARY KEY,version TEXT NOT NULL,chapter INTEGER NOT NULL,payload BLOB NOT NULL);
          CREATE TABLE blocks(document_id TEXT,block_id INTEGER,section_id INTEGER,kind TEXT,text TEXT,
            status TEXT,start INTEGER,end INTEGER,rects TEXT,PRIMARY KEY(document_id,block_id));''')
        db.execute('INSERT INTO metadata VALUES(?,?)', ('schema', SCHEMA))
        db.execute('INSERT INTO metadata VALUES(?,?)', ('normalization', NORMALIZATION))
        for record in registry:
            directory = course_dir/'chapters'/f"chapter_{record['chapter_id']:02d}"
            path = directory/f"chapter_{record['chapter_id']:02d}.generated.pdf"
            if hashlib.sha256(path.read_bytes()).hexdigest() != record['version']:
                raise ValueError('PDF 与清单版本不同，不能构建引用索引')
            text, glyphs, pages = pdf_characters(path)
            folded, mapping = normalized_with_map(text)
            document = json.loads((directory/'document.json').read_text(encoding='utf-8'))
            blocks = [b for b in document['blocks'] if b['text'].strip() or b.get('rows')]
            needles = [normalized(b['text'] if b['kind']!='table' else '\n'.join(' '.join(row) for row in b['rows'])) for b in blocks]
            positions = []
            for needle in needles:
                matches, cursor = [], 0
                if needle:
                    while (found := folded.find(needle, cursor)) >= 0:
                        matches.append((found, found+len(needle)));cursor=found+1
                positions.append(matches)
            previous_end = 0
            counts = {'exact': 0, 'ambiguous': 0, 'unmatched': 0}
            for index, block in enumerate(blocks):
                matches = positions[index]
                if len(matches)>1:
                    # 重复文字须由顺序及后续唯一原文夹定，不能直接取首次匹配。
                    next_start = next((items[0][0] for items in positions[index+1:] if len(items)==1 and items[0][0]>=previous_end), len(folded))
                    matches = [span for span in matches if span[0]>=previous_end and span[1]<=next_start]
                status = 'exact' if len(matches)==1 else 'ambiguous' if matches else 'unmatched'
                start = end = None;rects=[]
                if status=='exact':
                    a,b=matches[0];start,end=mapping[a],mapping[b-1]+1
                    rects=_rectangles([g for g in glyphs[start:end] if g])
                    previous_end=max(previous_end,b)
                value=block['text'] if block['kind']!='table' else '\n'.join(' '.join(row) for row in block['rows'])
                db.execute('INSERT INTO blocks VALUES(?,?,?,?,?,?,?,?,?)',
                    (record['document_id'], block['block_index'],block.get('section_id',1),block['kind'],value,status,start,end,json.dumps(rects)))
                counts[status]+=1
            payload=zlib.compress(json.dumps({'text':text,'glyphs':glyphs,'pages':pages},ensure_ascii=False).encode())
            db.execute('INSERT INTO documents VALUES(?,?,?,?)',(record['document_id'],record['version'],record['chapter_id'],payload))
            entry={'document_id':record['document_id'],'version':record['version'],'blocks':len(blocks),**counts}
            report['documents'].append(entry);report['blocks']+=len(blocks)
            for key,value in counts.items():report[key]+=value
    return report


class CitationIndex:
    def __init__(self, path):
        self.path=Path(path).resolve()
        self.db=sqlite3.connect(f'{self.path.as_uri()}?mode=ro',uri=True)
        self.db.row_factory=sqlite3.Row
        try:
            schema=self.db.execute('SELECT value FROM metadata WHERE key=?',('schema',)).fetchone()
            if not schema or schema[0]!=SCHEMA:raise ValueError('引用索引结构不兼容')
            policy=self.db.execute('SELECT value FROM metadata WHERE key=?',('normalization',)).fetchone()
            if not policy or policy[0]!=NORMALIZATION:raise ValueError('引用规范化规则已变化，请重建独立索引')
        except (sqlite3.Error,ValueError) as exc:
            self.db.close();raise ValueError('引用索引不兼容或损坏，请重建独立索引') from exc
        self._documents={}

    def close(self):self.db.close()

    def document(self, document_id, version):
        row=self.db.execute('SELECT * FROM documents WHERE id=?',(document_id,)).fetchone()
        if not row or row['version']!=version:raise ValueError('引用索引的教材版本已失效')
        if document_id not in self._documents:self._documents[document_id]=json.loads(zlib.decompress(row['payload']))
        return self._documents[document_id]

    def blocks(self, document_id, start=None, end=None):
        rows=self.db.execute('SELECT * FROM blocks WHERE document_id=? ORDER BY block_id',(document_id,)).fetchall()
        return [dict(r) for r in rows if (start is None or r['block_id']>=start) and (end is None or r['block_id']<=end)]

    def locate(self, document_id, version, quote, *, block_id=None):
        document=self.document(document_id,version)
        if block_id is not None:
            blocks=self.blocks(document_id,block_id,block_id)
            if not blocks or blocks[0]['status']!='exact':return {'status':'ambiguous' if blocks and blocks[0]['status']=='ambiguous' else 'unlocated','rects':[]}
            block=blocks[0];start,end=block['start'],block['end']
        else:start,end=0,len(document['text'])
        matches=selection_ranges(document['text'][start:end],quote)
        if len(matches)!=1:return {'status':'ambiguous' if matches else 'unlocated','rects':[]}
        a,b=matches[0];a+=start;b+=start
        return {'status':'exact','start':a,'end':b,'rects':_rectangles([g for g in document['glyphs'][a:b] if g])}


@lru_cache(maxsize=2)
def _live_document(path, version):
    text, glyphs, pages = pdf_characters(path)
    if hashlib.sha256(path.read_bytes()).hexdigest() != version:
        raise ValueError('教材在定位过程中发生变化')
    folded,mapping=normalized_with_map(text)
    return {'text': text, 'glyphs': glyphs, 'pages': pages, 'folded':folded, 'mapping':mapping}


class LiveCitationIndex:
    """没有已发布坐标索引时，直接核验当前原件；不创建或启用索引。"""
    def __init__(self):
        from knowledge.pdf_reader import documents
        self.records = {r['document_id']: r for r in documents()}

    def close(self):
        pass

    def document(self, document_id, version):
        from knowledge.pdf_reader import pdf_path
        record = self.records.get(document_id)
        if not record or record['version'] != version:
            raise ValueError('引用教材版本已失效')
        path = pdf_path(record)
        if hashlib.sha256(path.read_bytes()).hexdigest() != version:
            raise ValueError('引用教材文件已变化')
        return _live_document(path, version)

    def blocks(self, document_id, start=None, end=None):
        record = self.records[document_id]
        document = self.document(document_id, record['version'])
        path = PSYCHOLOGY_DIR/'chapters'/f'chapter_{record["chapter_id"]:02d}'/'document.json'
        result = []
        for block in json.loads(path.read_text(encoding='utf-8'))['blocks']:
            number = block['block_index']
            if (start is not None and number < start) or (end is not None and number > end):
                continue
            text = block['text'] if block['kind'] != 'table' else '\n'.join(' '.join(row) for row in block['rows'])
            needle=normalized(text)
            position=document['folded'].find(needle) if needle else -1
            unique=position>=0 and document['folded'].find(needle,position+1)<0
            a,b=(document['mapping'][position],document['mapping'][position+len(needle)-1]+1) if unique else (None,None)
            result.append({'block_id': number, 'section_id': block.get('section_id', 1), 'text': text,
                           'start': a, 'end': b, 'status': 'exact' if unique else 'ambiguous' if position>=0 else 'unlocated'})
        return result

    locate = CitationIndex.locate
