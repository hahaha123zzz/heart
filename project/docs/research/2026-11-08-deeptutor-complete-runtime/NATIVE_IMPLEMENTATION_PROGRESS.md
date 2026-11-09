# 整体改造实施进度

日期：2026-11-09。状态：实施中；未切换正式入口，未迁移正式用户数据。完整范围按NATIVE_132_IMPLEMENTATION_PLAN.md及Q1—Q10执行。

## 已实施

1. NativeTurnOptions补齐原生输入字段，保留服务器身份/租约字段禁入；新增缺省值不改变升级前宿主收据。移除bridge固定auto_route=False，保留原生配置语义。通用自动选择仍未实现，不能据此宣称完成。
2. 资源校验提取至knowledge/request_resources.py，原生与旧入口共享原有权限/版本校验。native_executor不再创建旧TaskContext/UnifiedContext；原生ContextBuilder与executor负责实际模型上下文。
3. 原生模式主程序不初始化旧教学组件；未迁旧入口通过带锁延迟装配保持可用。暂留LLMClient用于未迁教材/旧入口，不宣称整个产品无旧业务。
4. 从原生turn实际capability进行结果投影；原生自动出题可保留公开题目且过滤答案。
5. 直接复用MasteryQuestionCard与原生题卡解析；作答/跳过带mastery_answer/mastery_skip进入新请求。公开工具事件随页面历史保存，嵌套mastery_grade.result保持原协议；过滤原始工具正文及未答题私有字段。
6. 原生回答不再调用旧get_profile/read_version/append_exchange：epoch从现有任务授权仓库读取，宿主对话行仅为发布结果投影，不参与原生模型历史。原生模式不启动旧MemoryWorker，保留fixed_book生命周期。此为记忆阶段接线，不等于数据迁移和页面完成。

## 验收证据

- `.runtime/native-chat-chain/20261109-153848/report.json`：22项通过。真实宿主/worker/工具与受控模型，不代表回答质量验收。
- 原生协议/SQLite会话及执行器：21项通过。交付专项在嵌套评分修复后8项通过；原生启动延迟装配边界1项通过。
- `.runtime/native-mastery-browser/2026-11-09T07-49-47-898Z/report.json`：实际构建产物与原生组件，作答/跳过回调、评分恢复、页面无脚本错误。非真实模型判分。
- `.runtime/native-delivery-live/20261109-155333/`：真实模型检索及历史引用通过；Edge浏览器表单出题、私有答案过滤、同会话翻到PDF第2页/applied回执、刷新题卡恢复通过，errors为空，delivery.png已目视检查。该进程启动于记忆接线末次修改之前，不能替代记忆新接线的后续联验。
- 前端构建成功，SOURCE_NOTICE记录30个上游源文件及57个构建资源。

## 已定位但未计为通过

- 首次基线使用.venv-runtime缺少vendor导入路径/pydantic_settings；改用.venv-deeptutor后对应21项通过，不为测试安装重复环境。
- 旧离散数学TaskContext测试16项中5项因knowledge/pdf/manifest.json与exercises/catalog.json缺失不能运行；不为迁移编造教材/题库。
- 新题卡组件浏览器初次夹具缺UTF-8导致翻译乱码、按钮定位失败，修正测试页面后通过；原生组件无需改动。
- `.runtime/native-delivery-live/20261109-155116/`：GPU宿主环境缺lightrag，启动前失败，未调用真实模型；使用现有.venv-runtime重跑通过。

## 剩余必做

- 原生mastery真实模型出题→作答/跳过→判定→存储→页面恢复全链，以及分支/选文/指代/多意图输入矩阵；目前1-E/1-G仍未完成。
- 记忆原生API/页面、可靠旧数据迁移/只读归档、修改/删除对活跃任务的失效控制和真实跨会话注入；Memory/Journal/Learning权威来源仍需整体验证。
- 退出旧教学提示和评分业务覆盖，恢复原生LearningService/scheduler并保留授权与既有policy补丁。
- 原生练习、两种引擎接原生服务、本地资料研究、通用自动能力选择与任务暂停恢复、原生正文/结果组件、Word真实生成交付。
- 所有必交付真实浏览器/模型联验及正式切换前快照、迁移预览、恢复核对。

后续以真实模型与真实浏览器为主要验收方式；不把组件回调测试或工具目录存在当完整产品能力完成。
