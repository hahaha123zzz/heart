# TA3交互卡片交付与验收

日期：2026-10-28。基线 `e2694607741bc980f5dd0e4bc5da196d157872f4`（TA2）。本批完成卡片协议、服务端动作与隔离验收；不切换正式服务、正式数据库或原生写入方。

## 原计划对账

| 要求 | 交付 |
| --- | --- |
| 保留页面、增量接入 | 沿用frontend/learning-cards.js/css、现有聊天渲染器及正文流式；不增加React或第二个聊天页面。保留v1三类展示卡，新增v2原生测评题卡。 |
| 最小协议 | schema、card_id、interaction_id、objective_id、revision、source_refs和allowed_actions。标识按学生/课程/会话隔离。字段与动作有边界，不接受模型脚本、HTML或任意URL。 |
| 已登记动作 | 正式题卡提交、规则评分、三级提示、完整解释、跳过、延后及返回当前绑定路径，走TA2和原生服务；题目/答案/来源绑定从服务端记录取，不允许客户端改内部任务或答案键。 |
| 展开复用、无额外模型 | 普通展示卡用原有PDFCitationRow.reference保存展开状态，CAS与command_id收据去重；原生卡状态在原interaction.result内保存，不新增学习表。已生成内容直接读取，点击与刷新不触发LLM。没有缓存帮助时不显示对应动作，不伪造提示。 |
| 不泄露解答 | 原生帮助由可信宿主登记并进入审核绑定HMAC。未请求完整解释前，分步讲解和对比内容不下发，不能用隐藏DOM代替保密。答案键不进入公开卡片；明确查看解释后才公开相应讲解。修订答案键后旧帮助失效。 |
| 服务端恢复与失败重试 | pending/sending/failed状态，失败重新开放按钮并保留选项；未知是否提交成功时重试同一command_id。新的一次提示操作使用新命令。评分已提交而卡片响应丢失时，继续同一请求，不重复成绩。 |
| 来源与删除 | 普通卡核对会话、账户、epoch与文档版本；原生卡继续复用TA2来源/授权。未核验的历史正式题卡在服务端恢复前不展示成绩或可操作按钮。教材换版或删除不伪造成功。 |
| 进度语义 | 讲过读取真实explained记录；显示独立/辅助证据数量及待答，不把阅读/展开画成掌握率。TA4未启用时不生成假的到期复习项。 |

## 两条接线及权限

1. 当前宿主展示卡：聊天回答保存 → learning_cards/v1 → 主页面展开 → `/api/learning/cards/expand` → 原回答的reference；刷新从服务器恢复。`view_revision`与正文/task revision分开。卡片动作不修改正文、成绩或学习位置。
2. 原生正式题卡：受控宿主登记题目及帮助 → 原生 `/internal/heart/native/assessment/cards*` → v2公开投影 → 主页面 `/api/learning/cards/action` → 服务端私有绑定 → TA2/native LearningService → 原interaction/证据 → 更新只读对话投影。

私有接口新增：`cards`、`cards/configure`、`cards/action`。configure仅持宿主凭据的服务可用，学生页面没有审核或答案参数。宿主代理只接受对话/卡片ID和有限动作，`_native_assessment`由服务端保存；history过滤下划线内部字段，桥接token不进入浏览器。

主页面代理沿用 `DEEPTUTOR_NATIVE_ENABLED`，默认关闭。原生worker或授权未就绪时拒绝，不回退为旧辅助评分。旧聊天仍走既有Q3；原生正式入口迁移及生产路径激活继续归NT3。

正式题卡的返回动作只向**当前已绑定路径**提供，不跨路径切换，不隐式建计划或推进目标。交接包含实际path_id/objective_id；跨路径恢复仍沿用已有路径交接服务及其活动回合/租约限制，未借本批绕过限制。

## 源码复用

固定DeepTutor `6cf793bd868ba5ecbe64722936d4be8fab5a01df`，Apache-2.0。实际动作调用TA2已接入的LearningService/原生SQLite。阅读上游`web/hooks/use-card-submission.ts`、`web/lib/mastery-question.ts`、`web/components/chat/home/MasteryQuestionCard.tsx`，参考发送/失败/重试及按question_id恢复的做法。宿主是已有vanilla JS，因此适配协议和渲染，不复制React组件或增加React构建。

