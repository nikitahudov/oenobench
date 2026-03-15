# OenoBench — Claude Code Scraper Prompts

Each prompt below is a standalone task for a separate Claude Code session.
Scrapers 1-4 (Wikidata, Wikipedia, HuggingFace, UC Davis) are complete.
Run remaining scrapers in order (5→14).

After each session: `git push` from Claude Code, then on server: `git pull && python -m src.scrapers.<name> --dry-run`

---

## SHARED CONTEXT (paste at the top of every prompt)

```
CONTEXT FOR ALL SCRAPERS:

I'm building OenoBench, a wine knowledge LLM benchmark targeting NeurIPS 2026.
The repo is at ~/oenobench. The codebase has:

- src/utils/db.py — Connection helpers: get_pg(), get_es(), get_neo4j(), get_redis()
- src/utils/facts.py — ensure_source(name, url, source_type, tier, language), insert_facts_batch(), insert_fact(), get_fact_count()
- src/scrapers/wikidata.py — reference scraper (20,910 facts)
- src/scrapers/wikipedia.py — Wikipedia scraper (reference for patterns)
- src/scrapers/huggingface.py — HuggingFace datasets (16,514 facts)
- src/scrapers/ucdavis.py — UC Davis ontology/AVA/FPS (reference for multi-source scraper pattern)
- requirements.txt — all dependencies

READ src/utils/facts.py AND src/scrapers/ucdavis.py FIRST to understand the patterns.

Every scraper MUST:
1. Follow the same CLI pattern: --all, --list, --dry-run, plus source-specific options
2. Use ensure_source() to register each source URL before inserting facts
3. Use insert_facts_batch() for bulk inserts (handles dedup on exact fact_text)
4. Set appropriate domain values: "wine_regions", "grape_varieties", "producers", "viticulture", "winemaking", "wine_business"
5. Generate atomic facts (one fact per sentence, e.g. "Barolo DOCG requires 100% Nebbiolo.")
6. Never store verbatim source text — always rephrase into atomic facts
7. Log to data/logs/<scraper_name>_{time}.log
8. Rate-limit all HTTP requests (details per scraper below)
9. Set User-Agent: "OenoBench-Research/1.0 (academic wine benchmark)"

QUALITY CHECKS — every scraper must include a --validate flag that:
a) Counts facts per domain/subdomain and prints a distribution table
b) Checks for suspiciously short facts (<5 words) or long facts (>50 words)
c) Checks for facts that are just entity names with no predicate (e.g. "Merlot.")
d) Checks for duplicate-ish facts using simple string containment (not just exact match)
e) Reports % of facts with entities populated vs empty
f) Prints 10 random sample facts for manual eyeballing

Example validate output:
  Domain distribution:
    wine_regions:    342 facts
    grape_varieties: 128 facts
  Quality:
    Too short (<5 words): 3 (0.6%)
    Too long (>50 words):  7 (1.4%)
    Missing entities:      12 (2.4%)
    Possible near-dupes:   8 (1.6%)
  Sample facts:
    1. "Barolo DOCG is located in Piedmont, Italy."
    2. "Nebbiolo is the sole permitted grape in Barolo."
    ...

Commit and push when done. I'll pull on the server and test.
```

---

## SCRAPER 3: HuggingFace Datasets
**File:** `src/scrapers/huggingface.py`
**Schedule:** Week 1 | **Target:** 1,500-2,500 facts

