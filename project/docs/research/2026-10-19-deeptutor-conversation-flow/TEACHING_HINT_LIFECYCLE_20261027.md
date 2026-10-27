# TA1三级提示、完整解释与原题恢复

日期：2026-10-27。状态：宿主辅助教学链已实现并完成隔离验收；本批未提交、未推送、未部署。没有接正式评分或原生统一学习写入，不代表整份教学计划完成。

## 实现及调用范围

- `TeachingTurn`沿同一待答题选择第1—3级提示；支持明确指定和“再给一个提示”，第3级之后继续请求仍为第3级，不自动公开完整答案。
- 复用`learning_feedback.HINT_FEEDBACK_RULES`：第1级定位疑点，第2级给方法/相似情境，第3级示范中间步骤并留一步。
- 仅发布成功后，随原题记录实际帮助类别、提示等级、事件顺序和`full_explanation_seen`；失败/取消/未发布不增加，重复发布按原任务身份去重。实际示例工具仍记为示例，不冒充已给提示。
- 用户明确选择完整解释时，完整回应原题，保留原题供自愿返回；恢复原题复用已核验原文与原题干，不再次生成。明确跳过/不要出题继续沿用既有取消待答语义，不强制保题或测试。
- 提示/完整解释后的作答继续保存辅助记录，保留原题、原话及来源关联，不产生独立掌握或正式成绩。
- 公共`teaching.assistance`和进度卡仅投影帮助计数、最高提示等级与已查看完整解释标记；不投影答案键、私有工具参数或内部事件。历史卡片可显示这些记录，刷新不重新生成。

修改既有`adaptive_tutoring.py / learning_feedback.py / learning_cards.py / agent_loop.py`、前端卡片渲染及静态版本号；新增`tests/test_teaching_hint_lifecycle.py`，扩展现有模式/Node测试。无新模型调用、表、依赖、评分算法或第二套学习库。

## 实测发现及修正

第一次真实模型出题在取证后仍反复调用retrieve/read_material，没有登记teaching_step；8轮、7次工具步骤后被门禁拒绝。证据运行`e90ec3ac06`与`.runtime/teaching-modes/hint-lifecycle-live-attempt1.log`保留。

根因是取证就绪后，所有工具schema仍然可见。现在仅当已有依据、且唯一未完成的必需工具为teaching_step时，只向模型提供该schema并要求工具调用；登记成功再开放最终回答阶段。没有放宽来源、工具授权、发布门禁、取消或预算。用既有宿主测试新增断言先复现，再修复，见`hint-tool-mount-before.log / hint-tool-mount-tests.log`。

## 验证

最终相关集合**186项通过，177.016秒**，日志`.runtime/teaching-modes/hint-lifecycle-regression-final.log`：

```powershell
& .venv-runtime/Scripts/python.exe -B -m unittest tests.test_teaching_hint_lifecycle tests.test_teaching_evidence tests.test_adaptive_tutoring tests.test_learning_cards tests.test_review_followups tests.test_q3_agent_loop tests.test_q3_task_loop tests.test_q3_entrypoint tests.test_teaching_modes tests.test_task_execution tests.test_q5_learning tests.test_selection_loop -q
```

9项提示生命周期专项覆盖明确等级/递进/封顶、重复与未发布、旧记录缺省、实际方法优先、完整解释后回原题/辅助证据、目标/来源变化与隐私、进度卡。Node卡片检查与差异空白检查通过。此前旧编排兼容失败未包含在本集合，不宣称全库通过。

真实模型最终运行`5bce12e135`：

| 回合 | 结果 | 单次耗时 |
| --- | --- | --- |
| 背景音乐音量/阅读速度情境出题 | answered，登记原题 | 16.84秒 |
| 第1级提示 | 同题，已发布等级1 | 1.86秒 |
| 再给提示 | 同题，等级2 | 1.47秒 |
| 再给提示 | 同题，等级3，未自动给完整答案 | 1.62秒 |
| 查看完整解释 | 同题，已查看完整解释=true | 2.91秒 |
| 返回原题 | 同题、原题干、0模型轮次 | 0.44秒 |
| 学生作答 | 同题暂定partial、非独立掌握 | 2.34秒 |

原题还要求说明自变量应具备的条件；学生只回答变量名称，因此partial如实保留，没有改写成答对。上述是单次功能记录，不是提速基准或教学效果证明。

只读数据库复核确认：实际提示事件顺序`[1,2,3]`、hints_used=3、已查看完整解释、4条原文来源关联、independent=false、formal_mastery=false。证据为应用`.runtime/teaching-modes/live/5bce12e135-hint-summary.json`、同前缀逐轮文件和`-hint-evidence-check.json`；脚本`.runtime/teaching-modes/check_hint_lifecycle_live.py`。

Playwright对同一真实历史完成**9项检查**：等级/完整解释记录恢复、辅助标签、无私有字段、卡片展开与刷新恢复、375px无横向溢出、查看/刷新零生成请求、无pageerror。报告同前缀`-hint-browser.json`，桌面/手机卡片截图`-hint-card-desktop.png / -hint-card-mobile.png`已查看手机展示。脚本`.runtime/teaching-modes/playwright-hint-lifecycle.cjs`。该浏览器验证是实际历史及卡片操作，七轮输入由HTTP真实模型脚本完成，不混称页面完整输入通过。

## 完成边界

- 只使用8026及隔离`host.sqlite3 / course.sqlite3`；隔离服务已停止，未操作正式库或重启8000。收尾探测8000连接未响应，不据旧发布记录声称当前仍在线。
- 临时任务TTL、跨长时间待答恢复仍受原机制约束；没有通过保留私有答案键绕过过期清理。
- 原生prompt/mode统一、正式题卡/评分/到期复习、视觉/练习全入口矩阵仍未完成，继续依赖NT3。TA1.3的宿主辅助教学部分已完成，TA1整阶段保持部分完成。
