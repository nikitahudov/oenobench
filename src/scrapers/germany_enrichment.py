"""
OenoBench — German Wine Enrichment Scraper

Comprehensive German wine reference data covering all 13 Anbaugebiete (wine regions),
VDP classification system, Praedikat levels with Oechsle requirements, grape varieties,
notable Einzellagen (vineyard sites), and unique German wine traditions.

Usage:
    python -m src.scrapers.germany_enrichment --all
    python -m src.scrapers.germany_enrichment --type region
    python -m src.scrapers.germany_enrichment --type vdp
    python -m src.scrapers.germany_enrichment --type praedikat
    python -m src.scrapers.germany_enrichment --type grape
    python -m src.scrapers.germany_enrichment --type vineyard
    python -m src.scrapers.germany_enrichment --type unique
    python -m src.scrapers.germany_enrichment --dry-run
    python -m src.scrapers.germany_enrichment --validate
    python -m src.scrapers.germany_enrichment --test-run
    python -m src.scrapers.germany_enrichment --list
"""

import random
import re
from collections import defaultdict
from typing import Optional

import click
from loguru import logger

from src.utils.facts import (
    ensure_source,
    insert_fact,
    insert_facts_batch,
    get_fact_count,
)

# ─── Configuration ────────────────────────────────────────────────────────────

USER_AGENT = "OenoBench-Research/1.0 (academic wine benchmark)"
TEST_RUN_FACT_LIMIT = 5

SOURCE = {
    "name": "German Wine Reference Database",
    "url": "https://www.germanwines.de",
    "source_type": "reference",
    "tier": "tier_2_authoritative",
    "language": "en",
}


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Regional Database (13 Anbaugebiete)
# ═══════════════════════════════════════════════════════════════════════════════

