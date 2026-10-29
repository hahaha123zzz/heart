# TA4复习队列与可解释调整交付

日期：2026-10-29。基线：TA3 `f45854f6ffe2b2c1b82ed52ea463ab7a1fe4e92f`。本批完成原计划TA4的代码与隔离应用验收；正式启用仍由NT3/TA5负责，未切换8000服务、正式数据库或学习写入方。

## 原计划对账

| 要求 | 本批实现 |
| --- | --- |
| 原生调度器 | 直接调用固定上游RetentionScheduler/SpacedRepetitionScheduler.replay/build_review_queue，不新增固定间隔算法。受管正式证据强制DEBUG_MODE=false，使用秒时间戳与天级间隔；页面明确北京时间。测试可注入服务器时钟，公开接口不接受用户伪造now。 |
| 有效证据与原因 | 只消费TA2 reviewed_key/reviewed_rubric；未审核旧观察不覆盖最新正式证据。不可靠来源进入待核对，不当作遗忘或负面掌握。显示到期、曾用帮助、需巩固及待核对混淆的原因与evidence_id。没有校准掌握率或遗忘概率展示。 |
| 待复习列表 | 现有学习记录和首页列表接原生队列；同一知识点的新队列与旧弱项建议去重，保留实际练习订正。队列不依赖记忆worker、LLM或第二套学习数据库。 |
| 用户决定 | 开始、延后1/24/72小时、完成、返回。页面默认延后一天，私有/宿主API限制在白名单内。延后是独立用户选择，不伪改原始调度截止时间。到期不改当前教学模式、不自动推进或强制出题。 |
| 同一作答链 | 复习题是审核原题的新interaction，复用题目/答案键/rubric和TA2评分，不复制原成绩。提示、看解释、跳过和延后不是独立回忆；同周期“提示→返回→重开”继承帮助，不能洗成独立成绩。概念开放题继续待审核，不能由完成按钮代替评分。 |
| 位置与完成 | 保存原学习模块/知识点位置；复习不移动该位置，返回仅放弃本周期待答题，不关闭别的待答题。已评分后显式确认完成，完成事件与评分各有原生收据，失败重试不重复提交。 |
| 证据调整 | 仅使用实际作答/帮助/混淆假设和用户选择；原生提示增加“观察性线索不代表因果最优、调度值不是已校准掌握概率”的约束。pyBKT/pyKT保留以后有标注数据时的离线评估，不在本批训练或假称接入。 |

## 接线与授权

`LearningService评分/修订 → 同一原生事务同步调度 → 原生reviews API → 宿主review_api → 现有LearningReview列表 → 显式操作 → 原生题卡 → TA2评分 → 下一周期`。

- 新增`integrations/deeptutor/review.py`、宿主`review_api.py`及`frontend/learning-review.js`；沿用原生interaction.result、learning_evidence、repetition_states与事务事件，不新增学习表。
- 私有`/internal/heart/native/assessment/reviews`、`/reviews/action`；公开`/api/learning/reviews`、`/action`。公开请求只接受已保存conversation_id和有限动作，内部学生/课程/路径/题目/任务从服务端绑定取。
- 公开题卡来自既有PDFCitationRow.reference；每个复习尝试只投影一条assistant记录。未知响应失败保留原command_id；CAS冲突要求恢复，不能重用陈旧revision硬写。
- 新增专用`/internal/heart/native/authorize-assessment`：已发布题卡可独立于聊天TTL核验，不给旧聊天生成续期。账户、学生/会话/课程、记忆epoch、冻结教材版本和原题HMAC继续核对；用户取消、非过期修订、删除和换版拒绝。无持久题卡时仍要求原聊天任务有效。首次核验把服务端教材快照补存到题卡，支持后续任务清理。
- 普通聊天的`/authorize`和原Agent工具授权不放宽。原生服务写入前/事务提交仍回查宿主。跨库删除的极短竞争窗口依然归NT8，不据此宣布分布式事务已解决。
- 仍以`DEEPTUTOR_NATIVE_ENABLED=1`为启用前提，默认值未改。普通Q3聊天不自动创建原生题目；正式原生接管继续依赖NT3。

## 自动验证

以下集合重叠，不累加为全库测试总数。原生测试使用`.venv-deeptutor`；宿主测试使用`.venv-runtime`；数据库均隔离。

