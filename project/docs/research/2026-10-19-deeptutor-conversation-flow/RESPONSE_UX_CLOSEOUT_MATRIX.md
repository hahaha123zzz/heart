# 回答体验 UX0—UX5 收尾验收矩阵

最新增量（2026-10-22）：99aadf2官方DeepSeek查询迁移已真实接通。native取原文、原跨章双方原文进模型及最终双侧引用、6个带原文链接的关联候选消费、同一次Q5计划→确认讲解→成功跨章→返回原目标→下一部分→刷新均通过；插问完整Q5状态不变、未标掌握。见[迁移实证](DEEPSEEK_QUERY_MIGRATION.md)。**此前网关配置绑定阻塞已解除**，不再列为当前阻塞。缺一方真实partial、native取消/超时实际退出与晚到门禁、独立部署仍未完成；旧批次表格与失败作为历史证据保留，不追改原运行事实。

最新增量（2026-10-21）：用户允许标注的AI生成题。9b626d4/bbd69c4已接入默认关闭的测试输入，并通过一题的真实提示/讲解/有效引用/草稿与辅导刷新及禁正式评分，47项回归通过，见[AI测试题交付](AI_PRACTICE_TEST_HANDOFF.md)。因此“练习测试缺任何输入”已解除；原教材仍0题，其他题型/原题/正式评分未验。官方DeepSeek凭据可用，LightRAG具体阻塞为既有候选endpoint策略绑定，无native查询成功证据。下方be8daa7批次及失败保留，不追改历史事实。

2026-10-21；业务基线 `be8daa73b60c7e47d6954b95d85a574b191ecc72`；新增验收提交 `f0886a0`。本轮补验与运行准备，不重做流式、上标、排版或原图。

**回答体验已有功能可在已验入口隔离使用，暂不建议整体启用8000；LightRAG不可正式切换。** 8000未运行、独立环境与运行开关未就绪；不能把“代码已实现”写成“线上已生效”。完整Q5、实际练习和native查询退出仍缺实证。

## 稳定基线及证据方式

- main / HEAD be8daa7，origin/main已包含；完整祖先 `d3d6a76 → 2b79ddc → 31adf96 → 8bce4ee`、合并6a8b0f7、公共接线be8daa7均核验，宿主e3b7073保留。
- 既有4项修改（总计划、质量基线、`.env.example`、worker）、4455项删除及未跟踪教材保留；不修改其他worktree，不采用其未提交代码。本批只提交文档、指标摘要及现有浏览器夹具的A07补验。
- 从git archive导出已提交宿主至 `E:\项目\heart\.runtime\response-closeout-20261021\committed\project\integration\discrete-math-tutor`，未提交worker/config不参与测试。未跟踪教材通过junction读现有课程输入，数据库及输出独立，不重建索引。9个关键文件字节相同，app.js仅CRLF/LF不同，规范化内容相同。初次准备脚本误将换行当不一致，保留错误，修正对账方式，未改业务文件。
- f0886a0只改测试，业务代码仍be8daa7。A07提交后完整重跑通过；后续仅文档与指标提交，不改变被测业务/测试代码。历史真实模型证据单独标注，没有用多次运行拼出“最终代码完整Q5成功”。导出代码/借用已有依赖环境不代表独立部署完成。

证据根 **C**：`E:\项目\heart\.runtime\response-closeout-20261021`；历史根 **H**：`E:\项目\heart\project\integration\discrete-math-tutor\.runtime\response-experience\20261020`。可提交汇总：[RESPONSE_UX_CLOSEOUT_EVIDENCE.json](RESPONSE_UX_CLOSEOUT_EVIDENCE.json)。原始SSE、截图、失败继续保留本机原路径。

