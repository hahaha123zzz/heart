# 教学多入口联合验收与暂停恢复修正

日期：2026-10-26。范围：TA5中与TA1/TA3现有能力有关的选区、问题卡和刷新联验。工作区改动未提交；未切换8000、正式数据库或教材发布状态。不是原生完整迁入、正式评分或TA5全阶段完成证明。

## 1. 发现与最小修复

`TaskService`恢复ask_user时，已按补充回答重新计算上下文和教学约束；但`LocalAgentLoop._initial_messages()`直接返回暂停前的messages，忽略新`LoopRequest.system_prompt`。因此宿主已经选择新教法时，模型仍可能收到旧教法/授权说明。

先增加两个失败测试，确认普通恢复仍收到`OLD_POLICY`，无system消息的兼容记录也没有补入当前宿主约束。失败证据：应用`.runtime/teaching-modes/resume-policy-before.log`，2失败，未改写为通过。

修复仅在已验证的原ask_user工具答复替换成功后，使用本次宿主提示替换首条system消息；兼容历史缺首条system时插入。保留其他来源system消息、原user消息、tool_call/tool配对、任务身份、累计轮数/预算，不再次开始任务，不修改输入快照。源码：`agents/agent_loop.py`；测试：`tests/test_q3_agent_loop.py`。

本轮未修改原生vendor或另建循环。完整原生迁入仍按NT0—NT8推进；当前修正属于现有Q3宿主兼容链。

## 2. 相关自动测试

```powershell
& .venv-runtime/Scripts/python.exe -B -m unittest tests.test_q3_agent_loop tests.test_q3_task_loop tests.test_q3_entrypoint tests.test_selection_loop tests.test_teaching_modes tests.test_teaching_evidence tests.test_learning_cards tests.test_review_followups tests.test_q5_learning -q
```

131项通过，93.358秒；日志`.runtime/teaching-modes/entrypoints-regression.log`。该集合与此前162项集合不同，不能相加或当作全库测试。此前记录的基线兼容失败保持不变。

## 3. 真实模型与教材

固定8026隔离服务和已有隔离host/course SQLite，使用`.venv-runtime`、实际固定教材和真实模型。新增复现脚本`.runtime/teaching-modes/check_entrypoints_live.py`；开启已有`SELECTED_TEXT_AGENT_LOOP_ENABLED=1`，其余教学/Q5开关沿用先前隔离服务。未调整正式开关或安装依赖。

最终运行`1ee33512c4`全部断言通过：

| 场景 | 结果 | 单次耗时 |
| --- | --- | --- |
| 先问讲解方式 | ask_user暂停，同一任务保留 | 2.55秒 |
| 选择直接讲、不出题 | answered，7条引用，无待答/评分/掌握增加 | 11.53秒 |
| 同一答复命令重放 | 相同任务、revision和正文 | 0.06秒 |
| 真实PDF文字选区直接讲并分步展开 | answered，4条引用，共享选区循环 | 4.62秒 |
| 不重新圈选，要求换简单例子 | answered，原选区target不变，4条引用，无评分/掌握 | 3.75秒 |

报告`.runtime/teaching-modes/live/1ee33512c4-entrypoints-summary.json`及同前缀逐轮文件；控制台日志`entrypoints-attempt5.log`。耗时仅为本次功能记录，不是提速对照。

客户端选区预览故意使用伪造文字，实际响应只使用服务端PDF原文；公开结构及JSON工具参数不包含私有答案字段。系统提示中的工具字段说明不等于答案键泄露，不用对字段名的全文搜索冒充安全检查。

## 4. 真实浏览器

Playwright运行`mvp9q2dr`，四次真实页面发送均经原有SSE链路，无API替身。16项通过：问题卡暂停/选项可见、刷新后同任务且零生成、点击真实选项继续同任务、直接教法、引用证据、选区共享循环/分步卡、伪预览未入回答、追问同目标、求助不评分、刷新零生成/卡片恢复、手机无横向溢出、无pageerror。

问题卡由页面点击选项；PDF坐标来自真实教材，测试通过现有选区草稿和聊天表单提交，没有模拟鼠标拖选PDF，因此不声明原始划选手势已验收。

报告`.runtime/teaching-modes/live/mvp9q2dr-entrypoints-browser.json`，含实际四次结果。桌面截图同前缀`-entrypoints-desktop.png`。首次缩放截图捕获侧栏过渡中间态，补充375px稳定布局检查：输入框完整位于视口内、历史加载零生成，证据`-entrypoints-mobile-stable.json/png`。测试脚本已等待布局过渡，保存在`.runtime/teaching-modes/playwright-teaching-entrypoints.cjs`。稳定手机截图已人工查看。

## 5. 保留失败与边界

- `entrypoints-attempt1.log`：脚本健康检查误用路径；未执行功能验收。
- `entrypoints-attempt2.log`：脚本将工具参数说明中的字段名误当成答案键；改为检查实际结构和JSON参数，不计为产品泄露或功能通过。
- `entrypoints-attempt3.log`：修正前两入口真实验收通过，但不能代替最终修复后证据。
- `entrypoints-final-live.log`：重启尚未就绪时连接拒绝；保留为失败，最终有效运行另存attempt5。
- `entrypoints-browser-attempt1.log`：DevTools读取SSE响应体失败；改为仅旁观真实fetch响应的clone，不改接口/响应/模型，最终浏览器通过记录另存attempt2。
- 正式题卡、独立评分、复习到期/延后/完成及统一原生学习存储仍待NT3。视觉区域选区、正式练习、新教法完整取消/删除/并发矩阵未在本次真实页面联验，不声明TE01—TE18全通过。
- 测试只用合成学生，8026隔离服务交付前停止；无新增表、数据库迁移、密钥复制或正式启用。
