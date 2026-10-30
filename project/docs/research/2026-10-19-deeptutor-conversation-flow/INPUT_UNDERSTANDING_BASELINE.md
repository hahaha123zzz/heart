# 输入理解层执行基线

日期：2026-10-30。此文记录真实宿主验证，不把纯函数或替身回答当页面验证。

## 版本和隔离边界

- 原工作区：`E:\项目\heart`，`codex/ta5-acceptance-20261029 @ 816e78a1cd28b8db5f9a7b3741d292fdb82c04c0`。
- `main` 与 `origin/main`：`3b212250f774d2f461fb1676fd4bf2acd23bc475`。实施计划原先的 main 描述不准确；未在本轮合并 TA5。
- 实施工作区：`E:\项目\heart\.worktrees\input-understanding-v1`，分支 `codex/input-understanding-v1`，父提交 `816e78a`。
- 真实宿主：FastAPI → TaskService → 现有 Q3 AgentLoop / Q5。本轮没有另建 Agent 框架。
- 隔离端口：8147。每轮独立课程 SQLite，位于下述证据目录；未运行正式 8000 数据库迁移。
- 模型、GPU 模型缓存、教材从既有本机配置只读加载；不复制或提交密钥、教材、图谱、虚拟环境。
- 开启 Q3/Q5/辅助教学，关闭原生写入、会话同步、记忆后台任务。基线理解开关 off；实现验证 active，复杂解析另行验证。
- `.venv-runtime` 指向既有独立运行环境；`.venv-deeptutor` 用于原生测试，不合并两套 site-packages。

本轮新建的知识目录及运行环境 junction 均被忽略，不进入 Git。原工作区的教材删除、运行产物和其他未提交文件未覆盖、清理或重置。

## 证据目录

统一位于：`E:\项目\heart\.runtime\input-understanding-implementation-20261030`。

| 目录 | 用途与限制 |
| --- | --- |
| `baseline` | 实施前原宿主 16 轮 HTTP，保存 SSE、调用轨迹及数据库快照；首次请求早于启动完成，失败另存；初次浏览器遇到 402，不计通过 |
| `baseline-final` | 用户恢复余额后，重新以原工作区 816e78a 运行同小节页面四轮；没有载入新业务实现 |
| `active` | 第一轮实现的 HTTP、跨章/同小节页面证据；后续代码仍有修改，不作为最后代码全场景验收 |
| `active-final` | 16 轮 HTTP、7 轮浏览器、两次刷新和长期偏好确认；另保留复杂请求失败 |
| `active-verified` | 最后重启首次选错 Python，缺 fastembed 导致启动失败；没有据此改生产依赖 |
| `active-release-check` | 用正确运行环境重启最后代码，再运行仓库内真实 HTTP 验收脚本 |
| `active-commit-smoke` | 最后把理解移到任务认领后，又重启并实际出题→解释回题→恢复，核对保存身份 |

每轮脚本 `serve_deep.py` 记录实际 APP 路径与独立数据库；`deep-trace.jsonl` 记录上下文、理解/回答调用和教学评估阶段。日志可能含学生测试原话，只保存在受控本机证据目录，不加入公共仓库。

## 实证缺陷

1. 同小节页面出题后输入“先解释操作性定义，再回原题”：原版本 0.157 秒返回旧题，跳过解释；不是“回答变快”。轨迹未调用解释模型。见 `baseline-final/browser-same-reader-results.json`。
2. 阅读第一章背景时插问第二章待答题：原 HTTP/上下文证据显示 chapter 比较丢弃辅助 pending。模型可以复述旧题，但持久题目身份不在；不能按文字相似判恢复成功。
3. 长期偏好与当轮要求混在一起：当轮可回答，长期修改没有显式确认候选。后续实现使用现有偏好确认 API，不自动改画像。
4. 既有 `不给完整解释` 模式判断有误：在未修改原工作区复现同一教学模式测试失败；本分支修复否定词边界，保留基线失败日志。

这里是独立账号/会话上的功能对照，不是相同 SQLite 快照的受控性能 A/B；不计算整体提速比例。尤其原版本的快速跳题和修复后的真实讲解不是相同工作量。

## 入口与唯一写入方

| 入口 | 本批状态 | 写入方 |
| --- | --- | --- |
| 普通 Q3 / 旧 Orchestrator | TaskService 统一理解；明确单项请求可投影旧路由 | 原 TaskService / 对话仓储 |
| ask_user 暂停恢复 | 复用原 loop_state；原始要求和本次答复分开保存 | 原 TaskService 收据和 revision |
| Q5 计划生成/确认/插问/返回 | 理解在分流前生成，原 Q5 服务执行 | 原 Q5Runtime / SessionStudyService |
| PDF 文本/区域选区 | 接收既有校验对象，接线可用；新输入层页面矩阵未完成 | 原 PDF 定位 / selection_loop |
| 独立练习/可视化对象 | 接收既有 TaskObject；不改提交 API | 原 practice / 可视化服务 |
| 原生题卡/评估/复习 | 不打开正式写入开关；原生授权回归单独运行 | 原生授权服务，未新增第二写入方 |
| 长期偏好候选 | 当轮可读，确认前不落库；拒绝/刷新沿既有 UI | 原 Memory 偏好确认 API |

原生测试最初导入了虚拟环境 editable 安装的原工作区 DeepTutor，引发固定源码路径拒绝。校正 `PYTHONPATH` 和宿主 tests 包选择后复验，不放宽源码校验，不复制上游模块绕过检查。
