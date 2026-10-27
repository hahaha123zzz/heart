# NT3原生mastery工具的授权存储接线

日期：2026-10-27。状态：原生工具共用服务工厂的上下文适配已实现，正式单一写入与全部工具验收尚未完成。本批未提交或部署。

后续状态：另2项路径绑定工具已增加独立宿主适配，见[路径交接记录](NATIVE_PATH_HANDOFF_20261027.md)。下文保留本批工厂接线时的覆盖边界，不作为当前两项工具仍未适配的结论。

## 当前接线

此前受控LearningService只能通过桥接helper取得，原生工具中的 `_new_service()` 仍返回普通LearningStore。本批新增 `learning_tool_adapter.py`，在 `NativeTurnBridge.scope` 中建立请求上下文，将固定上游mastery模块的服务工厂在进程内替换为上下文工厂。没有替换全局LearningStore，也未修改vendor文件、复制工具execute或另建AgentLoop。

这是一处明确的适配层工厂替换，不能称作上游现成插件API。首次安装校验模块来源、固定源码SHA和原工厂归属；重复安装幂等，已有其他工厂实现时拒绝静默覆盖。

- 有宿主上下文：核对真实原生账户与工作区，构造上游LearningService + HostAuthorizedLearningStore。
- 宿主管理账户缺少上下文：拒绝退回普通存储。账户ID在映射登记中识别，不只依赖可变的用户名；启用原生运行时的bridge初始化会加载已有托管ID。
- 非宿主管理的独立原生环境：保留原工厂行为。
- ContextVar随原生后台任务和 `asyncio.to_thread` 传递；作用域退出恢复原值，不把上一轮任务信息留给下一轮。

没有改变现有模型/工具授权清单，没有新增工具挂载或打开正式评分开关。

## 具体覆盖

固定上游 `MASTERY_TOOL_NAMES` 共15项。源码AST核对其中13项通过 `_new_service()`，该共同存储入口现已适配：

`mastery_status / mastery_quiz / mastery_note_explained / mastery_grade / mastery_skip_question / mastery_repair_question / mastery_defer_objective / mastery_assess / mastery_build / mastery_mode / mastery_profile / mastery_revise / mastery_paths`。

这代表13项的工厂调用路径覆盖，不代表每项业务流程都已通过真实模型或页面验收。实际工具专项验证了原生 `MasteryNoteExplainedTool.execute`，它记录讲解、不授予掌握分；授权撤销后拒绝再次写入。

`mastery_switch / mastery_leave` 直接调用原生绑定服务，没有经过上述工厂，尚未补齐同等的提交授权边界。capability/pipeline/lifecycle中直接使用LearningStore的路径也未全部覆盖，因此不能标记“全部工具写入已统一”。

源码SHA与固定上游一致；AST台账 `.runtime/teaching-modes/native-tool-factory-audit.json`。vendor提交仍为 `6cf793bd868ba5ecbe64722936d4be8fab5a01df`。

## 验证

- 初批5项专项通过，43.673秒，日志 `.runtime/teaching-modes/native-tool-adapter-tests.log`。
- 工厂适配、写入保护、宿主授权、原生回合联合34项通过，256.611秒，日志 `.runtime/teaching-modes/native-tool-adapter-joint.log`。包括原生工具真实execute、后台任务/线程上下文、旧epoch拒绝、账户及工作区不匹配、原工厂兼容性。源码固定校验和托管ID启动恢复另有后续专项，不能将本轮集合相加为全库测试。
- 宿主轻量环境的私有接口/客户端边界14项通过，0.405秒，日志 `.runtime/teaching-modes/native-tool-adapter-host.log`。默认关闭原生运行时仍可加载接口边界，不要求宿主安装完整vendor依赖。
- 最终专项8项通过，46.408秒，日志 `.runtime/teaching-modes/native-tool-adapter-final2.log`；补充了启动恢复托管ID、账户改名后仍拒绝缺失上下文、不同工作区及外来工厂拒绝覆盖。第一次最终专项执行因工具stdout关闭中断，仅留下不完整 `.runtime/teaching-modes/native-tool-adapter-final.log`，不记为通过。语法编译与定向diff检查通过。

测试使用隔离SQLite、真实宿主ASGI授权和真实上游工具/存储；模型回答由受控能力替代。没有真实LLM、TCP部署或浏览器验收。正式库、索引、.env及现有worker未提交改动均未变更。

## 剩余与发布限制

正式TaskService入口尚未切换，旧Q5仍是现有运行链路；仍需对账原生worker挂载、两项路径绑定工具、其余直接存储调用、源身份与正式题卡、删除/并发竞争和回退。

当前存储授权仍通过同步本机HTTP复核，在原生同步工厂/读取路径上可能阻塞事件循环；未做生产延迟基准，不能据单测宣称提速或可承载并发。跨库授权返回与COMMIT之间的竞争仍未解决，候选不激活，正式评分及到期复习保持未启用。
