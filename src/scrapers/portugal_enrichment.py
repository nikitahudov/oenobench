"""
OenoBench — Portuguese Wine Enrichment Scraper

Comprehensive knowledge base covering Portuguese wine regions, Port wine styles,
Madeira wine, grape varieties, and the Portuguese wine classification system.

Focus areas: regional terroir (climate, soil, elevation), Port wine (styles,
sub-regions, classification, benefício), Madeira wine (noble grapes, aging,
history), native grape varieties, and the DOC/VR classification hierarchy.

Usage:
    python -m src.scrapers.portugal_enrichment --all
    python -m src.scrapers.portugal_enrichment --type region
    python -m src.scrapers.portugal_enrichment --type port
    python -m src.scrapers.portugal_enrichment --type madeira
    python -m src.scrapers.portugal_enrichment --type grape
    python -m src.scrapers.portugal_enrichment --type classification
    python -m src.scrapers.portugal_enrichment --dry-run
    python -m src.scrapers.portugal_enrichment --validate
    python -m src.scrapers.portugal_enrichment --test-run
    python -m src.scrapers.portugal_enrichment --list
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
    "name": "Portuguese Wine Reference Database",
    "url": "https://www.winesofportugal.info",
    "source_type": "reference",
    "tier": "tier_2_authoritative",
    "language": "en",
}


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Regional Data
# ═══════════════════════════════════════════════════════════════════════════════

REGION_DATABASE = [
    {
        "name": "Douro/Porto",
        "portuguese_name": "Douro e Porto",
        "climate": "extreme continental",
        "climate_details": "Summers are scorchingly hot (often exceeding 40°C) in the sheltered Douro Valley, while winters are cold with temperatures dropping below freezing; the surrounding mountain ranges block Atlantic moisture, creating a rain shadow with only 400-600mm of annual rainfall in the upper Douro",
        "soil_types": ["schist", "granite", "clay-schist"],
        "soil_details": "The Douro Valley is dominated by Pre-Cambrian schist soils on steep terraced hillsides, with granite intrusions at higher altitudes and in the western reaches; the thin, infertile schist fractures vertically, allowing deep root penetration",
        "elevation_range": "100-900m",
        "vineyard_area_ha": 45000,
        "annual_rainfall_mm": 500,
        "key_grapes": ["Touriga Nacional", "Touriga Franca", "Tinta Roriz", "Tinta Barroca", "Tinto Cão", "Rabigato", "Viosinho", "Gouveio"],
        "production_hl": 1500000,
        "doc_count": 3,
        "training_systems": "Traditional stone-walled terraces (socalcos) and modern earth-banked terraces (patamares) with vertical training; some vinha ao alto (vertical row planting on steep slopes)",
        "wine_styles": "Produces both Port (fortified) and Douro DOC (unfortified) wines; red Douro DOC wines have gained international acclaim alongside Port; white Douro DOC wines are increasingly important",
        "notable": "UNESCO World Heritage site since 2001; over 80 grape varieties permitted; birthplace of Port wine; terraced vineyards (socalcos and patamares) define the landscape",
    },
    {
        "name": "Minho",
        "portuguese_name": "Minho (Vinho Verde)",
        "climate": "Atlantic maritime",
        "climate_details": "The wettest wine region in Portugal with 1,200-1,500mm of annual rainfall; mild temperatures moderated by proximity to the Atlantic Ocean; high humidity encourages disease pressure, especially fungal diseases",
        "soil_types": ["granite", "sandy-granite", "alluvial"],
        "soil_details": "Predominantly granitic soils with high acidity and good drainage; alluvial deposits along river valleys; the granite bedrock produces naturally acidic, mineral-driven wines",
        "elevation_range": "50-700m",
        "vineyard_area_ha": 21000,
        "annual_rainfall_mm": 1350,
        "key_grapes": ["Alvarinho", "Loureiro", "Trajadura", "Arinto", "Avesso", "Vinhão"],
        "production_hl": 900000,
        "doc_count": 1,
        "training_systems": "Traditional pergola (latada) training raises vines high to improve airflow and reduce disease; modern estates increasingly use vertical shoot positioning (VSP) for better grape concentration",
        "wine_styles": "Famous for Vinho Verde — light, fresh, slightly effervescent wines; Alvarinho from Monção e Melgaço is the premium style; Vinhão produces deeply colored red Vinho Verde",
        "notable": "Highest rainfall in Portugal (1,200-1,500mm annually); traditional pergola (latada) vine training; 9 sub-regions including Monção e Melgaço, Lima, Cávado, Ave, Basto, Sousa, Baião, Paiva, and Amarante",
        "sub_regions": "Monção e Melgaço, Lima, Cávado, Ave, Basto, Sousa, Baião, Paiva, and Amarante",
    },
    {
        "name": "Alentejo",
        "portuguese_name": "Alentejo",
        "climate": "Mediterranean hot and dry",
        "climate_details": "Long, hot, dry summers with temperatures regularly exceeding 40°C; low annual rainfall (450-600mm) with most falling in winter; one of Europe's hottest wine regions; irrigation is commonly practiced",
        "soil_types": ["clay", "schist", "granite", "limestone"],
        "soil_details": "Varied geology across the vast region: granite in the north around Portalegre, schist and clay in central sub-regions, limestone and calcareous soils in the south; cork oak forests are ubiquitous",
        "elevation_range": "100-1,000m",
        "vineyard_area_ha": 22000,
        "annual_rainfall_mm": 525,
        "key_grapes": ["Aragonez", "Trincadeira", "Alicante Bouschet", "Castelão", "Antão Vaz", "Arinto", "Roupeiro"],
        "production_hl": 1100000,
        "doc_count": 1,
        "training_systems": "Low-trained bush vines and VSP; irrigation is essential due to extreme summer heat; night harvesting common to preserve freshness",
        "wine_styles": "Full-bodied reds dominate; rich, fruity whites from Antão Vaz and Arinto; increasingly producing premium single-varietal wines alongside traditional blends",
        "notable": "8 sub-regions: Portalegre, Borba, Redondo, Reguengos, Vidigueira, Granja-Amareleja, Évora, and Moura; largest wine-producing region by volume; summer temperatures regularly exceed 40°C",
        "sub_regions": "Portalegre, Borba, Redondo, Reguengos, Vidigueira, Granja-Amareleja, Évora, and Moura",
    },
    {
        "name": "Dão",
        "portuguese_name": "Dão",
        "climate": "continental with Atlantic influence",
        "climate_details": "Sheltered by three mountain ranges (Estrela, Caramulo, and Buçaco) that create a rain shadow; cold winters and warm summers with significant diurnal temperature variation; moderate rainfall of 700-1,000mm",
        "soil_types": ["granite", "sandy-granite", "schist"],
        "soil_details": "Predominantly granitic soils that produce elegant, aromatic wines; the Estrela, Caramulo, and Buçaco mountain ranges shelter vineyards from Atlantic weather, creating a rain shadow effect",
        "elevation_range": "200-800m",
        "vineyard_area_ha": 15000,
        "annual_rainfall_mm": 850,
        "key_grapes": ["Touriga Nacional", "Alfrocheiro", "Jaen", "Encruzado", "Bical", "Cerceal"],
        "production_hl": 400000,
        "doc_count": 1,
        "training_systems": "Mix of traditional low-trained bush vines and modern VSP; traditional granite lagares (stone treading troughs) still used by some producers for foot-treading",
        "wine_styles": "Elegant, perfumed reds centered on Touriga Nacional; age-worthy white wines from Encruzado that respond well to oak aging; the region's granite soils produce wines with natural freshness",
        "notable": "Considered the heartland of Touriga Nacional; mountain-sheltered terroir surrounded by pine forests; traditional granite lagares still used by some producers",
    },
    {
        "name": "Bairrada",
        "portuguese_name": "Bairrada",
        "climate": "Atlantic maritime",
        "climate_details": "Strongly influenced by Atlantic proximity; cool, wet winters and moderate summers; regular maritime breezes maintain natural acidity in grapes; annual rainfall around 800-1,000mm",
        "soil_types": ["clay", "limestone", "sand"],
        "soil_details": "Heavy clay soils (barro, from which the region takes its name) dominate the western area; sandy soils near the coast; limestone outcrops in the eastern hills",
        "elevation_range": "30-150m",
        "vineyard_area_ha": 6000,
        "annual_rainfall_mm": 900,
        "key_grapes": ["Baga", "Touriga Nacional", "Maria Gomes", "Bical", "Arinto"],
        "production_hl": 250000,
        "doc_count": 1,
        "training_systems": "Primarily VSP; traditional low bush vines for old Baga plantings",
        "wine_styles": "Tannic, age-worthy reds from Baga; traditional method sparkling wines (espumante) rivaling Champagne in quality; also produces rosé and white wines",
        "notable": "Baga grape thrives on the heavy clay soils; strong sparkling wine tradition (espumante) using the traditional method; proximity to the Atlantic provides natural acidity",
    },
    {
        "name": "Lisboa",
        "portuguese_name": "Lisboa",
        "climate": "diverse maritime",
        "climate_details": "Maritime influence dominates with cooling Atlantic breezes; diverse microclimates across the large region; annual rainfall varies from 500mm in the south to 900mm in the north",
        "soil_types": ["clay-limestone", "sand", "basalt", "alluvial"],
        "soil_details": "Extremely diverse geology: limestone ridges near the coast, basalt around Torres Vedras, sandy soils in the southern areas, and alluvial deposits in river valleys",
        "elevation_range": "10-500m",
        "vineyard_area_ha": 18000,
        "annual_rainfall_mm": 700,
        "key_grapes": ["Castelão", "Touriga Nacional", "Arinto", "Fernão Pires", "Vital"],
        "production_hl": 700000,
        "doc_count": 9,
        "training_systems": "VSP dominates modern plantings; traditional low bush vines in Colares on ungrafted rootstocks in sand",
        "wine_styles": "Diverse styles reflecting the many sub-regions; Bucelas produces benchmark Arinto whites; Colares makes rare ungrafted wines from sandy soils; Carcavelos produces a rare fortified wine",
        "notable": "9 sub-regions including Colares (phylloxera-free sandy vineyards), Bucelas (historic Arinto whites), Carcavelos (rare fortified), Alenquer, Arruda, Torres Vedras, Lourinhã, Óbidos, and Encostas d'Aire",
        "sub_regions": "Colares, Bucelas, Carcavelos, Alenquer, Arruda, Torres Vedras, Lourinhã, Óbidos, and Encostas d'Aire",
    },
    {
        "name": "Tejo",
        "portuguese_name": "Tejo",
        "climate": "warm Mediterranean with maritime influence",
        "climate_details": "Warm summers moderated by the Tagus River and Atlantic breezes; annual rainfall around 600-750mm; the flat alluvial plain is warmer than the hillsides",
        "soil_types": ["alluvial", "sand", "clay", "limestone"],
        "soil_details": "Three distinct soil zones: flat alluvial lezíria (flood plain) along the Tagus River, sandy bairro soils on hillsides, and limestone charneca soils on the higher eastern plateau",
        "elevation_range": "10-200m",
        "vineyard_area_ha": 12000,
        "annual_rainfall_mm": 675,
        "key_grapes": ["Castelão", "Trincadeira", "Touriga Nacional", "Fernão Pires", "Arinto"],
        "production_hl": 600000,
        "doc_count": 1,
        "training_systems": "VSP and mechanized harvesting on flat alluvial plains; some traditional low-trained vines on hillsides",
        "wine_styles": "Large volume of everyday drinking wines; reds from the bairro and charneca zones; whites dominated by Fernão Pires; increasingly quality-focused producers",
        "notable": "Named after the Tagus (Tejo) River; three distinct terroir zones (lezíria, bairro, charneca) produce markedly different wine styles; historically one of Portugal's highest-volume regions",
    },
    {
        "name": "Península de Setúbal",
        "portuguese_name": "Península de Setúbal",
        "climate": "Mediterranean maritime",
        "climate_details": "Warm, dry summers tempered by Atlantic and estuarine breezes; mild winters; the Arrábida hills create a sheltered microclimate; annual rainfall around 500-700mm",
        "soil_types": ["sand", "clay-limestone", "calcareous"],
        "soil_details": "Sandy soils on the coastal plain, calcareous clay on the Arrábida hills; the Moscatel vineyards sit on limestone and clay at low elevations near the coast",
        "elevation_range": "10-500m",
        "vineyard_area_ha": 9000,
        "annual_rainfall_mm": 600,
        "key_grapes": ["Castelão", "Moscatel de Setúbal", "Moscatel Roxo", "Fernão Pires"],
        "production_hl": 350000,
        "doc_count": 2,
        "training_systems": "VSP for modern red plantings; traditional low training for Moscatel vineyards",
        "wine_styles": "Moscatel de Setúbal (fortified Muscat) is the flagship; Palmela DOC reds from Castelão; also produces Moscatel Roxo (rare pink Muscat fortified wine)",
        "notable": "Famous for Moscatel de Setúbal, a fortified wine made from Muscat of Alexandria (Moscatel de Setúbal grape); Palmela DOC produces important Castelão-based reds",
    },
    {
        "name": "Madeira",
        "portuguese_name": "Madeira",
        "climate": "subtropical maritime",
        "climate_details": "Subtropical oceanic climate with warm temperatures year-round; high humidity; the north side is cooler and wetter than the south; altitude plays a major role in grape selection and wine style",
        "soil_types": ["volcanic basalt", "tufa", "clay"],
        "soil_details": "Volcanic basalt soils rich in minerals, with extremely steep terraced vineyards (poios) carved into the mountainsides; irrigation via historic levada channels",
        "elevation_range": "0-800m",
        "vineyard_area_ha": 500,
        "annual_rainfall_mm": 650,
        "key_grapes": ["Tinta Negra", "Sercial", "Verdelho", "Bual", "Malvasia"],
        "production_hl": 40000,
        "doc_count": 1,
        "training_systems": "Low pergola (latada) training on steep terraces (poios); most work done entirely by hand due to extreme gradients; no mechanization possible",
        "wine_styles": "Fortified wines ranging from bone-dry to lusciously sweet; classified by grape variety (noble grapes) or sweetness level; both estufagem and canteiro aging methods",
        "notable": "Volcanic island 600km off the coast of Morocco; vineyards on terraces (poios) among the steepest in the world; wines are virtually indestructible and can age for centuries; bottles from the 1700s remain drinkable",
    },
    {
        "name": "Açores",
        "portuguese_name": "Açores (Azores)",
        "climate": "Atlantic oceanic",
        "climate_details": "Cool, humid Atlantic climate with strong winds and salt spray; temperatures are moderated by the Gulf Stream; frequent cloud cover; high humidity year-round",
        "soil_types": ["volcanic basalt", "pumice", "volcanic ash"],
        "soil_details": "Young volcanic soils from basalt lava flows; vines are grown in UNESCO-protected currais (small stone-walled enclosures) on Pico island, shielded from Atlantic winds and salt spray",
        "elevation_range": "0-500m",
        "vineyard_area_ha": 2000,
        "annual_rainfall_mm": 1000,
        "key_grapes": ["Verdelho", "Arinto dos Açores", "Terrantez", "Isabella"],
        "production_hl": 15000,
        "doc_count": 3,
        "training_systems": "Unique UNESCO-protected currais (curral) system: vines planted inside small stone-walled enclosures built from volcanic basalt, protecting from Atlantic winds and reflecting heat",
        "wine_styles": "Crisp, mineral white wines dominate; historically famous for rich Verdelho; modern production focuses on fresh, terroir-driven whites with volcanic minerality",
        "notable": "Three DOCs: Pico, Biscoitos (Terceira), and Graciosa; UNESCO World Heritage currais (stone-walled vineyards) on Pico island; historically famous for Verdelho exported to Russia and America",
    },
    {
        "name": "Trás-os-Montes",
        "portuguese_name": "Trás-os-Montes",
        "climate": "extreme continental",
        "climate_details": "One of Portugal's most extreme climates: bitterly cold winters with snow and scorching summers exceeding 40°C; isolated from maritime influence by surrounding mountain ranges; annual rainfall 500-700mm",
        "soil_types": ["granite", "schist", "clay"],
        "soil_details": "Predominantly granitic soils with schist outcrops; remote and mountainous terrain with poor, thin soils that stress vines and concentrate flavors",
        "elevation_range": "300-900m",
        "vineyard_area_ha": 12000,
        "annual_rainfall_mm": 600,
        "key_grapes": ["Bastardo", "Trincadeira", "Touriga Nacional", "Gouveio", "Rabigato"],
        "production_hl": 200000,
        "doc_count": 3,
        "training_systems": "Low bush vines and VSP; traditional practices persist due to the region's isolation",
        "wine_styles": "Robust reds with high tannins; crisp whites from high-altitude vineyards; largely undiscovered region producing increasingly interesting wines",
        "notable": "Three sub-regions: Chaves, Valpaços, and Planalto Mirandês; the name means 'behind the mountains'; one of Portugal's most remote and underexplored wine regions; extreme temperature swings",
        "sub_regions": "Chaves, Valpaços, and Planalto Mirandês",
    },
    {
        "name": "Beira Interior",
        "portuguese_name": "Beira Interior",
        "climate": "continental with extreme temperature variation",
        "climate_details": "Harsh continental climate with cold winters (snow is common) and hot summers; among Portugal's highest-altitude vineyards; significant diurnal temperature variation preserves acidity",
        "soil_types": ["granite", "schist", "sandy-granite"],
        "soil_details": "High-altitude granite plateau with thin, acidic soils; the Serra da Estrela (Portugal's highest continental mountain) creates a dramatic continental climate with severe winters",
        "elevation_range": "400-900m",
        "vineyard_area_ha": 8000,
        "annual_rainfall_mm": 650,
        "key_grapes": ["Touriga Nacional", "Rufete", "Marufo", "Síria", "Fonte Cal"],
        "production_hl": 150000,
        "doc_count": 1,
        "training_systems": "Low bush vines and VSP; adapted to harsh mountain conditions",
        "wine_styles": "Fresh, acidic wines with altitude-driven freshness; reds from Touriga Nacional and Rufete; whites with crisp acidity from Síria and Fonte Cal",
        "notable": "Three sub-regions: Castelo Rodrigo, Pinhel, and Cova da Beira; bordered by Spain to the east; high-altitude vineyards produce wines with marked acidity and freshness",
        "sub_regions": "Castelo Rodrigo, Pinhel, and Cova da Beira",
    },
    {
        "name": "Algarve",
        "portuguese_name": "Algarve",
        "climate": "Mediterranean warm",
        "climate_details": "Warmest region in mainland Portugal with over 3,000 hours of sunshine annually; very dry summers (300-400mm annual rainfall in coastal areas); mild winters with virtually no frost",
        "soil_types": ["sandstone", "limestone", "clay", "schist"],
        "soil_details": "Red sandstone (grés de Silves) in the western Algarve, limestone in the barrocal hills, and schist in the northern serra; coastal areas have sandy soils",
        "elevation_range": "10-500m",
        "vineyard_area_ha": 2000,
        "annual_rainfall_mm": 350,
        "key_grapes": ["Negra Mole", "Castelão", "Syrah", "Arinto", "Crato Branco"],
        "production_hl": 30000,
        "doc_count": 4,
        "training_systems": "Low bush vines and VSP; irrigation essential in the dry climate",
        "wine_styles": "Full-bodied reds and rosés; a growing number of quality-focused producers are reviving the region; also produces medronho (arbutus berry spirit)",
        "notable": "Four DOCs: Lagos, Portimão, Lagoa, and Tavira; southernmost wine region in mainland Portugal; historically known for bulk wine, now undergoing quality renaissance",
        "sub_regions": "Lagos, Portimão, Lagoa, and Tavira",
    },
    {
        "name": "Távora-Varosa",
        "portuguese_name": "Távora-Varosa",
        "climate": "continental",
        "climate_details": "Cool continental climate with significant altitude; cold winters and moderate summers; excellent diurnal temperature variation preserves the natural acidity essential for sparkling wine production",
        "soil_types": ["granite", "schist"],
        "soil_details": "Granitic soils at high altitude with good drainage and mineral content; one of Portugal's highest-altitude DOC regions, well-suited to sparkling wine production",
        "elevation_range": "500-800m",
        "vineyard_area_ha": 1000,
        "annual_rainfall_mm": 700,
        "key_grapes": ["Malvasia Fina", "Cerceal", "Gouveio", "Touriga Nacional", "Pinot Noir"],
        "production_hl": 20000,
        "doc_count": 1,
        "training_systems": "VSP adapted to mountain conditions; focus on white grape varieties for sparkling wine base",
        "wine_styles": "Primarily sparkling wines (espumante) using the traditional method; Portugal's only DOC specifically designated for sparkling wine; also produces still whites and reds",
        "notable": "Portugal's only DOC specifically designated for sparkling wine (espumante); high altitude and cool climate produce grapes with the natural acidity essential for quality sparkling wines",
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Port Wine
# ═══════════════════════════════════════════════════════════════════════════════

PORT_DATABASE = {
    "styles": [
        {
            "name": "Ruby Port",
            "category": "ruby",
            "description": "Young, fruity Port aged in large vats (balseiros) to preserve fresh fruit character; deep ruby color with vibrant red fruit flavors",
            "aging": "Minimum 2-3 years in large wood before bottling",
            "serving": "Serve slightly chilled at 14-16°C",
        },
        {
            "name": "Ruby Reserve Port",
            "category": "ruby",
            "description": "Higher quality Ruby Port from a blend of wines aged 3-5 years; fuller and more complex than basic Ruby with more concentrated fruit",
            "aging": "3-5 years in large wood vats",
            "serving": "Serve at 14-16°C",
        },
        {
            "name": "Late Bottled Vintage (LBV) Port",
            "category": "ruby",
            "description": "Port from a single vintage aged 4-6 years in wood before bottling; may be filtered (ready to drink) or unfiltered (requires decanting and develops further in bottle)",
            "aging": "4-6 years in large casks before bottling",
            "serving": "Serve at 16-18°C; unfiltered LBV may need decanting",
        },
        {
            "name": "Crusted Port",
            "category": "ruby",
            "description": "Blended unfiltered Port that throws a crust (sediment) in bottle; offers vintage-Port character at more accessible prices; must be decanted",
            "aging": "Minimum 3 years in bottle after at least 2 years in wood",
            "serving": "Must be decanted; serve at 16-18°C",
        },
        {
            "name": "Vintage Port",
            "category": "ruby",
            "description": "The pinnacle of Port wine; single vintage from exceptional years, declared by individual shippers; intense, concentrated, and built for decades of aging; traditionally aged 2 years in wood before bottling unfiltered",
            "aging": "2 years in wood then extensive bottle aging; typically needs 15-40+ years to mature",
            "serving": "Must be decanted (often hours in advance); serve at 18°C",
        },
        {
            "name": "Single Quinta Vintage Port",
            "category": "ruby",
            "description": "Vintage-quality Port from a single named estate (quinta), typically produced in good but non-declared years; ages well but usually matures faster than classic Vintage Port",
            "aging": "Similar to Vintage Port; 2 years in wood then bottle aging",
            "serving": "Decant before serving at 18°C",
        },
        {
            "name": "Tawny Port",
            "category": "tawny",
            "description": "Basic Tawny Port aged in small oak casks (pipes of 550L); oxidative aging produces amber-tawny color with nutty, dried fruit character",
            "aging": "Minimum 2-3 years in small casks",
            "serving": "Serve slightly chilled at 12-14°C",
        },
        {
            "name": "Tawny Reserve Port",
            "category": "tawny",
            "description": "Higher quality Tawny from a blend averaging 6-9 years of cask aging; more complex with developed nutty, caramel, and dried fruit notes",
            "aging": "Average 6-9 years in small casks (pipes)",
            "serving": "Serve at 12-14°C",
        },
        {
            "name": "10-Year-Old Tawny Port",
            "category": "tawny",
            "description": "Blended Tawny with an average age of 10 years; approved by tasting panel; amber color with almond, butterscotch, and dried apricot notes",
            "aging": "Average 10 years in small casks; the age is an average, not a minimum",
            "serving": "Serve chilled at 10-14°C",
        },
        {
            "name": "20-Year-Old Tawny Port",
            "category": "tawny",
            "description": "Complex aged Tawny averaging 20 years in cask; rich amber color with intense nutty complexity, orange peel, coffee, and honeyed notes",
            "aging": "Average 20 years in small oak pipes",
            "serving": "Serve chilled at 10-14°C",
        },
        {
            "name": "30-Year-Old Tawny Port",
            "category": "tawny",
            "description": "Rare aged Tawny averaging 30 years; deep amber to olive-green rim; extraordinary complexity with layers of spice, smoke, chocolate, and dried fruits",
            "aging": "Average 30 years in cask with extensive evaporation (angel's share)",
            "serving": "Serve slightly chilled at 12°C",
        },
        {
            "name": "40-Year-Old Tawny Port",
            "category": "tawny",
            "description": "The oldest age-indicated Tawny; exceptionally rare and concentrated after four decades of oxidative aging; amber-green color with haunting complexity",
            "aging": "Average 40 years in small oak pipes; significant volume lost to evaporation",
            "serving": "Serve at 12°C",
        },
        {
            "name": "Colheita Port",
            "category": "tawny",
            "description": "Single-harvest Tawny Port from a specific year, aged in cask for a minimum of 7 years; shows the character of a particular harvest through the lens of oxidative aging",
            "aging": "Minimum 7 years in cask; many aged 20-50+ years before bottling",
            "serving": "Serve slightly chilled at 12-14°C; drink soon after bottling as it does not develop further in bottle",
        },
        {
            "name": "White Port",
            "category": "white",
            "description": "Made from white grape varieties using the Port method of fortification; styles range from extra-dry (very dry) to lágrima (very sweet); increasingly popular as an aperitif mixed with tonic water",
            "aging": "Typically aged 2-3 years; some reserve and aged versions exist",
            "serving": "Serve well chilled at 6-10°C; popular mixed with tonic and a sprig of mint",
        },
        {
            "name": "Rosé Port",
            "category": "rosé",
            "description": "A modern style created by brief skin contact with red grapes; fresh, fruity, and intended for immediate consumption; first introduced by Croft in 2008",
            "aging": "Minimal aging; intended for young consumption",
            "serving": "Serve cold over ice at 4-8°C; often mixed in cocktails",
        },
    ],
    "sub_regions": [
        {
            "name": "Baixo Corgo",
            "description": "Westernmost sub-region of the Douro; wettest with highest rainfall (900mm+); highest vine density and yields; produces lighter wines often used for Tawny and Ruby Port",
            "center": "Régua",
            "area_ha": 14000,
            "climate_note": "Most Atlantic influence; cooler and wetter than upriver sub-regions",
        },
        {
            "name": "Cima Corgo",
            "description": "Central sub-region centered on Pinhão; produces the finest Port wines; home to most classified A and B grade vineyards; ideal balance of heat, shelter, and schist soils",
            "center": "Pinhão",
            "area_ha": 20000,
            "climate_note": "Hotter and drier than Baixo Corgo; dramatic terraced hillsides along the Douro and its tributaries",
        },
        {
            "name": "Douro Superior",
            "description": "Easternmost sub-region extending to the Spanish border; hottest and driest (under 400mm rainfall); lowest vine density; large-scale estates with modern plantings; frontier territory being increasingly explored",
            "center": "Vila Nova de Foz Côa",
            "area_ha": 11000,
            "climate_note": "Near-arid continental climate with summer temperatures exceeding 45°C; large diurnal temperature variation",
        },
    ],
    "classification": {
        "description": "The Douro vineyard classification system rates individual parcels from A (best) to F based on multiple criteria",
        "criteria": [
            "altitude (lower is generally better for Port, scored 0-240 points)",
            "yield (lower yields score higher)",
            "vine density and training system",
            "grape variety quality (Touriga Nacional and Touriga Franca score highest)",
            "aspect and sun exposure (south-facing preferred)",
            "soil type (schist preferred over granite)",
            "vine age (older vines score higher)",
            "gradient (steeper slopes score higher)",
            "shelter and microclimate",
            "locality and historical reputation",
        ],
        "grades": {
            "A": "Highest quality; entitled to produce more Port per hectare",
            "B": "Very high quality; strong Port allocation",
            "C": "Good quality; moderate Port allocation",
            "D": "Average quality; limited Port allocation",
            "E": "Below average; minimal Port allocation",
            "F": "Lowest grade; may not be used for Port production",
        },
    },
    "beneficio": "The benefício is the annual authorization from the IVDP (Instituto dos Vinhos do Douro e do Porto) that determines how much must each grower can fortify into Port wine; typically only around 40% of Douro grape production is authorized as Port, with the remainder sold as unfortified Douro DOC table wine.",
    "vintage_declaration": "Vintage Port is not declared every year; a shipper declares a vintage only in years of exceptional quality, typically 3-4 times per decade; declarations are individual to each house, so one shipper may declare when another does not; the wine must be approved by the IVDP tasting panel.",
    "top_port_grapes": [
        {"name": "Touriga Nacional", "role": "Considered the finest Port grape; provides structure, intense color, and complex aromatic character with violet, dark berry, and floral notes"},
        {"name": "Touriga Franca", "role": "Most widely planted in the Douro; backbone of many Port blends; contributes body, dark fruit, and floral perfume"},
        {"name": "Tinta Roriz", "role": "Known as Tempranillo in Spain and Aragonez in southern Portugal; provides structure, red fruit, and spice; very versatile"},
        {"name": "Tinta Barroca", "role": "Heat-tolerant variety planted at lower altitudes; contributes soft, rich fruit and sweetness; often used in Tawny blends"},
        {"name": "Tinto Cão", "role": "Rare, low-yielding variety highly valued for elegance and aromatic complexity; adds finesse and aging potential to blends"},
    ],
    "field_blends": "Traditional Douro vineyards contain field blends (vinhas velhas) of dozens of interplanted varieties, often 40-80+ years old; these old mixed plantings are increasingly valued for their complexity and are among the Douro's most prized assets.",
    "lodges": "Historically, Port wine was aged and blended in lodges (armazéns) in Vila Nova de Gaia, across the river from Porto; wines were shipped downriver on flat-bottomed rabelo boats; today many producers also age wine at their Douro quintas.",
}


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Madeira Wine
# ═══════════════════════════════════════════════════════════════════════════════

MADEIRA_DATABASE = {
    "noble_grapes": [
        {
            "name": "Sercial",
            "style": "dry",
            "description": "Produces the driest style of Madeira; high acidity with citrus, almond, and saline notes; grown at higher altitudes (400-800m) on the cooler north side of the island; often needs 10+ years to show its best",
            "residual_sugar": "Under 18 g/L for dry designation",
        },
        {
            "name": "Verdelho",
            "style": "medium-dry",
            "description": "Medium-dry style with smoky, honeyed character and penetrating acidity; grown at medium altitudes (100-400m); historically the most important Madeira grape for export markets",
            "residual_sugar": "18-65 g/L for medium-dry designation",
        },
        {
            "name": "Bual",
            "style": "medium-sweet",
            "description": "Also known as Boal; medium-sweet style with rich dried fruit, caramel, and chocolate flavors balanced by marked acidity; grown on the warmer south side at lower altitudes",
            "residual_sugar": "65-96 g/L for medium-sweet designation",
        },
        {
            "name": "Malvasia",
            "style": "sweet",
            "description": "Also known as Malmsey; the sweetest and richest Madeira style; intensely sweet with coffee, toffee, dark chocolate, and tropical fruit notes offset by searing acidity; grown at the lowest, warmest coastal vineyards",
            "residual_sugar": "Over 96 g/L for sweet designation",
        },
    ],
    "other_grapes": [
        {
            "name": "Tinta Negra",
            "description": "The most widely planted grape on Madeira, accounting for approximately 85% of production; a versatile red variety that can be vinified in all sweetness styles; used for most 3-year and 5-year Madeira; cannot appear on the label unless the wine meets age-indicated requirements",
        },
        {
            "name": "Terrantez",
            "description": "Extremely rare Madeira grape producing medium-dry to medium-sweet wines of extraordinary complexity; nearly extinct due to susceptibility to disease; old vintages are among the most prized of all Madeiras",
        },
    ],
    "aging_methods": [
        {
            "name": "Estufagem",
            "description": "Bulk heating method where wine is held in concrete or stainless steel tanks (estufas) heated to 45-50°C for a minimum of 3 months; simulates the heating that occurred naturally in ships' holds during long sea voyages; used for most entry-level Madeira",
        },
        {
            "name": "Canteiro",
            "description": "Premium natural aging method where wine is placed in casks stored in the warmest rooms (attics/lofts) of the lodge, gradually moved to cooler floors over years; temperature varies naturally with the seasons from 25-40°C; used for all vintage-dated and noble-grape Madeiras",
        },
    ],
    "age_categories": [
        {"name": "Finest (3-Year)", "min_age": 3, "description": "Entry-level Madeira; typically made from Tinta Negra via estufagem; available in all sweetness levels (dry, medium-dry, medium-sweet, sweet)"},
        {"name": "Reserve (5-Year)", "min_age": 5, "description": "Aged a minimum of 5 years; may be labeled with a noble grape variety if at least 85% of that grape is used; first level where canteiro aging becomes common"},
        {"name": "Special Reserve (10-Year)", "min_age": 10, "description": "Minimum 10 years of aging; typically single noble-grape variety wines with significant complexity; all canteiro-aged"},
        {"name": "Extra Reserve (15-Year)", "min_age": 15, "description": "Minimum 15 years of cask aging; deep concentration and extraordinary complexity; exclusively canteiro-aged from noble grape varieties"},
        {"name": "20-Year", "min_age": 20, "description": "Average age of at least 20 years in cask; rare and concentrated with decades of flavor development"},
        {"name": "Vintage/Colheita", "min_age": 5, "description": "Single-harvest Madeira from a named vintage year; must be aged at least 5 years in cask; approved by the IVBAM tasting panel before release"},
        {"name": "Frasqueira/Garrafeira", "min_age": 20, "description": "The pinnacle of Madeira; single harvest from a noble grape variety aged a minimum of 20 years in cask; followed by additional bottle aging; must pass IVBAM tasting panel approval; can age virtually indefinitely"},
    ],
    "history": [
        "Madeira wine was discovered by accident when wines shipped through tropical climates were found to improve from the heat exposure during long sea voyages.",
        "The island of Madeira was a vital provisioning stop for ships crossing the Atlantic from the 15th century onward, creating huge demand for the island's wine.",
        "Madeira was the wine of choice for the American Founding Fathers; the Declaration of Independence was toasted with Madeira wine.",
        "The heating process that defines Madeira winemaking (estufagem) was developed to replicate the natural heating that occurred in ships' holds during tropical voyages (vinho da roda).",
        "Madeira has a winemaking tradition spanning over 600 years, dating back to the Portuguese colonization of the island in 1419.",
        "Madeira wine is considered virtually indestructible once made; opened bottles can last months, and sealed bottles from the 1700s have been found still drinkable with remarkable freshness.",
        "The IVBAM (Instituto do Vinho, do Bordado e do Artesanato da Madeira) regulates Madeira wine production and certifies all age-indicated and vintage wines.",
    ],
    "unique_characteristics": [
        "Madeira is the only wine in the world that is deliberately heated as part of its production process, either through estufagem or canteiro aging.",
        "The combination of fortification, heating, and high acidity gives Madeira wine unparalleled longevity; it is arguably the most age-worthy wine in the world.",
        "Once opened, a bottle of Madeira can remain in excellent condition for months or even years due to its already oxidized state.",
        "The terraced vineyards (poios) of Madeira are among the steepest and most labor-intensive in the world, with most work done entirely by hand.",
        "Madeira's vineyards are irrigated via an ancient network of levadas (water channels) that distribute water from the mountainous interior to the agricultural terraces.",
    ],
}


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Grape Varieties
# ═══════════════════════════════════════════════════════════════════════════════

GRAPE_VARIETY_DATABASE = [
    {
        "name": "Touriga Nacional",
        "color": "red",
        "area_ha": 12000,
        "origin": "Dão",
        "regions": ["Douro", "Dão", "Alentejo", "Tejo", "Lisboa", "Bairrada"],
        "description": "Considered Portugal's finest indigenous red grape; small, thick-skinned berries produce deeply colored, tannic wines with intense aromas of dark fruit, violet, and dried herbs",
        "characteristics": "Very low yields, small berries with thick skins, intense color extraction, high tannin and polyphenol content",
        "synonyms": [],
    },
    {
        "name": "Touriga Franca",
        "color": "red",
        "area_ha": 11000,
        "origin": "Douro",
        "regions": ["Douro"],
        "description": "The most widely planted grape in the Douro Valley; provides the aromatic backbone of many Port and Douro DOC blends with floral, dark berry, and spice notes",
        "characteristics": "Reliable yields, good drought resistance, aromatic intensity with floral perfume, less tannic than Touriga Nacional",
        "synonyms": ["Touriga Francesa"],
    },
    {
        "name": "Tinta Roriz",
        "color": "red",
        "area_ha": 10000,
        "origin": "Spain (Tempranillo)",
        "regions": ["Douro", "Dão", "Alentejo", "Tejo"],
        "description": "Known as Aragonez in southern Portugal and Tempranillo in Spain; one of the most versatile and widely planted red varieties in Portugal, used in Port blends and varietal table wines",
        "characteristics": "Medium to full body, red cherry and plum flavors, moderate tannins, good aging potential",
        "synonyms": ["Aragonez", "Tempranillo"],
    },
    {
        "name": "Tinta Barroca",
        "color": "red",
        "area_ha": 7000,
        "origin": "Douro",
        "regions": ["Douro"],
        "description": "Heat-tolerant Douro variety typically planted at lower altitudes; contributes soft, rich fruit and sweetness to Port blends; widely used in Tawny Port production",
        "characteristics": "Early ripening, thin-skinned, prone to rot in wet years, produces soft wines with low acidity",
        "synonyms": [],
    },
    {
        "name": "Tinto Cão",
        "color": "red",
        "area_ha": 800,
        "origin": "Douro",
        "regions": ["Douro"],
        "description": "Rare, traditional Douro variety that nearly went extinct but was saved by preservation efforts; highly valued for its elegant, perfumed character and ability to add finesse to Port blends",
        "characteristics": "Very low yields, late ripening, produces elegant wines with high natural acidity and floral aromatics",
        "synonyms": [],
    },
    {
        "name": "Baga",
        "color": "red",
        "area_ha": 4000,
        "origin": "Bairrada",
        "regions": ["Bairrada", "Dão"],
        "description": "The signature grape of Bairrada; produces deeply colored, tannic wines on clay soils that require extended aging; often compared to Nebbiolo for its tannin structure and aging potential",
        "characteristics": "Thick-skinned, extremely tannic and acidic in youth, late ripening, needs warm vintages to fully ripen; thrives on heavy clay soils",
        "synonyms": [],
    },
    {
        "name": "Trincadeira",
        "color": "red",
        "area_ha": 8000,
        "origin": "Alentejo",
        "regions": ["Alentejo", "Tejo", "Douro"],
        "description": "Widely planted across southern Portugal; produces aromatic, spicy red wines with herbal and pepper notes; drought-resistant and well-suited to hot climates",
        "characteristics": "Drought-resistant, irregular yields, prone to rot in wet years, aromatic with spice and herb notes",
        "synonyms": ["Tinta Amarela (in the Douro)"],
    },
    {
        "name": "Castelão",
        "color": "red",
        "area_ha": 6000,
        "origin": "Setúbal/Tejo",
        "regions": ["Península de Setúbal", "Tejo", "Alentejo", "Algarve"],
        "description": "Versatile red grape historically dominant in central and southern Portugal; produces medium-bodied wines with red fruit and earthy character; performs best on sandy and limestone soils",
        "characteristics": "Medium body, moderate tannins, red fruit character, performs best in warm climates on well-drained soils",
        "synonyms": ["Periquita", "João de Santarém"],
    },
    {
        "name": "Alicante Bouschet",
        "color": "red",
        "area_ha": 5000,
        "origin": "France (19th century cross)",
        "regions": ["Alentejo"],
        "description": "A teinturier grape (red flesh as well as red skin) that thrives in the Alentejo heat; produces deeply colored, full-bodied wines; originally a French cross (Petit Bouschet x Grenache) but has become an iconic Alentejo variety",
        "characteristics": "Teinturier (red flesh), extremely deep color, heat-tolerant, full-bodied with firm tannins; one of only a handful of red-fleshed grapes widely planted",
        "synonyms": [],
    },
    {
        "name": "Alvarinho",
        "color": "white",
        "area_ha": 3000,
        "origin": "Minho (Monção e Melgaço)",
        "regions": ["Minho"],
        "description": "Portugal's most prestigious white grape; produces aromatic, complex wines with stone fruit, citrus, and floral notes; at its best in the Monção e Melgaço sub-region of Vinho Verde on granite soils",
        "characteristics": "Thick-skinned, aromatic, high natural alcohol potential for a Vinho Verde variety, good acidity, ages well",
        "synonyms": ["Albariño (in Spain)"],
    },
    {
        "name": "Loureiro",
        "color": "white",
        "area_ha": 2500,
        "origin": "Minho",
        "regions": ["Minho"],
        "description": "Aromatic Vinho Verde variety producing floral, citrus-scented wines with a characteristic laurel (loureiro) note; the second most important white grape in the Minho region after Alvarinho",
        "characteristics": "Highly aromatic with floral and citrus notes, good natural acidity, best consumed young",
        "synonyms": [],
    },
    {
        "name": "Arinto",
        "color": "white",
        "area_ha": 5000,
        "origin": "Bucelas (Lisboa)",
        "regions": ["Lisboa", "Vinho Verde", "Alentejo", "Tejo", "Dão"],
        "description": "One of Portugal's most versatile and widely planted white grapes; known for its razor-sharp acidity that it retains even in the hottest climates; the backbone of Bucelas DOC wines",
        "characteristics": "High natural acidity, citrus and green apple flavors, mineral character, retains acidity even in warm regions; excellent blending partner",
        "synonyms": ["Pedernã (in Vinho Verde)"],
    },
    {
        "name": "Encruzado",
        "color": "white",
        "area_ha": 1000,
        "origin": "Dão",
        "regions": ["Dão"],
        "description": "Dão's finest white grape variety; produces complex, age-worthy wines with notes of citrus, white flowers, hazelnut, and subtle minerality; increasingly recognized as one of Portugal's most noble white grapes",
        "characteristics": "Complex and age-worthy, responds well to oak aging, medium to full body, naturally balanced acidity",
        "synonyms": [],
    },
    {
        "name": "Fernão Pires",
        "color": "white",
        "area_ha": 7000,
        "origin": "Tejo/Lisboa",
        "regions": ["Tejo", "Lisboa", "Bairrada", "Ribatejo"],
        "description": "The most widely planted white grape variety in Portugal; aromatic and fruity with low acidity; produces easy-drinking wines best consumed young",
        "characteristics": "Early ripening, aromatic, low acidity, high yields, prone to oxidation; best consumed within 1-2 years",
        "synonyms": ["Maria Gomes (in Bairrada)"],
    },
    {
        "name": "Antão Vaz",
        "color": "white",
        "area_ha": 1500,
        "origin": "Alentejo",
        "regions": ["Alentejo"],
        "description": "The leading white grape of the Alentejo; produces rich, full-bodied wines with tropical fruit and honeyed notes; handles heat well and responds positively to oak aging",
        "characteristics": "Heat-tolerant, rich and full-bodied, tropical fruit character, good response to oak, low acidity",
        "synonyms": [],
    },
    {
        "name": "Bical",
        "color": "white",
        "area_ha": 1000,
        "origin": "Bairrada/Dão",
        "regions": ["Bairrada", "Dão"],
        "description": "Important white variety in Bairrada used for both still and sparkling wines; contributes body and floral character; a key grape in Bairrada's traditional method espumante",
        "characteristics": "Moderate acidity, floral and fruity, good base for sparkling wines, susceptible to botrytis",
        "synonyms": ["Borrado das Moscas"],
    },
    {
        "name": "Sercial",
        "color": "white",
        "area_ha": 50,
        "origin": "Madeira",
        "regions": ["Madeira"],
        "description": "The driest of Madeira's four noble grape varieties; produces wines of extreme acidity and longevity; grown at the highest vineyards on the island (400-800m)",
        "characteristics": "Very high acidity, late ripening, difficult to grow, small berries, citrus and almond notes",
        "synonyms": ["Esgana Cão (on the mainland)"],
    },
    {
        "name": "Verdelho",
        "color": "white",
        "area_ha": 500,
        "origin": "Madeira/Açores",
        "regions": ["Madeira", "Açores", "Dão", "Alentejo"],
        "description": "Classic Madeira variety producing medium-dry fortified wines; also grown in the Açores and increasingly on the mainland; smoky, honeyed character with penetrating acidity in Madeira",
        "characteristics": "Versatile, good acidity, smoky and honeyed character in Madeira, crisp and mineral on the mainland",
        "synonyms": [],
    },
    {
        "name": "Bual",
        "color": "white",
        "area_ha": 30,
        "origin": "Madeira",
        "regions": ["Madeira"],
        "description": "Also known as Boal; one of Madeira's four noble grapes, producing medium-sweet wines of great richness and complexity; grown on the warmer south side of the island at lower altitudes",
        "characteristics": "Rich, medium-sweet character, dried fruit and caramel notes, excellent acidity, ages exceptionally well",
        "synonyms": ["Boal"],
    },
    {
        "name": "Malvasia",
        "color": "white",
        "area_ha": 20,
        "origin": "Madeira (Malvasia Cândida)",
        "regions": ["Madeira"],
        "description": "Known as Malmsey in English; produces the sweetest and richest Madeira style; intensely sweet with coffee, toffee, and dark chocolate flavors balanced by vibrant acidity; grown at the lowest, warmest coastal vineyards",
        "characteristics": "Very sweet, intensely flavored, extraordinary longevity, grown at sea level in warmest sites",
        "synonyms": ["Malmsey", "Malvasia Cândida"],
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Classification System
# ═══════════════════════════════════════════════════════════════════════════════

CLASSIFICATION_DATABASE = {
    "levels": [
        {
            "name": "DOC",
            "full_name": "Denominação de Origem Controlada",
            "description": "The highest classification level in the Portuguese wine system; equivalent to France's AOC or Italy's DOC; defines geographic boundaries, permitted grape varieties, yields, winemaking methods, and aging requirements",
            "count": 33,
            "examples": ["Douro", "Dão", "Bairrada", "Alentejo", "Vinho Verde", "Madeira", "Porto"],
        },
        {
            "name": "IPR",
            "full_name": "Indicação de Proveniência Regulamentada",
            "description": "An intermediate classification that has been gradually phased into DOC status since Portugal joined the EU; originally functioned as a stepping stone toward full DOC recognition",
            "count": 0,
            "examples": [],
        },
        {
            "name": "Vinho Regional (IGP)",
            "full_name": "Indicação Geográfica Protegida",
            "description": "Regional wine designation equivalent to France's IGP or Italy's IGT; allows greater flexibility in grape varieties and winemaking techniques than DOC; many top producers use VR/IGP classification to blend across DOC boundaries or use non-traditional varieties",
            "count": 14,
            "examples": ["Alentejano", "Lisboa", "Tejo", "Minho", "Duriense", "Terras do Dão", "Beiras"],
        },
        {
            "name": "Vinho de Mesa",
            "full_name": "Vinho de Mesa (Table Wine)",
            "description": "The most basic classification with no geographic indication; cannot state a vintage year or grape variety on the label; the lowest tier in the Portuguese wine hierarchy",
            "count": None,
            "examples": [],
        },
    ],
    "special_designations": [
        {
            "name": "Reserva",
            "description": "Designation for wines that have higher alcohol content than the regional minimum and have been approved by a tasting panel; indicates superior quality within its DOC or VR category",
        },
        {
            "name": "Grande Reserva",
            "description": "The highest quality designation for Portuguese table wines; must meet stricter alcohol and tasting-panel requirements than Reserva; often reserved for the finest vintages",
        },
        {
            "name": "Garrafeira",
            "description": "Traditional Portuguese designation for specially selected wines with extended aging: minimum 30 months in cask and 12 months in bottle for reds; minimum 6 months in cask and 6 months in bottle for whites; must also exceed the minimum alcohol for the region by 0.5%",
        },
    ],
    "regulatory_bodies": [
        {
            "name": "IVV",
            "full_name": "Instituto da Vinha e do Vinho",
            "role": "National body overseeing all Portuguese wine regulation, labeling, and quality control",
        },
        {
            "name": "IVDP",
            "full_name": "Instituto dos Vinhos do Douro e do Porto",
            "role": "Regulates Port wine and Douro DOC wines; manages the benefício system; approves vintage declarations; classifies vineyards",
        },
        {
            "name": "IVBAM",
            "full_name": "Instituto do Vinho, do Bordado e do Artesanato da Madeira",
            "role": "Regulates Madeira wine production, aging, and certification; approves vintage and age-indicated Madeira wines",
        },
        {
            "name": "CVRVV",
            "full_name": "Comissão de Viticultura da Região dos Vinhos Verdes",
            "role": "Regulates Vinho Verde DOC wines; oversees the 9 sub-regions and approves labels",
        },
    ],
    "doc_list": [
        "Douro", "Porto", "Vinho Verde", "Dão", "Bairrada", "Alentejo",
        "Lisboa (Alenquer, Arruda, Torres Vedras, Óbidos, Lourinhã, Encostas d'Aire, Bucelas, Colares, Carcavelos)",
        "Tejo", "Setúbal", "Palmela", "Madeira", "Biscoitos", "Graciosa", "Pico",
        "Trás-os-Montes (Chaves, Valpaços, Planalto Mirandês)",
        "Beira Interior (Castelo Rodrigo, Pinhel, Cova da Beira)",
        "Távora-Varosa",
        "Algarve (Lagos, Portimão, Lagoa, Tavira)",
        "Moscatel de Setúbal",
    ],
}


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Additional Portuguese Wine Facts
# ═══════════════════════════════════════════════════════════════════════════════

ADDITIONAL_PORT_FACTS = [
    "Port wine is produced exclusively in the Douro Valley of northern Portugal and must be aged and shipped through Vila Nova de Gaia or the Douro region.",
    "The fortification of Port wine involves adding aguardente (grape spirit at 77% ABV) to partially fermented must, halting fermentation and preserving natural grape sugars.",
    "Port wine typically has an alcohol content of 19-22% ABV, with the aguardente added at a ratio of approximately 115 liters of spirit per 435 liters of must.",
    "The IVDP (Instituto dos Vinhos do Douro e do Porto) was established in 1756 by the Marquis of Pombal, making the Douro one of the world's first demarcated wine regions.",
    "The traditional method of making Port involves foot-treading in granite lagares (stone tanks), which is still practiced by many top Port houses for their finest wines.",
    "Port wine fermentation is typically very short (2-3 days) before fortification, compared to 1-2 weeks for most dry wines.",
    "White Port is made from white grape varieties including Malvasia Fina, Viosinho, Gouveio, Rabigato, and Códega do Larinho.",
    "The Douro Valley has been producing wine for over 2,000 years, with evidence of viticulture dating back to Roman times.",
    "A pipe of Port (traditionally used for Tawny aging in Vila Nova de Gaia lodges) holds approximately 550 liters.",
    "The term 'Vintage Port' refers to Port from a single exceptional year; typically only 3-4 years per decade are declared by any given shipper.",
    "LBV (Late Bottled Vintage) Port was originally developed as an alternative to Vintage Port; it is bottled 4-6 years after harvest rather than the traditional 2 years for Vintage.",
    "Crusted Port takes its name from the crust (sediment) that forms in the bottle as the unfiltered wine throws a deposit during extended bottle aging.",
    "Single Quinta Vintage Ports are typically produced in very good but non-declared years, offering Vintage-quality wine from a single named estate at more accessible prices.",
    "The traditional Douro rabelo boats, with their flat bottoms and single square sail, were used to transport Port wine barrels down the Douro River to the Gaia lodges.",
    "Aged Tawny Ports (10, 20, 30, 40-Year-Old) indicate an average age, not a minimum; they are blends of wines from multiple years selected to achieve the target style profile.",
    "Colheita Port is a single-harvest Tawny that must spend a minimum of 7 years in wood; unlike Vintage Port, it is ready to drink upon release and does not improve in bottle.",
    "Port wine shippers traditionally had their lodges in Vila Nova de Gaia because the cooler, more humid conditions near the Atlantic coast were ideal for slow, graceful aging.",
    "Rosé Port was first introduced by Croft in 2008 and represented the first new Port style in decades; it is made by brief skin contact with red grapes.",
]

ADDITIONAL_MADEIRA_FACTS = [
    "Tinta Negra accounts for approximately 85% of all Madeira wine production and is the backbone of most 3-year and 5-year Madeira wines.",
    "The word 'vinho da roda' (wine of the round trip) refers to historical Madeira wines that improved after being shipped across the tropics and back.",
    "Madeira wine must have a minimum alcohol of 17% ABV for noble-grape varieties and 17.5% ABV for Tinta Negra-based wines.",
    "The 'angel's share' (evaporation loss) during Madeira aging is significant, especially for canteiro wines, which may lose 3-5% of volume per year.",
    "Vintage Madeira (Colheita) requires a minimum of 5 years of cask aging, while Frasqueira/Garrafeira requires a minimum of 20 years in cask.",
    "Madeira producers include historic firms such as Blandy's (founded 1811), Henriques & Henriques (1850), Justino's (1870), and the Madeira Wine Company.",
    "The 1792 Terrantez from the collection of Barbeito is one of the oldest commercially available wines in the world.",
    "Rainwater Madeira is a lighter, medium-dry style that originated from barrels diluted by rainwater during shipping; now it refers to any lighter-styled Madeira.",
    "The cuisine of Madeira traditionally pairs Madeira wine with food: Sercial with soup, Verdelho with fish, Bual with cheese, and Malmsey with dessert.",
    "Napoleon reportedly ordered Madeira wine during his exile on St. Helena, and it was the preferred drink at many colonial-era celebrations.",
    "The estufagem process for Madeira must heat the wine to a minimum of 45°C for at least 90 days; the temperature must not exceed 55°C.",
    "After estufagem, Madeira wine must rest for a minimum of 90 days before further processing, allowing it to recover from the heating process.",
]

ADDITIONAL_VITICULTURE_FACTS = [
    "Portugal has over 250 indigenous grape varieties, one of the highest concentrations of native varieties per capita of any wine-producing country.",
    "Portugal is the world's largest producer of cork, accounting for approximately 50% of global production; cork oak forests (montados) are integral to the wine landscape, especially in the Alentejo.",
    "The traditional Portuguese vine training system known as latada (pergola) is still widely used in Vinho Verde, raising vines overhead to improve air circulation in the humid climate.",
    "Vinha ao alto is a modern Douro planting method where vines are planted vertically up the slope rather than on horizontal terraces, allowing mechanization on less steep sites.",
    "Patamares are wide, earth-banked terraces in the Douro designed to accommodate mechanization; they replaced many traditional socalcos (narrow stone-walled terraces) in the late 20th century.",
    "Traditional socalcos in the Douro Valley are narrow stone-walled terraces, often supporting only 1-2 rows of vines, requiring all work to be done by hand.",
    "Portugal's phylloxera crisis arrived in the 1860s, devastating vineyards nationwide; Colares in Lisboa was notably spared because its sandy soils prevented the pest from establishing.",
    "Colares DOC near Lisbon is one of the few European regions where ungrafted vines still grow, planted in deep sand that phylloxera cannot penetrate.",
    "The practice of foot-treading grapes in stone lagares (stone troughs) remains important in the Douro for producing premium Port and in parts of the Alentejo for top red wines.",
    "Night harvesting is practiced increasingly in the Alentejo and other hot Portuguese regions to preserve grape freshness and prevent premature oxidation.",
    "Portugal ranks as the world's 11th largest wine producer by volume and has the highest per-capita wine consumption in the world.",
    "The total vineyard area in Portugal is approximately 195,000 hectares, making it the 6th largest vineyard area in the world.",
    "Portugal's wine exports have grown significantly in the 21st century, with the UK, USA, France, Germany, and Brazil being the largest export markets.",
    "The concept of 'garrafeira' in Portuguese wine indicates specially selected wines with extended aging: minimum 30 months in cask plus 12 months in bottle for reds.",
    "Portuguese winemaking has undergone a quality revolution since EU accession in 1986, with massive investment in modern equipment, temperature-controlled fermentation, and international marketing.",
    "The Douro Valley's UNESCO World Heritage status (granted 2001) recognizes the cultural landscape created by 2,000 years of winemaking on its terraced hillsides.",
    "The Pico Island vineyard culture (Açores) was inscribed as a UNESCO World Heritage site in 2004, recognizing the unique currais (stone-walled vineyard enclosures).",
    "Traditional field blends (vinhas velhas) in the Douro may contain 30-80+ grape varieties interplanted in a single vineyard, reflecting centuries of accumulated viticultural knowledge.",
    "Many Portuguese winemakers practice 'co-fermentation' of field blend varieties, fermenting multiple varieties together rather than separately, preserving traditional blending methods.",
    "The Portuguese wine industry underwent significant consolidation and modernization in the 1990s and 2000s, with the emergence of single-estate (quinta) bottlings challenging the traditional négociant model.",
    "Portuguese rosé wines (rosado) have a long tradition, particularly in the Minho (from Vinhão), Alentejo, and Bairrada regions.",
    "Touriga Nacional was nearly extinct by the mid-20th century due to its very low yields; government programs and the work of estates like Quinta do Noval helped preserve and promote the variety.",
    "The Alicante Bouschet grape in Portugal's Alentejo has achieved a status unmatched in any other wine region, producing world-class single-varietal wines from this teinturier variety.",
    "Jaen grape (known as Mencía in Spain) is an important red variety in the Dão region, producing medium-bodied, aromatic wines.",
    "Rufete is a rare red grape variety from Beira Interior that produces light, perfumed wines and is gaining attention from quality-focused producers.",
    "Alfrocheiro is a Dão red grape variety that contributes color and spice to blends; it is increasingly bottled as a single-varietal wine.",
    "The Roupeiro grape (also called Síria) is widely planted across southern Portugal and produces neutral, fruity white wines suitable for everyday drinking.",
    "Vinhão is the most important red grape of Vinho Verde, producing deeply colored, tannic red wines; it is also known as Sousão in the Douro.",
    "Avesso is a white grape found primarily in the Baião and Amarante sub-regions of Vinho Verde, producing rounder, fuller-bodied wines than typical Vinho Verde.",
    "Azal is a white grape variety from the inland sub-regions of Vinho Verde, producing crisp, high-acid wines that are ideal for the traditional light Vinho Verde style.",
    "Trajadura is a white grape variety used in Vinho Verde blends, contributing body and soft fruit character; it is known as Treixadura in Spain's Rías Baixas.",
    "The Bastardo grape (known as Trousseau in France) is grown in Trás-os-Montes and the Douro, producing light, perfumed red wines with high acidity.",
    "Rabigato is a white Douro grape valued for its high acidity and minerality; it is increasingly used in premium Douro white wine blends.",
    "Viosinho is a white Douro grape that has risen in importance for still white wines, contributing tropical fruit and floral aromatics to blends.",
    "Gouveio (also known as Verdelho on the mainland) is an important white Douro variety used in both Port and still white wine production.",
    "Códega do Larinho is a traditional Douro white grape variety that contributes structure and body to blends; it is also known as Síria in other regions.",
]

PORTUGUESE_WINEMAKING_FACTS = [
    "Autovinification is a winemaking technique developed in Portugal that uses the pressure of CO2 from fermentation to automatically pump juice over grape skins, replacing manual or mechanical punching-down.",
    "Talhas (large clay amphorae) are used for winemaking in the Alentejo, continuing a tradition dating back to Roman times; this method was recognized by UNESCO in 2020.",
    "Vinho de talha (clay amphora wine) from the Alentejo involves fermenting and aging wine in large clay pots (talhas) sealed with a mixture of olive oil and clay.",
    "Portuguese sparkling wine (espumante) is produced primarily in Bairrada and Távora-Varosa using the traditional method (método clássico), with some producers using Baga, Bical, and Maria Gomes grapes.",
    "Aguardente vínica (grape spirit) used to fortify Port wine must be produced from Portuguese grapes and approved by the IVDP; it is typically distilled to 77% ABV.",
    "The concept of 'lote' (blend) is central to Portuguese winemaking, with most wines being blends of multiple indigenous varieties rather than single-varietal wines.",
    "Granito (granite) lagares are traditional stone treading tanks found in the Douro and Dão, where grapes are crushed by foot to extract color, tannin, and flavor during Port and still wine production.",
    "Portuguese winemakers increasingly use temperature-controlled stainless steel fermentation alongside traditional methods to preserve fruit freshness and aromatic purity.",
    "Oak aging in Portugal uses both French and American oak barrels, as well as traditional large Portuguese oak casks (tonéis) for more subtle wood influence.",
    "The practice of 'bica aberta' (open spigot) white winemaking in Portugal involves minimal skin contact and immediate pressing, producing lighter, fresher white wines.",
    "Curtimenta is the Portuguese term for maceration/skin contact during red winemaking; extended curtimenta produces wines with deeper color and more robust tannins.",
    "Pisa a pé (foot-treading) remains the preferred method for producing top Port wines and premium Alentejo reds because human feet provide gentle, even extraction without crushing seeds.",
    "Many Douro estates now use robotic lagares that mimic the gentle action of foot-treading, allowing consistent quality extraction at larger volumes.",
    "Destemming (desengace) became common in Portuguese winemaking in the 1990s; before that, whole-bunch fermentation with stems was the norm, contributing to more tannic wines.",
    "The Bairrada region pioneered Portuguese sparkling wine production in the early 20th century, and Bairrada espumante remains Portugal's most important sparkling wine appellation.",
]

NOTABLE_PRODUCERS_DATABASE = [
    {"name": "Quinta do Noval", "region": "Douro", "notable": "Historic Port house founded in 1715; producer of the legendary Nacional Vintage Port from ungrafted vines; also produces acclaimed Douro DOC wines"},
    {"name": "Taylor's", "region": "Douro", "notable": "One of the founding Port houses, established in 1692; renowned for Vintage Port and aged Tawny; owns Quinta de Vargellas and Quinta de Terra Feita"},
    {"name": "Niepoort", "region": "Douro", "notable": "Innovative Douro producer known for both Port and premium Douro DOC table wines; Dirk Niepoort is credited with helping to redefine the modern Douro"},
    {"name": "Barca Velha", "region": "Douro", "notable": "Portugal's most iconic and expensive table wine, produced by Casa Ferreirinha (Sogrape) from the Douro; first vintage was 1952; only declared in exceptional years"},
    {"name": "Herdade do Esporão", "region": "Alentejo", "notable": "One of Portugal's largest and most important estates with over 700 hectares of vineyards in the Reguengos sub-region of the Alentejo"},
    {"name": "Quinta dos Roques", "region": "Dão", "notable": "Pioneer of quality Dão wines; helped establish the modern reputation of the Dão region and its Touriga Nacional and Encruzado wines"},
    {"name": "Luís Pato", "region": "Bairrada", "notable": "Iconic Bairrada producer who championed the Baga grape and demonstrated its world-class potential on clay soils; pioneer of single-vineyard wines in the region"},
    {"name": "Anselmo Mendes", "region": "Minho", "notable": "Leading Vinho Verde producer who revolutionized the perception of Alvarinho from Monção e Melgaço, producing complex, age-worthy whites"},
    {"name": "Blandy's", "region": "Madeira", "notable": "Historic Madeira wine family established in 1811; part of the Madeira Wine Company; produces some of the island's finest age-indicated and vintage Madeiras"},
    {"name": "Henriques & Henriques", "region": "Madeira", "notable": "Madeira's largest independent producer, founded in 1850; known for its comprehensive range of age-indicated Madeiras from all noble grape varieties"},
    {"name": "Symington Family Estates", "region": "Douro", "notable": "Largest family-owned Port company, owning Graham's, Dow's, Warre's, Cockburn's, and Quinta do Vesúvio; also produces Douro DOC wines including Chryseia and Altano"},
    {"name": "Sogrape", "region": "Multiple", "notable": "Portugal's largest wine company; produces Mateus Rosé (one of the world's best-selling wine brands), Casa Ferreirinha, and Sandeman Port among many others"},
    {"name": "Fonseca", "region": "Douro", "notable": "Historic Port house founded in 1815; known for opulent, richly fruity Vintage Ports; owns the legendary Quinta do Panascal in the Cima Corgo"},
    {"name": "Ramos Pinto", "region": "Douro", "notable": "Port house founded in 1880; now owned by Champagne Louis Roederer; known for both Port and quality Douro DOC wines; pioneered research into Douro grape varieties"},
    {"name": "Churchill's", "region": "Douro", "notable": "Founded in 1981 by John Graham, the first new British Port house in over 50 years; known for dry, elegant Ports and excellent Douro DOC wines"},
    {"name": "Quinta do Crasto", "region": "Douro", "notable": "Family-owned estate overlooking the Douro; produces highly-rated Douro DOC reds including the premium Quinta do Crasto Reserva Vinhas Velhas"},
    {"name": "Wine & Soul", "region": "Douro", "notable": "Boutique Douro producer founded in 2001; known for Pintas, a complex red from old-vine field blends; represents the new wave of artisanal Douro winemaking"},
    {"name": "Mouchão", "region": "Alentejo", "notable": "Historic Alentejo estate established in 1901; famous for its Alicante Bouschet-based Mouchão Tinto; traditional winemaking in large open-top fermenters with foot-treading"},
    {"name": "Quinta do Vallado", "region": "Douro", "notable": "One of the oldest Douro estates, dating back to 1716; produces both Port and acclaimed Douro DOC wines; owned by the descendants of the legendary Dona Antónia Adelaide Ferreira"},
    {"name": "Álvaro Castro", "region": "Dão", "notable": "Leading Dão producer at Quinta da Pellada and Quinta de Saes; produces benchmark Touriga Nacional and Encruzado wines that demonstrate the region's elegance"},
    {"name": "Soalheiro", "region": "Minho", "notable": "Pioneer of Alvarinho in the Monção e Melgaço sub-region of Vinho Verde; first producer to bottle varietal Alvarinho in Portugal (1982)"},
    {"name": "Justino's", "region": "Madeira", "notable": "One of Madeira's largest and oldest producers, founded in 1870; known for consistent quality across all age categories and noble grape varieties"},
    {"name": "Cortes de Cima", "region": "Alentejo", "notable": "Danish-owned Alentejo estate that pioneered Syrah in Portugal and demonstrated that the Alentejo could produce world-class wines to international standards"},
]

PORTUGUESE_WINE_HISTORY = [
    "The Treaty of Methuen (1703) between England and Portugal gave Portuguese wines preferential tariff rates in England, dramatically boosting Port wine exports and establishing Britain as Port's primary market.",
    "The Marquis of Pombal created the world's first demarcated wine region in 1756, establishing boundaries for the Douro Valley and founding the Companhia Geral da Agricultura das Vinhas do Alto Douro to regulate Port production.",
    "Portugal was the first country to create a system of regulated wine regions (1756), predating the French AOC system by nearly 180 years.",
    "Dona Antónia Adelaide Ferreira (1811-1896), known as 'Ferreirinha,' was one of the most important figures in Douro Valley history, amassing vast vineyard holdings and championing quality winemaking.",
    "Mateus Rosé, created in 1942 by Fernando Van Zeller Guedes, became one of the world's most commercially successful wines, selling millions of bottles worldwide and introducing many consumers to Portuguese wine.",
    "The Portuguese wine revolution accelerated after EU membership in 1986, with EU structural funds financing massive modernization of wineries, vineyards, and infrastructure across all regions.",
    "The concept of 'Douro Boys' emerged in the early 2000s, referring to a group of five Douro producers (Niepoort, Quinta do Vallado, Quinta do Crasto, Quinta Vale Meão, and Poeira) who championed premium Douro table wines.",
    "The 1820 Liberal revolution in Portugal disrupted the Port wine trade as religious orders were dissolved and many important Douro vineyards changed hands.",
    "British merchant families have played a crucial role in Port wine history since the 17th century, establishing famous houses such as Taylor's, Graham's, Warre's, Croft, and Cockburn's.",
    "The Port wine trade was historically dominated by British and Dutch merchants based in Porto and Vila Nova de Gaia, leading to the Anglo-Portuguese wine trade that has persisted for over 300 years.",
    "The phylloxera epidemic reached Portugal in 1868, first appearing in the Douro Valley; by 1900 it had devastated most of the country's vineyards, requiring replanting on American rootstocks.",
    "Portugal's Estado Novo dictatorship (1933-1974) promoted wine cooperatives (adegas cooperativas) as the primary means of wine production, resulting in decades of mediocre quality that only changed after the 1974 revolution.",
    "The Carnation Revolution of 1974 and subsequent land reforms initially disrupted the Portuguese wine industry, but ultimately paved the way for private investment and quality improvements.",
    "The Douro Valley has evidence of viticulture from at least the 3rd-4th century AD, with Roman-era grape presses (lagares) discovered in archaeological excavations.",
    "Prince Henry the Navigator established Madeira's wine industry in the 15th century, ordering the planting of Malvasia vines imported from Crete shortly after the island's colonization.",
    "The Wines of Portugal marketing body was established to promote Portuguese wines internationally, building recognition for the country's unique indigenous grape varieties and diverse wine regions.",
]

VINHO_VERDE_SUBREGION_DATABASE = [
    {"name": "Monção e Melgaço", "description": "Northernmost sub-region, furthest from the coast; warmer and drier than other sub-regions; the heartland of Alvarinho, producing the region's most full-bodied and age-worthy whites", "key_grape": "Alvarinho"},
    {"name": "Lima", "description": "Along the Lima River valley; produces aromatic wines from Loureiro and blends; cooler maritime climate", "key_grape": "Loureiro"},
    {"name": "Cávado", "description": "Named after the Cávado River; moderate Atlantic influence; produces light, fresh wines from multiple varieties", "key_grape": "Arinto"},
    {"name": "Ave", "description": "Along the Ave River; one of the larger sub-regions; good balance between maritime and inland influences", "key_grape": "Loureiro"},
    {"name": "Basto", "description": "Most inland sub-region; more continental climate with warmer summers; produces fuller-bodied wines", "key_grape": "Azal"},
    {"name": "Sousa", "description": "Small sub-region between Ave and Basto; transitional climate between coastal and inland", "key_grape": "Avesso"},
    {"name": "Baião", "description": "Inland sub-region in the south; warmer climate suited to the Avesso grape; produces rounder, fuller wines", "key_grape": "Avesso"},
    {"name": "Paiva", "description": "Southern sub-region along the Paiva River; cooler inland area; less well-known but producing quality wines", "key_grape": "Arinto"},
    {"name": "Amarante", "description": "Named after the town of Amarante; inland sub-region with granite soils; produces wines from Azal and Avesso", "key_grape": "Azal"},
]

ALENTEJO_SUBREGION_DATABASE = [
    {"name": "Portalegre", "description": "Northernmost sub-region at highest elevation (up to 1,000m); granite soils; coolest microclimate in the Alentejo, producing more elegant wines", "notable": "Serra de São Mamede creates a cool microclimate unique in the Alentejo"},
    {"name": "Borba", "description": "Central Alentejo sub-region known for marble quarries and reliable red wine production from Aragonez and Trincadeira", "notable": "Major cooperative region producing consistent quality"},
    {"name": "Redondo", "description": "Hilly sub-region with clay and limestone soils; produces balanced reds and whites", "notable": "Home to several quality-focused cooperatives"},
    {"name": "Reguengos", "description": "Flat plains with schist and clay soils; hot, dry conditions ideal for full-bodied reds", "notable": "Home to Herdade do Esporão, one of Portugal's most important estates"},
    {"name": "Vidigueira", "description": "Southernmost traditional sub-region; some of the hottest conditions in Portugal; known for both reds and whites", "notable": "South-facing slopes of the Serra de Portel provide some relief from heat"},
    {"name": "Granja-Amareleja", "description": "Eastern sub-region near the Spanish border; extreme heat and low rainfall; produces robust, concentrated reds", "notable": "One of the driest sub-regions in the Alentejo"},
    {"name": "Évora", "description": "Central sub-region surrounding the historic city of Évora; mix of clay and granite soils; growing reputation for quality", "notable": "Combines historical winemaking tradition with modern innovation"},
    {"name": "Moura", "description": "Southeastern sub-region with clay and limestone soils; hot, dry Mediterranean climate producing full-bodied wines", "notable": "Traditional olive oil and wine production region"},
]


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
    """Build facts about Portuguese wine regions (climate, soil, elevation, stats)."""
    facts = []

    for region in REGION_DATABASE:
        name = region["name"]
        pt_name = region["portuguese_name"]
        entities = [{"type": "region", "name": name}]
        base_tags = ["portugal", name.lower().replace("/", "_").replace(" ", "_")]

        # Region identity
        facts.append(_make_fact(
            f"{name} ({pt_name}) is one of Portugal's designated wine regions.",
            domain="wine_regions",
            source_id=source_id,
            subdomain="portugal_regions",
            entities=entities,
            tags=base_tags,
        ))

        # Climate
        facts.append(_make_fact(
            f"The {name} wine region in Portugal has a {region['climate']} climate.",
            domain="wine_regions",
            source_id=source_id,
            subdomain="climate",
            entities=entities,
            tags=base_tags + ["climate"],
        ))

        # Climate details
        if region.get("climate_details"):
            facts.append(_make_fact(
                f"{region['climate_details']}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="climate",
                entities=entities,
                tags=base_tags + ["climate"],
            ))

        # Soil types
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

        # Soil details
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
                f"Vineyards in the {name} wine region of Portugal are planted at elevations ranging from {region['elevation_range']}.",
                domain="viticulture",
                source_id=source_id,
                subdomain="terrain",
                entities=entities,
                tags=base_tags + ["elevation"],
            ))

        # Rainfall
        if region.get("annual_rainfall_mm"):
            facts.append(_make_fact(
                f"The {name} wine region in Portugal receives approximately {region['annual_rainfall_mm']}mm of annual rainfall.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="climate",
                entities=entities,
                tags=base_tags + ["rainfall", "climate"],
            ))

        # Vineyard area
        if region.get("vineyard_area_ha"):
            facts.append(_make_fact(
                f"The {name} wine region in Portugal has approximately {region['vineyard_area_ha']:,} hectares under vine.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="statistics",
                entities=entities,
                tags=base_tags + ["area", "statistics"],
            ))

        # Production
        if region.get("production_hl"):
            facts.append(_make_fact(
                f"The {name} wine region produces approximately {region['production_hl']:,} hectoliters of wine annually.",
                domain="wine_business",
                source_id=source_id,
                subdomain="production",
                entities=entities,
                tags=base_tags + ["production", "statistics"],
            ))

        # DOC count
        if region.get("doc_count"):
            facts.append(_make_fact(
                f"The {name} wine region encompasses {region['doc_count']} DOC designation(s).",
                domain="wine_regions",
                source_id=source_id,
                subdomain="classification",
                entities=entities,
                tags=base_tags + ["doc", "classification"],
            ))

        # Key grapes
        if region.get("key_grapes"):
            grape_list = ", ".join(region["key_grapes"])
            grape_entities = entities + [{"type": "grape", "name": g} for g in region["key_grapes"]]
            facts.append(_make_fact(
                f"The key grape varieties grown in the {name} wine region include {grape_list}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="regional_grapes",
                entities=grape_entities,
                tags=base_tags + ["grapes"],
            ))

        # Training systems
        if region.get("training_systems"):
            facts.append(_make_fact(
                f"Vine training in the {name} region: {region['training_systems']}.",
                domain="viticulture",
                source_id=source_id,
                subdomain="training_systems",
                entities=entities,
                tags=base_tags + ["viticulture", "training"],
            ))

        # Wine styles
        if region.get("wine_styles"):
            facts.append(_make_fact(
                f"Wine styles of {name}: {region['wine_styles']}.",
                domain="winemaking",
                source_id=source_id,
                subdomain="regional_styles",
                entities=entities,
                tags=base_tags + ["wine_styles"],
            ))

        # Sub-regions
        if region.get("sub_regions"):
            facts.append(_make_fact(
                f"The sub-regions of {name} in Portugal include {region['sub_regions']}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="portugal_sub_regions",
                entities=entities,
                tags=base_tags + ["sub_regions"],
            ))

        # Notable features
        if region.get("notable"):
            facts.append(_make_fact(
                f"{region['notable']}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="portugal_regions",
                entities=entities,
                tags=base_tags + ["notable"],
            ))

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# FACT BUILDERS — Port Wine
# ═══════════════════════════════════════════════════════════════════════════════


def _build_port_facts(source_id: str) -> list[dict]:
    """Build facts about Port wine styles, sub-regions, classification, and production."""
    facts = []
    base_tags = ["portugal", "port", "douro", "fortified"]
    base_entities = [{"type": "region", "name": "Douro"}, {"type": "wine_type", "name": "Port"}]

    # ── Port styles ──────────────────────────────────────────────────────────
    for style in PORT_DATABASE["styles"]:
        style_entities = base_entities + [{"type": "wine_style", "name": style["name"]}]
        style_tags = base_tags + [style["category"]]

        facts.append(_make_fact(
            f"{style['name']} is a style of Port wine: {style['description']}.",
            domain="winemaking",
            source_id=source_id,
            subdomain="port_styles",
            entities=style_entities,
            tags=style_tags,
        ))

        facts.append(_make_fact(
            f"{style['name']} aging: {style['aging']}.",
            domain="winemaking",
            source_id=source_id,
            subdomain="port_aging",
            entities=style_entities,
            tags=style_tags + ["aging"],
        ))

        facts.append(_make_fact(
            f"{style['name']} serving: {style['serving']}.",
            domain="winemaking",
            source_id=source_id,
            subdomain="port_service",
            entities=style_entities,
            tags=style_tags + ["serving"],
        ))

    # ── Douro sub-regions ────────────────────────────────────────────────────
    for sub in PORT_DATABASE["sub_regions"]:
        sub_entities = base_entities + [{"type": "sub_region", "name": sub["name"]}]

        facts.append(_make_fact(
            f"{sub['name']} is a sub-region of the Douro Valley: {sub['description']}.",
            domain="wine_regions",
            source_id=source_id,
            subdomain="douro_sub_regions",
            entities=sub_entities,
            tags=base_tags + ["sub_region", sub["name"].lower().replace(" ", "_")],
        ))

        if sub.get("center"):
            facts.append(_make_fact(
                f"The {sub['name']} sub-region of the Douro is centered on the town of {sub['center']}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="douro_sub_regions",
                entities=sub_entities,
                tags=base_tags + ["sub_region"],
            ))

        if sub.get("area_ha"):
            facts.append(_make_fact(
                f"The {sub['name']} sub-region of the Douro covers approximately {sub['area_ha']:,} hectares.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="douro_sub_regions",
                entities=sub_entities,
                tags=base_tags + ["sub_region", "statistics"],
            ))

        if sub.get("climate_note"):
            facts.append(_make_fact(
                f"Climate of {sub['name']} in the Douro: {sub['climate_note']}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="douro_climate",
                entities=sub_entities,
                tags=base_tags + ["sub_region", "climate"],
            ))

    # ── Classification system ────────────────────────────────────────────────
    classif = PORT_DATABASE["classification"]
    facts.append(_make_fact(
        f"{classif['description']}.",
        domain="wine_regions",
        source_id=source_id,
        subdomain="douro_classification",
        entities=base_entities,
        tags=base_tags + ["classification"],
    ))

    for criterion in classif["criteria"]:
        facts.append(_make_fact(
            f"The Douro vineyard classification considers {criterion}.",
            domain="wine_regions",
            source_id=source_id,
            subdomain="douro_classification",
            entities=base_entities,
            tags=base_tags + ["classification"],
        ))

    for grade, desc in classif["grades"].items():
        facts.append(_make_fact(
            f"In the Douro vineyard classification, grade {grade}: {desc}.",
            domain="wine_regions",
            source_id=source_id,
            subdomain="douro_classification",
            entities=base_entities,
            tags=base_tags + ["classification", "grade"],
        ))

    # ── Benefício ────────────────────────────────────────────────────────────
    facts.append(_make_fact(
        f"{PORT_DATABASE['beneficio']}",
        domain="wine_business",
        source_id=source_id,
        subdomain="port_regulation",
        entities=base_entities,
        tags=base_tags + ["beneficio", "regulation"],
    ))

    # ── Vintage declaration ──────────────────────────────────────────────────
    facts.append(_make_fact(
        f"{PORT_DATABASE['vintage_declaration']}",
        domain="winemaking",
        source_id=source_id,
        subdomain="port_vintage",
        entities=base_entities,
        tags=base_tags + ["vintage", "declaration"],
    ))

    # ── Top Port grapes ──────────────────────────────────────────────────────
    for grape in PORT_DATABASE["top_port_grapes"]:
        grape_entities = base_entities + [{"type": "grape", "name": grape["name"]}]
        facts.append(_make_fact(
            f"{grape['name']} in Port wine: {grape['role']}.",
            domain="grape_varieties",
            source_id=source_id,
            subdomain="port_grapes",
            entities=grape_entities,
            tags=base_tags + ["grape", grape["name"].lower().replace(" ", "_")],
        ))

    # ── Field blends ─────────────────────────────────────────────────────────
    facts.append(_make_fact(
        f"{PORT_DATABASE['field_blends']}",
        domain="viticulture",
        source_id=source_id,
        subdomain="douro_viticulture",
        entities=base_entities,
        tags=base_tags + ["field_blend", "vinhas_velhas"],
    ))

    # ── Gaia lodges ──────────────────────────────────────────────────────────
    facts.append(_make_fact(
        f"{PORT_DATABASE['lodges']}",
        domain="winemaking",
        source_id=source_id,
        subdomain="port_production",
        entities=base_entities + [{"type": "place", "name": "Vila Nova de Gaia"}],
        tags=base_tags + ["gaia", "lodges", "aging"],
    ))

    # ── Additional Port facts ────────────────────────────────────────────────
    for fact_text in ADDITIONAL_PORT_FACTS:
        facts.append(_make_fact(
            fact_text,
            domain="winemaking",
            source_id=source_id,
            subdomain="port_details",
            entities=base_entities,
            tags=base_tags + ["details"],
        ))

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# FACT BUILDERS — Madeira Wine
# ═══════════════════════════════════════════════════════════════════════════════


def _build_madeira_facts(source_id: str) -> list[dict]:
    """Build facts about Madeira wine: noble grapes, aging, categories, history."""
    facts = []
    base_tags = ["portugal", "madeira", "fortified"]
    base_entities = [{"type": "region", "name": "Madeira"}, {"type": "wine_type", "name": "Madeira"}]

    # ── Noble grapes ─────────────────────────────────────────────────────────
    for grape in MADEIRA_DATABASE["noble_grapes"]:
        grape_entities = base_entities + [{"type": "grape", "name": grape["name"]}]
        grape_tags = base_tags + ["noble_grape", grape["name"].lower()]

        facts.append(_make_fact(
            f"{grape['name']} is one of the four noble grape varieties of Madeira wine, producing {grape['style']} wines.",
            domain="grape_varieties",
            source_id=source_id,
            subdomain="madeira_grapes",
            entities=grape_entities,
            tags=grape_tags,
        ))

        facts.append(_make_fact(
            f"Madeira wine from {grape['name']}: {grape['description']}.",
            domain="winemaking",
            source_id=source_id,
            subdomain="madeira_styles",
            entities=grape_entities,
            tags=grape_tags,
        ))

        facts.append(_make_fact(
            f"Madeira labeled as {grape['name']} ({grape['style']}): {grape['residual_sugar']}.",
            domain="winemaking",
            source_id=source_id,
            subdomain="madeira_sweetness",
            entities=grape_entities,
            tags=grape_tags + ["sweetness"],
        ))

    # Noble grape ordering
    facts.append(_make_fact(
        "The four noble Madeira grapes from driest to sweetest are: Sercial (dry), Verdelho (medium-dry), Bual/Boal (medium-sweet), and Malvasia/Malmsey (sweet).",
        domain="grape_varieties",
        source_id=source_id,
        subdomain="madeira_grapes",
        entities=base_entities + [
            {"type": "grape", "name": "Sercial"},
            {"type": "grape", "name": "Verdelho"},
            {"type": "grape", "name": "Bual"},
            {"type": "grape", "name": "Malvasia"},
        ],
        tags=base_tags + ["noble_grape", "sweetness"],
    ))

    # ── Other grapes ─────────────────────────────────────────────────────────
    for grape in MADEIRA_DATABASE["other_grapes"]:
        grape_entities = base_entities + [{"type": "grape", "name": grape["name"]}]
        facts.append(_make_fact(
            f"{grape['description']}.",
            domain="grape_varieties",
            source_id=source_id,
            subdomain="madeira_grapes",
            entities=grape_entities,
            tags=base_tags + [grape["name"].lower().replace(" ", "_")],
        ))

    # ── Aging methods ────────────────────────────────────────────────────────
    for method in MADEIRA_DATABASE["aging_methods"]:
        facts.append(_make_fact(
            f"{method['name']} is a Madeira wine aging method: {method['description']}.",
            domain="winemaking",
            source_id=source_id,
            subdomain="madeira_aging",
            entities=base_entities,
            tags=base_tags + ["aging", method["name"].lower()],
        ))

    # ── Age categories ───────────────────────────────────────────────────────
    for cat in MADEIRA_DATABASE["age_categories"]:
        facts.append(_make_fact(
            f"Madeira {cat['name']} category: minimum {cat['min_age']} years aging; {cat['description']}.",
            domain="winemaking",
            source_id=source_id,
            subdomain="madeira_categories",
            entities=base_entities,
            tags=base_tags + ["aging", "category"],
        ))

    # ── History ──────────────────────────────────────────────────────────────
    for h in MADEIRA_DATABASE["history"]:
        facts.append(_make_fact(
            h,
            domain="wine_business",
            source_id=source_id,
            subdomain="madeira_history",
            entities=base_entities,
            tags=base_tags + ["history"],
        ))

    # ── Unique characteristics ───────────────────────────────────────────────
    for c in MADEIRA_DATABASE["unique_characteristics"]:
        facts.append(_make_fact(
            c,
            domain="winemaking",
            source_id=source_id,
            subdomain="madeira_characteristics",
            entities=base_entities,
            tags=base_tags + ["characteristics"],
        ))

    # ── Additional Madeira facts ─────────────────────────────────────────────
    for fact_text in ADDITIONAL_MADEIRA_FACTS:
        facts.append(_make_fact(
            fact_text,
            domain="winemaking",
            source_id=source_id,
            subdomain="madeira_details",
            entities=base_entities,
            tags=base_tags + ["details"],
        ))

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# FACT BUILDERS — Grape Varieties
# ═══════════════════════════════════════════════════════════════════════════════


def _build_grape_variety_facts(source_id: str) -> list[dict]:
    """Build facts about Portuguese grape varieties."""
    facts = []

    for grape in GRAPE_VARIETY_DATABASE:
        name = grape["name"]
        color = grape["color"]
        entities = [{"type": "grape", "name": name}]
        base_tags = ["portugal", "grape", name.lower().replace(" ", "_"), color]

        # Description
        facts.append(_make_fact(
            f"{name} is a {color} grape variety: {grape['description']}.",
            domain="grape_varieties",
            source_id=source_id,
            subdomain=f"portuguese_{color}_grapes",
            entities=entities,
            tags=base_tags,
        ))

        # Characteristics
        if grape.get("characteristics"):
            facts.append(_make_fact(
                f"{name} grape characteristics: {grape['characteristics']}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain=f"portuguese_{color}_grapes",
                entities=entities,
                tags=base_tags + ["characteristics"],
            ))

        # Planted area
        if grape.get("area_ha"):
            facts.append(_make_fact(
                f"{name} is planted on approximately {grape['area_ha']:,} hectares in Portugal.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="planting_statistics",
                entities=entities,
                tags=base_tags + ["statistics", "area"],
            ))

        # Origin
        if grape.get("origin"):
            facts.append(_make_fact(
                f"The {name} grape variety originates from {grape['origin']}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="grape_origins",
                entities=entities,
                tags=base_tags + ["origin"],
            ))

        # Regions grown
        if grape.get("regions") and len(grape["regions"]) > 1:
            region_list = ", ".join(grape["regions"])
            region_entities = entities + [{"type": "region", "name": r} for r in grape["regions"]]
            facts.append(_make_fact(
                f"{name} is grown in the Portuguese wine regions of {region_list}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="regional_grapes",
                entities=region_entities,
                tags=base_tags + ["regions"],
            ))

        # Synonyms
        if grape.get("synonyms") and len(grape["synonyms"]) > 0:
            synonym_list = ", ".join(grape["synonyms"])
            facts.append(_make_fact(
                f"{name} is also known as {synonym_list}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="grape_synonyms",
                entities=entities,
                tags=base_tags + ["synonyms"],
            ))

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# FACT BUILDERS — Classification System
# ═══════════════════════════════════════════════════════════════════════════════


def _build_classification_facts(source_id: str) -> list[dict]:
    """Build facts about the Portuguese wine classification system."""
    facts = []
    base_tags = ["portugal", "classification"]
    base_entities = [{"type": "country", "name": "Portugal"}]

    # ── Classification levels ────────────────────────────────────────────────
    for level in CLASSIFICATION_DATABASE["levels"]:
        level_entities = base_entities + [{"type": "classification", "name": level["name"]}]

        facts.append(_make_fact(
            f"{level['name']} ({level['full_name']}) in Portuguese wine: {level['description']}.",
            domain="wine_regions",
            source_id=source_id,
            subdomain="portugal_classification",
            entities=level_entities,
            tags=base_tags + [level["name"].lower().replace(" ", "_")],
        ))

        if level.get("count") and level["count"] > 0:
            facts.append(_make_fact(
                f"Portugal has approximately {level['count']} {level['name']} designated wine regions.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="portugal_classification",
                entities=level_entities,
                tags=base_tags + [level["name"].lower().replace(" ", "_"), "statistics"],
            ))

        if level.get("examples"):
            examples_str = ", ".join(level["examples"])
            facts.append(_make_fact(
                f"Examples of Portuguese {level['name']} wines include {examples_str}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="portugal_classification",
                entities=level_entities,
                tags=base_tags + [level["name"].lower().replace(" ", "_")],
            ))

    # ── Special designations ─────────────────────────────────────────────────
    for desig in CLASSIFICATION_DATABASE["special_designations"]:
        desig_entities = base_entities + [{"type": "designation", "name": desig["name"]}]

        facts.append(_make_fact(
            f"The {desig['name']} designation in Portuguese wine: {desig['description']}.",
            domain="wine_regions",
            source_id=source_id,
            subdomain="portugal_designations",
            entities=desig_entities,
            tags=base_tags + ["designation", desig["name"].lower()],
        ))

    # ── Regulatory bodies ────────────────────────────────────────────────────
    for body in CLASSIFICATION_DATABASE["regulatory_bodies"]:
        body_entities = base_entities + [{"type": "organization", "name": body["name"]}]

        facts.append(_make_fact(
            f"The {body['name']} ({body['full_name']}) {body['role']}.",
            domain="wine_business",
            source_id=source_id,
            subdomain="portugal_regulation",
            entities=body_entities,
            tags=base_tags + ["regulatory", body["name"].lower()],
        ))

    # ── Hierarchy summary ────────────────────────────────────────────────────
    facts.append(_make_fact(
        "The Portuguese wine classification hierarchy from highest to lowest is: DOC (Denominação de Origem Controlada), Vinho Regional/IGP (Indicação Geográfica Protegida), and Vinho de Mesa (table wine).",
        domain="wine_regions",
        source_id=source_id,
        subdomain="portugal_classification",
        entities=base_entities,
        tags=base_tags + ["hierarchy"],
    ))

    facts.append(_make_fact(
        "Port wine and Madeira wine each have their own separate regulatory bodies (IVDP and IVBAM respectively), distinct from the general Portuguese wine classification system overseen by the IVV.",
        domain="wine_business",
        source_id=source_id,
        subdomain="portugal_regulation",
        entities=base_entities + [
            {"type": "organization", "name": "IVDP"},
            {"type": "organization", "name": "IVBAM"},
            {"type": "organization", "name": "IVV"},
        ],
        tags=base_tags + ["regulatory"],
    ))

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# FACT BUILDERS — Sub-regions
# ═══════════════════════════════════════════════════════════════════════════════


def _build_subregion_facts(source_id: str) -> list[dict]:
    """Build facts about Vinho Verde and Alentejo sub-regions."""
    facts = []

    # ── Vinho Verde sub-regions ──────────────────────────────────────────────
    for sub in VINHO_VERDE_SUBREGION_DATABASE:
        entities = [
            {"type": "region", "name": "Vinho Verde"},
            {"type": "sub_region", "name": sub["name"]},
        ]
        tags = ["portugal", "vinho_verde", "sub_region", sub["name"].lower().replace(" ", "_").replace("ã", "a").replace("ç", "c")]

        facts.append(_make_fact(
            f"{sub['name']} is one of the nine sub-regions of Vinho Verde DOC: {sub['description']}.",
            domain="wine_regions",
            source_id=source_id,
            subdomain="vinho_verde_sub_regions",
            entities=entities,
            tags=tags,
        ))

        if sub.get("key_grape"):
            grape_entities = entities + [{"type": "grape", "name": sub["key_grape"]}]
            facts.append(_make_fact(
                f"The key grape variety in the {sub['name']} sub-region of Vinho Verde is {sub['key_grape']}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="vinho_verde_grapes",
                entities=grape_entities,
                tags=tags + ["grape"],
            ))

    # ── Alentejo sub-regions ─────────────────────────────────────────────────
    for sub in ALENTEJO_SUBREGION_DATABASE:
        entities = [
            {"type": "region", "name": "Alentejo"},
            {"type": "sub_region", "name": sub["name"]},
        ]
        tags = ["portugal", "alentejo", "sub_region", sub["name"].lower().replace(" ", "_")]

        facts.append(_make_fact(
            f"{sub['name']} is one of the eight sub-regions of Alentejo DOC: {sub['description']}.",
            domain="wine_regions",
            source_id=source_id,
            subdomain="alentejo_sub_regions",
            entities=entities,
            tags=tags,
        ))

        if sub.get("notable"):
            facts.append(_make_fact(
                f"{sub['name']} sub-region of the Alentejo: {sub['notable']}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="alentejo_sub_regions",
                entities=entities,
                tags=tags + ["notable"],
            ))

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# FACT BUILDERS — Additional Viticulture & Industry Facts
# ═══════════════════════════════════════════════════════════════════════════════


def _build_additional_facts(source_id: str) -> list[dict]:
    """Build additional Portuguese wine, viticulture, and industry facts."""
    facts = []
    base_entities = [{"type": "country", "name": "Portugal"}]
    base_tags = ["portugal"]

    for fact_text in ADDITIONAL_VITICULTURE_FACTS:
        # Determine domain based on content
        text_lower = fact_text.lower()
        if any(kw in text_lower for kw in ["vine training", "phylloxera", "foot-tread", "harvest", "planting", "terrace", "socalc", "patamar", "lagar", "field blend", "co-ferm", "ungraft", "latada"]):
            domain = "viticulture"
            subdomain = "portuguese_viticulture"
        elif any(kw in text_lower for kw in ["export", "producer", "cork", "per-capita", "market", "investment", "eu accession", "consol"]):
            domain = "wine_business"
            subdomain = "portuguese_industry"
        elif any(kw in text_lower for kw in ["indigenous", "variety", "grape", "touriga", "alicante"]):
            domain = "grape_varieties"
            subdomain = "portuguese_grapes"
        elif any(kw in text_lower for kw in ["unesco", "vineyard area", "docg", "doc"]):
            domain = "wine_regions"
            subdomain = "portuguese_regions"
        else:
            domain = "viticulture"
            subdomain = "portuguese_viticulture"

        facts.append(_make_fact(
            fact_text,
            domain=domain,
            source_id=source_id,
            subdomain=subdomain,
            entities=base_entities,
            tags=base_tags + [subdomain],
        ))

    # ── Winemaking techniques ────────────────────────────────────────────────
    for fact_text in PORTUGUESE_WINEMAKING_FACTS:
        facts.append(_make_fact(
            fact_text,
            domain="winemaking",
            source_id=source_id,
            subdomain="portuguese_winemaking",
            entities=base_entities,
            tags=base_tags + ["winemaking", "technique"],
        ))

    # ── Wine history ──────────────────────────────────────────────────────────
    for fact_text in PORTUGUESE_WINE_HISTORY:
        facts.append(_make_fact(
            fact_text,
            domain="wine_business",
            source_id=source_id,
            subdomain="portuguese_history",
            entities=base_entities,
            tags=base_tags + ["history"],
        ))

    # ── Notable producers ────────────────────────────────────────────────────
    for prod in NOTABLE_PRODUCERS_DATABASE:
        prod_entities = [
            {"type": "producer", "name": prod["name"]},
            {"type": "region", "name": prod["region"]},
        ]
        facts.append(_make_fact(
            f"{prod['name']} ({prod['region']}): {prod['notable']}.",
            domain="producers",
            source_id=source_id,
            subdomain="portuguese_producers",
            entities=prod_entities,
            tags=base_tags + ["producer", prod["region"].lower().replace(" ", "_")],
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
        "port": _build_port_facts,
        "madeira": _build_madeira_facts,
        "grape": _build_grape_variety_facts,
        "classification": _build_classification_facts,
        "subregion": _build_subregion_facts,
        "additional": _build_additional_facts,
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
        click.echo(f"\n[DRY RUN] Would insert {len(facts)} facts from Portuguese Wine Reference Database")

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

    logger.info(f"Inserted {inserted} new facts from Portuguese Wine Reference Database (duplicates skipped)")
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
        "Port Wine": _build_port_facts,
        "Madeira Wine": _build_madeira_facts,
        "Grape Varieties": _build_grape_variety_facts,
        "Classification": _build_classification_facts,
        "Sub-regions": _build_subregion_facts,
        "Additional": _build_additional_facts,
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
    type=click.Choice(["region", "port", "madeira", "grape", "classification", "subregion", "additional"]),
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
    """OenoBench Portuguese Wine Enrichment Scraper — Regions, Port, Madeira, grapes, classification."""
    logger.add("data/logs/portugal_enrichment_{time}.log", rotation="10 MB")

    if list_sources:
        click.echo("\nAvailable data categories:")
        click.echo(f"  {'region':18s} — {len(REGION_DATABASE)} Portuguese wine regions (climate, soil, elevation)")
        click.echo(f"  {'port':18s} — Port wine styles, Douro sub-regions, classification, benefício")
        click.echo(f"  {'madeira':18s} — Madeira noble grapes, aging methods, age categories, history")
        click.echo(f"  {'grape':18s} — {len(GRAPE_VARIETY_DATABASE)} Portuguese grape variety profiles")
        click.echo(f"  {'classification':18s} — DOC/VR/Vinho de Mesa hierarchy, regulatory bodies")
        click.echo(f"  {'subregion':18s} — Vinho Verde ({len(VINHO_VERDE_SUBREGION_DATABASE)}) and Alentejo ({len(ALENTEJO_SUBREGION_DATABASE)}) sub-regions")
        click.echo(f"  {'additional':18s} — {len(ADDITIONAL_VITICULTURE_FACTS)} Portuguese viticulture and industry facts")
        click.echo(f"\nKnowledge base coverage:")
        click.echo(f"  Regions:              {len(REGION_DATABASE)}")
        click.echo(f"  Port styles:          {len(PORT_DATABASE['styles'])}")
        click.echo(f"  Port sub-regions:     {len(PORT_DATABASE['sub_regions'])}")
        click.echo(f"  Port additional:      {len(ADDITIONAL_PORT_FACTS)}")
        click.echo(f"  Madeira grapes:       {len(MADEIRA_DATABASE['noble_grapes'])} noble + {len(MADEIRA_DATABASE['other_grapes'])} other")
        click.echo(f"  Madeira age cats:     {len(MADEIRA_DATABASE['age_categories'])}")
        click.echo(f"  Madeira additional:   {len(ADDITIONAL_MADEIRA_FACTS)}")
        click.echo(f"  Grape varieties:      {len(GRAPE_VARIETY_DATABASE)}")
        click.echo(f"  Classification:       {len(CLASSIFICATION_DATABASE['levels'])} levels + {len(CLASSIFICATION_DATABASE['special_designations'])} designations")
        click.echo(f"  VV sub-regions:       {len(VINHO_VERDE_SUBREGION_DATABASE)}")
        click.echo(f"  Alentejo sub-regions: {len(ALENTEJO_SUBREGION_DATABASE)}")
        click.echo(f"  Additional facts:     {len(ADDITIONAL_VITICULTURE_FACTS)}")
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
