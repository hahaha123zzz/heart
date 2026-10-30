# 8137 最近真实页面请求耗时核对

本次核对实际页面用户 demo-daec08fa-5b80-4ff1-9356-f4eed10c2bfd 的最近三条已完成请求，不使用新账户测速代替。

| 问题 | 总耗时 | 首字 | 检索 | 模型生成 | 图片选择/输入 | 发布核验 |
|---|---:|---:|---:|---:|---:|---:|
| 自变量是什么 | 51.703s | 43.734s | 38.688s | 1.734s | 0.000s / 0.000s | 3.891s |
| 因变量是什么 | 39.922s | 31.500s | 25.609s | 2.390s | 0.000s / 0.000s | 2.985s |
| 解释一下遗忘曲线 | 59.063s | 49.891s | 33.391s | 2.828s | 2.906s / 4.282s | 3.484s |

各阶段含子调用，不能把所有指标直接求和；总耗时内还有尚未细分的来源映射、上下文与结果处理。

## 已确认的代码开销

- knowledge/lightrag/retrieval.py:144 validate：逐次读取和 SHA256 校验候选索引、冻结教材和宿主教材；search 在查询前后各执行一次。三次请求前后校验合计分别 20.970s、10.031s、9.703s。
- knowledge/lightrag/retrieval.py:195 job：每次 build_rag / initialize / finalize；加载图谱与向量存储。三次 engine.build 分别 6.484s、5.953s、6.172s。
- 同文件 search 在原文映射后无条件 visual_inventory；course_input.py:48 每次创建独立 source_visuals 模块并加载全书图片，文本问题也经过此路径。这段尚无独立计时，不能将未分段耗时全部归给它。
- knowledge/figures.py:48 Figure.public -> course_release.binding -> validate(refresh=True) -> clear_cache -> snapshot：一次图片元数据读取触发全书版本重算。knowledge/answer_media.py current_media 同时用两次 figure.public 获取两个字段，重复触发。
- knowledge/grounded_citations.py EvidenceBundle.references 和 agent_loop_service._map_result 也会调用 release binding，造成发布与结果处理中的重复全书读取。

## GPU 与循环核对

- 8137 /health 的 embedding、reranker 均为 cuda，实际 providers 含 CUDAExecutionProvider。三次 GPU 重排 0.453s、0.562s、0.485s。
- 三条结果均一轮回答；没有原先的教学步骤拒绝后补工具重写，也没有 QualityChecker 第二次模型质检。publish_integrity 仍执行来源/引用核验。
- 8137 进程命令为 serve_gpu.py，cwd 为 .worktrees/integration-main-20261025 下应用目录。
- 当前内存占用 91.8%、可用约 1.28 GiB；仅为观察时状态，不证明历史请求发生换页，也不能据此断言磁盘/内存是唯一原因。

## 与先前快速测试的差异

- 同库早先成功案例总耗时 10.281s，检索 5.969s，前后校验约 1.360s，engine.build 1.157s，GPU 重排 0.297s。
- 最近页面案例沿用同一 GPU 代码路径，但全量校验及加载耗时大幅上涨；先前暖机短样本不代表真实页面长会话和稍后系统状态。
- 本次未重发用户问题、未更改业务代码、未重启服务；诊断原始记录在 real/recent-user-tasks.json。

## 下一步优先顺序

1. 将全书装载和发布身份计算从逐请求路径移到可失效的版本实例，保留版本变更与来源边界校验；不能直接永久缓存或删除验证。
2. 复用同一 worker/event loop 的 LightRAG 实例，处理实例关闭、查询取消、版本切换和并发，避免仅缓存跨 loop 对象。
3. 图片仅在需要时处理，复用一次图片元数据结果，分别计时来源映射、全书图片目录和发布快照。
4. 使用本次相同页面会话分别复验无图、有图、连续追问以及更换教材版本的失效行为。
