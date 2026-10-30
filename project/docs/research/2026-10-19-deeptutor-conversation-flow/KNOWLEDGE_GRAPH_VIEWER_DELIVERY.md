# 独立知识图谱页交付（2026-10-23）

用户确认采用独立 8001 页面，保持 8000 助教运行。本次只新增图谱浏览器、静态页面和测试，不修改公共入口、数据库、教材、图谱或正式检索开关。

## 范围与运行

- 地址：<http://127.0.0.1:8001/>，仅绑定本机。
- 输入：`.runtime/response-portable-20261022/candidate`。
- 实际图谱：7,138 个实体、14,741 条关系；来源清单覆盖 11 章。
- 图谱 SHA256：`427b51f74e77a96f1c494007b43a7c3a336f8f763d669a6caf3b06b757f0cc42`。
- 复用现有 `frontend/vendor/cytoscape`，不增加依赖，不加载模型或 LightRAG SDK。
- 搜索全图实体；局部图默认最多 60 个实体，接口上限 150，连续展开显示超过 350 时切回当前实体局部图，避免全图布局阻塞。
- 支持搜索、缩放、拖拽、节点详情、邻居展开、关系详情、检索片段和来源 PDF。
- 节点及关系摘要明确标记“自动抽取候选”。关系不是自动确认的先修或考试重点。
- GraphML、检索片段先校验候选 `index_files.json` 中的哈希；PDF 按冻结清单 version 校验，失败则禁用链接并返回 409。校验是对候选清单的一致性校验，不是外部签名认证。
- 来源 PDF 仅定位整章；没有伪造段落级页码。浏览器不接收本机绝对路径。

新增调用链：`graph_viewer.py:create_app → GraphView → 固定候选 GraphML / chunks / PDF`。前端仅调用该进程 `/api/graph/*`。不接入第二套问答检索、学习循环或学习状态。

启动（8001 未被占用时，在 PowerShell 执行）：

```powershell
Set-Location 'E:\项目\heart\project\integration\discrete-math-tutor'
& 'E:\项目\heart\.runtime\response-release-20261022\.venv\Scripts\python.exe' graph_viewer.py --candidate 'E:\项目\heart\.runtime\response-portable-20261022\candidate' --port 8001
```

后台启动使用 `Start-Process -WindowStyle Hidden`。本次进程和日志登记在 `E:\项目\heart\.runtime\graph-viewer-8001`；只停止该目录所登记且命令为 `graph_viewer.py` 的进程即可撤下图谱页，不影响 8000。

## 当前用户体验使用的 RAG

读取运行中 8000 进程 PID 43028 的白名单环境，`Q3_RETRIEVAL_MODE=lightrag`。其运行目录是 `code-proof-2ae1e5f` 部署副本，不等于主工作区所有新代码均已加载。

| 场景 | 实际边界 |
| --- | --- |
| 普通知识问答、跨章插问 | 共用 CourseSearch 的 LightRAG / CoverageNavigator 路径 |
| 已绑定精确教材目标 | Q2 read_target 精确读取；跨章插问移除当前单节裁剪 |
| PDF 选区 | 直接解析所选原文与裁图 |
| 来源发布 | 继续经过 Q2 的来源身份、原文和引用核验 |

这是按入口和目标选择，不能描述为每次把旧检索与 LightRAG 两套结果混合。LightRAG 故障或不完整不能默认为旧后端成功。以上是运行配置和代码边界核对，本次没有重新调用模型，也不据此新增真实问答验收结论。

## 实际验证与证据

1. `F:/python.exe -m pytest tests/test_graph_viewer.py -q -p no:cacheprovider`：**3 passed**。覆盖邻域裁剪及端点一致、来源去重、摘要/片段分离、文件哈希失配、越界路径、未知实体/关系、参数上限、PDF 换版失效。
2. 可见 Edge 浏览器：搜索“自变量”、展开邻居、关系详情、PDF 实际响应 200、放大、空结果、回到概览及 390px 窄屏无横向溢出通过，无 `pageerror`。脚本：`.runtime/graph-viewer-8001/browser-check.js`，截图同目录 `desktop.png`、`mobile.png`。
3. 初次截图发现布局尚未结束就显示完成；改为等待 `layoutstop` 后，用最终静态文件完整重跑浏览器脚本通过。
4. 部署 Python 和项目 `.venv` 未安装 pytest，原测试命令退出；未安装或修改依赖，改用已有 F 盘 Python 完成测试。
5. 最终 `final-check.json`：8000 `/health=ok`，原 PID 43028 继续监听；8001 PID 68156；图谱核心文件哈希不变。没有重建索引、写入学习库或改变 staging/ready。

本功能文件保留在主工作区新增文件中，未做 Git 提交或推送，以免介入主线程的并发提交。核对期间主分支 HEAD 从 `afd6226` 更新到 `0a5790c`；没有复制或覆盖其他窗口的修改。

## 限制

- 图谱质量沿用现有候选，存在技术实体 ID 和待核对描述；本次展示真实数据，没有重命名、删节点或修改冻结图谱。
- 检索片段每条最多 5,000 字，详情最多展示 8 个片段；不是全量来源审计器。
- 本机只读工具，没有实现用户登录、远程部署、图谱编辑或知识库重建。
- 未重新验收模型问答或全部图谱关系的教材正确性；已有 LightRAG 验收结论不因可视化页面上线而改变。
