from __future__ import annotations

import hashlib
import json
from typing import Any

from . import agent_prompts
from .config import settings
from .knowledge_models import (
    AgentTrace,
    Claim,
    ClaimLedger,
    EntityCandidate,
    EvidenceUnit,
    NormalizedMetric,
    RetrievalQuery,
    VerificationReport,
    WorkflowArtifacts,
)
from .knowledge_store import AzureKnowledgeStore
from .models import Confidence, ReferenceDraft
from .structuring import KPI_LIMIT, LIMITS, SourceChunk, compact


def _stable_id(prefix: str, value: str) -> str:
    return f"{prefix}_{hashlib.sha256(value.encode()).hexdigest()[:20]}"


def _agent_call(stage: str, prompt: str, payload: dict[str, Any], traces: list[AgentTrace]) -> dict[str, Any] | None:
    if not settings.agentic_workflow_enabled or settings.llm_provider != "openai" or not settings.openai_api_key:
        traces.append(AgentTrace(
            stage=stage,
            status="fallback",
            model="deterministic-v1",
            prompt_version=agent_prompts.PROMPT_VERSION,
        ))
        return None
    try:
        from openai import OpenAI

        client = OpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            timeout=45,
        )
        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or "{}"
        result = json.loads(content)
        traces.append(AgentTrace(
            stage=stage,
            status="completed",
            model=settings.openai_model,
            prompt_version=agent_prompts.PROMPT_VERSION,
        ))
        return result
    except Exception as exc:
        traces.append(AgentTrace(
            stage=stage,
            status="fallback",
            model=settings.openai_model,
            prompt_version=agent_prompts.PROMPT_VERSION,
            error=f"{type(exc).__name__}: {str(exc)[:240]}",
        ))
        return None


def _build_evidence(chunks: list[SourceChunk], classification: str) -> list[EvidenceUnit]:
    units: list[EvidenceUnit] = []
    for item in chunks:
        identity = f"{item.file_id}:{item.chunk.location}:{item.chunk.text}"
        units.append(EvidenceUnit(
            id=_stable_id("ev", identity),
            file_id=item.file_id,
            source_file=item.source_file,
            locator=item.chunk.location,
            original_text=item.chunk.text,
            normalized_text=item.chunk.text,
            classification=classification,
        ))
    return units


def _evidence_id_for(units: list[EvidenceUnit], source_file: str, locator: str | None, snippet: str) -> str | None:
    exact = next((unit for unit in units if unit.source_file == source_file and unit.locator == locator), None)
    if exact:
        return exact.id
    return next((unit.id for unit in units if unit.source_file == source_file and snippet[:80] in unit.original_text), None)


def _curate(units: list[EvidenceUnit], traces: list[AgentTrace]) -> list[EvidenceUnit]:
    payload_units = [{
        "id": unit.id,
        "source_file": unit.source_file,
        "locator": unit.locator,
        "text": unit.original_text[:1600],
    } for unit in units[:80]]
    response = _agent_call(
        "evidence-curator",
        agent_prompts.CURATOR,
        {"canonical_language": settings.canonical_language, "units": payload_units},
        traces,
    )
    if not response:
        return units
    by_id = {unit.id: unit for unit in units}
    for item in response.get("units", []):
        unit = by_id.get(item.get("id", ""))
        if not unit:
            continue
        unit.normalized_text = str(item.get("normalized_text") or unit.original_text)[:4000]
        translated = item.get("translated_text")
        unit.translated_text = str(translated)[:4000] if translated else None
        unit.source_language = str(item.get("source_language") or "und")[:12]
        try:
            unit.confidence = min(max(float(item.get("confidence", 1.0)), 0), 1)
        except (TypeError, ValueError):
            unit.confidence = 1.0
        unit.warnings = [str(value)[:240] for value in item.get("warnings", [])[:5]]
    return units


def _default_entities(draft: ReferenceDraft, units: list[EvidenceUnit]) -> list[EntityCandidate]:
    results = []
    for field, entity_type in (("client", "Organization"), ("service", "Service"), ("industry", "Industry")):
        section = getattr(draft, field)
        if section.confidence == Confidence.missing:
            continue
        evidence_ids = [
            value for ev in section.evidence
            if (value := _evidence_id_for(units, ev.source_file, ev.page_or_sheet, ev.snippet))
        ]
        results.append(EntityCandidate(
            id=_stable_id("entity", f"{entity_type}:{section.value.casefold()}"),
            type=entity_type,
            name=section.value,
            evidence_ids=evidence_ids,
            confidence=0.9 if section.confidence == Confidence.strong else 0.65,
        ))
    return results


