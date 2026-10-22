"""冻结 Q2 全书解析产物，显式转换为上游 ParsedDocument。"""
from pathlib import Path
import hashlib,json,shutil,importlib.util
from dataclasses import asdict
from .file_io import atomic_write_json
from .ingress import _copy_regular, _contained_regular_file, IngressError
from .parse_types import ParsedDocument
from .indexing_policy import _fingerprint

COURSE="experimental-psychology-3"

def digest(path):
    with Path(path).open("rb") as stream: return hashlib.file_digest(stream,"sha256").hexdigest()

def material_files(records):
    return {k:v for k,v in records.items() if Path(k).parts[0] in ("chapters","source")
            or k in ("manifest.json","pdf_manifest.json","import_report.json","rag_index.sqlite3")}

def inventory(root):
    root=Path(root)
    if root.is_symlink() or bool(getattr(root.lstat(),"st_file_attributes",0)&0x400):
        raise IngressError("教材输入根不得为 reparse point")
    root=root.resolve(strict=True)
    if (root/"rag_index.sqlite3-wal").exists(): raise IngressError("Q2 教材索引正在写入")
    result={}
    for path in sorted(root.rglob("*")):
        relative=path.relative_to(root).as_posix()
        if not material_files({relative:""}): continue
        if path.is_symlink() or bool(getattr(path.lstat(),"st_file_attributes",0)&0x400):
            raise IngressError("教材快照不允许 reparse point")
        if path.is_file():
            _contained_regular_file(root,path,label="course input")
            result[path.relative_to(root).as_posix()]=digest(path)
    if not result: raise IngressError("教材输入为空")
    return result

def verify(root, expected):
    actual=inventory(root)
    if actual!=material_files(expected): raise IngressError("教材输入已变化，拒绝在同一候选索引混入新版本")

def verify_active(root, expected):
    """宿主还含Q2索引/未入图产物；冻结原文必须逐项相同，额外文件不成为图证据。"""
    actual=inventory(root);required=material_files(expected)
    if any(actual.get(path)!=sha for path,sha in required.items()):
        raise IngressError("宿主教材缺失或版本变化，拒绝混用候选来源")
    return {path:sha for path,sha in actual.items() if path not in required}

def visual_inventory(root):
    # 独立模块实例绑定明确资源根，避免改写 Q2 模块全局状态。
    spec=importlib.util.spec_from_file_location("knowledge._lightrag_source_visuals",Path(__file__).parents[1]/"source_visuals.py")
    import sys
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    module.PSYCHOLOGY_DIR=Path(root)
    visuals,_=module.load_visuals()
    gaps=module.gaps();stats=module.stats()
    for declaration in (Path(root).parent/"q2_input_manifest.json",Path(root).parent/"input_manifest.json"):
        if not declaration.is_file(): continue
        declared=json.loads(declaration.read_text(encoding="utf-8"))
        if declared.get("schema")!="full-course-inputs-v1": continue
        assets={item["id"]:item for item in declared["assets"]}
        visuals=tuple(v for v in visuals if assets.get(v.id,{}).get("disposition")=="candidate_pending_review")
        for gap in gaps:
            item=assets.get(gap["visual_id"],{})
            gap.update(classification="decoration" if item.get("disposition")=="exclude_decoration" else "unresolved",
                       disposition=item.get("disposition"),reason=item.get("visual_inspection") or gap["reason"])
        stats.update(filtered_decorations=sum(g["classification"]=="decoration" for g in gaps),
                     unresolved_gaps=sum(g["classification"]!="decoration" for g in gaps))
        break
    return {v.id:v for v in visuals}, gaps, stats

