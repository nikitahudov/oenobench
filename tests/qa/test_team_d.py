"""Team D agent tests.

D3 SkewAudit — coverage-guard tests for the Phase 2g.9 fix. The audit #7
report flagged a 10.61× max country over-representation ratio that was
computed on only 16/242 country-tagged questions; with that thin a
denominator the metric is inactionable. The fix downgrades a FAIL to WARN
when country annotation coverage is below 50%.
"""

from __future__ import annotations

from collections import defaultdict
from unittest.mock import MagicMock

import pytest

from src.qa.agents.team_d_population import (
    COUNTRY_COVERAGE_MIN,
    D3_VERSION,
    run_d3_skew_audit,
)

RUN_ID = "00000000-0000-0000-0000-0000d3d30000"


def _stub_get_pg(monkeypatch, *, fact_country_rows, qfact_country_rows):
    """Patch `team_d_population.get_pg` to return a cursor that yields the
    given country-bearing rows for (a) the full fact base and (b) the
    question-linked fact join.
    """
    cursor = MagicMock()
    # Two SELECTs in run_d3_skew_audit: facts then question_facts join.
    cursor.fetchall.side_effect = [fact_country_rows, qfact_country_rows]
    conn = MagicMock()
    conn.cursor.return_value = cursor

    from src.qa.agents import team_d_population
    monkeypatch.setattr(team_d_population, "get_pg", lambda: conn)


def _entities(country: str) -> list[dict]:
    return [{"type": "country", "name": country}]


def _q(uuid: str, *, method: str = "fact_to_question", domain: str = "wine_regions",
       subdomain: str = "italy_piedmont") -> dict:
    return {
        "uuid": uuid,
        "generation_method": method,
        "domain": domain,
        "subdomain": subdomain,
    }


def test_d3_severity_downgrades_when_country_coverage_low(monkeypatch):
    """If a single country dominates the (tiny) tagged set so max_overrep_ratio
    >= 2.0, but coverage is below 50%, the finding must be WARN not FAIL.
    """
    fact_rows = [{"entities": _entities(c)} for c in
                 ["France"] * 50 + ["Italy"] * 30 + ["Spain"] * 20]
    # Only 4 of the 100 input questions have a tagged country, all France.
    qfact_rows = [{"entities": _entities("France")}] * 4
    _stub_get_pg(monkeypatch, fact_country_rows=fact_rows, qfact_country_rows=qfact_rows)

    questions = [_q(f"00000000-0000-0000-0000-{i:012d}") for i in range(100)]

    findings = run_d3_skew_audit(RUN_ID, questions)
    f = findings[0]

    assert f["agent_version"] == D3_VERSION
    assert f["score"] >= 2.0, "synthetic data should drive max_overrep_ratio above the FAIL threshold"
    assert f["severity"] == "warn", (
        "low country coverage must downgrade FAIL → WARN; got "
        f"severity={f['severity']!r}"
    )
    payload = f["payload"]
    assert payload["country_coverage_sufficient"] is False
    assert payload["country_annotation_coverage"] < COUNTRY_COVERAGE_MIN
    assert payload["country_tagged_questions"] == 4
    assert payload["total_questions"] == 100


def test_d3_severity_keeps_fail_when_country_coverage_sufficient(monkeypatch):
    """When most questions ARE country-tagged, an oversized ratio still FAILs.
    The coverage guard is one-directional: it never *upgrades* severity.
    """
    # Fact base is heavily Italian (50%); France is small (10%). Question
    # corpus over-samples France 70× → 70/90 ≈ 78% observed vs 10% expected
    # → ratio ≈ 7.8 (well above the 2.0 FAIL threshold).
    fact_rows = [{"entities": _entities(c)} for c in
                 ["Italy"] * 50 + ["Spain"] * 30 + ["France"] * 10 + ["Germany"] * 10]
    qfact_rows = (
        [{"entities": _entities("France")}] * 70
        + [{"entities": _entities("Italy")}] * 15
        + [{"entities": _entities("Spain")}] * 5
    )
    _stub_get_pg(monkeypatch, fact_country_rows=fact_rows, qfact_country_rows=qfact_rows)

    questions = [_q(f"00000000-0000-0000-0000-{i:012d}") for i in range(100)]

    findings = run_d3_skew_audit(RUN_ID, questions)
    f = findings[0]
    assert f["score"] >= 2.0
    assert f["severity"] == "fail", (
        "with sufficient coverage, a 2.0+ ratio must still FAIL; got "
        f"severity={f['severity']!r}"
    )
    payload = f["payload"]
    assert payload["country_coverage_sufficient"] is True
    assert payload["country_annotation_coverage"] >= COUNTRY_COVERAGE_MIN


def test_d3_payload_includes_coverage_fields_even_when_balanced(monkeypatch):
    """Coverage telemetry must always appear in the payload so reviewers can
    see denominator size at a glance, regardless of severity."""
    fact_rows = [{"entities": _entities(c)} for c in
                 ["France"] * 50 + ["Italy"] * 50]
    qfact_rows = [{"entities": _entities("France")}, {"entities": _entities("Italy")}]
    _stub_get_pg(monkeypatch, fact_country_rows=fact_rows, qfact_country_rows=qfact_rows)

    questions = [_q(f"00000000-0000-0000-0000-{i:012d}") for i in range(2)]

    findings = run_d3_skew_audit(RUN_ID, questions)
    payload = findings[0]["payload"]
    for k in (
        "country_annotation_coverage",
        "country_coverage_sufficient",
        "country_coverage_threshold",
        "country_tagged_questions",
        "total_questions",
    ):
        assert k in payload, f"missing payload key: {k}"