- 原生联合56项通过，266.102秒，`.runtime/ta4/native-verified-final.log`。包含测评、题卡、队列、授权、提示策略；补充真实TTL清理产生expired/revision变化的修正后，4项过期revision/任务清理专项通过，`.runtime/ta4/expired-revision-final.log`。不是将定向结果拼成同次全绿。
- 宿主此前相关回归230项通过，84.283秒，`.runtime/ta4/host-regression-final.log`；最终卡片/旧建议/教法/提示/适配76项通过，27.950秒，`.runtime/ta4/host-ui-final.log`。
- 收尾保留冻结教材快照时发现一次字典重复关键字异常，已修复；最终宿主题卡/展示卡/旧建议25项通过，17.543秒，`.runtime/ta4/card-final-delivery.log`。失败保留在`card-freeze-final.log`。
- 上游原生调度器原测试43项通过，`.runtime/ta4/upstream-scheduler-tests.log`，未改vendor。
- Node `tests/learning-review.cjs`、`tests/learning-cards.cjs`、`tests/learning-card-actions.cjs`通过；动作白名单、转义、未知失败同命令重试、新动作新命令、已评分恢复通过。JS语法与指定文件diff空白检查通过。

## 实际HTTP、浏览器与重启

隔离宿主8039运行实际main.app；独立原生8041运行实际App/SessionBridge/LearningStore，授权经真实HTTP回查宿主，不替换授权函数。测试用固定原题与受控教师批准，教材SourceRef来自此前Q2真实核验，提示内容来自TA3真实模型缓存。初始证据时间注入三天前以构造到期条件；这不是宣称已完成三天真实学习实验。本批操作本身不用LLM，故未把操作通过写成新模型生成通过。

- 18项核心页面检查通过，`.runtime/ta4/browser-functional-report.json`：到期原因、乱序刷新保护、键盘延后、刷新保留、位置与证据不变、开始响应丢失后同命令恢复、提示/返回/重开、作答响应丢失后重试、完成重放、单次事件、每次尝试一条对话、公开历史不含内部绑定/答案键、帮助不被返回重置、下一周期安排。该脚本之后点击隐藏的移动端按钮失败，未将整次运行伪标passed；移动端单独复验。
- 实际停止并重启原生进程，再停止并恢复宿主进程；保留原SQLite、学生、会话和凭据。旧聊天任务设为过期并由实际页面恢复逻辑标记expired/revision变化。复习周期、到期时间、作答/证据数量、待答及位置保持，`.runtime/ta4/restart-report.json`及后续页面复验。
- 6项页面恢复/布局检查通过，`.runtime/ta4/restore-browser-report.json`、`restore-browser-delivery.log`：过期聊天与重启后的队列、375px无横向溢出、评分卡恢复、无新聊天请求、无pageerror。窄屏检查进入相应页面并关闭侧栏后切换viewport，不代表全站移动导航专项通过。截图`mobile-review.png`、`mobile-card.png`。

## 保留的失败与修复

- 原生旧类型映射缺失导致scheduler KeyError：按已有KnowledgePoint.type补足，不凭空默认memory；补测通过。
- 原生旧choice证据evidence_id为空导致周期碰撞：为已有带question_id的事件补稳定标识，不升级审核或成绩；新复习仍独立interaction。
- 页面陈旧队列覆盖新revision、迟到响应切回聊天：加入刷新序号/账户校验，刷新期间禁用旧动作；导航在刷新前完成，CAS冲突恢复最新状态。
- 聊天TTL及expired revision误拦持久复习：新增专用持久题卡授权，未放宽聊天授权；账户/删除/取消/来源负例补测。
- 浏览器测试本身先后有路由完成顺序、未等待动作完成、隐藏移动按钮与侧栏定位问题；保留attempt1—7及restore-browser*.log，成功子项与失败原因分列。
- 一次联合测试56项中的1项仍把所有回查限定旧/authorize路径；更新为两条明确白名单后定向5项通过，再运行最终联合。没有改写旧失败日志。

## 交付边界

TA3代码与隔离验收已提交；TA4本批代码与隔离应用闭环完成。未合并main、未push、未启用正式原生写入或改.env。TA5完整TE矩阵、NT3普通聊天原生接管、NT8删除跨库一致性、实际教师审核及长期学习效果评估仍需单独完成。没有外部提醒、邮件、后台自动发题或pyBKT/pyKT拟合。
