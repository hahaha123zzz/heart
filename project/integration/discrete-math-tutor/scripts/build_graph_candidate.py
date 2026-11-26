"""用真教材生成 graph_viewer 需要的只读候选数据（不依赖 LightRAG 与模型）。

产物目录：knowledge/graph/psychology-candidate/
  index_files.json                      # index/ 下文件的 sha256 清单
  index/psychology/graph_chunk_entity_relation.graphml
  index/psychology/kv_store_text_chunks.json
  input/pdf_manifest.json               # version = 对应 PDF 的 sha256
  input/chapters/chapter_XX/chapter_XX.generated.pdf
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from xml.sax.saxutils import escape

BASE = Path(__file__).resolve().parents[1]
COURSE = BASE / "knowledge/courses/experimental-psychology-3"
OUT = BASE / "knowledge/graph/psychology-candidate"

# 领域术语表（人工整理，覆盖教材 11 章的核心概念）
LEXICON = """
实验心理学 心理学 心理学史 科学方法 观察法 实验法 相关法 个案法 心理物理学
自变量 因变量 控制变量 额外变量 中间变量 无关变量 操作定义 变量 水平 因素
实验组 对照组 控制组 随机化 匹配 被试 主试 样本 总体 随机抽样
内部效度 外部效度 信度 效度 生态效度 构思效度
实验设计 被试间设计 被试内设计 混合设计 单被试设计 准实验设计 相关设计 真实验设计
随机区组设计 拉丁方设计 完全随机设计 多因素设计 因子设计 交互作用 主效应 简单效应
平衡 抵消 顺序效应 练习效应 疲劳效应 迁移效应 霍桑效应 安慰剂效应 期望效应 要求特征
天花板效应 地板效应 回归效应 选择偏差 损耗 成熟 历史因素 测量
反应时 简单反应时 选择反应时 辨别反应时 减法反应时 加法反应时 减法法则 加法法则
唐德斯 斯腾伯格 加因素法 速度-准确性权衡 刺激-反应相容性
信号检测论 信号 噪音 击中 虚报 漏报 正确否定 感受性 判断标准 辨别力 似然比 ROC曲线
心理物理学方法 最小变化法 恒定刺激法 平均差误法 极限法 误差 常误 时间误差 空间误差 习惯误差
韦伯定律 费希纳定律 对数定律 幂定律 史蒂文斯 心理量表 顺序量表 等距量表 比例量表 差别阈限 绝对阈限
注意 选择性注意 分配性注意 持续性注意 过滤器模型 衰减模型 后期选择模型 多阶段模型 资源有限模型
双耳分听 追随 负启动 返回抑制 线索 有效线索 无效线索 空间线索范式 注意瞬脱 整体优先效应
记忆 感觉记忆 短时记忆 长时记忆 工作记忆 情景记忆 语义记忆 程序性记忆 内隐记忆 外显记忆
遗忘 保持 编码 提取 复述 组块 系列位置效应 首因效应 近因效应 前摄抑制 倒摄抑制
启动效应 词干补笔 内隐学习 加工水平 提取练习 再认 回忆 自由回忆 线索回忆
阅读 眼动 注视 眼跳 回视 知觉广度 阅读知觉广度 词汇识别 语义加工 句子加工 篇章加工
移动窗口技术 消失文本范式 边界范式 眼动仪 视觉度 中央凹
冯特 艾宾浩斯 韦伯 费希纳 唐德斯 斯珀林 布罗德本特 特雷斯曼 波斯纳 斯腾伯格 史蒂文斯 吉布森
实验程序 实验情境 实验控制 实验误差 随机误差 系统误差 恒定误差 指导语 实验者效应 单盲 双盲
""".split()


def sha256(path: Path) -> str:
    return hashlib.file_digest(path.open("rb"), "sha256").hexdigest()


STOP = set("""这个 那个 我们 他们 它们 可以 因此 如果 因为 所以 但是 而且 或者 以及 进行 具有 通过
这时 此时 其中 这些 那些 一个 一种 一样 什么 怎么 怎样 就是 不是 主要 重要 一般 通常 已经 可能
研究 实验 问题 情况 结果 过程 方法 方面 内容 部分 时候 时间 条件 形式 关系 作用 意义 特点 后者 前者 试变量 主试者 被试者 人们 二者 三者""".split())

BAD_HEAD = set("的了是在和与或等把将对中为以之其该此这那每各某如有由从到把被让使就也都又还才则均更很最太")
# 泛化词：单独出现时没有概念价值，避免图谱被“设计/水平/出现”这类词占满
GENERIC = set("""设计 水平 因素 反应 出现 测量 保持 变化 结果 过程 影响 分析 研究 实验 方法 条件 时间
空间 数量 目标 任务 材料 仪器 数据 统计 检验 比较 判断 选择 操作 控制 记录 观察 报告 描述 解释 预测
理论 模型 情况 问题 内容 部分 方面 关系 作用 意义 特点 形式 阶段 状态 差异 错误 效应 变量 概念 定义
标准 程度 范围 方式 途径 系统 结构 功能 能力 效果 原因 机制 假设 证据 结论 现象 事件 对象 主体 因素""".split())
SUFFIXES = [("变量", "变量"), ("设计", "设计"), ("效应", "效应"), ("错觉", "效应"), ("现象", "效应"),
            ("理论", "理论"), ("模型", "理论"), ("学说", "理论"), ("定律", "定律"), ("法则", "定律"),
            ("法", "方法"), ("范式", "方法"), ("技术", "方法"), ("仪", "方法")]


def etype(term: str) -> str:
    for tail, kind in SUFFIXES:
        if term.endswith(tail) and len(term) > len(tail):
            return kind
    return "概念"


def clean_term(raw: str) -> str | None:
    raw = raw.strip("　 　\t·，。、；：（）()“”‘’\"'")
    raw = re.split(r"[的了是在和与或等把将对中为以之其被就也都又还才则，。、；：]", raw)[-1]
    raw = raw.strip()
    if not (2 <= len(raw) <= 10):
        return None
    if any(ch in raw for ch in "0123456789０１２３４５６７８９％%") or raw[0] in BAD_HEAD or raw in STOP:
        return None
    if raw in GENERIC or raw[-1] in BAD_HEAD or raw.startswith(("试", "者", "同")):
        return None
    if not re.fullmatch(r"[\u4e00-\u9fa5A-Za-z·]+", raw):
        return None
    return raw


def load_chapters():
    manifest = json.loads((COURSE / "manifest.json").read_text("utf-8"))
    out = []
    for chapter in manifest["chapters"]:
        n = int(chapter["id"])
        doc = json.loads((COURSE / f"chapters/chapter_{n:02d}/document.json").read_text("utf-8"))
        blocks = [b for b in doc["blocks"] if b.get("kind") == "text" and len(b.get("text", "")) >= 8]
        out.append({"n": n, "title": chapter["title"], "blocks": blocks})
    return out


def build():
    chapters = load_chapters()
    full_text = "\n".join(b["text"] for c in chapters for b in c["blocks"])

    # ---------- 1. 语料块 ----------
    chunks, chunk_of = {}, []
    for c in chapters:
        ids = []
        for b in c["blocks"]:
            cid = f"chunk-{c['n']:02d}-{b['block_index']:04d}"
            chunks[cid] = {"content": b["text"], "file_path": f"chapter_{c['n']:02d}.generated.pdf"}
            ids.append(cid)
        chunk_of.append(ids)

    # ---------- 2. 候选术语 ----------
    freq = Counter(re.findall(r"[\u4e00-\u9fa5]{2,10}", full_text))
    terms = {}
    for t in LEXICON:
        if full_text.count(t) >= 2:
            terms[t] = full_text.count(t)
    for m in re.finditer(r"([\u4e00-\u9fa5A-Za-z·]{2,14})(?:是指|指的是|被称为|称为|叫做|叫作|定义为)", full_text):
        t = clean_term(m.group(1))
        if t and t not in STOP and full_text.count(t) >= 4:
            terms.setdefault(t, full_text.count(t))
    # 去掉被更长术语完全包含的短词噪声（同频才算冗余）
    for t in list(terms):
        if t in LEXICON:
            continue
        if t in GENERIC:
            terms.pop(t, None)
            continue
        if any(o != t and t in o and terms[o] >= terms[t] for o in terms):
            terms.pop(t, None)

    # ---------- 3. 每个术语的定义句与来源 ----------
    definition, sources, home = {}, {}, {}
    for c, ids in zip(chapters, chunk_of):
        for b, cid in zip(c["blocks"], ids):
            text = b["text"]
            for t in terms:
                if t not in text:
                    continue
                sources.setdefault(t, []).append(cid)
                home[t] = home.get(t, Counter())
                home[t][(c["n"], b.get("section", ""))] += 1
                if t not in definition:
                    for sent in re.split(r"(?<=[。；！？])", text):
                        if t in sent and re.search(r"是指|指的是|称为|叫做|定义为|即", sent):
                            definition[t] = sent.strip()[:260]
                            break
    for t in terms:
        definition.setdefault(t, next((b["text"].strip()[:220] for c in chapters for b in c["blocks"] if t in b["text"]), t))

    # ---------- 4. 节点 ----------
    nodes = {}
    for c in chapters:
        ch_id = f"第{c['n']}章·{c['title']}"
        nodes[ch_id] = {"type": "章", "desc": f"教材第 {c['n']} 章：{c['title']}。本章共 {len(c['blocks'])} 个正文段落。",
                        "src": chunk_of[c["n"] - 1][:6], "files": [f"chapter_{c['n']:02d}.generated.pdf"]}
        seen = []
        for b in c["blocks"]:
            sec = b.get("section") or "导言"
            if sec not in seen:
                seen.append(sec)
                sid = f"第{c['n']}章·{sec}"
                nodes[sid] = {"type": "小节", "desc": f"{c['title']} · {sec}",
                              "src": [f"chunk-{c['n']:02d}-{x['block_index']:04d}" for x in c["blocks"] if x.get("section") == sec][:5],
                              "files": [f"chapter_{c['n']:02d}.generated.pdf"]}
    for t, n in terms.items():
        nodes[t] = {"type": etype(t), "desc": definition[t],
                    "src": sources.get(t, [])[:8],
                    "files": sorted({chunks[i]["file_path"] for i in sources.get(t, [])[:8]}) or ["chapter_01.generated.pdf"]}

    # ---------- 5. 边 ----------
    edges = {}
    def add(a, b, w, key, desc, src):
        if a == b or a not in nodes or b not in nodes:
            return
        k = (a, b) if a < b else (b, a)
        if k in edges:
            edges[k]["w"] += w
            edges[k]["src"] = list(dict.fromkeys(edges[k]["src"] + src))[:8]
            return
        edges[k] = {"a": a, "b": b, "w": w, "key": key, "desc": desc, "src": list(dict.fromkeys(src))[:8]}

    for c, ids in zip(chapters, chunk_of):
        ch_id = f"第{c['n']}章·{c['title']}"
        for b, cid in zip(c["blocks"], ids):
            sec = f"第{c['n']}章·{b.get('section') or '导言'}"
            add(ch_id, sec, 1, "章节归属", f"「{sec.split('·',1)[1]}」属于本章。", [cid])
    # 术语共现（同块内），并按“归属小节”建立章节路径
    for t, c in terms.items():
        n_, sec = home[t].most_common(1)[0][0]
        add(f"第{n_}章·{sec}", t, min(3, c), "概念出现", f"「{t}」在「{sec}」中高频出现 {c} 次。",
            sources.get(t, [])[:3])
    pair = Counter()
    pair_src = {}
    for c, ids in zip(chapters, chunk_of):
        for b, cid in zip(c["blocks"], ids):
            here = [t for t in terms if t in b["text"]]
            if len(here) > 14:
                here = sorted(here, key=lambda t: -terms[t])[:14]
            for i in range(len(here)):
                for j in range(i + 1, len(here)):
                    a, b2 = here[i], here[j]
                    k = (a, b2) if a < b2 else (b2, a)
                    pair[k] += 1
                    pair_src.setdefault(k, []).append(cid)
    # 每个概念只保留共现最强的 12 条，既保连通又控噪声
    best = defaultdict(list)
    for (a, b2), count in pair.items():
        best[a].append((count, b2))
        best[b2].append((count, a))
    keep_pairs = set()
    for a, items in best.items():
        for count, b2 in sorted(items, key=lambda x: (-x[0], x[1]))[:12]:
            keep_pairs.add((a, b2) if a < b2 else (b2, a))
    for (a, b2) in keep_pairs:
        add(a, b2, pair[(a, b2)], "共现",
            f"「{a}」与「{b2}」在同一段落中共现 {pair[(a, b2)]} 次。", pair_src[(a, b2)][:3])
    kept = list(edges.values())

    # ---------- 6. 落盘 ----------
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "index/psychology").mkdir(parents=True)
    (OUT / "input/chapters").mkdir(parents=True)

    manifest_entries = []
    pm = json.loads((COURSE / "pdf_manifest.json").read_text("utf-8"))
    for entry in pm:
        n = int(entry["chapter_id"])
        src = COURSE / f"chapters/chapter_{n:02d}/chapter_{n:02d}.generated.pdf"
        dst_dir = OUT / f"input/chapters/chapter_{n:02d}"
        dst_dir.mkdir(parents=True, exist_ok=True)
        dst = dst_dir / f"chapter_{n:02d}.generated.pdf"
        shutil.copy2(src, dst)
        manifest_entries.append({"document_id": entry["document_id"], "chapter_id": n,
                                 "title": entry["title"], "page_count": entry["page_count"],
                                 "version": sha256(dst), "source": f"chapters/chapter_{n:02d}/{dst.name}"})
    (OUT / "input/pdf_manifest.json").write_text(json.dumps(manifest_entries, ensure_ascii=False, indent=1), "utf-8")

    (OUT / "index/psychology/kv_store_text_chunks.json").write_text(
        json.dumps(chunks, ensure_ascii=False), "utf-8")

    lines = ['<?xml version="1.0" encoding="utf-8"?>',
             '<graphml xmlns="http://graphml.graphdrawing.org/xmlns">',
             '  <key id="d0" for="node" attr.name="entity_id" attr.type="string"/>',
             '  <key id="d1" for="node" attr.name="entity_type" attr.type="string"/>',
             '  <key id="d2" for="node" attr.name="description" attr.type="string"/>',
             '  <key id="d3" for="node" attr.name="source_id" attr.type="string"/>',
             '  <key id="d4" for="node" attr.name="file_path" attr.type="string"/>',
             '  <key id="d5" for="edge" attr.name="weight" attr.type="double"/>',
             '  <key id="d6" for="edge" attr.name="description" attr.type="string"/>',
             '  <key id="d7" for="edge" attr.name="keywords" attr.type="string"/>',
             '  <key id="d8" for="edge" attr.name="source_id" attr.type="string"/>',
             '  <key id="d9" for="edge" attr.name="file_path" attr.type="string"/>',
             '  <graph edgedefault="undirected">']
    for name, node in nodes.items():
        lines.append(f'    <node id="{escape(name)}">')
        for key, value in (("d0", name), ("d1", node["type"]), ("d2", node["desc"]),
                           ("d3", "<SEP>".join(node["src"])), ("d4", "<SEP>".join(node["files"]))):
            lines.append(f'      <data key="{key}">{escape(value)}</data>')
        lines.append('    </node>')
    for e in kept:
        lines.append(f'    <edge source="{escape(e["a"])}" target="{escape(e["b"])}">')
        for key, value in (("d5", str(float(e["w"]))), ("d6", e["desc"]), ("d7", e["key"]),
                           ("d8", "<SEP>".join(e["src"])), ("d9", e["src"] and chunks[e["src"][0]]["file_path"] or "")):
            lines.append(f'      <data key="{key}">{escape(value)}</data>')
        lines.append('    </edge>')
    lines += ['  </graph>', '</graphml>', '']
    graph_file = OUT / "index/psychology/graph_chunk_entity_relation.graphml"
    graph_file.write_text("\n".join(lines), "utf-8")

    index_files = {p.relative_to(OUT / "index").as_posix(): sha256(p)
                   for p in sorted((OUT / "index").rglob("*")) if p.is_file()}
    (OUT / "index_files.json").write_text(json.dumps(index_files, ensure_ascii=False, indent=1), "utf-8")
    print(f"nodes={len(nodes)} edges={len(kept)} chunks={len(chunks)} terms={len(terms)}")
    print("chapters/sections:", sum(1 for n in nodes.values() if n["type"] == "章"),
          sum(1 for n in nodes.values() if n["type"] == "小节"))


if __name__ == "__main__":
    build()
