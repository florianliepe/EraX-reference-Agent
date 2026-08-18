from pathlib import Path
from pptx import Presentation
from backend.app.models import Confidence
from backend.app.parsers import Chunk, detect_classification
from backend.app.ppt import render_ppt
from backend.app.structuring import SourceChunk, build_draft


def sample_draft():
    chunks = [
        SourceChunk("1", "brief.docx", Chunk("Client: Northwind Rail", "paragraph 1")),
        SourceChunk("1", "brief.docx", Chunk("Project title: Digital maintenance transformation", "paragraph 2")),
        SourceChunk("1", "brief.docx", Chunk("Challenge: Manual planning caused delayed maintenance decisions.", "paragraph 3")),
        SourceChunk("1", "brief.docx", Chunk("Approach: Implemented a governed data platform and redesigned workflows.", "paragraph 4")),
        SourceChunk("1", "brief.docx", Chunk("Outcome: Reduced planning time by 30 percent.", "paragraph 5")),
    ]
    return build_draft(chunks)


def test_classification_uses_highest_label():
    assert detect_classification([Chunk("Internal"), Chunk("Strictly confidential")]) == "strict"


def test_missing_fields_are_explicit():
    draft = sample_draft()
    assert draft.industry.confidence == Confidence.missing
    assert draft.industry.value == "Insufficient source evidence"
    assert draft.date.confidence == Confidence.missing
    assert draft.date.value == "Insufficient source evidence"


def test_evidence_is_preserved():
    draft = sample_draft()
    assert draft.outcome_impact.evidence[0].source_file == "brief.docx"


def test_renderer_always_creates_one_slide(tmp_path: Path):
    output = tmp_path / "reference.pptx"
    render_ppt(sample_draft(), "internal", output, "job12345", "test")
    deck = Presentation(output)
    assert len(deck.slides) == 1
    assert "classification=internal" in deck.core_properties.comments
