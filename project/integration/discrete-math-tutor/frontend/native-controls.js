"use strict";
window.TutorNativeControls = (() => {
  let catalog = null, scopeKey = null, getScope = null;
  const names = {chat:"对话",ask_questions:"提问练习",mastery_path:"掌握度学习",immersive_reading:"沉浸阅读",
    course_study:"课程学习",deep_solve:"深入解题",deep_question:"生成题目",deep_research:"深入研究",
    visualize:"可视化",math_animator:"数学动画",audio_overview:"音频概览"};
  const labels = {mode:"内容形式",depth:"研究深度",topic:"主题",num_questions:"题目数量",difficulty:"难度",
    quality:"质量",output_mode:"输出形式",style_hint:"风格要求",target_minutes:"时长（分钟）",
    max_context_chunks:"材料数量",render_mode:"图示类型",host_voice:"主持人声音",expert_voice:"专家声音",
    max_questions:"最大题数",max_workers:"并行任务数",manual_subtopics:"子主题数量",
    manual_max_iterations:"最大迭代次数",question_types:"题型"};
  const values = {notes:"学习笔记",report:"研究报告",comparison:"比较分析",learning_path:"学习路径",
    quick:"快速",standard:"标准",deep:"深入",manual:"自定义",custom:"自定义",mimic:"参考材料出题",
    video:"视频",image:"图片",low:"低",medium:"中",high:"高"};
  const container = document.createElement("details");
  container.className = "native-controls";
  const summary = document.createElement("summary"); summary.textContent = "能力与工具";
  const status = document.createElement("p"); status.setAttribute("role", "status");
  const capability = document.createElement("select"); capability.setAttribute("aria-label", "选择能力");
  const config = document.createElement("fieldset"); config.setAttribute("aria-label", "能力设置");
  const tools = document.createElement("fieldset"), resources = document.createElement("fieldset");
  const legend = document.createElement("legend"); legend.textContent = "可选工具"; tools.append(legend);
  const resourceLegend = document.createElement("legend"); resourceLegend.textContent = "本轮资源"; resources.append(resourceLegend);
  const refresh = document.createElement("button"); refresh.type = "button"; refresh.className = "secondary-button"; refresh.textContent = "刷新可用能力";
  const body = document.createElement("div"); body.className = "native-controls-body";
  body.append(capability, config, tools, resources, refresh, status);
  container.append(summary, body);
  capability.hidden = config.hidden = tools.hidden = resources.hidden = true;
  document.querySelector(".chat-composer").prepend(container);
  const checkbox = (parent, name, value, label, disabled=false) => {
    const input = document.createElement("input"); input.type="checkbox"; input.name=name; input.value=value; input.disabled=disabled;
    const node=document.createElement("label"), text=document.createElement("span");
    text.textContent=label; node.append(input, text); parent.append(node);
  };
  // 只渲染宿主认识且当前能力声明了的配置项；未知字段不由页面猜测。
  function configure() {
    config.replaceChildren();
    const item = catalog?.capabilities.find(value => value.name === capability.value);
    const properties = item?.request_schema?.properties || {};
    for (const [name, schema] of Object.entries(properties)) {
      if (!labels[name]) continue;
      const spec = schema.anyOf?.find(value => value.type !== "null") || schema;
      const label = document.createElement("label"); label.append(document.createTextNode(labels[name] + " "));
      const input = spec.enum ? document.createElement("select") : document.createElement("input");
      if (spec.enum) for (const value of spec.enum) input.add(new Option(values[value] || value, value));
      else input.type = ["integer","number"].includes(spec.type) ? "number" : "text";
      if (spec.type === "array") input.placeholder = "用逗号分隔";
      input.dataset.nativeConfig = name; input.dataset.kind = spec.type || "string";
      if (spec.minimum != null) input.min = spec.minimum;
      if (spec.maximum != null) input.max = spec.maximum;
      if (spec.maxLength != null) input.maxLength = spec.maxLength;
      const initial = item.config_defaults?.[name] ?? schema.default;
      if (initial != null) input.value = Array.isArray(initial) ? initial.join(",") : String(initial);
      if (name === "depth" && !input.value) input.value = "standard";
      label.append(input); config.append(label);
    }
    config.hidden = !config.children.length;
  }
  async function load(scope) {
    const key = JSON.stringify(scope);
    if (catalog && key === scopeKey) return;
    status.textContent = "正在读取可用能力…";
    capability.hidden = config.hidden = tools.hidden = resources.hidden = true;
    refresh.disabled = true; body.setAttribute("aria-busy", "true");
    try {
    const response = await fetch("/api/deeptutor/catalog", {method:"POST", headers:{"Content-Type":"application/json"}, body:key, signal:AbortSignal.timeout(15000)});
    if (!response.ok) throw new Error("原生能力目录暂未就绪");
    catalog = await response.json(); scopeKey = key;
    if (catalog.enabled === false) { container.hidden = true; return; }
    container.hidden = false;
    capability.replaceChildren();
    for (const item of catalog.capabilities) {
      const option = new Option(names[item.name] || item.display_name || item.name, item.name);
      option.disabled = item.availability?.available === false; capability.add(option);
    }
    capability.hidden = !capability.options.length;
    configure();
    tools.querySelectorAll("label").forEach(node => node.remove());
    for (const item of catalog.tools.filter(item => item.user_toggleable))
      checkbox(tools, "native-tool", item.name, item.name, !item.allowed_by_grant);
    resources.querySelectorAll("label").forEach(node => node.remove());
    for (const [kind, ids] of Object.entries(catalog.resources || {}))
      for (const id of ids) {
        const item = catalog.resource_options?.[kind]?.find(item => item.id === id);
        checkbox(resources, kind, id, item?.name || id, item?.available === false);
      }
    tools.hidden = !tools.querySelector("label");
    resources.hidden = !resources.querySelector("label");
    status.textContent = capability.options.length
      ? "未勾选工具时使用默认配置；未连接的服务需要先配置。"
      : "暂无可用能力，请稍后刷新。";
    } catch (error) {
      catalog = null; scopeKey = null;
      throw new Error(error.name === "TimeoutError" || error.name === "AbortError"
        ? "读取能力超时，请点击刷新重试。" : "能力目录加载失败，请点击刷新重试。");
    } finally {
      refresh.disabled = false; body.removeAttribute("aria-busy");
    }
  }
  capability.addEventListener("change", configure);
  container.addEventListener("toggle", () => {
    if (container.open && getScope) load(getScope()).catch(error => { status.textContent = error.message; });
  });
  refresh.addEventListener("click", () => {
    catalog = null;
    if (getScope) load(getScope()).catch(error => { status.textContent = error.message; });
  });
  return {
    bindScope(provider) { getScope = provider; },
    async options(value) {
      if (!catalog || scopeKey !== JSON.stringify(value)) {
        try { await load(value); } catch (error) { status.textContent = error.message; throw error; }
      }
      if (catalog.enabled === false) return {};
      const result = {capability: capability.value, config: {}};
      for (const input of config.querySelectorAll("[data-native-config]")) {
        if (input.value === "") continue;
        const name = input.dataset.nativeConfig, raw = input.value;
        result.config[name] = ["integer","number"].includes(input.dataset.kind) ? Number(raw)
          : input.dataset.kind === "array" ? raw.split(/[,，\n]/).map(value => value.trim()).filter(Boolean)
          : raw;
      }
      const selected = [...tools.querySelectorAll("input:checked")].map(input => input.value);
      if (selected.length) result.tools = selected;
      for (const kind of ["knowledge_bases","skills","mcp","memory_references"]) {
        const ids = [...resources.querySelectorAll('input[name="' + kind + '"]:checked')].map(input => input.value);
        if (ids.length) result[kind] = ids;
      }
      return result;
    }
  };
})();
