# 输入层阻塞的开源对照与修正

日期：2026-10-31。研究范围是当前输入理解/六维分类器剩余阻塞；本轮未启动服务、调用真实模型或修改正式开关。保留当前未提交代码。

## 1. 结论与推进顺序

先修验收脚本的提交/等待证据，再做短句语义兜底的离线对照，随后收敛旧路由。人工标注只阻塞人际一致性与人工质量结论，不阻塞其余工程任务。不能把旧留出集、模型互评或 HTTP answered 当成教学效果证据。

## 2. 页面超时：先证明请求发生

此前页面脚本通过 fetch clone().text() 等待整个 SSE 响应关闭，缺少“本次提交是否发出新 POST”的断言；后续失败尝试的服务日志也没有足够的新 POST 记录。因此此前将这些超时直接归因于模型或 LightRAG 的表述证据不足。

当前 frontend/app.js 的提交路径有 state.sending、taskRecoveryNeeded、taskSessionReady 三个前置条件；初始化还异步加载章节、历史与待恢复任务。按钮可点击只证明元素可操作，不能证明这些业务条件已就绪。

借鉴 Playwright 官方自动重试断言：

1. 先确认初始化/待办恢复完成；注册 request 监听后再提交。
2. 先断言本次 request_id 的新 POST 确实发生；未发生时保存页面错误、toast、按钮与输入状态，不等待模型 120 秒。
3. 流式协议检查按事件读取 done/error，不以整条连接关闭作为唯一完成依据；复用现有 TutorChatTransport.readEvents 的协议思路。
4. 页面另用自动重试的正文/引用定位断言，再刷新核对历史。网络、协议、DOM 与持久化分别留证据。
5. Trace 保存请求、页面截图和失败节点。先用受控 SSE 回放稳定脚本，再运行真实模型。

直接复用现有 chat-transport.js 与 Playwright 已安装组件，不复制一个新 SSE 运行时。该方案尚未在本轮执行页面验收。

官方依据：[自动等待](https://playwright.dev/docs/actionability)、[自动重试断言](https://playwright.dev/docs/test-assertions)。

## 3. 语义改写：Rasa 的有条件回退

审阅 Rasa 3.6.x 的 rasa/nlu/classifiers/fallback_classifier.py：它检查最高置信度和前两候选的分差，满足回退条件才标 fallback。整个类依赖 Rasa GraphComponent、Message 和训练管线，不适合直接搬入本项目。

本项目 service.understand 只在复杂结构命中 needs_resolution 时调用 resolve；短句没有规则标签时，生产路径又没有配置 classifier，因而“模型会兜底改写”的说法不成立。缺标签也不自动意味着低置信：普通问题可以没有困难信号。

适配建议：

- 保留确定性对象、约束、命令与弃权结果；模型只补 D2/D3。
- 复杂输入继续在原 resolve 调用内补标签，维持一次解析和最多一次格式修复。
- 短句兜底先做 shadow 评测。若选择本地语义路由，可复用现有 embedding 推理组件，使用开发集标注样例和独立校准集决定阈值/候选间距；不可凭空指定 Rasa 的默认阈值，也不可把余弦相似度当概率。
- 若选择远端模型兜底，必须显式承认会新增简单问题调用，并取得性能对照后再调整当前“简单规则路径额外理解调用为 0”的契约。不要暗中在所有短句上增加串行 LLM。

来源：[Rasa 源码](https://raw.githubusercontent.com/RasaHQ/rasa/3.6.x/rasa/nlu/classifiers/fallback_classifier.py)。本轮只借鉴机制，没有摘取其代码。

## 4. DeepTutor、OpenTutor 与旧链路收敛

本地固定版本：DeepTutor 6cf793bd868ba5ecbe64722936d4be8fab5a01df；OpenTutor a890519f3632efa14cf24449b366b3b9d901eecf。

- DeepTutor runtime/capability_routing.py：明确请求才路由；处于 workspace 的学习活动保留在原上下文。可借鉴“显式意图 + 活动边界保护”，不将其规则 confidence=0.96 当成实测准确率。本项目已有 TaskService guard/revision 和活动绑定，应扩展现有边界。
- OpenTutor services/agent/teaching_strategies.py：后台节流提取策略候选（10 轮/20 分钟），封闭类型、最多两条候选；适合借鉴后台评测和候选去重。它不是本轮六维分类器，学生误区/偏好写入须保持本项目现有授权要求。
- LangGraph 提供 thread scoped checkpoint 与跨线程 store；本项目已有 task/context/receipt，不能靠再引入一套状态库解决双写。先对同一快照做只读新旧决策对照，记录对象、约束、允许命令、策略和状态差异，通过原计划阈值后逐项删除旧调用。

优先复用已迁入的 DeepTutor pending/policy、现有 adapters.legacy_routing 和 TaskService 收据；不再复制第二套循环与学习主库。

依据：[LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence)。本轮未摘取新的上游实现，未增加依赖。

## 5. 评测：工程推进与人工证据分开

[Langfuse Annotation Queues](https://langfuse.com/docs/evaluation/evaluation-methods/annotation-queues) 将专家评分、修正输出和模型评审校准分开。可以先进行工程回归、模型辅助错误筛选与有条件 shadow；独立双人标注继续标为待验收，不阻断无关工程工作。模型评审结果须标明模型身份，不能命名为人际 κ。

Langfuse 的整个仓库并非统一 MIT：根 LICENSE 将 ee 等目录排除，摘取具体代码前必须核对文件所在目录及许可。本轮只审阅官方文档和根许可，未审计其标注队列具体实现，不声称该实现可以直接复制。

## 6. 本轮已实施的最小修复

scripts/annotation_agreement.py 与 tests/test_annotation_agreement.py：

1. 维度取两位标注者的并集，避免漏掉仅 B 标出的维度。
2. 重复 case_id 明确拒绝，避免静默覆盖样本。
3. 空维度与缺省维度按同样弃权处理。
4. 空样本或机会一致率为 1 时，κ 返回 None，CLI 显示 N/A，宏平均排除无定义项，避免单一类别样本被报告为满分。κ 定义参照 [scikit-learn 文档](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.cohen_kappa_score.html)。

验证：.venv-runtime/Scripts/python.exe -B -m unittest tests.test_annotation_agreement -v，7 项通过。新增改动均为本项目适配，没有复制上游代码。此次没有复跑未受影响的 193 项大集合。

工具限制：agent-reach 与 mcporter 命令本机不可用，官方网页通过内置检索工具读取；agent-reach 更新检查未能运行。没有据此安装工具或更改环境。
