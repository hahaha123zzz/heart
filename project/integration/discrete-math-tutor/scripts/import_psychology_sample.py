"""正式教材独立暂存，复用Word解析器，不加载main或替换旧教材。"""
import argparse,copy,hashlib,io,json,re,sqlite3,sys
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
from xml.etree import ElementTree as ET
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.parse_converted_textbook import NS,paragraph_text,parse_document
COURSE='experimental-psychology-3'
CHAPTER=re.compile(r'^第([一二三四五六七八九十]+)章$')
SECTION=re.compile(r'^第[一二三四五六七八九十]+节\s*\S')
NUMBERS=['一','二','三','四','五','六','七','八','九','十','十一']
def digest(data):return hashlib.sha256(data).hexdigest()
def write_json(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')

def write_chapter(package, xml, nodes, sect_pr, target):
    chapter_body=b''.join(ET.tostring(n,encoding='utf-8') for n in nodes)
    if sect_pr is not None:chapter_body+=ET.tostring(sect_pr,encoding='utf-8')
    boundary=re.search(br'<w:body>(.*?)</w:body>',xml,re.S)
    if not boundary:raise ValueError('不支持的DOCX正文边界')
    rewritten=xml[:boundary.start(1)]+chapter_body+xml[boundary.end(1):]
    ET.fromstring(rewritten)
    with ZipFile(target,'w',ZIP_DEFLATED) as out:
        # writestr会修改ZipInfo偏移量；批量拆章时必须保留输入包的原始目录。
        for entry in package.infolist():out.writestr(copy.copy(entry),rewritten if entry.filename=='word/document.xml' else package.read(entry))
def chapter_groups(body):
    groups=[];current=None
    for index,node in enumerate(body):
        if node.tag=='{'+NS['w']+'}sectPr':continue
        text=paragraph_text(node);match=CHAPTER.fullmatch(text)
        if match and node.tag=='{'+NS['w']+'}p':
            number=NUMBERS.index(match[1])+1
            if number!=len(groups)+1:raise ValueError('本书章节编号不连续')
            current={'id':number,'title':'','sections':[],'nodes':[],'body_start':index};groups.append(current)
        if current is None:continue
        if not current['title'] and text and not match:current['title']=text
        if SECTION.match(text) and node.tag=='{'+NS['w']+'}p':
            current['sections'].append({'id':len(current['sections'])+1,'title':' '.join(text.split()),'body_index':index})
        current['nodes'].append(node)
    if len(groups)!=11:raise ValueError('正式教材应为11章')
    return groups
def import_book(archive_path):
    target=ROOT/'knowledge/courses'/COURSE;source=target/'source';sample=target/'sample';assets=sample/'assets'
    for directory in (source,sample,assets):directory.mkdir(parents=True,exist_ok=True)
    raw=archive_path.read_bytes()
    with ZipFile(io.BytesIO(raw)) as archive:
        entries=[e for e in archive.infolist() if e.filename.lower().endswith('.docx')]
        if len(entries)!=2 or sum(e.file_size for e in entries)>64*1024*1024:raise ValueError('附件格式或大小不符合预期')
        entries.sort(key=lambda e:e.file_size)
        files={name:archive.read(entry) for name,entry in zip(('frontmatter.docx','textbook.docx'),entries)}
    for name,data in files.items():
        p=source/name
        if p.exists() and digest(p.read_bytes())!=digest(data):raise ValueError('同课程原始文件已变更，须建立新版本')
        p.write_bytes(data)
    with ZipFile(io.BytesIO(files['textbook.docx'])) as package:
        xml=package.read('word/document.xml');root=ET.fromstring(xml);body=root.find('w:body',NS)
        groups=chapter_groups(body);catalog=[]
        for group in groups:
            nodes=group['nodes'];catalog.append({k:v for k,v in group.items() if k!='nodes'}|{
                'tables':sum(n.tag=='{'+NS['w']+'}tbl' for n in nodes),
                'omml_objects':sum(len(n.findall('.//m:oMath',NS)) for n in nodes),
                'block_count':len(nodes)})
        chosen=groups[3];sample_path=sample/'第4章被试间设计.docx'
        section=body.find('w:sectPr',NS)
        write_chapter(package,xml,chosen['nodes'],section,sample_path)
        formulas=[]
        for index,node in enumerate(chosen['nodes']):
            for math in node.findall('.//m:oMath',NS):
                ident=f'{COURSE}:chapter-04:omml-{len(formulas)+1:03d}'
                path=assets/(ident.rsplit(':',1)[-1]+'.xml');path.write_bytes(ET.tostring(math,encoding='utf-8'))
                formulas.append({'id':ident,'block_index':index,'path':str(path.relative_to(target)).replace('\\','/'),'status':'raw_omml_requires_pdf_verification'})
    document,chunks,media=parse_document(sample_path,'第4章被试间设计.txt',assets,sections=chosen['sections'],heading_pattern=SECTION)
    document['course_id']=COURSE;document['omml_objects']=formulas
    for record in chunks:record['course_id']=COURSE
    write_json(sample/'document.json',document);write_json(sample/'assets.json',media);write_json(sample/'formulas.json',formulas)
    (sample/'chunks.jsonl').write_text('\n'.join(json.dumps(c,ensure_ascii=False) for c in chunks),encoding='utf-8')
    (sample/'text.txt').write_text('\n\n'.join(b['text'] for b in document['blocks'] if b['text']),encoding='utf-8')
    manifest={'course_id':COURSE,'title':'实验心理学（第3版）','status':'staging','archive_sha256':digest(raw),'source_sha256':{n:digest(d) for n,d in files.items()},'chapters':catalog,'sample_chapter':4,'pdf_page_policy':'generated_pages_not_verified_printed_pages','sample_assets':len(media),'sample_omml':len(formulas)}
    write_json(target/'manifest.json',manifest)
    print(json.dumps({'chapters':len(groups),'sections':sum(len(c['sections']) for c in catalog),'sample_blocks':len(document['blocks']),'assets':len(media),'formulas':len(formulas)},ensure_ascii=False))
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('archive',type=Path);args=parser.parse_args();import_book(args.archive)
