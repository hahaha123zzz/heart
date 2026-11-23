"""厂家完成候选的待投递记录：PG 暂不可用或进程退出后仍可重放。"""
from __future__ import annotations
import asyncio,json
from dataclasses import dataclass
from integrations.deeptutor import assessment_jobs as jobs

@dataclass(frozen=True)
class EvaluationControl:
    owner:str
    vendor_id:str
    session_id:str
    turn_id:str
    enabled:bool
    revision:int

async def prepare_control(context):
    from deeptutor.multi_user.context import get_current_user_or_none
    user=get_current_user_or_none()
    context.extension("heart_evaluation")["prepared"]=True
    context.extension("heart_evaluation").pop("control",None)
    if user is None or user.is_admin:return
    try:
        control=await asyncio.to_thread(jobs.evaluation_control,user.username)
        context.extension("heart_evaluation")["control"]=EvaluationControl(user.username,user.id,context.session_id,str(context.metadata.get("turn_id") or ""),**control)
    except Exception:
        pass  # 开关不可核对时本轮不新建自动评估，聊天仍可继续。

def initialize(conn):
    # 与厂家 practice_review_outbox 一样，随厂家会话持久化；H 评分队列仍在 PG。
    conn.execute("""CREATE TABLE IF NOT EXISTS heart_assessment_delivery (
        source_id TEXT PRIMARY KEY,owner TEXT NOT NULL,vendor_id TEXT NOT NULL,workspace_id TEXT NOT NULL,
        session_id TEXT NOT NULL,turn_id TEXT NOT NULL,snapshot_json TEXT NOT NULL,ready INTEGER NOT NULL DEFAULT 0)""")

def before_delete(conn,session_id):
    if conn.execute("SELECT 1 FROM sqlite_master WHERE name='heart_assessment_delivery'").fetchone():
        conn.execute("""UPDATE heart_assessment_delivery SET ready=1 WHERE session_id=? AND turn_id IN
            (SELECT id FROM turns WHERE session_id=? AND status='completed')""",(session_id,session_id))

def save(store,candidate):
    owner,vendor,source,snapshot=candidate
    encoded=json.dumps(snapshot,ensure_ascii=False,sort_keys=True)
    with store._connect() as conn:
        initialize(conn)
        old=conn.execute("SELECT snapshot_json FROM heart_assessment_delivery WHERE source_id=?",(source,)).fetchone()
        if old is not None and old[0]!=encoded:raise ValueError("assessment_delivery_conflict")
        conn.execute("INSERT OR IGNORE INTO heart_assessment_delivery(source_id,owner,vendor_id,workspace_id,session_id,turn_id,snapshot_json) VALUES(?,?,?,?,?,?,?)",
            (source,owner,vendor,snapshot.get("workspace_id",""),snapshot["session_id"],snapshot["turn_id"],encoded))

async def prepare_completed(execution,context,events,message_id):
    from deeptutor.multi_user.context import get_current_user_or_none
    from deeptutor.services.session import get_sqlite_session_store
    from integrations.deeptutor.assessment_intake import build_snapshot,record_displayed_references,record_completed_teaching
    user=get_current_user_or_none()
    control=context.extension("heart_evaluation").get("control")
    if (not user or not isinstance(control,EvaluationControl) or not control.enabled or
        (control.owner,control.vendor_id,control.session_id,control.turn_id)!=(user.username,user.id,execution.session_id,execution.turn_id)):return
    await asyncio.to_thread(record_completed_teaching,execution,context)
    candidate=await asyncio.to_thread(build_snapshot,execution,context,events,message_id)
    if candidate:
        candidate[3]["evaluation_control"]={"enabled":control.enabled,"revision":control.revision}
        await asyncio.to_thread(record_displayed_references,candidate[3],context,events)
        await asyncio.to_thread(save,get_sqlite_session_store(),candidate)
        context.extension("heart_evaluation")["durable_candidate"]=True

def drain_store(store,owner,vendor_id,workspace_id):
    with store._connect() as conn:
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='heart_assessment_delivery'").fetchone():return
        rows=conn.execute("""SELECT d.* FROM heart_assessment_delivery d LEFT JOIN turns t ON t.id=d.turn_id
            WHERE d.ready=1 OR t.status='completed' ORDER BY d.rowid LIMIT 25""").fetchall()
    for row in rows:
        if (row['owner'],row['vendor_id'],row['workspace_id'])!=(owner,vendor_id,workspace_id):continue
        jobs.enqueue(owner,vendor_id,row['source_id'],json.loads(row['snapshot_json']),'vendor-qualitative-grounded-v1')
        with store._connect() as conn:
            conn.execute("DELETE FROM heart_assessment_delivery WHERE source_id=?",(row['source_id'],))

async def deliver_current():
    from deeptutor.multi_user.context import get_current_user_or_none
    from deeptutor.services.session import get_sqlite_session_store
    from deeptutor.services.workspace.context import current_workspace_id
    user=get_current_user_or_none()
    if user and not user.is_admin:
        await asyncio.to_thread(drain_store,get_sqlite_session_store(),user.username,user.id,current_workspace_id())
