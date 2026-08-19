from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

import httpx

from .config import settings
from .knowledge_models import JsonLdBundle, PublicationRecord, RetrievedKnowledge, WorkflowArtifacts
from .models import JobRecord


CLASSIFICATION_RANK = {"public": 0, "internal": 1, "confidential": 2, "strict": 3}


def _safe_id(prefix: str, value: str) -> str:
    return f"{prefix}_{hashlib.sha256(value.encode()).hexdigest()[:28]}"


def _public_blob_url(value: str) -> str:
    parts = urlsplit(value)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _approved_claims(job: JobRecord, artifacts: WorkflowArtifacts) -> list[dict[str, Any]]:
    """Build the publication ledger from the exact human-reviewed result."""
    if not job.result:
        return []
    evidence_lookup = {
        (unit.source_file, unit.locator): unit.id for unit in artifacts.evidence_units
    }
    claims: list[dict[str, Any]] = []
    for section in (
        "title", "client", "date", "industry", "service",
        "situation_challenge", "approach", "outcome_impact",
    ):
        value = getattr(job.result, section)
        if value.value == "Insufficient source evidence":
            continue
        evidence_ids = sorted({
            evidence_lookup[(item.source_file, item.page_or_sheet)]
            for item in value.evidence
            if (item.source_file, item.page_or_sheet) in evidence_lookup
        })
        claims.append({
            "id": _safe_id("approved", f"{job.id}:{section}:{value.value}"),
            "section": section,
            "text": value.value,
            "evidence_ids": evidence_ids,
            "human_edited": value.edited,
        })
    for metric in job.result.kpis:
        evidence_ids = sorted({
            evidence_lookup[(item.source_file, item.page_or_sheet)]
            for item in metric.evidence
            if (item.source_file, item.page_or_sheet) in evidence_lookup
        })
        text = f"{metric.name}: {metric.value}"
        claims.append({
            "id": _safe_id("approved", f"{job.id}:kpi:{text}"),
            "section": "kpi",
            "text": text,
            "evidence_ids": evidence_ids,
            "human_edited": metric.edited,
        })
    return claims


