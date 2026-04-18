"""Team C tests. Deterministic, no API."""

from __future__ import annotations

from tests.qa.fixtures.sample_questions import (
    CATEGORY_LEAK_QUESTION,
    CLEAN_QUESTION,
)

RUN_ID = "00000000-0000-0000-0000-00000000dead"


def test_c2_detects_category_leak():
    from src.qa.agents.team_c_probes import run_c2_category_leak

    findings = run_c2_category_leak(RUN_ID, [CATEGORY_LEAK_QUESTION])
    f = findings[0]
    # Stem says "red wine" → any sparkling distractor is a fail
    assert f["severity"] == "fail"
    leaked = f["payload"]["leaked_distractors"]
    assert any(l["option_category"] == "sparkling" for l in leaked)


def test_c2_passes_clean():
    from src.qa.agents.team_c_probes import run_c2_category_leak

    findings = run_c2_category_leak(RUN_ID, [CLEAN_QUESTION])
    # Clean question's options are grape varieties not category-coded
    assert findings[0]["severity"] in {"pass", "warn"}
