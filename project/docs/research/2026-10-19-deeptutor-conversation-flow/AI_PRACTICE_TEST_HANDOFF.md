# AI生成测试题接入与官方DeepSeek配置

2026-10-21；依据用户确认：允许用AI生成题补齐练习入口验收，必须标注AI来源。沿用现有练习API、草稿、TaskService流式辅导、原文引用与核验；不增加正式题库或评分系统。

## 已实现边界

- `ds.env`仅本机保存（Git忽略），显式注入隔离进程；官方key只发至`https://api.deepseek.com`，不发原网关，不复制到主.env。
- `AI_PRACTICE_TEST_CATALOG`显式指定测试输入；不设置时正式课程仍是原先0题，默认行为不变。目录按现有进程级cache读取，切换输入须重启隔离进程。
- `tests/fixtures/ai_practice_sample.json`为官方deepseek-flash实际生成的3道问答题，标注`origin=ai_generated/test_only=true/review_status=unreviewed`。题目根据第一章真实PDF选区生成，`basis_selection`仅是知识依据，不冒称题面位于教材中。输入版本为文件SHA256。
- 题目列表、题干、来源和辅导保存正文显示“AI生成 · 测试用 · 未人工审核”，生成题不显示“题号按教材保留”。旧教材原题沿用原显示。
- 允许隔离提示、讲解、草稿与刷新。前端禁正式提交，后端submit对AI题返回409，不排队、不记正式分，不接管Q5评分。模型生成的参考答案不作为教师答案或掌握证据。
- `exercise_context`仍经现有PDF版本/范围/哈希校验；AI题面与教材事实分开，教材结论继续走selection_evidence和QualityChecker。没有关事实核验来求通过。

## 代码、离线、真实模型与页面证据

业务提交`9b626d4`；夹具定位修复`bbd69c47e205578653013786284fee9da84b1042`。真实页面在该已提交版本完整执行，后续只更新文档/指标。证据汇总[AI_PRACTICE_TEST_EVIDENCE.json](AI_PRACTICE_TEST_EVIDENCE.json)。

- 生成脚本 `scripts/generate_ai_practice_test.py` 只允许官方HTTPS端点，拒绝覆盖已有输出；一次生成、SDK重试0、超时60秒。已观测一次2.015秒、260 tokens、finish_reason=stop；元数据保存在fixture，不含key。
- 首次生成成功但SDK计量采集范围错误，calls为空，原文件保留`.runtime/ai-practice-20261021/initial-generation-unobserved-usage.json`，不能记为零调用；修正后重新生成上述fixture。
- `tests.test_ai_practice_test`与引用相关检查26项通过，日志`.runtime/ai-practice-20261021/offline.log`。首轮命令误把课程与旧库均设为同一`:memory:`被现有隔离门禁拒绝；改为不同独立URL后通过，未改门禁。
- 最终定向回归47项、18.318秒、exit0：`.venv/Scripts/python.exe -B -m unittest tests.test_ai_practice_test tests.test_response_citations tests.test_q3_entrypoint tests.test_task_api -q`，使用不同独立数据库URL、LLM_MOCK=1、禁用后台/生成图；日志`.runtime/ai-practice-20261021/regression.log`。
- 已提交版本真实官方模型/页面验收通过：独立8012、测试学生`ai-practice-isolated`、H目录`ai-practice-live-v2`的host/course数据库、独立裁图目录，未修改主.env/正式库。`tests/browser/ai-practice-live.cjs`完整运行exit0，日志`.runtime/ai-practice-20261021/live-v2.log`。初轮因两个同名练习按钮strict定位失败，未调用生成模型，原phase`ai-practice-live`及live.log保留；修复为阅读页内按钮后新库完整复验，不拼接运行。

| 真实入口 | 总秒 | 页面收到首个正文增量秒 | 结果 |
|---|---:|---:|---|
| 第1级提示 | 5.519 | 3.682 | answered，未直接给完整答案；正文1号引用与1条原文一致，AI来源标注保留 |
| AI讲解 | 4.434 | 2.226 | answered，同样1号引用有效，step_advanced=false |

整个辅导phase为6次SDK create（两次正文流）、18004 total_tokens；HTTP内部重试未独立计量，金额未返回，不估价。两次生成POST，刷新0次额外生成。时间为本次观测，不声称性能普遍提升；first_delta是页面接收/接受增量时刻，不冒充独立像素首绘。

来源、题干和侧栏显示AI生成/测试用/未审核，未显示“题号按教材保留”；正文保存保留AI标签。前端提交禁用，实际后端submit返回409；只读检查隔离库`exercise_submissions=0`、`exercise_skill_observations=0`、`exercise_help=2`。刷新后草稿、AI标签和已保存讲解恢复。截图`practice-refresh.png`已查看。phase完整路径为`E:\项目\heart\project\integration\discrete-math-tutor\.runtime\response-experience\20261020\ai-practice-live-v2`，含practice-live.json、hint/explain.sse、模型调用、截图和服务日志；测试结束停止本次服务。

本次只验了生成样例中的一题、written题型、提示/讲解/草稿/历史/禁止正式评分。其他生成题质量、选择/填空等全部题型、原教材题库和正式批改尚未验完，不能宣布整个练习/评分/UX5完成。

## LightRAG兼容核对

官方DeepSeek凭据及模型列表检查已通过。只读核对候选policy与当前官方extract身份，差异仅`endpoint`：候选`https://cn.chatapi.app/v1`，当前`https://api.deepseek.com`。按当前`LightRagBackend.search`的严格身份比较会拒绝，状态为`blocked_model_policy_binding`。

这是身份静态核对，**没有执行native检索**，不代表跨章覆盖通过。候选policy未改、未重建、无网关调用。证据`.runtime/ai-practice-20261021/lightrag-compatibility.json`。官方key不能通过改URL解决原网关凭据；后续由LightRAG窗口核验查询角色与既有抽取身份的兼容方案，不在公共窗口绕过检查或伪装endpoint。

正式索引、8000服务、staging/ready=false均保持。AI生成题验收只能报告“AI生成测试输入的练习入口”，不能改称教材原题验收通过。
