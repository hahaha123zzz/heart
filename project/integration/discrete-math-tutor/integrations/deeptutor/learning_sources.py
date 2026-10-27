"""原生学习迁移的Q2来源检查；检查结果只属于本次调用，不激活路径。"""
import json

from .learning_migration import build_candidate, fingerprint


def check_candidate_sources(snapshot):
    build_candidate(snapshot)
    course_id = snapshot['path']['course_id']
    from knowledge.course_config import COURSE_ID
    if course_id != COURSE_ID:
        return {'verified': False, 'checked': 0, 'issues': [{'reason': 'course_mismatch'}]}
    from knowledge.course_navigation import validate
    from knowledge.course_release import validate as validate_release
    from knowledge.pdf_reader import document_for_chapter

    checked, issues, seen = 0, [], set()
    try:
        release = validate_release()
    except (ValueError, OSError):
        return {'verified': False, 'checked': 0, 'issues': [{'reason': 'release_unavailable'}]}
    for objective in snapshot['objectives']:
        refs = objective['source_refs']
        refs = json.loads(refs) if isinstance(refs, str) else refs
        for ref in refs:
            key = fingerprint(ref)
            if key in seen:
                continue
            seen.add(key)
            checked += 1
            reason = None
            if (ref.get('source_kind') != 'q2_navigation' or
                    not all(ref.get(name) for name in ('unit_id', 'version', 'document_id',
                                                      'release_id', 'source_version'))):
                reason = 'source_identity_incomplete'
            elif ref.get('source_valid') is False:
                reason = 'source_unavailable'
            elif ref['release_id'] != release['release_id']:
                reason = 'release_changed'
            else:
                try:
                    unit = validate({'id': ref['unit_id'], 'version': ref['version']})
                    document = document_for_chapter(unit['chapter_id'])
                    if (not document or document['document_id'] != ref['document_id'] or
                            any(ref.get(name) != unit.get(name) for name in
                                ('chapter_id', 'section_id', 'source_version'))):
                        reason = 'source_identity_changed'
                    # 早期Q5存目录目标ID，后续版本存原文块ID；两者均须精确匹配。
                    blocks = ref.get('source_block_ids')
                    if not isinstance(blocks, list) or not blocks or list(map(str, blocks)) not in (
                            [unit['id']], list(map(str, unit.get('source_block_ids', [])))):
                        reason = 'source_range_changed'
                    # 旧Q5误写过协议名；只有同版本、同原文且保存目标ID的旧记录可兼容。
                    legacy_schema = (ref.get('target_schema') == 'q2.teaching_targets.v1'
                                     and unit.get('target_schema') == 'word-heading-targets-v1'
                                     and blocks == [unit['id']])
                    if ref.get('target_schema') and ref['target_schema'] != unit.get('target_schema') and not legacy_schema:
                        reason = 'target_schema_changed'
                except (ValueError, KeyError, OSError):
                    reason = 'source_unavailable'
            if reason:
                issues.append({'source_digest': key, 'reason': reason})
    return {'verified': bool(checked) and not issues, 'checked': checked, 'issues': issues,
            'release_id': release['release_id'], 'release_ready': release.get('ready', False)}
