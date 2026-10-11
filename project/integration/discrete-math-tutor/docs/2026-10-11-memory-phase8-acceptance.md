# 第八阶段：跨会话个性化与练习证据验收

## 结论

记忆已经接入新会话的真实教学规划与回答生成模块：保存的偏好改变生成提示和普通回答的长度限制；已否认误区不再触发当前误区策略；超过最近 20 条范围的相关历史及练习来源可进入模型输入，其他学生记录不进入当前学生的提示。

本轮修复了练习记忆的两处分类问题：原始提交摘要遗漏独立作答标记，以及仅根据 confirmed 判断规则核验。对已有分项证据，检索索引重建时也重新核对原事件的批改方式和帮助记录，必要时降低验证类别。

8 项新跨会话场景及 52 项相关回归，共 **60 项通过**。这证明工程接线和约束生效，不证明真实模型的个性化教学质量、评分准确性或长期学习收益。

## 验收方法

- 每个案例使用独立的临时文件 SQLite；新建 MemoryManager 模拟下一会话，不依赖上一实例的状态缓存。
- 普通教学回合运行真实 TutorOrchestrator.handle_turn；教材、路由、状态观测和质量核验使用确定性测试输出。
- 使用真实 ResponseGenerator、TeachingPlanner、TeachingPolicy；RecordingLLM 记录实际收到的模型消息。规划模拟返回空结构以验证真实 Policy 的确定性回退。
- 回答模拟输出固定的长文本，验证偏好进入生成提示与实际长度限制；不能把这个长度实验当作模型语义适配能力评估。
- 不调用真实 API，不加载 GPU 或 embedding 模型，不修改用户数据库，不重启现有服务。

## 八个新场景

|场景|观测结果|
|---|---|
|偏好保存后开始新会话|实际生成提示分别包含 140/240 字限制、举例频率和学习节奏；普通长文本输出的最终长度随限制改变|
|清除偏好后开始新会话|回答长度恢复默认 200 字，已清除偏好不再出现在画像中|
|逐项否认误区后开始新会话|当前 has_misconception 为 false，未选择 error_based_learning；掌握估计不因否认而升高；更正陈述可检索|
|旧历史及学生范围隔离|超过 20 条的相关标记进入真实生成提示；另一个学生的私密标记不进入|
|独立规则作答后继续教学|question_id、version、submission_id 和 rule_verified/independent 到达新回合上下文；仅提问不额外抬高掌握估计|
|AI/未知批改方式|即使异常输入 confirmed=true，也只按 ai_provisional 进入索引及新证据，不能冒充规则核验|
|旧分项链接错误分类|重建派生索引后，原事件显示 AI 批改及辅助作答的条目被降级；原始审计链接保留|
|获得提示后的规则作答|可以记录规则核验的结果，但 independent=false，不能当作独立能力证据|

## 排查和修复

### 误区摘要疑点：未复现

最初检查 StudentState.has_misconception 时怀疑旧摘要会覆盖 dismissed 状态。实际追踪发现该兼容摘要字段未在 KnowledgeStateRow 中持久化；新 MemoryManager 从数据库重建状态时，以具有状态的误区列表判断。新测试验证更正后的状态、Policy 及生成输入，未发现这一跨会话错误，因此没有修改误区逻辑。

### 练习摘要缺少独立性

database/memory_index.py 生成原始 exercise 条目时只有 assisted，缺少统一上下文所消费的 independent。修复为仅当当前学生的关联事件明确记录 assisted=false 时，摘要标记 independent=true；无关联事件或帮助情况不明时保持 false。

### 规则核验分类过宽

原始 exercise 索引只检查各小题 confirmed；分项写入则仅排除 method=ai_assisted，未知方法仍可能算规则核验。

现在两条路径都要求 **confirmed is True 且 method == rule**。混合或未知方法的整次提交摘要保守地标为 ai_provisional，各分项保留自身类别。

已有分项链接在 sync_memory_index 时依据原事件 feedback.parts、observation_key 和 assisted 校验：仅降低证据等级，不将旧 AI 证据升级为规则核验。原始成绩、事件和审计链接不改写；索引 metadata/content_hash 更新后旧向量缓存失效。

## 文件与检查

- 新增 tests/test_memory_personalization.py。
- 修改 database/memory_index.py、memory/memory_manager.py。
- 修复前的确定性失败见 [before-fix.log](artifacts/memory-phase8/before-fix.log)、[legacy-before-fix.log](artifacts/memory-phase8/legacy-before-fix.log)。
- 最终检查见 [after-fix.log](artifacts/memory-phase8/after-fix.log) 与 [acceptance-summary.json](artifacts/memory-phase8/acceptance-summary.json)。
- 三个 Python 文件 py_compile 通过，定向 git diff --check 通过。

运行命令（先在独立进程明确使用隔离 DATABASE_URL、LLM_MOCK=1）：

~~~text
.venv/Scripts/python.exe -m unittest tests.test_memory_personalization tests.test_memory_retrieval tests.test_memory_events tests.test_memory_management
~~~

测试 setUp 自行创建临时 SQLite 并替换 SessionLocal，实际密钥不参与测试。现有 datetime.utcnow 弃用提示不影响这批检查。

## 当前能力和剩余工作

1. 偏好、相关历史、误区现状和练习来源已经到达教学规划/生成链路；真实模型是否遵循这些信息尚未在本轮测量。
2. 练习事件仍不会自动改变概念掌握度：题目尚缺可靠的知识点/技能/误区映射，不能因为一道题的规则核验就宣布整个知识点已掌握。
3. 画像偏好是生成控制，不是经过实验确认的学习风格；当前掌握估计、策略观察权重尚未校准。
4. 本轮 session 指新 MemoryManager 实例，不是完整操作系统重启或多设备实验；浏览器操作链路沿用第七阶段结果。
5. 后续应优先补齐题目到技能及误区的映射，再验证练习反馈如何驱动有证据的教学调整。若做真实模型效果验收，需要单独恢复已停止的真实 API 测试；本轮没有恢复。
