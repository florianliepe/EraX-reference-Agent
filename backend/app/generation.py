from __future__ import annotations

import json
from .config import settings
from .models import ReferenceDraft
from .structuring import LIMITS, compact


SYSTEM_PROMPT = """Rewrite only the supplied draft values into concise client-reference language.
Return one JSON object with the same keys. Do not add facts, numbers, names, or claims.
Keep 'Insufficient source evidence' unchanged. Respect the character limits supplied."""


def _validate(original: ReferenceDraft, proposed: dict[str, str]) -> ReferenceDraft:
    result = original.model_copy(deep=True)
    for name in LIMITS:
        section = getattr(result, name)
        candidate = proposed.get(name, section.value)
        if section.confidence == "missing":
            candidate = "Insufficient source evidence"
        section.value = compact(str(candidate), LIMITS[name])
    return result


def generate(draft: ReferenceDraft) -> tuple[ReferenceDraft, str]:
    if settings.llm_provider != "openai" or not settings.openai_api_key:
        return _validate(draft, {}), "deterministic-v1"
    from openai import OpenAI
    client = OpenAI(api_key=settings.openai_api_key)
    payload = {name: getattr(draft, name).value for name in LIMITS}
    response = client.responses.create(
        model=settings.openai_model,
        instructions=SYSTEM_PROMPT,
        input=json.dumps({"draft": payload, "limits": LIMITS}),
    )
    try:
        proposed = json.loads(response.output_text)
    except json.JSONDecodeError:
        proposed = {}
    return _validate(draft, proposed), settings.openai_model
