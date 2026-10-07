"""Reviewer API for evidence search and citation-backed findings."""

import os
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import select

from tracepaper.agent.enforcement import EnforcementPipeline
from tracepaper.agent.loop import AgentLoop
from tracepaper.agent.rules import SUPPORTED_OPERATORS, evaluate_rule
from tracepaper.agent.tools import EvidenceTools
from tracepaper.auth import AuthService, public_user
from tracepaper.config import get_settings
from tracepaper.ingestion.chunker import chunk_pages
from tracepaper.ingestion.extraction import DocumentExtractor
from tracepaper.ingestion.understanding import DocumentUnderstandingService
from tracepaper.llm.factory import create_llm_client
from tracepaper.logging import get_logger, setup_logging
from tracepaper.retrieval import EvidenceRetriever
from tracepaper.storage.models import (
    AuditFindingRecord,
    AuditRuleRecord,
    ClassificationTypeRecord,
    DocumentSegmentRecord,
    UploadedDocumentRecord,
    UserRecord,
)

settings = get_settings()
setup_logging(settings.log_level)
logger = get_logger(__name__)

app = FastAPI(
    title="Tracepaper Reviewer API",
    description="Reviewer-facing evidence retrieval and enforced findings.",
    version="0.1.0",
)


class CitationInput(BaseModel):
    doc_id: str
    page: int = Field(ge=1)
    bbox: tuple[float, float, float, float]
    quoted_span: str = Field(min_length=1)


class FindingInput(BaseModel):
    control_id: str
    population_item_id: str
    disposition: str
    rationale: str = ""
    citations: list[CitationInput] = Field(default_factory=list)


class ReviewAction(BaseModel):
    reviewer: str = "anonymous"
    note: str = ""


class AgentRequest(BaseModel):
    task: str = Field(min_length=1)


class LoginInput(BaseModel):
    email: str
    password: str


class InviteAcceptInput(BaseModel):
    token: str
    password: str


class InviteCreateInput(BaseModel):
    email: str
    display_name: str = Field(min_length=1, max_length=200)
    role: str = "reviewer"


class AuditRuleInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    control_type: str
    document_type: str = "*"
    field_name: str = Field(min_length=1, max_length=128)
    operator: str
    expected_value: Any = None
    severity: str = "high"
    enabled: bool = True


class FindingStatusInput(BaseModel):
    status: str


@lru_cache(maxsize=1)
def get_retriever() -> EvidenceRetriever:
    """Create one retriever for the configured PostgreSQL database."""
    return EvidenceRetriever(settings.database_url, embedding_model=settings.embeddings_model)


def _tools() -> EvidenceTools:
    return EvidenceTools(get_retriever())


@lru_cache(maxsize=1)
def get_auth_service() -> AuthService:
    return AuthService(settings)


bearer_auth = HTTPBearer(auto_error=False)


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_auth),
) -> UserRecord:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Sign in to continue")
    user = get_auth_service().authenticate(credentials.credentials)
    if user is None:
        raise HTTPException(status_code=401, detail="Session is invalid or expired")
    return user


def admin_user(user: UserRecord = Depends(current_user)) -> UserRecord:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required")
    return user


@lru_cache(maxsize=1)
def get_document_understanding() -> DocumentUnderstandingService:
    return DocumentUnderstandingService(settings)


def _owner_document_ids(user_id: str) -> list[str]:
    with get_auth_service().session_factory() as session:
        return list(session.scalars(select(UploadedDocumentRecord.document_id).where(
            UploadedDocumentRecord.owner_id == user_id,
        )).all())


def _scoped_tools(user: UserRecord) -> EvidenceTools:
    return EvidenceTools(get_retriever(), allowed_doc_ids=_owner_document_ids(user.user_id))


def _serialize_segment(segment: DocumentSegmentRecord) -> dict[str, Any]:
    return {
        "start_page": segment.start_page, "end_page": segment.end_page,
        "document_type": segment.document_type, "control_type": segment.control_type,
        "confidence": segment.confidence, "summary": segment.summary, "fields": segment.fields,
    }


