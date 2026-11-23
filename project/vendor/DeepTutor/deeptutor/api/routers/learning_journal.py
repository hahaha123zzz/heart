"""Read-only view of the workspace's conversational learning journal."""

from fastapi import APIRouter, HTTPException, Query, Response

from deeptutor.services.learning_journal import get_learning_journal_store

router = APIRouter()


@router.get("")
def overview(response: Response, limit: int = Query(default=20, ge=1, le=50), offset: int = Query(default=0, ge=0, le=50)):
    response.headers["Cache-Control"] = "no-store"
    try:
        snapshot = get_learning_journal_store().overview()
        records = snapshot["records"]
        return {**snapshot, "records": records[offset:offset + limit],
                "next_offset": offset + limit if offset + limit < len(records) else None}
    except (OSError, ValueError) as exc:
        raise HTTPException(
            status_code=409,
            detail="Learning journal could not be read. Its original file has been preserved.",
        ) from exc
