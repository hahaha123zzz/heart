"""学生个人模型配置 API：H PostgreSQL 密文存储，请求内加载。"""
from __future__ import annotations

from pathlib import Path
from uuid import UUID
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field

from deeptutor.api.routers.auth import require_auth, TokenPayload
from deeptutor.multi_user.personal_models import set_external_llm_profiles
from integrations.deeptutor import model_credentials as credentials
from integrations.deeptutor.model_http import build_student_http_client, resolve_public_endpoint


class EvaluationSettingsRequest(BaseModel):
    enabled: bool = Field(strict=True)


class ModelKeyRequest(BaseModel):
    base_url: str = Field(min_length=8, max_length=2048)
    model: str = Field(min_length=1, max_length=128)
    api_key: str = Field(min_length=1, max_length=512)


class ReassessmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: UUID
    reason: str = Field(strict=True, min_length=1, max_length=1000)
    confirm_cost: bool = Field(strict=True)
    confirm_unknown_retry: bool = Field(default=False, strict=True)


class ModelCheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: UUID
    credential_version: str = Field(strict=True, pattern=r"^[a-f0-9]{64}$")
    capability: Literal["chat", "assessment", "tools", "vision"]
    confirm_cost: bool = Field(strict=True)


def _check_endpoint(base_url: str) -> str:
    try:
        resolve_public_endpoint(base_url)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    return base_url


def _personal_profiles(user) -> list[dict] | None:
    if user is None or user.is_admin:
        return None
    record = credentials.runtime_config(user.username)
    if record is None:
        return []
    return [{"id": "heart-student-" + user.id, "name": "我的模型", "binding": "openai",
             "owner_bound": True, "base_url": _check_endpoint(record["base_url"]),
             "api_key": record["api_key"], "wire_api": "chat_completions",
             "models": [{"id": "student-model", "name": record["model"], "model": record["model"]}]}]