REGION_DATABASE = [
    {
        "name": "Mosel",
        "climate": "extreme cool continental",
        "soil_types": ["blue Devonian slate", "red slate", "greywacke"],
        "soil_details": "Blue Devonian slate dominates and retains heat on steep slopes, critical for ripening Riesling; some sites feature red slate and greywacke, each producing distinct flavor profiles",
        "elevation_range": "100-350m",
        "vineyard_area_ha": 8600,
        "key_grapes": ["Riesling", "Müller-Thurgau", "Elbling", "Spätburgunder"],
        "riesling_pct": 61,
        "pct_white": 91,
        "production_hl": None,
        "sub_regions": ["Saar", "Ruwer", "Mittelmosel", "Terrassenmosel"],
        "sub_region_details": {
            "Saar": "Cool tributary valley producing steely, high-acid Rieslings with pronounced minerality",
            "Ruwer": "Small tributary producing delicate, ethereal Rieslings with low alcohol",
            "Mittelmosel": "Heart of the region around Bernkastel, Wehlen, Piesport, Ürzig, and Erden with the most famous vineyards",
            "Terrassenmosel": "Lower Mosel with the steepest terraced vineyard slopes in Germany",
        },
        "famous_vineyards": [
            "Wehlener Sonnenuhr", "Bernkasteler Doctor", "Ürziger Würzgarten",
            "Erdener Treppchen", "Erdener Prälat", "Brauneberger Juffer-Sonnenuhr",
            "Scharzhofberger", "Maximin Grünhäuser Abtsberg",
        ],
        "notes": "Steep terraced slate vineyards along the Mosel, Saar, and Ruwer rivers; some slopes reach 65-degree gradients, among the steepest vineyards in the world",
    },
    {
        "name": "Rheingau",
        "climate": "mild continental",
        "soil_types": ["loess", "quartzite", "phyllite", "slate"],
        "soil_details": "South-facing slopes along the Rhine benefit from heat reflection off the river; higher sites have phyllite and slate while lower slopes have deep loess deposits",
        "elevation_range": "80-250m",
        "vineyard_area_ha": 3100,
        "key_grapes": ["Riesling", "Spätburgunder"],
        "riesling_pct": 78,
        "pct_white": 85,
        "production_hl": None,
        "sub_regions": [],
        "sub_region_details": {},
        "famous_vineyards": [
            "Schloss Johannisberg", "Rüdesheimer Berg Schlossberg",
            "Steinberg", "Hochheimer Kirchenstück",
        ],
        "notes": "South-facing slopes of the Rhine near the Taunus mountains; Schloss Johannisberg is considered the birthplace of intentional Spätlese (1775); stronghold of both Charta and VDP organizations",
    },
    {
        "name": "Pfalz",
        "climate": "warmest German region",
        "soil_types": ["sandstone", "limestone", "basalt", "loess", "clay"],
        "soil_details": "Sheltered by the Haardt mountains (northern extension of the Vosges), creating Germany's warmest and driest wine climate; diverse geology from volcanic basalt to sedimentary limestone",
        "elevation_range": "100-300m",
        "vineyard_area_ha": 23600,
        "key_grapes": ["Riesling", "Dornfelder", "Spätburgunder", "Müller-Thurgau", "Grauburgunder"],
        "riesling_pct": None,
        "pct_white": 64,
        "production_hl": None,
        "sub_regions": ["Mittelhaardt", "Südliche Weinstrasse"],
        "sub_region_details": {
            "Mittelhaardt": "Premium northern sub-region with the most celebrated vineyards and estates",
            "Südliche Weinstrasse": "Larger southern sub-region with warmer conditions and higher yields",
        },
        "famous_vineyards": [],
        "notes": "Sheltered by the Haardt mountains, an extension of the Alsatian Vosges; Germany's second-largest wine region by area",
    },
    {
        "name": "Rheinhessen",
        "climate": "moderate continental",
        "soil_types": ["limestone", "marl", "loess", "red slate"],
        "soil_details": "Germany's largest wine region with diverse soils; the Roter Hang (red slope) near Nierstein features iron-rich red slate and Rotliegend sandstone producing premium Riesling with distinctive minerality",
        "elevation_range": "80-300m",
        "vineyard_area_ha": 26700,
        "key_grapes": ["Riesling", "Müller-Thurgau", "Silvaner", "Dornfelder", "Grauburgunder"],
        "riesling_pct": None,
        "pct_white": 71,
        "production_hl": None,
        "sub_regions": ["Roter Hang"],
        "sub_region_details": {
            "Roter Hang": "Red slate slopes near Nierstein, a premium terroir site producing age-worthy Riesling",
        },
        "famous_vineyards": [],
        "notes": "Germany's largest wine region by vineyard area; historically known for Silvaner but increasingly focused on quality Riesling; Roter Hang is its premium terroir",
    },
    {
        "name": "Nahe",
        "climate": "moderate cool continental",
        "soil_types": ["volcanic", "slate", "sandstone", "loess", "quartzite"],
        "soil_details": "Extraordinary soil diversity within a small area, including volcanic porphyry, Devonian slate, sandstone, quartzite, and loess; this variety produces remarkably diverse wine styles",
        "elevation_range": "100-300m",
        "vineyard_area_ha": 4200,
        "key_grapes": ["Riesling", "Müller-Thurgau", "Silvaner", "Grauburgunder"],
        "riesling_pct": None,
        "pct_white": 76,
        "production_hl": None,
        "sub_regions": [],
        "sub_region_details": {},
        "famous_vineyards": [],
        "notes": "Often called the 'school of German wines' because its extraordinary soil diversity produces the full range of German wine styles within a single region",
    },
    {
        "name": "Baden",
        "climate": "warmest, southernmost German region",
        "soil_types": ["volcanic", "limestone", "granite", "loess"],
        "soil_details": "Kaiserstuhl is an extinct volcano with warm basalt and volcanic loess soils; Markgräflerland has limestone suited to Gutedel (Chasselas); Ortenau features decomposed granite for Spätburgunder",
        "elevation_range": "150-500m",
        "vineyard_area_ha": 15800,
        "key_grapes": ["Spätburgunder", "Grauburgunder", "Müller-Thurgau", "Gutedel", "Riesling"],
        "riesling_pct": None,
        "pct_white": 55,
        "production_hl": None,
        "sub_regions": ["Kaiserstuhl", "Markgräflerland", "Ortenau"],
        "sub_region_details": {
            "Kaiserstuhl": "Extinct volcano with warm basalt soils, Germany's hottest vineyard sites",
            "Markgräflerland": "Limestone terroir near the Swiss border, heartland of Gutedel (Chasselas)",
            "Ortenau": "Granite hills producing excellent Spätburgunder (Pinot Noir) and Riesling",
        },
        "famous_vineyards": [],
        "notes": "The only German wine region classified in EU wine zone B (same as Alsace, Champagne, and Loire); Germany's third-largest region",
    },
    {
        "name": "Franken",
        "climate": "continental",
        "soil_types": ["Muschelkalk", "Keuper", "Buntsandstein"],
        "soil_details": "Three distinct geological zones: Muschelkalk (shell limestone) in the center around Würzburg produces the finest Silvaner; Keuper (clay-gypsum) in the east; Buntsandstein (red sandstone) in the west",
        "elevation_range": "150-350m",
        "vineyard_area_ha": 6100,
        "key_grapes": ["Silvaner", "Müller-Thurgau", "Bacchus", "Riesling", "Domina"],
        "riesling_pct": None,
        "pct_white": 81,
        "production_hl": None,
        "sub_regions": [],
        "sub_region_details": {},
        "famous_vineyards": ["Würzburger Stein", "Iphöfer Julius-Echter-Berg"],
        "notes": "Heartland of Silvaner in Germany; wines traditionally bottled in the distinctive flat Bocksbeutel; major towns include Würzburg, Iphofen, and Escherndorf",
    },
    {
        "name": "Württemberg",
        "climate": "moderate continental",
        "soil_types": ["Keuper", "Muschelkalk"],
        "soil_details": "Keuper (clay-gypsum-marl) and Muschelkalk (shell limestone) soils on hillsides along the Neckar River and its tributaries",
        "elevation_range": "200-400m",
        "vineyard_area_ha": 11400,
        "key_grapes": ["Trollinger", "Lemberger", "Schwarzriesling", "Riesling", "Spätburgunder"],
        "riesling_pct": None,
        "pct_white": 30,
        "production_hl": None,
        "sub_regions": [],
        "sub_region_details": {},
        "famous_vineyards": [],
        "notes": "Germany's exception: approximately 70% red wine production, the highest proportion of any German region; Trollinger (Schiava) and Lemberger (Blaufränkisch) are signature varieties; most wine is consumed locally and rarely exported",
    },
    {
        "name": "Ahr",
        "climate": "cool continental with sheltered microclimate",
        "soil_types": ["slate", "greywacke", "basalt"],
        "soil_details": "Steep slate terraces in the narrow Ahr valley trap heat; volcanic basalt and greywacke add diversity; the sheltered valley creates a surprisingly warm microclimate for this northern latitude",
        "elevation_range": "100-300m",
        "vineyard_area_ha": 530,
        "key_grapes": ["Spätburgunder", "Frühburgunder", "Riesling"],
        "riesling_pct": None,
        "pct_white": 16,
        "production_hl": None,
        "sub_regions": [],
        "sub_region_details": {},
        "famous_vineyards": [],
        "notes": "Tiny, northernmost red wine region producing world-class Spätburgunder (Pinot Noir); 84% red wine production; devastated by catastrophic flooding in July 2021, the region is rebuilding its vineyards and cellars",
    },
    {
        "name": "Mittelrhein",
        "climate": "cool continental moderated by the Rhine",
        "soil_types": ["slate", "greywacke", "loess"],
        "soil_details": "Steep slate terraces along the dramatic Rhine Gorge, a UNESCO World Heritage Site; heat reflection from the river aids ripening on the narrow, terraced slopes",
        "elevation_range": "70-250m",
        "vineyard_area_ha": 460,
        "key_grapes": ["Riesling", "Spätburgunder", "Müller-Thurgau"],
        "riesling_pct": None,
        "pct_white": 85,
        "production_hl": None,
        "sub_regions": [],
        "sub_region_details": {},
        "famous_vineyards": [],
        "notes": "Dramatic Rhine Gorge landscape (UNESCO World Heritage Site) with the Loreley rock; primarily a tourism-driven wine region with steep terraced vineyards",
    },
    {
        "name": "Sachsen",
        "climate": "continental",
        "soil_types": ["granite", "gneiss", "loess"],
        "soil_details": "Granite and gneiss bedrock with loess topsoil along the Elbe River valley near Dresden and Meissen; one of the few German regions where Goldriesling is grown",
        "elevation_range": "100-350m",
        "vineyard_area_ha": 500,
        "key_grapes": ["Müller-Thurgau", "Riesling", "Goldriesling", "Weissburgunder"],
        "riesling_pct": None,
        "pct_white": None,
        "production_hl": None,
        "sub_regions": [],
        "sub_region_details": {},
        "famous_vineyards": [],
        "notes": "Germany's easternmost wine region, centered around Dresden and Meissen on the Elbe River; one of the only places in the world that grows the Goldriesling grape variety",
    },
    {
        "name": "Saale-Unstrut",
        "climate": "continental",
        "soil_types": ["Muschelkalk", "Buntsandstein"],
        "soil_details": "Shell limestone (Muschelkalk) and sandstone (Buntsandstein) soils at the confluence of the Saale and Unstrut rivers; terraced vineyards face south to maximize sun exposure at this northern latitude",
        "elevation_range": "100-250m",
        "vineyard_area_ha": 800,
        "key_grapes": ["Müller-Thurgau", "Weissburgunder", "Silvaner", "Riesling"],
        "riesling_pct": None,
        "pct_white": None,
        "production_hl": None,
        "sub_regions": [],
        "sub_region_details": {},
        "famous_vineyards": [],
        "notes": "Germany's northernmost wine region at approximately 51 degrees north latitude; formerly in the DDR (East Germany), the wine industry was revived after reunification in 1990",
    },
    {
        "name": "Hessische Bergstrasse",
        "climate": "mild continental",
        "soil_types": ["loess", "granite"],
        "soil_details": "Deep loess deposits over granite bedrock on west-facing slopes; the Odenwald forest provides shelter from cold eastern winds",
        "elevation_range": "100-300m",
        "vineyard_area_ha": 450,
        "key_grapes": ["Riesling", "Grauburgunder", "Spätburgunder"],
        "riesling_pct": None,
        "pct_white": None,
        "production_hl": None,
        "sub_regions": [],
        "sub_region_details": {},
        "famous_vineyards": [],
        "notes": "One of Germany's smallest wine regions; spring arrives here earlier than almost anywhere else in Germany, earning it the nickname 'Germany's spring garden'",
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — VDP Classification
# ═══════════════════════════════════════════════════════════════════════════════

VDP_CLASSIFICATION = [
    {
        "level": "VDP.GUTSWEIN",
        "english": "Estate Wine",
        "tier_rank": 1,
        "yield_max_hl_ha": 75,
        "description": "Entry-level estate-grown wine showing regional character",
        "details": "Grapes must be estate-grown from the VDP member's own vineyards; reflects the general style and character of the region",
    },
    {
        "level": "VDP.ORTSWEIN",
        "english": "Village Wine",
        "tier_rank": 2,
        "yield_max_hl_ha": 60,
        "description": "Village wine from the best sites within a specific village",
        "details": "Grapes sourced from top vineyard sites within a single village; the village name appears on the label as an expression of local terroir",
    },
    {
        "level": "VDP.ERSTE LAGE",
        "english": "Premier Cru equivalent",
        "tier_rank": 3,
        "yield_max_hl_ha": 50,
        "description": "Classified first-class vineyard sites, Premier Cru equivalent",
        "details": "Vineyards formally classified as first-class sites by the VDP; dry wines from these vineyards are labeled 'VDP.ERSTE LAGE trocken'; stricter viticultural standards apply",
    },
    {
        "level": "VDP.GROSSE LAGE",
        "english": "Grand Cru equivalent",
        "tier_rank": 4,
        "yield_max_hl_ha": 50,
        "description": "Germany's best vineyard sites, Grand Cru equivalent",
        "details": "The pinnacle of the VDP classification; dry wines from these sites are called GG (Grosses Gewächs); sweet Prädikat wines from Grosse Lage sites carry the GL eagle symbol on the label",
    },
]

VDP_GENERAL_FACTS = [
    "The VDP (Verband Deutscher Prädikatsweingüter) classification is modeled on 19th-century Prussian vineyard tax maps that ranked vineyards by quality and economic value.",
    "The VDP has approximately 200 member estates across Germany, each belonging to their respective regional VDP chapter.",
    "GG (Grosses Gewächs) is a dry wine from a VDP.GROSSE LAGE vineyard, released on September 1 of the year following harvest.",
    "The VDP classification system parallels the Burgundian model, with GUTSWEIN as regional, ORTSWEIN as village, ERSTE LAGE as Premier Cru, and GROSSE LAGE as Grand Cru.",
    "VDP member estates are identified by a stylized eagle logo on the capsule of the bottle, with the Grosse Lage eagle being the most prestigious symbol in German wine.",
    "Only VDP member estates may use the VDP classification terms and eagle symbols; non-members cannot label wines as GG or use the Grosse Lage designation.",
]


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Prädikat Levels
# ═══════════════════════════════════════════════════════════════════════════════

PRAEDIKAT_DATABASE = [
    {
        "level": "Kabinett",
        "min_oechsle_range": "67-82",
        "description": "Lightest Prädikat level, typically lower alcohol with refreshing acidity",
        "details": "Minimum must weight varies by region and grape variety (67° Oechsle for Riesling in Mosel, up to 82° in warmer regions); traditionally the benchmark for elegant, off-dry German Riesling",
        "style_notes": "Can be produced in trocken (dry), halbtrocken (off-dry), or fruity sweet styles; Mosel Kabinett at 7-9% alcohol is considered one of the world's most food-friendly wines",
    },
    {
        "level": "Spätlese",
        "min_oechsle_range": "76-90",
        "description": "Late harvest, riper grapes with more body and intensity",
        "details": "Literally 'late harvest'; grapes picked later than normal harvest date for additional ripeness; minimum 76-90° Oechsle depending on region and variety",
        "style_notes": "Increasingly vinified as trocken (dry Spätlese), but off-dry and sweet versions remain classic; the 1775 vintage at Schloss Johannisberg is considered the origin of intentional Spätlese",
    },
    {
        "level": "Auslese",
        "min_oechsle_range": "83-100",
        "description": "Select harvest from individually selected bunches, often with some botrytis",
        "details": "Literally 'selected harvest'; individual bunches are selected for exceptional ripeness, often showing noble rot (botrytis); minimum 83-100° Oechsle",
        "style_notes": "Usually sweet or off-dry; a bridge between the lighter Prädikats and the intensely sweet BA/TBA; Auslese Riesling from top producers can age for decades",
    },
    {
        "level": "Beerenauslese",
        "min_oechsle_range": "110-128",
        "description": "Individually selected botrytized berries producing intensely sweet wine",
        "details": "Literally 'berry selection'; individual berries are selected by hand, each one affected by botrytis cinerea (noble rot); minimum 110-128° Oechsle; only produced in exceptional vintages",
        "style_notes": "Rare dessert wine with intense sweetness balanced by bracing acidity; deep gold color with flavors of dried apricot, honey, and tropical fruit; can age for 50+ years",
    },
    {
        "level": "Trockenbeerenauslese",
        "min_oechsle_range": "150-154",
        "description": "Individually selected shriveled botrytized berries; rarest and sweetest Prädikat",
        "details": "Literally 'dry berry selection'; berries are individually selected in a shriveled, raisin-like state with extreme botrytis concentration; minimum 150-154° Oechsle; among the rarest and most expensive wines in the world",
        "style_notes": "Extraordinarily concentrated sweetness (often 200+ g/L residual sugar) balanced by electric acidity; produced in minute quantities only in the finest vintages; can age for over a century",
    },
    {
        "level": "Eiswein",
        "min_oechsle_range": "110-128",
        "description": "Grapes frozen naturally on the vine, harvested at minimum -7 degrees Celsius",
        "details": "Must weight requirement is the same as Beerenauslese (110-128° Oechsle), but grapes must be healthy (not botrytized) and frozen naturally on the vine; harvested at a minimum temperature of -7 degrees Celsius, typically in December or January",
        "style_notes": "Intense concentration of both sugar and acidity from the freeze concentration process; distinctly pure fruit character without botrytis complexity; increasingly rare due to climate change making reliable freezes less common",
    },
]

PRAEDIKAT_GENERAL_FACTS = [
    "The German Prädikat system classifies wines by the ripeness level of the grapes at harvest, measured in degrees Oechsle (a scale of must weight).",
    "Oechsle requirements for each Prädikat level vary by grape variety and wine region, with cooler regions like Mosel having lower minimums than warmer regions like Baden.",
    "Prädikatswein is the highest quality category in German wine law, above Qualitätswein (QbA), Landwein, and Deutscher Wein.",
    "The Oechsle scale was invented by the German goldsmith and pharmacist Ferdinand Oechsle in the early 19th century and measures the density of grape must relative to water.",
]


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Grape Varieties
# ═══════════════════════════════════════════════════════════════════════════════

GRAPE_VARIETY_DATABASE = [
    {
        "name": "Riesling",
        "color": "white",
        "area_ha": 23800,
        "pct_total": 23,
        "origin": "Rhine region of Germany",
        "key_regions": ["Mosel", "Rheingau", "Pfalz", "Nahe", "Rheinhessen"],
        "regional_styles": {
            "Mosel": "Slate-influenced, delicate, mineral, often lower alcohol with pronounced acidity",
            "Rheingau": "Structured, classic, age-worthy with a firm backbone",
            "Pfalz": "Ripe, generous, fuller-bodied with stone fruit character",
            "Nahe": "Diverse styles reflecting the region's extraordinary soil variety",
            "Franken": "Earthy, dry, mineral character distinct from Rhine Riesling",
        },
        "notes": "Germany's most important grape variety and the most widely planted Riesling in the world; capable of producing wines in every style from bone-dry to intensely sweet TBA",
    },
    {
        "name": "Müller-Thurgau",
        "color": "white",
        "area_ha": 11300,
        "pct_total": 11,
        "origin": "Created in 1882 by Hermann Müller from Thurgau, Switzerland",
        "key_regions": ["Rheinhessen", "Baden", "Franken", "Pfalz"],
        "regional_styles": {},
        "notes": "Once Germany's most planted variety, now in decline; produces easy-drinking, lightly aromatic wines; a crossing of Riesling and Madeleine Royale (not Silvaner as long believed)",
    },
    {
        "name": "Spätburgunder",
        "color": "red",
        "area_ha": 11800,
        "pct_total": 12,
        "origin": "Burgundy, France (Pinot Noir)",
        "key_regions": ["Ahr", "Baden", "Pfalz", "Rheingau"],
        "regional_styles": {
            "Ahr": "Elegant, complex, world-class with slate minerality",
            "Baden": "Richer, fuller-bodied with Kaiserstuhl warmth",
            "Pfalz": "Ripe, fruit-forward, increasingly Burgundian in style",
            "Rheingau": "Structured, fine, earthy character from Assmannshausen",
        },
        "notes": "Known internationally as Pinot Noir; Germany is the world's third-largest producer after France and the USA; quality has improved dramatically since the 1990s (the Spätburgunder quality revolution)",
    },
    {
        "name": "Grauburgunder",
        "color": "white",
        "area_ha": 7000,
        "pct_total": None,
        "origin": "Burgundy, France (Pinot Gris)",
        "key_regions": ["Baden", "Pfalz", "Rheinhessen"],
        "regional_styles": {},
        "notes": "Known internationally as Pinot Gris (or Pinot Grigio); produces rich, full-bodied dry whites; rapidly increasing in plantings across Germany",
    },
    {
        "name": "Weissburgunder",
        "color": "white",
        "area_ha": 5500,
        "pct_total": None,
        "origin": "Burgundy, France (Pinot Blanc)",
        "key_regions": ["Baden", "Pfalz", "Rheinhessen"],
        "regional_styles": {},
        "notes": "Known internationally as Pinot Blanc; produces crisp, neutral dry whites with good acidity; popular as a food wine and increasingly used for Sekt production",
    },
    {
        "name": "Silvaner",
        "color": "white",
        "area_ha": 4800,
        "pct_total": None,
        "origin": "Austria (likely Traminer x Österreichisch Weiss crossing)",
        "key_regions": ["Franken", "Rheinhessen"],
        "regional_styles": {
            "Franken": "Mineral, earthy, structured dry wines on Muschelkalk, the benchmark expression",
            "Rheinhessen": "Softer, rounder, often from old-vine plantings on limestone",
        },
        "notes": "Heartland grape of Franken where it reaches its finest expression on shell limestone (Muschelkalk) soils; once the most planted grape in Germany before being overtaken by Müller-Thurgau and then Riesling",
    },
    {
        "name": "Dornfelder",
        "color": "red",
        "area_ha": 7200,
        "pct_total": None,
        "origin": "Created in 1955 at Weinsberg, a crossing of Helfensteiner and Heroldrebe",
        "key_regions": ["Pfalz", "Rheinhessen", "Württemberg"],
        "regional_styles": {},
        "notes": "Germany's second most planted red variety; bred for deep color and fruity character; a modern crossing that has become commercially very successful; can be made in both simple fruity and more serious oak-aged styles",
    },
    {
        "name": "Lemberger",
        "color": "red",
        "area_ha": 1800,
        "pct_total": None,
        "origin": "Central Europe (known as Blaufränkisch in Austria and Hungary)",
        "key_regions": ["Württemberg"],
        "regional_styles": {},
        "notes": "Known as Blaufränkisch in Austria; grown almost exclusively in Württemberg; produces structured, deeply colored red wines with dark fruit and spice; increasingly gaining recognition for serious, age-worthy bottlings",
    },
    {
        "name": "Trollinger",
        "color": "red",
        "area_ha": 2200,
        "pct_total": None,
        "origin": "South Tyrol (identical to Schiava/Vernatsch)",
        "key_regions": ["Württemberg"],
        "regional_styles": {},
        "notes": "Known as Schiava in Italy; grown almost exclusively in Württemberg where it is the most popular local red; produces light, fruity reds meant for everyday drinking; deeply rooted in Swabian culture and consumed almost entirely locally",
    },
    {
        "name": "Schwarzriesling",
        "color": "red",
        "area_ha": 2100,
        "pct_total": None,
        "origin": "Burgundy, France (identical to Pinot Meunier)",
        "key_regions": ["Württemberg"],
        "regional_styles": {},
        "notes": "Known internationally as Pinot Meunier; in Germany grown primarily in Württemberg; produces soft, fruity red wines; despite its name ('Black Riesling'), it is unrelated to Riesling and is a member of the Pinot family",
    },
    {
        "name": "Gewürztraminer",
        "color": "white",
        "area_ha": 1000,
        "pct_total": None,
        "origin": "South Tyrol (aromatic mutation of Traminer)",
        "key_regions": ["Pfalz", "Baden", "Rheinhessen"],
        "regional_styles": {},
        "notes": "Intensely aromatic variety with lychee, rose petal, and spice characteristics; German versions tend to be lighter and drier than their Alsatian counterparts",
    },
    {
        "name": "Scheurebe",
        "color": "white",
        "area_ha": 1400,
        "pct_total": None,
        "origin": "Created in 1916 by Georg Scheu, a crossing of Silvaner and Riesling",
        "key_regions": ["Pfalz", "Rheinhessen"],
        "regional_styles": {},
        "notes": "A Silvaner x Riesling crossing known for its distinctive grapefruit and blackcurrant leaf aroma; produces excellent Prädikat-level sweet wines; plantings are declining but the variety has a devoted following among connoisseurs",
    },
    {
        "name": "Kerner",
        "color": "white",
        "area_ha": 2500,
        "pct_total": None,
        "origin": "Created in 1929 at Weinsberg, a crossing of Trollinger (red) and Riesling (white)",
        "key_regions": ["Württemberg", "Pfalz", "Rheinhessen"],
        "regional_styles": {},
        "notes": "A Trollinger x Riesling crossing named after the Swabian poet Justinus Kerner; produces Riesling-like wines with slightly less acidity and more body; particularly successful in sites too cool for Riesling",
    },
    {
        "name": "Gutedel",
        "color": "white",
        "area_ha": 1000,
        "pct_total": None,
        "origin": "Ancient variety, likely originating in the Middle East (identical to Chasselas)",
        "key_regions": ["Baden"],
        "regional_styles": {
            "Markgräflerland": "Light, neutral, delicate dry wines that are a specialty of this sub-region bordering Switzerland",
        },
        "notes": "Known internationally as Chasselas (or Fendant in Switzerland); in Germany grown almost exclusively in the Markgräflerland district of Baden, near the Swiss border where Chasselas is also important",
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Notable Einzellagen (Vineyard Sites)
# ═══════════════════════════════════════════════════════════════════════════════

NOTABLE_VINEYARDS = [
    # Mosel
    {
        "name": "Wehlener Sonnenuhr",
        "region": "Mosel",
        "sub_region": "Mittelmosel",
        "soil": "blue Devonian slate",
        "grape": "Riesling",
        "notes": "Named after the sundial (Sonnenuhr) on the steep slope; south-facing blue slate vineyard above the village of Wehlen producing some of Germany's most elegant Rieslings",
    },
    {
        "name": "Bernkasteler Doctor",
        "region": "Mosel",
        "sub_region": "Mittelmosel",
        "soil": "Devonian slate with scattered quartzite",
        "grape": "Riesling",
        "notes": "One of Germany's most famous and expensive vineyards; the name derives from a legend that Archbishop Boemund II of Trier was cured of illness by wine from this vineyard",
    },
    {
        "name": "Ürziger Würzgarten",
        "region": "Mosel",
        "sub_region": "Mittelmosel",
        "soil": "red slate and volcanic soil",
        "grape": "Riesling",
        "notes": "The 'Spice Garden' of Ürzig; distinctive red Devon slate and decomposed volcanic rock impart a spicy, exotic character unique among Mosel wines",
    },
    {
        "name": "Erdener Treppchen",
        "region": "Mosel",
        "sub_region": "Mittelmosel",
        "soil": "red Devonian slate",
        "grape": "Riesling",
        "notes": "The 'Little Staircase' of Erden; red slate terraces producing rich, full-bodied Mosel Riesling with spicy red-fruit aromatics",
    },
    {
        "name": "Erdener Prälat",
        "region": "Mosel",
        "sub_region": "Mittelmosel",
        "soil": "volcanic and slate",
        "grape": "Riesling",
        "notes": "Tiny, sheltered vineyard within Erden producing the richest wines of the village; the warmest microclimate on the Mittelmosel, favorably exposed to afternoon sun",
    },
    {
        "name": "Brauneberger Juffer-Sonnenuhr",
        "region": "Mosel",
        "sub_region": "Mittelmosel",
        "soil": "blue Devonian slate",
        "grape": "Riesling",
        "notes": "Premier site within the larger Juffer vineyard at Brauneberg; the steep, south-facing blue slate slope catches maximum sunlight",
    },
    {
        "name": "Scharzhofberger",
        "region": "Mosel",
        "sub_region": "Saar",
        "soil": "blue-grey Devonian slate",
        "grape": "Riesling",
        "notes": "The premier vineyard of the Saar; produces steely, high-acid Riesling with extraordinary aging potential; most closely associated with the Egon Müller estate, whose TBA bottlings are among the world's most expensive wines",
    },
    {
        "name": "Maximin Grünhäuser Abtsberg",
        "region": "Mosel",
        "sub_region": "Ruwer",
        "soil": "blue Devonian slate",
        "grape": "Riesling",
        "notes": "Historic vineyard on the Ruwer owned by the von Schubert family since 1882; produces ethereal, delicate Rieslings from steep slate slopes; one of three classified vineyards at Grünhaus (Abtsberg, Herrenberg, Bruderberg)",
    },
    # Rheingau
    {
        "name": "Schloss Johannisberg",
        "region": "Rheingau",
        "sub_region": None,
        "soil": "loess and quartzite",
        "grape": "Riesling",
        "notes": "Considered the birthplace of intentional Spätlese in 1775, when the courier carrying harvest permission from the Prince-Bishop of Fulda arrived late and the grapes had developed noble rot; the estate has been producing Riesling since at least 1720",
    },
    {
        "name": "Rüdesheimer Berg Schlossberg",
        "region": "Rheingau",
        "sub_region": None,
        "soil": "slate and quartzite",
        "grape": "Riesling",
        "notes": "Steep, south-facing slope above Rüdesheim at the western end of the Rheingau; one of the warmest sites in the region, producing powerful, concentrated Riesling",
    },
    {
        "name": "Steinberg",
        "region": "Rheingau",
        "sub_region": None,
        "soil": "phyllite and loess",
        "grape": "Riesling",
        "notes": "Walled vineyard (Clos) belonging to Kloster Eberbach, the former Cistercian monastery; one of the oldest documented German vineyards, with records dating to the 12th century",
    },
    {
        "name": "Hochheimer Kirchenstück",
        "region": "Rheingau",
        "sub_region": None,
        "soil": "deep loess over limestone",
        "grape": "Riesling",
        "notes": "Premier vineyard in Hochheim, a town whose name is the origin of the English word 'hock' (used to describe all Rhine wines); Queen Victoria visited and the vineyard was renamed in her honor in the 19th century",
    },
    # Franken
    {
        "name": "Würzburger Stein",
        "region": "Franken",
        "sub_region": None,
        "soil": "Muschelkalk (shell limestone)",
        "grape": "Silvaner",
        "notes": "Germany's most famous Silvaner vineyard; steep south-facing limestone slope above the Main River in Würzburg; the name 'Stein' is the origin of the term 'Steinwein' historically used for all Franken wines",
    },
    {
        "name": "Iphöfer Julius-Echter-Berg",
        "region": "Franken",
        "sub_region": None,
        "soil": "Keuper (clay-gypsum)",
        "grape": "Silvaner",
        "notes": "Named after Prince-Bishop Julius Echter von Mespelbrunn; steep Keuper slopes near Iphofen producing powerful, age-worthy Silvaner and Riesling",
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Unique German Wine Facts
# ═══════════════════════════════════════════════════════════════════════════════

UNIQUE_FACTS_DATABASE = [
    # Sekt (sparkling wine)
    {
        "category": "sekt",
        "facts": [
            "Sekt is the German term for sparkling wine; Germany is one of the world's largest sparkling wine markets.",
            "Winzersekt is estate-produced German sparkling wine made by the traditional method (Flaschengärung nach dem Traditionellen Verfahren), similar to Champagne.",
            "German Sekt b.A. (bestimmter Anbaugebiete) is quality sparkling wine produced from grapes of a single specified wine region.",
            "Germany produces approximately 400 million bottles of Sekt annually, making it the world's largest sparkling wine market per capita.",
            "Riesling Sekt, particularly from the Mosel, Rheingau, and Pfalz, is considered the finest expression of German sparkling wine.",
        ],
    },
    # Sweetness designations
    {
        "category": "sweetness",
        "facts": [
            "Trocken (dry) on a German wine label indicates a maximum residual sugar of 9 grams per liter.",
            "Halbtrocken (off-dry or semi-dry) on a German wine label indicates a maximum residual sugar of 18 grams per liter.",
            "Feinherb is an unofficial but widely used German wine term indicating an off-dry style, roughly equivalent to halbtrocken but with no legally defined sugar limit.",
            "The shift toward trocken (dry) wines in Germany accelerated from the 1980s onward, and today the majority of German wine produced is classified as dry.",
        ],
    },
    # History
    {
        "category": "history",
        "facts": [
            "In 1775, the courier carrying harvest permission for Schloss Johannisberg from the Prince-Bishop of Fulda arrived late, and the overripe, botrytis-affected grapes produced a legendary sweet wine, establishing intentional Spätlese production.",
            "The Charta organization was founded in 1984 by Rheingau producers to promote dry, food-friendly Riesling as an alternative to the sweet wines that dominated German exports.",
            "German wine law was reformed in 1971, replacing the Prussian-era quality system based on vineyard classification with the current system based primarily on must weight (Oechsle).",
            "The Bernkasteler Doctor vineyard in the Mosel was the subject of a famous legal dispute in the 1970s over its boundaries, which the German Federal Court ultimately resolved by reducing the vineyard from 3.26 to 3.26 hectares.",
        ],
    },
    # Steep slope viticulture
    {
        "category": "viticulture",
        "facts": [
            "Steillagenweinbau (steep slope viticulture) is a defining feature of German wine regions like the Mosel, Mittelrhein, and Ahr, with some slopes reaching gradients of up to 65 degrees.",
            "Vineyards on the Mosel with slopes exceeding 30 degrees gradient are classified as Steillage (steep site) and are almost impossible to work by machine, requiring manual labor for all viticultural tasks.",
            "The steep slate terraces of the Mosel were originally constructed by the Romans approximately 2,000 years ago and have been continuously cultivated since.",
            "Germany's steep-slope vineyards are under economic threat because manual cultivation costs up to ten times more per hectare than mechanized flat-site viticulture.",
            "Climate change is significantly impacting German viticulture: average growing season temperatures have risen, enabling fuller ripeness for Riesling and driving a Spätburgunder quality revolution, but threatening Eiswein production.",
        ],
    },
    # Wine law and quality tiers
    {
        "category": "wine_law",
        "facts": [
            "German wine quality categories in ascending order are: Deutscher Wein (table wine), Landwein (country wine with regional indication), Qualitätswein bestimmter Anbaugebiete (QbA, quality wine from a specified region), and Prädikatswein (top-quality wine with must weight classification).",
            "Qualitätswein (QbA) may be chaptalised (sugar added before fermentation to increase alcohol), while Prädikatswein may not be chaptalised.",
            "Germany's 13 Anbaugebiete (specified wine regions) are the geographic basis for the QbA and Prädikatswein quality classifications.",
            "An Einzellage is a single vineyard site in German wine law; a Grosslage is a collective vineyard grouping of multiple Einzellagen, which critics argue is misleading to consumers.",
            "The AP number (Amtliche Prüfungsnummer) is a quality control number on every bottle of German Qualitätswein and Prädikatswein, certifying that the wine passed analytical testing and a tasting panel evaluation.",
        ],
    },
    # Bocksbeutel
    {
        "category": "bocksbeutel",
        "facts": [
            "The Bocksbeutel is a distinctive flattened, elliptical bottle traditionally used for Franken wines, legally protected under EU law for use by Franken and a few other specified regions.",
            "The Bocksbeutel has been used in Franken since at least 1728, when the Bürgerspital zum Heiligen Geist in Würzburg began bottling wine in this distinctive flask to distinguish genuine Steinwein from counterfeits.",
        ],
    },
    # Notable estates and producers
    {
        "category": "producers",
        "facts": [
            "Egon Müller - Scharzhof in the Saar is one of the world's most celebrated wine estates, whose Scharzhofberger TBA is among the most expensive wines produced anywhere.",
            "Joh. Jos. Prüm in the Mosel is renowned for its Wehlener Sonnenuhr Riesling, with a distinctive style favoring restrained, off-dry wines with extraordinary aging potential.",
            "Schloss Johannisberg in the Rheingau is one of the world's oldest Riesling estates, with documented plantings dating to at least 1720 and the legendary 1775 Spätlese discovery.",
            "The Bürgerspital zum Heiligen Geist, Juliusspital, and Staatlicher Hofkeller are three historic charitable estates in Würzburg, Franken, each owning significant vineyard holdings and operating hospitals or social services funded by wine sales.",
        ],
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER
# ═══════════════════════════════════════════════════════════════════════════════


def _make_fact(
    fact_text: str,
    domain: str,
    source_id: str,
    subdomain: str = None,
    entities: list[dict] = None,
    confidence: float = 1.0,
    tags: list[str] = None,
) -> dict:
    """Create a fact dict in the standard format."""
    return {
        "fact_text": fact_text,
        "domain": domain,
        "source_id": source_id,
        "subdomain": subdomain,
        "entities": entities or [],
        "confidence": confidence,
        "tags": tags or [],
    }


# ═══════════════════════════════════════════════════════════════════════════════
# FACT BUILDERS — Regional
# ═══════════════════════════════════════════════════════════════════════════════


def _build_regional_facts(source_id: str) -> list[dict]:
    """Build facts about the 13 German Anbaugebiete (wine regions)."""
    facts = []

    for region in REGION_DATABASE:
        name = region["name"]
        entities = [{"type": "region", "name": name}]
        base_tags = ["germany", name.lower().replace(" ", "_").replace("ü", "ue").replace("ä", "ae")]

        # Climate
        facts.append(_make_fact(
            f"The {name} wine region in Germany has a {region['climate']} climate.",
            domain="wine_regions",
            source_id=source_id,
            subdomain="germany_regions",
            entities=entities,
            tags=base_tags + ["climate"],
        ))

        # Soil types
        if region.get("soil_types"):
            soil_list = ", ".join(region["soil_types"])
            facts.append(_make_fact(
                f"The predominant soil types in Germany's {name} wine region include {soil_list}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="germany_terroir",
                entities=entities,
                tags=base_tags + ["soil", "terroir"],
            ))

        # Soil details
        if region.get("soil_details"):
            facts.append(_make_fact(
                f"{region['soil_details']}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="germany_terroir",
                entities=entities,
                tags=base_tags + ["soil", "terroir"],
            ))

        # Elevation
        if region.get("elevation_range"):
            facts.append(_make_fact(
                f"Vineyards in Germany's {name} wine region are planted at elevations ranging from {region['elevation_range']}.",
                domain="viticulture",
                source_id=source_id,
                subdomain="terrain",
                entities=entities,
                tags=base_tags + ["elevation"],
            ))

        # Vineyard area
        if region.get("vineyard_area_ha"):
            facts.append(_make_fact(
                f"The {name} wine region in Germany has approximately {region['vineyard_area_ha']:,} hectares under vine.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="germany_statistics",
                entities=entities,
                confidence=0.95,
                tags=base_tags + ["statistics"],
            ))

        # Key grapes
        if region.get("key_grapes"):
            grapes_str = ", ".join(region["key_grapes"])
            grape_entities = entities + [{"type": "grape", "name": g} for g in region["key_grapes"]]
            facts.append(_make_fact(
                f"The principal grape varieties of Germany's {name} wine region include {grapes_str}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="germany_grapes",
                entities=grape_entities,
                tags=base_tags + ["grapes"],
            ))

        # Riesling percentage
        if region.get("riesling_pct"):
            facts.append(_make_fact(
                f"Riesling accounts for approximately {region['riesling_pct']}% of vineyard plantings in Germany's {name} wine region.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="germany_grapes",
                entities=entities + [{"type": "grape", "name": "Riesling"}],
                confidence=0.95,
                tags=base_tags + ["riesling", "statistics"],
            ))

        # White/red percentage
        if region.get("pct_white") is not None:
            pct_red = 100 - region["pct_white"]
            facts.append(_make_fact(
                f"Germany's {name} wine region produces approximately {region['pct_white']}% white wine and {pct_red}% red wine.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="germany_statistics",
                entities=entities,
                confidence=0.95,
                tags=base_tags + ["statistics"],
            ))

        # Sub-regions
        if region.get("sub_regions"):
            sub_list = ", ".join(region["sub_regions"])
            facts.append(_make_fact(
                f"The {name} wine region in Germany includes the sub-regions {sub_list}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="germany_regions",
                entities=entities,
                tags=base_tags + ["sub_regions"],
            ))

        # Sub-region details
        for sub_name, detail in region.get("sub_region_details", {}).items():
            facts.append(_make_fact(
                f"{sub_name} in Germany's {name} region: {detail}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="germany_regions",
                entities=entities + [{"type": "sub_region", "name": sub_name}],
                tags=base_tags + ["sub_regions", sub_name.lower().replace(" ", "_")],
            ))

        # Famous vineyards (regional context)
        if region.get("famous_vineyards"):
            vy_list = ", ".join(region["famous_vineyards"])
            facts.append(_make_fact(
                f"Famous vineyard sites (Einzellagen) in Germany's {name} region include {vy_list}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="germany_vineyards",
                entities=entities + [{"type": "vineyard", "name": v} for v in region["famous_vineyards"]],
                tags=base_tags + ["einzellagen", "vineyards"],
            ))

        # Notes
        if region.get("notes"):
            facts.append(_make_fact(
                f"{region['notes']}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="germany_regions",
                entities=entities,
                tags=base_tags,
            ))

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# FACT BUILDERS — VDP Classification
# ═══════════════════════════════════════════════════════════════════════════════


def _build_vdp_facts(source_id: str) -> list[dict]:
    """Build facts about the VDP classification system."""
    facts = []
    base_tags = ["germany", "vdp", "classification"]

    for tier in VDP_CLASSIFICATION:
        level = tier["level"]
        entities = [{"type": "classification", "name": level}]

        # Basic description
        facts.append(_make_fact(
            f"{level} is the {tier['english'].lower()} tier in the VDP classification, Germany's vineyard-based quality hierarchy.",
            domain="wine_regions",
            source_id=source_id,
            subdomain="germany_classification",
            entities=entities,
            tags=base_tags + [level.lower().replace(".", "_").replace(" ", "_")],
        ))

        # Yield limit
        facts.append(_make_fact(
            f"The maximum permitted yield for {level} wines is {tier['yield_max_hl_ha']} hl/ha.",
            domain="viticulture",
            source_id=source_id,
            subdomain="germany_classification",
            entities=entities,
            tags=base_tags + ["yield"],
        ))

        # Details
        facts.append(_make_fact(
            f"{tier['details']}.",
            domain="wine_regions",
            source_id=source_id,
            subdomain="germany_classification",
            entities=entities,
            tags=base_tags,
        ))

    # General VDP facts
    for fact_text in VDP_GENERAL_FACTS:
        facts.append(_make_fact(
            fact_text,
            domain="wine_regions",
            source_id=source_id,
            subdomain="germany_classification",
            entities=[{"type": "organization", "name": "VDP"}],
            tags=base_tags,
        ))

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# FACT BUILDERS — Prädikat Levels
# ═══════════════════════════════════════════════════════════════════════════════


def _build_praedikat_facts(source_id: str) -> list[dict]:
    """Build facts about the German Prädikat classification levels."""
    facts = []
    base_tags = ["germany", "praedikat", "classification"]

    for prad in PRAEDIKAT_DATABASE:
        level = prad["level"]
        entities = [{"type": "classification", "name": level}]

        # Basic with Oechsle
        facts.append(_make_fact(
            f"{level} is a German Prädikat level requiring a minimum must weight of {prad['min_oechsle_range']} degrees Oechsle, varying by region and grape variety.",
            domain="winemaking",
            source_id=source_id,
            subdomain="germany_praedikat",
            entities=entities,
            tags=base_tags + [level.lower()],
        ))

        # Description
        facts.append(_make_fact(
            f"{prad['description']}.",
            domain="winemaking",
            source_id=source_id,
            subdomain="germany_praedikat",
            entities=entities,
            tags=base_tags + [level.lower()],
        ))

        # Details
        facts.append(_make_fact(
            f"{prad['details']}.",
            domain="winemaking",
            source_id=source_id,
            subdomain="germany_praedikat",
            entities=entities,
            tags=base_tags + [level.lower()],
        ))

        # Style notes
        if prad.get("style_notes"):
            facts.append(_make_fact(
                f"{prad['style_notes']}.",
                domain="winemaking",
                source_id=source_id,
                subdomain="germany_praedikat",
                entities=entities,
                tags=base_tags + [level.lower(), "style"],
            ))

    # General Prädikat facts
    for fact_text in PRAEDIKAT_GENERAL_FACTS:
        facts.append(_make_fact(
            fact_text,
            domain="winemaking",
            source_id=source_id,
            subdomain="germany_praedikat",
            entities=[{"type": "classification", "name": "Prädikat"}],
            tags=base_tags,
        ))

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# FACT BUILDERS — Grape Varieties
# ═══════════════════════════════════════════════════════════════════════════════


def _build_grape_variety_facts(source_id: str) -> list[dict]:
    """Build facts about German grape varieties."""
    facts = []
    base_tags = ["germany", "grapes"]

    for grape in GRAPE_VARIETY_DATABASE:
        name = grape["name"]
        entities = [{"type": "grape", "name": name}]
        grape_tags = base_tags + [name.lower().replace(" ", "_").replace("ü", "ue").replace("ä", "ae")]

        # Planting area
        if grape.get("area_ha"):
            facts.append(_make_fact(
                f"{name} is planted on approximately {grape['area_ha']:,} hectares in Germany{', representing about ' + str(grape['pct_total']) + '% of total plantings' if grape.get('pct_total') else ''}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="germany_grapes",
                entities=entities,
                confidence=0.95,
                tags=grape_tags + ["statistics"],
            ))

        # Color
        facts.append(_make_fact(
            f"{name} is a {grape['color']} grape variety cultivated in Germany.",
            domain="grape_varieties",
            source_id=source_id,
            subdomain="germany_grapes",
            entities=entities,
            tags=grape_tags,
        ))

        # Origin
        if grape.get("origin"):
            facts.append(_make_fact(
                f"The origin of {name} is {grape['origin']}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="germany_grapes",
                entities=entities,
                tags=grape_tags + ["origin"],
            ))

        # Key regions
        if grape.get("key_regions"):
            regions_str = ", ".join(grape["key_regions"])
            region_entities = entities + [{"type": "region", "name": r} for r in grape["key_regions"]]
            facts.append(_make_fact(
                f"The key German wine regions for {name} include {regions_str}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="germany_grapes",
                entities=region_entities,
                tags=grape_tags + ["regions"],
            ))

        # Regional styles
        for reg, style in grape.get("regional_styles", {}).items():
            facts.append(_make_fact(
                f"{name} from Germany's {reg} region: {style}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="germany_grapes",
                entities=entities + [{"type": "region", "name": reg}],
                tags=grape_tags + [reg.lower()],
            ))

        # Notes
        if grape.get("notes"):
            facts.append(_make_fact(
                f"{grape['notes']}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="germany_grapes",
                entities=entities,
                tags=grape_tags,
            ))

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# FACT BUILDERS — Notable Einzellagen (Vineyards)
# ═══════════════════════════════════════════════════════════════════════════════


def _build_vineyard_facts(source_id: str) -> list[dict]:
    """Build facts about notable German Einzellagen (vineyard sites)."""
    facts = []
    base_tags = ["germany", "einzellagen", "vineyards"]

    for vy in NOTABLE_VINEYARDS:
        name = vy["name"]
        region = vy["region"]
        entities = [
            {"type": "vineyard", "name": name},
            {"type": "region", "name": region},
        ]
        vy_tags = base_tags + [region.lower()]

        # Location and region
        sub_str = f" in the {vy['sub_region']} sub-region" if vy.get("sub_region") else ""
        facts.append(_make_fact(
            f"{name} is a renowned Einzellage (single vineyard site) in Germany's {region} wine region{sub_str}.",
            domain="wine_regions",
            source_id=source_id,
            subdomain="germany_vineyards",
            entities=entities,
            tags=vy_tags,
        ))

        # Soil
        if vy.get("soil"):
            facts.append(_make_fact(
                f"The {name} vineyard in Germany's {region} region has {vy['soil']} soils.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="germany_vineyards",
                entities=entities,
                tags=vy_tags + ["soil", "terroir"],
            ))

        # Primary grape
        if vy.get("grape"):
            facts.append(_make_fact(
                f"The primary grape variety grown at {name} in Germany's {region} region is {vy['grape']}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="germany_vineyards",
                entities=entities + [{"type": "grape", "name": vy["grape"]}],
                tags=vy_tags + [vy["grape"].lower()],
            ))

        # Notes / historical details
        if vy.get("notes"):
            facts.append(_make_fact(
                f"{vy['notes']}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="germany_vineyards",
                entities=entities,
                tags=vy_tags,
            ))

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# FACT BUILDERS — Unique German Wine Facts
# ═══════════════════════════════════════════════════════════════════════════════


def _build_unique_facts(source_id: str) -> list[dict]:
    """Build facts about unique German wine traditions, history, and culture."""
    facts = []

    domain_map = {
        "sekt": ("winemaking", "germany_sekt"),
        "sweetness": ("winemaking", "germany_classification"),
        "history": ("wine_regions", "germany_history"),
        "viticulture": ("viticulture", "germany_viticulture"),
        "wine_law": ("wine_regions", "germany_classification"),
        "bocksbeutel": ("wine_regions", "germany_traditions"),
        "producers": ("producers", "germany_producers"),
    }

    for category_data in UNIQUE_FACTS_DATABASE:
        cat = category_data["category"]
        domain, subdomain = domain_map.get(cat, ("wine_regions", "germany_other"))
        base_tags = ["germany", cat]

        for fact_text in category_data["facts"]:
            facts.append(_make_fact(
                fact_text,
                domain=domain,
                source_id=source_id,
                subdomain=subdomain,
                entities=[],
                tags=base_tags,
            ))

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# PIPELINE
# ═══════════════════════════════════════════════════════════════════════════════


def _get_source_id() -> str:
    """Register and return the source ID."""
    return ensure_source(
        name=SOURCE["name"],
        url=SOURCE["url"],
        source_type=SOURCE["source_type"],
        tier=SOURCE["tier"],
        language=SOURCE["language"],
    )


def _build_all_facts(source_id: str, data_type: str = None) -> list[dict]:
    """Build all facts, optionally filtered by type."""
    all_facts = []

    builders = {
        "region": _build_regional_facts,
        "vdp": _build_vdp_facts,
        "praedikat": _build_praedikat_facts,
        "grape": _build_grape_variety_facts,
        "vineyard": _build_vineyard_facts,
        "unique": _build_unique_facts,
    }

    if data_type and data_type in builders:
        all_facts = builders[data_type](source_id)
    else:
        for builder in builders.values():
            all_facts.extend(builder(source_id))

    # Deduplicate within run
    seen = set()
    unique = []
    for f in all_facts:
        if f["fact_text"] not in seen:
            seen.add(f["fact_text"])
            unique.append(f)

    return unique


def run_all(dry_run: bool = False, data_type: str = None) -> dict:
    """Build and insert all facts. Returns summary dict."""
    source_id = _get_source_id()
    facts = _build_all_facts(source_id, data_type=data_type)

    summary = {
        "total_generated": len(facts),
        "total_inserted": 0,
    }

    if dry_run:
        click.echo(f"\n[DRY RUN] Would insert {len(facts)} facts from German Wine Reference Database")

        # Show breakdown by domain/subdomain
        domain_counts = defaultdict(int)
        for f in facts:
            domain_counts[f["domain"]] += 1
        click.echo("\nDomain breakdown:")
        for d, c in sorted(domain_counts.items()):
            click.echo(f"  {d:25s}: {c}")

        # Show samples
        click.echo(f"\nSample facts ({min(15, len(facts))} random):")
        for i, f in enumerate(random.sample(facts, min(15, len(facts))), 1):
            click.echo(f'  {i:2d}. "{f["fact_text"]}"')

        return summary

    inserted = insert_facts_batch(facts)
    summary["total_inserted"] = inserted

    logger.info(f"Inserted {inserted} new facts from German Wine Reference Database (duplicates skipped)")
    logger.info(f"Total facts in database: {get_fact_count()}")

    return summary


# ═══════════════════════════════════════════════════════════════════════════════
# VALIDATION
# ═══════════════════════════════════════════════════════════════════════════════


def validate_facts(facts: list[dict]) -> None:
    """Run quality checks on extracted facts and print a report."""
    if not facts:
        click.echo("No facts to validate.")
        return

    total = len(facts)

    # (a) Domain/subdomain distribution
    domain_counts: dict[str, int] = defaultdict(int)
    subdomain_counts: dict[str, int] = defaultdict(int)
    for f in facts:
        domain_counts[f["domain"]] += 1
        sub = f.get("subdomain") or "(none)"
        subdomain_counts[f"{f['domain']}/{sub}"] += 1

    click.echo("\nDomain distribution:")
    for domain, count in sorted(domain_counts.items()):
        click.echo(f"  {domain:25s}: {count} facts")

    click.echo("\nSubdomain distribution:")
    for sub, count in sorted(subdomain_counts.items()):
        click.echo(f"  {sub:45s}: {count} facts")

    # (b) Length checks
    too_short = [f for f in facts if len(f["fact_text"].split()) < 5]
    too_long = [f for f in facts if len(f["fact_text"].split()) > 50]
    click.echo(f"\nQuality:")
    click.echo(f"  Too short (<5 words):  {len(too_short)} ({100 * len(too_short) / total:.1f}%)")
    click.echo(f"  Too long (>50 words):  {len(too_long)} ({100 * len(too_long) / total:.1f}%)")
    if too_short:
        click.echo("  Short facts:")
        for f in too_short[:5]:
            click.echo(f'    - "{f["fact_text"]}"')
    if too_long:
        click.echo("  Long facts:")
        for f in too_long[:5]:
            click.echo(f'    - "{f["fact_text"]}"')

    # (c) Entity-name-only facts
    no_predicate = [f for f in facts if len(f["fact_text"].rstrip(".").strip().split()) <= 2]
    click.echo(f"  No-predicate facts:    {len(no_predicate)} ({100 * len(no_predicate) / total:.1f}%)")

    # (d) Near-duplicate check
    near_dupes = 0
    fact_texts = [f["fact_text"] for f in facts]
    sample_size = min(len(fact_texts), 500)
    sampled = random.sample(fact_texts, sample_size)
    for i, a in enumerate(sampled):
        for b in sampled[i + 1:]:
            a_stripped = a.rstrip(".")
            b_stripped = b.rstrip(".")
            if len(a_stripped) > 20 and len(b_stripped) > 20:
                if a_stripped in b_stripped or b_stripped in a_stripped:
                    near_dupes += 1
    click.echo(f"  Possible near-dupes:   {near_dupes} (sampled {sample_size} facts)")

    # (e) Entity population rate
    with_entities = sum(1 for f in facts if f.get("entities") and len(f["entities"]) > 0)
    missing_entities = total - with_entities
    click.echo(f"  Missing entities:      {missing_entities} ({100 * missing_entities / total:.1f}%)")

    # (f) Random samples
    click.echo(f"\nSample facts ({min(10, total)} random):")
    samples = random.sample(facts, min(10, total))
    for i, f in enumerate(samples, 1):
        click.echo(f'  {i:2d}. "{f["fact_text"]}"')


# ═══════════════════════════════════════════════════════════════════════════════
# TEST RUN
# ═══════════════════════════════════════════════════════════════════════════════


def _print_test_report(
    category_stats: dict[str, dict],
    all_facts: list[dict],
    all_inserted_ids: list[str],
) -> None:
    """Print structured test-run report."""
    click.echo("\n=== TEST RUN REPORT ===")
    click.echo("")

    header = (
        f"  {'Category':<25s} {'Items Processed':>17s} "
        f"{'Facts Generated':>17s} {'Facts Inserted (new)':>22s}"
    )
    separator = "  " + "-" * 83
    click.echo(header)
    click.echo(separator)

    total_items = 0
    total_generated = 0
    total_inserted = 0

    for cat_name, stats in category_stats.items():
        items = stats["items_processed"]
        generated = stats["facts_generated"]
        inserted = stats["facts_inserted"]
        total_items += items
        total_generated += generated
        total_inserted += inserted
        click.echo(f"  {cat_name:<25s} {items:>17d} {generated:>17d} {inserted:>22d}")

    click.echo(separator)
    click.echo(f"  {'TOTAL':<25s} {total_items:>17d} {total_generated:>17d} {total_inserted:>22d}")

    # Quality checks
    if not all_facts:
        click.echo("\n  No facts to analyze.")
        return

    total = len(all_facts)
    too_short = []
    too_long = []
    missing_entities = 0
    total_words = 0

    for f in all_facts:
        text = f["fact_text"]
        wc = len(text.split())
        total_words += wc
        if wc < 5:
            too_short.append(text)
        if wc > 50:
            too_long.append(text)
        if not f.get("entities"):
            missing_entities += 1

    avg_words = total_words / total if total else 0

    click.echo(f"\n  Quality Checks:")
    click.echo(f"    Too short (<5 words):  {len(too_short)} ({len(too_short)/total*100:.1f}%)")
    click.echo(f"    Too long (>50 words):  {len(too_long)} ({len(too_long)/total*100:.1f}%)")
    click.echo(f"    Missing entities:      {missing_entities} ({missing_entities/total*100:.1f}%)")
    click.echo(f"    Avg words per fact:    {avg_words:.1f}")

    # Sample facts
    sample = random.sample(all_facts, min(10, len(all_facts)))
    click.echo(f"\n  Sample Facts ({min(10, len(all_facts))} random from this run):")
    for i, f in enumerate(sample, 1):
        click.echo(f"    {i:2d}. \"{f['fact_text']}\"")


def run_test(cleanup: bool = False) -> None:
    """Run a limited test extraction: a few items per category, insert, report."""
    source_id = _get_source_id()
    category_stats = {}
    all_facts = []
    inserted_ids = []

    builders = {
        "Regions": _build_regional_facts,
        "VDP Classification": _build_vdp_facts,
        "Prädikat Levels": _build_praedikat_facts,
        "Grape Varieties": _build_grape_variety_facts,
        "Notable Vineyards": _build_vineyard_facts,
        "Unique Facts": _build_unique_facts,
    }

    for cat_name, builder in builders.items():
        all_generated = builder(source_id)
        test_facts = all_generated[:TEST_RUN_FACT_LIMIT]

        # Deduplicate
        seen_texts = set()
        unique_facts = []
        for f in test_facts:
            if f["fact_text"] not in seen_texts:
                seen_texts.add(f["fact_text"])
                unique_facts.append(f)

        # Insert individually to track IDs
        cat_inserted = 0
        for f in unique_facts:
            fact_id = insert_fact(
                fact_text=f["fact_text"],
                domain=f["domain"],
                source_id=f["source_id"],
                subdomain=f.get("subdomain"),
                entities=f.get("entities"),
                confidence=f.get("confidence", 1.0),
                tags=f.get("tags"),
            )
            if fact_id:
                inserted_ids.append(fact_id)
                cat_inserted += 1

        all_facts.extend(unique_facts)
        category_stats[cat_name] = {
            "items_processed": len(unique_facts),
            "facts_generated": len(unique_facts),
            "facts_inserted": cat_inserted,
        }

    _print_test_report(category_stats, all_facts, inserted_ids)

    # Cleanup
    if cleanup and inserted_ids:
        from src.utils.db import get_pg

        pg = get_pg()
        cur = pg.cursor()
        cur.execute("DELETE FROM facts WHERE id = ANY(%s::uuid[])", (inserted_ids,))
        pg.commit()
        click.echo(f"\n  Cleaned up {len(inserted_ids)} test facts from database.")


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════


@click.command()
@click.option("--all", "run_all_flag", is_flag=True, help="Run full extraction")
@click.option(
    "--type",
    "data_type",
    type=click.Choice(["region", "vdp", "praedikat", "grape", "vineyard", "unique"]),
    help="Extract a specific data category",
)
@click.option("--list", "list_sources", is_flag=True, help="List available data categories")
@click.option("--dry-run", is_flag=True, help="Extract facts but do not insert into DB")
@click.option("--validate", "validate_flag", is_flag=True, help="Run quality checks")
@click.option("--test-run", is_flag=True, help="Limited test with report")
@click.option("--cleanup", is_flag=True, help="With --test-run, delete inserted facts after reporting")
def main(
    run_all_flag: bool,
    data_type: Optional[str],
    list_sources: bool,
    dry_run: bool,
    validate_flag: bool,
    test_run: bool,
    cleanup: bool,
) -> None:
    """OenoBench German Wine Enrichment Scraper — Regions, VDP, Praedikat, grapes, vineyards."""
    logger.add("data/logs/germany_enrichment_{time}.log", rotation="10 MB")

    if list_sources:
        click.echo("\nAvailable data categories:")
        click.echo(f"  {'region':12s} — 13 Anbaugebiete (climate, soil, elevation, sub-regions)")
        click.echo(f"  {'vdp':12s} — VDP classification tiers (Gutswein to Grosse Lage/GG)")
        click.echo(f"  {'praedikat':12s} — {len(PRAEDIKAT_DATABASE)} Prädikat levels with Oechsle requirements")
        click.echo(f"  {'grape':12s} — {len(GRAPE_VARIETY_DATABASE)} grape variety profiles")
        click.echo(f"  {'vineyard':12s} — {len(NOTABLE_VINEYARDS)} notable Einzellagen (vineyard sites)")
        click.echo(f"  {'unique':12s} — Sekt, trocken styles, history, steep-slope viticulture, wine law")
        click.echo(f"\nKnowledge base coverage:")
        click.echo(f"  Regions:         {len(REGION_DATABASE)}")
        click.echo(f"  VDP tiers:       {len(VDP_CLASSIFICATION)}")
        click.echo(f"  Prädikat levels: {len(PRAEDIKAT_DATABASE)}")
        click.echo(f"  Grape varieties: {len(GRAPE_VARIETY_DATABASE)}")
        click.echo(f"  Einzellagen:     {len(NOTABLE_VINEYARDS)}")
        click.echo(f"  Unique fact categories: {len(UNIQUE_FACTS_DATABASE)}")
        return

    if validate_flag:
        click.echo("Running validation on all categories...")
        source_id = _get_source_id()
        all_facts = _build_all_facts(source_id, data_type=data_type)
        validate_facts(all_facts)
        return

    if test_run:
        run_test(cleanup=cleanup)
        return

    if run_all_flag or data_type:
        summary = run_all(dry_run=dry_run, data_type=data_type)
        if not dry_run:
            click.echo(f"\nInserted {summary['total_inserted']} new facts "
                       f"(from {summary['total_generated']} generated).")
        return

    click.echo("Use --all to extract all data, or --type <category> for a specific category.")
    click.echo("Use --list to see available categories.")
    click.echo("Use --dry-run to preview without inserting.")
    click.echo("Use --validate to run quality checks.")
    click.echo("Use --test-run to run a limited test extraction with report.")


if __name__ == "__main__":
    main()
