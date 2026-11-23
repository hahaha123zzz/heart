# 任务九验收（2026-11-22）

任务九八项完成。学生设置沿用成熟模型、能力验证、记忆与评估开关组件；新增账号只读信息与本人显示设置。显示设置仍写厂家原生 interface.json，H /api/heart/display 仅返回 language、response_language、code_block_wrap_long_lines，不开放设置总接口或 Embedding/项目模型配置。读取和模型元数据不缓存；不确定保存后禁用编辑并要求重新读取。

回答长度、举例、节奏和讲练顺序由“我的记忆”的示例填入，点击示例不会写入，主动确认添加才进入 H PG explicit_user 条目。关闭记忆不读取长期偏好，仍可管理；本轮明确要求优先。没有新增第二份教学偏好存储，不更改掌握。界面语言/回答语言为原生明确设置，与记忆开关独立。

已有资料契约：GET /api/auth/profile 返回 id、username、role、created_at、disabled、avatar、preset；PUT 同一路径只改本人 avatar 标记，头像上传/删除是 /api/auth/profile/avatar。原生 GET/PUT /api/auth/profile/learner-profile 支持 age、grade_level、curriculum、language、reading_level、explanation_style；本轮没有增加这些字段的表单，学生设置仅保留当前已接通入口。个人资料页原有头像能力保留。用户名、角色、启停和密码不在学生设置页编辑；重置由管理方受控处理。不开放注册、邮箱绑定/找回或 SSO。

个人 Key 使用 H PostgreSQL 密文、配置版本和本人身份；保存/更新/删除、HTTPS/Base URL 边界、并发快照和无共享 Key 兜底由 120 项模型/HTTP 回归验证。聊天、评分、工具、图片分别验证，须逐次确认费用，不明请求不自动重发；更新配置使旧验证失效。浏览器三项能力调用使用明确的本地 invoke 边界，经过真实能力校验和版本持久化，不代表本轮重新调用外部供应商。实际 DeepSeek 教材回答、评分和视觉识别证据分别见任务二、六、八，未重复收费。

固定十账号初始化经过随机独立厂家目录/PG 和新进程重跑、密码互不相同、凭据文件不改、身份不变、清理与过期 token 边界验收。实际本机 8000 另创建十个独立永久账号并授权 11 章教材，无旧聊天迁入；密码只在私密运行目录，报告与日志不包含密码。学生不能管理其他账号，账号永久和登录会话正常过期分开处理。

本轮 Python 120+1 项、组件 25 项（5 文件）、Node 1272 项、typecheck、生产 build 与双向契约检查通过。真实 Chromium 8 组通过；受测构建与当前前端运行源码逐项匹配。任务十另完成实际 8000 的十账号、教材/图谱和空状态检查。未运行全仓全部 Vitest，390px 是视口模拟；线上按用户要求暂缓。
