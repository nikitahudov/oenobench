"""
OenoBench — Distractor-mined question generator (Strategy 5).

Generates questions where wrong answers are mined from related facts about
different entities, making them factually true but wrong for the specific
question. This produces harder questions (Level 3-4) because distractors
are real facts, not fabrications.

Usage:
    python -m src.generators.distractor_miner --domain wine_regions --count 10
    python -m src.generators.distractor_miner --generator chatgpt --domain winemaking
    python -m src.generators.distractor_miner --test-run --domain grape_varieties
    python -m src.generators.distractor_miner --validate
    python -m src.generators.distractor_miner --dry-run --count 5 --domain viticulture
"""

import random
import sys
import time
from datetime import datetime
from pathlib import Path

import click
from loguru import logger

from src.generators._dedup import batch_embed_and_store, check_duplicate
from src.generators._fact_sampler import (
    _auto_distractor_type,
    _classify_dimension,
    sample_confusable_facts,
    sample_facts,
    _is_fact_rich,
)
from src.generators._id_generator import mint_question_id
from src.generators._llm_client import GENERATOR_MODELS, get_client
from src.generators._prompts import (
    DISTRACTOR_SYSTEM,
    DISTRACTOR_TEMPLATE,
    DISTRACTOR_TEMPLATE_ATTRIBUTE_SWAP,
    DISTRACTOR_TEMPLATE_ENTITY_ID,
    DISTRACTOR_TEMPLATE_NUMERIC,
    build_prompt,
    prompt_hash,
)
from src.generators._question_db import get_used_fact_ids, insert_question
from src.generators._schemas import parse_llm_response
from src.utils.db import get_pg

# ─── Logging setup ────────────────────────────────────────────────────────────

