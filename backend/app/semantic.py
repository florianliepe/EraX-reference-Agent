from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from .knowledge_models import AggregatedField, DocumentBlock, DocumentProfile, FieldCandidate
from .models import ClaimMode, CommercialMetric, Confidence, Evidence, KPI, ReferenceDraft, Section
from .parsers import Chunk


LIMITS = {
    "title": 90, "client": 55, "date": 30, "industry": 45, "service": 55,
    "situation_challenge": 360, "approach": 360, "outcome_impact": 320,
}
KPI_LIMIT = 6
KPI_NAME_LIMIT = 48
KPI_VALUE_LIMIT = 48
MISSING = "Insufficient source evidence"
OUTCOME_REQUIRED = "Outcome evidence required"

FIELD_TERMS = {
    "title": ("project title", "project", "projekt", "reference", "referenz"),
    "client": ("client", "customer", "kunde", "auftraggeber", "recipient"),
    "date": ("duration", "date", "year", "projektlaufzeit", "laufzeit", "datum"),
    "industry": ("industry", "sector", "branche", "industrie"),
    "service": ("service", "capability", "offering", "leistung", "gewerk"),
    "situation_challenge": ("challenge", "situation", "problem", "context", "need", "ausgangslage", "herausforderung", "bedarf"),
    "approach": ("approach", "solution", "implemented", "delivered", "method", "leistungsbeschreibung", "liefergegenstand", "vorgehen", "umsetzung"),
    "outcome_impact": ("outcome", "impact", "result", "benefit", "improved", "reduced", "increased", "ergebnis", "wirkung", "verbessert", "reduziert", "erreicht"),
}
BOILERPLATE_TERMS = (
    "geschäftsführer:", "amtsgericht", "ust-idnr", "iban", "swift/bic",
    "arbeitnehmerüberlassungsgesetz", "vertragsparteien", "personalhoheit",
)
ACTUAL_TERMS = (
    "achieved", "delivered", "implemented", "completed", "reduced", "increased",
    "erreicht", "umgesetzt", "abgeschlossen", "reduziert", "gesteigert",
)
PLANNED_TERMS = (
    "planned", "proposed", "offer", "shall", "will", "geplant", "angebot",
    "liefergegenstand", "wird", "soll", "zu erstellen", "umsetzung der geplanten",
)
ORG_PATTERN = re.compile(
    r"\b([A-ZÄÖÜ][\wÄÖÜäöüß&.,' -]{1,80}?\s(?:AG|GmbH|SE|KG|Inc\.?|Ltd\.?|LLC|Corporation))\b"
)
DATE_PATTERN = re.compile(r"\b(\d{1,2}[./]\d{1,2}[./]\d{4})\b")
METRIC_PATTERN = re.compile(
    r"(?:(?:EUR|USD|CHF|GBP|€|\$|£)\s*\d[\d.,]*(?:\s*(?:million|billion|mio\.?|bn|m|k)\b)?"
    r"|\d[\d.,]*\s*(?:EUR|USD|CHF|GBP)"
    r"|\d+(?:[.,]\d+)?\s*(?:%|percent\b|per cent\b|prozent\b|FTEs?\b|tage?\b|days?\b|x\b))",
    re.I,
)
INDUSTRY_MAP = {
    "mercedes-benz ag": "Automotive",
    "mercedes benz ag": "Automotive",
    "contoso energy": "Energy",
    "muster mobility ag": "Automotive",
}


@dataclass
class SourceChunk:
    file_id: str
    source_file: str
    chunk: Chunk


@dataclass
class SemanticAnalysis:
    draft: ReferenceDraft
    profiles: list[DocumentProfile]
    blocks: list[DocumentBlock]
    candidates: list[FieldCandidate]
    aggregated: list[AggregatedField]
    excluded_block_ids: list[str]


