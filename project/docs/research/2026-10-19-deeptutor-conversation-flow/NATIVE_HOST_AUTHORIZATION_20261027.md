# NT3原生回合的宿主任务复核

日期：2026-10-27。状态：宿主复核接口及原生接收端调用已实现，正式学习写入仍未切换。本批未提交、未部署。

## 发现与改动

此前 `native_requests` 保存了 `memory_epoch`，但start/status/events/reply只检查原生注册表，未向当前宿主核对。旧epoch因而只是记录，不能阻止宿主删除记忆后恢复原生旧回合。

复用 `task_projection.checked_task`、既有TaskRequestRow和宿主Repository，不建立另一个epoch或任务库。新增私有 `POST /internal/heart/native/authorize`，通过既有bridge token认证，检查：

- 当前服务课程；学生/会话/任务归属、账户存在与过期。
- task revision、取消/过期、当前memory epoch与原对话是否存在。
- request_id是否实际属于该学生/会话/任务。
- 请求教材版本集合是否等于宿主已保存的context快照，且仍与当前PDF登记版本相同。

响应只返回授权结果和请求身份/版本字段，不回传提问、答案、学习画像或教材正文。读取接口不修改数据库。

原生 `NativeTurnBridge` 在首次启动、状态恢复、流开始、DONE发出前/流结束及ask_user回复前调用该接口。status/events/reply使用原生登记时的epoch与教材快照，不能由浏览器覆盖。取消不要求任务仍有效，保留失效任务清理通道。

宿主不可达、凭据失败、响应身份不一致或宿主拒绝都使原生调用失败；不回退到“默认允许”。不增加LLM调用，也不逐token请求宿主。所有原生内容仍为 `pending_verification`，不直接成为正式回答。

## 运行配置

原生进程 `DEEPTUTOR_HOST_URL` 默认 `http://127.0.0.1:8000`；隔离验收应指向自己的宿主端口。沿用DeepTutorBackend的本机HTTP地址检查、禁止重定向与禁用系统代理；宿主/原生进程配置相同的 `DEEPTUTOR_BRIDGE_TOKEN`。密钥只保留安全配置，不写入本文或测试日志。

本批未修改 `.env` 或其已有未提交改动，也未启用 `DEEPTUTOR_NATIVE_ENABLED`。原生worker安装/正式路由启用仍需后续统一交付。

## 流中断修复与失败记录

删除授权在流中失效的专项触发内层异步生成器延迟关闭，出现ContextVar token跨Context释放错误。原生stream和NDJSON帧生成器改用标准库 `aclosing`，确保退出作用域前关闭内层订阅。

首次专项还有一项测试失败：测试把return_value写在patcher上，没有改变实际mock，因此“换版”并未发生。修正测试后版本变化被真实接口拒绝。初次日志 `.runtime/teaching-modes/native-authorization-tests.log` 保留；后续9项通过且没有上述Context错误，见 `.runtime/teaching-modes/native-authorization-final.log`。

## 验证方式与边界

宿主使用真实隔离SQLite和FastAPI TestClient；原生使用固定vendor真实应用层/协调器/会话库，受控能力替代模型。新增联验将原生默认授权方法接到真实宿主ASGI接口：有效任务可执行，增加宿主epoch后相同回合恢复及重放被阻断，不再调用模型能力。该联验没有跨TCP启动服务，不宣称独立部署或真实模型通过。

原生协议原有测试显式mock宿主授权，继续只验证原生协议；其通过不作为宿主授权通过证据。授权专项单独验证默认回查失败、响应身份错误、错误学生/会话/课程/request/revision/epoch、账户删除、任务取消和教材换版。

联合回归：`test_native_learning_authorization / test_deeptutor_native_runtime / test_native_learning_binding / test_native_learning_session_state / test_deeptutor_projection`，40项通过，106.699秒，日志 `.runtime/teaching-modes/native-authorization-joint.log`，无Context释放异常。宿主入口/接入边界回归日志 `.runtime/teaching-modes/native-authorization-host-regression.log` 输出 `Ran 18 tests / OK (skipped=1)`；其中上游回合存储测试类因runtime环境没有vendor而跳过，不能算该类通过。语法编译及定向diff检查通过。

随后在现有 `.venv-deeptutor` 单独补跑上述回合存储类：6项通过，3.642秒，日志 `.runtime/teaching-modes/native-authorization-turn-regression-native.log`。此前两次辅助命令额外加入vendor根后，上游同名tests包遮蔽宿主命名空间，导致模块导入失败；日志 `native-authorization-turn-regression.log / native-authorization-turn-regression-final.log` 保留，最终直接使用原生环境运行宿主测试，无需改源码或安装依赖。

## 未完成的关键事项

这不是完整删除传播或原生学习单写入完成：

- 尚未物理清除原生历史、迁移快照及所有派生学习证据。
- 尚未把epoch检查接到每个原生学习写入事务，也未保证后台回合在宿主删除发生瞬间停止。流中已发出的内部草稿仍需宿主正式发布门禁拒绝。
- 宿主TaskService的正式原生请求分支、学习状态唯一写入、完整取消/删除/刷新浏览器验收与回退未接通。
- 教材源文件实际字节、选区与视觉身份仍由Q2证据发布复核，本接口的版本集合核对不替代它。

因此原生候选继续不激活，正式评分与到期复习不启用，不标记TA0、TA2或NT3整体完成。
