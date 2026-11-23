"""按知识点生成候选题（AI 生成，必须带原文引用；不自动导入）。

产物：knowledge/courses/experimental-psychology-3/practice_candidates.json
每条 status=candidate、origin=ai_generated；evidence 必须是该节原文子串，否则丢弃。
"""
from __future__ import annotations

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
COURSE = ROOT / "knowledge" / "courses" / "experimental-psychology-3"
OUT = COURSE / "practice_candidates.json"
MAX_CHARS = 4000
PER_KC = 2

SYSTEM = (
    "你是《实验心理学》出题助手。只能依据用户给出的教材原文出题，"
    "禁止使用原文之外的知识。只输出 JSON。"
)
PROMPT = """根据下面的教材原文，为知识点「{name}」出 {count} 道练习题。

要求：
1. 题型只能是 single_choice（4 个选项）或 true_false（判断题）。
2. 答案必须能从原文直接判定，不要依赖外部知识。
3. evidence 字段必须逐字抄写原文中的一句话（可截取，但必须是原文连续片段）。
4. 如果原文不足以出题，返回 {{"questions": []}}。

原文：
{text}

只输出 JSON：{{"questions":[{{"type":"single_choice|true_false","question":"...","options":{{"A":"...","B":"...","C":"...","D":"..."}},"answer":"A|B|C|D|true|false","explanation":"...","evidence":"..."}}]}}"""


def normalize(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def load_sections() -> dict[tuple[int, int], str]:
    registry = json.loads((COURSE / "kc_registry_full.json").read_text(encoding="utf-8"))
    wanted = {(item["chapter_id"], item["section_id"]) for item in registry["knowledge_components"]}
    texts: dict[tuple[int, int], str] = {}
    for chapter_id, _ in sorted(wanted):
        path = COURSE / "chapters" / f"chapter_{chapter_id:02d}" / "document.json"
        if not path.is_file():
            continue
        document = json.loads(path.read_text(encoding="utf-8"))
        for block in document.get("blocks") or []:
            key = (chapter_id, block.get("section_id"))
            if key not in wanted:
                continue
            piece = str(block.get("text") or "").strip()
            if piece:
                texts[key] = (texts.get(key, "") + "\n" + piece)[:MAX_CHARS]
    return texts


def call_llm(payload: dict) -> dict:
    base = os.environ["OPENAI_BASE_URL"].rstrip("/")
    key = os.environ.get("DEEPSEEK_API_KEY") or os.environ["OPENAI_API_KEY"]
    response = requests.post(
        f"{base}/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"model": os.environ.get("OPENAI_MODEL", "deepseek-chat"),
              "messages": payload, "temperature": 0.2, "max_tokens": 1200},
        timeout=120)
    response.raise_for_status()
    return response.json()


def strip_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return {"questions": []}
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return {"questions": []}


def one(component: dict, text: str) -> list[dict]:
    prompt = PROMPT.format(name=component["name"], count=PER_KC, text=text)
    data = call_llm([{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": prompt}])
    content = data["choices"][0]["message"]["content"]
    parsed = strip_json(content)
    source = normalize(text)
    kept = []
    for item in parsed.get("questions") or []:
        evidence = str(item.get("evidence") or "")
        if not evidence or normalize(evidence) not in source:
            continue
        kept.append({
            "kc_id": component["id"],
            "kc_name": component["name"],
            "type": item.get("type"),
            "question": item.get("question"),
            "options": item.get("options") or {},
            "answer": item.get("answer"),
            "explanation": item.get("explanation") or "",
            "evidence": evidence,
            "status": "candidate",
            "origin": "ai_generated",
        })
    return kept


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    registry = json.loads((COURSE / "kc_registry_full.json").read_text(encoding="utf-8"))
    components = registry["knowledge_components"]
    existing: list[dict] = []
    if "--only-missing" in os.sys.argv and OUT.is_file():
        existing = json.loads(OUT.read_text(encoding="utf-8")).get("questions") or []
        covered = {item["kc_id"] for item in existing}
        components = [c for c in components if c["id"] not in covered]
        existing = [item for item in existing if item["kc_id"] in covered]
        print(f"missing components: {len(components)}")
    sections = load_sections()
    results: list[dict] = []
    skipped = 0
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = []
        for component in components:
            text = sections.get((component["chapter_id"], component["section_id"]), "")
            if len(text) < 200:
                skipped += 1
                continue
            futures.append((component, pool.submit(one, component, text)))
        for index, (component, future) in enumerate(futures, 1):
            try:
                kept = future.result()
            except Exception as exc:  # noqa: BLE001
                print(f"[{index}] {component['id']} ERROR {type(exc).__name__}: {exc}")
                continue
            results.extend(kept)
            print(f"[{index}/{len(futures)}] {component['id']} kept={len(kept)}")
    payload = {
        "schema": "practice-candidates-v1",
        "course_id": registry["course_id"],
        "note": "AI 生成，status=candidate；evidence 已校验为原文子串；导入前需人工审阅。",
        "generated_from": "kc_registry_full.json",
        "questions": existing + results,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"file={OUT} questions={len(results)} skipped_sections={skipped}")


if __name__ == "__main__":
    main()
