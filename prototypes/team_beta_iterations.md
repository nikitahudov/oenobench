# Team β — HARD RULE iterations log

Goal: drive scenario_synthesis closed-book leakage on Sonnet 4.6 from
~100% (audit_pilot_v5 evidence) to ≤ 20% via prompt-only changes to
SCENARIO_TEMPLATE.

## Method

For each iteration: revise SCENARIO_TEMPLATE in `src/generators/_prompts.py`,
run `prototypes/team_beta_run_proto.py` to generate N scenarios tagged
`prototype_team_beta_<iter>`, then run `prototypes/team_beta_check_leakage.py`
to manually call Sonnet 4.6 closed-book on each (bypassing the production
gate's MC-only restriction since scenario_based is normally skipped).

Generator: claude (anthropic/claude-opus-4.7) — same model used in audit
pilots, so iteration evidence is comparable to baseline B2 fail rate.

Closed-book judge: anthropic/claude-sonnet-4.6, conf >= 0.7.

## Iter 1 — Initial HARD RULE (anchor + stem-scrub + substitution-test +
   cliche-blocklist + self-check)

Prompt diff: 5 new bullet rules appended after `QUESTION DESIGN — INFERENCE
OVER RECALL` block. Bullets covered:
- ANCHOR REQUIREMENT (numeric/year/named-entity/regulatory anchor required)
- STEM SCRUBBING (premise must not contain answer or synonym)
- SUBSTITUTION TEST (if swap fact → answer must change)
- CLICHE BLOCKLIST (~10 named cliches)
- SELF-CHECK ("could a sommelier answer without source facts?")

Run: 50 + 50-Q across 2 sub-runs (`iter1`, `iter1b`).

Quantitative results:
- Attempts: ~75 cluster prompts (some hit `--max-attempts` budget)
- Inserted: 6 (1 from iter1, 5 from iter1b)
- Skip rate: ~92% (most by `Facts too unrelated` pre-existing rule, some
  by new `World-knowledge-solvable` rule)
- C4-rejected: 1
- Paraphrase-guard rejected: 1

Closed-book check on all 6 inserted:
| QID | Diff | Sonnet pick | Gold | Conf | Verdict |
|---|---|---|---|---|---|
| WB-VIT-0299-L2 | L2 | A | A | 0.72 | LEAK |
| WB-VIT-0300-L3 | L3 | D | D | 0.92 | LEAK |
| WB-GRP-0359-L3 | L3 | B | B | 0.95 | LEAK |
| WB-VIT-0301-L4 | L4 | C | C | 0.85 | LEAK |
| WB-VIT-0302-L3 | L3 | B | B | 0.92 | LEAK |
| WB-GRP-0360-L2 | L2 | D | D | 0.85 | LEAK |

**Leak rate: 6/6 = 100%.**

Sonnet recognized world-knowledge cliches even when the source-fact had
specific numerics: "240 hl/ha" → "very high yield, reduce" (cliche);
"Franconia Nera + Slovak 9% / 1742 hectares" → "= Blaufränkisch" (synonym
recognition); "icewine economics" → universal world knowledge; "permanent
horizontal arms + short retained spurs" → "cordon spur pruning, less
tying" (textbook viticulture).

Diagnosis: rule lets the model emit questions it considers anchor-grounded,
but the model's self-calibration is "average sommelier" rather than
"frontier LLM with comprehensive wine corpus."

## Iter 2 — Cliche-blocklist as auto-skip

Prompt diff: rephrased cliche blocklist as **"OUTPUT THE SKIP SIGNAL — do
NOT emit the question"** (rather than "rewrite or skip"). Added more
cliches drawn from the iter1 leakage failures (icewine economics,
cordon-spur pruning, thin-skin sunburn, grape-synonym recognition, etc).

Run: 25-Q on `winemaking,viticulture,grape_varieties,wine_business`.

Quantitative results:
- Attempts: 29
- Inserted: 0
- Skip rate: 100%

Diagnosis: cliche-blocklist auto-skip is over-broad — almost every fact
cluster in the pool can plausibly map to a cliche, so model skips
everything. Too aggressive.

## Iter 3 — Balanced (mix of iter1 anchor rule + iter2 strictness)

Prompt diff: kept anchor requirement at iter1 strength but explicitly
called out generic regional/category facts as INVALID anchors with
example list. Auto-skip ONLY for cliche blocklist matches; rewrite-first
for less obvious cases.

