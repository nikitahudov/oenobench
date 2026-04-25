"""Unit tests for src/qa/_scoring.py — pure functions, no DB, no API."""

from __future__ import annotations

import pytest

from src.qa._scoring import (
    auc,
    chi_square_uniform,
    cohens_kappa,
    feature_vector,
    fit_logreg,
    lcs_ratio,
    longest_common_ngram,
    mann_whitney_u,
    predict_proba,
    tokenize,
)


def test_chi_square_uniform_on_uniform_data():
    chi2, p = chi_square_uniform([25, 25, 25, 25])
    assert chi2 < 0.01
    assert p > 0.99


def test_chi_square_uniform_on_biased_data():
    chi2, p = chi_square_uniform([90, 5, 3, 2])
    assert chi2 > 100
    assert p < 0.001


def test_mann_whitney_u_symmetry():
    a = [1.0, 2.0, 3.0]
    b = [4.0, 5.0, 6.0]
    u, p = mann_whitney_u(a, b)
    u2, p2 = mann_whitney_u(b, a)
    assert u == pytest.approx(u2)
    assert p == pytest.approx(p2)


def test_mann_whitney_u_equal_distributions():
    a = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0] * 3
    b = list(a)
    _, p = mann_whitney_u(a, b)
    assert p > 0.8


def test_mann_whitney_u_shifted_distributions():
    a = [1.0, 2.0, 3.0, 4.0, 5.0] * 5
    b = [10.0, 11.0, 12.0, 13.0, 14.0] * 5
    _, p = mann_whitney_u(a, b)
    assert p < 0.001


def test_cohens_kappa_perfect():
    k = cohens_kappa([1, 0, 1, 0, 1], [1, 0, 1, 0, 1])
    assert k == pytest.approx(1.0)


def test_cohens_kappa_chance():
    # Random agreement should give κ close to 0
    a = [1, 0, 1, 0, 1, 0, 1, 0, 1, 0]
    b = [0, 1, 1, 0, 0, 1, 1, 0, 0, 1]
    k = cohens_kappa(a, b)
    assert -0.4 < k < 0.4


def test_lcs_ratio_full_copy():
    a = tokenize("Barolo is made from Nebbiolo grapes")
    b = tokenize("Barolo is made from Nebbiolo grapes")
    assert lcs_ratio(a, b) == pytest.approx(1.0)


def test_lcs_ratio_no_overlap():
    a = tokenize("Barolo wine Piedmont Italy Nebbiolo")
    b = tokenize("zzzz xxxx yyyy wwww qqqq")
    assert lcs_ratio(a, b) == 0.0


def test_longest_common_ngram_finds_contiguous_run():
    a = tokenize("the quick brown fox jumps over the lazy dog")
    b = tokenize("a quick brown fox sat on the log")
    n = longest_common_ngram(a, b)
    # "quick brown fox" = 3 contiguous tokens
    assert n >= 3


def test_feature_vector_has_bigrams():
    feats = feature_vector("Which country produces Nebbiolo?")
    assert any(k.startswith("bg:") for k in feats)
    # `punc:?` is now a per-token rate (normalized) so a single `?` in a
    # 5-token text scores 1/5 = 0.2 — still strictly positive and the
    # signal is preserved.
    assert feats.get("punc:?", 0) > 0
    # Sanity: feature value bounded in [0, 1] for natural text.
    assert feats["punc:?"] <= 1.0


def test_fit_logreg_separable():
    # Two features: f1 distinguishes classes perfectly
    feats_a = [{"f1": 1.0}, {"f1": 1.0}, {"f1": 1.2}, {"f1": 0.9}]
    feats_b = [{"f1": 0.0}, {"f1": -0.1}, {"f1": 0.1}, {"f1": -0.2}]
    all_feats = feats_a + feats_b
    labels = [1, 1, 1, 1, 0, 0, 0, 0]
    w, b = fit_logreg(all_feats, labels, epochs=500, lr=0.8)
    assert predict_proba(w, b, {"f1": 1.0}) > 0.8
    assert predict_proba(w, b, {"f1": 0.0}) < 0.2


def test_auc_perfect():
    assert auc([1, 1, 0, 0], [0.9, 0.8, 0.2, 0.1]) == pytest.approx(1.0)


def test_auc_random():
    # Scores independent of labels → AUC near 0.5
    assert auc([1, 0, 1, 0, 1, 0], [0.4, 0.5, 0.5, 0.4, 0.5, 0.4]) == pytest.approx(0.5, abs=0.2)
