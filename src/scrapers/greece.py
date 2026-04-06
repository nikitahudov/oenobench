"""
OenoBench — Greek Wine Scraper

Extracts structured Greek wine data covering regions, PDO appellations,
grape varieties, classification system, and unique winemaking traditions.

Greece has one of the oldest winemaking traditions in the world, with
indigenous grape varieties such as Assyrtiko, Xinomavro, and Agiorgitiko
that are increasingly recognized internationally.

Focus areas: regional profiles, 33 PDO appellations, 22 key grape varieties,
Greek wine classification (PDO/PGI), and unique winemaking practices
(kouloura training, Retsina, Vinsanto, Samos Muscat).

Usage:
    python -m src.scrapers.greece --all
    python -m src.scrapers.greece --type region
    python -m src.scrapers.greece --type pdo
    python -m src.scrapers.greece --type grape
    python -m src.scrapers.greece --type classification
    python -m src.scrapers.greece --type winemaking
    python -m src.scrapers.greece --dry-run
    python -m src.scrapers.greece --validate
    python -m src.scrapers.greece --test-run
    python -m src.scrapers.greece --list
"""

import random
import time
from collections import defaultdict
from typing import Optional

import click
import requests
from loguru import logger

from src.utils.facts import (
    ensure_source,
    insert_fact,
    insert_facts_batch,
    get_fact_count,
)

# ─── Configuration ────────────────────────────────────────────────────────────

USER_AGENT = "OenoBench-Research/1.0 (academic wine benchmark)"
REQUEST_DELAY = 5.0
REQUEST_TIMEOUT = 30
TEST_RUN_FACT_LIMIT = 5

SOURCE = {
    "name": "Greek Wine Reference Database",
    "url": "https://winesofgreece.org",
    "source_type": "reference",
    "tier": "tier_2_authoritative",
    "language": "en",
}

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,el;q=0.8",
}


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Regional Data
# ═══════════════════════════════════════════════════════════════════════════════