def _default_metrics(draft: ReferenceDraft, units: list[EvidenceUnit]) -> list[NormalizedMetric]:
    results = []
    for metric in draft.kpis[:KPI_LIMIT]:
        evidence_ids = [
            value for ev in metric.evidence
            if (value := _evidence_id_for(units, ev.source_file, ev.page_or_sheet, ev.snippet))
        ]
        results.append(NormalizedMetric(
            id=metric.id,
            name=metric.name,
            original_value=metric.value,
            status="commercial" if any(term in metric.name.casefold() for term in ("revenue", "budget")) else "unknown",
            evidence_ids=evidence_ids,
            confidence=0.9 if metric.confidence == Confidence.strong else 0.65,
        ))
    return results


def _link(
    draft: ReferenceDraft,
    units: list[EvidenceUnit],
    traces: list[AgentTrace],
) -> tuple[list[EntityCandidate], list[NormalizedMetric]]:
    entities = _default_entities(draft, units)
    metrics = _default_metrics(draft, units)
    response = _agent_call(
        "entity-metric-linker",
        agent_prompts.LINKER,
        {
            "evidence": [unit.model_dump() for unit in units[:80]],
            "deterministic_entities": [item.model_dump() for item in entities],
            "deterministic_metrics": [item.model_dump() for item in metrics],
        },
        traces,
    )
    if not response:
        return entities, metrics
    valid_ids = {unit.id for unit in units}
    try:
        proposed_entities = [EntityCandidate.model_validate(item) for item in response.get("entities", [])]
        proposed_metrics = [NormalizedMetric.model_validate(item) for item in response.get("metrics", [])]
        proposed_entities = [item for item in proposed_entities if item.evidence_ids and set(item.evidence_ids) <= valid_ids]
        proposed_metrics = [item for item in proposed_metrics if item.evidence_ids and set(item.evidence_ids) <= valid_ids]
        return proposed_entities or entities, proposed_metrics or metrics
    except Exception:
        return entities, metrics


def _default_claims(draft: ReferenceDraft, units: list[EvidenceUnit]) -> ClaimLedger:
    claims: list[Claim] = []
    for section_name in LIMITS:
        section = getattr(draft, section_name)
        if section.confidence == Confidence.missing:
            continue
        evidence_ids = [
            value for ev in section.evidence
            if (value := _evidence_id_for(units, ev.source_file, ev.page_or_sheet, ev.snippet))
        ]
        if not evidence_ids:
            continue
        claims.append(Claim(
            id=_stable_id("claim", f"{section_name}:{section.value}"),
            section=section_name,
            text=section.value,
            status="supported",
            confidence=0.9 if section.confidence == Confidence.strong else 0.65,
            evidence_ids=evidence_ids,
        ))
    return ClaimLedger(claims=claims)


def _plan_and_retrieve(
    draft: ReferenceDraft,
    units: list[EvidenceUnit],
    classification: str,
    project_id: str,
    traces: list[AgentTrace],
) -> tuple[list[RetrievalQuery], list]:
    response = _agent_call(
        "retrieval-planner",
        agent_prompts.RETRIEVAL_PLANNER,
        {
            "canonical_fields": {name: getattr(draft, name).model_dump() for name in LIMITS},
            "available_evidence": [{"id": u.id, "text": (u.translated_text or u.normalized_text)[:700]} for u in units[:80]],
            "cross_project_reuse": settings.cross_project_reuse_enabled,
            "external_web_enrichment": False,
        },
        traces,
    )
    queries: list[RetrievalQuery] = []
    if response:
        for item in response.get("queries", [])[:8]:
            try:
                queries.append(RetrievalQuery.model_validate(item))
            except Exception:
                continue
    retrieved = []
    if settings.cross_project_reuse_enabled and queries:
        store = AzureKnowledgeStore()
        for query in queries:
            try:
                retrieved.extend(store.query_approved(query.query, classification, project_id, query.top))
            except Exception as exc:
                traces.append(AgentTrace(
                    stage="azure-search-retrieval",
                    status="fallback",
                    model="azure-ai-search",
                    prompt_version=agent_prompts.PROMPT_VERSION,
                    error=f"{type(exc).__name__}: {str(exc)[:240]}",
                ))
                break
    return queries, retrieved


