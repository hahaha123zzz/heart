"""把正式教材全书转换为原项目可加载的资源，不接触学生数据库。"""
import json,sys
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.import_psychology_sample import COURSE,NS,SECTION,chapter_groups,digest,write_json,write_chapter
from scripts.parse_converted_textbook import parse_document

def import_all(*,refresh_text=False):
    course=ROOT/'knowledge/courses'/COURSE
    manifest=json.loads((course/'manifest.json').read_text(encoding='utf-8'))
    source=course/'source/textbook.docx'
    if digest(source.read_bytes())!=manifest['source_sha256']['textbook.docx']:
        raise ValueError('原始教材版本与清单不一致')
    report=[]
    with ZipFile(source) as package:
        xml=package.read('word/document.xml');body=ET.fromstring(xml).find('w:body',NS)
        groups=chapter_groups(body)
        for group in groups:
            number=group['id'];folder=course/'chapters'/f'chapter_{number:02d}'
            assets=folder/'assets';assets.mkdir(parents=True,exist_ok=True)
            path=folder/f'第{number}章{group["title"]}.docx'
            if refresh_text:
                if not path.is_file():raise ValueError('刷新文本要求已存在的章节DOCX：'+str(path))
            else:
                write_chapter(package,xml,group['nodes'],body.find('w:sectPr',NS),path)
            source_label=f'第{number}章{group["title"]}.txt'
            document,chunks,media=parse_document(path,source_label,assets,sections=group['sections'],heading_pattern=SECTION)
            formulas=[]
            for index,node in enumerate(group['nodes']):
                for math in node.findall('.//m:oMath',NS):
                    ident=f'omml-{len(formulas)+1:03d}';target=assets/(ident+'.xml')
                    target.write_bytes(ET.tostring(math,encoding='utf-8'))
                    formulas.append({'id':f'{COURSE}:chapter-{number:02d}:{ident}','block_index':index,
                                     'path':str(target.relative_to(folder)).replace('\\','/'),'status':'raw_omml_requires_pdf_verification'})
            document['course_id']=COURSE;document['omml_objects']=formulas
            for chunk in chunks:chunk['course_id']=COURSE
            write_json(folder/'document.json',document);write_json(folder/'assets.json',media);write_json(folder/'formulas.json',formulas)
            (folder/'chunks.jsonl').write_text('\n'.join(json.dumps(c,ensure_ascii=False) for c in chunks),encoding='utf-8')
            (folder/'text.txt').write_text('\n\n'.join(b['text'] for b in document['blocks'] if b['text']),encoding='utf-8')
            actual={b.get('section_id') for b in document['blocks'] if b.get('section_id')}
            if actual!={s['id'] for s in group['sections']}:raise ValueError(f'第{number}章节边界不完整')
            for asset in media:
                if not (folder/asset['filename']).is_file():raise ValueError(f'第{number}章资源文件缺失')
            row={'chapter_id':number,'title':group['title'],'sections':len(group['sections']),
                 'blocks':len(document['blocks']),'tables':sum(b['kind']=='table' for b in document['blocks']),
                 'assets':len(media),'omml':len(formulas),'docx':str(path.relative_to(course)).replace('\\','/'),
                 'source_sha256':digest(path.read_bytes())}
            report.append(row);print(json.dumps(row,ensure_ascii=False),flush=True)
    if len(report)!=11 or sum(r['sections'] for r in report)!=37:raise ValueError('全书章节数量不符')
    if sum(r['omml'] for r in report)!=sum(c['omml_objects'] for c in manifest['chapters']):raise ValueError('公式对象数量不符')
    status=manifest['full_import']['status'] if refresh_text else 'parsed_requires_pdf'
    manifest['full_import']={'status':status,'chapters':report}
    write_json(course/'manifest.json',manifest)
    write_json(course/'import_report.json',report)
    return report

if __name__=='__main__':import_all(refresh_text='--refresh-text' in sys.argv)
