"""
OenoBench — Comparative question generator (Strategy 3).

Generates questions that compare 2-4 wine entities using facts from the DB.
The LLM frames the comparison, but all factual content comes from the database.
Targets 15% of all questions (1,500).

Usage:
    python -m src.generators.comparative_generator --domain wine_regions --count 10
    python -m src.generators.comparative_generator --comparison-type which_one
    python -m src.generators.comparative_generator --test-run --domain wine_regions
    python -m src.generators.comparative_generator --validate
    python -m src.generators.comparative_generator --dry-run --count 5
"""

import random
import sys
import time
from datetime import datetime
from pathlib import Path

import click
from loguru import logger

from src.generators._dedup import batch_embed_and_store, check_duplicate
from src.generators._fact_sampler import sample_fact_pairs
from src.generators._id_generator import mint_question_id
from src.generators._llm_client import GENERATOR_MODELS, get_client
from src.generators._prompts import (
    COMPARATIVE_SYSTEM,
    COMPARATIVE_TEMPLATE,
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

# ─── Comparison type descriptions ─────────────────────────────────────────────

COMPARISON_TYPES = {
    "same_vs_different": (
        "Both entities share a common trait but differ in a specific way. "
        "Ask what distinguishes them."
    ),
    "which_one": (
        "Given facts about multiple entities, ask which entity matches a "
        "specific attribute. Only one correct answer."
    ),
    "most_least": (
        "Given numeric or ordinal facts about entities, ask which has the "
        "largest, smallest, earliest, or latest value."
    ),
}


# ─── Core generation logic ────────────────────────────────────────────────────


def _extract_primary_entity(fact: dict) -> str:
    """Extract the primary entity name from a fact for prompt display."""
    entities = fact.get("entities")
    if entities:
        if isinstance(entities, str):
            import orjson
            try:
                entities = orjson.loads(entities)
            except Exception:
                return "unknown"
        for e in entities:
            if e.get("name") and e["name"] != "| varietals =":
                return e["name"]
    return fact.get("subdomain", "unknown")


def _generate_one(
    fact_a: dict,
    fact_b: dict,
    domain: str,
    comparison_type: str,
    generator: str,
) -> dict | None:
    """Generate a single comparative question from a fact pair.

    Returns result dict or None on failure.
    """
    entity_a = _extract_primary_entity(fact_a)
    entity_b = _extract_primary_entity(fact_b)
    comp_desc = COMPARISON_TYPES[comparison_type]

    prompt_rendered = build_prompt(
        COMPARATIVE_TEMPLATE,
        entity_a=entity_a,
        fact_a=fact_a["fact_text"],
        entity_b=entity_b,
        fact_b=fact_b["fact_text"],
        comparison_type=f"{comparison_type} — {comp_desc}",
    )
    phash = prompt_hash(prompt_rendered)

    client = get_client()
    model_id = GENERATOR_MODELS[generator]

    for attempt in range(1 + MAX_RETRIES):
        t0 = time.time()
        response = client.generate(
            prompt=prompt_rendered,
            system=COMPARATIVE_SYSTEM,
            model=model_id,
        )
        latency = int((time.time() - t0) * 1000)

        if not response.success:
            logger.warning(
                "LLM call failed | facts=({},{}) | attempt={} | error={}",
                fact_a["id"], fact_b["id"], attempt + 1, response.error,
            )
            continue

        # Check if LLM signaled to skip
        if response.parsed and response.parsed.get("skip"):
            logger.info(
                "LLM skipped pair | facts=({},{}) | reason={}",
                fact_a["id"], fact_b["id"],
                response.parsed.get("reason", "unspecified"),
            )
            return None

        parsed = parse_llm_response(response.content, "multiple_choice")
        if parsed is not None:
            return {
                "parsed": parsed,
                "prompt_rendered": prompt_rendered,
                "prompt_hash_val": phash,
                "response": response,
                "latency_ms": latency,
            }

        logger.warning(
            "Parse failed | facts=({},{}) | attempt={}",
            fact_a["id"], fact_b["id"], attempt + 1,
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
@click.option(
    "--comparison-type",
    type=click.Choice(["same_vs_different", "which_one", "most_least"]),
    default="same_vs_different",
    help="Comparison type",
)
@click.option("--dry-run", is_flag=True, help="Generate but don't insert into DB")
@click.option("--test-run", is_flag=True, help="Generate 3 questions, print details")
@click.option("--validate", is_flag=True, help="Quality checks on existing questions")
@click.option("--all", "run_all", is_flag=True, help="Generate full quota (1500)")
def main(domain, count, generator, comparison_type, dry_run, test_run, validate, run_all):
    """Generate comparative benchmark questions from fact pairs via LLM."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    logger.add(LOG_DIR / f"comparative_{timestamp}.log", rotation="50 MB")

    if validate:
        _run_validate()
        return

    if not domain:
        logger.error("--domain is required for generation (use --validate without it)")
        sys.exit(1)

    if test_run:
        _run_test(domain, generator, comparison_type)
        return

    target = count
    if run_all:
        target = 1500
        logger.info(f"--all mode: targeting {target} comparative questions")

    _run_generate(domain, target, generator, comparison_type, dry_run)


# ─── Generate run ─────────────────────────────────────────────────────────────


def _run_generate(
    domain: str,
    count: int,
    generator: str,
    comparison_type: str,
    dry_run: bool,
):
    """Main generation loop."""
    logger.info(
        "Starting comparative generation | domain={} | count={} | generator={} | "
        "comparison_type={} | dry_run={}",
        domain, count, generator, comparison_type, dry_run,
    )

    used_fact_ids = get_used_fact_ids()
    run_used_ids: set[str] = set()
    generated = 0
    skipped_parse = 0
    skipped_dup = 0
    inserted_uuids: list[str] = []

    while generated < count:
        batch_size = min(count - generated, 10)
        pairs = sample_fact_pairs(domain, batch_size, exclude_ids=used_fact_ids | run_used_ids)
        if not pairs:
            logger.warning("No more fact pairs available for domain={}", domain)
            break

        for fact_a, fact_b in pairs:
            if generated >= count:
                break

            run_used_ids.add(str(fact_a["id"]))
            run_used_ids.add(str(fact_b["id"]))

            result = _generate_one(fact_a, fact_b, domain, comparison_type, generator)
            if result is None:
                skipped_parse += 1
                logger.info(
                    "SKIP (parse/skip) | facts=({},{}) | generator={}",
                    fact_a["id"], fact_b["id"], generator,
                )
                continue

            parsed = result["parsed"]

            # Dedup check
            is_dup, dup_id = check_duplicate(parsed.question_text)
            if is_dup:
                skipped_dup += 1
                logger.info(
                    "SKIP (duplicate) | question matches existing {} | facts=({},{})",
                    dup_id, fact_a["id"], fact_b["id"],
                )
                continue

            if dry_run:
                generated += 1
                logger.info(
                    "DRY-RUN | #{} | facts=({},{}) | Q: {}",
                    generated, fact_a["id"], fact_b["id"],
                    parsed.question_text[:80],
                )
                continue

            # Assign difficulty based on comparison type
            difficulty = random.choice(["2", "3"])
            qid = mint_question_id(domain, difficulty)
            options_dicts = (
                [{"id": o.id, "text": o.text} for o in parsed.options]
                if parsed.options
                else None
            )

            question_data = {
                "question_id": qid,
                "domain": domain,
                "subdomain": fact_a.get("subdomain"),
                "question_type": "multiple_choice",
                "difficulty": difficulty,
                "cognitive_dim": "analysis",
                "question_text": parsed.question_text,
                "options": options_dicts,
                "correct_answer": parsed.correct_answer,
                "correct_answer_text": parsed.correct_answer_text,
                "explanation": parsed.explanation,
                "tags": parsed.tags + [f"comparative:{comparison_type}"],
            }

            generation_meta = {
                "generator": generator,
                "generator_version": result["response"].model,
                "generation_method": "comparative",
                "template_id": "COMPARATIVE_TEMPLATE",
                "llm_creativity": "medium",
                "prompt_hash": result["prompt_hash_val"],
                "raw_response": {
                    "content": result["response"].content,
                    "input_tokens": result["response"].input_tokens,
                    "output_tokens": result["response"].output_tokens,
                    "latency_ms": result["latency_ms"],
                },
            }

            q_uuid = insert_question(
                question_data, generation_meta,
                fact_ids=[str(fact_a["id"]), str(fact_b["id"])],
                source_ids=list({str(fact_a["source_id"]), str(fact_b["source_id"])}),
            )
            if q_uuid:
                generated += 1
                inserted_uuids.append(q_uuid)
                logger.info(
                    "OK | #{} | {} | facts=({},{}) | Q: {}",
                    generated, qid, fact_a["id"], fact_b["id"],
                    parsed.question_text[:80],
                )
            else:
                logger.error(
                    "DB insert failed for facts=({},{})",
                    fact_a["id"], fact_b["id"],
                )

    # Batch-embed inserted questions for future dedup
    if inserted_uuids:
        embedded = batch_embed_and_store(inserted_uuids)
        logger.info(f"Embedded {embedded}/{len(inserted_uuids)} new questions")

    logger.info(
        "Comparative generation complete | generated={} | skipped_parse={} | "
        "skipped_dup={} | dry_run={}",
        generated, skipped_parse, skipped_dup, dry_run,
    )
    click.echo(
        f"\nDone: {generated} comparative questions generated, "
        f"{skipped_parse} parse/skip failures, {skipped_dup} duplicates skipped."
    )


# ─── Test run ─────────────────────────────────────────────────────────────────


def _run_test(domain: str, generator: str, comparison_type: str):
    """Generate 3 questions and print details without DB insertion."""
    click.echo(f"\n=== Comparative Test Run: {domain} / {generator} / {comparison_type} ===\n")

    used = get_used_fact_ids()
    pairs = sample_fact_pairs(domain, 3, exclude_ids=used)
    if not pairs:
        click.echo("No fact pairs available for this domain.")
        return

    for i, (fact_a, fact_b) in enumerate(pairs[:3], 1):
        click.echo(f"--- Question {i}/3 ---")
        click.echo(f"Fact A [{fact_a.get('subdomain')}]: {fact_a['fact_text']}")
        click.echo(f"Fact B [{fact_b.get('subdomain')}]: {fact_b['fact_text']}")
        click.echo(f"Generator: {generator} ({GENERATOR_MODELS[generator]})")
        click.echo(f"Comparison: {comparison_type}")

        result = _generate_one(fact_a, fact_b, domain, comparison_type, generator)
        if result is None:
            click.echo("  FAILED: could not parse LLM response or LLM skipped\n")
            continue

        parsed = result["parsed"]
        click.echo(f"Question:    {parsed.question_text}")
        if parsed.options:
            for opt in parsed.options:
                marker = " *" if opt.id in parsed.correct_answer else ""
                click.echo(f"  {opt.id}) {opt.text}{marker}")
        click.echo(f"Answer:      {parsed.correct_answer}")
        if parsed.correct_answer_text:
            click.echo(f"Answer text: {parsed.correct_answer_text}")
        click.echo(f"Explanation: {parsed.explanation}")
        click.echo(f"Tags:        {parsed.tags}")
        click.echo(f"Latency:     {result['latency_ms']}ms")
        click.echo()

    click.echo("Test run complete. No questions were inserted into the database.")


# ─── Validate ─────────────────────────────────────────────────────────────────


def _run_validate():
    """Quality checks on existing comparative questions."""
    conn = get_pg()
    cur = conn.cursor()

    click.echo("\n=== Comparative Question Validation Report ===\n")

    # Questions by domain
    cur.execute(
        """
        SELECT q.domain, count(*) AS cnt
        FROM questions q
        JOIN generation_metadata gm ON gm.question_id = q.id
        WHERE gm.generation_method = 'comparative'
        GROUP BY q.domain ORDER BY q.domain
        """
    )
    rows = cur.fetchall()
    total = sum(r["cnt"] for r in rows)
    click.echo(f"Total comparative questions: {total}")
    click.echo("\nBy domain:")
    for r in rows:
        click.echo(f"  {r['domain']:20s} {r['cnt']}")

    # By comparison type (from tags)
    cur.execute(
        """
        SELECT
            CASE
                WHEN 'comparative:same_vs_different' = ANY(q.tags) THEN 'same_vs_different'
                WHEN 'comparative:which_one' = ANY(q.tags) THEN 'which_one'
                WHEN 'comparative:most_least' = ANY(q.tags) THEN 'most_least'
                ELSE 'unknown'
            END AS comp_type,
            count(*) AS cnt
        FROM questions q
        JOIN generation_metadata gm ON gm.question_id = q.id
        WHERE gm.generation_method = 'comparative'
        GROUP BY comp_type ORDER BY comp_type
        """
    )
    rows = cur.fetchall()
    click.echo("\nBy comparison type:")
    for r in rows:
        click.echo(f"  {r['comp_type']:25s} {r['cnt']}")

    # Generator distribution
    cur.execute(
        """
        SELECT gm.generator, count(*) AS cnt
        FROM questions q
        JOIN generation_metadata gm ON gm.question_id = q.id
        WHERE gm.generation_method = 'comparative'
        GROUP BY gm.generator ORDER BY gm.generator
        """
    )
    rows = cur.fetchall()
    click.echo("\nGenerator distribution:")
    for r in rows:
        click.echo(f"  {r['generator']:20s} {r['cnt']}")

    # Fact linkage — each comparative question should link to 2 facts
    cur.execute(
        """
        SELECT q.question_id, count(qf.fact_id) AS fact_count
        FROM questions q
        JOIN generation_metadata gm ON gm.question_id = q.id
        LEFT JOIN question_facts qf ON qf.question_id = q.id
        WHERE gm.generation_method = 'comparative'
        GROUP BY q.question_id
        HAVING count(qf.fact_id) != 2
        """
    )
    bad_links = cur.fetchall()
    click.echo(f"\nQuestions with != 2 linked facts: {len(bad_links)}")
    for r in bad_links[:5]:
        click.echo(f"  {r['question_id']}: {r['fact_count']} facts")

    # Quality: missing explanations
    cur.execute(
        """
        SELECT count(*) AS cnt FROM questions q
        JOIN generation_metadata gm ON gm.question_id = q.id
        WHERE gm.generation_method = 'comparative'
          AND (q.explanation IS NULL OR q.explanation = '')
        """
    )
    no_expl = cur.fetchone()["cnt"]
    click.echo(f"\nMissing explanations: {no_expl}")

    # 10 random samples with source facts
    cur.execute(
        """
        SELECT q.question_id, q.question_text, q.correct_answer, q.domain,
               array_agg(f.fact_text) AS source_facts
        FROM questions q
        JOIN generation_metadata gm ON gm.question_id = q.id
        JOIN question_facts qf ON qf.question_id = q.id
        JOIN facts f ON f.id = qf.fact_id
        WHERE gm.generation_method = 'comparative'
        GROUP BY q.question_id, q.question_text, q.correct_answer, q.domain
        ORDER BY random()
        LIMIT 10
        """
    )
    samples = cur.fetchall()
    if samples:
        click.echo(f"\nRandom sample ({len(samples)} questions):")
        for s in samples:
            click.echo(f"\n  [{s['question_id']}] ({s['domain']})")
            click.echo(f"  Q: {s['question_text'][:120]}")
            click.echo(f"  A: {s['correct_answer']}")
            for i, ft in enumerate(s["source_facts"], 1):
                click.echo(f"  Fact {i}: {ft[:100]}")

    click.echo("\nValidation complete.\n")


if __name__ == "__main__":
    main()
