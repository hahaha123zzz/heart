"""独立样章阅读与问答服务，不初始化学习数据库。"""
import sys,mimetypes
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT/'.env')
load_dotenv(ROOT/'deepseek.env')
mimetypes.add_type('application/javascript','.js')
mimetypes.add_type('application/javascript','.mjs')
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from course_preview_api import router
import uvicorn
app=FastAPI(title='实验心理学样章预览');app.include_router(router)
app.mount('/static',StaticFiles(directory=ROOT/'frontend'))
@app.get('/')
def home():return RedirectResponse('/textbook-preview/psychology')
if __name__=='__main__':uvicorn.run(app,host='127.0.0.1',port=8001)
