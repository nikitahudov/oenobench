"""
OenoBench — Fact-to-Question generator (Strategy 1).

Converts a single verified fact from the database into a benchmark question
via LLM. This is the primary generation strategy, responsible for ~40% of
all questions.

Usage:
    python -m src.generators.fact_to_question --domain wine_regions --count 10
    python -m src.generators.fact_to_question --domain viticulture --generator chatgpt
    python -m src.generators.fact_to_question --test-run
    python -m src.generators.fact_to_question --validate
    python -m src.generators.fact_to_question --dry-run --count 5
"""

import sys
import time
from datetime import datetime
from pathlib import Path

import click
from loguru import logger

from src.generators._dedup import batch_embed_and_store, check_duplicate
from src.generators._fact_sampler import sample_facts
from src.generators._id_generator import mint_question_id
from src.generators._llm_client import GENERATOR_MODELS, get_client
from src.generators._prompts import (
    COGNITIVE_DESCRIPTIONS,
    DIFFICULTY_DESCRIPTIONS,
    FACT_TO_QUESTION_SYSTEM,
    FACT_TO_QUESTION_TEMPLATE,
    QUESTION_TYPE_INSTRUCTIONS,
    build_prompt,
    prompt_hash,
)
from src.generators._question_db import (
    get_used_fact_ids,
    insert_question_gated,
)
from src.generators._schemas import parse_llm_response, pre_screen_for_verifier_skip
from src.qa._attempted_facts import (
    get_attempted_fact_ids,
    register_attempted_fact_ids,
)
from src.utils.db import get_pg

# Strategy name for the cross-pass attempted-fact-ID registry. Must match
# the key used in ``src.qa._corpus.STRATEGY_MODULES``.
_STRATEGY_NAME = "fact_to_question"

# ─── Logging setup ────────────────────────────────────────────────────────────

