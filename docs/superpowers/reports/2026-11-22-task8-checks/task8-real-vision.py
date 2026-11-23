from pathlib import Path
import os,sys,json,asyncio,base64,hashlib
from urllib.parse import urlsplit
h=Path.cwd();v=h.parents[1]/'vendor/DeepTutor';run=h/'.runtime/browser-check-12d290667b'
sys.path[:0]=[str(h),str(v),str(run/'python-deps')]
sys.path.append('E:/项目/heart/project/integration/discrete-math-tutor/.venv-deeptutor/Lib/site-packages')
from dotenv import load_dotenv
load_dotenv('E:/项目/heart/project/integration/discrete-math-tutor/.env')
config={'base_url':os.getenv('OPENAI_BASE_URL','https://api.deepseek.com'),'model':os.getenv('DEEPSEEK_MODEL') or os.getenv('OPENAI_MODEL','deepseek-flash'),'api_key':os.getenv('DEEPSEEK_API_KEY') or os.getenv('OPENAI_API_KEY')}
url=urlsplit(config['base_url']);assert url.scheme=='https' and url.hostname=='api.deepseek.com' and not url.username and not url.query
assert config['model']=='deepseek-flash' and config['api_key']
from PIL import Image,ImageDraw,ImageFont
from integrations.deeptutor.screenshot_intake import recognize,ScreenshotReading
font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',28)
report={'endpoint':'api.deepseek.com','model':config['model'],'ocr_model_added':False,'source':'agent-authored synthetic images; no private screenshot or textbook scan','cases':[]}
async def check():
 for label,lines in [('complete',['心理学练习（测试自编题）','题目：哪一种设计只测量变量关系，不操纵变量？','A. 相关设计    B. 真正的实验设计','学生作答：A','参考答案：A']),('incomplete',['心理学练习（测试自编题）','题目：哪一种设计只测量变量关系，不操纵变量？','A. 相关设计    B. [选项被裁掉]','学生作答：[无法辨认]'])]:
  image=Image.new('RGB',(1100,340),'white');draw=ImageDraw.Draw(image)
  for i,line in enumerate(lines):draw.text((28,24+i*54),line,font=font,fill='black')
  path=run/('task8-vision-'+label+'.png');image.save(path)
  data=base64.b64encode(path.read_bytes()).decode()
  raw=await recognize(config,'请核对这张自编测试题截图，区分学生作答、参考答案和缺失内容。',[{'type':'image_url','image_url':{'url':'data:image/png;base64,'+data}}])
  (run/("task8-real-vision-"+label+"-raw.json")).write_text(raw,encoding="utf-8")
  reading=ScreenshotReading.model_validate_json(raw)
  case={'label':label,'image_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'reading':reading.model_dump(),'ready':reading.ready,'assisted':reading.assisted}
  report['cases'].append(case)
  (run/'task8-real-vision.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
  if label=='complete':assert reading.ready and reading.student_answer.strip()=='A' and reading.assisted,case
  else:assert not reading.ready,case
 report['passed']=True
 (run/'task8-real-vision.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
asyncio.run(check())
print(json.dumps({'passed':True,'model':config['model'],'cases':len(report['cases'])}))