def install_heart_model(app, home: Path) -> None:
    # 保留 home 参数兼容 worker；凭据不再读写厂家目录。
    credentials.ensure_table()
    set_external_llm_profiles(_personal_profiles)
    from deeptutor.multi_user.context import get_current_user_or_none
    from deeptutor.services.llm.openai_http_client import set_external_http_client

    def personal_http_client(base_url):
        user = get_current_user_or_none()
        return build_student_http_client(base_url) if user is not None and not user.is_admin else None

    set_external_http_client(personal_http_client)
    router = APIRouter(prefix="/api/heart", dependencies=[Depends(require_auth)])

    @router.get("/display")
    def read_display(response: Response, payload: TokenPayload = Depends(require_auth)) -> dict:
        from deeptutor.api.routers.settings import load_ui_settings
        response.headers["Cache-Control"] = "no-store"
        current = load_ui_settings()
        return {key: current.get(key, False if key == "code_block_wrap_long_lines" else "zh")
                for key in ("language", "response_language", "code_block_wrap_long_lines")}

    @router.get("/model")
    def read_model(response: Response, payload: TokenPayload = Depends(require_auth)) -> dict:
        response.headers["Cache-Control"] = "no-store"
        return credentials.read(payload.username) or {"configured": False}

    @router.put("/model")
    def save_model(body: ModelKeyRequest, payload: TokenPayload = Depends(require_auth)) -> dict:
        base_url = _check_endpoint(body.base_url.strip().rstrip("/"))
        model, api_key = body.model.strip(), body.api_key.strip()
        if not model or not api_key:
            raise HTTPException(400, "模型名称和 API Key 不能为空")
        try:
            version = credentials.save(payload.username, base_url, model, api_key)
        except RuntimeError as exc:
            raise HTTPException(503, str(exc)) from None
        return {"configured": True, "api_key_masked": "••••" + api_key[-4:], "credential_version": version}

    @router.delete("/model")
    def delete_model(payload: TokenPayload = Depends(require_auth)) -> dict:
        credentials.delete(payload.username)
        return {"configured": False}

    from integrations.deeptutor import model_capabilities

    from deeptutor.services.llm.multimodal import set_external_image_guard

    def require_images(model):
        user = get_current_user_or_none()
        if user is None or user.is_admin:
            return False
        config = credentials.read(user.username)
        if (not config or (model and model != config["model"])
                or not model_capabilities.capability_ready(user.username, user.id,
                    config["credential_version"], "vision")):
            raise ValueError("图片请求已暂停，请到个人模型设置验证当前配置的图片能力，或更换支持图片的模型。")
        return True

    set_external_image_guard(require_images)

    from deeptutor.learning.service import set_external_assessment_guard, MasteryInteractionError

    def require_assessment(user):
        config = credentials.read(user.username)
        if not config or not model_capabilities.assessment_ready(user.username, user.id, config["credential_version"]):
            raise MasteryInteractionError("评分已暂停，请到个人模型设置验证当前配置的结构化评估能力。")

    set_external_assessment_guard(require_assessment)

    @router.get("/model/checks")
    def read_model_checks(response: Response, payload: TokenPayload = Depends(require_auth)) -> dict:
        response.headers["Cache-Control"] = "no-store"
        return model_capabilities.read_checks(payload.username, payload.user_id)

    @router.post("/model/checks")
    async def check_model(body: ModelCheckRequest, payload: TokenPayload = Depends(require_auth)) -> dict:
        try:
            return await model_capabilities.run_check(payload.username, payload.user_id, str(body.request_id),
                body.capability, body.credential_version, confirm_cost=body.confirm_cost)
        except ValueError as exc:
            raise HTTPException(409, model_capabilities.MESSAGES.get(str(exc), "检查申请无效，请重新读取配置并确认费用。")) from None
        except RuntimeError:
            raise HTTPException(503, "无法读取个人模型凭据，请重新保存 Key 或联系管理员。") from None

    from integrations.deeptutor import assessment_jobs

    @router.get("/learning/chapter-progress")
    def read_chapter_progress(response: Response, chapter: int = Query(ge=1, le=11),
                              payload: TokenPayload = Depends(require_auth)) -> dict:
        from knowledge.course_config import PSYCHOLOGY, ROOT
        if not payload or not payload.user_id:
            raise HTTPException(401, "请先登录")
        response.headers["Cache-Control"] = "no-store"
        if not PSYCHOLOGY:
            import json
            from pathlib import Path as _Path
            records = json.loads((_Path(ROOT) / "knowledge/pdf_sections.json").read_text("utf-8"))
            record = next((item for item in records if int(item["id"]) == chapter), None)
            chapter_title = "".join(str((record or {}).get("title") or "").split())
            chapter_label = f"第{chapter}章{chapter_title}"
            points = [{"id": f"d{chapter}-{section['id']}",
                       "name": " ".join(str(section["title"]).split()),
                       "snapshot": None, "practice_review": None,
                       "sync_pending": False, "sync_blocked": False}
                      for section in (record or {}).get("sections") or []
                      if "".join(str(section["title"]).split()) not in {chapter_label, chapter_title}]
            return {"catalog_available": True, "points": points}
        from integrations.deeptutor.learning_projection import chapter_progress
        return chapter_progress(payload.username, payload.user_id, chapter)

    @router.get("/learning/evidence/{job_id}")
    def read_learning_evidence(job_id: UUID, response: Response, payload: TokenPayload = Depends(require_auth)) -> dict:
        from integrations.deeptutor.learning_projection import assessment_evidence
        if not payload or not payload.user_id:
            raise HTTPException(401, "请先登录")
        result = assessment_evidence(payload.username, payload.user_id, str(job_id))
        if result is None:
            raise HTTPException(404, "学习证据不存在")
        response.headers["Cache-Control"] = "no-store"
        return result

    @router.get("/evaluation")
    def read_evaluation(payload: TokenPayload = Depends(require_auth)) -> dict:
        return assessment_jobs.get_enabled(payload.username)

    @router.put("/evaluation")
    def save_evaluation(body: EvaluationSettingsRequest, payload: TokenPayload = Depends(require_auth)) -> dict:
        return assessment_jobs.set_enabled(payload.username, body.enabled)

    @router.get("/evaluation/jobs")
    def read_evaluation_jobs(response: Response, payload: TokenPayload = Depends(require_auth)) -> dict:
        response.headers["Cache-Control"] = "no-store"
        return assessment_jobs.recent_jobs(payload.username, payload.user_id)

    @router.get("/evaluation/jobs/{job_id}")
    def read_evaluation_job(job_id: str, payload: TokenPayload = Depends(require_auth)) -> dict:
        result = assessment_jobs.status(payload.username, job_id, payload.user_id)
        if result is None:
            raise HTTPException(404, "评估任务不存在")
        return result

    @router.post("/evaluation/jobs/{job_id}/reassessment")
    def request_evaluation_reassessment(job_id: str, body: ReassessmentRequest,
                                       payload: TokenPayload = Depends(require_auth)) -> dict:
        try:
            return assessment_jobs.request_reassessment(payload.username, payload.user_id, job_id,
                str(body.request_id), body.reason, confirm_cost=body.confirm_cost,
                confirm_unknown_retry=body.confirm_unknown_retry)
        except ValueError as exc:
            code = str(exc)
            messages = {
                "assessment_not_found": "评估任务不存在",
                "reassessment_cost_confirmation_required": "请先确认复评费用",
                "invalid_reassessment_reason": "请填写 1 到 1000 字的复评原因",
                "reassessment_request_conflict": "该申请编号已用于其他复评原因，请刷新记录",
                "assessment_not_published": "原评估尚未完成记录同步，请稍后申请",
                "reassessment_already_succeeded": "该原评分已完成一次复评，不能再次申请",
                "reassessment_outcome_unknown": "上次结果不明，可能已计费；请明确确认再次调用的费用",
                "reassessment_qualification_unsupported": "该记录的独立资格复核尚未接入，暂不能复评",
                "reassessment_catalog_changed": "教材目录或规则已更新，不能按旧版本发起复评",
            }
            raise HTTPException(404 if code == "assessment_not_found" else 409,
                                messages.get(code, "该记录暂不符合复评条件，请刷新后查看")) from None

    app.include_router(router)
