# 任务七验收证据

记忆正文仅来自 H PostgreSQL memory_documents 的 student_memory 条目；mem0 student_memory 只提供候选，注入前核对身份、有效性、正文哈希、索引同步版本及来源目录/原事件。厂家独立 Markdown 读写与旧管理接口禁用，不迁旧聊天。

隔离生产前端按 Next standalone/server.js 启动，静态资源来自同一次构建。

前端固定 LibreChat commit 4700c44eb77c142b4f9f8b87476924f22890eb39 的 MemoryCard/MemoryList/MemoryEmptyState/MemoryCardActions 结构。宿主数据 hooks 替换 LibreChat hooks，删除确认沿用 DeepTutor ConfirmDialog；无编辑、管理权限、token 或 MongoDB。来源和日期缺失不补造。

偏好正文仅存 PG 的 explicit_user 条目，记忆页面是其唯一手动添加入口，聊天 write_preference 拒绝静默写入。设置页长期记忆开关单独保存在 student_memory_settings，同一 API 为唯一开关来源；界面语言/主题等原生明确设置继续由原生设置保存，不复制为记忆。上下文明确指示设置及本轮要求优先，推断不得覆盖它们。自述与推断不写评估、成绩或掌握。

自动记忆不运行额外生成式提取：仅保存已同步评估的有依据观察，以及能完整匹配已确认目录的部分中文学习困难自述。引用、案例、第三方、假设及歧义跳过；推断待确认，自述不当已核验能力。回合开始冻结 enabled/revision，写入重查；关闭、关后重开或删除后，旧回合及旧评估结果均不得写入，不补扫历史。未发起独立提取队列，因此没有待取消的生成式提取请求；评估任务不因关闭记忆被取消，其记忆写入受版本拦截。

本次后端 30 项、组件 10 项及类型/构建通过，真实 Chromium 11 组通过。两个随机账号、随机临时 PostgreSQL、真实原生聊天与完成回调、本地 httpx.MockTransport 作答；生成请求实载记录见 task7-model-requests.json，不含 Key。关闭评估后明确困难仍写自述，并确认 evidence/learning_events/knowledge_states 均未产生。故障验收在查询边界注入可控异常，聊天继续不读记忆，恢复后重新读取；页面 503 可重试。

真实 mem0 使用已缓存 ONNX CPU 与临时 PG pgvector，infer=False，已核验写入、检索、账号隔离、删除索引滞后期间 PG 拦截及后台删除。构造器需要非空凭据，测试仅给无效占位值且地址指向本机不可用端口，不调用外部生成模型；已修复原生模式启动旧宿主索引器的问题，旧壳模式保留旧索引器，学生 worker 的真实 mem0 保持开启。测试结束数据库回收。

复验需要 H 既有 Python 环境、browser-check-12d290667b/python-deps、临时 PG 支持及 task6-build.json 指向的当前生产包。脚本为审阅副本，不应连正式学生库。未运行全仓 Vitest，390px 为视口模拟；正式服务未切换，图片暂缓。
