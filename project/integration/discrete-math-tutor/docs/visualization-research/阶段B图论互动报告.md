# 阶段 B：欧拉图互动、状态恢复与数学验证

日期：2026-10-12。状态：阶段 B 已实施并通过隔离验收；图提问与学生记忆联动属于阶段 C，尚未接入。

## 用户可见功能

开放试点时，对话输入区显示“图论互动”。点击创建四顶点环，并在一条持久化助手消息中显示辅助图。支持：

- 通过两个端点选择框添加/删除边；不接受自环、重复边、未知端点。
- 拖动顶点，保存布局。
- 查看后端计算的度数、奇度顶点、连通性及欧拉通路/回路结论。
- 刷新当前标签页，恢复图和布局；聊天更新不重建画布。
- 保存回包丢失时，明确提示并以同一请求编号重试；图版本冲突时读取最新状态。

这是辅助示例，不是教材原图。没有生成任意 HTML/JS，也没有调用模型。

## 教材语义核对

实际教材位置为第 7 章第 7 小节“7.3.1欧拉图及欧拉路径”，不是第 8 章欧拉公式。

`knowledge/textbook_text/第7章图（新）.txt` 的定义 7.18、定理 7.11/7.12要求遍历所有顶点和边，且明确允许单个孤立顶点的特例。本试点采用全顶点连通约定，有孤立点的多顶点图不满足条件。

四节点环加一条对角线后：恰有两个奇度顶点，有非闭合欧拉通路、没有欧拉回路。两个互不连通的环即使全部顶点偶数度也不满足要求。

后端复用 [NetworkX 欧拉图算法](https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.euler.is_eulerian.html)，没有自行实现欧拉判定引擎。规格验证最多 12 个节点、30 条边；算法层允许单节点以检验教材特例，首个用户模板固定四节点，当前不能添加/删除节点。

## 技术实现

|模块|实现|
|---|---|
|图引擎|Cytoscape.js 3.33.1，固定 npm 版本与 lockfile；复制 UMD 资源及 MIT LICENSE 到本地静态目录，无运行时 CDN|
|算法|NetworkX 3.5，requirements 固定版本；实际项目虚拟环境已安装|
|规格|models/visualization.py，Pydantic strict/extra forbid，边规范化、有限坐标、受控操作|
|状态|visualizations 表保存规范图与布局，分别使用 revision/layout_revision|
|收据|visualization_operations 表保存请求哈希与结果，重复提交不重复操作|
|保存接线|创建图时在同一事务保存 assistant conversation、Artifact 和可追溯行为事件，直接取得数据库消息 ID|
|组件|frontend/visualizations/graph.js 使用既有消息组件接口；事件中止、ResizeObserver 与 Cytoscape 实例在删除时释放|
|服务|visualization/service.py 与 visualization_api.py，main 注册路由；SQLite 使用即时写事务保护版本检查和写入|