def _serialize_document(
    document: UploadedDocumentRecord, segments: list[DocumentSegmentRecord] | None = None,
) -> dict[str, Any]:
    return {
        "segments": [_serialize_segment(item) for item in segments or []],
        "document_id": document.document_id,
        "original_name": document.original_name,
        "status": document.status,
        "document_type": document.document_type,
        "control_type": document.control_type,
        "confidence": document.classification_confidence,
        "fields": document.extracted_fields,
        "summary": document.extraction_summary,
        "page_count": document.page_count,
        "created_at": document.created_at.isoformat(),
    }


def _apply_matching_rules(session, document: UploadedDocumentRecord) -> list[dict[str, Any]]:
    rules = session.scalars(select(AuditRuleRecord).where(
        AuditRuleRecord.owner_id == document.owner_id,
        AuditRuleRecord.enabled.is_(True),
        AuditRuleRecord.control_type == document.control_type,
    )).all()
    flags = []
    for rule in rules:
        if rule.document_type not in {"*", document.document_type}:
            continue
        discrepancy = evaluate_rule(rule, document.extracted_fields)
        if discrepancy is None:
            continue
        finding = AuditFindingRecord(
            finding_id=str(uuid4()), document_id=document.document_id, rule_id=rule.rule_id,
            owner_id=document.owner_id, severity=rule.severity, message=discrepancy["message"],
            observed_value=discrepancy["observed_value"], expected_value=discrepancy["expected_value"],
        )
        session.add(finding)
        flags.append({"finding_id": finding.finding_id, **discrepancy})
    return flags


_finding_reviews: dict[str, dict[str, Any]] = {}


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "Tracepaper Reviewer API", "version": "0.1.0"}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy"}


