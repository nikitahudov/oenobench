# OenoBench — Wine Knowledge LLM Benchmark
## Project Plan v2.0

---

## 1. Executive Summary

This project aims to develop a comprehensive benchmark for evaluating Large Language Models' knowledge and reasoning capabilities related to wine. The benchmark will assess factual knowledge, applied understanding, and reasoning across all aspects of the wine industry—from grape growing to glass.

**A key methodological innovation of this project is the AI-driven approach to dataset creation**, leveraging automated data collection, synthetic question generation, and AI-assisted validation to efficiently produce a large-scale, high-quality benchmark while minimizing manual effort.

The project will culminate in a **peer-reviewed scientific publication** documenting the benchmark methodology, dataset characteristics, and baseline LLM evaluation results.

**Project Name:** OenoBench (formerly WineBench)
**Version Target:** 1.0  
**Total Questions:** 5,000  
**Primary Methodology:** AI-driven with human expert validation

---

## 2. Project Objectives

### Primary Objectives
- Create a rigorous, comprehensive benchmark of **5,000 questions** for wine knowledge evaluation
- **Pioneer an AI-driven methodology** for domain-specific benchmark creation
- Enable standardized comparison of LLM performance in the wine domain
- Cover the full breadth of wine industry knowledge (viticulture, winemaking, business, regions, varieties, producers)
- Design questions that test both factual recall and applied reasoning
- **Publish findings in a peer-reviewed scientific venue**

### Secondary Objectives
- Establish difficulty tiers for nuanced performance analysis
- Create a reproducible, automated evaluation methodology
- Build a benchmark that can be updated as wine industry knowledge evolves
- Provide category-level scoring for granular performance insights
- **Document best practices for AI-assisted benchmark creation**
- **Release dataset and tools as open-source resources**

---

## 3. Scientific Publication Plan

### 3.1 Publication Strategy

| Aspect | Details |
|--------|---------|
| **Paper Type** | Full research paper (8-10 pages + appendices) |
| **Target Venues** | Primary: ACL, EMNLP, NeurIPS (Datasets & Benchmarks track); Secondary: LREC-COLING, *Nature Scientific Data* |
| **Open Access** | ArXiv preprint concurrent with submission |
| **Timeline** | Submit within 4 weeks of benchmark completion |

### 3.2 Paper Structure

| Section | Content |
|---------|---------|
| **Abstract** | Benchmark overview, scale, key findings |
| **Introduction** | Motivation for domain-specific LLM evaluation; gap in existing benchmarks |
| **Related Work** | Existing LLM benchmarks (MMLU, HellaSwag, etc.); domain-specific evaluations; wine knowledge resources; LLM-generated dataset methodology |
| **Methodology** | AI-driven pipeline; data sources; question generation; validation process |
| **Methodological Validity** | Multi-model generation; bias mitigation strategies; control set design |
| **Dataset Description** | Statistics, category distribution, difficulty analysis, quality metrics |
| **Experiments** | Evaluation protocol; LLMs tested; prompting strategies |
| **Results & Analysis** | Performance comparisons; error analysis; category-level insights |
| **Bias Analysis** | Self-preference scores; human vs. LLM-generated comparison; held-out subset analysis |
| **Discussion** | Implications; limitations; AI-assisted benchmark creation lessons |
| **Conclusion** | Summary; future directions |
| **Appendices** | Sample questions; full category breakdown; evaluation prompts; per-generator breakdowns |

### 3.3 Key Scientific Contributions

1. **OenoBench Dataset:** First large-scale, comprehensive wine knowledge benchmark (5,000 questions)
2. **AI-Driven Methodology:** Reproducible pipeline for domain-specific benchmark creation using LLMs and automation
3. **Methodological Validity Framework:** Novel approach to mitigating LLM-generation bias with multi-model generation, held-out evaluation, and human control sets
4. **Bias Analysis:** Empirical analysis of self-preference effects in LLM-generated benchmarks
5. **Evaluation Framework:** Multi-dimensional assessment (knowledge domains, difficulty levels, cognitive skills)
6. **Baseline Results:** Comprehensive evaluation of major LLMs on specialized domain knowledge

### 3.4 Supplementary Materials for Publication

- Complete dataset (JSON/CSV format)
- Evaluation code and scripts
- Data collection and generation pipelines
- Human validation interface
- Results reproduction instructions
- Interactive results explorer (optional)

---

## 4. AI-Driven Methodology

### 4.1 Methodology Overview

The dataset creation leverages AI at every stage, with targeted human expert involvement only for validation and quality assurance.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        AI-DRIVEN PIPELINE OVERVIEW                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌───────────┐ │
│  │   STAGE 1    │    │   STAGE 2    │    │   STAGE 3    │    │  STAGE 4  │ │
│  │    Data      │───▶│   Question   │───▶│     AI       │───▶│   Human   │ │
│  │  Collection  │    │  Generation  │    │  Validation  │    │  Review   │ │
│  │  (Automated) │    │  (Synthetic) │    │  (Automated) │    │ (Targeted)│ │
│  └──────────────┘    └──────────────┘    └──────────────┘    └───────────┘ │
│        │                    │                   │                   │       │
│        ▼                    ▼                   ▼                   ▼       │
│   Web scraping         LLM-based           Multi-model          Expert     │
│   API extraction       generation          cross-check          sampling   │
│   Document parsing     Template-guided     Consistency          Final QA   │
│   Knowledge bases      Few-shot prompts    Difficulty est.      Calibrate  │
│                                                                             │
│  ════════════════════════════════════════════════════════════════════════  │
│   ~95% Automated                                          ~5% Human Input  │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 4.2 Stage 1: Automated Data Collection

#### 4.2.1 Data Sources & Scraping Targets

| Source Type | Examples | Data Extracted |
|-------------|----------|----------------|
| **Official Appellation Sites** | INAO (France), DOCG/DOC registries (Italy), AVA databases (USA) | Classification rules, permitted varieties, geographic boundaries |
| **Wine Encyclopedias** | Wikipedia wine articles, Wikidata structured data | Region facts, producer info, grape characteristics |
| **Regulatory Documents** | EU wine regulations, TTB rulings, appellation laws | Legal requirements, labeling rules |
| **Educational Resources** | WSET candidate guidance (public), UC Davis extension materials | Technical viticulture/winemaking facts |
| **Producer Websites** | Major estate websites, consortium member pages | Winemaking techniques, vineyard details |
| **Wine Databases** | Wine-Searcher (public data), Vivino (public reviews/data) | Producer lists, regional associations, vintage data |
| **Academic Sources** | Open-access journals (OENO One, AJEV), thesis repositories | Scientific facts, research findings |
| **Books (Digitized/Licensed)** | Oxford Companion to Wine (if licensed), public domain texts | Comprehensive reference data |