图引擎的基础能力与许可证参考 [Cytoscape.js 官方文档](https://js.cytoscape.org/)。图与布局最终以服务端为准；操作后重新读取最新状态，防止早前收据或聊天缓存覆盖新图。

### 接口

- GET `/api/visualizations/capabilities`：可用性、模板、知识点、删除 epoch。
- POST `/api/visualizations`：受控模板创建；请求必须包含当前 expected_epoch。
- GET `/api/visualizations`：恢复当前学生/会话的最近图。
- GET `/api/visualizations/{id}`：归属核验与最新状态。
- POST `/api/visualizations/{id}/operations`：增删边或保存布局，带 request_id 与 expected_revision。

本阶段只提供探索模式。请求不能指定评分、掌握度或其他教学模式。提示与测评的字段投影、图状态作为 AI 对象的接线留待阶段 C/D；不要把当前可查看结论的探索图当作独立测评。

## 删除与一致性

- Artifact 的学生和消息外键设置 ON DELETE CASCADE；操作收据级联关联 Artifact。
- 记忆管理能列出图关联知识点；忘记该知识点时清理图、收据和关联消息，并增加现有 memory_epoch。
- 带旧 expected_epoch 的迟到创建请求被拒绝；已经删除图的操作返回不存在，不会自动重建图。
- 增删边和布局操作不写入掌握度。创建仅保存行为来源，不代表理解知识点。
- 范围检查沿用本机 Demo 的 student_id/session_id 约定；没有新增登录认证，不能将该检查称为完整生产身份鉴权。
- 当前完整聊天历史仍是学生粒度；图的互动状态按会话恢复，其他会话中的历史文字可见但不能据此访问图。

## 验收与修复记录

后端联合执行：

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_visualization tests.test_memory_management tests.test_conversation_identity -q
```

37 项全部通过，其中图模块 20 项、既有记忆管理 15 项、历史标识 2 项。覆盖数学反例、单点/空边集、非法规格、创建幂等、操作幂等与冲突、布局、学生/会话范围、关闭/白名单、学生/消息删除、忘知识点、双线程竞争、HTTP 恢复及不增加掌握度。

真实浏览器测试 `tests/browser/graph-interaction.cjs` 使用实际静态页面、Cytoscape.js、FastAPI、NetworkX 与临时 SQLite。通过：

1. 加对角边后的判定正确，聊天重绘保留同一画布及新版本。
2. 真实鼠标拖动保存布局，数学版本不变，刷新恢复图 ID、边集与位置。
3. 故意在服务器完成保存后丢弃响应，原请求重试不重复删边。
4. 重复边、自环、旧版本拒绝；冲突后加载新版本，跨会话读取拒绝。
5. 忘知识点后图消失，重新显式打开生成新图；无页面 JavaScript 异常。

联调发现首次开图时，未存在的测试学生和消息在同一 flush 中触发外键错误。修复为同一事务内先 flush 学生，再保存消息；新增首开新账户回归检查。还修正错误分类，非唯一键 IntegrityError 不再伪装成请求冲突。

第一次拖动验收失败是测试坐标落在聊天滚动区域的裁剪范围；测试先将画布滚入视口后执行真实拖动，完成验证，没有用 API 调用替代拖动检查。

现有 chat-lifecycle 和 task-clarification 两组浏览器回归全部通过。JavaScript 语法及 git diff --check 通过。既有 datetime.utcnow 弃用提示未造成失败。

## 开放、构建与回退

默认 `VISUALIZATION_ROLLOUT=off`，未修改实际 .env、未重启正式服务。试点启用方法是在启动进程设置 `VISUALIZATION_ROLLOUT=test`；重启该进程后，测试账户显示“图论互动”。`allowlist` 需设置 `VISUALIZATION_STUDENT_ALLOWLIST`，且仅允许真实数据库中已有的测试账户。配置错误在业务初始化前暴露。

从代码重新准备依赖：

```powershell
# 项目根目录；现有虚拟环境下补充本阶段依赖。
.\.venv\Scripts\python.exe -m pip install networkx==3.5
# visualization-client 目录
npm ci --ignore-scripts --no-audit --no-fund
npm run build
```

数据库新增两张表，沿用 init_db 的 create_all，在启动时幂等创建；没有改写旧表。部署前备份数据库，停下在途写入后启用新代码。临时验收服务没有运行真实 main 或连接真实学生数据库。

回退试点时设置开关 off 并重启进程：拒绝新创建/操作，现有图只读，保留历史数据和新增表。当前进程模式不提供跨进程配置热更新。

图拖动状态与回退为本阶段验证范围；模型迟到回答的版本/epoch guard、提示约束、独立提交及正式灰度仍须下一阶段实现和验收。

## 下一步

阶段 C：添加 visualization_target，把后端验证的图快照接入现有 TaskService、教材检索与 MemoryManager，提供“解释当前图”和“只给提示”，并阻止图已变化或知识点已忘记时的旧回答写回。
