# OenoBench — Data Collection Architecture & Workflow

> Comprehensive scheme of the data collection pipeline, agent team coordination,
> and quality assurance process. Intended for use in the NeurIPS 2026 paper.

---

## 1. High-Level Pipeline Overview

The end-to-end data collection pipeline from raw sources to validated atomic facts.

```mermaid
flowchart TB
    subgraph SOURCES["DATA SOURCES"]
        direction TB
        S1["Knowledge Bases\n(Wikidata SPARQL)"]
        S2["Encyclopedias\n(Wikipedia MediaWiki API)"]
        S3["Official Wine Bodies\n(CIVB, BIVB, Inter-Rhone,\naustrianwine.com, etc.)"]
        S4["Government Registries\n(INAO, TTB, eCFR,\ndata.gouv.fr)"]
        S5["Academic Sources\n(OENO One, AJEV,\nVitis, UC Davis)"]
        S6["Datasets\n(HuggingFace, Kaggle,\nUC IPM)"]
    end

    subgraph COLLECTION["COLLECTION LAYER (30 Scrapers)"]
        direction TB
        C1["SPARQL Queries\n(country-scoped via P17,\ndirect P131)"]
        C2["MediaWiki API\n(article extracts,\ncategory crawls,\ninfobox parsing)"]
        C3["Web Scraping\n(session management,\npage discovery,\nsitemap parsing)"]
        C4["API/Dataset Clients\n(HuggingFace load_dataset,\nKaggle CSV, RDF/GeoJSON)"]
    end

    subgraph PROCESSING["FACT PROCESSING PIPELINE"]
        direction TB
        P1["Sentence Decomposition\n(split compound sentences\nat conjunctions)"]
        P2["Reference Resolution\n(replace He/She/It/They\nwith explicit subjects)"]
        P3["Domain Classification\n(keyword-based:\n6 wine domains)"]
        P4["Validation Filter\n(reject: <5 or >30 words,\nno verb, off-topic,\nunresolved pronouns)"]
    end

    subgraph QA["QUALITY ASSURANCE"]
        direction TB
        Q1["Automated Checks\n(--validate per scraper:\ndomain distribution,\nword counts, duplicates)"]
        Q2["Cross-Database Analysis\n(near-duplicates,\ncontradictions,\ncoverage gaps)"]
        Q3["Provenance Audit\n(every fact traces to\na fetched URL)"]
        Q4["Human Expert Review\n(10-sample per scraper,\ndomain verification)"]
    end

    subgraph DB["STORAGE"]
        direction LR
        DB1[("PostgreSQL\n(facts, sources,\nmetadata)")]
        DB2[("Elasticsearch\n(full-text search,\nwine synonyms)")]
        DB3[("Neo4j\n(entity\nrelationships)")]
        DB4[("Redis\n(cache,\nrate limits)")]
    end

    OUTPUT["Validated Atomic Facts\n(target: 20,000+)"]

    SOURCES --> COLLECTION
    COLLECTION --> PROCESSING
    PROCESSING --> DB
    DB --> QA
    QA -->|"issues found"| PROCESSING
    QA -->|"clean"| OUTPUT
```

---

## 2. Fact Processing Pipeline (Detail)

The transformation from raw text to validated atomic facts. This is the core methodology for the paper.

```mermaid
flowchart LR
    RAW["Raw Text\n(Wikipedia extract,\nHTML paragraph,\nSPARQL result)"]

    subgraph DECOMPOSE["1. Decompose"]
        D1["Split at ', and'\n'; ' ', which'"]
        D2["Prepend subject\nto fragments"]
        D3["Cap at 25 words"]
    end

    subgraph RESOLVE["2. Resolve References"]
        R1["Detect leading\npronouns:\nHe/She/It/They"]
        R2["Replace with\nexplicit subject\nfrom article title"]
    end

    subgraph CLASSIFY["3. Classify Domain"]
        CL1["wine_regions"]
        CL2["grape_varieties"]
        CL3["producers"]
        CL4["winemaking"]
        CL5["viticulture"]
        CL6["wine_business"]
    end

    subgraph VALIDATE["4. Validate"]
        V1["Length: 5-30 words"]
        V2["Has verb"]
        V3["No unresolved\npronouns"]
        V4["On-topic for\ntarget region"]
        V5["Wine-relevant\n(keyword match)"]
    end

    ACCEPTED["Accepted\nAtomic Fact"]
    REJECTED["Rejected\n(logged with reason)"]

    RAW --> DECOMPOSE --> RESOLVE --> CLASSIFY --> VALIDATE
    VALIDATE -->|"pass"| ACCEPTED
    VALIDATE -->|"fail"| REJECTED
```

