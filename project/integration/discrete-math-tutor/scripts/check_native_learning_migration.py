"""从只读Q5快照验证隔离原生候选，不启用线上迁移或修改原数据库。"""
import argparse
import asyncio
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from integrations.deeptutor.worker import VENDOR_ROOT
from integrations.deeptutor.learning_migration import read_snapshots, import_candidate, fingerprint


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-snapshot', required=True, type=Path)
    parser.add_argument('--student', required=True)
    parser.add_argument('--course', required=True)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--bind-sessions', action='store_true', help='在隔离原生home建立真实账户/工作区/会话绑定')
    parser.add_argument('--verify-sources', action='store_true', help='用当前宿主Q2重新核验候选来源，不激活路径')
    args = parser.parse_args()
    output = args.output.resolve()
    allowed = ROOT / '.runtime' / 'native-learning-migration'
    if not output.is_relative_to(allowed) or output == allowed:
        parser.error('输出必须是应用.runtime/native-learning-migration下的独立候选目录')
    source = args.source_snapshot.resolve()
    if not source.is_file() or source.is_relative_to(output):
        parser.error('原快照必须存在，且不能位于输出目录内')
    pin = json.loads((VENDOR_ROOT / 'UPSTREAM_SNAPSHOT.json').read_text(encoding='utf-8'))
    hashes = {}
    for relative in ('deeptutor/learning/models.py', 'deeptutor/learning/storage.py',
                     'deeptutor/learning/service.py', 'deeptutor/learning/objective_relations.py'):
        hashes[relative] = hashlib.sha256((VENDOR_ROOT / relative).read_bytes()).hexdigest()
        if hashes[relative] != pin['files'][relative]:
            raise ValueError('上游源码与固定清单不一致：' + relative)
    if args.bind_sessions:
        from integrations.deeptutor.worker import prepare
        prepare(output / 'native-home', 18001)
    else:
        sys.path.insert(0, str(VENDOR_ROOT))
    import deeptutor
    from deeptutor.learning.storage import LearningStore
    from deeptutor.learning.service import LearningService
    if not Path(deeptutor.__file__).resolve().is_relative_to(VENDOR_ROOT.resolve()):
        raise ValueError('导入了固定vendor之外的原生包')
    output.mkdir(parents=True, exist_ok=True)
    # 固定本次只读输入，重跑使用同一候选原文；新输入须使用新的输出目录。
    copied = output / 'q5-input.sqlite3'
    if not copied.exists():
        with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as original, \
             closing(sqlite3.connect(copied)) as backup:
            original.backup(backup)
            backup.commit()
    snapshots = read_snapshots(copied, student_id=args.student, course_id=args.course)
    current = read_snapshots(source, student_id=args.student, course_id=args.course)
    if fingerprint(current) != fingerprint(snapshots):
        raise ValueError('原输入或目标作用域已变化，请使用新的独立候选目录')
    owner = fingerprint([args.student, args.course])[:32]
    if args.bind_sessions:
        from integrations.deeptutor.native_bridge import NativeTurnBridge
        from integrations.deeptutor.session_bridge import SessionBridge
        from integrations.deeptutor.learning_migration import bind_candidate_sessions
        bridge = NativeTurnBridge(SessionBridge(output / 'native-home'))
    else:
        store = LearningStore(root=output / owner / 'learning')
        service = LearningService(store)
    report = {'schema': 'host-q5-migration-report/v1', 'ready_for_cutover': False,
              'activated': False, 'upstream_commit': pin['commit'], 'source_hashes': hashes,
              'snapshot_paths': len(snapshots), 'paths': [], 'sessions_bound': args.bind_sessions,
              'pending': ['正式入口授权与删除传播', 'Q2导航适配', '自报理解/本次安排/画像映射',
                          '来源版本重新核验', '单一写入方切换与在线回退']}
    async def convert_paths():
        for snapshot in snapshots:
            try:
                if args.bind_sessions:
                    bound = await bind_candidate_sessions(snapshot, bridge)
                    item = {**bound['migration'], 'bound_sessions': len(bound['bindings'])}
                else:
                    item = import_candidate(snapshot, store)
                    progress = service.get_or_create(item['native_path_id'])
                    item['native_service_loaded'] = progress.book_id == item['native_path_id']
                    item['mastery_evidence_count'] = store.count_learning_evidence(progress.book_id)
                if args.verify_sources:
                    from integrations.deeptutor.learning_sources import check_candidate_sources
                    item['sources'] = check_candidate_sources(snapshot)
            except (ValueError, KeyError, TypeError, HTTPException) as exc:
                item = {'status': 'blocked', 'legacy_path_id': snapshot['path']['path_id'], 'reason': str(exc)}
            report['paths'].append(item)
    asyncio.run(convert_paths())
    report['candidate_verified'] = bool(report['paths']) and all(
        item['status'] in ('imported', 'already_imported') and item.get('native_service_loaded')
        and item.get('mastery_evidence_count') == 0
        and (not args.bind_sessions or item.get('workspace_store_verified')) for item in report['paths'])
    report['sources_verified'] = bool(report['paths']) and all(
        item.get('sources', {}).get('verified', False) for item in report['paths']) if args.verify_sources else None
    (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'snapshot_paths': len(snapshots),
                      'statuses': [item['status'] for item in report['paths']],
                      'candidate_verified': report['candidate_verified'],
                      'sources_verified': report['sources_verified'],
                      'ready_for_cutover': False, 'report': str(output / 'report.json')}, ensure_ascii=False))
    if not report['candidate_verified'] or (args.verify_sources and not report['sources_verified']):
        raise SystemExit(2)


if __name__ == '__main__':
    main()