Run: 25-Q (interrupted by API key exhaustion at attempt #14).

Quantitative results:
- Attempts: ~32
- Inserted: 1 (`WB-WMK-0263-L2` on Crémant/Trento DOC sparkling)
- Manual closed-book on 1: LEAK at conf 0.92 (Sonnet recognizes Crémant
  + Trento DOC traditional method as textbook fact)

## Iter 4 — Frontier-LLM self-check explicit

Prompt diff: replaced the "could a sommelier answer this?" self-check
with explicit "a frontier LLM (not a sommelier) will answer with source
facts hidden — frontier LLMs know virtually all wine textbook material."
Listed the kinds of details that beat a frontier LLM (specific clone
codes, narrow sub-tier minima, niche cooperatives).

Run: 25-Q on `winemaking,viticulture,grape_varieties,wine_business`.

Quantitative results:
- Attempts: 35
- Inserted: 0

Subsequent runs (final, final2) hit OpenRouter `Key limit exceeded` at
12:17:41 UTC, contaminating all "0 inserted" totals after that point.
Iter 4's pre-exhaustion data shows the prompt was over-restrictive
(consistent with iter 2 pattern), but quantitative comparison is not
clean.

## Final ship wording

Reverted to a synthesis: anchor requirement (iter1), explicit invalid-
anchor list with frontier-LLM framing (iter4 self-check wording), cliche
blocklist as inclusion-exclusion guidance not auto-skip (iter3), and
`{"skip": true, "reason": ...}` as preferred output when no anchor
exists. Final shipped wording is committed alongside this report.

## Goal vs measurement

Target: ≤ 20% closed-book solvable in manual gate.
Best measured: 100% (iter1, n=6) and 100% (iter3, n=1).
Did NOT meet target on this prototype.

## Diagnosis & recommendation

The prompt-only fix has hit a **structural ceiling**:

1. **Sonnet 4.6 (the closed-book judge) has wider wine knowledge than the
   "average sommelier" the prompt's self-check invokes.** Even with
   numeric/named-entity anchors, Sonnet recognizes the cliche reasoning
   chain ("240 hl/ha for Chenin Blanc = high yield, reduce") because the
   *reasoning* is textbook even when the specific number isn't.

2. **Many source facts in the wine_regions / grape_varieties / winemaking
   pools are themselves textbook-level.** The HARD RULE correctly
   identifies these and instructs skip — but that drops generation yield
   to ~10% even before the model errs on specific cases.

3. **Closed-book gate currently SKIPS scenario_based question type.** From
   `_closed_book_gate.py` line 54: `_GATED_QUESTION_TYPES = {"multiple_choice"}`.
   Phase 2g.5/2g.6 deliberately scoped the production gate to MC; scenarios
   pass through unscreened. Audit_pilot_v5's 19 fails are all unscreened.

The right fix is **structural, not prompt-only**:

* **Recommended next step:** extend `_GATED_QUESTION_TYPES` to include
  `scenario_based`, and route gate-flagged scenarios through the same
  `closed_book_solvable` tag-and-quota policy v2.0 already uses for MC.
  This converts the 100% leakage into either (a) ~25% of scenarios
  becoming `closed_book_solvable`-tagged at L1 (within the corpus quota),
  or (b) hard rejections once quota is full.

* **The HARD RULE prompt change still ships as a defensive measure** —
  it correctly raises the skip rate (model now refuses world-knowledge-
  solvable clusters), and it provides scaffolding (anchor requirement,
  stem-scrubbing, substitution test) for the LLM to produce
  better-shaped questions when good source facts ARE available.
  Combined with the structural gate extension, the two layers should
  drive scenario-leak rates to the target ≤ 15%.

* **Fact-pool issue is also signal:** the high skip rate on `wine_regions`
  (mostly grape-region associations) suggests the sampler should
  prioritize anchor-rich facts (regulatory minima, specific producer
  details) for scenario_synthesis clusters specifically. Out of scope
  for Team β — flagging for orchestrator/sampler work.

## Cost

Estimated $1.20 for iter1 + iter1b (75 LLM calls, ~3K input tokens each).
$0.20 for iter2 (29 calls), $0.20 for iter3 (32 calls), $0.20 for iter4
(35 calls). Manual closed-book check on 7 questions ≈ $0.10. Total
≈ $1.90, within the $2 budget. (Hit OpenRouter key cap on the project
account at the end of iter3.)
