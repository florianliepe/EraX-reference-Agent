from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal
from uuid import uuid4
from pydantic import BaseModel, Field


class Confidence(str, Enum):
    strong = "strong"
    weak = "weak"
    missing = "missing"


class ClaimMode(str, Enum):
    fact = "fact"
    planned = "planned"
    target = "target"
    actual = "actual"
    commercial = "commercial"
    inferred = "inferred"
    unknown = "unknown"


class Evidence(BaseModel):
    file_id: str
    source_file: str
    snippet: str
    page_or_sheet: str | None = None
    block_id: str | None = None


class Section(BaseModel):
    value: str = "Insufficient source evidence"
    confidence: Confidence = Confidence.missing
    evidence: list[Evidence] = Field(default_factory=list)
    edited: bool = False
    claim_mode: ClaimMode = ClaimMode.unknown
    semantic_type: str | None = None
    inference_basis: list[str] = Field(default_factory=list)


class KPI(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    name: str
    value: str
    confidence: Confidence = Confidence.weak
    evidence: list[Evidence] = Field(default_factory=list)
    edited: bool = False
    status: Literal["achieved", "target", "forecast", "unknown"] = "unknown"


class CommercialMetric(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    name: str
    value: str
    evidence: list[Evidence] = Field(default_factory=list)
    internal_only: bool = True


class ReferenceDraft(BaseModel):
    reference_status: Literal["planned", "in_delivery", "completed", "unknown"] = "unknown"
    title: Section = Field(default_factory=Section)
    client: Section = Field(default_factory=Section)
    supplier: Section = Field(default_factory=Section)
    project_id: Section = Field(default_factory=Section)
    date: Section = Field(default_factory=Section)
    industry: Section = Field(default_factory=Section)
    service: Section = Field(default_factory=Section)
    situation_challenge: Section = Field(default_factory=Section)
    approach: Section = Field(default_factory=Section)
    outcome_impact: Section = Field(default_factory=Section)
    kpis: list[KPI] = Field(default_factory=list)
    commercial_metrics: list[CommercialMetric] = Field(default_factory=list)


class FileRecord(BaseModel):
    id: str
    name: str
    path: str
    size: int
    status: str = "uploaded"
    error: str | None = None


class JobRecord(BaseModel):
    id: str
    session_id: str
    status: str = "queued"
    progress: int = 0
    stage: str = "Queued"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
    classification: str = "public"
    result: ReferenceDraft | None = None
    output_path: str | None = None
    error: str | None = None
    workflow_artifacts: dict = Field(default_factory=dict)
    publication: dict | None = None
