"""
OenoBench — Fact Quality Analysis

Analyzes the facts database to test quality hypotheses:
  H1: Domain coverage gaps (viticulture, winemaking underrepresented)
  H2: Source quality & balance (Wikidata/HuggingFace dominance)
  H3: Atomicity issues (multi-sentence, compound facts)

Usage:
    python -m src.analysis.fact_quality
    python -m src.analysis.fact_quality --hypothesis h1
    python -m src.analysis.fact_quality --hypothesis h2
    python -m src.analysis.fact_quality --hypothesis h3
    python -m src.analysis.fact_quality --json data/reports/quality.json
"""

import json
import re
import random
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

import click

from src.utils.db import get_pg

# ─── Target Proportions ─────────────────────────────────────────────────────
# Derived from PROJECT_PLAN.md question targets, converted to fact shares.

DOMAIN_TARGETS = {
    "wine_regions": 0.35,
    "winemaking": 0.20,
    "viticulture": 0.15,
    "grape_varieties": 0.12,
    "wine_business": 0.10,
    "producers": 0.08,
}

# ─── Pattern Regexes ────────────────────────────────────────────────────────

# Wikidata boilerplate patterns
RE_GEO_BOILERPLATE = re.compile(
    r"^.+ is (located|situated) (in|within) (the )?.+\.$", re.IGNORECASE
)
RE_REGION_BOILERPLATE = re.compile(
    r"^.+ is a (wine region|wine area|wine-producing) (in|of) .+\.$", re.IGNORECASE
)
RE_APPELLATION_BOILERPLATE = re.compile(
    r"^.+ is an? (AOC|AOP|DOC|DOCG|IGP|IGT|AVA) appellation (in|of) .+\.$",
    re.IGNORECASE,
)

# HuggingFace patterns
RE_PRODUCER_REGION = re.compile(
    r"(is a (winery|wine producer|vineyard|producer)|produces wine in|"
    r"is (located|based|situated) in .+ (region|area|valley|county))",
    re.IGNORECASE,
)
RE_VARIETY_REGION = re.compile(
    r"(is (commonly |widely )?(grown|planted|cultivated) in|"
    r"is a (key|major|primary|dominant) (grape|variety) in)",
    re.IGNORECASE,
)
RE_PRICE_STAT = re.compile(
    r"(average|median|typically|price|rating|point|score)", re.IGNORECASE
)

# Multi-sentence detection (exclude common abbreviations)
RE_MULTI_SENTENCE = re.compile(
    r"(?<!U\.S)(?<!St)(?<!Mt)(?<!Dr)(?<!vs)(?<!Mr)(?<!Mrs)(?<!Jr)"
    r"\.\s+[A-Z]"
)

# Trivial/tautological patterns
RE_TRIVIAL = re.compile(
    r"^[A-Z][^.]{2,40} is a (wine|grape|grape variety|winery|vineyard|"
    r"wine region|wine producer|red wine|white wine)\.$",
    re.IGNORECASE,
)

# Verbs for atomicity check
RE_VERB = re.compile(
    r"\b(is|are|was|were|has|have|had|produces?|grows?|requires?|"
    r"allows?|contains?|makes?|uses?|covers?|includes?|"
    r"permits?|located|situated|known|classified|designated|"
    r"established|founded|created|produces|planted|cultivated)\b",
    re.IGNORECASE,
)

# Winemaking keywords (for misclassification check)
WINEMAKING_KW = re.compile(
    r"\b(ferment|barrel|oak|aging|ageing|maceration|yeast|malolactic|"
    r"pressing|bottling|fining|filtration|tannin|phenolic)\b",
    re.IGNORECASE,
)
VITICULTURE_KW = re.compile(
    r"\b(pruning|canopy|rootstock|harvest|yield|vine training|"
    r"trellising|irrigation|phylloxera|grafting|dormancy)\b",
    re.IGNORECASE,
)


# ─── Data Loading ────────────────────────────────────────────────────────────


