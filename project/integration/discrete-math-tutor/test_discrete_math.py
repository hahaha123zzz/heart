"""Offline integration checks; never touches the configured MySQL database."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="discrete-tutor-test-") as temp:
        os.environ["DATABASE_URL"] = "sqlite:///" + (Path(temp) / "test.sqlite").as_posix()
        os.environ["LLM_MOCK"] = "1"
        from database.database import engine, init_db
        from database.repository import Repository
        from knowledge.textbook import load_textbook, retrieve
        from orchestrator import TutorOrchestrator

        chunks = load_textbook()
        assert len({chunk.source for chunk in chunks}) == 10
        assert retrieve("图", chunks)[0].source.startswith("第7章图")

        tutor = TutorOrchestrator()
        first = tutor.handle_turn("demo-test", "我想学图的基本概念")
        assert "第7章图" in first["textbook_sources"][0]
        second = tutor.handle_turn("demo-test", "不知道")
        assert second["instructional_move"]["instructional_move"] == "worked_example"
        assert second["step_advanced"] is False
        third = tutor.handle_turn("demo-test", "还是不知道")
        assert third["instructional_move"]["instructional_move"] == "direct_explanation"
        assert third["student_state"]["mastery"] == second["student_state"]["mastery"]
        assert len(third["reply"]) <= 260
        switched = tutor.handle_turn("demo-test", "我想学集合")
        assert switched["routing"]["intent"] == "switch_topic"
        assert switched["knowledge_point"] == "集合"
        assert tutor.memory.get_lesson_plan("demo-test", "图") is not None
        tutor.memory.add_hypothesis("demo-test", "集合", "union_intersection_confusion", "把并集当成交集", 0.6)
        tutor.memory.add_hypothesis("demo-test", "集合", "union_intersection_confusion", "把交集当成并集", 0.7)
        assert len(tutor.memory.get_misconceptions("demo-test", "集合")) == 1

        # 初始化和代码更新都不能删除历史学生或其学习记录。
        repo = Repository()
        init_db()
        assert repo.get_conversation("demo-test")
        print("离散数学教材、卡住降难度、话题切换、误解去重和记忆持久化：通过")
        engine.dispose()


if __name__ == "__main__":
    main()
