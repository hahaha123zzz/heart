"""验收后原子切换独立索引；未达标拒绝启用，支持恢复上一指针。"""
import argparse,hashlib,json,os,shutil,tempfile
from pathlib import Path
from knowledge.citation_index import CitationIndex,POINTER,SCHEMA
from knowledge.pdf_reader import documents,pdf_path

GATES=('known_failure','semantic_support','exact_precision','exact_coverage','crops','negatives','data_protection','stability')


def atomic_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent,delete=False) as handle:
        handle.write(json.dumps(value,ensure_ascii=False,indent=2).encode());name=handle.name
    os.replace(name,path)


def verified_pointer(pointer):
    if not pointer.get('enabled'):return
    path=(POINTER.parent/pointer['path']).resolve()
    if not path.is_relative_to(POINTER.parent.resolve()):raise ValueError('索引路径越界')
    if hashlib.sha256(path.read_bytes()).hexdigest()!=pointer['sha256']:raise ValueError('索引文件已变化')
    index=CitationIndex(path)
    try:
        for record in documents():
            if hashlib.sha256(pdf_path(record).read_bytes()).hexdigest()!=record['version']:raise ValueError('教材版本已变化')
            index.document(record['document_id'],record['version'])
    finally:index.close()


def approved(report,index):
    if report.get('schema')!=SCHEMA or report.get('index_sha256')!=hashlib.sha256(index.read_bytes()).hexdigest():
        raise ValueError('验收报告不属于该索引')
    if any(report.get('gates',{}).get(gate)!='passed' for gate in GATES):
        raise ValueError('发布门槛未全部通过，拒绝切换默认链路')
    metrics=report.get('metrics',{})
    for key,threshold in (('semantic_support',.95),('exact_precision',.98),('exact_coverage',.95)):
        value=metrics.get(key)
        if not isinstance(value,(int,float)) or isinstance(value,bool) or not threshold<=value<=1:
            raise ValueError(f'{key}未达到发布门槛')
    if report.get('real_model_runs',0)<160 or report.get('reviewed_holdout_cases',0)!=30:
        raise ValueError('真实模型执行或留出复核未完成')


def main():
    parser=argparse.ArgumentParser();group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--enable',type=Path);group.add_argument('--disable',action='store_true');group.add_argument('--rollback',action='store_true')
    parser.add_argument('--acceptance',type=Path);args=parser.parse_args()
    previous=POINTER.with_name('citation_index.previous.json')
    current=json.loads(POINTER.read_text(encoding='utf-8')) if POINTER.is_file() else {'enabled':False}
    if args.enable:
        if not args.acceptance:raise ValueError('必须提供验收报告')
        report=json.loads(args.acceptance.read_text(encoding='utf-8'));approved(report,args.enable)
        digest=hashlib.sha256(args.enable.read_bytes()).hexdigest();target=POINTER.parent/'citation-indexes'/f'{digest}.sqlite3'
        target.parent.mkdir(parents=True,exist_ok=True)
        if not target.exists():
            with tempfile.NamedTemporaryFile(dir=target.parent,delete=False) as handle:name=handle.name
            shutil.copyfile(args.enable,name);os.replace(name,target)
        pointer={'enabled':True,'schema':SCHEMA,'path':str(target.relative_to(POINTER.parent)),'sha256':digest,
                 'acceptance_sha256':hashlib.sha256(args.acceptance.read_bytes()).hexdigest()}
    elif args.rollback:
        if not previous.is_file():raise ValueError('没有上一版指针；可使用--disable')
        pointer=json.loads(previous.read_text(encoding='utf-8'))
    else:pointer={'enabled':False}
    verified_pointer(pointer)
    atomic_json(previous,current);atomic_json(POINTER,pointer)
    # 索引只在每轮创建只读连接；教材版本切换须重启服务以清空教材、检索及PDF清单缓存。
    print(json.dumps(pointer,ensure_ascii=False));print('切换后重启服务；CITATION_GROUNDING_MODE=off可立即回退到旧链路。')


if __name__=='__main__':main()