---

## 3. Agent Team Architecture

The multi-agent coordination system using Claude Code Agent Teams.

```mermaid
flowchart TB
    subgraph PHASE0["PHASE 0: Infrastructure (Lead Solo)"]
        direction LR
        P0A["DB Backup"]
        P0B["Build _fact_processing.py\n_web_helpers.py\n_wiki_helpers.py"]
        P0C["Purge 8,821\nhardcoded facts"]
        P0D["Comprehensive\ntesting (0E)"]
        P0A --> P0B --> P0C --> P0D
    end

    subgraph PHASE1["PHASE 1: Team 'scraper-fix' (Lead + 3 Teammates)"]
        direction TB
        LEAD1["Lead\n(escalation handler,\ninfra fixes,\nworktree merges)"]
        T1A["Teammate 1A\n(worktree)\nborderaux.py\nburgundy.py"]
        T1B["Teammate 1B\n(worktree)\nchampagne.py\nitalian_wine_central.py"]
        T1C["Teammate 1C\n(worktree)\naustria.py, greece.py\nconsortiums_italy.py\nttb.py"]
        T1A <-->|"escalation\n& status"| LEAD1
        T1B <-->|"escalation\n& status"| LEAD1
        T1C <-->|"escalation\n& status"| LEAD1
        T1A <-.->|"cross-team\nintel"| T1B
        T1B <-.->|"cross-team\nintel"| T1C
    end

    subgraph PHASE2A["PHASE 2.1: Team 'rebuild-major' (Lead + 7 Teammates)"]
        direction TB
        LEAD2A["Lead\n(rate-limit coord,\nmerges, logging)"]
        T2A1["europe.py\nSpain/Portugal"]
        T2A2["italy.py"]
        T2A3["newworld.py\nAU/NZ/SA"]
        T2A4["rhone_loire\n_alsace.py"]
        T2A5["spain_\nenrichment.py"]
        T2A6["portugal_\nenrichment.py"]
        T2A7["germany_enrichment.py\n+ eu_oiv.py"]
        T2A1 & T2A2 & T2A3 & T2A4 & T2A5 & T2A6 & T2A7 <-->|"rate limits\n& escalation"| LEAD2A
    end

    subgraph PHASE2B["PHASE 2.2: Team 'rebuild-remaining' (Lead + 8 Teammates)"]
        direction TB
        LEAD2B["Lead\n(carries intel\nfrom 2.1)"]
        T2B1["hungary_\ngeorgia.py"]
        T2B2["croatia_\nslovenia.py"]
        T2B3["usa_\nenrichment.py"]
        T2B4["aus_nz_enrichment.py\n+ south_africa.py"]
        T2B5["south_\namerica.py"]
        T2B6["canada.py\n+ england.py"]
        T2B7["lebanon_\nisrael.py"]
        T2B8["eu_oiv.py\n(EU regs)"]
        T2B1 & T2B2 & T2B3 & T2B4 & T2B5 & T2B6 & T2B7 & T2B8 <-->|"rate limits\n& escalation"| LEAD2B
    end

    subgraph PHASE3["PHASE 3: Team 'verification' (Lead + 3 Teammates)"]
        direction TB
        LEAD3["Lead\n(compiles report,\nwrites summary,\nupdates docs)"]
        T3A["Teammate 3A\nPer-scraper\nquality checks\n(--validate all)"]
        T3B["Teammate 3B\nFull-database\nanalysis\n(duplicates, coverage,\nconsistency)"]
        T3C["Teammate 3C\nProvenance audit\n+ sample review\n(10 per scraper)"]
        T3A <-->|"findings"| LEAD3
        T3B <-->|"findings"| LEAD3
        T3C <-->|"findings"| LEAD3
        T3A <-.->|"cross-ref"| T3B
        T3B <-.->|"cross-ref"| T3C
    end

    PHASE0 -->|"gate: tests pass"| PHASE1
    PHASE1 -->|"gate: all merged\n& validated"| PHASE2A
    PHASE2A -->|"intel carried\nforward"| PHASE2B
    PHASE2B -->|"all scrapers\nrebuilt"| PHASE3
    PHASE3 --> REPORT["Final Report\n+ DATA_COLLECTION_SUMMARY.md\n+ PROCESS_LOG.md"]
```

