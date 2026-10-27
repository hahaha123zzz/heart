# NT3原生学习事务授权适配

日期：2026-10-27。状态：隔离适配层与宿主受控服务入口已实现；未开启正式学习写入。本批未提交、未部署。

后续状态更新：13项原生工具的共同工厂已接本适配，详见[工厂接线记录](NATIVE_MASTERY_TOOL_FACTORY_20261027.md)。本文后面的“工具尚未切换”保留为本批次历史边界，正式入口及全部写入覆盖仍未完成。

## 复用边界

新增 `HostAuthorizedLearningStore` 继承固定vendor的LearningStore。原生save、transaction、CAS、题目状态机、评分/证据投影和回滚逻辑原样复用，不再实现一套事务或评分器。models/storage/service三份原文件SHA仍与固定清单相同，上游提交仍为 `6cf793bd868ba5ecbe64722936d4be8fab5a01df`。

唯一复制适配的部分是 `learning/storage.py::_connect` 的SQLite连接配置（Apache-2.0）：沿用timeout、isolation_level、row_factory、foreign_keys及busy_timeout，并设置 `cached_statements=0`。原因是SQLite的authorizer在语句编译时运行，保留缓存会使同连接重复COMMIT跳过检查。没有复制存储事务主体。

授权响应校验抽到现有 `DeepTutorBackend.authorize_native_task`，异步回合桥接与同步存储共用它；没有第二套身份/epoch协议。

## 授权与回滚

- 创建适配存储前、每次打开连接时复核宿主任务，读访问同样不能沿用已撤销授权。
- 使用SQLite原生authorizer，在BEGIN、COMMIT和事务外INSERT/UPDATE/DELETE前复核当前宿主身份、任务revision/epoch及教材快照。
- 授权失败返回SQLITE_DENY，由原生事务捕获异常并rollback，随后适配层还原宿主授权异常。ROLLBACK不要求授权，避免失效任务无法撤销未提交内容。
- 题目登记、答案、评分、事件和证据继续使用原生同一事务；不允许出现“成绩没保存但题目已消失”的半提交。
- 请求身份/资源快照深拷贝后固定，调用者修改原请求对象不能改变既有存储实例的授权作用域。

新增 `NativeTurnBridge.learning_service(request)`：从不可由前端覆盖的原生请求登记恢复epoch/教材快照，在原用户/工作区scope内构造原生LearningService和上述存储。此同步入口供后续受控学习命令使用，应在线程中调用；没有挂到逐token流路径。

## 验证

- 初批10项测试通过，17.419秒，日志 `.runtime/teaching-modes/native-write-guard-tests.log`。该轮包含重复导入的5项宿主授权测试，后已改为模块引用，不能当10项新增能力。
- 7项写入专项 + 10项授权 + 11项原生回合联合：28项通过，100.352秒，日志 `.runtime/teaching-modes/native-write-guard-joint.log`。日志内controlled failure是既有失败回放用例的预期模型替身异常，不是未处理的测试失败。
- 后补原桥接入口专项：1项通过，10.377秒，日志 `.runtime/teaching-modes/native-write-guard-bridge.log`。真实宿主SQLite/ASGI授权到真实原生工作区中的受控学习服务，检查存储根归属；宿主epoch增加后拒绝获得旧服务。
- 现有后端客户端边界13项通过，0.300秒，日志 `.runtime/teaching-modes/native-write-guard-client.log`。语法编译、定向diff检查及固定vendor SHA核对通过。

核心负例实证：原生grade_interaction已经计算成绩时递增宿主epoch，提交被拒绝；重新从原生库读取，revision未增，原题仍为registered/待答，quiz_attempts、掌握分、证据投影和复习队列均没有新增。另覆盖同连接第二次COMMIT不能复用旧授权，以及连接打开后撤销授权再做autocommit写入也会失败。

测试只用隔离库和受控能力，无真实模型、无跨TCP服务部署、无浏览器；未修改正式数据库。

## 必须保留的未完成边界

这是原生SQLite提交检查，不是跨宿主库与原生库的分布式原子事务。宿主授权返回与SQLite实际COMMIT之间仍存在竞争窗口；正式发布前仍须解决删除与提交的协调及删除后的派生状态清理。不得据此声明“删除绝不会与提交竞争”。

原生mastery工具当前仍在自己的工厂中构造普通LearningStore；本批没有全局猴子补丁，也没有切换这些工具到受控服务入口。正式TaskService接线、全量写入入口覆盖、恢复重放、取消清理、原生历史物理删除和回退仍需后续工作。候选仍不激活，正式评分和到期复习不启用，TA0/TA2/NT3不标完成。
