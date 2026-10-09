"""Student-facing course, quiz, progress and preference API for the local demo."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from database.database import session_scope
from database.models import (ConversationRow, KnowledgeStateRow, MisconceptionRow,
                             QuizAttemptRow, ResourceViewRow, ExerciseSubmissionRow)
from knowledge.figures import get_figure, section_figures
from knowledge.content import section_blocks
from knowledge.pdf_reader import section_pdf
from knowledge.course import (CHAPTER_TITLES, chapter_summary, get_chapter,
                              get_section, grade_quiz, public_quiz, QUIZZES)

router = APIRouter(prefix="/api")


def _student_id(value: str) -> str:
    if not 1 <= len(value) <= 64 or any(c in value for c in "\r\n\t"):
        raise HTTPException(422, "学生 ID 无效")
    return value


def _demo_account(student_id: str):
    from main import orchestrator
    _student_id(student_id)
    try:
        orchestrator.memory.accounts.create_test_account(student_id, ttl_hours=24)
    except ValueError as exc:
        raise HTTPException(403, str(exc)) from exc


@router.get("/course/chapters")
def course_chapters():
    return chapter_summary()


@router.get("/course/search")
def search_course(q: str):
    query = "".join(q.casefold().split())
    if not query:
        return []
    results = []
    for chapter in chapter_summary():
        full = get_chapter(chapter["id"])
        for section_meta in chapter["sections"]:
            section = get_section(chapter["id"], section_meta["id"])
            title_match = query in "".join(section["title"].casefold().split())
            text = "".join(section["content"].casefold().split())
            at = text.find(query)
            if not title_match and at < 0:
                continue
            excerpt = section["content"][:260]
            results.append({"chapter_id": chapter["id"], "section_id": section["id"],
                "chapter_title": chapter["title"], "title": section["title"],
                "excerpt": excerpt, "source": full["source"]})
            if len(results) >= 12:
                return results
    return results


@router.get("/course/chapters/{chapter_id}/sections/{section_id}")
def course_section(chapter_id: int, section_id: int):
    chapter = get_chapter(chapter_id)
    section = get_section(chapter_id, section_id)
    if chapter is None or section is None:
        raise HTTPException(404, "章节或小节不存在")
    return {"chapter_id": chapter_id, "chapter_title": chapter["title"],
            "source": chapter["source"], **section,
            "figures": section_figures(chapter_id, section_id),
            "blocks": section_blocks(chapter_id, section_id),
            "pdf": section_pdf(chapter_id, section_id),
            "figure_note": "图、公式和表格来自原 Word。公式保留原图，可点击放大；绘图锚点预览可能含多个子图，图号未逐一核定。"}


class ViewRequest(BaseModel):
    student_id: str
    chapter_id: int
    section_id: int


@router.post("/course/views")
def record_view(request: ViewRequest):
    if get_section(request.chapter_id, request.section_id) is None:
        raise HTTPException(404, "章节或小节不存在")
    _demo_account(request.student_id)
    with session_scope() as session:
        session.add(ResourceViewRow(student_id=request.student_id,
                                    chapter_id=request.chapter_id,
                                    section_id=request.section_id))
    return {"ok": True}


@router.get("/course/chapters/{chapter_id}/quiz")
def chapter_quiz(chapter_id: int):
    if chapter_id not in CHAPTER_TITLES:
        raise HTTPException(404, "章节不存在")
    return {"chapter_id": chapter_id, "title": CHAPTER_TITLES[chapter_id],
            "questions": public_quiz(chapter_id)}


class QuizSubmission(BaseModel):
    student_id: str
    answers: dict[str, int] = Field(default_factory=dict)


@router.post("/course/chapters/{chapter_id}/quiz")
def submit_quiz(chapter_id: int, request: QuizSubmission):
    try:
        result = grade_quiz(chapter_id, request.answers)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    _demo_account(request.student_id)
    with session_scope() as session:
        session.add(QuizAttemptRow(student_id=request.student_id,
                                   chapter_id=chapter_id, score=result["score"],
                                   result=result))
    return result


@router.get("/students/{student_id}/dashboard")
def dashboard(student_id: str):
    _student_id(student_id)
    with session_scope() as session:
        views = session.scalars(select(ResourceViewRow).where(
            ResourceViewRow.student_id == student_id)).all()
        attempts = session.scalars(select(QuizAttemptRow).where(
            QuizAttemptRow.student_id == student_id).order_by(QuizAttemptRow.id.desc())).all()
        states = session.scalars(select(KnowledgeStateRow).where(
            KnowledgeStateRow.student_id == student_id)).all()
        chats = session.scalars(select(ConversationRow).where(
            ConversationRow.student_id == student_id,
            ConversationRow.role == "user")).all()
        best: dict[int, int] = {}
        for row in attempts:
            best[row.chapter_id] = max(row.score, best.get(row.chapter_id, 0))
        question_lookup = {
            question[0]: {"question": question[1], "options": question[2],
                          "correct": question[3], "chapter_id": chapter_id}
            for chapter_id, questions in QUIZZES.items() for question in questions
        }
        wrong_counts = defaultdict(int)
        for attempt in attempts:
            for item in (attempt.result or {}).get("items", []):
                if not item.get("is_correct") and item.get("id") in question_lookup:
                    wrong_counts[item["id"]] += 1
        common_errors = []
        for qid, count in sorted(wrong_counts.items(), key=lambda item: item[1], reverse=True):
            question = question_lookup[qid]
            common_errors.append({"chapter_id": question["chapter_id"],
                "question": question["question"], "wrong_count": count,
                "correct_option": question["options"][question["correct"]]})
        from practice_api import catalog
        exercise_attempts = session.scalars(select(ExerciseSubmissionRow).where(ExerciseSubmissionRow.student_id==student_id, ExerciseSubmissionRow.version==catalog()['version']).order_by(ExerciseSubmissionRow.created_at)).all()
        latest = {r.question_id:r for r in exercise_attempts if r.status=='completed'}
        confirmed_scores=[];answered_parts=0;pending_review=0
        for qid,row in latest.items():
            q=catalog()['by_id'].get(qid)
            if not q:continue
            for item in row.result.get('parts',[]):
                answered_parts+=1
                if item.get('confirmed'):
                    confirmed_scores.append(item['score'])
                    if item['score']<100:
                        common_errors.append({'chapter_id':q['chapter_id'],'question_id':qid,'question':q['knowledge_point']+' · 练习'+q['group_id']+' 第'+str(q['number'])+'题 '+item['part_id'],'wrong_count':1,'correct_option':str(item.get('reference_answer',''))})
                else:pending_review+=1
        today = datetime.utcnow().date()
        days = [(today - timedelta(days=6-i)).isoformat() for i in range(7)]
        activity = defaultdict(int)
        for row in views:
            activity[row.created_at.date().isoformat()] += 1
        for row in chats:
            activity[row.created_at.date().isoformat()] += 1
        for row in exercise_attempts:
            activity[row.created_at.date().isoformat()] += 1
        return {
            "exercise_stats": {"submissions":len(exercise_attempts),"answered_questions":len(latest),"answered_parts":answered_parts,"needs_review_parts":pending_review,"confirmed_average":round(sum(confirmed_scores)/len(confirmed_scores)) if confirmed_scores else None},
            "viewed_chapters": len({row.chapter_id for row in views}),
            "view_count": len(views), "quiz_attempts": len(attempts),
            "average_best_score": round(sum(best.values()) / len(best)) if best else None,
            "completed_chapters": sum(score >= 80 for score in best.values()),
            "chat_turns": len(chats),
            "chapter_scores": [{"chapter_id": k, "title": CHAPTER_TITLES[k], "score": v}
                               for k, v in sorted(best.items())],
            "common_errors": common_errors[:8],
            "activity": [{"day": day, "count": activity[day]} for day in days],
            "knowledge": [{"point": row.knowledge_point, "mastery": row.mastery,
                           "confidence": row.confidence, "turns": row.turn_count}
                          for row in states],
        }


@router.get("/students/{student_id}/review")
def review_items(student_id: str):
    _student_id(student_id)
    with session_scope() as session:
        misconceptions = session.scalars(select(MisconceptionRow).where(
            MisconceptionRow.student_id == student_id,
            MisconceptionRow.status != "resolved")).all()
        states = session.scalars(select(KnowledgeStateRow).where(
            KnowledgeStateRow.student_id == student_id,
            KnowledgeStateRow.mastery < 0.65,
            KnowledgeStateRow.turn_count > 0)).all()
        items = [{"point": row.knowledge_point, "reason": row.description,
                  "kind": "misconception", "confidence": row.confidence}
                 for row in misconceptions]
        existing = {item["point"] for item in items}
        items += [{"point": row.knowledge_point,
                   "reason": row.remaining_gap or "这个知识点还需要一次小练习。",
                   "kind": "low_mastery", "mastery": row.mastery}
                  for row in states if row.knowledge_point not in existing]
        from practice_api import catalog
        rows=session.scalars(select(ExerciseSubmissionRow).where(ExerciseSubmissionRow.student_id==student_id,ExerciseSubmissionRow.version==catalog()['version'],ExerciseSubmissionRow.status=='completed').order_by(ExerciseSubmissionRow.created_at)).all()
        latest={r.question_id:r for r in rows}
        for qid,row in latest.items():
            q=catalog()['by_id'].get(qid)
            if not q:continue
            weak=[p for p in row.result.get('parts',[]) if p.get('confirmed') and p['score']<100]
            pending=[p for p in row.result.get('parts',[]) if p.get('verdict')=='uncertain']
            if weak or pending:items.append({'point':q['knowledge_point']+' · 练习'+q['group_id']+' 第'+str(q['number'])+'题','reason':str(len(weak))+' 个小题需要订正' if weak else '本题反馈待核对，可重新作答或请 AI 解释','kind':'exercise_review','question_id':qid,'chapter_id':q['chapter_id']})
        return items


@router.get("/students/{student_id}/conversation")
def conversation_history(student_id: str):
    _student_id(student_id)
    from main import orchestrator
    rows = orchestrator.memory.repo.get_conversation_with_figures(student_id, limit=40)
    return [
        {"role": row["role"], "content": row["content"],
         "selection_ref": row.get("selection_ref"),
         "image_refs": [figure.public() for figure_id in row["image_ref_ids"]
                        if (figure := get_figure(figure_id)) is not None]}
        for row in rows
    ]


@router.get("/students/{student_id}/preferences")
def get_preferences(student_id: str):
    _student_id(student_id)
    from main import orchestrator
    return orchestrator.memory.get_profile(student_id).preferences


class PreferenceUpdate(BaseModel):
    answer_length: float = Field(0.5, ge=0.0, le=1.0)
    example_density: float = Field(0.5, ge=0.0, le=1.0)
    learning_pace: float = Field(0.5, ge=0.0, le=1.0)


@router.put("/students/{student_id}/preferences")
def set_preferences(student_id: str, request: PreferenceUpdate):
    _demo_account(student_id)
    from main import orchestrator
    profile = orchestrator.memory.get_profile(student_id)
    profile.preferences.update(request.model_dump())
    orchestrator.memory.save_profile(profile)
    return profile.preferences