| 本轮检查（已提交代码） | 实际结果 | 证据 |
|---|---|---|
| 后端联合 | 161项，236.019秒，exit0；进程含启动248.264秒 | C/committed-backend.log；committed-checks.json含完整命令 |
| node --test tests/chat-transport.cjs | 9项，exit0 | C/transport.log |
| Playwright现有chat-lifecycle.cjs | 全部检查通过，exit0；API替身，不是模型验收 | C/browser-lifecycle.log |
| Playwright现有response-format.cjs | 8类增量/重放/375px样本通过，exit0；排版替身 | C/format.json；browser-format.log |
| A07延迟关闭浏览器断言 | f0886a0提交后完整生命周期重跑exit0；真实本机HTTP响应保持未结束，正文可见后才释放done，1次POST；不调用模型 | C/browser-delayed-close-final.log；delayed-close.json |
| 备份与代码完整性 | 2份隔离WAL库备份/完整性/数据通过；启动Python片段编译通过，未启动；导出5374文件测试后哈希无变化 | C/preparation-checks.json；backup-fixture/backup/backup-manifest.json；正式库未备份/改动 |
| 实际课程练习API | TestClient、独立库、LLM_MOCK=1，逐章GET /api/practice/chapters/1…11；全部200、0题，不调用模型 | C/practice-audit.json；practice-check.log |
| 来源发布/正式环境 | course_release仍ready=false；新网关请求0，正式服务/索引未变 | C/practice-audit.json；runtime-audit.json；baseline.json |

后端命令：已有native环境Python `-B -m unittest tests.test_course_search_bridge tests.test_q3_agent_loop tests.test_q3_task_loop tests.test_q3_entrypoint tests.test_q5_learning tests.test_answer_media tests.test_answer_stream tests.test_response_citations tests.test_lightrag_coverage tests.test_lightrag_q3_adapter tests.test_lightrag_backend -q`。只读借用LightRAG窗口已有venv，禁写pycache，未安装或修改该环境。此前主venv缺可选依赖的8错误保留在旧报告；本轮另一环境通过不抹掉原失败。datetime弃用警告保留。

## UX0—UX5 分层状态

“历史通过”仅代表已有真实证据；“部分”不能代表整批完成。原清单未批量打勾，完整完成定义仍有效。

| 批次 / 实现SHA | 已实现 | 离线通过 | 真实模型通过 | 浏览器通过 | 阻塞 / 未完成及证据 |
|---|---|---|---|---|---|
| UX0 a2be387；本轮be8daa7 | 基线、隔离、事件/来源契约 | 本轮已提交宿主与祖先核验通过 | 历史5类请求已留存，含失败，非全部成功 | 历史截图保留 | 性能成本不等于整体改善；C/baseline.json、H/ux3-five、RESPONSE_UX_EXECUTION.md |
| UX1 064376a、e3b7073/be8daa7 | 上标、隐藏底部列表、按需原文、失效/历史 | 本轮引用/历史/传输通过 | 历史普通/PDF/原图引用通过 | 历史图5-2真实上标/410/刷新，本轮生命周期替身通过 | 实际练习缺输入；H/lr-joint-media/media-live.json、H/lr-joint-pdf、C/browser-lifecycle.log |
| UX2 78fb20f、e3b7073 | 任务预算、增量格式、受控媒体、文字降级 | 本轮8类格式通过，旧预算/质检证据保留 | 历史概念/比较/图表；旧313/339字草稿当前门禁回放通过，非新检索 | 本轮格式/窄屏/重放通过 | 完整长期规划、复杂原表无完整真实样本；C/format.json、H/ux4-latest-gate/report.json |
| UX3 b7c00f9、e3b7073/be8daa7 | 增量、探索/收尾、暂停恢复、保存/取消/收据 | 本轮Loop/Task/entrypoint/transport通过 | 历史普通/PDF、ask_user、Q2生成中取消/断线通过；强制收尾特殊分支仅离线 | 历史真实页面，本轮生命周期替身通过 | native取消/超时退出、实际练习未验；H/lr-joint-q5-ask-retry、H/lr-joint-recovery-v2、C/committed-backend.log |
| UX4 e3b7073/be8daa7 | 原图身份、临时批次、像素质检、正文/历史；pending不升级 | 本轮消息/历史/媒体安全通过 | 历史图5-2生成/质检收到同图像素 | 历史真实图5-2五组通过 | 全部同号歧义/复杂原表/精确区域/无视觉的真实场景不完整；H/lr-joint-media/model-calls.jsonl、media-live.json/png |
| UX5 6a8b0f7/be8daa7，增量99aadf2 | 共用CoverageNavigator/ContextualRetrieveCourseTool、Q3/Q5接口及官方查询迁移 | 原161+9及迁移65项通过 | 原跨章/关联消费、固定Q5单次序列通过；AI练习一题通过 | 同次Q5刷新及AI练习页面通过 | 真实partial/native退出、独立部署、全部题型仍未验；不再因网关凭据阻塞；见最新迁移/AI题报告 |

