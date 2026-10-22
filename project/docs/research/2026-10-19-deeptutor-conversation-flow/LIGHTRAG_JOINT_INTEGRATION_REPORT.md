# LightRAG 公共接线与隔离联合验收（2026-10-21）

2026-10-22更新：99aadf2官方查询迁移解除旧网关阻塞，421f871修复新任务取消身份；禁SDK关键词缓存后，原跨章、partial、关联候选消费、native取消/注入截止超时/晚到门禁和修复后单次完整Q5均有真实证据，见[最新收尾](RESPONSE_UX_REMAINING_CLOSEOUT.md)。独立环境的一般检索/页面与备份已准备，8000未启动，LightRAG侧车部署可迁移性/全部入口/正式发布仍未完成。下面保持原2026-10-21运行事实与失败，不代表当前仍缺官方凭据。

本轮完成公共代码接线及不依赖网关的验收。**网关真实检索为凭据阻塞，不建议正式切换。** 未完成全入口 LightRAG 实证，不标记 Q2/Q3/Q5 或回答体验整阶段完成。

## 提交与工作树

- 宿主：`e3b7073`；共同基础：`d3d6a76`。
- 已核验完整祖先链：`d3d6a76 → 2b79ddc434824510a6d296d5f6201bc3858b3e81 → 31adf968cfbc9a5490905867fc18eef194524d90 → 8bce4eee62206bd25884a9be9484c0860d12e096`。不把这三个提交当作可脱离基础代码的补丁。
- `6a8b0f7` 将上述交付与宿主合并，两亲为 `e3b7073`、`8bce4ee`。本报告与后续公共接线修复同一提交交付，最终 SHA 见 Git 与窗口回复。
- 验证使用当前混合工作树；不是 detached 提交树验证，也不声称纯净检出可直接运行。既有教材删除、未跟踪教材、`.env.example`、worker、总计划和质量基线改动保留，不纳入本批提交。没有复制其他窗口未提交代码，没有修改其他 worktree。

## 实际调用点及兼容性

1. `agents/course_search.py::shared_search` 保留 Q2/Q5 resolve，在共同 search 边界使用交付的 `CoverageNavigator`。按原始完整问题拆分覆盖需求，各对象经 Q2 原文选择后合并，不再全局筛掉另一对象；同轮重复调用复用已核验覆盖结果，不重开补查预算。`trace`、`coverage_report`、`tool_context` 透传原接口。
2. Q2 精确 `read_target` 保留；Q5 UUID 目标可使用其单一、带版本的 `source_scope.source_refs` 指针读取，目标 ID/路径不改。多章插问不套用当前单节范围。原文选择沿用 document/version、真实 block/char 范围及来源链，不升级历史来源。
3. `agents/agent_loop_service.py` 注册交付的 `ContextualRetrieveCourseTool`，仍是现有 AgentLoop。工具返回有界关联候选与原文链接；图谱描述分开，不能作为独立事实、先修、重点或掌握凭据。
4. 发布门禁保留原文、事实、版本、引用、像素和保存检查。覆盖成功时还检查**最终正文引用**包含每个需求对象；明确 partial 才允许缺一方，并在最终展示和保存正文中标明缺失对象。保留 `answer_status=answered` 兼容旧页面，通过新增 `retrieval_coverage.status=partial` 表达部分回答。
5. 返回结果增加可选 `retrieval_coverage`、`retrieval_trace`、`backend_calls`、`learning_interjection`。旧调用方不必传参。`TaskContext.course_navigation`、bind_result、source_visuals、course_release 不改结构；循环快照补存 `source_scope`，旧快照缺字段默认空。
6. `TaskService` 对显式跨章插问不推进、不记录已讲解、不重新绑定课程目标。Q5 工具在该轮仅开放状态/路径读取，不开放掌握更新。回到原目标继续使用原位置。
7. 同一循环只保留一次修复机会：尚未检索原文时允许补取；只缺某对象正文引用时使用已有原文重写，不重复检索。ask_user 不是检索，不能因曾调用问题卡而跳过原文修复。
8. 单工具等待上限为每对象120秒（单对象120秒、双对象240秒，受覆盖需求上限约束）；adapter最多3次尝试。结束或取消时传播取消令牌，暂停时保留恢复令牌。**原生长查询线程及时退出仍未实测**，不把协作取消等同于强制终止。
9. 保留草稿追加/替换、探索/收尾流、核验后保存、收据与刷新。页面增加真实等待澄清状态；媒体只在助教消息中展示，修复历史来源绑定同时出现在用户消息导致的原图重复。Q5 当前路径头去重。
10. `web_api.conversation_history` 每请求批量校验历史引用，避免逐条重复全书哈希；无跨请求持久缓存，不削弱换版失效检查，不伪升级历史引用。共享入口调整独立包含在本批提交；集成调用方为 history API、TaskService 和现有 Q3/Q5，不引入第二套路径或后端。

