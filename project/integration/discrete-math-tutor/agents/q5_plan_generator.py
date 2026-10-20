"""Q5 first-batch plan generation through the project LLM client.

The prompt schema is local; it is inspired by the mastery outline/playbook in
DeepTutor ``capabilities/mastery/prompts`` but does not copy its application
container or prompt runtime.  Generation is deliberately separated from
persistence: the service validates every returned module/objective/source.
"""
from __future__ import annotations

import json
from typing import Any

from agents.q5_learning import PlanDraft


SYSTEM_PROMPT = """[AGENT:q5_plan_generator]
你是学习计划设计器。请根据学习目标、已选资料和学习者画像，设计一份可执行的学习大纲。
只输出 JSON，不要输出解释或 Markdown。结构：
{
  "name": "路径名称",
  "modules": [
    {
      "name": "模块名称",
      "objective": "学完这个模块后学习者能做什么（一句能力句）",
      "objectives": [
        {
          "name": "可观察的知识点/能力目标",
          "type": "memory|procedure|concept|design",
          "source_refs": [
            {"document_id": "...", "version": "...", "unit_id": "...",
             "chapter_id": 1, "section_id": 1, "page": 3, "title": "..."}
          ],
          "prerequisite_ids": [],
          "required_visual_tasks": []
        }
      ]
    }
  ]
}
规则：
- 模块围绕目标组织，不照抄教材目录；每个模块最多 6 个知识点。
- 每个知识点必须绑定至少一个已选资料的 source_refs；不得编造 document_id/version。
- 类型只能是 memory/procedure/concept/design；目标要可观察，避免“了解/理解”。
- 只使用给定资料和画像；资料不足时减少目标，不要虚构内容。
- 不设计正式题卡、评分或掌握分，这些由后续阶段处理。"""


class LLMPlanGenerator:
    def __init__(self, llm: Any) -> None:
        self.llm = llm

    def generate(
        self,
        *,
        goal: str,
        materials: list[dict[str, Any]],
        profile: dict[str, Any],
    ) -> PlanDraft:
        payload = {
            "goal": goal,
            "materials": materials,
            "learner_profile": profile,
        }
        data = self.llm.chat_json(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(payload, ensure_ascii=False),
                },
            ]
        )
        if not isinstance(data, dict):
            raise ValueError("plan_generator_response_not_object")
        return PlanDraft.from_mapping(data, goal=goal)


__all__ = ["LLMPlanGenerator", "SYSTEM_PROMPT"]
