"""Regenerate the Q4 100-tool / 14-extension migration ledger.

Usage (from the integration directory):
    python -X utf8 scripts/audit_q4_tools.py

The script reads the fixed source audit and migration map already committed in
the research directory, verifies that each audited class still occurs in the
fixed source tree, and writes Q4_TOOL_LEDGER.json/.md.  It never imports or
runs the upstream application.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

INTEGRATION_DIR = Path(__file__).resolve().parents[1]
if str(INTEGRATION_DIR) not in sys.path:
    sys.path.insert(0, str(INTEGRATION_DIR))

# This audit reads extension metadata only; it is allowed to run before Q3 is
# merged and does not instantiate the tool protocol.
os.environ.setdefault("Q4_ALLOW_PROTOCOL_FALLBACK", "1")

from agents.tools.extensions import EXTENSIONS  # noqa: E402

STATUS_LABELS = {
    "runnable": "已可运行（隔离验证）",
    "missing_config": "缺配置",
    "pending_business": "待接业务",
    "not_applicable": "不适用",
}

RUNNABLE = {
    "workspace_list",
    "workspace_read",
    "workspace_search",
    "read_skill",
}

MISSING_CONFIG = {
    "web_search",
    "paper_search",
    "zotero_search",
    "geogebra_analysis",
    "imagegen",
    "videogen",
    "web_fetch",
    "github",
    "exec",
    "obsidian_search",
    "obsidian_read",
    "obsidian_list",
    "obsidian_backlinks",
    "obsidian_links",
    "obsidian_tags",
    "obsidian_create_note",
    "obsidian_append",
    "obsidian_set_property",
    "ima_list",
    "ima_read",
    "ima_note_search",
    "ima_add_url",
    "ima_write_note",
    "consult_subagent",
    "preprint",
    "research_audit",
    "research_lit",
}

NOT_APPLICABLE = {
    "marginnote_search",
    "marginnote_read",
    "marginnote_list",
    "marginnote_documents",
    "marginnote_links",
    "marginnote_tags",
    "marginnote_cards",
    "inspect_setup",
    "apply_setting",
    "request_credential",
    "run_setup_job",
    "propose_partner",
    "invoke_other",
    "partner_read",
    "partner_memorize",
    "partner_search",
}

RUNNABLE_FILES = {
    "workspace_list": ["agents/tools/workspace_tools.py"],
    "workspace_read": ["agents/tools/workspace_tools.py"],
    "workspace_search": ["agents/tools/workspace_tools.py"],
    "read_skill": ["agents/tools/skill_tools.py"],
}

MISSING_REASONS = {
    "web_search": (
        "需要搜索服务商与 API key；项目未配置 deeptutor/services/search 或 model_catalog 搜索 provider。",
        "services/search/*; SEARCH_API_KEY_ENV; data/user/settings/model_catalog.json",
        "Q4 配置搜索 provider 后接 WebSearchTool；无凭据时保持缺配置。",
    ),
    "paper_search": (
        "需要 arXiv 网络出口；当前没有工具级网络策略与 arXiv 客户端迁移。",
        "tools/paper_search_tool.py; arXiv API; 网络出口策略",
        "Q4 接 arXiv 客户端与出口白名单，验证超时/限流。",
    ),
    "zotero_search": (
        "需要 Zotero 用户 ID 与 API key；项目没有 Zotero 凭据。",
        "tools/zotero_search.py; Zotero Web API v3; Zotero-API-Key",
        "Q4 读取服务端 Zotero 配置并做 401/429/超时验证。",
    ),
    "geogebra_analysis": (
        "需要可用的视觉模型与图像输入；当前仅配置聊天模型，未验证视觉端点。",
        "VisionSolverAgent; deeptutor.services.llm.config; image_base64",
        "Q4 配置视觉模型并用真实图像验证，失败不得返回空命令。",
    ),
    "imagegen": (
        "需要 imagegen 生成服务/模型目录配置；项目只配置了聊天模型。",
        "services/imagegen; model_catalog imagegen; media_gen_tool.py",
        "Q4 配置生成服务并验证产物落盘；未配置时明确拒绝。",
    ),
    "videogen": (
        "需要 videogen 生成服务/模型目录配置；项目未配置视频生成。",
        "services/videogen; model_catalog videogen; media_gen_tool.py",
        "Q4 配置生成服务并验证渲染/下载；未配置时明确拒绝。",
    ),
    "web_fetch": (
        "需要受控 HTTP 出口与 HTML 抽取；项目尚未定义 URL 白名单/内网拦截策略。",
        "tools/web_fetch.py; services/web_source/html_extractor; httpx",
        "Q4 增加 SSRF/内网地址拦截、大小与重定向限制后再开放。",
    ),
    "github": (
        "依赖服务器安装 gh CLI 及认证；未验证本机 gh 可用性。",
        "tools/github_query.py; gh CLI; GitHub token",
        "Q4 验证 gh 安装/登录；只读动作先行，写入不自动授权。",
    ),
    "exec": (
        "依赖统一沙箱、资源限制与挂载；项目没有等价沙箱服务。",
        "tools/exec_tool.py; services/sandbox/ExecRequest; ResourceLimits; mounts",
        "Q4 接受控沙箱并验证命令拒绝、超时、资源限制；不得裸执行。",
    ),
    "consult_subagent": (
        "需要已配置的外部 Agent 运行器与连接；本项目未安装/登录任何外部 Agent。",
        "capabilities/subagent/tools.py; services/subagent/get_backend; connection registry",
        "Q4 配置连接后验证预算、超时和真实就绪状态。",
    ),
    "preprint": (
        "需要 ResearchClient、arXiv 网络出口、缓存与可选 GitHub token；未配置。",
        "services/research/primitives; path_service parse cache; github token",
        "Q4 接研究客户端并验证 PDF/页码；失败不得伪造阅读。",
    ),
    "research_audit": (
        "需要 ResearchClient、arXiv/GitHub 出口与固定 commit 读取；未配置。",
        "services/research/primitives; github_source/_token; ResearchClient",
        "Q4 接研究客户端；不执行仓库代码，只做静态证据核对。",
    ),
    "research_lit": (
        "需要 ResearchClient 与 arXiv 检索出口；未配置。",
        "services/research/primitives; arXiv API; ResearchClient",
        "Q4 接文献检索并保留来源/摘要证据等级。",
    ),
}

for _name in (
    "obsidian_search",
    "obsidian_read",
    "obsidian_list",
    "obsidian_backlinks",
    "obsidian_links",
    "obsidian_tags",
    "obsidian_create_note",
    "obsidian_append",
    "obsidian_set_property",
):
    MISSING_REASONS[_name] = (
        "需要已绑定的 Obsidian vault；本项目当前没有 vault 绑定。",
        "capabilities/obsidian/vault.py; vault_for_turn; vault path",
        "Q4 接 vault 绑定；先只读工具，再单独授权写入工具。",
    )

for _name in (
    "ima_list",
    "ima_read",
    "ima_note_search",
    "ima_add_url",
    "ima_write_note",
):
    MISSING_REASONS[_name] = (
        "需要腾讯 IMA 知识库绑定与有效凭据；本项目未配置 IMA。",
        "capabilities/ima/binding; services/rag/pipelines/ima; IMA credentials",
        "Q4 接 IMA 绑定；查询与写入分别授权，写入不自动执行。",
    )

NOT_APPLICABLE_REASONS = {
    "setup": (
        "本项目已有 .env/管理员配置权威；上游设置 UI 与凭据采集会形成第二套配置权威。",
        "capabilities/setup/*; data/user/settings; credential UI",
        "保留台账；如未来需要只读设置检查，另做项目设置适配，不迁入凭据写入。",
    ),
    "marginnote": (
        "MarginNote 4 是 macOS/iOS 本地应用；当前 Windows 部署没有本地库或绑定。",
        "capabilities/marginnote4/store; MarginNote local library",
        "保留台账；平台不适用，不以空实现冒充可用。",
    ),
    "partner": (
        "本项目没有伙伴/IM 账户与会话产品面；迁入会复制第二套账户/会话存储。",
        "services/partners/*; partner sessions; partner memory",
        "保留台账；不迁入伙伴账户/IM 连接器。",
    ),
}

PENDING_REASONS = {
    "rag": (
        "Q2 已有本地混合检索/重排模块，但尚未提供工具侧检索、来源映射和证据返回接口。",
        "knowledge/hybrid_retrieval.py; knowledge/psychology_retrieval.py; Q2 source/evidence mapping",
        "Q2 暴露检索接口后接 RAGTool；不得把上游 node_id 冒充本项目 chunk_id。",
    ),
    "kb_files": (
        "依赖 Q2 教材清单/版本发布接口；当前没有工具侧知识库枚举。",
        "knowledge/course.py; Q2 manifest/publish; knowledge_frontier",
        "Q2 发布清单就绪后接只读枚举。",
    ),
    "knowledge_frontier": (
        "依赖 Q2 知识库清单与 frontier 服务；当前只有本地检索模块。",
        "knowledge/course.py; tools/knowledge_frontier.py; Q2 manifest",
        "Q2 接清单/探索接口并验证空库与未命中。",
    ),
    "read_source": (
        "依赖 Q3 source_index 与来源读取协议；Q3 契约已建立，来源读取尚未接本项目任务。",
        "Q3 source_index; read_source binding; task context",
        "按 Q3 契约接来源身份后做只读读取；普通回答循环不得无条件挂载。",
    ),
    "ask_user": (
        "依赖 Q3 问题卡、任务/修订/命令身份和答复续跑；Q3 契约已建立，尚未接本项目任务链路。",
        "Q3 task identity; ask_user payload; SSE; reply/cancel commands",
        "按 Q3 契约接任务链路；刷新/重复答复不得重复执行。",
    ),
    "brainstorm": (
        "依赖项目 LLMClient 与 Q3 工具调用协议；Q3 契约已建立，工具适配尚未迁移。",
        "llm/client.py; Q3 tool protocol; tools/brainstorm.py",
        "按 Q3 契约接模型/工具协议后迁入；保留多方案与理由输出。",
    ),
    "reason": (
        "依赖项目推理模型配置与 Q3 工具调用协议；Q3 契约已建立，尚未迁移适配。",
        "llm/client.py; model config; tools/reason.py",
        "按 Q3 契约接模型/工具协议后迁入；无专用推理模型时明确降级/拒绝。",
    ),
    "cron": (
        "依赖项目定时任务存储、所有者范围和结果投递；当前没有等价调度服务。",
        "services/cron equivalent; task store; delivery/SSE",
        "Q4/Q5 建所有者隔离的调度存储后再开放；外发/定时执行需显式授权。",
    ),
    "workspace_present": (
        "依赖 Q3 任务事件/UI 预览与工作区发布协议；当前只有只读工作区工具。",
        "Q3 event protocol; workspace publish service; reader/UI",
        "Q3 事件接通后做真实卡片呈现，不以一段文本冒充预览。",
    ),
    "workspace_export": (
        "依赖 Q3 ask_user 一次性授权与导出执行；当前没有授权卡片/写入通道。",
        "Q3 ask_user; workspace export service; authorization record",
        "Q3 接通后只执行用户批准的精确复制；不自动授权外发/覆盖。",
    ),
    "load_tools": (
        "加载器、同轮 schema 追加和 Q3 registry 挂载已用替身 deferred tool 验证；尚无真实 MCP/CLI provider，"
        "不能标为动态外部工具可用。",
        "agents/tools/loader.py; agents/tools/skill_tools.py; ScopedToolRegistry.mount_tool; entry points heart.tools",
        "Q4 配置真实 MCP/CLI provider 后做端到端验证；当前不冒充。",
    ),
    "submit_visualization": (
        "依赖 Q6 可视化载荷校验、Viewer 和产物处理；Q6 未开始。",
        "visualization/; visualization-client/; Q6 payload validator",
        "Q6 接载荷校验与 Viewer；无效载荷不得空画布冒充成功。",
    ),
    "solve_plan": (
        "依赖 Q5/Q6 解题引擎状态与 Q3 循环；当前没有 solve 状态工具。",
        "capabilities/solve; Q3 loop; Q5/Q6 solve engine",
        "Q5/Q6 接计划/步骤/重规划预算；模型文字不得替代状态门槛。",
    ),
    "solve_finish_step": (
        "依赖 solve 计划状态与步骤核验；当前没有 solve 引擎。",
        "capabilities/solve; Q3 loop; Q5/Q6 solve engine",
        "Q5/Q6 接步骤完成校验；不能跳过状态门槛。",
    ),
    "solve_replan": (
        "依赖 solve 预算与重规划状态；当前没有 solve 引擎。",
        "capabilities/solve; Q3 loop; Q5/Q6 solve engine",
        "Q5/Q6 接受限重规划，失败保留真实状态。",
    ),
}

for _name in (
    "read_memory",
    "write_memory",
    "list_notebook",
    "write_note",
    "question_bank",
    "learning_status",
    "learning_update",
):
    PENDING_REASONS[_name] = (
        "依赖 Q5 记忆/笔记/题库/学习日志业务与删除语义；Q5 未开始。",
        "memory/; database/; memory_api.py; Q5 deletion/epoch",
        "Q5 接项目数据仓库与删除/遗忘语义，不复制上游账户存储。",
    )

for _name in (
    "reading_list_tabs",
    "reading_switch_tab",
    "material_outline",
    "search_material",
    "read_material",
    "view_figure",
    "reader_goto",
    "reader_annotate",
):
    PENDING_REASONS[_name] = (
        "依赖 Q5 阅读器目录/原图/跳转/批注与当前材料绑定；Q5 未开始。",
        "reader/; knowledge/pdf_reader.py; Q5 reading state",
        "Q5 接现有阅读器；空材料/失效 revision 不得伪造内容。",
    )

for _name in (
    "course_overview",
    "course_material",
    "course_edit",
    "course_handoff",
):
    PENDING_REASONS[_name] = (
        "依赖 Q5 课程绑定、课程状态与学习入口；Q5 未开始。",
        "knowledge/course.py; Q5 course binding; reader/learning UI",
        "Q5 接课程状态与可操作交接；无课程时明确缺口。",
    )


def _find_repo_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "project/docs/research/2026-10-19-deeptutor-conversation-flow").is_dir():
            return parent
    raise RuntimeError("Could not locate repository root")


def _normalise_stage(stage: str) -> str:
    return "Q2" if stage == "P2" else stage


def _class_name(class_path: str) -> str:
    return class_path.rsplit(":", 1)[-1]


def _source_file(repo_root: Path, audit_root: str, relative: str) -> Path:
    candidate = Path(audit_root) / relative
    if candidate.is_file():
        return candidate
    return repo_root / "project/vendor/DeepTutor" / relative


def _verify_source(path: Path, class_name: str, line: int) -> str:
    if not path.is_file():
        return f"MISSING source file {path}"
    text = path.read_text(encoding="utf-8", errors="replace")
    if class_name not in text:
        return f"MISSING class {class_name} in {path.name}"
    line_count = len(text.splitlines())
    if line < 1 or line > line_count:
        return f"line {line} outside {path.name} ({line_count} lines)"
    return f"源文件存在；类名匹配；审计行 {line}/{line_count}"


def _local_hashes(repo_root: Path, relative_files: list[str]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for relative in relative_files:
        path = repo_root / "project/integration/discrete-math-tutor" / relative
        if not path.is_file():
            continue
        rows.append(
            {
                "path": relative,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    return rows


def _tool_status(name: str) -> str:
    if name in RUNNABLE:
        return "runnable"
    if name in MISSING_CONFIG:
        return "missing_config"
    if name in NOT_APPLICABLE:
        return "not_applicable"
    return "pending_business"


def _tool_details(name: str, stage: str) -> tuple[str, str, str]:
    if name in RUNNABLE:
        if name.startswith("workspace_"):
            return (
                "已迁入并用手工创建的隔离工作区完成列表/读取/搜索、路径逃逸与二进制拒绝测试。",
                "agents/tools/workspace_tools.py; tests/test_q4_tool_foundation.py; scope workspace:read",
                "Q3 在任务上下文中注入 per-task workspace root；未绑定即失败关闭。",
            )
        return (
            "已迁入并用临时技能包及项目真实 visualization/skills 完成读取、名称校验和路径逃逸拒绝测试。",
            "agents/tools/skill_tools.py; tests/test_q4_tool_foundation.py; scope skills:read",
            "Q3 注入任务技能根；真实 visualization/skills 已做只读验证。",
        )
    if name in MISSING_CONFIG:
        return MISSING_REASONS[name]
    if name in NOT_APPLICABLE:
        if name.startswith("marginnote_"):
            return NOT_APPLICABLE_REASONS["marginnote"]
        if name.startswith("partner_"):
            return NOT_APPLICABLE_REASONS["partner"]
        return NOT_APPLICABLE_REASONS["setup"]
    if name in PENDING_REASONS:
        return PENDING_REASONS[name]
    if name.startswith("mastery_"):
        return (
            "依赖 Q5 掌握学习状态、attempt/evidence、题卡与评分；Q5 未开始。",
            "agents/learning; database; practice_api; Q5 attempt/evidence",
            "Q5 接掌握状态与题卡；每次作答只记一次事实。",
        )
    if stage == "Q2":
        return (
            "Q2 本地检索模块已存在，但尚无工具侧检索/来源接口。",
            "knowledge/hybrid_retrieval.py; Q2 evidence/source mapping",
            "Q2 完成工具接口后迁移。",
        )
    if stage == "Q3":
        return (
            "Q3 契约已建立（Q3_INTERFACE_CONTRACT.md），对应工具尚未接入本项目任务/事件。",
            "Q3 loop; task events; project LLM/task interfaces",
            "按 Q3 契约接项目任务/事件后验证。",
        )
    if stage == "Q5":
        return (
            "依赖 Q5 业务数据与项目权威身份；Q5 未开始。",
            "database/; memory/; practice_api; reader/; Q5 business modules",
            "Q5 接项目数据与删除/评分语义。",
        )
    if stage == "Q6":
        return (
            "依赖 Q6 多媒体/可视化产物链路；Q6 未开始。",
            "visualization/; agents/media/; Q6 render/audio services",
            "Q6 接产物校验与页面消费。",
        )
    return (
        "Q4 工具适配尚未迁移；Q3 契约已建立，需接实际调用点。",
        "Q3 tool protocol; project LLM/task interfaces",
        "按 Q3 契约接实际调用点并做真实调用验证。",
    )


def _extension_status(name: str) -> str:
    return next(extension.migration_status for extension in EXTENSIONS if extension.name == name)


def _extension_details(name: str) -> tuple[str, str, str]:
    status = _extension_status(name)
    if status == "missing_config":
        if name == "obsidian":
            return (
                "需要已绑定的 Obsidian vault；本项目无 vault 配置。",
                "capabilities/obsidian/vault.py; vault_for_turn",
                "Q4 接 vault 绑定；先只读，再单独授权写入。",
            )
        if name == "ima":
            return (
                "需要腾讯 IMA 知识库绑定与凭据；未配置。",
                "capabilities/ima/binding; IMA credentials",
                "Q4 接绑定；查询/写入分权。",
            )
        return (
            "需要外部 Agent 运行器与连接；本项目未配置。",
            "services/subagent/get_backend; connection registry",
            "Q4 配置后验证预算、超时与真实就绪状态。",
        )
    if status == "not_applicable":
        if name == "marginnote4":
            return NOT_APPLICABLE_REASONS["marginnote"]
        if name in {"setup"}:
            return NOT_APPLICABLE_REASONS["setup"]
        return NOT_APPLICABLE_REASONS["partner"]
    if name == "ask_questions":
        return (
            "依赖 Q3 ask_user 问题卡、答复续跑和任务身份。",
            "Q3 ask_user/task identity; Q3_INTERFACE_CONTRACT.md",
            "Q3 建立接口后接问题策略与恢复。",
        )
    if name == "explore_context":
        return (
            "依赖 Q3 source_index 与只读来源调查；Q3 未开始。",
            "Q3 source_index; read_source; task context",
            "Q3 接入后按来源存在条件激活。",
        )
    if name == "mastery":
        return (
            "依赖 Q5 掌握状态、题卡、评分和完成门槛。",
            "agents/learning; database; practice_api; Q5",
            "Q5 接状态与题卡；重复作答不重复推进。",
        )
    if name == "solve":
        return (
            "依赖 Q5/Q6 solve 引擎与 Q3 循环。",
            "capabilities/solve; Q3 loop; Q5/Q6",
            "Q5/Q6 接计划/重规划预算。",
        )
    if name == "immersive_reading":
        return (
            "依赖 Q5 阅读器材料/视口/原图状态。",
            "reader/; knowledge/pdf_reader.py; Q5",
            "Q5 接现有阅读器与阅读交接。",
        )
    if name == "course_study":
        return (
            "依赖 Q5 课程绑定与学习入口。",
            "knowledge/course.py; Q5 course binding",
            "Q5 接课程状态与交接。",
        )
    if name == "visualization_generation":
        return (
            "依赖 Q6 可视化载荷校验、Viewer 与产物。",
            "visualization/; visualization-client/; Q6",
            "Q6 接载荷校验与画布产物。",
        )
    return (
        "Q4 扩展适配尚未接通；Q3 契约已建立，等待对应业务状态。",
        "Q3 tool protocol; project state/events",
        "按 Q3 契约接项目状态/事件。",
    )


def build_ledger() -> tuple[dict[str, Any], str]:
    repo_root = _find_repo_root()
    docs_dir = repo_root / "project/docs/research/2026-10-19-deeptutor-conversation-flow"
    audit = json.loads((docs_dir / "SOURCE_AUDIT.json").read_text(encoding="utf-8"))
    mapping = json.loads((docs_dir / "LOCAL_MIGRATION_MAP.json").read_text(encoding="utf-8"))
    stage_by_name = {
        row["name"]: _normalise_stage(row["stage"])
        for row in mapping["coverage"]
        if row["kind"] == "tool"
    }

    tool_rows: list[dict[str, Any]] = []
    for tool in audit["tools"]:
        name = tool["name"]
        stage = stage_by_name.get(name, "Q4")
        status = _tool_status(name)
        reason, dependencies, next_action = _tool_details(name, stage)
        source_path = _source_file(repo_root, audit["source_root"], tool["source"])
        verification = _verify_source(
            source_path, _class_name(tool["class_path"]), int(tool["line"])
        )
        tool_rows.append(
            {
                "name": name,
                "kind": "tool",
                "stage": stage,
                "status": status,
                "status_label": STATUS_LABELS[status],
                "description": tool.get("description", ""),
                "source": tool["source"],
                "class_path": tool["class_path"],
                "source_line": tool["line"],
                "source_verification": verification,
                "reason": reason,
                "dependencies": dependencies,
                "next_action": next_action,
                "local_files": _local_hashes(repo_root, RUNNABLE_FILES.get(name, [])),
            }
        )

    extension_rows: list[dict[str, Any]] = []
    extension_by_name = {extension.name: extension for extension in EXTENSIONS}
    for extension in audit["loop_extensions"]:
        name = extension["name"]
        spec = extension_by_name.get(name)
        if spec is None:
            raise RuntimeError(f"Extension {name} missing from runtime catalogue")
        if tuple(spec.hooks) != tuple(extension.get("hooks") or ()):
            raise RuntimeError(
                f"Extension {name} hooks drift from SOURCE_AUDIT: "
                f"{spec.hooks!r} != {extension.get('hooks')!r}"
            )
        status = spec.migration_status
        reason, dependencies, next_action = _extension_details(name)
        source_path = _source_file(repo_root, audit["source_root"], extension["source"])
        verification = _verify_source(
            source_path, _class_name(extension["class_path"]), int(extension["line"])
        )
        extension_rows.append(
            {
                "name": name,
                "kind": "extension",
                "stage": spec.stage,
                "status": status,
                "status_label": STATUS_LABELS[status],
                "description": spec.description,
                "activation": spec.activation,
                "activation_source": extension.get("activation_source", ""),
                "owned_tools": list(spec.owned_tools),
                "hooks": extension.get("hooks", []),
                "hooks_verified_against_source_audit": True,
                "source": extension["source"],
                "class_path": extension["class_path"],
                "source_line": extension["line"],
                "source_verification": verification,
                "reason": reason,
                "dependencies": dependencies,
                "next_action": next_action,
            }
        )

    if len(tool_rows) != 100:
        raise RuntimeError(f"Expected 100 tools, found {len(tool_rows)}")
    if len(extension_rows) != 14:
        raise RuntimeError(f"Expected 14 extensions, found {len(extension_rows)}")
    if len({row["name"] for row in tool_rows}) != 100:
        raise RuntimeError("Duplicate tool names in ledger")
    if len({row["name"] for row in extension_rows}) != 14:
        raise RuntimeError("Duplicate extension names in ledger")

    counts = {
        status: {
            "tools": sum(1 for row in tool_rows if row["status"] == status),
            "extensions": sum(1 for row in extension_rows if row["status"] == status),
        }
        for status in STATUS_LABELS
    }
    ledger = {
        "schema_version": 1,
        "date": "2026-10-19",
        "source_commit": audit["commit"],
        "source_root": audit["source_root"],
        "counts": {"tools": len(tool_rows), "extensions": len(extension_rows)},
        "status_counts": counts,
        "tools": tool_rows,
        "extensions": extension_rows,
    }
    return ledger, _render_markdown(ledger)


def _render_markdown(ledger: dict[str, Any]) -> str:
    lines = [
        "# Q4 工具与循环扩展迁入台账",
        "",
        "日期：2026-10-19。固定源码：`6cf793bd868ba5ecbe64722936d4be8fab5a01df`（"
        + ledger["source_root"]
        + "）。本台账由 `scripts/audit_q4_tools.py` 从 SOURCE_AUDIT.json、"
        "LOCAL_MIGRATION_MAP.json 和当前运行目录生成；100 个工具与 14 个扩展逐项保留。",
        "",
        "状态口径：**已可运行（隔离验证）**表示本项目已有迁入实现并在隔离资源上通过测试，"
        "不等于已接入 Q3 生产任务；**缺配置**表示实现依赖外部服务/凭据/数据；"
        "**待接业务**表示依赖尚未建立的 Q2/Q3/Q5/Q6 业务接口；**不适用**表示上游产品面"
        "与本项目部署冲突或平台不可用，保留台账但不以空实现冒充完成。",
        "",
        "## 汇总",
        "",
        "| 状态 | 工具 | 扩展 |",
        "| --- | ---: | ---: |",
    ]
    for status, label in STATUS_LABELS.items():
        counts = ledger["status_counts"][status]
        lines.append(f"| {label} | {counts['tools']} | {counts['extensions']} |")
    lines.extend(
        [
            f"| **合计** | **{ledger['counts']['tools']}** | **{ledger['counts']['extensions']}** |",
            "",
            "## 已迁入文件与验证入口",
            "",
            "- `agents/tools/protocol.py`：工具 schema/结果/查找协议（上游 `core/tool_protocol.py` 适配）。",
            "- `agents/tools/registry.py`：惰性注册、别名、动态 entry point、进程注册表与按授权视图。",
            "- `agents/tools/scope.py`：`Allowlist`、`ToolGrant`、`ToolScope`，由授权代理在 `run` 再次校验。",
            "- `agents/tools/validation.py`：JSON 解析、必填/类型/枚举/未知参数检查和有限类型归一。",
            "- `agents/tools/loader.py`：deferred schema 动态加载、同轮 live schema、会话持久化回调。",
            "- `agents/tools/mounting.py`：按场景/上下文/扩展挂载，避免把全部工具强开给通用循环。",
            "- `agents/tools/extensions.py`：14 个扩展的激活条件、owned tools 与阶段。",
            "- `agents/tools/dispatch.py`：Q3 `tool_dispatch` 的薄桥接；Q4 不再实现第二套调度器。",
            "- `agents/tools/workspace_tools.py`、`skill_tools.py`：已迁入的只读工具。",
            "- `tests/test_q4_tool_foundation.py`：45 项隔离测试（未合并 Q3 时 1 项自动跳过）；另用 Q3 实际协议与调度做过联调。",
            "",
            "复现（在集成目录、已激活本项目虚拟环境）：",
            "",
            "```powershell",
            "$env:PYTHONPATH=(Get-Location).Path",
            "python -B -m unittest tests.test_q4_tool_foundation -v",
            "```",
            "",
            "## 100 个内置工具",
            "",
        ]
    )
    for status, label in STATUS_LABELS.items():
        rows = [row for row in ledger["tools"] if row["status"] == status]
        lines.extend(
            [
                f"### {label}（{len(rows)}）",
                "",
                "| 工具 | 阶段 | 来源与依据 | 依赖/下一步 |",
                "| --- | --- | --- | --- |",
            ]
        )
        for row in rows:
            source = f"`{row['source']}:{row['source_line']}`；{row['source_verification']}"
            dependency = row["dependencies"]
            next_action = row["next_action"]
            lines.append(
                f"| `{row['name']}` | {row['stage']} | {source}；{row['reason']} | "
                f"{dependency}；{next_action} |"
            )
        lines.append("")
    lines.extend(
        [
            "## 14 个循环扩展",
            "",
            "| 扩展 | 阶段 | 状态 | 激活条件 | owned tools | 依据/下一步 |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in ledger["extensions"]:
        owned = ", ".join(f"`{name}`" for name in row["owned_tools"])
        source = f"`{row['source']}:{row['source_line']}`；{row['source_verification']}"
        lines.append(
            f"| `{row['name']}` | {row['stage']} | {row['status_label']} | "
            f"{row['activation']} | {owned} | {source}；{row['reason']}；{row['next_action']} |"
        )
    lines.extend(
        [
            "",
            "## 明确未完成 / 不冒充项",
            "",
            "- 已可运行工具只在隔离工作区/技能库上验证；Q3 生产任务根、技能根和事件 sink 尚未接入。",
            "- `load_tools` 的加载器、同轮 schema 追加和 registry 挂载已用替身 deferred tool 验证；"
            "没有真实 MCP/CLI provider，因此本台账不把“动态外部工具可用”标为通过。",
            "- 外部搜索、Zotero、arXiv/GitHub、Obsidian、IMA、外部 Agent、媒体生成、视觉和沙箱均未配置；"
            "没有执行外发、发布或第三方写入来证明功能。",
            "- 未实现第二套 AgentLoop；Q3 契约已建立，dispatch 只执行单批工具调用，不决定循环轮数。",
            "- 上游工具描述/行号来自固定源码审计；本台账不把注册名、文件存在或模拟返回当作能力验收。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    ledger, markdown = build_ledger()
    repo_root = _find_repo_root()
    docs_dir = repo_root / "project/docs/research/2026-10-19-deeptutor-conversation-flow"
    (docs_dir / "Q4_TOOL_LEDGER.json").write_text(
        json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (docs_dir / "Q4_TOOL_LEDGER.md").write_text(markdown.rstrip() + "\n", encoding="utf-8")
    print(json.dumps(ledger["status_counts"], ensure_ascii=False, indent=2))
    print(
        f"wrote {docs_dir / 'Q4_TOOL_LEDGER.json'} and "
        f"{docs_dir / 'Q4_TOOL_LEDGER.md'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
