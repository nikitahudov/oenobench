"""Tests for src/utils/cost.py — pricing snapshot 2026-05-02."""
import pytest
from src.utils.cost import compute_cost, get_pricing, known_models, _PRICING


# ---------------------------------------------------------------------------
# 1. All 14 known models return non-zero cost for non-zero tokens
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("model_id", list(_PRICING.keys()))
def test_all_known_models_nonzero_cost(model_id: str) -> None:
    """Every known model must return a positive cost for non-zero tokens."""
    cost = compute_cost(model_id, input_tokens=1000, output_tokens=100)
    assert cost > 0.0, f"Expected non-zero cost for {model_id}"


# ---------------------------------------------------------------------------
# 2. Reasoning tokens billed at output rate
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("model_id", [
    "anthropic/claude-opus-4.7",
    "openai/o3",
    "deepseek/deepseek-r1",
    "google/gemini-2.5-pro",
])
def test_reasoning_tokens_billed_at_output_rate(model_id: str) -> None:
    """compute_cost(m, 0, 0, N) must equal compute_cost(m, 0, N, 0)."""
    cost_via_reasoning = compute_cost(model_id, input_tokens=0, output_tokens=0, reasoning_tokens=1000)
    cost_via_output = compute_cost(model_id, input_tokens=0, output_tokens=1000, reasoning_tokens=0)
    assert cost_via_reasoning == pytest.approx(cost_via_output, rel=1e-9)


# ---------------------------------------------------------------------------
# 3. Unknown model returns 0.0
# ---------------------------------------------------------------------------

def test_unknown_model_returns_zero() -> None:
    cost = compute_cost("unknown/bogus-model", input_tokens=1000, output_tokens=1000)
    assert cost == 0.0


def test_empty_model_id_returns_zero() -> None:
    cost = compute_cost("", input_tokens=500, output_tokens=500)
    assert cost == 0.0


# ---------------------------------------------------------------------------
# 4. Spot-checks against EVALUATION_PLAN.md §5 cost projections
#    Assumption per plan §5: 800 input tokens, 5 output tokens per question.
# ---------------------------------------------------------------------------

def test_spot_claude_opus_5k_questions() -> None:
    """Claude Opus 4.7 × 5000 Qs at 800 in + 5 out → ~$20.6 (plan §5.1 table)."""
    per_q = compute_cost("anthropic/claude-opus-4.7", input_tokens=800, output_tokens=5)
    total = per_q * 5000
    assert abs(total - 20.625) < 0.5, f"Expected ~$20.6 ± $0.5, got ${total:.4f}"


def test_spot_haiku_5k_questions() -> None:
    """Claude Haiku 4.5 × 5000 Qs at 800 in + 5 out → ~$4.125.
    Plan §5.1: $4.1. Tolerance ±0.5.
    """
    per_q = compute_cost("anthropic/claude-haiku-4.5", input_tokens=800, output_tokens=5)
    total = per_q * 5000
    assert abs(total - 4.125) < 0.5, f"Expected ~$4.1 ± $0.5, got ${total:.4f}"


def test_spot_llama_70b_5k_questions() -> None:
    """Llama 3.3 70B × 5000 Qs at 800 in + 5 out → ~$0.408.
    input: 800 × 0.10/M = $0.00008; output: 5 × 0.32/M = $0.0000016
    per_q = $0.0000816 → total = $0.408. Tolerance ±0.1.
    """
    per_q = compute_cost("meta-llama/llama-3.3-70b-instruct", input_tokens=800, output_tokens=5)
    total = per_q * 5000
    assert abs(total - 0.408) < 0.1, f"Expected ~$0.41 ± $0.1, got ${total:.4f}"


def test_spot_opus_reasoning_per_question() -> None:
    """Claude Opus 4.7 with 2000 reasoning tokens + 5 output + 800 input.
    input: 800 × 5.00/M = $0.004
    output+reasoning: (5+2000) × 25.00/M = $0.050125
    per_q ≈ $0.054125 → 5000 Qs ≈ $270.6 (plan §5.1 table shows ~$270).
    """
    per_q = compute_cost(
        "anthropic/claude-opus-4.7",
        input_tokens=800,
        output_tokens=5,
        reasoning_tokens=2000,
    )
    total = per_q * 5000
    assert abs(total - 270.625) < 2.0, f"Expected ~$270.6 ± $2, got ${total:.4f}"


# ---------------------------------------------------------------------------
# 5. known_models() returns exactly 14 entries
# ---------------------------------------------------------------------------

def test_known_models_count() -> None:
    models = known_models()
    assert len(models) == 14, f"Expected 14 models, got {len(models)}: {models}"


def test_known_models_sorted() -> None:
    models = known_models()
    assert models == sorted(models), "known_models() should return a sorted list"


def test_known_models_no_duplicates() -> None:
    models = known_models()
    assert len(models) == len(set(models)), "known_models() should have no duplicates"


# ---------------------------------------------------------------------------
# 6. get_pricing helper
# ---------------------------------------------------------------------------

def test_get_pricing_known_model() -> None:
    pricing = get_pricing("anthropic/claude-opus-4.7")
    assert pricing is not None
    assert pricing.input_per_mtok_usd == 5.00
    assert pricing.output_per_mtok_usd == 25.00


def test_get_pricing_unknown_model() -> None:
    assert get_pricing("unknown/model") is None


# ---------------------------------------------------------------------------
# 7. Zero tokens → zero cost
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("model_id", [
    "anthropic/claude-opus-4.7",
    "openai/gpt-5",
    "google/gemini-2.5-flash",
])
def test_zero_tokens_zero_cost(model_id: str) -> None:
    cost = compute_cost(model_id, input_tokens=0, output_tokens=0, reasoning_tokens=0)
    assert cost == 0.0
