"""纯导航隔离宿主，使用实际web_api/前端/PDF；无模型，不连接正式学生库。"""
import argparse,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True);parser.add_argument('--port',type=int,default=18981);args=parser.parse_args();out=args.out.resolve();out.mkdir(parents=True,exist_ok=True)
 os.environ['DATABASE_URL']='sqlite:///:memory:';os.environ['COURSE_DATABASE_URL']='sqlite:///'+str(out/'unused-student.sqlite3');os.environ['TUTOR_COURSE']='experimental-psychology-3'
 from fastapi import FastAPI,HTTPException
 from fastapi.responses import FileResponse
 from fastapi.staticfiles import StaticFiles
 from web_api import router
 from knowledge.pdf_reader import document,pdf_path
 from knowledge.figures import get_figure
 from knowledge.answer_media import selected_media
 from knowledge.visual_locations import resolve_figure
 import uvicorn,mimetypes
 mimetypes.add_type('application/javascript','.js');mimetypes.add_type('application/javascript','.mjs')
 app=FastAPI();app.include_router(router);app.mount('/static',StaticFiles(directory=ROOT/'frontend'),name='static')
 @app.middleware('http')
 async def record(request,call_next):
  response=await call_next(request)
  with (out/'requests.jsonl').open('a',encoding='utf-8') as log:log.write(json.dumps({'method':request.method,'path':request.url.path,'status':response.status_code})+'\n')
  return response
 @app.get('/')
 def index():return FileResponse(ROOT/'frontend/index.html')
 @app.get('/api/pdf/documents/{document_id}/file')
 def pdf(document_id:str):
  row=document(document_id)
  if not row:raise HTTPException(404)
  return FileResponse(pdf_path(row),media_type='application/pdf')
 @app.get('/api/figures/{figure_id}/image')
 def image(figure_id:str,sha256:str='',version:str='',document_id:str=''):
  figure=get_figure(figure_id)
  if not figure:raise HTTPException(404)
  public=figure.public()
  if any(saved and saved!=public[field] for saved,field in [(sha256,'sha256'),(version,'version'),(document_id,'document_id')]):raise HTTPException(410)
  return FileResponse(figure.path)
 @app.get('/__test__/fixtures')
 def fixtures():
  media=[]
  for asset_id in ['image-01-0004','image-01-0005','image-07-0003','image-08-0001','image-09-0001']:
   f=get_figure(asset_id);pub=f.public();source=dict(chapter_id=f.chapter_id,section_id=f.section_id,document_id=pub['document_id'],version=pub['version'],text='deterministic source fixture')
   item=selected_media(f.label,[source],asset_id=f.id)[0];media.append(item)
  old=json.loads(json.dumps(media[0]));old['location_status']='section';old['selection_ref'].update(rects=[],kind='text',location_status='section',text='历史回答普通检索段落，不用于定位图注')
  return dict(media=media,legacy=old)
 uvicorn.run(app,host='127.0.0.1',port=args.port,log_level='warning')
if __name__=='__main__':main()