def load_domain_counts():
    """Count facts per domain."""
    cur = get_pg().cursor()
    cur.execute("SELECT domain, count(*) AS cnt FROM facts GROUP BY domain ORDER BY cnt DESC")
    return {row["domain"]: row["cnt"] for row in cur.fetchall()}


def load_source_domain_matrix():
    """Cross-tabulation of source x domain."""
    cur = get_pg().cursor()
    cur.execute("""
        SELECT
            CASE
                WHEN s.name = 'Wikidata' THEN 'Wikidata'
                WHEN s.name LIKE 'Wikipedia:%%' THEN 'Wikipedia'
                WHEN s.name LIKE '%%HuggingFace%%' THEN 'HuggingFace'
                WHEN s.name LIKE 'UC Davis%%' THEN 'UC Davis'
                WHEN s.name LIKE 'Kaggle%%' THEN 'Kaggle'
                WHEN s.name LIKE 'INAO%%' THEN 'INAO'
                WHEN s.name LIKE 'OENO One%%' THEN 'OENO One'
                WHEN s.name LIKE 'Vitis%%' THEN 'Vitis'
                ELSE s.name
            END AS source_group,
            f.domain,
            count(*) AS cnt
        FROM facts f JOIN sources s ON f.source_id = s.id
        GROUP BY source_group, f.domain
        ORDER BY cnt DESC
    """)
    matrix = defaultdict(lambda: defaultdict(int))
    source_totals = defaultdict(int)
    for row in cur.fetchall():
        matrix[row["source_group"]][row["domain"]] = row["cnt"]
        source_totals[row["source_group"]] += row["cnt"]
    return dict(matrix), dict(source_totals)


def load_text_stats():
    """Aggregate text metrics via SQL."""
    cur = get_pg().cursor()
    cur.execute("""
        SELECT
            count(*) AS total,
            count(*) FILTER (WHERE array_length(string_to_array(fact_text, ' '), 1) < 5)
                AS short_facts,
            count(*) FILTER (WHERE array_length(string_to_array(fact_text, ' '), 1) > 30)
                AS long_facts,
            count(*) FILTER (WHERE array_length(string_to_array(fact_text, ' '), 1) > 50)
                AS very_long_facts,
            count(*) FILTER (WHERE confidence < 0.7) AS low_confidence,
            count(*) FILTER (WHERE entities::text = '[]' OR entities IS NULL)
                AS empty_entities,
            round(avg(array_length(string_to_array(fact_text, ' '), 1))::numeric, 1)
                AS avg_words
        FROM facts
    """)
    return dict(cur.fetchone())


def load_word_count_histogram():
    """Word count distribution in buckets."""
    cur = get_pg().cursor()
    cur.execute("""
        SELECT
            CASE
                WHEN array_length(string_to_array(fact_text, ' '), 1) <= 5 THEN '01-05'
                WHEN array_length(string_to_array(fact_text, ' '), 1) <= 10 THEN '06-10'
                WHEN array_length(string_to_array(fact_text, ' '), 1) <= 15 THEN '11-15'
                WHEN array_length(string_to_array(fact_text, ' '), 1) <= 20 THEN '16-20'
                WHEN array_length(string_to_array(fact_text, ' '), 1) <= 30 THEN '21-30'
                ELSE '31+'
            END AS bucket,
            count(*) AS cnt
        FROM facts GROUP BY bucket ORDER BY bucket
    """)
    return [(row["bucket"], row["cnt"]) for row in cur.fetchall()]


def load_sample_facts(source_pattern=None, domain=None, limit=1000):
    """Load random sample of facts, optionally filtered."""
    cur = get_pg().cursor()
    conditions = []
    params = []
    if source_pattern:
        conditions.append("s.name ILIKE %s")
        params.append(f"%{source_pattern}%")
    if domain:
        conditions.append("f.domain = %s")
        params.append(domain)
    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    cur.execute(
        f"""
        SELECT f.fact_text, f.domain, f.confidence, s.name AS source_name
        FROM facts f JOIN sources s ON f.source_id = s.id
        {where}
        ORDER BY random() LIMIT %s
        """,
        params + [limit],
    )
    return cur.fetchall()


