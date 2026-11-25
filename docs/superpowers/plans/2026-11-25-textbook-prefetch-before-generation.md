# 学生端默认教材与生成前预检索实施计划

日期 2026-11-25
工作树 student-frontend-reuse-20261117
本计划替代 11 月 25 日早先版本的「新增宿主钩子/自定义预检索」方案。

## 已确认的决定

1. 直接修改复用的 DeepTutor 代码；上游版本校验本次不删，功能验收后单独清理。
2. 教材先注册成知识库；学生没选知识库时，继承课程挂载的教材 KB。
3. 是否预检索用现成 `is_course_question` 规则判断；只对 `chat` 生效。
4. 教材检索失败时，用模型自己的知识兜底（提示词已具备该规则）。
5. 预检索不设额外超时。
6. native 回合的最终发布检查不再拦截回答。
7. 练习、测评、研究、`course_study` 沿用各自入口。

## 现状（已核对）

- `register_course_sources()` 已把规范教材 KB 注册并挂到课程（course_rag_provider.py:378，native_bridge.py:234）。
- 上游已有「本轮未传知识库时继承课程资源」的逻辑（_turn_runtime_shared.py:741）。真正的堵点是宿主 `native_executor.py:179` 总会传 `knowledge_bases: []`，上游因此认为学生明确选择了空列表。
- 上游已有生成前预取 `_retrieve_kb_seed_block`（pipeline.py:1481）。两个缺陷：调用工具时没带 `_heart_context`，教材工具会退回旧本地索引；上游读 `metadata.content/answer`，而教材工具原文在 `result_text`（tool_dispatch.py:775）。
- 提示词已写「没有检索到教材依据时，先说明，再用自己的知识回答并标为通识解释」（agentic_chat.yaml zh:51-52 / en:68-71）。
- 现有发布门禁对普通题已允许通识兜底；它拦的是伪造引用、无来源却写编号、跨章缺证据。按决定 6，native 路径不再因这些原因拒绝发布。
- 每轮教材检索预算为 2 批（heart_rag.py:51-58）；预检索占第 1 批。

## 实施步骤

### 1. 默认教材绑定

- [x] `native_executor.py` 启动选项：`knowledge_bases` 为空时不传给 worker，让上游继承课程挂载的教材 KB；非空选择原样保留。
- [x] `_turn_runtime_shared._apply_course_defaults`：会话偏好里的空 `knowledge_bases` 视为未设置，继续用课程资源补默认。
- [x] 接受一个副作用：默认 KB 会在首个回合写入会话偏好（request_preparer.py:629）。后续回合沿用该偏好。

### 2. 首次回答前的教材读取

- [x] `tool_policy.py` 在组装工具时写入 `context.metadata['heart_skip_kb_seed']`：只有绑定规范教材 KB、当前能力是 `chat`、且消息是课程问题时才预检索。
- [x] `pipeline._retrieve_kb_seed_block`：发现该标记直接返回空；其余逻辑沿用上游的批量、截断和 `sources` 事件。
- [x] `pipeline._seed_search_one_kb`：把当前 `UnifiedContext` 作为 `_heart_context` 传给宿主教材工具；只对带 `_heart_course_rag` 标记的工具传入，避免影响上游其他 RAG 工具。
- [x] 原文提取改为优先 `result_text`，其次 `metadata.content/answer`。
- [x] 不设预检索超时；失败返回空 seed，不向模型注入错误说明。
- [x] 预检索前写入 `_heart_citation_offset`，避免与阅读选区来源的引用编号冲突。

### 3. 取消首轮强制工具

- [x] 删除 `tool_policy.preferred_first_tool`、`apply_first_tool_choice` 及其调用；保留 `is_course_question` 供预检索判断。
- [x] 不动 `agentic_bridge.py` 的 `read_current_evidence` 和 `ask_questions` 能力的 `ask_user` 强制。

### 4. 发布与兜底

- [x] `native_executor.py` 不再因发布门禁拒绝回答：保留空回答保护；门禁只用于生成引用投影，失败时用已核验来源生成 `textbook_sources` 标签并照常发布。
- [x] `_publish_gate` 函数本身保留给其他入口，不删。