相关文件哈希与UPSTREAM_SNAPSHOT一致，来源及“原生复用/宿主适配”边界见NATIVE_FULL_SOURCE_NOTICE.json。未改vendor，没有新AgentLoop、评分器或学习数据库。

## 自动验证

- 原生联合45项通过，1009.065秒，`.runtime/ta3/native-final-tests.log`。包括TA2、工具授权、教学提示及首批卡片状态测试。
- 补齐宿主代理→真实原生私有HTTP路由联测后5项通过，26.074秒，`.runtime/ta3/native-cards-final.log`；修订键后旧帮助失效、延后状态补验5项通过，30.765秒，`.runtime/ta3/native-cards-review-final.log`。最终交付定向结果在下方收尾核对记录。
- 最终定向5项通过，26.679秒，`.runtime/ta3/native-cards-final-delivery.log`，增加原生真实讲解记录到进度卡的验证。以上集合重叠，不重复累加。
- 宿主回归229项通过，201.798秒，`.runtime/ta3/host-regression-final.log`。包含教法、偏好、Q3/Q5、选区及检索桥接；后续代理/边界定向12项通过，9.047秒，`.runtime/ta3/host-proxy-tests.log`。
- Node的`tests/learning-cards.cjs`、`tests/learning-card-actions.cjs`通过，含转义、动作白名单、失败重开、重试命令一致、新操作新命令、原答恢复和延后显示。app.js与learning-cards.js语法检查通过。

测试集合存在重叠，不相加为独立案例总数。单测中的审核、教材来源和部分模型输入为明确夹具；宿主代理联测执行真实FastAPI与原生存储/服务，不用模拟评分结果，但不是跨进程部署验收。

## 真实模型与浏览器

- 宿主真实模型：隔离8038、`.runtime/ta3/live/{host,course}.sqlite3`，run `7fdb61ba0e`。概念对比卡answered，13.12秒、6条来源；分步卡answered，4.06秒、4条来源。均保存实际对话，三种展示卡正常。这是单次观测，不宣称整体加速或p95。
- 原生隔离8040：真实Q2原文/版本、真实模型生成三级提示/讲解/两类展示内容，原生服务与SQLite执行动作；审核批准与宿主身份受控，不是实际教师审核或正式首页原生接管。
- 浏览器最终19项通过，`.runtime/ta3/browser-report.json`、`browser-attempt4.log`：当前首页展示卡服务端展开恢复、刷新零生成、上标引用、375px；原生组件页失联后同命令重试、三级提示、完整解释后才出现解题卡、展开恢复、当前绑定路径定位、原答保留、评分一次、辅助证据及刷新恢复；无pageerror。
- 追加历史保护3项通过，`.runtime/ta3/browser-unverified-report.json`：用明确的历史响应夹具验证未核验成绩不先显示，服务不可用时保留原回答；重新启动后的真实main路由拒绝未登记卡片。此项不冒充真实历史/教师数据验收。
- 已查看`host-mobile.png`和`native-mobile.png`，375px正文可读、题卡及表格未造成页面横向溢出。

保留失败：首轮脚本把`full_explanation_seen`字段误当私有完整解答，修正为检查实际秘密正文；浏览器第1/3次未可靠等待异步持久化后即断言/刷新，第2次假设服务端折叠状态为空。服务端事件实证分别是3次帮助和`expanded=[0,1]`，最终改为轮询接口确认再继续。失败日志/报告不覆盖为成功，不因此放松业务断言。

## 完成与未启用范围

本批可交付TA3协议、页面组件、宿主代理和持久动作；普通展示卡已真实首页验证，正式题卡动作已接口/隔离组件页面验证。正式首页由真实聊天自动产生、评分并恢复原生题卡的完整跨进程流程，仍需NT3单写入接管及TA5验收；不把组件页写成正式首页通过。

教师审核界面、视觉评分、跨路径切换、TA4正式到期复习及长期学习效果未完成。主页面代理默认关闭；未合并main、未推送、未改正式8000、正式库、发布ready或教材索引。运行产物、模型配置、数据库和教材不纳入Git。

2026-10-29收尾：本地独立交付分支`codex/ta3-cards-20261029`，8038/8040隔离服务停止；后续TA4在该提交上继续，不占用正式服务。