#### 4.2.2 Scraping & Extraction Pipeline

```python
# Conceptual Pipeline Architecture
PIPELINE = {
    "web_scraper": {
        "tools": ["Scrapy", "Playwright", "BeautifulSoup"],
        "rate_limiting": "Respectful crawling with delays",
        "output": "Raw HTML/JSON per source"
    },
    "document_processor": {
        "tools": ["PyMuPDF", "pdfplumber", "python-docx"],
        "tasks": "Extract text from PDFs, official documents",
        "output": "Structured text segments"
    },
    "entity_extractor": {
        "tools": ["spaCy NER", "LLM-based extraction"],
        "entities": ["Regions", "Grapes", "Producers", "Techniques", "Regulations"],
        "output": "Entity database with relationships"
    },
    "knowledge_graph_builder": {
        "tools": ["Neo4j", "NetworkX"],
        "purpose": "Map relationships between wine entities",
        "output": "Queryable knowledge graph"
    },
    "fact_database": {
        "storage": "PostgreSQL + Elasticsearch",
        "schema": "Facts with source attribution and confidence",
        "output": "Verified fact repository for question generation"
    }
}
```

#### 4.2.3 Data Collection Targets

| Category | Target Facts | Primary Sources |
|----------|--------------|-----------------|
| Wine Regions | 5,000+ facts | Appellation sites, Wikipedia, regulatory docs |
| Grape Varieties | 2,000+ facts | Wine Grapes database, ampelography resources |
| Producers | 3,000+ facts | Producer sites, wine databases, consortiums |
| Viticulture | 1,500+ facts | Academic papers, extension resources |
| Winemaking | 1,500+ facts | Technical manuals, winery documentation |
| Wine Business | 1,000+ facts | Trade publications, regulatory bodies |

### 4.3 Stage 2: Synthetic Question Generation

#### 4.3.1 Generation Strategy

| Approach | Description | Use Case | % of Questions |
|----------|-------------|----------|----------------|
| **Fact-to-Question** | Convert extracted facts into questions using LLM | Factual recall questions | 40% |
| **Template-Based** | Fill parameterized templates with entity data | Consistent format questions | 25% |
| **Comparative Generation** | Generate questions comparing entities | Analysis questions | 15% |
| **Scenario Synthesis** | Create applied scenarios from multiple facts | Application questions | 10% |
| **Distractor Mining** | Generate plausible wrong answers from related facts | Quality MC options | 10% |

#### 4.3.2 Question Generation Prompts

**Fact-to-Question Prompt Example:**
```
You are creating questions for a wine knowledge benchmark. Given the following verified fact, generate a multiple-choice question.

FACT: "Brunello di Montalcino DOCG requires wines to be made from 100% Sangiovese (locally called Brunello) and aged for a minimum of 5 years, including at least 2 years in oak barrels."

SOURCE: Consorzio del Vino Brunello di Montalcino official regulations

Generate:
1. A clear, unambiguous question
2. The correct answer
3. Three plausible but incorrect distractors
4. Difficulty level (1-4)
5. Cognitive dimension (recall/comprehension/application/analysis)

Format as JSON.
```

**Template-Based Generation Example:**
```
TEMPLATE: "Which grape variety is {REGION} {WINE_TYPE} primarily made from?"
PARAMETERS: 
  - REGION: "Barolo"
  - WINE_TYPE: "DOCG"
CORRECT_ANSWER: "Nebbiolo"
DISTRACTORS_POOL: [Related red Italian varieties from knowledge graph]
```

#### 4.3.3 Generation Pipeline

```
┌─────────────────────────────────────────────────────────────────────┐
│                    QUESTION GENERATION PIPELINE                     │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Fact Database ──┬──▶ Fact-to-Question Generator ───────────┐      │
│                  │         (Claude/GPT-4)                    │      │
│                  │                                           │      │
│  Entity Graph ───┼──▶ Template Filler ──────────────────────┼──▶ Raw│
│                  │         (Programmatic + LLM)              │   Questions│
│                  │                                           │      │
│  Relationship DB ┴──▶ Comparative Question Generator ───────┘      │
│                            (LLM with structured prompts)            │
│                                                                     │
│  ─────────────────────────────────────────────────────────────────  │
│                                                                     │
│  Raw Questions ──▶ Deduplication ──▶ Format Normalization ──▶ Stage 3│
│                      (Embedding      (JSON schema                   │
│                       similarity)     validation)                   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

#### 4.3.4 Question Distribution Targets

| Domain | Target Questions | Generation Approach |
|--------|------------------|---------------------|
| **Viticulture** | 750 | Fact-to-question from academic sources |
| **Winemaking** | 1,000 | Template + scenario synthesis |
| **Wine Business** | 500 | Fact-to-question + comparative |
| **Wine Regions** | 1,750 | Heavy template use with region entities |
| **Grape Varieties** | 600 | Template + comparative generation |
| **Producers** | 400 | Fact-to-question from producer data |
| **TOTAL** | **5,000** | |

### 4.4 Stage 3: AI-Powered Validation

#### 4.4.1 Multi-Model Cross-Validation

Each generated question is validated by multiple LLMs independently:

```
┌─────────────────────────────────────────────────────────────────────┐
│                    MULTI-MODEL VALIDATION                           │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│                      ┌─────────────────┐                            │
│                      │  Raw Question   │                            │
│                      └────────┬────────┘                            │
│                               │                                     │
│         ┌─────────────────────┼─────────────────────┐               │
│         ▼                     ▼                     ▼               │
│  ┌─────────────┐       ┌─────────────┐       ┌─────────────┐        │
│  │  Claude     │       │   GPT-4     │       │   Gemini    │        │
│  │  Validator  │       │  Validator  │       │  Validator  │        │
│  └──────┬──────┘       └──────┬──────┘       └──────┬──────┘        │
│         │                     │                     │               │
│         └─────────────────────┼─────────────────────┘               │
│                               ▼                                     │
│                      ┌─────────────────┐                            │
│                      │   Consensus     │                            │
│                      │   Analysis      │                            │
│                      └────────┬────────┘                            │
│                               │                                     │
│              ┌────────────────┼────────────────┐                    │
│              ▼                ▼                ▼                    │
│        ┌──────────┐    ┌──────────┐    ┌──────────────┐             │
│        │ ACCEPTED │    │  REVISE  │    │   FLAGGED    │             │
│        │ (≥2/3    │    │ (Minor   │    │ (For human   │             │
│        │  agree)  │    │  issues) │    │   review)    │             │
│        └──────────┘    └──────────┘    └──────────────┘             │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

