"""Quality Checker —— 生成后检查，不通过则打回重生成。

【参考实现】
- ScaffoldLM 的 rule_filter / model_filter / grader（生成后过滤与评估）；
- conv-vs-ped-tutor 的审计维度（答案泄露、学生独立性）；
- 题目质量维度参考 misconception-based 诊断题原则。

检查项：
1. 是否符合 Teaching Plan（策略 / 动作 / 难度）
2. 是否回应了学生当前的问题
3. 是否直接泄露答案
4. 是否符合当前学生状态（情绪 / 信心）
5. 是否偏离当前教学目标
6. 题目质量：是否有诊断力（不是一眼可辨的简单二选一）
实现：规则检查、教学质量检查；证明讲解追加独立证明核验。
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from agents.proof_checker import ProofChecker, ProofAudit, needs_proof_audit

from agents.question_designer import QuestionSpec
from agents.response_generator import requests_proof_overview, requests_supplementary_proof
from agents.teaching_planner import TeachingPlan
from llm.client import LLMClient
from models.student_state import StudentState

_CHECK_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="tutor-quality")

MAX_REPLY_LENGTH = 260
LEAK_MARKERS = ["答案是", "正确答案", "标准答案", "其实就是", "说白了就是"]

SYSTEM_PROMPT = """[AGENT:quality_checker]
你是 AI Tutor 的质量检查器。检查回复是否满足教学计划与学生状态。
检查项：
1. 是否符合计划的 strategy / action / difficulty；
2. 是否先简短回应了学生发言的意图（即使选择反问，也应让学生感到被听到）；
3. 是否泄露答案（计划要求引导时，直接给出完整答案或结论 = 不合格）；
4. 是否照顾了学生情绪与信心；
5. 是否偏离当前教学目标；
6. 题目质量：若回复包含题目，检查题目是否有诊断力——
   一眼就能答对的二选一、敷衍的干扰项 = 不合格；
   若提供了"问题设计规格"，检查回复是否忠实呈现了题目与全部选项、是否当场泄露答案；
