# 输出速度实施记录

日期：2026-10-24。独立 worktree：`E:\项目\heart\.worktrees\output-speed`，分支 `codex/output-speed`。

## OS0 基线

- 主线基线：`be7cc9c7b18530b2660d5df33cede4efbd76e10f`。8000 保持既有 `2ae1e5f` 固定导出，不用正式服务做压力测试。
- 已核对流式完整依赖链，采用 `4bf24d934dba605a27c1d1a3ddf42592b4797be9` 及全部祖先；合并基础 `0bd95c0`。唯一冲突为 app.js 错误状态列表，保留 Q5 和流式双方状态。
- 原 E 盘基线导出发生 WinError 112（磁盘已满），尚未启动或查询；只删除本次不完整导出，保留工具失败堆栈。改用 C 盘临时目录，完整教材和独立候选逐项复制，7 个核心文件哈希一致；未清理其他窗口。
- 隔离基线 8016：`C:\Users\free\AppData\Local\Temp\heart-output-speed-20261024\baseline`，`setup.json` 记录完整 SHA、路径、候选哈希。
- 冷启动定义请求：224.687 秒，失败（不计成功性能）。第一次工具120秒超时后，迟到结果仍分配来源号，第二次工具从4开始；最终未保存。原始收据 `baseline/cold-definition.json`，内部阶段 `baseline/stage-observations.jsonl`；仅观测包装，不改变任何检索/模型结果。该样本不代表热启动中位数。
- 基准运行器：应用 `scripts/benchmark_output_speed.py`；对每类按 A/B、B/A 交替，分别记录首进度、正文 delta、完成、原始收据和失败率。不把失败草稿首字当有效首字；无 p95 声明。

## 执行状态

代码改造与针对性回归进行中。OS01—OS16 真实模型、页面和20%性能目标尚未验收，不据代码存在标记完成。
