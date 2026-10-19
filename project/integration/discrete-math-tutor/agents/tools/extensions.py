"""Metadata and activation gates for the 14 built-in loop extensions.

Q4 owns the extension catalog, owned-tool surface, and resource gates.  The
loop hooks themselves stay in Q3/Q5/Q6: this module never runs a turn.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ExtensionStatus = Literal[
    "runnable", "missing_config", "pending_business", "not_applicable"
]


@dataclass(frozen=True, slots=True)
class ExtensionSpec:
    name: str
    stage: str
    description: str
    activation: str
    owned_tools: tuple[str, ...]
    hooks: tuple[str, ...]
    migration_status: ExtensionStatus
    source: str
    class_path: str


@dataclass(frozen=True, slots=True)
class ExtensionFlags:
    """Trusted per-turn facts used by the extension activation gates."""

    ask_questions_mode: bool = False
    mastery_mode: bool = False
    solve_mode: bool = False
    has_obsidian_vault: bool = False
    has_marginnote: bool = False
    has_subagent: bool = False
    has_ima: bool = False
    reading_open: bool = False
    course_id: str = ""
    has_source_index: bool = False
    setup_mode: bool = False
    partner_authoring_mode: bool = False
    partner_group: bool = False
    visualization_generation: bool = False


EXTENSIONS: tuple[ExtensionSpec, ...] = (
    ExtensionSpec(
        "ask_questions",
        "Q3",
        "问题卡策略、答复续跑与首轮交互。",
        "ask_questions_mode 或 ask_questions 场景",
        ("ask_user",),
        ("is_active", "system_block", "augment_kwargs", "pre_loop_seed"),
        "pending_business",
        "deeptutor/capabilities/ask_questions/loop.py",
        "deeptutor.capabilities.ask_questions.loop:AskQuestionsLoopCapability",
    ),
    ExtensionSpec(
        "mastery",
        "Q5",
        "掌握学习模式、题卡、完成门槛与权威状态种子。",
        "mastery_mode 或 mastery_path 场景",
        (
            "mastery_status",
            "mastery_quiz",
            "mastery_note_explained",
            "mastery_grade",
            "mastery_skip_question",
            "mastery_repair_question",
            "mastery_defer_objective",
            "mastery_assess",
            "mastery_build",
            "mastery_mode",
            "mastery_profile",
            "mastery_revise",
            "mastery_paths",
            "mastery_switch",
            "mastery_leave",
        ),
        ("is_active", "system_block", "owned_tools", "augment_kwargs", "pre_loop_seed"),
        "pending_business",
        "deeptutor/capabilities/mastery/loop.py",
        "deeptutor.capabilities.mastery.loop:MasteryLoopCapability",
    ),
    ExtensionSpec(
        "solve",
        "Q6",
        "分步解题计划、完成步骤与受限重规划。",
        "solve_mode 或 deep_solve 场景",
        ("solve_plan", "solve_finish_step", "solve_replan"),
        ("is_active", "system_block", "owned_tools", "augment_kwargs", "pre_loop_seed"),
        "pending_business",
        "deeptutor/capabilities/solve/loop.py",
        "deeptutor.capabilities.solve.loop:SolveLoopCapability",
    ),
    ExtensionSpec(
        "obsidian",
        "Q4",
        "绑定 vault 后的只读检索与受控笔记写入。",
        "本轮存在绑定的 Obsidian vault",
        (
            "obsidian_search",
            "obsidian_read",
            "obsidian_list",
            "obsidian_backlinks",
            "obsidian_links",
            "obsidian_tags",
            "obsidian_create_note",
            "obsidian_append",
            "obsidian_set_property",
        ),
        ("is_active", "owned_kbs", "system_block", "augment_kwargs", "pre_loop_seed"),
        "missing_config",
        "deeptutor/capabilities/obsidian/capability.py",
        "deeptutor.capabilities.obsidian.capability:ObsidianCapability",
    ),
    ExtensionSpec(
        "marginnote4",
        "Q4",
        "绑定 MarginNote 4 数据后的资料、卡片与标签读取。",
        "本轮存在可访问的 MarginNote 4 绑定",
        (
            "marginnote_search",
            "marginnote_read",
            "marginnote_list",
            "marginnote_documents",
            "marginnote_links",
            "marginnote_tags",
            "marginnote_cards",
        ),
        ("is_active", "owned_kbs", "system_block", "augment_kwargs", "pre_loop_seed"),
        "not_applicable",
        "deeptutor/capabilities/marginnote4/capability.py",
        "deeptutor.capabilities.marginnote4.capability:MarginNoteCapability",
    ),
    ExtensionSpec(
        "subagent",
        "Q4",
        "调用已配置的外部 Agent，并执行连接与会话预算。",
        "本轮存在外部 Agent 连接",
        ("consult_subagent",),
        ("is_active", "system_block", "augment_kwargs", "pre_loop_seed"),
        "missing_config",
        "deeptutor/capabilities/subagent/capability.py",
        "deeptutor.capabilities.subagent.capability:SubagentCapability",
    ),
    ExtensionSpec(
        "ima",
        "Q4",
        "腾讯 IMA 知识库的读取、检索与受控写入。",
        "本轮存在 IMA 知识库绑定",
        ("ima_list", "ima_read", "ima_note_search", "ima_add_url", "ima_write_note"),
        ("is_active", "owned_kbs", "system_block", "augment_kwargs", "pre_loop_seed"),
        "missing_config",
        "deeptutor/capabilities/ima/capability.py",
        "deeptutor.capabilities.ima.capability:ImaCapability",
    ),
    ExtensionSpec(
        "immersive_reading",
        "Q5",
        "材料、视口、原图与阅读操作驱动的回答上下文。",
        "已打开材料/阅读工作区，或显式阅读模式",
        (
            "reading_list_tabs",
            "reading_switch_tab",
            "material_outline",
            "search_material",
            "read_material",
            "view_figure",
            "reader_goto",
            "reader_annotate",
        ),
        ("is_active", "system_block", "owned_tools", "augment_kwargs", "pre_loop_seed"),
        "pending_business",
        "deeptutor/capabilities/reading/capability.py",
        "deeptutor.capabilities.reading.capability:ReadingCapability",
    ),
    ExtensionSpec(
        "course_study",
        "Q5",
        "课程状态预读、推荐与学习入口交接。",
        "course_study 场景且课程 ID 可解析",
        ("course_overview", "course_material", "course_edit", "course_handoff"),
        ("is_active", "system_block", "owned_tools", "augment_kwargs", "pre_loop_seed"),
        "pending_business",
        "deeptutor/capabilities/course_study/capability.py",
        "deeptutor.capabilities.course_study.capability:CourseStudyLoopCapability",
    ),
    ExtensionSpec(
        "explore_context",
        "Q3",
        "回答前的只读来源调查与上下文补充。",
        "source_index 非空",
        ("read_source",),
        ("is_active", "system_block", "augment_kwargs", "pre_loop_seed", "pre_loop"),
        "pending_business",
        "deeptutor/capabilities/explore_context/capability.py",
        "deeptutor.capabilities.explore_context.capability:ExploreContextCapability",
    ),
    ExtensionSpec(
        "setup",
        "Q4",
        "上游设置引导、凭据采集与安装任务。",
        "仅设置引导上下文",
        ("inspect_setup", "apply_setting", "request_credential", "run_setup_job"),
        ("is_active", "system_block", "augment_kwargs", "pre_loop_seed"),
        "not_applicable",
        "deeptutor/capabilities/setup/capability.py",
        "deeptutor.capabilities.setup.capability:SetupCapability",
    ),
    ExtensionSpec(
        "partner_authoring",
        "Q4",
        "伙伴创建提案与配置确认。",
        "仅伙伴创建上下文",
        ("propose_partner",),
        ("is_active", "system_block", "augment_kwargs", "pre_loop_seed"),
        "not_applicable",
        "deeptutor/capabilities/partner_authoring/capability.py",
        "deeptutor.capabilities.partner_authoring.capability:PartnerAuthoringCapability",
    ),
    ExtensionSpec(
        "partner_group",
        "Q4",
        "伙伴小组讨论、成员预算与正式回答边界。",
        "存在 partner_group 字典上下文",
        ("invoke_other",),
        (
            "is_active",
            "system_block",
            "augment_kwargs",
            "pre_loop_seed",
            "finish_instruction",
            "tool_round_output_policy",
            "final_text_override",
            "_save_formal_answer",
        ),
        "not_applicable",
        "deeptutor/capabilities/partner_group/capability.py",
        "deeptutor.capabilities.partner_group.capability:PartnerGroupCapability",
    ),
    ExtensionSpec(
        "visualization_generation",
        "Q6",
        "可视化载荷提交、模式完成检查与画布产物。",
        "已设置可视化生成模式",
        ("submit_visualization",),
        ("is_active", "system_block", "owned_tools", "augment_kwargs", "pre_loop_seed"),
        "pending_business",
        "deeptutor/visualizers/loop_capability.py",
        "deeptutor.visualizers.loop_capability:VisualizationLoopCapability",
    ),
)

EXTENSION_BY_NAME = {extension.name: extension for extension in EXTENSIONS}


def active_extensions(flags: ExtensionFlags, scene: str = "") -> list[ExtensionSpec]:
    """Return extensions whose trusted activation gate is satisfied."""

    scene = str(scene or "").strip().lower()
    active: list[ExtensionSpec] = []
    if flags.ask_questions_mode or scene == "ask_questions":
        active.append(EXTENSION_BY_NAME["ask_questions"])
    if flags.mastery_mode or scene == "mastery_path":
        active.append(EXTENSION_BY_NAME["mastery"])
    if flags.solve_mode or scene == "deep_solve":
        active.append(EXTENSION_BY_NAME["solve"])
    if flags.has_obsidian_vault:
        active.append(EXTENSION_BY_NAME["obsidian"])
    if flags.has_marginnote:
        active.append(EXTENSION_BY_NAME["marginnote4"])
    if flags.has_subagent:
        active.append(EXTENSION_BY_NAME["subagent"])
    if flags.has_ima:
        active.append(EXTENSION_BY_NAME["ima"])
    if flags.reading_open or scene == "immersive_reading":
        active.append(EXTENSION_BY_NAME["immersive_reading"])
    if flags.course_id.strip() or scene == "course_study":
        active.append(EXTENSION_BY_NAME["course_study"])
    if flags.has_source_index:
        active.append(EXTENSION_BY_NAME["explore_context"])
    if flags.setup_mode:
        active.append(EXTENSION_BY_NAME["setup"])
    if flags.partner_authoring_mode:
        active.append(EXTENSION_BY_NAME["partner_authoring"])
    if flags.partner_group:
        active.append(EXTENSION_BY_NAME["partner_group"])
    if flags.visualization_generation or scene == "visualize":
        active.append(EXTENSION_BY_NAME["visualization_generation"])
    return active


def owned_tools_for(extensions: list[ExtensionSpec] | tuple[ExtensionSpec, ...]) -> list[str]:
    """Ordered, de-duplicated tool names owned by the active extensions."""

    seen: set[str] = set()
    tools: list[str] = []
    for extension in extensions:
        for name in extension.owned_tools:
            if name in seen:
                continue
            seen.add(name)
            tools.append(name)
    return tools


__all__ = [
    "EXTENSION_BY_NAME",
    "EXTENSIONS",
    "ExtensionFlags",
    "ExtensionSpec",
    "ExtensionStatus",
    "active_extensions",
    "owned_tools_for",
]
