"""从 startup-traces 生成分段耗时报告；只读 JSONL，不再访问服务。"""
from __future__ import annotations
import argparse,json,statistics
from datetime import datetime
from pathlib import Path

# 总量、里程碑和事件流不参与阶段排名，避免把 100% 总耗时当成最慢阶段。
MARKERS={'fixed_book.entry','fixed_book.ready_flag','fixed_book.start.complete','fixed_book.start.failed',
         'host.health.first_ok','control.begin','control.done','control.failed',
         'worker.entry','worker.vendor_import','worker.app_import','worker.ready_to_listen',
         'sample.begin','sample.login','sample.connected','sample.done','sample.turn'}


def load(directory):
    rows=[]
    for path in sorted(Path(directory).rglob('*.jsonl')):
        for line in path.read_text(encoding='utf-8').splitlines():
            if not line.strip():continue
            try:rows.append(json.loads(line))
            except json.JSONDecodeError:continue
    return rows


def group(rows):
    grouped={}
    for row in rows:grouped.setdefault(row['startup_id'],[]).append(row)
    return grouped


def complete_ids(rows):
    return {row['startup_id'] for row in rows
            if row['stage']=='fixed_book.start.complete' and row['status']=='ok'}


def _median(values):
    return statistics.median(values) if values else None


def _seconds(value):
    return '—' if value is None else ('%.2f' % value)


def _effective_parent(row, rows):
    """旧发行把 resident.start 直接挂在 fixed_book；有 schedule 时归到 schedule，避免重复计入顶层。"""
    if row['stage']=='lightrag.resident.start' and any(
            other['startup_id']==row['startup_id'] and other['service']==row['service']
            and other['stage']=='lightrag.resident.schedule' for other in rows):
        return 'lightrag.resident.schedule'
    return row['parent']


def summaries(rows):
    """只统计成功启动：先按 startup 汇总同名阶段，再对自身耗时取中位数。"""
    complete=complete_ids(rows);per={}
    for row in rows:
        if row['startup_id'] not in complete or row['status']!='ok':continue
        if row['service'] in ('probe','sample','control'):continue
        if row['stage'] in MARKERS or row['stage'].startswith(('sample.','probe.')):continue
        key=(row['startup_id'],row['service'],row['stage'])
        parent=_effective_parent(row,rows)
        entry=per.setdefault(key,{'seconds':0.0,'calls':0,'parent':parent})
        entry['seconds']+=row['seconds'];entry['calls']+=1
    children={}
    for (sid,service,stage),entry in per.items():
        if entry['parent']:
            key=(sid,service,entry['parent'])
            children[key]=children.get(key,0.0)+entry['seconds']
    aggregated={}
    for (sid,service,stage),entry in per.items():
        own=max(0.0,entry['seconds']-children.get((sid,service,stage),0.0))
        agg=aggregated.setdefault((service,stage),{'own':[],'calls':0,'parent':entry['parent']})
        agg['own'].append(own);agg['calls']+=entry['calls']
    baselines=[row['seconds'] for row in rows
               if row['stage']=='fixed_book.start.complete' and row['status']=='ok']
    baseline=_median(baselines)
    result=[]
    for (service,stage),agg in aggregated.items():
        median=_median(agg['own'])
        result.append({'service':service,'stage':stage,'parent':agg['parent'],
            'calls':agg['calls'],'startups':len(agg['own']),'median':median,
            'minimum':min(agg['own']),'maximum':max(agg['own']),
            'share':(median/baseline) if baseline else None})
    return sorted(result,key=lambda row:(-(row['median'] or 0),row['service'],row['stage'])),baseline


def reconciliation(rows):
    result=[]
    for sid in sorted(complete_ids(rows)):
        items=[row for row in rows if row['startup_id']==sid and row['service']=='host' and row['status']=='ok']
        total=next((row['seconds'] for row in items if row['stage']=='fixed_book.start.complete'),None)
        top=sum(row['seconds'] for row in items
                if _effective_parent(row,rows) in ('fixed_book','warmup') and row['stage'] not in MARKERS)
        result.append({'startup_id':sid,'total':total,'stages':top,
                       'residual':(total-top) if total is not None else None})
    return result