UX2.4未引入第二套Streamdown：现有引擎通过标准增量样本，不触发替换。UX5.5仍未完成，启动准备不算运行切换。未新增业务依赖、数据库表或第二套路径/循环。

### A01—A18 对照（业务SHA沿用上述批次）

| 案例 | 当前状态与证据 |
|---|---|
| A01 多来源概念 | 历史真实模型/页面通过；H/lr-joint-plain及lr-joint-media，代码e3b7073/be8daa7 |
| A02 重复编号/跨消息 | 离线及浏览器替身通过，C/committed-backend.log、browser-lifecycle.log；实际练习跨消息未验 |
| A03 旧历史/失效/未知编号 | 离线/替身、历史真实410通过，C/committed-backend.log、H/lr-joint-media/media-live.json |
| A04 格式/数字误转 | 本轮浏览器8类格式通过，C/format.json；代码78fb20f/e3b7073 |
| A05 半截公式/围栏/表格 | 本轮逐字符增量及重放通过，C/format.json；代码78fb20f |
| A06 详细规划 | 预算/标准长内容离线通过；真实长期详细规划未完整验收，不以结构化第一章计划代替 |
| A07 流结束前正文 | 历史真实Q3提前出现见H/ux4-q3-guard；本轮专用延迟关闭HTTP流替身浏览器断言通过，f0886a0、C/browser-delayed-close-final.log与delayed-close.json；替身不冒充真实SDK调用 |
| A08 多工具/分片 | 本轮离线通过，C/committed-backend.log；代码b7c00f9 |
| A09 拒绝/修订/重映射 | 本轮离线/生命周期替身通过，历史模型质检修订保留，C/browser-lifecycle.log、H/ux4-media-retry；代码b7c00f9/e3b7073 |
| A10 断线/重复 | 本轮transport/替身及历史真实模型通过，C/transport.log、H/lr-joint-recovery-v2；非运行中自动续流 |
| A11 取消/删除/旧revision | 本轮离线/替身、历史Q2生成中取消通过；native底层退出仍凭据阻塞 |
| A12 ask_user | 历史同任务真实恢复通过，H/lr-joint-q5-ask-retry；本轮离线修复通过，be8daa7 |
| A13 图号/表号 | 历史图5-2真实通过；完整原表/同号歧义未验，H/lr-joint-media；代码e3b7073/be8daa7 |
| A14 实际像素 | 历史真实生成/质检同图SHA通过，H/lr-joint-media/model-calls.jsonl；不是本轮重发图片 |
| A15 缺图/歧义/无视觉 | 部分离线通过，C/committed-backend.log；全部真实降级场景未验 |
| A16 非法URL/失效/装饰 | 离线/替身及历史实际410/pending通过，C/browser-lifecycle.log、H/lr-joint-media；全部装饰资产人工审核不在本轮完成 |
| A17 四入口与接续 | 普通/PDF有历史实证，99aadf2固定Q5成功跨章整条与刷新通过，标注AI题的一题辅导通过；全题型/原题/所有场景未齐，不勾整项 |
| A18 性能成本 | 已记录首字/总时长/SDK调用/tokens及失败；未受控重复冷热测试、无金额，不声称整体改善 |

## 剩余优先项

| 项目 | 已提交实现 / 离线 | 本轮真实状态与缺口 |
|---|---|---|
| “第一章的实验程序和第二章的自变量控制有哪些联系？” | 共用search、按对象保留原文/检查最终双侧引用，通过 | **99aadf2真实通过**。官方LightRAG双方相关原文进模型、最终双侧引用，2次检索0补查，见迁移实证 |
| 缺一方 | 有界补查、partial、事实/引用门禁，通过 | **待完成真实补验**。官方查询已可用，不再是凭据阻塞；该案例实际补查次数仍null |
| 图谱关联 | 有界候选、原文链接、evidence_eligible=false，通过 | **本题真实消费通过**。6个带原文链接的候选进正文模型请求；不代表全图关系正确或可当考点/先修 |
| Q5计划→确认→讲解→成功跨章→返回→下一部分→刷新 | 插问不写掌握/推进、原目标保留 | **99aadf2固定单次序列通过**，新隔离学生/数据库，插问完整状态不变、返回目标相同、下一目标不标掌握；旧失败仍保留 |
| 实际练习 | 现有入口契约保留，11章原教材目录仍0 | **生成测试输入已补齐并部分通过**。按用户后续授权的AI题完成一题提示/讲解/草稿/刷新，不是教材原题或正式评分验收，见最新增量 |
| native查询取消/超时 | 令牌/guard/晚到拒绝离线通过；回环SDK有界故障原记录保留 | **待完成真实补验**。凭据已可用；底层实际结束时间仍null，晚到不发布/保存/推进的native实证未取得；UI停止/Q2取消不算 |