def load_confidence_histogram():
    """Confidence score distribution."""
    cur = get_pg().cursor()
    cur.execute("""
        SELECT
            CASE
                WHEN confidence >= 1.0 THEN '1.00'
                WHEN confidence >= 0.9 THEN '0.90-0.99'
                WHEN confidence >= 0.8 THEN '0.80-0.89'
                WHEN confidence >= 0.7 THEN '0.70-0.79'
                WHEN confidence >= 0.5 THEN '0.50-0.69'
                ELSE '<0.50'
            END AS bucket,
            count(*) AS cnt
        FROM facts GROUP BY bucket ORDER BY bucket DESC
    """)
    return [(row["bucket"], row["cnt"]) for row in cur.fetchall()]


def load_near_duplicates(prefix_len=40, min_count=3, limit=20):
    """Find facts sharing the same prefix."""
    cur = get_pg().cursor()
    cur.execute(
        """
        SELECT left(fact_text, %s) AS prefix, count(*) AS cnt
        FROM facts GROUP BY prefix HAVING count(*) > %s
        ORDER BY cnt DESC LIMIT %s
        """,
        [prefix_len, min_count, limit],
    )
    return cur.fetchall()


def load_entity_stats_by_domain():
    """Entity population rate per domain."""
    cur = get_pg().cursor()
    cur.execute("""
        SELECT
            domain,
            count(*) AS total,
            count(*) FILTER (WHERE entities::text = '[]' OR entities IS NULL)
                AS empty_entities
        FROM facts GROUP BY domain ORDER BY total DESC
    """)
    return cur.fetchall()


# ─── H1: Domain Coverage ────────────────────────────────────────────────────


def analyze_h1(domain_counts, source_matrix, source_totals):
    total = sum(domain_counts.values())
    results = []
    any_critical = False

    for domain, target_pct in sorted(DOMAIN_TARGETS.items(), key=lambda x: -x[1]):
        actual = domain_counts.get(domain, 0)
        actual_pct = actual / total if total else 0
        ratio = actual_pct / target_pct if target_pct else 0
        status = "OK"
        if ratio < 0.3:
            status = "CRITICAL"
            any_critical = True
        elif ratio < 0.5:
            status = "LOW"
        elif ratio > 2.0:
            status = "OVER"
        results.append({
            "domain": domain,
            "actual": actual,
            "actual_pct": actual_pct * 100,
            "target_pct": target_pct * 100,
            "ratio": ratio,
            "status": status,
        })

    # Sources contributing to underrepresented domains
    underrep_sources = {}
    for domain in ["viticulture", "winemaking", "wine_business"]:
        contributors = []
        for source, domains in source_matrix.items():
            if domains.get(domain, 0) > 0:
                contributors.append((source, domains[domain]))
        contributors.sort(key=lambda x: -x[1])
        underrep_sources[domain] = contributors[:5]

    # Sample facts from underrepresented domains
    samples = {}
    for domain in ["viticulture", "winemaking"]:
        samples[domain] = [
            r["fact_text"] for r in load_sample_facts(domain=domain, limit=5)
        ]

    return {
        "pass": not any_critical,
        "results": results,
        "underrep_sources": underrep_sources,
        "samples": samples,
    }


# ─── H2: Source Quality & Balance ────────────────────────────────────────────


def classify_wikidata_fact(text):
    if RE_GEO_BOILERPLATE.match(text):
        return "geographic_boilerplate"
    if RE_REGION_BOILERPLATE.match(text):
        return "region_boilerplate"
    if RE_APPELLATION_BOILERPLATE.match(text):
        return "appellation_boilerplate"
    return "substantive"


