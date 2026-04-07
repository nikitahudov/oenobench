"""
OenoBench — South African Wine Enrichment Scraper

Comprehensive knowledge base covering South Africa's Wine of Origin system,
grape varieties, regional profiles, classification structures, and unique
wine-cultural features (biodiversity, Cap Classique, Constantia history, etc.).

Usage:
    python -m src.scrapers.south_africa_enrichment --all
    python -m src.scrapers.south_africa_enrichment --type region
    python -m src.scrapers.south_africa_enrichment --type grape
    python -m src.scrapers.south_africa_enrichment --type classification
    python -m src.scrapers.south_africa_enrichment --type unique
    python -m src.scrapers.south_africa_enrichment --dry-run
    python -m src.scrapers.south_africa_enrichment --validate
    python -m src.scrapers.south_africa_enrichment --test-run
    python -m src.scrapers.south_africa_enrichment --list
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

TEST_RUN_FACT_LIMIT = 5

SOURCE = {
    "name": "South African Wine Reference Database",
    "url": "https://www.wosa.co.za",
    "source_type": "reference",
    "tier": "tier_2_authoritative",
    "language": "en",
}


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Regional Data
# ═══════════════════════════════════════════════════════════════════════════════

REGION_DATABASE = [
    {
        "name": "Stellenbosch",
        "wo_unit": "district",
        "parent_region": "Cape South Coast",
        "climate": "Mediterranean",
        "climate_details": "Warm days moderated by afternoon sea breezes from False Bay; significant variation between warmer inland valleys and cooler mountain slopes; dry summers with winter rainfall",
        "soil_types": ["granite", "Table Mountain sandstone", "shale"],
        "soil_details": "Diverse soils ranging from decomposed granite on mountain slopes to Table Mountain sandstone and Bokkeveld shale in lower areas; soil diversity is the district's hallmark, producing markedly different wine styles across short distances",
        "elevation_range": "100-500m",
        "vineyard_area_ha": 16000,
        "key_grapes": ["Cabernet Sauvignon", "Shiraz", "Chenin Blanc", "Merlot", "Pinotage"],
        "wine_styles": ["premium Bordeaux-style reds", "full-bodied Shiraz", "complex Chenin Blanc"],
        "wards": ["Simonsberg-Stellenbosch", "Helderberg", "Bottelary Hills", "Devon Valley", "Jonkershoek Valley", "Banghoek", "Polkadraai Hills"],
        "notes": "South Africa's most prestigious red wine district, home to many of the country's top estates and the University of Stellenbosch's viticulture and oenology department",
    },
    {
        "name": "Swartland",
        "wo_unit": "district",
        "parent_region": "Coastal Region",
        "climate": "Mediterranean",
        "climate_details": "Hot, dry summers with limited rainfall; continental-style diurnal temperature variation inland; dryland (unirrigated) bush vines thrive in the warm conditions",
        "soil_types": ["granite", "schist", "slate", "shale"],
        "soil_details": "Granite-based soils on hill slopes around Paardeberg and Kasteelberg; weathered schist and slate in elevated areas; shale-derived soils on lower slopes provide good water retention for dryland viticulture",
        "elevation_range": "100-400m",
        "vineyard_area_ha": 15000,
        "key_grapes": ["Chenin Blanc", "Syrah", "Grenache", "Mourvèdre", "Cinsault"],
        "wine_styles": ["old-vine Chenin Blanc", "Rhône-style reds", "Swartland Revolution natural wines"],
        "wards": ["Malmesbury", "Riebeekberg"],
        "notes": "Epicenter of the Swartland Revolution — a movement of independent winemakers championing old bush vines, minimal intervention, and terroir-driven wines since the early 2000s",
    },
    {
        "name": "Constantia",
        "wo_unit": "ward",
        "parent_region": "Cape Town",
        "climate": "cool maritime",
        "climate_details": "South Africa's coolest wine-growing area, strongly influenced by the cold Benguela Current and winds funneled between Table Mountain and the Constantiaberg; long, cool growing season",
        "soil_types": ["granite", "Table Mountain sandstone"],
        "soil_details": "Decomposed Table Mountain granite on the lower slopes of the Constantiaberg mountain, providing excellent drainage and low fertility that naturally restricts vine vigour",
        "elevation_range": "60-350m",
        "vineyard_area_ha": 500,
        "key_grapes": ["Sauvignon Blanc", "Muscat de Frontignan", "Semillon"],
        "wine_styles": ["crisp Sauvignon Blanc", "Vin de Constance (Muscat dessert wine)"],
        "wards": [],
        "notes": "South Africa's oldest wine-producing area (first vines planted 1685 by Governor Simon van der Stel); Constantia's legendary Muscat-based dessert wine was prized by Napoleon, Frederick the Great, and referenced by Jane Austen and Charles Dickens",
    },
    {
        "name": "Franschhoek",
        "wo_unit": "ward",
        "parent_region": "Cape Winelands",
        "climate": "warm Mediterranean",
        "climate_details": "Sheltered mountain valley that is one of the warmer Cape wine areas; surrounded by the Franschhoek, Groot Drakenstein, and Simonsberg mountains; afternoon breezes from the southeast provide some cooling",
        "soil_types": ["alluvial", "granite", "sandstone"],
        "soil_details": "Rich alluvial soils on the valley floor with granite-derived soils on the mountain slopes; the valley's enclosed shape traps heat, suited to full-bodied reds",
        "elevation_range": "200-500m",
        "vineyard_area_ha": 1500,
        "key_grapes": ["Semillon", "Cabernet Sauvignon", "Chenin Blanc", "Shiraz"],
        "wine_styles": ["old-vine Semillon", "Bordeaux-style blends", "Cap Classique sparkling"],
        "wards": [],
        "notes": "Known as the 'French Corner' — settled by French Huguenot refugees in 1688 who brought winemaking traditions; Franschhoek is the centre of South Africa's Cap Classique (traditional method sparkling wine) production",
    },
    {
        "name": "Paarl",
        "wo_unit": "district",
        "parent_region": "Cape Winelands",
        "climate": "warm Mediterranean",
        "climate_details": "Generally warm and dry; the imposing Paarl Rock (granite dome) and surrounding mountains create varied microclimates; the Berg River valley is cooler, while northern slopes are warmer",
        "soil_types": ["granite", "shale", "sandstone"],
        "soil_details": "Granite-derived soils on the slopes of Paarl Mountain; Bokkeveld shale in lower areas; the district's diversity of terroir supports a wide range of wine styles",
        "elevation_range": "100-600m",
        "vineyard_area_ha": 16000,
        "key_grapes": ["Chenin Blanc", "Cabernet Sauvignon", "Shiraz", "Pinotage", "Chardonnay"],
        "wine_styles": ["everyday to premium reds", "fortified wines", "brandy"],
        "wards": ["Voor-Paardeberg", "Simonsberg-Paarl"],
        "notes": "Historically the headquarters of the KWV (Ko-operatieve Wijnbouwers Vereniging), the cooperative that controlled the South African wine industry for most of the 20th century",
    },
    {
        "name": "Walker Bay",
        "wo_unit": "district",
        "parent_region": "Cape South Coast",
        "climate": "cool maritime",
        "climate_details": "Strong maritime influence from Walker Bay and the cold Antarctic-fed ocean currents; the Hemel-en-Aarde valley is sheltered from the harshest winds while retaining cool temperatures ideal for Pinot Noir and Chardonnay",
        "soil_types": ["shale", "clay", "sandstone", "granite"],
        "soil_details": "The Hemel-en-Aarde Valley has clay-rich Bokkeveld shale providing excellent water retention; the Upper Hemel-en-Aarde Valley has more granite and sandstone with better drainage; the Hemel-en-Aarde Ridge has iron-rich clay over Table Mountain sandstone",
        "elevation_range": "50-400m",
        "vineyard_area_ha": 1000,
        "key_grapes": ["Pinot Noir", "Chardonnay", "Sauvignon Blanc", "Pinotage"],
        "wine_styles": ["Burgundian-style Pinot Noir", "elegant Chardonnay", "cool-climate Pinotage"],
        "wards": ["Hemel-en-Aarde Valley", "Upper Hemel-en-Aarde Valley", "Hemel-en-Aarde Ridge"],
        "notes": "Walker Bay's Hemel-en-Aarde ('Heaven and Earth') valley is divided into three wards — Hemel-en-Aarde Valley, Upper Hemel-en-Aarde Valley, and Hemel-en-Aarde Ridge — each with distinct soil and mesoclimate profiles",
    },
    {
        "name": "Elgin",
        "wo_unit": "ward",
        "parent_region": "Cape South Coast",
        "climate": "cool continental",
        "climate_details": "One of the coolest wine regions in South Africa due to high elevation and proximity to the ocean; formerly apple-growing country, converted to vineyards from the 1980s onward; average temperature 2-3 degrees Celsius cooler than Stellenbosch",
        "soil_types": ["shale", "sandstone", "clay"],
        "soil_details": "Table Mountain sandstone and Bokkeveld shale form the base geology; well-drained soils on gentle slopes at relatively high altitude provide stress that concentrates flavors in cool-climate varieties",
        "elevation_range": "250-600m",
        "vineyard_area_ha": 700,
        "key_grapes": ["Sauvignon Blanc", "Pinot Noir", "Chardonnay", "Riesling"],
        "wine_styles": ["lean mineral Sauvignon Blanc", "elegant Pinot Noir", "Méthode Cap Classique"],
        "wards": [],
        "notes": "Elgin was traditionally apple-farming country; wine grapes were first planted in the 1980s and the ward has rapidly established itself as one of South Africa's premier cool-climate areas",
    },
    {
        "name": "Robertson",
        "wo_unit": "district",
        "parent_region": "Breede River Valley",
        "climate": "warm semi-arid",
        "climate_details": "Hot summers with low rainfall (350mm annually); irrigation from the Breede River is essential; the Langeberg mountains to the south provide some protection; warm days and cool nights from high elevation",
        "soil_types": ["limestone", "alluvial", "shale"],
        "soil_details": "Distinctive lime-rich soils (some of the only limestone soils in South Africa) along with alluvial deposits from the Breede River; the limestone contributes mineral character to the wines",
        "elevation_range": "150-400m",
        "vineyard_area_ha": 13000,
        "key_grapes": ["Chardonnay", "Shiraz", "Colombard", "Sauvignon Blanc", "Cabernet Sauvignon"],
        "wine_styles": ["value Chardonnay", "Shiraz", "Colombard for brandy distillation"],
        "wards": ["McGregor", "Bonnievale", "Vinkrivier"],
        "notes": "Robertson is one of the few South African districts with significant limestone soils; its warm climate and irrigation-dependent viticulture produce large volumes of fruit-driven wines and brandy base wine",
    },
    {
        "name": "Cape Point",
        "wo_unit": "ward",
        "parent_region": "Cape Town",
        "climate": "extreme maritime",
        "climate_details": "One of the most maritime wine regions in the world; constant wind, sea fog, and proximity to the confluence of the Atlantic and Indian Oceans create challenging but unique growing conditions",
        "soil_types": ["granite", "sandstone"],
        "soil_details": "Weathered Table Mountain sandstone and granite soils; thin, well-drained soils with low natural fertility; vineyards must be carefully sited to manage wind exposure",
        "elevation_range": "50-250m",
        "vineyard_area_ha": 100,
        "key_grapes": ["Sauvignon Blanc", "Semillon", "Chardonnay"],
        "wine_styles": ["mineral-driven Sauvignon Blanc", "Sauvignon Blanc-Semillon blends"],
        "wards": [],
        "notes": "Cape Point is one of the smallest and most extreme wine wards in South Africa, with vineyards exposed to powerful south-easterly winds and cool maritime conditions near the Cape of Good Hope",
    },
    {
        "name": "Tulbagh",
        "wo_unit": "district",
        "parent_region": "Cape Winelands",
        "climate": "warm with continental influence",
        "climate_details": "Enclosed mountain basin surrounded by the Witzenberg, Winterhoek, and Obiqua ranges; very hot days but significant nighttime cooling from mountain air drainage creates marked diurnal temperature variation",
        "soil_types": ["shale", "sandstone", "alluvial"],
        "soil_details": "Bokkeveld shale on the mountain slopes with alluvial soils on the valley floor; the enclosed basin collects heat during the day but cools sharply at night",
        "elevation_range": "150-500m",
        "vineyard_area_ha": 1200,
        "key_grapes": ["Shiraz", "Chenin Blanc", "Pinotage", "Sauvignon Blanc"],
        "wine_styles": ["robust Shiraz", "Méthode Cap Classique"],
        "wards": [],
        "notes": "Tulbagh is an enclosed mountain basin with some of the largest diurnal temperature swings in the Cape winelands, producing wines with strong fruit concentration and natural acidity retention",
    },
    {
        "name": "Elim",
        "wo_unit": "ward",
        "parent_region": "Cape South Coast",
        "climate": "cool maritime",
        "climate_details": "South Africa's southernmost wine ward; exposed to fierce Antarctic-origin winds off the ocean; very cool growing conditions with a long ripening season that extends the hangtime of grapes",
        "soil_types": ["shale", "sandstone", "limestone"],
        "soil_details": "Bokkeveld shale over Table Mountain sandstone with some pockets of limestone; the wind-battered vines produce small, concentrated berries with thick skins",
        "elevation_range": "50-300m",
        "vineyard_area_ha": 200,
        "key_grapes": ["Sauvignon Blanc", "Semillon", "Shiraz"],
        "wine_styles": ["intense cool-climate Sauvignon Blanc", "Semillon", "peppery Shiraz"],
        "wards": [],
        "notes": "Elim is the southernmost wine ward in Africa, located near the village of Elim originally established by Moravian missionaries; its extreme maritime exposure produces some of South Africa's most aromatic Sauvignon Blanc",
    },
    {
        "name": "Darling",
        "wo_unit": "district",
        "parent_region": "Coastal Region",
        "climate": "cool maritime",
        "climate_details": "Cool maritime climate with strong influence from the cold Atlantic Ocean; the Groenekloof ward is particularly cool and windy, producing wines with notable freshness",
        "soil_types": ["shale", "granite", "ferricrete"],
        "soil_details": "Predominantly Malmesbury shale with weathered granite on the higher slopes of the Darling Hills; Groenekloof has iron-rich ferricrete soils that stress the vines naturally",
        "elevation_range": "100-350m",
        "vineyard_area_ha": 2000,
        "key_grapes": ["Sauvignon Blanc", "Chenin Blanc", "Shiraz"],
        "wine_styles": ["fresh cool-climate Sauvignon Blanc", "elegant Shiraz"],
        "wards": ["Groenekloof"],
        "notes": "The Groenekloof ward within Darling district is renowned for maritime-influenced Sauvignon Blanc and was one of the first single-ward wines to gain international recognition",
    },
    {
        "name": "Durbanville",
        "wo_unit": "ward",
        "parent_region": "Cape Town",
        "climate": "cool maritime",
        "climate_details": "Cool breezes from Table Bay and the Atlantic provide natural temperature moderation; vineyards on the slopes of the Tygerberg hills enjoy good air drainage and afternoon cooling",
        "soil_types": ["granite", "shale", "clay"],
        "soil_details": "Decomposed Malmesbury granite and shale on the slopes of the Tygerberg hills; red clay subsoils provide good water retention during the dry summer months",
        "elevation_range": "100-380m",
        "vineyard_area_ha": 1400,
        "key_grapes": ["Sauvignon Blanc", "Merlot", "Cabernet Sauvignon", "Chardonnay"],
        "wine_styles": ["crisp Sauvignon Blanc", "supple Merlot"],
        "wards": [],
        "notes": "Durbanville's vineyards are increasingly under pressure from urban expansion as Cape Town grows northward; the ward produces notably crisp Sauvignon Blanc thanks to cool maritime influence",
    },
    {
        "name": "Worcester",
        "wo_unit": "district",
        "parent_region": "Breede River Valley",
        "climate": "warm semi-arid",
        "climate_details": "Warm to hot inland climate in the Breede River valley; the Hex River and Du Toitskloof mountains provide some shelter; irrigation from the Breede River is essential as rainfall is only 250-300mm per year",
        "soil_types": ["alluvial", "shale", "sandstone"],
        "soil_details": "Deep alluvial soils deposited by the Breede River and its tributaries; some shale and sandstone on higher ground; fertile soils support high-yielding vineyards",
        "elevation_range": "150-500m",
        "vineyard_area_ha": 18000,
        "key_grapes": ["Colombard", "Chenin Blanc", "Muscadel", "Cabernet Sauvignon"],
        "wine_styles": ["bulk wine", "brandy base wine", "fortified Muscadel", "dessert wines"],
        "wards": ["Nuy", "Goudini", "Slanghoek"],
        "notes": "Worcester is South Africa's largest wine district by volume, producing more wine than any other; a major centre for brandy distillation and fortified Muscadel dessert wines",
    },
    {
        "name": "Olifants River",
        "wo_unit": "region",
        "parent_region": "Olifants River",
        "climate": "hot semi-arid",
        "climate_details": "Hot, dry conditions with very low rainfall; irrigation from the Olifants River is essential; the Citrusdal and Cederberg sub-areas at higher elevations produce more refined wines",
        "soil_types": ["alluvial", "sandy loam", "shale"],
        "soil_details": "Deep alluvial soils along the Olifants River; sandy loam in the lower areas; Citrusdal Mountain has some shale and sandstone at higher elevations",
        "elevation_range": "50-900m",
        "vineyard_area_ha": 8000,
        "key_grapes": ["Colombard", "Chenin Blanc", "Sauvignon Blanc", "Pinotage"],
        "wine_styles": ["bulk wine", "cooperative wine", "value whites"],
        "wards": ["Citrusdal Mountain", "Piekenierskloof"],
        "notes": "Olifants River is primarily a high-volume production area; however, the Piekenierskloof ward has gained recognition for old bush vine Grenache and Chenin Blanc from high-altitude, dryland vineyards",
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Grape Variety Data
# ═══════════════════════════════════════════════════════════════════════════════

GRAPE_VARIETY_DATABASE = [
    {
        "name": "Chenin Blanc",
        "synonyms": ["Steen"],
        "color": "white",
        "planted_ha": 18000,
        "share_pct": 18.0,
        "origin": "Loire Valley, France",
        "introduction": "Brought to the Cape by Jan van Riebeeck's gardener in the mid-17th century; known locally as Steen until the 1960s when ampelographer Professor Chris Orffer confirmed its identity as Chenin Blanc",
        "key_regions": ["Swartland", "Paarl", "Stellenbosch", "Worcester"],
        "wine_styles": ["dry still", "off-dry", "rich wooded", "sparkling (Cap Classique)", "sweet botrytized"],
        "viticulture_notes": "Old bush vines (some 50+ years) in the Swartland are the source of South Africa's most acclaimed Chenin Blanc; dryland farming concentrates flavors in these low-yielding old vines",
        "significance": "Most planted grape variety in South Africa, accounting for approximately 18% of all plantings; the Chenin Blanc Association promotes quality and old-vine preservation",
    },
    {
        "name": "Pinotage",
        "synonyms": [],
        "color": "red",
        "planted_ha": 6000,
        "share_pct": 6.0,
        "origin": "South Africa",
        "introduction": "Created in 1925 by Professor Abraham Izak Perold at Stellenbosch University by crossing Pinot Noir with Cinsault (then called Hermitage in South Africa); the first experimental vines were planted at the Welgevallen experimental farm and almost lost before being rescued by Professor Charlie Niehaus",
        "key_regions": ["Stellenbosch", "Swartland", "Paarl", "Western Cape"],
        "wine_styles": ["fruity unoaked", "full-bodied wooded", "rosé", "Cape Blend component", "fortified"],
        "viticulture_notes": "Pinotage is an early-ripening variety that can be sensitive to heat stress; it requires careful canopy management to avoid acetone-like off-flavors; best results come from older, low-yielding vines",
        "significance": "South Africa's signature grape variety, though controversial — praised for distinctive smoky, dark-fruit character by supporters and criticized by detractors; the Pinotage Association promotes quality standards",
    },
    {
        "name": "Cabernet Sauvignon",
        "synonyms": [],
        "color": "red",
        "planted_ha": 11000,
        "share_pct": 11.0,
        "origin": "Bordeaux, France",
        "introduction": "Established in South Africa from the mid-19th century; quality improved dramatically after the virus-free clonal selections became available in the 1980s and 1990s",
        "key_regions": ["Stellenbosch", "Paarl", "Franschhoek"],
        "wine_styles": ["single varietal", "Bordeaux-style blends", "Cape Blend component"],
        "viticulture_notes": "Performs best on well-drained granite and sandstone soils at moderate elevation in the Stellenbosch district; virus-free plant material was a transformative improvement",
        "significance": "South Africa's most planted red variety and the backbone of the country's premium red wine production; Stellenbosch Cabernet Sauvignon benchmarks can compete with the best internationally",
    },
    {
        "name": "Shiraz",
        "synonyms": ["Syrah"],
        "color": "red",
        "planted_ha": 10000,
        "share_pct": 10.0,
        "origin": "Rhône Valley, France",
        "introduction": "Has been in South Africa since the late 18th century; renewed interest since the 1990s driven by the Swartland Revolution and the Rhône Ranger movement",
        "key_regions": ["Swartland", "Stellenbosch", "Paarl", "Franschhoek"],
        "wine_styles": ["cool-climate peppery Syrah", "warm-climate rich Shiraz", "Rhône-style blends (GSM)", "rosé"],
        "viticulture_notes": "Style varies dramatically by region: Swartland produces spicy, medium-bodied Rhône-style wines from bush vines, while Stellenbosch tends toward richer, more structured expressions from trellised vines",
        "significance": "Increasingly seen as South Africa's most versatile red grape; the stylistic divide between warm-climate Shiraz and cool-climate Syrah mirrors Australian and French approaches",
    },
    {
        "name": "Colombard",
        "synonyms": [],
        "color": "white",
        "planted_ha": 11000,
        "share_pct": 11.0,
        "origin": "South-west France",
        "introduction": "Originally planted in South Africa as a brandy base variety; remains widely planted in the warm inland districts",
        "key_regions": ["Robertson", "Worcester", "Olifants River", "Breedekloof"],
        "wine_styles": ["crisp dry white", "brandy base wine", "sparkling wine base"],
        "viticulture_notes": "High-yielding variety that retains acidity well in warm climates; primarily grown in irrigated inland districts for volume production",
        "significance": "Second most planted white grape variety in South Africa alongside Sauvignon Blanc; primarily used for brandy distillation and everyday white wines",
    },
    {
        "name": "Sauvignon Blanc",
        "synonyms": [],
        "color": "white",
        "planted_ha": 10000,
        "share_pct": 10.0,
        "origin": "Loire Valley / Bordeaux, France",
        "introduction": "Plantings expanded rapidly from the 1990s, driven by consumer demand and the discovery that cool-climate South African sites could produce world-class examples",
        "key_regions": ["Constantia", "Cape Point", "Elgin", "Darling", "Durbanville", "Elim"],
        "wine_styles": ["fresh and aromatic", "mineral and restrained", "wooded (fumé style)"],
        "viticulture_notes": "Thrives in cool maritime and elevated sites; Cape Point, Constantia, and Elgin produce the most refined examples; the variety is sensitive to site selection and benefits from long, cool ripening",
        "significance": "South Africa's most successful white wine export; cool-climate expressions from the Cape South Coast have established international benchmark quality",
    },
    {
        "name": "Chardonnay",
        "synonyms": [],
        "color": "white",
        "planted_ha": 7000,
        "share_pct": 7.0,
        "origin": "Burgundy, France",
        "introduction": "Became widely planted in the 1980s and 1990s; initially produced in an over-oaked New World style, but has evolved toward more restrained, site-specific expressions",
        "key_regions": ["Robertson", "Walker Bay", "Elgin", "Stellenbosch"],
        "wine_styles": ["unoaked and fresh", "barrel-fermented and complex", "Méthode Cap Classique base"],
        "viticulture_notes": "Increasingly planted in cool-climate sites in Walker Bay and Elgin where the variety achieves better acidity balance and longer hangtime; also widely used as a base for Cap Classique sparkling wines",
        "significance": "Robertson is the largest Chardonnay-producing area by volume; Walker Bay and Elgin produce the most critically acclaimed still Chardonnay",
    },
    {
        "name": "Merlot",
        "synonyms": [],
        "color": "red",
        "planted_ha": 6000,
        "share_pct": 6.0,
        "origin": "Bordeaux, France",
        "introduction": "Gained popularity in the 1990s as part of the global Merlot trend; plantings have stabilised",
        "key_regions": ["Stellenbosch", "Paarl", "Durbanville"],
        "wine_styles": ["soft single varietal", "Bordeaux-style blend component"],
        "viticulture_notes": "Best results from cooler sites in Stellenbosch and Durbanville where the variety retains structure; can overcrop easily in warm, fertile conditions",
        "significance": "Important blending partner for Cabernet Sauvignon in Bordeaux-style blends; also produced as an approachable single varietal wine",
    },
    {
        "name": "Cinsault",
        "synonyms": ["Cinsaut", "Hermitage"],
        "color": "red",
        "planted_ha": 2500,
        "share_pct": 2.5,
        "origin": "Southern France",
        "introduction": "One of South Africa's oldest planted red varieties, historically known as Hermitage; old Cinsault bush vines are increasingly valued by the natural wine movement",
        "key_regions": ["Swartland", "Paarl", "Stellenbosch"],
        "wine_styles": ["light-bodied reds", "rosé", "field blend component"],
        "viticulture_notes": "Old bush vines (some 40+ years) produce low yields of concentrated fruit; the parent variety of Pinotage (crossed with Pinot Noir to create Pinotage in 1925)",
        "significance": "Historically used as a workhorse blending grape and Pinotage's parent; now championed by the Swartland Revolution for producing elegant, light-bodied reds and rosé from old vines",
    },
    {
        "name": "Muscat de Frontignan",
        "synonyms": ["Muscat Blanc à Petits Grains", "Muscadel"],
        "color": "white",
        "planted_ha": 3000,
        "share_pct": 3.0,
        "origin": "Mediterranean basin",
        "introduction": "Brought to the Cape in the earliest days of the colony; the variety behind the legendary 18th-century Constantia dessert wines that were among the most expensive wines in the world",
        "key_regions": ["Constantia", "Worcester", "Robertson"],
        "wine_styles": ["Vin de Constance (sweet)", "fortified Muscadel", "dry aromatic"],
        "viticulture_notes": "In Constantia, grapes are left to raisin partially on the vine for the production of Vin de Constance; in the warm inland districts, used for fortified Muscadel dessert wines",
        "significance": "The grape behind Klein Constantia's Vin de Constance, a revival of the legendary 18th-century Constantia dessert wine; Muscat de Frontignan-based fortified Muscadel is a traditional South African dessert wine style",
    },
    {
        "name": "Grenache",
        "synonyms": ["Grenache Noir"],
        "color": "red",
        "planted_ha": 500,
        "share_pct": 0.5,
        "origin": "Spain (as Garnacha)",
        "introduction": "Small but growing plantings driven by interest in Rhône-style blends; some very old bush vines exist in Piekenierskloof",
        "key_regions": ["Swartland", "Piekenierskloof", "Stellenbosch"],
        "wine_styles": ["Rhône-style blends (GSM)", "single varietal", "rosé"],
        "viticulture_notes": "Old bush vines in Piekenierskloof (some 50+ years) are among the most prized Grenache vineyards in South Africa; the variety thrives in hot, dry conditions on low-fertility soils",
        "significance": "A key component in Swartland Rhône-style blends; Piekenierskloof old-vine Grenache has attracted international attention as some of the finest expressions of the variety outside France and Spain",
    },
    {
        "name": "Semillon",
        "synonyms": [],
        "color": "white",
        "planted_ha": 1000,
        "share_pct": 1.0,
        "origin": "Bordeaux, France",
        "introduction": "One of the earliest white varieties planted in the Cape; Franschhoek has old Semillon vineyards dating back decades",
        "key_regions": ["Franschhoek", "Stellenbosch", "Cape Point"],
        "wine_styles": ["barrel-fermented and rich", "Sauvignon Blanc-Semillon blends", "sweet late-harvest"],
        "viticulture_notes": "Franschhoek old-vine Semillon is a uniquely South African speciality; the variety has historical significance as one of the Huguenot settlers' first plantings",
        "significance": "Franschhoek is one of the few places in the world producing high-quality varietal Semillon from old vines; the grape is also blended with Sauvignon Blanc in Bordeaux-style white blends",
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Classification System
# ═══════════════════════════════════════════════════════════════════════════════

CLASSIFICATION_DATABASE = {
    "wo_system": {
        "name": "Wine of Origin (WO)",
        "description": "South Africa's appellation system, established in 1973, guarantees the origin, vintage, and grape variety of wines through a certification process administered by the Wine and Spirit Board",
        "levels": [
            {
                "level": "Geographical Unit",
                "description": "The broadest level, covering large production areas",
                "examples": ["Western Cape", "Northern Cape", "Eastern Cape", "KwaZulu-Natal", "Limpopo", "Free State"],
                "notes": "Western Cape is by far the most important, encompassing the vast majority of South African wine production",
            },
            {
                "level": "Region",
                "description": "A grouping of districts within a geographical unit",
                "examples": ["Coastal Region", "Breede River Valley", "Cape South Coast", "Klein Karoo", "Olifants River"],
                "notes": "Regions are broader than districts and may contain multiple districts within them",
            },
            {
                "level": "District",
                "description": "A defined wine-growing area within a region",
                "examples": ["Stellenbosch", "Paarl", "Swartland", "Robertson", "Walker Bay", "Worcester"],
                "notes": "Districts are the most commonly used WO unit on wine labels and must share broadly similar environmental conditions",
            },
            {
                "level": "Ward",
                "description": "The most specific geographical unit, a smaller area within a district with distinctive terroir",
                "examples": ["Constantia", "Elgin", "Franschhoek", "Jonkershoek Valley", "Banghoek", "Hemel-en-Aarde Valley"],
                "notes": "Wards must demonstrate unique soil, climate, or terrain characteristics distinct from the broader district",
            },
        ],
    },
    "estate_wine": {
        "name": "Estate Wine",
        "description": "Estate wine in South Africa must be produced entirely from grapes grown on a registered estate — a defined, contiguous area of land where the wine is also vinified",
        "requirements": "The grapes must be grown, vinified, and bottled on the registered estate; the estate must be a single contiguous property",
    },
    "single_vineyard": {
        "name": "Single Vineyard Wine",
        "description": "A Single Vineyard wine must be produced from a specific demarcated vineyard block of no more than 6 hectares",
        "requirements": "The vineyard block must be no larger than 6 hectares and must be separately registered with the Wine and Spirit Board; the block must be clearly defined and consistently used",
    },
    "integrity_seal": {
        "name": "Integrity & Sustainability Seal",
        "description": "The green-and-white capsule seal found on the neck of certified South African wines guarantees the wine's origin, vintage, and variety claims and certifies that it was produced under sustainable practices",
        "details": "Introduced in its current form to combine the traditional certification of origin, vintage, and variety with the IPW sustainability certification; the seal is only applied after the wine passes chemical and sensory analysis",
    },
    "ipw": {
        "name": "Integrated Production of Wine (IPW)",
        "description": "South Africa's environmental sustainability certification for wine production, covering vineyard practices, cellar operations, and biodiversity conservation",
        "details": "IPW was established in 1998 and sets guidelines for responsible use of pesticides, water, energy, and waste management; compliance is independently audited; over 95% of South African wine is produced under IPW guidelines",
    },
    "old_vine_project": {
        "name": "Old Vine Project",
        "description": "The Old Vine Project certifies and promotes Heritage Vineyards — vineyard blocks that are 35 years or older — by maintaining a registry, awarding a certified seal, and supporting the preservation of these irreplaceable vines",
        "details": "Some of South Africa's certified Heritage Vineyards are over 100 years old, including bush vine Chenin Blanc, Cinsault, and Muscat plantings; the oldest registered vineyard dates to 1900; the seal on the bottle guarantees the wine was made from vines in the Heritage Vineyard register",
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Unique Features
# ═══════════════════════════════════════════════════════════════════════════════

UNIQUE_DATABASE = {
    "bwi": {
        "name": "Biodiversity & Wine Initiative (BWI)",
        "description": "The BWI is a partnership between the South African wine industry and conservation organizations to protect the Cape Floral Kingdom — the world's smallest and most threatened floral kingdom — by establishing conservation corridors between vineyards and setting aside natural habitat on wine farms",
        "facts": [
            "The Cape Floral Kingdom (Cape Floristic Region) is the smallest of the world's six floral kingdoms and is a UNESCO World Heritage Site.",
            "The BWI encourages wine farms to set aside natural fynbos vegetation as conservation areas, creating biodiversity corridors that connect fragmented habitats.",
            "Over 130,000 hectares of natural habitat on wine farms have been set aside for conservation through the BWI.",
            "The Cape winelands overlap with one of the world's 36 biodiversity hotspots, making conservation in vineyards critically important for endangered species.",
            "South Africa's wine industry is one of the few in the world where biodiversity conservation is formally integrated into production standards through the BWI and IPW programs.",
            "Many South African wine estates serve as custodians of endangered fynbos species, with some farms harboring more plant species per hectare than tropical rainforests.",
        ],
    },
    "cap_classique": {
        "name": "Cap Classique",
        "description": "Cap Classique is South Africa's term for traditional method sparkling wine (méthode champenoise), produced using the same secondary fermentation in bottle technique as Champagne",
        "facts": [
            "The term Cap Classique was coined by Frans Malan of Simonsig Estate in 1992 to distinguish South African traditional method sparkling wines from Champagne.",
            "Simonsig produced the first South African méthode champenoise sparkling wine, Kaapse Vonkel, in 1971.",
            "Cap Classique wines are made primarily from Chardonnay and Pinot Noir, following the Champagne model, though some producers also use Chenin Blanc as a uniquely South African variation.",
            "Franschhoek has positioned itself as the epicentre of Cap Classique production, hosting an annual Cap Classique Challenge competition.",
            "South African Cap Classique production has grown significantly since the 2000s, with over 100 producers now making traditional method sparkling wine.",
            "The Cap Classique Producers Association sets minimum quality standards including a minimum of 9 months on lees, though premium cuvées often age for 36 months or more.",
            "Graham Beck is one of South Africa's most recognized Cap Classique producers, having supplied sparkling wine for Nelson Mandela's presidential inauguration in 1994.",
        ],
    },
    "constantia_history": {
        "name": "Constantia — Historic Wine Legacy",
        "description": "The Constantia wine estate, founded in 1685, produced a legendary dessert wine that was among the most expensive and sought-after wines in 18th and 19th century Europe",
        "facts": [
            "Constantia was established in 1685 by the Dutch governor of the Cape, Simon van der Stel, who selected the site for its cool maritime climate and south-facing mountain slopes.",
            "Groot Constantia, the original estate, was divided after Van der Stel's death into Groot Constantia, Klein Constantia, and Buitenverwachting.",
            "The Vin de Constance dessert wine, made from Muscat de Frontignan grapes, was one of the most sought-after and expensive wines in 18th-century Europe.",
            "Napoleon Bonaparte requested Constantia wine during his exile on Saint Helena, and it was reportedly one of the last wines he drank before his death.",
            "Jane Austen referenced Constantia wine in her novel Sense and Sensibility (1811), where it is recommended as a cure for a broken heart.",
            "Frederick the Great of Prussia was a devoted customer of Constantia wine and regularly ordered it for the Prussian court.",
            "Charles Dickens and Charles Baudelaire also referenced Constantia wine in their writings, testifying to its legendary reputation across Europe.",
            "Klein Constantia revived the historic dessert wine in 1986, releasing the first modern Vin de Constance from the 1986 vintage, using Muscat de Frontignan grapes from original vineyard sites.",
            "The original Constantia dessert wine production declined after the phylloxera epidemic reached the Cape in the 1880s and the vineyards were devastated.",
        ],
    },
    "cape_blend": {
        "name": "Cape Blend",
        "description": "Cape Blend is a uniquely South African red wine category that must contain between 20% and 70% Pinotage, blended with other varieties, creating a distinctive style that anchors South Africa's national grape in a quality blend",
        "facts": [
            "A Cape Blend must contain between 20% and 70% Pinotage to qualify for the designation.",
            "The Cape Blend concept was developed to showcase Pinotage as a blending component rather than solely as a single varietal wine.",
            "Common blending partners for Pinotage in Cape Blend include Cabernet Sauvignon, Merlot, Shiraz, and occasionally Cabernet Franc.",
            "The Cape Blend category was formalized through the Cape Winemakers Guild's efforts to establish a uniquely South African wine identity on the international stage.",
        ],
    },
    "wine_history": {
        "name": "South African Wine History",
        "description": "South Africa has over 360 years of continuous winemaking history, making it one of the oldest New World wine-producing countries",
        "facts": [
            "The first South African wine was produced on 2 February 1659 by the Dutch East India Company's Cape colony, making South Africa's wine industry over 360 years old.",
            "Jan van Riebeeck, the first commander of the Cape colony, recorded the first wine pressing in his diary on 2 February 1659.",
            "The KWV (Ko-operatieve Wijnbouwers Vereniging), established in 1918, controlled South African wine production through a quota system and minimum pricing until deregulation in the late 1990s.",
            "International sanctions during the apartheid era (1948-1994) isolated South African wine from global markets and limited quality improvements for decades.",
            "The post-apartheid era from 1994 onward saw a dramatic transformation of the South African wine industry, with access to international markets, new vine material, and modern winemaking techniques.",
            "South Africa ranks among the top 10 wine-producing countries in the world by volume, producing approximately 1 billion litres of wine annually.",
            "The Swartland Revolution, beginning around 2000, was a movement of independent winemakers — including Eben Sadie, Andrea Mullineux, and Adi Badenhorst — who pioneered old-vine, terroir-driven wines outside the traditional cooperative system.",
            "South Africa has approximately 93,000 hectares of vineyard under vine, with the majority in the Western Cape geographical unit.",
        ],
    },
    "sustainability": {
        "name": "Sustainability and Environmental Leadership",
        "description": "South Africa is a global leader in integrating environmental sustainability and biodiversity conservation into wine production",
        "facts": [
            "South Africa was the first wine-producing country to establish an industry-wide environmental sustainability certification program with the launch of IPW in 1998.",
            "The World Wide Fund for Nature (WWF) has been a key partner in South African wine industry conservation efforts through the BWI since 2004.",
            "The Sustainability in South African Wine (WIETA) certification addresses ethical labor practices alongside environmental sustainability in the wine industry.",
            "South Africa's SWSA (Sustainable Wine South Africa) brand integrates IPW environmental compliance, BWI biodiversity commitments, and WIETA ethical trade standards into a single certification framework.",
        ],
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════


def _get_source_id() -> str:
    """Register and return the WOSA source ID."""
    return ensure_source(
        name=SOURCE["name"],
        url=SOURCE["url"],
        source_type=SOURCE["source_type"],
        tier=SOURCE["tier"],
        language=SOURCE["language"],
    )


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
    """Build facts about South African wine regions (climate, soil, elevation, grapes)."""
    facts = []

    for region in REGION_DATABASE:
        name = region["name"]
        wo_unit = region["wo_unit"]
        entities = [{"type": "region", "name": name}]
        base_tags = ["south_africa", name.lower().replace(" ", "_").replace("'", "")]

        # WO unit classification
        facts.append(_make_fact(
            f"{name} is a Wine of Origin (WO) {wo_unit} in South Africa.",
            domain="wine_regions",
            source_id=source_id,
            subdomain="south_africa_classification",
            entities=entities,
            tags=base_tags + ["wo_system"],
        ))

        # Climate
        facts.append(_make_fact(
            f"The {name} wine {wo_unit} in South Africa has a {region['climate']} climate.",
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

        # Soil types
        if region.get("soil_types"):
            soil_list = ", ".join(region["soil_types"])
            facts.append(_make_fact(
                f"The predominant soil types in the {name} wine {wo_unit} of South Africa include {soil_list}.",
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
                f"Vineyards in the {name} wine {wo_unit} of South Africa are planted at elevations ranging from {region['elevation_range']}.",
                domain="viticulture",
                source_id=source_id,
                subdomain="terrain",
                entities=entities,
                tags=base_tags + ["elevation"],
            ))

        # Vineyard area
        if region.get("vineyard_area_ha"):
            facts.append(_make_fact(
                f"The {name} wine {wo_unit} in South Africa has approximately {region['vineyard_area_ha']:,} hectares of vineyard.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="statistics",
                entities=entities,
                confidence=0.95,
                tags=base_tags + ["vineyard_area", "statistics"],
            ))

        # Key grapes
        if region.get("key_grapes"):
            grapes_str = ", ".join(region["key_grapes"])
            grape_entities = entities + [{"type": "grape", "name": g} for g in region["key_grapes"]]
            facts.append(_make_fact(
                f"The principal grape varieties of the {name} wine {wo_unit} in South Africa include {grapes_str}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="regional_grapes",
                entities=grape_entities,
                tags=base_tags + ["grapes"],
            ))

        # Wine styles
        if region.get("wine_styles"):
            styles_str = ", ".join(region["wine_styles"])
            facts.append(_make_fact(
                f"The {name} wine {wo_unit} in South Africa is known for producing {styles_str}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="wine_styles",
                entities=entities,
                tags=base_tags + ["wine_styles"],
            ))

        # Wards
        if region.get("wards") and len(region["wards"]) > 0:
            wards_str = ", ".join(region["wards"])
            ward_entities = entities + [{"type": "ward", "name": w} for w in region["wards"]]
            facts.append(_make_fact(
                f"The {name} wine {wo_unit} in South Africa contains the wards {wards_str}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="geography",
                entities=ward_entities,
                tags=base_tags + ["wards", "geography"],
            ))

        # Notes (unique/historical information)
        if region.get("notes"):
            facts.append(_make_fact(
                f"{region['notes']}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="south_africa_history",
                entities=entities,
                tags=base_tags + ["history"],
            ))

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# FACT BUILDERS — Grape Varieties
# ═══════════════════════════════════════════════════════════════════════════════


def _build_grape_variety_facts(source_id: str) -> list[dict]:
    """Build facts about South African grape varieties."""
    facts = []

    for grape in GRAPE_VARIETY_DATABASE:
        name = grape["name"]
        color = grape["color"]
        entities = [{"type": "grape", "name": name}]
        base_tags = ["south_africa", name.lower().replace(" ", "_")]

        # Basic identity
        facts.append(_make_fact(
            f"{name} is a {color} grape variety widely grown in South Africa.",
            domain="grape_varieties",
            source_id=source_id,
            subdomain="south_africa_grapes",
            entities=entities,
            tags=base_tags + ["identity"],
        ))

        # Synonyms
        if grape.get("synonyms") and len(grape["synonyms"]) > 0:
            synonyms_str = ", ".join(grape["synonyms"])
            facts.append(_make_fact(
                f"{name} is also known as {synonyms_str} in South Africa.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="south_africa_grapes",
                entities=entities,
                tags=base_tags + ["synonyms"],
            ))

        # Plantings
        if grape.get("planted_ha"):
            facts.append(_make_fact(
                f"South Africa has approximately {grape['planted_ha']:,} hectares of {name} planted.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="statistics",
                entities=entities,
                confidence=0.95,
                tags=base_tags + ["plantings", "statistics"],
            ))

        # Share percentage
        if grape.get("share_pct"):
            facts.append(_make_fact(
                f"{name} accounts for approximately {grape['share_pct']}% of all vineyard plantings in South Africa.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="statistics",
                entities=entities,
                confidence=0.95,
                tags=base_tags + ["plantings", "statistics"],
            ))

        # Origin and introduction
        if grape.get("origin"):
            facts.append(_make_fact(
                f"{name}, originally from {grape['origin']}, is an important grape variety in South Africa.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="south_africa_grapes",
                entities=entities,
                tags=base_tags + ["origin"],
            ))

        if grape.get("introduction"):
            facts.append(_make_fact(
                f"{grape['introduction']}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="south_africa_history",
                entities=entities,
                tags=base_tags + ["history"],
            ))

        # Key regions
        if grape.get("key_regions"):
            regions_str = ", ".join(grape["key_regions"])
            region_entities = entities + [{"type": "region", "name": r} for r in grape["key_regions"]]
            facts.append(_make_fact(
                f"The key South African regions for {name} production include {regions_str}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="regional_grapes",
                entities=region_entities,
                tags=base_tags + ["regions"],
            ))

        # Wine styles
        if grape.get("wine_styles"):
            styles_str = ", ".join(grape["wine_styles"])
            facts.append(_make_fact(
                f"In South Africa, {name} is used to produce {styles_str}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="wine_styles",
                entities=entities,
                tags=base_tags + ["wine_styles"],
            ))

        # Viticulture notes
        if grape.get("viticulture_notes"):
            facts.append(_make_fact(
                f"{grape['viticulture_notes']}.",
                domain="viticulture",
                source_id=source_id,
                subdomain="south_africa_viticulture",
                entities=entities,
                tags=base_tags + ["viticulture"],
            ))

        # Significance
        if grape.get("significance"):
            facts.append(_make_fact(
                f"{grape['significance']}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="south_africa_grapes",
                entities=entities,
                tags=base_tags + ["significance"],
            ))

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# FACT BUILDERS — Classification System
# ═══════════════════════════════════════════════════════════════════════════════


def _build_classification_facts(source_id: str) -> list[dict]:
    """Build facts about South Africa's Wine of Origin system and certifications."""
    facts = []
    base_tags = ["south_africa", "classification"]

    # WO system overview
    wo = CLASSIFICATION_DATABASE["wo_system"]
    facts.append(_make_fact(
        f"{wo['description']}.",
        domain="wine_regions",
        source_id=source_id,
        subdomain="south_africa_classification",
        entities=[{"type": "classification", "name": "Wine of Origin"}],
        tags=base_tags + ["wo_system"],
    ))

    # WO levels
    for level in wo["levels"]:
        examples_str = ", ".join(level["examples"])
        facts.append(_make_fact(
            f"The {level['level']} is {level['description'].lower()} in South Africa's Wine of Origin system.",
            domain="wine_regions",
            source_id=source_id,
            subdomain="south_africa_classification",
            entities=[{"type": "classification", "name": level["level"]}],
            tags=base_tags + ["wo_system", level["level"].lower().replace(" ", "_")],
        ))

        facts.append(_make_fact(
            f"Examples of {level['level']} designations in South Africa's WO system include {examples_str}.",
            domain="wine_regions",
            source_id=source_id,
            subdomain="south_africa_classification",
            entities=[{"type": "classification", "name": level["level"]}],
            tags=base_tags + ["wo_system", level["level"].lower().replace(" ", "_")],
        ))

        if level.get("notes"):
            facts.append(_make_fact(
                f"{level['notes']}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="south_africa_classification",
                entities=[{"type": "classification", "name": level["level"]}],
                tags=base_tags + ["wo_system", level["level"].lower().replace(" ", "_")],
            ))

    # The four-level hierarchy as a single fact
    facts.append(_make_fact(
        "South Africa's Wine of Origin (WO) system has four levels of geographical classification from broadest to most specific: geographical unit, region, district, and ward.",
        domain="wine_regions",
        source_id=source_id,
        subdomain="south_africa_classification",
        entities=[{"type": "classification", "name": "Wine of Origin"}],
        tags=base_tags + ["wo_system", "hierarchy"],
    ))

    # Estate wine
    estate = CLASSIFICATION_DATABASE["estate_wine"]
    facts.append(_make_fact(
        f"{estate['description']}.",
        domain="wine_regions",
        source_id=source_id,
        subdomain="south_africa_classification",
        entities=[{"type": "classification", "name": "Estate Wine"}],
        tags=base_tags + ["estate"],
    ))

    facts.append(_make_fact(
        f"{estate['requirements']}.",
        domain="wine_regions",
        source_id=source_id,
        subdomain="south_africa_classification",
        entities=[{"type": "classification", "name": "Estate Wine"}],
        tags=base_tags + ["estate"],
    ))

    # Single vineyard
    sv = CLASSIFICATION_DATABASE["single_vineyard"]
    facts.append(_make_fact(
        f"{sv['description']}.",
        domain="wine_regions",
        source_id=source_id,
        subdomain="south_africa_classification",
        entities=[{"type": "classification", "name": "Single Vineyard"}],
        tags=base_tags + ["single_vineyard"],
    ))

    facts.append(_make_fact(
        f"{sv['requirements']}.",
        domain="wine_regions",
        source_id=source_id,
        subdomain="south_africa_classification",
        entities=[{"type": "classification", "name": "Single Vineyard"}],
        tags=base_tags + ["single_vineyard"],
    ))

    # Integrity seal
    seal = CLASSIFICATION_DATABASE["integrity_seal"]
    facts.append(_make_fact(
        f"{seal['description']}.",
        domain="wine_regions",
        source_id=source_id,
        subdomain="south_africa_classification",
        entities=[{"type": "certification", "name": "Integrity & Sustainability Seal"}],
        tags=base_tags + ["seal", "sustainability"],
    ))

    facts.append(_make_fact(
        f"{seal['details']}.",
        domain="wine_regions",
        source_id=source_id,
        subdomain="south_africa_classification",
        entities=[{"type": "certification", "name": "Integrity & Sustainability Seal"}],
        tags=base_tags + ["seal", "sustainability"],
    ))

    # IPW
    ipw = CLASSIFICATION_DATABASE["ipw"]
    facts.append(_make_fact(
        f"{ipw['description']}.",
        domain="wine_regions",
        source_id=source_id,
        subdomain="south_africa_sustainability",
        entities=[{"type": "certification", "name": "IPW"}],
        tags=base_tags + ["ipw", "sustainability"],
    ))

    facts.append(_make_fact(
        f"{ipw['details']}.",
        domain="wine_regions",
        source_id=source_id,
        subdomain="south_africa_sustainability",
        entities=[{"type": "certification", "name": "IPW"}],
        tags=base_tags + ["ipw", "sustainability"],
    ))

    # Old Vine Project
    ovp = CLASSIFICATION_DATABASE["old_vine_project"]
    facts.append(_make_fact(
        f"{ovp['description']}.",
        domain="viticulture",
        source_id=source_id,
        subdomain="south_africa_viticulture",
        entities=[{"type": "certification", "name": "Old Vine Project"}],
        tags=base_tags + ["old_vine_project"],
    ))

    facts.append(_make_fact(
        f"{ovp['details']}.",
        domain="viticulture",
        source_id=source_id,
        subdomain="south_africa_viticulture",
        entities=[{"type": "certification", "name": "Old Vine Project"}],
        tags=base_tags + ["old_vine_project"],
    ))

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# FACT BUILDERS — Unique Features
# ═══════════════════════════════════════════════════════════════════════════════


