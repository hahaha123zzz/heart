# 第二阶段：先读合格文字，再补辅助图解

## 范围与决策

- 延续第一阶段，改教材聊天和 PDF 选区讲解的交付顺序，不改意图识别、教学规划或质检标准。
- 复用 `build_guide`，API 执行器传入本轮专属的延后任务列表；直接调用业务方法的旧接口仍按原流程返回完整结果。
- 文字通过原有核验并提交对话后，SSE 发 `answer`；图解生成后通过原有 `done` 发完整结果。
- 对话返回稳定 `conversation_id`，图解更新现有 `PDFCitationRow.reference`，不再写一次学习事件、状态或对话。最终任务回执与图解附件在同一事务提交。
- 图解生成失败保留文字，返回 `visualization_status=unavailable`。前端连接中断保留已显示文字并提示恢复；服务端继续保存结果。
- 补图事务重新检查任务版本、记忆 epoch 和对话归属；删除后不得重建。前端忽略不属于当前账户/当前消息的事件，最终失效结果替换先前文字。

## 当前明确限制

- 这不是逐 token 输出。只有通过核验并保存的完整文字才提前展示。
- 图解期间同一学生的执行锁与页面发送限制仍保留，暂不引入并行追问。
- 实验心理学没有独立习题库；旧离散数学练习入口仍按原有完整结果流程运行。
- 突然停止服务时，已提交文字可从历史读取；本阶段不引入持久化图解后台队列，未完成图解不会在重启后自动续建。

## 验证记录

### 定向回归

128 项测试通过，耗时 93.633 秒，退出码 0。日志：`project/integration/discrete-math-tutor/artifacts/answer-flow-phase2-final.txt`。

在应用目录执行：

```powershell
./.venv-gpu/Scripts/python.exe -X utf8 -m unittest tests.test_progressive_answer tests.test_task_api tests.test_answer_flow tests.test_task_execution tests.test_quality_guard tests.test_memory_events tests.test_memory_jobs tests.test_clarification_tasks tests.test_conversation_identity tests.test_psychology_pipeline tests.test_psychology_visualization tests.test_psychology_presets -q
```

- 新增 5 项隔离数据库/任务测试：文字先落库、图解后写入、回执重放不重复生成、附件失败保留文字、删除拦截、归属校验、延后执行机制（部分同一用例覆盖多个断言）。
- HTTP/SSE 测试新增真实 TaskService 接线断言：`answer` 在 `done` 之前，conversation_id 一致，历史能读取已补图解。
- 心理学预制图新增真实教材锚点的延后执行检查，生成前不运行预制选择/模型，执行后保留现有图解结构。
- 第一阶段分流、质检、学习事件、后台记忆、澄清、心理学流程/图解继续通过。

### 浏览器

先检测到本机 8000 服务，但测试使用独立随机端口的静态页面与 API 替身，不向学生服务写入。Edge 可见窗口测试真实 `app.js` 与图解组件：

1. SSE 先发文字并保持连接，页面已可读文字，图解尚不存在；随后放行 `done`，图解挂到同一回答。
2. 刷新后从模拟历史恢复同一文字和图解。
3. 提前文字之后断线，正文保留，显示“文字已保存，图解待恢复”。
4. 最终收到 memory_deleted，旧文字被失效说明替换，图解不出现。
5. 切换账户/移除消息后，迟到结果不写回当前对话。

脚本：`%TEMP%/playwright-test-progressive-answer.cjs`，通过 `NODE_PATH=C:/Users/free/.agents/skills/playwright/node_modules` 执行。技能自带 run.js 尝试在技能目录写临时文件被文件权限拒绝，因此直接使用已安装 Playwright 运行临时脚本，无安装或权限变更。

原有 `tests/browser/chat-lifecycle.cjs` 也通过：20 次进度更新、焦点/组件保留、引用、证据拒绝、滚动、刷新和稳定历史 ID。其引用标签预期补上界面已有的 ↗，没有为测试改引用行为。

### 已发现但未计入通过的旧测试

初次混合回归 88 项中有 12 项旧 `test_on_demand_visualization` 报错：11 项夹具需要数学“定义9.5”，当前教材已经迁移；1 项仍把数学模板当当前模板。记录保留在 `artifacts/answer-flow-phase2-regression.txt`。本轮没有恢复数学教材、放宽课程校验或将其标记为通过。最终 128 项只包含当前适用的流程回归和心理学测试。

### 检查边界

- `node --check frontend/app.js` 和本轮相关文件 `git diff --check` 通过。
- 本轮未调用真实模型测量耗时、未重启现有服务、未提交或 push。不能据此宣称总生成耗时减少或教学效果提升。
- 未引入依赖、数据库表或迁移。现有教材迁移和资源删除保留。
