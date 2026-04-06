"""
OenoBench — Italian Wine Central Scraper

Extracts structured Italian wine data from Italian Wine Central
(https://italianwinecentral.com/) — a comprehensive reference database
covering all 411 Italian DOC/DOCG appellations, grape varieties, and regions.

Focus areas: climate, soil, elevation, grape variety profiles, subzones,
and regional statistics that complement the existing italy.py scraper
(which covers basic DOCG/DOC classification, grape requirements, and aging rules).

Usage:
    python -m src.scrapers.italian_wine_central --all
    python -m src.scrapers.italian_wine_central --type region
    python -m src.scrapers.italian_wine_central --type docg
    python -m src.scrapers.italian_wine_central --type doc
    python -m src.scrapers.italian_wine_central --type grape
    python -m src.scrapers.italian_wine_central --type stats
    python -m src.scrapers.italian_wine_central --region piedmont
    python -m src.scrapers.italian_wine_central --dry-run
    python -m src.scrapers.italian_wine_central --validate
    python -m src.scrapers.italian_wine_central --test-run
    python -m src.scrapers.italian_wine_central --list
"""

import random
import re
import time
from collections import defaultdict
from typing import Optional

import click
import requests
from bs4 import BeautifulSoup
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
    "name": "Italian Wine Central — Reference Database",
    "url": "https://italianwinecentral.com",
    "source_type": "reference",
    "tier": "tier_2_authoritative",
    "language": "en",
}

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,it;q=0.8",
}


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Regional Data
# ═══════════════════════════════════════════════════════════════════════════════