---

## 4. Escalation & Communication Flow

How teammates coordinate within an Agent Team.

```mermaid
sequenceDiagram
    participant Lead
    participant T_A as Teammate A
    participant T_B as Teammate B
    participant T_C as Teammate C
    participant Shared as Shared Task List

    Note over Lead,Shared: Phase start: Lead creates team & assigns tasks

    Lead->>Shared: Create tasks (one per scraper)
    T_A->>Shared: Pick task → "in progress"
    T_B->>Shared: Pick task → "in progress"
    T_C->>Shared: Pick task → "in progress"

    Note over T_A: Encounters _web_helpers.py bug

    T_A->>Lead: ESCALATION: create_session() fails on CIVB<br/>(403, Cloudflare challenge)
    T_A->>T_B: Heads up: CIVB blocked, you may hit same issue
    T_A->>T_C: Heads up: CIVB blocked, you may hit same issue

    Note over Lead: Fixes _web_helpers.py<br/>(adds Cloudflare bypass)

    Lead->>T_A: Fix applied — git pull origin main
    Lead->>T_B: Fix applied — git pull origin main
    Lead->>T_C: Fix applied — git pull origin main

    T_A->>T_A: git pull, resume work
    T_B->>T_B: git pull, continue

    Note over T_B: Discovers site is down

    T_B->>Lead: wineaustralia.com returning 503
    T_B->>T_C: FYI: wineaustralia.com down, using Wikipedia fallback

    Note over T_A: Completes work

    T_A->>Lead: DONE: bordeaux 180 facts, burgundy 95 facts<br/>[--validate output attached]
    T_A->>Shared: Tasks → "completed"
    Lead->>Lead: Merge worktree, review output

    T_B->>Lead: DONE: champagne 340 facts, IWC 720 facts
    T_B->>Shared: Tasks → "completed"

    T_C->>Lead: DONE: austria 310 facts, greece 240 facts,<br/>consortiums 430 facts, ttb 500 facts
    T_C->>Shared: Tasks → "completed"

    Note over Lead: All tasks complete

    Lead->>Lead: Final validation pass<br/>Log to PROCESS_LOG.md<br/>Proceed to next phase
```

---

## 5. Data Source Taxonomy

Classification of all data sources by type and tier.

```mermaid
mindmap
    root((OenoBench\nData Sources))
        Knowledge Bases
            Wikidata SPARQL
                Country-scoped queries P17
                Direct location P131
                Wine region entities
                Grape variety entities
        Encyclopedias
            Wikipedia MediaWiki API
                Key article extracts
                Category tree crawls
                Infobox field parsing
                Wikitext table parsing
        Official Wine Bodies
            French
                CIVB Bordeaux
                BIVB Burgundy
                Inter-Rhone
                Vins de Loire
                Champagne.fr
            European
                Austrian Wine
                German Wines DWI
                Wines of Portugal
                Spanish Wine MAPA
            New World
                Wine Australia
                NZ Wine
                WOSA South Africa
                Wines of Argentina
        Government Registries
            INAO data.gouv.fr
                French appellations
            TTB gov
                US wine regulations
            eCFR
                Code of Federal Regulations
            eAmbrosia
                EU GI registry
        Academic Sources
            OENO One journal
            AJEV journal
            Vitis journal
            UC Davis
                Wine ontology RDF
                AVA GeoJSON
                FPS database
            UC IPM
                Pest management
            Extension services
                USDA, Penn State, Oregon State
        Datasets
            HuggingFace
                Wine review datasets
            Kaggle
                Wine quality CSV
                Wine reviews CSV
            OIV
                Statistical reports PDF
```

