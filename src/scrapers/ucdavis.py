"""
OenoBench — UC Davis Repositories Scraper

Extracts wine facts from three UC Davis public data sources:
  1. Wine Ontology (RDF/Turtle) — wine classifications, properties, region-variety links
  2. AVA Digitizing Project (GeoJSON) — all US AVAs with hierarchy and establishment dates
  3. FPS Grape Variety Database (HTML) — grape varieties, clones, TTB-approved names

Usage:
    python -m src.scrapers.ucdavis --all
    python -m src.scrapers.ucdavis --source ontology
    python -m src.scrapers.ucdavis --source ava
    python -m src.scrapers.ucdavis --source fps
    python -m src.scrapers.ucdavis --dry-run
    python -m src.scrapers.ucdavis --validate
    python -m src.scrapers.ucdavis --list
    python -m src.scrapers.ucdavis --test-run
    python -m src.scrapers.ucdavis --test-run --source ava
    python -m src.scrapers.ucdavis --test-run --cleanup
"""

import json
import os
import random
import re
import subprocess
import tempfile
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

import click
import requests
from bs4 import BeautifulSoup
from loguru import logger

from src.utils.facts import ensure_source, insert_facts_batch, get_fact_count

# ─── Configuration ────────────────────────────────────────────────────────────

USER_AGENT = "OenoBench-Research/1.0 (academic wine benchmark)"
FPS_REQUEST_DELAY = 3.0  # seconds between requests to FPS website

SOURCES = {
    "ontology": {
        "name": "UC Davis Wine Ontology",
        "url": "https://github.com/UCDavisLibrary/wine-ontology",
        "source_type": "knowledge_base",
        "tier": "tier_1_official",
        "description": "RDF/Turtle wine entity classifications and properties",
    },
    "ava": {
        "name": "UC Davis AVA Digitizing Project",
        "url": "https://github.com/UCDavisLibrary/ava",
        "source_type": "government_data",
        "tier": "tier_1_official",
        "description": "GeoJSON files for 267+ American Viticultural Areas",
    },
    "fps": {
        "name": "UC Davis FPS Grape Variety Database",
        "url": "https://fps.ucdavis.edu/fgrabout.cfm",
        "source_type": "academic_database",
        "tier": "tier_1_official",
        "description": "Foundation Plant Services grape variety and clone data",
    },
}

KNOWN_AVA_COUNT = 267  # expected approximate count for quality check

# ─── Helper: clone or update a GitHub repo ────────────────────────────────────


def _clone_repo(repo_url: str, target_dir: str) -> str:
    """Clone a GitHub repo into target_dir. Returns the repo path."""
    repo_name = repo_url.rstrip("/").split("/")[-1]
    repo_path = os.path.join(target_dir, repo_name)

    if os.path.exists(repo_path):
        logger.info(f"Repo already cloned at {repo_path}")
        return repo_path

    logger.info(f"Cloning {repo_url} into {target_dir}...")
    subprocess.run(
        ["git", "clone", "--depth", "1", repo_url, repo_path],
        check=True,
        capture_output=True,
        text=True,
    )
    logger.info(f"Cloned {repo_name} successfully")
    return repo_path


# ═══════════════════════════════════════════════════════════════════════════════
# SOURCE 1: UC Davis Wine Ontology (RDF/Turtle)
# ═══════════════════════════════════════════════════════════════════════════════


def _scrape_ontology(source_id: str, dry_run: bool = False, test_run_limit: Optional[int] = None) -> list[dict]:
    """Parse RDF/Turtle files from the Wine Ontology repo."""
    from rdflib import Graph, RDF, RDFS, OWL, Namespace

    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = _clone_repo(SOURCES["ontology"]["url"], tmpdir)

        # Find all Turtle / RDF files
        rdf_files = []
        for ext in ("*.ttl", "*.rdf", "*.owl", "*.xml", "*.n3"):
            rdf_files.extend(Path(repo_path).rglob(ext))

        logger.info(f"Found {len(rdf_files)} RDF/Turtle files in ontology repo")

        # Filter to wine-related files only — the repo bundles general-purpose
        # ontologies (LinkedGeoData OSM, DBpedia) that produce non-wine junk
        rdf_files = [f for f in rdf_files if "wine" in f.name.lower()]
        logger.info(f"Filtered to {len(rdf_files)} wine-related RDF files")

        if test_run_limit:
            rdf_files = rdf_files[:test_run_limit]
            logger.info(f"[TEST RUN] Limited to {len(rdf_files)} RDF files")

        if not rdf_files:
            logger.warning("No RDF files found in wine-ontology repo")
            return []

        g = Graph()
        for f in rdf_files:
            # Skip tiny stub files (< 2KB) — the lib.ucdavis.edu/wine.rdf
            # is a 1.4KB broken stub; the real data is in the 77KB W3C wine.rdf
            if f.stat().st_size < 2048:
                logger.debug(f"Skipping {f.name} (stub file, {f.stat().st_size} bytes)")
                continue

            fmt = _guess_rdf_format(f)
            try:
                g.parse(str(f), format=fmt)
                logger.debug(f"Parsed {f.name} ({fmt})")
            except Exception as e:
                # N3 is a superset of Turtle — try as fallback for files
                # using extended syntax like = (owl:sameAs shorthand)
                if fmt != "n3":
                    try:
                        g.parse(str(f), format="n3")
                        logger.debug(f"Parsed {f.name} (n3 fallback)")
                        continue
                    except Exception:
                        pass

                # Last resort: extract triples with regex for broken files
                triples = _extract_triples_from_broken_turtle(f)
                if triples:
                    base_ns = "http://library.ucdavis.edu/wine-ontology#"
                    added = _inject_triples_into_graph(g, triples, base_ns)
                    logger.info(
                        f"Parsed {f.name} (regex fallback, "
                        f"{added} triples from {len(triples)} extracted)"
                    )
                else:
                    logger.warning(f"Failed to parse {f.name}: {e}")

        logger.info(f"Loaded {len(g)} triples from ontology")
        facts = _extract_ontology_facts(g, source_id)

    logger.info(f"Generated {len(facts)} facts from Wine Ontology")
    return facts


def _guess_rdf_format(filepath: Path) -> str:
    """Guess rdflib parse format, using content sniffing for ambiguous extensions.

    Some .owl files in the UC Davis repo are actually Turtle syntax (start with
    @prefix), not OWL/XML. Content sniffing catches this mismatch.
    """
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                if stripped.startswith("@prefix") or stripped.startswith("@base"):
                    return "turtle"
                if stripped.startswith("<?xml") or stripped.startswith("<!DOCTYPE") or stripped.startswith("<rdf:"):
                    return "xml"
                break
    except Exception:
        pass

    # Fall back to extension-based guess
    ext = filepath.suffix.lower()
    return {
        ".ttl": "turtle",
        ".n3": "n3",
        ".rdf": "xml",
        ".owl": "xml",
        ".xml": "xml",
        ".jsonld": "json-ld",
    }.get(ext, "turtle")


