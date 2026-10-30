# 第一批工具复用与接入准备核对

日期：2026-10-23。宿主被查提交：`62b3598`；DeepTutor：`6cf793bd868ba5ecbe64722936d4be8fab5a01df`，Apache-2.0。本次仅本地源码调研、注册表探测和离线专项，不修改业务代码、不挂新工具、不执行外网工具或写正式数据。

## 结论

Q4 的协议、惰性注册、授权与执行底座已经接入 Q3，可以承接第一批工具。当前还不是任意 DeepTutor 工具复制进来即可使用：协议是同步适配，业务资源、来源发布、页面动作和动态provider还没有全部接齐。

首批建议围绕现有教材和学生学习：`material_outline`、`read_material`、`read_source`、`read_memory`；随后接 `reader_goto` 和 `kb_files`。已存在的 `read_skill` 先补可发现性与使用验收，不重复开发。先不接写记忆/笔记、评分、代码执行或完整 MCP。

## 1. DeepTutor 如何挂载工具

`tools/builtin_specs.py` 的AST清点为100项、100个唯一工具名；不是每轮全开。真实规则在 `agents/_shared/tool_composition.py`：

- 用户可选工具如web_search、paper_search、reason、brainstorm及媒体生成；不能绕过上下文门。
- 有知识库才挂rag/kb_files，有来源索引才挂read_source，有记忆才挂read_memory，有技能目录才挂read_skill，有deferred provider才挂load_tools。
- workspace工具和capability专属工具另行组合；沉浸阅读、mastery、课程等有自己的业务状态。
- Tool定义只负责参数；运行时注入学生/知识库/材料/来源索引等可信上下文。阅读工具的material_id不是模型可自由指定的参数。

因此可复用的主体是算法、工具说明、参数契约和边界；不能复制其用户ContextVars、账户路径、ReadingStore、JSON记忆库等作为本项目新的数据权威。

## 2. 我们当前实际挂载情况

真实调用链：TaskService → run_agent_loop_turn → build_registry → ScopedToolRegistry → LocalAgentLoop → tool_dispatch。

| 场景 | 实际工具/状态 |
|---|---|
| 普通Q3场景（技能根存在） | 探测得到retrieve_course、ask_user、read_skill |
| 开启Q3_ENABLE_WORKSPACE_TOOLS=1 | 另加workspace_list、workspace_read、workspace_search；根来自宿主可信配置 |
| Q5路径活动 | 另挂9个本项目mastery工具；须有绑定和相应scope |
| 跨章插问 | Q5工具缩至mastery_status、mastery_paths，防止插问推进学习位置 |
| load_tools | 有实现但未列入当前build_registry可见集合，tool_state.deferred_loader=None；没有真实provider接入证据 |
| 其余Q4台账名称 | 名称/扩展元数据不等于实现，也不等于本轮可调用 |

Q5当前9项：mastery_status、mastery_build、mastery_note_explained、mastery_understood、mastery_mode、mastery_paths、mastery_switch、mastery_leave、mastery_revise。不是上游15项全部迁入，也不包含正式评分/复习完成证明。

当前技能根实际包含experimental-design、reasoning-diagrams、finite-structures。read_skill已能挂载，但loop prompt只列工具定义，没有看到完整技能目录清单注入，不能保证模型知道可读的准确技能名；需要增加最小目录描述并验证，不把读技能当作可视化工具已执行。

## 3. 第一批候选与复用方式

### A. 优先4项：教材与学习上下文

