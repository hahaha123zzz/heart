# Q4 首批只读工具交付：TW0、TW1 与 kb_files 准备

日期：2026-10-24。分支：`codex/q4-first-wave-tools`。基线：`be7cc9c7b18530b2660d5df33cede4efbd76e10f`。

## 1. 范围与状态

按用户指定的并行边界交付工具模块，不接公共业务入口。实施计划原件 SHA256：`3095d7142870baf350692bd18be156adb35996c6c7a2224edc098186be2f5ffb`。

| 项目 | 本次状态 | 集成方后续工作 |
|---|---|---|
| TW0 六工具 schema、scope、读取预算 | 已固定，见 SCHEMAS.json | 结合可信身份与真实资源决定本轮可见工具 |
| TW0 普通/Q5/插问授权快照 | 已记录，见 TW0_SNAPSHOT.json | 不能把静态探测当线上进程已生效 |
| material_outline | 独立模块与现有目录适配完成 | 目录类回答的发布分流 |
| read_material | 单目标/相邻三页原文、版本核验、范围、续读完成 | 公共引用分配、发布与展示联合接线 |
| read_source | 任务内动态索引、相同范围复用编号、相邻段落补读完成 | retrieve_course 使用相同登记入口；暂停恢复重建 |
| read_memory | 复用现有画像与显式偏好来源，只读完成 | personal_state 与混合教材问题的发布规则 |
| kb_files | 基于公开 PDF manifest 的盘点、过滤和分页完成 | 按宿主授权文档集合挂载并验收正文 |
| reader_goto | 仅 schema/scope/回执契约 | TW2/TW3：事件、页面应用及真实回执 |
| TW2、read_skill 目录增强、TW4 | 本轮未实施 | 等流式与学习计划窗口稳定提交后由集成负责人完成 |

本轮未修改用户列出的公共文件，也未修改 Q5 业务实现、公共发布门禁或正式数据库/索引；不引入外部依赖。没有把其他窗口的未提交代码复制进来。

## 2. 文件接口

以下路径相对 `project/integration/discrete-math-tutor`：

- `agents/tools/first_wave_contracts.py`：`DEFINITIONS`、`SCOPES`、预算常量。
- `agents/tools/first_wave.py`：`ReadBinding`、`ReadResources`、`readonly_tools(resources)`、`register_sources(context, sources)` 与五个真实工具类。
- `agents/tools/first_wave_services.py`：`CourseReadService`，复用 course_navigation.outline/read_target、course_release.validate、PDF evidence_text、LiveCitationIndex 的原文与坐标读取。
- `memory/readonly_context.py`：`ReadonlyMemoryContext(memory_manager)`。现有 MemoryManager.get_profile + 现有 MemoryChangeRow 显式确认来源，不建立表或记忆库。
- `tests/test_first_wave_tools.py`：临时 PDF/SQLite、真实底座/dispatcher 与只读服务的隔离验证。

全部运行服务都是每轮可信注入，模型不能提供学生 ID、课程 ID、路径或完整 source_index。无资源时不开放相应工具；`read_source` 有一个本任务的活跃来源索引服务，索引为空时明确拒绝未知 ID，后续精读/检索可以动态补入。

## 3. 接线示意（由集成方实施）

```python
from agents.tools.first_wave import ReadBinding, ReadResources, readonly_tools
from agents.tools.first_wave_services import CourseReadService
from memory.readonly_context import ReadonlyMemoryContext

# 下列身份均来自宿主已验证的任务/课程/文档绑定，不来自模型参数。
binding = ReadBinding(student_id, session_id, task_id, course_id,
                      release_id, tuple(authorized_document_versions))
resources = ReadResources(binding, CourseReadService(), ReadonlyMemoryContext(memory_manager))
context.state['first_wave'] = resources
tools = readonly_tools(resources)
# 合并到既有 extra_tools；不要覆盖 Q5 的 extra_tools/extra_scopes。
new_scopes = {scope for tool in tools for scope in tool.scopes}
```

当前默认真实入口仍只由原 `build_registry/run_agent_loop_turn` 决定。本分支不修改 local_specs、不自动扩大所有会话的权限、不接第二个 dispatcher。可把新实例传入已有 `build_registry(extra_tools=..., extra_scopes=...)` 做隔离调用，专项测试已有此实例。