```
Build src/scrapers/huggingface.py that extracts wine facts from HuggingFace datasets.

[PASTE SHARED CONTEXT ABOVE]

SPECIFIC REQUIREMENTS:

1. DATASETS TO PROCESS:
   a) spawn99/wine-reviews (281K rows, CC BY-NC-SA 4.0)
      Columns: country, description, designation, points, price, province, region_1, region_2, taster_name, title, variety, winery
   b) christopher/winesensed (1M+ rows, CC BY-NC-ND 4.0)
      Sensory profiling data — wine-variety-descriptor associations

2. EXTRACTION STRATEGY for wine-reviews:
   - Variety-Region associations: group by (variety, province, country), keep combos with 5+ occurrences
     → "Pinot Noir is grown in the Burgundy region of France."
   - Variety-Province top varieties: top 3 varieties per province by count
     → "The most widely reviewed variety in Napa Valley is Cabernet Sauvignon."
   - Producer-Region links: group by (winery, province, country), keep wineries with 3+ reviews
     → "Robert Mondavi Winery is a producer in Napa Valley, California, USA."
   - Region-Country mappings: unique province→country
     → "Mendoza is a wine region in Argentina."
   - Price tier associations: average price per variety where 10+ data points exist
     → "Pinot Noir wines from Burgundy have a median price of $45."
   DO NOT extract from the 'description' column (those are copyrighted tasting notes).

3. EXTRACTION STRATEGY for winesensed:
   - Explore the schema first (print column names and sample rows)
   - Extract variety-descriptor patterns where statistically significant
     → "Cabernet Sauvignon is commonly associated with blackcurrant and cedar aromas."
   - Only create facts from patterns with strong support (20+ occurrences)

4. CLI:
   - python -m src.scrapers.huggingface --all
   - python -m src.scrapers.huggingface --dataset wine-reviews
   - python -m src.scrapers.huggingface --dataset winesensed
   - python -m src.scrapers.huggingface --dry-run
   - python -m src.scrapers.huggingface --validate

5. DEPENDENCIES: datasets, pandas (already in requirements.txt)

6. SOURCE REGISTRATION:
   - Source name: "spawn99/wine-reviews (HuggingFace)"
   - URL: "https://huggingface.co/datasets/spawn99/wine-reviews"
   - Tier: "tier_2_authoritative" (derived data)
```

---

## SCRAPER 4: UC Davis Repositories
**File:** `src/scrapers/ucdavis.py`
**Schedule:** Week 1-2 | **Target:** 1,000-2,000 facts

```
Build src/scrapers/ucdavis.py that extracts wine facts from three UC Davis public repositories.

[PASTE SHARED CONTEXT ABOVE]

SPECIFIC REQUIREMENTS:

1. THREE DATA SOURCES:
   a) UC Davis Wine Ontology — https://github.com/UCDavisLibrary/wine-ontology
      - Format: RDF/Turtle files
      - Parse with rdflib (in requirements.txt)
      - Extract: wine entity classifications, property definitions, region-variety relationships
      - License: Open academic

   b) UC Davis AVA Digitizing Project — https://github.com/UCDavisLibrary/ava
      - Format: GeoJSON files (one per AVA)
      - Extract: all 267+ AVA names, parent-child relationships, establishment dates, Federal Register references
      - Facts like: "Napa Valley AVA was established in 1981."
        "Stags Leap District AVA is located within the Napa Valley AVA."
        "There are 267 recognized American Viticultural Areas."
      - License: CC BY 4.0

   c) UC Davis FPS Grape Variety Database — https://fps.ucdavis.edu/fgrabout.cfm
      - Format: HTML pages (structured tables)
      - Extract: 595 grape varieties with TTB-approved names, synonyms, clone counts
      - Facts like: "Cabernet Sauvignon has 32 registered clones in the UC Davis FPS collection."
        "Grüner Veltliner is the TTB-approved name for this Austrian variety."
      - Rate limit: 1 request per 3 seconds
      - License: Public/educational

2. APPROACH:
   - For GitHub repos: clone or download the repos locally, parse files offline (no rate limiting needed)
   - For FPS website: scrape HTML pages respectfully
   - Use rdflib for RDF parsing, json for GeoJSON, beautifulsoup4 for HTML

3. CLI:
   - python -m src.scrapers.ucdavis --all
   - python -m src.scrapers.ucdavis --source ontology
   - python -m src.scrapers.ucdavis --source ava
   - python -m src.scrapers.ucdavis --source fps
   - python -m src.scrapers.ucdavis --dry-run
   - python -m src.scrapers.ucdavis --validate

4. AVA QUALITY CHECK: After insertion, verify the count against the known ~267 AVAs.
   Print a warning if significantly fewer were found.

5. SOURCE REGISTRATION: Register each of the 3 repos as separate sources with tier "tier_1_official".
```

---

## SCRAPER 5: Kaggle Datasets
**File:** `src/scrapers/kaggle_data.py` (not kaggle.py — avoid naming conflicts)
**Schedule:** Week 1-2 | **Target:** 500-1,000 facts