def classify_hf_fact(text):
    if RE_PRODUCER_REGION.search(text):
        return "producer_region"
    if RE_VARIETY_REGION.search(text):
        return "variety_region"
    if RE_PRICE_STAT.search(text):
        return "price_statistical"
    return "specific_knowledge"


def analyze_h2(source_totals, sample_size):
    total = sum(source_totals.values())

    # Concentration metrics
    shares = {s: c / total for s, c in source_totals.items()}
    hhi = sum(s ** 2 for s in shares.values())
    top2 = sorted(source_totals.values(), reverse=True)
    top2_share = sum(top2[:2]) / total if len(top2) >= 2 else 1.0

    # Wikidata classification
    wd_facts = load_sample_facts(source_pattern="Wikidata", limit=sample_size)
    wd_classes = defaultdict(int)
    wd_examples = defaultdict(list)
    for row in wd_facts:
        cls = classify_wikidata_fact(row["fact_text"])
        wd_classes[cls] += 1
        if len(wd_examples[cls]) < 3:
            wd_examples[cls].append(row["fact_text"])
    wd_total = len(wd_facts)
    wd_boilerplate_pct = (
        (wd_classes.get("geographic_boilerplate", 0)
         + wd_classes.get("region_boilerplate", 0)
         + wd_classes.get("appellation_boilerplate", 0))
        / wd_total * 100 if wd_total else 0
    )

    # HuggingFace classification
    hf_facts = load_sample_facts(source_pattern="HuggingFace", limit=sample_size)
    hf_classes = defaultdict(int)
    hf_examples = defaultdict(list)
    for row in hf_facts:
        cls = classify_hf_fact(row["fact_text"])
        hf_classes[cls] += 1
        if len(hf_examples[cls]) < 3:
            hf_examples[cls].append(row["fact_text"])
    hf_total = len(hf_facts)

    # Low-information patterns (full DB count)
    cur = get_pg().cursor()
    cur.execute("""
        SELECT count(*) AS cnt FROM facts
        WHERE fact_text ~ E'^[A-Z][^.]{2,40} is a (wine|grape|grape variety|winery|vineyard|wine region|wine producer|red wine|white wine)\\.$'
    """)
    trivial_count = cur.fetchone()["cnt"]

    pass_check = wd_boilerplate_pct < 50

    return {
        "pass": pass_check,
        "hhi": hhi,
        "top2_share": top2_share * 100,
        "top_sources": sorted(source_totals.items(), key=lambda x: -x[1])[:10],
        "wikidata": {
            "sample_size": wd_total,
            "classes": dict(wd_classes),
            "boilerplate_pct": wd_boilerplate_pct,
            "examples": dict(wd_examples),
        },
        "huggingface": {
            "sample_size": hf_total,
            "classes": dict(hf_classes),
            "examples": dict(hf_examples),
        },
        "trivial_count": trivial_count,
    }


# ─── H3: Atomicity ──────────────────────────────────────────────────────────


def check_compound(text):
    """Check if a fact contains two independent clauses joined by a conjunction."""
    # Split on ", and " or "; " or " and " (with comma before)
    parts = re.split(r",\s+and\s+|;\s+|\s+and\s+", text, maxsplit=1)
    if len(parts) < 2:
        return False
    # Both parts need a verb to be independent clauses
    return bool(RE_VERB.search(parts[0])) and bool(RE_VERB.search(parts[1]))


