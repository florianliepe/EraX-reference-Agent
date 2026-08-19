from pathlib import Path

import fitz

from backend.app.parsers import Chunk, needs_document_intelligence, parse_pdf
from backend.app.semantic import OUTCOME_REQUIRED, SourceChunk, analyze_reference


def _offer_chunks():
    return [
        SourceChunk("offer", "sanitized-offer.pdf", Chunk(
            "Muster Mobility AG\nSample Contact\n70567 Sample City", "page 1",
            page=1, bbox=(70, 120, 300, 180),
        )),
        SourceChunk("offer", "sanitized-offer.pdf", Chunk(
            "Angebot: SAMPLE-2026-001\nProjekt: PROD Cutover & Hypercare Support der lokalen DataCenter Transformation",
            "page 1", page=1, bbox=(70, 220, 500, 270), is_bold=True,
        )),
        SourceChunk("offer", "sanitized-offer.pdf", Chunk(
            "Muster Consulting GmbH\nLieferantennummer 12345", "page 1",
            page=1, bbox=(70, 290, 400, 330),
        )),
        SourceChunk("offer", "sanitized-offer.pdf", Chunk(
            "Leistungsbeschreibung des Projektes:", "page 2", block_type="heading",
            page=2, bbox=(70, 70, 450, 95), is_bold=True,
        )),
        SourceChunk("offer", "sanitized-offer.pdf", Chunk(
            "Unterstützung bei Erarbeitung, Tracking und Dokumentation des Maßnahmenkatalogs zur geplanten Transformation.",
            "page 2", block_type="list_item", page=2, heading_path=("Leistungsbeschreibung des Projektes:",),
        )),
        SourceChunk("offer", "sanitized-offer.pdf", Chunk(
            "Erstellung von Migrationskonzepten, Management-Entscheidungsvorlagen und Steuerung der Hypercare-Phase.",
            "page 2", block_type="list_item", page=2, heading_path=("Leistungsbeschreibung des Projektes:",),
        )),
        SourceChunk("offer", "sanitized-offer.pdf", Chunk(
            "Project Leader | 22,5 Tage | 1.400,- | 31.500,-", "page 3, table 1, row 2",
            block_type="table_row", page=3,
        )),
        SourceChunk("offer", "sanitized-offer.pdf", Chunk(
            "Summe | 31.500,-", "page 3, table 1, row 3", block_type="table_row", page=3,
        )),
        SourceChunk("offer", "sanitized-offer.pdf", Chunk(
            "Projektlaufzeit: 16.04.2026 (geplant) bis 31.05.2026", "page 3", page=3,
        )),
        SourceChunk("offer", "sanitized-offer.pdf", Chunk(
            "Muster Consulting GmbH Geschäftsführer: Sample | Amtsgericht Sample", "page 3",
            page=3, block_type="footer", repeated=True,
        )),
    ]


def test_offer_semantics_are_role_and_modality_aware():
    analysis = analyze_reference(_offer_chunks(), "internal")
    draft = analysis.draft

    assert draft.reference_status == "planned"
    assert draft.title.value.startswith("PROD Cutover & Hypercare")
    assert draft.client.value == "Muster Mobility AG"
    assert draft.supplier.value == "Muster Consulting GmbH"
    assert draft.project_id.value == "SAMPLE-2026-001"
    assert draft.date.value == "16 Apr-31 May 2026"
    assert draft.industry.value == "Automotive"
    assert draft.industry.claim_mode.value == "inferred"
    assert draft.service.value == "Data center transformation, application migration, hypercare"
    assert draft.approach.claim_mode.value == "planned"
    assert draft.outcome_impact.value == OUTCOME_REQUIRED
    assert draft.kpis == []
    assert {item.name for item in draft.commercial_metrics} == {"Planned effort", "Total offer value"}
    assert all(item.internal_only for item in draft.commercial_metrics)
    assert analysis.excluded_block_ids


def test_layout_parser_marks_repeated_footer(tmp_path: Path):
    source = tmp_path / "layout.pdf"
    document = fitz.open()
    for page_number in range(2):
        page = document.new_page()
        page.insert_text((72, 90), f"Project content page {page_number + 1}", fontsize=12)
        page.insert_text((72, 800), "Muster Consulting GmbH | HRB 12345", fontsize=8)
    document.save(source)

    chunks = parse_pdf(source)

    assert any(chunk.bbox for chunk in chunks)
    assert any(chunk.repeated and chunk.block_type == "footer" for chunk in chunks)


def test_document_intelligence_fallback_has_quality_gate():
    assert needs_document_intelligence([], 2) is True
    assert needs_document_intelligence([Chunk("x" * 500)], 2) is False