---

## 6. Quality Assurance Framework

The multi-layer quality assurance process.

```mermaid
flowchart TB
    subgraph L1["LAYER 1: Per-Fact Validation (automated, inline)"]
        direction LR
        L1A["Word count\n5-30 words"]
        L1B["Has verb"]
        L1C["No dangling\npronouns"]
        L1D["On-topic\nfor region"]
        L1E["Wine-relevant\nkeyword match"]
    end

    subgraph L2["LAYER 2: Per-Scraper Checks (automated, --validate)"]
        direction LR
        L2A["Domain distribution\n(wine_regions < 60%)"]
        L2B["No facts > 30 words\n(<2% over 25 words)"]
        L2C["Entity coverage\n(>60% with entities)"]
        L2D["No hardcoded\ndata patterns"]
    end

    subgraph L3["LAYER 3: Cross-Database Analysis (automated, Phase 3)"]
        direction LR
        L3A["Near-duplicate\ndetection\n(fuzzy matching)"]
        L3B["Factual\nconsistency\n(contradiction\ndetection)"]
        L3C["Coverage &\nbalance\n(domain/geographic\ngaps)"]
        L3D["Entity name\nnormalization\n(spelling\nvariants)"]
    end

    subgraph L4["LAYER 4: Provenance Audit (automated + manual, Phase 3)"]
        direction LR
        L4A["Every fact\ntraces to\nfetched URL"]
        L4B["No fake\nsource URLs"]
        L4C["Source tier\ndistribution\ncheck"]
        L4D["Suspicious\npattern\ndetection"]
    end

    subgraph L5["LAYER 5: Human Expert Review (manual, ongoing)"]
        direction LR
        L5A["10-sample review\nper scraper"]
        L5B["Domain accuracy\nverification"]
        L5C["Wine knowledge\nfact-checking"]
        L5D["Coverage priority\ndecisions"]
    end

    L1 -->|"rejected facts\nlogged with reason"| L1_OUT["Rejection Log\n(acceptance rate\nper scraper)"]
    L1 -->|"accepted"| L2
    L2 -->|"flags"| L2_OUT["Scraper-Level\nReport"]
    L2 -->|"clean"| L3
    L3 -->|"issues"| L3_OUT["Database Health\nReport"]
    L3 -->|"clean"| L4
    L4 -->|"issues"| L4_OUT["Provenance\nReport"]
    L4 -->|"clean"| L5
    L5 -->|"decisions"| L5_OUT["Expert Review\nLog"]
    L5 -->|"approved"| FINAL["Validated\nFact Database"]
```

---

## 7. Provenance Chain

How data provenance is guaranteed for every fact in the database.

```mermaid
flowchart LR
    subgraph ORIGIN["Origin (verifiable)"]
        O1["URL fetched\nvia HTTP GET"]
        O2["SPARQL query\nexecuted against\nWikidata endpoint"]
        O3["Dataset downloaded\nvia API/URL"]
    end

    subgraph TRANSFORM["Transformation (reproducible)"]
        T1["HTML → text blocks\n(BeautifulSoup)"]
        T2["SPARQL bindings\n→ fact templates"]
        T3["CSV/JSON rows\n→ structured facts"]
        T4["Decompose →\nResolve →\nClassify →\nValidate"]
    end

    subgraph STORE["Storage (auditable)"]
        S1["facts table\n(fact_text, domain,\nsource_id, confidence)"]
        S2["sources table\n(name, url,\nsource_type, tier)"]
        S3["Scraper log\n(data/logs/\n<name>_<timestamp>.log)"]
    end

    subgraph AUDIT["Audit Trail"]
        A1["source_id FK\n→ source URL"]
        A2["Log file records\nevery HTTP request\nand response code"]
        A3["PROCESS_LOG.md\nrecords methodology\nand decisions"]
    end

    O1 --> T1
    O2 --> T2
    O3 --> T3
    T1 & T2 & T3 --> T4
    T4 --> S1
    O1 & O2 & O3 --> S2
    O1 & O2 & O3 --> S3
    S1 --> A1
    S3 --> A2
    A3 --> A2
    S2 --> A1

    A1 -.- VERIFY["Any fact can be\nverified by:\n1. Look up source_id\n2. Visit source URL\n3. Confirm fact text\n   derived from content"]
```

