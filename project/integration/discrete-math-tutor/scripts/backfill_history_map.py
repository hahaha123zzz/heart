"""可选：为已验证归属的旧账号补建问题历史图。默认只预览，不写库。"""

import argparse
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from database.database import session_scope
from database.models import ConversationRow, QuestionAnalysisJobRow, UserRow
from history_map import process_job


def pairs_for(student_id):
    with session_scope() as session:
        rows = session.scalars(select(ConversationRow).where(
            ConversationRow.student_id == student_id, ConversationRow.turn_id.is_(None))
            .order_by(ConversationRow.id)).all()
        ids = [(row.id, row.role) for row in rows]
    pairs = []
    index = 0
    while index + 1 < len(ids):
        left, right = ids[index], ids[index + 1]
        if left[1] == "user" and right[1] == "assistant":
            pairs.append((left[0], right[0]))
            index += 2
        else:
            index += 1
    return pairs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", required=True, help="已验证归属的正式账号用户名")
    parser.add_argument("--apply", action="store_true", help="确认已备份后入队并开始分析")
    args = parser.parse_args()
    with session_scope() as session:
        user = session.scalar(select(UserRow).where(UserRow.username == args.username.lower()))
        if not user:
            parser.error("账号不存在；旧 student_id 不能在这里自行认领")
        student_id = user.student_id
    pairs = pairs_for(student_id)
    print(f"账号 {args.username}：发现 {len(pairs)} 对未索引的旧问答。")
    if not args.apply:
        print("仅预览。先备份数据库，再加 --apply；真实语义关联需要配置 LLM_MOCK=0。")
        return
    if os.getenv("LLM_MOCK", "0") == "1":
        parser.error("模拟模型不能可靠判断旧问题引申关系；请配置真实模型后再执行")
    for user_id, assistant_id in pairs:
        turn_id = str(uuid.uuid4())
        with session_scope() as session:
            rows = [session.get(ConversationRow, user_id), session.get(ConversationRow, assistant_id)]
            if any(row is None or row.student_id != student_id or row.turn_id for row in rows):
                continue
            for row in rows:
                row.turn_id = turn_id
            session.add(QuestionAnalysisJobRow(turn_id=turn_id, student_id=student_id))
        process_job(turn_id)
    print("旧问答索引已处理；失败任务保留在库中，可在服务重启后重试。")


if __name__ == "__main__":
    main()
