# 任务 0 当前审计

最终状态为已完成，最终验证和修复结果见文末“任务 0 最终完成核验”。

本次冻结日期为 2026-11-19，执行目录为隔离工作树 `.worktrees/student-frontend-reuse-20261117`。历史报告保留，当前事实以本文件与 `2026-11-19-task0-freeze.json` 为准。

## 前置工作

用户已批准实施计划、厂家认证、白灰布局、37 个知识点目录和定性规则。2026-11-18 决定取消效果图与截图交付门槛。图片处理及 30/60 天清理按用户指示暂缓。任务 0 负责查清来源、接口和缺口，正式部署、旧学习数据清理和外部模型验证仍受各自验收条件约束。

隔离分支为 `codex/student-frontend-reuse-20261117`，携入 14 个文件的原清单位于 `2026-11-17-student-frontend-execution/carried-files.json`。本轮冻结文件记录 HEAD、完整 tracked diff 文件哈希、工作区状态、实际页面导入和依赖文件哈希。主工作区已有改动保留。node_modules 通过 Junction 复用，Python 使用主工作区 .venv-runtime 并追加 .venv-deeptutor 的依赖路径。独立依赖重装属于任务 2 的剩余验收。

DeepTutor 上游固定为 `6cf793bd868ba5ecbe64722936d4be8fab5a01df`，许可证见 V/LICENSE，本地补丁见 V/LOCAL_PATCHES 与 UPSTREAM_SNAPSHOT.json。Node v24.15.0、npm 11.12.1。实际文件核验结果另见冻结 JSON，不能仅依据目录存在判断版本正确。

## 当前页面与调用链

表中 V=project/vendor/DeepTutor，H=project/integration/discrete-math-tutor。实际全部 page.tsx 及其直接导入已列入冻结 JSON。历史全量 HTTP 调用表保留于 .superpowers/sdd/2026-11-13-student-frontend-reuse/task0-vweb-surface.md。

| 页面、二三级入口与写动作 | 组件、Provider、hooks | HTTP、流与资源 | 后端与存储、验证范围 |
|---|---|---|---|
| /login，登录、退出 | 登录页 → lib/auth → apiFetch | /api/auth/login、logout、status，dt_token | 厂家 auth/identity；home/data/system/auth。两账号真实浏览器通过，永久十账号隔离初始化已验 |
| /chat、/chat/[sessionId]，新建、续聊、取消、重放 | ChatWorkspace → ChatRuntimeProvider → ChatStateAdapter → TurnRuntimeClient/UnifiedTurnClient，模型选择和能力 hooks | /api/sessions；/ws v2 的 start_turn、subscribe、reply、cancel、seq 恢复 | 厂家 unified_ws → TurnApplicationService → SQLite session/turn store。真实浏览器流式通过，模型传输使用替身；取消与恢复沿用专项证据 |
| /learning/reading，materials、folders/[folderId] | 材料库和文件夹组件 → reading-api、useChatWorkspaces | /api/reading/materials、workspaces；固定材料列表，raw 范围读取 | 厂家 reading store、个人 grant 和学习白名单。11 章真实 PDF；上传/删教材受服务端限制 |
| /learning/reading/[workspaceId]、sessions、sessions/[sessionId]，批注、选区提问、会话菜单 | ReadingWorkspace → ReaderPane/PdfPage/AnnotationPopover → ReadingProvider、ReadingComposer → ChatRuntimeProvider | /api/reading 下材料、批注、会话接口；/ws immersive_reading；PDF canvas/text-layer | 个人阅读目录、会话 SQLite。PDF 渲染和问答已验；跨页/旋转/全部引用几何等任务 4 场景尚须逐项验 |
| /learning，学习状态、档案、评估详情及复评确认 | LearningDashboard → ChapterProgress、StudentAssessments → requestJson | /api/heart/learning/chapter-progress、/evaluation/jobs、jobs/{id}、jobs/{id}/reassessment | worker 的 heart_model_api → H PG → 厂家学习证据投影。复评/同步 fixture 与隔离浏览器已有证据，独立资格未完整核验 |
| /learning/graph，章节切换、搜索、节点详情 | KnowledgeGraph → Cytoscape、章节状态组件 | /api/graph/subgraph → Next HEART_API_BASE_URL | H graph_api → LightRAG PG。实际第 2 章图谱已验；节点到知识点映射待确认，指定 GraphViewer 复用仍有缺口 |
| /learning/mastery、[pathId]、sessions/[sessionId] | 厂家 mastery 页面 → ChatRuntimeProvider、MasteryComposer | /api/mastery-paths、/ws/mastery-paths 以及 /ws 回合 | 厂家学习/会话存储，H 结果投影。完整业务联验仍待办 |
| /learning/practice，选题、草稿、提交、揭晓、复习 | PracticeSession → practice-api → 厂家题库与复习 hooks | /api/practice/questions/{id}、check、review；题库列表与保存接口 | 厂家题库/SQLite → practice_sync → H evidence。题库来源幂等同步与浏览器已验；其他题源和完整辅助追踪待办 |
| /memory，搜索、详情、删除、添加偏好 | StudentMemory → 同源 fetch | GET /api/heart/memory；POST /preference；DELETE /{kind}/{id} | heart_memory_api → student_memory → H PG，mem0 候选回 PG 校验。厂家本地记忆禁用；真实 mem0 与账号隔离已有证据 |
| /settings/model，保存/更新/删 Key、能力检查、独立开关 | 学生 SettingsContent → 模型页、StudentModelCapabilities、StudentEvaluationSettings、StudentMemorySettings | /api/heart/model、model/checks、evaluation、memory/settings | H PG 密文、版本及持久任务；个人 HTTPS 传输。浏览器和替身错误场景已验，外部真实模型待验 |
| books/[bookId]/pages/[pageId]、watching/[sessionId]、课程、notebooks 等源码路由 | 对应厂家页面及 hooks | 依各页面的 api client | 路由存在不表示学生可用；按 learning_policy 收敛。物理裁剪清单及未开放路由继续列任务 3 |
| /settings/[section]，管理设置、共享资源弹窗 | SettingsAccessProvider → 学生重定向 /settings/model | 学生不挂载管理员 SettingsProvider；跳过权限外预取 | 后端继续返回 403；最新浏览器 12 类权限外请求为 0 |

