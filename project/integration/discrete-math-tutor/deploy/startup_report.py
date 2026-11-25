"""从 startup-traces 生成分段耗时报告；只读 JSONL，不再访问服务。"""
from __future__ import annotations
import argparse,json,statistics
from pathlib import Path


def load(directory):
    rows=[]
    for path in sorted(Path(directory).glob('*.jsonl')):
        rows.extend(json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip())
    return rows


def group(rows):
    grouped={}
    for row in rows:grouped.setdefault(row['startup_id'],[]).append(row)
    return grouped


def _median(values):
    return statistics.median(values) if values else None


def _seconds(value):
    return '—' if value is None else ('%.2f' % value)


def summaries(rows):
    entries={}
    for row in rows:
        if row['status']!='ok':continue
        entries.setdefault((row['service'],row['stage']),[]).append(row['seconds'])
    baselines=[row['seconds'] for row in rows if row['stage']=='fixed_book.start.complete' and row['status']=='ok']
    baseline=_median(baselines)
    result=[]
    for (service,stage),values in entries.items():
        median=_median(values)
        result.append({'service':service,'stage':stage,'calls':len(values),'median':median,
                       'minimum':min(values),'maximum':max(values),
                       'share':(median/baseline) if baseline else None})
    return sorted(result,key=lambda row:(-(row['median'] or 0),row['service'],row['stage'])),baseline


def timeline(rows):
    result=[]
    for sid,items in group(rows).items():
        control={row['stage']:row for row in items if row['service']=='control'}
        begin=control.get('control.begin')
        done=control.get('control.done')
        ready={row['fields'].get('target'):row for row in items
               if row['service']=='control' and row['stage']=='control.ready'}
        probed={row['fields'].get('target'):row for row in items
                if row['service']=='probe' and row['stage']=='probe.first_ok'}
        host={row['stage']:row for row in items if row['service']=='host'}
        sample={row['stage']:row for row in items if row['service']=='sample'}
        turns=[row for row in items if row['service']=='sample' and row['stage']=='sample.turn']
        result.append({'startup_id':sid,'at':begin['at'] if begin else None,
            'label':(begin['fields'] if begin else {}).get('label'),
            'cache_state':(begin['fields'] if begin else {}).get('cache_state'),
            'control_total':done['seconds'] if done else None,
            'ready':{name:row['seconds'] for name,row in ready.items()},
            'probed':{name:row['seconds'] for name,row in probed.items()},
            'health_first':(host.get('host.health.first_ok') or {}).get('seconds'),
            'fixed_book':(host.get('fixed_book.start.complete') or {}).get('seconds'),
            'first_answer':next((row['seconds'] for row in turns if row['fields'].get('turn')=='first'),None),
            'second_answer':next((row['seconds'] for row in turns if row['fields'].get('turn')=='second'),None)})
    return sorted(result,key=lambda row:row['at'] or '')


def duplicates(rows):
    result=[]
    for sid,items in group(rows).items():
        host_scan={row['stage']:row for row in items if row['service']=='host'}
        first=host_scan.get('lightrag.manifest.host_textbook')
        second=host_scan.get('fixed_book.hashes')
        if first and second:
            result.append({'startup_id':sid,'verify_active':first['seconds'],
                'inventory':second['seconds'],
                'verify_files':first['fields'].get('files'),
                'inventory_files':second['fields'].get('files'),
                'mergeable':min(first['seconds'],second['seconds'])})
    return sorted(result,key=lambda row:row['startup_id'])


def render(rows,title='固定教材启动分段报告'):
    grouped=group(rows)
    lines=['# '+title,'','样本数：%d' % len(grouped),'','## 时间线','']
    lines.append('| 启动 | 缓存状态 | 控制脚本总计 | 固定教材初始化 | /health 首次 | 第一问 | 第二问 |')
    lines.append('| --- | --- | --- | --- | --- | --- | --- |')
    for row in timeline(rows):
        lines.append('| %s | %s | %s | %s | %s | %s | %s |' % (row['startup_id'],row['cache_state'] or '—',
            _seconds(row['control_total']),_seconds(row['fixed_book']),_seconds(row['health_first']),
            _seconds(row['first_answer']),_seconds(row['second_answer'])))
    lines+=['','控制脚本就绪（顺序阻塞）与并行探测（独立采集）对照：','']
    lines.append('| 启动 | 顺序 host | 顺序 worker | 顺序 web | 探测 host | 探测 worker | 探测 web |')
    lines.append('| --- | --- | --- | --- | --- | --- | --- |')
    for row in timeline(rows):
        lines.append('| %s | %s | %s | %s | %s | %s | %s |' % (row['startup_id'],
            _seconds(row['ready'].get('host')),_seconds(row['ready'].get('worker')),_seconds(row['ready'].get('web')),
            _seconds(row['probed'].get('host')),_seconds(row['probed'].get('worker')),_seconds(row['probed'].get('web'))))
    summary,baseline=summaries(rows)
    single=len(grouped)==1
    lines+=['','## 阶段耗时','','占固定教材初始化比例按 %s s 计算。' % _seconds(baseline),'']
    if single:
        lines.append('| 位置 | 阶段 | 调用 | 实测耗时 | 占固定教材 |')
        lines.append('| --- | --- | --- | --- | --- |')
        for row in summary:
            lines.append('| %s | %s | %d | %s | %s |' % (row['service'],row['stage'],row['calls'],
                _seconds(row['median']),'%s%%' % ('%.1f' % (row['share']*100)) if row['share'] is not None else '—'))
    else:
        lines.append('| 位置 | 阶段 | 调用 | 中位数 | 范围 | 占固定教材 |')
        lines.append('| --- | --- | --- | --- | --- | --- |')
        for row in summary:
            lines.append('| %s | %s | %d | %s | %s–%s | %s |' % (row['service'],row['stage'],row['calls'],
                _seconds(row['median']),_seconds(row['minimum']),_seconds(row['maximum']),
                '%s%%' % ('%.1f' % (row['share']*100)) if row['share'] is not None else '—'))
    lines+=['','## 重复目录遍历','','`lightrag.manifest.host_textbook` 与 `fixed_book.hashes` 使用同一教材根和同一 inventory；'
            '可合并范围取两者较小值。','']
    lines.append('| 启动 | verify_active | 再次 inventory | 文件数 | 可合并上限 |')
    lines.append('| --- | --- | --- | --- | --- |')
    for row in duplicates(rows):
        lines.append('| %s | %s | %s | %s / %s | %s |' % (row['startup_id'],_seconds(row['verify_active']),
            _seconds(row['inventory']),row['verify_files'],row['inventory_files'],_seconds(row['mergeable'])))
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