#### 4.4.2 Automated Validation Checks

| Check Type | Method | Action on Failure |
|------------|--------|-------------------|
| **Factual Accuracy** | Cross-reference with source database | Flag for review |
| **Answer Correctness** | Multiple LLMs solve independently | Revise if disagreement |
| **Distractor Quality** | Check distractors aren't arguably correct | Regenerate distractors |
| **Ambiguity Detection** | LLM analysis for multiple interpretations | Rewrite question |
| **Difficulty Estimation** | Ensemble model prediction | Adjust difficulty tag |
| **Duplicate Detection** | Semantic similarity (embeddings) | Remove duplicates |
| **Grammar & Clarity** | LLM proofreading | Auto-correct or flag |
| **Bias Detection** | Check for regional/cultural bias | Flag for review |

#### 4.4.3 Difficulty Calibration (Automated)

```python
# Difficulty Estimation Model
difficulty_features = {
    "entity_obscurity": "How well-known is the subject?",
    "fact_specificity": "General knowledge vs. precise detail?",
    "reasoning_steps": "Direct recall vs. inference required?",
    "distractor_similarity": "How close are wrong answers to correct?",
    "domain_specificity": "General wine vs. technical knowledge?",
    "geographic_scope": "Major region vs. obscure subregion?"
}

# Calibrated against WSET/CMS level expectations
difficulty_model = train_on_human_calibration_subset()
```

### 4.5 Stage 4: Human Expert Review (Targeted)

#### 4.5.1 Human Review Scope

Human experts review only a strategic subset, not all 5,000 questions:

| Review Type | Sample Size | Purpose |
|-------------|-------------|---------|
| **Human-Authored Control Set** | 300 questions | Zero-LLM baseline for bias analysis |
| **Calibration Set** | 200 questions | Validate AI difficulty ratings |
| **Flagged Questions** | ~500 questions (est.) | Resolve AI-detected issues |
| **Random Sample QA** | 300 questions | Spot-check overall quality |
| **Edge Cases** | ~100 questions | Complex/controversial topics |
| **TOTAL HUMAN INVOLVEMENT** | **~1,400 questions (~28%)** | |

**Note:** The 300 human-authored questions require more expert time than review tasks, as experts write questions from scratch based on the fact database.

#### 4.5.2 Expert Review Interface

Build a streamlined review tool:

```
┌─────────────────────────────────────────────────────────────────────┐
│  WINEBENCH EXPERT REVIEW INTERFACE                                  │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Question ID: WB-REG-1247-L3          Category: Regions/Burgundy    │
│  AI Confidence: 87%                   Flagged: Distractor concern   │
│  ─────────────────────────────────────────────────────────────────  │
│                                                                     │
│  QUESTION:                                                          │
│  Which of the following is NOT a Grand Cru vineyard in              │
│  Gevrey-Chambertin?                                                 │
│                                                                     │
│  ○ A) Chambertin-Clos de Bèze                                       │
│  ○ B) Mazis-Chambertin                                              │
│  ○ C) Charmes-Chambertin                                            │
│  ● D) Clos de Vougeot           ◄── Marked correct                  │
│                                                                     │
│  SOURCE: BIVB Official Grand Cru list                               │
│  ─────────────────────────────────────────────────────────────────  │
│                                                                     │
│  EXPERT ASSESSMENT:                                                 │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌───────────────┐  │
│  │  ✓ APPROVE  │ │  ✎ EDIT     │ │  ⚠ FLAG     │ │  ✗ REJECT     │  │
│  └─────────────┘ └─────────────┘ └─────────────┘ └───────────────┘  │
│                                                                     │
│  Notes: ________________________________________________________   │
│                                                                     │
│  Difficulty Assessment:  ○ Too Easy  ● Correct  ○ Too Hard         │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

#### 4.5.3 Expert Panel (Reduced Scope)

| Role | Count | Responsibility | Hours Est. |
|------|-------|----------------|------------|
| **Lead Validator (MW/MS level)** | 1 | Final authority on disputed questions, control set oversight | 50 hrs |
| **Domain Experts** | 2-3 | Review flagged questions, author control set questions | 50 hrs each |
| **Calibration Testers** | 5-10 | Take calibration test, provide difficulty feedback | 5 hrs each |

**Control Set Authoring:** Domain experts will author the 300-question human control set using the fact database as source material, ensuring questions follow the same format and difficulty distribution as the AI-generated questions.

---

## 5. Methodological Validity & Bias Mitigation

### 5.1 The Challenge: LLM-Generated Benchmarks for LLM Evaluation

Using LLMs to generate benchmark questions that will later evaluate LLMs raises legitimate methodological concerns. This section addresses these challenges transparently and outlines our mitigation strategies.

#### 5.1.1 Identified Risks

| Risk | Description | Severity |
|------|-------------|----------|
| **Circular Evaluation** | Models may perform better on questions they generated due to stylistic familiarity | High |
| **Blind Spot Inheritance** | LLMs cannot generate questions about knowledge they lack, creating systematic gaps | High |
| **Difficulty Miscalibration** | LLM-estimated difficulty may reflect model limitations, not true domain expertise levels | Medium |
| **Stylistic Overfitting** | LLM-generated syntax/framing may advantage LLM test-takers over the underlying knowledge | Medium |
| **Homogeneous Question Patterns** | Single-model generation may produce repetitive structures | Low |

### 5.2 Mitigation Strategy Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      BIAS MITIGATION FRAMEWORK                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐              │
│  │  GENERATION     │  │  STRUCTURAL     │  │  EVALUATION     │              │
│  │  DIVERSITY      │  │  SAFEGUARDS     │  │  CONTROLS       │              │
│  ├─────────────────┤  ├─────────────────┤  ├─────────────────┤              │
│  │ • Multi-model   │  │ • Fact-grounded │  │ • Held-out      │              │
│  │   generation    │  │   generation    │  │   subsets       │              │
│  │ • Template-     │  │ • External      │  │ • Human control │              │
│  │   heavy approach│  │   source req.   │  │   set           │              │
│  │ • Adversarial   │  │ • Post-cutoff   │  │ • Self-pref.    │              │
│  │   mining        │  │   facts         │  │   analysis      │              │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘              │
│                                                                             │
│                        ┌─────────────────┐                                  │
│                        │  TRANSPARENCY   │                                  │
│                        ├─────────────────┤                                  │
│                        │ • Full metadata │                                  │
│                        │ • Paper section │                                  │
│                        │ • Bias metrics  │                                  │
│                        └─────────────────┘                                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 5.3 Mitigation 1: Generation Diversity

#### 5.3.1 Multi-Model Question Generation

Questions will be generated by multiple LLMs to prevent single-model bias:

| Generator Model | Question Target | Percentage |
|-----------------|-----------------|------------|
| Claude 3.5 Sonnet | 1,500 questions | 30% |
| GPT-4o | 1,500 questions | 30% |
| Gemini 1.5 Pro | 1,000 questions | 20% |
| Llama 3.1 405B | 500 questions | 10% |
| Template-only (no LLM creativity) | 500 questions | 10% |

Each question will be tagged with its generator model, enabling downstream analysis.

#### 5.3.2 Template-Heavy Generation

Increase reliance on deterministic template-based generation to reduce LLM "creativity":

```
TEMPLATE EXAMPLE:
"The {APPELLATION} appellation requires a minimum of {PERCENTAGE}% {GRAPE_VARIETY} 
in its {COLOR} wines."