def _aggregate(
    draft: ReferenceDraft,
    units: list[EvidenceUnit],
    metrics: list[NormalizedMetric],
    retrieved: list,
    traces: list[AgentTrace],
) -> ClaimLedger:
    baseline = _default_claims(draft, units)
    response = _agent_call(
        "claim-aggregator",
        agent_prompts.AGGREGATOR,
        {
            "evidence": [unit.model_dump() for unit in units[:80]],
            "metrics": [item.model_dump() for item in metrics],
            "approved_retrieved_knowledge": [item.model_dump() for item in retrieved[:20]],
            "baseline_claims": baseline.model_dump(),
        },
        traces,
    )
    if not response:
        return baseline
    valid_evidence = {unit.id for unit in units}
    retrieved_ids = {item.id for item in retrieved}
    claims: list[Claim] = []
    for item in response.get("claims", [])[:30]:
        try:
            claim = Claim.model_validate(item)
        except Exception:
            continue
        cited = set(claim.evidence_ids)
        if claim.status == "supported" and cited and cited <= (valid_evidence | retrieved_ids):
            claims.append(claim)
        elif claim.status != "supported":
            claims.append(claim)
    return ClaimLedger(claims=claims or baseline.claims)


def _write(
    original: ReferenceDraft,
    ledger: ClaimLedger,
    traces: list[AgentTrace],
) -> tuple[ReferenceDraft, dict[str, list[str]]]:
    response = _agent_call(
        "reference-writer",
        agent_prompts.WRITER,
        {
            "claims": ledger.model_dump(),
            "original_draft": {name: getattr(original, name).model_dump() for name in LIMITS},
            "limits": LIMITS,
            "output_language": settings.canonical_language,
        },
        traces,
    )
    if not response:
        return original.model_copy(deep=True), {}
    supported = {claim.id: claim for claim in ledger.claims if claim.status == "supported"}
    result = original.model_copy(deep=True)
    mappings: dict[str, list[str]] = {}
    for name in LIMITS:
        section = getattr(result, name)
        if section.confidence == Confidence.missing:
            section.value = "Insufficient source evidence"
            continue
        proposed = response.get("fields", {}).get(name, {})
        claim_ids = [str(value) for value in proposed.get("claim_ids", [])]
        if not claim_ids or any(value not in supported or supported[value].section != name for value in claim_ids):
            continue
        section.value = compact(str(proposed.get("value") or section.value), LIMITS[name])
        mappings[name] = claim_ids
    return result, mappings


def _verify(
    draft: ReferenceDraft,
    original: ReferenceDraft,
    ledger: ClaimLedger,
    mappings: dict[str, list[str]],
    units: list[EvidenceUnit],
    traces: list[AgentTrace],
) -> tuple[ReferenceDraft, VerificationReport]:
    response = _agent_call(
        "grounding-verifier",
        agent_prompts.VERIFIER,
        {
            "draft": {name: {"value": getattr(draft, name).value, "claim_ids": mappings.get(name, [])} for name in LIMITS},
            "claims": ledger.model_dump(),
            "evidence": [unit.model_dump() for unit in units[:80]],
            "limits": LIMITS,
        },
        traces,
    )
    if not response:
        return original.model_copy(deep=True), VerificationReport(status="pass")
    try:
        report = VerificationReport.model_validate(response)
    except Exception:
        return original.model_copy(deep=True), VerificationReport(status="fail")
    if report.status != "pass":
        return original.model_copy(deep=True), report
    return draft, report


def run_agentic_workflow(
    draft: ReferenceDraft,
    chunks: list[SourceChunk],
    classification: str,
    project_id: str,
) -> tuple[ReferenceDraft, str, WorkflowArtifacts]:
    traces: list[AgentTrace] = []
    units = _curate(_build_evidence(chunks, classification), traces)
    entities, metrics = _link(draft, units, traces)
    queries, retrieved = _plan_and_retrieve(draft, units, classification, project_id, traces)
    ledger = _aggregate(draft, units, metrics, retrieved, traces)
    written, mappings = _write(draft, ledger, traces)
    verified, verification = _verify(written, draft, ledger, mappings, units, traces)
    artifacts = WorkflowArtifacts(
        evidence_units=units,
        entities=entities,
        metrics=metrics,
        retrieval_queries=queries,
        retrieved_knowledge=retrieved,
        claim_ledger=ledger,
        verification=verification,
        traces=traces,
    )
    model_version = f"agentic:{settings.openai_model}:{agent_prompts.PROMPT_VERSION}" if settings.agentic_workflow_enabled else "deterministic-v1"
    return verified, model_version, artifacts
