# Team ε — D3 Country Skew Diagnosis (audit_pilot_v5)

**Run:** `541d1d1d-1a89-4f5a-8940-218928da3729` (audit_pilot_v5, 295 questions)
**D3 finding:** `max_country_overrep_ratio = 3.696` (FAIL gate ≥ 2.0)

## Method

D3 SkewAudit (`src/qa/agents/team_d_population.py:178`) extracts a country only
from `entities[type='country']`. We replicate that exact logic against
both the fact pool and the v5 question→fact join.

## Pool-level country distribution (D3 logic — entity.type='country' only)

Total country-tagged facts in pool: ~5,944.

| Country | pool_n | pool_pct |
|---|---:|---:|
| Australia | 1306 | 21.98% |
| South Africa | 794 | 13.36% |
| New Zealand | 761 | 12.80% |
| US | 576 | 9.69% |
| Italy | 426 | 7.17% |
| France | 420 | 7.07% |
| Chile | 325 | 5.47% |
| Portugal | 259 | 4.36% |
| Spain | 233 | 3.92% |
| Austria | 226 | 3.80% |
| Argentina | 105 | 1.77% |
| Greece | 97 | 1.63% |
| Germany | 95 | 1.60% |
| Israel | 65 | 1.09% |
| Canada | 40 | 0.67% |
| Hungary | 28 | 0.47% |
| Uruguay | 24 | 0.40% |
| Bulgaria | 23 | 0.39% |
| Romania | 21 | 0.35% |
| Georgia | 15 | 0.25% |

## v5 corpus distribution (question→fact join)

D3 counts every `(question, fact)` row whose linked fact has a `type='country'`
entity. v5 has 295 questions but expands to 690 fact rows (scenario_synthesis
has 3 facts/q, distractor_mining has ~5.8). Of those 690 rows, only 69 are
country-tagged.

| Country | v5_rows | v5_pct (of 69) | overrep_ratio (v5_pct / pool_pct) |
|---|---:|---:|---:|
| **South Africa** | 25 | 36.23% | **2.71** |
| Australia | 17 | 24.64% | 1.12 |
| New Zealand | 11 | 15.94% | 1.25 |
| Spain | 4 | 5.80% | 1.48 |
| England | 2 | 2.90% | — (not in pool top-20) |
| France | 2 | 2.90% | 0.41 |
| Austria | 2 | 2.90% | 0.76 |
| Italy | 2 | 2.90% | 0.40 |
| US | 1 | 1.45% | 0.15 |
| Germany | 1 | 1.45% | 0.91 |
| Uruguay | 1 | 1.45% | **3.59** |
| Argentina | 1 | 1.45% | 0.82 |

## Per-strategy breakdown

| strategy | country | rows |
|---|---|---:|
| scenario_synthesis | South Africa | 16 |
| scenario_synthesis | Australia | 12 |
| scenario_synthesis | New Zealand | 9 |
| fact_to_question | South Africa | 5 |
| fact_to_question | Australia | 4 |
| fact_to_question | New Zealand | 2 |
| fact_to_question | Italy | 1 |
| fact_to_question | US | 1 |
| fact_to_question | Uruguay | 1 |
| distractor_mining | South Africa | 4 |
| distractor_mining | England | 2 |
| distractor_mining | Spain | 1 |
| template | Spain | 3 |
| template | Austria | 2 |
| template | France | 2 |
| template | Australia | 1 |
| template | Argentina | 1 |
| template | Germany | 1 |
| template | Italy | 1 |

## Diagnosis: case (c) — both pool-driven AND sampler-driven

**The prompt narrative ("Australia: 17") was misread:** Australia at 17 rows
sounds high, but expressed as a ratio it is actually **1.12× pool share** —
i.e. nearly proportional. The actual D3 FAIL trigger is split between two
distinct effects:

1. **Pool-driven:** the `entity.type='country'` slice of the pool is heavily
   dominated by Anglosphere new-world wine countries — Australia (22%),
   South Africa (13%), New Zealand (13%), and US (10%) together account for
   ~58% of all country-tagged facts. Old-world giants like France (7%) and
   Italy (7%) are under-tagged because their facts use `subdomain` ('bordeaux',
   'burgundy') or `type='region'` entities, not `type='country'`.

2. **Sampler-driven:** **South Africa is over-sampled at 2.71×** its pool
   share (36% v5 vs 13% pool). Looking at the per-strategy split, 16 of the
   25 SA rows come from `scenario_synthesis`. The existing `_cap_admit_and_record`
   in `sample_fact_clusters` is bypassed because clusters are admitted
   atomically and the dominant pool keeps producing SA-heavy clusters that
   slip in below the 1.2× ratio gate during the warm-up grace period
   (`_QUOTA_GRACE_N=10`). Since `_TOTAL_RETURNED_TAGGED` only counts
   country-tagged facts and most clusters are largely country-less, the
   tagged-only denominator stays small and the cap rarely fires.

3. **Long-tail noise:** Uruguay (24 facts in pool, 1 in v5) sits at 3.59×
   pool share due to integer-rounding noise. With only 1 emitted fact at
   1.45% of the tiny tagged total of 69, it's an artefact of the chi-squared
   denominator. A per-call absolute cap (e.g. ≤10% per country in the
   sampled set) prevents a single country from dominating but won't fix the
   single-fact long-tail noise — that needs an absolute floor (e.g.
   "ignore countries with v5_n < 3 in the ratio test"), which is a D3-side
   change, not a sampler-side one.