---

## 8. Phase Execution Timeline

```mermaid
gantt
    title OenoBench Data Collection — Execution Timeline
    dateFormat  YYYY-MM-DD
    axisFormat  %b %d

    section Phase 0
    DB Backup                          :p0pre, 2026-04-11, 1d
    Build _fact_processing.py          :p0a, after p0pre, 1d
    Build _web_helpers.py              :p0b, after p0a, 1d
    Update _wiki_helpers.py            :p0c, after p0b, 1d
    Purge hardcoded facts              :p0d, after p0c, 1d
    Comprehensive testing (0E)         :p0e, after p0d, 2d
    GATE: Tests pass                   :milestone, after p0e, 0d

    section Phase 1 (Team scraper-fix)
    Teammate 1A: bordeaux + burgundy      :t1a, after p0e, 3d
    Teammate 1B: champagne + IWC          :t1b, after p0e, 3d
    Teammate 1C: austria + greece + 2     :t1c, after p0e, 4d
    Lead: merge + validate                :p1m, after t1c, 1d
    GATE: All merged & validated          :milestone, after p1m, 0d

    section Phase 2.1 (Team rebuild-major)
    7 teammates in parallel               :t2a, after p1m, 4d
    Lead: merges + logging                :p2am, after t2a, 1d

    section Phase 2.2 (Team rebuild-remaining)
    8 teammates in parallel               :t2b, after p2am, 4d
    Lead: merges + logging                :p2bm, after t2b, 1d

    section Phase 3 (Team verification)
    3A: Per-scraper checks                :t3a, after p2bm, 2d
    3B: Full DB analysis                  :t3b, after p2bm, 3d
    3C: Provenance audit + samples        :t3c, after p2bm, 2d
    Lead: compile report + summary        :p3l, after t3b, 2d
    GATE: Report delivered to user        :milestone, after p3l, 0d
```

---

## 9. Database Schema (Fact Storage)

```mermaid
erDiagram
    SOURCES {
        uuid id PK
        varchar name
        varchar url UK
        source_type_enum source_type
        tier_enum tier
        varchar language
        timestamp created_at
    }
    FACTS {
        uuid id PK
        text fact_text UK
        domain_enum domain
        varchar subdomain
        uuid source_id FK
        jsonb entities
        float confidence
        text[] tags
        vector embedding
        timestamp created_at
    }
    QUESTIONS {
        uuid id PK
        text question_text
        text correct_answer
        varchar difficulty
        uuid source_fact_id FK
        timestamp created_at
    }
    QUESTION_FACTS {
        uuid question_id FK
        uuid fact_id FK
    }
    GENERATION_METADATA {
        uuid question_id FK
        varchar model_name
        varchar model_version
        jsonb prompt_used
        timestamp generated_at
    }

    SOURCES ||--o{ FACTS : "provides"
    FACTS ||--o{ QUESTION_FACTS : "supports"
    QUESTIONS ||--o{ QUESTION_FACTS : "based on"
    QUESTIONS ||--|| GENERATION_METADATA : "generated by"
```

---

## Summary Statistics (Targets)

| Metric | Before Cleanup | After Cleanup (Target) |
|--------|---------------|----------------------|
| Total facts in DB | ~24,563 | ~20,000+ (genuine only) |
| Hardcoded/fake facts | ~8,821 | 0 |
| Data sources (by type) | 6 types | 6 types |
| Scrapers (genuine) | 10 | 30+ |
| Facts > 30 words | ~800+ | 0 |
| Dangling references | 231 | 0 |
| Domain = wine_regions | ~50% | < 40% |
| Official website facts | ~20 | 500-2,000+ |
| Provenance: fact → fetched URL | ~60% | 100% |
| Quality layers | 2 (inline + manual) | 5 (see QA Framework) |