### 5. 测试

- [x] 新增默认绑定测试：空请求/空偏好回落到课程 KB；显式知识库保留；空请求字段不传给 worker。
- [x] 新增预检索测试：传入了 `_heart_context`；优先使用 `result_text`；非 chat、问候语、无教材 KB 时不预检索。
- [x] 更新 `test_tool_policy_course_first.py`：不再断言强制工具名，改为断言预检索开关。
- [x] 保持 `test_course_grounding_prompt.py` 通过；现有 `test_course_rag_provider.py`、`test_heart_rag_citations.py` 不得回归。
- [x] 运行命令：`.venv-deeptutor/Scripts/python.exe -B -m pytest tests -q`，工作树缺少 `.env` 与教材资产时需设置 `PYTHONPATH=<worktree>/project/vendor/DeepTutor` 和 `TUTOR_PSYCHOLOGY_DIR`。

### 6. 真实验收

- [ ] `/api/chat/stream` 新会话空知识库：确认 `rag` 预检索先于第一次回答模型请求，回答带可点击教材角标。
- [ ] 旧会话追问、概念题、阅读器当前页/选区、无匹配、宿主未就绪、未授权材料、取消。
- [ ] 两账号验证材料范围与来源隔离。
- [ ] 记录预检索耗时、第一次回答模型请求时间、首段正文和 `done`；不设超时，异常时记录宿主 120 秒预算的实际表现。
- [ ] 用 deepseek-flash 思考模式回放「自变量是什么」和「解释信号检测论中的辨别力并给出处」，确认首轮无命名 `tool_choice` 的 HTTP 400。

## 本次不做

- 不删除上游源码版本校验（验收后单独清理）。
- 不新增 Jev 的「是否检索」判断；Jev 仍只负责检索模式。
- 不覆盖 `course_study`、练习、测评、研究。
- 不新增预检索超时和失败提示注入。

## 执行记录 2026-11-25

- 已改代码：`native_executor.py`、`tool_policy.py`、`heart_rag.py`、vendor `pipeline.py`、vendor `_turn_runtime_shared.py`。
- 新增测试：`test_native_default_kb.py`、`test_kb_seed_course_context.py`；更新 `test_native_executor.py`、`test_native_tool_policy.py`、`test_tool_policy_course_first.py`。
- 已通过：75 项课程/原生/引用相关测试，33 项默认绑定/预检索/发布/工具策略测试。
- 工作树缺 `.env` 与教材资产，测试时使用主工作树的 `.env`、`TUTOR_PSYCHOLOGY_DIR` 指向主工作树教材目录，并注入 worktree 的 vendor `PYTHONPATH`。
- 已知与本次无关的既有失败：`test_course_search_bridge.py` 4 项（`loop_failed: memory_save_failed`），`test_deeptutor_integration.py` 2 项（setup 脚本依赖安装断言与脚本现状不一致）。
- 已构建候选发行 `textbook-prefetch-20261125`，`verify` 通过，`select` 后重启三服务；8000/18000/18001 健康。
- 8000 真实浏览器验收（`heart-review-01`，deepseek-flash）：
  - 「自变量是什么」43 秒回答，正文带「教材第5章第5页」「教材第5章第9页」可点击角标。
  - 「解释信号检测论中的辨别力并给出处」带「教材第5章第38页」角标。
  - 两轮均由模型主动调用 `rag`，没有出现预检索批次的 `sources` 事件；该界面走 vendor `/ws` 的阅读/知识库资源，不走宿主的课程默认教材绑定。
- 宿主 `/api/chat/stream` 验收被既有环境问题阻塞：新建宿主学生会话在 worker `request_preparer` 报 `This model is not assigned to your account.`，返回 `native_unavailable`。该错误来自未修改的模型授权代码，属于本地账号/模型授权未预置，不是本次改动引入。
- 结论：代码与单测完成；vendor 8000 界面在候选发行上正常。宿主 `/api/chat/stream` 的「默认教材 + 生成前预检索」真实验收需要在本地为目标学生预置模型授权后重跑。
- 回退：`active-release.json` 的上一版为 `lightrag-native-v4-20261124`。


