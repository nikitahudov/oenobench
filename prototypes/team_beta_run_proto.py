"""Team β prototype — generate scenario questions tagged `prototype_team_beta`.

Runs the existing scenario_generator pipeline but injects the
`prototype_team_beta` tag on every inserted question so cleanup is a single
DELETE statement.

Usage:
  python -m prototypes.team_beta_run_proto --count 50 --domain wine_regions
"""

import random
import sys
import time
from datetime import datetime
from pathlib import Path

import click
from loguru import logger

# Re-use generator internals
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
from src.generators._question_db import (
    get_used_fact_ids,
    insert_question_gated,
)
from src.generators._schemas import parse_llm_response

PROTOTYPE_TAG = "prototype_team_beta"
LOG_DIR = Path("data/logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)


def _format_facts_block(cluster):
    lines = []
    for i, fact in enumerate(cluster, 1):
        src = fact.get("source_name", "unknown")
        lines.append(f"{i}. {fact['fact_text']}  [Source: {src}]")
    return "\n".join(lines)


def _generate_one(cluster, scenario_type, generator, labelled_difficulty):
    facts_block = _format_facts_block(cluster)
    prompt_rendered = build_prompt(
        SCENARIO_TEMPLATE, facts=facts_block, scenario_type=scenario_type,
    )
    phash = prompt_hash(prompt_rendered)
    client = get_client()
    model_id = GENERATOR_MODELS[generator]
    t0 = time.time()
    response = client.generate(
        prompt=prompt_rendered, system=SCENARIO_SYSTEM, model=model_id,
    )
    latency = int((time.time() - t0) * 1000)
    if not response.success:
        logger.warning(f"LLM call failed: {response.error}")
        return None
    if response.parsed and response.parsed.get("skip"):
        logger.info(f"LLM skipped: {response.parsed.get('reason')}")
        return None
    if response.parsed and response.parsed.get("error"):
        logger.info(f"LLM declined: {response.parsed.get('error')}")
        return None
    parsed = parse_llm_response(
        response.content, "scenario_based",
        source_fact_texts=[f["fact_text"] for f in cluster],
        verify_with_independent_solver=True,
        verify_difficulty_with_c4=True,
        labelled_difficulty=labelled_difficulty,
        generator=generator,
    )
    if parsed is None:
        return None
    return {
        "parsed": parsed,
        "prompt_rendered": prompt_rendered,
        "prompt_hash_val": phash,
        "response": response,
        "latency_ms": latency,
    }


@click.command()
@click.option("--count", type=int, default=50)
@click.option(
    "--domains",
    type=str,
    default="winemaking,viticulture,grape_varieties,wine_regions,wine_business",
    help="Comma-separated list of domains to rotate through.",
)
@click.option(
    "--generator",
    type=click.Choice(["claude", "chatgpt", "gemini", "llama", "qwen"]),
    default="claude",
)
@click.option("--scenario-type", type=str, default="rotate")
@click.option("--iteration-label", type=str, default="iter1",
              help="Free-form label appended to the prototype tag for traceability.")
@click.option("--max-attempts", type=int, default=400,
              help="Max sample-and-prompt attempts before giving up.")
def main(count, domains, generator, scenario_type, iteration_label, max_attempts):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    logger.add(LOG_DIR / f"team_beta_proto_{timestamp}.log", rotation="50 MB")
    iter_tag = f"{PROTOTYPE_TAG}_{iteration_label}"

    domain_list = [d.strip() for d in domains.split(",") if d.strip()]

    used_fact_ids = get_used_fact_ids()
    run_used_ids: set[str] = set()
    generated = 0
    skipped_parse = 0
    skipped_dup = 0
    relabeled_l1 = 0
    rejected_overflow = 0
    attempts = 0
    inserted_uuids: list[str] = []

    SCENARIO_TYPES = ["winemaking", "tasting", "business", "service", "viticulture"]

    domain_idx = 0

    while generated < count and attempts < max_attempts:
        domain = domain_list[domain_idx % len(domain_list)]
        domain_idx += 1
        batch = min(count - generated, 3)
        attempts += batch
        clusters = sample_fact_clusters(
            domain, batch, cluster_size=3,
            exclude_ids=used_fact_ids | run_used_ids,
        )
        if not clusters:
            logger.warning("No more clusters for domain=%s", domain)
            break
        for cluster in clusters:
            if generated >= count:
                break
            cluster_ids = {str(f["id"]) for f in cluster}
            run_used_ids.update(cluster_ids)
            difficulty = str(random.randint(2, 4))
            cognitive_dim = random.choice(["application", "analysis", "synthesis"])
            stype = random.choice(SCENARIO_TYPES) if scenario_type == "rotate" else scenario_type
            result = _generate_one(cluster, stype, generator, difficulty)
            if result is None:
                skipped_parse += 1
                continue
            parsed = result["parsed"]
            is_dup, dup_id = check_duplicate(parsed.question_text)
            if is_dup:
                skipped_dup += 1
                continue
            qid = mint_question_id(domain, difficulty)
            options_dicts = (
                [{"id": o.id, "text": o.text} for o in parsed.options]
                if parsed.options else None
            )
            # Inject prototype tag — keep any LLM-emitted tags too.
            new_tags = list(parsed.tags or []) + [PROTOTYPE_TAG, iter_tag]
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
                "tags": new_tags,
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
            q_uuid, gate = insert_question_gated(
                question_data, generation_meta,
                fact_ids=fact_ids, source_ids=source_ids,
            )
            if q_uuid and gate.relabeled:
                generated += 1
                relabeled_l1 += 1
                inserted_uuids.append(q_uuid)
            elif q_uuid:
                generated += 1
                inserted_uuids.append(q_uuid)
            elif gate.applied and gate.quota_full:
                rejected_overflow += 1

    if inserted_uuids:
        batch_embed_and_store(inserted_uuids)

    click.echo(
        f"\nDone: {generated} inserted ({iter_tag}), "
        f"{skipped_parse} parse fails, {skipped_dup} dups, "
        f"{relabeled_l1} relabeled→L1, {rejected_overflow} dropped over quota."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
