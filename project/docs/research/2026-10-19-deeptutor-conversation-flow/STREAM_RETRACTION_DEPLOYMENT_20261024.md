# 流式撤回正式8000切换记录

2026-10-24 15:55完成核对。授权：用户在交付后明确要求“切换”。本次切换到已交付的稳定release，不合并main或复制其他窗口未提交改动。

## 运行身份

- 运行代码：`17f8944cda993ed639ccc43e5b361fd69adcaf33`，功能修复基线`a693dfb`。
- 实际8000监听PID：19700；cwd：`E:/项目/heart/.runtime/stream-switch-20261024/release-17f8944`。venv启动器PID54876与实际监听子进程区分记录，证据以`verified-runtime.json`为准。
- `/health`正常、mock=false；线上app.js/chat-transport.js/practice.js哈希与同一release一致。
- 当前原阅读器构建已保留，reader.js SHA256：`cae56d95ffe3c022ce12699235f7c8d1f8db105f20a068b9d9633c89a98c6992`。
- 旧PID43308身份/cwd/创建时间核对后停止；旧release仍在`E:/项目/heart/.runtime/response-portable-20261022/code-proof-2ae1e5f/project/integration/discrete-math-tutor`。其相对原2ae归档只有reader.js覆盖，已保留。

## 数据与配置

两个SQLite仍使用原项目路径`ai_tutor.db`、`ai_tutor.experimental-psychology-3.db`，没有用测试库替换。停旧实例时无ready/executing任务；SQLite backup一致性备份及integrity_check通过。最终逐表逐行哈希核对：切换前所有既有记录仍在且未修改，仅添加专用验收测试账户及记录；详见database-preservation.json。备份仅存本机，不提交Git。

候选路径仍为`E:/项目/heart/.runtime/response-portable-20261022/candidate`，7个核心文件哈希不变；教材515文件逐项核对，staging/ready=false及原图pending状态未更改。未重建索引。模型、CPU embedding/rerank、线程数、Q5和LightRAG配置沿用旧实例；密钥仍仅运行时读取原ds.env，没有复制或打印。

## 8000真实页面验收

| 场景 | 秒 | 结果 |
|---|---:|---|
| 冷启动自变量概念 | 110.768 | saved，LightRAG，无fallback |
| 热概念 | 23.509 | saved，LightRAG，无fallback |
| 原句“给我解释一下图1-4，我有点看不懂” | 14.589 | saved，actual_backend=q2_figure，无fallback，image-01-0006实际像素 |
| 不存在图99-99 | 7.124 | rejected，无伪原图解释 |
| 真实工具过程取消 | 1.536 | cancelled，无本轮保存 |

前三项均一次POST、最终收据200、刷新历史一致、工具造成的空正文替换0次。主SDK可得tokens分别9815、9476、10052；未返回金额，不估算费用；原生LightRAG调用/缓存见原SSE及报告，不与循环汇总重复相加。冷启动本次成功不代表所有请求保证120秒内完成。

证据目录：`E:/项目/heart/.runtime/stream-switch-20261024`。其中before.json、release-preflight.json、verified-runtime.json、result.json为身份与核对记录；browser-live与browser-guards保留全部SSE、截图、收据和尝试；live-acceptance.json含实测指标。服务日志持续增长，evidence-manifest.json记录的是封存时文件签名。

## 回退与剩余边界

旧release、索引及数据库备份均保留。必要时执行：

```powershell
& E:/项目/heart/.runtime/response-release-20261022/.venv/Scripts/python.exe E:/项目/heart/.runtime/stream-switch-20261024/rollback.py
```

脚本只停止cwd匹配本次新release的8000实例，恢复原代码/配置；保留当前数据库，避免覆盖切换后学习记录。回退脚本已准备，因线上验收通过未实际触发回退。

此前隔离记录中的“未切换”描述是历史状态，以本记录为准。本次是17f稳定交付的正式端口验收，不等于main最新2803d8d及其他窗口未部署功能已合入；R03真实供应商延迟tool_calls与真人多标签页全量验收仍未完成。没有将专项成功改写为全项目或全部矩阵通过。