所有浏览器接口和流经 V/web/proxy.ts，同源 /api/*、/ws、/files/* 注入服务端桥接令牌后转独立 worker；/api/graph 转 H。认证采用厂家 dt_token，H 图谱验证同一签名。student_id=username，vendor_user_id 为厂家稳定 ID，不采信页面自报身份。浏览器模型列表与每轮请求只解析当前账号配置。未使用旧 native 派生用户作为新前端登录身份。

启动方式沿用 V/web/scripts/dev.mjs，可通过 --hostname 127.0.0.1 --port 指定隔离端口。worker 入口 H/integrations/deeptutor/worker.py，参数 --home 与 --port；H 使用 main:app，DEEPTUTOR_AUTOSTART=0 时连接已有隔离 worker。DEEPTUTOR_API_BASE_URL 指向 worker，HEART_API_BASE_URL 指向 H，DEEPTUTOR_BRIDGE_TOKEN 在服务端共享；教材路径通过 TUTOR_PSYCHOLOGY_DIR 注入。验证使用随机空闲端口和随机临时 PG，生产默认值不作为实际部署事实。

## 厂家能力与当前缺口

| 核验对象 | 实际机制 | 当前缺口与后续归属 |
|---|---|---|
| 知识点评估、多次证据 | 厂家 learning store 与 mastery tools 保存证据；H assessment_publication 同步原结论，37 个目录项已确认 | 概念/设计类无独立量表，已选教材依据定性判断；独立资格、其他来源和实体映射继续任务 6/8 |
| 复评 | H 申请编号幂等、一次成功复评、未知费用确认及前后结论 | 普通聊天部分辅助追踪仍不完整；不自动授予独立掌握 |
| 后台队列 | H assessment_jobs 持久状态/租约，assessment_worker 前台优先与全局 slot | 非厂家现成队列；真实供应商及完整混合负载仍须验 |
| 能力验证与 Key 生命周期 | model_capabilities 分聊天/评估/图片，凭据版本绑定；model_credentials H 加密；model_http 固定公网 IP/TLS | 外部服务准确性未验，图片工作暂缓，正式加密密钥交付待部署 |
| 记忆 | H PG 正文、mem0 索引、稳定 ID/开关版本；厂家 external_store/history 注入 | 普通聊天目前支持明确目录内困难自述，自由文本推断未全覆盖；首版不做更正 |
| 旧数据空状态 | 十个新厂家身份与新 H 学生作用域，不绑定旧聊天；provision_review_accounts、assign_review_reading 幂等初始化 | 正式账号创建、旧数据精确清单批准与清理继续部署阶段 |
| 资产保留 | 正式教材 PDF、章节/目录/page_map、课程发布清单、索引、LightRAG 图谱、图库和来源映射 | 当前仍有 staging 素材与映射缺口；空状态起步不能删除教材或索引 |

## 数据与部署基线

旧学习数据范围包括 H students、会话/任务、evidence、learning_events、个人记忆、评估任务和个人模型配置，以及旧厂家账号目录的会话、学习证据与文件。正式切换应按身份和实际表清单制定清理范围。当前方案通过新账号与新作用域建立空状态，不把“空状态验收”写成已清理正式库。

教材资产保留于 H/knowledge/courses/experimental-psychology-3 和其实际依赖的共享 LightRAG、索引与图库。隔离树不携 PDF，验收读取主工作区原件，只写临时厂家副本。历史截图 2026-11-17-student-frontend-execution/*.png 已存在；用户取消截图交付后不补造 2026-11-13 的旧页面截图。旧可用功能记录见原基线第 4 节和 baseline 报告后续记录。

上一版包仅查到主工作区 artifacts/archive/discrete-math-20261015，不能作为当前心理学部署的可回退整包。现有 deploy_heart.py 仍采用 app/app.prev 覆盖部署，其旧指令不能据此认证新版三服务回退。备份/恢复已在随机库与新 home 验证，上一版整包、生产 Next 构建、代理版本与切换回退仍待任务 10。回退按计划使用切换时的学生数据，生产停机和切换须在可审阅配置就绪后执行。

## 证据解释

完整 worker、浏览器、记忆、评分与恢复等既有验收按 2026-11-18-student-frontend-execution.md 各批次读取。真实教材、数据库、worker 和浏览器已运行；生成模型多数为本地替身。任务 0 完成表示基线、调用方与缺口明确，不能据此认定任务 1–10 或全量上线完成。旧测试命令中 test_native_memory_entries.py 与 test_native_product_surface.py 在隔离树缺失，原命令不可复现；对应现有记忆、评估和浏览器专项另有证据。本轮导航及发布测试结果补记于本文件末尾。

## 本轮核验结果与失败归因

冻结 3764 个上游文件记录，登记补丁修改 57 项，实际页面 36 个。发现 46 个上游文件已被裁剪、26 个现存文件与旧登记哈希不同，逐项路径、当前哈希及预期哈希见冻结 JSON。这是当前工作区差异清单，后续发布需重整累计补丁并逐文件核对，不能把旧账本直接作为发行包校验结果。缺少的 3 份历史补丁已从主工作区补入隔离树。

在随机临时 PostgreSQL、真实教材只读路径下，导航与课程发布两个现存测试文件合计 19 passed、14 failed，另有 39 subtests passed。12 项 NavigationTaskTests 通过 SimpleNamespace(memory=...) 构造 tutor，但 task_service.py 的 input_understanding 已依赖 tutor.llm，执行前即失败，归为过期测试替身。1 项通过 test_quality_guard 导入已删除的 requests_supplementary_proof，归为失效测试依赖。test_stale_version_does_not_fall_back_to_reader 的旧 cursor.version 为 stale 时仍返回 ready，源码 resolve 按 ID 寻找 current 后未先比较 cursor.version，归为旧导航路径的版本校验缺口。该缺口未在本轮审计中改动，修复及行为回归须进入代码工作项。课程发布两项通过，staging 素材仍明确非发布就绪。

旧命令另外两个测试文件在当前树缺失，因此旧“16 failed / 20 passed”不可直接复用。基线冻结采用本轮具体结果及已记录专项验收，未将失败测试标为通过。任务 0 退出条件以来源、调用链、差异、能力边界和缺口均可查证为准，产品发布门禁继续保留失败项。

## 任务 0 最终完成核验

本节取代上文审计初轮的未修复状态。原始失败和差异保留作追溯，当前任务 0 的前置条件与退出清单已全部完成。

修复了旧导航续学前的教材游标版本校验，过期版本先要求重新选择；补齐 TurnRoute 接受的 topic、section、chapter 导航模式，避免正常下一知识点请求触发模型验证异常。两处导航服务测试替身补齐 llm 字段，质检测试从仍有效的 agents.reply_budget 导入补充证明判断函数。

导航、课程发布、输入路由及 worker 快照校验共 48 项通过，另有 56 个子检查通过。补丁校验测试首次受旧 pytest 公共临时目录权限影响，指定唯一 basetemp 后通过，未改应用权限。历史缺失的两份测试文件作为失效旧命令登记，当前可执行基线及替代专项证据明确列出。

从本地 Git 历史恢复全部 72 项差异对应的原导入文件并验证原始 SHA-256，重建 task0-source-reconciliation.patch 和新增文件补丁 task0-added-source-reconciliation.patch。两个补丁均通过反向应用检查。3,764 个导入文件、82 项本地修改及 46 项删除全部能与当前文件状态对应，未解释差异为 0，缺失补丁文件为 0。7 项导入前已应用补丁单独登记 imported_baseline_layers，保留最初导入哈希与真正上游哈希的区别。DeepTutor 来源许可证为 Apache-2.0。

代码修复和来源账本位于隔离工作树，主工作区同步本轮文档与冻结结果。任务 0 的冻结不要求正式服务切换。独立依赖安装/生产构建复现、近期上一版整包与代理回退演练、真实模型和其余功能矩阵继续按任务 2–10 执行。图片工作按用户要求暂缓。
