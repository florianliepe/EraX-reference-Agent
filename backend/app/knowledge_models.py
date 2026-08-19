from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


class DocumentBlock(BaseModel):
    id: str
    file_id: str
    source_file: str
    page: int | None = None
    bbox: tuple[float, float, float, float] | None = None
    block_type: Literal[
        "title", "heading", "paragraph", "list_item", "table", "table_row",
        "header", "footer", "signature",
    ] = "paragraph"
    heading_path: list[str] = Field(default_factory=list)
    original_text: str
    normalized_text: str
    language: str = "und"
    font_size: float | None = None
    is_bold: bool = False
    reading_order: int = 0
    repeated: bool = False
    parser: str = "local"
    classification: str = "public"


class DocumentProfile(BaseModel):
    document_type: Literal[
        "offer", "statement_of_work", "status_report", "final_report",
        "presentation", "commercial_calculation", "mixed", "unknown",
    ] = "unknown"
    source_language: str = "und"
    project_phase: Literal["proposal", "planned", "in_delivery", "completed", "unknown"] = "unknown"
    confidence: float = 0.5
    evidence_block_ids: list[str] = Field(default_factory=list)


class FieldCandidate(BaseModel):
    field: str
    value: str
    semantic_type: str = "unknown"
    claim_mode: Literal["fact", "planned", "target", "actual", "commercial", "inferred", "unknown"] = "unknown"
    evidence_block_ids: list[str] = Field(default_factory=list)
    structural_score: float = 0
    lexical_score: float = 0
    semantic_score: float = 0
    combined_score: float = 0
    warnings: list[str] = Field(default_factory=list)


class AggregatedField(BaseModel):
    field: str
    value: str
    confidence: float = 0.5
    claim_mode: Literal["fact", "planned", "target", "actual", "commercial", "inferred", "unknown"] = "unknown"
    evidence_block_ids: list[str] = Field(default_factory=list)
    inference_basis: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    missing_reason: str | None = None


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
    page: int | None = None
    bbox: tuple[float, float, float, float] | None = None
    block_type: str = "paragraph"
    heading_path: list[str] = Field(default_factory=list)
    parser: str = "local"
    repeated: bool = False


class EntityCandidate(BaseModel):
    id: str
    type: str
    name: str
    aliases: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = 0.5
    ambiguous: bool = False
    role: str | None = None


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
    claim_mode: Literal["fact", "planned", "target", "actual", "commercial", "inferred", "unknown"] = "unknown"


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
    document_profiles: list[DocumentProfile] = Field(default_factory=list)
    document_blocks: list[DocumentBlock] = Field(default_factory=list)
    field_candidates: list[FieldCandidate] = Field(default_factory=list)
    aggregated_fields: list[AggregatedField] = Field(default_factory=list)
    excluded_block_ids: list[str] = Field(default_factory=list)
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