PARAMETERS FROM DATABASE:
- APPELLATION: "Châteauneuf-du-Pape"
- PERCENTAGE: "0" (no minimum for any single variety)
- GRAPE_VARIETY: [N/A - trick question]
- COLOR: "red"

GENERATED QUESTION:
"What is the minimum percentage of Grenache required in red Châteauneuf-du-Pape?"
A) 50%  B) 70%  C) 80%  D) There is no minimum for any single variety ✓
```

**Target:** At least 40% of questions should be template-generated with minimal LLM involvement.

#### 5.3.3 Adversarial Question Mining

Deliberately target known LLM weaknesses:

| Weakness Category | Mining Strategy | Target Questions |
|-------------------|-----------------|------------------|
| **Numeric precision** | Questions requiring exact numbers (hectares, percentages, years) | 300 |
| **Similar entity confusion** | Questions distinguishing easily confused items (Pouilly-Fumé vs Pouilly-Fuissé) | 200 |
| **Negative/exception knowledge** | "Which is NOT..." or exception-based questions | 250 |
| **Obscure regions/varieties** | Questions about lesser-known wine areas | 300 |
| **Recent changes** | Classification updates, new appellations post-2023 | 150 |
| **Counter-intuitive facts** | Facts that contradict common assumptions | 150 |

### 5.4 Mitigation 2: Structural Safeguards

#### 5.4.1 Fact-Grounded Generation Requirement

**Rule:** Every generated question MUST trace to a verified external fact in our source database.

```
┌─────────────────────────────────────────────────────────────────────┐
│                    FACT-GROUNDING REQUIREMENT                       │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  External Source ──▶ Fact Database ──▶ LLM Reformatter ──▶ Question │
│  (authoritative)     (verified)        (style only)       (output)  │
│                                                                     │
│  ✓ ALLOWED: LLM reformats verified fact into question format        │
│  ✗ FORBIDDEN: LLM invents facts from its own knowledge              │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

The LLM's role is **reformatting**, not **fact provision**. This separates knowledge testing from generation artifacts.

#### 5.4.2 External Source Requirement

Every fact must have documented external attribution:

| Source Quality Tier | Examples | Minimum Coverage |
|---------------------|----------|------------------|
| **Tier 1: Official** | Appellation laws, government registries, consortium rules | 50% |
| **Tier 2: Authoritative** | Oxford Companion to Wine, WSET materials, academic papers | 30% |
| **Tier 3: Reliable** | Major producer websites, established wine publications | 20% |

#### 5.4.3 Post-Training-Cutoff Facts

Where possible, include facts that postdate LLM training cutoffs:

- New appellation creations (2024-2025)
- Recent classification changes
- Updated regulations
- New vintage assessments

**Target:** 5-10% of questions based on information from 2024 or later.

### 5.5 Mitigation 3: Evaluation Controls

#### 5.5.1 Held-Out Evaluation Subsets

For each evaluated model, create a "held-out" subset excluding questions generated by that model:

| Evaluated Model | Held-Out Subset | Questions Available |
|-----------------|-----------------|---------------------|
| Claude 3.5 Sonnet | Exclude Claude-generated | 3,500 questions |
| GPT-4o | Exclude GPT-generated | 3,500 questions |
| Gemini 1.5 Pro | Exclude Gemini-generated | 4,000 questions |
| Llama 3.1 | Exclude Llama-generated | 4,500 questions |
| Other models | Full dataset | 5,000 questions |

**Analysis:** Compare each model's performance on full dataset vs. held-out subset.

#### 5.5.2 Human-Authored Control Set

Create a **300-question human-authored control set** with zero LLM involvement:

| Aspect | Specification |
|--------|---------------|
| **Size** | 300 questions (60 per difficulty level 1-4, 60 mixed) |
| **Authors** | Wine educators, MW/MS candidates, domain experts |
| **Coverage** | Proportional to main dataset categories |
| **Purpose** | Baseline comparison for LLM-generated questions |
| **Analysis** | Compare model performance on human vs. LLM-generated questions |

**Key Research Question:** Do LLMs perform systematically better on LLM-generated questions than on human-authored questions?

#### 5.5.3 Self-Preference Analysis

Explicitly analyze whether models perform better on self-generated questions:

```
SELF-PREFERENCE METRIC:

Self-Preference Score (SPS) = 
    (Accuracy on self-generated questions) - (Accuracy on other-generated questions)

SPS > 0  →  Model shows self-preference (potential bias)
SPS ≈ 0  →  No detectable self-preference
SPS < 0  →  Model performs worse on own questions (unexpected)
```

This analysis will be a dedicated subsection in the research paper.

### 5.6 Mitigation 4: Transparency & Documentation

#### 5.6.1 Full Metadata Tracking

Every question includes complete generation provenance:

```json
{
  "question_id": "WB-REG-1247",
  "generation_metadata": {
    "generator_model": "gpt-4o-2024-05-13",
    "generation_method": "fact_to_question",
    "template_id": null,
    "source_fact_ids": ["fact_8821", "fact_8822"],
    "llm_creativity_level": "medium",
    "human_edited": false
  }
}
```

#### 5.6.2 Paper Transparency Requirements

The research paper MUST include:

| Section | Content |
|---------|---------|
| **Methodology** | Full disclosure of multi-model generation approach |
| **Limitations** | Explicit discussion of LLM-generation risks |
| **Results: Bias Analysis** | Self-preference scores for all evaluated models |
| **Results: Control Comparison** | Human-authored vs. LLM-generated performance comparison |
| **Appendix** | Per-generator-model performance breakdown |

#### 5.6.3 Dataset Release Documentation

Public dataset release will include:

- Generator model for each question
- Full source attribution
- Flags for template-generated vs. LLM-generated
- Human-edited indicators
- The 300-question human-authored control set as a separate subset

### 5.7 Validity Analysis Metrics

| Metric | Calculation | Acceptable Threshold |
|--------|-------------|----------------------|
| **Max Self-Preference Score** | Max SPS across all models | < 3 percentage points |
| **Human vs. LLM-Generated Gap** | Avg. accuracy difference | < 5 percentage points |
| **Generator Model Variance** | Std. dev. of accuracy across generator sources | < 2 percentage points |
| **Held-Out vs. Full Correlation** | Pearson correlation of model rankings | > 0.95 |

If thresholds are exceeded, additional mitigation steps will be taken before publication.

### 5.8 Addressing Blind Spot Inheritance

To mitigate the risk of LLMs only generating questions about what they know:

| Strategy | Implementation |
|----------|----------------|
| **Coverage-driven generation** | Mandate questions for every region/variety in our taxonomy, regardless of LLM confidence |
| **Adversarial prompting** | Explicitly prompt for obscure, lesser-known topics |
| **Human gap review** | Experts review category coverage and flag missing areas |
| **External curriculum alignment** | Cross-check coverage against WSET Diploma/MW syllabi |
| **Failure analysis seeding** | Analyze LLM failures on existing wine quizzes to target weak areas |

### 5.9 Why This Approach Remains Valid

Despite the challenges, LLM-generated benchmarks for factual domains offer advantages:

| Advantage | Explanation |
|-----------|-------------|
| **Scale** | 5,000 high-quality questions would take humans months/years |
| **Consistency** | Uniform formatting and style across questions |
| **Source traceability** | Every fact is externally grounded and documented |
| **Reproducibility** | Generation pipeline can be re-run, audited, extended |
| **Transparency** | Full metadata enables bias analysis impossible with opaque human authorship |
| **Scientific contribution** | Analyzing LLM-generation bias is itself a novel contribution |

**Key insight:** For factual knowledge benchmarks (vs. reasoning benchmarks), the LLM's role is reformatting externally verified facts—not providing the knowledge being tested. This fundamentally limits the circularity concern.

---

## 6. Knowledge Domains & Categories

### 5.1 Viticulture (Grape Growing) — 750 Questions

| Subcategory | Questions | Automated Source |
|-------------|-----------|------------------|
| Vine Biology | 120 | Academic papers, extension resources |
| Terroir | 150 | Regional appellation documents |
| Vineyard Management | 150 | Technical manuals, research papers |
| Pest & Disease | 120 | UC Davis IPM, agricultural databases |
| Organic/Biodynamic | 100 | Certification body documents |
| Climate & Weather | 110 | Climate databases, vintage reports |

### 5.2 Winemaking (Oenology) — 1,000 Questions

| Subcategory | Questions | Automated Source |
|-------------|-----------|------------------|
| Harvest & Crushing | 80 | Technical winemaking resources |
| Fermentation | 150 | Oenology textbooks, research |
| Maceration & Extraction | 100 | Winemaking guides |
| Aging & Maturation | 150 | Cooperage data, winery techniques |
| Blending | 80 | Appellation rules, producer data |
| Fining & Filtration | 70 | Technical specifications |
| Faults & Flaws | 120 | Sensory science resources |
| Sparkling Wine | 100 | Champagne/sparkling regulations |
| Fortified Wine | 80 | DO/DOC regulations, producer info |
| Sweet Wine | 70 | Regional specialty documents |

### 5.3 Wine Business & Industry — 500 Questions

| Subcategory | Questions | Automated Source |
|-------------|-----------|------------------|
| Regulations & Law | 150 | Government databases, legal texts |
| Economics | 60 | Trade publications, market reports |
| Distribution | 60 | Industry structure documentation |
| Marketing & Branding | 50 | Public case studies |
| Wine Service | 80 | Sommelier resources |
| Storage & Cellaring | 50 | Technical guides |
| Sustainability | 50 | Certification bodies |

### 5.4 Wine Regions (Geography) — 1,750 Questions

| Region Group | Questions | Key Data Sources |
|--------------|-----------|------------------|
| **France** | 400 | INAO, regional interprofessions |
| **Italy** | 300 | Federdoc, consortium sites |
| **Spain & Portugal** | 200 | DO/DOC registries |
| **Germany & Austria** | 150 | VDP, regional wine boards |
| **USA** | 200 | TTB AVA database, regional associations |
| **South America** | 150 | National wine institutes |
| **Australia & NZ** | 150 | Wine Australia, NZ Winegrowers |
| **South Africa** | 75 | WOSA, WO documentation |
| **Other Regions** | 125 | National regulatory bodies |

### 5.5 Grape Varieties — 600 Questions