def compact(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", text).strip(" •-\t")
    if len(text) <= limit:
        return text
    shortened = text[: limit - 1].rsplit(" ", 1)[0]
    return shortened.rstrip(".,;:") + "…"


def stable_block_id(item: SourceChunk) -> str:
    raw = f"{item.file_id}:{item.chunk.location}:{item.chunk.text}"
    return f"block_{hashlib.sha256(raw.encode()).hexdigest()[:20]}"


def _language(text: str) -> str:
    lowered = f" {text.casefold()} "
    de = sum(lowered.count(f" {word} ") for word in ("der", "die", "das", "und", "für", "projekt", "angebot"))
    en = sum(lowered.count(f" {word} ") for word in ("the", "and", "for", "project", "offer", "client"))
    return "de" if de > en else "en" if en else "und"


def build_blocks(chunks: list[SourceChunk], classification: str = "public") -> list[DocumentBlock]:
    results: list[DocumentBlock] = []
    for order, item in enumerate(chunks):
        chunk = item.chunk
        results.append(DocumentBlock(
            id=stable_block_id(item), file_id=item.file_id, source_file=item.source_file,
            page=chunk.page, bbox=chunk.bbox,
            block_type=chunk.block_type if chunk.block_type in {
                "title", "heading", "paragraph", "list_item", "table", "table_row",
                "header", "footer", "signature",
            } else "paragraph",
            heading_path=list(chunk.heading_path), original_text=chunk.text,
            normalized_text=re.sub(r"\s+", " ", chunk.text).strip(), language=_language(chunk.text),
            font_size=chunk.font_size, is_bold=chunk.is_bold, reading_order=order,
            repeated=chunk.repeated, parser=chunk.parser, classification=classification,
        ))
    return results


def profile_document(blocks: list[DocumentBlock]) -> DocumentProfile:
    usable = [block for block in blocks if not block.repeated and block.block_type not in {"header", "footer"}]
    joined = " ".join(block.normalized_text for block in usable).casefold()
    offer_hits = sum(term in joined for term in ("angebot", "offer", "proposal", "kommerzielles angebot"))
    status_hits = sum(term in joined for term in ("status report", "statusbericht", "cutover status"))
    final_hits = sum(term in joined for term in ("abschlussbericht", "final report", "project closure"))
    if offer_hits:
        document_type, phase, confidence = "offer", "planned", 0.96
    elif final_hits:
        document_type, phase, confidence = "final_report", "completed", 0.9
    elif status_hits:
        document_type, phase, confidence = "status_report", "in_delivery", 0.85
    else:
        document_type, phase, confidence = "unknown", "unknown", 0.5
    evidence = [block.id for block in usable if any(term in block.normalized_text.casefold() for term in ("angebot", "offer", "status", "abschluss"))][:5]
    return DocumentProfile(
        document_type=document_type, project_phase=phase, source_language=_language(joined),
        confidence=confidence, evidence_block_ids=evidence,
    )


def _is_boilerplate(block: DocumentBlock) -> bool:
    lowered = block.normalized_text.casefold()
    return block.repeated or block.block_type in {"header", "footer", "signature"} or any(term in lowered for term in BOILERPLATE_TERMS)


def _score_block(field: str, block: DocumentBlock, profile: DocumentProfile) -> tuple[float, float, float, float]:
    lowered = block.normalized_text.casefold()
    lexical = min(1.0, sum(term in lowered for term in FIELD_TERMS.get(field, ())) / 2)
    structural = 0.0
    if block.block_type in {"title", "heading"}:
        structural += 0.35
    if block.page == 1 and field in {"title", "client"}:
        structural += 0.3
    if field == "approach" and any("leistungsbeschreibung" in value.casefold() for value in block.heading_path):
        structural += 0.5
    if field == "date" and "projektlaufzeit" in lowered:
        structural += 0.7
    if _is_boilerplate(block):
        structural -= 1.0
    semantic = lexical
    compatibility = 1.0 if profile.document_type == "offer" and field in {"title", "client", "date", "approach", "service"} else 0.5
    combined = 0.4 * structural + 0.25 * lexical + 0.25 * semantic + 0.1 * compatibility
    return structural, lexical, semantic, combined


def _candidate(field: str, value: str, block: DocumentBlock, profile: DocumentProfile, semantic_type: str, mode: str) -> FieldCandidate:
    structural, lexical, semantic, combined = _score_block(field, block, profile)
    if semantic_type in {"recipient_organization", "supplier_organization", "project_title", "offer_or_project_id"}:
        structural += 0.45
        combined += 0.3
    return FieldCandidate(
        field=field, value=compact(value, LIMITS.get(field, 360)), semantic_type=semantic_type,
        claim_mode=mode, evidence_block_ids=[block.id], structural_score=round(structural, 4),
        lexical_score=round(lexical, 4), semantic_score=round(semantic, 4), combined_score=round(combined, 4),
    )


def _label_value(text: str, labels: Iterable[str]) -> str | None:
    for label in labels:
        match = re.search(rf"(?:^|\n)\s*{re.escape(label)}\s*[:\-]\s*([^\n]+)", text, re.I)
        if match:
            return match.group(1).strip()
    return None


def _format_project_period(text: str) -> str | None:
    if not re.search(r"projektlaufzeit|project duration|project period", text, re.I):
        return None
    values = DATE_PATTERN.findall(text)
    if len(values) < 2:
        return None
    parsed = []
    for value in values[:2]:
        try:
            parsed.append(datetime.strptime(value.replace("/", "."), "%d.%m.%Y"))
        except ValueError:
            return f"{values[0]}-{values[1]}"
    if parsed[0].year == parsed[1].year:
        return f"{parsed[0].strftime('%d %b')}-{parsed[1].strftime('%d %b %Y')}"
    return f"{parsed[0].strftime('%d %b %Y')}-{parsed[1].strftime('%d %b %Y')}"


def retrieve_field_candidates(blocks: list[DocumentBlock], profile: DocumentProfile) -> list[FieldCandidate]:
    usable = [block for block in blocks if not _is_boilerplate(block)]
    candidates: list[FieldCandidate] = []
    for block in usable:
        title = _label_value(block.original_text, ("Project title", "Project", "Projekt"))
        if title and not re.match(r"laufzeit\b", title, re.I):
            candidates.append(_candidate("title", title, block, profile, "project_title", "planned" if profile.project_phase == "planned" else "fact"))
        client = _label_value(block.original_text, ("Client", "Customer", "Kunde", "Auftraggeber"))
        if client:
            candidates.append(_candidate("client", client, block, profile, "client_organization", "fact"))
        for organization in ORG_PATTERN.findall(block.original_text):
            clean = re.sub(r"\s+", " ", organization).strip(" ,.-")
            if "eraneos" in clean.casefold() or re.search(r"lieferantennummer|supplier number", block.original_text, re.I):
                candidates.append(_candidate("supplier", clean, block, profile, "supplier_organization", "fact"))
            elif block.page in {None, 1}:
                candidates.append(_candidate("client", clean, block, profile, "recipient_organization", "fact"))
        project_id = _label_value(block.original_text, ("Angebot", "Offer", "Projekt-ID", "Project ID"))
        if project_id and re.search(r"\d", project_id):
            candidates.append(_candidate("project_id", project_id, block, profile, "offer_or_project_id", "fact"))
        period = _format_project_period(block.original_text)
        if period:
            candidates.append(_candidate("date", period, block, profile, "planned_project_duration", "planned"))
        for field, labels in (
            ("situation_challenge", ("Challenge", "Situation", "Ausgangslage", "Herausforderung")),
            ("approach", ("Approach", "Solution", "Vorgehen", "Lösung")),
            ("outcome_impact", ("Outcome", "Impact", "Result", "Ergebnis", "Wirkung")),
            ("service", ("Service", "Leistung", "Gewerk")),
            ("industry", ("Industry", "Branche", "Industrie")),
        ):
            value = _label_value(block.original_text, labels)
            if value:
                mode = "actual" if field == "outcome_impact" else "planned" if profile.project_phase == "planned" and field in {"approach", "service"} else "fact"
                candidates.append(_candidate(field, value, block, profile, field, mode))
        if any("leistungsbeschreibung" in heading.casefold() for heading in block.heading_path) and block.block_type in {"paragraph", "list_item"}:
            if not any(term in block.normalized_text.casefold() for term in ("zusammenarbeitsmodell", "vertragsparteien")):
                candidates.append(_candidate("approach", block.normalized_text, block, profile, "planned_deliverable", "planned"))
        lowered = block.normalized_text.casefold()
        if any(term in lowered for term in ACTUAL_TERMS) and not any(term in lowered for term in PLANNED_TERMS):
            if any(term in lowered for term in FIELD_TERMS["outcome_impact"]):
                candidates.append(_candidate("outcome_impact", block.normalized_text, block, profile, "achieved_outcome", "actual"))
    best_client = max((item for item in candidates if item.field == "client"), key=lambda item: item.combined_score, default=None)
    best_title = max((item for item in candidates if item.field == "title"), key=lambda item: item.combined_score, default=None)
    if best_title:
        lowered_title = best_title.value.casefold()
        service_terms = []
        if "datacenter" in lowered_title or "data center" in lowered_title:
            service_terms.append("Data center transformation")
        if "cutover" in lowered_title or "migration" in lowered_title:
            service_terms.append("application migration")
        if "hypercare" in lowered_title:
            service_terms.append("hypercare")
        if service_terms:
            candidates.append(FieldCandidate(
                field="service", value=", ".join(dict.fromkeys(service_terms)),
                semantic_type="service_from_project_title", claim_mode="planned" if profile.project_phase == "planned" else "fact",
                evidence_block_ids=best_title.evidence_block_ids, structural_score=0.8,
                lexical_score=0.8, semantic_score=0.85, combined_score=0.81,
            ))
    if best_client:
        industry = INDUSTRY_MAP.get(best_client.value.casefold())
        if industry:
            candidates.append(FieldCandidate(
                field="industry", value=industry, semantic_type="controlled_company_industry_mapping",
                claim_mode="inferred", evidence_block_ids=best_client.evidence_block_ids,
                structural_score=0.5, lexical_score=0, semantic_score=0.75, combined_score=0.65,
                warnings=[f"Inferred from curated mapping for {best_client.value}"],
            ))
    return candidates


def _evidence(blocks: dict[str, DocumentBlock], ids: list[str]) -> list[Evidence]:
    return [Evidence(
        file_id=blocks[value].file_id, source_file=blocks[value].source_file,
        snippet=compact(blocks[value].original_text, 300),
        page_or_sheet=f"page {blocks[value].page}" if blocks[value].page else None,
        block_id=value,
    ) for value in ids if value in blocks]


def _aggregate_field(
    field: str,
    items: list[FieldCandidate],
    profile: DocumentProfile,
    blocks: dict[str, DocumentBlock],
) -> AggregatedField:
    ranked = sorted(items, key=lambda item: item.combined_score, reverse=True)
    if field == "outcome_impact" and profile.project_phase == "planned" and not any(item.claim_mode == "actual" for item in ranked):
        return AggregatedField(field=field, value=OUTCOME_REQUIRED, confidence=1.0, claim_mode="unknown", missing_reason="The source describes planned work and contains no achieved outcome evidence")
    if not ranked:
        return AggregatedField(field=field, value=MISSING, confidence=0, claim_mode="unknown", missing_reason="No relevant source evidence")
    if field == "approach":
        selected_by_id: dict[str, FieldCandidate] = {}
        for item in ranked:
            if item.combined_score < 0:
                continue
            for identifier in item.evidence_block_ids:
                selected_by_id.setdefault(identifier, item)
        selected = sorted(
            selected_by_id.values(),
            key=lambda item: min((blocks[value].reading_order for value in item.evidence_block_ids if value in blocks), default=9999),
        )[:12]
        pieces: list[str] = []
        for item in selected:
            identifier = item.evidence_block_ids[0]
            text = blocks[identifier].original_text if identifier in blocks else item.value
            text = re.sub(r"^\s*(?:[•▪◦]|[a-z]|[ivx]+|\d+)[.)]\s*", "", text, flags=re.I)
            if pieces and pieces[-1].endswith("-"):
                pieces[-1] = pieces[-1][:-1] + text.lstrip()
            else:
                pieces.append(text.strip())
        value = compact(" ".join(pieces), LIMITS[field])
        evidence_ids = [identifier for item in selected for identifier in item.evidence_block_ids]
        return AggregatedField(field=field, value=value, confidence=min(0.95, 0.65 + 0.05 * len(selected)), claim_mode=selected[0].claim_mode, evidence_block_ids=list(dict.fromkeys(evidence_ids)))
    top = ranked[0]
    inference_basis = [warning.removeprefix("Inferred from ") for warning in top.warnings] if top.claim_mode == "inferred" else []
    confidence = 0.75 if top.claim_mode == "inferred" else min(0.98, max(0.45, 0.55 + top.combined_score))
    return AggregatedField(
        field=field, value=top.value, confidence=confidence,
        claim_mode=top.claim_mode, evidence_block_ids=top.evidence_block_ids, inference_basis=inference_basis,
    )


def _commercial_metrics(blocks: list[DocumentBlock]) -> list[CommercialMetric]:
    lookup = {block.id: block for block in blocks}
    results: list[CommercialMetric] = []
    seen: set[tuple[str, str]] = set()
    for block in blocks:
        lowered = block.normalized_text.casefold()
        commercial_context = block.block_type == "table_row" or any(term in lowered for term in ("gesamtpreis", "summe", "project leader", "kommerzielles angebot", "total price", "daily rate", "revenue", "budget"))
        if not commercial_context:
            continue
        days = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:tage|days)\b", block.normalized_text, re.I)
        if days:
            key = ("Planned effort", days.group(0).casefold())
            if key not in seen:
                seen.add(key)
                results.append(CommercialMetric(name="Planned effort", value=days.group(0), evidence=_evidence(lookup, [block.id])))
        prices = re.findall(r"\b\d{1,3}(?:[. ]\d{3})+(?:,[-\d]{0,2})?\b", block.normalized_text)
        if prices and any(term in lowered for term in ("gesamtpreis", "summe", "total")):
            value = f"EUR {prices[-1].rstrip(',-')}"
            key = ("Total offer value", value.casefold())
            if key not in seen:
                seen.add(key)
                results.append(CommercialMetric(name="Total offer value", value=value, evidence=_evidence(lookup, [block.id])))
        currency = next((match.group(0) for match in METRIC_PATTERN.finditer(block.normalized_text) if re.search(r"EUR|USD|CHF|GBP|€|\$|£", match.group(0), re.I)), None)
        if currency:
            name = "Project revenue" if "revenue" in lowered else "Commercial budget" if "budget" in lowered else "Total offer value"
            key = (name, currency.casefold())
            if key not in seen:
                seen.add(key)
                results.append(CommercialMetric(name=name, value=currency, evidence=_evidence(lookup, [block.id])))
    return results[:6]