def timeline(rows):
    result=[]
    for sid,items in group(rows).items():
        control={row['stage']:row for row in items if row['service']=='control'}
        begin=control.get('control.begin');done=control.get('control.done')
        ready={row['fields'].get('target'):row for row in items
               if row['service']=='control' and row['stage']=='control.ready'}
        probed={row['fields'].get('target'):row for row in items
                if row['service']=='probe' and row['stage']=='probe.first_ok'}
        host={row['stage']:row for row in items if row['service']=='host'}
        turns=[row for row in items if row['service']=='sample' and row['stage']=='sample.turn']
        first_turn=next((row for row in turns if row['fields'].get('turn')=='first'),None)
        health=host.get('host.health.first_ok')
        gap=None
        if first_turn and health:
            gap=(datetime.fromisoformat(first_turn['at'])-datetime.fromisoformat(health['at'])).total_seconds()
        result.append({'startup_id':sid,'at':begin['at'] if begin else None,
            'label':(begin['fields'] if begin else {}).get('label'),
            'cache_state':(begin['fields'] if begin else {}).get('cache_state'),
            'control_total':done['seconds'] if done else None,
            'ready':{name:row['fields'].get('elapsed_since_origin') for name,row in ready.items()},
            'probed':{name:row['seconds'] for name,row in probed.items()},
            'health_first':(health or {}).get('seconds'),
            'fixed_book':(host.get('fixed_book.start.complete') or {}).get('seconds'),
            'ready_gap':gap,
            'first_answer':(first_turn or {}).get('seconds'),
            'second_answer':next((row['seconds'] for row in turns if row['fields'].get('turn')=='second'),None)})
    return sorted(result,key=lambda row:row['at'] or '')


def duplicates(rows):
    result=[]
    for sid,items in group(rows).items():
        host_scan={row['stage']:row for row in items if row['service']=='host'}
        first=host_scan.get('lightrag.manifest.host_textbook')
        second=host_scan.get('fixed_book.hashes')
        if not first or not second:continue
        verify_files=first['fields'].get('files');inventory_files=second['fields'].get('files')
        mergeable=None
        if verify_files is not None and verify_files==inventory_files:
            mergeable=min(first['seconds'],second['seconds'])
        result.append({'startup_id':sid,'verify_active':first['seconds'],'inventory':second['seconds'],
            'verify_files':verify_files,'inventory_files':inventory_files,'mergeable':mergeable})
    return sorted(result,key=lambda row:row['startup_id'])


def control_stages(rows):
    result=[]
    for sid,items in group(rows).items():
        entries={}
        for row in items:
            if row['service']!='control' or row['status']!='ok':continue
            if row['stage'] in ('control.begin','control.done','control.failed'):continue
            entries[row['stage']]=entries.get(row['stage'],0.0)+row['seconds']
        if entries:result.append({'startup_id':sid,'stages':entries})
    return sorted(result,key=lambda row:row['startup_id'])


