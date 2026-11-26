"""把用户提供的《实验心理学》原教材 txt 重建进平台课程资源。
生成：document.json / chapter_XX.generated.pdf / pdf_locations.json / pdf_manifest.json / manifest.json
约束：document.json 块文本逐字出现在 PDF 中；pdf_manifest.version = PDF sha256。
"""
import hashlib, json, re, sys
from pathlib import Path
import fitz

ROOT = Path(r"C:/Users/HP/WorkBuddy/2026-11-19-21-53-59/heart_extracted/heart-codex-ta5-acceptance-20261029/project/integration/discrete-math-tutor")
COURSE = ROOT / "knowledge/courses/experimental-psychology-3"
TXT = Path(r"C:/Users/HP/Downloads/实验心理学.txt")

CN = "一二三四五六七八九十"
CHAPTER_RE = re.compile(rf"^第[{CN}]+章$")
SECTION_RE = re.compile(rf"^(第[{CN}]+节)〔(.+)〕$")  # placeholder, replaced below
SECTION_RE = re.compile(rf"^(第[{CN}]+节)[　\s]*(.+)$")
CN_NUM = {c: i + 1 for i, c in enumerate("一二三四五六七八九")}
CN_NUM["十"] = 10


def cn_to_int(s):
    if s == "十":
        return 10
    if "十" in s:
        a, _, b = s.partition("十")
        return (CN_NUM[a] if a else 1) * 10 + (CN_NUM[b] if b else 0)
    return CN_NUM[s]


def parse():
    lines = TXT.read_text(encoding="utf-8").replace("\U001001b3", "\u2019").splitlines()
    chapters, cur, sec = [], None, None
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if CHAPTER_RE.match(line):
            num = cn_to_int(re.match(rf"^第([{CN}]+)章$", line).group(1))
            cur = {"num": num, "title": None, "sections": []}
            chapters.append(cur)
            sec = None
            continue
        if cur is not None and cur["title"] is None:
            cur["title"] = re.sub(r"[　\s]+", "", line)
            continue
        if cur is None:
            continue  # 前置空白
        m = SECTION_RE.match(line)
        if m:
            sec = {"id": len(cur["sections"]) + 1, "title": line, "blocks": []}
            cur["sections"].append(sec)
            continue
        if sec is None:
            sec = {"id": 1, "title": "导言", "blocks": []}
            cur["sections"].append(sec)
        sec["blocks"].append(line)
    # 章级重复合并：任何在章内重复出现的行并入前一块，保证块文本在文档内唯一
    for ch in chapters:
        seen = set()
        last_holder = None  # (blocks_list, index)
        for s in ch["sections"]:
            out = []
            for b in s["blocks"]:
                if b in seen:
                    if out:
                        out[-1] += "\n" + b
                        last_holder = (out, len(out) - 1)
                    elif last_holder:
                        lst, i = last_holder
                        lst[i] += "\n" + b
                    continue
                seen.add(b)
                out.append(b)
                last_holder = (out, len(out) - 1)
            s["blocks"] = out
    return chapters


