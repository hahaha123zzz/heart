"""从教材 manifest 生成全教材候选知识点（每节一个 KC，status=candidate）。

产物：knowledge/courses/experimental-psychology-3/kc_registry_full.json
不修改人工审阅过的 kc_registry.json（第 1 章那 4 条）。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

COURSE = Path(__file__).resolve().parents[1] / "knowledge" / "courses" / "experimental-psychology-3"
OUT = COURSE / "kc_registry_full.json"
SECTION_PREFIX = re.compile(r"^第[一二三四五六七八九十百]+节\s*")


def clean(title: str) -> str:
    return re.sub(r"\s+", " ", SECTION_PREFIX.sub("", title.replace("\u3000", " "))).strip()


def main() -> None:
    manifest = json.loads((COURSE / "manifest.json").read_text(encoding="utf-8"))
    components = []
    for chapter in manifest["chapters"]:
        chapter_title = clean(chapter["title"])
        for section in chapter.get("sections") or []:
            name = clean(section["title"])
            components.append({
                "id": f"kc-{chapter['id']}-{section['id']}",
                "name": name,
                "aliases": [alias for alias in {chapter_title, chapter_title + " " + name} if alias != name],
                "observable": "",
                "status": "candidate",
                "chapter_id": chapter["id"],
                "section_id": section["id"],
                "source_refs": [{
                    "document": f"chapters/chapter_{chapter['id']:02d}/document.json",
                    "chapter_id": chapter["id"],
                    "section_id": section["id"],
                    "block_ids": [section.get("body_index")],
                }],
            })
    payload = {
        "schema": "kc-registry-full-v1",
        "course_id": manifest["course_id"],
        "status": "candidate",
        "note": "由 manifest 的章节结构生成，每节一个候选知识点；status=candidate 表示尚未人工确认。",
        "source_manifest_sha256": manifest.get("source_sha256", {}),
        "knowledge_components": components,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    chapters = sorted({c["chapter_id"] for c in components})
    print(f"file={OUT}")
    print(f"chapters={len(chapters)} kcs={len(components)}")
    for item in components[:5]:
        print(f"  {item['id']}: {item['name']}")


if __name__ == "__main__":
    main()
