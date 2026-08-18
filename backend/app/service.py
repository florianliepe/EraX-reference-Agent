from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from .generation import generate
from .models import Confidence, KPI, ReferenceDraft
from .parsers import CLASSIFICATION_ORDER, detect_classification, parse_file
from .ppt import render_ppt
from .store import store
from .structuring import SourceChunk, build_draft


MODEL_VERSIONS: dict[str, str] = {}


def _visual_path(session_id: str) -> Path | None:
    return next(
        (Path(file.path) for file in store.sessions[session_id] if Path(file.path).suffix.lower() in {".png", ".jpg", ".jpeg"}),
        None,
    )


def process_job(job_id: str) -> None:
    job = store.jobs[job_id]
    try:
        job.status = "running"; job.progress = 8
        chunks: list[SourceChunk] = []
        labels: list[str] = []
        files = store.sessions[job.session_id]
        for index, file in enumerate(files):
            file.status = "parsing"
            try:
                parsed = parse_file(Path(file.path))
                file.status = "parsed"
                labels.append(detect_classification(parsed))
                chunks.extend(SourceChunk(file.id, file.name, chunk) for chunk in parsed)
            except Exception as exc:
                file.status = "failed"; file.error = str(exc)
            job.progress = 12 + int(38 * (index + 1) / max(1, len(files)))
        if not chunks:
            raise ValueError("No readable source evidence was extracted")
        job.classification = max(labels or ["public"], key=lambda label: CLASSIFICATION_ORDER[label])
        draft = build_draft(chunks); job.progress = 65
        job.result, model_version = generate(draft)
        MODEL_VERSIONS[job_id] = model_version; job.progress = 84
        output = Path(store.sessions[job.session_id][0].path).parent / f"reference-{job.id}.pptx"
        render_ppt(job.result, job.classification, output, job.id, model_version, _visual_path(job.session_id))
        job.output_path = str(output); job.progress = 100; job.status = "completed"
        job.completed_at = datetime.now(timezone.utc)
    except Exception as exc:
        job.status = "failed"; job.error = str(exc); job.progress = 100


def update_result(job_id: str, values: dict[str, str], kpis: list[dict[str, str]] | None = None) -> ReferenceDraft:
    job = store.jobs[job_id]
    if not job.result:
        raise ValueError("Result is not ready")
    for name, value in values.items():
        if hasattr(job.result, name):
            section = getattr(job.result, name)
            section.value = value.strip() or "Insufficient source evidence"
            section.edited = True
    if kpis is not None:
        previous = job.result.kpis
        revised: list[KPI] = []
        by_id = {item.id: item for item in previous}
        for item in kpis[:6]:
            name = item.get("name", "").strip()
            value = item.get("value", "").strip()
            if not name or not value:
                continue
            existing = by_id.get(item.get("id", ""))
            if existing:
                metric = existing.model_copy(deep=True)
                metric.edited = metric.edited or metric.name != name or metric.value != value
                metric.name, metric.value = name, value
            else:
                metric = KPI(id=item.get("id") or KPI(name=name, value=value).id, name=name, value=value, confidence=Confidence.weak, edited=True)
            revised.append(metric)
        job.result.kpis = revised
    render_ppt(
        job.result,
        job.classification,
        Path(job.output_path),
        job.id,
        MODEL_VERSIONS.get(job.id, "deterministic-v1"),
        _visual_path(job.session_id),
    )
    return job.result