| Category | Questions | Data Sources |
|----------|-----------|--------------|
| International Varieties | 150 | Cross-referenced from multiple regions |
| French Varieties | 100 | French ampelography databases |
| Italian Varieties | 100 | Italian grape registry |
| Iberian Varieties | 75 | Spanish/Portuguese registries |
| Germanic Varieties | 50 | Austrian/German variety lists |
| Emerging/Indigenous | 125 | Wine Grapes database, Wikidata |

### 5.6 Producers & Wines — 400 Questions

| Category | Questions | Data Sources |
|----------|-----------|--------------|
| Iconic Estates | 100 | Classification documents, producer sites |
| Regional Leaders | 150 | Consortium member lists, wine databases |
| Historic Wines & Vintages | 100 | Historical records, auction data |
| Cooperatives & Négociants | 50 | Industry directories |

---

## 7. Question Categories & Formats

### 6.1 Question Types

| Type | Format | Purpose | Count |
|------|--------|---------|-------|
| **Multiple Choice (MC)** | 4 options, single correct | Factual knowledge | 2,500 (50%) |
| **Multiple Select (MS)** | 4-6 options, 2-3 correct | Comprehensive understanding | 750 (15%) |
| **True/False with Justification** | T/F + explanation required | Reasoning evaluation | 500 (10%) |
| **Matching** | Match items from two lists | Associations & relationships | 500 (10%) |
| **Short Answer** | Free-text, defined correct answers | Recall precision | 500 (10%) |
| **Scenario-Based** | Applied reasoning questions | Practical application | 250 (5%) |

### 6.2 Difficulty Levels

| Level | Description | WSET/CMS Equivalent | Count |
|-------|-------------|---------------------|-------|
| **Level 1: Beginner** | Basic wine literacy | WSET Level 1-2 | 1,250 (25%) |
| **Level 2: Intermediate** | Solid foundational knowledge | WSET Level 3, Certified Sommelier | 1,750 (35%) |
| **Level 3: Advanced** | Deep expertise required | WSET Diploma, Advanced Sommelier | 1,500 (30%) |
| **Level 4: Expert** | Master-level knowledge | Master of Wine, Master Sommelier | 500 (10%) |

### 6.3 Cognitive Dimensions

| Dimension | Description | Count |
|-----------|-------------|-------|
| **Recall** | Direct factual retrieval | 2,000 (40%) |
| **Comprehension** | Understanding concepts | 1,000 (20%) |
| **Application** | Using knowledge in context | 750 (15%) |
| **Analysis** | Breaking down complex topics | 600 (12%) |
| **Synthesis** | Combining multiple knowledge areas | 400 (8%) |
| **Evaluation** | Making judgments | 250 (5%) |

---

## 8. Technical Implementation

### 7.1 Data Pipeline Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         WINEBENCH TECHNICAL ARCHITECTURE                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                        DATA COLLECTION LAYER                         │   │
│  ├─────────────────────────────────────────────────────────────────────┤   │
│  │  Scrapy Spiders │ API Clients │ Document Parsers │ Wikidata Query   │   │
│  └────────────────────────────────┬────────────────────────────────────┘   │
│                                   ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                        DATA STORAGE LAYER                            │   │
│  ├─────────────────────────────────────────────────────────────────────┤   │
│  │  PostgreSQL     │  Elasticsearch  │  Neo4j          │  S3/MinIO     │   │
│  │  (Structured    │  (Full-text     │  (Knowledge     │  (Raw docs,   │   │
│  │   facts)        │   search)       │   graph)        │   backups)    │   │
│  └────────────────────────────────┬────────────────────────────────────┘   │
│                                   ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                     QUESTION GENERATION LAYER                        │   │
│  ├─────────────────────────────────────────────────────────────────────┤   │
│  │  Template Engine │ LLM Generator │ Distractor Miner │ Deduplicator  │   │
│  │  (Jinja2)        │ (Claude API)  │ (Graph queries)  │ (Embeddings)  │   │
│  └────────────────────────────────┬────────────────────────────────────┘   │
│                                   ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                        VALIDATION LAYER                              │   │
│  ├─────────────────────────────────────────────────────────────────────┤   │
│  │  Multi-LLM       │ Fact Checker  │ Difficulty      │ Bias           │   │
│  │  Consensus       │ (Source DB)   │ Estimator       │ Detector       │   │
│  └────────────────────────────────┬────────────────────────────────────┘   │
│                                   ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      HUMAN REVIEW LAYER                              │   │
│  ├─────────────────────────────────────────────────────────────────────┤   │
│  │  Review Web App  │  Expert Queue  │  Calibration Tool │ Analytics   │   │
│  └────────────────────────────────┬────────────────────────────────────┘   │
│                                   ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                       EVALUATION LAYER                               │   │
│  ├─────────────────────────────────────────────────────────────────────┤   │
│  │  LLM Test Runner │ Scoring Engine │ Results DB      │ Dashboard     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 7.2 Technology Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| **Web Scraping** | Scrapy, Playwright, BeautifulSoup | Automated data collection |
| **Document Processing** | PyMuPDF, pdfplumber, Unstructured | PDF/document text extraction |
| **NLP/NER** | spaCy, Hugging Face Transformers | Entity extraction |
| **Knowledge Graph** | Neo4j | Relationship mapping |
| **Primary Database** | PostgreSQL | Structured data storage |
| **Search** | Elasticsearch | Full-text search, similarity |
| **Embeddings** | OpenAI/Cohere Embeddings | Deduplication, similarity |
| **LLM APIs** | Claude API, OpenAI API, Google AI | Generation & validation |
| **Backend API** | FastAPI (Python) | Service orchestration |
| **Review Interface** | React + Tailwind | Human review tool |
| **Evaluation Runner** | Python + asyncio | Parallel LLM evaluation |
| **Results Dashboard** | Streamlit or Plotly Dash | Visualization |
| **Infrastructure** | Docker, AWS/GCP | Deployment |
| **Orchestration** | Airflow or Prefect | Pipeline management |

### 7.3 Question Data Schema

