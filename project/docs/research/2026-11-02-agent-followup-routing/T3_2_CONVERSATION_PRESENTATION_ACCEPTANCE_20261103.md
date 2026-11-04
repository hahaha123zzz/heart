# T3.2 对话内容语义展示实施记录

日期：2026-11-03。范围：`frontend/chat-renderer.js`、`frontend/styles.css`、`frontend/index.html`、`tests/response-composition.cjs`。按 ponytail 原则只做最小展示层改动，不改后端协议、正文生成、引用或教学状态。

## 1. 实现

### 1.1 类型映射

`renderLearningResponse` 在原有协议、发布状态、块身份、重复块和正文一致性校验之后，使用固定映射：

| semantic_type | class | 可见标记 |
| --- | --- | --- |
| comparison | `response-comparison` | 对照 |
| procedure | `response-procedure` | 步骤 |
| recap | `response-recap` | 无（避免重复正文“总结”标题） |
| counterexample | `response-counterexample` | 边界 |
| misconception | `response-misconception` | 易混边界 |
| worked_example / analogy | `response-example` | 无（保留服务端示例说明） |
| 其他/未知 | `response-block` | 无 |

约束保留：

- 只接受 `learning-response/v1`、`status=published`、`b\d+` 块 ID、无重复块、正文拼接一致；
- `content_origin=host_snapshot` 不套用教学 class/标签，保留宿主原文与互动语义；
- 未知类型、旧消息、缺失类型、正文不一致仍回退基础正文或返回 `null`；
- 不执行模型 HTML，不按关键词猜类型，不重排引用。

### 1.2 样式

`frontend/styles.css` 增加局部语义样式：

- 比较/步骤/总结/边界/示例使用轻边框和浅背景，普通解释不套卡片；
- 长表格在块内横向滚动，不撑宽整页；
- `:focus-visible` 可见；
- 窄屏减少内边距，不隐藏正文。

`index.html` 更新 `styles.css` 与 `chat-renderer.js` 的 cache version，避免旧缓存。

## 2. 验证

### 2.1 合成回归

```text
node tests/response-composition.cjs
```

结果：通过。覆盖：

- comparison/procedure/recap/counterexample 的 class 与可见标记；
- 正文只出现一次；
- host_snapshot 不增加教学标签；
- 未知 semantic_type 不进入专用样式；
- 原协议、正文一致性、重复块、危险 HTML、旧版本回退仍通过。

### 2.2 真实数据渲染

使用 8000 真实 V02 回答（`visual-live-v02-v04.json`）的 `learning_response` 和 `reply` 在 Node 中调用真实 `chat-renderer.js`：

```json
{
  "blocks": [["comparison", "generated"]],
  "comparison": true,
  "label": "对照",
  "citation": true,
  "chars": 3300
}
```

说明：真实 comparison 块被识别，正文与引用仍在，未重复。

### 2.3 8000 页面验收

本机浏览器脚本原先缺少 `playwright` 模块；本轮在隔离目录 `.runtime/pw` 安装 `playwright@1.63.0`（不写入项目依赖），复用已安装的 Chromium，执行：

```text
$env:NODE_PATH='E:\项目\heart\.runtime\pw\node_modules'
node tests/browser/t3-2-semantic-display.cjs
```

结果：**PASS**。

覆盖：

- comparison/procedure/recap/counterexample 类型 class 与可见标记；
- 正文只出现一次，引用按钮保留；
- `host_snapshot` 不套教学 class/标签；
- 图解上一步/下一步，正文更新后 `data-step` 保持 `1`，不重置；
- partial → final 同 `renderKey` 更新，不重复正文；
- `messagesFromHistory` 读取同一 `learning_response`；
- 390px 窄屏无整页横向溢出；
- 引用按钮可聚焦。

另用真实 8000 数据验证：

- V02 `comparison/generated` 在页面渲染出 `response-comparison`、`对照`、引用按钮；
- 真实“心理学实验程序”回答含 `procedure/generated`，页面渲染出 `response-procedure`、`步骤`。

### 2.4 仍未验证

- P08 的“点击图解来源跳到教材页并高亮”未在本轮 rerun；既有 guided 浏览器脚本依赖 artifacts 和 8002 环境。
- P04 真实 recap、P05 真实 counterexample：真实请求分别未稳定产生对应块；P05 的“相关不等于因果”请求返回 `quality_rejected`，属上游证据/发布门禁，不是展示层失败。合成夹具已覆盖渲染。
- P01 简单事实仅由 API 负向用例和基础正文回退覆盖，未单独截图。
- 没有跑完整测试矩阵。

## 3. 文件

- `frontend/chat-renderer.js`：固定类型映射、class、可见标记。
- `frontend/styles.css`：局部语义样式、块内表格滚动、焦点。
- `frontend/index.html`：cache version。
- `tests/response-composition.cjs`：类型展示、host_snapshot、未知类型、正文/引用一致性回归。
- `tests/browser/t3-2-semantic-display.cjs`：8000 页面类型展示、host_snapshot、图解步骤保持、partial→final、历史、窄屏与焦点。

## 4. 边界

- 没有修改后端 `semantic_type` 或教学规划。
- 没有给 `roadmap`/`section_map` 增加第二套渲染器，仍按基础正文。
- 没有新增输入框上方预制按钮或学生参数。
- 所有改动未提交，仍在工作区。

## 5. 下一步

1. 安装/启用现有 Playwright 测试环境，在 8000 页面验收 P01–P10。
2. 检查部分发布、最终消息、刷新历史是否都使用同一 `learning_response` 路径。
3. 如页面出现正文重复或引用错位，先回退本次前端差异，保留基础正文。
