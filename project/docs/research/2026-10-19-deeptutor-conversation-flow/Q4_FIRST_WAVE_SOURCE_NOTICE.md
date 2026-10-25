# 首批工具的上游来源与许可记录

上游：HKUDS/DeepTutor，固定 `6cf793bd868ba5ecbe64722936d4be8fab5a01df`，Apache-2.0。

本机 `D:/deeptutor` HEAD已核对为该SHA。对应Git对象字节与本分支 vendor 五份文件逐字节相同；各文件 SHA256 见 `Q4_FIRST_WAVE_SOURCE_AUDIT.json`。核对读取固定Git对象，未使用本机未提交的 LLM factory 修改。许可证原件保留在 `project/vendor/DeepTutor/LICENSE`。

| 上游位置 | 本轮采用内容 | 未采用内容 |
|---|---|---|
| deeptutor/capabilities/reading/tools.py：MaterialOutlineTool、ReadMaterialTool、ReaderGotoTool | 先查真实目录、按locator有界精读、合法定位/quote与回执区分的契约 | ReadingStore、用户材料容器、上游异步执行/页面已到达文案 |
| deeptutor/tools/builtin/__init__.py：ReadSourceTool | 按本轮source_id读取、未知ID失败、按需补读思路 | 将任意source_index字符串当可发布原文 |
| 同文件：ReadMemoryTool | 按需读取已记录偏好，缺失不推断 | 上游L3 Markdown存储/用户ContextVars |
| 同文件：KbFilesTool；deeptutor/knowledge/manifest.py | 盘点与检索分离、名称筛选、total/omitted/limit口径 | 知识库路径/管理文件枚举与账号目录 |
| deeptutor/agents/_shared/tool_composition.py | 资源存在才给可用工具的策略 | 平台provider、MCP、exec及与本项目无关的全量工具 |

本批新实现是**契约与思路借鉴**，没有摘抄上述类/函数、提示或导入上游运行容器；新增同步run调用本项目现有业务服务，不为了保留上游async execute另起事件循环。现有本项目Q3/Q4底座本身的改编标注与Apache-2.0记录保持不变。

因此本轮没有需要迁入的新增上游代码文件，也没有额外第三方依赖或新许可证文件。哈希证明调研对象，不把“已核对源文件”写成“复制了源码”。
