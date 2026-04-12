# OenoBench — Data Collection Summary

Paper-ready summary of the data collection pipeline for NeurIPS 2026.

## Overview

OenoBench collected **38,104 atomic wine facts** from **35 scrapers** covering **22 countries**, drawn from **~580 unique sources** across 15 source types. Every fact traces to a genuinely fetched URL with full provenance.

## Source Inventory

### Source Types

| Source Type | Sources | Facts | % |
|-------------|---------|-------|---|
| Encyclopedia (Wikipedia) | 265 | 13,083 | 34.3% |
| Knowledge Base (Wikidata SPARQL) | 3 | 11,806 | 31.0% |
| Curated Datasets (HuggingFace, Kaggle) | 3 | 4,739 | 12.4% |
| Government Extension (UC IPM, Penn State, Oregon State) | 3 | 1,786 | 4.7% |
| Government Registry (INAO) | 1 | 1,471 | 3.9% |
| Government Data (UC Davis AVA) | 1 | 1,412 | 3.7% |
| Academic Journals (OENO One, Vitis, AJEV) | 279 | 891 | 2.3% |
| Wine Consortiums (9 Italian + Federdoc) | 10 | 681 | 1.8% |
| National Wine Bodies (CIVB, BIVB, CIVC) | 3 | 566 | 1.5% |
| Government Regulations (TTB/eCFR) | 3 | 514 | 1.3% |
| Academic Database (UC Davis FPS) | 1 | 502 | 1.3% |
| Official Wine Bodies (Inter Rhône, Vins de Loire) | 5 | 476 | 1.2% |
| Other (OIV, trade bodies, references) | 4 | 177 | 0.5% |

### Source Tier Distribution

| Tier | Facts | % | Description |
|------|-------|---|-------------|
| Tier 1 — Official | 7,472 | 19.6% | Government registries, regulations, academic databases |
| Tier 2 — Authoritative | 29,199 | 76.6% | Wikipedia, Wikidata, wine bodies, consortiums, journals |
| Tier 3 — Reliable | 1,433 | 3.8% | Curated datasets, reference databases |

## Domain Distribution

| Domain | Facts | % |
|--------|-------|---|
| Wine Regions | 18,943 | 49.7% |
| Producers | 6,215 | 16.3% |
| Grape Varieties | 5,959 | 15.6% |
| Viticulture | 3,635 | 9.5% |
| Wine Business | 1,985 | 5.2% |
| Winemaking | 1,367 | 3.6% |

## Geographic Coverage

| Country | Facts | Top Source |
|---------|-------|-----------|
| General (cross-country) | 11,864 | Wikidata (2,795), HuggingFace (2,095), UC IPM (1,145) |
| Portugal | 6,176 | Wikidata SPARQL (5,755 wine regions) |
| United States | 4,177 | UC Davis AVA (1,412), TTB (515), Wikipedia |
| France | 3,437 | INAO (1,471), Wikipedia (Bordeaux/Champagne/Burgundy) |
| Italy | 3,088 | Wikipedia Italian wine (1,755), Federdoc (434) |
| Germany | 1,659 | Wikipedia (555), Wikidata (395) |
| Spain | 1,543 | Wikidata (714 producers), Wikipedia (388) |
| Australia | 1,247 | Wikipedia (417), Wikidata (257) |
| South Africa | 879 | Wikipedia (347 grape varieties), Wikidata (241) |
| New Zealand | 723 | Wikipedia (280 grape varieties), Wikidata (217) |
| Slovenia | 577 | Wikidata (522 wine regions) |
| Austria | 485 | Wikipedia (246), Wikidata (180 producers) |
| Canada | 480 | Wikipedia (186 producers), Wikidata (115 grape varieties) |
| Hungary | 461 | Wikipedia (212 wine regions), Wikidata (158 grape varieties) |
| England | 361 | Wikipedia (163 wine regions), Wikidata (70 grape varieties) |
| Georgia | 355 | Wikipedia (150 wine regions), Wikidata (145 grape varieties) |
| Greece | 272 | Wikipedia (227 wine regions) |
| Croatia | 147 | Wikipedia (76 wine regions) |
| Chile | 104 | Kaggle (59 producers) |
| Argentina | 43 | Kaggle (27 wine regions) |
| Israel | 24 | Kaggle (11 producers) |
| Lebanon | 2 | Kaggle (2 producers) |

## Fact Processing Pipeline

Every scraped text passes through a 5-stage pipeline (`src/scrapers/_fact_processing.py`):

1. **Sentence Decomposition** (`decompose_sentence`) — Split compound sentences at conjunctions. Cap at 30 words. Prepend subject to fragments that lose context.
2. **Reference Resolution** (`resolve_references`) — Replace leading pronouns (He/She/It/They/The estate) with explicit entity names from article context.
3. **Domain Classification** (`classify_domain`) — Keyword-based classification into 6 wine domains. Priority-ordered scoring to avoid default wine_regions bias.
4. **Fact Validation** (`validate_fact`) — Reject: <5 words, >30 words, no verb, unresolved pronoun, no predicate structure.
5. **On-Topic Filtering** (`is_on_topic`) — Region-specific keyword sets reject facts about unrelated wine regions (e.g., Austrian facts in a Bordeaux scraper).

### Wikidata SPARQL Methodology

Country-scoped queries using `P17` (country) property — NOT transitive `P131*` which caused cross-region contamination in initial implementations. Four query templates:
- Wine regions: `P31/P279* → Q1131296 ∪ Q10864048` + `P17 = country QID`
- Wineries: `P31/P279* → Q156362` + `P17 = country QID`
- Grape varieties: `P31/P279* → Q10978` + `P495 = country QID`
- Appellations: `P31/P279* → Q454541` + `P17 = country QID`

Post-filtered with `run_sparql_filtered()` using per-scraper region keyword sets.

## Quality Assurance

### Automated Validation (Phase 3)

| Check | Before | After |
|-------|--------|-------|
| Total facts | 40,020 | 38,104 |
| Dangling references | 305 | 0 |
| Marketing/promotional text | 175 | 0 |
| Over 50 words | 24 | 0 |
| Under 5 words | 31 | 0 |
| Near-duplicates | 375 pairs | 0 |
| Wikipedia disambiguation leaks | 3 | 0 |
| Website boilerplate | 13 | 0 |
| Facts with entities | 94.5% | 94.5% |

### Provenance Audit

The project underwent a comprehensive provenance audit (April 2026) that discovered 17 of the original 30 scrapers contained hardcoded LLM-generated data disguised as scraped content. All 17 were rebuilt from scratch with genuine external data sources. This audit-and-rebuild process strengthens the dataset's scientific integrity.

**Key findings:**
- 10 original scrapers verified genuine (~13,718 facts)
- 8 scrapers had quality issues fixed (SPARQL scoping, fact atomicity, domain classification)
- 17 scrapers completely rebuilt (hardcoded data purged, genuine scraping pipelines created)
- Net codebase change: -26,000+ lines of hardcoded data removed

## Limitations & Known Gaps

1. **Portugal over-representation** (16.2% of all facts) — Wikidata has extensive Portuguese administrative region data
2. **wine_regions domain bias** (49.7%) — inherent in geographic data sources
3. **Low coverage countries** — Argentina (43), Chile (104), Lebanon (2), Israel (24) need additional sources
4. **Unreachable official sites** — inter-rhone.com, brunellodimontalcino.it, franciacorta.wine
5. **910 semi-atomic facts** (31-50 words) — confidence-reduced but not split
6. **Wikipedia temporal bias** — facts reflect current Wikipedia state, not historical accuracy
