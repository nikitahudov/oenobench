# OenoBench — Current Status & Progress

**Last updated:** March 2026  
**Project phase:** Phase 1 — Data Collection  
**Target venue:** NeurIPS 2026 Datasets & Benchmarks Track (~May 15, 2026 deadline)

---

## Timeline Overview (30 weeks)

| Phase | Weeks | Status |
|-------|-------|--------|
| 1. Infrastructure & Data Collection | 1-6 | 🟡 In progress |
| 2. Question Generation | 7-12 | ⬜ Not started |
| 3. AI Validation | 13-16 | ⬜ Not started |
| 4. Human Review & Control Set | 17-20 | ⬜ Not started |
| 5. Evaluation & Analysis | 21-24 | ⬜ Not started |
| 6. Publication & Release | 25-30 | ⬜ Not started |

---

## Phase 1: Data Collection Progress

### Infrastructure ✅

- PostgreSQL, Elasticsearch, Neo4j, Redis all running in Docker containers
- Git repository structure established
- `src/utils/db.py` and `src/utils/facts.py` utilities working
- pgAdmin available for data inspection
- Universal `--test-run` feature across scrapers

### Scraper Status

| # | Scraper | File | Target | Actual | Status |
|---|---------|------|--------|--------|--------|
| 1 | Wikidata | `wikidata.py` | 3,000-5,000 | **20,910** | ✅ Complete |
| 2 | Wikipedia | `wikipedia.py` | 3,000-4,000 | — | ✅ Complete (reference) |
| 3 | HuggingFace | `huggingface.py` | 1,500-2,500 | **16,514** | ✅ Complete |
| 4 | UC Davis | `ucdavis.py` | 1,000-2,000 | — | ⬜ Prompt ready |
| 5 | Kaggle | `kaggle_data.py` | 500-1,000 | — | ⬜ Prompt ready |
| 6 | INAO (France) | `inao.py` | 2,000-3,000 | — | ⬜ Prompt ready |
| 7 | Italy | `italy.py` | 1,500-2,000 | — | ⬜ Prompt ready |
| 8 | TTB (US) | `ttb.py` | 500-800 | — | ⬜ Prompt ready |
| 9 | Europe (ES/DE/PT) | `europe.py` | 1,500-2,400 | — | ⬜ Prompt ready |
| 10 | New World | `newworld.py` | 800-1,200 | — | ⬜ Prompt ready |
| 11 | EU/OIV | `eu_oiv.py` | 500-800 | — | ⬜ Prompt ready |
| 12 | Regional France | `regional_france.py` | 800-1,500 | — | ⬜ Prompt ready |
| 13 | Italian Consortiums | `consortiums_italy.py` | 400-600 | — | ⬜ Prompt ready |
| 14 | Academic | `academic.py` | 500-800 | — | ⬜ Prompt ready |
| — | Verify | `verify.py` | — | — | ⬜ Prompt ready |

**Total raw facts collected:** ~38,000+  
**Target after dedup:** 15,000-20,000 unique facts

### Key Learnings So Far

1. **Quality over quantity** — Atomic fact extraction works better than accepting verbose or compound statements
2. **Validation before full runs** — Always use SQL queries in pgAdmin to inspect data quality before committing to full scraper runs
3. **Claude Code workflow** — Using Claude Code prompts rather than direct code implementation has been more effective. 14 comprehensive scraper prompts have been created.
4. **Wikidata overperformed** — 20,910 facts vs 3,000-5,000 target, excellent structured data source
5. **HuggingFace contributed well** — 16,514 facts from wine review datasets

---

## Domain Coverage Assessment (Estimated)

Based on completed scrapers, coverage is currently weighted toward regions and varieties. Upcoming scrapers should balance this:

| Domain | Current Coverage | Scrapers That Will Help |
|--------|-----------------|-------------------------|
| Wine Regions | 🟢 Good | Scrapers 6-10, 12 |
| Grape Varieties | 🟢 Good | Scrapers 4, 6-10 |
| Producers | 🟡 Moderate | Scrapers 12, 13 |
| Viticulture | 🔴 Low | Scrapers 14 (academic) |
| Winemaking | 🔴 Low | Scrapers 11, 14 (academic) |
| Wine Business | 🔴 Low | Scrapers 8, 11 |

---

## Next Steps

1. Implement scrapers 4-14 using prompts in `docs/SCRAPER_PROMPTS.md`
2. Run `verify.py` gap analysis after completing scraper batch
3. Begin question generation pipeline design (Phase 2)
4. Set up multi-model LLM API access for question generation
5. Design evaluation framework and scoring pipeline