```
Build src/scrapers/kaggle_data.py that extracts wine facts from Kaggle CSV datasets.

[PASTE SHARED CONTEXT ABOVE]

SPECIFIC REQUIREMENTS:

1. DATASETS (user will download CSVs to data/raw/kaggle/ before running):
   a) Wine Quality Dataset (UCI) — red and white wine physicochemical data
      - Extract: typical pH, alcohol, acidity ranges for red vs white wines
      - Facts like: "Red wines typically have a pH between 3.0 and 3.7."
        "White wines generally have higher residual sugar than red wines."
      - Generate statistical summary facts, not per-row facts

   b) Wine Reviews (zynicide/wine-reviews) — 130K reviews
      - Similar to HuggingFace dataset but different source
      - Extract: variety-region associations, producer-region links
      - Deduplicate against HuggingFace facts (many will overlap)

2. APPROACH:
   - Expect CSV files in data/raw/kaggle/ directory
   - Print clear error message if files are missing, with download instructions
   - Use pandas for processing
   - Generate aggregate/statistical facts, not per-row facts

3. CLI:
   - python -m src.scrapers.kaggle_data --all
   - python -m src.scrapers.kaggle_data --dataset wine-quality
   - python -m src.scrapers.kaggle_data --dataset wine-reviews
   - python -m src.scrapers.kaggle_data --dry-run
   - python -m src.scrapers.kaggle_data --validate

4. QUALITY CHECK: Since this overlaps with HuggingFace data, the --validate flag should
   also report how many facts were skipped as duplicates of existing DB facts.

5. SOURCE REGISTRATION: tier "tier_2_authoritative" for UCI, tier "tier_3_reliable" for reviews.
```

---

## SCRAPER 6: INAO — French Appellations
**File:** `src/scrapers/inao.py`
**Schedule:** Week 2-3 | **Target:** 2,000-3,000 facts

```
Build src/scrapers/inao.py that extracts French wine appellation data from INAO.

[PASTE SHARED CONTEXT ABOVE]

SPECIFIC REQUIREMENTS:

1. SOURCE: https://www.inao.gouv.fr — French government appellation authority
   - License: Government/public information (safe for research)
   - This is the single highest-value regulatory source for the project

2. WHAT TO EXTRACT:
   - List of all AOC/AOP wine appellations (~360)
   - For each appellation:
     - Name and type (AOC, AOP, IGP)
     - Region/department
     - Permitted grape varieties (red and white)
     - Maximum yield (hl/ha)
     - Minimum alcohol content
     - Aging requirements (if any)
     - Color(s) produced (red, white, rosé)
   - Geographic hierarchy: region → subregion → appellation

3. APPROACH:
   - First check robots.txt at https://www.inao.gouv.fr/robots.txt
   - Start by scraping the appellation listing/search pages
   - Then follow links to individual appellation pages
   - Some data may be in PDF "cahiers des charges" — use pdfplumber to extract
   - Rate limit: 1 request per 5 seconds (government site, be extra respectful)
   - If the site structure is difficult, fall back to scraping what's accessible
     and note gaps for manual filling later

4. FACT EXAMPLES:
   - "Châteauneuf-du-Pape is an AOC appellation in the Rhône Valley, France."
   - "Châteauneuf-du-Pape AOC permits 13 grape varieties including Grenache, Syrah, and Mourvèdre."
   - "The maximum yield for Châteauneuf-du-Pape AOC red wines is 35 hl/ha."
   - "Châteauneuf-du-Pape AOC requires a minimum alcohol content of 12.5% for red wines."

5. CLI:
   - python -m src.scrapers.inao --all
   - python -m src.scrapers.inao --region rhone (filter by region)
   - python -m src.scrapers.inao --dry-run
   - python -m src.scrapers.inao --validate

6. LANGUAGE: Site is in French. Extract facts and rephrase them in English.
   Use simple translation patterns (AOC names stay in French, but descriptions in English).

7. QUALITY CHECK: After extraction, verify count against known ~360 AOC wine appellations.
   Report how many have complete data (grapes + yield + alcohol) vs partial.

8. FALLBACK: If the INAO site proves too difficult to scrape programmatically,
   create a structured JSON template file (data/raw/inao_template.json) with the
   schema for manual/semi-manual data entry, and document which fields couldn't
   be auto-extracted. Include a note about this in the code.

9. SOURCE REGISTRATION: tier "tier_1_official" (government regulatory body).
```

---

## SCRAPER 7: Italian Wine Registries
**File:** `src/scrapers/italy.py`
**Schedule:** Week 3 | **Target:** 1,500-2,000 facts

