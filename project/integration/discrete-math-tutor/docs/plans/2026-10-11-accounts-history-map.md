# 正式账号与提问历史图：实现边界

本次基于 `heart-main.zip` 中的离散数学项目实施。主页面仍是原生 HTML/CSS/JS，后端仍为 FastAPI + SQLAlchemy；没有引入第二套 Agent、重写教学策略或把教材变成知识图谱。

## 身份与数据流

注册时创建 `students` 内部 ID 和一对一 `users` 记录；密码仅存 Argon2 哈希。登录签发随机不透明会话令牌，数据库只存令牌 SHA-256 摘要；浏览器只持有 HttpOnly、SameSite=Lax Cookie。HTTPS 部署启用 Secure。写请求检查同源 Origin 和会话绑定的 CSRF 令牌。前端 `/api/auth/me` 获得账号信息后才加载私有数据。

聊天、选区解释、画像、学习统计、资源浏览、章节测验、偏好、教材练习和历史图接口均使用服务端确认的 `student_id`。旧的路径参数只作归属校验；练习的旧查询/正文参数仅作兼容，若不匹配当前会话就拒绝。退出只撤销当前会话；过期会话不能读取数据，但学习记录不清理。

原 `students.account_type`、`expires_at` 及数据库中的 `test_build_state` 旧表不删除，以免破坏已有记录；运行代码不再创建、过期清理或按代码版本清理测试学生。新注册账号不认领旧 ID。旧数据必须先核实归属，再由管理员单独迁移。

## 问题历史图

API 为每个完成的聊天回合生成 UUID `turn_id`，两条原始 `conversations` 记录通过该 ID 配对。回合结束后快速保存 `question_analysis_jobs`，再由后台线程调用已有模型，判断 `ignore`、`continue`、`child`、`new_root`。节点存于 `question_nodes`，父节点表达语义引申；`question_node_messages` 精确关联原始消息 ID。失败任务保留并在启动时重试，不影响助教回答。

历史页面只读取已保存的节点，横向布局、缩放、拖动、折叠由 `frontend/history-map.js` 实现。点击节点按归属检查读取原始消息及教材图片引用。旧问答不在打开页面时批量调用模型；对已完成可信账号归属迁移的旧记录，可用 `scripts/backfill_history_map.py` 明确执行增量补建。

## 迁移与测试

SQLite 首次增量迁移自动做一致性备份；既有 MySQL 库要求管理员先备份再显式允许迁移。只新增表与 `conversations.turn_id`，不改写旧对话正文。测试使用临时 SQLite 和模拟模型，覆盖账号隔离、跨浏览器恢复、CSRF、退出/过期不删数据、原始消息关联、四种历史分类、SSE 聊天、旧库备份和原有教学/练习/PDF 选区回归。真实 DeepSeek 的语义分叉质量仍需配置密钥后人工验证。