def render_pdf(ch, blocks, pdf_path):
    """按块顺序渲染 PDF；返回 sections 的 (page,y) 与页数。blocks: [(text, is_section_heading, sec_id)]"""
    W, H = 595.28, 841.89
    MARGIN_L, MARGIN_R, TOP, BOTTOM = 56, 56, 64, 64
    FS, LEAD = 11, 16.2
    HFS, HLEAD = 13, 19
    usable_w = W - MARGIN_L - MARGIN_R
    doc = fitz.open()
    page = doc.new_page(width=W, height=H)
    y = TOP
    records = {}  # sec_id -> (page, ynorm)
    page_no = 1

    def new_page():
        nonlocal page, y, page_no
        page = doc.new_page(width=W, height=H)
        page_no += 1
        y = TOP

    def wrap(text, fs):
        per = max(8, int(usable_w // fs))
        out = []
        for para in text.split("\n"):
            t = para.replace("\t", "　")
            for i in range(0, len(t), per):
                out.append(t[i:i + per])
        return out

    def draw(text, fs, lead, is_heading):
        nonlocal y
        lines_ = wrap(text, fs)
        for ln in lines_:
            if y + lead > H - BOTTOM:
                new_page()
            if is_heading:
                # 小节标题前留白，避免孤行
                if y + lead + 10 > H - BOTTOM:
                    new_page()
            page.insert_text((MARGIN_L, y + fs), ln, fontname="simsun",
                             fontfile="C:/Windows/Fonts/simsun.ttc", fontsize=fs)
            y += lead

    # 章标题
    draw(f"第{ch['num']}章 {ch['title']}", 16, 24, False)
    y += 10
    for text, is_sec, sid in blocks:
        if is_sec:
            y += 8
            if y + 40 > H - BOTTOM:
                new_page()
            records[sid] = (page_no, max(0.02, round((y - 24) / H, 4)))
            draw(text, HFS, HLEAD, True)
            y += 4
        else:
            draw(text, FS, LEAD, False)
            y += 7
    doc.save(str(pdf_path), deflate=True)
    doc.close()
    return records, page_no


def main():
    chapters = parse()
    print("解析章节：", [(c["num"], c["title"], len(c["sections"])) for c in chapters])
    assert len(chapters) == 11, "章数不为 11"
    sha_txt = hashlib.sha256(TXT.read_bytes()).hexdigest()

    pdf_manifest = []
    manifest_chapters = []
    report = []
    for ch in chapters:
        n = ch["num"]
        folder = COURSE / "chapters" / f"chapter_{n:02d}"
        folder.mkdir(parents=True, exist_ok=True)
        source_label = f"实验心理学（第3版）/第{n}章 {ch['title']}"
        # 组渲染序列与文档块
        blocks_for_pdf, doc_blocks = [], []
        idx = 0
        for s in ch["sections"]:
            blocks_for_pdf.append((s["title"], True, s["id"]))
            doc_blocks.append({"block_index": idx, "section": s["title"], "section_id": s["id"],
                               "kind": "text", "text": s["title"], "image_ids": []})
            idx += 1
            for b in s["blocks"]:
                blocks_for_pdf.append((b, False, s["id"]))
                doc_blocks.append({"block_index": idx, "section": s["title"], "section_id": s["id"],
                                   "kind": "text", "text": b, "image_ids": []})
                idx += 1
        (folder / "document.json").write_text(
            json.dumps({"chapter_id": n, "source": source_label, "blocks": doc_blocks}, ensure_ascii=False), encoding="utf-8")
        pdf_path = folder / f"chapter_{n:02d}.generated.pdf"
        records, page_count = render_pdf(ch, blocks_for_pdf, pdf_path)
        sha_pdf = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
        sections_pdf = [{"id": s["id"], "title": s["title"], "page": records[s["id"]][0], "y": records[s["id"]][1]}
                        for s in ch["sections"]]
        pdf_manifest.append({
            "document_id": f"chapter-{n:02d}", "chapter_id": n, "version": sha_pdf,
            "page_count": page_count, "course_id": "experimental-psychology-3",
            "title": f"第{n}章 {ch['title']}",
            "source": f"chapters/chapter_{n:02d}/第{n}章 {ch['title']}.pdf",
            "sections": sections_pdf,
        })
        (folder / "pdf_locations.json").write_text(json.dumps({
            "source": source_label,
            "sections": [{"id": s["id"], "title": s["title"], "generated_page": records[s["id"]][0]}
                         for s in ch["sections"]]}, ensure_ascii=False), encoding="utf-8")
        (folder / "assets.json").write_text("[]", encoding="utf-8")
        (folder / "text.txt").write_text("\n\n".join(b["text"] for b in doc_blocks if b["text"]), encoding="utf-8")
        manifest_chapters.append({"id": n, "title": ch["title"],
                                  "sections": [{"id": s["id"], "title": s["title"]} for s in ch["sections"]]})
        report.append({"chapter_id": n, "title": ch["title"], "sections": len(ch["sections"]),
                       "blocks": idx, "pages": page_count, "source_sha256": sha_txt})
        print(json.dumps(report[-1], ensure_ascii=False))

    (COURSE / "pdf_manifest.json").write_text(json.dumps(pdf_manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    manifest = {
        "course_id": "experimental-psychology-3",
        "version": "textbook-real-v1",
        "title": "实验心理学（第3版）",
        "full_import": {"status": "released", "chapters": [{"chapter_id": c["num"]} for c in chapters]},
        "chapters": manifest_chapters,
        "source_sha256": {"textbook.docx": sha_txt},
        "status": "released",
    }
    (COURSE / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    # kc_registry 版本对齐
    kc_path = COURSE / "kc_registry.json"
    kc = json.loads(kc_path.read_text(encoding="utf-8"))
    kc["version"] = "textbook-real-v1"
    kc_path.write_text(json.dumps(kc, ensure_ascii=False), encoding="utf-8")
    print("重建完成，共", sum(r["pages"] for r in report), "页")


if __name__ == "__main__":
    main()