REGIONAL_DATABASE = [
    {
        "name": "Macedonia",
        "greek_name": "Makedonia",
        "climate": "continental with Mediterranean influence",
        "climate_details": "Cold winters and warm summers with significant diurnal temperature variation; northern location provides cooler conditions than most Greek regions; Naoussa and Amynteo benefit from elevation and continental air masses",
        "soil_types": ["clay-limestone", "sand", "schist", "alluvial"],
        "soil_details": "Naoussa has clay-limestone and schist soils on the slopes of Mount Vermion; Amynteo sits on sandy and clay soils around lakes at high elevation; Halkidiki peninsula has varied clay and limestone",
        "vineyard_area_ha": 10000,
        "elevation_range": "100-700m",
        "annual_rainfall_mm": 550,
        "key_grapes": ["Xinomavro", "Negoska", "Limnio", "Malagousia", "Assyrtiko"],
        "pdo_appellations": ["Naoussa", "Amynteo", "Goumenissa", "Slopes of Meliton"],
    },
    {
        "name": "Peloponnese",
        "greek_name": "Peloponnisos",
        "climate": "varied Mediterranean to continental",
        "climate_details": "Coastal areas have a warm Mediterranean climate; the Mantinia plateau at 650m has cool continental conditions ideal for aromatic whites; Nemea valley has hot summers moderated by altitude on the upper slopes",
        "soil_types": ["clay-limestone", "marl", "alluvial", "gravel"],
        "soil_details": "Nemea has clay-limestone and marl soils at varying elevations; Mantinia plateau has limestone-rich soils at high altitude; Patras coastal zone has alluvial and clay soils",
        "vineyard_area_ha": 23000,
        "elevation_range": "50-800m",
        "annual_rainfall_mm": 600,
        "key_grapes": ["Agiorgitiko", "Moschofilero", "Mavrodaphne", "Rhoditis", "Robola"],
        "pdo_appellations": ["Nemea", "Mantinia", "Patras", "Mavrodaphne of Patras", "Muscat of Patras", "Muscat of Rio Patras"],
    },
    {
        "name": "Crete",
        "greek_name": "Kriti",
        "climate": "Mediterranean hot",
        "climate_details": "Hot dry summers and mild winters; the island's mountainous spine creates diverse microclimates with cooler conditions at higher elevations; strong sea breezes moderate coastal vineyard temperatures",
        "soil_types": ["limestone", "clay", "sandy loam", "gravel"],
        "soil_details": "Heraklion and Peza zones have limestone and clay soils; eastern Crete (Sitia) has poor, stony soils ideal for Liatiko; the Dafnes area features clay-limestone slopes",
        "vineyard_area_ha": 7000,
        "elevation_range": "100-800m",
        "annual_rainfall_mm": 500,
        "key_grapes": ["Vidiano", "Vilana", "Kotsifali", "Mandilari", "Liatiko"],
        "pdo_appellations": ["Peza", "Archanes", "Daphnes", "Sitia"],
    },
    {
        "name": "Aegean Islands",
        "greek_name": "Nissia Aigaiou",
        "climate": "Mediterranean with strong maritime influence",
        "climate_details": "Hot dry summers with persistent Meltemi winds that desiccate vines; Santorini has volcanic soils with minimal rainfall; Samos has mountainous terrain with varying microclimates; Lemnos has a warm, windy climate",
        "soil_types": ["volcanic ash", "pumice", "granite", "schist", "limestone"],
        "soil_details": "Santorini has unique volcanic soils of ash, pumice, and tephra that retain moisture; Samos has granite and schist on steep mountain slopes; Paros has granite and gneiss; Lemnos has volcanic soils",
        "vineyard_area_ha": 5000,
        "elevation_range": "10-800m",
        "annual_rainfall_mm": 350,
        "key_grapes": ["Assyrtiko", "Athiri", "Aidani", "Mandilari", "Mavrotragano", "Muscat Blanc a Petits Grains", "Muscat of Alexandria"],
        "pdo_appellations": ["Santorini", "Samos", "Muscat of Lemnos", "Limnio of Lemnos", "Paros", "Rhodes"],
    },
    {
        "name": "Central Greece",
        "greek_name": "Sterea Ellada / Attiki",
        "climate": "Mediterranean",
        "climate_details": "Hot dry summers and mild winters; Attica has a classic Mediterranean climate with limited rainfall; Boeotia inland has slightly more continental character; this is the heartland of Retsina production",
        "soil_types": ["limestone", "clay", "sandy loam", "marl"],
        "soil_details": "Attica has limestone and clay soils on rolling hills; Boeotia has alluvial and clay soils; Mesogia plain east of Athens has sandy loam over limestone bedrock",
        "vineyard_area_ha": 13000,
        "elevation_range": "50-600m",
        "annual_rainfall_mm": 400,
        "key_grapes": ["Savatiano", "Rhoditis", "Assyrtiko", "Malagousia"],
        "pdo_appellations": [],
    },
    {
        "name": "Thessaly",
        "greek_name": "Thessalia",
        "climate": "continental",
        "climate_details": "Hot summers and cold winters on the Thessalian plain; the slopes of Mount Olympus in Rapsani provide a unique mesoclimate with significant altitude variation and cooler nights; Anchialos near the coast has maritime influence",
        "soil_types": ["clay", "limestone", "schist", "alluvial"],
        "soil_details": "Rapsani vineyards on Mount Olympus slopes have schist and limestone at varying elevations; the Thessalian plain has deep alluvial clay soils; Anchialos coastal area has sandy clay",
        "vineyard_area_ha": 3000,
        "elevation_range": "50-700m",
        "annual_rainfall_mm": 500,
        "key_grapes": ["Xinomavro", "Krassato", "Stavroto", "Batiki", "Muscat of Hamburg"],
        "pdo_appellations": ["Rapsani", "Anchialos"],
    },
    {
        "name": "Epirus",
        "greek_name": "Ipiros",
        "climate": "continental mountainous",
        "climate_details": "Greece's coolest and wettest wine region; high mountain elevations create truly continental conditions; cold winters with snow and cool summers; the Zitsa plateau sits at 600-750m elevation with acidic, fresh wines",
        "soil_types": ["limestone", "clay", "flysch", "sandstone"],
        "soil_details": "Zitsa has limestone and flysch soils on mountain slopes; the region's high rainfall and cool temperatures produce naturally high-acid wines; rocky terrain limits vineyard expansion",
        "vineyard_area_ha": 1000,
        "elevation_range": "400-750m",
        "annual_rainfall_mm": 1000,
        "key_grapes": ["Debina", "Vlachiko", "Bekari"],
        "pdo_appellations": ["Zitsa"],
    },
    {
        "name": "Ionian Islands",
        "greek_name": "Ionia Nissia",
        "climate": "Mediterranean maritime",
        "climate_details": "More rainfall than other Greek islands due to western exposure to Adriatic weather systems; mild winters and warm but not extreme summers; Cephalonia has mountainous terrain with limestone bedrock ideal for Robola",
        "soil_types": ["limestone", "clay", "sandy loam", "terra rossa"],
        "soil_details": "Cephalonia has thin limestone soils on steep slopes in the Robola zone; Zakynthos has clay and limestone; Corfu has clay-rich alluvial soils; Lefkada has limestone with red clay pockets",
        "vineyard_area_ha": 2000,
        "elevation_range": "50-800m",
        "annual_rainfall_mm": 800,
        "key_grapes": ["Robola", "Tsaousi", "Mavrodaphne", "Vertzami", "Muscat Blanc a Petits Grains"],
        "pdo_appellations": ["Robola of Cephalonia", "Muscat of Cephalonia", "Mavrodaphne of Cephalonia"],
    },
    {
        "name": "Thrace",
        "greek_name": "Thraki",
        "climate": "continental with maritime influence",
        "climate_details": "Northeastern Greece with cold winters and warm summers; proximity to the Aegean and Thracian seas provides some maritime moderation; continental character is stronger than in Macedonia",
        "soil_types": ["clay", "sand", "limestone", "granite"],
        "soil_details": "Varied soils including clay and sandy loam in river valleys; granite and limestone on hillsides; the region is increasingly recognized for quality reds from international and indigenous varieties",
        "vineyard_area_ha": 1500,
        "elevation_range": "50-400m",
        "annual_rainfall_mm": 550,
        "key_grapes": ["Limnio", "Mavroudi", "Pamidi", "Assyrtiko", "Malagousia"],
        "pdo_appellations": [],
    },
    {
        "name": "Sterea Ellada",
        "greek_name": "Sterea Ellada",
        "climate": "Mediterranean to semi-continental",
        "climate_details": "Central mainland region with transitional climate between coastal Mediterranean and inland continental; varied terrain from sea level to mountainous areas; Boeotia and Phthiotis are notable subregions",
        "soil_types": ["clay", "limestone", "alluvial", "sandy"],
        "soil_details": "Diverse geological composition with alluvial plains, limestone hills, and clay deposits; lower-lying areas have deeper, more fertile soils while hillsides offer better drainage",
        "vineyard_area_ha": 5000,
        "elevation_range": "50-500m",
        "annual_rainfall_mm": 500,
        "key_grapes": ["Savatiano", "Rhoditis", "Agiorgitiko"],
        "pdo_appellations": [],
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — PDO Appellations
# ═══════════════════════════════════════════════════════════════════════════════

PDO_DATABASE = [
    # ── Macedonia ──
    {
        "name": "Naoussa",
        "region": "Macedonia",
        "grapes": ["Xinomavro"],
        "grape_pct": "100% Xinomavro",
        "soil_types": ["clay-limestone", "schist", "marl"],
        "elevation_range": "150-450m",
        "climate_note": "Continental with cold winters and warm summers on the southeastern slopes of Mount Vermion; autumn fog is common",
        "wine_styles": ["dry red", "dry red reserve"],
        "vineyard_area_ha": 600,
        "aging_notes": "Reserve requires minimum 3 years aging including 12 months in oak; Grand Reserve requires minimum 4 years including 18 months in oak",
    },
    {
        "name": "Amynteo",
        "region": "Macedonia",
        "grapes": ["Xinomavro"],
        "grape_pct": "100% Xinomavro",
        "soil_types": ["sandy", "clay", "alluvial"],
        "elevation_range": "580-700m",
        "climate_note": "One of Greece's highest-altitude and coldest wine zones; continental climate with lakes providing some temperature moderation; suitable for sparkling wine production",
        "wine_styles": ["dry red", "dry rose", "sparkling rose"],
        "vineyard_area_ha": 250,
        "aging_notes": "One of the few Greek PDOs producing sparkling wine from Xinomavro",
    },
    {
        "name": "Goumenissa",
        "region": "Macedonia",
        "grapes": ["Xinomavro", "Negoska"],
        "grape_pct": "Minimum 70% Xinomavro, up to 30% Negoska",
        "soil_types": ["clay-limestone", "sand", "gravel"],
        "elevation_range": "100-300m",
        "climate_note": "Continental with warmer conditions than Naoussa; lower elevation on the slopes of Mount Paiko",
        "wine_styles": ["dry red"],
        "vineyard_area_ha": 100,
        "aging_notes": "The addition of Negoska softens Xinomavro's tannins and adds fruity character",
    },
    {
        "name": "Slopes of Meliton",
        "region": "Macedonia",
        "grapes": ["Limnio", "Cabernet Sauvignon", "Cabernet Franc", "Athiri", "Rhoditis", "Assyrtiko"],
        "grape_pct": "Blends of Greek and international varieties",
        "soil_types": ["clay", "sand", "granite"],
        "elevation_range": "50-300m",
        "climate_note": "Maritime Mediterranean on the Sithonia peninsula of Halkidiki; sea breezes moderate temperatures; pioneered by Domaine Carras in the 1960s",
        "wine_styles": ["dry red", "dry white"],
        "vineyard_area_ha": 120,
        "aging_notes": "One of the first modern Greek appellations to blend indigenous and international varieties",
    },
    # ── Peloponnese ──
    {
        "name": "Nemea",
        "region": "Peloponnese",
        "grapes": ["Agiorgitiko"],
        "grape_pct": "100% Agiorgitiko",
        "soil_types": ["clay-limestone", "marl", "gravel", "alluvial"],
        "elevation_range": "250-800m",
        "climate_note": "Mediterranean with continental influence at higher elevations; vineyards at three altitude zones produce different styles: lower (250-450m) gives fuller wines, middle (450-600m) gives balanced wines, upper (600-800m) gives lighter, more aromatic wines",
        "wine_styles": ["dry red", "dry red reserve", "dry red grand reserve"],
        "vineyard_area_ha": 2500,
        "aging_notes": "Reserve requires minimum 2 years aging including 12 months in oak; Grand Reserve requires 3 years including 18 months in oak",
    },
    {
        "name": "Mantinia",
        "region": "Peloponnese",
        "grapes": ["Moschofilero"],
        "grape_pct": "Minimum 85% Moschofilero",
        "soil_types": ["limestone", "clay", "marl"],
        "elevation_range": "600-700m",
        "climate_note": "High-altitude plateau in the central Peloponnese at approximately 650m; cool continental conditions despite southern latitude; one of Greece's coolest vineyard sites",
        "wine_styles": ["dry white", "sparkling"],
        "vineyard_area_ha": 1000,
        "aging_notes": "The high altitude produces naturally aromatic wines with vibrant acidity; some producers make traditional-method sparkling",
    },
    {
        "name": "Patras",
        "region": "Peloponnese",
        "grapes": ["Rhoditis"],
        "grape_pct": "Minimum 85% Rhoditis",
        "soil_types": ["clay", "limestone", "sand"],
        "elevation_range": "100-400m",
        "climate_note": "Mediterranean coastal climate near the Gulf of Patras; warm conditions moderated by sea breezes",
        "wine_styles": ["dry white"],
        "vineyard_area_ha": 400,
        "aging_notes": "Rhoditis-based dry white; distinct from the sweet Mavrodaphne of Patras and Muscat of Patras appellations",
    },
    {
        "name": "Mavrodaphne of Patras",
        "region": "Peloponnese",
        "grapes": ["Mavrodaphne", "Korinthiaki"],
        "grape_pct": "Minimum 51% Mavrodaphne",
        "soil_types": ["clay", "limestone", "alluvial"],
        "elevation_range": "50-300m",
        "climate_note": "Warm Mediterranean climate near Patras; the warm conditions help produce the ripe, sweet fruit needed for this fortified wine style",
        "wine_styles": ["sweet fortified red"],
        "vineyard_area_ha": 300,
        "aging_notes": "Sweet fortified wine with extended oxidative aging in oak barrels; some producers age for decades developing complex, port-like character",
    },
    {
        "name": "Muscat of Patras",
        "region": "Peloponnese",
        "grapes": ["Muscat Blanc a Petits Grains"],
        "grape_pct": "100% Muscat Blanc a Petits Grains",
        "soil_types": ["clay", "limestone"],
        "elevation_range": "50-300m",
        "climate_note": "Warm Mediterranean near Patras; the white Muscat grape produces sweet fortified wines in this appellation",
        "wine_styles": ["sweet fortified white"],
        "vineyard_area_ha": 200,
        "aging_notes": "Vin de liqueur style: grape spirit added during fermentation to preserve natural sweetness and Muscat aromatics",
    },
    {
        "name": "Muscat of Rio Patras",
        "region": "Peloponnese",
        "grapes": ["Muscat Blanc a Petits Grains"],
        "grape_pct": "100% Muscat Blanc a Petits Grains",
        "soil_types": ["clay", "sand", "limestone"],
        "elevation_range": "50-200m",
        "climate_note": "Coastal Mediterranean in the Rio subzone of Patras; warmer than the hillside Muscat of Patras vineyards",
        "wine_styles": ["sweet unfortified white"],
        "vineyard_area_ha": 50,
        "aging_notes": "Naturally sweet wine (vin naturellement doux) without fortification; sweetness comes from late-harvested sun-dried grapes",
    },
    # ── Aegean Islands ──
    {
        "name": "Santorini",
        "region": "Aegean Islands",
        "grapes": ["Assyrtiko", "Athiri", "Aidani"],
        "grape_pct": "Minimum 75% Assyrtiko",
        "soil_types": ["volcanic ash", "pumice", "tephra"],
        "elevation_range": "50-350m",
        "climate_note": "Hot Mediterranean with very low rainfall (around 300mm annually); fierce Meltemi winds; volcanic soils retain moisture from overnight sea mist; phylloxera never reached the island so vines are ungrafted",
        "wine_styles": ["dry white", "Nykteri (barrel-aged dry white)", "Vinsanto (sun-dried sweet)"],
        "vineyard_area_ha": 1200,
        "aging_notes": "Vinsanto of Santorini requires sun-drying of grapes for 10-14 days and minimum 2 years aging in oak barrels; Nykteri requires minimum 3 months barrel aging",
    },
    {
        "name": "Samos",
        "region": "Aegean Islands",
        "grapes": ["Muscat Blanc a Petits Grains"],
        "grape_pct": "100% Muscat Blanc a Petits Grains (locally called Muscat Aspro)",
        "soil_types": ["granite", "schist", "clay"],
        "elevation_range": "50-800m",
        "climate_note": "Mediterranean island climate with mountainous terrain; steep terraced vineyards face south; higher-altitude vineyards at 400-800m produce the most aromatic Muscat",
        "wine_styles": ["Vin Doux (fortified sweet)", "Vin Doux Naturel (fortified late-harvest)", "Vin Naturellement Doux (naturally sweet unfortified)"],
        "vineyard_area_ha": 1500,
        "aging_notes": "Three distinct sweet wine styles: Vin Doux is fortified during fermentation; Vin Doux Naturel is fortified from late-harvest grapes; Vin Naturellement Doux achieves sweetness from sun-dried grapes without fortification",
    },
    {
        "name": "Muscat of Lemnos",
        "region": "Aegean Islands",
        "grapes": ["Muscat of Alexandria"],
        "grape_pct": "100% Muscat of Alexandria",
        "soil_types": ["volcanic", "clay", "sand"],
        "elevation_range": "20-200m",
        "climate_note": "Warm island climate with persistent winds; volcanic soil from ancient eruptions; flatter terrain than most Aegean islands",
        "wine_styles": ["sweet fortified white", "dry white"],
        "vineyard_area_ha": 200,
        "aging_notes": "Both dry and sweet versions are produced; the fortified Muscat is the traditional flagship",
    },
    {
        "name": "Limnio of Lemnos",
        "region": "Aegean Islands",
        "grapes": ["Limnio"],
        "grape_pct": "Minimum 85% Limnio",
        "soil_types": ["volcanic", "clay"],
        "elevation_range": "20-200m",
        "climate_note": "Same volcanic island terroir as Muscat of Lemnos; Limnio is one of the world's oldest documented grape varieties",
        "wine_styles": ["dry red"],
        "vineyard_area_ha": 50,
        "aging_notes": "Limnio was referenced by Aristotle in the 4th century BCE, making it one of the oldest named grape varieties still cultivated",
    },
    {
        "name": "Paros",
        "region": "Aegean Islands",
        "grapes": ["Mandilari", "Monemvasia"],
        "grape_pct": "Minimum 70% Mandilari, up to 30% Monemvasia (white)",
        "soil_types": ["granite", "gneiss", "schist"],
        "elevation_range": "50-300m",
        "climate_note": "Cycladic island with hot dry summers and strong Meltemi winds; unusual blend of a red and white grape variety is traditional to the island",
        "wine_styles": ["dry red", "dry white"],
        "vineyard_area_ha": 100,
        "aging_notes": "The traditional Paros red uniquely blends the deep-colored Mandilari with the white Monemvasia grape",
    },
    {
        "name": "Rhodes",
        "region": "Aegean Islands",
        "grapes": ["Athiri", "Mandilari", "Muscat Trani"],
        "grape_pct": "Varies by wine style",
        "soil_types": ["limestone", "clay", "sand"],
        "elevation_range": "50-500m",
        "climate_note": "Southeastern Aegean with warm Mediterranean climate; Dodecanese island group; mountainous interior with vineyard sites at moderate elevation",
        "wine_styles": ["dry white", "dry red", "sparkling", "sweet"],
        "vineyard_area_ha": 200,
        "aging_notes": "Produces a range of styles including sparkling wine from Athiri",
    },
    # ── Crete ──
    {
        "name": "Archanes",
        "region": "Crete",
        "grapes": ["Kotsifali", "Mandilari"],
        "grape_pct": "Minimum 80% Kotsifali and Mandilari combined",
        "soil_types": ["limestone", "clay"],
        "elevation_range": "200-600m",
        "climate_note": "Central Crete south of Heraklion on the slopes of Mount Juktas; warm days and cooler mountain nights; one of the smaller Cretan PDOs",
        "wine_styles": ["dry red"],
        "vineyard_area_ha": 150,
        "aging_notes": "Kotsifali contributes aroma and body while Mandilari adds deep color and tannin structure",
    },
    {
        "name": "Peza",
        "region": "Crete",
        "grapes": ["Kotsifali", "Mandilari", "Vilana"],
        "grape_pct": "Red: Kotsifali + Mandilari; White: minimum 85% Vilana",
        "soil_types": ["limestone", "clay", "marl"],
        "elevation_range": "200-500m",
        "climate_note": "Central Crete in the Heraklion prefecture; the largest Cretan PDO by volume; warm Mediterranean tempered by mountain proximity",
        "wine_styles": ["dry red", "dry white"],
        "vineyard_area_ha": 500,
        "aging_notes": "The most commercially significant Cretan appellation; white wines from Vilana are light and crisp",
    },
    {
        "name": "Sitia",
        "region": "Crete",
        "grapes": ["Liatiko", "Vilana"],
        "grape_pct": "Red: minimum 80% Liatiko; White: minimum 70% Vilana",
        "soil_types": ["limestone", "clay", "rocky"],
        "elevation_range": "100-600m",
        "climate_note": "Eastern Crete with hot, dry conditions; poor soils and low yields produce concentrated wines; increasingly recognized for quality Liatiko reds",
        "wine_styles": ["dry red", "sweet red", "dry white"],
        "vineyard_area_ha": 200,
        "aging_notes": "Liatiko produces both dry table wines and sweet sun-dried wines in the eastern Cretan tradition",
    },
    {
        "name": "Daphnes",
        "region": "Crete",
        "grapes": ["Liatiko"],
        "grape_pct": "Minimum 85% Liatiko",
        "soil_types": ["limestone", "clay-limestone"],
        "elevation_range": "200-500m",
        "climate_note": "South-central Crete near the Messara plain; warm conditions with cooling mountain air; historically known for sweet wine production",
        "wine_styles": ["dry red", "sweet red"],
        "vineyard_area_ha": 100,
        "aging_notes": "Traditionally produced as a sweet wine from sun-dried Liatiko grapes; dry versions are an increasingly important modern style",
    },
    # ── Thessaly ──
    {
        "name": "Rapsani",
        "region": "Thessaly",
        "grapes": ["Xinomavro", "Krassato", "Stavroto"],
        "grape_pct": "Roughly equal parts Xinomavro, Krassato, and Stavroto",
        "soil_types": ["schist", "limestone", "clay"],
        "elevation_range": "200-700m",
        "climate_note": "On the southeastern slopes of Mount Olympus; dramatic altitude variation creates diverse microclimates; higher vineyards experience cool mountain air while lower sites are warmer",
        "wine_styles": ["dry red"],
        "vineyard_area_ha": 100,
        "aging_notes": "The three-grape blend creates a unique style distinct from single-variety Xinomavro in Naoussa; Krassato adds fruit and Stavroto adds acidity",
    },
    {
        "name": "Anchialos",
        "region": "Thessaly",
        "grapes": ["Rhoditis", "Savatiano"],
        "grape_pct": "Blends of Rhoditis and Savatiano",
        "soil_types": ["clay", "sand", "alluvial"],
        "elevation_range": "10-100m",
        "climate_note": "Coastal zone near the Pagasetic Gulf; maritime influence moderates the Thessalian continental climate; primarily white wine production",
        "wine_styles": ["dry white", "semi-dry white"],
        "vineyard_area_ha": 200,
        "aging_notes": "A minor PDO producing simple, fresh white wines",
    },
    # ── Epirus ──
    {
        "name": "Zitsa",
        "region": "Epirus",
        "grapes": ["Debina"],
        "grape_pct": "100% Debina",
        "soil_types": ["limestone", "clay", "flysch"],
        "elevation_range": "600-750m",
        "climate_note": "One of the highest and coolest vineyard sites in Greece; mountain climate produces naturally high-acid wines; frost risk and cool temperatures limit the growing season",
        "wine_styles": ["dry sparkling white", "semi-sparkling", "still white"],
        "vineyard_area_ha": 200,
        "aging_notes": "Debina's naturally high acidity makes it ideal for sparkling wine production; both traditional method and tank method sparkling wines are produced",
    },
    # ── Ionian Islands ──
    {
        "name": "Robola of Cephalonia",
        "region": "Ionian Islands",
        "grapes": ["Robola"],
        "grape_pct": "100% Robola",
        "soil_types": ["limestone", "thin rocky"],
        "elevation_range": "200-800m",
        "climate_note": "Mountainous terrain on the island of Cephalonia; thin limestone soils on steep slopes; maritime climate with higher rainfall than Aegean islands; the best vineyards are in the Omala valley",
        "wine_styles": ["dry white"],
        "vineyard_area_ha": 300,
        "aging_notes": "Robola produces mineral-driven whites with citrus and stone fruit character; the limestone soils contribute pronounced minerality",
    },
    {
        "name": "Muscat of Cephalonia",
        "region": "Ionian Islands",
        "grapes": ["Muscat Blanc a Petits Grains"],
        "grape_pct": "100% Muscat Blanc a Petits Grains",
        "soil_types": ["limestone", "clay"],
        "elevation_range": "100-400m",
        "climate_note": "Warm maritime climate on Cephalonia; the Muscat vines benefit from sea breezes and limestone soils",
        "wine_styles": ["sweet fortified white", "naturally sweet white"],
        "vineyard_area_ha": 30,
        "aging_notes": "A rare sweet Muscat from the Ionian Islands; both fortified and naturally sweet styles are produced",
    },
    {
        "name": "Mavrodaphne of Cephalonia",
        "region": "Ionian Islands",
        "grapes": ["Mavrodaphne"],
        "grape_pct": "Minimum 85% Mavrodaphne",
        "soil_types": ["limestone", "clay"],
        "elevation_range": "100-400m",
        "climate_note": "Ionian maritime climate; Cephalonia's Mavrodaphne tends to produce a drier style than the Patras version",
        "wine_styles": ["sweet fortified red", "dry red"],
        "vineyard_area_ha": 20,
        "aging_notes": "Less well-known than Mavrodaphne of Patras but can produce excellent sweet wines with aging potential",
    },
    # ── Additional PDOs ──
    {
        "name": "Cotes de Meliton",
        "region": "Macedonia",
        "grapes": ["Limnio", "Cabernet Sauvignon", "Cabernet Franc", "Athiri", "Rhoditis", "Assyrtiko"],
        "grape_pct": "Blends of Greek and international varieties",
        "soil_types": ["clay", "sand", "limestone"],
        "elevation_range": "50-300m",
        "climate_note": "Halkidiki peninsula maritime climate; closely related to Slopes of Meliton; developed as a modern Greek wine estate",
        "wine_styles": ["dry red", "dry white"],
        "vineyard_area_ha": 100,
        "aging_notes": "Pioneered by Domaine Carras with consulting from Professor Emile Peynaud of Bordeaux",
    },
    {
        "name": "Messenikola",
        "region": "Thessaly",
        "grapes": ["Mavro Messenikola", "Carignan", "Syrah"],
        "grape_pct": "Minimum 70% Mavro Messenikola",
        "soil_types": ["clay", "limestone"],
        "elevation_range": "200-400m",
        "climate_note": "Interior Thessaly with continental climate; small appellation producing robust red wines",
        "wine_styles": ["dry red"],
        "vineyard_area_ha": 30,
        "aging_notes": "One of the lesser-known Greek PDOs; Mavro Messenikola is a rare indigenous variety",
    },
    {
        "name": "Muscat of Rhodes",
        "region": "Aegean Islands",
        "grapes": ["Muscat Trani", "Muscat Blanc a Petits Grains"],
        "grape_pct": "100% Muscat varieties",
        "soil_types": ["limestone", "clay"],
        "elevation_range": "50-300m",
        "climate_note": "Warm Dodecanese island climate; Muscat production on Rhodes dates to the Knights of St. John period",
        "wine_styles": ["sweet fortified white"],
        "vineyard_area_ha": 50,
        "aging_notes": "A lesser-known sweet Muscat from the Dodecanese; Rhodes also produces dry wines under its own PDO",
    },
    {
        "name": "Kantza",
        "region": "Central Greece",
        "grapes": ["Savatiano"],
        "grape_pct": "Minimum 85% Savatiano",
        "soil_types": ["clay", "limestone", "sandy loam"],
        "elevation_range": "100-300m",
        "climate_note": "Eastern Attica near Athens; warm Mediterranean; the Mesogia plain has been a traditional viticultural area since antiquity",
        "wine_styles": ["dry white"],
        "vineyard_area_ha": 100,
        "aging_notes": "One of the few PDOs in the Attica region; demonstrates Savatiano's potential beyond Retsina",
    },
    {
        "name": "Monemvasia-Malvasia",
        "region": "Peloponnese",
        "grapes": ["Monemvasia", "Kydonitsa", "Asproudes"],
        "grape_pct": "Primarily Monemvasia and Kydonitsa",
        "soil_types": ["limestone", "schist", "clay"],
        "elevation_range": "50-400m",
        "climate_note": "Southeastern Peloponnese near the historic port of Monemvasia; maritime climate; this area is the historical origin of the Malvasia grape family",
        "wine_styles": ["dry white", "sweet white"],
        "vineyard_area_ha": 80,
        "aging_notes": "The port of Monemvasia was the medieval trading hub that gave the Malvasia family of grapes its name; wines were exported across the Mediterranean and to England",
    },
    {
        "name": "Lesbos",
        "region": "Aegean Islands",
        "grapes": ["Chidiriotiko", "Muscat of Alexandria"],
        "grape_pct": "Varies by wine style",
        "soil_types": ["volcanic", "clay", "sand"],
        "elevation_range": "20-300m",
        "climate_note": "Large northeastern Aegean island; warm maritime climate; historically more associated with ouzo production but wine tradition is being revived",
        "wine_styles": ["dry white", "dry red"],
        "vineyard_area_ha": 60,
        "aging_notes": "Chidiriotiko is an indigenous red variety unique to the island of Lesbos",
    },
    {
        "name": "Naousa",
        "region": "Macedonia",
        "grapes": ["Xinomavro"],
        "grape_pct": "100% Xinomavro",
        "soil_types": ["clay-limestone", "schist"],
        "elevation_range": "150-450m",
        "climate_note": "Alternative transliteration of Naoussa PDO",
        "wine_styles": ["dry red"],
        "vineyard_area_ha": 0,
        "aging_notes": "See Naoussa entry (same appellation, different romanization)",
        "_skip": True,  # Avoid duplicate
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Grape Varieties
# ═══════════════════════════════════════════════════════════════════════════════

GRAPE_VARIETY_DATABASE = [
    # ── Red Grapes ──
    {
        "name": "Xinomavro",
        "color": "red",
        "origin": "autochthonous",
        "origin_region": "Macedonia",
        "synonyms": ["Xynomavro", "Populka"],
        "characteristics": "High tannin and high acidity with aromas of tomato, olive, dried fruit, and gooseberry; often compared to Nebbiolo for its tannic structure, aging potential, and ability to express terroir; pale garnet color that develops brick-orange tones with age",
        "key_denominations": ["Naoussa", "Amynteo", "Goumenissa", "Rapsani"],
        "regions_grown": ["Macedonia", "Thessaly"],
        "vineyard_area_ha": 2000,
        "aging_potential": "Top Xinomavro wines from Naoussa can age for 20-30 years, developing secondary aromas of sundried tomato, olive tapenade, leather, and tobacco similar to aged Barolo.",
    },
    {
        "name": "Agiorgitiko",
        "color": "red",
        "origin": "autochthonous",
        "origin_region": "Peloponnese",
        "synonyms": ["St. George", "Aghiorghitiko", "Mavro Nemeas"],
        "characteristics": "Versatile grape producing wines from soft, fruity roses to complex, structured reds; moderate tannin and acidity with red fruit character including cherry, plum, and raspberry; adapts to different winemaking styles and altitude zones",
        "key_denominations": ["Nemea"],
        "regions_grown": ["Peloponnese", "Macedonia", "Central Greece"],
        "vineyard_area_ha": 3000,
        "aging_potential": "Premium Agiorgitiko from upper Nemea can age for 8-15 years, developing complexity beyond its typically approachable youth.",
    },
    {
        "name": "Mavrodaphne",
        "color": "red",
        "origin": "autochthonous",
        "origin_region": "Peloponnese",
        "synonyms": ["Mavrodafni"],
        "characteristics": "Name means 'black laurel'; produces deeply colored sweet fortified wines with flavors of dried fig, chocolate, coffee, and raisin; also used for dry reds with dark berry and spice character",
        "key_denominations": ["Mavrodaphne of Patras", "Mavrodaphne of Cephalonia"],
        "regions_grown": ["Peloponnese", "Ionian Islands"],
        "vineyard_area_ha": 600,
    },
    {
        "name": "Kotsifali",
        "color": "red",
        "origin": "autochthonous",
        "origin_region": "Crete",
        "synonyms": [],
        "characteristics": "Crete's main red blending grape; low acidity and soft tannins with aromatic complexity; lacks color and structure on its own so is typically blended with the deeply colored Mandilari",
        "key_denominations": ["Peza", "Archanes"],
        "regions_grown": ["Crete"],
        "vineyard_area_ha": 1500,
    },
    {
        "name": "Mandilari",
        "color": "red",
        "origin": "autochthonous",
        "origin_region": "Crete",
        "synonyms": ["Mandilaria", "Amorgiano"],
        "characteristics": "Produces intensely deep-colored wines with high tannin but relatively low aromatic intensity and low acidity; almost always blended to provide color and structure to lighter grapes like Kotsifali",
        "key_denominations": ["Peza", "Archanes", "Paros", "Rhodes"],
        "regions_grown": ["Crete", "Aegean Islands", "Peloponnese"],
        "vineyard_area_ha": 1000,
    },
    {
        "name": "Limnio",
        "color": "red",
        "origin": "autochthonous",
        "origin_region": "Aegean Islands",
        "synonyms": ["Kalambaki", "Lemnio"],
        "characteristics": "One of the oldest documented grape varieties in the world, referenced by Aristotle as originating from Lemnos; produces medium-bodied red wines with herbal, bay leaf, and spice character; moderate tannin and good acidity",
        "key_denominations": ["Limnio of Lemnos", "Slopes of Meliton"],
        "regions_grown": ["Aegean Islands", "Macedonia", "Thrace"],
        "vineyard_area_ha": 300,
    },
    {
        "name": "Liatiko",
        "color": "red",
        "origin": "autochthonous",
        "origin_region": "Crete",
        "synonyms": ["Leatiko"],
        "characteristics": "Ancient Cretan variety; name may derive from July (Iouliatiko) reflecting its early ripening; produces light-colored, low-tannin wines with sweet spice and dried fruit notes; used for both dry and sweet wines",
        "key_denominations": ["Daphnes", "Sitia"],
        "regions_grown": ["Crete"],
        "vineyard_area_ha": 500,
    },
    {
        "name": "Negoska",
        "color": "red",
        "origin": "autochthonous",
        "origin_region": "Macedonia",
        "synonyms": ["Negoska Goumenissis"],
        "characteristics": "Soft and fruity with low tannin and moderate acidity; used primarily as a blending partner for Xinomavro in Goumenissa PDO to soften the latter's tannic intensity; rarely vinified on its own",
        "key_denominations": ["Goumenissa"],
        "regions_grown": ["Macedonia"],
        "vineyard_area_ha": 200,
    },
    {
        "name": "Mavrotragano",
        "color": "red",
        "origin": "autochthonous",
        "origin_region": "Aegean Islands",
        "synonyms": [],
        "characteristics": "Rare Santorini red variety being revived from near extinction; deeply colored with very high tannin and intense dark fruit flavors; one of Greece's most powerful and age-worthy reds; grows in the same volcanic conditions as Assyrtiko",
        "key_denominations": [],
        "regions_grown": ["Aegean Islands"],
        "vineyard_area_ha": 20,
        "aging_potential": "Mavrotragano from Santorini is one of Greece's most age-worthy red wines, capable of developing over 15-20 years with extremely concentrated dark fruit and mineral character.",
    },
    {
        "name": "Krassato",
        "color": "red",
        "origin": "autochthonous",
        "origin_region": "Thessaly",
        "synonyms": [],
        "characteristics": "Indigenous to the slopes of Mount Olympus; contributes fruity, soft character to the Rapsani three-grape blend; medium body with red fruit aromas; rarely bottled as a varietal",
        "key_denominations": ["Rapsani"],
        "regions_grown": ["Thessaly"],
        "vineyard_area_ha": 100,
    },
    {
        "name": "Stavroto",
        "color": "red",
        "origin": "autochthonous",
        "origin_region": "Thessaly",
        "synonyms": [],
        "characteristics": "Indigenous Thessalian variety grown on the slopes of Mount Olympus; contributes acidity and herbal notes to the Rapsani blend; named for its cross-shaped (stavros) leaf formation",
        "key_denominations": ["Rapsani"],
        "regions_grown": ["Thessaly"],
        "vineyard_area_ha": 80,
    },
    # ── White Grapes ──
    {
        "name": "Assyrtiko",
        "color": "white",
        "origin": "autochthonous",
        "origin_region": "Aegean Islands",
        "synonyms": ["Asyrtiko"],
        "characteristics": "Widely considered Greece's finest white grape; extreme minerality and razor-sharp acidity even in hot climates; flavors of citrus, stone fruit, wet stone, and saline; retains acidity exceptionally well even at full ripeness; volcanic Santorini expressions are benchmark",
        "key_denominations": ["Santorini"],
        "regions_grown": ["Aegean Islands", "Macedonia", "Central Greece", "Peloponnese", "Crete"],
        "vineyard_area_ha": 1500,
        "aging_potential": "Top Santorini Assyrtiko wines can age for 10-15 years, developing honey, lanolin, and petrol notes while retaining their characteristic acidity and minerality.",
    },
    {
        "name": "Moschofilero",
        "color": "white",
        "origin": "autochthonous",
        "origin_region": "Peloponnese",
        "synonyms": ["Fileri"],
        "characteristics": "Pink-skinned aromatic variety; intensely floral with rose petal, violet, and citrus aromas; lighter body with vibrant acidity; produces pale, highly aromatic dry white wines; sometimes used for rose and sparkling",
        "key_denominations": ["Mantinia"],
        "regions_grown": ["Peloponnese"],
        "vineyard_area_ha": 1000,
    },
    {
        "name": "Malagousia",
        "color": "white",
        "origin": "autochthonous",
        "origin_region": "Macedonia",
        "synonyms": ["Malagouzia"],
        "characteristics": "Rescued from the brink of extinction in the 1970s by winemaker Evangelos Gerovassiliou, who found surviving vines in a village vineyard; richly aromatic with peach, apricot, jasmine, and citrus; full-bodied with moderate acidity",
        "key_denominations": [],
        "regions_grown": ["Macedonia", "Central Greece", "Peloponnese"],
        "vineyard_area_ha": 500,
    },
    {
        "name": "Rhoditis",
        "color": "white",
        "origin": "autochthonous",
        "origin_region": "Peloponnese",
        "synonyms": ["Roditis", "Alepou"],
        "characteristics": "Pink-skinned variety; widely planted across Greece; base grape for Retsina; produces crisp, light-bodied wines with citrus and green apple character; best quality comes from mountainous sites where it retains acidity",
        "key_denominations": ["Patras", "Anchialos"],
        "regions_grown": ["Peloponnese", "Central Greece", "Macedonia", "Thessaly"],
        "vineyard_area_ha": 8000,
    },
    {
        "name": "Savatiano",
        "color": "white",
        "origin": "autochthonous",
        "origin_region": "Central Greece",
        "synonyms": ["Savvatiano"],
        "characteristics": "The most widely planted grape variety in Greece, concentrated in Attica; traditionally the primary grape for Retsina; drought-resistant; produces neutral, light wines when overcropped but can be surprisingly complex with low yields and careful winemaking",
        "key_denominations": [],
        "regions_grown": ["Central Greece", "Thessaly", "Peloponnese"],
        "vineyard_area_ha": 9000,
    },
    {
        "name": "Robola",
        "color": "white",
        "origin": "autochthonous",
        "origin_region": "Ionian Islands",
        "synonyms": ["Ribolla"],
        "characteristics": "Signature grape of Cephalonia; produces mineral-driven dry whites with citrus, stone fruit, and pronounced saline minerality from the island's limestone soils; high acidity and medium body; may be related to Ribolla Gialla of Friuli",
        "key_denominations": ["Robola of Cephalonia"],
        "regions_grown": ["Ionian Islands"],
        "vineyard_area_ha": 300,
    },
    {
        "name": "Vidiano",
        "color": "white",
        "origin": "autochthonous",
        "origin_region": "Crete",
        "synonyms": [],
        "characteristics": "A revived ancient Cretan variety; richly aromatic and full-bodied with tropical fruit, peach, and honey character; good acidity and aging potential; increasingly popular as a premium Cretan white alternative to international varieties",
        "key_denominations": [],
        "regions_grown": ["Crete"],
        "vineyard_area_ha": 200,
    },
    {
        "name": "Vilana",
        "color": "white",
        "origin": "autochthonous",
        "origin_region": "Crete",
        "synonyms": [],
        "characteristics": "Crete's most widely planted white grape; produces light, crisp wines with citrus and green apple character; moderate acidity; typically consumed young; the main white grape in Peza PDO",
        "key_denominations": ["Peza", "Sitia"],
        "regions_grown": ["Crete"],
        "vineyard_area_ha": 800,
    },
    {
        "name": "Debina",
        "color": "white",
        "origin": "autochthonous",
        "origin_region": "Epirus",
        "synonyms": ["Ntempina"],
        "characteristics": "Signature grape of Epirus; naturally high acidity makes it ideal for sparkling wine; produces light-bodied wines with green apple, citrus, and mineral character; the cool, mountainous Zitsa plateau is its home terroir",
        "key_denominations": ["Zitsa"],
        "regions_grown": ["Epirus"],
        "vineyard_area_ha": 200,
    },
    {
        "name": "Athiri",
        "color": "white",
        "origin": "autochthonous",
        "origin_region": "Aegean Islands",
        "synonyms": ["Athiri Aspro"],
        "characteristics": "Widely planted across the Aegean islands; light and neutral with delicate citrus and floral notes; low acidity; often blended with Assyrtiko to soften its intensity; one of the permitted varieties in Santorini PDO",
        "key_denominations": ["Santorini", "Rhodes"],
        "regions_grown": ["Aegean Islands", "Macedonia", "Crete"],
        "vineyard_area_ha": 1000,
    },
    {
        "name": "Monemvasia",
        "color": "white",
        "origin": "autochthonous",
        "origin_region": "Peloponnese",
        "synonyms": ["Monemvassia", "Malvasia"],
        "characteristics": "Historically significant variety believed to be the origin of the Malvasia family of grapes; name comes from the fortified port town of Monemvasia in the southeastern Peloponnese; produces aromatic, medium-bodied wines; used in blending with Mandilari in Paros PDO",
        "key_denominations": ["Paros"],
        "regions_grown": ["Peloponnese", "Aegean Islands"],
        "vineyard_area_ha": 150,
    },
    {
        "name": "Aidani",
        "color": "white",
        "origin": "autochthonous",
        "origin_region": "Aegean Islands",
        "synonyms": ["Aidani Aspro"],
        "characteristics": "Aromatic Cycladic variety; contributes floral and perfumed notes when blended with Assyrtiko and Athiri in Santorini wines; delicate with low acidity and stone fruit character; also used for Vinsanto production",
        "key_denominations": ["Santorini"],
        "regions_grown": ["Aegean Islands"],
        "vineyard_area_ha": 200,
    },
    {
        "name": "Muscat Blanc a Petits Grains",
        "color": "white",
        "origin": "international",
        "origin_region": "Aegean Islands",
        "synonyms": ["Muscat Aspro", "Muscat de Samos"],
        "characteristics": "One of the oldest known grape varieties; produces intensely aromatic wines with orange blossom, rose, and lychee character; in Greece it is the base for the famous sweet wines of Samos, Patras, Cephalonia, and Rio Patras",
        "key_denominations": ["Samos", "Muscat of Patras", "Muscat of Rio Patras", "Muscat of Cephalonia"],
        "regions_grown": ["Aegean Islands", "Peloponnese", "Ionian Islands"],
        "vineyard_area_ha": 2000,
    },
    {
        "name": "Vertzami",
        "color": "red",
        "origin": "autochthonous",
        "origin_region": "Ionian Islands",
        "synonyms": ["Lefkaditiko"],
        "characteristics": "Indigenous to Lefkada in the Ionian Islands; produces deeply colored, tannic red wines with dark fruit and spice character; increasingly used for premium single-variety bottlings",
        "key_denominations": [],
        "regions_grown": ["Ionian Islands"],
        "vineyard_area_ha": 100,
    },
    {
        "name": "Mavroudi",
        "color": "red",
        "origin": "autochthonous",
        "origin_region": "Thrace",
        "synonyms": ["Mavroudi Thrakis"],
        "characteristics": "Dark-skinned Thracian variety producing deeply colored, full-bodied red wines with black fruit and earthy notes; an emerging premium variety in northeastern Greece",
        "key_denominations": [],
        "regions_grown": ["Thrace", "Macedonia"],
        "vineyard_area_ha": 100,
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Classification System
# ═══════════════════════════════════════════════════════════════════════════════

CLASSIFICATION_DATABASE = [
    {
        "category": "PDO System",
        "facts": [
            "Greece adopted the EU PDO (Protected Designation of Origin) system, which replaced the former Greek OPAP and OPE designations in 2009.",
            "The Greek PDO system is officially called Prostatevomenis Onomasias Proelefsis (POP) in Greek.",
            "Greece has 33 PDO (Protected Designation of Origin) wine appellations as of 2024.",
            "The former OPAP (Onomasia Proelefsis Anoteras Poiotitas) designation was used for quality dry wines and was replaced by PDO in 2009.",
            "The former OPE (Onomasia Proelefsis Elegchomeni) designation was used for quality sweet and fortified wines and was replaced by PDO in 2009.",
            "Under the pre-2009 Greek system, OPAP wines covered dry wine appellations like Naoussa and Nemea, while OPE covered sweet wines like Samos and Mavrodaphne of Patras.",
            "All former OPAP and OPE appellations were unified under the single PDO designation when Greece aligned with EU wine regulations in 2009.",
        ],
    },
    {
        "category": "PGI System",
        "facts": [
            "Greece has over 100 PGI (Protected Geographical Indication) wine designations covering broader regional areas.",
            "The Greek PGI system is officially called Prostatevomenis Geografikis Endixis (PGE) in Greek.",
            "Greek PGI wines allow more flexibility in grape variety selection than PDO wines, including the use of international varieties.",
            "Major Greek PGI designations include PGI Macedonia, PGI Peloponnese, PGI Crete, and PGI Attiki.",
            "The PGI system replaced the former Topikos Oinos (regional wine) classification when Greece adopted EU regulations.",
        ],
    },
    {
        "category": "Table Wine",
        "facts": [
            "Greek table wine without geographical indication is classified as Epitrapezios Oinos.",
            "Epitrapezios Oinos (table wine) is the lowest tier of Greek wine classification and does not require specific grape varieties or production methods.",
        ],
    },
    {
        "category": "Aging Categories",
        "facts": [
            "Greek Reserve red wines require a minimum of 3 years total aging, including at least 6 months in oak barrels and 6 months in bottle.",
            "Greek Reserve white and rose wines require a minimum of 2 years total aging, including at least 6 months in oak barrels and 6 months in bottle.",
            "Greek Grand Reserve red wines require a minimum of 4 years total aging, including at least 18 months in oak barrels and 6 months in bottle.",
            "Greek Grand Reserve white wines require a minimum of 3 years total aging, including at least 12 months in oak barrels and 6 months in bottle.",
            "The Reserve and Grand Reserve designations may only appear on PDO wines that meet the minimum aging requirements.",
        ],
    },
    {
        "category": "Retsina",
        "facts": [
            "Retsina holds a unique Traditional Designation status in EU wine law, separate from the PDO and PGI systems.",
            "Retsina is made by adding small pieces of Aleppo pine resin (Pinus halepensis) to the must during fermentation.",
            "The practice of adding pine resin to Greek wine dates back to ancient times when pine resin was used to seal amphorae, inadvertently flavoring the wine.",
            "Retsina is most commonly produced from Savatiano grapes in the Attica region, though Rhoditis and Assyrtiko may also be used.",
            "Modern Retsina producers use significantly less resin than traditional versions, creating a more subtle pine character.",
            "Retsina can only be produced in Greece and is protected as a Traditional Appellation under EU Regulation.",
        ],
    },
    {
        "category": "General Statistics",
        "facts": [
            "Greece has approximately 64,000 hectares of vineyards under cultivation.",
            "Greece produces approximately 2.5 million hectoliters of wine annually, making it one of the smaller wine-producing nations in the EU.",
            "Greece has over 300 indigenous grape varieties, with roughly 30 used commercially.",
            "Greek vineyards are spread across mainland Greece and numerous islands, creating diverse terroirs from sea level to over 1,000 meters elevation.",
            "The Peloponnese is Greece's largest wine-producing region by vineyard area, followed by Central Greece and Crete.",
            "Greek wine consumption is approximately 23 liters per capita annually, below the EU average.",
            "Greece ranks among the top 15 wine-producing countries globally by volume.",
        ],
    },
    {
        "category": "Viticulture Practices",
        "facts": [
            "Dry farming (non-irrigated viticulture) is the traditional practice throughout most of Greece due to low rainfall and EU regulations historically prohibiting irrigation for quality wines.",
            "Bush vine (gobelet) training is the traditional vine training method across Greece, particularly on islands where wind exposure makes trellising impractical.",
            "The Meltemi winds of the Aegean Sea are a defining viticultural factor, desiccating vines and requiring protective training systems like Santorini's kouloura.",
            "Phylloxera never reached Santorini's volcanic sandy soils, making it one of the few European wine regions with ungrafted vines on their own rootstocks.",
            "The steep terraced vineyards of Samos, reaching 800m elevation, represent some of the most labor-intensive viticulture in the Mediterranean.",
            "Greece's latitude (35-41 degrees N) combined with altitude creates conditions where Mediterranean warmth is moderated by cool mountain air, producing wines with both ripeness and acidity.",
            "Many Greek vineyards practice organic or sustainable viticulture due to the naturally dry climate that reduces disease pressure.",
        ],
    },
    {
        "category": "Greek Wine Regions Overview",
        "facts": [
            "Greece is divided into approximately 10 major wine-producing regions spanning from Macedonia in the north to Crete in the south.",
            "The northernmost Greek wine regions (Macedonia, Thrace) share a continental climate more similar to the Balkans than to the Mediterranean islands.",
            "The Aegean Islands collectively produce some of Greece's most distinctive wines due to volcanic soils, extreme wind exposure, and maritime conditions.",
            "Crete is the largest Greek island and has its own distinct viticultural identity with indigenous varieties like Vidiano, Vilana, Kotsifali, and Liatiko.",
            "The Ionian Islands on Greece's western coast receive more rainfall than the Aegean Islands, resulting in different grape varieties and wine styles.",
            "Central Greece (Attica and Boeotia) is the historical heartland of Retsina production and home to Savatiano, Greece's most widely planted grape variety.",
        ],
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Unique Winemaking Traditions
# ═══════════════════════════════════════════════════════════════════════════════

WINEMAKING_DATABASE = [
    {
        "category": "Santorini Kouloura Training",
        "facts": [
            "Santorini vineyards use the unique kouloura (basket) vine training system where canes are woven into a low, circular basket shape close to the ground.",
            "The kouloura training system on Santorini protects grape clusters from the fierce Meltemi winds and intense sun by positioning them inside the woven vine basket.",
            "Santorini vines trained in the kouloura system are not trellised and sit only 10-20 centimeters above the volcanic soil surface.",
            "The volcanic pumice soil of Santorini absorbs moisture from overnight sea mist and morning dew, providing water to vines that receive as little as 300mm of annual rainfall.",
            "Santorini vines are ungrafted (own-rooted) because phylloxera never reached the island, likely due to the volcanic sandy soil which the pest cannot survive in.",
            "Some Santorini vines are over 200 years old, among the oldest producing vines in the world, maintained through the kouloura system that allows continual regeneration.",
            "The kouloura is reformed every growing season during winter pruning by weaving new canes into the basket shape.",
        ],
    },
    {
        "category": "Vinsanto of Santorini",
        "facts": [
            "Vinsanto of Santorini is a sweet wine made primarily from Assyrtiko grapes that are sun-dried on the volcanic terraces for 10 to 14 days after harvest.",
            "Santorini Vinsanto must be aged for a minimum of 2 years in oak barrels, though many top producers age it for 10-20 years.",
            "The sun-drying process for Vinsanto concentrates the grape sugars to very high levels, with must often reaching over 400 grams per liter of sugar.",
            "Vinsanto of Santorini is unrelated to Italian Vin Santo despite the similar name; the Greek version predates the Italian tradition and may derive from 'wine of Santorini'.",
            "Fermentation of Vinsanto can take many months or even years due to the extremely high sugar concentration, often resulting in wines of 8-14% alcohol with substantial residual sugar.",
            "Aged Vinsanto develops complex aromas of dried apricot, caramel, coffee, toffee, orange peel, and honey.",
        ],
    },
    {
        "category": "Samos Muscat Production",
        "facts": [
            "Samos produces three distinct sweet Muscat wine styles under its PDO: Vin Doux, Vin Doux Naturel, and Vin Naturellement Doux.",
            "Samos Vin Doux is a fortified sweet wine where grape spirit is added during fermentation to stop it, preserving grape sweetness and fresh Muscat aromatics.",
            "Samos Vin Doux Naturel is a fortified wine made from late-harvested grapes that have naturally concentrated sugars on the vine before fortification.",
            "Samos Vin Naturellement Doux is made from sun-dried grapes and achieves sweetness naturally without any fortification, relying solely on concentrated grape sugar.",
            "The Union of Viticultural Cooperatives of Samos (EOSS), founded in 1934, controls all wine production on the island under a cooperative monopoly system.",
            "Samos Muscat vineyards are planted on steep terraced hillsides reaching up to 800 meters elevation, with the highest-altitude vineyards producing the most aromatic wines.",
            "Samos has been producing Muscat wine since antiquity and was famous for its sweet wines in the medieval period when they were traded across the Mediterranean.",
        ],
    },
    {
        "category": "Retsina Tradition",
        "facts": [
            "Retsina production involves adding small pieces of Aleppo pine resin to the grape must at the beginning of or during fermentation.",
            "The ancient practice of adding pine resin originated as a preservation method: resin sealed amphorae and prevented oxidation during storage and transport.",
            "Traditional Retsina was often heavily resinated, but modern producers use just 1-2 grams of resin per liter of must for a more subtle flavor profile.",
            "Retsina ferments with the pine resin and the resin is removed with the lees after fermentation is complete.",
            "The resinated wine style is almost exclusively Greek, reflecting over 2,000 years of continuous winemaking tradition.",
            "Kechribari is a rose-tinted style of Retsina made from Rhoditis or other pink-skinned grapes.",
        ],
    },
    {
        "category": "Ancient Greek Winemaking Heritage",
        "facts": [
            "Greece is one of the oldest wine-producing regions in the world, with evidence of winemaking dating back to 4500 BCE in Macedonia.",
            "The ancient Greeks spread viticulture across the Mediterranean through colonization, establishing vineyards in southern Italy, Sicily, southern France, and the Black Sea coast.",
            "Dionysos, the Greek god of wine, was one of the most important deities in ancient Greek religion, reflecting wine's central role in Greek culture.",
            "The ancient Greek symposium was a ritualized drinking party where wine was mixed with water and philosophical discussion was central to the social event.",
            "Ancient Greek wines were often flavored with herbs, honey, seawater, or pine resin and were typically consumed diluted with water.",
            "The island of Thasos had the earliest known wine appellation laws in the 5th century BCE, regulating grape harvest dates and wine trade.",
        ],
    },
    {
        "category": "Modern Greek Winemaking Renaissance",
        "facts": [
            "The modern Greek wine renaissance began in the 1980s when a new generation of French and Australian-trained winemakers returned to Greece and invested in indigenous varieties.",
            "Evangelos Gerovassiliou is credited with saving the Malagousia grape from extinction in the 1970s, discovering surviving vines in a village vineyard in western Macedonia.",
            "The Greek wine industry shifted focus from bulk production and Retsina to premium quality wines from indigenous varieties starting in the 1990s.",
            "Santorini emerged as an internationally recognized wine region in the 2000s, with Assyrtiko becoming Greece's most acclaimed white wine grape.",
            "Greek wine exports have grown significantly since 2010, driven by international interest in indigenous grape varieties and unique terroirs like Santorini.",
            "The establishment of Domaine Carras in Halkidiki in the 1960s, with consulting from Bordeaux oenologist Emile Peynaud, marked one of the first modern Greek wine estates.",
            "Boutari, one of Greece's oldest wine companies founded in 1879, played a key role in popularizing Naoussa Xinomavro internationally.",
            "Paris Sigalas of Domaine Sigalas on Santorini was instrumental in demonstrating that Assyrtiko could produce world-class dry white wines, not just sweet Vinsanto.",
        ],
    },
    {
        "category": "Mavrodaphne Winemaking",
        "facts": [
            "Mavrodaphne of Patras is produced by fortifying partially fermented must with grape spirit, arresting fermentation and preserving natural sweetness.",
            "Traditional Mavrodaphne is aged oxidatively in old oak barrels, sometimes using a solera-like system of blending different vintages.",
            "The best aged Mavrodaphne of Patras develops complex flavors reminiscent of tawny port, with notes of dried fruit, toffee, chocolate, and roasted nuts.",
            "Mavrodaphne must reach a minimum of 15% alcohol by volume, with the addition of grape spirit contributing to the final alcoholic strength.",
            "Some Mavrodaphne bottlings are aged for 50 or more years, developing extraordinary complexity while maintaining a balance of sweetness and acidity.",
        ],
    },
    {
        "category": "Nykteri of Santorini",
        "facts": [
            "Nykteri is a premium dry white wine style from Santorini, meaning 'wine of the night', referring to the traditional practice of harvesting and pressing grapes at night to avoid the intense daytime heat.",
            "Santorini Nykteri must be aged for a minimum of 3 months in oak barrels before release.",
            "Nykteri is made primarily from Assyrtiko, often blended with small amounts of Athiri and Aidani, and achieves higher alcohol levels (typically 13-14.5%) than standard Santorini whites.",
            "The barrel aging gives Nykteri a richer, more complex character than unwooded Santorini Assyrtiko, with notes of honey, beeswax, and toasted almonds alongside the characteristic minerality.",
        ],
    },
    {
        "category": "Greek Orange and Natural Wine",
        "facts": [
            "Greece has a growing natural wine movement, with several producers in Macedonia, Thessaly, and the islands experimenting with minimal intervention winemaking.",
            "Skin-contact (orange) wines have ancient roots in Greece, where amphorae fermentation with extended skin contact predates modern orange wine trends by millennia.",
            "Some Greek producers are reviving ancient winemaking techniques including clay amphora (pithos) fermentation, connecting modern winemaking to Greece's 6,000-year winemaking heritage.",
        ],
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# HTTP CLIENT
# ═══════════════════════════════════════════════════════════════════════════════

_last_request_time = 0.0


def _get_session() -> requests.Session:
    """Create a configured HTTP session."""
    session = requests.Session()
    session.headers.update(HEADERS)
    return session


def _fetch_page(url: str, session: Optional[requests.Session] = None) -> Optional[str]:
    """Fetch a URL with rate limiting. Returns HTML or None on failure."""
    global _last_request_time
    elapsed = time.time() - _last_request_time
    if elapsed < REQUEST_DELAY:
        time.sleep(REQUEST_DELAY - elapsed)

    if session is None:
        session = _get_session()

    try:
        resp = session.get(url, timeout=REQUEST_TIMEOUT)
        _last_request_time = time.time()
        if resp.status_code == 403:
            logger.warning(f"403 on {url} — falling back to knowledge base")
            return None
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as e:
        logger.warning(f"Failed to fetch {url}: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# FACT BUILDER HELPERS
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
    """Build facts about Greek wine regions (climate, soil, elevation, stats)."""
    facts = []

    for region in REGIONAL_DATABASE:
        name = region["name"]
        greek = region["greek_name"]
        entities = [{"type": "region", "name": name}]
        base_tags = ["greece", name.lower().replace(" ", "_")]

        # Climate
        facts.append(_make_fact(
            f"The {name} ({greek}) wine region of Greece has a {region['climate']} climate.",
            domain="wine_regions",
            source_id=source_id,
            subdomain="climate",
            entities=entities,
            tags=base_tags + ["climate"],
        ))

        if region.get("climate_details"):
            facts.append(_make_fact(
                f"{region['climate_details']}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="climate",
                entities=entities,
                tags=base_tags + ["climate"],
            ))

        # Soil
        if region.get("soil_types"):
            soil_list = ", ".join(region["soil_types"])
            facts.append(_make_fact(
                f"The predominant soil types in the {name} wine region of Greece include {soil_list}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="terroir",
                entities=entities,
                tags=base_tags + ["soil", "terroir"],
            ))

        if region.get("soil_details"):
            facts.append(_make_fact(
                f"{region['soil_details']}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="terroir",
                entities=entities,
                tags=base_tags + ["soil", "terroir"],
            ))

        # Elevation
        if region.get("elevation_range"):
            facts.append(_make_fact(
                f"Vineyards in the {name} wine region of Greece are planted at elevations ranging from {region['elevation_range']}.",
                domain="viticulture",
                source_id=source_id,
                subdomain="terrain",
                entities=entities,
                tags=base_tags + ["elevation"],
            ))

        # Rainfall
        if region.get("annual_rainfall_mm"):
            facts.append(_make_fact(
                f"The {name} wine region of Greece receives approximately {region['annual_rainfall_mm']}mm of annual rainfall.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="climate",
                entities=entities,
                confidence=0.95,
                tags=base_tags + ["climate", "rainfall"],
            ))

        # Key grapes
        if region.get("key_grapes"):
            grapes_str = ", ".join(region["key_grapes"])
            grape_entities = entities + [{"type": "grape", "name": g} for g in region["key_grapes"]]
            facts.append(_make_fact(
                f"The principal grape varieties of the {name} wine region of Greece include {grapes_str}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="regional_grapes",
                entities=grape_entities,
                tags=base_tags + ["grapes"],
            ))

        # Vineyard area
        if region.get("vineyard_area_ha"):
            facts.append(_make_fact(
                f"The {name} wine region of Greece has approximately {region['vineyard_area_ha']:,} hectares of vineyards.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="statistics",
                entities=entities,
                confidence=0.95,
                tags=base_tags + ["vineyard_area", "statistics"],
            ))

        # PDO appellations
        if region.get("pdo_appellations") and len(region["pdo_appellations"]) > 0:
            pdo_str = ", ".join(region["pdo_appellations"])
            pdo_entities = entities + [{"type": "appellation", "name": p} for p in region["pdo_appellations"]]
            facts.append(_make_fact(
                f"The PDO appellations within the {name} wine region of Greece include {pdo_str}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="appellations",
                entities=pdo_entities,
                tags=base_tags + ["appellations", "pdo"],
            ))

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# FACT BUILDERS — PDO Appellations
# ═══════════════════════════════════════════════════════════════════════════════


def _build_pdo_facts(source_id: str) -> list[dict]:
    """Build facts about Greek PDO wine appellations."""
    facts = []

    for pdo in PDO_DATABASE:
        # Skip duplicates
        if pdo.get("_skip"):
            continue

        name = pdo["name"]
        region = pdo.get("region", "")
        entities = [
            {"type": "appellation", "name": name},
            {"type": "region", "name": region},
        ]
        base_tags = ["greece", "pdo", region.lower().replace(" ", "_")]

        # Basic identity
        facts.append(_make_fact(
            f"{name} is a PDO (Protected Designation of Origin) wine appellation in the {region} region of Greece.",
            domain="wine_regions",
            source_id=source_id,
            subdomain="appellations",
            entities=entities,
            tags=base_tags + [name.lower().replace(" ", "_")],
        ))

        # Grape requirements
        if pdo.get("grape_pct"):
            grape_entities = entities + [{"type": "grape", "name": g} for g in pdo.get("grapes", [])]
            facts.append(_make_fact(
                f"The {name} PDO requires {pdo['grape_pct']}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="appellations",
                entities=grape_entities,
                tags=base_tags + ["grapes", name.lower().replace(" ", "_")],
            ))

        # Soil types
        if pdo.get("soil_types"):
            soil_list = ", ".join(pdo["soil_types"])
            facts.append(_make_fact(
                f"Vineyards in the {name} PDO grow on {soil_list} soils.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="terroir",
                entities=entities,
                tags=base_tags + ["soil", "terroir", name.lower().replace(" ", "_")],
            ))

        # Elevation
        if pdo.get("elevation_range"):
            facts.append(_make_fact(
                f"Vineyards in the {name} PDO are planted between {pdo['elevation_range']} elevation.",
                domain="viticulture",
                source_id=source_id,
                subdomain="terrain",
                entities=entities,
                tags=base_tags + ["elevation", name.lower().replace(" ", "_")],
            ))

        # Climate note
        if pdo.get("climate_note"):
            facts.append(_make_fact(
                f"{pdo['climate_note']}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="climate",
                entities=entities,
                tags=base_tags + ["climate", name.lower().replace(" ", "_")],
            ))

        # Wine styles
        if pdo.get("wine_styles"):
            styles_str = ", ".join(pdo["wine_styles"])
            facts.append(_make_fact(
                f"The {name} PDO produces wines in the following styles: {styles_str}.",
                domain="winemaking",
                source_id=source_id,
                subdomain="wine_styles",
                entities=entities,
                tags=base_tags + ["wine_styles", name.lower().replace(" ", "_")],
            ))

        # Vineyard area
        if pdo.get("vineyard_area_ha") and pdo["vineyard_area_ha"] > 0:
            facts.append(_make_fact(
                f"The {name} PDO has approximately {pdo['vineyard_area_ha']:,} hectares of vineyard.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="statistics",
                entities=entities,
                confidence=0.95,
                tags=base_tags + ["vineyard_area", name.lower().replace(" ", "_")],
            ))

        # Aging notes
        if pdo.get("aging_notes") and "See " not in pdo["aging_notes"]:
            facts.append(_make_fact(
                f"{pdo['aging_notes']}.",
                domain="winemaking",
                source_id=source_id,
                subdomain="production_rules",
                entities=entities,
                tags=base_tags + ["aging", name.lower().replace(" ", "_")],
            ))

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# FACT BUILDERS — Grape Varieties
# ═══════════════════════════════════════════════════════════════════════════════


def _build_grape_variety_facts(source_id: str) -> list[dict]:
    """Build grape variety profile facts."""
    facts = []

    for grape in GRAPE_VARIETY_DATABASE:
        name = grape["name"]
        entities = [{"type": "grape", "name": name}]
        base_tags = ["greece", "grape_variety", grape["color"]]

        # Origin
        if grape.get("origin") == "autochthonous" and grape.get("origin_region"):
            facts.append(_make_fact(
                f"{name} is an indigenous Greek grape variety originating from the {grape['origin_region']} region.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="origin",
                entities=entities + [{"type": "region", "name": grape["origin_region"]}],
                tags=base_tags + ["origin", "autochthonous"],
            ))

        # Synonyms
        if grape.get("synonyms") and len(grape["synonyms"]) > 0:
            synonyms_str = ", ".join(grape["synonyms"])
            facts.append(_make_fact(
                f"{name} is also known as {synonyms_str}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="synonyms",
                entities=entities,
                tags=base_tags + ["synonyms"],
            ))

        # Characteristics
        if grape.get("characteristics"):
            facts.append(_make_fact(
                f"{name}: {grape['characteristics']}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="characteristics",
                entities=entities,
                tags=base_tags + ["characteristics", "tasting_notes"],
            ))

        # Key denominations
        if grape.get("key_denominations") and len(grape["key_denominations"]) > 0:
            denoms_str = ", ".join(grape["key_denominations"])
            denom_entities = entities + [{"type": "appellation", "name": d} for d in grape["key_denominations"]]
            facts.append(_make_fact(
                f"{name} is a principal grape in the following Greek appellations: {denoms_str}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="appellations",
                entities=denom_entities,
                tags=base_tags + ["appellations"],
            ))

        # Regions grown
        if grape.get("regions_grown") and len(grape["regions_grown"]) > 0:
            regions_str = ", ".join(grape["regions_grown"])
            region_entities = entities + [{"type": "region", "name": r} for r in grape["regions_grown"]]
            facts.append(_make_fact(
                f"{name} is cultivated in the Greek regions of {regions_str}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="distribution",
                entities=region_entities,
                tags=base_tags + ["distribution"],
            ))

        # Vineyard area
        if grape.get("vineyard_area_ha"):
            facts.append(_make_fact(
                f"Greece has approximately {grape['vineyard_area_ha']:,} hectares planted with {name}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="statistics",
                entities=entities,
                confidence=0.95,
                tags=base_tags + ["vineyard_area", "statistics"],
            ))

        # Aging potential
        if grape.get("aging_potential"):
            facts.append(_make_fact(
                grape["aging_potential"],
                domain="grape_varieties",
                source_id=source_id,
                subdomain="aging",
                entities=entities,
                tags=base_tags + ["aging", "aging_potential"],
            ))

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# FACT BUILDERS — Classification System
# ═══════════════════════════════════════════════════════════════════════════════


def _build_classification_facts(source_id: str) -> list[dict]:
    """Build facts about the Greek wine classification system."""
    facts = []

    for category in CLASSIFICATION_DATABASE:
        cat_name = category["category"]
        base_tags = ["greece", "classification", cat_name.lower().replace(" ", "_")]

        for fact_text in category["facts"]:
            # Determine domain based on category
            if cat_name == "General Statistics":
                domain = "wine_business"
                subdomain = "statistics"
            elif cat_name == "Retsina":
                domain = "winemaking"
                subdomain = "retsina"
            elif cat_name == "Aging Categories":
                domain = "winemaking"
                subdomain = "production_rules"
            else:
                domain = "wine_regions"
                subdomain = "classification"

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
# FACT BUILDERS — Unique Winemaking Traditions
# ═══════════════════════════════════════════════════════════════════════════════


def _build_winemaking_facts(source_id: str) -> list[dict]:
    """Build facts about unique Greek winemaking traditions."""
    facts = []

    for category in WINEMAKING_DATABASE:
        cat_name = category["category"]
        base_tags = ["greece", "winemaking", cat_name.lower().replace(" ", "_")]

        # Determine subdomain based on category
        if "Santorini" in cat_name or "Vinsanto" in cat_name:
            subdomain = "santorini"
            entities = [{"type": "region", "name": "Santorini"}]
        elif "Samos" in cat_name:
            subdomain = "samos"
            entities = [{"type": "region", "name": "Samos"}]
        elif "Retsina" in cat_name:
            subdomain = "retsina"
            entities = []
        elif "Ancient" in cat_name:
            subdomain = "history"
            entities = []
        elif "Modern" in cat_name or "Renaissance" in cat_name:
            subdomain = "modern_winemaking"
            entities = []
        else:
            subdomain = "traditions"
            entities = []

        for fact_text in category["facts"]:
            # Determine domain
            if "Ancient" in cat_name or "Modern" in cat_name or "Renaissance" in cat_name:
                domain = "wine_business"
            else:
                domain = "winemaking"

            facts.append(_make_fact(
                fact_text,
                domain=domain,
                source_id=source_id,
                subdomain=subdomain,
                entities=entities,
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
        "pdo": _build_pdo_facts,
        "grape": _build_grape_variety_facts,
        "classification": _build_classification_facts,
        "winemaking": _build_winemaking_facts,
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
        click.echo(f"\n[DRY RUN] Would insert {len(facts)} facts from Greek Wine Reference Database")

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

    logger.info(f"Inserted {inserted} new facts from Greek Wine Reference Database (duplicates skipped)")
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
        "PDO Appellations": _build_pdo_facts,
        "Grape Varieties": _build_grape_variety_facts,
        "Classification": _build_classification_facts,
        "Winemaking": _build_winemaking_facts,
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
    type=click.Choice(["region", "pdo", "grape", "classification", "winemaking"]),
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
    """OenoBench Greek Wine Scraper — Regions, PDOs, grape varieties, classification, and winemaking traditions."""
    logger.add("data/logs/greece_{time}.log", rotation="10 MB")

    if list_sources:
        click.echo("\nAvailable data categories:")
        click.echo(f"  {'region':18s} — {len(REGIONAL_DATABASE)} Greek wine regions (climate, soil, elevation)")
        click.echo(f"  {'pdo':18s} — {len([p for p in PDO_DATABASE if not p.get('_skip')])} PDO appellations (grapes, terroir, wine styles)")
        click.echo(f"  {'grape':18s} — {len(GRAPE_VARIETY_DATABASE)} grape variety profiles")
        click.echo(f"  {'classification':18s} — Greek wine law (PDO/PGI system, aging categories, Retsina)")
        click.echo(f"  {'winemaking':18s} — Unique Greek winemaking traditions")
        click.echo(f"\nKnowledge base coverage:")
        click.echo(f"  Regions:            {len(REGIONAL_DATABASE)}")
        click.echo(f"  PDO entries:        {len([p for p in PDO_DATABASE if not p.get('_skip')])}")
        click.echo(f"  Grape varieties:    {len(GRAPE_VARIETY_DATABASE)}")
        click.echo(f"  Classification:     {sum(len(c['facts']) for c in CLASSIFICATION_DATABASE)} facts")
        click.echo(f"  Winemaking:         {sum(len(c['facts']) for c in WINEMAKING_DATABASE)} facts")
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