def declared_snapshot(source):
    path=Path(source).parent/"input_manifest.json"
    if not path.is_file(): return None
    value=json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema")!="full-course-inputs-v1": return None
    calculated=hashlib.sha256(json.dumps(value["files"],ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    if value.get("snapshot_id")!=calculated: raise IngressError("Q2冻结清单身份无效")
    if sorted(c["chapter_id"] for c in value["chapters"])!=list(range(1,12)):
        raise IngressError("Q2冻结清单不含完整11章")
    if value.get("ready") is not False or value.get("course_status")!="staging":
        # 本适配仅构建当前已授权的staging候选，不推导任何发布状态。
        raise IngressError("Q2输入发布状态不属于当前候选任务")
    expected={f["path"]:f["sha256"] for f in value["files"]}
    if len(expected)!=len(value["files"]): raise IngressError("Q2冻结清单存在重复路径")
    for f in value["files"]:
        relative=Path(f["path"])
        if relative.is_absolute() or ".." in relative.parts: raise IngressError("Q2清单路径越界")
        if (Path(source)/relative).stat().st_size!=f["size"]: raise IngressError("Q2冻结文件长度不符")
    verify(source,expected)
    return value


def freeze(source, base):
    source=Path(source);base=Path(base).resolve()
    before=inventory(source)
    source=source.resolve(strict=True)
    q2=declared_snapshot(source)
    signature=q2["snapshot_id"] if q2 else _fingerprint(before)
    candidate=base/signature;candidate.mkdir(parents=True,exist_ok=True)
    target=candidate/"input"; record=candidate/"input_manifest.json"
    if record.exists():
        manifest=json.loads(record.read_text(encoding="utf-8"))
        if manifest["files"]!=before: raise IngressError("快照身份冲突")
        verify(target,before)
        return candidate,manifest
    if target.exists():
        # 断点复制只接纳已存在且哈希一致的完整文件。
        for relative,sha in before.items():
            p=target/relative
            if p.exists() and digest(p)!=sha: raise IngressError("不完整快照需要另建候选目录")
    for relative,sha in before.items():
        dst=target/relative
        if not dst.exists(): _copy_regular(source/relative,dst,allowed_root=source)
    verify(source,before);verify(target,before)
    manifest=json.loads((target/"manifest.json").read_text(encoding="utf-8"))
    if manifest.get("course_id")!=COURSE or {c["id"] for c in manifest["chapters"]}!=set(range(1,12)):
        raise IngressError("课程必须包含且仅包含 1—11 章")
    if q2:
        (candidate/"q2_input_manifest.json").write_bytes((source.parent/"input_manifest.json").read_bytes())
    visuals,gaps,stats=visual_inventory(target)
    frozen={"schema":1,"course_id":COURSE,"input_signature":signature,"source_root":str(source),
            "files":before,"status":manifest.get("status"),"visuals":stats,"visual_gaps":gaps,
            "q2_source_visuals_sha256":digest(Path(__file__).parents[1]/"source_visuals.py")}
    if q2:
        frozen.update(q2_snapshot_id=q2["snapshot_id"],q2_manifest_sha256=digest(source.parent/"input_manifest.json"))
    atomic_write_json(record,frozen)
    return candidate,frozen

def convert(course, chapter, *, visual_map=None):
    course=Path(course).resolve(strict=True);directory=course/"chapters"/f"chapter_{chapter:02d}"
    doc=json.loads((directory/"document.json").read_text(encoding="utf-8"))
    if doc.get("course_id")!=COURSE or doc.get("chapter_id")!=chapter: raise IngressError("章节身份错误")
    if doc.get("block_count")!=len(doc["blocks"]): raise IngressError("章节块数不一致")
    ids=[b["block_index"] for b in doc["blocks"]]
    if len(set(ids))!=len(ids) or ids!=sorted(ids): raise IngressError("原文 block 身份重复或乱序")
    pdf=next(r for r in json.loads((course/"pdf_manifest.json").read_text(encoding="utf-8")) if r["chapter_id"]==chapter)
    pdf_file=directory/f"chapter_{chapter:02d}.generated.pdf"
    if digest(pdf_file)!=pdf["version"]: raise IngressError("PDF 版本哈希不符")
    docx=_contained_regular_file(course,directory/doc["word_source"],label="Q2 DOCX")
    if digest(docx)!=doc["docx_sha256"]: raise IngressError("DOCX 版本哈希不符")
    visual_map=visual_map if visual_map is not None else visual_inventory(course)[0]
    blocks=[];mapping=[];current_section=None
    for block in doc["blocks"]:
        index=block["block_index"];section=block.get("section_id")
        if section != current_section:
            current_section=section
            blocks.append({"type":"section_header","text":block["section"],"level":2})
        text=block["text"]
        # 原文独立保留；SDK 表格摘要、图片分析不能覆盖正文。
        if text.strip(): blocks.append({"type":"text","text":text,"heart_block_index":index})
        if block["kind"]=="table":
            rows=block.get("rows")
            if not isinstance(rows,list) or not rows or not all(isinstance(r,list) for r in rows):
                raise IngressError("Q2 表格缺少有效 rows")
            blocks.append({"type":"table","rows":rows,"heart_block_index":index})
        for asset_id in dict.fromkeys(block.get("image_ids",[])+block.get("formula_ids",[])):
            visual=visual_map.get(asset_id)
            if visual:
                relative=visual.path.relative_to(directory/"assets")
                blocks.append({"type":"image","img_path":str(relative),
                    "image_caption":list(visual.labels),"heart_block_index":index,
                    "heart_asset_id":asset_id,"review_status":visual.review_status})
        mapping.append({"block_index":index,"section_id":section,"section":block["section"],
                        "kind":block["kind"],"text":text,"rows":block.get("rows"),
                        "image_ids":block.get("image_ids",[]),"formula_ids":block.get("formula_ids",[])})
    if not any(b["type"]=="text" for b in blocks): raise IngressError("章节正文为空")
    parsed=ParsedDocument(markdown="\n\n".join(b["text"] for b in doc["blocks"] if b["text"].strip()),
        blocks=blocks, asset_dir=directory/"assets", source_hash=doc["docx_sha256"],
        parser_signature="heart-q2-document-v1:"+digest(directory/"document.json"),engine="heart-q2")
    source_map={"chapter_id":chapter,"source":doc["source"],"document_id":pdf["document_id"],
                "version":pdf["version"],"document_sha256":digest(directory/"document.json"),
                "sections":pdf["sections"],"blocks":mapping,"omml_objects":doc.get("omml_objects",[]),
                "formulas_status":"raw_omml_requires_pdf_verification" if doc.get("omml_objects") else "none"}
    return pdf_file,parsed,source_map