def _improvement_kpis(blocks: list[DocumentBlock], profile: DocumentProfile) -> list[KPI]:
    lookup = {block.id: block for block in blocks}
    results: list[KPI] = []
    for block in blocks:
        lowered = block.normalized_text.casefold()
        if any(term in lowered for term in ("revenue", "budget", "gesamtpreis", "angebot", "commercial", "project leader")):
            continue
        actual = any(term in lowered for term in ACTUAL_TERMS)
        target = any(term in lowered for term in ("target", "ziel", "planned improvement"))
        if profile.project_phase == "planned" and not actual:
            continue
        for metric in METRIC_PATTERN.finditer(block.normalized_text):
            if not re.search(r"%|percent|prozent|fte|\bx\b", metric.group(0), re.I):
                continue
            prefix = block.normalized_text[:metric.start()].rstrip()
            action = re.search(r"(reduced|increased|improved|reduziert|gesteigert|verbessert)\s+(.{2,45}?)\s+(?:by|um)$", prefix, re.I)
            if action:
                suffix = "reduction" if action.group(1).casefold() in {"reduced", "reduziert"} else "improvement"
                name = compact(f"{action.group(2).strip().title()} {suffix}", KPI_NAME_LIMIT)
            else:
                name = "Reported impact"
            results.append(KPI(
                name=name, value=compact(metric.group(0), KPI_VALUE_LIMIT),
                confidence=Confidence.strong if action and actual else Confidence.weak,
                evidence=_evidence(lookup, [block.id]), status="achieved" if actual else "target" if target else "unknown",
            ))
            if len(results) >= KPI_LIMIT:
                return results
    return results