## 凭据、候选与隔离边界

用户确认主 `.env` 没有可复用网关专用凭据。早期 `lr-joint-first` 曾以继承配置请求网关，3次401，未执行检索、未保存教材答案；该失败保留。确认后不再将官方密钥发送至 `https://cn.chatapi.app/v1`，不搜索或复制密钥，不改 `.env`。后续真实模型验收仅使用官方端点 `https://api.deepseek.com`；LightRAG 候选与其端点政策不匹配时明确失败，没有静默回退。

候选来自 LightRAG 窗口 `.runtime/lightrag-proxy-nothinking/0a6096dc43a8829d48776cbcd0c583b6dc779bd6b450614b4bd20bd1d7f0e5ce`，只读复制至本项目 `.runtime/lightrag-joint-20261021/candidate`，311300220字节。7项核心文件在原目录和副本共14项哈希核对不变，见 `integrity-after.json`。未重建、未改 ready/staging、未切换正式索引或8000服务。

测试使用8012、独立 host/course DB；退出时仅终止本轮子进程。native依赖使用 LightRAG 已有虚拟环境，`-B`/禁用 bytecode，不安装、不更改其他工作树。候选 full_docs 内的绝对侧车路径只在隔离进程读取视图映射至副本，不改签名存储文件；**此迁移方案尚未经成功原生查询验证，不代表候选可直接跨目录部署。**

## 验证证据（分别记录）

证据根目录：`E:\项目\heart\project\integration\discrete-math-tutor\.runtime`。以下不是生产服务验收；指标包括冷启动/原文核验，本轮无受控性能对比，不声称整体加速。首次正文是浏览器观测值，缺少观测的项目不补造。

### 代码与故障测试

命令：LightRAG现有虚拟环境 Python `-B -m unittest tests.test_course_search_bridge tests.test_q3_agent_loop tests.test_q3_task_loop tests.test_q3_entrypoint tests.test_q5_learning tests.test_answer_media tests.test_answer_stream tests.test_response_citations tests.test_lightrag_coverage tests.test_lightrag_q3_adapter tests.test_lightrag_backend -q`。

结果 **161项通过，90.103秒**，日志 `lightrag-joint-20261021/final-combined-tests.log`。含覆盖/补查上限、重复来源、关系边界、版本失效、发布引用门禁、暂停后修复、Q5插问不推进、history批量核验等。此前普通项目虚拟环境的组合出现8个缺少可选 native依赖错误，保留 `lr-joint-offline-v2.log`；不是代码通过，也不是同环境复验。native相关单独49项通过记录保留。

真实 OpenAI SDK 对**回环地址、固定假凭据**执行 TLS EOF/握手超时故障注入：分别3次调用/3次连接、3.672秒和3.718秒，SDK内部重试0，adapter有界重试；fallback=false。命令 `scripts/check_lightrag_transport_faults.py --output .runtime/lightrag-joint-20261021/transport-faults.json`。这不代表真实网关或 native图查询通过；没有外发真实密钥。

### 真实模型与页面

原始 SSE、模型调用记录、截图、JSON 位于 `response-experience/20261020/<phase>/`。记录模型实际工具输入与像素哈希，不记录 key/base64。汇总 `lightrag-joint-20261021/joint-evidence.json` 含当前被测源码哈希、actual_backend、检索次数、覆盖与引用一致性。