def _build_unique_facts(source_id: str) -> list[dict]:
    """Build facts about South Africa's unique wine features (BWI, Cap Classique, Constantia, Cape Blend, history, sustainability)."""
    facts = []
    base_tags = ["south_africa"]

    for key, section in UNIQUE_DATABASE.items():
        section_name = section["name"]
        section_tags = base_tags + [key]

        # Section description as a fact
        entities = [{"type": "concept", "name": section_name}]

        # Determine appropriate domain
        if key in ("bwi", "sustainability"):
            domain = "viticulture"
            subdomain = "south_africa_sustainability"
        elif key == "wine_history":
            domain = "wine_business"
            subdomain = "south_africa_history"
        elif key == "cap_classique":
            domain = "winemaking"
            subdomain = "south_africa_sparkling"
        elif key == "cape_blend":
            domain = "winemaking"
            subdomain = "south_africa_blends"
        elif key == "constantia_history":
            domain = "wine_regions"
            subdomain = "south_africa_history"
        else:
            domain = "wine_regions"
            subdomain = "south_africa"

        facts.append(_make_fact(
            f"{section['description']}.",
            domain=domain,
            source_id=source_id,
            subdomain=subdomain,
            entities=entities,
            tags=section_tags + ["overview"],
        ))

        # Individual facts from the section
        for fact_text in section.get("facts", []):
            # Ensure fact ends with period
            text = fact_text.rstrip(".")
            text = f"{text}."

            facts.append(_make_fact(
                text,
                domain=domain,
                source_id=source_id,
                subdomain=subdomain,
                entities=entities,
                tags=section_tags,
            ))

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# ORCHESTRATION
# ═══════════════════════════════════════════════════════════════════════════════


