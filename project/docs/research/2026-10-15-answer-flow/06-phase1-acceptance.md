# 第一阶段完成：普通解释分流

日期：2026-10-15。代码已修改、定向回归与真实模型对照已完成；未提交、push或主动重启正式服务。

## 实现

- TaskExecution.can_answer_directly复用已校验意图。高置信度question、明确explain/proof/example/hint/summary/compare走普通解释；作答、check_answer、practice、低置信度、旧版无扩展意图及明确系统学习请求保留原辅导链路。
- 普通解释跳过LessonPlanner、EvidenceExtractor、TeachingPlanner、StrategyRouter与StateUpdater模型调用。读取已有状态和偏好；TeachingPlan由既有任务要求确定，生成和质检仍共同消费它。
- 不创建、覆盖或推进课程计划。没有课程计划时，MemoryManager仍用原事务保存对话、事件、引用和后台记忆任务；保留memory_epoch、任务guard、幂等和冲突检查。
- 增加response_path仅作后端分流诊断，原有回答字段保留；lesson_progress可以为null，既有前端不依赖该字段。无新接口、依赖、数据库迁移或前端改动。
- 原生教材依据、补检索、回答核验与一次重写、图解及引用定位均保留。没有把已核验文字提前发布，本阶段仍沿用原done事件。
- 辅助例子明确标为“非原书例题”；补齐progressive_hinting的辅助标记，避免下一次作答被算成独立测量。

## 真实问题对照

使用scripts/accept_answer_flow.py、tests/data/answer_flow/psychology.json。实际调用原main._run_turn→TaskService→编排执行器，每个案例为独立合成学生，使用临时课程库，关闭图解和后台任务。--baseline仅将can_answer_directly固定为False，其余链路不变；不是模拟模型。原始结果逐题保留，包括失败。

|案例|基线调用→优化调用|基线秒→优化秒|最终分流|状态|
|---|---|---|---|---|
|解释自变量|9→4|22.985→31.344|direct_answer|两次均回答|
|比较随机抽样/分配|9→4|18.453→7.485|direct_answer|两次均回答|
|被试间设计日常例子|9→4|19.219→6.797|direct_answer|两次均回答；例子标记另作最终复验|
|检查错误理解|9→9|17.235→18.750|tutoring|两次均回答，仍指出每人只接受一个水平|
|仅给提示|9→4|16.844→6.328|direct_answer|两次均回答，未当成独立掌握|
|承接随机区组追问|10→6|21.297→14.125|direct_answer|基线质检拒绝；优化经历一次重写后回答|

数据摘要见05-baseline-comparison.json。每题只有一次采样，调用次数说明少走了哪些模块；耗时混有模型负载、冷启动和检索开销。自变量案例优化后反而更慢，不能据此宣称所有问题提速或一个固定改善比例。追问前后状态也不代表经过统计验证的正确率提升。

例子人工抽查发现未显式说明非原书，随后补充共享任务约束并用同一题复验：4次调用、12.422秒，输出“日常辅助例子（非原书例题）”，采用记忆方法A/B→记忆测验成绩，随机分组且每人只接受一种方法，未虚构实际结果。这是最终例子用例；上表保留修改前原始数据。

内容抽查：定义解释了操纵变量；比较覆盖两种随机化的目的与环节；作答检查指出被试间/被试内混淆；提示保留思考方向；追问承接随机区组、组内随机化及区组分析条件。模型核验passed不等于所有语义均已由教师认证。普通解释案例的mastery均保持初始0.5，step_advanced均为false；0.5是既有默认估计，不代表新生真实掌握一半。

### 原始文件

均位于项目artifacts目录，不写入正式学生库：

- answer-flow-api-baseline-20261015.json
- answer-flow-api-optimized-20261015.json
- answer-flow-example-final-20261015.json

最初的answer-flow-before-20261015.json和answer-flow-after-20261015.json直接调用底层handle_turn，绕过TaskService，缺少扩展意图；两者保留用于说明验收脚本修正，不纳入正式效果对照。最终脚本显式指定临时COURSE_DATABASE_URL并断言数据库路径，避免本地环境配置把测试导向正式库。

## 自动回归

最终105次测试执行通过，命令：

```powershell
./.venv-gpu/Scripts/python.exe -X utf8 -m unittest tests.test_answer_flow tests.test_task_execution tests.test_quality_guard tests.test_memory_events tests.test_memory_jobs tests.test_clarification_tasks tests.test_psychology_pipeline -q
```

包括直接解释/比较/提示、原辅导路径、已有课程计划保留、状态数值不变、记忆/偏好消费、核验拒绝、生成期间删除、并发状态冲突、事务回滚、幂等、后台任务和跨进程澄清恢复。105是测试执行数，不是本轮新增105个用例。

本轮补齐旧测试夹具的epoch和llm；改为mock课程检索入口，避免默认课程变化让旧数学夹具意外检索真实心理学教材。跨进程澄清测试原先只传DATABASE_URL，会在心理学模式下被派生为另一个文件；现明确传临时课程库，修复了这项夹具失败，没有放松业务删除或身份校验。初次失败记录保存在artifacts/answer-flow-regression.txt；最终记录为answer-flow-final-regression.txt。未安装pytest，沿用unittest。

## 限制与下一步

- 未做浏览器回归、生产服务复验、多人负载和真实学生学习效果试验。
- 真实对照关闭图解；其生成调用与时延不计入本表，不能宣称整套可视化端到端已提速。
- 学习模式暂由明确措辞保守排除，代码已注明限制；将来新增结构化学习模式时应替换该判断。
- 下一阶段才处理“文字核验后先展示、图解随后补充”和更完整的学生诊断。当前只完成已确认的第一阶段，不提前改SSE和前端生命周期。