宿主仍需证明 `student_id/session_id/task_id/course_id` 的授权关系；这里只验证工具上下文与该可信绑定一致及课程版本未变化。`CourseReadService` 使用现有进程级课程配置；它不负责多租户授权，也不能允许模型选择课程。

## 4. 已固定参数与预算

完整机器契约见 `Q4_FIRST_WAVE_SCHEMAS.json`。

| 名称 | 参数 | scope | 输出类型 |
|---|---|---|---|
| material_outline | chapter_id?、offset?、limit?（1–50） | course:read | outline |
| read_material | unit_id（可加 block_offset/char_offset 续读），或 document_id+version+page（可加 end_page） | course:read | textbook |
| read_source | source_id、expand? | course:read + sources:read | textbook |
| read_memory | section?：profile/preferences，默认 preferences | memory:read | personal_state |
| kb_files | pattern?、offset?、limit?（默认20，最大100） | course:read | catalog |
| reader_goto | source_id 或 document_id+version+page；quote? | reader:navigate | reader_action（本轮无执行器） |

封闭参数拒绝未知字段，包括 `_` 开头、event_sink、路径和用户ID；沿用现有参数校验器并在新工具内补齐它尚未处理的边界/互斥校验，不修改公共 validator。

- 原文每次最多一个目标或相邻三页，正文最多12000字符；来源预算最多24个，并尊重更小的 context.state.max_sources。
- 目标截断返回可直接再次传入 read_material 的 continuation；不把部分目标宣称为完整目标。
- 按页读取返回 requested_pages/read_pages、page_basis=generated_reader；对应生成阅读版页码，不承诺纸书原始页码。单页超过预算时不伪装完整页，明确提示按目标缩小范围。
- 目录 limit 默认50；输出含 total/truncated/next_offset。
- 记忆正文最多4000字符，超过预算失败而非破坏结构地截断。
- kb_files 的 total 是**本次授权的公开 PDF 文档数**，当前教材按章发布阅读 PDF；不是教材书籍数，也不是 DOCX、数据库、索引片段、缓存或部署文件数。omitted=matched-listed，next_offset 可续列。

## 5. 来源与发布交接：必须同时接

`register_sources(context, sources)` 接 Q2 已核验的 SourceRef 或其 dict。登记前再次核对真实段落范围/原页坐标，页级来源重读对应页；普通字符串或伪造 quote 不能升级成证据。登记使用既有 `_RETRIEVE_LOCK`，成功后更新：

- `resources.source_index`：当前任务动态来源表，最多24项；
- `context.state.source_offset`：本轮编号游标；
- `context.state.seen_source_ids`：与当前检索链对齐的已见来源集合。

同一版本、段落、字符范围和正文复用编号；相邻小节相同标题不合并，不同页也不合并。扩展范围生成重新定位的独立证据。失败/预算不足时不会提交半个来源批次。工具的模型正文含 `[n]` 与 citations 映射；ToolResult.sources 保留标准 SourceRef/Q2 evidence，支持现有 as_textbook_chunk 适配。

**TW2 不能只把新工具挂进去：**

1. 原 retrieve_course/ContextualRetrieveCourseTool 也须在分配编号之前调用同一登记入口，替换其单独 offset 分配；不能在旧工具已经编号之后再登记一次。
2. 既有 Loop.sources 合并与最终紧凑引用须统一去重。目录/盘点/画像不能硬塞为 TextbookChunk；textbook 结果仍进入既有事实核验门禁。result_kind 是宿主工具结果的类型，不是允许模型自报绕过核验的参数。
3. 页级证据没有 source_block_id。现有 EvidenceBundle.publish 的范围去重键未含 page，直接接入多页结果可能把不同页压成一项；集成方须把真实 page/证据ID纳入页级去重，并保留跨页引用。此问题未在本轮修改公共发布门禁。
4. 本轮读的是文字。没有传递图像像素或 model_message，不可因 caption/页级文字成功而声称已经看过图片。图像继续复用已有 SourceVisual/媒体核验链。
5. 本轮没有通用 source_index 历史升级器；read_source 只认本任务已登记来源。恢复时必须先重建可信绑定，重新核验每个来源指针，再恢复其原 index 和 offset，不能照搬旧资源对象或把任意历史正文注册为新证据。
6. 服务实例、数据库 session、锁和回调不进入 LoopState/JSON 暂停快照。只持久化身份、文档版本、受限原文指针和编号；改变学生/会话/任务/发布版本后拒绝旧绑定。
7. 错误通过 success=false + metadata.error 返回；取消沿用 CancelledError。只读检查在执行前、服务循环、登记和返回前执行。既有线程超时不保证线程被杀；集成方仍需按任务 revision/取消状态丢弃晚到结果，不能让旧任务发布或导航。

