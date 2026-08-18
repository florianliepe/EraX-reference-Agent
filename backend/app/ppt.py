from __future__ import annotations

from pathlib import Path
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.util import Inches, Pt
from .models import ReferenceDraft
from .structuring import LIMITS, compact


BG = RGBColor(247, 244, 239)
INK = RGBColor(25, 24, 22)
ORANGE = RGBColor(239, 94, 47)
MUTED = RGBColor(105, 101, 94)
WHITE = RGBColor(255, 255, 255)


def _box(slide, x, y, w, h, text, size=14, bold=False, color=INK, fill=None, margin=0.14):
    shape = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    if fill:
        shape.fill.solid(); shape.fill.fore_color.rgb = fill
    else:
        shape.fill.background()
    shape.line.fill.background()
    frame = shape.text_frame
    frame.clear(); frame.word_wrap = True
    frame.margin_left = frame.margin_right = Inches(margin)
    frame.margin_top = frame.margin_bottom = Inches(margin)
    frame.vertical_anchor = MSO_ANCHOR.TOP
    paragraph = frame.paragraphs[0]
    paragraph.text = text
    paragraph.font.name = "Arial"
    paragraph.font.size = Pt(size)
    paragraph.font.bold = bold
    paragraph.font.color.rgb = color
    return shape


def render_ppt(draft: ReferenceDraft, classification: str, output: Path, job_id: str, model_version: str) -> None:
    deck = Presentation()
    deck.slide_width = Inches(13.333)
    deck.slide_height = Inches(7.5)
    slide = deck.slides.add_slide(deck.slide_layouts[6])
    background = slide.background.fill
    background.solid(); background.fore_color.rgb = BG

    _box(slide, .48, .24, 2.0, .38, "eraneos", 21, True)
    _box(slide, 10.55, .28, 2.25, .28, f"CLIENT REFERENCE  ·  {classification.upper()}", 8, True, ORANGE)
    slide.shapes.add_shape(1, Inches(.5), Inches(.72), Inches(12.32), Inches(.018)).fill.solid()
    slide.shapes[-1].fill.fore_color.rgb = INK; slide.shapes[-1].line.fill.background()

    _box(slide, .48, .9, 8.25, 1.1, compact(draft.title.value, LIMITS["title"]), 29, True)
    _box(slide, 9.2, .92, 3.55, .28, draft.client.value, 14, True)
    _box(slide, 9.2, 1.3, 3.55, .25, f"{draft.industry.value}  ·  {draft.service.value}", 9, False, MUTED)
    _box(slide, 9.2, 1.62, 3.55, .25, draft.date.value, 9, True, ORANGE)

    sections = [
        ("01", "Situation & challenge", draft.situation_challenge.value, .5),
        ("02", "Our approach", draft.approach.value, 4.77),
        ("03", "Outcome & impact", draft.outcome_impact.value, 9.04),
    ]
    for number, heading, text, x in sections:
        card = slide.shapes.add_shape(5, Inches(x), Inches(2.28), Inches(3.78), Inches(4.32))
        card.fill.solid(); card.fill.fore_color.rgb = WHITE
        card.line.color.rgb = RGBColor(226, 220, 212)
        _box(slide, x + .18, 2.48, .6, .28, number, 9, True, ORANGE)
        _box(slide, x + .18, 2.86, 3.35, .58, heading, 17, True)
        _box(slide, x + .18, 3.62, 3.35, 2.45, text, 13, False)
        _box(slide, x + .18, 6.13, 3.35, .22, "Evidence-grounded · Reviewed in EraX", 7, False, MUTED)

    _box(slide, .5, 6.93, 12.3, .2, f"Generated with traceability · Job {job_id[:8]}", 7, False, MUTED, margin=0)
    deck.core_properties.title = draft.title.value
    deck.core_properties.subject = "Eraneos client reference one-pager"
    deck.core_properties.comments = f"classification={classification}; job={job_id}; generator={model_version}"
    if len(deck.slides) != 1:
        raise ValueError("Renderer invariant violated: output must contain exactly one slide")
    output.parent.mkdir(parents=True, exist_ok=True)
    deck.save(output)