REGIONAL_DATABASE = [
    {
        "name": "Piedmont",
        "italian_name": "Piemonte",
        "climate": "continental",
        "climate_details": "Cold winters and hot summers with significant diurnal temperature variation; fog (nebbia) is common in autumn across the Langhe and Monferrato hills",
        "soil_types": ["calcareous marl", "clay-limestone", "sand", "tufo"],
        "soil_details": "The Langhe hills feature Tortonian-era calcareous marl (blue-gray) and Helvetian-era sandier soils; Roero has sandy, less calcareous soils on the left bank of the Tanaro River",
        "vineyard_area_ha": 42000,
        "elevation_range": "150-800m",
        "annual_rainfall_mm": 700,
        "docg_count": 19,
        "doc_count": 41,
        "key_grapes": ["Nebbiolo", "Barbera", "Dolcetto", "Moscato Bianco", "Cortese", "Arneis"],
        "production_hl": 2690000,
    },
    {
        "name": "Tuscany",
        "italian_name": "Toscana",
        "climate": "Mediterranean",
        "climate_details": "Dry hot summers, warm springs, and mild rainy autumns and winters; inland areas have more continental influence with cooler nights at higher elevations",
        "soil_types": ["galestro", "alberese", "clay", "sand", "limestone"],
        "soil_details": "Chianti zone features galestro (flakey schistose clay) and alberese (hard calcareous rock); Montalcino has clay and limestone at 200-600m; Bolgheri and Maremma have gravelly clay and sandy soils",
        "vineyard_area_ha": 58000,
        "elevation_range": "50-600m",
        "annual_rainfall_mm": 750,
        "docg_count": 11,
        "doc_count": 41,
        "key_grapes": ["Sangiovese", "Trebbiano Toscano", "Vernaccia", "Canaiolo", "Colorino"],
        "production_hl": 2770000,
    },
    {
        "name": "Veneto",
        "italian_name": "Veneto",
        "climate": "varied continental to Mediterranean",
        "climate_details": "Northern mountain areas have an Alpine continental climate; the Valpolicella and Soave hills have a temperate sub-Mediterranean climate moderated by Lake Garda; the plains are continental with fog",
        "soil_types": ["volcanic", "alluvial", "clay-limestone", "moraine"],
        "soil_details": "Soave has volcanic basalt soils from ancient eruptions; Valpolicella features limestone-rich glacial moraine; Prosecco hills have clay-sandstone marine sediments; Colli Euganei are volcanic",
        "vineyard_area_ha": 87000,
        "elevation_range": "10-700m",
        "annual_rainfall_mm": 850,
        "docg_count": 14,
        "doc_count": 29,
        "key_grapes": ["Glera", "Corvina", "Garganega", "Rondinella", "Pinot Grigio", "Trebbiano di Soave"],
        "production_hl": 11670000,
    },
    {
        "name": "Lombardy",
        "italian_name": "Lombardia",
        "climate": "continental",
        "climate_details": "Cold winters and warm summers; Franciacorta benefits from temperature moderation by Lake Iseo; Valtellina has an Alpine climate with steep south-facing terraced vineyards",
        "soil_types": ["glacial moraine", "limestone", "clay", "gravel"],
        "soil_details": "Franciacorta has glacial moraine soils rich in minerals; Oltrepò Pavese features clay-limestone; Valtellina has sandy-silty soils on steep terraces at 300-700m elevation",
        "vineyard_area_ha": 24000,
        "elevation_range": "80-700m",
        "annual_rainfall_mm": 800,
        "docg_count": 5,
        "doc_count": 21,
        "key_grapes": ["Nebbiolo", "Chardonnay", "Pinot Nero", "Barbera", "Croatina"],
        "production_hl": 1520000,
    },
    {
        "name": "Trentino-Alto Adige",
        "italian_name": "Trentino-Alto Adige",
        "climate": "Alpine continental",
        "climate_details": "Cool Alpine climate with warm, sunny days and cold nights producing excellent diurnal temperature variation; valleys channel cooling winds; winters are cold with significant snowfall",
        "soil_types": ["porphyry", "limestone", "dolomite", "moraine", "gravel"],
        "soil_details": "Alto Adige features decomposed porphyry and volcanic soils; Trentino has limestone and dolomite-derived soils; alluvial gravel in valley floors from ancient glacial deposits",
        "vineyard_area_ha": 15700,
        "elevation_range": "200-1000m",
        "annual_rainfall_mm": 850,
        "docg_count": 1,
        "doc_count": 10,
        "key_grapes": ["Pinot Grigio", "Gewürztraminer", "Schiava", "Lagrein", "Teroldego", "Müller-Thurgau"],
        "production_hl": 1150000,
    },
    {
        "name": "Friuli Venezia Giulia",
        "italian_name": "Friuli Venezia Giulia",
        "climate": "continental with maritime influence",
        "climate_details": "The Adriatic Sea and Julian Alps create a unique microclimate; warm breezes from the sea moderate temperatures while Alpine winds provide cooling; Collio and Colli Orientali have the best diurnal range",
        "soil_types": ["ponca", "flysch", "marl", "alluvial gravel"],
        "soil_details": "Collio and Colli Orientali feature ponca (compressed layers of sandstone and marl from the Eocene era); Grave del Friuli has alluvial gravelly plains; Carso has iron-rich red soils on limestone karst",
        "vineyard_area_ha": 27000,
        "elevation_range": "20-400m",
        "annual_rainfall_mm": 1200,
        "docg_count": 4,
        "doc_count": 12,
        "key_grapes": ["Friulano", "Ribolla Gialla", "Pinot Grigio", "Sauvignon Blanc", "Refosco dal Peduncolo Rosso", "Schioppettino"],
        "production_hl": 1830000,
    },
    {
        "name": "Emilia-Romagna",
        "italian_name": "Emilia-Romagna",
        "climate": "continental",
        "climate_details": "Hot summers and cold winters on the Po River plain; Apennine foothills in Romagna enjoy more temperate conditions with better diurnal variation; frequent fog on the plains",
        "soil_types": ["alluvial clay", "sand", "limestone", "calcareous clay"],
        "soil_details": "The Po plain features deep alluvial soils; Romagna hills have calcareous clay and limestone at moderate elevation; Colli Piacentini have sandstone and clay",
        "vineyard_area_ha": 52000,
        "elevation_range": "10-500m",
        "annual_rainfall_mm": 700,
        "docg_count": 2,
        "doc_count": 18,
        "key_grapes": ["Lambrusco", "Sangiovese", "Trebbiano Romagnolo", "Albana", "Pignoletto", "Malvasia"],
        "production_hl": 7100000,
    },
    {
        "name": "Campania",
        "italian_name": "Campania",
        "climate": "Mediterranean",
        "climate_details": "Hot dry summers and mild winters along the coast; higher inland areas like Irpinia and Taurasi have a more continental climate with significant diurnal temperature variation and cooler nights",
        "soil_types": ["volcanic", "tufo", "clay-limestone", "pumice"],
        "soil_details": "Vesuvius area has rich volcanic soils with pumice and ash; Irpinia has clay-limestone at 400-700m; Ischia and Campi Flegrei have volcanic tufo; Aglianico del Taburno grows on calcareous clay",
        "vineyard_area_ha": 23000,
        "elevation_range": "50-700m",
        "annual_rainfall_mm": 850,
        "docg_count": 4,
        "doc_count": 15,
        "key_grapes": ["Aglianico", "Fiano", "Greco", "Falanghina", "Piedirosso", "Coda di Volpe"],
        "production_hl": 1330000,
    },
    {
        "name": "Sicily",
        "italian_name": "Sicilia",
        "climate": "Mediterranean",
        "climate_details": "Hot dry summers and mild winters; Mount Etna creates a unique high-altitude microclimate with volcanic influence; western Sicily is hotter and drier than the eastern slopes",
        "soil_types": ["volcanic", "clay", "limestone", "sand", "calcareous"],
        "soil_details": "Etna has dark volcanic soils rich in minerals at elevations up to 1000m; western Sicily features clay and limestone; Pantelleria has volcanic soils; Marsala area has calcareous clay",
        "vineyard_area_ha": 97000,
        "elevation_range": "50-1000m",
        "annual_rainfall_mm": 500,
        "docg_count": 1,
        "doc_count": 23,
        "key_grapes": ["Nero d'Avola", "Grillo", "Catarratto", "Nerello Mascalese", "Carricante", "Zibibbo"],
        "production_hl": 2740000,
    },
    {
        "name": "Sardinia",
        "italian_name": "Sardegna",
        "climate": "Mediterranean",
        "climate_details": "Warm dry climate moderated by sea breezes (the mistral wind); higher inland areas around Barbagia have a more continental character with cooler temperatures",
        "soil_types": ["granite", "schist", "sand", "limestone", "volcanic"],
        "soil_details": "Gallura in the northeast has decomposed granite soils ideal for Vermentino; Sulcis has sandy soils for Carignano; central highlands have schist and volcanic soils",
        "vineyard_area_ha": 26000,
        "elevation_range": "20-700m",
        "annual_rainfall_mm": 500,
        "docg_count": 1,
        "doc_count": 17,
        "key_grapes": ["Cannonau", "Vermentino", "Carignano", "Monica", "Nuragus", "Bovale"],
        "production_hl": 530000,
    },
    {
        "name": "Puglia",
        "italian_name": "Puglia",
        "climate": "Mediterranean",
        "climate_details": "Hot summers and mild winters with low rainfall; the Adriatic coast provides some cooling; inland Murgia plateau has slightly more continental nights",
        "soil_types": ["calcareous", "clay", "iron-rich red earth", "tufo"],
        "soil_details": "Salento has iron-rich red terra rossa over limestone; Gioia del Colle has calcareous clay at higher elevation; Castel del Monte features calcareous tufo; Daunia has alluvial clay",
        "vineyard_area_ha": 87000,
        "elevation_range": "10-500m",
        "annual_rainfall_mm": 550,
        "docg_count": 4,
        "doc_count": 28,
        "key_grapes": ["Primitivo", "Negroamaro", "Nero di Troia", "Bombino Bianco", "Bombino Nero", "Verdeca"],
        "production_hl": 7600000,
    },
    {
        "name": "Abruzzo",
        "italian_name": "Abruzzo",
        "climate": "Mediterranean with continental influence",
        "climate_details": "Adriatic coast has moderate temperatures; inland areas sheltered by the Apennines have colder winters and hot summers; Gran Sasso massif moderates summer heat with cool mountain air",
        "soil_types": ["clay", "limestone", "alluvial", "sandy clay"],
        "soil_details": "Colline Teramane has calcareous clay at moderate elevation; coastal hills feature sandy clay; inland valleys have alluvial soils; the best Montepulciano d'Abruzzo sites are on calcareous clay hillsides",
        "vineyard_area_ha": 32000,
        "elevation_range": "50-600m",
        "annual_rainfall_mm": 650,
        "docg_count": 1,
        "doc_count": 8,
        "key_grapes": ["Montepulciano", "Trebbiano d'Abruzzo", "Pecorino", "Cococciola", "Passerina"],
        "production_hl": 2250000,
    },
    {
        "name": "Marche",
        "italian_name": "Marche",
        "climate": "Mediterranean with Adriatic influence",
        "climate_details": "Adriatic breezes moderate summer heat; the Apennines provide a western barrier creating a rain shadow; hillside vineyards benefit from good sun exposure and natural drainage",
        "soil_types": ["calcareous clay", "sandstone", "marl", "limestone"],
        "soil_details": "Verdicchio zone has calcareous clay and limestone at 200-500m; Conero features limestone-clay near the Adriatic; Offida has sandy marl soils",
        "vineyard_area_ha": 17000,
        "elevation_range": "50-600m",
        "annual_rainfall_mm": 750,
        "docg_count": 5,
        "doc_count": 15,
        "key_grapes": ["Verdicchio", "Montepulciano", "Sangiovese", "Pecorino", "Lacrima", "Passerina"],
        "production_hl": 920000,
    },
    {
        "name": "Umbria",
        "italian_name": "Umbria",
        "climate": "continental with Mediterranean influence",
        "climate_details": "Landlocked region with warm summers and cold winters; Lake Trasimeno moderates temperatures in the northwest; vineyards at moderate elevation enjoy good diurnal variation",
        "soil_types": ["clay", "limestone", "volcanic tufo", "sand"],
        "soil_details": "Orvieto has volcanic tufo soils; Montefalco features clay-limestone at 250-450m; Torgiano has alluvial soils near the Tiber; Spoleto area has calcareous clay",
        "vineyard_area_ha": 13000,
        "elevation_range": "100-500m",
        "annual_rainfall_mm": 800,
        "docg_count": 2,
        "doc_count": 13,
        "key_grapes": ["Sagrantino", "Sangiovese", "Grechetto", "Trebbiano Spoletino", "Procanico"],
        "production_hl": 780000,
    },
    {
        "name": "Lazio",
        "italian_name": "Lazio",
        "climate": "Mediterranean",
        "climate_details": "Warm coastal climate with hot dry summers; volcanic hill areas around the Alban Hills and Castelli Romani have cooler microclimates from elevation and volcanic lakes",
        "soil_types": ["volcanic tufo", "peperino", "clay", "sand"],
        "soil_details": "Castelli Romani and Frascati zones sit on volcanic tufo from ancient eruptions; Olevano Romano has calcareous clay; Cesanese del Piglio grows on volcanic soils at 200-600m",
        "vineyard_area_ha": 21000,
        "elevation_range": "50-600m",
        "annual_rainfall_mm": 750,
        "docg_count": 3,
        "doc_count": 27,
        "key_grapes": ["Malvasia Puntinata", "Trebbiano", "Cesanese", "Bellone", "Grechetto"],
        "production_hl": 1550000,
    },
    {
        "name": "Calabria",
        "italian_name": "Calabria",
        "climate": "Mediterranean",
        "climate_details": "Hot dry coastal climate with cooling sea breezes on three sides; mountainous interior with the Sila and Aspromonte ranges provides higher-altitude sites with continental character",
        "soil_types": ["clay", "granite", "limestone", "sand"],
        "soil_details": "Cirò has calcareous clay soils; Sila plateau provides cooler high-altitude sites; coastal areas have sandy clay; Savuto valley features alluvial soils",
        "vineyard_area_ha": 10000,
        "elevation_range": "50-700m",
        "annual_rainfall_mm": 600,
        "docg_count": 1,
        "doc_count": 9,
        "key_grapes": ["Gaglioppo", "Greco Nero", "Magliocco", "Greco Bianco", "Mantonico"],
        "production_hl": 260000,
    },
    {
        "name": "Basilicata",
        "italian_name": "Basilicata",
        "climate": "continental",
        "climate_details": "High-altitude interior with cold winters and warm summers; the Vulture area, an extinct volcano, has a unique microclimate with excellent diurnal temperature variation at 400-700m",
        "soil_types": ["volcanic", "clay", "tufo", "limestone"],
        "soil_details": "Aglianico del Vulture grows on dark volcanic soils from the extinct Monte Vulture at 200-700m elevation; soils are rich in minerals including potassium and phosphorus",
        "vineyard_area_ha": 4000,
        "elevation_range": "200-700m",
        "annual_rainfall_mm": 600,
        "docg_count": 1,
        "doc_count": 4,
        "key_grapes": ["Aglianico", "Malvasia Bianca di Basilicata", "Moscato"],
        "production_hl": 96000,
    },
    {
        "name": "Molise",
        "italian_name": "Molise",
        "climate": "continental",
        "climate_details": "Mountainous inland climate with cold winters and warm summers; Adriatic coast has more moderate temperatures; vineyards are primarily on hillsides at moderate elevation",
        "soil_types": ["clay", "limestone", "sand"],
        "soil_details": "Calcareous clay on hillsides at 200-500m; some alluvial soils in river valleys; Biferno valley features clay-limestone with good drainage",
        "vineyard_area_ha": 5000,
        "elevation_range": "100-600m",
        "annual_rainfall_mm": 650,
        "docg_count": 0,
        "doc_count": 4,
        "key_grapes": ["Montepulciano", "Tintilia", "Trebbiano", "Falanghina"],
        "production_hl": 280000,
    },
    {
        "name": "Liguria",
        "italian_name": "Liguria",
        "climate": "Mediterranean",
        "climate_details": "Mild coastal climate protected by the Apennines from cold northern winds; steep terraced vineyards face the sea; Cinque Terre vineyards are among Italy's most dramatic",
        "soil_types": ["schist", "clay", "limestone", "sandy"],
        "soil_details": "Cinque Terre has thin schist soils on steep terraces; Colli di Luni features clay-limestone; Riviera Ligure di Ponente has calcareous sandy soils; very limited flat land forces heroic viticulture",
        "vineyard_area_ha": 2000,
        "elevation_range": "20-500m",
        "annual_rainfall_mm": 900,
        "docg_count": 0,
        "doc_count": 8,
        "key_grapes": ["Vermentino", "Pigato", "Rossese", "Bosco", "Albarola", "Ormeasco"],
        "production_hl": 60000,
    },
    {
        "name": "Valle d'Aosta",
        "italian_name": "Valle d'Aosta",
        "climate": "Alpine continental",
        "climate_details": "Italy's smallest and highest wine region; Alpine climate with extreme diurnal variation; south-facing terraces on the Dora Baltea valley capture maximum sunlight; some of Europe's highest vineyards",
        "soil_types": ["moraine", "granite", "schist", "sand"],
        "soil_details": "Glacial moraine and alluvial soils in the Dora Baltea valley; steep terraces at 500-1200m with thin granitic and schistose soils; among the highest vineyards in Europe",
        "vineyard_area_ha": 400,
        "elevation_range": "400-1200m",
        "annual_rainfall_mm": 550,
        "docg_count": 0,
        "doc_count": 1,
        "key_grapes": ["Petit Rouge", "Fumin", "Prié Blanc", "Petite Arvine", "Nebbiolo"],
        "production_hl": 18000,
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — DOCG Supplement (climate, soil, elevation, communes, subzones)
# Supplements italy.py DOCG_DATABASE which covers grapes, aging, yields
# ═══════════════════════════════════════════════════════════════════════════════

DOCG_SUPPLEMENT = {
    # ── Piedmont ──
    "Barolo": {
        "region": "Piedmont",
        "climate": "continental with fog common in autumn",
        "soil_types": ["calcareous marl", "clay-limestone", "sand-clay"],
        "soil_details": "Tortonian-era soils (blue-gray calcareous marl, higher sand, limestone) dominate in Serralunga d'Alba and Monforte d'Alba; Helvetian-era soils (sandier, more calcareous) in La Morra and Barolo commune",
        "elevation_range": "170-540m",
        "vineyard_area_ha": 2100,
        "communes": ["Barolo", "La Morra", "Monforte d'Alba", "Serralunga d'Alba", "Castiglione Falletto", "Novello", "Grinzane Cavour", "Verduno", "Diano d'Alba", "Cherasco", "Roddi"],
        "subzones_type": "MeGA",
        "subzones_count": 181,
        "notable_subzones": ["Cannubi", "Brunate", "Rocche dell'Annunziata", "Bussia", "Ginestra", "Lazzarito", "Vigna Rionda", "Monprivato", "Villero", "Francia"],
    },
    "Barbaresco": {
        "region": "Piedmont",
        "climate": "continental, slightly warmer than Barolo due to lower average elevation",
        "soil_types": ["calcareous marl", "sand-limestone", "clay"],
        "soil_details": "Predominantly Tortonian-era calcareous marl and sandy limestone; soils are generally more calcareous and less compact than Barolo",
        "elevation_range": "150-400m",
        "vineyard_area_ha": 700,
        "communes": ["Barbaresco", "Neive", "Treiso", "San Rocco Seno d'Elvio"],
        "subzones_type": "MeGA",
        "subzones_count": 66,
        "notable_subzones": ["Asili", "Rabajà", "Pajé", "Pora", "Rio Sordo", "Montestefano", "Gallina", "Santo Stefano", "Montefico", "Ovello"],
    },
    "Asti": {
        "region": "Piedmont",
        "climate": "continental with warm summers ideal for aromatic grapes",
        "soil_types": ["calcareous clay", "marl", "sand"],
        "soil_details": "Calcareous clay and marl on hillsides in the provinces of Asti, Cuneo, and Alessandria",
        "elevation_range": "150-500m",
        "vineyard_area_ha": 9700,
        "communes": [],
        "subzones_type": None,
        "subzones_count": 0,
    },
    "Gavi": {
        "region": "Piedmont",
        "climate": "continental with maritime influence from proximity to Liguria",
        "soil_types": ["clay-limestone", "red clay", "marl"],
        "soil_details": "Red clay soils and calcareous marl on the hills around Gavi in the province of Alessandria; maritime influence from the Ligurian coast brings unique character",
        "elevation_range": "180-450m",
        "vineyard_area_ha": 1500,
        "communes": ["Gavi", "Bosio", "Carrosio", "Francavilla Bisio", "Novi Ligure", "Parodi Ligure", "Pasturana", "San Cristoforo", "Serravalle Scrivia", "Tassarolo", "Capriata d'Orba"],
        "subzones_type": None,
        "subzones_count": 0,
    },
    "Ghemme": {
        "region": "Piedmont",
        "climate": "continental with Alpine influence",
        "soil_types": ["glacial moraine", "clay", "gravel"],
        "soil_details": "Glacial moraine soils with gravel and clay on the foothills of Monte Rosa; differs from Langhe soils, producing a distinctive expression of Nebbiolo",
        "elevation_range": "200-450m",
        "vineyard_area_ha": 60,
        "communes": ["Ghemme", "Romagnano Sesia"],
    },
    "Gattinara": {
        "region": "Piedmont",
        "climate": "continental with cold Alpine winters",
        "soil_types": ["volcanic porphyry", "granite", "clay"],
        "soil_details": "Distinctive volcanic porphyry and granitic soils from ancient eruptions; these acidic soils differ markedly from the calcareous soils of the Langhe",
        "elevation_range": "250-480m",
        "vineyard_area_ha": 100,
        "communes": ["Gattinara"],
    },
    "Roero": {
        "region": "Piedmont",
        "climate": "continental with good diurnal variation",
        "soil_types": ["sand", "marl", "calcareous clay"],
        "soil_details": "Sandy soils with marine fossil deposits on the left bank of the Tanaro River; soils are lighter and sandier than the neighboring Langhe, producing more aromatic and earlier-drinking wines",
        "elevation_range": "150-400m",
        "vineyard_area_ha": 1200,
        "communes": ["Canale", "Vezza d'Alba", "Monteu Roero", "Montaldo Roero", "Santo Stefano Roero", "Castellinaldo", "Govone", "Priocca", "Corneliano d'Alba", "Piobesi d'Alba", "Baldissero d'Alba"],
        "subzones_type": "MeGA",
        "subzones_count": 134,
    },
    "Dogliani": {
        "region": "Piedmont",
        "climate": "continental",
        "soil_types": ["calcareous marl", "clay", "limestone"],
        "soil_details": "White calcareous marl and clay soils on the hills around Dogliani in the southern Langhe",
        "elevation_range": "250-600m",
        "vineyard_area_ha": 850,
        "communes": ["Dogliani", "Farigliano", "Rocca Ciglié", "Belvedere Langhe", "Bastia Mondovì", "Cissone", "Cigliè", "Monchiero", "Roddino", "Somano"],
    },
    "Nizza": {
        "region": "Piedmont",
        "climate": "continental with warm summers",
        "soil_types": ["calcareous marl", "clay-limestone", "sand"],
        "soil_details": "Calcareous marl and clay-limestone soils in the Monferrato hills around Nizza Monferrato; similar geological age to Barolo but with distinct mineral composition",
        "elevation_range": "150-400m",
        "vineyard_area_ha": 230,
        "communes": ["Nizza Monferrato", "Castelnuovo Calcea", "Agliano Terme", "Belveglio", "Bruno", "Calamandrana", "Castel Boglione", "Castel Rocchero", "Cortiglione", "Incisa Scapaccino", "Moasca", "Mombaruzzo", "Mombercelli", "San Marzano Oliveto", "Vaglio Serra", "Vinchio"],
    },
    "Barbera d'Asti": {
        "region": "Piedmont",
        "climate": "continental",
        "soil_types": ["calcareous marl", "clay", "sand"],
        "soil_details": "Calcareous marl and clay in the Monferrato and Langhe Astigiane; varied soils contribute to diverse expressions of Barbera",
        "elevation_range": "150-400m",
        "vineyard_area_ha": 4500,
    },
    "Erbaluce di Caluso": {
        "region": "Piedmont",
        "climate": "continental with Alpine cooling",
        "soil_types": ["glacial moraine", "gravel", "sand"],
        "soil_details": "Glacial moraine soils with gravel and sandy deposits in the Canavese area north of Turin; the moraine amphitheater of Ivrea influences the microclimate",
        "elevation_range": "250-450m",
        "vineyard_area_ha": 200,
        "communes": ["Caluso", "Carema", "Borgomasino", "Cossano Canavese"],
    },
    "Alta Langa": {
        "region": "Piedmont",
        "climate": "cool continental with significant altitude influence",
        "soil_types": ["calcareous marl", "limestone", "clay"],
        "soil_details": "High-altitude Langhe hills with calcareous marl and limestone soils; cool conditions ideal for traditional method sparkling wine production",
        "elevation_range": "250-800m",
        "vineyard_area_ha": 300,
    },
    "Brachetto d'Acqui": {
        "region": "Piedmont",
        "climate": "continental",
        "soil_types": ["calcareous clay", "marl", "sand"],
        "soil_details": "Clay and marl soils in the hills around Acqui Terme in the province of Alessandria",
        "elevation_range": "150-400m",
        "vineyard_area_ha": 120,
    },
    "Ruchè di Castagnole Monferrato": {
        "region": "Piedmont",
        "climate": "continental with warm summers",
        "soil_types": ["calcareous marl", "clay-sand"],
        "soil_details": "Calcareous marl and clay-sand mix on the Monferrato hills around Castagnole Monferrato",
        "elevation_range": "200-350m",
        "vineyard_area_ha": 130,
        "communes": ["Castagnole Monferrato", "Grana", "Montemagno", "Portacomaro", "Refrancore", "Scurzolengo", "Viarigi"],
    },
    "Terre Alfieri": {
        "region": "Piedmont",
        "climate": "continental",
        "soil_types": ["sandy marl", "calcareous clay"],
        "soil_details": "Sandy marl soils in the transition zone between Roero and Monferrato; newest Piedmont DOCG (2020)",
        "elevation_range": "200-400m",
        "vineyard_area_ha": 80,
    },

    # ── Tuscany ──
    "Brunello di Montalcino": {
        "region": "Tuscany",
        "climate": "warm Mediterranean, the warmest and driest Tuscan wine zone",
        "soil_types": ["clay", "limestone", "alberese", "galestro", "sand"],
        "soil_details": "Northern slopes have heavier galestro and clay producing more structured wines; southern slopes have sandier, warmer soils; alberese (calcareous rock) provides excellent drainage throughout",
        "elevation_range": "150-500m",
        "vineyard_area_ha": 2100,
        "communes": ["Montalcino"],
        "subzones_type": None,
        "subzones_count": 0,
        "notable_subzones": [],
    },
    "Chianti Classico": {
        "region": "Tuscany",
        "climate": "Mediterranean with continental influence at higher elevations",
        "soil_types": ["galestro", "alberese", "sandstone", "clay"],
        "soil_details": "Galestro (crumbly schist-like marl) dominates around Radda and Gaiole; alberese (calcareous rock) is more common at lower elevations; Panzano in Chianti's Conca d'Oro has ideal sun exposure",
        "elevation_range": "200-600m",
        "vineyard_area_ha": 7200,
        "communes": ["Greve in Chianti", "Radda in Chianti", "Gaiole in Chianti", "Castellina in Chianti", "Castelnuovo Berardenga", "San Casciano in Val di Pesa", "Barberino Tavarnelle", "Poggibonsi"],
        "subzones_type": "UGA",
        "subzones_count": 11,
        "notable_subzones": ["Greve", "Panzano", "Radda", "Gaiole", "Castellina", "Castelnuovo Berardenga", "San Casciano", "Lamole", "Montefioralle", "San Donato in Poggio", "Vagliagli"],
    },
    "Vino Nobile di Montepulciano": {
        "region": "Tuscany",
        "climate": "Mediterranean continental with cooler nights than Montalcino",
        "soil_types": ["clay", "sand", "limestone", "tufo"],
        "soil_details": "Varied soils around the town of Montepulciano at 250-600m; clay and sand dominate, with some tufo (volcanic tuff) contributing to minerality",
        "elevation_range": "250-600m",
        "vineyard_area_ha": 1300,
        "communes": ["Montepulciano"],
    },
    "Vernaccia di San Gimignano": {
        "region": "Tuscany",
        "climate": "Mediterranean",
        "soil_types": ["sandy clay", "tufo", "limestone"],
        "soil_details": "Sandy clay and yellow tufo soils around the medieval towers of San Gimignano; Italy's first DOC (1966), elevated to DOCG in 1993",
        "elevation_range": "200-400m",
        "vineyard_area_ha": 740,
        "communes": ["San Gimignano"],
    },
    "Carmignano": {
        "region": "Tuscany",
        "climate": "Mediterranean with Apennine cooling",
        "soil_types": ["clay", "sand", "limestone", "gravel"],
        "soil_details": "Varied soils on the hills of Carmignano near Prato; one of the first zones in Italy to officially sanction Cabernet Sauvignon in blends (since the Medici era)",
        "elevation_range": "100-400m",
        "vineyard_area_ha": 270,
        "communes": ["Carmignano", "Poggio a Caiano"],
    },
    "Morellino di Scansano": {
        "region": "Tuscany",
        "climate": "Mediterranean, warmer and drier than Chianti",
        "soil_types": ["volcanic", "clay", "sand", "limestone"],
        "soil_details": "Varied soils in the Maremma area with volcanic elements; lower and warmer than central Tuscany; Sangiovese here is locally called Morellino",
        "elevation_range": "50-500m",
        "vineyard_area_ha": 1500,
        "communes": ["Scansano", "Magliano in Toscana", "Manciano", "Campagnatico", "Roccalbegna", "Semproniano"],
    },
    "Chianti": {
        "region": "Tuscany",
        "climate": "Mediterranean to continental depending on subzone",
        "soil_types": ["clay", "galestro", "alberese", "sand", "limestone"],
        "soil_details": "Diverse soils across 8 subzones; higher-elevation subzones like Rufina have cooler continental conditions; lower areas near Pisa have more maritime influence",
        "elevation_range": "100-600m",
        "vineyard_area_ha": 15000,
        "subzones_type": "sottozona",
        "subzones_count": 8,
        "notable_subzones": ["Rufina", "Colli Senesi", "Colli Fiorentini", "Colli Aretini", "Colline Pisane", "Montalbano", "Montespertoli", "Colli della Toscana Centrale"],
    },
    "Suvereto": {
        "region": "Tuscany",
        "climate": "Mediterranean with maritime influence from the Tyrrhenian Sea",
        "soil_types": ["clay", "sand", "gravel", "limestone"],
        "soil_details": "Varied soils in the Val di Cornia coastal area; benefits from sea breezes and warm growing conditions for Cabernet Sauvignon, Merlot, and Sangiovese",
        "elevation_range": "50-300m",
        "vineyard_area_ha": 200,
        "communes": ["Suvereto"],
    },
    "Val di Cornia Rosso": {
        "region": "Tuscany",
        "climate": "Mediterranean with maritime influence",
        "soil_types": ["sandy clay", "limestone", "gravel"],
        "soil_details": "Coastal Maremma soils similar to Bolgheri but further south",
        "elevation_range": "50-250m",
        "vineyard_area_ha": 100,
    },
    "Elba Aleatico Passito": {
        "region": "Tuscany",
        "climate": "Mediterranean island climate",
        "soil_types": ["granite", "schist", "iron-rich"],
        "soil_details": "Island of Elba features mineral-rich soils from ancient mining deposits, including iron-rich earth; unique microclimate for passito-style Aleatico",
        "elevation_range": "50-300m",
        "vineyard_area_ha": 30,
    },

    # ── Veneto ──
    "Amarone della Valpolicella": {
        "region": "Veneto",
        "climate": "temperate sub-Mediterranean moderated by Lake Garda",
        "soil_types": ["limestone", "clay-limestone", "volcanic basalt"],
        "soil_details": "Classico zone has limestone-rich soils on hillsides; volcanic basalt found in some eastern areas; glacial moraine deposits provide variety; the appassimento method requires well-ventilated drying lofts",
        "elevation_range": "100-500m",
        "vineyard_area_ha": 8300,
        "communes": ["Fumane", "Marano di Valpolicella", "Negrar", "San Pietro in Cariano", "Sant'Ambrogio di Valpolicella"],
        "subzones_type": "UGA",
        "subzones_count": 11,
        "notable_subzones": [],
    },
    "Soave Superiore": {
        "region": "Veneto",
        "climate": "temperate with good diurnal variation",
        "soil_types": ["volcanic basalt", "limestone", "tufo"],
        "soil_details": "Classico zone features dark volcanic basalt soils from ancient eruptions mixed with calcareous tufo; these volcanic soils give Garganega distinctive minerality",
        "elevation_range": "40-350m",
        "vineyard_area_ha": 1700,
        "communes": ["Soave", "Monteforte d'Alpone"],
    },
    "Recioto di Soave": {
        "region": "Veneto",
        "climate": "temperate with dry autumn winds for grape drying",
        "soil_types": ["volcanic basalt", "limestone"],
        "soil_details": "Same volcanic soils as Soave Superiore; grapes are dried on mats (appassimento) for 3-6 months before pressing",
        "elevation_range": "40-350m",
        "vineyard_area_ha": 150,
    },
    "Recioto della Valpolicella": {
        "region": "Veneto",
        "climate": "temperate sub-Mediterranean",
        "soil_types": ["limestone", "clay-limestone"],
        "soil_details": "Same terroir as Amarone; Recioto is the sweet counterpart made from the same dried grapes but with residual sugar retained",
        "elevation_range": "100-500m",
        "vineyard_area_ha": 200,
    },
    "Conegliano Valdobbiadene Prosecco Superiore": {
        "region": "Veneto",
        "climate": "temperate continental with Alpine influence",
        "soil_types": ["clay-sandstone", "marl", "moraine"],
        "soil_details": "UNESCO World Heritage hills with steep hogback ridges (ciglioni) of marine-origin clay-sandstone; Cartizze sub-zone has the most prized terroir at 300m with morainic soils",
        "elevation_range": "50-500m",
        "vineyard_area_ha": 6800,
        "communes": ["Conegliano", "Valdobbiadene"],
        "subzones_type": "rive",
        "subzones_count": 43,
        "notable_subzones": ["Cartizze", "Rive di Col San Martino", "Rive di Santo Stefano", "Rive di Refrontolo"],
    },
    "Colli di Conegliano": {
        "region": "Veneto",
        "climate": "temperate continental",
        "soil_types": ["clay", "sandstone", "marl"],
        "soil_details": "Clay and sandstone on the hills near Conegliano; cooler than the plains",
        "elevation_range": "100-400m",
        "vineyard_area_ha": 200,
    },
    "Bagnoli Friularo": {
        "region": "Veneto",
        "climate": "continental with Adriatic influence",
        "soil_types": ["alluvial clay", "silt", "sand"],
        "soil_details": "Flat alluvial soils of the Po delta near Padua; Friularo (Raboso Piave) is a late-ripening variety requiring long hang time",
        "elevation_range": "0-20m",
        "vineyard_area_ha": 50,
    },
    "Piave Malanotte": {
        "region": "Veneto",
        "climate": "continental",
        "soil_types": ["alluvial gravel", "clay", "sand"],
        "soil_details": "Gravel and alluvial soils of the Piave river plain; Raboso Piave grapes are partially dried before vinification",
        "elevation_range": "10-50m",
        "vineyard_area_ha": 100,
    },
    "Montello Rosso": {
        "region": "Veneto",
        "climate": "temperate with Alpine influence",
        "soil_types": ["clay-limestone", "gravel"],
        "soil_details": "Montello hill has calcareous clay with good drainage; one of Veneto's newest DOCGs (2011)",
        "elevation_range": "100-350m",
        "vineyard_area_ha": 90,
    },
    "Asolo Prosecco Superiore": {
        "region": "Veneto",
        "climate": "temperate continental with Alpine influence",
        "soil_types": ["clay", "sand", "moraine"],
        "soil_details": "Morainic hills around Asolo near the base of the Dolomites; slightly different character from Conegliano Valdobbiadene",
        "elevation_range": "100-450m",
        "vineyard_area_ha": 2000,
    },
    "Lison": {
        "region": "Veneto",
        "climate": "temperate continental with Adriatic influence",
        "soil_types": ["alluvial clay", "silt"],
        "soil_details": "Rich alluvial soils of the eastern Veneto plain near the Friuli border",
        "elevation_range": "0-30m",
        "vineyard_area_ha": 100,
    },

    # ── Lombardy ──
    "Franciacorta": {
        "region": "Lombardy",
        "climate": "temperate continental moderated by Lake Iseo",
        "soil_types": ["glacial moraine", "gravel", "sand", "clay"],
        "soil_details": "Ancient glacial moraine deposits rich in minerals; Lake Iseo moderates temperature extremes; soils range from sandy-gravelly to heavier clay depending on position",
        "elevation_range": "150-400m",
        "vineyard_area_ha": 2900,
        "communes": ["Erbusco", "Corte Franca", "Adro", "Provaglio d'Iseo", "Paderno Franciacorta", "Passirano", "Cellatica", "Gussago", "Rodengo-Saiano", "Ome", "Monticelli Brusati", "Cazzago San Martino"],
    },
    "Valtellina Superiore": {
        "region": "Lombardy",
        "climate": "Alpine with exceptional south-facing exposure",
        "soil_types": ["sandy-silty", "gneiss", "mica-schist"],
        "soil_details": "Steep south-facing terraced vineyards on sandy-silty soils derived from gneiss and mica-schist; terraces (known locally as muretti) are maintained by hand",
        "elevation_range": "300-700m",
        "vineyard_area_ha": 650,
        "subzones_type": "sottozona",
        "subzones_count": 5,
        "notable_subzones": ["Sassella", "Grumello", "Inferno", "Valgella", "Maroggia"],
    },
    "Sforzato di Valtellina": {
        "region": "Lombardy",
        "climate": "Alpine with dry autumn winds ideal for grape drying",
        "soil_types": ["sandy-silty", "gneiss", "mica-schist"],
        "soil_details": "Same steep terraces as Valtellina Superiore; grapes are dried for approximately 3 months before pressing; Lombardy's answer to Amarone using Nebbiolo (locally called Chiavennasca)",
        "elevation_range": "300-700m",
        "vineyard_area_ha": 100,
    },
    "Oltrepò Pavese Metodo Classico": {
        "region": "Lombardy",
        "climate": "continental with cool nights at higher elevations",
        "soil_types": ["clay-limestone", "marl", "gravel"],
        "soil_details": "Apennine foothills south of Pavia with clay-limestone and marl; one of Italy's most important areas for Pinot Nero used in traditional method sparkling wines",
        "elevation_range": "100-500m",
        "vineyard_area_ha": 1500,
    },
    "Moscato di Scanzo": {
        "region": "Lombardy",
        "climate": "temperate continental",
        "soil_types": ["limestone", "clay", "marl"],
        "soil_details": "Very small DOCG around Scanzorosciate near Bergamo; Italy's smallest DOCG by production volume; passito-style dessert wine from Moscato di Scanzo grapes",
        "elevation_range": "250-350m",
        "vineyard_area_ha": 30,
    },

    # ── Trentino-Alto Adige ──
    "Trento": {
        "region": "Trentino-Alto Adige",
        "climate": "Alpine continental with exceptional diurnal variation",
        "soil_types": ["limestone", "porphyry", "alluvial gravel"],
        "soil_details": "Vineyards at altitude on limestone and porphyry soils; the Adige Valley channels cool Alpine air creating ideal conditions for traditional method sparkling wine (Trentodoc)",
        "elevation_range": "200-800m",
        "vineyard_area_ha": 1000,
    },

    # ── Friuli Venezia Giulia ──
    "Ramandolo": {
        "region": "Friuli Venezia Giulia",
        "climate": "pre-Alpine with humid conditions",
        "soil_types": ["marl", "flysch", "clay"],
        "soil_details": "Steep south-facing slopes of flysch and marl around the hamlet of Ramandolo; produces sweet wines from Verduzzo Friulano grapes dried naturally",
        "elevation_range": "200-400m",
        "vineyard_area_ha": 40,
    },
    "Colli Orientali del Friuli Picolit": {
        "region": "Friuli Venezia Giulia",
        "climate": "temperate with Alpine and Adriatic influence",
        "soil_types": ["ponca", "flysch", "marl"],
        "soil_details": "Ponca soils (alternating layers of sandstone and marl from the Eocene era) on steep hillsides; Picolit is notoriously low-yielding due to floral abortion",
        "elevation_range": "100-350m",
        "vineyard_area_ha": 30,
    },
    "Rosazzo": {
        "region": "Friuli Venezia Giulia",
        "climate": "temperate with good sun exposure",
        "soil_types": ["ponca", "marl", "sandstone"],
        "soil_details": "Ponca soils in the Colli Orientali del Friuli; the Rosazzo DOCG is a white blend dominated by Friulano with Sauvignon, Chardonnay, and Pinot Bianco",
        "elevation_range": "100-300m",
        "vineyard_area_ha": 50,
    },
    "Friuli Colli Orientali Picolit": {
        "region": "Friuli Venezia Giulia",
        "climate": "temperate with Alpine influence",
        "soil_types": ["ponca", "flysch", "marl"],
        "soil_details": "Same ponca terroir as the broader Colli Orientali zone; dessert wine from late-harvest Picolit",
        "elevation_range": "100-350m",
        "vineyard_area_ha": 25,
    },

    # ── Emilia-Romagna ──
    "Romagna Albana": {
        "region": "Emilia-Romagna",
        "climate": "continental with Adriatic influence",
        "soil_types": ["calcareous clay", "sand", "limestone"],
        "soil_details": "Hillsides of Romagna between Imola and Rimini; calcareous clay with good sun exposure; first Italian white wine to receive DOCG status (1987)",
        "elevation_range": "100-400m",
        "vineyard_area_ha": 900,
    },
    "Colli Bolognesi Pignoletto": {
        "region": "Emilia-Romagna",
        "climate": "continental with moderate summers",
        "soil_types": ["calcareous clay", "marl", "sandstone"],
        "soil_details": "Hills south of Bologna with calcareous clay and marl; Pignoletto (also known as Grechetto Gentile) is the key white variety",
        "elevation_range": "100-400m",
        "vineyard_area_ha": 300,
    },

    # ── Campania ──
    "Taurasi": {
        "region": "Campania",
        "climate": "continental due to inland mountain elevation",
        "soil_types": ["clay-limestone", "volcanic ash", "tufo"],
        "soil_details": "High-altitude Irpinia area with clay-limestone and volcanic influence; cold winters and warm summers with excellent diurnal variation produce a powerful expression of Aglianico",
        "elevation_range": "400-700m",
        "vineyard_area_ha": 400,
        "communes": ["Taurasi", "Bonito", "Castelfranci", "Castelvetere sul Calore", "Fontanarosa", "Lapio", "Luogosano", "Mirabella Eclano", "Montefalcione", "Montemiletto", "Paternopoli", "Pietradefusi", "Sant'Angelo all'Esca", "San Mango sul Calore", "Torre le Nocelle", "Venticano", "Gesualdo"],
    },
    "Fiano di Avellino": {
        "region": "Campania",
        "climate": "continental due to elevation in Irpinia hills",
        "soil_types": ["clay-limestone", "volcanic", "marl"],
        "soil_details": "Hillside vineyards at 300-700m in the province of Avellino; volcanic mineral influence from ancient eruptions; cool nights preserve Fiano's distinctive aromatic character",
        "elevation_range": "300-700m",
        "vineyard_area_ha": 500,
    },
    "Greco di Tufo": {
        "region": "Campania",
        "climate": "continental at elevation with volcanic soil influence",
        "soil_types": ["volcanic tufo", "clay-limestone", "sulfur-rich"],
        "soil_details": "Vineyards around the town of Tufo on volcanic tufo (tuff) soils at 400-600m; the sulfur-rich soils contribute to the variety's distinctive mineral character",
        "elevation_range": "400-600m",
        "vineyard_area_ha": 300,
    },
    "Aglianico del Taburno": {
        "region": "Campania",
        "climate": "Mediterranean with continental influence from Monte Taburno",
        "soil_types": ["calcareous clay", "tufo", "sand"],
        "soil_details": "Vineyards on the slopes of Monte Taburno in the Sannio area of Benevento province; calcareous clay and tufo soils at moderate elevation",
        "elevation_range": "200-500m",
        "vineyard_area_ha": 200,
    },

    # ── Sicily ──
    "Cerasuolo di Vittoria": {
        "region": "Sicily",
        "climate": "hot Mediterranean",
        "soil_types": ["calcareous clay", "sand", "limestone"],
        "soil_details": "Southeastern Sicily between Ragusa and Vittoria; calcareous sandy soils at low elevation; Sicily's only DOCG; blend of Nero d'Avola and Frappato",
        "elevation_range": "50-250m",
        "vineyard_area_ha": 600,
        "communes": ["Vittoria", "Comiso", "Acate", "Chiaramonte Gulfi", "Ragusa", "Santa Croce Camerina", "Niscemi", "Gela", "Riesi", "Butera", "Mazzarino", "Licodia Eubea", "Caltagirone"],
    },

    # ── Sardinia ──
    "Vermentino di Gallura": {
        "region": "Sardinia",
        "climate": "Mediterranean with strong mistral winds",
        "soil_types": ["decomposed granite", "sand", "quartz"],
        "soil_details": "Gallura's distinctive decomposed granite (granitic arena) soils give Vermentino intense minerality; the mistral wind provides natural disease control but stresses vines",
        "elevation_range": "100-500m",
        "vineyard_area_ha": 1600,
    },

    # ── Puglia ──
    "Castel del Monte Bombino Nero": {
        "region": "Puglia",
        "climate": "Mediterranean with Murgia plateau influence",
        "soil_types": ["calcareous", "tufo", "terra rossa"],
        "soil_details": "Calcareous tufo soils on the Murgia plateau near Castel del Monte at 300-500m; among Puglia's highest vineyards",
        "elevation_range": "300-500m",
        "vineyard_area_ha": 100,
    },
    "Castel del Monte Rosso Riserva": {
        "region": "Puglia",
        "climate": "Mediterranean with Murgia plateau influence",
        "soil_types": ["calcareous", "tufo", "terra rossa"],
        "soil_details": "Same high-altitude Murgia plateau terroir as other Castel del Monte DOCGs",
        "elevation_range": "300-500m",
        "vineyard_area_ha": 100,
    },
    "Castel del Monte Nero di Troia Riserva": {
        "region": "Puglia",
        "climate": "Mediterranean with diurnal variation from altitude",
        "soil_types": ["calcareous", "tufo", "terra rossa"],
        "soil_details": "Nero di Troia (also known as Uva di Troia) on the calcareous Murgia plateau; this indigenous grape thrives in Puglia's warm conditions",
        "elevation_range": "300-500m",
        "vineyard_area_ha": 80,
    },
    "Primitivo di Manduria Dolce Naturale": {
        "region": "Puglia",
        "climate": "hot Mediterranean",
        "soil_types": ["terra rossa", "calcareous", "sand"],
        "soil_details": "Iron-rich red terra rossa over limestone bedrock in the Salento peninsula; dry hot conditions concentrate sugars naturally for this dessert wine",
        "elevation_range": "20-150m",
        "vineyard_area_ha": 50,
    },

    # ── Abruzzo ──
    "Montepulciano d'Abruzzo Colline Teramane": {
        "region": "Abruzzo",
        "climate": "Mediterranean with mountain cooling from Gran Sasso",
        "soil_types": ["calcareous clay", "sand", "alluvial"],
        "soil_details": "Clay-limestone hills in the province of Teramo between the Adriatic Sea and the Gran Sasso massif; sheltered from western weather by the mountains",
        "elevation_range": "100-550m",
        "vineyard_area_ha": 500,
    },

    # ── Marche ──
    "Conero": {
        "region": "Marche",
        "climate": "Mediterranean with Adriatic influence",
        "soil_types": ["clay-limestone", "calcareous"],
        "soil_details": "Monte Conero promontory on the Adriatic coast near Ancona; limestone-clay soils on south-facing slopes; solely Montepulciano variety",
        "elevation_range": "50-400m",
        "vineyard_area_ha": 200,
    },
    "Castelli di Jesi Verdicchio Riserva": {
        "region": "Marche",
        "climate": "continental with Adriatic influence",
        "soil_types": ["calcareous clay", "sandstone", "marl"],
        "soil_details": "Jesi hills with calcareous clay and sandstone at 200-500m; Verdicchio benefits from the thermal excursion between warm days and cool Adriatic-influenced nights",
        "elevation_range": "200-500m",
        "vineyard_area_ha": 1200,
    },
    "Vernaccia di Serrapetrona": {
        "region": "Marche",
        "climate": "continental at inland elevation",
        "soil_types": ["clay", "marl", "limestone"],
        "soil_details": "Mountain vineyards around Serrapetrona in Macerata province; sparkling red wine from partially dried Vernaccia Nera grapes; unique Italian wine type",
        "elevation_range": "300-600m",
        "vineyard_area_ha": 40,
    },
    "Offida": {
        "region": "Marche",
        "climate": "Mediterranean with continental influence",
        "soil_types": ["sandy marl", "clay", "limestone"],
        "soil_details": "Hills around Offida in Ascoli Piceno province; sandy marl and clay for Pecorino (white) and Montepulciano (red)",
        "elevation_range": "200-500m",
        "vineyard_area_ha": 300,
    },

    # ── Umbria ──
    "Montefalco Sagrantino": {
        "region": "Umbria",
        "climate": "continental with warm summers",
        "soil_types": ["clay-limestone", "marl", "sand"],
        "soil_details": "Hillsides around Montefalco at 250-472m; clay-limestone soils retain water well; Sagrantino is one of the most tannic grapes in the world and is indigenous to this area",
        "elevation_range": "250-472m",
        "vineyard_area_ha": 660,
        "communes": ["Montefalco", "Bevagna", "Castel Ritaldi", "Giano dell'Umbria", "Gualdo Cattaneo"],
    },
    "Torgiano Rosso Riserva": {
        "region": "Umbria",
        "climate": "continental with some Mediterranean influence",
        "soil_types": ["alluvial clay", "sand", "gravel"],
        "soil_details": "Alluvial soils near the confluence of the Tiber and Chiascio rivers; historically promoted by the Lungarotti family; Sangiovese-based DOCG since 1990",
        "elevation_range": "200-350m",
        "vineyard_area_ha": 120,
    },

    # ── Lazio ──
    "Frascati Superiore": {
        "region": "Lazio",
        "climate": "Mediterranean with volcanic microclimate",
        "soil_types": ["volcanic tufo", "peperino", "leucitite"],
        "soil_details": "Alban Hills volcanic soils (tufo and peperino) southeast of Rome; ancient volcanic lakes provide unique microclimates; one of Rome's most historic wine zones",
        "elevation_range": "100-500m",
        "vineyard_area_ha": 400,
    },
    "Cannellino di Frascati": {
        "region": "Lazio",
        "climate": "Mediterranean with volcanic microclimate",
        "soil_types": ["volcanic tufo", "peperino"],
        "soil_details": "Same Alban Hills terroir as Frascati Superiore; sweet version (cannellino) from late-harvest grapes affected by noble rot or partial drying",
        "elevation_range": "100-500m",
        "vineyard_area_ha": 30,
    },
    "Cesanese del Piglio": {
        "region": "Lazio",
        "climate": "continental at inland elevation",
        "soil_types": ["volcanic", "clay-limestone", "tufo"],
        "soil_details": "Inland hills southeast of Rome in the Ciociaria area; Cesanese d'Affile and Cesanese Comune grapes on volcanic and clay-limestone soils; Lazio's first red DOCG (2008)",
        "elevation_range": "200-600m",
        "vineyard_area_ha": 100,
    },

    # ── Basilicata ──
    "Aglianico del Vulture Superiore": {
        "region": "Basilicata",
        "climate": "continental at high altitude on an extinct volcano",
        "soil_types": ["volcanic", "tufo", "ash", "pumice"],
        "soil_details": "Dark volcanic soils on the slopes of Monte Vulture, an extinct volcano; rich in potassium, phosphorus, and iron; the high altitude (200-700m) provides dramatic diurnal temperature variation essential for Aglianico's long ripening season",
        "elevation_range": "200-700m",
        "vineyard_area_ha": 1100,
        "communes": ["Barile", "Rapolla", "Rionero in Vulture", "Ripacandida", "Ginestra", "Maschito", "Forenza", "Acerenza", "Melfi", "Atella", "Venosa", "Lavello", "Palazzo San Gervasio", "Banzi", "Genzano di Lucania"],
    },

    # ── Calabria ──
    "Cirò": {
        "region": "Calabria",
        "climate": "hot Mediterranean with cooling sea breezes from the Ionian Sea",
        "soil_types": ["calcareous clay", "sand", "limestone"],
        "soil_details": "Hillsides above the Ionian coast in the province of Crotone; Gaglioppo thrives in the warm climate tempered by marine influence; one of Italy's oldest wine zones with Greek origins",
        "elevation_range": "50-300m",
        "vineyard_area_ha": 400,
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Grape Variety Profiles
# ═══════════════════════════════════════════════════════════════════════════════

GRAPE_VARIETY_DATABASE = [
    # ── Red Varieties ──
    {
        "name": "Nebbiolo",
        "color": "red",
        "origin": "autochthonous",
        "origin_region": "Piedmont",
        "synonyms": ["Spanna", "Chiavennasca", "Picutener", "Pugnet"],
        "characteristics": "High tannin, high acidity, pale garnet color; aromas of tar, roses, red cherry, and dried herbs; extremely age-worthy",
        "key_denominations": ["Barolo", "Barbaresco", "Roero", "Gattinara", "Ghemme", "Valtellina Superiore", "Sforzato di Valtellina", "Carema"],
        "regions_grown": ["Piedmont", "Lombardy", "Valle d'Aosta"],
        "vineyard_area_ha": 5900,
    },
    {
        "name": "Sangiovese",
        "color": "red",
        "origin": "autochthonous",
        "origin_region": "Tuscany",
        "synonyms": ["Brunello", "Prugnolo Gentile", "Morellino", "Sangioveto", "Nielluccio"],
        "characteristics": "Medium to high tannin and acidity; cherry, plum, dried herbs, and earthy notes; Italy's most widely planted red grape",
        "key_denominations": ["Brunello di Montalcino", "Chianti Classico", "Vino Nobile di Montepulciano", "Morellino di Scansano", "Romagna Sangiovese"],
        "regions_grown": ["Tuscany", "Emilia-Romagna", "Umbria", "Marche", "Lazio", "Campania"],
        "vineyard_area_ha": 54000,
    },
    {
        "name": "Aglianico",
        "color": "red",
        "origin": "autochthonous",
        "origin_region": "Campania",
        "synonyms": ["Aglianico del Vulture", "Aglianichello"],
        "characteristics": "High tannin and acidity; dark fruit, spice, leather, and mineral notes; often compared to Nebbiolo for ageability; requires long hang time and warm sites",
        "key_denominations": ["Taurasi", "Aglianico del Vulture Superiore", "Aglianico del Taburno"],
        "regions_grown": ["Campania", "Basilicata", "Puglia", "Calabria", "Molise"],
        "vineyard_area_ha": 7500,
    },
    {
        "name": "Corvina",
        "color": "red",
        "origin": "autochthonous",
        "origin_region": "Veneto",
        "synonyms": ["Corvina Veronese", "Cruina"],
        "characteristics": "Medium body with bright cherry and almond notes; the principal grape of Amarone and Valpolicella; well-suited to the appassimento drying process",
        "key_denominations": ["Amarone della Valpolicella", "Valpolicella", "Bardolino", "Recioto della Valpolicella"],
        "regions_grown": ["Veneto"],
        "vineyard_area_ha": 7000,
    },
    {
        "name": "Nero d'Avola",
        "color": "red",
        "origin": "autochthonous",
        "origin_region": "Sicily",
        "synonyms": ["Calabrese"],
        "characteristics": "Full-bodied with dark fruit, chocolate, and spice; Sicily's most important red grape; performs best in the warmer southeastern parts of the island",
        "key_denominations": ["Cerasuolo di Vittoria", "Noto", "Eloro"],
        "regions_grown": ["Sicily"],
        "vineyard_area_ha": 12000,
    },
    {
        "name": "Primitivo",
        "color": "red",
        "origin": "autochthonous",
        "origin_region": "Puglia",
        "synonyms": ["Zinfandel"],
        "characteristics": "High sugar potential yielding rich, full-bodied wines with dark fruit, jam, and spice; genetically identical to California's Zinfandel and Croatia's Crljenak Kaštelanski",
        "key_denominations": ["Primitivo di Manduria", "Gioia del Colle"],
        "regions_grown": ["Puglia"],
        "vineyard_area_ha": 12000,
    },
    {
        "name": "Negroamaro",
        "color": "red",
        "origin": "autochthonous",
        "origin_region": "Puglia",
        "synonyms": ["Negro Amaro"],
        "characteristics": "Full-bodied with dark cherry, plum, and earthy notes; the name translates to 'black bitter'; dominant red grape of the Salento peninsula",
        "key_denominations": ["Salice Salentino", "Copertino", "Squinzano", "Leverano"],
        "regions_grown": ["Puglia"],
        "vineyard_area_ha": 11000,
    },
    {
        "name": "Barbera",
        "color": "red",
        "origin": "autochthonous",
        "origin_region": "Piedmont",
        "synonyms": [],
        "characteristics": "High acidity, low tannin, deep color; cherry, plum, and spice; Piedmont's most widely planted red grape; extremely versatile from young and fruity to oak-aged and structured",
        "key_denominations": ["Barbera d'Asti", "Nizza", "Barbera d'Alba", "Barbera del Monferrato"],
        "regions_grown": ["Piedmont", "Lombardy", "Emilia-Romagna"],
        "vineyard_area_ha": 19000,
    },
    {
        "name": "Dolcetto",
        "color": "red",
        "origin": "autochthonous",
        "origin_region": "Piedmont",
        "synonyms": ["Ormeasco"],
        "characteristics": "Low acidity, moderate tannin, deep purple color; fresh dark fruit and almond notes; typically consumed young; the name means 'little sweet one' but the wines are dry",
        "key_denominations": ["Dogliani", "Dolcetto d'Alba", "Dolcetto d'Asti", "Dolcetto di Diano d'Alba"],
        "regions_grown": ["Piedmont", "Liguria"],
        "vineyard_area_ha": 5500,
    },
    {
        "name": "Montepulciano",
        "color": "red",
        "origin": "autochthonous",
        "origin_region": "Abruzzo",
        "synonyms": ["Cordisco"],
        "characteristics": "Deep color, moderate acidity, soft tannins; dark cherry, plum, and violet notes; not to be confused with Vino Nobile di Montepulciano which uses Sangiovese",
        "key_denominations": ["Montepulciano d'Abruzzo", "Montepulciano d'Abruzzo Colline Teramane", "Conero", "Rosso Piceno"],
        "regions_grown": ["Abruzzo", "Marche", "Molise", "Puglia"],
        "vineyard_area_ha": 25000,
    },
    {
        "name": "Cannonau",
        "color": "red",
        "origin": "autochthonous",
        "origin_region": "Sardinia",
        "synonyms": ["Grenache", "Garnacha", "Tocai Rosso"],
        "characteristics": "Full-bodied with ripe red fruit, herbs, and spice; Sardinia's most important red grape; genetically identical to Grenache/Garnacha; Sardinia claims it as originating on the island",
        "key_denominations": ["Cannonau di Sardegna"],
        "regions_grown": ["Sardinia"],
        "vineyard_area_ha": 6200,
    },
    {
        "name": "Nerello Mascalese",
        "color": "red",
        "origin": "autochthonous",
        "origin_region": "Sicily",
        "synonyms": ["Nerello", "Niureddu Mascalisi"],
        "characteristics": "Pale color, high acidity, ethereal perfume; often compared to Pinot Noir or Nebbiolo; thrives on the volcanic slopes of Mount Etna; intensely mineral wines",
        "key_denominations": ["Etna Rosso", "Faro"],
        "regions_grown": ["Sicily"],
        "vineyard_area_ha": 3200,
    },
    {
        "name": "Nero di Troia",
        "color": "red",
        "origin": "autochthonous",
        "origin_region": "Puglia",
        "synonyms": ["Uva di Troia", "Sumarello"],
        "characteristics": "Full-bodied, high tannin; dark fruit, spice, and mineral notes; the leading grape of northern Puglia; name refers to the town of Troia in Foggia province",
        "key_denominations": ["Castel del Monte Nero di Troia Riserva", "Castel del Monte", "Cacc'e Mmitte di Lucera"],
        "regions_grown": ["Puglia"],
        "vineyard_area_ha": 1800,
    },
    {
        "name": "Gaglioppo",
        "color": "red",
        "origin": "autochthonous",
        "origin_region": "Calabria",
        "synonyms": ["Cirotana", "Magliocco"],
        "characteristics": "Pale color, high tannin and acidity; cherry and herb notes; the dominant red grape of Calabria with ancient Greek origins; main grape of Cirò",
        "key_denominations": ["Cirò"],
        "regions_grown": ["Calabria"],
        "vineyard_area_ha": 4000,
    },
    {
        "name": "Sagrantino",
        "color": "red",
        "origin": "autochthonous",
        "origin_region": "Umbria",
        "synonyms": [],
        "characteristics": "Extremely high tannin (among the highest of any wine grape); intense dark fruit, spice, and earth; indigenous to the Montefalco area; historically made as a sweet passito wine",
        "key_denominations": ["Montefalco Sagrantino"],
        "regions_grown": ["Umbria"],
        "vineyard_area_ha": 500,
    },
    {
        "name": "Lagrein",
        "color": "red",
        "origin": "autochthonous",
        "origin_region": "Trentino-Alto Adige",
        "synonyms": [],
        "characteristics": "Deep color, moderate tannin; dark berry, chocolate, and violet notes; performs best on warm valley floor sites in Alto Adige; also used for rosé (Kretzer)",
        "key_denominations": ["Alto Adige Lagrein"],
        "regions_grown": ["Trentino-Alto Adige"],
        "vineyard_area_ha": 450,
    },
    {
        "name": "Teroldego",
        "color": "red",
        "origin": "autochthonous",
        "origin_region": "Trentino-Alto Adige",
        "synonyms": [],
        "characteristics": "Deep purple color, moderate acidity; blackberry, almond, and floral notes; native to the Rotaliano plain in Trentino; parent grape of Lagrein according to DNA research",
        "key_denominations": ["Teroldego Rotaliano"],
        "regions_grown": ["Trentino-Alto Adige"],
        "vineyard_area_ha": 800,
    },
    {
        "name": "Frappato",
        "color": "red",
        "origin": "autochthonous",
        "origin_region": "Sicily",
        "synonyms": ["Frappato di Vittoria"],
        "characteristics": "Light-bodied, aromatic with strawberry and floral notes; often compared to Gamay or Schiava for its freshness; blending partner with Nero d'Avola in Cerasuolo di Vittoria",
        "key_denominations": ["Cerasuolo di Vittoria"],
        "regions_grown": ["Sicily"],
        "vineyard_area_ha": 700,
    },
    {
        "name": "Rondinella",
        "color": "red",
        "origin": "autochthonous",
        "origin_region": "Veneto",
        "synonyms": [],
        "characteristics": "Supporting variety in Valpolicella blends; contributes color and mild tannin; well-suited to the appassimento drying process; rarely vinified alone",
        "key_denominations": ["Amarone della Valpolicella", "Valpolicella", "Recioto della Valpolicella"],
        "regions_grown": ["Veneto"],
        "vineyard_area_ha": 2500,
    },
    {
        "name": "Schiava",
        "color": "red",
        "origin": "autochthonous",
        "origin_region": "Trentino-Alto Adige",
        "synonyms": ["Vernatsch", "Trollinger"],
        "characteristics": "Light-bodied with low tannin; almond, cherry, and violet notes; historically the most planted grape in Alto Adige; known as Vernatsch in German",
        "key_denominations": ["Santa Maddalena", "Lago di Caldaro", "Alto Adige Schiava"],
        "regions_grown": ["Trentino-Alto Adige"],
        "vineyard_area_ha": 1200,
    },
    {
        "name": "Lambrusco",
        "color": "red",
        "origin": "autochthonous",
        "origin_region": "Emilia-Romagna",
        "synonyms": ["Lambrusco di Sorbara", "Lambrusco Grasparossa", "Lambrusco Salamino"],
        "characteristics": "Not a single variety but a family of related grapes; produces sparkling to frizzante red wines; ranges from dry to sweet; Sorbara is the most refined subvariety",
        "key_denominations": ["Lambrusco di Sorbara", "Lambrusco Grasparossa di Castelvetro", "Lambrusco Salamino di Santa Croce"],
        "regions_grown": ["Emilia-Romagna", "Lombardy"],
        "vineyard_area_ha": 9000,
    },
    {
        "name": "Refosco dal Peduncolo Rosso",
        "color": "red",
        "origin": "autochthonous",
        "origin_region": "Friuli Venezia Giulia",
        "synonyms": ["Refosco"],
        "characteristics": "Deep color, brisk acidity; dark cherry, plum, and herbal notes; the name refers to its distinctive red stems (peduncoli rossi)",
        "key_denominations": ["Friuli Colli Orientali Refosco", "Lison Pramaggiore"],
        "regions_grown": ["Friuli Venezia Giulia", "Veneto"],
        "vineyard_area_ha": 1500,
    },
    {
        "name": "Cesanese",
        "color": "red",
        "origin": "autochthonous",
        "origin_region": "Lazio",
        "synonyms": ["Cesanese d'Affile", "Cesanese Comune"],
        "characteristics": "Medium-bodied with cherry, herb, and floral notes; two distinct clones exist (d'Affile and Comune); the most important indigenous red grape of Lazio",
        "key_denominations": ["Cesanese del Piglio"],
        "regions_grown": ["Lazio"],
        "vineyard_area_ha": 800,
    },
    {
        "name": "Tintilia",
        "color": "red",
        "origin": "autochthonous",
        "origin_region": "Molise",
        "synonyms": [],
        "characteristics": "Full-bodied with dark fruit, spice, and mineral notes; nearly extinct before revitalization in the 1990s; Molise's signature indigenous grape",
        "key_denominations": ["Tintilia del Molise"],
        "regions_grown": ["Molise"],
        "vineyard_area_ha": 200,
    },
    {
        "name": "Piedirosso",
        "color": "red",
        "origin": "autochthonous",
        "origin_region": "Campania",
        "synonyms": ["Per'e Palummo"],
        "characteristics": "Medium-bodied with red fruit and herbal notes; the name means 'red foot' referring to the red stems; traditional blending partner with Aglianico in Campania",
        "key_denominations": ["Lacryma Christi del Vesuvio", "Campi Flegrei"],
        "regions_grown": ["Campania"],
        "vineyard_area_ha": 1800,
    },
    {
        "name": "Croatina",
        "color": "red",
        "origin": "autochthonous",
        "origin_region": "Lombardy",
        "synonyms": ["Bonarda"],
        "characteristics": "Deep color, moderate acidity with dark cherry and berry notes; confusingly marketed as 'Bonarda' in Oltrepò Pavese though it is not the same as Bonarda Piemontese",
        "key_denominations": ["Oltrepò Pavese Bonarda", "Gutturnio"],
        "regions_grown": ["Lombardy", "Emilia-Romagna", "Piedmont"],
        "vineyard_area_ha": 3500,
    },
    {
        "name": "Carignano",
        "color": "red",
        "origin": "autochthonous",
        "origin_region": "Sardinia",
        "synonyms": ["Carignan", "Mazuelo", "Cariñena"],
        "characteristics": "Full-bodied with dark fruit and earthy character; thrives in sandy, wind-swept conditions; old bush-vine (alberello) Carignano from Sulcis produces some of Sardinia's finest reds",
        "key_denominations": ["Carignano del Sulcis"],
        "regions_grown": ["Sardinia"],
        "vineyard_area_ha": 1700,
    },

    # ── White Varieties ──
    {
        "name": "Garganega",
        "color": "white",
        "origin": "autochthonous",
        "origin_region": "Veneto",
        "synonyms": ["Grecanico Dorato"],
        "characteristics": "Medium to full-bodied with almond, citrus, and honey notes; excellent aging potential especially from volcanic Soave Classico soils; may be identical to Sicily's Grecanico Dorato",
        "key_denominations": ["Soave", "Soave Superiore", "Gambellara", "Recioto di Soave"],
        "regions_grown": ["Veneto"],
        "vineyard_area_ha": 11000,
    },
    {
        "name": "Glera",
        "color": "white",
        "origin": "autochthonous",
        "origin_region": "Veneto",
        "synonyms": ["Prosecco"],
        "characteristics": "Light-bodied, aromatic with green apple, pear, and white flower notes; primary grape for Prosecco sparkling wines; formerly called Prosecco before the 2009 regulation change",
        "key_denominations": ["Prosecco DOC", "Conegliano Valdobbiadene Prosecco Superiore", "Asolo Prosecco Superiore"],
        "regions_grown": ["Veneto", "Friuli Venezia Giulia"],
        "vineyard_area_ha": 27000,
    },
    {
        "name": "Verdicchio",
        "color": "white",
        "origin": "autochthonous",
        "origin_region": "Marche",
        "synonyms": ["Trebbiano di Soave", "Trebbiano di Lugana"],
        "characteristics": "High acidity, citrus, green almond, and mineral notes; one of Italy's most age-worthy white grapes; genetically identical to Trebbiano di Soave and Trebbiano di Lugana",
        "key_denominations": ["Verdicchio dei Castelli di Jesi", "Verdicchio di Matelica"],
        "regions_grown": ["Marche", "Veneto"],
        "vineyard_area_ha": 3500,
    },
    {
        "name": "Fiano",
        "color": "white",
        "origin": "autochthonous",
        "origin_region": "Campania",
        "synonyms": ["Fiano di Avellino", "Fiano Minutolo"],
        "characteristics": "Complex with hazelnut, honey, pear, and mineral notes; excellent aging potential; thrives in the high-altitude Irpinia hills of Campania",
        "key_denominations": ["Fiano di Avellino"],
        "regions_grown": ["Campania", "Puglia", "Sicily"],
        "vineyard_area_ha": 3000,
    },
    {
        "name": "Greco",
        "color": "white",
        "origin": "autochthonous",
        "origin_region": "Campania",
        "synonyms": ["Greco di Tufo"],
        "characteristics": "Medium to full-bodied with peach, apricot, almond, and smoky mineral notes; high acidity; the name reflects its ancient Greek origins; thrives on the tufo soils of Irpinia",
        "key_denominations": ["Greco di Tufo"],
        "regions_grown": ["Campania", "Calabria"],
        "vineyard_area_ha": 2500,
    },
    {
        "name": "Falanghina",
        "color": "white",
        "origin": "autochthonous",
        "origin_region": "Campania",
        "synonyms": ["Falanghina Flegrea", "Falanghina Beneventana"],
        "characteristics": "Fresh, aromatic with citrus, peach, and floral notes; two distinct biotypes exist (Flegrea from Naples area and Beneventana from inland); Campania's most widely planted white grape",
        "key_denominations": ["Falanghina del Sannio", "Falerno del Massico"],
        "regions_grown": ["Campania"],
        "vineyard_area_ha": 3500,
    },
    {
        "name": "Vermentino",
        "color": "white",
        "origin": "autochthonous",
        "origin_region": "Sardinia",
        "synonyms": ["Favorita", "Pigato", "Rolle"],
        "characteristics": "Medium-bodied with citrus, almond, herbal, and saline notes; performs especially well on Gallura's granite soils; possibly identical to Rolle in southern France and Pigato in Liguria",
        "key_denominations": ["Vermentino di Gallura", "Vermentino di Sardegna", "Riviera Ligure di Ponente"],
        "regions_grown": ["Sardinia", "Liguria", "Tuscany"],
        "vineyard_area_ha": 8000,
    },
    {
        "name": "Friulano",
        "color": "white",
        "origin": "autochthonous",
        "origin_region": "Friuli Venezia Giulia",
        "synonyms": ["Sauvignonasse", "Tai"],
        "characteristics": "Medium-bodied with almond, apple, and herbal notes with a characteristic bitter almond finish; formerly called Tocai Friulano before EU regulation required the name change in 2007",
        "key_denominations": ["Friuli Colli Orientali", "Collio", "Friuli Isonzo"],
        "regions_grown": ["Friuli Venezia Giulia", "Veneto"],
        "vineyard_area_ha": 3000,
    },
    {
        "name": "Ribolla Gialla",
        "color": "white",
        "origin": "autochthonous",
        "origin_region": "Friuli Venezia Giulia",
        "synonyms": ["Rebula"],
        "characteristics": "High acidity, lean, mineral; citrus, green apple, and floral notes; increasingly used for orange wines (skin-contact) following Friulian traditions; known as Rebula in Slovenia",
        "key_denominations": ["Collio", "Friuli Colli Orientali"],
        "regions_grown": ["Friuli Venezia Giulia"],
        "vineyard_area_ha": 1000,
    },
    {
        "name": "Arneis",
        "color": "white",
        "origin": "autochthonous",
        "origin_region": "Piedmont",
        "synonyms": ["Barolo Bianco"],
        "characteristics": "Medium-bodied with pear, white peach, and almond notes; rescued from near extinction in the 1970s; native to the Roero sandy hills across the Tanaro from the Langhe",
        "key_denominations": ["Roero Arneis"],
        "regions_grown": ["Piedmont"],
        "vineyard_area_ha": 1100,
    },
    {
        "name": "Cortese",
        "color": "white",
        "origin": "autochthonous",
        "origin_region": "Piedmont",
        "synonyms": [],
        "characteristics": "Light, crisp, with citrus and mineral notes; best known from Gavi where maritime influence from Liguria adds aromatic complexity; refreshing acidity",
        "key_denominations": ["Gavi"],
        "regions_grown": ["Piedmont"],
        "vineyard_area_ha": 2800,
    },
    {
        "name": "Moscato Bianco",
        "color": "white",
        "origin": "autochthonous",
        "origin_region": "Piedmont",
        "synonyms": ["Muscat Blanc à Petits Grains", "Moscato d'Asti", "Moscato di Canelli"],
        "characteristics": "Intensely aromatic with peach, apricot, orange blossom, and sage notes; low alcohol potential makes it ideal for sweet and semi-sparkling wines; one of the oldest known grape varieties",
        "key_denominations": ["Asti", "Moscato d'Asti"],
        "regions_grown": ["Piedmont"],
        "vineyard_area_ha": 9700,
    },
    {
        "name": "Albana",
        "color": "white",
        "origin": "autochthonous",
        "origin_region": "Emilia-Romagna",
        "synonyms": [],
        "characteristics": "Medium to full-bodied with apricot, honey, and almond notes; thick-skinned white variety capable of producing dry, sweet, and passito wines; first Italian white grape to receive DOCG status",
        "key_denominations": ["Romagna Albana"],
        "regions_grown": ["Emilia-Romagna"],
        "vineyard_area_ha": 2000,
    },
    {
        "name": "Vernaccia di San Gimignano",
        "color": "white",
        "origin": "autochthonous",
        "origin_region": "Tuscany",
        "synonyms": [],
        "characteristics": "Medium-bodied with citrus, almond, and mineral notes; Italy's first DOC (1966); unrelated to other Italian grapes named Vernaccia",
        "key_denominations": ["Vernaccia di San Gimignano"],
        "regions_grown": ["Tuscany"],
        "vineyard_area_ha": 740,
    },
    {
        "name": "Catarratto",
        "color": "white",
        "origin": "autochthonous",
        "origin_region": "Sicily",
        "synonyms": ["Catarratto Bianco Comune", "Catarratto Bianco Lucido"],
        "characteristics": "Neutral to aromatic depending on yield and site; citrus and floral notes; was historically Sicily's and Italy's most planted grape; used for Marsala production",
        "key_denominations": ["Alcamo", "Etna Bianco", "Marsala"],
        "regions_grown": ["Sicily"],
        "vineyard_area_ha": 26000,
    },
    {
        "name": "Grillo",
        "color": "white",
        "origin": "autochthonous",
        "origin_region": "Sicily",
        "synonyms": [],
        "characteristics": "Full-bodied with tropical fruit, citrus, and almond notes; originally cultivated for Marsala production; increasingly made as a fresh varietal white; thrives in Sicily's hot climate",
        "key_denominations": ["Marsala", "Sicilia"],
        "regions_grown": ["Sicily"],
        "vineyard_area_ha": 7000,
    },
    {
        "name": "Carricante",
        "color": "white",
        "origin": "autochthonous",
        "origin_region": "Sicily",
        "synonyms": [],
        "characteristics": "High acidity with citrus, saline, and volcanic mineral notes; native to Mount Etna; thrives at high altitude on volcanic soils producing age-worthy white wines",
        "key_denominations": ["Etna Bianco"],
        "regions_grown": ["Sicily"],
        "vineyard_area_ha": 500,
    },
    {
        "name": "Pecorino",
        "color": "white",
        "origin": "autochthonous",
        "origin_region": "Marche",
        "synonyms": [],
        "characteristics": "Aromatic with citrus, green herbs, and mineral notes; high acidity; rescued from near extinction in the 1990s; the name possibly derives from pecora (sheep) suggesting mountain pasture origins",
        "key_denominations": ["Offida Pecorino", "Falerio Pecorino"],
        "regions_grown": ["Marche", "Abruzzo"],
        "vineyard_area_ha": 2000,
    },
    {
        "name": "Trebbiano Toscano",
        "color": "white",
        "origin": "autochthonous",
        "origin_region": "Tuscany",
        "synonyms": ["Ugni Blanc", "Procanico"],
        "characteristics": "High yield, neutral flavor profile with mild citrus and almond notes; one of the world's most planted white grapes; used for brandy production in France as Ugni Blanc",
        "key_denominations": ["Orvieto", "Frascati", "Est! Est!! Est!!!"],
        "regions_grown": ["Tuscany", "Lazio", "Umbria", "Emilia-Romagna", "Abruzzo"],
        "vineyard_area_ha": 18000,
    },
    {
        "name": "Grechetto",
        "color": "white",
        "origin": "autochthonous",
        "origin_region": "Umbria",
        "synonyms": ["Grechetto di Orvieto", "Grechetto di Todi"],
        "characteristics": "Medium-bodied with almond, pear, and citrus notes; two distinct clones (di Orvieto and di Todi) with different characteristics; key white grape of Umbria",
        "key_denominations": ["Orvieto", "Colli Martani Grechetto"],
        "regions_grown": ["Umbria", "Lazio"],
        "vineyard_area_ha": 2500,
    },
    {
        "name": "Erbaluce",
        "color": "white",
        "origin": "autochthonous",
        "origin_region": "Piedmont",
        "synonyms": [],
        "characteristics": "High acidity with citrus, mineral, and floral notes; versatile grape made in still, sparkling, and passito styles; native to the Canavese area north of Turin",
        "key_denominations": ["Erbaluce di Caluso"],
        "regions_grown": ["Piedmont"],
        "vineyard_area_ha": 200,
    },
    {
        "name": "Gewürztraminer",
        "color": "white",
        "origin": "international",
        "origin_region": "Trentino-Alto Adige",
        "synonyms": ["Traminer Aromatico"],
        "characteristics": "Intensely aromatic with lychee, rose petal, ginger, and spice; full-bodied with low acidity; the village of Tramin (Termeno) in Alto Adige is considered its likely origin",
        "key_denominations": ["Alto Adige Gewürztraminer"],
        "regions_grown": ["Trentino-Alto Adige"],
        "vineyard_area_ha": 700,
    },
    {
        "name": "Nuragus",
        "color": "white",
        "origin": "autochthonous",
        "origin_region": "Sardinia",
        "synonyms": [],
        "characteristics": "Light, neutral with mild citrus notes; high-yielding and widely planted in southern Sardinia; name derives from the Nuraghi (ancient Sardinian stone towers)",
        "key_denominations": ["Nuragus di Cagliari"],
        "regions_grown": ["Sardinia"],
        "vineyard_area_ha": 3500,
    },
    {
        "name": "Trebbiano d'Abruzzo",
        "color": "white",
        "origin": "autochthonous",
        "origin_region": "Abruzzo",
        "synonyms": ["Bombino Bianco"],
        "characteristics": "Two distinct varieties share this name: the true Trebbiano d'Abruzzo (rare, high quality, selected by Valentini) and the more common Bombino Bianco; the authentic version produces age-worthy whites",
        "key_denominations": ["Trebbiano d'Abruzzo"],
        "regions_grown": ["Abruzzo"],
        "vineyard_area_ha": 8000,
    },
    {
        "name": "Passerina",
        "color": "white",
        "origin": "autochthonous",
        "origin_region": "Marche",
        "synonyms": [],
        "characteristics": "Crisp with green apple, citrus, and white flower notes; the name may derive from passera (sparrow) as birds favor the sweet grapes; increasingly bottled as a varietal in Marche and Abruzzo",
        "key_denominations": ["Offida Passerina"],
        "regions_grown": ["Marche", "Abruzzo", "Lazio"],
        "vineyard_area_ha": 1500,
    },
    {
        "name": "Trebbiano Spoletino",
        "color": "white",
        "origin": "autochthonous",
        "origin_region": "Umbria",
        "synonyms": [],
        "characteristics": "Complex with citrus, herbal, and mineral notes; despite the Trebbiano name, it is unrelated to other Trebbiano varieties; considered one of central Italy's finest and most interesting whites",
        "key_denominations": ["Spoleto Trebbiano Spoletino"],
        "regions_grown": ["Umbria"],
        "vineyard_area_ha": 300,
    },
    {
        "name": "Zibibbo",
        "color": "white",
        "origin": "autochthonous",
        "origin_region": "Sicily",
        "synonyms": ["Muscat of Alexandria", "Moscato d'Alessandria"],
        "characteristics": "Intensely aromatic with apricot, orange blossom, and honey notes; used for the famous Passito di Pantelleria dessert wine; Pantelleria's alberello cultivation of Zibibbo is a UNESCO intangible heritage",
        "key_denominations": ["Passito di Pantelleria", "Moscato di Pantelleria"],
        "regions_grown": ["Sicily"],
        "vineyard_area_ha": 2500,
    },
    {
        "name": "Schioppettino",
        "color": "red",
        "origin": "autochthonous",
        "origin_region": "Friuli Venezia Giulia",
        "synonyms": ["Ribolla Nera"],
        "characteristics": "Peppery and spicy with dark fruit and violet notes; nearly went extinct before being revived in the 1970s by local growers in Prepotto and Cialla; the name refers to the cracking sound of its berries",
        "key_denominations": ["Friuli Colli Orientali Schioppettino"],
        "regions_grown": ["Friuli Venezia Giulia"],
        "vineyard_area_ha": 100,
    },
    {
        "name": "Petit Rouge",
        "color": "red",
        "origin": "autochthonous",
        "origin_region": "Valle d'Aosta",
        "synonyms": [],
        "characteristics": "Medium-bodied with red fruit, herb, and floral notes; Valle d'Aosta's most important indigenous red grape; adapted to extreme mountain viticulture conditions",
        "key_denominations": ["Valle d'Aosta Torrette"],
        "regions_grown": ["Valle d'Aosta"],
        "vineyard_area_ha": 50,
    },
    {
        "name": "Pignoletto",
        "color": "white",
        "origin": "autochthonous",
        "origin_region": "Emilia-Romagna",
        "synonyms": ["Grechetto Gentile"],
        "characteristics": "Fresh with citrus, pear, and mineral notes; made in still, frizzante, and spumante styles; genetically identical to Umbria's Grechetto di Todi despite different regional names",
        "key_denominations": ["Colli Bolognesi Pignoletto"],
        "regions_grown": ["Emilia-Romagna"],
        "vineyard_area_ha": 2000,
    },
    {
        "name": "Lacrima",
        "color": "red",
        "origin": "autochthonous",
        "origin_region": "Marche",
        "synonyms": ["Lacrima di Morro d'Alba"],
        "characteristics": "Intensely aromatic with rose, violet, strawberry, and spice notes; the name (tear) refers to drops of juice that seep from ripe berries; almost exclusively grown around Morro d'Alba in the Marche",
        "key_denominations": ["Lacrima di Morro d'Alba"],
        "regions_grown": ["Marche"],
        "vineyard_area_ha": 250,
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Production Statistics (by region, from IWC)
# ═══════════════════════════════════════════════════════════════════════════════

PRODUCTION_STATS = {
    "Veneto": {"production_hl": 11670000, "doc_docg_pct": 78, "vineyard_area_ha": 87000},
    "Puglia": {"production_hl": 7600000, "doc_docg_pct": 30, "vineyard_area_ha": 87000},
    "Emilia-Romagna": {"production_hl": 7100000, "doc_docg_pct": 55, "vineyard_area_ha": 52000},
    "Tuscany": {"production_hl": 2770000, "doc_docg_pct": 85, "vineyard_area_ha": 58000},
    "Sicily": {"production_hl": 2740000, "doc_docg_pct": 35, "vineyard_area_ha": 97000},
    "Piedmont": {"production_hl": 2690000, "doc_docg_pct": 89, "vineyard_area_ha": 42000},
    "Abruzzo": {"production_hl": 2250000, "doc_docg_pct": 45, "vineyard_area_ha": 32000},
    "Friuli Venezia Giulia": {"production_hl": 1830000, "doc_docg_pct": 70, "vineyard_area_ha": 27000},
    "Lazio": {"production_hl": 1550000, "doc_docg_pct": 40, "vineyard_area_ha": 21000},
    "Lombardy": {"production_hl": 1520000, "doc_docg_pct": 65, "vineyard_area_ha": 24000},
    "Campania": {"production_hl": 1330000, "doc_docg_pct": 25, "vineyard_area_ha": 23000},
    "Trentino-Alto Adige": {"production_hl": 1150000, "doc_docg_pct": 90, "vineyard_area_ha": 15700},
    "Marche": {"production_hl": 920000, "doc_docg_pct": 50, "vineyard_area_ha": 17000},
    "Umbria": {"production_hl": 780000, "doc_docg_pct": 40, "vineyard_area_ha": 13000},
    "Sardinia": {"production_hl": 530000, "doc_docg_pct": 40, "vineyard_area_ha": 26000},
    "Molise": {"production_hl": 280000, "doc_docg_pct": 20, "vineyard_area_ha": 5000},
    "Calabria": {"production_hl": 260000, "doc_docg_pct": 15, "vineyard_area_ha": 10000},
    "Basilicata": {"production_hl": 96000, "doc_docg_pct": 30, "vineyard_area_ha": 4000},
    "Liguria": {"production_hl": 60000, "doc_docg_pct": 50, "vineyard_area_ha": 2000},
    "Valle d'Aosta": {"production_hl": 18000, "doc_docg_pct": 85, "vineyard_area_ha": 400},
}


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — MeGA / UGA / Subzone Data
# ═══════════════════════════════════════════════════════════════════════════════

MEGA_UGA_DATABASE = {
    "Barolo": {
        "type": "MeGA",
        "count": 181,
        "description": "Barolo DOCG established 181 Menzioni Geografiche Aggiuntive (MeGAs), officially recognized vineyard sites that may appear on the label to indicate specific origin within the production zone.",
        "notable": ["Cannubi", "Brunate", "Cerequio", "Rocche dell'Annunziata", "Bussia", "Ginestra", "Lazzarito", "Vigna Rionda", "Monprivato", "Villero", "Francia", "Arborina", "Fossati", "Bricco Boschis", "Bricco Rocche"],
    },
    "Barbaresco": {
        "type": "MeGA",
        "count": 66,
        "description": "Barbaresco DOCG has 66 officially recognized MeGAs across its four communes.",
        "notable": ["Asili", "Rabajà", "Pajé", "Pora", "Rio Sordo", "Montestefano", "Gallina", "Santo Stefano", "Montefico", "Ovello", "Rombone", "Martinenga", "Camp Gros", "Bernardot"],
    },
    "Roero": {
        "type": "MeGA",
        "count": 134,
        "description": "Roero DOCG has 134 recognized MeGAs on the sandy Tanaro left bank.",
        "notable": [],
    },
    "Chianti Classico": {
        "type": "UGA",
        "count": 11,
        "description": "Chianti Classico introduced 11 Unità Geografiche Aggiuntive (UGAs) in 2021 for the Gran Selezione category, representing distinct subzones within the historic Chianti Classico territory.",
        "notable": ["Greve", "Panzano", "Radda", "Gaiole", "Castellina", "Castelnuovo Berardenga", "San Casciano", "San Donato in Poggio", "Vagliagli", "Lamole", "Montefioralle"],
    },
    "Conegliano Valdobbiadene Prosecco Superiore": {
        "type": "rive",
        "count": 43,
        "description": "Conegliano Valdobbiadene has 43 recognized rive (steep hillside sites) that may appear on the label, along with the prestigious Cartizze sub-zone of 107 hectares.",
        "notable": ["Cartizze", "Rive di Col San Martino", "Rive di Santo Stefano", "Rive di Refrontolo"],
    },
    "Valtellina Superiore": {
        "type": "sottozona",
        "count": 5,
        "description": "Valtellina Superiore DOCG has 5 recognized subzones on the steep south-facing terraces of the Adige Valley.",
        "notable": ["Sassella", "Grumello", "Inferno", "Valgella", "Maroggia"],
    },
    "Chianti": {
        "type": "sottozona",
        "count": 8,
        "description": "Chianti DOCG has 8 recognized subzones reflecting the diversity of terroirs across the broader Chianti production area.",
        "notable": ["Rufina", "Colli Senesi", "Colli Fiorentini", "Colli Aretini", "Colline Pisane", "Montalbano", "Montespertoli"],
    },
    "Amarone della Valpolicella": {
        "type": "UGA",
        "count": 11,
        "description": "Valpolicella introduced UGAs to recognize distinct valley systems and hillside zones within the production territory.",
        "notable": [],
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — DOC Enriched Data (soil, elevation, climate, wine styles)
# Complements italy.py DOC_DATABASE which only has name/region/grapes/colors.
# Fact templates here focus on terroir data that italy.py does not generate.
# ═══════════════════════════════════════════════════════════════════════════════

DOC_ENRICHED_DATABASE = [
    # ── Piedmont ──
    {
        "name": "Barbera d'Alba",
        "region": "Piedmont",
        "province": "Cuneo",
        "soil_types": ["calcareous marl", "clay-limestone"],
        "elevation_range": "200-500m",
        "climate_note": "Continental; vineyards share the Langhe hills with Barolo and Barbaresco",
        "wine_styles": ["dry red", "superiore"],
        "superiore_aging_months": 12,
        "vineyard_area_ha": 1800,
    },
    {
        "name": "Dolcetto d'Alba",
        "region": "Piedmont",
        "province": "Cuneo",
        "soil_types": ["calcareous marl", "clay"],
        "elevation_range": "200-500m",
        "climate_note": "Continental; typically planted on north-facing slopes or lower elevations not suited for Nebbiolo",
        "wine_styles": ["dry red", "superiore"],
        "vineyard_area_ha": 1300,
    },
    {
        "name": "Langhe",
        "region": "Piedmont",
        "province": "Cuneo",
        "soil_types": ["calcareous marl", "clay-limestone", "sand"],
        "elevation_range": "200-600m",
        "climate_note": "Continental; covers the entire Langhe hills providing a flexible DOC for varieties and blends not fitting stricter DOCG rules",
        "wine_styles": ["dry red", "dry white", "rosé", "sparkling"],
        "vineyard_area_ha": 3000,
    },
    {
        "name": "Nebbiolo d'Alba",
        "region": "Piedmont",
        "province": "Cuneo",
        "soil_types": ["calcareous marl", "sand", "clay"],
        "elevation_range": "200-450m",
        "climate_note": "Continental; vineyards between Barolo and Roero zones on both sides of the Tanaro River",
        "wine_styles": ["dry red", "spumante"],
        "vineyard_area_ha": 700,
    },
    {
        "name": "Moscato d'Asti",
        "region": "Piedmont",
        "province": "Asti, Cuneo, Alessandria",
        "soil_types": ["calcareous marl", "clay", "sand"],
        "elevation_range": "200-500m",
        "climate_note": "Continental; warm days preserve aromatic intensity while cool nights maintain acidity in Moscato Bianco",
        "wine_styles": ["sweet frizzante white"],
        "vineyard_area_ha": 9700,
    },
    {
        "name": "Gavi",
        "region": "Piedmont",
        "province": "Alessandria",
        "soil_types": ["red clay", "calcareous marl", "limestone"],
        "elevation_range": "180-450m",
        "climate_note": "Continental with maritime influence from Ligurian coast proximity",
        "wine_styles": ["dry white", "frizzante", "spumante"],
        "vineyard_area_ha": 1500,
    },
    {
        "name": "Dolcetto di Diano d'Alba",
        "region": "Piedmont",
        "province": "Cuneo",
        "soil_types": ["calcareous marl", "clay"],
        "elevation_range": "250-500m",
        "climate_note": "Continental; Diano d'Alba vineyards on south-facing slopes in the Langhe",
        "wine_styles": ["dry red", "superiore"],
        "vineyard_area_ha": 200,
    },
    {
        "name": "Dolcetto d'Asti",
        "region": "Piedmont",
        "province": "Asti",
        "soil_types": ["calcareous clay", "marl", "sand"],
        "elevation_range": "200-400m",
        "climate_note": "Continental; Monferrato and Langhe Astigiane hills",
        "wine_styles": ["dry red"],
        "vineyard_area_ha": 300,
    },
    {
        "name": "Grignolino d'Asti",
        "region": "Piedmont",
        "province": "Asti",
        "soil_types": ["calcareous clay", "sand", "marl"],
        "elevation_range": "150-350m",
        "climate_note": "Continental; Monferrato hills east of Asti",
        "wine_styles": ["dry red"],
        "vineyard_area_ha": 250,
    },
    {
        "name": "Grignolino del Monferrato Casalese",
        "region": "Piedmont",
        "province": "Alessandria",
        "soil_types": ["clay", "sand", "calcareous marl"],
        "elevation_range": "130-300m",
        "climate_note": "Continental; lower Monferrato near Casale Monferrato",
        "wine_styles": ["dry red"],
        "vineyard_area_ha": 150,
    },
    {
        "name": "Freisa d'Asti",
        "region": "Piedmont",
        "province": "Asti",
        "soil_types": ["calcareous clay", "sand"],
        "elevation_range": "200-400m",
        "climate_note": "Continental; ancient Piedmontese variety on Monferrato slopes",
        "wine_styles": ["dry red", "sweet frizzante red"],
        "vineyard_area_ha": 200,
    },
    {
        "name": "Ruché di Castagnole Monferrato",
        "region": "Piedmont",
        "province": "Asti",
        "soil_types": ["calcareous marl", "clay-sand"],
        "elevation_range": "200-350m",
        "climate_note": "Continental; warm Monferrato microclimate suits this aromatic red variety",
        "wine_styles": ["dry red"],
        "vineyard_area_ha": 130,
    },
    {
        "name": "Colli Tortonesi",
        "region": "Piedmont",
        "province": "Alessandria",
        "soil_types": ["calcareous clay", "marl", "sand"],
        "elevation_range": "150-400m",
        "climate_note": "Continental with Ligurian influence; Timorasso is the star white grape of this zone",
        "wine_styles": ["dry white", "dry red"],
        "vineyard_area_ha": 500,
    },
    {
        "name": "Carema",
        "region": "Piedmont",
        "province": "Turin",
        "soil_types": ["glacial moraine", "granite", "sand"],
        "elevation_range": "300-600m",
        "climate_note": "Alpine continental; pergola-trained Nebbiolo on steep terraces at the entrance to Valle d'Aosta",
        "wine_styles": ["dry red"],
        "vineyard_area_ha": 15,
    },
    {
        "name": "Lessona",
        "region": "Piedmont",
        "province": "Biella",
        "soil_types": ["volcanic porphyry", "sand", "gravel"],
        "elevation_range": "300-450m",
        "climate_note": "Alpine continental; acidic volcanic soils producing a distinctive, mineral-driven Nebbiolo expression",
        "wine_styles": ["dry red"],
        "vineyard_area_ha": 10,
    },
    {
        "name": "Bramaterra",
        "region": "Piedmont",
        "province": "Biella, Vercelli",
        "soil_types": ["volcanic porphyry", "clay", "sand"],
        "elevation_range": "250-450m",
        "climate_note": "Alpine continental; similar volcanic geology to neighboring Lessona and Gattinara",
        "wine_styles": ["dry red"],
        "vineyard_area_ha": 20,
    },
    {
        "name": "Boca",
        "region": "Piedmont",
        "province": "Novara",
        "soil_types": ["volcanic porphyry", "granite", "clay"],
        "elevation_range": "350-500m",
        "climate_note": "Alpine continental; among the highest-altitude Nebbiolo vineyards in northern Piedmont",
        "wine_styles": ["dry red"],
        "vineyard_area_ha": 10,
    },
    {
        "name": "Fara",
        "region": "Piedmont",
        "province": "Novara",
        "soil_types": ["glacial moraine", "gravel", "clay"],
        "elevation_range": "250-400m",
        "climate_note": "Alpine continental; glacial moraine soils on the hills near Fara Novarese",
        "wine_styles": ["dry red"],
        "vineyard_area_ha": 10,
    },
    {
        "name": "Sizzano",
        "region": "Piedmont",
        "province": "Novara",
        "soil_types": ["glacial moraine", "alluvial gravel", "clay"],
        "elevation_range": "200-350m",
        "climate_note": "Continental; lower elevation than Boca and Ghemme, with more alluvial influence",
        "wine_styles": ["dry red"],
        "vineyard_area_ha": 15,
    },
    {
        "name": "Colline Novaresi",
        "region": "Piedmont",
        "province": "Novara",
        "soil_types": ["volcanic", "glacial moraine", "clay"],
        "elevation_range": "200-400m",
        "climate_note": "Alpine continental; umbrella DOC covering multiple varieties on the Novara hills",
        "wine_styles": ["dry red", "dry white"],
        "vineyard_area_ha": 100,
    },
    {
        "name": "Piemonte",
        "region": "Piedmont",
        "province": "region-wide",
        "soil_types": ["varied"],
        "elevation_range": "150-800m",
        "climate_note": "Continental; regional DOC covering all of Piedmont for wines that don't fit narrower appellations",
        "wine_styles": ["dry red", "dry white", "sparkling", "rosé"],
        "vineyard_area_ha": 5000,
    },

    # ── Veneto ──
    {
        "name": "Valpolicella",
        "region": "Veneto",
        "province": "Verona",
        "soil_types": ["limestone", "clay-limestone", "volcanic basalt", "alluvial"],
        "elevation_range": "50-450m",
        "climate_note": "Sub-Mediterranean moderated by Lake Garda; Classico zone hillsides are warmer and better-drained than the plain",
        "wine_styles": ["dry red", "ripasso", "superiore"],
        "vineyard_area_ha": 8300,
    },
    {
        "name": "Soave",
        "region": "Veneto",
        "province": "Verona",
        "soil_types": ["volcanic basalt", "tufo", "alluvial"],
        "elevation_range": "40-350m",
        "climate_note": "Temperate; Classico zone on volcanic hills produces more mineral wines than the alluvial plains",
        "wine_styles": ["dry white", "superiore"],
        "vineyard_area_ha": 6500,
    },
    {
        "name": "Prosecco",
        "region": "Veneto",
        "province": "Treviso, and across Veneto/Friuli",
        "soil_types": ["clay", "marl", "alluvial", "sand"],
        "elevation_range": "10-300m",
        "climate_note": "Continental to sub-Mediterranean; the broad Prosecco DOC covers a large flat area distinct from the DOCG hillside zones",
        "wine_styles": ["sparkling (spumante)", "frizzante", "still (tranquillo)"],
        "vineyard_area_ha": 24000,
    },
    {
        "name": "Bardolino",
        "region": "Veneto",
        "province": "Verona",
        "soil_types": ["glacial moraine", "clay-limestone", "gravel"],
        "elevation_range": "50-300m",
        "climate_note": "Sub-Mediterranean moderated by Lake Garda; lighter, fresher reds than neighboring Valpolicella",
        "wine_styles": ["dry red", "chiaretto (rosé)", "superiore"],
        "vineyard_area_ha": 2600,
    },
    {
        "name": "Custoza",
        "region": "Veneto",
        "province": "Verona",
        "soil_types": ["glacial moraine", "clay", "limestone"],
        "elevation_range": "50-200m",
        "climate_note": "Sub-Mediterranean with Lake Garda influence; morainic hills south of the lake",
        "wine_styles": ["dry white", "spumante", "passito"],
        "vineyard_area_ha": 1500,
    },
    {
        "name": "Gambellara",
        "region": "Veneto",
        "province": "Vicenza",
        "soil_types": ["volcanic basalt", "tufo", "clay"],
        "elevation_range": "50-300m",
        "climate_note": "Temperate; similar volcanic terroir to neighboring Soave but in Vicenza province",
        "wine_styles": ["dry white", "recioto (sweet)", "vin santo"],
        "vineyard_area_ha": 700,
    },
    {
        "name": "Breganze",
        "region": "Veneto",
        "province": "Vicenza",
        "soil_types": ["volcanic", "clay-limestone", "gravel"],
        "elevation_range": "100-400m",
        "climate_note": "Temperate continental; foothills of the Asiago plateau with volcanic soils",
        "wine_styles": ["dry red", "dry white", "torcolato (passito)"],
        "vineyard_area_ha": 500,
    },
    {
        "name": "Colli Euganei",
        "region": "Veneto",
        "province": "Padua",
        "soil_types": ["volcanic", "trachyte", "rhyolite", "clay"],
        "elevation_range": "50-400m",
        "climate_note": "Mediterranean microclimate on volcanic hills rising from the Paduan plain; unique geology from ancient eruptions",
        "wine_styles": ["dry red", "dry white", "fior d'arancio (Moscato)"],
        "vineyard_area_ha": 2000,
    },
    {
        "name": "Lugana",
        "region": "Veneto",
        "province": "Verona (and Brescia in Lombardy)",
        "soil_types": ["glacial clay", "morainic gravel", "calcareous"],
        "elevation_range": "50-150m",
        "climate_note": "Sub-Mediterranean; southern shore of Lake Garda with excellent temperature moderation for Turbiana (Trebbiano di Lugana)",
        "wine_styles": ["dry white", "superiore", "riserva", "late harvest"],
        "vineyard_area_ha": 2500,
    },
    {
        "name": "Valdadige",
        "region": "Veneto",
        "province": "Verona, Trento",
        "soil_types": ["alluvial gravel", "limestone", "clay"],
        "elevation_range": "50-400m",
        "climate_note": "Continental; follows the Adige River valley from Trentino into Veneto",
        "wine_styles": ["dry red", "dry white", "rosé"],
        "vineyard_area_ha": 1000,
    },
    {
        "name": "Piave",
        "region": "Veneto",
        "province": "Treviso, Venice",
        "soil_types": ["alluvial gravel", "clay", "sand"],
        "elevation_range": "10-100m",
        "climate_note": "Continental; flat gravelly plains of the Piave river providing well-drained conditions for Raboso, Merlot, and Tai",
        "wine_styles": ["dry red", "dry white"],
        "vineyard_area_ha": 3000,
    },
    {
        "name": "Lessini Durello",
        "region": "Veneto",
        "province": "Verona, Vicenza",
        "soil_types": ["volcanic basalt", "limestone", "clay"],
        "elevation_range": "100-600m",
        "climate_note": "Cool continental; high-altitude vineyards in the Lessini mountains; Durella grape produces high-acid wines ideal for sparkling",
        "wine_styles": ["sparkling (metodo classico)", "frizzante"],
        "vineyard_area_ha": 500,
    },

    # ── Lombardy ──
    {
        "name": "Oltrepò Pavese",
        "region": "Lombardy",
        "province": "Pavia",
        "soil_types": ["clay-limestone", "marl", "sandstone"],
        "elevation_range": "100-500m",
        "climate_note": "Continental; Apennine foothills south of the Po River; Italy's largest Pinot Nero growing area",
        "wine_styles": ["dry red", "dry white", "sparkling (metodo classico)", "frizzante"],
        "vineyard_area_ha": 13000,
    },
    {
        "name": "Garda",
        "region": "Lombardy",
        "province": "Brescia (and Verona in Veneto)",
        "soil_types": ["glacial moraine", "gravel", "clay"],
        "elevation_range": "50-300m",
        "climate_note": "Sub-Mediterranean; Lake Garda's thermal mass creates a mild microclimate ideal for Groppello, Marzemino, and olive cultivation",
        "wine_styles": ["dry red", "dry white", "chiaretto (rosé)"],
        "vineyard_area_ha": 2000,
    },
    {
        "name": "Valtellina",
        "region": "Lombardy",
        "province": "Sondrio",
        "soil_types": ["sandy-silty", "gneiss", "mica-schist"],
        "elevation_range": "300-700m",
        "climate_note": "Alpine; steep south-facing terraced vineyards on hand-maintained stone walls (muretti); Nebbiolo is locally called Chiavennasca",
        "wine_styles": ["dry red"],
        "vineyard_area_ha": 900,
    },
    {
        "name": "San Colombano al Lambro",
        "region": "Lombardy",
        "province": "Milan, Lodi, Pavia",
        "soil_types": ["clay-limestone", "gravel"],
        "elevation_range": "80-150m",
        "climate_note": "Continental; the only DOC in the Milan metropolitan area, on a small isolated hill south of the city",
        "wine_styles": ["dry red", "dry white"],
        "vineyard_area_ha": 100,
    },
    {
        "name": "Riviera del Garda Classico",
        "region": "Lombardy",
        "province": "Brescia",
        "soil_types": ["glacial moraine", "limestone", "clay"],
        "elevation_range": "65-400m",
        "climate_note": "Sub-Mediterranean; western shore of Lake Garda known for elegant Groppello-based reds and chiaretto rosé",
        "wine_styles": ["dry red", "chiaretto (rosé)", "superiore"],
        "vineyard_area_ha": 400,
    },
    {
        "name": "Cellatica",
        "region": "Lombardy",
        "province": "Brescia",
        "soil_types": ["limestone", "clay", "gravel"],
        "elevation_range": "200-400m",
        "climate_note": "Continental; hills northwest of Brescia adjacent to Franciacorta; blend of Barbera, Marzemino, Schiava, and Incrocio Terzi",
        "wine_styles": ["dry red", "superiore"],
        "vineyard_area_ha": 50,
    },

    # ── Trentino-Alto Adige ──
    {
        "name": "Alto Adige",
        "region": "Trentino-Alto Adige",
        "province": "Bolzano",
        "soil_types": ["porphyry", "limestone", "dolomite", "glacial moraine"],
        "elevation_range": "200-1000m",
        "climate_note": "Alpine continental; extreme diurnal temperature variation between warm sunny days and cool mountain nights; numerous subzones (Terlano, Caldaro, Santa Maddalena, etc.)",
        "wine_styles": ["dry white", "dry red", "rosé", "passito"],
        "vineyard_area_ha": 5300,
    },
    {
        "name": "Teroldego Rotaliano",
        "region": "Trentino-Alto Adige",
        "province": "Trento",
        "soil_types": ["alluvial gravel", "sand", "clay"],
        "elevation_range": "200-300m",
        "climate_note": "Continental; the Rotaliano plain is a flat alluvial area in the Adige Valley uniquely suited to Teroldego's vigorous growth",
        "wine_styles": ["dry red", "rosé", "superiore", "riserva"],
        "vineyard_area_ha": 450,
    },
    {
        "name": "Trentino",
        "region": "Trentino-Alto Adige",
        "province": "Trento",
        "soil_types": ["alluvial gravel", "limestone", "porphyry"],
        "elevation_range": "100-700m",
        "climate_note": "Continental Alpine; broad DOC covering the southern part of the region with various subzones along the Adige Valley",
        "wine_styles": ["dry red", "dry white", "rosé", "vin santo"],
        "vineyard_area_ha": 8000,
    },
    {
        "name": "Lago di Caldaro",
        "region": "Trentino-Alto Adige",
        "province": "Bolzano, Trento",
        "soil_types": ["porphyry", "clay-limestone", "glacial moraine"],
        "elevation_range": "200-600m",
        "climate_note": "Mediterranean pocket in the Alps; Lake Caldaro (Kalterer See) creates an unusually mild microclimate; traditionally Schiava (Vernatsch) territory",
        "wine_styles": ["dry red (light)"],
        "vineyard_area_ha": 300,
    },

    # ── Friuli Venezia Giulia ──
    {
        "name": "Collio",
        "region": "Friuli Venezia Giulia",
        "province": "Gorizia",
        "soil_types": ["ponca", "flysch", "marl-sandstone"],
        "elevation_range": "50-280m",
        "climate_note": "Temperate with Adriatic and Alpine influence; ponca (Eocene marl-sandstone) is the defining soil; arguably Italy's greatest white wine terroir",
        "wine_styles": ["dry white", "dry red", "orange (skin-contact)"],
        "vineyard_area_ha": 1500,
    },
    {
        "name": "Friuli Colli Orientali",
        "region": "Friuli Venezia Giulia",
        "province": "Udine",
        "soil_types": ["ponca", "flysch", "marl"],
        "elevation_range": "80-350m",
        "climate_note": "Temperate with good diurnal variation; ponca soils extend north from Collio with slightly more continental character",
        "wine_styles": ["dry white", "dry red", "sweet (picolit, verduzzo)"],
        "vineyard_area_ha": 2000,
    },
    {
        "name": "Friuli Grave",
        "region": "Friuli Venezia Giulia",
        "province": "Pordenone, Udine",
        "soil_types": ["alluvial gravel", "marl", "clay"],
        "elevation_range": "30-150m",
        "climate_note": "Continental; largest DOC in Friuli on the gravelly Tagliamento river plain; 'grave' means gravel",
        "wine_styles": ["dry white", "dry red"],
        "vineyard_area_ha": 8000,
    },
    {
        "name": "Friuli Isonzo",
        "region": "Friuli Venezia Giulia",
        "province": "Gorizia",
        "soil_types": ["alluvial gravel", "clay", "sand"],
        "elevation_range": "20-100m",
        "climate_note": "Temperate with Adriatic influence; gravelly Isonzo river plain warmer than Collio hills above; red gravel subsoil drains excellently",
        "wine_styles": ["dry white", "dry red"],
        "vineyard_area_ha": 1000,
    },
    {
        "name": "Carso",
        "region": "Friuli Venezia Giulia",
        "province": "Trieste, Gorizia",
        "soil_types": ["terra rossa", "limestone karst"],
        "elevation_range": "50-350m",
        "climate_note": "Extreme winds (bora) from the northeast; thin iron-rich red soils over limestone karst; tiny production from Vitovska, Malvasia Istriana, and Terrano",
        "wine_styles": ["dry white", "dry red"],
        "vineyard_area_ha": 50,
    },

    # ── Emilia-Romagna ──
    {
        "name": "Romagna Sangiovese",
        "region": "Emilia-Romagna",
        "province": "across Romagna",
        "soil_types": ["calcareous clay", "sand", "limestone"],
        "elevation_range": "50-400m",
        "climate_note": "Continental with Adriatic influence; Romagna's hillsides produce a distinctive, often lighter expression of Sangiovese",
        "wine_styles": ["dry red", "superiore", "riserva"],
        "vineyard_area_ha": 5500,
    },
    {
        "name": "Lambrusco di Sorbara",
        "region": "Emilia-Romagna",
        "province": "Modena",
        "soil_types": ["alluvial sand", "clay", "silt"],
        "elevation_range": "10-80m",
        "climate_note": "Continental; Po plain alluvial soils; Sorbara is considered the most refined Lambrusco subvariety with delicate floral character",
        "wine_styles": ["sparkling red", "frizzante red", "rosé"],
        "vineyard_area_ha": 1500,
    },
    {
        "name": "Lambrusco Grasparossa di Castelvetro",
        "region": "Emilia-Romagna",
        "province": "Modena",
        "soil_types": ["clay", "marl", "limestone"],
        "elevation_range": "50-300m",
        "climate_note": "Continental; foothills south of Modena at higher elevation than Sorbara; produces the fullest-bodied Lambrusco",
        "wine_styles": ["sparkling red", "frizzante red"],
        "vineyard_area_ha": 1000,
    },
    {
        "name": "Lambrusco Salamino di Santa Croce",
        "region": "Emilia-Romagna",
        "province": "Modena",
        "soil_types": ["alluvial clay", "sand", "silt"],
        "elevation_range": "10-50m",
        "climate_note": "Continental; flat plain near Carpi north of Modena; name comes from the salami-shaped grape clusters",
        "wine_styles": ["sparkling red", "frizzante red"],
        "vineyard_area_ha": 800,
    },
    {
        "name": "Gutturnio",
        "region": "Emilia-Romagna",
        "province": "Piacenza",
        "soil_types": ["clay", "limestone", "sandstone"],
        "elevation_range": "100-400m",
        "climate_note": "Continental; Colli Piacentini hills near Lombardy border; named after a Roman wine goblet (gutturnium)",
        "wine_styles": ["dry red", "frizzante red", "superiore", "riserva"],
        "vineyard_area_ha": 1000,
    },
    {
        "name": "Colli di Parma",
        "region": "Emilia-Romagna",
        "province": "Parma",
        "soil_types": ["clay", "limestone", "marl"],
        "elevation_range": "100-400m",
        "climate_note": "Continental; Apennine foothills south of Parma; produces varietal whites, reds, and the local sparkling Malvasia di Candia Aromatica",
        "wine_styles": ["dry white", "dry red", "frizzante"],
        "vineyard_area_ha": 500,
    },

    # ── Tuscany ──
    {
        "name": "Bolgheri",
        "region": "Tuscany",
        "province": "Livorno",
        "soil_types": ["gravel", "clay", "sand", "limestone"],
        "elevation_range": "10-150m",
        "climate_note": "Maritime Mediterranean; Tyrrhenian Sea proximity and the famous Viale dei Cipressi cooling breezes; birthplace of Italian 'Super Tuscans'",
        "wine_styles": ["dry red", "dry white", "rosé", "Sassicaia (subzone)"],
        "vineyard_area_ha": 1400,
    },
    {
        "name": "Rosso di Montalcino",
        "region": "Tuscany",
        "province": "Siena",
        "soil_types": ["clay", "limestone", "alberese", "galestro"],
        "elevation_range": "150-500m",
        "climate_note": "Warm Mediterranean; same terroir as Brunello but wine released earlier; serves as 'second wine' for many Brunello producers",
        "wine_styles": ["dry red"],
        "vineyard_area_ha": 700,
    },
    {
        "name": "Rosso di Montepulciano",
        "region": "Tuscany",
        "province": "Siena",
        "soil_types": ["clay", "sand", "limestone", "tufo"],
        "elevation_range": "250-600m",
        "climate_note": "Mediterranean continental; same zone as Vino Nobile but released after one year rather than two",
        "wine_styles": ["dry red"],
        "vineyard_area_ha": 400,
    },
    {
        "name": "Maremma Toscana",
        "region": "Tuscany",
        "province": "Grosseto",
        "soil_types": ["volcanic", "clay", "sand", "gravel"],
        "elevation_range": "10-400m",
        "climate_note": "Mediterranean; Tuscany's coastal and southern zone with warmer conditions than central Tuscany; diverse terroirs from coast to volcanic hills",
        "wine_styles": ["dry red", "dry white", "rosé"],
        "vineyard_area_ha": 3000,
    },
    {
        "name": "Montecucco",
        "region": "Tuscany",
        "province": "Grosseto",
        "soil_types": ["volcanic", "clay", "sand"],
        "elevation_range": "100-500m",
        "climate_note": "Mediterranean; south slope of Monte Amiata; transitional zone between Montalcino and the Maremma coast",
        "wine_styles": ["dry red", "dry white", "sangiovese riserva"],
        "vineyard_area_ha": 500,
    },
    {
        "name": "San Gimignano",
        "region": "Tuscany",
        "province": "Siena",
        "soil_types": ["sandy clay", "tufo", "limestone"],
        "elevation_range": "200-400m",
        "climate_note": "Mediterranean; DOC for red wines from the same commune as the Vernaccia di San Gimignano DOCG; San Gimignano Rosso features Sangiovese",
        "wine_styles": ["dry red", "vin santo"],
        "vineyard_area_ha": 300,
    },
    {
        "name": "Cortona",
        "region": "Tuscany",
        "province": "Arezzo",
        "soil_types": ["clay", "sand", "gravel", "alluvial"],
        "elevation_range": "200-600m",
        "climate_note": "Continental with some Mediterranean influence; southeast Tuscany near Umbria border; known for Syrah alongside Sangiovese",
        "wine_styles": ["dry red", "dry white", "vin santo"],
        "vineyard_area_ha": 300,
    },
    {
        "name": "Pomino",
        "region": "Tuscany",
        "province": "Florence",
        "soil_types": ["sand", "clay", "limestone"],
        "elevation_range": "400-700m",
        "climate_note": "Cool continental; one of Tuscany's highest-altitude DOCs in the Rufina hills east of Florence; suited to Chardonnay, Pinot Bianco, and Pinot Nero",
        "wine_styles": ["dry white", "dry red", "vin santo"],
        "vineyard_area_ha": 100,
    },
    {
        "name": "Elba",
        "region": "Tuscany",
        "province": "Livorno",
        "soil_types": ["granite", "schist", "iron-rich", "clay"],
        "elevation_range": "50-400m",
        "climate_note": "Maritime Mediterranean; island microclimate with sea breezes; mineral-rich soils from ancient mining; Ansonica (Inzolia) and Sangiovese",
        "wine_styles": ["dry white", "dry red", "aleatico passito"],
        "vineyard_area_ha": 150,
    },

    # ── Umbria ──
    {
        "name": "Orvieto",
        "region": "Umbria",
        "province": "Terni (and Viterbo in Lazio)",
        "soil_types": ["volcanic tufo", "clay", "limestone"],
        "elevation_range": "100-400m",
        "climate_note": "Mediterranean with continental nights; the city of Orvieto sits on a tufo cliff; historically produced sweet (abboccato) whites, now mostly dry",
        "wine_styles": ["dry white", "abboccato (off-dry)", "late harvest"],
        "vineyard_area_ha": 2000,
    },
    {
        "name": "Montefalco",
        "region": "Umbria",
        "province": "Perugia",
        "soil_types": ["clay-limestone", "marl", "sand"],
        "elevation_range": "220-470m",
        "climate_note": "Continental; DOC covers Rosso (Sangiovese blend) and Bianco; adjacent to and lower tier than the DOCG Montefalco Sagrantino",
        "wine_styles": ["dry red", "dry white"],
        "vineyard_area_ha": 800,
    },
    {
        "name": "Torgiano",
        "region": "Umbria",
        "province": "Perugia",
        "soil_types": ["alluvial clay", "sand", "gravel"],
        "elevation_range": "200-350m",
        "climate_note": "Continental with some Mediterranean influence; confluence of Tiber and Chiascio rivers; the Lungarotti family pioneered quality winemaking here",
        "wine_styles": ["dry red", "dry white", "rosé"],
        "vineyard_area_ha": 300,
    },
    {
        "name": "Spoleto",
        "region": "Umbria",
        "province": "Perugia",
        "soil_types": ["calcareous clay", "marl", "alluvial"],
        "elevation_range": "200-500m",
        "climate_note": "Continental; the Spoleto DOC recognizes Trebbiano Spoletino, a distinct variety unrelated to other Trebbiano types, producing complex mineral whites",
        "wine_styles": ["dry white", "superiore"],
        "vineyard_area_ha": 200,
    },

    # ── Marche ──
    {
        "name": "Verdicchio dei Castelli di Jesi",
        "region": "Marche",
        "province": "Ancona, Macerata",
        "soil_types": ["calcareous clay", "sandstone", "marl"],
        "elevation_range": "150-500m",
        "climate_note": "Continental with Adriatic influence; the Esino Valley funnels cooling breezes; Verdicchio achieves excellent minerality on these calcareous soils",
        "wine_styles": ["dry white", "superiore", "riserva", "spumante", "passito"],
        "vineyard_area_ha": 2500,
    },
    {
        "name": "Verdicchio di Matelica",
        "region": "Marche",
        "province": "Macerata, Ancona",
        "soil_types": ["calcareous clay", "marl", "limestone"],
        "elevation_range": "300-600m",
        "climate_note": "More continental than Jesi due to higher altitude inland valley; cooler nights produce more structured, mineral-driven Verdicchio",
        "wine_styles": ["dry white", "riserva", "spumante", "passito"],
        "vineyard_area_ha": 300,
    },
    {
        "name": "Rosso Piceno",
        "region": "Marche",
        "province": "across southern Marche",
        "soil_types": ["calcareous clay", "sand", "marl"],
        "elevation_range": "100-500m",
        "climate_note": "Mediterranean with Adriatic influence; Montepulciano and Sangiovese blend across the southern Marche hills",
        "wine_styles": ["dry red", "superiore"],
        "vineyard_area_ha": 2500,
    },
    {
        "name": "Lacrima di Morro d'Alba",
        "region": "Marche",
        "province": "Ancona",
        "soil_types": ["calcareous clay", "sand"],
        "elevation_range": "100-350m",
        "climate_note": "Mediterranean with Adriatic moderation; the Lacrima grape is almost exclusively cultivated in this small zone around Morro d'Alba",
        "wine_styles": ["dry red", "superiore", "passito"],
        "vineyard_area_ha": 250,
    },

    # ── Lazio ──
    {
        "name": "Frascati",
        "region": "Lazio",
        "province": "Rome",
        "soil_types": ["volcanic tufo", "peperino", "leucitite"],
        "elevation_range": "100-500m",
        "climate_note": "Mediterranean with volcanic microclimate; Castelli Romani zone southeast of Rome; historically Rome's house white wine",
        "wine_styles": ["dry white", "spumante", "cannellino (sweet)"],
        "vineyard_area_ha": 1200,
    },
    {
        "name": "Est! Est!! Est!!! di Montefiascone",
        "region": "Lazio",
        "province": "Viterbo",
        "soil_types": ["volcanic tufo", "clay", "limestone"],
        "elevation_range": "300-500m",
        "climate_note": "Mediterranean continental; shores of Lake Bolsena, a volcanic crater lake; the name derives from a medieval legend about a bishop's wine scout",
        "wine_styles": ["dry white"],
        "vineyard_area_ha": 300,
    },
    {
        "name": "Olevano Romano",
        "region": "Lazio",
        "province": "Rome",
        "soil_types": ["calcareous clay", "volcanic tufo"],
        "elevation_range": "200-500m",
        "climate_note": "Mediterranean continental; Cesanese-based reds from hills east of Rome",
        "wine_styles": ["dry red"],
        "vineyard_area_ha": 100,
    },

    # ── Campania ──
    {
        "name": "Lacryma Christi del Vesuvio",
        "region": "Campania",
        "province": "Naples",
        "soil_types": ["volcanic ash", "pumice", "lapilli"],
        "elevation_range": "50-450m",
        "climate_note": "Mediterranean with volcanic terroir; vineyards on the slopes of Mount Vesuvius in mineral-rich volcanic soils; phylloxera-resistant rootstocks not needed in some sandy volcanic areas",
        "wine_styles": ["dry red", "dry white", "rosé", "spumante"],
        "vineyard_area_ha": 600,
    },
    {
        "name": "Falanghina del Sannio",
        "region": "Campania",
        "province": "Benevento",
        "soil_types": ["calcareous clay", "volcanic tufo", "sand"],
        "elevation_range": "200-500m",
        "climate_note": "Continental inland; Sannio (ancient Samnite territory) in Benevento province; Falanghina Beneventana biotype thrives at elevation",
        "wine_styles": ["dry white", "spumante", "passito"],
        "vineyard_area_ha": 2000,
    },
    {
        "name": "Irpinia",
        "region": "Campania",
        "province": "Avellino",
        "soil_types": ["clay-limestone", "volcanic", "marl"],
        "elevation_range": "300-700m",
        "climate_note": "Continental at elevation; umbrella DOC for the Irpinia area; covers Aglianico, Fiano, Greco, and Coda di Volpe not qualifying for the stricter DOCGs",
        "wine_styles": ["dry red", "dry white", "rosé"],
        "vineyard_area_ha": 1500,
    },
    {
        "name": "Ischia",
        "region": "Campania",
        "province": "Naples",
        "soil_types": ["volcanic tufo", "pumice", "clay"],
        "elevation_range": "50-500m",
        "climate_note": "Maritime Mediterranean; island microclimate with volcanic soils; one of southern Italy's oldest wine-producing areas; key grapes Biancolella and Forastera",
        "wine_styles": ["dry white", "dry red"],
        "vineyard_area_ha": 150,
    },
    {
        "name": "Campi Flegrei",
        "region": "Campania",
        "province": "Naples",
        "soil_types": ["volcanic tufo", "pumice", "pozzolana"],
        "elevation_range": "20-300m",
        "climate_note": "Mediterranean with active volcanic geology; Campi Flegrei (Phlegraean Fields) is a volcanic caldera west of Naples; some ungrafted pre-phylloxera vines survive in the sandy volcanic soils",
        "wine_styles": ["dry white", "dry red"],
        "vineyard_area_ha": 100,
    },
    {
        "name": "Costa d'Amalfi",
        "region": "Campania",
        "province": "Salerno",
        "soil_types": ["limestone", "volcanic", "clay"],
        "elevation_range": "50-650m",
        "climate_note": "Mediterranean; dramatic terraced vineyards on the Amalfi Coast cliff faces; three subzones: Furore, Ravello, and Tramonti; heroic viticulture",
        "wine_styles": ["dry white", "dry red", "rosé"],
        "vineyard_area_ha": 50,
    },

    # ── Puglia ──
    {
        "name": "Primitivo di Manduria",
        "region": "Puglia",
        "province": "Taranto, Brindisi",
        "soil_types": ["terra rossa", "calcareous", "sandy"],
        "elevation_range": "20-150m",
        "climate_note": "Hot Mediterranean; iron-rich red terra rossa over limestone in the Salento peninsula; extreme heat concentrates sugars naturally",
        "wine_styles": ["dry red", "dolce naturale (sweet)"],
        "vineyard_area_ha": 4000,
    },
    {
        "name": "Salice Salentino",
        "region": "Puglia",
        "province": "Lecce, Brindisi",
        "soil_types": ["terra rossa", "calcareous", "clay"],
        "elevation_range": "20-100m",
        "climate_note": "Hot Mediterranean; flat Salento peninsula between the Adriatic and Ionian seas; Negroamaro is the dominant variety",
        "wine_styles": ["dry red", "rosé", "riserva"],
        "vineyard_area_ha": 2000,
    },
    {
        "name": "Castel del Monte",
        "region": "Puglia",
        "province": "Bari, Barletta-Andria-Trani",
        "soil_types": ["calcareous tufo", "terra rossa", "clay"],
        "elevation_range": "200-500m",
        "climate_note": "Mediterranean with altitude; Murgia plateau around Frederick II's octagonal castle; among Puglia's highest and coolest vineyard sites",
        "wine_styles": ["dry red", "dry white", "rosé", "riserva"],
        "vineyard_area_ha": 1500,
    },
    {
        "name": "Gioia del Colle",
        "region": "Puglia",
        "province": "Bari",
        "soil_types": ["calcareous clay", "terra rossa", "limestone"],
        "elevation_range": "300-500m",
        "climate_note": "Mediterranean with continental influence from Murgia plateau altitude; cooler than coastal Puglia; produces a more elegant expression of Primitivo",
        "wine_styles": ["dry red", "dry white", "rosé"],
        "vineyard_area_ha": 800,
    },
    {
        "name": "Copertino",
        "region": "Puglia",
        "province": "Lecce",
        "soil_types": ["terra rossa", "calcareous", "clay"],
        "elevation_range": "20-80m",
        "climate_note": "Hot Mediterranean; central Salento; Negroamaro-based reds with long riserva aging potential",
        "wine_styles": ["dry red", "rosé", "riserva"],
        "vineyard_area_ha": 500,
    },
    {
        "name": "Locorotondo",
        "region": "Puglia",
        "province": "Bari, Brindisi",
        "soil_types": ["calcareous", "terra rossa", "clay"],
        "elevation_range": "350-450m",
        "climate_note": "Mediterranean continental; Itria Valley (Valle d'Itria) known for trulli architecture and white wines from Verdeca and Bianco d'Alessano",
        "wine_styles": ["dry white", "spumante"],
        "vineyard_area_ha": 300,
    },

    # ── Basilicata ──
    {
        "name": "Aglianico del Vulture",
        "region": "Basilicata",
        "province": "Potenza",
        "soil_types": ["volcanic", "tufo", "ash", "pumice"],
        "elevation_range": "200-700m",
        "climate_note": "Continental at altitude on Monte Vulture; dramatic diurnal variation; volcanic soils rich in potassium and iron; Aglianico's longest ripening season in Italy",
        "wine_styles": ["dry red", "spumante"],
        "vineyard_area_ha": 1100,
    },
    {
        "name": "Matera",
        "region": "Basilicata",
        "province": "Matera",
        "soil_types": ["calcareous clay", "tufo", "sand"],
        "elevation_range": "200-500m",
        "climate_note": "Mediterranean continental; the Matera DOC was established in 2005 covering the area around the UNESCO World Heritage Sassi caves",
        "wine_styles": ["dry red", "dry white", "rosé", "spumante"],
        "vineyard_area_ha": 200,
    },

    # ── Calabria ──
    {
        "name": "Cirò",
        "region": "Calabria",
        "province": "Crotone",
        "soil_types": ["calcareous clay", "sand", "limestone"],
        "elevation_range": "50-300m",
        "climate_note": "Hot Mediterranean with Ionian Sea breezes; one of the oldest continuously producing wine zones in the world, dating to Greek colonization; Gaglioppo is the sole red grape",
        "wine_styles": ["dry red", "dry white", "rosé", "classico superiore"],
        "vineyard_area_ha": 400,
    },
    {
        "name": "Melissa",
        "region": "Calabria",
        "province": "Crotone",
        "soil_types": ["clay", "sand", "limestone"],
        "elevation_range": "50-400m",
        "climate_note": "Mediterranean; adjacent to Cirò on the Ionian coast; Gaglioppo reds and Greco Bianco whites",
        "wine_styles": ["dry red", "dry white"],
        "vineyard_area_ha": 100,
    },
    {
        "name": "Savuto",
        "region": "Calabria",
        "province": "Cosenza, Catanzaro",
        "soil_types": ["clay", "granite", "alluvial"],
        "elevation_range": "100-500m",
        "climate_note": "Mediterranean with mountain influence; Savuto River valley between the Sila and Coastal mountain ranges; Gaglioppo and local varieties",
        "wine_styles": ["dry red", "rosé"],
        "vineyard_area_ha": 100,
    },

    # ── Sicily ──
    {
        "name": "Etna",
        "region": "Sicily",
        "province": "Catania",
        "soil_types": ["volcanic lava", "pumice", "ash", "basalt"],
        "elevation_range": "350-1000m",
        "climate_note": "Unique Alpine-Mediterranean hybrid; dramatic altitude range on Europe's most active volcano; distinct contrade (vineyard sites) with north/south exposure differences; snow-capped in winter, hot in summer",
        "wine_styles": ["dry red", "dry white", "rosé", "spumante"],
        "vineyard_area_ha": 1200,
    },
    {
        "name": "Marsala",
        "region": "Sicily",
        "province": "Trapani",
        "soil_types": ["calcareous clay", "sand", "tufo"],
        "elevation_range": "10-200m",
        "climate_note": "Hot Mediterranean; western Sicily near the African coast; fortified wine production dating to 1773 when English merchant John Woodhouse began exports",
        "wine_styles": ["fortified (fine, superiore, vergine)", "secco", "semisecco", "dolce"],
        "vineyard_area_ha": 2000,
    },
    {
        "name": "Noto",
        "region": "Sicily",
        "province": "Siracusa",
        "soil_types": ["calcareous", "sand", "clay"],
        "elevation_range": "50-250m",
        "climate_note": "Hot Mediterranean; southeastern Sicily in the province of Siracusa; Nero d'Avola and Moscato di Noto (sweet)",
        "wine_styles": ["dry red", "sweet white (moscato)", "spumante"],
        "vineyard_area_ha": 500,
    },
    {
        "name": "Faro",
        "region": "Sicily",
        "province": "Messina",
        "soil_types": ["sand", "clay-limestone", "gravel"],
        "elevation_range": "50-500m",
        "climate_note": "Mediterranean with strong sea influence from the Strait of Messina; tiny production zone; Nerello Mascalese and Nerello Cappuccio blend",
        "wine_styles": ["dry red"],
        "vineyard_area_ha": 15,
    },
    {
        "name": "Pantelleria",
        "region": "Sicily",
        "province": "Trapani",
        "soil_types": ["volcanic", "pumice", "lava rock"],
        "elevation_range": "10-400m",
        "climate_note": "Hot Mediterranean island climate; fierce winds require alberello (bush vine) training in hollowed pits; Zibibbo cultivation is UNESCO intangible heritage",
        "wine_styles": ["passito (sweet)", "moscato", "dry white"],
        "vineyard_area_ha": 400,
    },
    {
        "name": "Alcamo",
        "region": "Sicily",
        "province": "Trapani, Palermo",
        "soil_types": ["calcareous clay", "sand", "tufo"],
        "elevation_range": "50-400m",
        "climate_note": "Hot Mediterranean; western Sicily between Palermo and Trapani; traditionally Catarratto white wines, now increasingly international varieties",
        "wine_styles": ["dry white", "dry red", "spumante"],
        "vineyard_area_ha": 2000,
    },
    {
        "name": "Contea di Sclafani",
        "region": "Sicily",
        "province": "Palermo",
        "soil_types": ["clay", "limestone", "sand"],
        "elevation_range": "300-700m",
        "climate_note": "Mediterranean continental; high-altitude inland Sicily; cooler conditions than coastal zones allow for elegant wines from both indigenous and international varieties",
        "wine_styles": ["dry red", "dry white", "rosé", "sweet"],
        "vineyard_area_ha": 500,
    },

    # ── Sardinia ──
    {
        "name": "Cannonau di Sardegna",
        "region": "Sardinia",
        "province": "island-wide",
        "soil_types": ["granite", "schist", "sand", "clay", "limestone"],
        "elevation_range": "50-700m",
        "climate_note": "Mediterranean with mistral wind influence; island-wide DOC allowing production across all Sardinia; subzones include Jerzu, Capo Ferrato, and Oliena/Nepente di Oliena",
        "wine_styles": ["dry red", "rosé", "passito", "liquoroso"],
        "vineyard_area_ha": 6200,
    },
    {
        "name": "Vermentino di Sardegna",
        "region": "Sardinia",
        "province": "island-wide",
        "soil_types": ["granite", "sand", "schist", "limestone"],
        "elevation_range": "20-500m",
        "climate_note": "Mediterranean with sea breezes; island-wide DOC distinct from the DOCG Vermentino di Gallura in the northeast; lighter style than Gallura",
        "wine_styles": ["dry white", "frizzante", "spumante"],
        "vineyard_area_ha": 4000,
    },
    {
        "name": "Carignano del Sulcis",
        "region": "Sardinia",
        "province": "Carbonia-Iglesias",
        "soil_types": ["sand", "clay", "limestone"],
        "elevation_range": "10-200m",
        "climate_note": "Hot Mediterranean with fierce mistral winds; sandy soils protect ungrafted, pre-phylloxera Carignano bush vines (alberello) in the Sulcis area of southwestern Sardinia",
        "wine_styles": ["dry red", "rosé", "passito"],
        "vineyard_area_ha": 1700,
    },
    {
        "name": "Monica di Sardegna",
        "region": "Sardinia",
        "province": "island-wide",
        "soil_types": ["granite", "sand", "clay"],
        "elevation_range": "50-500m",
        "climate_note": "Mediterranean; island-wide DOC for the Monica grape, producing light, fruity reds often consumed young",
        "wine_styles": ["dry red", "frizzante"],
        "vineyard_area_ha": 1000,
    },

    # ── Abruzzo ──
    {
        "name": "Montepulciano d'Abruzzo",
        "region": "Abruzzo",
        "province": "across Abruzzo",
        "soil_types": ["calcareous clay", "alluvial", "sand"],
        "elevation_range": "50-500m",
        "climate_note": "Mediterranean with Apennine cooling from the Gran Sasso and Majella mountains; the Adriatic coast moderates eastern vineyards while inland sites benefit from altitude",
        "wine_styles": ["dry red", "cerasuolo (rosé)"],
        "vineyard_area_ha": 17000,
    },
    {
        "name": "Trebbiano d'Abruzzo",
        "region": "Abruzzo",
        "province": "across Abruzzo",
        "soil_types": ["calcareous clay", "sand", "alluvial"],
        "elevation_range": "50-450m",
        "climate_note": "Mediterranean with mountain influence; most production is from Bombino Bianco (common Trebbiano), but the rare authentic Trebbiano d'Abruzzo clone produces much finer wines",
        "wine_styles": ["dry white"],
        "vineyard_area_ha": 8000,
    },
    {
        "name": "Cerasuolo d'Abruzzo",
        "region": "Abruzzo",
        "province": "across Abruzzo",
        "soil_types": ["calcareous clay", "sand", "alluvial"],
        "elevation_range": "50-500m",
        "climate_note": "Same terroir as Montepulciano d'Abruzzo; cerasuolo (cherry-colored) rosé from Montepulciano grapes with brief skin contact; elevated to DOC from subtype in 2010",
        "wine_styles": ["rosé (cerasuolo)"],
        "vineyard_area_ha": 3000,
    },

    # ── Molise ──
    {
        "name": "Biferno",
        "region": "Molise",
        "province": "Campobasso",
        "soil_types": ["clay", "limestone", "sand"],
        "elevation_range": "100-400m",
        "climate_note": "Continental with Adriatic influence; Biferno River valley; Montepulciano-based reds and Trebbiano whites",
        "wine_styles": ["dry red", "dry white", "rosé"],
        "vineyard_area_ha": 200,
    },
    {
        "name": "Tintilia del Molise",
        "region": "Molise",
        "province": "across Molise",
        "soil_types": ["clay", "limestone", "calcareous"],
        "elevation_range": "200-600m",
        "climate_note": "Continental mountain climate; Tintilia is Molise's signature indigenous grape, nearly extinct before revival in the 1990s; only DOC exclusively for a native Molise variety",
        "wine_styles": ["dry red", "rosé"],
        "vineyard_area_ha": 200,
    },

    # ── Liguria ──
    {
        "name": "Cinque Terre",
        "region": "Liguria",
        "province": "La Spezia",
        "soil_types": ["schist", "clay", "limestone"],
        "elevation_range": "20-450m",
        "climate_note": "Maritime Mediterranean; dramatic steep terraced vineyards on sea cliffs; among Italy's most extreme examples of heroic viticulture; Sciacchetrà is the rare passito version",
        "wine_styles": ["dry white", "sciacchetrà (passito)"],
        "vineyard_area_ha": 100,
    },
    {
        "name": "Riviera Ligure di Ponente",
        "region": "Liguria",
        "province": "Imperia, Savona",
        "soil_types": ["calcareous clay", "sand", "limestone"],
        "elevation_range": "50-400m",
        "climate_note": "Maritime Mediterranean; western Ligurian Riviera; Pigato (possibly identical to Vermentino) and Rossese are the key varieties",
        "wine_styles": ["dry white", "dry red"],
        "vineyard_area_ha": 300,
    },
    {
        "name": "Colli di Luni",
        "region": "Liguria",
        "province": "La Spezia (and Massa-Carrara in Tuscany)",
        "soil_types": ["clay-limestone", "sand", "marl"],
        "elevation_range": "50-400m",
        "climate_note": "Maritime Mediterranean; eastern Liguria at the Tuscany border; Vermentino achieves a coastal, saline expression",
        "wine_styles": ["dry white", "dry red"],
        "vineyard_area_ha": 200,
    },

    # ── Valle d'Aosta ──
    {
        "name": "Valle d'Aosta",
        "region": "Valle d'Aosta",
        "province": "Aosta",
        "soil_types": ["glacial moraine", "granite", "schist", "sand"],
        "elevation_range": "400-1200m",
        "climate_note": "Alpine; Italy's smallest wine region with some of Europe's highest vineyards; south-facing terraces on the Dora Baltea valley; 7 subzones including Chambave, Torrette, Donnas, and Blanc de Morgex et de La Salle (up to 1200m)",
        "wine_styles": ["dry red", "dry white", "sweet"],
        "vineyard_area_ha": 400,
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
            logger.warning(f"Cloudflare 403 on {url} — falling back to knowledge base")
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
    """Build facts about Italian wine regions (climate, soil, elevation, stats)."""
    facts = []

    for region in REGIONAL_DATABASE:
        name = region["name"]
        italian = region["italian_name"]
        entities = [{"type": "region", "name": name}]
        base_tags = ["italy", name.lower().replace(" ", "_").replace("'", "")]

        # Climate
        facts.append(_make_fact(
            f"The {name} ({italian}) wine region has a {region['climate']} climate.",
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
                f"The predominant soil types in the {name} wine region include {soil_list}.",
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
                f"Vineyards in the {name} wine region are planted at elevations ranging from {region['elevation_range']}.",
                domain="viticulture",
                source_id=source_id,
                subdomain="terrain",
                entities=entities,
                tags=base_tags + ["elevation"],
            ))

        # Rainfall
        if region.get("annual_rainfall_mm"):
            facts.append(_make_fact(
                f"The {name} wine region receives approximately {region['annual_rainfall_mm']}mm of annual rainfall.",
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
                f"The principal grape varieties of the {name} wine region include {grapes_str}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="regional_grapes",
                entities=grape_entities,
                tags=base_tags + ["grapes"],
            ))

        # DOC/DOCG count
        if region.get("docg_count") is not None and region.get("doc_count") is not None:
            facts.append(_make_fact(
                f"The {name} wine region has {region['docg_count']} DOCG and {region['doc_count']} DOC appellations.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="appellations",
                entities=entities,
                confidence=0.95,
                tags=base_tags + ["appellations", "statistics"],
            ))

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# FACT BUILDERS — DOCG Supplement
# ═══════════════════════════════════════════════════════════════════════════════


def _build_docg_supplement_facts(source_id: str) -> list[dict]:
    """Build supplementary DOCG facts (climate, soil, elevation, communes, subzones).
    These complement italy.py's basic classification/grape/aging facts.
    """
    facts = []

    for docg_name, data in DOCG_SUPPLEMENT.items():
        region = data.get("region", "")
        entities = [
            {"type": "appellation", "name": docg_name},
            {"type": "region", "name": region},
        ]
        base_tags = ["italy", "docg", region.lower().replace(" ", "_").replace("'", "")]

        # Climate
        if data.get("climate"):
            facts.append(_make_fact(
                f"The {docg_name} DOCG production zone has a {data['climate']} climate.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="climate",
                entities=entities,
                tags=base_tags + ["climate", docg_name.lower().replace(" ", "_")],
            ))

        # Soil types
        if data.get("soil_types"):
            soil_list = ", ".join(data["soil_types"])
            facts.append(_make_fact(
                f"The soils in the {docg_name} DOCG zone are primarily {soil_list}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="terroir",
                entities=entities,
                tags=base_tags + ["soil", "terroir", docg_name.lower().replace(" ", "_")],
            ))

        # Soil details
        if data.get("soil_details"):
            facts.append(_make_fact(
                f"{data['soil_details']}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="terroir",
                entities=entities,
                tags=base_tags + ["soil", "terroir", docg_name.lower().replace(" ", "_")],
            ))

        # Elevation
        if data.get("elevation_range"):
            facts.append(_make_fact(
                f"Vineyards in {docg_name} DOCG are planted between {data['elevation_range']} elevation.",
                domain="viticulture",
                source_id=source_id,
                subdomain="terrain",
                entities=entities,
                tags=base_tags + ["elevation", docg_name.lower().replace(" ", "_")],
            ))

        # Vineyard area
        if data.get("vineyard_area_ha"):
            facts.append(_make_fact(
                f"The {docg_name} DOCG has approximately {data['vineyard_area_ha']:,} hectares of vineyard.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="statistics",
                entities=entities,
                confidence=0.95,
                tags=base_tags + ["vineyard_area", docg_name.lower().replace(" ", "_")],
            ))

        # Communes
        if data.get("communes") and len(data["communes"]) > 0:
            communes_str = ", ".join(data["communes"])
            facts.append(_make_fact(
                f"The {docg_name} DOCG production zone encompasses the communes of {communes_str}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="geography",
                entities=entities,
                tags=base_tags + ["communes", "geography", docg_name.lower().replace(" ", "_")],
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
        base_tags = ["italy", "grape_variety", grape["color"]]

        # Origin
        if grape.get("origin") == "autochthonous" and grape.get("origin_region"):
            facts.append(_make_fact(
                f"{name} is an indigenous Italian grape variety originating from the {grape['origin_region']} region.",
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
                f"{name} is a principal grape in the following Italian appellations: {denoms_str}.",
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
                f"{name} is cultivated in the Italian regions of {regions_str}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="distribution",
                entities=region_entities,
                tags=base_tags + ["distribution"],
            ))

        # Vineyard area
        if grape.get("vineyard_area_ha"):
            facts.append(_make_fact(
                f"Italy has approximately {grape['vineyard_area_ha']:,} hectares planted with {name}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="statistics",
                entities=entities,
                confidence=0.95,
                tags=base_tags + ["vineyard_area", "statistics"],
            ))

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# FACT BUILDERS — Production Statistics
# ═══════════════════════════════════════════════════════════════════════════════


def _build_production_stats_facts(source_id: str) -> list[dict]:
    """Build regional production statistics facts."""
    facts = []

    for region_name, stats in PRODUCTION_STATS.items():
        entities = [{"type": "region", "name": region_name}]
        base_tags = ["italy", "statistics", region_name.lower().replace(" ", "_").replace("'", "")]

        # Production volume
        if stats.get("production_hl"):
            hl = stats["production_hl"]
            if hl >= 1_000_000:
                formatted = f"{hl / 1_000_000:.1f} million"
            else:
                formatted = f"{hl:,}"
            facts.append(_make_fact(
                f"{region_name} produces approximately {formatted} hectoliters of wine annually.",
                domain="wine_business",
                source_id=source_id,
                subdomain="production",
                entities=entities,
                confidence=0.95,
                tags=base_tags + ["production"],
            ))

        # DOC/DOCG percentage
        if stats.get("doc_docg_pct"):
            facts.append(_make_fact(
                f"Approximately {stats['doc_docg_pct']}% of {region_name}'s wine production carries DOC or DOCG classification.",
                domain="wine_business",
                source_id=source_id,
                subdomain="classification",
                entities=entities,
                confidence=0.95,
                tags=base_tags + ["classification", "quality"],
            ))

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# FACT BUILDERS — MeGA / UGA / Subzone Data
# ═══════════════════════════════════════════════════════════════════════════════


def _build_mega_uga_facts(source_id: str) -> list[dict]:
    """Build facts about MeGA, UGA, and subzone designations."""
    facts = []

    for docg_name, data in MEGA_UGA_DATABASE.items():
        entities = [{"type": "appellation", "name": docg_name}]
        base_tags = ["italy", "subzones", docg_name.lower().replace(" ", "_")]

        # Description
        if data.get("description"):
            facts.append(_make_fact(
                data["description"],
                domain="wine_regions",
                source_id=source_id,
                subdomain="subzones",
                entities=entities,
                tags=base_tags + [data["type"]],
            ))

        # Notable subzones
        if data.get("notable") and len(data["notable"]) > 0:
            notable_str = ", ".join(data["notable"])
            facts.append(_make_fact(
                f"Notable {data['type']} designations within {docg_name} include {notable_str}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="subzones",
                entities=entities + [{"type": "vineyard", "name": n} for n in data["notable"][:5]],
                tags=base_tags + [data["type"], "notable"],
            ))

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# FACT BUILDERS — DOC Enriched (soil, elevation, climate, wine styles)
# ═══════════════════════════════════════════════════════════════════════════════


def _build_doc_enriched_facts(source_id: str) -> list[dict]:
    """Build enriched DOC facts focusing on terroir data (soil, elevation, climate, wine styles).
    These complement italy.py's basic DOC facts (name/region/grapes/colors).
    """
    facts = []

    for doc in DOC_ENRICHED_DATABASE:
        name = doc["name"]
        region = doc.get("region", "")
        province = doc.get("province", "")
        entities = [
            {"type": "appellation", "name": name},
            {"type": "region", "name": region},
        ]
        base_tags = ["italy", "doc", region.lower().replace(" ", "_").replace("'", "")]

        # Soil types
        if doc.get("soil_types") and doc["soil_types"] != ["varied"]:
            soil_list = ", ".join(doc["soil_types"])
            facts.append(_make_fact(
                f"Vineyards in the {name} DOC grow on {soil_list} soils.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="terroir",
                entities=entities,
                tags=base_tags + ["soil", "terroir", name.lower().replace(" ", "_").replace("'", "")],
            ))

        # Elevation
        if doc.get("elevation_range"):
            facts.append(_make_fact(
                f"The {name} DOC vineyard area spans elevations of {doc['elevation_range']}.",
                domain="viticulture",
                source_id=source_id,
                subdomain="terrain",
                entities=entities,
                tags=base_tags + ["elevation", name.lower().replace(" ", "_").replace("'", "")],
            ))

        # Climate note
        if doc.get("climate_note"):
            facts.append(_make_fact(
                f"The {name} DOC has {doc['climate_note']}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="climate",
                entities=entities,
                tags=base_tags + ["climate", name.lower().replace(" ", "_").replace("'", "")],
            ))

        # Wine styles
        if doc.get("wine_styles"):
            styles_str = ", ".join(doc["wine_styles"])
            facts.append(_make_fact(
                f"The {name} DOC produces wines in the following styles: {styles_str}.",
                domain="winemaking",
                source_id=source_id,
                subdomain="wine_styles",
                entities=entities,
                tags=base_tags + ["wine_styles", name.lower().replace(" ", "_").replace("'", "")],
            ))

        # Province location
        if province and province not in ("region-wide", "island-wide"):
            facts.append(_make_fact(
                f"The {name} DOC is located in the province of {province} in {region}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="geography",
                entities=entities,
                tags=base_tags + ["geography", "province"],
            ))

        # Vineyard area
        if doc.get("vineyard_area_ha"):
            facts.append(_make_fact(
                f"The {name} DOC has approximately {doc['vineyard_area_ha']:,} hectares under vine.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="statistics",
                entities=entities,
                confidence=0.95,
                tags=base_tags + ["vineyard_area", "statistics"],
            ))

        # Superiore aging
        if doc.get("superiore_aging_months"):
            facts.append(_make_fact(
                f"The Superiore version of {name} DOC requires a minimum of {doc['superiore_aging_months']} months aging.",
                domain="winemaking",
                source_id=source_id,
                subdomain="production_rules",
                entities=entities,
                tags=base_tags + ["aging", "superiore"],
            ))

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# PIPELINE
# ═══════════════════════════════════════════════════════════════════════════════


def _get_source_id() -> str:
    """Register and return the IWC source ID."""
    return ensure_source(
        name=SOURCE["name"],
        url=SOURCE["url"],
        source_type=SOURCE["source_type"],
        tier=SOURCE["tier"],
        language=SOURCE["language"],
    )


def _build_all_facts(source_id: str, data_type: str = None, region_filter: str = None) -> list[dict]:
    """Build all facts, optionally filtered by type or region."""
    all_facts = []

    builders = {
        "region": _build_regional_facts,
        "docg": _build_docg_supplement_facts,
        "doc": _build_doc_enriched_facts,
        "grape": _build_grape_variety_facts,
        "stats": _build_production_stats_facts,
        "mega": _build_mega_uga_facts,
    }

    if data_type and data_type in builders:
        all_facts = builders[data_type](source_id)
    else:
        for builder in builders.values():
            all_facts.extend(builder(source_id))

    # Region filter
    if region_filter:
        region_lower = region_filter.lower()
        all_facts = [
            f for f in all_facts
            if region_lower in f.get("fact_text", "").lower()
            or any(region_lower in t for t in f.get("tags", []))
        ]

    # Deduplicate within run
    seen = set()
    unique = []
    for f in all_facts:
        if f["fact_text"] not in seen:
            seen.add(f["fact_text"])
            unique.append(f)

    return unique


def run_all(dry_run: bool = False, data_type: str = None, region_filter: str = None) -> dict:
    """Build and insert all facts. Returns summary dict."""
    source_id = _get_source_id()
    facts = _build_all_facts(source_id, data_type=data_type, region_filter=region_filter)

    summary = {
        "total_generated": len(facts),
        "total_inserted": 0,
    }

    if dry_run:
        click.echo(f"\n[DRY RUN] Would insert {len(facts)} facts from Italian Wine Central")

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

    logger.info(f"Inserted {inserted} new facts from Italian Wine Central (duplicates skipped)")
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

    # (g) Overlap check with italy.py patterns
    italy_patterns = [
        r"^.+ is a DOCG appellation in the .+ region of Italy\.$",
        r"^.+ DOCG requires .+%",
        r"^.+ DOCG must be aged for minimum .+ months",
        r"^.+ is a DOC appellation in the .+ region of Italy\.$",
        r"^.+ DOC is primarily made from",
        r"^.+ DOC produces .+ wine\.$",
    ]
    overlap_count = 0
    for f in facts:
        for pat in italy_patterns:
            if re.match(pat, f["fact_text"]):
                overlap_count += 1
                break
    click.echo(f"\n  Potential italy.py overlaps: {overlap_count}")


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
        "DOCG Supplement": _build_docg_supplement_facts,
        "DOC Enriched": _build_doc_enriched_facts,
        "Grape Varieties": _build_grape_variety_facts,
        "Production Stats": _build_production_stats_facts,
        "MeGA/UGA": _build_mega_uga_facts,
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
    type=click.Choice(["region", "docg", "doc", "grape", "stats", "mega"]),
    help="Extract a specific data category",
)
@click.option("--region", "region_filter", type=str, help="Filter by region name")
@click.option("--list", "list_sources", is_flag=True, help="List available data categories")
@click.option("--dry-run", is_flag=True, help="Extract facts but do not insert into DB")
@click.option("--validate", "validate_flag", is_flag=True, help="Run quality checks")
@click.option("--test-run", is_flag=True, help="Limited test with report")
@click.option("--cleanup", is_flag=True, help="With --test-run, delete inserted facts after reporting")
def main(
    run_all_flag: bool,
    data_type: Optional[str],
    region_filter: Optional[str],
    list_sources: bool,
    dry_run: bool,
    validate_flag: bool,
    test_run: bool,
    cleanup: bool,
) -> None:
    """OenoBench Italian Wine Central Scraper — Climate, soil, grape variety, and appellation data."""
    logger.add("data/logs/italian_wine_central_{time}.log", rotation="10 MB")

    if list_sources:
        click.echo("\nAvailable data categories:")
        click.echo(f"  {'region':12s} — 20 Italian wine regions (climate, soil, elevation)")
        click.echo(f"  {'docg':12s} — DOCG supplement data (climate, soil, communes, subzones)")
        click.echo(f"  {'doc':12s} — {len(DOC_ENRICHED_DATABASE)} DOC appellations (soil, elevation, climate, wine styles)")
        click.echo(f"  {'grape':12s} — {len(GRAPE_VARIETY_DATABASE)} grape variety profiles")
        click.echo(f"  {'stats':12s} — Regional production statistics")
        click.echo(f"  {'mega':12s} — MeGA/UGA/subzone designations")
        click.echo(f"\nKnowledge base coverage:")
        click.echo(f"  Regions:       {len(REGIONAL_DATABASE)}")
        click.echo(f"  DOCG entries:  {len(DOCG_SUPPLEMENT)}")
        click.echo(f"  DOC entries:   {len(DOC_ENRICHED_DATABASE)}")
        click.echo(f"  Grape varieties: {len(GRAPE_VARIETY_DATABASE)}")
        click.echo(f"  MeGA/UGA DOCGs: {len(MEGA_UGA_DATABASE)}")
        return

    if validate_flag:
        click.echo("Running validation on all categories...")
        source_id = _get_source_id()
        all_facts = _build_all_facts(source_id, data_type=data_type, region_filter=region_filter)
        validate_facts(all_facts)
        return

    if test_run:
        run_test(cleanup=cleanup)
        return

    if run_all_flag or data_type or region_filter:
        summary = run_all(dry_run=dry_run, data_type=data_type, region_filter=region_filter)
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