| 工具 | 学生可感知的用途 | DeepTutor源文件 | 本项目接入方式 |
|---|---|---|---|
| material_outline | “这本书有什么内容/这一章结构是什么”先读真实目录 | capabilities/reading/tools.py::MaterialOutlineTool | 参考参数、输出和材料绑定；数据复用knowledge.course_navigation.outline、章节/小节元数据；目录本身不冒充全章完整讲解 |
| read_material | 按页/小节读取原文，而非每次只做相似检索 | 同文件::ReadMaterialTool | 参考locator语义、范围限制、截断提示；复用course_navigation.read_target、pdf_reader和Q2原文版本核验，返回可发布证据 |
| read_source | 对刚查到/已附的来源补读，不重复广泛检索 | tools/builtin/__init__.py::ReadSourceTool | 主体很小，可摘取按source_id查可信source_index与错误处理；来源内容仍走现有Q2发布链，不照抄任意文本直出 |
| read_memory | “我的基础/偏好/上次卡在哪”按需查询 | 同文件::ReadMemoryTool | 参数/用途说明可复用；底层必须调用MemoryManager.get_profile、memory_overview等本项目服务，注入当前student_id，不读上游L3 Markdown |

四项基本不需新外部服务；也不需要为了工具建立第二套RAG、目录或画像数据库。read_material按页读取需确保返回原始支持范围而非整个章节默认灌入。

### B. 同批后续2项：定位与资料盘点

| 工具 | 用途 | 复用与限制 |
|---|---|---|
| reader_goto | AI带学生到教材某页/段落 | 参考reading/tools.py::_goto_result、ReaderGotoTool的合法locator与quote校验。跳页≠已掌握；找不到引句可以到合法页，但不得假高亮。本项目还缺工具动作→SSE→前端执行/确认链，不能只返回“已跳转” |
| kb_files | 回答教材有哪些文件/资料 | 参考KbFilesTool及knowledge/manifest.py的过滤、limit、total/omitted报告；当前以公开教材文档manifest为权威，不把325个构图输入或457个部署文件当成教材文档数，隐藏SQLite/缓存/sidecar等内部产物 |

`search_material` 可在证明现有retrieve_course不能满足定位查询后增加；已有检索链不能仅为名称对齐再包装一遍。`view_figure` 的价值在精确图号/视觉输入，当前retrieve_course及媒体链已提供相近能力，先复用，不重复建图库和工具。

## 4. 其他工具的复用价值

| 工具组 | 判断 |
|---|---|
| web_fetch | tools/web_fetch.py相对独立，httpx已安装，适合第二批摘取；保留逐跳URL/网络访问限制、超时/体积上限。需要外部来源类型与页面展示，不能伪装成教材PDF证据；未做完整网络安全审计 |
| web_search | wrapper依赖deeptutor.services.web_search的provider/配置体系，并非一个函数即可使用；要先选搜索后端及授权，避免重复内部总结模型调用 |
| paper_search | paper_search_tool.py的arXiv元数据检索可较独立迁入，但所测环境未安装arxiv；并非心理学综合文献库，不能当最新临床/心理学证据保证 |
| reason/brainstorm | 可参考提示和LLM调用，但会增加内层模型调用；现有模型能做的简单解释无需为工具名称而增加耗时 |
| write_memory/write_note/learning_update | 后续批次；用户、课程、撤销、幂等和取消前提交guard必须适配已有数据层，不接上游第二个记忆库，也不把学习日志当掌握度 |
| question_bank/mastery_quiz/grade/assess | 依赖题卡、作答与可靠评分状态，不因有Q5底座就全部就绪；心理学概念/设计评分须按既有Q5后续计划 |
| MCP/CLI load_tools | deferred loader已有，但缺provider生命周期、配置、可信授权、会话恢复/重授权与实际入口接线；不建议作为首批前置 |
| exec/cron/第三方写入/媒体生成/外部Agent | 配置、权限、运行环境或产品UI依赖大；本轮不作为快速首批 |
| reading_list_tabs/switch_tab、reader_annotate | 上游ReadingCatalog/批注存储与当前阅读器产品不一致，不能原样挂载；批注持久化属后续写操作 |

## 5. 接入前还缺的7处边界