LOG_DIR = Path("data/logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)

MAX_RETRIES = 1  # retry once on parse failure


# ─── Core generation logic ────────────────────────────────────────────────────


def _generate_one(
    fact: dict,
    domain: str,
    difficulty: str,
    cognitive_dim: str,
    question_type: str,
    generator: str,
) -> dict | None:
    """Generate a single question from a fact. Returns result dict or None on failure.

    The result dict has keys: parsed, prompt_rendered, prompt_hash_val,
    response, latency_ms.
    """
    prompt_rendered = build_prompt(
        FACT_TO_QUESTION_TEMPLATE,
        fact_text=fact["fact_text"],
        source_name=fact["source_name"],
        domain=domain,
        difficulty=difficulty,
        difficulty_description=DIFFICULTY_DESCRIPTIONS[difficulty],
        cognitive_dim=cognitive_dim,
        cognitive_description=COGNITIVE_DESCRIPTIONS[cognitive_dim],
        question_type=question_type,
        question_type_description=QUESTION_TYPE_INSTRUCTIONS[question_type],
        type_specific_instructions=QUESTION_TYPE_INSTRUCTIONS[question_type],
    )
    phash = prompt_hash(prompt_rendered)

    client = get_client()
    model_id = GENERATOR_MODELS[generator]

    _STRICT_JSON_PREFIX = (
        "IMPORTANT: Respond with raw JSON only. Do NOT include markdown fences"
        " (no ```json), prose, or explanation. The first character of your"
        " response must be { and the last must be }.\n\n"
    )

    for attempt in range(1 + MAX_RETRIES):
        prompt_for_attempt = (
            _STRICT_JSON_PREFIX + prompt_rendered if attempt > 0 else prompt_rendered
        )
        if attempt > 0:
            logger.info(
                "parse-retry attempt=1 generator={}",
                _STRATEGY_NAME,
            )
        t0 = time.time()
        response = client.generate(
            prompt=prompt_for_attempt,
            system=FACT_TO_QUESTION_SYSTEM,
            model=model_id,
        )
        latency = int((time.time() - t0) * 1000)

        if not response.success:
            logger.warning(
                "LLM call failed | fact={} | attempt={} | error={}",
                fact["id"], attempt + 1, response.error,
            )
            continue

        # Check if LLM signaled to skip (vague/marketing fact)
        if response.parsed and response.parsed.get("skip"):
            logger.info(
                "LLM skipped fact | fact={} | reason={}",
                fact["id"], response.parsed.get("reason", "unspecified"),
            )
            return None

        # Phase 2g.18 lever L5: run the closed-book gate BEFORE
        # parse_llm_response so should_skip_verifier() can fire on
        # confident gate-passed Llama/Qwen questions when
        # OENOBENCH_VERIFIER_SKIP=1.
        pre_gate_passed, gen_confidence = pre_screen_for_verifier_skip(
            response.content,
            question_type=question_type,
            labelled_difficulty=difficulty,
        )

        parsed = parse_llm_response(
            response.content,
            question_type,
            source_fact_texts=[fact["fact_text"]],
            verify_with_independent_solver=True,
            verify_difficulty_with_c4=True,
            labelled_difficulty=difficulty,
            generator=generator,
            pre_gate_passed=pre_gate_passed,
            generator_confidence=gen_confidence,
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
            "Parse failed | fact={} | attempt={} | type={}",
            fact["id"], attempt + 1, question_type,
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
    "--question-type",
    type=click.Choice([
        "multiple_choice", "multiple_select", "true_false",
        "matching", "short_answer", "scenario_based",
    ]),
    default="multiple_choice",
    help="Question type to generate",
)
@click.option(
    "--difficulty",
    type=click.Choice(["1", "2", "3", "4"]),
    default="2",
    help="Difficulty level",
)
@click.option(
    "--cognitive-dim",
    type=click.Choice([
        "recall", "comprehension", "application",
        "analysis", "synthesis", "evaluation",
    ]),
    default="recall",
    help="Cognitive dimension",
)
@click.option("--dry-run", is_flag=True, help="Generate but don't insert into DB")
@click.option("--test-run", is_flag=True, help="Generate 3 questions, print details")
@click.option("--validate", is_flag=True, help="Quality checks on existing questions")
@click.option("--all", "run_all", is_flag=True, help="Generate full quota for domain")
@click.option(
    "--tag",
    type=str,
    default=None,
    help="Append this tag to every generated question (used for prototype/audit corpora).",
)
@click.option(
    "--per-country-cap",
    type=float,
    default=None,
    help=(
        "Per-call absolute country cap as a fraction in (0, 1]. "
        "When set, no single country may exceed ceil(cap * count) of "
        "the sampled facts. Default unset (no cap)."
    ),
)
@click.option(
    "--circuit-breaker/--no-circuit-breaker",
    default=None,
    help=(
        "Phase 2g.10 (Team Golf B3): when ON, the per-attempt loop tracks "
        "kept-rate over a rolling window and abandons the cell early when "
        "rate < 5% after 10+ attempts. Default OFF (env var "
        "OENOBENCH_CIRCUIT_BREAKER=1 also enables it)."
    ),
)
def main(
    domain, count, generator, question_type, difficulty,
    cognitive_dim, dry_run, test_run, validate, run_all,
    tag, per_country_cap, circuit_breaker,
):
    """Generate benchmark questions from individual facts via LLM."""
    if validate:
        _run_validate()
        return

    if not domain:
        logger.error("--domain is required for generation (use --validate without it)")
        sys.exit(1)

    if test_run:
        _run_test(domain, generator, question_type, difficulty, cognitive_dim)
        return

    target = count
    if run_all:
        from src.generators._fact_sampler import DOMAIN_TARGETS
        target = DOMAIN_TARGETS.get(domain, 1000)
        logger.info(f"--all mode: targeting {target} questions for {domain}")

    run_generate(
        domain=domain, count=target, generator=generator,
        question_type=question_type,
        difficulty=str(difficulty) if difficulty else "2",
        cognitive_dim=cognitive_dim, dry_run=dry_run,
        tag=tag, per_country_cap=per_country_cap,
        circuit_breaker=circuit_breaker,
    )


# ─── Generate run ─────────────────────────────────────────────────────────────


def run_generate(
    *,
    domain: str,
    count: int,
    generator: str = "claude",
    question_type: str = "multiple_choice",
    difficulty: str | int | None = "2",
    cognitive_dim: str = "recall",
    dry_run: bool = False,
    tag: str | None = None,
    per_country_cap: float | None = None,
    tracker=None,
    circuit_breaker: bool | None = None,
) -> dict:
    """Main generation loop. Returns stats dict.

    Phase 2g.10 (Team Delta A2): in-process callable. The click ``main()`` is
    a thin shim around this function. The legacy ``_run_generate`` alias is
    preserved below for backwards compatibility.

    Logging: each call registers its own loguru sink under ``data/logs/`` and
    removes it in ``finally`` so concurrent calls (Team Delta A3) don't
    accumulate handlers across cells.

    Phase 2g.10 (Team Golf B3): when ``tracker`` is provided OR the
    ``OENOBENCH_CIRCUIT_BREAKER`` env var is "1" (or ``circuit_breaker=True``
    is explicitly passed), the per-attempt loop maintains a rolling-window
    kept-rate. When the rate falls below 5% after 10+ attempts, the cell
    abandons early. Default OFF preserves v8 reproducibility.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    handler_id = logger.add(
        LOG_DIR / f"fact_to_question_{timestamp}.log", rotation="50 MB",
    )
    try:
        return _run_generate_body(
            domain=domain, count=count, generator=generator,
            question_type=question_type,
            difficulty=str(difficulty) if difficulty is not None else "2",
            cognitive_dim=cognitive_dim, dry_run=dry_run,
            tag=tag, per_country_cap=per_country_cap,
            tracker=_resolve_tracker(tracker, circuit_breaker),
        )
    finally:
        try:
            logger.remove(handler_id)
        except ValueError:
            pass


def _resolve_tracker(tracker, circuit_breaker: bool | None):
    """Materialise a CellTracker if one is requested but not passed."""
    if tracker is not None:
        return tracker
    from src.qa._corpus import CellTracker, _circuit_breaker_enabled
    enabled = circuit_breaker if circuit_breaker is not None else _circuit_breaker_enabled()
    return CellTracker() if enabled else None


# Legacy alias — preserved for any internal caller that imports
# ``_run_generate`` directly.
def _run_generate(
    domain: str,
    count: int,
    generator: str,
    question_type: str,
    difficulty: str,
    cognitive_dim: str,
    dry_run: bool,
    tag: str | None = None,
    per_country_cap: float | None = None,
):  # pragma: no cover — thin compatibility shim
    return run_generate(
        domain=domain, count=count, generator=generator,
        question_type=question_type, difficulty=difficulty,
        cognitive_dim=cognitive_dim, dry_run=dry_run,
        tag=tag, per_country_cap=per_country_cap,
    )


def _run_generate_body(
    *,
    domain: str,
    count: int,
    generator: str,
    question_type: str,
    difficulty: str,
    cognitive_dim: str,
    dry_run: bool,
    tag: str | None = None,
    per_country_cap: float | None = None,
    tracker=None,
) -> dict:
    """Inner generation loop, sans logger-handler setup."""
    logger.info(
        "Starting generation | domain={} | count={} | generator={} | type={} | "
        "difficulty={} | cognitive={} | dry_run={} | tag={} | per_country_cap={}",
        domain, count, generator, question_type, difficulty, cognitive_dim, dry_run,
        tag, per_country_cap,
    )

    # Early-out for count=0 (used by smoke tests) so we don't hit the DB.
    if count <= 0:
        return {
            "generated": 0, "skipped_parse": 0, "skipped_dup": 0,
            "skipped_sample": 0, "relabeled_l1": 0, "rejected_overflow": 0,
            "inserted_uuids": [],
        }

    used_fact_ids = get_used_fact_ids()
    # Phase 2g.13: seed run_used_ids with cross-pass attempted IDs so the
    # multi-pass loop's previous passes' attempted-but-unsuccessful facts
    # are excluded from the sampler.
    run_used_ids: set[str] = set(get_attempted_fact_ids(_STRATEGY_NAME))
    generated = 0
    skipped_parse = 0
    skipped_dup = 0
    relabeled_l1 = 0
    rejected_overflow = 0
    inserted_uuids: list[str] = []

    while generated < count:
        if tracker is not None and tracker.should_abandon():
            logger.warning(
                "CIRCUIT BREAKER | strategy=fact_to_question | cell={}/{} | "
                "attempts={} | kept={} | rate={:.1%} — abandoning",
                generator, domain, tracker.attempts, tracker.kept,
                tracker.kept_rate(),
            )
            break
        batch_size = min(count - generated, 10)
        facts = sample_facts(
            domain, batch_size,
            exclude_ids=used_fact_ids | run_used_ids,
            strategy="fact_to_question",
            per_country_cap=per_country_cap,
            require_substantive=True,  # Phase 2g.18 lever L9: mirror template substantive filter
            reject_ubiquitous_for_region_answer=(domain == "grape_varieties"),  # Phase 2g.17
        )
        if not facts:
            logger.warning("No more facts available for domain={}", domain)
            break

        for fact in facts:
            if generated >= count:
                break
            if tracker is not None and tracker.should_abandon():
                logger.warning(
                    "CIRCUIT BREAKER | strategy=fact_to_question | cell={}/{} | "
                    "attempts={} | kept={} | rate={:.1%} — abandoning",
                    generator, domain, tracker.attempts, tracker.kept,
                    tracker.kept_rate(),
                )
                break

            fact_id_str = str(fact["id"])
            run_used_ids.add(fact_id_str)
            register_attempted_fact_ids(_STRATEGY_NAME, [fact_id_str])
            result = _generate_one(
                fact, domain, difficulty, cognitive_dim, question_type, generator,
            )
            if result is None:
                skipped_parse += 1
                if tracker is not None:
                    tracker.record(False)
                logger.info(
                    "SKIP (parse) | fact={} | generator={} | type={}",
                    fact["id"], generator, question_type,
                )
                continue

            parsed = result["parsed"]

            # Dedup check
            is_dup, dup_id = check_duplicate(parsed.question_text)
            if is_dup:
                skipped_dup += 1
                if tracker is not None:
                    tracker.record(False)
                logger.info(
                    "SKIP (duplicate) | question matches existing {} | fact={}",
                    dup_id, fact["id"],
                )
                continue

            if dry_run:
                generated += 1
                if tracker is not None:
                    tracker.record(True)
                logger.info(
                    "DRY-RUN | #{} | fact={} | Q: {}",
                    generated, fact["id"], parsed.question_text[:80],
                )
                continue

            # Mint ID and insert
            qid = mint_question_id(domain, difficulty)
            options_dicts = (
                [{"id": o.id, "text": o.text} for o in parsed.options]
                if parsed.options
                else None
            )

            tags_with_run = list(parsed.tags or [])
            if tag and tag not in tags_with_run:
                tags_with_run.append(tag)
            question_data = {
                "question_id": qid,
                "domain": domain,
                "subdomain": fact.get("subdomain"),
                "question_type": question_type,
                "difficulty": difficulty,
                "cognitive_dim": cognitive_dim,
                "question_text": parsed.question_text,
                "options": options_dicts,
                "correct_answer": parsed.correct_answer,
                "correct_answer_text": parsed.correct_answer_text,
                "explanation": parsed.explanation,
                "tags": tags_with_run,
            }

            generation_meta = {
                "generator": generator,
                "generator_version": result["response"].model,
                "generation_method": "fact_to_question",
                "template_id": "FACT_TO_QUESTION_TEMPLATE",
                "llm_creativity": "medium",
                "prompt_hash": result["prompt_hash_val"],
                "raw_response": {
                    "content": result["response"].content,
                    "input_tokens": result["response"].input_tokens,
                    "output_tokens": result["response"].output_tokens,
                    "latency_ms": result["latency_ms"],
                },
            }

            q_uuid, gate = insert_question_gated(
                question_data, generation_meta,
                fact_ids=[str(fact["id"])],
                source_ids=[str(fact["source_id"])],
            )
            if q_uuid and gate.relabeled:
                generated += 1
                relabeled_l1 += 1
                inserted_uuids.append(q_uuid)
                if tracker is not None:
                    tracker.record(True)
                logger.info(
                    "OK (relabeled L1) | #{} | {} | fact={} | Q: {} | {}",
                    generated, qid, fact["id"], parsed.question_text[:80], gate.reason,
                )
            elif q_uuid:
                generated += 1
                inserted_uuids.append(q_uuid)
                if tracker is not None:
                    tracker.record(True)
                logger.info(
                    "OK | #{} | {} | fact={} | Q: {}",
                    generated, qid, fact["id"], parsed.question_text[:80],
                )
            elif gate.applied and gate.quota_full:
                rejected_overflow += 1
                if tracker is not None:
                    tracker.record(False)
                logger.info(
                    "DROP (cb_quota_full) | fact={} | {}",
                    fact["id"], gate.reason,
                )
            else:
                if tracker is not None:
                    tracker.record(False)
                logger.error("DB insert failed for fact={}", fact["id"])

    # Batch-embed inserted questions for future dedup
    if inserted_uuids:
        embedded = batch_embed_and_store(inserted_uuids)
        logger.info(f"Embedded {embedded}/{len(inserted_uuids)} new questions")

    logger.info(
        "Generation complete | generated={} | skipped_parse={} | skipped_dup={} | "
        "relabeled_l1={} | rejected_overflow={} | dry_run={}",
        generated, skipped_parse, skipped_dup, relabeled_l1, rejected_overflow, dry_run,
    )
    click.echo(
        f"\nDone: {generated} questions generated, "
        f"{skipped_parse} parse failures, {skipped_dup} duplicates skipped, "
        f"{relabeled_l1} relabeled to L1 (closed_book_solvable), "
        f"{rejected_overflow} dropped over quota."
    )

    return {
        "generated": generated,
        "skipped_parse": skipped_parse,
        "skipped_dup": skipped_dup,
        "skipped_sample": 0,
        "relabeled_l1": relabeled_l1,
        "rejected_overflow": rejected_overflow,
        "inserted_uuids": list(inserted_uuids),
    }


# ─── Test run ─────────────────────────────────────────────────────────────────


def _run_test(
    domain: str,
    generator: str,
    question_type: str,
    difficulty: str,
    cognitive_dim: str,
):
    """Generate 3 questions and print details without DB insertion."""
    click.echo(f"\n=== Test Run: {domain} / {generator} / {question_type} ===\n")

    used = get_used_fact_ids()
    facts = sample_facts(domain, 3, exclude_ids=used, strategy="fact_to_question")
    if not facts:
        click.echo("No facts available for this domain.")
        return

    for i, fact in enumerate(facts, 1):
        click.echo(f"--- Question {i}/{len(facts)} ---")
        click.echo(f"Source fact:  {fact['fact_text']}")
        click.echo(f"Source:       {fact['source_name']}")
        click.echo(f"Generator:    {generator} ({GENERATOR_MODELS[generator]})")

        result = _generate_one(
            fact, domain, difficulty, cognitive_dim, question_type, generator,
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

    click.echo("Test run complete. No questions were inserted into the database.")


# ─── Validate ─────────────────────────────────────────────────────────────────


def _run_validate():
    """Quality checks on existing questions generated by fact_to_question."""
    conn = get_pg()
    cur = conn.cursor()

    click.echo("\n=== Fact-to-Question Validation Report ===\n")

    # Questions by domain
    cur.execute(
        """
        SELECT q.domain, count(*) AS cnt
        FROM questions q
        JOIN generation_metadata gm ON gm.question_id = q.id
        WHERE gm.generation_method = 'fact_to_question'
        GROUP BY q.domain ORDER BY q.domain
        """
    )
    rows = cur.fetchall()
    click.echo("Questions by domain:")
    for r in rows:
        click.echo(f"  {r['domain']:20s} {r['cnt']}")

    # By question type
    cur.execute(
        """
        SELECT q.question_type, count(*) AS cnt
        FROM questions q
        JOIN generation_metadata gm ON gm.question_id = q.id
        WHERE gm.generation_method = 'fact_to_question'
        GROUP BY q.question_type ORDER BY q.question_type
        """
    )
    rows = cur.fetchall()
    click.echo("\nQuestions by type:")
    for r in rows:
        click.echo(f"  {r['question_type']:20s} {r['cnt']}")

    # By difficulty
    cur.execute(
        """
        SELECT q.difficulty, count(*) AS cnt
        FROM questions q
        JOIN generation_metadata gm ON gm.question_id = q.id
        WHERE gm.generation_method = 'fact_to_question'
        GROUP BY q.difficulty ORDER BY q.difficulty
        """
    )
    rows = cur.fetchall()
    click.echo("\nQuestions by difficulty:")
    for r in rows:
        click.echo(f"  Level {r['difficulty']:5s} {r['cnt']}")

    # By cognitive dimension
    cur.execute(
        """
        SELECT q.cognitive_dim, count(*) AS cnt
        FROM questions q
        JOIN generation_metadata gm ON gm.question_id = q.id
        WHERE gm.generation_method = 'fact_to_question'
        GROUP BY q.cognitive_dim ORDER BY q.cognitive_dim
        """
    )
    rows = cur.fetchall()
    click.echo("\nQuestions by cognitive dimension:")
    for r in rows:
        click.echo(f"  {r['cognitive_dim']:20s} {r['cnt']}")

    # Generator distribution
    cur.execute(
        """
        SELECT gm.generator, count(*) AS cnt
        FROM questions q
        JOIN generation_metadata gm ON gm.question_id = q.id
        WHERE gm.generation_method = 'fact_to_question'
        GROUP BY gm.generator ORDER BY gm.generator
        """
    )
    rows = cur.fetchall()
    click.echo("\nGenerator distribution:")
    for r in rows:
        click.echo(f"  {r['generator']:20s} {r['cnt']}")

    # Quality issues: missing explanations or empty options for MC types
    cur.execute(
        """
        SELECT count(*) AS cnt FROM questions q
        JOIN generation_metadata gm ON gm.question_id = q.id
        WHERE gm.generation_method = 'fact_to_question'
          AND (q.explanation IS NULL OR q.explanation = '')
        """
    )
    no_expl = cur.fetchone()["cnt"]
    cur.execute(
        """
        SELECT count(*) AS cnt FROM questions q
        JOIN generation_metadata gm ON gm.question_id = q.id
        WHERE gm.generation_method = 'fact_to_question'
          AND q.question_type IN ('multiple_choice', 'multiple_select', 'true_false')
          AND (q.options IS NULL OR q.options = '[]'::jsonb)
        """
    )
    no_opts = cur.fetchone()["cnt"]
    click.echo(f"\nQuality issues:")
    click.echo(f"  Missing explanations:  {no_expl}")
    click.echo(f"  Empty options (MC/TF): {no_opts}")

    # 10 random sample questions with source facts
    cur.execute(
        """
        SELECT q.question_id, q.question_text, q.correct_answer, q.domain,
               f.fact_text AS source_fact
        FROM questions q
        JOIN generation_metadata gm ON gm.question_id = q.id
        JOIN question_facts qf ON qf.question_id = q.id
        JOIN facts f ON f.id = qf.fact_id
        WHERE gm.generation_method = 'fact_to_question'
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
            click.echo(f"  Fact: {s['source_fact'][:120]}")

    click.echo("\nValidation complete.\n")


if __name__ == "__main__":
    main()
