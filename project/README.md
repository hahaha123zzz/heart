# Agent 模块抽离区

本目录从 `psychology-learning-platform-demo-student-integration.zip` 中抽取了与 Agent 直接相关的代码和资料，供后续修改。这里的文件是副本，可以直接编辑；压缩包和项目同步资料不受影响。

## 核心代码

- `server/app/modules/question_agent/`：出题 Agent。负责基于课程证据生成题目草稿、唯一可解校验、超纲检查、去重和审核任务。
- `server/app/modules/tutor/`：教学辅导 Agent。包含回答生成、证据引用与主张校验、SSE 教学回合、学习状态机、策略解析和下一步规划。

## 配套内容

- `server/tests/`：两个 Agent 的后端测试。
- `web/lib/tutor-claim-verification.ts`：前端对 Tutor 主张校验结果的类型/显示契约。
- `web/tests/`：Tutor 的 SSE 恢复、选中文本提问和图注提问测试。
- `docs/`：智能体平台设计文档及证据闭环、生成单元、查询分析相关文档。

## 运行依赖

这不是完全独立的可执行项目。核心模块仍依赖原项目中的：

- `server/app/db/`：数据库模型与会话；
- `server/app/core/`：配置、错误处理、模型网关；
- `server/app/modules/knowledge/`：知识检索、证据和发布快照；
- `server/app/modules/auth/`、`assessments/`、`courses/`、`materials/`、`learning_events/`：鉴权、课程范围与学习流程。

修改 Agent 逻辑时，优先从以下入口开始：

1. Tutor：`server/app/modules/tutor/service.py`
2. Tutor 策略：`server/app/modules/tutor/policy.py`
3. Tutor 规划：`server/app/modules/tutor/planner.py`
4. 出题：`server/app/modules/question_agent/service.py`
5. API 入口：各目录下的 `router.py`

如需把修改后的模块接回完整项目，需要将变更同步回原项目对应路径，并一起运行配套测试。
