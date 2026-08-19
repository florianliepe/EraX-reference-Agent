from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


class EvidenceUnit(BaseModel):
    id: str
    file_id: str
    source_file: str
    locator: str | None = None
    original_text: str
    normalized_text: str
    translated_text: str | None = None
    source_language: str = "und"
    classification: str = "public"
    confidence: float = 1.0
    warnings: list[str] = Field(default_factory=list)


class EntityCandidate(BaseModel):
    id: str
    type: str
    name: str
    aliases: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = 0.5
    ambiguous: bool = False


class NormalizedMetric(BaseModel):
    id: str
    name: str
    original_value: str
    numeric_value: float | None = None
    unit: str | None = None
    currency: str | None = None
    baseline: str | None = None
    target: str | None = None
    achieved: str | None = None
    period: str | None = None
    scope: str | None = None
    status: Literal["achieved", "target", "forecast", "commercial", "unknown"] = "unknown"
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = 0.5


class Claim(BaseModel):
    id: str
    section: str
    text: str
    status: Literal["supported", "disputed", "missing-context", "superseded", "rejected"]
    confidence: float = 0.5
    evidence_ids: list[str] = Field(default_factory=list)
    contradicting_evidence_ids: list[str] = Field(default_factory=list)


class ClaimLedger(BaseModel):
    claims: list[Claim] = Field(default_factory=list)


class RetrievalQuery(BaseModel):
    purpose: str
    query: str
    section: str | None = None
    top: int = 5


class RetrievedKnowledge(BaseModel):
    id: str
    content: str
    project_id: str | None = None
    section: str | None = None
    score: float | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class VerificationDefect(BaseModel):
    section: str
    assertion: str
    verdict: Literal["fail", "needs-human"]
    severity: Literal["low", "medium", "high"] = "high"
    evidence_ids: list[str] = Field(default_factory=list)
    repair: str


class VerificationReport(BaseModel):
    status: Literal["pass", "fail", "needs-human"] = "fail"
    defects: list[VerificationDefect] = Field(default_factory=list)


class AgentTrace(BaseModel):
    stage: str
    status: Literal["completed", "fallback", "failed"]
    model: str
    prompt_version: str
    error: str | None = None


class WorkflowArtifacts(BaseModel):
    evidence_units: list[EvidenceUnit] = Field(default_factory=list)
    entities: list[EntityCandidate] = Field(default_factory=list)
    metrics: list[NormalizedMetric] = Field(default_factory=list)
    retrieval_queries: list[RetrievalQuery] = Field(default_factory=list)
    retrieved_knowledge: list[RetrievedKnowledge] = Field(default_factory=list)
    claim_ledger: ClaimLedger = Field(default_factory=ClaimLedger)
    verification: VerificationReport = Field(default_factory=VerificationReport)
    traces: list[AgentTrace] = Field(default_factory=list)


class PublicationRecord(BaseModel):
    approved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    approved_by: str
    reuse_allowed: bool
    bundle_path: str
    blob_url: str | None = None
    search_documents: int = 0
    status: Literal["local", "published", "partial"] = "local"
    error: str | None = None


class JsonLdBundle(BaseModel):
    context: dict[str, Any] = Field(alias="@context")
    graph: list[dict[str, Any]] = Field(alias="@graph")

    model_config = {"populate_by_name": True}
