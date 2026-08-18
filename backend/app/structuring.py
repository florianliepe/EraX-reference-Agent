from __future__ import annotations

import re
from dataclasses import dataclass
from .models import Confidence, Evidence, KPI, ReferenceDraft, Section
from .parsers import Chunk


LABELS = {
    "title": ("project title", "title", "project", "reference"),
    "client": ("client", "customer", "organisation", "organization"),
    "date": ("date", "year", "duration"),
    "industry": ("industry", "sector"),
    "service": ("service", "capability", "offering"),
    "situation_challenge": ("challenge", "situation", "problem", "context", "need"),
    "approach": ("approach", "solution", "implemented", "delivered", "method"),
    "outcome_impact": ("outcome", "impact", "result", "benefit", "improved", "reduced", "increased"),
}
LIMITS = {
    "title": 90, "client": 55, "date": 30, "industry": 45, "service": 55,
    "situation_challenge": 360, "approach": 360, "outcome_impact": 320,
}
KPI_NAME_LIMIT = 48
KPI_VALUE_LIMIT = 48
KPI_LIMIT = 6
KPI_TERMS = (
    "revenue", "budget", "saving", "cost", "roi", "return on investment", "fte",
    "cycle time", "lead time", "processing time", "planning time", "quality", "nps",
    "availability", "uptime", "duration", "productivity", "efficiency", "improvement", "kpi",
)
METRIC_PATTERN = re.compile(
    r"(?:(?:EUR|USD|CHF|GBP|€|\$|£)\s*\d[\d.,]*(?:\s*(?:million|billion|bn|m|k)\b)?"
    r"|\d[\d.,]*\s*(?:EUR|USD|CHF|GBP)"
    r"|\d+(?:[.,]\d+)?\s*(?:%|percent\b|per cent\b|FTEs?\b|full-time equivalents?\b|x\b))",
    re.I,
)


@dataclass
class SourceChunk:
    file_id: str
    source_file: str
    chunk: Chunk


def compact(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", text).strip(" •-\t")
    if len(text) <= limit:
        return text
    shortened = text[: limit - 1].rsplit(" ", 1)[0]
    return shortened.rstrip(".,;:") + "…"


def _score(text: str, keywords: tuple[str, ...]) -> int:
    lowered = text.lower()
    score = 0
    for word in keywords:
        if not re.search(rf"\b{re.escape(word)}\b", lowered):
            continue
        score += 3 if re.search(rf"\b{re.escape(word)}\b\s*[:\-]", lowered) else 1
    return score


def _clean_label(text: str, keywords: tuple[str, ...]) -> str:
    pattern = "|".join(re.escape(k) for k in keywords)
    return re.sub(rf"^\s*(?:{pattern})\s*[:\-]\s*", "", text, flags=re.I).strip()


def _kpi_name(text: str, metric_start: int) -> tuple[str, bool]:
    prefix = re.sub(r"\s+", " ", text[:metric_start]).strip(" .;,-")
    labeled = re.search(r"(?:^|[.;])\s*([^:]{2,55})\s*:\s*$", prefix)
    if labeled:
        label = labeled.group(1).strip()
        if any(term in label.lower() for term in KPI_TERMS):
            return compact(re.sub(r"^kpi\s*[-–—]?\s*", "", label, flags=re.I).title(), KPI_NAME_LIMIT), True

    action = re.search(r"(?:reduced|decreased|lowered|cut)\s+(.{2,45}?)\s+by$", prefix, re.I)
    if action:
        return compact(f"{action.group(1).strip().title()} reduction", KPI_NAME_LIMIT), True
    action = re.search(r"(?:increased|improved|raised|boosted)\s+(.{2,45}?)\s+by$", prefix, re.I)
    if action:
        return compact(f"{action.group(1).strip().title()} improvement", KPI_NAME_LIMIT), True

    for term in sorted(KPI_TERMS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(term)}\b", prefix, re.I):
            return term.title(), True
    return "Reported impact", False


def _extract_kpis(chunks: list[SourceChunk]) -> list[KPI]:
    results: list[KPI] = []
    seen: set[tuple[str, str]] = set()
    for item in chunks:
        text = re.sub(r"\s+", " ", item.chunk.text).strip()
        for metric in METRIC_PATTERN.finditer(text):
            name, contextual = _kpi_name(text, metric.start())
            value = compact(metric.group(0).strip(), KPI_VALUE_LIMIT)
            key = (name.casefold(), value.casefold())
            if key in seen:
                continue
            seen.add(key)
            evidence = Evidence(
                file_id=item.file_id,
                source_file=item.source_file,
                snippet=compact(item.chunk.text, 240),
                page_or_sheet=item.chunk.location,
            )
            results.append(KPI(
                name=name,
                value=value,
                confidence=Confidence.strong if contextual else Confidence.weak,
                evidence=[evidence],
            ))
            if len(results) >= KPI_LIMIT:
                return results
    return results


def build_draft(chunks: list[SourceChunk]) -> ReferenceDraft:
    values: dict[str, Section] = {}
    for field, keywords in LABELS.items():
        ranked = sorted((( _score(item.chunk.text, keywords), item) for item in chunks), key=lambda pair: pair[0], reverse=True)
        matches = [(score, item) for score, item in ranked if score > 0]
        if not matches:
            values[field] = Section()
            continue
        best_score, best = matches[0]
        candidates = matches[:2] if field in {"situation_challenge", "approach", "outcome_impact"} else matches[:1]
        combined = " ".join(_clean_label(item.chunk.text, keywords) for _, item in candidates)
        evidence = [Evidence(file_id=item.file_id, source_file=item.source_file, snippet=compact(item.chunk.text, 240), page_or_sheet=item.chunk.location) for _, item in candidates]
        confidence = Confidence.strong if best_score >= 3 or len(matches) >= 2 else Confidence.weak
        values[field] = Section(value=compact(combined, LIMITS[field]), confidence=confidence, evidence=evidence)
    return ReferenceDraft(**values, kpis=_extract_kpis(chunks))
