"""命令行测试客户端。

默认使用**测试账户**（account_type=test）：结束时自动删除该学生的全部记忆
（画像 / 状态 / 误解 / 证据 / 对话 / 教学计划，靠 ON DELETE CASCADE 级联清空）。

用法：
    py -3.11 chat_cli.py                                  # 测试账户 test-chat，退出自动清理
    py -3.11 chat_cli.py --keep                           # 测试账户，但保留数据（想查库用）
    py -3.11 chat_cli.py --account production --student demo-student   # 正式账户，长期保存
    py -3.11 chat_cli.py --once "我对图的基本概念不太懂"           # 单轮，自动清理
"""

from __future__ import annotations

import argparse
import json

from orchestrator import TutorOrchestrator


def print_result(result: dict, debug: bool = False) -> None:
    print("\n助教> " + result.get("reply", ""))
    sources = result.get("textbook_sources") or []
    if sources:
        print("教材：" + str(sources[0]))
    if not debug:
        return
    routing = result.get("routing") or {}
    print()
    if routing:
        print(
            "[路由] intent={} move={} topic={}".format(
                routing.get("intent"),
                routing.get("student_move"),
                routing.get("topic") or "-",
            )
        )
    state = result.get("student_state")
    if not state:
        return
    print("[知识点] " + str(result.get("knowledge_point", "")))
    if "teaching_plan" not in result:
        return  # 非学习消息的轻量路径
    plan = result["teaching_plan"]
    print(
        "[状态] mastery={:.2f} confidence={:.2f} metacognition={:.2f} "
        "emotion={} misconception={}".format(
            state["mastery"],
            state["confidence"],
            state["metacognition"],
            state["emotion"],
            state["misconception"],
        )
    )
    print(
        "[计划] strategy={} action={} difficulty={} hint_level={}".format(
            plan["strategy"], plan["action"], plan["difficulty"], plan["hint_level"]
        )
    )
    lesson = result.get("lesson_progress") or {}
    if lesson:
        if lesson.get("status") == "completed":
            print(
                "[课程] 已完成全部 {} 步：{}".format(
                    lesson.get("total_steps"), lesson.get("goal")
                )
            )
        else:
            print(
                "[课程] 第 {}/{} 步：{}".format(
                    lesson.get("current_step_index"),
                    lesson.get("total_steps"),
                    lesson.get("current_objective"),
                )
            )
    mis = result.get("misconceptions") or []
    if mis:
        print(
            "[误解] "
            + str([(m["type"], m["status"], m["evidence_count"]) for m in mis])
        )
    if result.get("step_advanced"):
        print("[课程] 步骤达成，已推进到下一步！")
    spec = result.get("question_spec") or {}
    if spec:
        print(
            "[问题] type={} 目标误解={}".format(
                spec.get("question_type"), spec.get("target_misconception")
            )
        )
    move = result.get("instructional_move") or {}
    if move:
        print(
            "[策略] {} / {} / {}（rationale: {}）".format(
                move.get("instructional_move"),
                move.get("action"),
                move.get("difficulty"),
                (move.get("rationale") or "")[:30],
            )
        )
    quality = result.get("quality")
    if quality:
        print(
            "[质检] passed={} attempts_regen={}".format(
                quality["passed"], result["regenerated"]
            )
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="离散数学助教 CLI")
    parser.add_argument("--once", type=str, default=None, help="只发送一条消息后退出")
    parser.add_argument("--goal", type=str, default="图的基本概念", help="学习目标")
    parser.add_argument("--student", type=str, default=None, help="学生 ID")
    parser.add_argument(
        "--account",
        choices=["test", "production"],
        default="test",
        help="test=测试账户(默认,会清理)；production=正式账户(长期保存)",
    )
    parser.add_argument("--keep", action="store_true", help="测试账户也保留数据，不清理")
    parser.add_argument("--debug", action="store_true", help="显示路由、状态和教学计划等调试信息")
    args = parser.parse_args()

    student_id = args.student or (
        "test-chat" if args.account == "test" else "demo-student"
    )
    account = args.account
    tutor = TutorOrchestrator()

    if account == "test":
        tutor.memory.accounts.create_test_account(student_id, ttl_hours=24)
        print(
            ">>> 测试账户: {}（24 小时后自动过期；{}）".format(
                student_id,
                "结束后保留数据" if args.keep else "结束后自动删除全部记忆",
            )
        )
    else:
        print(">>> 正式账户: {}（长期保存）".format(student_id))

    try:
        if args.once:
            result = tutor.handle_turn(student_id, args.once, args.goal, account)
            if args.debug:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print_result(result)
            return

        print("AI Tutor 已启动（输入 exit 退出）")
        print("提示：先试试 '我对图这一章不太懂，该怎么学？'")
        print("（只有输入 exit / quit / 退出 才会结束，直接按回车不会退出）")
        while True:
            try:
                message = input("\n学生> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if message.lower() in ("exit", "quit", "退出"):
                break
            if not message:
                print("（你还没有输入内容。继续说点什么？想结束请输入 exit）")
                continue
            result = tutor.handle_turn(student_id, message, args.goal, account)
            print_result(result, debug=args.debug)
        print("再见！")
    finally:
        if account == "test" and not args.keep:
            removed = tutor.memory.accounts.destroy_test_account(student_id)
            print(">>> 测试账户已清理: {}".format(removed))


if __name__ == "__main__":
    main()