## 6. read_memory 的保守口径

没有使用会调用 sync_memory_index 的 memory_overview。每次从现有画像重读偏好，且只保留当前仍存在、在 InteractionPreferences 白名单、具有 explicit_user/set_preference 来源的字段；旧无来源统计不被冒充已确认偏好。查询现有变更表只 SELECT DISTINCT 有限白名单字段，不扫描或返回聊天正文。

profile 当前没有专业、年级、先验知识的可靠结构化字段，明确返回 known={} 和 missing；不把提问、答错一次或教学统计推断成基础。recent 是可选扩展，本轮未开放，不输出跨课程学习摘要或本次安排的缓存。一次性安排不会写成长偏好。遗忘后的值下一次查询立即缺失，不缓存旧偏好。

## 7. reader_goto 接续契约（本轮不执行）

模型只能给 source_id 或合法文档/版本/页码，quote≤500。宿主校验后才创建 action_id，附 task_id/session_id/revision、document_id/version/page 和可选已核实 quote/rects，初态 **requested**。缺乏匹配 quote/rects 只允许合法页定位，不伪造高亮。

流式事件载荷及前端操作由集成负责人按流式窗口稳定接口实现。只有前端实际到达后才回 **applied**；拒绝、取消、版本不匹配、后台会话或旧 revision 回 **rejected**（带 reason）。重复 action_id 不再执行；刷新/历史不自动重放。没有真实回执不能说“已跳转”，不能以跳页代替已学会或更新 Q5。没有在 factory 中挂一个返回“已请求”的空执行器。

## 8. 验证与限制

```powershell
# cwd：独立worktree/project/integration/discrete-math-tutor
& 'E:/项目/heart/.runtime/response-release-20261022/.venv/Scripts/python.exe' -B -m unittest tests.test_first_wave_tools tests.test_q4_tool_foundation -q
```

结果：**65项通过**（新专项20项，既有底座45项）。新专项覆盖真实临时PDF文字/坐标、目录分页、可执行续读、来源扩展及编号、伪造证据拒绝、版本/用户/任务/会话边界、页码/路径/保留参数攻击、取消、原子预算、授权scope、真实dispatcher和学习游标不变。记忆专项使用临时SQLite，SQL监听证明工具读取只有SELECT；其他学生偏好、未确认字段不返回，删除后不再输出。

另以本分支代码只读指向主目录正式教材资产，授权范围仅第一章：目录72个目标，第1页1056字符成功读取，目标 ch1:s1:b6 返回5条精确证据。见 `Q4_FIRST_WAVE_TEXTBOOK_READ_CHECK.json`。没有复制教材或其他窗口代码，没有接触正式学生库。现有教材 release_ready=false（staging），不据此宣称教材发布就绪。

尝试既有 `tests.test_q3_q4_integration`：在导入阶段因独立worktree没有未跟踪的正式教材 manifest 而失败，未计入通过；未为使测试通过复制教材/改公共导入。真实模型、浏览器、流式、最终发布和Q5联合验收未执行。8000端口探测未观察到监听，未能核实运行进程SHA；没有启动/停止任何并行服务。

## 9. 集成与回滚

本次稳定提交可由集成负责人 cherry-pick 到其集成 worktree；以本分支 git rev-parse HEAD 的完整SHA为准，不以主目录未提交文件交接。不要求流式或Q5窗口修改本批文件。需要他们的稳定SHA后，再接 TW2、reader_goto 与 TW4。

仅新增文件，无默认启用开关变更；未接 public entry 时无需部署回滚。后续若接线，先撤销公共入口挂载/来源登记调用，再撤销本提交，不能留下对已删模块的 import。