## Recommendation for Task 3

Implement a per-call absolute-fraction cap (`per_country_cap: float | None`).
This addresses (2) directly by capping South Africa (and any other country)
at ≤ `cap` of the returned set, regardless of pool share. It does not, by
itself, fix (3) — but a 0.10 cap brings the dominant-country ratio into the
1.0–2.0 band even when the pool is heavily skewed. For the long-tail
single-fact noise, propose an audit-side change as a follow-up.

## Prototype results (Task 4)

We ran two prototypes:
* `prototype_team_epsilon_a` — `--count 100` no cap → 35 questions inserted
  before OpenRouter API key limit hit.
* `prototype_team_epsilon_b` — `--count 100 --per-country-cap 0.10` → 10
  questions inserted before key limit hit.

Both runs were terminated by an unrelated 403 from OpenRouter
("Key limit exceeded"). The DB writes that did succeed are the ground truth.

### Distribution under D3 logic (entity.type='country' only)

| metric | proto A (no cap, n=35) | proto B (cap=0.10, n=10) |
|---|---|---|
| total q | 35 | 10 |
| country-tagged q | 2 | 2 |
| tagged-share pct | 5.71% | 20% |
| herfindahl (tagged) | 0.50 | 0.50 |
| max pct (tagged) | 50% | 50% |
| max overrep ratio | 3.74 (South Africa) | 3.74 (South Africa) |
| tagged-country counts | {SA: 1, AU: 1} | {SA: 1, AU: 1} |

**This is meaningless data.** Both prototypes only had 2 country-tagged
questions out of 35 / 10 — far below the per-call cap threshold of
`ceil(0.10 × 100) = 10` per country. With only 2 tagged samples the D3
chi-squared metric trivially returns ratio 3.74 because each single tagged
fact is 50% of the tiny tagged total, vastly above any pool share.

### Why prototypes can't show the cap working

The fact_to_question generator on `wine_regions` returns mostly facts WITHOUT
a `type='country'` entity (the country lives in `subdomain` or in
`type='region'/'appellation'` entries). The per-call cap is a no-op against
those facts (it only counts country-tagged ones). So the cap's behaviour at
realistic volumes is best demonstrated by the unit-test suite, where we
control the in-memory pool to be 100% country-tagged.

### Test-suite verification (Task 6)

`tests/generators/test_fact_sampler.py` covers all three required cases:

1. **`test_per_country_cap_default_value_is_none`** — every public sampler
   entry point has `per_country_cap` defaulting to `None`, so existing
   callers pass the kwarg implicitly and behaviour is unchanged.
2. **`test_per_country_cap_enforced_size_100`** — with cap=0.10 and
   target=100, no country exceeds 10 facts in the returned set.
3. **`test_per_country_cap_pair_strategy_counts_both_facts`** — with an
   all-Australian pair, both facts count toward Australia's quota (2 not 1).

Also covered: `test_apply_per_country_cap_caps_dominant_country`,
`test_apply_per_country_cap_admits_country_less_facts`,
`test_per_country_cap_pair_strategy_mixed_country_admissible`,
`test_per_country_cap_does_not_lock_out_singletons`,
`test_country_cap_max_basic`, `test_country_cap_max_disabled`,
`test_apply_per_country_cap_no_cap_passthrough`, plus
`test_per_country_cap_none_unchanged_size`.

Test count: **226 → 237** generator tests (236 generator + 60 qa = 296 total).
All green.

### Recommended cap value for v6 build

**`per_country_cap = 0.10`** for `sample_facts` and `sample_fact_clusters`
(the two paths where we have empirical evidence of skew). For the other
strategies we recommend defaulting to `None` because:

* `sample_fact_pairs` already constrains pairs to same-country, so per-call
  capping at the strategy level is redundant — the cap is more naturally
  applied at the corpus-build level (across all strategies).
* `sample_confusable_facts` already same-country-filters at Priority 1, so
  the cap would just shrink distractor lists for popular-country targets.

The cleanest corpus-build wiring is in `src/qa/_corpus.py`'s strategy loop:
pass `per_country_cap=0.10` to `sample_facts` and `sample_fact_clusters`
when the corpus tag is `audit_pilot_v6` or later.

### Follow-up (out of scope for this PR)

The 3.59× Uruguay ratio in v5 is not solved by the per-call cap because it's
driven by single-question chi-square noise, not by sampler over-pick. Two
options:

1. **Audit-side floor** — modify `src/qa/agents/team_d_population.py:271`
   to ignore countries with `obs < 3` in the `max_overrep_ratio` calculation.
2. **Country attribution from subdomain** — broaden D3's
   `_extract_country_from_entities` to also pull country from `subdomain`
   (so e.g. `subdomain='loire'` → `country='France'`). This grows the
   tagged denominator from ~5,944 to the full ~38k, eliminating the
   small-N noise and giving D3 a much more honest view of country balance.

We recommend (2) as the principled fix, since it also lets D3 see the
real pool distribution (Portugal 5755 facts via `subdomain='portugal'` are
currently invisible to D3).