---

## 10. Question Quality Audit Framework (Phase 2c/2d, Apr 2026)

The QA layers above operate on **facts** during scraping. After question generation a separate multi-agent audit operates on **generated questions**. Code lives at `src/qa/`; CLI at `python -m src.qa.orchestrator`.

```mermaid
flowchart LR
    subgraph CORPUS["Stage 0 — Pilot Corpus (audit_pilot_v1)"]
        BC["build-corpus<br/>~600 Qs stratified<br/>5 strategies × 4 difficulties × 6 domains"]
    end

    subgraph TEAMS["Stages 1–3 — 4 Teams, 9 Agents"]
        direction TB
        TA["Team A · Static (no LLM)<br/>A1 LexicalHygiene<br/>A2 BiasStats (χ², MWU)<br/>A3 FactEcho (LCS)<br/>A4 TemplateFingerprint (logreg)"]
        TB["Team B · Tri-Judge Panel<br/>(Claude/ChatGPT/Gemini)<br/>B1 TriJudgeAnswer (open-book)<br/>B2 ClosedBookSolvability"]
        TC["Team C · Adversarial<br/>C2 CategoryLeak<br/>(C1/C3/C4 deferred)"]
        TD["Team D · Population<br/>D1 SelfPreference (5×5 matrix)<br/>D3 SkewAudit (country χ²)"]
    end

    subgraph PERSIST["Persistence"]
        AF["audit_findings<br/>(idempotent on<br/>run_id, q_id, agent_id, version)"]
        AR["audit_runs<br/>(config_hash, seed, cost)"]
        AGL["audit_gold_labels<br/>(human reviewer rubrics)"]
    end

    subgraph REPORT["Stage 5 — Reports"]
        QAR["docs/QUALITY_AUDIT_REPORT.md<br/>per-strategy + per-generator"]
        GIP["docs/GENERATION_IMPROVEMENT_PLAN.md<br/>ranked defects + Go/No-Go gate"]
    end

    BC --> TA
    BC --> TB
    BC --> TC
    BC --> TD
    TA --> AF
    TB --> AF
    TC --> AF
    TD --> AF
    AF --> QAR
    AGL --> QAR
    AR -.-> QAR
    QAR --> GIP
```

**Key design choices:**
- **Judges (Claude/ChatGPT/Gemini) are kept distinct from generator subjects** — Llama and Qwen are evaluated by D1 SelfPreference, never used as judges, to keep the bias measurement independent.
- **Findings are idempotent and resumable.** Each audit run has a `config_hash`; identical configs reuse already-stored findings. Team B writes inline (not batched), so a 4-hour audit can be killed and resumed without losing work.
- **Population-level findings (A2, A4, D1, D3) are bundled** into a single row per agent (cell breakdowns nested in payload) because the unique constraint cannot distinguish multiple `question_id=NULL` rows from the same agent.
- **The Go/No-Go gate** in `docs/GENERATION_IMPROVEMENT_PLAN.md` sets concrete pass thresholds per agent that must hold before the full 10k generation run is allowed to start.
- **Deferred LLM-driven adversarial agents (C1, C3, C4, B3, B4, D2)** are listed in the report's Limitations section with explicit escalation triggers (e.g., "if A4 AUC ≥ 0.9, run C1 + B4 on flagged subset").

**First audit run (April 19, 2026):** 472 questions, 9 agents, 3,207 LLM calls, **$8.49 total**, 7h wall-clock. Identified 3 critical blockers (verbatim copying 35% fail, world-knowledge solvable 30% fail, country over-rep 4.46×). See `docs/QUALITY_AUDIT_REPORT.md` and `docs/GENERATION_IMPROVEMENT_PLAN.md`.

---

*This document is maintained alongside the codebase. Mermaid diagrams can be
rendered to SVG/PDF for paper figures using `mmdc` (Mermaid CLI) or any
Mermaid-compatible renderer.*
