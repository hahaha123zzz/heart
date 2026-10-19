"""独立构建引用坐标索引；不自动切换当前服务。"""
import argparse,json
from pathlib import Path
from knowledge.citation_index import build_index

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();report=build_index(args.output.resolve())
    args.output.with_suffix('.report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))
