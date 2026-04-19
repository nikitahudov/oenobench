"""Statistical and string-similarity helpers for audit agents.

Pure functions, no DB or LLM dependencies, easy to unit-test.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Iterable, Sequence

# ─── Statistical tests ─────────────────────────────────────────────────────────


def chi_square_uniform(counts: Sequence[int]) -> tuple[float, float]:
    """Chi-square test for whether `counts` are uniformly distributed.

    Returns (chi2_statistic, p_value). p_value uses scipy when available,
    otherwise a survival-function approximation good enough for k <= 6.
    """
    n = sum(counts)
    k = len(counts)
    if n == 0 or k <= 1:
        return 0.0, 1.0
    expected = n / k
    chi2 = sum((c - expected) ** 2 / expected for c in counts)
    df = k - 1
    p = _chi2_sf(chi2, df)
    return chi2, p


def mann_whitney_u(a: Sequence[float], b: Sequence[float]) -> tuple[float, float]:
    """Two-sample Mann–Whitney U test (two-sided).

    Returns (U_statistic, p_value). Uses normal approximation with tie
    correction; reliable for n_a + n_b >= 20.
    """
    n_a, n_b = len(a), len(b)
    if n_a == 0 or n_b == 0:
        return 0.0, 1.0

    combined = sorted([(v, "a") for v in a] + [(v, "b") for v in b])
    # Assign average ranks to ties
    ranks = [0.0] * len(combined)
    i = 0
    tie_correction = 0.0
    while i < len(combined):
        j = i
        while j + 1 < len(combined) and combined[j + 1][0] == combined[i][0]:
            j += 1
        avg_rank = (i + j) / 2 + 1  # 1-indexed
        for k in range(i, j + 1):
            ranks[k] = avg_rank
        t = j - i + 1
        if t > 1:
            tie_correction += t**3 - t
        i = j + 1

    rank_sum_a = sum(r for r, (_, lbl) in zip(ranks, combined) if lbl == "a")
    u_a = rank_sum_a - n_a * (n_a + 1) / 2
    u_b = n_a * n_b - u_a
    u = min(u_a, u_b)

    n = n_a + n_b
    mean_u = n_a * n_b / 2
    var_u = n_a * n_b * (n + 1) / 12
    if tie_correction > 0:
        var_u -= n_a * n_b * tie_correction / (12 * n * (n - 1))
    if var_u <= 0:
        return float(u), 1.0

    z = (u - mean_u) / math.sqrt(var_u)
    p = 2 * (1 - _normal_cdf(abs(z)))
    return float(u), max(min(p, 1.0), 0.0)


def cohens_kappa(rater_a: Sequence, rater_b: Sequence) -> float:
    """Cohen's κ for two raters over the same items.

    Each sequence holds discrete labels for the corresponding item.
    Returns κ in [-1, 1]; ~0 = chance agreement, 1 = perfect.
    """
    if len(rater_a) != len(rater_b) or not rater_a:
        return 0.0
    labels = sorted({*rater_a, *rater_b})
    n = len(rater_a)
    agree = sum(1 for x, y in zip(rater_a, rater_b) if x == y)
    p_o = agree / n
    a_counts = Counter(rater_a)
    b_counts = Counter(rater_b)
    p_e = sum((a_counts[l] / n) * (b_counts[l] / n) for l in labels)
    if p_e == 1.0:
        return 1.0
    return (p_o - p_e) / (1 - p_e)


def _chi2_sf(chi2: float, df: int) -> float:
    """Approximate survival function of chi-square. Falls back to scipy if available."""
    try:
        from scipy.stats import chi2 as _scipy_chi2

        return float(_scipy_chi2.sf(chi2, df))
    except ImportError:
        # Wilson–Hilferty approximation
        if df <= 0:
            return 1.0
        x = (chi2 / df) ** (1 / 3)
        mean = 1 - 2 / (9 * df)
        sd = math.sqrt(2 / (9 * df))
        z = (x - mean) / sd
        return 1 - _normal_cdf(z)


def _normal_cdf(z: float) -> float:
    """Standard normal CDF using erf."""
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


# ─── String similarity ────────────────────────────────────────────────────────

_TOKEN_RE = re.compile(r"\w+")


def tokenize(text: str) -> list[str]:
    """Lowercase word tokenizer."""
    return _TOKEN_RE.findall(text.lower())


def lcs_ratio(a_tokens: Sequence[str], b_tokens: Sequence[str]) -> float:
    """Longest common subsequence ratio over min(len_a, len_b).

    Range [0, 1]. Used by FactEcho to detect verbatim source copying.
    """
    if not a_tokens or not b_tokens:
        return 0.0
    n, m = len(a_tokens), len(b_tokens)
    if n * m > 200_000:
        # Cap to keep this O(n*m) cheap; truncate to first 500 tokens each
        a_tokens = list(a_tokens)[:500]
        b_tokens = list(b_tokens)[:500]
        n, m = len(a_tokens), len(b_tokens)

    prev = [0] * (m + 1)
    curr = [0] * (m + 1)
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if a_tokens[i - 1] == b_tokens[j - 1]:
                curr[j] = prev[j - 1] + 1
            else:
                curr[j] = max(prev[j], curr[j - 1])
        prev, curr = curr, prev
    lcs_len = prev[m]
    return lcs_len / min(n, m)


def longest_common_ngram(a_tokens: Sequence[str], b_tokens: Sequence[str]) -> int:
    """Length of the longest contiguous shared n-gram between the two token sequences."""
    if not a_tokens or not b_tokens:
        return 0
    a, b = list(a_tokens), list(b_tokens)
    n, m = len(a), len(b)
    # DP with rolling array — O(n*m) but with short circuit
    if n * m > 1_000_000:
        a, b = a[:1000], b[:1000]
        n, m = len(a), len(b)
    prev = [0] * (m + 1)
    longest = 0
    for i in range(1, n + 1):
        curr = [0] * (m + 1)
        for j in range(1, m + 1):
            if a[i - 1] == b[j - 1]:
                curr[j] = prev[j - 1] + 1
                if curr[j] > longest:
                    longest = curr[j]
        prev = curr
    return longest


# ─── Feature extraction (Team A4 TemplateFingerprint) ─────────────────────────

# Light-weight POS-ish bigrams: we don't ship spaCy as a hard dep, so we bucket
# tokens into rough categories by surface form. Good enough to detect the
# rigidly-formatted template grammar vs free-form LLM grammar.

_NUMERIC_TOKEN = re.compile(r"^\d[\d,.]*$")
_PUNCT_TOKEN = re.compile(r"^[^\w\s]+$")
_QUESTION_WORDS = {
    "what", "which", "who", "where", "when", "why", "how",
}
_DETERMINERS = {"the", "a", "an", "this", "these", "that", "those"}
_AUX = {
    "is", "are", "was", "were", "be", "been", "being",
    "has", "have", "had", "does", "do", "did",
    "will", "would", "should", "could", "may", "might", "can",
}


def pos_bucket(token: str) -> str:
    """Tiny POS bucketizer used for template detection bigrams."""
    t = token.lower()
    if _NUMERIC_TOKEN.match(t):
        return "NUM"
    if _PUNCT_TOKEN.match(t):
        return "PUN"
    if t in _QUESTION_WORDS:
        return "QW"
    if t in _DETERMINERS:
        return "DET"
    if t in _AUX:
        return "AUX"
    if len(t) <= 3:
        return "SHORT"
    if t.endswith("ing") or t.endswith("ed"):
        return "VERB?"
    return "WORD"


def feature_vector(text: str) -> dict[str, float]:
    """POS-bigram + punctuation features for template detection.

    Return dict with bigram counts (normalized), question-mark count,
    comma/colon/dash counts, average word length, sentence count.
    """
    raw_tokens = re.findall(r"\w+|[^\w\s]", text)
    if not raw_tokens:
        return {}
    buckets = [pos_bucket(t) for t in raw_tokens]
    bigrams = [f"{a}-{b}" for a, b in zip(buckets, buckets[1:])]
    n = max(len(bigrams), 1)
    feats: dict[str, float] = {f"bg:{bg}": c / n for bg, c in Counter(bigrams).items()}
    feats["punc:?"] = text.count("?")
    feats["punc:,"] = text.count(",")
    feats["punc::"] = text.count(":")
    feats["punc:-"] = text.count("-")
    feats["len:tokens"] = float(len(raw_tokens))
    feats["len:avg_word"] = sum(len(t) for t in raw_tokens) / len(raw_tokens)
    feats["len:sentences"] = float(text.count(".") + text.count("!") + text.count("?"))
    return feats


# ─── Tiny logistic regression (no sklearn dependency) ─────────────────────────


def _sigmoid(z: float) -> float:
    """Numerically stable sigmoid, clamped to avoid math.exp overflow."""
    if z > 35:
        return 1.0
    if z < -35:
        return 0.0
    return 1.0 / (1.0 + math.exp(-z))


def fit_logreg(
    feats: list[dict[str, float]],
    labels: list[int],
    *,
    epochs: int = 200,
    lr: float = 0.5,
    l2: float = 0.01,
) -> tuple[dict[str, float], float]:
    """Fit a tiny binary logistic regression with L2.

    Returns (weights, bias). Sufficient for ~600 examples × ~few-hundred features.
    """
    if not feats:
        return {}, 0.0
    vocab = sorted({k for f in feats for k in f})
    w = {k: 0.0 for k in vocab}
    b = 0.0
    n = len(feats)
    for _ in range(epochs):
        grad_w: dict[str, float] = {k: 0.0 for k in vocab}
        grad_b = 0.0
        for f, y in zip(feats, labels):
            z = b + sum(w[k] * v for k, v in f.items() if k in w)
            p = _sigmoid(z)
            err = p - y
            for k, v in f.items():
                if k in grad_w:
                    grad_w[k] += err * v
            grad_b += err
        for k in w:
            w[k] -= lr * (grad_w[k] / n + l2 * w[k])
        b -= lr * grad_b / n
    return w, b


def predict_proba(weights: dict[str, float], bias: float, f: dict[str, float]) -> float:
    z = bias + sum(weights.get(k, 0.0) * v for k, v in f.items())
    return _sigmoid(z)


def auc(y_true: Sequence[int], y_score: Sequence[float]) -> float:
    """Trapezoidal ROC AUC. O(n log n)."""
    pos = [s for s, y in zip(y_score, y_true) if y == 1]
    neg = [s for s, y in zip(y_score, y_true) if y == 0]
    if not pos or not neg:
        return 0.5
    wins = ties = 0
    for p in pos:
        for n in neg:
            if p > n:
                wins += 1
            elif p == n:
                ties += 1
    return (wins + 0.5 * ties) / (len(pos) * len(neg))


# ─── Convenience iterators ────────────────────────────────────────────────────


def chunked(it: Iterable, size: int):
    """Yield successive `size`-chunks from `it`."""
    buf = []
    for x in it:
        buf.append(x)
        if len(buf) >= size:
            yield buf
            buf = []
    if buf:
        yield buf