| 入口 / phase | 总秒 / 首次正文秒 | 实际结果与边界 |
|---|---|---|
| 普通单章 `lr-joint-plain` | 39.590 / 35.151 | q2_exact，1次取原文，3条有效引用；保存、刷新一致。不是 LightRAG 检索通过。 |
| PDF `lr-joint-pdf` | 解释30.012；换说法12.529 / 未采集 | 使用实际PDF选区，解释后“没听懂”连续追问；原文与引用保留，刷新一致。 |
| Q5计划 `lr-joint-q5-final` | 6.602 / 无正文 | 等待确认，非假模型流。 |
| Q5确认讲解 | 28.694 / 17.166 | q2_exact保存，1次取原文。 |
| 原跨章题 | 12.689 / 11.143 | lightrag选择/调用边界已到达；端点政策阻断，未执行 native图查询，拒绝未保存。Q5前后完整状态快照相等，不推进。不是跨章通过。 |
| 返回原目标 | 15.424 / 4.845 | q2_exact保存，1次取原文。 |
| 下一部分 | 32.990 / 17.225 | q2_exact保存，下一目标“笛卡儿的哲学思想”，未标掌握。 |
| ask_user `lr-joint-q5-ask-retry` | 暂停7.017；恢复39.071 / 4.897 | 同一任务选定“我思故我在”，一次有界原文修复后保存，刷新一致。使用上轮**隔离DB**备份继续；不是正式库。 |
| 教材图表 `lr-joint-media` | 48.240 / 32.113 | q2_exact取图5-2原文，生成/视觉质检同图像素；页面正文展示并刷新恢复。 |
| 取消 `lr-joint-recovery-v2` | 32.429 | 首段流时取消，单次生成POST，task_cancelled，助教历史0，刷新不复活。 |
| 断线 `lr-joint-recovery-v2` | 32.619 | SSE reader实际断开，页面如实显示网络失败；只读等待原收据完成，历史2条、刷新与收据相同，单次POST，无重生成。不是运行中自动续接流。 |

图表：原图 `image-05-0004`，SHA256 `d713f3bae36f099e03fefaea8533fa84c0afae74e3b8891ca164087db43e0f75`。真实流式生成与非流式视觉质检均收到该像素哈希；pending仍pending，没有变approved。先用真实Q5服务绑定教材目标 `ch5:s3:b114` 准备隔离场景，再通过实际页面提问；不把fixture绑定当作完整页面导航验收。

`tests/browser/response-media-live.cjs` 在375px真实历史页面5组通过：仅一张原图、上标打开原文且无底部引用表、返回真实第五章第三节、失效身份410、刷新零生成。截图 `lr-joint-media/media-live.png` 已人工查看。图片进入模型使用现有临时消息批次链，不写base64至正式历史；未复用生成图片替代教材图。

### 保留的失败和输入缺口

- 初轮Q5精确指针丢失、返回原目标缺原文、ask_user恢复被错误视作已检索的失败均保留；分别修复源指针、一次原文修复、按真实retrieve_course调用判断。最终ask_user重验通过，不把早期失败抹掉。
- 最终Q5整条中跨章仍拒绝；因此不是“计划→讲解→成功跨章→返回→下一部分”完整通过。旧路径头重复最后以单测修复；未重新跑整条真实Q5流程。
- 初轮断线fixture在原收据完成前停止服务，不能算通过；v2明确等待原任务收据后才比较刷新。故意断线的 WinError10054 保留，服务未崩溃。
- 实际练习目录 `GET /api/practice/chapters/1` 返回 total_parts=0，见 `lr-practice-catalog.json`。实际练习帮助缺验收输入；不造题、不以mock代替。
- 原跨章双侧相关原文实际进模型、最终双方引用、缺一方证据真实partial、图谱关联候选实际消费、成功跨章Q5闭环、原生长查询取消/超时线程退出均**未通过真实验收**。离线契约通过不能替代这些实证。

## 后续补验与正式切换建议

保持现状不正式切换。取得网关**专用**凭据后仅经本机安全配置注入隔离进程，不提交密钥；复验固定原题与缺失一方、确认双方原文输入/输出引用、actual_backend/索引身份/实际调用与补查次数，再完成Q5成功跨章闭环、独立练习及原生取消退出测量。任何fallback必须单独记账，不计LightRAG成功。

候选仍是staging/ready=false，文件存在或宿主公共接线通过不改变此含义；就绪审批、全章概述/长期路径由既有分工处理，本窗口不实现第二套学习路径或重建全书候选。