def render(rows,title='固定教材启动分段报告'):
    grouped=group(rows);complete=complete_ids(rows);single=len(complete)==1
    lines=['# '+title,'','样本数：%d（成功就绪 %d）' % (len(grouped),len(complete)),'','## 时间线','']
    lines.append('| 启动 | 缓存状态 | 控制脚本总计 | 固定教材初始化 | health 首次（自模块初始化） | 就绪→首问 | 首问耗时 | 第二问 |')
    lines.append('| --- | --- | --- | --- | --- | --- | --- | --- |')
    for row in timeline(rows):
        lines.append('| %s | %s | %s | %s | %s | %s | %s | %s |' % (row['startup_id'],row['cache_state'] or '—',
            _seconds(row['control_total']),_seconds(row['fixed_book']),_seconds(row['health_first']),
            _seconds(row['ready_gap']),_seconds(row['first_answer']),_seconds(row['second_answer'])))
    lines+=['','顺序就绪（相对控制脚本起点）与并行探测对照：','']
    lines.append('| 启动 | 顺序 host | 顺序 worker | 顺序 web | 探测 host | 探测 worker | 探测 web |')
    lines.append('| --- | --- | --- | --- | --- | --- | --- |')
    for row in timeline(rows):
        lines.append('| %s | %s | %s | %s | %s | %s | %s |' % (row['startup_id'],
            _seconds(row['ready'].get('host')),_seconds(row['ready'].get('worker')),_seconds(row['ready'].get('web')),
            _seconds(row['probed'].get('host')),_seconds(row['probed'].get('worker')),_seconds(row['probed'].get('web'))))
    lines+=['','控制脚本分段（不参与宿主阶段排名）：','']
    lines.append('| 启动 | 发行校验合计 | 进程创建合计 | 顺序就绪等待合计 |')
    lines.append('| --- | --- | --- | --- |')
    for row in control_stages(rows):
        lines.append('| %s | %s | %s | %s |' % (row['startup_id'],
            _seconds(row['stages'].get('control.release_verify',0)),
            _seconds(row['stages'].get('control.process_start',0)),
            _seconds(row['stages'].get('control.ready',0))))
    summary,baseline=summaries(rows)
    lines+=['','## 阶段自身耗时','','自身耗时 = 该阶段总耗时 − 同启动内子阶段合计；总量和里程碑不参与排名。',
            '占固定教材初始化比例按 %s s 计算。' % _seconds(baseline),'']
    if single:
        lines.append('| 位置 | 阶段 | 父阶段 | 调用 | 实测自身耗时 | 占固定教材 |')
        lines.append('| --- | --- | --- | --- | --- | --- |')
        for row in summary:
            lines.append('| %s | %s | %s | %d | %s | %s |' % (row['service'],row['stage'],row['parent'] or '—',
                row['calls'],_seconds(row['median']),
                '%s%%' % ('%.1f' % (row['share']*100)) if row['share'] is not None else '—'))
    else:
        lines.append('| 位置 | 阶段 | 父阶段 | 调用 | 启动数 | 中位数 | 范围 | 占固定教材 |')
        lines.append('| --- | --- | --- | --- | --- | --- | --- | --- |')
        for row in summary:
            lines.append('| %s | %s | %s | %d | %d | %s | %s–%s | %s |' % (row['service'],row['stage'],
                row['parent'] or '—',row['calls'],row['startups'],_seconds(row['median']),
                _seconds(row['minimum']),_seconds(row['maximum']),
                '%s%%' % ('%.1f' % (row['share']*100)) if row['share'] is not None else '—'))
    lines+=['','## 串行阶段对账','','顶层阶段合计应与固定教材总耗时接近；剩余为未计时的 Python 开销。','']
    lines.append('| 启动 | 固定教材总耗时 | 顶层阶段合计 | 未计时剩余 |')
    lines.append('| --- | --- | --- | --- |')
    for row in reconciliation(rows):
        lines.append('| %s | %s | %s | %s |' % (row['startup_id'],_seconds(row['total']),
            _seconds(row['stages']),_seconds(row['residual'])))
    lines+=['','## 重复目录遍历','','`lightrag.manifest.host_textbook` 与 `fixed_book.hashes` 使用同一教材根和同一 inventory；'
            '仅在文件数一致时给出可合并范围（两者较小值，保守估计）。','']
    lines.append('| 启动 | verify_active | 再次 inventory | 文件数 | 可合并范围 |')
    lines.append('| --- | --- | --- | --- | --- |')
    for row in duplicates(rows):
        lines.append('| %s | %s | %s | %s / %s | %s |' % (row['startup_id'],_seconds(row['verify_active']),
            _seconds(row['inventory']),row['verify_files'],row['inventory_files'],
            _seconds(row['mergeable']) if row['mergeable'] is not None else '范围不一致'))
    return '\n'.join(lines)+'\n'


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--startup-id',action='append');parser.add_argument('--output',type=Path)
    args=parser.parse_args();root=args.root.resolve(strict=True)
    rows=load(root/'private'/'startup-traces')
    if args.startup_id:rows=[row for row in rows if row['startup_id'] in set(args.startup_id)]
    if not rows:raise SystemExit('没有分段记录')
    report=render(rows)
    if args.output:args.output.write_text(report,encoding='utf-8')
    else:print(report)


if __name__=='__main__':main()
