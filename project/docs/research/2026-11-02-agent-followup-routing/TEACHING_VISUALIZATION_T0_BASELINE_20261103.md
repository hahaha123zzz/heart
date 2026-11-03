# 教学表达与自动图解：T0基线

日期：2026-11-03。对应[专项计划](TEACHING_VISUALIZATION_IMPLEMENTATION_PLAN_20261103.md)。本阶段不调用真实模型、不改变服务配置或正式数据库。

## 基线

- 根工作区分支`codex/ta5-acceptance-20261029`，HEAD `2019833c38844b7afe6c3488507f8c81a72b6f22`。工作区有大量其他窗口的未提交修改，因此HEAD不代表工作区全部代码；执行后续修改前需核对相关文件当前差异，不覆盖其他工作。
- 127.0.0.1:8000 TCP连接成功，netstat显示监听者为PID 21884，与旧启动记录一致，该Python进程存在。没有核实进程内开关或加载的代码哈希，因此不能据此确认它一定是当前工作区最新版。
- 磁盘`.env`中`VISUALIZATION_ON_DEMAND=0`、`LOCAL_AGENT_LOOP_ENABLED=1`、`RESPONSE_COMPOSITION_ENABLED=1`。这是磁盘配置，不证明进程当前实际值。
- 已有小修复位于`agents/response_composition_adapters.py`：优先读取原始策略，summary映射为recap；`tests/test_response_composition_adapters.py`增加总结和反例的回归。尚未完成图解接线或上线。

## 调用边界与复现证据

1. `main.py::_execute_task_turn`：选区AgentLoop分支传递visualization_jobs，普通AgentLoop分支未传。旧orchestrator及选区服务有build_guide入口。
2. `agents/agent_loop_service.py::run_agent_loop_turn`：唯一build_guide调用位于selection_input非空的条件分支；普通聊天无法由该调用排队。即使传递jobs，也需要补普通分支调用。
3. `visualization/on_demand.py::build_guide`负责预制命中、按需生成与校验；`agents/task_service.py`负责已回答任务的延迟执行、状态和图解保存。前端guided组件负责实际展示。后续应沿用这些边界并核对取消、版本和权限。
4. `agents/response_composition_adapters.py::response_plan`、`agents/response_composition.py::plan_response`、`agents/teaching_strategy.py::runtime_strategy`共同决定策略投影；其调用方还包括AgentLoop和历史快照路径。既有测试已覆盖部分协议，新增测试覆盖summary/counterexample。

新增`tests/test_visualization_t0_reproduction.py`，以合成问题和脚本模型调用真实run_agent_loop_turn；文字回答为answered，但图解任务数为0。测试以expectedFailure保存期望行为，并单独确认失败断言确为“任务数0而不是1”。这是真实AgentLoop入口的隔离复现，不是真实模型或完整TaskService/浏览器回放；T2必须移除expectedFailure并补齐完整链路测试。

## 基线验证

- `python -m unittest tests.test_response_composition_adapters tests.test_response_composition -q`：24项通过，包括新增的总结/反例策略回归。
- `python -m unittest tests.test_psychology_visualization -q`：1项通过。
- 单独运行`tests.test_on_demand_visualization`并逐项归类：心理学配置下12项error，其中11项在旧教材定义夹具初始化时KeyError，1项因心理学目录不含旧欧拉模板ValueError；切换discrete-math后该套件14项中11项因旧教材`knowledge/pdf/manifest.json`不存在而FileNotFoundError，其余3项通过。旧教材资源已经替换，不应把这些旧夹具算作心理学测试成功，也不能据此断言被遮蔽的测试逻辑全部正确。
- 未调用外部模型，未做浏览器或完整TaskService图解验证。现有trace及状态仅可部分区分未排队、无模板和失败；未完成所有失败原因分类和真实运行配置核验，列入T2/T4，不宣称已经实现完整可观测性。

## 后续阶段入口

T1继续完善策略与内容块覆盖及兼容测试；T2接通普通对话的自动图解任务、错误状态和取消保护。考虑共享文件已有其他窗口改动，必须基于当前已核实的工作区逐段整合，并在独立测试数据库中验收。若使用独立worktree，需先获得包含上述未提交成果的稳定交接；不得从HEAD直接假设已包含这些成果。