def _extract_triples_from_broken_turtle(filepath: Path) -> list[tuple]:
    """Extract RDF-like triples from a broken Turtle/N3 file using regex.

    The wine-ontology.owl file has too many syntax errors for any standard
    parser. This function extracts structured data directly from the text.

    Returns a list of (subject, predicate, object) string tuples.
    """
    try:
        content = filepath.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []

    triples = []
    current_subject = None

    for line in content.split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # New subject definition: :SubjectName a :TypeName
        m = re.match(r':(\w+)\s+a\s+:?(\w[\w:]*)', stripped)
        if m:
            current_subject = m.group(1)
            obj = m.group(2)
            triples.append((current_subject, "rdf:type", obj))
            # Check for continuation on same line after ;
            rest = stripped[m.end():]
            if ";" in rest:
                # Process continuation predicates
                for pm in re.finditer(r'(?:rdfs?:|owl:)(\w+)\s+"([^"]*)"', rest):
                    triples.append((current_subject, pm.group(1), pm.group(2)))
                for pm in re.finditer(r'rdfs:subClassOf\s+:(\w+)', rest):
                    triples.append((current_subject, "subClassOf", pm.group(1)))
            continue

        # Continuation predicate on indented line
        if current_subject and stripped.startswith(("rdfs:", "rdf:", "owl:", "=")):
            # Label — also match broken pattern :SomeLabel" (missing opening quote)
            m = re.match(r'(?:rdfs?:label|rdf:label)\s+(?::)?"?([^"]+)"', stripped)
            if m:
                triples.append((current_subject, "label", m.group(1)))
                continue
            # SubClassOf
            m = re.match(r'(?:rdfs:subClassOf|owl:subClass)\s+:(\w+)', stripped)
            if m:
                triples.append((current_subject, "subClassOf", m.group(1)))
                continue
            # Domain
            m = re.match(r'rdfs:domain\s+:(\w+)', stripped)
            if m:
                triples.append((current_subject, "domain", m.group(1)))
                continue
            # Range
            m = re.match(r'rdfs:range\s+:(\w+)', stripped)
            if m:
                triples.append((current_subject, "range", m.group(1)))
                continue
            # owl:sameAs (= shorthand)
            m = re.match(r'=\s+(\S+)', stripped)
            if m:
                triples.append((current_subject, "sameAs", m.group(1)))
                continue

    return triples


def _inject_triples_into_graph(g, triples: list[tuple], base_ns: str) -> int:
    """Inject regex-extracted triples into an rdflib Graph.

    Returns the number of triples added.
    """
    from rdflib import URIRef, Literal, RDF, RDFS, OWL, Namespace

    ns = Namespace(base_ns)
    added = 0

    # Mapping for rdf:X type URIs
    type_map = {
        "rdf:Class": RDFS.Class,
        "rdf:Property": RDF.Property,
        "rdfs:Class": RDFS.Class,
        "owl:Class": OWL.Class,
    }

    for subj_name, pred, obj_val in triples:
        subj = ns[subj_name]

        if pred == "rdf:type":
            type_uri = type_map.get(obj_val, ns[obj_val])
            g.add((subj, RDF.type, type_uri))
            added += 1
        elif pred == "label":
            g.add((subj, RDFS.label, Literal(obj_val, lang="en")))
            added += 1
        elif pred == "subClassOf":
            g.add((subj, RDFS.subClassOf, ns[obj_val]))
            added += 1
        elif pred == "domain":
            g.add((subj, RDFS.domain, ns[obj_val]))
            added += 1
        elif pred == "range":
            g.add((subj, RDFS.range, ns[obj_val]))
            added += 1
        elif pred == "sameAs":
            # Clean trailing punctuation from regex capture
            uri = obj_val.rstrip(";.")
            try:
                g.add((subj, OWL.sameAs, URIRef(uri)))
                added += 1
            except Exception:
                pass

    return added


def _extract_ontology_facts(g, source_id: str) -> list[dict]:
    """Extract atomic facts from the parsed RDF graph."""
    from rdflib import RDF, RDFS, OWL, Namespace

    facts = []
    seen = set()

    # Extract all classes and their labels
    classes = {}
    for s, p, o in g.triples((None, RDF.type, OWL.Class)):
        label = _get_label(g, s)
        if label:
            classes[s] = label

    for s, p, o in g.triples((None, RDF.type, RDFS.Class)):
        label = _get_label(g, s)
        if label:
            classes[s] = label

    logger.info(f"Found {len(classes)} named classes in ontology")

    # Extract subclass relationships (wine region hierarchy, grape taxonomy, etc.)
    for s, p, o in g.triples((None, RDFS.subClassOf, None)):
        s_label = _get_label(g, s) or classes.get(s)
        o_label = _get_label(g, o) or classes.get(o)

        if not s_label or not o_label:
            continue
        if s_label == o_label:
            continue

        domain, subdomain, tags = _classify_ontology_entity(s_label, o_label)

        key = f"subclass:{s_label}:{o_label}"
        if key not in seen:
            seen.add(key)
            facts.append({
                "fact_text": f"{s_label} is a type of {o_label} in wine classification.",
                "domain": domain,
                "subdomain": subdomain,
                "source_id": source_id,
                "entities": [
                    {"type": "class", "name": s_label},
                    {"type": "class", "name": o_label},
                ],
                "tags": tags,
            })

    # Extract OWL properties (e.g., hasColor, madeFromGrape, locatedIn)
    for prop_type in (OWL.ObjectProperty, OWL.DatatypeProperty):
        for s, p, o in g.triples((None, RDF.type, prop_type)):
            label = _get_label(g, s)
            if not label:
                continue

            # Get domain and range
            domain_node = None
            range_node = None
            for _, _, d in g.triples((s, RDFS.domain, None)):
                domain_node = _get_label(g, d)
            for _, _, r in g.triples((s, RDFS.range, None)):
                range_node = _get_label(g, r)

            readable = _property_to_readable(label)
            if domain_node and range_node:
                key = f"property:{label}:{domain_node}:{range_node}"
                if key not in seen:
                    seen.add(key)
                    facts.append({
                        "fact_text": f"In wine ontology, {domain_node} {readable} {range_node}.",
                        "domain": "winemaking",
                        "subdomain": "ontology",
                        "source_id": source_id,
                        "entities": [
                            {"type": "class", "name": domain_node},
                            {"type": "class", "name": range_node},
                        ],
                        "tags": ["ontology", "property"],
                    })
            elif domain_node:
                key = f"property_domain:{label}:{domain_node}"
                if key not in seen:
                    seen.add(key)
                    facts.append({
                        "fact_text": f"The property '{readable}' applies to {domain_node} in wine classification.",
                        "domain": "winemaking",
                        "subdomain": "ontology",
                        "source_id": source_id,
                        "entities": [
                            {"type": "class", "name": domain_node},
                        ],
                        "tags": ["ontology", "property"],
                    })

    # Extract individuals (named wine instances, regions, grapes)
    for s, p, o in g.triples((None, RDF.type, None)):
        s_label = _get_label(g, s)
        o_label = _get_label(g, o) or classes.get(o)

        if not s_label or not o_label:
            continue
        if o in (OWL.Class, RDFS.Class, OWL.ObjectProperty,
                 OWL.DatatypeProperty, OWL.Ontology, OWL.NamedIndividual,
                 OWL.Thing):
            continue
        # Safety net: reject generic OWL/RDFS class names even from unknown namespaces
        if o_label in ("Thing", "Resource", "Class", "Nothing"):
            continue

        domain, subdomain, tags = _classify_ontology_entity(s_label, o_label)

        key = f"individual:{s_label}:{o_label}"
        if key not in seen:
            seen.add(key)
            facts.append({
                "fact_text": f"{s_label} is classified as {o_label}.",
                "domain": domain,
                "subdomain": subdomain,
                "source_id": source_id,
                "entities": [
                    {"type": "instance", "name": s_label},
                    {"type": "class", "name": o_label},
                ],
                "tags": tags,
            })

    # Extract data properties on individuals (e.g., hasSugar "dry", hasBody "full")
    for s in g.subjects(RDF.type, None):
        s_label = _get_label(g, s)
        if not s_label:
            continue

        for pred, obj in g.predicate_objects(s):
            pred_label = _get_label(g, pred)
            if not pred_label:
                continue
            # Skip RDF/OWL built-in predicates
            pred_str = str(pred)
            if any(ns in pred_str for ns in [
                "www.w3.org", "rdf-syntax", "rdf-schema", "owl#"
            ]):
                continue

            obj_val = _get_label(g, obj) or str(obj)
            if len(obj_val) > 100:
                continue
            # Reject hash/UUID-like values in literals
            if re.search(r'[0-9a-f]{20,}', obj_val, re.IGNORECASE):
                continue
            # Reject purely numeric object values (database IDs)
            if obj_val.strip().isdigit():
                continue

            readable_pred = _property_to_readable(pred_label)
            key = f"data_prop:{s_label}:{pred_label}:{obj_val}"
            if key not in seen:
                seen.add(key)
                domain, subdomain, tags = _classify_ontology_entity(
                    s_label, pred_label
                )
                facts.append({
                    "fact_text": f"{s_label} {readable_pred} {obj_val}.",
                    "domain": domain,
                    "subdomain": subdomain,
                    "source_id": source_id,
                    "entities": [{"type": "instance", "name": s_label}],
                    "tags": tags + ["property"],
                })

    return facts


