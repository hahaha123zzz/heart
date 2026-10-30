# GitHub学习Agent：源码核验与复用判断

日期：2026-10-15。使用agent-reach的gh只读后端；元数据、目录、下列实际源码和关键许可证已读。未安装或运行这些项目。提交固定，避免用旧架构名称推断今天的实现。

## 1. DeepTutor：共享上下文与有界执行

版本：`HKUDS/DeepTutor@6cf793bd868ba5ecbe64722936d4be8fab5a01df`，根许可证Apache-2.0。

已读[agent_loop.py](https://github.com/HKUDS/DeepTutor/blob/6cf793bd868ba5ecbe64722936d4be8fab5a01df/deeptutor/agents/loop/agent_loop.py)、[context_budget.py](https://github.com/HKUDS/DeepTutor/blob/6cf793bd868ba5ecbe64722936d4be8fab5a01df/deeptutor/agents/loop/context_budget.py)、[course_study/mode.py](https://github.com/HKUDS/DeepTutor/blob/6cf793bd868ba5ecbe64722936d4be8fab5a01df/deeptutor/capabilities/course_study/mode.py)。当前是能力共享运行时、工具循环、预算与ask_user暂停；课程模式强调推荐下一动作和移交，不直接承担课程讲解。不能沿用旧版本“固定若干解题Agent串行”描述当前主干。

对我们有用：共享当前请求、教材、学习状态、工具结果；设轮次/上下文预算并明确停止状态。现有TaskContext/TaskExecution已经具备部分基础，扩现有字段即可。循环本体约1800行且依赖自有runtime/context/stream等，不适合整文件移植；其预算后强制收尾策略也不能绕过我们的教材质检。

## 2. OpenMAIC：按问题验收、给工具执行上限

版本：`THU-MAIC/OpenMAIC@ecb940c136cc5b4ea56dc81b2505e64eff1dea29`，根许可证MIT，已读LICENSE正文。

已读[director-loop.ts](https://github.com/THU-MAIC/OpenMAIC/blob/ecb940c136cc5b4ea56dc81b2505e64eff1dea29/lib/chat/pi/director-loop.ts)、[tool-timeout.ts](https://github.com/THU-MAIC/OpenMAIC/blob/ecb940c136cc5b4ea56dc81b2505e64eff1dea29/lib/agent/runtime/tool-timeout.ts)、[answering-runner.ts](https://github.com/THU-MAIC/OpenMAIC/blob/ecb940c136cc5b4ea56dc81b2505e64eff1dea29/eval/orchestration/answering-runner.ts)。工具执行超时/取消被结构化返回；回答路由评测专门处理学生问题尚未被回答、Agent却继续讨论的情况。

借鉴：用户问题的完成条件、阶段预算、失败可解释和场景A/B。我们只有一个主要导师，不应复制多教师/同伴导演或“选到教师即正确”的评分；需要测具体问题是否回答完整。TypeScript运行器依赖pi与其事件协议，不能原样接入Python。MIT允许在满足许可条件下抽取局部代码，但工程上先移植测试思想最划算。

## 3. GenMentor：聊天和长期画像更新分开

版本：`GeminiLight/gen-mentor@7cb4d9ac7a062bebf4b0030597afce744d3e62c9`，根LICENSE为CC0-1.0。官方论文项目当前main已重建为TypeScript，原Python版在v0.1-demo/paper-python-v1；不能把旧论文分支接口当main接口。

已读[tutor.ts](https://github.com/GeminiLight/gen-mentor/blob/7cb4d9ac7a062bebf4b0030597afce744d3e62c9/app/src/lib/agents/tutor.ts)、[profile.ts](https://github.com/GeminiLight/gen-mentor/blob/7cb4d9ac7a062bebf4b0030597afce744d3e62c9/app/src/lib/agents/profile.ts)、[replay.ts](https://github.com/GeminiLight/gen-mentor/blob/7cb4d9ac7a062bebf4b0030597afce744d3e62c9/app/src/lib/llm/replay.ts)，以及[系统架构](https://github.com/GeminiLight/gen-mentor/blob/7cb4d9ac7a062bebf4b0030597afce744d3e62c9/wiki/02-system-architecture.md)。聊天函数消费已有profile并生成回复；画像是另一个操作；文档描述完成会话后排队评估。回放按请求散列，缺fixture明确失败，不悄悄调用线上模型。

适合借鉴：普通问答不必逐轮重算画像；学习动作/测验事件才驱动评估；录制/回放将工程验收与真实模型评估分离。不要复制localStorage档案替代服务器记忆；不要采用文档中“三分钟截止后继续”的确认规则——用户明确要求AI不能代替其决定，超时不能代表同意。也不复制其可选webSearch作为教材事实来源。

## 4. Verify-then-Generate：先诊断学生，再补救

版本：`eth-lre/verify-then-generate@161019e6cc29968bb9a9ae7f261daf63f00e6fc7`，README声明CC BY-SA 4.0；GitHub的license=null不代表无授权或可任意复制。

已读[main.py](https://github.com/eth-lre/verify-then-generate/blob/161019e6cc29968bb9a9ae7f261daf63f00e6fc7/verification_based_response/main.py)、[model.py](https://github.com/eth-lre/verify-then-generate/blob/161019e6cc29968bb9a9ae7f261daf63f00e6fc7/verification_based_response/model.py)：有baseline、joint、two_step、oracle对照；两步方案把预测的错误原因传给反馈生成。某些变体先让LLM生成参考解，再判断学生错误，这并不构成独立真值验证。

可改造离线实验与诊断输出结构，不直接作为线上正确性裁判。研究依赖MathDial、旧模型/API包装及步骤对齐；心理学应按教材诊断变量、分组、控制和因果推断。未提供作答的“什么是随机区组”不需要走步骤诊断。

## 5. OATutor：可抽取的小算法与审核过的提示内容

版本：`CAHLR/OATutor@a40eff7d0bd8073d2f82dd879dba22da2b320a55`，平台MIT，课程素材单独授权。

已读[BKT-brain.js](https://github.com/CAHLR/OATutor/blob/a40eff7d0bd8073d2f82dd879dba22da2b320a55/src/models/BKT/BKT-brain.js)：14行单函数，输入当前掌握、猜测、失误、学习转移参数和答题正误，更新估计。它不训练参数，也没有替我们校验输入和处理所有分母边界。

这种小算法有实际代码复用空间，但当前心理学缺已校准的技能题序列；不应在回答流程优化第一阶段接入。更优先借鉴题目→提示等级→学生作答→新题确认的组织，不能搬用代数题的教学内容或参数。

## 复用结论

|对象|原样复制|适合本轮采用|
|---|---|---|
|整个学习平台/Agent运行时|否：状态、依赖、协议与课程不同|保留现有FastAPI与Memory/RAG/Intent|
|小型无依赖算法|部分可以，先核验输入和测试|BKT作为后续候选，不为这轮强加|
|评测案例/运行器|可在许可允许范围内改造|先移植问题未回答、拒绝引导、错误诊断等场景|
|教学Prompt和数据|需课程改写及授权核对|教师审核后作为示例，不能当独立真值|
|预算、模式分流、画像触发、确认协议|最适合借鉴|复用本项目现有模块实现，避免框架迁移|

根LICENSE不是所有第三方依赖/数据/历史分支的统一授权。这里的许可为源码入口识别，不是完整法律审查；正式复制时记录版本、来源、所需许可与修改。