```
Build src/scrapers/italy.py that extracts Italian wine appellation data.

[PASTE SHARED CONTEXT ABOVE]

SPECIFIC REQUIREMENTS:

1. SOURCES:
   a) Federdoc — https://www.federdoc.com (consortium of DOC/DOCG consortiums)
   b) Italian Ministry of Agriculture databases (if accessible)
   c) Individual consortium pages as fallback

2. WHAT TO EXTRACT:
   - All 77 DOCG appellations with: name, region, permitted grapes, production rules
   - All 330+ DOC appellations with: name, region, key grapes
   - For each: color(s), aging requirements (Riserva, etc.), yield limits
   - Classification hierarchy: DOCG > DOC > IGT

3. FACT EXAMPLES:
   - "Barolo is a DOCG appellation in the Piedmont region of Italy."
   - "Barolo DOCG requires 100% Nebbiolo grape."
   - "Barolo DOCG wines must be aged for a minimum of 38 months, including 18 months in wood."
   - "Barolo Riserva requires a minimum of 62 months aging."
   - "Italy has 77 DOCG and over 330 DOC wine appellations."

4. LANGUAGE: Sites are in Italian. Translate descriptions to English.
   Appellation names stay in Italian.

5. CLI:
   - python -m src.scrapers.italy --all
   - python -m src.scrapers.italy --type docg (just DOCG)
   - python -m src.scrapers.italy --type doc
   - python -m src.scrapers.italy --dry-run
   - python -m src.scrapers.italy --validate

6. Rate limit: 1 request per 5 seconds.

7. QUALITY CHECK: Verify DOCG count is close to 77. Report completeness
   (how many have full grape + aging data vs just name + region).

8. FALLBACK: Like INAO, if sites are hard to scrape, create a structured template
   and document gaps. The 77 DOCG list at minimum should be achievable since it's
   a well-known fixed list that can be populated from multiple web sources.

9. SOURCE REGISTRATION: tier "tier_1_official" for government data, "tier_2_authoritative" for consortiums.
```

---

## SCRAPER 8: TTB — US Wine Regulations
**File:** `src/scrapers/ttb.py`
**Schedule:** Week 3-4 | **Target:** 500-800 facts

```
Build src/scrapers/ttb.py that extracts US wine regulation data from the TTB.

[PASTE SHARED CONTEXT ABOVE]

SPECIFIC REQUIREMENTS:

1. SOURCE: https://www.ttb.gov — US Alcohol and Tobacco Tax and Trade Bureau
   - License: US Government (public domain)

2. WHAT TO EXTRACT:
   a) AVA listings — name, state, establishment date, Federal Register citation
      (complements UC Davis AVA GeoJSON with regulatory details)
   b) Approved grape variety names — the official TTB list of permitted label names
   c) Key labeling regulations from 27 CFR Part 4:
      - Varietal labeling minimum (75%)
      - AVA labeling requirements (85%)
      - Estate bottled requirements
      - Vintage date rules
      - Alcohol tolerance rules

3. FACT EXAMPLES:
   - "US wine labeled with a varietal name must contain at least 75% of that grape variety."
   - "Wine labeled with an AVA must contain at least 85% grapes from that AVA."
   - "The Willamette Valley AVA was established in 1984 in Oregon."
   - "Estate Bottled wine in the US must be made from grapes grown on land owned or controlled by the winery."

4. CLI:
   - python -m src.scrapers.ttb --all
   - python -m src.scrapers.ttb --source ava
   - python -m src.scrapers.ttb --source varieties
   - python -m src.scrapers.ttb --source regulations
   - python -m src.scrapers.ttb --dry-run
   - python -m src.scrapers.ttb --validate

5. Rate limit: 1 request per 3 seconds. Government site, be respectful.

6. QUALITY CHECK: Cross-reference AVA count with UC Davis data if already loaded.
   Report discrepancies.

7. SOURCE REGISTRATION: tier "tier_1_official" (US government).
```

---

## SCRAPER 9: European Wine Registries (Spain, Germany, Portugal)
**File:** `src/scrapers/europe.py`
**Schedule:** Week 3-4 | **Target:** 1,500-2,400 facts

