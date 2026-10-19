"""只发送三个样章问题与相关教材依据，不读取学生数据。"""
import json
from pathlib import Path
import requests

BASE='http://127.0.0.1:8001'
def main():
    data=requests.get(BASE+'/api/textbook-preview/psychology/catalog',timeout=10).json()
    results=[]
    for question in ['什么是被试间设计？请用一个简单例子解释。',
                     '单因素随机区组设计为什么能控制被试的个体差异？',
                     '什么是配对组设计？它如何进行匹配和随机分配？']:
        response=requests.post(BASE+'/api/textbook-preview/psychology/ask',
                               json={'question':question,'version':data['version']},timeout=180)
        response.raise_for_status();answer=response.json()
        results.append({'question':question,**answer})
        Path('artifacts/psychology-qa-acceptance.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'question':question,'status':answer['status'],'reason':answer.get('reason'),
                          'pages':[c['reference']['rects'][0]['page'] for c in answer.get('citations',[])]},ensure_ascii=False),flush=True)
    assert all(r['status']=='completed' and r['citations'] for r in results), '部分真实问答未通过核验，请检查结果文件'

if __name__=='__main__':main()
