# WineBench — Data Source Inventory & Scraping Strategy

## Overview

This document catalogues every data source for the WineBench fact database,
prioritized by value, ease of access, and legal safety. The goal is 15,000+
verified facts across 6 domains.

**Guiding principles:**
- Start with open/structured data (APIs, datasets, Wikidata) — highest value, lowest risk
- Use official regulatory sources for authoritative facts
- Scrape websites only where necessary, respecting robots.txt and ToS
- Every fact must trace to a documented source

---

## Priority Tiers

### TIER 1 — Start here (Week 1-2)
Open datasets, public APIs, and structured data with clear licensing.
No legal risk. Highest fact density per effort.

### TIER 2 — Core sources (Week 2-4)
Official regulatory and educational resources. Public information
but may require careful scraping. High authority.

### TIER 3 — Supplementary (Week 4-6)
Producer websites, wine databases, publications. Requires respectful
scraping. Fills gaps left by Tier 1-2.

---

## TIER 1: Open Data & Structured Sources

### 1.1 Wikidata (SPARQL API)

| Attribute       | Details |
|-----------------|---------|
| **URL**         | https://query.wikidata.org |
| **Access**      | Free SPARQL API, no auth needed |
| **License**     | CC0 (public domain) |
| **Format**      | JSON/CSV via SPARQL queries |
| **Est. facts**  | 3,000-5,000 |
| **Priority**    | ★★★★★ — Start here first |

**What to extract:**
- Wine regions (Q1131296) — names, countries, parent regions, coordinates
- Grape varieties (Q10978) — names, color, synonyms, origin regions
- Wine appellations (Q454541) — classification type, country, permitted grapes
- Wine producers/wineries (Q156362) — location, founding year, region
- Wine classifications — Bordeaux, Burgundy, Italian DOCG/DOC lists

**Sample SPARQL queries to develop:**

```sparql
# All wine regions with country and coordinates
SELECT ?region ?regionLabel ?country ?countryLabel ?coord WHERE {
  ?region wdt:P31/wdt:P279* wd:Q1131296 .  # instance of wine region
  ?region wdt:P17 ?country .                 # country
  OPTIONAL { ?region wdt:P625 ?coord }       # coordinates
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en" }
}

# All grape varieties with color
SELECT ?grape ?grapeLabel ?color ?colorLabel WHERE {
  ?grape wdt:P31 wd:Q10978 .                # instance of grape variety
  OPTIONAL { ?grape wdt:P462 ?color }        # color
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en" }
}
```

**Scraping approach:** Python with `SPARQLWrapper` library. Rate limit to 1 query/second.
Run batch queries by domain, paginate with LIMIT/OFFSET.

---

### 1.2 spawn99/wine-reviews (Hugging Face)

| Attribute       | Details |
|-----------------|---------|
| **URL**         | https://huggingface.co/datasets/spawn99/wine-reviews |
| **Access**      | Direct download via `datasets` library |
| **License**     | CC BY-NC-SA 4.0 |
| **Format**      | Parquet (281K rows) |
| **Est. facts**  | 1,000-2,000 (derived from entity extraction) |
| **Priority**    | ★★★★★ |