```
Build src/scrapers/europe.py that extracts wine regulation data from Spain, Germany, and Portugal.

[PASTE SHARED CONTEXT ABOVE]

SPECIFIC REQUIREMENTS:

1. SOURCES:
   a) Spain — https://www.mapa.gob.es + individual DO websites
      - All 68 DO + 2 DOCa (Rioja, Priorat) appellations
      - Permitted varieties, aging categories (Crianza, Reserva, Gran Reserva)
      - Target: 800-1,200 facts

   b) Germany — https://www.deutscheweine.de + https://www.vdp.de
      - 13 Anbaugebiete (wine regions)
      - VDP classification: Gutswein → Ortswein → Erste Lage → Große Lage
      - Prädikat levels: Kabinett, Spätlese, Auslese, Beerenauslese, Trockenbeerenauslese, Eiswein
      - Key varieties by region (Riesling, Spätburgunder, etc.)
      - Target: 400-600 facts

   c) Portugal — https://www.ivdp.pt + https://www.ivv.gov.pt
      - DOC and IGP regions
      - Port wine categories (Ruby, Tawny, Vintage, Vintage, LBV, Vintage/Colheita, Vintage/Vintage)
      - Douro classification details
      - Madeira wine types
      - Target: 400-600 facts

2. CLI:
   - python -m src.scrapers.europe --all
   - python -m src.scrapers.europe --country spain
   - python -m src.scrapers.europe --country germany
   - python -m src.scrapers.europe --country portugal
   - python -m src.scrapers.europe --dry-run
   - python -m src.scrapers.europe --validate

3. LANGUAGE: Sites may be in Spanish/German/Portuguese. Translate to English.
   Appellation names stay in original language.

4. Rate limit: 1 request per 5 seconds per domain.

5. FACT EXAMPLES:
   - "Rioja is one of only two DOCa appellations in Spain."
   - "Spanish Reserva red wines must be aged for at least 36 months, with 12 months in oak."
   - "Germany has 13 official wine-growing regions (Anbaugebiete)."
   - "Mosel is the largest Riesling-producing region in Germany."
   - "Port wine must be produced in the Douro Valley of Portugal."
   - "Tawny Port aged for 10, 20, 30, or 40+ years carries an age indication on the label."

6. QUALITY CHECK: Verify known counts — 70 Spanish DO/DOCa, 13 German regions, ~14 Portuguese DOCs.
   Report completeness per country.

7. FALLBACK: If any site is inaccessible, use Wikipedia data for that country's
   appellations as a structured alternative and document the gap.

8. SOURCE REGISTRATION: tier "tier_1_official" for government sites, "tier_2_authoritative" for trade bodies.
```

---

## SCRAPER 10: New World Wine Regions
**File:** `src/scrapers/newworld.py`
**Schedule:** Week 4 | **Target:** 800-1,200 facts

```
Build src/scrapers/newworld.py that extracts wine data from Australia, New Zealand, South Africa, and South America.

[PASTE SHARED CONTEXT ABOVE]

SPECIFIC REQUIREMENTS:

1. SOURCES:
   a) Australia — https://www.wineaustralia.com
      - 65+ GI zones, regions, subregions
      - Key varieties by region
      - Production statistics
      - Target: 300-400 facts

   b) New Zealand — https://www.nzwine.com
      - Wine regions (Marlborough, Hawke's Bay, Central Otago, etc.)
      - Signature varieties (Sauvignon Blanc, Pinot Noir)
      - Target: 150-200 facts

   c) South Africa — https://www.wosa.co.za
      - Wine of Origin regions, districts, wards
      - Key varieties (Chenin Blanc/Steen, Pinotage)
      - Target: 150-200 facts

   d) South America — Argentina (winesofargentina.org), Chile (winesofchile.org)
      - Major regions (Mendoza, Maipo, Colchagua, etc.)
      - Signature varieties (Malbec, Carménère)
      - Altitude viticulture facts
      - Target: 200-400 facts

2. CLI:
   - python -m src.scrapers.newworld --all
   - python -m src.scrapers.newworld --country australia
   - python -m src.scrapers.newworld --country new-zealand
   - python -m src.scrapers.newworld --country south-africa
   - python -m src.scrapers.newworld --country argentina
   - python -m src.scrapers.newworld --country chile
   - python -m src.scrapers.newworld --dry-run
   - python -m src.scrapers.newworld --validate

3. FACT EXAMPLES:
   - "Barossa Valley is a wine region in South Australia known for Shiraz."
   - "Marlborough produces over 75% of New Zealand's wine."
   - "Pinotage is a cross between Pinot Noir and Cinsaut, created in South Africa in 1925."
   - "Mendoza is Argentina's largest wine region, producing over 70% of the country's wine."
   - "Many Argentine vineyards are planted at altitudes exceeding 1,000 meters."

4. Rate limit: 1 request per 5 seconds per domain.

5. QUALITY CHECK: Verify approximate region counts per country.
   Flag any country with fewer than 50 facts as potentially under-scraped.

6. SOURCE REGISTRATION: tier "tier_2_authoritative" for national wine bodies.
```

---

## SCRAPER 11: EU Regulations & OIV
**File:** `src/scrapers/eu_oiv.py`
**Schedule:** Week 4 | **Target:** 500-800 facts

