"""Generate all paper figures (F1-F12) from the eval markdown report.

Reads:
  data/reports/eval_release_v1_2_full_cleaned.md  (16-config x 3266-Q eval)
  data/reports/zero_correct_97_audit.md           (post-eval defect audit)

Writes (PDF + PNG):
  paper/figures/fig_leaderboard.{pdf,png}
  paper/figures/fig_reasoning_lift.{pdf,png}
  paper/figures/fig_sps_heatmap.{pdf,png}
  paper/figures/fig_sps_lollipop.{pdf,png}
  paper/figures/fig_pareto_cost.{pdf,png}
  paper/figures/fig_cb_vs_source.{pdf,png}
  paper/figures/fig_cb_scatter.{pdf,png}
  paper/figures/fig_difficulty_calib.{pdf,png}
  paper/figures/fig_strategy_heatmap.{pdf,png}
  paper/figures/fig_domain_heatmap.{pdf,png}
  paper/figures/fig_zero_correct_donut.{pdf,png}
  paper/figures/fig_item_histogram.{pdf,png}
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "data" / "reports" / "eval_release_v1_2_full_cleaned.md"
ZERO_AUDIT = ROOT / "data" / "reports" / "zero_correct_97_audit.md"
OUT = ROOT / "paper" / "figures"
OUT.mkdir(parents=True, exist_ok=True)

# Paper-quality defaults
plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["DejaVu Serif", "Times New Roman", "Liberation Serif"],
    "font.size": 9,
    "axes.titlesize": 10,
    "axes.labelsize": 9,
    "legend.fontsize": 8,
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "savefig.bbox": "tight",
    "savefig.dpi": 300,
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
})

FAMILY_COLORS = {
    "anthropic": "#D97757",   # warm orange-brown
    "openai":    "#10A37F",   # green
    "google":    "#4285F4",   # blue
    "meta":      "#6366F1",   # indigo (distinct from google blue)
    "qwen":      "#A020F0",   # purple
    "deepseek":  "#DC2626",   # red
    "mistral":   "#EC4899",   # pink
}

# Pretty short labels
LABEL = {
    "claude-opus-4.7": "Claude Opus 4.7",
    "claude-opus-4.7-thinking": "Claude Opus 4.7 (think)",
    "claude-haiku-4.5": "Claude Haiku 4.5",
    "gpt-5": "GPT-5",
    "gpt-5-mini": "GPT-5-mini",
    "o3": "o3",
    "gemini-2.5-pro": "Gemini 2.5 Pro",
    "gemini-2.5-pro-thinking": "Gemini 2.5 Pro (think)",
    "gemini-2.5-flash": "Gemini 2.5 Flash",
    "llama-3.3-70b": "Llama 3.3 70B",
    "llama-3.1-8b": "Llama 3.1 8B",
    "deepseek-v3": "DeepSeek V3",
    "deepseek-r1": "DeepSeek R1",
    "qwen-2.5-72b": "Qwen 2.5 72B",
    "qwen-2.5-7b": "Qwen 2.5 7B",
    "mistral-large-2411": "Mistral Large",
}


def save(fig, name):
    pdf = OUT / f"{name}.pdf"
    png = OUT / f"{name}.png"
    fig.savefig(pdf)
    fig.savefig(png, dpi=200)
    plt.close(fig)
    print(f"wrote {pdf.relative_to(ROOT)}")


# --------------------------------------------------------------------------- #
# Parse the markdown report                                                   #
# --------------------------------------------------------------------------- #


def _read_report() -> str:
    return REPORT.read_text()


def _table_rows(report: str, header_marker: str, n_cols: int):
    """Extract pipe-table rows for a section identified by `header_marker`.

    Returns list of stripped cell-lists, excluding header / separator rows.
    """
    # find section
    idx = report.find(header_marker)
    if idx < 0:
        raise RuntimeError(f"section not found: {header_marker}")
    # capture lines starting with `|`
    rows = []
    for line in report[idx:].splitlines():
        line = line.strip()
        if not line.startswith("|"):
            if rows:
                break
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) != n_cols:
            continue
        # skip separators (---, etc.)
        if all(set(c) <= {"-", ":", " "} and c for c in cells):
            continue
        rows.append(cells)
    return rows


def _pct(s: str) -> float:
    return float(s.replace("%", "").replace("**", "").replace("+", "").strip())


def _money(s: str) -> float:
    return float(s.replace("$", "").replace(",", "").replace("**", "").strip())


def _int(s: str) -> int:
    return int(s.replace(",", "").replace("**", "").strip())


def parse_per_config():
    rep = _read_report()
    rows = _table_rows(rep, "## 1. Per-Config Summary", n_cols=12)
    # header is first row
    data = []
    for r in rows[1:]:
        slot, config, family, reasoning, acc, parse_p, p50, p95, tin, tout, treason, cost = r
        if slot == "Slot":
            continue
        data.append({
            "slot": int(slot),
            "config": config,
            "family": family,
            "reasoning": reasoning,
            "acc": _pct(acc),
            "parse": _pct(parse_p),
            "p50": int(p50),
            "p95": int(p95),
            "cost": _money(cost),
        })
    return data


def parse_per_domain():
    rep = _read_report()
    rows = _table_rows(rep, "## 2. Per-Config × Per-Domain", n_cols=7)
    domains = ["Wine Regions", "Grape Varieties", "Producers", "Viticulture", "Winemaking", "Wine Business"]
    data = {}
    for r in rows[1:]:
        cfg = r[0]
        if cfg in ("Config", "**all**"):
            continue
        data[cfg] = [_pct(c) for c in r[1:]]
    return domains, data


def parse_per_strategy():
    rep = _read_report()
    rows = _table_rows(rep, "## 3. Per-Config × Per-Strategy", n_cols=6)
    strategies = ["FTQ", "Scenario", "Template", "Comparative", "Distractor"]
    data = {}
    for r in rows[1:]:
        cfg = r[0]
        if cfg in ("Config", "**all**"):
            continue
        data[cfg] = [_pct(c) for c in r[1:]]
    return strategies, data


def parse_sps():
    rep = _read_report()
    rows = _table_rows(rep, "## 4. Self-Preference", n_cols=6)
    data = []
    for r in rows[1:]:
        cfg, family, own, other, delta, ci = r
        if cfg == "Config":
            continue
        if own.strip() == "—" or delta.strip() == "—":
            continue
        # parse CI
        m = re.match(r"\[\s*([+\-\d.]+)%\s*,\s*([+\-\d.]+)%\s*\]", ci)
        lo, hi = (float(m.group(1)), float(m.group(2))) if m else (np.nan, np.nan)
        data.append({
            "config": cfg, "family": family,
            "own": _pct(own), "other": _pct(other),
            "delta": _pct(delta), "lo": lo, "hi": hi,
        })
    return data


def parse_sps_matrix():
    rep = _read_report()
    rows = _table_rows(rep, "## 4b. Self-Preference Family Matrix", n_cols=6)
    families = ["anthropic", "openai", "google", "meta", "qwen"]
    matrix = np.full((5, 5), np.nan)
    for r in rows[1:]:
        eval_fam = r[0].strip("*").strip().lower()
        if eval_fam not in families:
            continue
        i = families.index(eval_fam)
        for j, cell in enumerate(r[1:]):
            if cell.strip() in ("—", ""):
                continue
            m = re.match(r"([\d.]+)%", cell.replace("**", ""))
            if m:
                matrix[i, j] = float(m.group(1))
    return families, matrix


def parse_reasoning_pairs():
    rep = _read_report()
    rows = _table_rows(rep, "## 5. Reasoning-Effect Deltas", n_cols=7)
    data = []
    for r in rows[1:]:
        pair, t_cfg, s_cfg, t_acc, s_acc, delta, ci = r
        if pair == "Pair":
            continue
        m = re.match(r"\[\s*([+\-\d.]+)%\s*,\s*([+\-\d.]+)%\s*\]", ci)
        lo, hi = (float(m.group(1)), float(m.group(2))) if m else (np.nan, np.nan)
        data.append({
            "pair": pair, "thinking": t_cfg, "standard": s_cfg,
            "t_acc": _pct(t_acc), "s_acc": _pct(s_acc),
            "delta": _pct(delta), "lo": lo, "hi": hi,
        })
    return data


def parse_cb():
    rep = _read_report()
    rows = _table_rows(rep, "## 7. Closed-Book vs", n_cols=8)
    data = []
    for r in rows[1:]:
        slot, cfg, n_cb, acc_cb, n_pass, acc_pass, delta, ci = r
        if slot == "Slot" or "all configs" in cfg:
            continue
        m = re.match(r"\[\s*([+\-\d.]+)%\s*,\s*([+\-\d.]+)%\s*\]", ci)
        lo, hi = (float(m.group(1)), float(m.group(2))) if m else (np.nan, np.nan)
        data.append({
            "config": cfg,
            "acc_cb": _pct(acc_cb),
            "acc_pass": _pct(acc_pass),
            "delta": _pct(delta), "lo": lo, "hi": hi,
        })
    return data


def parse_difficulty():
    rep = _read_report()
    rows = _table_rows(rep, "## 8. Per-Config × Per-Difficulty", n_cols=5)
    data = {}
    for r in rows[1:]:
        cfg = r[0]
        if cfg in ("Config", "**all**"):
            continue
        data[cfg] = [_pct(c) for c in r[1:]]
    return data


def parse_item_histogram():
    rep = _read_report()
    rows = _table_rows(rep, "### 9a. Per-Question Accuracy Distribution", n_cols=3)
    counts = []
    for r in rows[1:]:
        k, n, pct = r
        if k == "k correct out of 16":
            continue
        try:
            counts.append((int(k), _int(n)))
        except ValueError:
            continue
    counts.sort()
    return counts


def parse_cost_efficiency():
    rep = _read_report()
    rows = _table_rows(rep, "## 10. Cost-Efficiency", n_cols=5)
    data = []
    for r in rows[1:]:
        slot, cfg, correct, cost, cpc = r
        if slot == "Slot":
            continue
        data.append({
            "config": cfg,
            "correct": _int(correct),
            "cost": _money(cost),
            "cpc": _money(cpc),
        })
    return data


# --------------------------------------------------------------------------- #
# F1 — Leaderboard horizontal bar                                              #
# --------------------------------------------------------------------------- #
def fig_leaderboard():
    cfgs = parse_per_config()
    cfgs = sorted(cfgs, key=lambda c: c["acc"], reverse=True)
    labels = [LABEL.get(c["config"], c["config"]) for c in cfgs]
    accs = [c["acc"] for c in cfgs]
    families = [c["family"] for c in cfgs]
    reasoning = [c["reasoning"] for c in cfgs]
    colors = [FAMILY_COLORS.get(f, "#888") for f in families]
    hatch = ["//" if r != "standard" else "" for r in reasoning]

    fig, ax = plt.subplots(figsize=(5.2, 3.6))
    y = np.arange(len(labels))
    bars = ax.barh(y, accs, color=colors, edgecolor="black", linewidth=0.4)
    for b, h in zip(bars, hatch):
        b.set_hatch(h)
    for i, a in enumerate(accs):
        ax.text(a + 0.5, i, f"{a:.1f}%", va="center", fontsize=6.5)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=7)
    ax.invert_yaxis()
    ax.set_xlim(40, 95)
    ax.tick_params(axis="x", labelsize=7)
    ax.set_xlabel("Accuracy (%) on 3,266 wine MC questions", fontsize=8)
    ax.set_title("Overall capability ranking — 16-config slate", fontsize=9)

    # legend
    fams = sorted(set(families), key=lambda f: list(FAMILY_COLORS).index(f) if f in FAMILY_COLORS else 99)
    handles = [Patch(facecolor=FAMILY_COLORS.get(f, "#888"), edgecolor="black", label=f) for f in fams]
    handles.append(Patch(facecolor="white", edgecolor="black", hatch="//", label="reasoning mode"))
    ax.legend(handles=handles, loc="lower right", frameon=False, fontsize=6.5)
    save(fig, "fig_leaderboard")


# --------------------------------------------------------------------------- #
# F2 — Reasoning lift                                                          #
# --------------------------------------------------------------------------- #
def fig_reasoning_lift():
    pairs = parse_reasoning_pairs()
    fig, ax = plt.subplots(figsize=(6.0, 3.4))
    n = len(pairs)
    x = np.arange(n)
    width = 0.35
    s_acc = [p["s_acc"] for p in pairs]
    t_acc = [p["t_acc"] for p in pairs]
    deltas = [p["delta"] for p in pairs]
    lo = [p["lo"] for p in pairs]
    hi = [p["hi"] for p in pairs]
    fams = ["anthropic", "google", "openai", "deepseek"]
    fcolors = [FAMILY_COLORS[f] for f in fams]

    ax.bar(x - width / 2, s_acc, width,
           color=[matplotlib.colors.to_rgba(c, 0.45) for c in fcolors],
           edgecolor="black", linewidth=0.4, label="standard")
    ax.bar(x + width / 2, t_acc, width,
           color=fcolors, edgecolor="black", linewidth=0.4,
           hatch="//", label="reasoning mode")

    for i, (d, l, h) in enumerate(zip(deltas, lo, hi)):
        sign = "+" if d >= 0 else ""
        ax.text(i, max(s_acc[i], t_acc[i]) + 1.5,
                f"{sign}{d:.1f} pp\n[{l:+.1f},{h:+.1f}]",
                ha="center", fontsize=7)
    ax.set_xticks(x)
    ax.set_xticklabels([
        "Claude\nOpus 4.7", "Gemini\n2.5 Pro",
        "OpenAI\no3 vs GPT-5", "DeepSeek\nR1 vs V3"], fontsize=8)
    ax.set_ylim(60, 95)
    ax.set_ylabel("Accuracy (%)")
    ax.set_title("Reasoning-mode lift over standard")
    # family legend (matches leaderboard) + reasoning hatch
    handles = [Patch(facecolor=FAMILY_COLORS[f], edgecolor="black", label=f) for f in fams]
    handles.append(Patch(facecolor="white", edgecolor="black", hatch="//", label="reasoning"))
    ax.legend(handles=handles, frameon=False, fontsize=7, loc="upper right", ncol=2)
    save(fig, "fig_reasoning_lift")


# --------------------------------------------------------------------------- #
# F3 — SPS family matrix heatmap                                               #
# --------------------------------------------------------------------------- #
def fig_sps_heatmap():
    families, M = parse_sps_matrix()
    fig, ax = plt.subplots(figsize=(4.6, 3.6))
    im = ax.imshow(M, cmap="RdYlGn", vmin=40, vmax=95, aspect="auto")
    for i in range(M.shape[0]):
        for j in range(M.shape[1]):
            v = M[i, j]
            if not np.isnan(v):
                color = "white" if v < 60 or v > 88 else "black"
                ax.text(j, i, f"{v:.1f}", ha="center", va="center",
                        fontsize=8, color=color,
                        fontweight="bold" if i == j else "normal")
    # mark diagonal
    for k in range(M.shape[0]):
        ax.add_patch(plt.Rectangle((k - 0.5, k - 0.5), 1, 1, fill=False,
                                    edgecolor="black", lw=1.2))
    ax.set_xticks(range(len(families)))
    ax.set_yticks(range(len(families)))
    ax.set_xticklabels(families, rotation=30, ha="right")
    ax.set_yticklabels(families)
    ax.set_xlabel("Question generator family")
    ax.set_ylabel("Evaluator family")
    ax.set_title("Cross-family accuracy (%) — diagonal = own family")
    cbar = fig.colorbar(im, ax=ax, fraction=0.04, pad=0.03)
    cbar.set_label("Accuracy %")
    save(fig, "fig_sps_heatmap")


# --------------------------------------------------------------------------- #
# F4 — SPS lollipop                                                            #
# --------------------------------------------------------------------------- #
def fig_sps_lollipop():
    sps = parse_sps()
    sps = sorted(sps, key=lambda s: s["delta"])
    fig, ax = plt.subplots(figsize=(5.6, 4.4))
    y = np.arange(len(sps))
    deltas = [s["delta"] for s in sps]
    los = [s["lo"] for s in sps]
    his = [s["hi"] for s in sps]
    colors = [FAMILY_COLORS.get(s["family"], "#666") for s in sps]
    for i, (d, lo, hi, c) in enumerate(zip(deltas, los, his, colors)):
        ax.plot([lo, hi], [i, i], color=c, lw=2.5, alpha=0.45)
        ax.scatter([d], [i], color=c, s=50, zorder=3, edgecolor="black", linewidth=0.4)
    ax.axvline(0, color="black", lw=0.6)
    ax.set_yticks(y)
    ax.set_yticklabels([LABEL.get(s["config"], s["config"]) for s in sps])
    ax.set_xlabel("Self-Preference Score δ (own − other), pp")
    ax.set_title("Per-config self-preference (95% bootstrap CI)")
    save(fig, "fig_sps_lollipop")


# --------------------------------------------------------------------------- #
# F5 — Cost Pareto                                                             #
# --------------------------------------------------------------------------- #
def fig_pareto_cost():
    cfgs = parse_per_config()
    eff = parse_cost_efficiency()
    cost_by_cfg = {e["config"]: e["cost"] for e in eff}

    fig, ax = plt.subplots(figsize=(5.5, 3.7))
    points = []
    for c in cfgs:
        cost = max(cost_by_cfg.get(c["config"], c["cost"]), 0.01)
        points.append({
            "cost": cost, "acc": c["acc"],
            "label": LABEL.get(c["config"], c["config"]),
            "color": FAMILY_COLORS.get(c["family"], "#888"),
        })
    xs = [p["cost"] for p in points]
    ys = [p["acc"] for p in points]
    cs = [p["color"] for p in points]
    ax.scatter(xs, ys, c=cs, s=70, edgecolor="black",
               linewidth=0.5, zorder=3)

    # Sparse area: short right-of-dot labels.
    OFFSETS = {
        "Llama 3.1 8B":            (8,  -3),
        "Llama 3.3 70B":           (8,   5),
        "Gemini 2.5 Flash":        (8,   5),
        "DeepSeek V3":             (8,  -3),
        "Qwen 2.5 7B":             (8,  -3),
        "Qwen 2.5 72B":            (8,  -10),
        "Claude Haiku 4.5":        (8,  -3),
        "Mistral Large":           (8,   4),
    }
    # Dense upper-right cluster: route every label with a leader line so
    # nothing sits on top of a neighbouring dot or the Pareto dashed.
    # Left-column labels park around x=$0.7 (gap between sparse-low and
    # dense clusters); right-column labels park around x=$45 (open
    # right edge). Vertical stagger avoids label-on-label collisions.
    LEADER = {
        # Right column (anchored x=$45-65, decreasing y)
        "o3":                      ((25.0, 90.0),  "left"),
        "Gemini 2.5 Pro (think)":  ((55.0, 87.0),  "left"),
        "GPT-5":                   ((55.0, 83.5),  "left"),
        "Gemini 2.5 Pro":          ((55.0, 80.0),  "left"),
        "DeepSeek R1":             ((55.0, 76.5),  "left"),
        # Left column (anchored x=$0.6-0.8, decreasing y)
        "Claude Opus 4.7":         ((0.6, 86.0),   "right"),
        "Claude Opus 4.7 (think)": ((0.6, 82.5),   "right"),
        "GPT-5-mini":              ((0.6, 79.0),   "right"),
    }
    for p in points:
        if p["label"] in LEADER:
            (lx, ly), ha = LEADER[p["label"]]
            ax.annotate(p["label"], xy=(p["cost"], p["acc"]),
                        xytext=(lx, ly), textcoords="data",
                        ha=ha, va="center", fontsize=7.0,
                        arrowprops=dict(arrowstyle="-", color="#6B7280",
                                        lw=0.5, shrinkA=0, shrinkB=3))
        else:
            dx, dy = OFFSETS.get(p["label"], (8, 4))
            ax.annotate(p["label"], (p["cost"], p["acc"]),
                        xytext=(dx, dy), textcoords="offset points",
                        fontsize=7.0)

    # Pareto frontier (upper-left envelope: low cost, high acc)
    sorted_pts = sorted(points, key=lambda p: p["cost"])
    fxs, fys = [], []
    best = -np.inf
    for p in sorted_pts:
        if p["acc"] > best:
            fxs.append(p["cost"])
            fys.append(p["acc"])
            best = p["acc"]
    ax.plot(fxs, fys, color="#1F2937", lw=1.2, linestyle="--",
            label="Pareto frontier", zorder=2)

    ax.set_xscale("log")
    ax.set_xlim(0.005, 100)
    ax.set_ylim(48, 94)
    ax.set_xlabel("Total evaluation cost (USD, 3,266 questions)")
    ax.set_ylabel("Accuracy (%)")
    ax.set_title("Cost-vs-accuracy Pareto frontier")
    fams = sorted(set(c["family"] for c in cfgs),
                  key=lambda f: list(FAMILY_COLORS).index(f) if f in FAMILY_COLORS else 99)
    handles = [Patch(facecolor=FAMILY_COLORS.get(f, "#888"),
                     edgecolor="black", label=f) for f in fams]
    handles.append(Patch(facecolor="white", edgecolor="#1F2937",
                         linewidth=1.4, label="Pareto frontier"))
    # Legend in lower-right corner (low-acc / mid-cost area is empty in
    # this layout) with a tighter 4-row × 2-col arrangement.
    ax.legend(handles=handles, frameon=False, fontsize=7, loc="lower right",
              ncol=1)
    ax.grid(True, axis="both", linestyle=":", lw=0.4, alpha=0.5)
    save(fig, "fig_pareto_cost")


# --------------------------------------------------------------------------- #
# F6 — CB vs source-grounded grouped bar                                       #
# --------------------------------------------------------------------------- #
def fig_cb_vs_source():
    cb = parse_cb()
    cb = sorted(cb, key=lambda r: r["acc_pass"], reverse=True)
    labels = [LABEL.get(c["config"], c["config"]) for c in cb]
    fig, ax = plt.subplots(figsize=(6.4, 5.2))
    y = np.arange(len(labels))
    width = 0.4
    ax.barh(y - width / 2, [c["acc_cb"] for c in cb], width,
            color="#FBBF24", edgecolor="black", linewidth=0.4,
            label="closed-book solvable")
    ax.barh(y + width / 2, [c["acc_pass"] for c in cb], width,
            color="#3B82F6", edgecolor="black", linewidth=0.4,
            label="contextual / source-grounded")
    for i, c in enumerate(cb):
        ax.text(c["acc_cb"] + 0.5, i - width / 2,
                f"{c['acc_cb']:.0f}", va="center", fontsize=7)
        ax.text(c["acc_pass"] + 0.5, i + width / 2,
                f"{c['acc_pass']:.0f}", va="center", fontsize=7)
    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.invert_yaxis()
    ax.set_xlim(30, 108)
    ax.set_xlabel("Accuracy (%)")
    ax.set_title("Closed-book vs source-grounded performance per config")
    # Legend below the plot, inside the bottom margin, so it sits clear
    # of every bar and every value label.
    ax.legend(loc="upper center", frameon=False, fontsize=8,
              bbox_to_anchor=(0.5, -0.10), ncol=2)
    save(fig, "fig_cb_vs_source")


# --------------------------------------------------------------------------- #
# F7 — CB scatter                                                              #
# --------------------------------------------------------------------------- #
def fig_cb_scatter():
    cb = parse_cb()
    cfgs = {c["config"]: c["family"] for c in parse_per_config()}
    fig, ax = plt.subplots(figsize=(5.0, 5.0))
    for c in cb:
        fam = cfgs.get(c["config"], "default")
        ax.scatter(c["acc_pass"], c["acc_cb"],
                   c=FAMILY_COLORS.get(fam, "#888"),
                   s=70, edgecolor="black", linewidth=0.5, zorder=3)
        ax.annotate(LABEL.get(c["config"], c["config"]),
                    (c["acc_pass"], c["acc_cb"]),
                    fontsize=6.8, xytext=(3, 2), textcoords="offset points")
    lo, hi = 30, 100
    ax.plot([lo, hi], [lo, hi], color="grey", lw=0.6, linestyle=":",
            label="parity (no CB advantage)")
    ax.set_xlim(lo, hi)
    ax.set_ylim(lo, hi)
    ax.set_xlabel("Source-grounded accuracy (%)")
    ax.set_ylabel("Closed-book solvable accuracy (%)")
    ax.set_title("Where models lean on parametric wine knowledge")
    ax.legend(loc="lower right", frameon=False, fontsize=8)
    ax.grid(True, linestyle=":", lw=0.4, alpha=0.4)
    save(fig, "fig_cb_scatter")


# --------------------------------------------------------------------------- #
# F8 — Difficulty box                                                          #
# --------------------------------------------------------------------------- #
def fig_difficulty_calib():
    diff = parse_difficulty()
    cfgs = parse_per_config()
    cfg_order = [c["config"] for c in sorted(cfgs, key=lambda c: c["acc"], reverse=True)]
    levels = ["L1", "L2", "L3", "L4"]
    data = [[diff[c][i] for c in cfg_order if c in diff] for i in range(4)]
    fig, ax = plt.subplots(figsize=(5.0, 3.4))
    bp = ax.boxplot(data, labels=levels, showmeans=True, patch_artist=True,
                    meanprops={"marker": "D", "markerfacecolor": "white",
                               "markeredgecolor": "black", "markersize": 5})
    for patch, c in zip(bp["boxes"], ["#A7F3D0", "#FCD34D", "#FDA4AF", "#94A3B8"]):
        patch.set_facecolor(c)
        patch.set_edgecolor("black")
    ax.set_ylabel("Accuracy (%)")
    ax.set_xlabel("Assigned difficulty level")
    ax.set_title("Difficulty calibration across 16 configs")
    save(fig, "fig_difficulty_calib")


# --------------------------------------------------------------------------- #
# F9 — Strategy heatmap                                                        #
# --------------------------------------------------------------------------- #
def fig_strategy_heatmap():
    strategies, data = parse_per_strategy()
    cfgs = parse_per_config()
    cfg_order = [c["config"] for c in sorted(cfgs, key=lambda c: c["acc"], reverse=True)]
    M = np.array([data[c] for c in cfg_order if c in data])
    fig, ax = plt.subplots(figsize=(5.2, 5.6))
    im = ax.imshow(M, cmap="RdYlGn", vmin=40, vmax=100, aspect="auto")
    for i in range(M.shape[0]):
        for j in range(M.shape[1]):
            v = M[i, j]
            color = "white" if v < 55 or v > 92 else "black"
            ax.text(j, i, f"{v:.0f}", ha="center", va="center",
                    fontsize=7.5, color=color)
    ax.set_xticks(range(len(strategies)))
    ax.set_xticklabels(strategies, rotation=30, ha="right")
    ax.set_yticks(range(len(cfg_order)))
    ax.set_yticklabels([LABEL.get(c, c) for c in cfg_order])
    ax.set_title("Per-strategy accuracy (%)")
    fig.colorbar(im, ax=ax, fraction=0.03, pad=0.03)
    save(fig, "fig_strategy_heatmap")


# --------------------------------------------------------------------------- #
# F10 — Domain heatmap                                                         #
# --------------------------------------------------------------------------- #
def fig_domain_heatmap():
    domains, data = parse_per_domain()
    cfgs = parse_per_config()
    cfg_order = [c["config"] for c in sorted(cfgs, key=lambda c: c["acc"], reverse=True)]
    M = np.array([data[c] for c in cfg_order if c in data])
    fig, ax = plt.subplots(figsize=(5.6, 5.6))
    im = ax.imshow(M, cmap="RdYlGn", vmin=35, vmax=95, aspect="auto")
    for i in range(M.shape[0]):
        for j in range(M.shape[1]):
            v = M[i, j]
            color = "white" if v < 50 or v > 88 else "black"
            ax.text(j, i, f"{v:.0f}", ha="center", va="center",
                    fontsize=7.5, color=color)
    ax.set_xticks(range(len(domains)))
    ax.set_xticklabels(domains, rotation=25, ha="right")
    ax.set_yticks(range(len(cfg_order)))
    ax.set_yticklabels([LABEL.get(c, c) for c in cfg_order])
    ax.set_title("Per-domain accuracy (%)")
    fig.colorbar(im, ax=ax, fraction=0.03, pad=0.03)
    save(fig, "fig_domain_heatmap")


# --------------------------------------------------------------------------- #
# F11 — Zero-correct donut                                                     #
# --------------------------------------------------------------------------- #
def fig_zero_correct_donut():
    # Hardcoded from zero_correct_97_audit.md (already documented in CURRENT_STATUS):
    #   54 DROP (defect), 29 REVIEW, 14 RETAIN out of 97
    labels = ["Defect — drop (54)", "Borderline — review (29)", "Genuinely hard — retain (14)"]
    sizes = [54, 29, 14]
    colors = ["#DC2626", "#F59E0B", "#16A34A"]
    fig, ax = plt.subplots(figsize=(4.0, 3.4))
    wedges, _texts, autotexts = ax.pie(
        sizes, labels=labels, colors=colors, autopct="%1.0f%%",
        wedgeprops=dict(width=0.45, edgecolor="white"),
        textprops=dict(fontsize=8))
    for at in autotexts:
        at.set_color("white")
        at.set_fontweight("bold")
    ax.set_title("Audit of 97 zero-correct items\n(items every model got wrong)", fontsize=9)
    save(fig, "fig_zero_correct_donut")


# --------------------------------------------------------------------------- #
# F12 — Item correctness histogram                                             #
# --------------------------------------------------------------------------- #
def fig_item_histogram():
    counts = parse_item_histogram()
    ks = [k for k, _ in counts]
    ns = [n for _, n in counts]
    fig, ax = plt.subplots(figsize=(5.6, 3.2))
    bars = ax.bar(ks, ns, color="#6366F1", edgecolor="black", linewidth=0.4)
    for k, n in zip(ks, ns):
        if n >= 100:
            ax.text(k, n + 8, str(n), ha="center", fontsize=7)
    # highlight floor
    for b, k in zip(bars, ks):
        if k <= 1:
            b.set_color("#DC2626")
        elif k >= 15:
            b.set_color("#16A34A")
    ax.set_xlabel("Number of configs (out of 16) answering correctly")
    ax.set_ylabel("# questions")
    ax.set_xticks(range(0, 17))
    ax.set_title("Item-correctness distribution across 3,266 questions")
    save(fig, "fig_item_histogram")


# --------------------------------------------------------------------------- #
def main():
    fig_leaderboard()
    fig_reasoning_lift()
    fig_sps_heatmap()
    fig_sps_lollipop()
    fig_pareto_cost()
    fig_cb_vs_source()
    fig_cb_scatter()
    fig_difficulty_calib()
    fig_strategy_heatmap()
    fig_domain_heatmap()
    fig_zero_correct_donut()
    fig_item_histogram()
    print(f"all figures written to {OUT.relative_to(ROOT)}/")


if __name__ == "__main__":
    main()
