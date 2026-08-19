from backend.app import agentic_workflow
from backend.app.agentic_workflow import run_agentic_workflow
from backend.app.parsers import Chunk
from backend.app.structuring import SourceChunk, build_draft


def test_deterministic_fallback_produces_typed_grounded_artifacts(monkeypatch):
    chunks = [
        SourceChunk("f1", "brief.docx", Chunk("Client: Northwind Rail", "paragraph 1")),
        SourceChunk("f1", "brief.docx", Chunk("Project title: Maintenance redesign", "paragraph 2")),
        SourceChunk("f1", "brief.docx", Chunk("Outcome: Planning time reduced by 30 percent.", "paragraph 3")),
    ]
    monkeypatch.setattr(agentic_workflow.settings, "agentic_workflow_enabled", False)
    result, model, artifacts = run_agentic_workflow(build_draft(chunks), chunks, "internal", "job-1")

    assert result.client.value == "Northwind Rail"
    assert model == "deterministic-v1"
    assert artifacts.evidence_units[0].original_text == "Client: Northwind Rail"
    assert artifacts.claim_ledger.claims
    assert all(claim.evidence_ids for claim in artifacts.claim_ledger.claims)
    assert artifacts.verification.status == "pass"
    assert {trace.stage for trace in artifacts.traces} == {
        "evidence-curator", "entity-metric-linker", "retrieval-planner",
        "claim-aggregator", "reference-writer", "grounding-verifier",
    }


def test_failed_verification_reverts_writer_output(monkeypatch):
    chunks = [
        SourceChunk("f1", "brief.docx", Chunk("Client: Northwind Rail", "paragraph 1")),
        SourceChunk("f1", "brief.docx", Chunk("Project title: Maintenance redesign", "paragraph 2")),
    ]
    original = build_draft(chunks)
    monkeypatch.setattr(agentic_workflow.settings, "agentic_workflow_enabled", True)
    monkeypatch.setattr(agentic_workflow.settings, "llm_provider", "openai")
    monkeypatch.setattr(agentic_workflow.settings, "openai_api_key", "test")

    def fake_call(stage, _prompt, _payload, traces):
        traces.append(agentic_workflow.AgentTrace(
            stage=stage, status="completed", model="fake", prompt_version="test"
        ))
        if stage == "reference-writer":
            claim = agentic_workflow._default_claims(original, agentic_workflow._build_evidence(chunks, "internal")).claims[0]
            return {"fields": {claim.section: {"value": "Unsupported rewrite", "claim_ids": [claim.id]}}}
        if stage == "grounding-verifier":
            return {"status": "fail", "defects": [{
                "section": "client", "assertion": "Unsupported rewrite", "verdict": "fail",
                "severity": "high", "evidence_ids": [], "repair": "Revert to source text",
            }]}
        return None

    monkeypatch.setattr(agentic_workflow, "_agent_call", fake_call)
    result, _, artifacts = run_agentic_workflow(original, chunks, "internal", "job-2")
    assert result.client.value == "Northwind Rail"
    assert artifacts.verification.status == "fail"