**What to extract:**
- Producer names linked to regions and varieties
- Region-variety associations (what's grown where)
- Tasting descriptor patterns by variety/region
- Price point distributions by region

**Note:** This is originally Wine Enthusiast data. License allows research use
with attribution. Facts extracted will be cross-referenced, not used verbatim.

**Approach:** Load with `datasets` library, run entity extraction (spaCy + LLM)
to identify regions, varieties, producers. Build association database.

---

### 1.3 Wikipedia Wine Articles (MediaWiki API)

| Attribute       | Details |
|-----------------|---------|
| **URL**         | https://en.wikipedia.org/w/api.php |
| **Access**      | Free REST API, no auth needed |
| **License**     | CC BY-SA 3.0 |
| **Format**      | JSON (parsed wikitext) |
| **Est. facts**  | 3,000-4,000 |
| **Priority**    | ★★★★★ |

**Key article categories to scrape:**
- "Wine regions" (~800 articles)
- "Grape varieties" (~500 articles)
- "Wineries" (~1,200 articles)
- "Appellations" (~400 articles)
- "Wine classification" (~100 articles)
- "Viticulture" (~200 articles)
- "Oenology" (~150 articles)

**What to extract:**
- Structured infobox data (region, grape, winery templates)
- Key facts from article text (via LLM extraction)
- Category memberships (for entity classification)
- References/citations (for source verification)

**Approach:** Use `wptools` or direct MediaWiki API. Start with category
crawling to build article list, then extract infobox data programmatically.
Use LLM for unstructured text → fact extraction.

---

### 1.4 UC Davis Wine Ontology

| Attribute       | Details |
|-----------------|---------|
| **URL**         | https://github.com/UCDavisLibrary/wine-ontology |
| **Access**      | Public GitHub repository |
| **License**     | Open (academic) |
| **Format**      | RDF/Turtle |
| **Est. facts**  | 200-500 |
| **Priority**    | ★★★★ |

**What to extract:**
- Wine entity classifications and relationships
- Property definitions (color, type, region associations)
- Example wine entries from Amerine collection

**Approach:** Parse RDF with `rdflib`. Map ontology classes to our Neo4j schema.

---

### 1.5 UC Davis AVA Digitizing Project

| Attribute       | Details |
|-----------------|---------|
| **URL**         | https://github.com/UCDavisLibrary/ava |
| **Access**      | Public GitHub repository |
| **License**     | CC BY 4.0 |
| **Format**      | GeoJSON |
| **Est. facts**  | 500-800 |
| **Priority**    | ★★★★ |

**What to extract:**
- All 267+ American Viticultural Areas (names, boundaries)
- Parent-child AVA relationships (nesting)
- Federal Register references for each AVA
- Establishment dates

**Approach:** Parse GeoJSON files, extract attributes into PostgreSQL.

---

### 1.6 UC Davis FPS Grape Variety Database

| Attribute       | Details |
|-----------------|---------|
| **URL**         | https://fps.ucdavis.edu/fgrabout.cfm |
| **Access**      | Public web pages |
| **License**     | Public/educational |
| **Format**      | HTML (structured pages) |
| **Est. facts**  | 500-1,000 |
| **Priority**    | ★★★★ |

**What to extract:**
- 595 grape varieties with TTB-approved names
- 2,341 individual selections/clones
- Synonyms across countries
- Pedigree information

**Approach:** Scrape variety listing pages. Parse structured HTML tables.

---

### 1.7 Kaggle Wine Datasets

| Attribute       | Details |
|-----------------|---------|
| **URL**         | kaggle.com/datasets (multiple) |
| **Access**      | Free download with Kaggle account |
| **License**     | Varies (mostly CC/public domain) |
| **Format**      | CSV |
| **Est. facts**  | 500-1,000 |
| **Priority**    | ★★★ |

**Key datasets:**
- **Wine Quality Dataset** (UCI) — chemical composition of red/white wines
- **Wine Reviews** (zynicide) — 130K reviews with variety, region, price
- **Wine Ratings** — aggregated rating data

**Approach:** Download CSVs, extract entity associations and factual patterns.
Cross-reference with Wikidata entities.

---

### 1.8 WineSensed Dataset (Hugging Face)

| Attribute       | Details |
|-----------------|---------|
| **URL**         | https://huggingface.co/datasets/christopher/winesensed |
| **Access**      | Direct download |
| **License**     | CC BY-NC-ND 4.0 |
| **Format**      | Parquet (1M+ rows) |
| **Est. facts**  | 500-800 |
| **Priority**    | ★★★ |

**What to extract:**
- Sensory profiling data (tasting descriptors)
- Wine-variety-sensory associations

**Approach:** Load with `datasets`, extract patterns for sensory science questions.

---

## TIER 2: Official & Regulatory Sources

### 2.1 INAO — French Appellations (France)

| Attribute       | Details |
|-----------------|---------|
| **URL**         | https://www.inao.gouv.fr |
| **Access**      | Public web pages, some PDFs |
| **License**     | Government/public information |
| **Format**      | HTML + PDF (cahiers des charges) |
| **Est. facts**  | 2,000-3,000 |
| **Priority**    | ★★★★★ |

**What to extract:**
- All AOC/AOP wine appellations (~360)
- Cahiers des charges: permitted grapes, yields, alcohol levels, aging requirements
- Geographic boundaries and commune lists
- IGP specifications

**Approach:** Scrape appellation listing pages. Download and parse PDFs of
cahiers des charges using `pdfplumber`. Rate-limit to 1 request/5 seconds.
Government data is generally safe to scrape for research.

---

### 2.2 Italian Wine Registries (Federdoc / Ministry)

| Attribute       | Details |
|-----------------|---------|
| **URL**         | https://www.federdoc.com, Italian Ministry databases |
| **Access**      | Public web pages |
| **License**     | Government/public information |
| **Format**      | HTML, PDF |
| **Est. facts**  | 1,500-2,000 |
| **Priority**    | ★★★★ |

**What to extract:**
- All DOCG (77) and DOC (330+) appellations
- Disciplinare di produzione (production rules)
- Permitted grape varieties per appellation
- Yield limits, aging requirements

**Approach:** Scrape Federdoc consortium pages. Parse Italian-language
disciplinare PDFs (use LLM for translation/extraction).

---

### 2.3 TTB — US Appellations & Regulations

| Attribute       | Details |
|-----------------|---------|
| **URL**         | https://www.ttb.gov |
| **Access**      | Public government data |
| **License**     | US Government (public domain) |
| **Format**      | HTML, PDF, some structured data |
| **Est. facts**  | 500-800 |
| **Priority**    | ★★★★ |

**What to extract:**
- AVA listings and establishment details
- US wine labeling regulations (27 CFR Part 4)
- Approved grape variety names list
- Wine import/export rules

**Approach:** Scrape TTB AVA database. Parse CFR regulations.
Complements the UC Davis AVA GeoJSON data with regulatory details.

---

### 2.4 Spanish DO/DOCa Registries

| Attribute       | Details |
|-----------------|---------|
| **URL**         | https://www.mapa.gob.es, individual DO websites |
| **Access**      | Public web pages |
| **License**     | Government/public information |
| **Format**      | HTML, PDF |
| **Est. facts**  | 800-1,200 |
| **Priority**    | ★★★★ |

**What to extract:**
- All DO (68) and DOCa (2) appellations
- Permitted varieties, yields, production methods
- Consejo Regulador rules

---

### 2.5 German VDP / Wine Law

| Attribute       | Details |
|-----------------|---------|
| **URL**         | https://www.vdp.de, https://www.deutscheweine.de |
| **Access**      | Public web pages |
| **License**     | Public information |
| **Format**      | HTML |
| **Est. facts**  | 400-600 |
| **Priority**    | ★★★ |

**What to extract:**
- Anbaugebiete (13 wine regions)
- VDP classification system (Gutswein → Große Lage)
- Prädikat levels and requirements
- Permitted varieties by region

---

### 2.6 Portuguese IVDP & IVV

| Attribute       | Details |
|-----------------|---------|
| **URL**         | https://www.ivdp.pt, https://www.ivv.gov.pt |
| **Access**      | Public web pages |
| **License**     | Government/public information |
| **Format**      | HTML, PDF |
| **Est. facts**  | 400-600 |
| **Priority**    | ★★★ |

**What to extract:**
- DOC and IGP regions
- Port wine categories and regulations
- Douro classification details

---

### 2.7 Wine Australia & NZ Winegrowers

| Attribute       | Details |
|-----------------|---------|
| **URL**         | https://www.wineaustralia.com, https://www.nzwine.com |
| **Access**      | Public web pages, some public datasets |
| **License**     | Public information |
| **Format**      | HTML, PDF, CSV (some) |
| **Est. facts**  | 600-800 |
| **Priority**    | ★★★ |

**What to extract:**
- Australian GI zones, regions, subregions (65+)
- NZ wine regions and subregions
- Production statistics
- Key variety plantings by region

---

### 2.8 South African WOSA / Wine of Origin

| Attribute       | Details |
|-----------------|---------|
| **URL**         | https://www.wosa.co.za |
| **Access**      | Public web pages |
| **License**     | Public information |
| **Format**      | HTML |
| **Est. facts**  | 200-400 |
| **Priority**    | ★★★ |

**What to extract:**
- Wine of Origin regions, districts, wards
- Key grape varieties by region
- Industry statistics

---

### 2.9 EU Wine Regulations (EUR-Lex)

| Attribute       | Details |
|-----------------|---------|
| **URL**         | https://eur-lex.europa.eu |
| **Access**      | Public — EU law is public domain |
| **License**     | Public domain |
| **Format**      | HTML, PDF |
| **Est. facts**  | 300-500 |
| **Priority**    | ★★★ |

**What to extract:**
- EU wine classification system (PDO/PGI framework)
- Labeling regulations
- Oenological practices regulations
- Protected wine names (E-Bacchus database)

---

### 2.10 OIV (International Organisation of Vine and Wine)

| Attribute       | Details |
|-----------------|---------|
| **URL**         | https://www.oiv.int |
| **Access**      | Public pages + some open data |
| **License**     | Public information |
| **Format**      | HTML, PDF, some CSV |
| **Est. facts**  | 300-500 |
| **Priority**    | ★★★ |

**What to extract:**
- Global wine statistics (production, consumption, trade)
- International oenological codex (permitted practices)
- Grape variety descriptions
- Global wine region overview data

---

## TIER 3: Supplementary Sources

### 3.1 Bourgogne Wines (BIVB)

| Attribute       | Details |
|-----------------|---------|
| **URL**         | https://www.bourgogne-wines.com |
| **Access**      | Public pages — check robots.txt |
| **License**     | Public information (interprofession) |
| **Est. facts**  | 300-500 |

**What to extract:** Burgundy appellations (84), Grand Cru/Premier Cru
vineyard lists, permitted varieties, commune details.

---

### 3.2 Comité Champagne

| Attribute       | Details |
|-----------------|---------|
| **URL**         | https://www.champagne.fr |
| **Access**      | Public pages |
| **Est. facts**  | 200-300 |

**What to extract:** Champagne production rules, village classifications,
grape variety rules, methods, house information.

---

### 3.3 Consorzio Websites (Italy)

Key consortiums to scrape:
- Consorzio del Vino Brunello di Montalcino
- Consorzio del Barolo e Barbaresco
- Consorzio del Chianti Classico
- Consorzio di Tutela Prosecco DOC

**Est. facts:** 400-600 total across all consortiums.

---

### 3.4 Bordeaux Wine Council (CIVB)

| Attribute       | Details |
|-----------------|---------|
| **URL**         | https://www.bordeaux.com |
| **Access**      | Public pages |
| **Est. facts**  | 300-500 |

**What to extract:** Bordeaux appellations, 1855 Classification,
Saint-Émilion Classification, Graves Classification, production rules.

---

### 3.5 Open-Access Academic Journals

| Journal | URL | Focus |
|---------|-----|-------|
| **OENO One** | https://oeno-one.eu | Vine and wine sciences |
| **Vitis** | https://pub.jki.bund.de/index.php/VITIS | Grapevine research |
| **Catalyst** | https://www.ajevonline.org/content/catalyst | AJEV discovery reports |

**Est. facts:** 500-800 from abstracts and key findings.
**Approach:** Scrape article metadata and abstracts (not full text).
Extract factual claims via LLM. Always cite the paper.

---

### 3.6 Wine-Searcher (Public Data Only)

| Attribute       | Details |
|-----------------|---------|
| **URL**         | https://www.wine-searcher.com |
| **Access**      | Public pages — strict ToS, check carefully |
| **Est. facts**  | 300-500 |
| **Note**        | ⚠️ Only use clearly public reference data |

**What to extract:** Region profiles (public reference pages),
grape variety reference pages. Do NOT scrape pricing or review data.

---

## Sources to AVOID

| Source | Reason |
|--------|--------|
| **Robert Parker / Wine Advocate** | Paywalled, strict copyright |
| **Wine Spectator** | Paywalled, strict copyright |
| **Jancis Robinson / Purple Pages** | Paywalled, strict copyright |
| **Vivino** | ToS prohibits scraping |
| **Wine-Searcher pricing data** | ToS prohibits scraping commercial data |
| **WSET study materials** | Copyrighted educational content |
| **Oxford Companion to Wine (full text)** | Copyrighted — use for reference only |

---

## Scraping Strategy & Legal Considerations

### General Rules

1. **Always check robots.txt** before scraping any domain
2. **Rate limit all scrapers** — max 1 request per 3-5 seconds
3. **Identify your scraper** — set User-Agent to `WineBench-Research/1.0 (academic research; contact@email)`
4. **Government/regulatory data** — generally safe to scrape (public information)
5. **Interprofession/consortium data** — public promotional information, generally safe
6. **Commercial websites** — check ToS carefully, only extract public reference data
7. **Academic papers** — abstracts and metadata only, not full text
8. **Transform all content** — never store verbatim text passages, extract atomic facts

### Legal Framework

For a research project published at NeurIPS:
- **Fair use (US)** / **Text and data mining exception (EU)** applies to research
- Facts themselves are not copyrightable — only expression is
- We extract and rephrase facts, we don't reproduce original text
- All sources are attributed in the dataset metadata

### Data Storage Approach

```
Raw scrape → Fact extraction (LLM) → Atomic fact → Source attribution → PostgreSQL
                                         ↑
                         Never store original text verbatim.
                         Store rephrased atomic facts with source URL.
```

---

## Collection Schedule

| Week | Focus | Sources | Target Facts |
|------|-------|---------|-------------|
| 1 | Structured data | Wikidata, HF datasets, UC Davis repos | 4,000 |
| 2 | Structured + France | Wikipedia, INAO (start) | 3,000 |
| 3 | Europe regulations | Italy, Spain, Germany, Portugal, EU | 2,500 |
| 4 | New World + remaining | US (TTB), Australia, NZ, South Africa, South America | 2,000 |
| 5 | Supplementary | Consortium sites, BIVB, CIVB, academic journals | 2,000 |
| 6 | Gap filling + verification | Cross-reference, fill category gaps, verify | 1,500 |
| **Total** | | | **15,000** |

---

## Fact Count Targets by Domain

| Domain | Target | Primary Sources |
|--------|--------|-----------------|
| **Wine Regions** | 5,000 | Wikidata, Wikipedia, INAO, Federdoc, TTB, regional bodies |
| **Grape Varieties** | 2,000 | Wikidata, UC Davis FPS, Wikipedia, Wine Grapes references |
| **Producers** | 3,000 | Wikipedia, wine-reviews dataset, consortium member lists |
| **Viticulture** | 1,500 | Academic papers, UC Davis, Wikipedia |
| **Winemaking** | 1,500 | Academic papers, Wikipedia, regulatory docs |
| **Wine Business** | 1,000 | EU regulations, TTB, trade body publications, OIV |
| **TOTAL** | **14,000-16,000** | |

---

## Implementation Priority

Build scrapers in this order:

1. **Wikidata SPARQL** — highest ROI, structured data, no scraping risk
2. **HuggingFace datasets** — download and process, no scraping needed
3. **Wikipedia API** — massive coverage, clear licensing
4. **UC Davis repos** — download from GitHub, parse locally
5. **INAO (France)** — highest-value regulatory source
6. **Italian registries** — second-largest wine regulatory corpus
7. **TTB + other regulatory** — complete regulatory coverage
8. **Consortium/interprofession sites** — fill remaining gaps
9. **Academic journal abstracts** — technical/scientific facts
10. **Gap-filling passes** — targeted scraping for underrepresented areas