def analyze_h3(sample_size):
    # Multi-sentence count (full DB)
    cur = get_pg().cursor()
    cur.execute("SELECT count(*) AS cnt FROM facts")
    total = cur.fetchone()["cnt"]

    # Multi-sentence via sampling (regex too complex for PG)
    all_facts = load_sample_facts(limit=min(sample_size, 5000))
    multi_sentence = []
    compound = []

    for row in all_facts:
        text = row["fact_text"]
        if RE_MULTI_SENTENCE.search(text):
            multi_sentence.append(text)
        elif check_compound(text):
            compound.append(text)

    sample_total = len(all_facts)
    multi_pct = len(multi_sentence) / sample_total * 100 if sample_total else 0
    compound_pct = len(compound) / sample_total * 100 if sample_total else 0
    combined_pct = (len(multi_sentence) + len(compound)) / sample_total * 100 if sample_total else 0

    # Extrapolate to full DB
    est_multi = int(multi_pct / 100 * total)
    est_compound = int(compound_pct / 100 * total)

    # Word count histogram
    histogram = load_word_count_histogram()

    pass_check = combined_pct < 10

    return {
        "pass": pass_check,
        "sample_size": sample_total,
        "total_facts": total,
        "multi_sentence": {
            "count": len(multi_sentence),
            "pct": multi_pct,
            "estimated_total": est_multi,
            "examples": multi_sentence[:5],
        },
        "compound": {
            "count": len(compound),
            "pct": compound_pct,
            "estimated_total": est_compound,
            "examples": compound[:5],
        },
        "combined_pct": combined_pct,
        "histogram": histogram,
    }


# ─── Additional Checks ──────────────────────────────────────────────────────


def analyze_additional(sample_size):
    results = {}

    # Near-duplicates
    dupes = load_near_duplicates()
    results["near_duplicates"] = {
        "groups": len(dupes),
        "top": [(d["prefix"], d["cnt"]) for d in dupes[:10]],
    }

    # Domain misclassification (sample)
    misclass = []
    sample = load_sample_facts(limit=min(sample_size, 3000))
    for row in sample:
        text = row["fact_text"]
        domain = row["domain"]
        issue = None
        if domain == "wine_regions" and WINEMAKING_KW.search(text):
            issue = f"wine_regions fact has winemaking keywords"
        elif domain == "wine_regions" and VITICULTURE_KW.search(text):
            issue = f"wine_regions fact has viticulture keywords"
        elif domain == "producers" and RE_APPELLATION_BOILERPLATE.match(text):
            issue = f"producers fact looks like appellation"
        if issue:
            misclass.append({"fact": text, "domain": domain, "issue": issue})

    results["misclassification"] = {
        "count": len(misclass),
        "sample_size": len(sample),
        "pct": len(misclass) / len(sample) * 100 if sample else 0,
        "examples": misclass[:10],
    }

    # Confidence distribution
    conf_hist = load_confidence_histogram()
    results["confidence"] = conf_hist

    # Entity population by domain
    entity_stats = load_entity_stats_by_domain()
    results["entity_stats"] = [
        {
            "domain": row["domain"],
            "total": row["total"],
            "empty": row["empty_entities"],
            "pct_empty": round(row["empty_entities"] / row["total"] * 100, 1)
            if row["total"]
            else 0,
        }
        for row in entity_stats
    ]

    # Trivial fact count (already computed in H2 but get full count here)
    cur = get_pg().cursor()
    cur.execute("""
        SELECT count(*) AS cnt FROM facts
        WHERE fact_text ~ E'^[A-Z][^.]{2,40} is a (wine|grape|grape variety|winery|vineyard|wine region|wine producer|red wine|white wine)\\.$'
    """)
    results["trivial_facts"] = cur.fetchone()["cnt"]

    return results


# ─── Report Formatting ───────────────────────────────────────────────────────


def status_icon(passed):
    return "PASS" if passed else "FAIL"


def print_header():
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    click.echo("=" * 80)
    click.echo("                     OENOBENCH FACT QUALITY REPORT")
    click.echo(f"                     Generated: {now}")
    click.echo("=" * 80)


def print_summary(h1, h2, h3, additional):
    total = sum(r["actual"] for r in h1["results"])
    click.echo("\nEXECUTIVE SUMMARY")
    click.echo("-" * 40)
    click.echo(f"  Total facts analyzed:  {total:,}")
    click.echo(f"  H1 - Domain Coverage:  {status_icon(h1['pass'])}")
    click.echo(f"  H2 - Source Quality:   {status_icon(h2['pass'])}")
    click.echo(f"  H3 - Atomicity:        {status_icon(h3['pass'])}")
    issues = (
        additional["near_duplicates"]["groups"]
        + (1 if additional["trivial_facts"] > 100 else 0)
        + (1 if additional["misclassification"]["count"] > 0 else 0)
    )
    click.echo(f"  Additional issues:     {issues} found")