@app.post("/api/v1/auth/login")
async def login(payload: LoginInput) -> dict[str, Any]:
    try:
        user, token, expires_at = get_auth_service().login(payload.email, payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return {"access_token": token, "token_type": "bearer", "expires_at": expires_at.isoformat(), "user": user}


@app.post("/api/v1/auth/accept-invite")
async def accept_invite(payload: InviteAcceptInput) -> dict[str, Any]:
    try:
        user = get_auth_service().accept_invite(payload.token, payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"user": user, "message": "Account created. Sign in to continue."}


@app.get("/api/v1/auth/me")
async def who_am_i(user: UserRecord = Depends(current_user)) -> dict[str, Any]:
    return {"user": public_user(user)}


@app.post("/api/v1/auth/logout")
async def logout(credentials: HTTPAuthorizationCredentials | None = Depends(bearer_auth)) -> dict[str, str]:
    if credentials:
        get_auth_service().logout(credentials.credentials)
    return {"status": "signed_out"}


@app.post("/api/v1/admin/invites")
async def create_invite(
    payload: InviteCreateInput, admin: UserRecord = Depends(admin_user)
) -> dict[str, Any]:
    try:
        invite, token = get_auth_service().create_invite(
            payload.email, payload.display_name, payload.role, admin.user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    invite["accept_url"] = f"/?invite={token}"
    return {"invite": invite}


@app.get("/config")
async def config() -> dict[str, Any]:
    return {
        "llm_provider": settings.llm_provider,
        "llm_model": settings.llm_model,
        "embeddings_model": settings.embeddings_model,
        "cache_enabled": settings.cache_enabled,
        "log_level": settings.log_level,
    }


@app.get("/api/v1/engagements")
async def engagements(user: UserRecord = Depends(current_user)) -> dict[str, Any]:
    return {
        "engagements": [{
            "engagement_id": "demo-sox-2026",
            "name": "Synthetic SOX Control Testing",
            "status": "ready",
            "controls": ["p2p_001", "uar_001", "jer_001"],
        }]
    }


@app.get("/api/v1/evidence/search")
async def search_evidence(
    q: str = Query(min_length=1), limit: int = Query(default=10, ge=1, le=100),
    user: UserRecord = Depends(current_user),
) -> dict[str, Any]:
    try:
        results = _scoped_tools(user).search_evidence(q, limit)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid evidence query: {exc}") from exc
    return {"query": q, "results": results}


@app.get("/api/v1/evidence/{doc_id}/pages/{page}")
async def fetch_page(
    doc_id: str, page: int, user: UserRecord = Depends(current_user)
) -> dict[str, Any]:
    if page < 1:
        raise HTTPException(status_code=422, detail="page must be at least 1")
    chunks = _scoped_tools(user).fetch_page(doc_id, page)
    if not chunks:
        raise HTTPException(status_code=404, detail="Document page not found")
    return {"doc_id": doc_id, "page": page, "chunks": chunks}


@app.post("/api/v1/documents/upload")
async def upload_document(
    upload: UploadFile = File(...), user: UserRecord = Depends(current_user),
) -> dict[str, Any]:
    original_name = Path(upload.filename or "upload").name
    suffix = Path(original_name).suffix.lower()
    if suffix not in {".pdf", ".csv", ".eml"}:
        raise HTTPException(status_code=415, detail="Supported formats are PDF, CSV, and EML")
    content = await upload.read(25 * 1024 * 1024 + 1)
    if len(content) > 25 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File exceeds the 25 MB upload limit")
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    document_id = str(uuid4())
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temporary:
            temporary.write(content)
            temp_path = Path(temporary.name)
        pages = DocumentExtractor().extract(temp_path)
        result = get_document_understanding().classify_and_extract(original_name, pages)
        chunks = chunk_pages(document_id, pages)
        if not chunks:
            raise ValueError("No text could be extracted from this file")

        retriever = get_retriever()
        coverage = sum(page.extraction_method == "text_layer" for page in pages) / len(pages)
        retriever.store.insert_document(document_id, result["document_type"], f"postgres://uploads/{document_id}", len(pages), coverage)
        retriever.store.insert_chunks(chunks)
        document = UploadedDocumentRecord(
            document_id=document_id, owner_id=user.user_id, original_name=original_name,
            file_content=content, media_type=upload.content_type or "application/octet-stream",
            file_size=len(content), status="classified", document_type=result["document_type"],
            control_type=result["control_type"], classification_confidence=float(result["confidence"]),
            extracted_fields=result["fields"], extraction_summary=result["summary"], page_count=len(pages),
        )
        with get_auth_service().session_factory() as session:
            session.add(document)
            session.flush()
            segment_records = [DocumentSegmentRecord(
                segment_id=str(uuid4()), document_id=document_id, start_page=item["start_page"],
                end_page=item["end_page"], document_type=item["document_type"],
                control_type=item["control_type"], confidence=float(item["confidence"]),
                summary=item["summary"], fields=item["fields"],
            ) for item in result.get("segments") or []]
            session.add_all(segment_records)
            flags = _apply_matching_rules(session, document)
            session.commit()
            serialized = _serialize_document(document, segment_records)
        return {"document": serialized, "flags": flags}
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=502, detail=f"Document understanding failed: {exc}") from exc
    finally:
        if temp_path is not None:
            try:
                os.unlink(temp_path)
            except OSError:
                pass


@app.get("/api/v1/documents")
async def list_documents(user: UserRecord = Depends(current_user)) -> dict[str, Any]:
    with get_auth_service().session_factory() as session:
        documents = session.scalars(select(UploadedDocumentRecord).where(
            UploadedDocumentRecord.owner_id == user.user_id,
        ).order_by(UploadedDocumentRecord.created_at.desc())).all()
        segments: dict[str, list[DocumentSegmentRecord]] = {}
        for segment in session.scalars(select(DocumentSegmentRecord).where(
            DocumentSegmentRecord.document_id.in_([item.document_id for item in documents]),
        ).order_by(DocumentSegmentRecord.start_page)).all():
            segments.setdefault(segment.document_id, []).append(segment)
        return {"documents": [_serialize_document(item, segments.get(item.document_id)) for item in documents]}


@app.get("/api/v1/classification-types")
async def list_classification_types(user: UserRecord = Depends(current_user)) -> dict[str, Any]:
    with get_auth_service().session_factory() as session:
        rows = session.scalars(select(ClassificationTypeRecord).where(
            ClassificationTypeRecord.enabled.is_(True),
        ).order_by(ClassificationTypeRecord.sort_order, ClassificationTypeRecord.value)).all()
        result: dict[str, list[dict[str, str]]] = {"control": [], "document": []}
        for row in rows:
            result.setdefault(row.category, []).append({"value": row.value, "label": row.label})
        return result


@app.get("/api/v1/documents/{document_id}/pages/{page}")
async def uploaded_document_page(
    document_id: str, page: int, user: UserRecord = Depends(current_user),
) -> dict[str, Any]:
    if document_id not in _owner_document_ids(user.user_id):
        raise HTTPException(status_code=404, detail="Document not found")
    chunks = _scoped_tools(user).fetch_page(document_id, page)
    if not chunks:
        raise HTTPException(status_code=404, detail="Page not found")
    return {"document_id": document_id, "page": page, "chunks": chunks}

@app.get("/api/v1/audit-rules")
async def list_audit_rules(user: UserRecord = Depends(current_user)) -> dict[str, Any]:
    with get_auth_service().session_factory() as session:
        rules = session.scalars(select(AuditRuleRecord).where(AuditRuleRecord.owner_id == user.user_id)).all()
        return {"rules": [{
            "rule_id": rule.rule_id, "name": rule.name, "description": rule.description,
            "control_type": rule.control_type, "document_type": rule.document_type,
            "field_name": rule.field_name, "operator": rule.operator,
            "expected_value": rule.expected_value, "severity": rule.severity, "enabled": rule.enabled,
        } for rule in rules]}


@app.post("/api/v1/audit-rules")
async def create_audit_rule(
    payload: AuditRuleInput, user: UserRecord = Depends(current_user),
) -> dict[str, Any]:
    if payload.operator not in SUPPORTED_OPERATORS:
        raise HTTPException(status_code=422, detail=f"Operator must be one of {sorted(SUPPORTED_OPERATORS)}")
    with get_auth_service().session_factory() as session:
        allowed_controls = set(session.scalars(select(ClassificationTypeRecord.value).where(
            ClassificationTypeRecord.category == "control",
            ClassificationTypeRecord.enabled.is_(True),
        )).all())
    if payload.control_type not in allowed_controls:
        raise HTTPException(status_code=422, detail="Unsupported control type")
    if payload.severity not in {"low", "medium", "high", "critical"}:
        raise HTTPException(status_code=422, detail="Severity must be low, medium, high, or critical")
    rule = AuditRuleRecord(rule_id=str(uuid4()), owner_id=user.user_id, **payload.model_dump())
    with get_auth_service().session_factory() as session:
        session.add(rule)
        documents = session.scalars(select(UploadedDocumentRecord).where(
            UploadedDocumentRecord.owner_id == user.user_id,
            UploadedDocumentRecord.control_type == payload.control_type,
        )).all()
        flags = []
        for document in documents:
            if payload.document_type not in {"*", document.document_type}:
                continue
            discrepancy = evaluate_rule(rule, document.extracted_fields)
            if discrepancy:
                finding = AuditFindingRecord(
                    finding_id=str(uuid4()), document_id=document.document_id, rule_id=rule.rule_id,
                    owner_id=user.user_id, severity=rule.severity, message=discrepancy["message"],
                    observed_value=discrepancy["observed_value"], expected_value=discrepancy["expected_value"],
                )
                session.add(finding)
                flags.append({"document_id": document.document_id, **discrepancy})
        session.commit()
    return {"rule_id": rule.rule_id, "flags_created": len(flags), "flags": flags}


@app.get("/api/v1/audit-findings")
async def list_audit_findings(user: UserRecord = Depends(current_user)) -> dict[str, Any]:
    with get_auth_service().session_factory() as session:
        findings = session.scalars(select(AuditFindingRecord).where(
            AuditFindingRecord.owner_id == user.user_id,
        ).order_by(AuditFindingRecord.created_at.desc())).all()
        return {"findings": [{
            "finding_id": finding.finding_id, "document_id": finding.document_id,
            "rule_id": finding.rule_id, "status": finding.status, "severity": finding.severity,
            "message": finding.message, "observed_value": finding.observed_value,
            "expected_value": finding.expected_value,
        } for finding in findings]}


@app.patch("/api/v1/audit-findings/{finding_id}")
async def update_audit_finding(
    finding_id: str, payload: FindingStatusInput, user: UserRecord = Depends(current_user),
) -> dict[str, Any]:
    if payload.status not in {"needs_review", "accepted", "dismissed"}:
        raise HTTPException(status_code=422, detail="Unsupported finding status")
    with get_auth_service().session_factory() as session:
        finding = session.scalar(select(AuditFindingRecord).where(
            AuditFindingRecord.finding_id == finding_id,
            AuditFindingRecord.owner_id == user.user_id,
        ))
        if finding is None:
            raise HTTPException(status_code=404, detail="Finding not found")
        finding.status = payload.status
        session.commit()
        return {"finding_id": finding.finding_id, "status": finding.status}


@app.patch("/api/v1/audit-rules/{rule_id}")
async def set_audit_rule_enabled(
    rule_id: str, enabled: bool, user: UserRecord = Depends(current_user),
) -> dict[str, Any]:
    with get_auth_service().session_factory() as session:
        rule = session.scalar(select(AuditRuleRecord).where(
            AuditRuleRecord.rule_id == rule_id,
            AuditRuleRecord.owner_id == user.user_id,
        ))
        if rule is None:
            raise HTTPException(status_code=404, detail="Audit rule not found")
        rule.enabled = enabled
        session.commit()
        return {"rule_id": rule.rule_id, "enabled": rule.enabled}

@app.post("/api/v1/agent/analyze")
async def analyze_with_agent(
    payload: AgentRequest, user: UserRecord = Depends(current_user)
) -> dict[str, Any]:
    """Run a control-testing task through the configured LLM agent."""
    try:
        agent = AgentLoop(create_llm_client(settings), _scoped_tools(user))
        finding = agent.run(payload.task)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {
        "finding": {
            "control_id": finding.control_id,
            "population_item_id": finding.population_item_id,
            "disposition": finding.disposition,
            "rationale": finding.rationale,
            "citations": list(finding.citations),
        },
        "provider": settings.llm_provider,
        "model": settings.llm_model,
    }


@app.post("/api/v1/findings/validate")
async def validate_finding(
    payload: FindingInput, user: UserRecord = Depends(current_user)
) -> dict[str, Any]:
    pipeline = EnforcementPipeline(_scoped_tools(user))
    try:
        finding = pipeline.validate_finding(payload.model_dump())
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finding_id = str(uuid4())
    result = {
        "valid": True,
        "finding_id": finding_id,
        "finding": {
            "control_id": finding.control_id,
            "population_item_id": finding.population_item_id,
            "disposition": finding.disposition,
            "rationale": finding.rationale,
            "citations": list(finding.citations),
        },
    }
    _finding_reviews[finding_id] = {**result["finding"], "owner_id": user.user_id, "status": "pending", "trace": [
        {"step": "validate_citations", "status": "passed"},
        {"step": "await_reviewer_decision", "status": "pending"},
    ]}
    return result


@app.get("/api/v1/findings/{finding_id}/trace")
async def finding_trace(finding_id: str, user: UserRecord = Depends(current_user)) -> dict[str, Any]:
    review = _finding_reviews.get(finding_id)
    if review is None or review["owner_id"] != user.user_id:
        raise HTTPException(status_code=404, detail="Finding not found")
    return {"finding_id": finding_id, "trace": review["trace"]}


async def _review_finding(
    finding_id: str, action: str, payload: ReviewAction, user: UserRecord
) -> dict[str, Any]:
    review = _finding_reviews.get(finding_id)
    if review is None or review["owner_id"] != user.user_id:
        raise HTTPException(status_code=404, detail="Finding not found")
    review["status"] = action
    review["reviewer"] = payload.reviewer
    review["note"] = payload.note
    review["trace"][-1] = {"step": "reviewer_decision", "status": action, "reviewer": payload.reviewer}
    return {"finding_id": finding_id, "status": action, "reviewer": payload.reviewer}


@app.post("/api/v1/findings/{finding_id}/accept")
async def accept_finding(
    finding_id: str, payload: ReviewAction, user: UserRecord = Depends(current_user)
) -> dict[str, Any]:
    return await _review_finding(finding_id, "accepted", payload, user)


@app.post("/api/v1/findings/{finding_id}/reject")
async def reject_finding(
    finding_id: str, payload: ReviewAction, user: UserRecord = Depends(current_user)
) -> dict[str, Any]:
    return await _review_finding(finding_id, "rejected", payload, user)


@app.post("/api/v1/findings/{finding_id}/rerun")
async def rerun_finding(
    finding_id: str, payload: ReviewAction, user: UserRecord = Depends(current_user)
) -> dict[str, Any]:
    result = await _review_finding(finding_id, "rerun_requested", payload, user)
    return {**result, "message": "Agent rerun queued for this finding"}