LOG_DIR = Path("data/logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)

MAX_RETRIES = 1

# Template selection by distractor type
DISTRACTOR_TEMPLATE_MAP = {
    "attribute_swap": DISTRACTOR_TEMPLATE_ATTRIBUTE_SWAP,
    "entity_id": DISTRACTOR_TEMPLATE_ENTITY_ID,
    "numeric": DISTRACTOR_TEMPLATE_NUMERIC,
}


# ─── Distractor sampling ─────────────────────────────────────────────────────


def _sample_target_and_distractors(
    domain: str,
    exclude_ids: set[str],
) -> tuple[dict, list[dict], str] | None:
    """Sample 1 target fact and confusable distractor facts.

    Distractors are from the SAME subdomain or share entity types with the
    target, so wrong answers are plausible — not obviously about unrelated entities.
    Dimension-matched distractors are preferred.

    Returns (target_fact, distractor_facts, distractor_type) or None.
    """
    # Get a random target fact with entities — must have rich wine content
    targets = sample_facts(domain, 5, min_confidence=0.7, exclude_ids=exclude_ids, strategy="distractor_mining")
    target = None
    for t in targets:
        if _is_fact_rich(t["fact_text"]):
            target = t
            break
    if target is None:
        return None

    # Classify target dimension
    target_dim = _classify_dimension(target["fact_text"])
    target["_dimension"] = target_dim

    # Get confusable distractors (dimension-aware, same subdomain or shared entity types)
    distractors = sample_confusable_facts(
        target, domain, count=5, exclude_ids=exclude_ids,
    )

    if len(distractors) < 2:
        logger.debug(
            "Not enough distractor facts for subdomain={} (got {})",
            target["subdomain"], len(distractors),
        )
        return None

    # Auto-select distractor type based on dimension alignment
    distractor_dims = [d.get("_dimension") for d in distractors]
    dtype = _auto_distractor_type(target_dim, distractor_dims)

    return target, distractors, dtype


# ─── Core generation logic ────────────────────────────────────────────────────


def _format_distractor_facts(distractors: list[dict]) -> str:
    """Format distractor facts as a numbered list for the prompt."""
    lines = []
    for i, fact in enumerate(distractors, 1):
        sub = fact.get("subdomain", "unknown")
        # Include primary entity name so the LLM knows what each distractor is about
        entity_name = _extract_primary_entity_name(fact)
        lines.append(
            f"{i}. {fact['fact_text']}  [Entity: {entity_name}, Subdomain: {sub}]"
        )
    return "\n".join(lines)


def _extract_primary_entity_name(fact: dict) -> str:
    """Extract the primary entity name from a fact for display."""
    entities = fact.get("entities")
    if entities:
        if isinstance(entities, str):
            import orjson
            try:
                entities = orjson.loads(entities)
            except Exception:
                return "unknown"
        for e in entities:
            if e.get("type") in ("region", "grape", "appellation", "producer", "ava"):
                return e.get("name", "unknown")
    return fact.get("subdomain", "unknown")


def _generate_one(
    target: dict,
    distractors: list[dict],
    domain: str,
    generator: str,
    distractor_type: str = "entity_id",
    labelled_difficulty: str | None = None,
) -> dict | None:
    """Generate a single distractor-mined question.

    Returns result dict or None on failure.
    """
    distractor_block = _format_distractor_facts(distractors)
    template = DISTRACTOR_TEMPLATE_MAP.get(distractor_type, DISTRACTOR_TEMPLATE)

    # Build structured confusability context from distractor metadata
    target_dim = target.get("_dimension")
    contexts = [d.get("_confusability_context", "") for d in distractors if d.get("_confusability_context")]
    if contexts:
        confusability_context = contexts[0]
    else:
        confusability_context = "similar entities from the same domain"

    prompt_rendered = build_prompt(
        template,
        fact_text=target["fact_text"],
        distractor_facts=distractor_block,
        dimension=target_dim or "unspecified",
        confusability_context=confusability_context,
    )
    phash = prompt_hash(prompt_rendered)

    client = get_client()
    model_id = GENERATOR_MODELS[generator]

    for attempt in range(1 + MAX_RETRIES):
        t0 = time.time()
        response = client.generate(
            prompt=prompt_rendered,
            system=DISTRACTOR_SYSTEM,
            model=model_id,
        )
        latency = int((time.time() - t0) * 1000)

        if not response.success:
            logger.warning(
                "LLM call failed | target_fact={} | attempt={} | error={}",
                target["id"], attempt + 1, response.error,
            )
            continue

        # Check for skip signal
        if response.parsed and response.parsed.get("skip"):
            logger.info(
                "LLM skipped fact | fact={} | reason={}",
                target["id"], response.parsed.get("reason", "unspecified"),
            )
            return None

        # Source-fact list for the paraphrase guard: target fact is the
        # primary source (its content drives the correct answer); distractor
        # facts are also linked to the question and must not be copied verbatim
        # into options.
        all_source_facts = [target["fact_text"]] + [d["fact_text"] for d in distractors]
        parsed = parse_llm_response(
            response.content,
            "multiple_choice",
            source_fact_texts=all_source_facts,
            verify_with_independent_solver=True,
            verify_difficulty_with_c4=True,
            labelled_difficulty=labelled_difficulty,
            generator=generator,
        )
        if parsed is not None:
            return {
                "parsed": parsed,
                "prompt_rendered": prompt_rendered,
                "prompt_hash_val": phash,
                "response": response,
                "latency_ms": latency,
            }

        logger.warning(
            "Parse failed | target_fact={} | attempt={}",
            target["id"], attempt + 1,
        )

    return None


# ─── CLI ──────────────────────────────────────────────────────────────────────


@click.command()
@click.option(
    "--domain",
    type=click.Choice([
        "wine_regions", "winemaking", "viticulture",
        "grape_varieties", "wine_business", "producers",
    ]),
    help="Domain to generate questions for",
)
@click.option("--count", type=int, default=10, help="Number of questions to generate")
@click.option(
    "--generator",
    type=click.Choice(["claude", "chatgpt", "gemini", "llama", "qwen"]),
    default="claude",
    help="LLM generator to use",
)
@click.option("--dry-run", is_flag=True, help="Generate but don't insert into DB")
@click.option("--test-run", is_flag=True, help="Generate 3 questions, print details")
@click.option("--validate", is_flag=True, help="Quality checks on existing questions")
@click.option("--all", "run_all", is_flag=True, help="Generate full quota (1000)")
def main(domain, count, generator, dry_run, test_run, validate, run_all):
    """Generate distractor-mined questions where wrong answers are real facts about other entities."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    logger.add(LOG_DIR / f"distractor_{timestamp}.log", rotation="50 MB")

    if validate:
        _run_validate()
        return

    if not domain:
        logger.error("--domain is required for generation (use --validate without it)")
        sys.exit(1)

    if test_run:
        _run_test(domain, generator)
        return

    target = count
    if run_all:
        target = 1000
        logger.info(f"--all mode: targeting {target} distractor-mined questions")

    _run_generate(domain, target, generator, dry_run)


# ─── Generate run ─────────────────────────────────────────────────────────────


def _run_generate(
    domain: str,
    count: int,
    generator: str,
    dry_run: bool,
):
    """Main generation loop."""
    logger.info(
        "Starting distractor mining | domain={} | count={} | generator={} | "
        "dry_run={}",
        domain, count, generator, dry_run,
    )

    used_fact_ids = get_used_fact_ids()
    run_used_ids: set[str] = set()
    generated = 0
    skipped_parse = 0
    skipped_dup = 0
    skipped_sample = 0
    inserted_uuids: list[str] = []

    max_attempts = count * 5  # prevent infinite loops if facts are exhausted
    attempts = 0

    while generated < count and attempts < max_attempts:
        attempts += 1

        result_tuple = _sample_target_and_distractors(
            domain, exclude_ids=used_fact_ids | run_used_ids,
        )
        if result_tuple is None:
            skipped_sample += 1
            if skipped_sample > 20:
                logger.warning("Too many sampling failures, stopping")
                break
            continue

        target_fact, distractor_facts, dtype = result_tuple
        all_fact_ids = {str(target_fact["id"])} | {str(f["id"]) for f in distractor_facts}
        run_used_ids.update(all_fact_ids)

        # Difficulty 3-4 for distractor-mined questions. v2.2 fix #5 —
        # threaded into C4 gen-time gate inside parse_llm_response.
        difficulty = str(random.choice([3, 4]))

        result = _generate_one(
            target_fact, distractor_facts, domain, generator, dtype,
            labelled_difficulty=difficulty,
        )
        if result is None:
            skipped_parse += 1
            logger.info(
                "SKIP (parse/skip) | target_fact={} | generator={}",
                target_fact["id"], generator,
            )
            continue

        parsed = result["parsed"]

        # Dedup check
        is_dup, dup_id = check_duplicate(parsed.question_text)
        if is_dup:
            skipped_dup += 1
            logger.info(
                "SKIP (duplicate) | question matches existing {} | target_fact={}",
                dup_id, target_fact["id"],
            )
            continue

        if dry_run:
            generated += 1
            logger.info(
                "DRY-RUN | #{} | target_fact={} | Q: {}",
                generated, target_fact["id"], parsed.question_text[:80],
            )
            continue

        # Mint ID and insert
        qid = mint_question_id(domain, difficulty)
        options_dicts = (
            [{"id": o.id, "text": o.text} for o in parsed.options]
            if parsed.options
            else None
        )

        question_data = {
            "question_id": qid,
            "domain": domain,
            "subdomain": target_fact.get("subdomain"),
            "question_type": "multiple_choice",
            "difficulty": difficulty,
            "cognitive_dim": "analysis",
            "question_text": parsed.question_text,
            "options": options_dicts,
            "correct_answer": parsed.correct_answer,
            "correct_answer_text": parsed.correct_answer_text,
            "explanation": parsed.explanation,
            "tags": parsed.tags + [f"distractor:{dtype}"],
        }

        generation_meta = {
            "generator": generator,
            "generator_version": result["response"].model,
            "generation_method": "distractor_mining",
            "template_id": f"DISTRACTOR_TEMPLATE_{dtype.upper()}",
            "llm_creativity": "medium",
            "prompt_hash": result["prompt_hash_val"],
            "raw_response": {
                "content": result["response"].content,
                "input_tokens": result["response"].input_tokens,
                "output_tokens": result["response"].output_tokens,
                "latency_ms": result["latency_ms"],
            },
        }

        # Link both target fact AND distractor facts
        fact_ids = [str(target_fact["id"])] + [str(f["id"]) for f in distractor_facts]
        source_ids = list(
            {str(target_fact["source_id"])} |
            {str(f["source_id"]) for f in distractor_facts}
        )

        q_uuid = insert_question(
            question_data, generation_meta,
            fact_ids=fact_ids,
            source_ids=source_ids,
        )
        if q_uuid:
            generated += 1
            inserted_uuids.append(q_uuid)
            logger.info(
                "OK | #{} | {} | target_fact={} | distractors={} | Q: {}",
                generated, qid, target_fact["id"],
                len(distractor_facts), parsed.question_text[:80],
            )
        else:
            logger.error("DB insert failed for target_fact={}", target_fact["id"])

    # Batch-embed inserted questions for future dedup
    if inserted_uuids:
        embedded = batch_embed_and_store(inserted_uuids)
        logger.info(f"Embedded {embedded}/{len(inserted_uuids)} new questions")

    logger.info(
        "Distractor mining complete | generated={} | skipped_parse={} | "
        "skipped_dup={} | skipped_sample={} | dry_run={}",
        generated, skipped_parse, skipped_dup, skipped_sample, dry_run,
    )
    click.echo(
        f"\nDone: {generated} distractor-mined questions generated, "
        f"{skipped_parse} parse failures, {skipped_dup} duplicates skipped, "
        f"{skipped_sample} sampling failures."
    )


# ─── Test run ─────────────────────────────────────────────────────────────────


def _run_test(domain: str, generator: str):
    """Generate 3 distractor-mined questions and print details."""
    click.echo(f"\n=== Test Run: {domain} / {generator} / distractor-mined ===\n")

    used = get_used_fact_ids()
    tested = 0

    for i in range(1, 4):
        result_tuple = _sample_target_and_distractors(domain, exclude_ids=used)
        if result_tuple is None:
            click.echo(f"--- Question {i}/3 ---")
            click.echo("  Could not sample target + distractors\n")
            continue

        target_fact, distractor_facts, dtype = result_tuple
        used.add(str(target_fact["id"]))

        click.echo(f"--- Question {i}/3 ---")
        click.echo(f"Target fact:  {target_fact['fact_text'][:100]}")
        click.echo(f"  Subdomain:  {target_fact.get('subdomain')}")
        click.echo(f"  Dimension:  {target_fact.get('_dimension', 'unclassified')}")
        click.echo(f"Distractors:  {len(distractor_facts)} facts | type: {dtype}")
        for j, df in enumerate(distractor_facts, 1):
            dim = df.get("_dimension", "?")
            ctx = df.get("_confusability_context", "")
            click.echo(f"  D{j} [{df.get('subdomain')}] (dim={dim}): {df['fact_text'][:80]}")
            if ctx and j == 1:
                click.echo(f"     Context: {ctx}")
        click.echo(f"Generator:    {generator} ({GENERATOR_MODELS[generator]})")

        result = _generate_one(
            target_fact, distractor_facts, domain, generator, dtype,
            labelled_difficulty=str(random.choice([3, 4])),
        )
        if result is None:
            click.echo("  FAILED: could not parse LLM response\n")
            continue

        parsed = result["parsed"]
        click.echo(f"Question:     {parsed.question_text}")
        if parsed.options:
            for opt in parsed.options:
                marker = " *" if opt.id in parsed.correct_answer else ""
                click.echo(f"  {opt.id}) {opt.text}{marker}")
        click.echo(f"Answer:       {parsed.correct_answer}")
        if parsed.correct_answer_text:
            click.echo(f"Answer text:  {parsed.correct_answer_text}")
        click.echo(f"Explanation:  {parsed.explanation}")
        click.echo(f"Tags:         {parsed.tags}")
        click.echo(f"Latency:      {result['latency_ms']}ms")
        click.echo()
        tested += 1

    click.echo(f"Test run complete ({tested}/3 generated). "
               "No questions were inserted into the database.")


# ─── Validate ─────────────────────────────────────────────────────────────────


def _run_validate():
    """Quality checks on existing distractor-mined questions."""
    conn = get_pg()
    cur = conn.cursor()

    click.echo("\n=== Distractor Miner Validation Report ===\n")

    # Questions by domain
    cur.execute(
        """
        SELECT q.domain, count(*) AS cnt
        FROM questions q
        JOIN generation_metadata gm ON gm.question_id = q.id
        WHERE gm.generation_method = 'distractor_mining'
        GROUP BY q.domain ORDER BY q.domain
        """
    )
    rows = cur.fetchall()
    total = sum(r["cnt"] for r in rows)
    click.echo(f"Total distractor-mined questions: {total}")
    click.echo("By domain:")
    for r in rows:
        click.echo(f"  {r['domain']:20s} {r['cnt']}")

    # By distractor type (from tags)
    cur.execute(
        """
        SELECT
            CASE
                WHEN 'distractor:attribute_swap' = ANY(q.tags) THEN 'attribute_swap'
                WHEN 'distractor:entity_id' = ANY(q.tags) THEN 'entity_id'
                WHEN 'distractor:numeric' = ANY(q.tags) THEN 'numeric'
                ELSE 'unknown'
            END AS dtype,
            count(*) AS cnt
        FROM questions q
        JOIN generation_metadata gm ON gm.question_id = q.id
        WHERE gm.generation_method = 'distractor_mining'
        GROUP BY dtype ORDER BY dtype
        """
    )
    rows = cur.fetchall()
    click.echo("\nBy distractor type:")
    for r in rows:
        click.echo(f"  {r['dtype']:25s} {r['cnt']}")

    # By difficulty (should be 3-4)
    cur.execute(
        """
        SELECT q.difficulty, count(*) AS cnt
        FROM questions q
        JOIN generation_metadata gm ON gm.question_id = q.id
        WHERE gm.generation_method = 'distractor_mining'
        GROUP BY q.difficulty ORDER BY q.difficulty
        """
    )
    rows = cur.fetchall()
    click.echo("\nBy difficulty:")
    for r in rows:
        click.echo(f"  Level {r['difficulty']:5s} {r['cnt']}")
    low_diff = sum(r["cnt"] for r in rows if r["difficulty"] in ("1", "2"))
    if low_diff:
        click.echo(f"  WARNING: {low_diff} questions below expected L3-4 difficulty")

    # Facts per question (should be 4-6: 1 target + 3-5 distractors)
    cur.execute(
        """
        SELECT q.id, count(qf.fact_id) AS fact_count
        FROM questions q
        JOIN generation_metadata gm ON gm.question_id = q.id
        JOIN question_facts qf ON qf.question_id = q.id
        WHERE gm.generation_method = 'distractor_mining'
        GROUP BY q.id
        """
    )
    rows = cur.fetchall()
    if rows:
        counts = [r["fact_count"] for r in rows]
        click.echo(f"\nFacts per question: min={min(counts)}, max={max(counts)}, "
                    f"avg={sum(counts)/len(counts):.1f}")
        single_fact = sum(1 for c in counts if c < 2)
        if single_fact:
            click.echo(f"  WARNING: {single_fact} questions linked to <2 facts "
                        "(expected target + distractors)")

    # Generator distribution
    cur.execute(
        """
        SELECT gm.generator, count(*) AS cnt
        FROM questions q
        JOIN generation_metadata gm ON gm.question_id = q.id
        WHERE gm.generation_method = 'distractor_mining'
        GROUP BY gm.generator ORDER BY gm.generator
        """
    )
    rows = cur.fetchall()
    click.echo("\nGenerator distribution:")
    for r in rows:
        click.echo(f"  {r['generator']:20s} {r['cnt']}")

    # 5 random samples with linked fact count
    cur.execute(
        """
        SELECT q.question_id, q.question_text, q.correct_answer, q.domain,
               q.difficulty, count(qf.fact_id) AS linked_facts
        FROM questions q
        JOIN generation_metadata gm ON gm.question_id = q.id
        JOIN question_facts qf ON qf.question_id = q.id
        WHERE gm.generation_method = 'distractor_mining'
        GROUP BY q.id, q.question_id, q.question_text, q.correct_answer,
                 q.domain, q.difficulty
        ORDER BY random()
        LIMIT 5
        """
    )
    samples = cur.fetchall()
    if samples:
        click.echo(f"\nRandom sample ({len(samples)} questions):")
        for s in samples:
            click.echo(f"\n  [{s['question_id']}] ({s['domain']}) L{s['difficulty']} "
                        f"[{s['linked_facts']} linked facts]")
            click.echo(f"  Q: {s['question_text'][:150]}")
            click.echo(f"  A: {s['correct_answer']}")

    click.echo("\nValidation complete.\n")


if __name__ == "__main__":
    main()