7. 话题一致性：若本轮已切换到新知识点，回复不得把学生拉回旧知识点；
8. 重复与推进：回复不得与上一轮几乎相同；教学动作连续多轮不变说明教学没有推进。
9. 离散数学事实须由教材摘录或本轮随附且可辨识的教材原图支持。若公式文字缺失但附有原式图片，可核对后转述图片中清晰可见的公式；这不是自行补写。只有图片未附、内容看不清或标记模糊时，才要求说明并避免猜测。
10. 证明必须检查推理依赖：引用待证结论本身、其尚未证明的等价表述，或依赖待证结论的命题作为证明依据，属于循环论证，应判定不合格并要求改用已知定义或已建立的定理。
11. 核对“教材没有写出”“留给读者”的说法是否对应当前指定步骤的原文：原书已经断言的结论不得称作未断言；其他步骤的省略不能套用到本步。原书未写证明但条件充分时，允许明确标记的补充推导；既要核验推导成立，也要检查是否同时证明了问题要求的全部结论。补充推导不得冒充原书证明。
学生明确请求定理证明解释且计划要求 explain 时，允许先概述路线再解释一小步；不要仅因学生尚未展示基础知识掌握就拒绝回应明确问题，也不能因此认为学生已掌握。
注意：如果 action 是 ask_question，反问与引导是符合计划的正常教学行为，
不要因为"没有直接给出知识性答案"而判定不合格。
issues 只列必须修复才能发布的问题，例如数学错误、关键推理缺口、错误教材归属、引用不支持结论、未回答明确请求、违反当前教学动作的要求。一般措辞改进或语气偏好放入 suggestions，不得在 issues 中一边称不合格一边承认满足要求。
对于 explain，完整回应后无需强制出题；不要因为没有检验学生掌握就判不合格。
判定通过时 passed=true 且 issues=[]；存在必须修复的问题时 passed=false。不得因风格建议放过实际数学错误，也不得要求补充推导必须逐字出现在原书。
只输出 JSON，格式：
{"passed": true 或 false, "issues": ["问题1", "问题2"], "suggestions": "如何修改的一句话建议"}"""


class QualityResult(BaseModel):
    passed: bool
    issues: List[str] = []
    suggestions: str = ""
    proof_audit: Optional[ProofAudit] = None
    timings: Dict[str, Any] = Field(default_factory=dict)


class QualityChecker:
    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm
        self.proof_checker = ProofChecker(llm)

    def check(
        self,
        response: str,
        state: StudentState,
        plan: TeachingPlan,
        student_input: str,
        question_spec: Optional[QuestionSpec] = None,
        context: Optional[Dict[str, Any]] = None,
        textbook_excerpts: str = "",
        figure_images: Optional[List[Path]] = None,
    ) -> QualityResult:
        rule_context = dict(context or {})
        rule_context["proof_overview"] = plan.action == "explain" and requests_proof_overview(student_input)
        rule_context["supplementary_proof"] = plan.action == "explain" and requests_supplementary_proof(student_input)
        rule_issues = self._rule_check(response, plan, rule_context)
        if rule_issues:
            return QualityResult(
                passed=False,
                issues=rule_issues,
                suggestions="删除答案泄露内容，改为引导性提问；或压缩回复长度。",
            )

        content = (
            "学生状态：" + str(state.model_dump()) + "\n"
            "教学计划：" + str(plan.model_dump()) + "\n"
            "学生最新发言：" + student_input + "\n"
            "待检查的 Tutor 回复：" + response + "\n"
            "教材摘录及图号背景：" + textbook_excerpts
        )
        if figure_images:
            content += ("\n本轮已附经审核的教材 PNG 原图，可直接依据清晰可辨的原图核实图或公式；"
                        "文字摘录没有抄出公式时，不能因此把准确的图片转述判作臆造。"
                        "只有图像模糊或公式无法辨认时才要求谨慎。")
        if question_spec is not None:
            content += "\n问题设计规格：" + str(question_spec.model_dump())

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ]
        started=time.perf_counter()
        proof_required=needs_proof_audit(student_input,response,plan.action)

        def teaching_check():
            check_started=time.perf_counter()
            try:
                bounded={"timeout":25,"retries":0,"max_tokens":1200} if proof_required else {}
                data=self.llm.chat_json(messages,image_paths=figure_images,**bounded)
                if (not isinstance(data,dict) or type(data.get("passed")) is not bool
                        or not isinstance(data.get("issues"),list)
                        or any(not isinstance(issue,str) for issue in data["issues"])):
                    result=QualityResult(passed=False,issues=["质量检查结果格式无效，暂不发布"])
                else:
                    result=QualityResult(passed=data["passed"] and not data["issues"],
                        issues=data["issues"],suggestions=str(data.get("suggestions") or ""))
            except Exception as exc:
                logging.getLogger(__name__).warning("教学质量核验未完成：%s",type(exc).__name__)
                result=QualityResult(passed=False,issues=["教学质量核验未完成，暂不发布"])
            return result,int((time.perf_counter()-check_started)*1000)

        audit=None
        if proof_required and not getattr(self.llm,"mock",False):
            # 输入已固定；两个检查互不消费对方结果，汇合后共同决定是否发布。
            teaching_future=_CHECK_POOL.submit(teaching_check)
            proof_future=_CHECK_POOL.submit(self.proof_checker.check,response,student_input,
                                           textbook_excerpts,figure_images)
            result,teaching_ms=teaching_future.result()
            audit=proof_future.result()
            mode="parallel"
        else:
            result,teaching_ms=teaching_check()
            if proof_required:
                audit=self.proof_checker.check(response,student_input,textbook_excerpts,figure_images)
            mode="mock" if getattr(self.llm,"mock",False) else "single"
        if audit is not None:
            result.proof_audit=audit
            if not audit.passed:
                result.passed=False
                result.issues.extend(audit.issues)
        result.timings={"mode":mode,"teaching_ms":teaching_ms,
                        "proof_ms":audit.elapsed_ms if audit else 0,
                        "total_ms":int((time.perf_counter()-started)*1000)}
        return result

    @staticmethod
    def _rule_check(
        response: str,
        plan: TeachingPlan,
        context: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        issues: List[str] = []
        limit = 500 if plan.action == "explain" and (context or {}).get("proof_overview") else MAX_REPLY_LENGTH
        if plan.action == "explain" and (context or {}).get("supplementary_proof"):
            limit = max(limit, 340)
        if len(response) > limit:
            issues.append(
                "回复过长（超过 "
                + str(limit)
                + " 字），违反一次只推进一小步的原则"
            )
        if plan.action in ("ask_question", "give_hint"):
            for marker in LEAK_MARKERS:
                if marker in response:
                    issues.append("计划要求提问/引导，但回复包含疑似答案泄露：" + marker)
        ctx = context or {}
        previous_reply = (ctx.get("previous_reply") or "").strip()
        if previous_reply and response.strip() == previous_reply:
            issues.append("与上一轮回复完全相同（重复，教学没有推进）")
        if ctx.get("topic_switched"):
            old_topic = str(ctx.get("old_topic") or "")
            current_topic = str(ctx.get("current_topic") or "")
            if old_topic and old_topic in response and current_topic not in response:
                issues.append("已切换到新知识点，但回复仍在讲旧知识点：" + old_topic)
        recent_moves = ctx.get("recent_moves") or []
        if len(recent_moves) >= 3 and len(set(recent_moves[-3:])) == 1:
            issues.append(
                "教学动作连续 3 轮未变化（" + str(recent_moves[-1]) + "），教学可能没有推进"
            )
        return issues
