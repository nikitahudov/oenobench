"""
OenoBench — Scenario-based question generator (Strategy 4).

Synthesizes 2-4 related facts into realistic wine scenarios that test
application, analysis, and synthesis skills. Targets 10% of all questions
(~1,000). These are inherently higher-difficulty (Level 2-4).

Usage:
    python -m src.generators.scenario_generator --domain wine_regions --count 10
    python -m src.generators.scenario_generator --scenario-type tasting --generator chatgpt
    python -m src.generators.scenario_generator --test-run --domain winemaking
    python -m src.generators.scenario_generator --validate
    python -m src.generators.scenario_generator --dry-run --count 5 --domain viticulture
"""

import random
import sys
import time
from datetime import datetime
from pathlib import Path

import click
from loguru import logger

from src.generators._dedup import batch_embed_and_store, check_duplicate
from src.generators._fact_sampler import sample_fact_clusters
from src.generators._id_generator import mint_question_id
from src.generators._llm_client import GENERATOR_MODELS, get_client
from src.generators._prompts import (
    SCENARIO_SYSTEM,
    SCENARIO_TEMPLATE,
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

SCENARIO_TYPES = ["winemaking", "tasting", "business", "service", "viticulture"]

# Default cognitive dimensions for scenario questions (higher-order)
_COGNITIVE_DIMS = ["application", "analysis", "synthesis"]


# ─── Core generation logic ────────────────────────────────────────────────────


def _format_facts_block(cluster: list[dict]) -> str:
    """Format a cluster of facts into a numbered block for the prompt."""
    lines = []
    for i, fact in enumerate(cluster, 1):
        src = fact.get("source_name", "unknown")
        lines.append(f"{i}. {fact['fact_text']}  [Source: {src}]")
    return "\n".join(lines)


def _generate_one(
    cluster: list[dict],
    domain: str,
    scenario_type: str,
    generator: str,
) -> dict | None:
    """Generate a single scenario question from a fact cluster.

    Returns result dict or None on failure.
    """
    facts_block = _format_facts_block(cluster)

    prompt_rendered = build_prompt(
        SCENARIO_TEMPLATE,
        facts=facts_block,
        scenario_type=scenario_type,
    )
    phash = prompt_hash(prompt_rendered)

    client = get_client()
    model_id = GENERATOR_MODELS[generator]

    for attempt in range(1 + MAX_RETRIES):
        t0 = time.time()
        response = client.generate(
            prompt=prompt_rendered,
            system=SCENARIO_SYSTEM,
            model=model_id,
        )
        latency = int((time.time() - t0) * 1000)

        if not response.success:
            logger.warning(
                "LLM call failed | cluster subdomain={} | attempt={} | error={}",
                cluster[0].get("subdomain"), attempt + 1, response.error,
            )
            continue

        # Check for skip signal
        if response.parsed and response.parsed.get("skip"):
            logger.info(
                "LLM skipped cluster | subdomain={} | reason={}",
                cluster[0].get("subdomain"),
                response.parsed.get("reason", "unspecified"),
            )
            return None

        parsed = parse_llm_response(response.content, "scenario_based")
        if parsed is not None:
            return {
                "parsed": parsed,
                "prompt_rendered": prompt_rendered,
                "prompt_hash_val": phash,
                "response": response,
                "latency_ms": latency,
            }

        logger.warning(
            "Parse failed | subdomain={} | attempt={}",
            cluster[0].get("subdomain"), attempt + 1,
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
    "--scenario-type",
    type=click.Choice(SCENARIO_TYPES),
    default="winemaking",
    help="Scenario type to generate",
)
@click.option("--dry-run", is_flag=True, help="Generate but don't insert into DB")
@click.option("--test-run", is_flag=True, help="Generate 3 questions, print details")
@click.option("--validate", is_flag=True, help="Quality checks on existing questions")
@click.option("--all", "run_all", is_flag=True, help="Generate full quota (1000)")
def main(domain, count, generator, scenario_type, dry_run, test_run, validate, run_all):
    """Generate scenario-based questions by synthesizing fact clusters via LLM."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    logger.add(LOG_DIR / f"scenario_{timestamp}.log", rotation="50 MB")

    if validate:
        _run_validate()
        return

    if not domain:
        logger.error("--domain is required for generation (use --validate without it)")
        sys.exit(1)

    if test_run:
        _run_test(domain, generator, scenario_type)
        return

    target = count
    if run_all:
        target = 1000
        logger.info(f"--all mode: targeting {target} scenario questions")

    _run_generate(domain, target, generator, scenario_type, dry_run)


# ─── Generate run ─────────────────────────────────────────────────────────────


def _run_generate(
    domain: str,
    count: int,
    generator: str,
    scenario_type: str,
    dry_run: bool,
):
    """Main generation loop."""
    logger.info(
        "Starting scenario generation | domain={} | count={} | generator={} | "
        "scenario_type={} | dry_run={}",
        domain, count, generator, scenario_type, dry_run,
    )

    used_fact_ids = get_used_fact_ids()
    run_used_ids: set[str] = set()
    generated = 0
    skipped_parse = 0
    skipped_dup = 0
    inserted_uuids: list[str] = []

    while generated < count:
        batch_size = min(count - generated, 5)
        clusters = sample_fact_clusters(
            domain, batch_size, cluster_size=3,
            exclude_ids=used_fact_ids | run_used_ids,
        )
        if not clusters:
            logger.warning("No more fact clusters available for domain={}", domain)
            break

        for cluster in clusters:
            if generated >= count:
                break

            cluster_ids = {str(f["id"]) for f in cluster}
            run_used_ids.update(cluster_ids)

            # Randomly pick difficulty (2-4) and cognitive dim for variety
            difficulty = str(random.randint(2, 4))
            cognitive_dim = random.choice(_COGNITIVE_DIMS)

            result = _generate_one(cluster, domain, scenario_type, generator)
            if result is None:
                skipped_parse += 1
                logger.info(
                    "SKIP (parse/skip) | subdomain={} | generator={}",
                    cluster[0].get("subdomain"), generator,
                )
                continue

            parsed = result["parsed"]

            # Dedup check
            is_dup, dup_id = check_duplicate(parsed.question_text)
            if is_dup:
                skipped_dup += 1
                logger.info(
                    "SKIP (duplicate) | question matches existing {} | subdomain={}",
                    dup_id, cluster[0].get("subdomain"),
                )
                continue

            if dry_run:
                generated += 1
                logger.info(
                    "DRY-RUN | #{} | subdomain={} | Q: {}",
                    generated, cluster[0].get("subdomain"),
                    parsed.question_text[:80],
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
                "subdomain": cluster[0].get("subdomain"),
                "question_type": "scenario_based",
                "difficulty": difficulty,
                "cognitive_dim": cognitive_dim,
                "question_text": parsed.question_text,
                "options": options_dicts,
                "correct_answer": parsed.correct_answer,
                "correct_answer_text": parsed.correct_answer_text,
                "explanation": parsed.explanation,
                "tags": parsed.tags,
            }

            generation_meta = {
                "generator": generator,
                "generator_version": result["response"].model,
                "generation_method": "scenario_synthesis",
                "template_id": "SCENARIO_TEMPLATE",
                "llm_creativity": "medium",
                "prompt_hash": result["prompt_hash_val"],
                "raw_response": {
                    "content": result["response"].content,
                    "input_tokens": result["response"].input_tokens,
                    "output_tokens": result["response"].output_tokens,
                    "latency_ms": result["latency_ms"],
                },
            }

            fact_ids = [str(f["id"]) for f in cluster]
            source_ids = list({str(f["source_id"]) for f in cluster})

            q_uuid = insert_question(
                question_data, generation_meta,
                fact_ids=fact_ids,
                source_ids=source_ids,
            )
            if q_uuid:
                generated += 1
                inserted_uuids.append(q_uuid)
                logger.info(
                    "OK | #{} | {} | subdomain={} | Q: {}",
                    generated, qid, cluster[0].get("subdomain"),
                    parsed.question_text[:80],
                )
            else:
                logger.error(
                    "DB insert failed for cluster subdomain={}",
                    cluster[0].get("subdomain"),
                )

    # Batch-embed inserted questions for future dedup
    if inserted_uuids:
        embedded = batch_embed_and_store(inserted_uuids)
        logger.info(f"Embedded {embedded}/{len(inserted_uuids)} new questions")

    logger.info(
        "Scenario generation complete | generated={} | skipped_parse={} | "
        "skipped_dup={} | dry_run={}",
        generated, skipped_parse, skipped_dup, dry_run,
    )
    click.echo(
        f"\nDone: {generated} scenario questions generated, "
        f"{skipped_parse} parse failures, {skipped_dup} duplicates skipped."
    )


# ─── Test run ─────────────────────────────────────────────────────────────────


def _run_test(domain: str, generator: str, scenario_type: str):
    """Generate 3 scenario questions and print details without DB insertion."""
    click.echo(f"\n=== Test Run: {domain} / {generator} / {scenario_type} ===\n")

    used = get_used_fact_ids()
    clusters = sample_fact_clusters(domain, 3, cluster_size=3, exclude_ids=used)
    if not clusters:
        click.echo("No fact clusters available for this domain.")
        return

    for i, cluster in enumerate(clusters, 1):
        click.echo(f"--- Scenario {i}/{len(clusters)} ---")
        click.echo(f"Subdomain:    {cluster[0].get('subdomain')}")
        click.echo(f"Facts used:   {len(cluster)}")
        for j, fact in enumerate(cluster, 1):
            click.echo(f"  Fact {j}: {fact['fact_text'][:100]}")
        click.echo(f"Generator:    {generator} ({GENERATOR_MODELS[generator]})")
        click.echo(f"Scenario:     {scenario_type}")

        result = _generate_one(cluster, domain, scenario_type, generator)
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

    click.echo("Test run complete. No questions were inserted into the database.")


# ─── Validate ─────────────────────────────────────────────────────────────────


def _run_validate():
    """Quality checks on existing scenario questions."""
    conn = get_pg()
    cur = conn.cursor()

    click.echo("\n=== Scenario Generator Validation Report ===\n")

    # Questions by domain
    cur.execute(
        """
        SELECT q.domain, count(*) AS cnt
        FROM questions q
        JOIN generation_metadata gm ON gm.question_id = q.id
        WHERE gm.generation_method = 'scenario_synthesis'
        GROUP BY q.domain ORDER BY q.domain
        """
    )
    rows = cur.fetchall()
    total = sum(r["cnt"] for r in rows)
    click.echo(f"Total scenario questions: {total}")
    click.echo("By domain:")
    for r in rows:
        click.echo(f"  {r['domain']:20s} {r['cnt']}")

    # By scenario type (from tags)
    cur.execute(
        """
        SELECT q.difficulty, count(*) AS cnt
        FROM questions q
        JOIN generation_metadata gm ON gm.question_id = q.id
        WHERE gm.generation_method = 'scenario_synthesis'
        GROUP BY q.difficulty ORDER BY q.difficulty
        """
    )
    rows = cur.fetchall()
    click.echo("\nBy difficulty:")
    for r in rows:
        click.echo(f"  Level {r['difficulty']:5s} {r['cnt']}")

    # By cognitive dimension
    cur.execute(
        """
        SELECT q.cognitive_dim, count(*) AS cnt
        FROM questions q
        JOIN generation_metadata gm ON gm.question_id = q.id
        WHERE gm.generation_method = 'scenario_synthesis'
        GROUP BY q.cognitive_dim ORDER BY q.cognitive_dim
        """
    )
    rows = cur.fetchall()
    click.echo("\nBy cognitive dimension:")
    for r in rows:
        click.echo(f"  {r['cognitive_dim']:20s} {r['cnt']}")

    # Facts per question (should be 2-4)
    cur.execute(
        """
        SELECT q.id, count(qf.fact_id) AS fact_count
        FROM questions q
        JOIN generation_metadata gm ON gm.question_id = q.id
        JOIN question_facts qf ON qf.question_id = q.id
        WHERE gm.generation_method = 'scenario_synthesis'
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
            click.echo(f"  WARNING: {single_fact} questions linked to <2 facts")

    # Generator distribution
    cur.execute(
        """
        SELECT gm.generator, count(*) AS cnt
        FROM questions q
        JOIN generation_metadata gm ON gm.question_id = q.id
        WHERE gm.generation_method = 'scenario_synthesis'
        GROUP BY gm.generator ORDER BY gm.generator
        """
    )
    rows = cur.fetchall()
    click.echo("\nGenerator distribution:")
    for r in rows:
        click.echo(f"  {r['generator']:20s} {r['cnt']}")

    # 5 random samples
    cur.execute(
        """
        SELECT q.question_id, q.question_text, q.correct_answer, q.domain,
               q.cognitive_dim, q.difficulty
        FROM questions q
        JOIN generation_metadata gm ON gm.question_id = q.id
        WHERE gm.generation_method = 'scenario_synthesis'
        ORDER BY random()
        LIMIT 5
        """
    )
    samples = cur.fetchall()
    if samples:
        click.echo(f"\nRandom sample ({len(samples)} questions):")
        for s in samples:
            click.echo(f"\n  [{s['question_id']}] ({s['domain']}) L{s['difficulty']} "
                        f"[{s['cognitive_dim']}]")
            click.echo(f"  Q: {s['question_text'][:150]}")
            click.echo(f"  A: {s['correct_answer']}")

    click.echo("\nValidation complete.\n")


if __name__ == "__main__":
    main()