```
Build src/scrapers/eu_oiv.py that extracts wine regulatory facts from EU legislation and OIV.

[PASTE SHARED CONTEXT ABOVE]

SPECIFIC REQUIREMENTS:

1. SOURCES:
   a) EUR-Lex — https://eur-lex.europa.eu
      - EU wine classification system (PDO/PGI framework)
      - Wine labeling regulations
      - Permitted oenological practices
      - E-Bacchus database of protected wine names
      - License: Public domain (EU law)
      - Target: 300-500 facts

   b) OIV — https://www.oiv.int
      - Global wine production/consumption statistics
      - International oenological codex
      - Grape variety descriptions
      - Target: 200-300 facts

2. WHAT TO EXTRACT:
   - EU PDO vs PGI vs varietal wine definitions
   - Labeling requirements (vintage, variety, region rules)
   - Permitted oenological practices (chaptalisation rules, acidification, etc.)
   - Global statistics: top producing countries, top consuming countries
   - Permitted winemaking additives and processes

3. FACT EXAMPLES:
   - "EU wine regulations recognize three categories: PDO (Protected Designation of Origin), PGI (Protected Geographical Indication), and varietal wines."
   - "Chaptalisation (adding sugar before fermentation) is permitted in northern European wine regions but prohibited in southern regions."
   - "Italy, France, and Spain are the three largest wine-producing countries by volume."
   - "Global wine production in 2023 was approximately 244 million hectolitres."

4. CLI:
   - python -m src.scrapers.eu_oiv --all
   - python -m src.scrapers.eu_oiv --source eurlex
   - python -m src.scrapers.eu_oiv --source oiv
   - python -m src.scrapers.eu_oiv --dry-run
   - python -m src.scrapers.eu_oiv --validate

5. DOMAIN MAPPING: Most facts here go to "wine_business" and "winemaking" domains,
   which are currently underrepresented in our database. This scraper is important
   for balancing coverage.

6. Rate limit: 1 request per 3 seconds.

7. SOURCE REGISTRATION: tier "tier_1_official" for both.
```

---

## SCRAPER 12: Regional Wine Bodies (France)
**File:** `src/scrapers/regional_france.py`
**Schedule:** Week 5 | **Target:** 800-1,500 facts

```
Build src/scrapers/regional_france.py that extracts detailed wine data from French regional interprofession bodies.

[PASTE SHARED CONTEXT ABOVE]

SPECIFIC REQUIREMENTS:

1. SOURCES:
   a) BIVB (Bourgogne) — https://www.bourgogne-wines.com
      - 84 Burgundy appellations
      - Grand Cru vineyard lists (33 Grand Crus)
      - Premier Cru vineyard lists
      - Permitted varieties per appellation
      - Commune-level details
      - Target: 300-500 facts

   b) Comité Champagne — https://www.champagne.fr
      - Champagne production rules (méthode champenoise)
      - Village classifications (Grand Cru, Premier Cru)
      - Permitted grapes (Chardonnay, Pinot Noir, Pinot Meunier)
      - House/maison information
      - Target: 200-300 facts

   c) CIVB (Bordeaux) — https://www.bordeaux.com
      - Bordeaux appellations (60+)
      - 1855 Classification (all 5 growths, 61 châteaux)
      - Saint-Émilion Classification
      - Graves/Pessac-Léognan Classification
      - Production rules
      - Target: 300-500 facts

2. FACT EXAMPLES:
   - "Romanée-Conti is a Grand Cru vineyard in Vosne-Romanée, Burgundy."
   - "Burgundy has 33 Grand Cru appellations."
   - "Champagne must undergo a minimum of 15 months aging on lees for non-vintage."
   - "There are 17 Grand Cru villages in Champagne."
   - "Château Lafite Rothschild is a First Growth (Premier Cru Classé) in the 1855 Classification."
   - "The 1855 Classification of Bordeaux ranks 61 châteaux across five growths."

3. CLI:
   - python -m src.scrapers.regional_france --all
   - python -m src.scrapers.regional_france --region burgundy
   - python -m src.scrapers.regional_france --region champagne
   - python -m src.scrapers.regional_france --region bordeaux
   - python -m src.scrapers.regional_france --dry-run
   - python -m src.scrapers.regional_france --validate

4. Rate limit: 1 request per 5 seconds. Check robots.txt for each domain first.

5. QUALITY CHECKS specific to this scraper:
   - Verify 33 Burgundy Grand Crus found
   - Verify 17 Champagne Grand Cru villages found
   - Verify 61 châteaux in 1855 Classification found
   - These are fixed, well-known lists — missing entries indicate scraping gaps

6. SOURCE REGISTRATION: tier "tier_2_authoritative" (interprofession bodies).
```

