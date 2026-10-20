# 回答体验专项执行记录

## UX0：真实基线与契约冻结（2026-10-20）

开发基线 `2b5d5d6aa6080588ed9ba927a59d568984e4bb7a`，按 RESPONSE_EXPERIENCE_IMPLEMENTATION_PLAN 顺序实施。起始源码 SHA 保存于 `.runtime/response-experience/20261020/baseline/source.json`。已有主计划、QUALITY_BASELINE、.env.example、worker 修改及教材删除保持原状；不修改其他 worktree 或现有 8000 服务。

采用现有 LLMClient、单一 Markdown 管线、TaskService 与 SSE，不迁移整个聊天应用、不等待 LightRAG。事件字段严格采用计划第 4 节：`answer_delta/answer_replace/answer_state` 的 task_id、task_revision、answer_id、round_id、seq；最终 answer/done 覆盖正文，草稿不入正式历史。来源保存仍用 `[n]` 与 pdf_references；媒体只取本条回答的授权集合。尚未实施的事件不能算现有能力。

四入口：普通/Q5 经 main→TaskService→agent_loop_service 或 Orchestrator；选区经 pdf_selection_tutor；练习聊天经 exercise_task_tutor→practice_api；练习页面有独立帮助与历史渲染。四条链分别验收，不把普通聊天通过算作全部通过。

隔离 8012、独立 host.db/course.db、测试学生、可见 Edge，使用 Playwright 技能运行器完成五个合成问题的真实请求，保存原始 SSE、原始页面消息及截图。模型 deepseek-flash；embedding 配置 cpu、rerank 配置 cuda（配置值不等于每次实际设备证明）；原 .env 未修改。原默认 LOCAL_AGENT_LOOP_ENABLED、Q5 开关未设置，本组是旧编排路径基线，后续 Q3 另验，不能混报。

| 合成样本 | 结果 | 页面总时间/秒 | SDK 调用数 | 返回 total_tokens | 引用 |
| --- | --- | ---: | ---: | ---: | ---: |
| 自变量概念（首次冷请求） | answered | 20.221 | 5 | 16369 | 4 |
| 被试内/被试间比较 | answered | 9.651 | 5 | 19692 | 4 |
| 韦伯定律公式 | evidence_rejected | 1.532 | 1 | 2555 | 0 |
| 三类变量表格比较 | answered | 12.768 | 5 | 19781 | 4 |
| 第一章详细规划 | evidence_rejected | 5.229 | 3 | 11718 | 0 |

五组均没有 `answer_delta`；保留两组真实失败，不算五组业务通过。首次请求单列，不与热请求平均后宣称加速。SDK 调用次数由隔离服务器捕获 create 边界；SDK 内部 HTTP 重试不可见，未伪报 0；未配置价格，不推算费用。原协议没有足够时间戳，未伪造每阶段耗时；后续事件补齐时再做同组对照。

结构化汇总见 RESPONSE_UX_BASELINE.json。原始证据、模型调用计数、环境、截图在 `project/integration/discrete-math-tutor/.runtime/response-experience/20261020/baseline`；启动器正常关闭测试服务。用户未提供原始失败请求，全部明确标记合成样本。选区/练习入口的独立基线和联合验收仍待补齐，不标记 UX0—UX5 整体完成。