```json
{
  "question_id": "WB-REG-FR-1247-L3",
  "version": "1.0",
  "domain": "regions",
  "subdomain": "france_burgundy",
  "question_type": "multiple_choice",
  "difficulty": 3,
  "cognitive_dimension": "recall",
  
  "question_text": "Which of the following is NOT a Grand Cru vineyard located in the commune of Gevrey-Chambertin?",
  
  "options": [
    {"id": "A", "text": "Chambertin-Clos de Bèze"},
    {"id": "B", "text": "Mazis-Chambertin"},
    {"id": "C", "text": "Charmes-Chambertin"},
    {"id": "D", "text": "Clos de Vougeot"}
  ],
  
  "correct_answer": "D",
  "correct_answer_text": "Clos de Vougeot",
  
  "explanation": "Clos de Vougeot is a Grand Cru vineyard, but it is located in the commune of Vougeot, not Gevrey-Chambertin. The other three options are all among the nine Grand Cru vineyards of Gevrey-Chambertin.",
  
  "generation_metadata": {
    "method": "fact_to_question",
    "source_facts": ["fact_id_7823", "fact_id_7824"],
    "generator_model": "claude-3-opus",
    "generation_date": "2025-02-15"
  },
  
  "validation_metadata": {
    "ai_validators": ["claude-3-opus", "gpt-4", "gemini-pro"],
    "ai_consensus": "3/3 correct",
    "ai_confidence": 0.95,
    "human_reviewed": true,
    "human_reviewer": "expert_001",
    "review_date": "2025-03-01",
    "human_verdict": "approved"
  },
  
  "sources": [
    {
      "title": "BIVB Official Burgundy Grand Cru List",
      "url": "https://www.bourgogne-wines.com/grand-crus",
      "accessed": "2025-01-20"
    }
  ],
  
  "tags": ["burgundy", "grand_cru", "gevrey-chambertin", "classification"],
  
  "date_created": "2025-02-15",
  "last_modified": "2025-03-01"
}
```

---

## 9. Evaluation Methodology

### 8.1 LLM Evaluation Protocol

| Parameter | Setting |
|-----------|---------|
| **Temperature** | 0 (deterministic) |
| **Prompting** | Zero-shot (primary), Few-shot (secondary analysis) |
| **Runs per question** | 3 (for consistency measurement) |
| **Response parsing** | Regex + LLM fallback extraction |
| **Timeout** | 30 seconds per question |

### 8.2 Evaluation Prompt Template

```
You are being evaluated on wine knowledge. Answer the following question by selecting the correct option.

Question: {question_text}

Options:
A) {option_a}
B) {option_b}
C) {option_c}
D) {option_d}

Respond with ONLY the letter of your answer (A, B, C, or D).
```

### 8.3 Scoring Framework

| Metric | Calculation |
|--------|-------------|
| **Overall Accuracy** | Correct / Total × 100 |
| **Domain Scores** | Accuracy per knowledge domain |
| **Difficulty-Weighted Score** | Σ(correct × difficulty_weight) / Σ(difficulty_weight) |
| **Cognitive Profile** | Accuracy per cognitive dimension |
| **Consistency Score** | Agreement across 3 runs |

### 8.4 LLMs to Evaluate (Initial Release)

| Model | Provider |
|-------|----------|
| Claude 3.5 Sonnet | Anthropic |
| Claude 3 Opus | Anthropic |
| GPT-4o | OpenAI |
| GPT-4 Turbo | OpenAI |
| Gemini 1.5 Pro | Google |
| Llama 3.1 405B | Meta (via API) |
| Mistral Large | Mistral |
| Command R+ | Cohere |

---

## 10. Project Timeline

### Phase 1: Infrastructure & Data Collection (Weeks 1-6)

| Task | Duration | Deliverable |
|------|----------|-------------|
| Set up development environment | Week 1 | Docker, databases, cloud infra |
| Build web scraping pipelines | Weeks 1-3 | Scrapers for 20+ source types |
| Implement document processors | Weeks 2-3 | PDF/doc extraction pipeline |
| Build entity extraction system | Weeks 3-4 | NER models, extraction rules |
| Construct knowledge graph | Weeks 4-5 | Neo4j graph with relationships |
| Populate fact database | Weeks 5-6 | 15,000+ verified facts |
| **Milestone:** Data collection complete | Week 6 | Fact repository ready |

### Phase 2: Question Generation (Weeks 7-12)

| Task | Duration | Deliverable |
|------|----------|-------------|
| Develop generation prompts | Week 7 | Prompt library |
| Build template system | Week 7-8 | Parameterized templates |
| Implement generation pipeline | Weeks 8-9 | End-to-end generator |
| Generate candidate questions | Weeks 9-11 | 7,000+ raw questions |
| Deduplication & normalization | Weeks 11-12 | 6,000 unique questions |
| **Milestone:** Raw questions generated | Week 12 | Question candidate pool |

### Phase 3: AI Validation (Weeks 13-16)

| Task | Duration | Deliverable |
|------|----------|-------------|
| Build multi-model validator | Week 13 | Validation pipeline |
| Run validation on all questions | Weeks 13-15 | Validated question set |
| Implement difficulty estimator | Week 14 | Calibrated difficulty scores |
| Automated quality filtering | Weeks 15-16 | 5,500 validated questions |
| **Milestone:** AI validation complete | Week 16 | Validated question pool |

### Phase 4: Human Review & Control Set (Weeks 17-20)

| Task | Duration | Deliverable |
|------|----------|-------------|
| Build review interface | Week 17 | Web-based review tool |
| Recruit expert panel | Week 17 | 3-5 experts confirmed |
| **Human control set authoring** | Weeks 17-19 | 300 human-authored questions |
| Human calibration testing | Week 18 | Difficulty calibration data |
| Expert review of flagged questions | Weeks 18-19 | Resolved flagged items |
| Random sample QA | Week 19 | Quality verification |
| Final curation to 5,000 | Week 20 | Production dataset |
| **Milestone:** Dataset finalized | Week 20 | 5,000 + 300 control questions |

### Phase 5: Evaluation & Analysis (Weeks 21-24)

| Task | Duration | Deliverable |
|------|----------|-------------|
| Build evaluation runner | Week 21 | LLM test infrastructure |
| Evaluate all target LLMs | Weeks 21-23 | Raw results |
| Build results dashboard | Week 22-23 | Visualization tool |
| Analyze results | Weeks 23-24 | Statistical analysis |
| **Self-preference bias analysis** | Week 23-24 | SPS scores, held-out comparisons |
| **Human vs. LLM-generated comparison** | Week 24 | Control set analysis |
| Error categorization | Week 24 | Error taxonomy |
| **Milestone:** Evaluation complete | Week 24 | Baseline results + bias analysis |

