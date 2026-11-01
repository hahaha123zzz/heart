"""Read-only acceptance against the 94ba9ca release's textbook and state data."""
from __future__ import annotations
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def accept(snapshot_db):
    from knowledge.course import chapters
    from knowledge.pdf_reader import documents,pdf_path
    from knowledge.textbook import load_textbook
    from knowledge.course_release import validate
    from agents.adaptive_tutoring import TeachingTurn, verified_sources, SCHEMA
    from agents.deeptutor_learning.models import LearningProgress
    from agents.deeptutor_learning.policy import is_mastered
    from agents.q3_navigation import LearningTarget
    from agents.teaching_policy import strategy_ids
    from models.task_context import TaskContext
    from models.chat_request import ChatRequest
    book=chapters(); records=documents(); chunks=load_textbook()
    assert len(book)==11 and {c.chapter_id for c in chunks}==set(range(1,12))
    for record in records:
        assert hashlib.sha256(pdf_path(record).read_bytes()).hexdigest()==record['version']
    release=validate()
    summary={'course_chapters':len(book),'sections':sum(len(c['sections']) for c in book),
        'pdf_documents':len(records),'pdf_pages':sum(r['page_count'] for r in records),
        'text_chunks':len(chunks),'release_id':release['release_id'],
        'release_ready':release['ready'],'release_gaps':release['gaps'],
        'models':'not_called','snapshot_replays':0,'source_invalidations':0,'snapshot_contexts':0}
    before=hashlib.sha256(snapshot_db.read_bytes()).hexdigest()
    with sqlite3.connect(snapshot_db.resolve().as_uri()+'?mode=ro&immutable=1',uri=True) as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        columns={row[1] for row in db.execute('PRAGMA table_info(learning_tasks)')}
        assert {'context','student_id','session_id'} <= columns
        for student,session,raw in db.execute('SELECT student_id,session_id,context FROM learning_tasks'):
            value=json.loads(raw or '{}'); old=value.get('tutoring') or {}
            if old.get('schema')!=SCHEMA: continue
            summary['snapshot_contexts']+=1
            progress=LearningProgress.model_validate(old.get('progress') or {})
            if not progress.modules or not progress.modules[0].knowledge_points: continue
            ctx=TaskContext(student_id=student,session_id=session,message='我还是不懂',
                knowledge_point=old.get('topic') or '当前学习目标',tutoring=deepcopy(old))
            request=ChatRequest(student_id=student,session_id=session,request_id='release-replay-'+str(summary['snapshot_replays']),message=ctx.message)
            turn=TeachingTurn(ctx,request,None,validate_sources=verified_sources,
                target=LearningTarget(old.get('target_id') or 'release-target',ctx.knowledge_point))
            assert turn.plan.primary_strategy in strategy_ids()
            assert len(turn.progress.learning_evidence)==len(progress.learning_evidence)
            assert turn.state['formal_mastery']==is_mastered(progress,progress.modules[0].knowledge_points[0])
            assert turn.plan.publication_receipt is None
            summary['source_invalidations']+=int(turn.sources_invalidated)
            summary['snapshot_replays']+=1
    assert hashlib.sha256(snapshot_db.read_bytes()).hexdigest()==before
    summary['snapshot_sha256_unchanged']=True
    summary['snapshot_integrity']='ok'
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--snapshot-db',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=accept(args.snapshot_db)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='release_gaps'},ensure_ascii=True))
