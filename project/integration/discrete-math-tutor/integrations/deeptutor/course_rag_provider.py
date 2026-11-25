"""Bind the host-published course pack to an upstream study course."""
from __future__ import annotations

import os
from pathlib import Path

from .published_course import COURSE, read_pack, register_course_knowledge

COURSE_ALIASES = {
    COURSE,
    "heart-" + COURSE,
    "course:" + COURSE,
    "实验心理学",
    "实验心理学（第3版）",
}


def _published() -> tuple[Path, dict] | None:
    home = os.getenv("DEEPTUTOR_HOME", "").strip()
    if not home:
        return None
    try:
        return read_pack(Path(home), verify_files=False)
    except (OSError, ValueError):
        return None


def canonical_names(names) -> list[str]:
    """Resolve course aliases to the current immutable published KB name."""
    published = _published()
    current = "heart_" + published[1]["version"][:24] if published else COURSE
    result = []
    for raw in names or ():
        name = str(raw).strip()
        if not name:
            continue
        name = current if name in COURSE_ALIASES or name.startswith("heart_" + COURSE) else name
        if name not in result:
            result.append(name)
    return result


def register_course_sources(course_id: str) -> str | None:
    """Attach the verified published vault when one exists.

    Native course search uses the Host's own retrieval tool even without a
    published vault, so a missing pack must not make normal chat unavailable.
    """
    published = _published()
    if published is None:
        return None
    home = Path(os.environ["DEEPTUTOR_HOME"]).resolve()
    from deeptutor.services.courses import CourseService

    return register_course_knowledge(home, CourseService(), course_id)