class AzureKnowledgeStore:
    def __init__(self) -> None:
        self.search_endpoint = (settings.azure_search_endpoint or "").rstrip("/")
        self.search_key = settings.azure_search_api_key or ""
        self.container_url = (settings.knowledge_blob_container_url or "").rstrip("/")

    @property
    def search_configured(self) -> bool:
        return bool(self.search_endpoint and self.search_key)

    def _search_headers(self) -> dict[str, str]:
        return {"api-key": self.search_key, "Content-Type": "application/json"}

    def query_approved(
        self,
        query: str,
        classification: str,
        project_id: str,
        top: int = 5,
    ) -> list[RetrievedKnowledge]:
        if not self.search_configured or not settings.cross_project_reuse_enabled:
            return []
        rank = CLASSIFICATION_RANK.get(classification, 0)
        body = {
            "search": query,
            "top": min(max(top, 1), 10),
            "queryType": "semantic",
            "semanticConfiguration": "erax-semantic",
            "select": "id,content,project_id,section,evidence_ids",
            "filter": f"approved eq true and reuse_allowed eq true and classification_rank le {rank}",
        }
        url = (
            f"{self.search_endpoint}/indexes/{settings.azure_search_index_references}/docs/search"
            f"?api-version={settings.azure_search_api_version}"
        )
        response = httpx.post(url, headers=self._search_headers(), json=body, timeout=20)
        response.raise_for_status()
        results = []
        for item in response.json().get("value", []):
            results.append(RetrievedKnowledge(
                id=item["id"],
                content=item.get("content", ""),
                project_id=item.get("project_id"),
                section=item.get("section"),
                score=item.get("@search.rerankerScore") or item.get("@search.score"),
                evidence_ids=item.get("evidence_ids", []),
            ))
        return results

    def _upload_blob(self, job_id: str, payload: bytes) -> str | None:
        if not self.container_url:
            return None
        parts = urlsplit(self.container_url)
        blob_path = f"{parts.path.rstrip('/')}/{quote(job_id)}/bundle.jsonld"
        blob_url = urlunsplit((parts.scheme, parts.netloc, blob_path, parts.query, ""))
        response = httpx.put(
            blob_url,
            headers={"x-ms-blob-type": "BlockBlob", "Content-Type": "application/ld+json"},
            content=payload,
            timeout=30,
        )
        response.raise_for_status()
        return _public_blob_url(blob_url)

    def _index_documents(self, index: str, documents: list[dict[str, Any]]) -> int:
        if not self.search_configured or not documents:
            return 0
        url = (
            f"{self.search_endpoint}/indexes/{index}/docs/index"
            f"?api-version={settings.azure_search_api_version}"
        )
        response = httpx.post(
            url,
            headers=self._search_headers(),
            json={"value": [{"@search.action": "mergeOrUpload", **item} for item in documents]},
            timeout=30,
        )
        response.raise_for_status()
        results = response.json().get("value", [])
        failures = [item for item in results if not item.get("status")]
        if failures:
            raise ValueError(f"Azure Search rejected {len(failures)} document(s)")
        return len(results)

    def publish(
        self,
        job: JobRecord,
        approved_by: str,
        reuse_allowed: bool,
        output_dir: Path,
    ) -> PublicationRecord:
        if not job.result:
            raise ValueError("Result is not ready")
        artifacts = WorkflowArtifacts.model_validate(job.workflow_artifacts or {})
        now = datetime.now(timezone.utc)
        activity_id = f"urn:erax:activity:{job.id}"
        project_id = f"urn:erax:project:{job.id}"
        review_id = f"urn:erax:review:{job.id}"
        approved_claims = _approved_claims(job, artifacts)
        graph: list[dict[str, Any]] = [{
            "@id": project_id,
            "@type": "schema:Project",
            "schema:name": job.result.title.value,
            "schema:description": job.result.outcome_impact.value,
            "erax:classification": job.classification,
            "erax:approved": True,
            "erax:reuseAllowed": reuse_allowed,
            "prov:wasGeneratedBy": {"@id": activity_id},
        }, {
            "@id": activity_id,
            "@type": "prov:Activity",
            "schema:name": "EraX reference generation",
            "prov:endedAtTime": now.isoformat(),
            "erax:model": next((t.model for t in reversed(artifacts.traces) if t.model), "deterministic-v1"),
        }, {
            "@id": review_id,
            "@type": "erax:ReviewDecision",
            "erax:decision": "approved",
            "erax:approvedBy": approved_by,
            "prov:generatedAtTime": now.isoformat(),
            "prov:wasDerivedFrom": {"@id": project_id},
        }]
        for unit in artifacts.evidence_units:
            graph.append({
                "@id": f"urn:erax:evidence:{unit.id}",
                "@type": "erax:EvidenceUnit",
                "schema:name": unit.source_file,
                "schema:text": unit.original_text,
                "erax:normalizedText": unit.normalized_text,
                "erax:translatedText": unit.translated_text,
                "erax:sourceLanguage": unit.source_language,
                "erax:sourceLocator": unit.locator,
                "erax:classification": unit.classification,
            })
        for claim in approved_claims:
            graph.append({
                "@id": f"urn:erax:claim:{claim['id']}",
                "@type": "erax:Claim",
                "schema:description": claim["text"],
                "erax:section": claim["section"],
                "erax:status": "human-approved",
                "erax:humanEdited": claim["human_edited"],
                "erax:reuseAllowed": reuse_allowed and bool(claim["evidence_ids"]),
                "prov:wasDerivedFrom": [
                    {"@id": f"urn:erax:evidence:{item}"} for item in claim["evidence_ids"]
                ],
                "prov:wasGeneratedBy": {"@id": activity_id},
                "prov:wasInfluencedBy": {"@id": review_id},
            })
        for metric in artifacts.metrics:
            graph.append({
                "@id": f"urn:erax:metric:{metric.id}",
                "@type": "schema:QuantitativeValue",
                "schema:name": metric.name,
                "schema:value": metric.numeric_value if metric.numeric_value is not None else metric.original_value,
                "schema:unitText": metric.unit,
                "schema:currency": metric.currency,
                "erax:metricStatus": metric.status,
                "prov:wasDerivedFrom": [
                    {"@id": f"urn:erax:evidence:{item}"} for item in metric.evidence_ids
                ],
            })
        bundle = JsonLdBundle.model_validate({
            "@context": {
                "schema": "https://schema.org/",
                "prov": "http://www.w3.org/ns/prov#",
                "erax": "https://eraneos.com/ns/reference/",
            },
            "@graph": graph,
        })
        output_dir.mkdir(parents=True, exist_ok=True)
        bundle_path = output_dir / f"knowledge-{job.id}.jsonld"
        payload = bundle.model_dump_json(by_alias=True, exclude_none=True, indent=2).encode()
        bundle_path.write_bytes(payload)
        blob_url = None
        indexed = 0
        errors: list[str] = []
        try:
            blob_url = self._upload_blob(job.id, payload)
        except Exception as exc:
            errors.append(f"blob: {exc}")

        rank = CLASSIFICATION_RANK.get(job.classification, 0)
        reference_docs = []
        for claim in approved_claims:
            reference_docs.append({
                "id": claim["id"],
                "project_id": job.id,
                "content": claim["text"],
                "section": claim["section"],
                "classification": job.classification,
                "classification_rank": rank,
                "approved": True,
                "reuse_allowed": reuse_allowed and bool(claim["evidence_ids"]),
                "language": settings.canonical_language,
                "evidence_ids": claim["evidence_ids"],
                "source_files": sorted({
                    unit.source_file for unit in artifacts.evidence_units if unit.id in claim["evidence_ids"]
                }),
                "generated_at": now.isoformat(),
            })
        evidence_docs = [{
            "id": _safe_id("evidence", f"{job.id}:{unit.id}"),
            "project_id": job.id,
            "content": unit.translated_text or unit.normalized_text,
            "original_content": unit.original_text,
            "source_file": unit.source_file,
            "source_locator": unit.locator,
            "classification": job.classification,
            "classification_rank": rank,
            "approved": True,
            "reuse_allowed": reuse_allowed,
            "language": settings.canonical_language,
            "generated_at": now.isoformat(),
        } for unit in artifacts.evidence_units]
        try:
            indexed += self._index_documents(settings.azure_search_index_references, reference_docs)
            indexed += self._index_documents(settings.azure_search_index_evidence, evidence_docs)
        except Exception as exc:
            errors.append(f"search: {exc}")
        status = "published" if (blob_url or not self.container_url) and (indexed or not self.search_configured) and not errors else "partial"
        return PublicationRecord(
            approved_by=approved_by,
            reuse_allowed=reuse_allowed,
            bundle_path=str(bundle_path),
            blob_url=blob_url,
            search_documents=indexed,
            status=status if self.container_url or self.search_configured else "local",
            error="; ".join(errors) or None,
        )