def _build_all_facts(source_id: str, data_type: str = None) -> list[dict]:
    """Build all facts, optionally filtered by type."""
    all_facts = []

    builders = {
        "region": _build_regional_facts,
        "grape": _build_grape_variety_facts,
        "classification": _build_classification_facts,
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
        click.echo(f"\n[DRY RUN] Would insert {len(facts)} facts from South African Wine Reference Database")

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

    logger.info(f"Inserted {inserted} new facts from South African Wine Reference Database (duplicates skipped)")
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
        "Grape Varieties": _build_grape_variety_facts,
        "Classification": _build_classification_facts,
        "Unique Features": _build_unique_facts,
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
    type=click.Choice(["region", "grape", "classification", "unique"]),
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
    """OenoBench South African Wine Enrichment Scraper — Regions, grapes, classification, and unique features."""
    logger.add("data/logs/south_africa_enrichment_{time}.log", rotation="10 MB")

    if list_sources:
        click.echo("\nAvailable data categories:")
        click.echo(f"  {'region':18s} — {len(REGION_DATABASE)} South African wine regions/districts/wards (climate, soil, elevation)")
        click.echo(f"  {'grape':18s} — {len(GRAPE_VARIETY_DATABASE)} grape variety profiles")
        click.echo(f"  {'classification':18s} — Wine of Origin system, estate/single vineyard, seals, certifications")
        click.echo(f"  {'unique':18s} — Biodiversity, Cap Classique, Constantia history, Cape Blend, wine history, sustainability")
        click.echo(f"\nKnowledge base coverage:")
        click.echo(f"  Regions/districts/wards: {len(REGION_DATABASE)}")
        click.echo(f"  Grape varieties:         {len(GRAPE_VARIETY_DATABASE)}")
        click.echo(f"  Classification entries:   {len(CLASSIFICATION_DATABASE)}")
        click.echo(f"  Unique feature sections:  {len(UNIQUE_DATABASE)}")
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
