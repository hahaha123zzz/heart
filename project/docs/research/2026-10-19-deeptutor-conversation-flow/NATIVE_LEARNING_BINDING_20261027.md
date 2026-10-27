# NT3原生账户、工作区、会话与学习路径绑定

日期：2026-10-27。状态：隔离候选接线及验证完成，本批未提交、未推送、未部署。仍不是正式单写入切换或TA0—TA5整体完成；本轮没有启动/重启服务或操作正式数据库。

## 1. 本批解决什么

上一批候选使用显式目录的原生LearningStore，尚不能证明真实用户/工作区/会话会访问到同一份学习库。本批复用现有NativeTurnBridge，建立真实原生身份、课程工作区、原生会话与候选路径关联，使用`LearningStore()`默认工作区路径，复核学习库确实位于该工作区内。

没有新造一套学生/会话ID算法、账户库、学习库或调度器。固定vendor仍为`6cf793bd868ba5ecbe64722936d4be8fab5a01df`，无上游源码改动。

## 2. 修改范围与边界

- `native_bridge.py`：将原账户初始化拆为`account_identity`，原`account`继续复用它并保留原模型配置流程；新增内部`bind_scope`，复用原`_bind`及注册表事务，只初始化身份/工作区/会话，不读取模型配置、授予模型/工具权限或启动回合。没有新增HTTP接口。
- `learning_migration.py`：新增`bind_candidate_sessions`。先检查原Q5活动绑定归属与会话格式，再在真实原生user_scope/workspace_context内调用原生默认LearningStore。保留原ID与迁移收据，绑定原生会话；如该会话已有另一条原生路径则拒绝，不能静默切换。缺少活动绑定时不新造宿主会话。
- `check_native_learning_migration.py`：显式`--bind-sessions`启用隔离原生home验证；默认模式保持原独立store流程。所有路径在同一asyncio事件循环中顺序处理，原生HTTPException记为blocked，避免将账户拒绝当作成功。
- `tests/test_native_learning_binding.py`：原生账户、工作区、会话、SQLite与租约均真实执行；只复用现有测试的受控能力/禁止网络模型设施。

源路径仍为archived、来源available=false、`activated=false / ready_for_cutover=false`。关联的是活动会话与路径，不冒充已迁移study/review模式、本次安排、画像、旧命令或辅助待答题。`owns_path=false`，不猜测哪一旧会话最初创建了路径。

绑定候选只在独立home内执行。注册表与各上游存储之间没有跨库整体回滚保证；中途失败可留已创建的隔离资源，重跑按稳定映射恢复，不允许据此在线切换。原生路径租约本批已验证，但尚未挂载到宿主在线请求生命周期。

## 3. 验证结果

使用已有`.venv-deeptutor`完整原生环境，无新增依赖。第一次误用`.venv-runtime`缺少pydantic_settings，记录`native-binding-before.log`；换用已有原生环境后，修复前5项因接口缺失失败，记录`native-binding-contract-before.log`。这些均不计通过。

原生桥/会话相关回归25项通过，170.456秒：

```powershell
& .venv-deeptutor/Scripts/python.exe -B -m unittest tests.test_native_learning_binding tests.test_deeptutor_native_runtime tests.test_deeptutor_sessions -q
```

日志`.runtime/teaching-modes/native-binding-regression.log`。后续补强工作区路径归属和双路径测试，最终绑定专项**7项通过，9.499秒**，日志`native-binding-final7-tests.log`。覆盖：

- 重复初始化返回同一原生映射，桥接账户保持普通user；没有启动原生turn，也不将测试模型密钥写入JSON。
- 同学生不同标签页共享正确工作区，学生/课程/会话分别隔离。
- 使用真实默认工作区LearningStore，原生会话可恢复相同候选路径，重跑不重置状态或新增路径。
- 缺失/外来绑定在创建原生课程前拒绝；已有其他路径不被替换。
- 两个已绑定会话争用同一路径时，直接复用原生租约拒绝第二个turn；释放后可重新获取。
- 同一工作区的两条路径分别保留自己的会话关联。

宿主Q5/迁移相关42项通过，50.714秒，日志`native-binding-host-regression.log`；原默认CLI在`.venv-runtime`中重新执行通过，见`native-binding-legacy-cli.log`。以上集合有重叠，不相加成全库通过；原生回归中的模型执行为受控能力，不计真实模型教学验收。

## 4. 真实备份隔离运行

使用原部署备份的1条实际Q5路径，在应用`.runtime/native-learning-migration/20261027-q5-bound-candidate/`建立独立native-home，成功绑定1个真实原生会话；1条课程映射、1个工作区学习库、1条路径，原生turn请求数为0。重复执行均为already_imported，数量保持不变，源备份SHA未变。学习库工作区归属验证通过，正式学习证据仍为0。

证据：候选目录`report.json / roundtrip-check.json / final-check.json`；应用`.runtime/teaching-modes/native-binding-candidate-attempt1.log / native-binding-real-rerun.log / native-binding-final-rerun.log`。本机目录包含私有账户资料、密码哈希及原数据快照，不提交远端，不包含复制的宿主模型配置。

复现时使用本机明确的学生ID：

```powershell
& .venv-deeptutor/Scripts/python.exe -B scripts/check_native_learning_migration.py `
  --source-snapshot .runtime/backups/teaching-20261026-211951/ai_tutor.experimental-psychology-3.db `
  --student '<学生ID>' --course experimental-psychology-3 `
  --output .runtime/native-learning-migration/<独立运行ID> --bind-sessions
```

## 5. 继续执行的门槛

后续仍需接正式入口授权与删除epoch传播、Q2教材导航、来源实时验证、自报理解/画像/本次安排及旧命令/待答题映射，然后验证唯一写入方切换与回退。正式题目、评分与间隔复习不能仅凭本批候选会话绑定启用。本批未修改worker候选、.env或前端入口，也未做真实模型/浏览器及在线切换验收。