---

## SCRAPER 13: Italian Consortiums
**File:** `src/scrapers/consortiums_italy.py`
**Schedule:** Week 5 | **Target:** 400-600 facts

```
Build src/scrapers/consortiums_italy.py that extracts wine data from major Italian wine consortiums.

[PASTE SHARED CONTEXT ABOVE]

SPECIFIC REQUIREMENTS:

1. SOURCES:
   a) Consorzio del Vino Brunello di Montalcino — brunellodimontalcino.it
   b) Consorzio del Barolo e Barbaresco — langhevini.it or consorziobfrolo.it
   c) Consorzio del Chianti Classico — chianticlassico.com
   d) Consorzio di Tutela Prosecco DOC — prosecco.wine

2. WHAT TO EXTRACT PER CONSORTIUM:
   - Production rules (grapes, aging, yields)
   - Geographic boundaries / zones
   - Classification tiers (e.g., Brunello vs Rosso di Montalcino)
   - Key statistics
   - Historical facts (founding dates, first vintages)

3. FACT EXAMPLES:
   - "Brunello di Montalcino DOCG requires 100% Sangiovese and a minimum 5 years aging."
   - "Brunello di Montalcino Riserva requires a minimum of 6 years aging."
   - "Chianti Classico must contain a minimum of 80% Sangiovese."
   - "Chianti Classico Gran Selezione is the highest tier, requiring estate-grown grapes."
   - "Prosecco DOC is produced primarily from the Glera grape variety."

4. CLI:
   - python -m src.scrapers.consortiums_italy --all
   - python -m src.scrapers.consortiums_italy --consortium brunello
   - python -m src.scrapers.consortiums_italy --consortium barolo
   - python -m src.scrapers.consortiums_italy --consortium chianti
   - python -m src.scrapers.consortiums_italy --consortium prosecco
   - python -m src.scrapers.consortiums_italy --dry-run
   - python -m src.scrapers.consortiums_italy --validate

5. LANGUAGE: Sites are in Italian (some have English versions). Use English version where available.

6. Rate limit: 1 request per 5 seconds per domain.

7. SOURCE REGISTRATION: tier "tier_2_authoritative".
```

---

## SCRAPER 14: Academic Journals
**File:** `src/scrapers/academic.py`
**Schedule:** Week 5-6 | **Target:** 500-800 facts

```
Build src/scrapers/academic.py that extracts scientific wine facts from open-access journal abstracts.

[PASTE SHARED CONTEXT ABOVE]

SPECIFIC REQUIREMENTS:

1. SOURCES (abstracts and metadata only — never full text):
   a) OENO One — https://oeno-one.eu (vine and wine sciences)
   b) Vitis — https://pub.jki.bund.de/index.php/VITIS (grapevine research)
   c) Catalyst (AJEV) — https://www.ajevonline.org/content/catalyst

2. APPROACH:
   - Scrape article listing pages to get titles, authors, abstracts, DOIs
   - Extract factual claims from abstracts using pattern matching:
     - Look for sentences with numerical data, definitions, comparisons
     - Focus on conclusions and key findings
   - DO NOT download or process full paper text
   - Rephrase all extracted facts — never quote abstracts verbatim

3. FACT EXAMPLES (the kind of facts to extract from abstracts):
   - "Malolactic fermentation converts malic acid to lactic acid, reducing perceived acidity."
   - "Vine water stress during véraison can increase anthocyanin concentration in red grapes."
   - "Oak aging contributes vanillin, eugenol, and furfural compounds to wine."
   - "Brettanomyces yeast produces 4-ethylphenol, which causes barnyard-like aromas."

4. DOMAIN MAPPING: Most facts map to "viticulture" or "winemaking" — these are
   underrepresented domains that academic sources fill well.

5. CLI:
   - python -m src.scrapers.academic --all
   - python -m src.scrapers.academic --journal oeno
   - python -m src.scrapers.academic --journal vitis
   - python -m src.scrapers.academic --journal catalyst
   - python -m src.scrapers.academic --dry-run
   - python -m src.scrapers.academic --validate

6. Rate limit: 1 request per 5 seconds. Academic sites have limited bandwidth.

7. QUALITY CHECK: Facts from academic sources should be more technical.
   Report the distribution across viticulture/winemaking/other domains.
   Flag any facts that seem too generic ("Wine is made from grapes.").

8. CITATION: Every fact must include the paper DOI in the source attribution.

9. SOURCE REGISTRATION: tier "tier_2_authoritative" with individual paper DOIs.
```

