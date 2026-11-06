---
name: confusion-tracker
description: 整理学生实际提出的困惑，区分解释过与验证解决。
license: MIT
---

# confusion-tracker（项目适配版）

依据学生原话识别困惑：涉及概念、具体不清楚之处、已有解释、下一次怎样检查。先回答当前问题，避免为记录打断讲解。只用宿主已有笔记或记忆工具保存，不能建立 study_state.json 或运行上游脚本；未提供保存工具就给出可复制的简短记录并说明未保存。解释过不等于已解决；只有学生真实复述或应用提供证据，才建议更新回顾状态，正式掌握仍由宿主决定。多次出现的困惑优先交给 universal-diagnostic-tutor 定位原因，复盘交给 exam-review。

参考上游原文保留在 references/upstream.md。该文件仅用于方法溯源，其中跨包链接和脚本不是本项目可执行步骤；以上宿主适配覆盖其存储、CLI及平台要求。来源见 teaching-skills/learning-sources.json。