### Phase 6: Publication & Release (Weeks 25-30)

| Task | Duration | Deliverable |
|------|----------|-------------|
| Write paper draft | Weeks 25-27 | Full paper manuscript |
| Internal review & revision | Week 28 | Revised draft |
| Prepare supplementary materials | Weeks 27-28 | Code, data, appendices |
| Submit to ArXiv | Week 28 | Preprint |
| Submit to target venue | Week 29 | Conference/journal submission |
| Public dataset release | Week 29 | GitHub, HuggingFace |
| **Milestone:** Publication submitted | Week 30 | Paper under review |

---

## 11. Team & Resources

### 10.1 Core Team (AI-First Approach)

| Role | Responsibility | FTE |
|------|----------------|-----|
| **Project Lead** | Overall coordination, paper writing | 1.0 |
| **ML/NLP Engineer** | Generation & validation pipelines | 1.0 |
| **Data Engineer** | Scraping, databases, infrastructure | 1.0 |
| **Full-Stack Developer** | Review interface, dashboard | 0.5 |
| **Wine Domain Consultant** | Guidance, final validation | 0.25 |

### 10.2 Expert Panel (Contract/Hourly)

| Role | Count | Hours | Purpose |
|------|-------|-------|---------|
| **Lead Validator (MW/MS)** | 1 | 40 | Final authority |
| **Domain Experts** | 2-3 | 30 each | Flagged question review |
| **Calibration Testers** | 5-10 | 5 each | Difficulty calibration |

### 10.3 Estimated Costs

| Category | Items | Estimated Cost |
|----------|-------|----------------|
| **Personnel** | Core team (6 months) | Variable by location |
| **LLM API Costs** | Generation + validation + evaluation | $3,000 - $8,000 |
| **Expert Fees** | ~200 total hours @ market rate | $5,000 - $15,000 |
| **Infrastructure** | Cloud compute, databases | $1,000 - $2,000 |
| **Reference Materials** | Book licenses, subscriptions | $500 - $1,000 |
| **Contingency** | 15% buffer | Variable |

---

## 12. Risk Management

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| **AI generation quality issues** | Medium | High | Multi-model validation, human QA sampling |
| **Factual errors in sources** | Medium | High | Cross-reference multiple sources, expert review |
| **Copyright/scraping concerns** | Medium | Medium | Focus on public data, respect robots.txt, cite sources |
| **LLM API costs exceed budget** | Low | Medium | Monitor usage, optimize prompts, use caching |
| **Expert availability** | Medium | Medium | Early recruitment, backup experts |
| **Difficulty miscalibration** | Medium | Medium | Human calibration subset, iterative adjustment |
| **Paper rejection** | Medium | Low | Multiple venue options, strong methodology |
| **Scope creep** | Medium | Medium | Strict phase gates, MVP focus |

---

## 13. Success Metrics

| Metric | Target |
|--------|--------|
| **Total questions** | 5,000 production-ready |
| **Category coverage** | All 6 domains, balanced distribution |
| **Regional coverage** | 60+ wine regions |
| **Grape variety coverage** | 120+ varieties |
| **AI validation pass rate** | >80% first-pass acceptance |
| **Human review agreement** | >95% agreement with AI validation |
| **Inter-annotator agreement** | >0.8 Cohen's kappa |
| **LLMs evaluated** | 8+ major models |
| **Paper submission** | Submitted within 30 weeks |
| **Open-source release** | Dataset + code on GitHub/HuggingFace |
| **Human-authored control set** | 300 questions with zero LLM involvement |
| **Multi-model generation** | No single LLM generates >35% of questions |
| **Max self-preference score** | <3 percentage points for all models |
| **Human vs. LLM-generated gap** | <5 percentage points avg. difference |
| **Held-out vs. full correlation** | >0.95 model ranking correlation |

---

## 14. Deliverables Summary

| Deliverable | Format | Release |
|-------------|--------|---------|
| **OenoBench Dataset (5,000 Q)** | JSON, CSV, HuggingFace Dataset | Public |
| **Human-Authored Control Set (300 Q)** | JSON, CSV (separate subset) | Public |
| **Evaluation Code** | Python package | Open-source (GitHub) |
| **Data Collection Pipelines** | Python/Scrapy | Open-source |
| **Results Dashboard** | Web application | Public demo |
| **Research Paper** | PDF | ArXiv + venue |
| **Bias Analysis Report** | Within paper + supplementary | With paper |
| **Supplementary Materials** | Documentation, appendices | With paper |
| **Leaderboard** | Web page | Public (optional) |

---

## 15. Future Roadmap

### Version 1.1 (3 months post-launch)
- Community feedback integration
- Additional 1,000 questions from gap analysis
- Expanded emerging regions coverage

### Version 2.0 (6-12 months post-launch)
- **Tasting Note Generation Task:** Evaluate LLM ability to generate accurate tasting notes
- **Wine Recommendation Task:** Evaluate pairing and recommendation quality
- **Multi-language Support:** French, Italian, Spanish, German versions
- **Dynamic Difficulty:** Adaptive testing based on model performance

### Ongoing
- Annual refresh with new vintages, classification changes
- Continuous LLM evaluation as new models release
- Community contribution pipeline

---

## 16. Appendices

### Appendix A: Sample Questions by Category
*[To be populated during Phase 2]*

### Appendix B: Data Source Registry
*[To be populated during Phase 1]*

### Appendix C: Generation Prompt Library
*[To be developed during Phase 2]*

### Appendix D: Validation Criteria Checklist
*[To be developed during Phase 3]*

### Appendix E: Human Review Guidelines
*[To be developed during Phase 4]*

### Appendix F: Evaluation Prompt Variations
*[To be developed during Phase 5]*

---

## Document Control

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-01-29 | [Author] | Initial draft |
| 2.0 | 2025-01-29 | [Author] | Updated to 5,000 questions; added scientific publication plan; restructured for AI-driven methodology |
| 2.1 | 2025-01-29 | [Author] | Added Section 5: Methodological Validity & Bias Mitigation; multi-model generation; human-authored control set; self-preference analysis framework |

---

*End of Project Plan*