1. **工具协议适配**：上游get_definition()/async execute(**kwargs)；本项目definition/run(arguments, ToolContext)。注册表不会把上游execute自动变成本地run。摘取具体业务算法并写最薄本地适配，不绕过唯一调度器。
2. **可信上下文注入**：当前tool_state只有workspace_root、skills_root、deferred_loader。新工具需要授权课程、绑定document/version/release、source_index、受限memory服务；标识由服务端注入，不能让模型参数选择其他学生或任意路径。暂停快照存标识，恢复后重新取服务并核验版本，不能序列化数据库session/服务对象。
3. **发布规则**：_publish_gate当前要求有教材来源和[n]，无来源即拒绝；有evidence时要求所有来源均有Q2 evidence。目录/画像/状态回答不能硬造引用，外部web来源也不能混入TextbookChunk。需按可信任务用途定义结构化状态/导航结果与教材事实回答边界，不能靠模型自报“这是状态”跳过事实核验。
4. **工具来源与编号**：普通ToolResult.sources会合入循环来源，read_source/read_material必须接当前编号分配、去重、正文发布及引用卡。否则多工具会重复[1]或把无核验摘录混为正式原文。
5. **页面动作**：上游reader_action在metadata；本项目dispatch只把工具结果content给模型，事件摘要不等于前端动作。reader_goto须明确传输、当前文档匹配、取消/revision guard、去重和实际执行回执；不能只复用上游“Reader moved”文案宣称成功。
6. **挂载策略真实调用点**：mounting.py的compose_enabled_tools/compose_for_scene目前主要是底座导出；run_agent_loop_turn使用显式build_registry，不自动调用该策略。新工具必须进入实际per-turn selected/grant/scopes及schema，不能只改台账/flags。先最小接入当前入口，不重建全场景平台。
7. **慢操作/写入取消**：dispatch超时返回不保证底层线程终止。首批只读工具也应使用本身的有界读取和取消检查；后续写工具提交前须再次核对任务状态/epoch，不能把UI停止当作底层已停。

## 6. 本次验证

在主项目代码、独立解释器上运行：

```powershell
# cwd E:\项目\heart\project\integration\discrete-math-tutor
& 'E:/项目/heart/.runtime/response-release-20261022/.venv/Scripts/python.exe' -B -m unittest tests.test_q4_tool_foundation tests.test_q3_q4_integration -q
```

74项通过，7.496秒，exit0。覆盖底座/集成的既有检查，不是新工具真实模型验收。

另外实际调用build_registry探测普通/工作区两场景，工具名见第2节；没有创建工作区或读取学生数据库。独立环境find_spec：httpx存在，arxiv与mcp不存在。只代表所测解释器，不推断所有环境。

未启动服务、未读取进程实际工具开关、未从浏览器发工具请求。上述是当前已提交代码的准备程度，不宣称8000运行进程已加载最新代码或某工具已被模型实际调用。

## 7. 建议交付批次与验收

先做4个只读工具和read_skill可发现性，再做reader_goto/kb_files。每个工具必须同时交付参数/schema、本地业务适配、可信scope、真实挂载点、可发布结果与必要页面表现；以稳定提交交接，不改并行LightRAG/滚轮实现。

关键真实案例：

- “先给我看第一章目录”→真实目录，无相似召回猜目录；不改变学习目标。
- “读取教材第X页/这个来源完整段落”→合法版本原文与紧凑引用；未知ID、过期版本明确失败。
- “你记得我喜欢什么讲法吗”→当前学生的真实偏好；无记录就说明，不推断画像。
- “带我到刚才那一页”→实际阅读器到达并确认，引用不匹配不伪高亮；刷新不重复执行。
- “教材有几个文档”→公开manifest计数，不把构图文件计作书。
- 取消、暂停恢复、重复调用和其他学生ID攻击不越权、不重复推进。

工具需要存在、可见、执行成功、结果可发布、页面/历史正确，五层都核对后才算接入完成。无需为了第一批重新实现Q4底座，也不需要全开100工具。
