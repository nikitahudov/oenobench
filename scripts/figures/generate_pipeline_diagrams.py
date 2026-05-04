"""Generate 3 clean matplotlib-rendered pipeline diagrams to replace the
unreadable mermaid PNGs from docs/figures/.

Outputs (PDF + PNG):
  paper/figures/diagram_pipeline.{pdf,png}          — high-level end-to-end flow
  paper/figures/diagram_fact_processing.{pdf,png}    — 5-stage atomic-fact pipeline
  paper/figures/diagram_quality_assurance.{pdf,png}  — 4-team x N-agent QA stack
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "paper" / "figures"
OUT.mkdir(parents=True, exist_ok=True)

plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["DejaVu Serif", "Times New Roman", "Liberation Serif"],
    "font.size": 9.5,
    "axes.titlesize": 11,
    "savefig.bbox": "tight",
    "savefig.dpi": 300,
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
})


def save(fig, name):
    pdf = OUT / f"{name}.pdf"
    png = OUT / f"{name}.png"
    fig.savefig(pdf)
    fig.savefig(png, dpi=200)
    plt.close(fig)
    print(f"wrote {pdf.relative_to(ROOT)}")


def _box(ax, x, y, w, h, text, *, fc="#EDF2F7", ec="#2D3748",
         fontsize=9, fontweight="normal", lw=1.0, radius=0.05):
    box = mpatches.FancyBboxPatch(
        (x, y), w, h,
        boxstyle=f"round,pad=0.01,rounding_size={radius}",
        facecolor=fc, edgecolor=ec, linewidth=lw, zorder=2,
    )
    ax.add_patch(box)
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
            fontsize=fontsize, fontweight=fontweight, zorder=3,
            wrap=True)


def _arrow(ax, x1, y1, x2, y2, *, color="#2D3748", lw=1.2):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="-|>", color=color, lw=lw,
                                shrinkA=2, shrinkB=2, mutation_scale=12),
                zorder=1)


# ---------------------------------------------------------------------------
# Diagram 1 — End-to-end pipeline overview                                    #
# ---------------------------------------------------------------------------
def diagram_pipeline():
    fig, ax = plt.subplots(figsize=(12.0, 7.0))
    ax.set_xlim(0, 12.0)
    ax.set_ylim(0, 7.0)
    ax.axis("off")

    # Row 1: Sources (y=6.20..6.95)
    sources = [
        ("Government\nregistries\n(INAO, TTB, OIV)", "#FED7AA"),
        ("Wikipedia /\nWikidata\n(SPARQL, MediaWiki)", "#FBCFE8"),
        ("Academic\njournals\n(OENO One, Vitis)", "#C7D2FE"),
        ("University DBs\n(UC Davis, USDA\nExtension)", "#BFDBFE"),
        ("Curated open\ndatasets\n(HF, Kaggle)", "#A7F3D0"),
    ]
    strat_xs = [0.30 + i * 2.34 for i in range(5)]
    strat_w = 2.04
    for i, (txt, fc) in enumerate(sources):
        _box(ax, strat_xs[i], 6.20, strat_w, 0.75, txt, fc=fc, fontsize=8.5)

    # Row 2: Scrapers (y=5.30)
    _box(ax, 0.5, 5.30, 11.0, 0.55,
         "35 provenance-verified scrapers  (Tier-1 / Tier-2 / Tier-3 source-tier labels)",
         fc="#1F2937", ec="#1F2937", fontsize=10, fontweight="bold")
    for t in ax.texts[-1:]:
        t.set_color("white")

    # Row 3: Atomic fact corpus (y=4.40)
    _box(ax, 0.5, 4.40, 11.0, 0.55,
         "38,104 atomic facts  ·  6 domains  ·  580 unique source URLs",
         fc="#FEF3C7", ec="#D97706", fontsize=10, fontweight="bold")

    # Row 4a: section banner (full-width slim header announcing the
    # generation stage and listing the LLM models). Placed in the gap
    # between the atomic-facts row and the strategy boxes so it never
    # crosses any arrows.
    _box(ax, 0.5, 3.65, 11.0, 0.45,
         "generation stage  ·  5 strategies  ×  5 LLM models  "
         "(Claude · GPT · Gemini · Llama · Qwen)  +  deterministic templates",
         fc="#F1F5F9", ec="#475569", fontsize=8.8, fontweight="bold")

    # Row 4b: Generation strategies (the 5 colored boxes)
    strategies = [
        ("fact-to-question\n1,909", "#DBEAFE"),
        ("distractor mining\n405",   "#DBEAFE"),
        ("template\n389",            "#E5E7EB"),
        ("scenario synthesis\n319",  "#DBEAFE"),
        ("comparative\n244",         "#DBEAFE"),
    ]
    for i, (txt, fc) in enumerate(strategies):
        _box(ax, strat_xs[i], 2.55, strat_w, 0.70, txt, fc=fc, fontsize=8.5)

    # Row 5: Audit (y=1.20..2.05) — full-width box; all 5 strategies feed in
    _box(ax, 0.5, 1.20, 11.0, 0.85,
         "9-agent automated audit\n"
         "4 teams: static · tri-judge · deterministic · corpus statistics",
         fc="#F3E8FF", ec="#7E22CE", fontsize=10.5, fontweight="bold")

    # Row 6: Release (y=0.10..0.80) — centered
    _box(ax, 3.0, 0.10, 6.0, 0.70,
         "release_v1.2  ·  3,266 questions  ·  CC-BY-SA-4.0",
         fc="#DCFCE7", ec="#15803D", fontsize=10.5, fontweight="bold")

    # ---- Arrows -----------------------------------------------------------
    # Sources → scrapers
    for i in range(5):
        x = strat_xs[i] + strat_w / 2
        _arrow(ax, x, 6.20, x, 5.85)
    # Scrapers → atomic facts
    _arrow(ax, 6.0, 5.30, 6.0, 4.95)
    # Atomic facts → generation banner (single arrow)
    _arrow(ax, 6.0, 4.40, 6.0, 4.10)
    # Generation banner → strategies (fan-out from banner to each strategy)
    for i in range(5):
        x = strat_xs[i] + strat_w / 2
        _arrow(ax, 6.0, 3.65, x, 3.25)
    # Strategies → audit (fan-in: every strategy passes through audit)
    for i in range(5):
        x = strat_xs[i] + strat_w / 2
        _arrow(ax, x, 2.55, x, 2.05)
    # Audit → release (single bold arrow)
    _arrow(ax, 6.0, 1.20, 6.0, 0.80, lw=1.8)

    save(fig, "diagram_pipeline")


# ---------------------------------------------------------------------------
# Diagram 2 — Atomic-fact processing (5 stages)                                #
# ---------------------------------------------------------------------------
def diagram_fact_processing():
    fig, ax = plt.subplots(figsize=(11.5, 2.8))
    ax.set_xlim(0, 11.5)
    ax.set_ylim(0, 2.8)
    ax.axis("off")

    stages = [
        ("1. Sentence split",
         "split at conjunctions;\n5–30 word atomic band"),
        ("2. Reference resolve",
         "pronouns / demonstratives\n→ entity names"),
        ("3. Domain classify",
         "lexicon + rules\n→ 1 of 6 pillars"),
        ("4. Length & predicate",
         "must have verb;\nno dangling refs"),
        ("5. On-topic filter",
         "region-specific\nkeyword sets"),
    ]
    n = len(stages)
    box_w = 1.95
    gap = 0.25
    total_w = n * box_w + (n - 1) * gap
    x0 = (11.5 - total_w) / 2

    for i, (title, body) in enumerate(stages):
        x = x0 + i * (box_w + gap)
        _box(ax, x, 0.85, box_w, 1.20, "", fc="#EFF6FF", ec="#1D4ED8", lw=1.1)
        ax.text(x + box_w / 2, 1.78, title, ha="center", va="center",
                fontsize=9.5, fontweight="bold", color="#1D4ED8")
        ax.text(x + box_w / 2, 1.25, body, ha="center", va="center",
                fontsize=8)
        if i < n - 1:
            x_a1 = x + box_w
            x_a2 = x + box_w + gap
            _arrow(ax, x_a1, 1.45, x_a2, 1.45, lw=1.4)

    # source / output endcaps
    ax.annotate("source HTML / RDF /\nSPARQL response",
                xy=(x0, 1.45), xytext=(x0 - 1.1, 1.45),
                ha="right", va="center", fontsize=8.5,
                style="italic", color="#475569",
                arrowprops=dict(arrowstyle="-|>", color="#1D4ED8",
                                lw=1.3, shrinkA=4, shrinkB=4,
                                mutation_scale=12))
    ax.annotate("atomic, entity-tagged,\nprovenance-stamped fact",
                xy=(x0 + total_w, 1.45),
                xytext=(x0 + total_w + 1.1, 1.45),
                ha="left", va="center", fontsize=8.5,
                style="italic", color="#1D4ED8", fontweight="bold",
                arrowprops=dict(arrowstyle="-|>", color="#1D4ED8",
                                lw=1.3, shrinkA=4, shrinkB=4,
                                mutation_scale=12))

    # rejection bin under the chain
    _box(ax, x0 + 0.5, 0.05, total_w - 1.0, 0.55,
         "rejected facts → rejection log  (length, missing predicate, off-topic, dangling reference)",
         fc="#FEE2E2", ec="#B91C1C", fontsize=8.5)
    for i in range(n):
        x_mid = x0 + i * (box_w + gap) + box_w / 2
        ax.annotate("", xy=(x_mid, 0.60), xytext=(x_mid, 0.85),
                    arrowprops=dict(arrowstyle="-|>", color="#B91C1C",
                                    lw=0.9, shrinkA=1, shrinkB=1,
                                    mutation_scale=9, alpha=0.7),
                    zorder=1)

    save(fig, "diagram_fact_processing")


# ---------------------------------------------------------------------------
# Diagram 3 — Quality-assurance teams                                          #
# ---------------------------------------------------------------------------
def diagram_quality_assurance():
    fig, ax = plt.subplots(figsize=(11.5, 5.0))
    ax.set_xlim(0, 11.5)
    ax.set_ylim(0, 5.0)
    ax.axis("off")

    # Top: candidate questions
    _box(ax, 3.6, 4.20, 4.3, 0.55,
         "Candidate questions  (5 strategies × 5 generators)",
         fc="#FEF3C7", ec="#D97706", fontsize=10, fontweight="bold")

    # Four team boxes
    teams = [
        ("Team A — Static integrity", "#DBEAFE", "#1D4ED8",
         ["A1 LexicalHygiene", "A2 BiasStats",
          "A3 FactEcho",       "A4 TemplateFingerprint"]),
        ("Team B — Tri-judge LLM panel", "#F3E8FF", "#7E22CE",
         ["B1 TriJudgeAnswer",       "B2 ClosedBookSolvability",
          "B3 UbiquityRisk",         "B4 Ambiguity (esc)",
          "B5 VerifierSkip (esc)"]),
        ("Team C — Deterministic checks", "#DCFCE7", "#15803D",
         ["C1 DistractorDifficulty (esc)",
          "C2 CategoryLeak",
          "C3 SourceSwap (esc)",
          "C4 DifficultyAudit"]),
        ("Team D — Corpus statistics", "#FFE4E6", "#B91C1C",
         ["D1 SelfPreference",
          "D2 DedupCalibration (esc)",
          "D3 SkewAudit"]),
    ]

    # 4 columns
    col_w = 2.6
    col_gap = 0.20
    total_w = 4 * col_w + 3 * col_gap
    x0 = (11.5 - total_w) / 2

    for i, (title, fc, ec, agents) in enumerate(teams):
        x = x0 + i * (col_w + col_gap)
        # Team header
        _box(ax, x, 3.30, col_w, 0.55, title,
             fc=fc, ec=ec, fontsize=9.5, fontweight="bold")
        # Agent list
        for j, agent in enumerate(agents):
            _box(ax, x + 0.10, 2.95 - j * 0.40, col_w - 0.20, 0.32,
                 agent, fc="white", ec=ec, lw=0.7, fontsize=8.0)

    # Arrows from candidates → each team
    for i in range(4):
        x = x0 + i * (col_w + col_gap) + col_w / 2
        _arrow(ax, 5.75, 4.20, x, 3.85)

    # Outcome row
    _box(ax, 0.50, 0.45, 4.3, 0.55,
         "DROP (critical FAIL)  →  341 questions removed",
         fc="#FEE2E2", ec="#B91C1C", fontsize=9, fontweight="bold")
    _box(ax, 5.0, 0.45, 3.0, 0.55,
         "RELABEL (C4 / human)  →  1,259",
         fc="#FEF3C7", ec="#D97706", fontsize=9, fontweight="bold")
    _box(ax, 8.20, 0.45, 2.80, 0.55,
         "KEEP  →  release_v1.2",
         fc="#DCFCE7", ec="#15803D", fontsize=9, fontweight="bold")

    # Calibration callout
    _box(ax, 1.5, 1.20, 8.5, 0.50,
         "Each agent calibrated against human gold sheet via Cohen's κ "
         "— signals with κ < 0.6 are advisory-only",
         fc="#F1F5F9", ec="#334155", fontsize=8.5)

    # Connect teams to outcome row
    for i in range(4):
        x = x0 + i * (col_w + col_gap) + col_w / 2
        _arrow(ax, x, 1.05, x, 1.70)

    save(fig, "diagram_quality_assurance")


def main():
    diagram_pipeline()
    diagram_fact_processing()
    diagram_quality_assurance()


if __name__ == "__main__":
    main()