---

## POST-SCRAPING: Gap Analysis & Verification
**File:** `src/scrapers/verify.py`
**Schedule:** Week 6 | Run after all scrapers complete

```
Build src/scrapers/verify.py — a verification and gap analysis tool for the full fact database.

[PASTE SHARED CONTEXT ABOVE]

This is NOT a scraper. It analyzes the existing fact database to find gaps and quality issues.

REQUIREMENTS:

1. DOMAIN COVERAGE REPORT:
   - Count facts per domain vs targets:
     wine_regions: 5,000 target
     grape_varieties: 2,000 target
     producers: 3,000 target
     viticulture: 1,500 target
     winemaking: 1,500 target
     wine_business: 1,000 target
   - Flag domains below 70% of target as "needs attention"

2. GEOGRAPHIC COVERAGE:
   - Check facts mention key countries: France, Italy, Spain, USA, Australia, Germany, Portugal, Argentina, Chile, South Africa, New Zealand, Austria
   - For each country, count facts and flag if below expected threshold
   - Flag if any country in the project plan has zero facts

3. TOPIC COVERAGE (search fact_text for keywords):
   - Viticulture topics: terroir, pruning, rootstock, phylloxera, canopy, harvest, organic, biodynamic
   - Winemaking topics: fermentation, oak, aging, malolactic, fining, filtration, chaptalisation
   - Business topics: labeling, regulation, classification, export, import, pricing
   - Flag topics with zero or very few facts

4. SOURCE DIVERSITY:
   - Count facts per source
   - Flag if any single source contributes >40% of total facts
   - Report tier distribution (tier_1 vs tier_2 vs tier_3)

5. QUALITY AUDIT:
   - Find duplicate or near-duplicate facts (Levenshtein distance or simple substring matching)
   - Find facts with empty entities
   - Find suspiciously short/long facts
   - Find facts that might be opinions rather than facts (containing "best", "greatest", "finest")

6. GENERATE GAP-FILL REPORT:
   - Output a JSON file data/reports/gap_analysis.json with:
     - Underrepresented domains and suggested topics
     - Missing countries/regions
     - Missing key wine entities (well-known regions/grapes not in DB)
   - Check against a hardcoded list of "must have" entities:
     Regions: Bordeaux, Burgundy, Champagne, Napa Valley, Barossa Valley, Rioja, Tuscany, Mosel, Douro, Mendoza
     Grapes: Cabernet Sauvignon, Merlot, Pinot Noir, Chardonnay, Sauvignon Blanc, Riesling, Syrah/Shiraz, Nebbiolo, Sangiovese, Tempranillo
     Producers: Château Lafite, Château Margaux, Opus One, Penfolds, Antinori

7. CLI:
   - python -m src.scrapers.verify --full (complete analysis)
   - python -m src.scrapers.verify --domains (domain coverage only)
   - python -m src.scrapers.verify --geography (geographic coverage only)
   - python -m src.scrapers.verify --quality (quality audit only)
   - python -m src.scrapers.verify --gaps (gap analysis only)

8. Output both to terminal (summary) and to data/reports/ (full JSON reports).
```

---

## Execution Order Summary

| # | Scraper | File | Target Facts | Week |
|---|---------|------|-------------|------|
| 1 | Wikidata | wikidata.py | ✅ 20,910 done | 1 |
| 2 | Wikipedia | wikipedia.py | ✅ done | 1-2 |
| 3 | HuggingFace | huggingface.py | ✅ 16,514 done | 1 |
| 4 | UC Davis | ucdavis.py | ✅ done | 1-2 |
| 5 | Kaggle | kaggle_data.py | 500-1,000 | 1-2 |
| 6 | INAO France | inao.py | 2,000-3,000 | 2-3 |
| 7 | Italy | italy.py | 1,500-2,000 | 3 |
| 8 | TTB (US) | ttb.py | 500-800 | 3-4 |
| 9 | Europe | europe.py | 1,500-2,400 | 3-4 |
| 10 | New World | newworld.py | 800-1,200 | 4 |
| 11 | EU/OIV | eu_oiv.py | 500-800 | 4 |
| 12 | Regional France | regional_france.py | 800-1,500 | 5 |
| 13 | Italian Consortiums | consortiums_italy.py | 400-600 | 5 |
| 14 | Academic | academic.py | 500-800 | 5-6 |
| — | Verify | verify.py | — (analysis) | 6 |
| | **TOTAL** | | **~35,000-42,000 raw** | |

Note: With deduplication across sources, expect 15,000-20,000 unique facts.