没有请求旧网关，不扫描任意凭据文件、不输出密钥，不将官方key发送旧网关。当前通过用户本机ds.env显式注入官方隔离查询进程。候选保持，未改staging/ready=false、教材、正式索引或8000。

## 历史真实指标（不拼接为本轮成功整流程）

来自原始SDK/SSE记录；费用API未返回，不估价。SDK create包含选择/正文/质检，不代表所有HTTP内部重试。补查“—”表示覆盖协调器未执行或未取得数据，不能算作LightRAG零补查。每条的来源章、编号一致性、backend、原始路径和失败详见指标JSON。

| 案例 / H子目录 | 首次正文秒 / 总秒 | SDK调用 / total_tokens | backend；取原文 / 补查 | 来源/引用结果 |
|---|---|---|---|---|
| 普通 lr-joint-plain | 35.151 / 39.590 | 4 / 8053（全phase） | q2_exact；1 / — | 第1章3条，编号/刷新一致 |
| PDF解释 lr-joint-pdf | 未采集 / 30.012 | 5 / 18591 | 选区链路；覆盖协调器未执行 | 第1章，编号/刷新一致 |
| PDF换说法 同上 | 未采集 / 12.529 | 5 / 18562 | 选区链路；覆盖协调器未执行 | 第1章，编号/刷新一致 |
| Q5计划 lr-joint-q5-final | 无正文 / 6.602 | 0 / 0 | 结构化待确认 | 非模型流、非教材事实回答 |
| Q5讲解 同上 | 17.166 / 28.694 | 4 / 13200 | q2_exact；1 / — | 第1章，保存 |
| Q5跨章 同上 | 11.143 / 12.689 | 2 / 5385（外层） | lightrag选择边界政策失败，未执行native / — | 无双侧证据，拒绝未保存；完整Q5状态前后相同 |
| Q5返回 同上 | 4.845 / 15.424 | 4 / 13883 | q2_exact；1 / — | 原目标，保存 |
| Q5下一部分 同上 | 17.225 / 32.990 | 5 / 16474 | q2_exact；1 / — | 下一目标，不标掌握 |
| ask_user暂停 lr-joint-q5-ask-retry | 无正文 / 7.017 | 1 / 4097 | 暂停，未取原文 | 同任务问题卡 |
| ask_user恢复 同上 | 4.897 / 39.071 | 5 / 15736 | q2_exact；1 / — | 保存/刷新一致；另一次隔离DB备份运行 |
| 图5-2 lr-joint-media | 32.113 / 48.240 | 4 / 13758 | q2_exact；1 / — | 第5章2条，同图像素生成/质检，pending，刷新一致 |

历史取消/断线 `lr-joint-recovery-v2` 为32.429/32.619秒，每案1次生成POST；取消助教历史0条无复活；断线只读等待原收据后历史2条、刷新一致。不是native线程退出计时。旧401、Q5指针/无原文/暂停修复、提前停服断线fixture等失败保留在joint报告/原phase。

没有受控冷热重复统计，不声明整体加速、节省费用或完整教学循环通过。

## 启用结论

8000只读socket、健康检查、提升权限TCP/进程查询确认未运行，实际目录/SHA/backend为null。主.env磁盘未显式启用Q3/Q5，主venv缺llama_index/lightrag。详见 [RESPONSE_UX_ENABLEMENT_RUNBOOK.md](RESPONSE_UX_ENABLEMENT_RUNBOOK.md)。

**回答体验**：成功子入口可继续隔离使用；不建议本轮整体启用8000。先准备独立依赖、固定运行来源，补验目标配置的一般检索，明确Q5/练习限制并备份，再提出具体启用动作。这不依赖LightRAG切换。

**LightRAG**：官方查询及本题双侧原文/关联消费、固定完整Q5序列已通过；仍不可据此正式切换。真实partial、native退出/晚到门禁、独立部署与候选侧车可迁移性仍待验。保留全书候选，不重建、不改ready；长期路径/全章概述/Q5正式评分仍按原分工。
