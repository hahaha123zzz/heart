# 本轮源码与专项验证记录

日期：2026-10-19。源码：D:/deeptutor，提交 6cf793bd868ba5ecbe64722936d4be8fab5a01df。

## 静态核查

- 100 个内置工具描述符名称唯一，全部解析到真实类定义；跟踪 view_figure 的重导出。
- 11 个顶层回合能力和 14 个循环扩展的实现入口均存在。
- 为 99 个相关 Python 文件建立 SHA-256、符号行号和方法范围，包含本地已有 factory.py 修改的实际内容哈希。
- 完整工具清单的每个名称与审计 JSON 做集合比较，确保没有重复或遗漏。静态存在性不代表运行成功。
- 后端源码未改动；测试关闭 bytecode/cache 写入，运行数据放宿主 .runtime 的新建隔离目录。

## 专项测试

使用宿主 `.venv-deeptutor` Python 3.13 环境，PYTHONPATH 指向用户指定的 D 盘源码。关闭自动 pytest 插件加载，仅显式启用 pytest_asyncio。

| 模块 | 主要验证范围 |
| --- | --- |
| tests/services/session/test_capability_routing.py | 明确出题请求、自动开关、普通聊天与工作区边界 |
| tests/agents/chat/test_agent_loop.py | 循环、工具/正文、预算、截断、模型失败、原生协议等 |
| tests/capabilities/test_explore_context_capability.py | 材料调查激活及预处理 |
| tests/tools/test_ask_user.py | 问题卡的结构与验证 |
| tests/app/test_turn_application_service.py | 启动、恢复、回合管理等应用服务行为 |
| tests/services/session/test_context_builder.py | 模型历史、压缩、预算与协议 |

结果：**224 passed, 1 failed, 2 warnings，耗时 127.03 秒。** 使用替身模型，不是在线模型评测或完整浏览器验收。

复现命令（PowerShell；D 盘源码只读，输出写入新的宿主运行目录）：

```powershell
$auditRun = Join-Path 'E:\项目\heart\project\integration\discrete-math-tutor\.runtime' ('deeptutor-flow-audit-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $auditRun | Out-Null
$env:DEEPTUTOR_HOME = $auditRun
$env:PYTHONPATH = 'D:\deeptutor'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
Set-Location 'D:\deeptutor'
& 'E:\项目\heart\project\integration\discrete-math-tutor\.venv-deeptutor\Scripts\python.exe' -B -m pytest tests/services/session/test_capability_routing.py tests/agents/chat/test_agent_loop.py tests/capabilities/test_explore_context_capability.py tests/tools/test_ask_user.py tests/app/test_turn_application_service.py tests/services/session/test_context_builder.py -q -p no:cacheprovider -p pytest_asyncio.plugin --basetemp (Join-Path $auditRun 'pytest')
```

## 唯一失败及诊断

失败位置：`tests/agents/chat/test_agent_loop.py:2434`，测试名：

```text
test_cold_start_stalled_provider_settles_with_bounded_retries[partial_stream]
assert sum(event.metadata.get("error_code") == "provider_transport" for event in events) >= 1
实际断言：0 >= 1
```

该测试用替身先输出 Partial answer，再永久等待，将流空闲超时压缩为 0.01 秒。此前的异常类型、retryable、调用次数、partial_response 等断言均已执行到通过，最后在消费者事件列表的断言失败。

单独重跑：1 failed，3.99 秒。

按 systematic-debugging 的先查证据原则，在隔离运行目录创建只记录 StreamBus.emit 的临时 pytest 观测插件，没有修改或替换源码行为。再次失败，记录为：

```text
AUDIT_DIAGNOSTIC emitted_provider_transport=1 collected_at_assert=1
```

该插件的计数发生在 pytest 收集失败时，此时测试 finally 已关闭总线并等待消费者。与断言当时的 0 对照，说明事件确已发出，消费列表在清理等待后补齐。源码的失败事件发出位置在 agent_loop.py:1473 附近；StreamBus.emit 使用队列分发。

诊断结论：此失败反映该用例断言与异步消费完成时机之间的问题，不能据此断言模型错误事件从未产生；也不以诊断代替修改后的绿色验收。上游测试和源码未改动，正式结果仍保留 1 failed。

## 环境与未验证范围

DEPENDENCY_SNAPSHOT.json 仅读取发行包元数据；安装了包不代表模型权重、embedding 端点、凭据、沙箱或系统依赖可用。没有在本轮安装新包。

未调用真实模型、外部工具或 MCP；未使用源项目真实配置；未运行全套上游测试、浏览器端到端测试、全教材解析/建索引或生产并发测试。
