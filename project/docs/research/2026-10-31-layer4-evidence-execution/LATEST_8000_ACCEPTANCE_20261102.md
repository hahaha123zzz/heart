# 最新工作区代码的8000验收配置

2026-11-02，按用户“全部切换最新代码、在8000检验”的明确授权执行。

## 实际部署

运行当前主工作区：`project/integration/discrete-math-tutor`。基础提交7b752ad，包含输入理解、教学策略、前端及评价脚本的未提交修改；没有替其他窗口提交、覆盖或推送代码。运行版本以`.runtime/latest-8000-20261102/manifest.json`的724份源码hash及code-snapshot.zip为准，不能仅用Git SHA代表当前服务。真实问答后核对这724份文件，变化数为0。

8000启动前无服务响应，未终止未知进程。启动器为同目录serve.py，运行PID与实际配置记录在service.json，stdout/stderr日志保留。继续使用原正式心理学数据库、现有固定教材索引、GPU embedding/reranker及真实DeepSeek配置；未重新导入教材、切换数据源或安装依赖。

## 本次明确开启

- INPUT_UNDERSTANDING_MODE=active；INPUT_UNDERSTANDING_SEMANTIC_ENABLED=1。
- SEMANTIC_LABELS_ENABLED=1；LABELS_POLICY、LABELS_STRUCTURE、LABELS_TURN均为1。
- LOCAL_AGENT_LOOP_ENABLED、ADAPTIVE_TUTORING_ENABLED、SELECTED_TEXT_AGENT_LOOP_ENABLED均为1。
- RESPONSE_COMPOSITION_ENABLED、RESPONSE_BLOCK_STREAMING_ENABLED均为1。

只修改上述配置项，其他原配置保留。第六层现有代码随应用加载，但未审核KC仍是候选；没有生成教师审核记录、强行启用尚未实现的学习闭环或为宣称完成而改变掌握度。

## 验证

相关输入理解、语义标签、统一策略、内容组合/执行及第四层桥接回归106项通过，使用独立测试库和明确本地检索测试配置，日志regression.log。该回归不代表所有入口、正式配置或六层完整教学效果验证。

正式服务页面与health均HTTP 200，mock=false，fixed_book.ready=true，embedding/reranker实际为CUDA。专用新建测试账户真实请求：“先解释自变量，再比较自变量与因变量，最后简短总结，不要出题。”约12.3秒answered，2条教材引用；实际输入解析1次模型调用，三个动作均completed；返回learning_response与三个内容块，step_advanced=false。完整请求及结果保存在smoke.json，未读取其他学生历史进行模型测试。

未在本次重新执行浏览器全场景、教师语义审核、KC审核或性能对照。分批开关已启用，但具体回合是否走分批仍取决于现有文本/证据/工具等适用条件，不强行让选区、图像或题卡沿用文本分批路径。

## 备份与回退

正式库在启动前通过SQLite backup API备份至course-before.sqlite3，integrity_check=ok；旧配置私有备份为config-before.private，原flag值在manifest.previous_flags。备份、数据库、完整运行结果和代码快照均不提交Git。

需要回退配置时，先核对service.json对应进程及启动脚本，再停止本次服务；逐项恢复previous_flags中的键（原来不存在的键用unset_key删除），不整体覆盖后来变化的.env。随后用既有启动脚本重启。普通开关回退不应还原数据库而覆盖新学习记录。
