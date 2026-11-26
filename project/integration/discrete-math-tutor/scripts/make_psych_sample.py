"""从正式第四章资源生成样章目录（course_preview_api 契约）。"""
import hashlib, json, shutil
from pathlib import Path
import fitz

ROOT = Path(r"C:/Users/HP/WorkBuddy/2026-11-19-21-53-59/heart_extracted/"
            r"heart-codex-ta5-acceptance-20261029/project/integration/discrete-math-tutor")
COURSE = ROOT / "knowledge/courses/experimental-psychology-3"
SRC = COURSE / "chapters/chapter_04"
SAMPLE = COURSE / "sample"
SAMPLE.mkdir(parents=True, exist_ok=True)

pdf_src = SRC / "chapter_04.generated.pdf"
pdf_dst = SAMPLE / "chapter_04.generated.pdf"
shutil.copyfile(pdf_src, pdf_dst)
version = hashlib.sha256(pdf_dst.read_bytes()).hexdigest()

shutil.copyfile(SRC / "document.json", SAMPLE / "document.json")
doc = json.loads((SAMPLE / "document.json").read_text(encoding="utf-8"))
old = json.loads((SRC / "pdf_locations.json").read_text(encoding="utf-8"))

with fitz.open(pdf_dst) as pdf:
    page_count = pdf.page_count
    sections = []
    for sec in old["sections"]:
        page = pdf[sec["generated_page"] - 1]
        w, h = page.rect.width, page.rect.height
        hits = page.search_for(sec["title"][:12])
        if hits:
            r = hits[0]
            x1, y1 = max(0.0, (r.x0 - 2) / w), max(0.0, (r.y0 - 1) / h)
            x2, y2 = min(1.0, (r.x1 + 2) / w), min(1.0, (r.y1 + 1) / h)
        else:
            x1, y1, x2, y2 = 0.08, 0.10, 0.92, 0.14
        sections.append({
            "id": sec["id"], "title": sec["title"], "generated_page": sec["generated_page"],
            "rect": {"page": sec["generated_page"], "x1": x1, "y1": y1, "x2": max(x2, x1 + 0.02), "y2": max(y2, y1 + 0.01)},
        })

record = {
    "course_id": "experimental-psychology-3",
    "document_id": "chapter-04",
    "version": version,
    "page_count": page_count,
    "source": doc["source"],
    "sections": sections,
}
(SAMPLE / "pdf_locations.json").write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
print("sample ok:", pdf_dst, page_count, "pages", len(sections), "sections", version[:12])