def print_h1(h1):
    click.echo("\n" + "=" * 80)
    click.echo(f"H1: DOMAIN COVERAGE GAP  [{status_icon(h1['pass'])}]")
    click.echo("=" * 80)

    click.echo(f"\n  {'Domain':<20s} {'Actual':>8s} {'Actual%':>8s} {'Target%':>8s} {'Ratio':>7s} {'Status':>10s}")
    click.echo("  " + "-" * 65)
    for r in h1["results"]:
        click.echo(
            f"  {r['domain']:<20s} {r['actual']:>8,d} {r['actual_pct']:>7.1f}% "
            f"{r['target_pct']:>7.1f}% {r['ratio']:>7.2f} {r['status']:>10s}"
        )

    click.echo("\n  Sources contributing to underrepresented domains:")
    for domain, contributors in h1["underrep_sources"].items():
        if contributors:
            parts = ", ".join(f"{s} ({c})" for s, c in contributors[:3])
            click.echo(f"    {domain}: {parts}")
        else:
            click.echo(f"    {domain}: NO SOURCES")

    for domain in ["viticulture", "winemaking"]:
        samples = h1["samples"].get(domain, [])
        if samples:
            click.echo(f"\n  Sample {domain} facts:")
            for i, f in enumerate(samples, 1):
                click.echo(f"    {i}. \"{f}\"")


def print_h2(h2):
    click.echo("\n" + "=" * 80)
    click.echo(f"H2: SOURCE QUALITY & BALANCE  [{status_icon(h2['pass'])}]")
    click.echo("=" * 80)

    click.echo(f"\n  Concentration Metrics:")
    click.echo(f"    Herfindahl Index (HHI): {h2['hhi']:.4f}  {'(highly concentrated)' if h2['hhi'] > 0.25 else '(moderate)' if h2['hhi'] > 0.15 else '(diverse)'}")
    click.echo(f"    Top-2 source share:     {h2['top2_share']:.1f}%")

    click.echo(f"\n  Top Sources:")
    for source, count in h2["top_sources"]:
        click.echo(f"    {source:<45s} {count:>6,d}")

    # Wikidata
    wd = h2["wikidata"]
    click.echo(f"\n  Wikidata Quality (sample of {wd['sample_size']}):")
    for cls, cnt in sorted(wd["classes"].items(), key=lambda x: -x[1]):
        pct = cnt / wd["sample_size"] * 100 if wd["sample_size"] else 0
        click.echo(f"    {cls:<30s} {cnt:>5d} ({pct:.1f}%)")
    click.echo(f"    BOILERPLATE TOTAL:         {wd['boilerplate_pct']:.1f}%")
    for cls, examples in wd["examples"].items():
        if examples:
            click.echo(f"\n    Examples ({cls}):")
            for e in examples[:2]:
                click.echo(f"      \"{e}\"")

    # HuggingFace
    hf = h2["huggingface"]
    click.echo(f"\n  HuggingFace Quality (sample of {hf['sample_size']}):")
    for cls, cnt in sorted(hf["classes"].items(), key=lambda x: -x[1]):
        pct = cnt / hf["sample_size"] * 100 if hf["sample_size"] else 0
        click.echo(f"    {cls:<30s} {cnt:>5d} ({pct:.1f}%)")
    for cls, examples in hf["examples"].items():
        if examples:
            click.echo(f"\n    Examples ({cls}):")
            for e in examples[:2]:
                click.echo(f"      \"{e}\"")

    click.echo(f"\n  Trivial facts (full DB): {h2['trivial_count']:,d}")