def analyze_reference(chunks: list[SourceChunk], classification: str = "public") -> SemanticAnalysis:
    blocks = build_blocks(chunks, classification)
    profile = profile_document(blocks)
    candidates = retrieve_field_candidates(blocks, profile)
    fields = ["title", "client", "supplier", "project_id", "date", "industry", "service", "situation_challenge", "approach", "outcome_impact"]
    by_id = {block.id: block for block in blocks}
    aggregated = [_aggregate_field(field, [item for item in candidates if item.field == field], profile, by_id) for field in fields]
    values: dict[str, Section] = {}
    for item in aggregated:
        confidence = Confidence.missing if item.missing_reason else Confidence.strong if item.confidence >= 0.8 else Confidence.weak
        values[item.field] = Section(
            value=item.value, confidence=confidence, evidence=_evidence(by_id, item.evidence_block_ids),
            claim_mode=ClaimMode(item.claim_mode),
            semantic_type=(
                "aggregated_planned_scope" if item.field == "approach" and item.evidence_block_ids
                else next((candidate.semantic_type for candidate in candidates if candidate.field == item.field and candidate.value == item.value), None)
            ),
            inference_basis=item.inference_basis,
        )
    status = "planned" if profile.project_phase in {"proposal", "planned"} else "in_delivery" if profile.project_phase == "in_delivery" else "completed" if profile.project_phase == "completed" else "unknown"
    draft = ReferenceDraft(
        reference_status=status, **values, kpis=_improvement_kpis(blocks, profile),
        commercial_metrics=_commercial_metrics(blocks),
    )
    return SemanticAnalysis(
        draft=draft, profiles=[profile], blocks=blocks, candidates=candidates, aggregated=aggregated,
        excluded_block_ids=[block.id for block in blocks if _is_boilerplate(block)],
    )
