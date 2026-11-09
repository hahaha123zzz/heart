"""宿主课程大纲到原生课程服务的导入；只读宿主已校验教材清单。"""
from __future__ import annotations

import json


def course_syllabus() -> list[dict]:
    """把教材章节转成原生 syllabus units；章节号保持宿主 id 以便对照。"""
    from knowledge.course_config import PSYCHOLOGY_DIR

    path = PSYCHOLOGY_DIR / "manifest.json"
    if not path.is_file():
        raise ValueError("课程教材清单不存在")
    data = json.loads(path.read_text(encoding="utf-8"))
    units = []
    for chapter in data.get("chapters", ()):
        topics = [str(section.get("title")).strip() for section in chapter.get("sections", ())
                  if str(section.get("title") or "").strip()]
        units.append({"id": f"chapter-{chapter.get('id')}", "position": len(units) + 1,
                      "title": str(chapter.get("title") or f"第{chapter.get('id')}章").strip(),
                      "topics": topics})
    return units


def ensure_syllabus(course_id: str) -> int:
    """补齐空课程大纲；已有大纲不覆盖用户或前面的导入结果。"""
    from deeptutor.services.courses import get_course_service

    service = get_course_service()
    course = service.get(course_id)
    if course.syllabus:
        return len(course.syllabus)
    units = course_syllabus()
    if units:
        service.set_syllabus(course_id, units)
    return len(units)
