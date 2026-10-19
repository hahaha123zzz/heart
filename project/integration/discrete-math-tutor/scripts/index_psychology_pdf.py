"""核验全书Word节页码并建立现有PDF阅读器所用的注册表。"""
import json,sys
from pathlib import Path
import fitz
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.import_psychology_sample import COURSE,digest,write_json

def compact(text):return ''.join(text.split())

def index_pdfs():
    course=ROOT/'knowledge/courses'/COURSE
    manifest=json.loads((course/'manifest.json').read_text(encoding='utf-8'));records=[]
    for chapter in manifest['full_import']['chapters']:
        number=chapter['chapter_id'];folder=course/'chapters'/f'chapter_{number:02d}'
        path=folder/f'chapter_{number:02d}.generated.pdf'
        word=json.loads((folder/'word_pages.json').read_text(encoding='utf-8'))
        if digest(path.read_bytes())!=word['pdf_sha256'] or word['source_sha256']!=chapter['source_sha256']:
            raise ValueError(f'第{number}章版本不一致')
        sections=[];pages=[]
        with fitz.open(path) as pdf:
            for number_page,page in enumerate(pdf,1):
                pages.append({'page':number_page,'width':page.rect.width,'height':page.rect.height,'text':page.get_text(sort=True)})
            for section in word['sections']:
                page=pdf[section['generated_page']-1];matches=[]
                for block in page.get_text('dict')['blocks']:
                    for line in block.get('lines',[]):
                        text=''.join(span['text'] for span in line['spans'])
                        if compact(text)==compact(section['title']):matches.append(line['bbox'])
                if len(matches)!=1:raise ValueError(f'第{number}章节标题坐标无法唯一核验：{section["title"]}')
                box=matches[0];rect={'page':section['generated_page'],'x1':box[0]/page.rect.width,
                                   'y1':box[1]/page.rect.height,'x2':box[2]/page.rect.width,'y2':box[3]/page.rect.height}
                sections.append(section|{'page':section['generated_page'],'y':rect['y1'],'rect':rect,'verified':True})
            record={'course_id':COURSE,'document_id':f'{COURSE}:chapter-{number:02d}','chapter_id':number,
                    'title':compact(chapter['title']),'source':f'第{number}章{chapter["title"]}.txt',
                    'source_sha256':chapter['source_sha256'],'version':word['pdf_sha256'],
                    'page_count':len(pdf),'page_policy':'generated_pdf_pages','sections':sections,'pages':pages}
        write_json(folder/'pdf_locations.json',record);records.append(record)
        print(json.dumps({'chapter':number,'pages':record['page_count'],'verified_sections':len(sections)},ensure_ascii=False),flush=True)
    if len(records)!=11 or sum(len(r['sections']) for r in records)!=37:raise ValueError('PDF注册表不完整')
    write_json(course/'pdf_manifest.json',records)
    manifest['full_import']['status']='pdf_headings_verified_requires_visual_review'
    write_json(course/'manifest.json',manifest)
    return records

if __name__=='__main__':index_pdfs()
