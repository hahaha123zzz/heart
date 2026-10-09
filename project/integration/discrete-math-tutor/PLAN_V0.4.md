# 离散数学助教 Demo：当前边界与后续计划

原版本的 Interaction Router、Student State、Teaching Planner、短期教学计划和学生画像继续保留。此次改造加上了离散数学教材检索、DeepSeek 接口、简短回复与学生卡住时的降难度处理。

当前优先级：

1. 让真实学生使用 `2-chat.bat` 验证图、集合、关系、逻辑等章节的学习体验。
2. 收集教材引用错位、公式/图片缺失、回复过长、误判掌握度的案例。
3. 再考虑将教材 Word 中的公式/图片结构化。
4. 增加针对真实教学质量的人工评价；离线 mock 只能验证流程。

架构约束：保留一个 Orchestrator 和一个 LLM 客户端；教材检索只在 `knowledge/textbook.py`，测试账户隔离只在 `database/`，避免服务类继续膨胀。