def print_h3(h3):
    click.echo("\n" + "=" * 80)
    click.echo(f"H3: ATOMICITY  [{status_icon(h3['pass'])}]")
    click.echo("=" * 80)

    click.echo(f"\n  Sample size: {h3['sample_size']:,d} facts")
    ms = h3["multi_sentence"]
    cp = h3["compound"]
    click.echo(f"\n  Multi-sentence facts:  {ms['count']:>5d} ({ms['pct']:.1f}%) est. {ms['estimated_total']:,d} total")
    click.echo(f"  Compound facts:        {cp['count']:>5d} ({cp['pct']:.1f}%) est. {cp['estimated_total']:,d} total")
    click.echo(f"  Combined non-atomic:   {h3['combined_pct']:.1f}%")

    if ms["examples"]:
        click.echo(f"\n  Multi-sentence examples:")
        for i, e in enumerate(ms["examples"][:5], 1):
            click.echo(f"    {i}. \"{e[:120]}{'...' if len(e) > 120 else ''}\"")

    if cp["examples"]:
        click.echo(f"\n  Compound fact examples:")
        for i, e in enumerate(cp["examples"][:5], 1):
            click.echo(f"    {i}. \"{e[:120]}{'...' if len(e) > 120 else ''}\"")

    click.echo(f"\n  Word Count Distribution:")
    click.echo(f"    {'Bucket':<10s} {'Count':>8s} {'%':>7s}")
    click.echo("    " + "-" * 27)
    total = sum(cnt for _, cnt in h3["histogram"])
    for bucket, cnt in h3["histogram"]:
        pct = cnt / total * 100 if total else 0
        bar = "#" * int(pct / 2)
        click.echo(f"    {bucket:<10s} {cnt:>8,d} {pct:>6.1f}% {bar}")


def print_additional(additional):
    click.echo("\n" + "=" * 80)
    click.echo("ADDITIONAL CHECKS")
    click.echo("=" * 80)

    # Near-duplicates
    nd = additional["near_duplicates"]
    click.echo(f"\n  Near-duplicate groups (same first 40 chars, >3 occurrences): {nd['groups']}")
    if nd["top"]:
        click.echo(f"  Top duplicated prefixes:")
        for prefix, cnt in nd["top"][:5]:
            click.echo(f"    ({cnt}x) \"{prefix}...\"")

    # Confidence
    click.echo(f"\n  Confidence Distribution:")
    for bucket, cnt in additional["confidence"]:
        click.echo(f"    {bucket:<12s} {cnt:>8,d}")

    # Entity population
    click.echo(f"\n  Entity Population by Domain:")
    click.echo(f"    {'Domain':<20s} {'Total':>8s} {'Empty':>8s} {'%Empty':>8s}")
    click.echo("    " + "-" * 46)
    for row in additional["entity_stats"]:
        click.echo(
            f"    {row['domain']:<20s} {row['total']:>8,d} "
            f"{row['empty']:>8,d} {row['pct_empty']:>7.1f}%"
        )

    # Misclassification
    mc = additional["misclassification"]
    click.echo(f"\n  Potential Misclassifications: {mc['count']} in sample of {mc['sample_size']} ({mc['pct']:.1f}%)")
    for ex in mc["examples"][:5]:
        click.echo(f"    [{ex['domain']}] \"{ex['fact'][:90]}...\" -> {ex['issue']}")

    # Trivial
    click.echo(f"\n  Trivial/tautological facts: {additional['trivial_facts']:,d}")


