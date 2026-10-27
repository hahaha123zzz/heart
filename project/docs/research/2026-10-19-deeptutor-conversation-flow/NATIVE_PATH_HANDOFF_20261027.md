# NT3原生路径切换与离开接线

日期：2026-10-27。状态：宿主管理回合的路径交接适配已实现，正式入口未切换。本批未提交、未部署。

## 上游做法与适配原因

原生 `capabilities/mastery/binding.py` 按“释放旧租约→申请新租约→更新当前回合→尽力保存会话偏好”交接。`LearningStore.acquire_path_lease` 会先bind_session再检查目标租约。正常上游冲突会尝试恢复，但宿主授权撤销、会话写入失败等其他异常仍可能留下部分修改。

继续复用原生MasterySwitchTool/MasteryLeaveTool的参数、工具协议与结果，不重写工具execute。新增 `learning_binding_adapter.py`，在进程内适配两项绑定函数，非宿主管理回合继续委托原函数；固定vendor文件未修改。

SQL沿用固定上游 `learning/storage.py` 的路径/成员/租约表、初始路径和owner语义，并复用原生 `LearningProgress / sanitize_mastery_path_id / upgrade_workspace_preferences / publish_topic_signal`。这里需要适配事务边界，不能直接复制上游多次提交的顺序；来源与许可证已追加third_party/DeepTutor/NOTICE。

## 实际交接

- 工具上下文包含宿主核验键、真实用户/工作区、原生会话和submission身份；先验证会话/turn属于该活动submission及工作区。
- 学习库必须位于当前用户的当前工作区，会话库必须位于该用户根目录。只支持带db_path的原生SQLite会话库；其他后端拒绝，不能默默退回无保护流程。
- 使用授权LearningStore连接，ATTACH原生会话库后BEGIN IMMEDIATE。在同一次事务中检查目标、租约冲突，更新租约、会话成员绑定与会话偏好。
- 目标冲突在释放旧租约之前检查；未知/归档目标拒绝。普通SQL异常或提交前授权撤销时，两个库中的本次修改一起rollback。
- leave沿用会话自有scratch语义：保留原命名路径，切到该会话scratch、记录owner、清空mastery_path_id偏好。不产生掌握分或评分证据。
- 数据库提交后更新当前回合并发布原生topic信号。若当前回调失败，明确返回位置已保存、要求恢复；不谎称持久位置回滚，也不补偿覆盖可能的新状态。

工厂安装同时安装两项绑定适配，检查固定binding/storage/session/preferences文件SHA、原函数归属及重复安装标记。没有全局替换LearningStore，没有增加工具授权或开启mastery评分。

## 验证

- 初批6项专项通过，36.753秒，`.runtime/teaching-modes/native-binding-adapter-tests.log`。
- 路径交接/工具工厂/写入保护/宿主授权/原生回合联合43项通过，179.904秒，`.runtime/teaching-modes/native-binding-adapter-joint.log`。
- 后补工作区与固定依赖校验：原生switch专项1项通过，7.993秒，`.runtime/teaching-modes/native-binding-adapter-final-scope.log`。
- 已提交位置但live回调失败专项1项通过，7.776秒，`.runtime/teaching-modes/native-binding-adapter-callback.log`。不把重叠集合累计成全库测试数。

测试运行真实宿主SQLite/ASGI授权、原生SQLite学习/会话库、真实switch/leave工具和一个受控阻塞回合。验证目标占用、偏好写入trigger故障、提交前epoch撤销、伪造session/turn、缺少上下文、未知/归档路径、leave持有scratch及不增加掌握。测试收尾通过既有取消接口，未因epoch失效阻止清理。

没有真实模型、浏览器、独立TCP部署或断电测试；没有改正式数据库、教材、.env及已有worker改动。固定vendor源码和已有表结构不变。

## 剩余与发布限制

本批覆盖普通异常下的路径交接事务，不代表跨库崩溃原子性：SQLite多库且使用WAL时，断电恢复仍需单独验证/协调。宿主授权响应与实际COMMIT之间的竞争也没有消失。

13项工具服务工厂加两项路径绑定入口均有适配，不等于15项业务全部通过真实教学验收。原生mode偏好、capability/lifecycle直接存储、正式TaskService入口、唯一写入、物理删除传播、评分/复习完整规则及回退仍待完成。原生候选不激活，正式评分与到期复习不启用。
