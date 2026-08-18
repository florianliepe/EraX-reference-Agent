from pathlib import Path
from types import SimpleNamespace
from pptx import Presentation
from backend.app.models import Confidence
from backend.app.generation import generate
from backend.app import generation
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
        SourceChunk("1", "brief.docx", Chunk("Project revenue: EUR 1.2 million", "paragraph 6")),
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


def test_flexible_kpis_are_extracted_as_grounded_pairs():
    draft = sample_draft()
    pairs = {(item.name, item.value) for item in draft.kpis}
    assert ("Planning Time reduction", "30 percent") in pairs
    assert ("Project Revenue", "EUR 1.2 million") in pairs
    assert all(item.evidence[0].source_file == "brief.docx" for item in draft.kpis)


def test_openai_compatible_gateway_uses_configured_base_url(monkeypatch):
    captured = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured["request"] = kwargs
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content='{"title":"Concise title"}'))]
            )

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured["client"] = kwargs
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr("openai.OpenAI", FakeOpenAI)
    monkeypatch.setattr(generation.settings, "llm_provider", "openai")
    monkeypatch.setattr(generation.settings, "openai_api_key", "test-key")
    monkeypatch.setattr(generation.settings, "openai_base_url", "https://gateway.example")
    monkeypatch.setattr(generation.settings, "openai_model", "gpt-test")

    result, model = generate(sample_draft())

    assert captured["client"] == {
        "api_key": "test-key",
        "base_url": "https://gateway.example",
    }
    assert captured["request"]["model"] == "gpt-test"
    assert captured["request"]["response_format"] == {"type": "json_object"}
    assert result.title.value == "Concise title"
    assert model == "gpt-test"


def test_renderer_always_creates_one_slide(tmp_path: Path):
    output = tmp_path / "reference.pptx"
    render_ppt(sample_draft(), "internal", output, "job12345", "test")
    deck = Presentation(output)
    assert len(deck.slides) == 1
    assert "classification=internal" in deck.core_properties.comments
    slide = deck.slides[0]
    assert slide.part.slide_layout.name == "Title Only"
    assert next(shape for shape in slide.shapes if shape.name == "Title 12").text == "Digital maintenance transformation"
    metadata = next(shape for shape in slide.shapes if shape.name == "Table 5").table
    assert metadata.cell(0, 0).text == "Client: Northwind Rail"
    assert metadata.cell(1, 1).text == "Service: Insufficient source evidence"
    content = next(shape for shape in slide.shapes if shape.name == "Table 13").table
    assert "Manual planning caused delayed maintenance decisions." in content.cell(0, 0).text
    assert "Key KPIs" in content.cell(1, 0).text
    assert "EUR 1.2 million" in content.cell(1, 0).text
    assert "No structured test management" not in content.cell(0, 0).text