def print_recommendations(h1, h2, h3, additional):
    click.echo("\n" + "=" * 80)
    click.echo("RECOMMENDATIONS")
    click.echo("=" * 80)

    recs = []
    if not h1["pass"]:
        recs.append(
            "HIGH: Expand viticulture & winemaking facts. Current coverage is "
            f"{h1['results'][3]['actual_pct']:.1f}% and {h1['results'][4]['actual_pct']:.1f}% "
            "vs targets of 20% and 15%. Consider curated knowledge bases, textbook "
            "extraction, or targeted scraping of UC Davis viticulture resources."
        )
    if not h2["pass"]:
        wd_bp = h2["wikidata"]["boilerplate_pct"]
        recs.append(
            f"HIGH: {wd_bp:.0f}% of Wikidata facts are geographic boilerplate. "
            "Consider filtering low-information patterns or downweighting these "
            "facts during question generation."
        )
    if h2["top2_share"] > 60:
        recs.append(
            f"MEDIUM: Top-2 sources account for {h2['top2_share']:.0f}% of facts. "
            "Diversify by expanding underrepresented scrapers."
        )
    if not h3["pass"]:
        recs.append(
            f"MEDIUM: {h3['combined_pct']:.1f}% of facts appear non-atomic. "
            "Consider splitting multi-sentence and compound facts."
        )
    if additional["near_duplicates"]["groups"] > 50:
        recs.append(
            f"LOW: {additional['near_duplicates']['groups']} near-duplicate groups found. "
            "Run deduplication pass."
        )
    if additional["trivial_facts"] > 500:
        recs.append(
            f"LOW: {additional['trivial_facts']:,d} trivial facts detected. "
            "Consider filtering or flagging for lower priority in question generation."
        )

    if not recs:
        click.echo("\n  No critical issues found.")
    else:
        for i, rec in enumerate(recs, 1):
            click.echo(f"\n  {i}. {rec}")


# ─── CLI ─────────────────────────────────────────────────────────────────────


@click.command()
@click.option("--hypothesis", "-h", type=click.Choice(["h1", "h2", "h3", "all"]),
              default="all", help="Run specific hypothesis or all")
@click.option("--json", "json_path", type=click.Path(), default=None,
              help="Write machine-readable JSON report")
@click.option("--sample-size", type=int, default=1000,
              help="Sample size for pattern analysis")
def main(hypothesis, json_path, sample_size):
    """OenoBench Fact Quality Analysis — Test hypotheses about database quality."""

    print_header()

    # Load shared data
    domain_counts = load_domain_counts()
    source_matrix, source_totals = load_source_domain_matrix()
    text_stats = load_text_stats()

    h1_result = h2_result = h3_result = add_result = None

    if hypothesis in ("h1", "all"):
        click.echo("\nRunning H1: Domain Coverage Analysis...")
        h1_result = analyze_h1(domain_counts, source_matrix, source_totals)

    if hypothesis in ("h2", "all"):
        click.echo("Running H2: Source Quality Analysis...")
        h2_result = analyze_h2(source_totals, sample_size)

    if hypothesis in ("h3", "all"):
        click.echo("Running H3: Atomicity Analysis...")
        h3_result = analyze_h3(sample_size)

    if hypothesis == "all":
        click.echo("Running Additional Checks...")
        add_result = analyze_additional(sample_size)

    # Print report
    if hypothesis == "all" and h1_result and h2_result and h3_result and add_result:
        print_summary(h1_result, h2_result, h3_result, add_result)

    if h1_result:
        print_h1(h1_result)
    if h2_result:
        print_h2(h2_result)
    if h3_result:
        print_h3(h3_result)
    if add_result:
        print_additional(add_result)

    if hypothesis == "all" and h1_result and h2_result and h3_result:
        print_recommendations(h1_result, h2_result, h3_result, add_result or {})

    # JSON output
    if json_path:
        report = {
            "generated_at": datetime.now().isoformat(),
            "total_facts": text_stats["total"],
            "avg_words": float(text_stats["avg_words"]),
        }
        if h1_result:
            report["h1_domain_coverage"] = h1_result
        if h2_result:
            report["h2_source_quality"] = h2_result
        if h3_result:
            report["h3_atomicity"] = h3_result
        if add_result:
            report["additional"] = add_result

        Path(json_path).parent.mkdir(parents=True, exist_ok=True)
        with open(json_path, "w") as f:
            json.dump(report, f, indent=2, default=str)
        click.echo(f"\nJSON report written to {json_path}")


if __name__ == "__main__":
    main()
