# 任务 4 验收证据

本目录为日志及脚本审阅副本。汇总、浏览器返回、坐标与引用证据在相邻的 `2026-11-20-task4-acceptance.json`。

脚本实际从隔离树 H/.runtime/browser-check-12d290667b/check_task4.py 运行，使用 .runtime/task4-build-47b8efee 生产包、python-deps、临时 PostgreSQL 库及 Playwright skill。浏览器脚本路径经 HEART_BROWSER_SCRIPT 指定，账号凭据由环境变量传递，不在本目录保存。复制到这里的脚本用于审阅，不能把本目录当作独立应用启动。

模型使用本地 MockTransport，阅读工具实际访问隔离教材；朗读在浏览器语音合成接口处替身验证，未检查实体扬声器。图片处理和正式服务切换未执行。