def _get_label(g, node) -> Optional[str]:
    """Get rdfs:label or derive a human-readable label from a URI."""
    from rdflib import RDFS

    for _, _, label in g.triples((node, RDFS.label, None)):
        return str(label)

    # Fall back to URI fragment
    uri = str(node)
    if "#" in uri:
        fragment = uri.split("#")[-1]
    elif "/" in uri:
        fragment = uri.split("/")[-1]
    else:
        return None

    if not fragment or fragment.startswith("Q") and fragment[1:].isdigit():
        return None

    # Reject purely numeric fragments (database IDs like "0172", "0250")
    if fragment.isdigit():
        return None

    # Reject hash/UUID-like fragments (20+ consecutive hex chars)
    if re.search(r'[0-9a-f]{20,}', fragment, re.IGNORECASE):
        return None

    # CamelCase to spaces
    readable = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", fragment)
    readable = readable.replace("_", " ").strip()
    return readable if readable else None


def _property_to_readable(prop_name: str) -> str:
    """Convert a property name like 'hasColor' to 'has color'."""
    readable = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", prop_name)
    return readable.lower().strip()


def _classify_ontology_entity(
    entity_label: str, class_label: str
) -> tuple[str, Optional[str], list[str]]:
    """Classify an ontology entity into a domain/subdomain."""
    combined = (entity_label + " " + class_label).lower()

    if any(w in combined for w in ["region", "location", "area", "appellation"]):
        return "wine_regions", "ontology", ["ontology", "region"]
    if any(w in combined for w in ["grape", "variety", "varietal"]):
        return "grape_varieties", "ontology", ["ontology", "grape"]
    if any(w in combined for w in ["producer", "winery", "maker", "chateau"]):
        return "producers", "ontology", ["ontology", "producer"]
    if any(w in combined for w in ["viticulture", "vine", "soil", "climate"]):
        return "viticulture", "ontology", ["ontology", "viticulture"]
    if any(w in combined for w in ["business", "price", "market", "trade"]):
        return "wine_business", "ontology", ["ontology", "business"]

    return "winemaking", "ontology", ["ontology", "classification"]


# ═══════════════════════════════════════════════════════════════════════════════
# SOURCE 2: UC Davis AVA Digitizing Project (GeoJSON)
# ═══════════════════════════════════════════════════════════════════════════════


def _scrape_ava(source_id: str, dry_run: bool = False, test_run_limit: Optional[int] = None) -> list[dict]:
    """Parse GeoJSON files from the AVA Digitizing Project."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = _clone_repo(SOURCES["ava"]["url"], tmpdir)

        # Find GeoJSON files — typically in avas/ directory
        geojson_files = list(Path(repo_path).rglob("*.geojson"))
        json_files = [
            f for f in Path(repo_path).rglob("*.json")
            if "geojson" in f.read_text(errors="ignore")[:200].lower()
            or '"type"' in f.read_text(errors="ignore")[:200]
        ]

        # Also check for a combined file
        all_files = geojson_files + json_files
        logger.info(f"Found {len(all_files)} GeoJSON/JSON files in AVA repo")

        avas = []
        for f in all_files:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                extracted = _extract_ava_from_geojson(data, f.stem)
                avas.extend(extracted)
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                logger.warning(f"Failed to parse {f.name}: {e}")

        # Deduplicate AVAs by name
        seen_names = set()
        unique_avas = []
        for ava in avas:
            name_key = ava["name"].lower().strip()
            if name_key not in seen_names:
                seen_names.add(name_key)
                unique_avas.append(ava)

        logger.info(f"Found {len(unique_avas)} unique AVAs")

        if test_run_limit:
            unique_avas = unique_avas[:test_run_limit]
            logger.info(f"[TEST RUN] Limited to {len(unique_avas)} AVAs")

        # Quality check: warn if count is low (skip during test runs)
        if not test_run_limit and len(unique_avas) < KNOWN_AVA_COUNT * 0.8:
            logger.warning(
                f"AVA count ({len(unique_avas)}) is significantly below "
                f"expected ~{KNOWN_AVA_COUNT}. Some AVAs may be missing."
            )

        facts = _build_ava_facts(unique_avas, source_id)

    logger.info(f"Generated {len(facts)} facts from AVA project")
    return facts


def _extract_ava_from_geojson(data: dict, filename: str) -> list[dict]:
    """Extract AVA metadata from a GeoJSON feature or feature collection."""
    avas = []

    features = []
    if data.get("type") == "FeatureCollection":
        features = data.get("features", [])
    elif data.get("type") == "Feature":
        features = [data]
    elif data.get("properties"):
        features = [data]

    for feature in features:
        props = feature.get("properties", {})
        if not props:
            continue

        ava = {
            "name": (
                props.get("name")
                or props.get("NAME")
                or props.get("ava_name")
                or props.get("AVA_NAME")
                or props.get("title")
                or filename.replace("_", " ").replace("-", " ").title()
            ),
            "state": props.get("state") or props.get("STATE") or props.get("states"),
            "within": (
                props.get("within")
                or props.get("WITHIN")
                or props.get("contained_by")
                or props.get("parent")
            ),
            "created": (
                props.get("created")
                or props.get("CREATED")
                or props.get("established")
                or props.get("valid_start")
                or props.get("cfr_revision_history")
            ),
            "cfr_author": props.get("cfr_author") or props.get("CFR_AUTHOR"),
            "cfr_index": props.get("cfr_index") or props.get("CFR_INDEX"),
            "fr_doc": (
                props.get("used_fr_doc")
                or props.get("fr_doc")
                or props.get("FR_DOC")
            ),
        }

        # Try to extract year from created field
        if ava["created"]:
            year_match = re.search(r"\b(19|20)\d{2}\b", str(ava["created"]))
            if year_match:
                ava["year"] = year_match.group()
            else:
                ava["year"] = None
        else:
            ava["year"] = None

        if ava["name"]:
            avas.append(ava)

    return avas


def _build_ava_facts(avas: list[dict], source_id: str) -> list[dict]:
    """Convert AVA metadata into atomic facts."""
    facts = []
    seen = set()

    # Aggregate count fact
    total = len(avas)
    facts.append({
        "fact_text": f"There are {total} American Viticultural Areas documented in the UC Davis AVA project.",
        "domain": "wine_regions",
        "subdomain": "ava",
        "source_id": source_id,
        "entities": [],
        "tags": ["ava", "united_states", "count"],
    })

    for ava in avas:
        name = ava["name"]
        ava_label = f"{name} AVA" if not name.upper().endswith("AVA") else name

        # Fact: AVA existence and state
        if ava.get("state"):
            state_str = ava["state"]
            key = f"ava_state:{name}:{state_str}"
            if key not in seen:
                seen.add(key)
                facts.append({
                    "fact_text": f"{ava_label} is an American Viticultural Area located in {state_str}.",
                    "domain": "wine_regions",
                    "subdomain": "ava",
                    "source_id": source_id,
                    "entities": [
                        {"type": "ava", "name": name},
                        {"type": "state", "name": state_str},
                    ],
                    "tags": ["ava", "united_states", "geography"],
                })
        else:
            key = f"ava_exists:{name}"
            if key not in seen:
                seen.add(key)
                facts.append({
                    "fact_text": f"{ava_label} is a recognized American Viticultural Area.",
                    "domain": "wine_regions",
                    "subdomain": "ava",
                    "source_id": source_id,
                    "entities": [{"type": "ava", "name": name}],
                    "tags": ["ava", "united_states"],
                })

        # Fact: establishment year
        if ava.get("year"):
            key = f"ava_year:{name}:{ava['year']}"
            if key not in seen:
                seen.add(key)
                facts.append({
                    "fact_text": f"{ava_label} was established in {ava['year']}.",
                    "domain": "wine_regions",
                    "subdomain": "ava",
                    "source_id": source_id,
                    "entities": [{"type": "ava", "name": name}],
                    "tags": ["ava", "united_states", "history", "establishment"],
                })

        # Fact: parent AVA relationship
        if ava.get("within"):
            within = ava["within"]
            # Can be comma-separated
            parents = [p.strip() for p in within.split(",") if p.strip()]
            for parent in parents:
                parent_label = (
                    f"{parent} AVA" if not parent.upper().endswith("AVA") else parent
                )
                key = f"ava_within:{name}:{parent}"
                if key not in seen:
                    seen.add(key)
                    facts.append({
                        "fact_text": f"{ava_label} is located within the {parent_label}.",
                        "domain": "wine_regions",
                        "subdomain": "ava",
                        "source_id": source_id,
                        "entities": [
                            {"type": "ava", "name": name},
                            {"type": "ava", "name": parent},
                        ],
                        "tags": ["ava", "united_states", "hierarchy"],
                    })

        # Fact: Federal Register reference
        if ava.get("fr_doc"):
            key = f"ava_fr:{name}"
            if key not in seen:
                seen.add(key)
                facts.append({
                    "fact_text": f"{ava_label} boundaries are defined in Federal Register document {ava['fr_doc']}.",
                    "domain": "wine_regions",
                    "subdomain": "ava",
                    "source_id": source_id,
                    "entities": [{"type": "ava", "name": name}],
                    "tags": ["ava", "united_states", "regulation", "federal_register"],
                })

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# SOURCE 3: UC Davis FPS Grape Variety Database (HTML)
# ═══════════════════════════════════════════════════════════════════════════════


def _scrape_fps(source_id: str, dry_run: bool = False, test_run_limit: Optional[int] = None) -> list[dict]:
    """Scrape the FPS grape variety database from HTML pages."""
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    # Start from the grape variety listing page
    base_url = "https://fps.ucdavis.edu"
    index_url = f"{base_url}/fgrvarieties.cfm"

    logger.info(f"Fetching FPS varieties page: {index_url}")
    resp = session.get(index_url, timeout=30)
    resp.raise_for_status()
    time.sleep(FPS_REQUEST_DELAY)

    soup = BeautifulSoup(resp.text, "lxml")

    # Find links to variety detail pages
    variety_links = _find_variety_links(soup, base_url)
    logger.info(f"Found {len(variety_links)} variety links on index page")

    # If the main page uses a letter-based index (A-Z), follow each letter page
    if len(variety_links) < 20:
        letter_links = _find_letter_index_links(soup, base_url)
        if letter_links:
            logger.info(f"Found {len(letter_links)} letter-index pages, following them...")
            for letter_url in letter_links:
                try:
                    resp = session.get(letter_url, timeout=30)
                    resp.raise_for_status()
                    time.sleep(FPS_REQUEST_DELAY)
                    letter_soup = BeautifulSoup(resp.text, "lxml")
                    new_links = _find_variety_links(letter_soup, base_url)
                    variety_links.extend(new_links)
                    logger.debug(f"Found {len(new_links)} variety links on {letter_url}")
                except Exception as e:
                    logger.debug(f"Could not fetch letter page {letter_url}: {e}")

    # Deduplicate variety links
    seen_urls = set()
    unique_links = []
    for link in variety_links:
        if link["url"] not in seen_urls:
            seen_urls.add(link["url"])
            unique_links.append(link)
    variety_links = unique_links

    # If still not enough, try alternative pages
    if len(variety_links) < 10:
        alt_urls = [
            f"{base_url}/fgrselections.cfm",
            f"{base_url}/fgrabout.cfm",
        ]
        for alt_url in alt_urls:
            try:
                logger.info(f"Trying alternative page: {alt_url}")
                resp = session.get(alt_url, timeout=30)
                resp.raise_for_status()
                time.sleep(FPS_REQUEST_DELAY)
                soup_alt = BeautifulSoup(resp.text, "lxml")
                alt_links = _find_variety_links(soup_alt, base_url)
                if len(alt_links) > len(variety_links):
                    variety_links = alt_links
                    soup = soup_alt
                    logger.info(f"Found {len(alt_links)} links on {alt_url}")
            except Exception as e:
                logger.debug(f"Could not fetch {alt_url}: {e}")

    # Also extract facts directly from any tables on the index/list pages
    facts = _extract_fps_table_facts(soup, source_id)
    logger.info(f"Extracted {len(facts)} facts from index/list tables")

    if test_run_limit:
        facts = _limit_fps_facts_by_variety(facts, test_run_limit)
        logger.info(f"[TEST RUN] Limited to facts from first {test_run_limit} varieties ({len(facts)} facts)")
        variety_links = variety_links[:test_run_limit]
        logger.info(f"[TEST RUN] Limited to {len(variety_links)} variety pages")

    # Scrape individual variety pages
    scraped_count = 0
    for link_info in variety_links:
        url = link_info["url"]
        variety_name = link_info.get("name", "")

        try:
            logger.debug(f"Fetching variety page: {variety_name} ({url})")
            resp = session.get(url, timeout=30)
            resp.raise_for_status()
            time.sleep(FPS_REQUEST_DELAY)

            page_soup = BeautifulSoup(resp.text, "lxml")
            page_facts = _extract_fps_variety_facts(
                page_soup, variety_name, url, source_id
            )
            facts.extend(page_facts)
            scraped_count += 1

            if scraped_count % 50 == 0:
                logger.info(
                    f"Scraped {scraped_count}/{len(variety_links)} variety pages"
                )
        except Exception as e:
            logger.warning(f"Failed to scrape {url}: {e}")

    # Deduplicate
    seen = set()
    unique_facts = []
    for fact in facts:
        if fact["fact_text"] not in seen:
            seen.add(fact["fact_text"])
            unique_facts.append(fact)

    logger.info(f"Generated {len(unique_facts)} unique facts from FPS database")
    return unique_facts


def _find_variety_links(soup: BeautifulSoup, base_url: str) -> list[dict]:
    """Find links to individual grape variety detail pages (fgrdetails.cfm?varietyid=X)."""
    links = []
    seen_urls = set()

    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(strip=True)
        href_lower = href.lower()

        # Only match actual variety detail pages, not navigation pages
        # Detail pages use: fgrdetails.cfm?varietyid=123
        if "fgrdetails" in href_lower or "varietyid=" in href_lower:
            if href.startswith("/"):
                full_url = base_url + href
            elif href.startswith("http"):
                full_url = href
            else:
                full_url = base_url + "/" + href

            if full_url not in seen_urls:
                seen_urls.add(full_url)
                links.append({"url": full_url, "name": text or ""})

    return links


def _find_letter_index_links(soup: BeautifulSoup, base_url: str) -> list[str]:
    """Find letter-based index links (A-Z) on paginated variety listing pages."""
    links = []
    seen = set()

    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(strip=True)
        href_lower = href.lower()

        # Look for letter-index patterns: ?letter=A, or single-letter links to variety pages
        if "letter=" in href_lower or (
            len(text) == 1 and text.isalpha() and "fgrvariet" in href_lower
        ):
            if href.startswith("/"):
                full_url = base_url + href
            elif href.startswith("http"):
                full_url = href
            else:
                full_url = base_url + "/" + href

            if full_url not in seen:
                seen.add(full_url)
                links.append(full_url)

    return sorted(links)


def _limit_fps_facts_by_variety(facts: list[dict], limit: int) -> list[dict]:
    """Limit FPS facts to those from the first N unique grape varieties."""
    seen_varieties = set()
    limited = []
    for fact in facts:
        variety = None
        for ent in fact.get("entities", []):
            if ent.get("type") == "grape":
                variety = ent["name"]
                break
        if variety is not None:
            if variety not in seen_varieties:
                if len(seen_varieties) >= limit:
                    continue
                seen_varieties.add(variety)
        limited.append(fact)
    return limited


def _extract_fps_table_facts(
    soup: BeautifulSoup, source_id: str
) -> list[dict]:
    """Extract facts from HTML tables on the FPS pages."""
    facts = []
    seen = set()

    tables = soup.find_all("table")
    for table in tables:
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue

        # Try to find header row
        headers = []
        header_row = rows[0]
        for th in header_row.find_all(["th", "td"]):
            headers.append(th.get_text(strip=True).lower())

        if not headers:
            continue

        # Map column indices
        col_map = {}
        for i, h in enumerate(headers):
            if any(w in h for w in ["variety", "name", "cultivar"]):
                col_map["name"] = i
            elif any(w in h for w in ["synonym", "alias", "other name"]):
                col_map["synonym"] = i
            elif any(w in h for w in ["clone", "selection"]):
                col_map["clones"] = i
            elif any(w in h for w in ["color", "type"]):
                col_map["color"] = i
            elif any(w in h for w in ["ttb", "approved", "official"]):
                col_map["ttb_name"] = i
            elif any(w in h for w in ["origin", "country"]):
                col_map["origin"] = i

        if "name" not in col_map:
            continue

        for row in rows[1:]:
            cells = row.find_all(["td", "th"])
            if len(cells) <= col_map["name"]:
                continue

            name = cells[col_map["name"]].get_text(strip=True)
            if not name:
                continue

            # Fact: variety exists in FPS collection
            key = f"fps_variety:{name}"
            if key not in seen:
                seen.add(key)
                facts.append({
                    "fact_text": f"{name} is registered in the UC Davis Foundation Plant Services grape collection.",
                    "domain": "grape_varieties",
                    "subdomain": "fps",
                    "source_id": source_id,
                    "entities": [{"type": "grape", "name": name}],
                    "tags": ["fps", "ucdavis", "grape"],
                })

            # Clone count
            if "clones" in col_map and len(cells) > col_map["clones"]:
                clone_text = cells[col_map["clones"]].get_text(strip=True)
                clone_count = _extract_number(clone_text)
                if clone_count and clone_count > 0:
                    key = f"fps_clones:{name}:{clone_count}"
                    if key not in seen:
                        seen.add(key)
                        facts.append({
                            "fact_text": f"{name} has {clone_count} registered clones in the UC Davis FPS collection.",
                            "domain": "grape_varieties",
                            "subdomain": "fps",
                            "source_id": source_id,
                            "entities": [{"type": "grape", "name": name}],
                            "tags": ["fps", "ucdavis", "grape", "clone"],
                        })

            # TTB approved name
            if "ttb_name" in col_map and len(cells) > col_map["ttb_name"]:
                ttb_name = cells[col_map["ttb_name"]].get_text(strip=True)
                if ttb_name and ttb_name.lower() != name.lower():
                    key = f"fps_ttb:{name}:{ttb_name}"
                    if key not in seen:
                        seen.add(key)
                        facts.append({
                            "fact_text": f"{ttb_name} is the TTB-approved name for {name}.",
                            "domain": "grape_varieties",
                            "subdomain": "fps",
                            "source_id": source_id,
                            "entities": [
                                {"type": "grape", "name": name},
                                {"type": "grape", "name": ttb_name},
                            ],
                            "tags": ["fps", "ucdavis", "grape", "ttb", "regulation"],
                        })

            # Synonyms
            if "synonym" in col_map and len(cells) > col_map["synonym"]:
                syn_text = cells[col_map["synonym"]].get_text(strip=True)
                if syn_text:
                    synonyms = [s.strip() for s in re.split(r"[,;/]", syn_text) if s.strip()]
                    for syn in synonyms[:5]:  # limit to avoid noise
                        key = f"fps_synonym:{name}:{syn}"
                        if key not in seen:
                            seen.add(key)
                            facts.append({
                                "fact_text": f"{syn} is a synonym for the grape variety {name}.",
                                "domain": "grape_varieties",
                                "subdomain": "fps",
                                "source_id": source_id,
                                "entities": [
                                    {"type": "grape", "name": name},
                                    {"type": "grape", "name": syn},
                                ],
                                "tags": ["fps", "ucdavis", "grape", "synonym"],
                            })

            # Color
            if "color" in col_map and len(cells) > col_map["color"]:
                color_text = cells[col_map["color"]].get_text(strip=True)
                if color_text:
                    key = f"fps_color:{name}:{color_text}"
                    if key not in seen:
                        seen.add(key)
                        facts.append({
                            "fact_text": f"{name} is a {color_text.lower()} grape variety according to UC Davis FPS.",
                            "domain": "grape_varieties",
                            "subdomain": "fps",
                            "source_id": source_id,
                            "entities": [{"type": "grape", "name": name}],
                            "tags": ["fps", "ucdavis", "grape", color_text.lower()],
                        })

    return facts


def _extract_fps_variety_facts(
    soup: BeautifulSoup, variety_name: str, url: str, source_id: str
) -> list[dict]:
    """Extract facts from an individual FPS variety detail page."""
    facts = []
    seen = set()

    # Try to get the variety name from the page title if not provided
    if not variety_name:
        title = soup.find("h1") or soup.find("h2") or soup.find("title")
        if title:
            variety_name = title.get_text(strip=True)
    if not variety_name:
        return facts

    # Clean the variety name
    variety_name = re.sub(r"\s*\(.*?\)\s*", "", variety_name).strip()
    if not variety_name:
        return facts

    page_text = soup.get_text(" ", strip=True)

    # Look for clone count
    clone_patterns = [
        r"(\d+)\s*(?:registered\s+)?clones?",
        r"clones?\s*(?:available)?:?\s*(\d+)",
        r"(\d+)\s*selections?",
    ]
    for pattern in clone_patterns:
        match = re.search(pattern, page_text, re.IGNORECASE)
        if match:
            count = int(match.group(1))
            if 0 < count < 500:
                key = f"fps_clones:{variety_name}:{count}"
                if key not in seen:
                    seen.add(key)
                    facts.append({
                        "fact_text": f"{variety_name} has {count} registered clones in the UC Davis FPS collection.",
                        "domain": "grape_varieties",
                        "subdomain": "fps",
                        "source_id": source_id,
                        "entities": [{"type": "grape", "name": variety_name}],
                        "tags": ["fps", "ucdavis", "grape", "clone"],
                    })
                break

    # Look for TTB name
    ttb_patterns = [
        r"TTB[- ]?approved\s+name:?\s*([A-Z][a-zA-Zéèüöä\s]+)",
        r"official\s+name:?\s*([A-Z][a-zA-Zéèüöä\s]+)",
    ]
    for pattern in ttb_patterns:
        match = re.search(pattern, page_text, re.IGNORECASE)
        if match:
            ttb_name = match.group(1).strip()
            if ttb_name and ttb_name.lower() != variety_name.lower():
                key = f"fps_ttb:{variety_name}:{ttb_name}"
                if key not in seen:
                    seen.add(key)
                    facts.append({
                        "fact_text": f"{ttb_name} is the TTB-approved name for {variety_name}.",
                        "domain": "grape_varieties",
                        "subdomain": "fps",
                        "source_id": source_id,
                        "entities": [
                            {"type": "grape", "name": variety_name},
                            {"type": "grape", "name": ttb_name},
                        ],
                        "tags": ["fps", "ucdavis", "grape", "ttb", "regulation"],
                    })
            break

    # Look for color/type info
    color_patterns = [
        r"(?:berry\s+)?color:?\s*(black|red|white|green|pink|grey|blue)",
        r"(red|white|black)\s+(?:wine\s+)?grape",
    ]
    for pattern in color_patterns:
        match = re.search(pattern, page_text, re.IGNORECASE)
        if match:
            color = match.group(1).lower()
            wine_color = "red" if color in ("black", "blue") else color
            key = f"fps_color:{variety_name}:{wine_color}"
            if key not in seen:
                seen.add(key)
                facts.append({
                    "fact_text": f"{variety_name} is a {wine_color} grape variety according to UC Davis FPS.",
                    "domain": "grape_varieties",
                    "subdomain": "fps",
                    "source_id": source_id,
                    "entities": [{"type": "grape", "name": variety_name}],
                    "tags": ["fps", "ucdavis", "grape", wine_color],
                })
            break

    # Look for origin info
    origin_patterns = [
        r"origin:?\s*([A-Z][a-zA-Z\s,]+?)(?:\.|$)",
        r"native\s+to\s+([A-Z][a-zA-Z\s,]+?)(?:\.|$)",
        r"originat(?:ed|ing)\s+(?:from|in)\s+([A-Z][a-zA-Z\s,]+?)(?:\.|$)",
    ]
    for pattern in origin_patterns:
        match = re.search(pattern, page_text)
        if match:
            origin = match.group(1).strip().rstrip(",")
            if len(origin) < 50:
                key = f"fps_origin:{variety_name}:{origin}"
                if key not in seen:
                    seen.add(key)
                    facts.append({
                        "fact_text": f"{variety_name} originates from {origin}.",
                        "domain": "grape_varieties",
                        "subdomain": "fps",
                        "source_id": source_id,
                        "entities": [
                            {"type": "grape", "name": variety_name},
                            {"type": "region", "name": origin},
                        ],
                        "tags": ["fps", "ucdavis", "grape", "origin"],
                    })
            break

    # Extract facts from tables on the detail page
    tables = soup.find_all("table")
    for table in tables:
        table_facts = _extract_fps_detail_table(
            table, variety_name, source_id
        )
        for tf in table_facts:
            if tf["fact_text"] not in seen:
                seen.add(tf["fact_text"])
                facts.append(tf)

    return facts


def _extract_fps_detail_table(
    table, variety_name: str, source_id: str
) -> list[dict]:
    """Extract facts from a detail page table (clone list, etc.)."""
    facts = []
    rows = table.find_all("tr")
    if len(rows) < 2:
        return facts

    # Check if it's a clone table
    header_text = rows[0].get_text(" ", strip=True).lower()
    if any(w in header_text for w in ["clone", "selection", "accession"]):
        clone_count = len(rows) - 1  # minus header
        if clone_count > 0:
            facts.append({
                "fact_text": f"{variety_name} has {clone_count} registered clones in the UC Davis FPS collection.",
                "domain": "grape_varieties",
                "subdomain": "fps",
                "source_id": source_id,
                "entities": [{"type": "grape", "name": variety_name}],
                "tags": ["fps", "ucdavis", "grape", "clone"],
            })

    return facts


def _extract_number(text: str) -> Optional[int]:
    """Extract the first integer from a string."""
    match = re.search(r"\d+", text)
    return int(match.group()) if match else None


# ═══════════════════════════════════════════════════════════════════════════════
# Validation
# ═══════════════════════════════════════════════════════════════════════════════


def validate_facts(source_ids: list[str]):
    """Run quality checks on inserted facts from UC Davis sources."""
    from src.utils.db import get_pg

    conn = get_pg()
    cur = conn.cursor()

    # Get all facts for these sources
    placeholders = ",".join(["%s"] * len(source_ids))
    cur.execute(
        f"SELECT fact_text, domain, subdomain, entities FROM facts WHERE source_id IN ({placeholders})",
        source_ids,
    )
    rows = cur.fetchall()

    if not rows:
        click.echo("No facts found for UC Davis sources. Run --all first.")
        return

    facts = [dict(r) for r in rows]
    total = len(facts)

    # Domain distribution
    domain_counts = Counter(f["domain"] for f in facts)
    subdomain_counts = Counter(
        f"{f['domain']}/{f['subdomain']}" for f in facts if f.get("subdomain")
    )

    click.echo(f"\n{'='*60}")
    click.echo(f"UC Davis Validation Report — {total} total facts")
    click.echo(f"{'='*60}")

    click.echo("\nDomain distribution:")
    for domain, count in sorted(domain_counts.items(), key=lambda x: -x[1]):
        click.echo(f"  {domain:25s}: {count:5d} facts")

    click.echo("\nSubdomain distribution:")
    for subdomain, count in sorted(subdomain_counts.items(), key=lambda x: -x[1]):
        click.echo(f"  {subdomain:35s}: {count:5d} facts")

    # Quality checks
    too_short = [f for f in facts if len(f["fact_text"].split()) < 5]
    too_long = [f for f in facts if len(f["fact_text"].split()) > 50]

    # Check for facts that are just entity names
    no_predicate = []
    for f in facts:
        text = f["fact_text"].rstrip(".")
        if len(text.split()) <= 2:
            no_predicate.append(f)

    # Check for entities populated
    import orjson

    entities_populated = 0
    entities_empty = 0
    for f in facts:
        ent = f.get("entities")
        if isinstance(ent, str):
            ent = orjson.loads(ent)
        if ent:
            entities_populated += 1
        else:
            entities_empty += 1

    # Near-duplicate detection (simple string containment)
    near_dupes = _find_near_duplicates(facts)

    click.echo("\nQuality:")
    click.echo(f"  Too short (<5 words):  {len(too_short):5d} ({len(too_short)/total*100:.1f}%)")
    click.echo(f"  Too long (>50 words):  {len(too_long):5d} ({len(too_long)/total*100:.1f}%)")
    click.echo(f"  No predicate:          {len(no_predicate):5d} ({len(no_predicate)/total*100:.1f}%)")
    click.echo(f"  Missing entities:      {entities_empty:5d} ({entities_empty/total*100:.1f}%)")
    click.echo(f"  Possible near-dupes:   {len(near_dupes):5d} ({len(near_dupes)/total*100:.1f}%)")

    # Print some examples of issues
    if too_short:
        click.echo("\n  Examples of too-short facts:")
        for f in too_short[:3]:
            click.echo(f'    - "{f["fact_text"]}"')

    if too_long:
        click.echo("\n  Examples of too-long facts:")
        for f in too_long[:3]:
            click.echo(f'    - "{f["fact_text"][:100]}..."')

    if near_dupes:
        click.echo("\n  Examples of near-duplicates:")
        for pair in near_dupes[:3]:
            click.echo(f'    - "{pair[0]}"')
            click.echo(f'      "{pair[1]}"')

    # Random sample
    click.echo("\nSample facts:")
    sample = random.sample(facts, min(10, len(facts)))
    for i, f in enumerate(sample, 1):
        click.echo(f'  {i:2d}. "{f["fact_text"]}"')

    click.echo(f"\n{'='*60}")


def _find_near_duplicates(facts: list[dict], max_check: int = 2000) -> list[tuple]:
    """Find near-duplicate facts using simple string containment."""
    near_dupes = []
    texts = [f["fact_text"].lower() for f in facts]

    # Only check a sample if there are too many
    if len(texts) > max_check:
        indices = random.sample(range(len(texts)), max_check)
        check_texts = [(i, texts[i]) for i in indices]
    else:
        check_texts = list(enumerate(texts))

    checked = set()
    for i, text_a in check_texts:
        for j, text_b in check_texts:
            if i >= j:
                continue
            pair_key = (min(i, j), max(i, j))
            if pair_key in checked:
                continue
            checked.add(pair_key)

            # Check if one contains the other (but they're not identical)
            if text_a != text_b and (text_a in text_b or text_b in text_a):
                near_dupes.append((facts[i]["fact_text"], facts[j]["fact_text"]))
                if len(near_dupes) >= 50:
                    return near_dupes

    return near_dupes


# ═══════════════════════════════════════════════════════════════════════════════
# Test Run
# ═══════════════════════════════════════════════════════════════════════════════

TEST_RUN_LIMIT = 5


def run_test_run(source_filter: Optional[str] = None, cleanup: bool = False):
    """Execute a test run: process 5 items per source, insert, report, optionally clean up."""
    sources_to_run = [source_filter] if source_filter else list(SOURCES.keys())

    results = []
    all_fact_texts = []

    scrapers = {
        "ontology": _scrape_ontology,
        "ava": _scrape_ava,
        "fps": _scrape_fps,
    }

    for source_name in sources_to_run:
        if source_name not in SOURCES:
            logger.error(f"Unknown source: {source_name}")
            continue

        config = SOURCES[source_name]
        source_id = ensure_source(
            name=config["name"],
            url=config["url"],
            source_type=config["source_type"],
            tier=config["tier"],
        )

        # Scrape with limit
        logger.info(f"[TEST RUN] Scraping {source_name} (limit={TEST_RUN_LIMIT})")
        facts = scrapers[source_name](source_id, test_run_limit=TEST_RUN_LIMIT)
        items_processed = _count_items_in_facts(facts, source_name)

        # Insert
        if facts:
            inserted = insert_facts_batch(facts)
        else:
            inserted = 0

        # Track fact texts for cleanup
        all_fact_texts.extend(f["fact_text"] for f in facts)

        results.append({
            "source": source_name,
            "items_processed": items_processed,
            "facts_generated": len(facts),
            "facts_inserted": inserted,
            "facts": facts,
        })

    # Print report
    _print_test_run_report(results)

    # Cleanup if requested
    if cleanup and all_fact_texts:
        cleaned = _cleanup_test_facts(all_fact_texts)
        click.echo(f"\nCleaned up {cleaned} test facts from database")


def _count_items_in_facts(facts: list[dict], source_name: str) -> int:
    """Count unique primary items (entities) in a facts list for the test-run report."""
    items = set()
    for fact in facts:
        entities = fact.get("entities", [])
        if not entities:
            continue
        primary = entities[0]
        name = primary.get("name", "")
        if not name:
            continue
        if source_name == "ava" and primary.get("type") == "ava":
            items.add(name)
        elif source_name == "fps" and primary.get("type") == "grape":
            items.add(name)
        elif source_name == "ontology":
            items.add(name)
    return len(items) if items else min(len(facts), TEST_RUN_LIMIT)


def _print_test_run_report(results: list[dict]):
    """Print the structured test-run report with quality checks and warnings."""
    all_facts = []
    for r in results:
        all_facts.extend(r["facts"])

    total_items = sum(r["items_processed"] for r in results)
    total_generated = sum(r["facts_generated"] for r in results)
    total_inserted = sum(r["facts_inserted"] for r in results)

    click.echo("")
    click.echo("=== TEST RUN REPORT ===")
    click.echo(
        f"{'Source/Category':<23s} {'Items Processed':>17s} "
        f"{'Facts Generated':>17s} {'Facts Inserted (new)':>22s}"
    )
    click.echo("\u2500" * 80)

    for r in results:
        click.echo(
            f"{r['source']:<23s} {r['items_processed']:>17d} "
            f"{r['facts_generated']:>17d} {r['facts_inserted']:>22d}"
        )

    click.echo("\u2500" * 80)
    click.echo(
        f"{'TOTAL':<23s} {total_items:>17d} "
        f"{total_generated:>17d} {total_inserted:>22d}"
    )

    if not all_facts:
        click.echo("\nNo facts generated — nothing to check.")
        return

    total = len(all_facts)
    too_short = [f for f in all_facts if len(f["fact_text"].split()) < 5]
    too_long = [f for f in all_facts if len(f["fact_text"].split()) > 50]
    missing_entities = [f for f in all_facts if not f.get("entities")]
    word_counts = [len(f["fact_text"].split()) for f in all_facts]
    avg_words = sum(word_counts) / len(word_counts)

    click.echo("\nQuality Checks:")
    click.echo(f"  Too short (<5 words):    {len(too_short)} ({len(too_short)/total*100:.1f}%)")
    click.echo(f"  Too long (>50 words):    {len(too_long)} ({len(too_long)/total*100:.1f}%)")
    click.echo(f"  Missing entities:        {len(missing_entities)} ({len(missing_entities)/total*100:.1f}%)")
    click.echo(f"  Avg words per fact:      {avg_words:.1f}")

    # Sample facts
    sample = random.sample(all_facts, min(10, total))
    click.echo(f"\nSample Facts ({min(10, total)} random from this run):")
    for i, f in enumerate(sample, 1):
        click.echo(f'  {i:2d}. "{f["fact_text"]}"')

    # Warnings
    warnings = []

    for r in results:
        src = r["source"]

        # Zero facts generated
        if r["facts_generated"] == 0:
            warnings.append(f"ERROR: No facts from {src}")
        # Facts generated but none inserted (all dupes)
        elif r["facts_inserted"] == 0:
            warnings.append(
                f"ERROR: No facts inserted from {src} (all duplicates?)"
            )

        # Low extraction rate
        if r["items_processed"] > 0:
            avg_per_item = r["facts_generated"] / r["items_processed"]
            if avg_per_item < 2:
                warnings.append(
                    f"WARNING: Low extraction rate in {src} "
                    f"({avg_per_item:.1f} facts/item, expected 4-6)"
                )

        # High duplicate rate
        if r["facts_generated"] > 0:
            dupe_rate = (r["facts_generated"] - r["facts_inserted"]) / r["facts_generated"]
            if dupe_rate > 0.5:
                warnings.append(
                    f"WARNING: High duplicate rate in {src} "
                    f"({dupe_rate*100:.0f}% skipped)"
                )

    # Global quality warnings
    if len(too_short) / total > 0.1:
        warnings.append("WARNING: Too many trivial facts (>10% under 5 words)")
    if len(too_long) / total > 0.1:
        warnings.append("WARNING: Facts need better splitting (>10% over 50 words)")

    # Verbatim text check
    regarding_facts = [f for f in all_facts if f["fact_text"].startswith("Regarding")]
    if regarding_facts:
        warnings.append(
            f"WARNING: Verbatim text detected "
            f"({len(regarding_facts)} facts start with 'Regarding')"
        )

    # Facts over 40 words for manual review
    long_facts = [f for f in all_facts if len(f["fact_text"].split()) > 40]
    if long_facts:
        warnings.append(
            f"{len(long_facts)} facts exceed 40 words — review fact splitting logic"
        )

    if warnings:
        click.echo("\nWarnings:")
        for w in warnings:
            click.echo(f"  - {w}")
        if long_facts:
            click.echo("\n  Facts over 40 words (manual review):")
            for f in long_facts[:5]:
                click.echo(f'    - "{f["fact_text"]}"')
    else:
        click.echo("\nNo warnings — all checks passed!")


def _cleanup_test_facts(fact_texts: list[str]) -> int:
    """Delete test-run facts from the database. Returns count deleted."""
    from src.utils.db import get_pg

    conn = get_pg()
    cur = conn.cursor()

    deleted = 0
    batch_size = 100
    for i in range(0, len(fact_texts), batch_size):
        batch = fact_texts[i : i + batch_size]
        placeholders = ",".join(["%s"] * len(batch))
        cur.execute(
            f"DELETE FROM facts WHERE fact_text IN ({placeholders})",
            batch,
        )
        deleted += cur.rowcount

    conn.commit()
    logger.info(f"Cleaned up {deleted} test facts from database")
    return deleted


# ═══════════════════════════════════════════════════════════════════════════════
# Main Pipeline
# ═══════════════════════════════════════════════════════════════════════════════


def run_source(source_name: str, dry_run: bool = False, test_run_limit: Optional[int] = None) -> int:
    """Run a single source scraper. Returns fact count."""
    if source_name not in SOURCES:
        logger.error(
            f"Unknown source: {source_name}. Available: {list(SOURCES.keys())}"
        )
        return 0

    config = SOURCES[source_name]
    logger.info(f"Running source: {source_name} — {config['description']}")

    source_id = ensure_source(
        name=config["name"],
        url=config["url"],
        source_type=config["source_type"],
        tier=config["tier"],
    )

    scrapers = {
        "ontology": _scrape_ontology,
        "ava": _scrape_ava,
        "fps": _scrape_fps,
    }

    facts = scrapers[source_name](source_id, dry_run=dry_run, test_run_limit=test_run_limit)

    if dry_run:
        click.echo(f"\n[DRY RUN] Would insert {len(facts)} facts from {source_name}")
        click.echo("Sample facts:")
        for f in facts[:10]:
            click.echo(f'  - "{f["fact_text"]}"')
        return len(facts)

    if not facts:
        logger.warning(f"No facts generated from {source_name}")
        return 0

    inserted = insert_facts_batch(facts)
    logger.info(f"Inserted {inserted} new facts from {source_name}")

    # AVA quality check
    if source_name == "ava":
        ava_facts = [f for f in facts if f.get("subdomain") == "ava"]
        ava_names = set()
        for f in ava_facts:
            for ent in f.get("entities", []):
                if ent.get("type") == "ava":
                    ava_names.add(ent["name"])
        if len(ava_names) < KNOWN_AVA_COUNT * 0.8:
            logger.warning(
                f"AVA quality check: Only found {len(ava_names)} unique AVA names, "
                f"expected ~{KNOWN_AVA_COUNT}. Check data completeness."
            )
            click.echo(
                f"\n⚠ AVA WARNING: Found {len(ava_names)} AVAs, expected ~{KNOWN_AVA_COUNT}"
            )
        else:
            click.echo(f"\n✓ AVA count check passed: {len(ava_names)} AVAs found")

    return inserted


def run_all(dry_run: bool = False) -> dict:
    """Run all three sources. Returns summary."""
    summary = {}
    total = 0

    for source_name in SOURCES:
        count = run_source(source_name, dry_run=dry_run)
        summary[source_name] = count
        total += count

    if not dry_run:
        logger.info(f"UC Davis scraping complete. Total new facts: {total}")
        logger.info(f"Total facts in database: {get_fact_count()}")

    return summary


# ─── CLI ──────────────────────────────────────────────────────────────────────


@click.command()
@click.option("--source", "-s", type=click.Choice(["ontology", "ava", "fps"]),
              help="Run a specific source")
@click.option("--all", "run_all_flag", is_flag=True, help="Run all three sources")
@click.option("--list", "list_sources", is_flag=True, help="List available sources")
@click.option("--dry-run", is_flag=True, help="Parse and generate facts without inserting")
@click.option("--validate", is_flag=True, help="Run quality checks on inserted facts")
@click.option("--test-run", is_flag=True, help="Run limited test (5 items per source) with report")
@click.option("--cleanup", is_flag=True, help="Delete test-run facts after report (use with --test-run)")
def main(
    source: Optional[str],
    run_all_flag: bool,
    list_sources: bool,
    dry_run: bool,
    validate: bool,
    test_run: bool,
    cleanup: bool,
):
    """OenoBench UC Davis Scraper — Extract wine facts from UC Davis repositories."""
    os.makedirs("data/logs", exist_ok=True)
    logger.add("data/logs/ucdavis_{time}.log", rotation="10 MB")

    if list_sources:
        click.echo("\nAvailable UC Davis sources:")
        for name, config in SOURCES.items():
            click.echo(f"  {name:15s} — {config['description']}")
            click.echo(f"  {'':15s}   URL: {config['url']}")
        return

    if test_run:
        run_test_run(source_filter=source, cleanup=cleanup)
        return

    if validate:
        # Collect source IDs for all UC Davis sources
        source_ids = []
        for name, config in SOURCES.items():
            sid = ensure_source(
                name=config["name"],
                url=config["url"],
                source_type=config["source_type"],
                tier=config["tier"],
            )
            source_ids.append(sid)
        validate_facts(source_ids)
        return

    if run_all_flag:
        summary = run_all(dry_run=dry_run)
        click.echo("\nSummary:")
        for name, count in summary.items():
            label = "would insert" if dry_run else "inserted"
            click.echo(f"  {name:15s}: {count} facts {label}")
        click.echo(f"  {'TOTAL':15s}: {sum(summary.values())} facts")
        return

    if source:
        count = run_source(source, dry_run=dry_run)
        label = "Would insert" if dry_run else "Inserted"
        click.echo(f"\n{label} {count} facts from '{source}'.")
        return

    click.echo("Use --all to run all sources, or --source <name> for a specific one.")
    click.echo("Use --list to see available sources.")
    click.echo("Use --validate to run quality checks on inserted facts.")
    click.echo("Use --dry-run to parse without inserting.")
    click.echo("Use --test-run to process 5 items per source with a report.")
    click.echo("Use --test-run --cleanup to auto-delete test facts after the report.")


if __name__ == "__main__":
    main()
