"""
OenoBench — Spanish Wine Enrichment Scraper

Enriches Spain's coverage (currently ~801 basic appellation facts in europe.py)
with terroir depth, grape profiles, classification details, and unique wine styles.

Focus areas: DO/DOCa terroir (climate, soil, elevation, subzones), grape variety
profiles, Spanish classification/aging system, Sherry styles & solera, and Cava
sparkling wine rules.

Usage:
    python -m src.scrapers.spain_enrichment --all
    python -m src.scrapers.spain_enrichment --type appellation
    python -m src.scrapers.spain_enrichment --type grape
    python -m src.scrapers.spain_enrichment --type classification
    python -m src.scrapers.spain_enrichment --type sherry
    python -m src.scrapers.spain_enrichment --type cava
    python -m src.scrapers.spain_enrichment --dry-run
    python -m src.scrapers.spain_enrichment --validate
    python -m src.scrapers.spain_enrichment --test-run
    python -m src.scrapers.spain_enrichment --list
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
    "name": "Spanish Wine Reference Database",
    "url": "https://www.winesfromspain.com",
    "source_type": "reference",
    "tier": "tier_2_authoritative",
    "language": "en",
}


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Appellation Database
# ═══════════════════════════════════════════════════════════════════════════════

APPELLATION_DATABASE = [
    {
        "name": "Rioja",
        "region": "La Rioja / Basque Country / Navarra",
        "classification": "DOCa",
        "climate": "continental with Atlantic and Mediterranean influences",
        "soil_types": ["chalky clay", "clay-ferruginous", "alluvial", "iron-rich clay"],
        "soil_details": "Rioja Alavesa features chalky clay soils producing elegant, aromatic wines; Rioja Alta has clay-ferruginous and alluvial soils at altitude giving structured wines; Rioja Oriental (formerly Rioja Baja) has alluvial and iron-rich clay soils in a warmer climate producing full-bodied wines",
        "elevation_range": "300-800m",
        "vineyard_area_ha": 66000,
        "key_red_grapes": ["Tempranillo", "Garnacha", "Graciano", "Mazuelo"],
        "key_white_grapes": ["Viura", "Malvasía", "Garnacha Blanca"],
        "wine_styles": ["red (tinto)", "white (blanco)", "rosé (rosado)"],
        "subzones": [
            {"name": "Rioja Alavesa", "notes": "Chalky clay soils, cooler climate from Cantabrian Mountains shelter, produces the most elegant and aromatic Tempranillo-based wines"},
            {"name": "Rioja Alta", "notes": "Clay-ferruginous and alluvial soils at higher altitude, cooler Atlantic influence, wines are structured and age-worthy"},
            {"name": "Rioja Oriental", "notes": "Formerly Rioja Baja, warmer Mediterranean climate, alluvial and iron-rich clay soils, Garnacha thrives here producing full-bodied wines"},
        ],
        "notes": "Spain's first DOCa (1991). Pioneered the Crianza/Reserva/Gran Reserva aging system. The 2017 single-vineyard (Viñedo Singular) classification allows estate-bottled wines.",
    },
    {
        "name": "Ribera del Duero",
        "region": "Castilla y León",
        "classification": "DO",
        "climate": "extreme continental with large diurnal temperature variation",
        "soil_types": ["limestone", "chalk", "clay", "sandy alluvial"],
        "soil_details": "The high Meseta plateau features limestone and chalk soils at elevation, with sandy alluvial deposits along the Duero River; calcareous clay dominates the best vineyard sites",
        "elevation_range": "700-1000m",
        "vineyard_area_ha": 23000,
        "key_red_grapes": ["Tinto Fino (Tempranillo)"],
        "key_white_grapes": ["Albillo Mayor"],
        "wine_styles": ["red (tinto)", "rosé (rosado)"],
        "subzones": [],
        "notes": "Tinto Fino is the local name for Tempranillo. Extreme diurnal variation (up to 20°C) produces wines with intense color, concentration, and acidity. Vega Sicilia established the region's fine-wine reputation in the 19th century.",
    },
    {
        "name": "Priorat",
        "region": "Catalonia",
        "classification": "DOCa",
        "climate": "Mediterranean with continental influence",
        "soil_types": ["llicorella (slate)", "quartzite"],
        "soil_details": "The steep terraced hillsides are dominated by llicorella, a distinctive local slate and quartzite soil that forces vine roots deep for water and reflects heat, concentrating flavors in the grapes",
        "elevation_range": "100-700m",
        "vineyard_area_ha": 2000,
        "key_red_grapes": ["Garnacha", "Cariñena (Carignan)", "Cabernet Sauvignon", "Syrah"],
        "key_white_grapes": ["Garnacha Blanca", "Macabeo"],
        "wine_styles": ["red (tinto)", "white (blanco)"],
        "subzones": [],
        "notes": "Spain's second DOCa (2009). Old-vine Garnacha and Cariñena on llicorella produce some of Spain's most concentrated and mineral-driven wines. The Priorat revival began in the late 1980s led by René Barbier and the 'Clos' group.",
    },
    {
        "name": "Rías Baixas",
        "region": "Galicia",
        "classification": "DO",
        "climate": "Atlantic maritime with high rainfall",
        "soil_types": ["granite", "sandy", "alluvial"],
        "soil_details": "Decomposed granite soils dominate, providing excellent drainage in a high-rainfall environment; granite sand and alluvial deposits along river valleys contribute mineral character to the wines",
        "elevation_range": "0-300m",
        "vineyard_area_ha": 4000,
        "key_red_grapes": [],
        "key_white_grapes": ["Albariño", "Treixadura", "Loureira", "Caiño Blanco", "Godello"],
        "wine_styles": ["white (blanco)"],
        "subzones": [
            {"name": "Val do Salnés", "notes": "The historic heartland and largest subzone, closest to the Atlantic coast, producing the most aromatic and mineral Albariño wines"},
            {"name": "Condado do Tea", "notes": "Warmer inland area along the Miño River, produces rounder Albariño and blends with Treixadura"},
            {"name": "O Rosal", "notes": "Southern coastal subzone near the Portuguese border, granite soils, blends of Albariño with Loureira and Caiño Blanco"},
            {"name": "Soutomaior", "notes": "Small inland subzone, granite soils, relatively recent addition to the DO"},
            {"name": "Ribeira do Ulla", "notes": "Northernmost subzone, coolest climate, highest acidity in wines"},
        ],
        "notes": "Spain's premier white wine region. Albariño is traditionally trained on pergolas (parras) to protect from humidity and fungal disease in the wet Atlantic climate.",
    },
    {
        "name": "Jerez-Xérès-Sherry",
        "region": "Andalusia",
        "classification": "DO",
        "climate": "hot Mediterranean with Atlantic influence",
        "soil_types": ["albariza (chalk)", "barro (clay)", "arena (sand)"],
        "soil_details": "Albariza is the prized white chalky soil composed of limestone, clay, and silica that retains moisture through the hot dry summer and reflects sunlight; barro (clay) and arena (sandy) soils produce lesser-quality wines",
        "elevation_range": "0-150m",
        "vineyard_area_ha": 7000,
        "key_red_grapes": [],
        "key_white_grapes": ["Palomino Fino", "Pedro Ximénez", "Moscatel de Alejandría"],
        "wine_styles": ["Fino", "Manzanilla", "Amontillado", "Oloroso", "Palo Cortado", "Pedro Ximénez", "Cream"],
        "subzones": [],
        "notes": "The Sherry Triangle encompasses Jerez de la Frontera, El Puerto de Santa María, and Sanlúcar de Barrameda. Wines must be aged and shipped from these towns.",
    },
    {
        "name": "Penedès",
        "region": "Catalonia",
        "classification": "DO",
        "climate": "Mediterranean with continental influence at higher altitude",
        "soil_types": ["limestone", "clay", "alluvial"],
        "soil_details": "Three altitude zones: Baix Penedès (coastal, warm, calcareous clay), Mitjà Penedès (mid-level, limestone and clay, Cava heartland), and Alt Penedès (highest, cooler, limestone and chalk)",
        "elevation_range": "50-800m",
        "vineyard_area_ha": 26000,
        "key_red_grapes": ["Garnacha", "Monastrell", "Ull de Llebre (Tempranillo)"],
        "key_white_grapes": ["Macabeo", "Xarel·lo", "Parellada", "Chardonnay"],
        "wine_styles": ["white (blanco)", "red (tinto)", "rosé (rosado)", "sparkling (Cava)"],
        "subzones": [],
        "notes": "The heartland of Cava production, centered around Sant Sadurní d'Anoia. Also produces still wines from both indigenous and international varieties. Miguel Torres pioneered modern winemaking here in the 1960s-70s.",
    },
    {
        "name": "Rueda",
        "region": "Castilla y León",
        "classification": "DO",
        "climate": "continental with extreme temperatures",
        "soil_types": ["gravel", "limestone", "sandy", "alluvial"],
        "soil_details": "High plateau soils with gravel and limestone over clay subsoil provide good drainage; sandy alluvial soils along the Duero River; stony soils help retain daytime heat",
        "elevation_range": "700-800m",
        "vineyard_area_ha": 17000,
        "key_red_grapes": [],
        "key_white_grapes": ["Verdejo", "Viura", "Sauvignon Blanc"],
        "wine_styles": ["white (blanco)"],
        "subzones": [],
        "notes": "Spain's premier Verdejo region. Old-vine Verdejo (pre-phylloxera) on sandy soils survived ungrafted. High-altitude continental climate preserves acidity. Rueda Verdejo must contain at least 85% Verdejo.",
    },
    {
        "name": "Toro",
        "region": "Castilla y León",
        "classification": "DO",
        "climate": "extreme continental with very hot summers and cold winters",
        "soil_types": ["sandy", "clay", "alluvial"],
        "soil_details": "Sandy soils over clay subsoil dominate, with many old-vine plots on ungrafted rootstocks that survived phylloxera due to the sandy soils; alluvial deposits along the Duero River",
        "elevation_range": "650-750m",
        "vineyard_area_ha": 5500,
        "key_red_grapes": ["Tinta de Toro (Tempranillo)"],
        "key_white_grapes": ["Malvasía"],
        "wine_styles": ["red (tinto)", "rosé (rosado)"],
        "subzones": [],
        "notes": "Tinta de Toro is a thick-skinned local clone of Tempranillo adapted to extreme heat. Many vines are ungrafted and over 100 years old, having survived phylloxera in the sandy soils. Wines are characteristically powerful and deeply colored.",
    },
    {
        "name": "Bierzo",
        "region": "Castilla y León",
        "classification": "DO",
        "climate": "Atlantic-continental transitional",
        "soil_types": ["slate", "quartzite", "clay", "alluvial"],
        "soil_details": "Steep hillside vineyards on slate and quartzite soils in the Sil and Cúa river valleys; alluvial clay on lower slopes and valley floors; the best sites are on decomposed slate at altitude",
        "elevation_range": "450-800m",
        "vineyard_area_ha": 3000,
        "key_red_grapes": ["Mencía"],
        "key_white_grapes": ["Godello", "Doña Blanca"],
        "wine_styles": ["red (tinto)", "white (blanco)"],
        "subzones": [],
        "notes": "Mencía on slate soils produces aromatic, medium-bodied reds often compared to Loire Cabernet Franc or Burgundy Pinot Noir. The Bierzo quality pyramid: Bierzo (regional), Bierzo Villa (village), Bierzo Cru (single vineyard), Gran Cru (top sites).",
    },
    {
        "name": "Jumilla",
        "region": "Murcia",
        "classification": "DO",
        "climate": "semi-arid continental with very low rainfall",
        "soil_types": ["limestone", "sandy", "clay-limestone"],
        "soil_details": "Calcareous and sandy soils at moderate altitude; limestone bedrock provides good drainage in the arid climate; many old bush-trained Monastrell vines on poor soils",
        "elevation_range": "400-800m",
        "vineyard_area_ha": 23000,
        "key_red_grapes": ["Monastrell (Mourvèdre)"],
        "key_white_grapes": ["Airén", "Macabeo"],
        "wine_styles": ["red (tinto)", "rosé (rosado)"],
        "subzones": [],
        "notes": "Old-vine bush-trained (en vaso) Monastrell is the region's hallmark. Many vines are ungrafted due to sandy phylloxera-resistant soils. Very low yields from dry-farmed vineyards produce concentrated wines.",
    },
    {
        "name": "Navarra",
        "region": "Navarra",
        "classification": "DO",
        "climate": "transitional from Atlantic in the north to Mediterranean in the south",
        "soil_types": ["limestone", "clay", "gravel", "alluvial"],
        "soil_details": "Diverse soils reflecting the five subzones: chalky limestone in the north, gravel and clay in central areas, alluvial soils in the Ebro valley to the south",
        "elevation_range": "250-600m",
        "vineyard_area_ha": 11000,
        "key_red_grapes": ["Garnacha", "Tempranillo", "Cabernet Sauvignon", "Merlot"],
        "key_white_grapes": ["Chardonnay", "Viura"],
        "wine_styles": ["rosé (rosado)", "red (tinto)", "white (blanco)"],
        "subzones": [
            {"name": "Tierra Estella", "notes": "Northwestern subzone, Atlantic influence, cooler climate, higher altitude vineyards"},
            {"name": "Valdizarbe", "notes": "Central zone, transitional climate, clay-limestone soils"},
            {"name": "Baja Montaña", "notes": "Northeastern zone near the Pyrenees foothills, continental-Mediterranean climate"},
            {"name": "Ribera Alta", "notes": "Central Ebro valley, alluvial soils, warm climate ideal for Garnacha"},
            {"name": "Ribera Baja", "notes": "Southern subzone, warmest and driest, Mediterranean climate, Moscatel and Garnacha"},
        ],
        "notes": "Historically renowned for rosado (rosé) made from Garnacha. Navarra was the first Spanish region to widely adopt international varieties. The five subzones reflect a climate gradient from Atlantic north to Mediterranean south.",
    },
    {
        "name": "Somontano",
        "region": "Aragon",
        "classification": "DO",
        "climate": "continental with Pyrenean influence",
        "soil_types": ["limestone", "sandstone", "clay"],
        "soil_details": "Calcareous sandstone and limestone soils on the Pyrenees foothills; clay-limestone at moderate elevations; well-drained soils with good mineral content",
        "elevation_range": "350-650m",
        "vineyard_area_ha": 4000,
        "key_red_grapes": ["Moristel", "Parraleta", "Tempranillo", "Cabernet Sauvignon"],
        "key_white_grapes": ["Chardonnay", "Gewürztraminer", "Macabeo"],
        "wine_styles": ["red (tinto)", "white (blanco)", "rosé (rosado)"],
        "subzones": [],
        "notes": "Name means 'at the foot of the mountain' (the Pyrenees). Successfully blends indigenous varieties (Moristel, Parraleta) with international grapes. Cooperative-driven modernization in the 1980s-90s.",
    },
    {
        "name": "Campo de Borja",
        "region": "Aragon",
        "classification": "DO",
        "climate": "continental with cierzo wind influence",
        "soil_types": ["slate", "limestone", "clay", "gravel"],
        "soil_details": "Higher-altitude sites on slate and limestone produce the most concentrated Garnacha; lower areas have clay and gravel soils; the cierzo wind from the northwest helps prevent disease",
        "elevation_range": "350-700m",
        "vineyard_area_ha": 6000,
        "key_red_grapes": ["Garnacha"],
        "key_white_grapes": ["Macabeo"],
        "wine_styles": ["red (tinto)", "rosé (rosado)"],
        "subzones": [],
        "notes": "Known as the 'Empire of Garnacha' for its extensive old-vine Garnacha plantings. Many vines are 30-50+ years old, bush-trained. The cierzo wind (cold, dry northwesterly) is a defining climatic feature.",
    },
    {
        "name": "Calatayud",
        "region": "Aragon",
        "classification": "DO",
        "climate": "continental with significant altitude influence",
        "soil_types": ["slate", "limestone", "clay-limestone"],
        "soil_details": "Hillside vineyards on slate and limestone soils at high altitude; clay-limestone on lower slopes; poor, well-drained soils that stress vines for concentrated fruit",
        "elevation_range": "500-1000m",
        "vineyard_area_ha": 3000,
        "key_red_grapes": ["Garnacha"],
        "key_white_grapes": ["Macabeo", "Viura"],
        "wine_styles": ["red (tinto)", "rosé (rosado)"],
        "subzones": [],
        "notes": "Among Spain's highest vineyards. Old-vine Garnacha at extreme altitude produces wines with fresh acidity, aromatic intensity, and moderate alcohol. Roman-era wine heritage dating to Augusta Bilbilis.",
    },
    {
        "name": "Montsant",
        "region": "Catalonia",
        "classification": "DO",
        "climate": "Mediterranean with continental influence",
        "soil_types": ["llicorella (slate)", "limestone", "clay", "gravel"],
        "soil_details": "The horseshoe-shaped DO surrounds Priorat, sharing some llicorella soils on the border; limestone and clay dominate the outer areas; diverse terroir from varied geology",
        "elevation_range": "200-700m",
        "vineyard_area_ha": 1800,
        "key_red_grapes": ["Garnacha", "Cariñena", "Syrah", "Tempranillo"],
        "key_white_grapes": ["Garnacha Blanca", "Macabeo"],
        "wine_styles": ["red (tinto)", "white (blanco)", "rosé (rosado)"],
        "subzones": [],
        "notes": "Geographically surrounds Priorat in a horseshoe shape. Offers similar Mediterranean character at more accessible prices. Upgraded from subzona to full DO in 2001.",
    },
    {
        "name": "Terra Alta",
        "region": "Catalonia",
        "classification": "DO",
        "climate": "Mediterranean continental",
        "soil_types": ["limestone", "clay-limestone", "sandy"],
        "soil_details": "Calcareous limestone soils with clay on hillsides; well-drained stony soils at moderate altitude; the name means 'high land' reflecting its elevated plateau position",
        "elevation_range": "350-550m",
        "vineyard_area_ha": 5800,
        "key_red_grapes": ["Garnacha", "Cariñena", "Syrah"],
        "key_white_grapes": ["Garnacha Blanca"],
        "wine_styles": ["white (blanco)", "red (tinto)"],
        "subzones": [],
        "notes": "The heartland of Garnacha Blanca in Spain, with more plantings of this white grape than anywhere else. Terra Alta Garnacha Blanca must contain at least 85% of the variety.",
    },
    {
        "name": "Valdepeñas",
        "region": "Castilla-La Mancha",
        "classification": "DO",
        "climate": "hot continental with very dry summers",
        "soil_types": ["chalky clay", "limestone", "sandy"],
        "soil_details": "Chalky white clay soils (similar to Jerez albariza) over limestone bedrock; sandy soils on lower areas; the white soils reflect heat and retain moisture",
        "elevation_range": "700-800m",
        "vineyard_area_ha": 23000,
        "key_red_grapes": ["Cencibel (Tempranillo)"],
        "key_white_grapes": ["Airén"],
        "wine_styles": ["red (tinto)", "white (blanco)"],
        "subzones": [],
        "notes": "Cencibel is the local name for Tempranillo. Located within the larger La Mancha region but with its own distinct DO since 1932, one of Spain's oldest. Known historically for value-driven wines.",
    },
    {
        "name": "La Mancha",
        "region": "Castilla-La Mancha",
        "classification": "DO",
        "climate": "extreme continental with very hot summers and cold winters",
        "soil_types": ["chalky clay", "limestone", "sandy", "alluvial"],
        "soil_details": "Flat central plateau with chalky clay and limestone soils; poor soils with limited water retention forcing deep root systems; some sandy areas near rivers",
        "elevation_range": "600-700m",
        "vineyard_area_ha": 160000,
        "key_red_grapes": ["Cencibel (Tempranillo)", "Garnacha"],
        "key_white_grapes": ["Airén"],
        "wine_styles": ["white (blanco)", "red (tinto)", "rosé (rosado)"],
        "subzones": [],
        "notes": "The world's largest single delimited wine region by vineyard area. Airén is the dominant grape and was historically the world's most planted variety. Modernization since the 1990s has shifted production toward quality red wines.",
    },
    {
        "name": "Getariako Txakolina",
        "region": "Basque Country",
        "classification": "DO",
        "climate": "cool Atlantic maritime with high rainfall",
        "soil_types": ["clay", "sandstone", "limestone"],
        "soil_details": "Clay and sandstone soils on steep terraced hillsides near the Cantabrian coast; well-drained but retaining enough moisture from the abundant rainfall",
        "elevation_range": "0-300m",
        "vineyard_area_ha": 400,
        "key_red_grapes": ["Hondarrabi Beltza"],
        "key_white_grapes": ["Hondarrabi Zuri"],
        "wine_styles": ["white (blanco)", "rosé (rosado)"],
        "subzones": [],
        "notes": "Txakoli (also spelled Chacolí) is a crisp, slightly spritzy white wine traditionally poured from a height. The Basque Country has three Txakoli DOs: Getariako Txakolina, Bizkaiko Txakolina, and Arabako Txakolina.",
    },
    {
        "name": "Cava",
        "region": "Multi-regional (primarily Catalonia)",
        "classification": "DO",
        "climate": "Mediterranean (Penedès heartland)",
        "soil_types": ["limestone", "clay", "chalk"],
        "soil_details": "The Penedès heartland around Sant Sadurní d'Anoia features limestone and clay soils; the DO extends across multiple regions but 95% of production comes from Catalonia",
        "elevation_range": "150-500m",
        "vineyard_area_ha": 33000,
        "key_red_grapes": ["Garnacha", "Monastrell", "Pinot Noir", "Trepat"],
        "key_white_grapes": ["Macabeo", "Xarel·lo", "Parellada", "Chardonnay"],
        "wine_styles": ["sparkling (traditional method)"],
        "subzones": [],
        "notes": "Spain's traditional method sparkling wine. 95% produced in Penedès, centered on Sant Sadurní d'Anoia. The 2020 reform introduced quality tiers: Cava de Guarda, Cava de Guarda Superior (Reserva/Gran Reserva), and Cava de Paraje Calificado.",
    },
    {
        "name": "Mallorca",
        "region": "Balearic Islands",
        "classification": "DO (Binissalem / Pla i Llevant)",
        "climate": "Mediterranean with maritime influence",
        "soil_types": ["limestone", "clay-limestone", "sandy"],
        "soil_details": "Calcareous clay and limestone soils typical of the Mediterranean island; Binissalem in the Tramuntana foothills has more clay-limestone; Pla i Llevant on the eastern plain has lighter, sandier soils",
        "elevation_range": "50-400m",
        "vineyard_area_ha": 2500,
        "key_red_grapes": ["Manto Negro", "Callet", "Fogoneu"],
        "key_white_grapes": ["Prensal Blanc (Moll)", "Giró Ros"],
        "wine_styles": ["red (tinto)", "white (blanco)", "rosé (rosado)"],
        "subzones": [],
        "notes": "Two DOs on the island: Binissalem (since 1990, must use minimum 50% Manto Negro for reds) and Pla i Llevant (since 1999, more permissive). Manto Negro and Callet are indigenous Mallorcan varieties.",
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Grape Variety Database
# ═══════════════════════════════════════════════════════════════════════════════

GRAPE_VARIETY_DATABASE = [
    # ── Red varieties ──
    {
        "name": "Tempranillo",
        "color": "red",
        "origin": "Spain (Rioja / Ribera del Duero)",
        "synonyms": ["Tinto Fino", "Tinto del País", "Cencibel", "Tinta de Toro", "Ull de Llebre", "Tinta Roriz (Portugal)", "Aragonez (Portugal)"],
        "characteristics": "Thick-skinned, early-ripening (the name derives from 'temprano', meaning early), produces deeply colored wines with flavors of plum, cherry, tobacco, leather, and vanilla; excellent affinity with oak aging",
        "key_regions": ["Rioja", "Ribera del Duero", "Toro", "Valdepeñas", "La Mancha", "Navarra"],
        "vineyard_area_ha": 88000,
    },
    {
        "name": "Garnacha Tinta",
        "color": "red",
        "origin": "Spain (Aragon)",
        "synonyms": ["Grenache (France)", "Cannonau (Sardinia)", "Garnaxa"],
        "characteristics": "Late-ripening, drought-resistant, high sugar potential; produces wines with red fruit, spice, and herbal notes; naturally high alcohol; old vines yield concentrated wines; oxidation-prone, often blended",
        "key_regions": ["Priorat", "Campo de Borja", "Calatayud", "Navarra", "Rioja", "Montsant", "Terra Alta"],
        "vineyard_area_ha": 55000,
    },
    {
        "name": "Monastrell",
        "color": "red",
        "origin": "Spain (Levante region)",
        "synonyms": ["Mourvèdre (France)", "Mataro (Australia/California)"],
        "characteristics": "Late-ripening, drought-tolerant, thrives in hot dry climates; produces deeply colored tannic wines with blackberry, plum, and earthy notes; often bush-trained (en vaso) in arid conditions",
        "key_regions": ["Jumilla", "Yecla", "Alicante", "Bullas"],
        "vineyard_area_ha": 40000,
    },
    {
        "name": "Mencía",
        "color": "red",
        "origin": "Spain (northwest Iberia)",
        "synonyms": ["Jaén (Portugal)"],
        "characteristics": "Medium-bodied, aromatic, with floral and red fruit notes reminiscent of Pinot Noir; moderate tannins, good acidity; expresses terroir distinctly on slate soils; revived from near-extinction in the 1990s",
        "key_regions": ["Bierzo", "Ribeira Sacra", "Valdeorras", "Monterrei"],
        "vineyard_area_ha": 9000,
    },
    {
        "name": "Bobal",
        "color": "red",
        "origin": "Spain (Utiel-Requena)",
        "synonyms": [],
        "characteristics": "Thick-skinned, drought-resistant, high yields; historically used for bulk wine and blending but now producing quality single-varietal wines from old vines; deep color, moderate tannins, fresh acidity",
        "key_regions": ["Utiel-Requena", "Manchuela"],
        "vineyard_area_ha": 37000,
    },
    {
        "name": "Graciano",
        "color": "red",
        "origin": "Spain (Rioja)",
        "synonyms": ["Morrastel (France)"],
        "characteristics": "Small berries with thick skins; highly aromatic with intense color and high acidity; low-yielding and difficult to grow; valued as a blending partner in Rioja for its color, aroma, and aging potential",
        "key_regions": ["Rioja", "Navarra"],
        "vineyard_area_ha": 2000,
    },
    {
        "name": "Mazuelo",
        "color": "red",
        "origin": "Spain (Aragon)",
        "synonyms": ["Cariñena", "Carignan (France)", "Carignane"],
        "characteristics": "Late-ripening, vigorous, high-yielding; produces wines with high tannins, color, and acidity; prone to oidium; old vines in Priorat and Montsant produce outstanding wines; name Cariñena derives from the Aragonese town",
        "key_regions": ["Priorat", "Montsant", "Penedès", "Terra Alta", "Rioja"],
        "vineyard_area_ha": 4000,
    },
    {
        "name": "Callet",
        "color": "red",
        "origin": "Mallorca, Balearic Islands",
        "synonyms": [],
        "characteristics": "Indigenous Mallorcan variety; light to medium-bodied with bright fruit, floral aromas, and moderate tannins; nearly extinct by the late 20th century but revived by local producers",
        "key_regions": ["Mallorca (Pla i Llevant)"],
        "vineyard_area_ha": 200,
    },
    {
        "name": "Prieto Picudo",
        "color": "red",
        "origin": "Spain (León)",
        "synonyms": [],
        "characteristics": "Indigenous to the province of León; thick-skinned with distinctive pointed berries; produces deeply colored wines with dark fruit and spice; traditionally used for rosado but increasingly for quality reds",
        "key_regions": ["Tierra de León"],
        "vineyard_area_ha": 1500,
    },
    # ── White varieties ──
    {
        "name": "Airén",
        "color": "white",
        "origin": "Spain (Castilla-La Mancha)",
        "synonyms": ["Lairén", "Manchega"],
        "characteristics": "Vigorous, drought-resistant, high-yielding; neutral flavor profile; historically the world's most planted grape variety due to extensive La Mancha plantings; traditionally used for brandy distillation and bulk wine",
        "key_regions": ["La Mancha", "Valdepeñas"],
        "vineyard_area_ha": 218000,
    },
    {
        "name": "Albariño",
        "color": "white",
        "origin": "Spain (Galicia) / Portugal (Vinho Verde)",
        "synonyms": ["Alvarinho (Portugal)"],
        "characteristics": "Thick-skinned, small berries; aromatic with peach, apricot, citrus, and saline/mineral notes; naturally high acidity; thrives in the wet Atlantic climate of Galicia; resistant to fungal disease",
        "key_regions": ["Rías Baixas"],
        "vineyard_area_ha": 6000,
    },
    {
        "name": "Verdejo",
        "color": "white",
        "origin": "Spain (Rueda)",
        "synonyms": [],
        "characteristics": "Aromatic with herbal, fennel, citrus, and stone fruit notes; naturally high acidity; slightly bitter finish characteristic of the variety; old vines on sandy soils produce the most complex wines",
        "key_regions": ["Rueda"],
        "vineyard_area_ha": 12000,
    },
    {
        "name": "Godello",
        "color": "white",
        "origin": "Spain (Galicia / Bierzo)",
        "synonyms": ["Gouveio (Portugal)"],
        "characteristics": "Full-bodied white with stone fruit, citrus, and mineral character; good acidity and aging potential; nearly extinct by the 1970s but revived by dedicated growers in Valdeorras and Bierzo",
        "key_regions": ["Valdeorras", "Bierzo", "Ribeira Sacra"],
        "vineyard_area_ha": 1500,
    },
    {
        "name": "Viura",
        "color": "white",
        "origin": "Spain (Rioja)",
        "synonyms": ["Macabeo", "Macabeu"],
        "characteristics": "Vigorous, productive; neutral to floral flavor profile; the main white grape of Rioja (as Viura) and Cava (as Macabeo); versatile, producing both fresh unoaked and rich barrel-fermented styles",
        "key_regions": ["Rioja", "Penedès (Cava)", "Navarra", "Somontano"],
        "vineyard_area_ha": 35000,
    },
    {
        "name": "Palomino Fino",
        "color": "white",
        "origin": "Spain (Andalusia)",
        "synonyms": ["Listán (Canary Islands)"],
        "characteristics": "Neutral, low-acid table grape that is ideal for Sherry production; the lack of strong varietal character allows the biological and oxidative aging processes of Sherry to dominate the flavor profile",
        "key_regions": ["Jerez-Xérès-Sherry"],
        "vineyard_area_ha": 17000,
    },
    {
        "name": "Pedro Ximénez",
        "color": "white",
        "origin": "Spain (Andalusia / Montilla-Moriles)",
        "synonyms": ["PX"],
        "characteristics": "Sun-dried to raisins for sweet wine production; produces intensely sweet, viscous wines with flavors of fig, date, coffee, and molasses; also used for blending and sweetening Sherry; primary grape of Montilla-Moriles",
        "key_regions": ["Montilla-Moriles", "Jerez-Xérès-Sherry"],
        "vineyard_area_ha": 10000,
    },
    {
        "name": "Parellada",
        "color": "white",
        "origin": "Spain (Catalonia)",
        "synonyms": ["Montonec", "Montonega"],
        "characteristics": "Delicate, aromatic, with floral and citrus notes; low alcohol potential; grown at the highest altitudes in Penedès where cool temperatures preserve freshness; one of the three traditional Cava grapes, contributing elegance and aroma",
        "key_regions": ["Penedès (Cava)"],
        "vineyard_area_ha": 7000,
    },
    {
        "name": "Xarel·lo",
        "color": "white",
        "origin": "Spain (Catalonia)",
        "synonyms": ["Pansa Blanca"],
        "characteristics": "Full-bodied, earthy, with apple and citrus notes; the backbone grape of Cava providing structure, body, and aging potential; also produces distinctive still wines in Penedès; relatively aromatic",
        "key_regions": ["Penedès (Cava)"],
        "vineyard_area_ha": 8000,
    },
    {
        "name": "Garnacha Blanca",
        "color": "white",
        "origin": "Spain (northeast Spain)",
        "synonyms": ["Grenache Blanc (France)"],
        "characteristics": "Full-bodied with stone fruit, herbal, and slightly oily character; naturally low acidity; thrives in warm Mediterranean conditions; produces rich, textured whites often with subtle anise notes",
        "key_regions": ["Terra Alta", "Priorat", "Navarra"],
        "vineyard_area_ha": 5000,
    },
    {
        "name": "Hondarrabi Zuri",
        "color": "white",
        "origin": "Spain (Basque Country)",
        "synonyms": ["Courbu Blanc"],
        "characteristics": "High-acid, low-alcohol variety used for Txakoli; produces crisp, citrusy, slightly spritzy wines; adapted to the cool, wet Basque Atlantic climate; name means 'white grape' in Basque",
        "key_regions": ["Getariako Txakolina", "Bizkaiko Txakolina"],
        "vineyard_area_ha": 800,
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Classification System
# ═══════════════════════════════════════════════════════════════════════════════

CLASSIFICATION_DATABASE = {
    "hierarchy": [
        {"level": "Vino de Mesa", "description": "Basic table wine with no geographic indication; the lowest tier in the Spanish wine classification system"},
        {"level": "Vino de la Tierra (VdlT/IGP)", "description": "Country wine with a geographic indication equivalent to the French Vin de Pays; approximately 46 recognized Vinos de la Tierra across Spain"},
        {"level": "Denominación de Origen (DO)", "description": "Quality wine from a defined region meeting specific production standards; regulated by a Consejo Regulador (regulatory council); approximately 70 DOs in Spain"},
        {"level": "Denominación de Origen Calificada (DOCa)", "description": "The highest quality tier for Spanish wine regions, requiring at least 10 years as a DO plus stricter quality controls; only Rioja (1991) and Priorat (2009) hold this status"},
        {"level": "Vino de Pago (VP)", "description": "Single-estate wines from a recognized exceptional vineyard (pago); the estate must demonstrate distinctive terroir character and have its own quality controls; approximately 20 recognized Vinos de Pago"},
    ],
    "aging_red": [
        {"level": "Joven", "description": "Young wine with no required oak aging; released in the year following harvest; also called 'vino del año' (wine of the year)"},
        {"level": "Roble / Semi-Crianza", "description": "Wine with some oak aging (typically 3-6 months) but not meeting full Crianza requirements; 'roble' means 'oak'"},
        {"level": "Crianza", "description": "Minimum 24 months total aging with at least 12 months in oak barrels (225-liter barricas) for red wines; released in the third year after vintage"},
        {"level": "Reserva", "description": "Minimum 36 months total aging with at least 12 months in oak barrels for red wines; made only in above-average vintages from selected fruit"},
        {"level": "Gran Reserva", "description": "Minimum 60 months total aging with at least 18 months in oak barrels for red wines; made only in exceptional vintages from the best fruit"},
    ],
    "aging_white_rose": [
        {"level": "Crianza (white/rosé)", "description": "Minimum 18 months total aging with at least 6 months in oak barrels for white and rosé wines"},
        {"level": "Reserva (white/rosé)", "description": "Minimum 24 months total aging with at least 6 months in oak barrels for white and rosé wines"},
        {"level": "Gran Reserva (white/rosé)", "description": "Minimum 48 months total aging with at least 6 months in oak barrels for white and rosé wines"},
    ],
    "general_facts": [
        "Spain has two DOCa (Denominación de Origen Calificada) wine regions: Rioja (since 1991) and Priorat (since 2009).",
        "Spain has approximately 20 recognized Vinos de Pago (VP), each representing a single estate with distinctive terroir.",
        "Spain has approximately 70 Denominaciones de Origen (DOs) covering wine production across the country.",
        "Each Spanish DO is regulated by a Consejo Regulador (regulatory council) responsible for enforcing production standards, grape variety restrictions, aging requirements, and quality controls.",
        "The Consejo Regulador system in Spain dates back to the creation of the Rioja Consejo Regulador in 1926.",
        "Spanish wine law requires red Crianza wines to age for a minimum of 24 months total, including at least 12 months in 225-liter oak barrels (barricas).",
        "Spanish red Reserva wines must age for a minimum of 36 months total, including at least 12 months in oak barrels.",
        "Spanish red Gran Reserva wines must age for a minimum of 60 months (5 years) total, including at least 18 months in oak barrels.",
        "White and rosé Crianza wines in Spain require a minimum of 18 months total aging with at least 6 months in oak.",
        "The Vino de Pago classification was established by Spanish wine law in 2003 to recognize exceptional single-estate wines.",
    ],
}


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Sherry Database
# ═══════════════════════════════════════════════════════════════════════════════

SHERRY_DATABASE = {
    "styles": [
        {
            "name": "Fino",
            "description": "Dry Sherry aged under a film of flor yeast (biological aging), protecting the wine from oxidation",
            "color": "pale straw to light gold",
            "aging": "biological (under flor)",
            "alcohol": "15-15.5%",
            "characteristics": "Bone-dry, delicate, with almond, yeast, and saline notes; light-bodied with pungent, complex aromatics",
            "serving": "Chilled (7-9°C), best consumed fresh after opening",
            "grape": "Palomino Fino",
        },
        {
            "name": "Manzanilla",
            "description": "A style of Fino Sherry produced exclusively in Sanlúcar de Barrameda, where the coastal humidity promotes thicker flor and distinct character",
            "color": "very pale straw",
            "aging": "biological (under flor)",
            "alcohol": "15-15.5%",
            "characteristics": "The lightest and most delicate Sherry style; pronounced saline/iodine character from the sea air; chamomile (manzanilla) aromas; slightly bitter almond finish",
            "serving": "Chilled (7-9°C), even more perishable than Fino",
            "grape": "Palomino Fino",
        },
        {
            "name": "Amontillado",
            "description": "Sherry that begins aging biologically under flor, then continues with oxidative aging after the flor dies or is removed by fortification to ~17.5%",
            "color": "amber to dark gold",
            "aging": "biological then oxidative",
            "alcohol": "16-22%",
            "characteristics": "Combines the nutty, yeasty character of biological aging with the complexity of oxidation; dry, with hazelnut, caramel, and tobacco notes; fuller than Fino but drier than Oloroso",
            "serving": "Slightly chilled (12-14°C)",
            "grape": "Palomino Fino",
        },
        {
            "name": "Oloroso",
            "description": "Sherry aged entirely through oxidative aging without flor; fortified to 17-17.5% after classification to prevent flor development",
            "color": "dark amber to mahogany",
            "aging": "oxidative (no flor)",
            "alcohol": "17-22%",
            "characteristics": "Rich, complex, and full-bodied; naturally dry with walnut, dried fruit, leather, and spice notes; despite dark color and richness, true Oloroso is dry",
            "serving": "Room temperature or slightly chilled (14-16°C)",
            "grape": "Palomino Fino",
        },
        {
            "name": "Palo Cortado",
            "description": "Rare Sherry that begins biological aging as a Fino but spontaneously loses its flor, continuing as an oxidative wine; combines characteristics of both Amontillado and Oloroso",
            "color": "chestnut to mahogany",
            "aging": "biological then oxidative (spontaneous)",
            "alcohol": "17-22%",
            "characteristics": "Combines the aromatic finesse and pungency of Amontillado with the body and richness of Oloroso; complex, rare, and highly prized",
            "serving": "Slightly chilled (12-14°C)",
            "grape": "Palomino Fino",
        },
        {
            "name": "Pedro Ximénez (PX)",
            "description": "Intensely sweet Sherry made from sun-dried Pedro Ximénez grapes (asoleo process) that concentrates sugars to extreme levels",
            "color": "dark mahogany to opaque black",
            "aging": "oxidative",
            "alcohol": "15-22%",
            "characteristics": "Extremely sweet and viscous with flavors of fig, date, raisin, coffee, molasses, and chocolate; one of the sweetest wines in the world; can contain over 400 g/L residual sugar",
            "serving": "Room temperature, often over ice cream or desserts",
            "grape": "Pedro Ximénez",
        },
        {
            "name": "Cream Sherry",
            "description": "A blended, sweetened Sherry style made by combining dry Oloroso with sweet Pedro Ximénez or Moscatel wine",
            "color": "dark gold to mahogany",
            "aging": "blended",
            "alcohol": "15.5-22%",
            "characteristics": "Medium to sweet with dried fruit, nut, and caramel notes; the original commercially successful style, popularized by Harvey's Bristol Cream",
            "serving": "Chilled or at room temperature",
            "grape": "Palomino Fino blend with PX or Moscatel",
        },
    ],
    "solera_system": [
        "The solera system is a fractional blending method used for aging Sherry, where wine is progressively moved through a series of barrel tiers (criaderas) from youngest to oldest.",
        "In a solera system, the bottom row of barrels (the solera) contains the oldest wine; above it are successive criaderas (nurseries) of progressively younger wine.",
        "When wine is drawn from the solera (lowest tier) for bottling, it is replenished from the first criadera above, which is in turn topped up from the second criadera, and so on.",
        "The solera system ensures consistency across bottlings because no barrel is ever fully emptied; typically no more than one-third of each barrel is drawn at a time.",
        "A Sherry solera may contain 3 to 14 tiers (criaderas), with finer and older Sherries typically having more criaderas and slower extraction rates.",
        "The fractional blending of the solera system means that a solera begun in a given year theoretically contains a decreasing fraction of that original wine in perpetuity.",
    ],
    "flor_facts": [
        "Flor is a film of Saccharomyces cerevisiae yeast that forms naturally on the surface of wine in partially filled Sherry barrels, protecting it from oxidation.",
        "Flor requires an alcohol level of 15-15.5% to survive; wines destined for Fino or Manzanilla are fortified to exactly this level to promote flor growth.",
        "Flor feeds on the wine's alcohol, glycerol, and residual sugars, producing acetaldehyde which gives Fino and Manzanilla their characteristic pungent, almond-like aroma.",
        "The thickness and vitality of the flor varies seasonally; it is most active in spring and autumn when temperatures in the bodega are moderate.",
        "Flor is thicker and more vigorous in Sanlúcar de Barrameda than in Jerez due to the town's higher humidity from the Guadalquivir estuary, contributing to Manzanilla's distinctive character.",
        "If flor dies naturally or is killed by further fortification (raising alcohol above 15.5%), the wine transitions from biological to oxidative aging, as occurs in Amontillado production.",
    ],
    "geography_facts": [
        "The Sherry Triangle encompasses the three towns of Jerez de la Frontera, El Puerto de Santa María, and Sanlúcar de Barrameda in Andalusia, southwestern Spain.",
        "All Sherry must be aged and shipped from bodegas within the Sherry Triangle to qualify for the DO Jerez-Xérès-Sherry designation.",
        "Sanlúcar de Barrameda, located at the mouth of the Guadalquivir River, is the exclusive production zone for Manzanilla Sherry due to its unique coastal microclimate.",
        "The albariza soil of the Sherry region is a white chalky soil composed of up to 80% calcium carbonate mixed with clay and silica; it absorbs and retains winter rainfall, releasing moisture during the dry summer.",
        "The pagos (vineyard areas) of the Jerez region are classified by soil type: albariza (chalk, highest quality), barro (clay), and arena (sand), with albariza vineyards producing the finest Sherry grapes.",
    ],
    "age_designations": [
        "VOS (Vinum Optimum Signatum) is an age designation for Sherry wines with an average age of at least 20 years, verified by the Consejo Regulador.",
        "VORS (Vinum Optimum Rare Signatum) is an age designation for Sherry wines with an average age of at least 30 years, representing the pinnacle of aged Sherry.",
        "The VOS and VORS age categories apply only to Amontillado, Oloroso, Palo Cortado, and Pedro Ximénez Sherry styles.",
        "En rama is an unfiltered or minimally filtered Fino or Manzanilla Sherry bottled directly from the solera, preserving the delicate flor character; it is typically released seasonally.",
        "Age-dated Sherry (12-year and 15-year categories) was introduced alongside VOS (20-year) and VORS (30-year) to help consumers understand Sherry quality tiers.",
    ],
}


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Cava Database
# ═══════════════════════════════════════════════════════════════════════════════

CAVA_DATABASE = {
    "production_method": [
        "Cava is produced using the traditional method (método tradicional), involving a secondary fermentation in the bottle, the same technique used for Champagne.",
        "The base wine for Cava undergoes primary fermentation, then is bottled with a liqueur de tirage (sugar and yeast) to trigger secondary fermentation, producing the bubbles.",
        "During Cava production, bottles undergo riddling (removido/remuage) to collect spent yeast lees in the neck, followed by disgorgement (degüelle) to expel the sediment.",
    ],
    "aging_tiers": [
        {"name": "Cava", "min_months": 9, "description": "Standard Cava with a minimum of 9 months aging on lees (sur lie) after secondary fermentation"},
        {"name": "Cava Reserva", "min_months": 15, "description": "Cava Reserva requires a minimum of 15 months aging on lees"},
        {"name": "Cava Gran Reserva", "min_months": 30, "description": "Cava Gran Reserva requires a minimum of 30 months aging on lees; only Brut Nature, Extra Brut, or Brut dosage permitted"},
        {"name": "Cava de Paraje Calificado", "min_months": 36, "description": "The highest tier of Cava, requiring a minimum of 36 months on lees from a single certified vineyard site (paraje); must be vintage-dated and estate-bottled"},
    ],
    "grapes": [
        "The three traditional Cava grapes are Macabeo (base and freshness), Xarel·lo (body and structure), and Parellada (elegance and aroma).",
        "Chardonnay and Pinot Noir are permitted in Cava production as supplementary varieties alongside the traditional Macabeo, Xarel·lo, and Parellada.",
        "Rosé Cava (rosado) may be produced using Garnacha, Monastrell, Pinot Noir, or Trepat for the red grape component.",
        "Xarel·lo provides the backbone and aging potential in Cava blends, contributing body, earthy character, and structure.",
        "Parellada, grown at the highest altitudes in Penedès, contributes floral aromas and delicate elegance to Cava blends.",
        "Macabeo (Viura) provides the fresh fruit base and citrus character in traditional Cava blends.",
    ],
    "geography": [
        "Approximately 95% of all Cava is produced in the Penedès region of Catalonia, centered on the town of Sant Sadurní d'Anoia.",
        "Sant Sadurní d'Anoia is the capital of Cava production, home to the largest Cava houses including Codorníu (founded 1551) and Freixenet (founded 1861).",
        "Although Cava production is dominated by Catalonia, the DO permits production in several other Spanish regions including Rioja, Navarra, Aragon, Extremadura, and Valencia.",
    ],
    "quality_reform": [
        "The 2020 Cava reform introduced three quality tiers: Cava de Guarda (basic), Cava de Guarda Superior (Reserva and Gran Reserva), and Cava de Paraje Calificado (single vineyard).",
        "Cava de Guarda Superior wines must be sourced from organic or sustainable vineyards and are subject to stricter yield limits and quality controls than basic Cava.",
        "Cava de Paraje Calificado must come from a single certified vineyard parcel, be vintage-dated, estate-bottled, and aged a minimum of 36 months on lees.",
    ],
}


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


def _get_source_id() -> str:
    """Register and return the Spanish Wine source ID."""
    return ensure_source(
        name=SOURCE["name"],
        url=SOURCE["url"],
        source_type=SOURCE["source_type"],
        tier=SOURCE["tier"],
        language=SOURCE["language"],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# FACT BUILDERS — Appellation
# ═══════════════════════════════════════════════════════════════════════════════


def _build_appellation_facts(source_id: str) -> list[dict]:
    """Build facts about Spanish appellations: terroir, climate, soil, elevation, grapes."""
    facts = []

    for do in APPELLATION_DATABASE:
        name = do["name"]
        classification = do["classification"]
        entities = [{"type": "appellation", "name": name}]
        base_tags = ["spain", name.lower().replace(" ", "_").replace("·", "").replace("/", "_")]

        # Classification
        facts.append(_make_fact(
            f"{name} holds {classification} status in the Spanish wine classification system.",
            domain="wine_regions",
            source_id=source_id,
            subdomain="classification",
            entities=entities,
            tags=base_tags + ["classification"],
        ))

        # Region
        facts.append(_make_fact(
            f"The {name} {classification} is located in {do['region']}, Spain.",
            domain="wine_regions",
            source_id=source_id,
            subdomain="geography",
            entities=entities,
            tags=base_tags + ["geography"],
        ))

        # Climate
        facts.append(_make_fact(
            f"The {name} {classification} has a {do['climate']} climate.",
            domain="wine_regions",
            source_id=source_id,
            subdomain="climate",
            entities=entities,
            tags=base_tags + ["climate"],
        ))

        # Soil types
        if do.get("soil_types"):
            soil_list = ", ".join(do["soil_types"])
            facts.append(_make_fact(
                f"The predominant soil types in the {name} {classification} include {soil_list}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="terroir",
                entities=entities,
                tags=base_tags + ["soil", "terroir"],
            ))

        # Soil details
        if do.get("soil_details"):
            facts.append(_make_fact(
                f"{do['soil_details']}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="terroir",
                entities=entities,
                tags=base_tags + ["soil", "terroir"],
            ))

        # Elevation
        if do.get("elevation_range"):
            facts.append(_make_fact(
                f"Vineyards in the {name} {classification} are planted at elevations ranging from {do['elevation_range']}.",
                domain="viticulture",
                source_id=source_id,
                subdomain="terrain",
                entities=entities,
                tags=base_tags + ["elevation"],
            ))

        # Vineyard area
        if do.get("vineyard_area_ha"):
            facts.append(_make_fact(
                f"The {name} {classification} has approximately {do['vineyard_area_ha']:,} hectares of vineyard.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="statistics",
                entities=entities,
                confidence=0.95,
                tags=base_tags + ["statistics", "vineyard_area"],
            ))

        # Key red grapes
        if do.get("key_red_grapes"):
            grapes_str = ", ".join(do["key_red_grapes"])
            grape_entities = entities + [{"type": "grape", "name": g.split(" (")[0]} for g in do["key_red_grapes"]]
            facts.append(_make_fact(
                f"The principal red grape varieties of the {name} {classification} include {grapes_str}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="regional_grapes",
                entities=grape_entities,
                tags=base_tags + ["grapes", "red_grapes"],
            ))

        # Key white grapes
        if do.get("key_white_grapes"):
            grapes_str = ", ".join(do["key_white_grapes"])
            grape_entities = entities + [{"type": "grape", "name": g.split(" (")[0]} for g in do["key_white_grapes"]]
            facts.append(_make_fact(
                f"The principal white grape varieties of the {name} {classification} include {grapes_str}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="regional_grapes",
                entities=grape_entities,
                tags=base_tags + ["grapes", "white_grapes"],
            ))

        # Wine styles
        if do.get("wine_styles"):
            styles_str = ", ".join(do["wine_styles"])
            facts.append(_make_fact(
                f"The {name} {classification} produces wines in the following styles: {styles_str}.",
                domain="winemaking",
                source_id=source_id,
                subdomain="wine_styles",
                entities=entities,
                tags=base_tags + ["wine_styles"],
            ))

        # Subzones
        for subzone in do.get("subzones", []):
            sub_entities = entities + [{"type": "subzone", "name": subzone["name"]}]
            facts.append(_make_fact(
                f"{subzone['name']} is a recognized subzone of the {name} {classification}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="subzones",
                entities=sub_entities,
                tags=base_tags + ["subzones", subzone["name"].lower().replace(" ", "_")],
            ))
            if subzone.get("notes"):
                facts.append(_make_fact(
                    f"{subzone['notes']}.",
                    domain="wine_regions",
                    source_id=source_id,
                    subdomain="subzones",
                    entities=sub_entities,
                    tags=base_tags + ["subzones", subzone["name"].lower().replace(" ", "_")],
                ))

        # Notes
        if do.get("notes"):
            # Split notes into separate sentences for atomic facts
            for sentence in do["notes"].split(". "):
                sentence = sentence.strip().rstrip(".")
                if len(sentence.split()) >= 5:
                    facts.append(_make_fact(
                        f"{sentence}.",
                        domain="wine_regions",
                        source_id=source_id,
                        subdomain="history_notes",
                        entities=entities,
                        confidence=0.95,
                        tags=base_tags + ["notes"],
                    ))

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# FACT BUILDERS — Grape Varieties
# ═══════════════════════════════════════════════════════════════════════════════


def _build_grape_variety_facts(source_id: str) -> list[dict]:
    """Build facts about Spanish grape variety profiles."""
    facts = []

    for grape in GRAPE_VARIETY_DATABASE:
        name = grape["name"]
        entities = [{"type": "grape", "name": name}]
        base_tags = ["spain", "grape", name.lower().replace(" ", "_").replace("·", "")]

        # Color and origin
        facts.append(_make_fact(
            f"{name} is a {grape['color']} grape variety originating from {grape['origin']}.",
            domain="grape_varieties",
            source_id=source_id,
            subdomain="grape_profile",
            entities=entities,
            tags=base_tags + ["origin"],
        ))

        # Synonyms
        if grape.get("synonyms"):
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
                f"{grape['characteristics']}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="grape_profile",
                entities=entities,
                tags=base_tags + ["characteristics"],
            ))

        # Key regions
        if grape.get("key_regions"):
            regions_str = ", ".join(grape["key_regions"])
            region_entities = entities + [{"type": "appellation", "name": r} for r in grape["key_regions"]]
            facts.append(_make_fact(
                f"The key Spanish wine regions for {name} include {regions_str}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="regional_grapes",
                entities=region_entities,
                tags=base_tags + ["regions"],
            ))

        # Vineyard area
        if grape.get("vineyard_area_ha"):
            facts.append(_make_fact(
                f"{name} has approximately {grape['vineyard_area_ha']:,} hectares planted in Spain.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="statistics",
                entities=entities,
                confidence=0.95,
                tags=base_tags + ["statistics", "vineyard_area"],
            ))

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# FACT BUILDERS — Classification System
# ═══════════════════════════════════════════════════════════════════════════════


def _build_classification_facts(source_id: str) -> list[dict]:
    """Build facts about the Spanish wine classification and aging system."""
    facts = []
    base_tags = ["spain", "classification"]

    # Hierarchy levels
    for level in CLASSIFICATION_DATABASE["hierarchy"]:
        facts.append(_make_fact(
            f"{level['description']}.",
            domain="wine_regions",
            source_id=source_id,
            subdomain="classification",
            entities=[{"type": "classification", "name": level["level"]}],
            tags=base_tags + ["hierarchy", level["level"].lower().replace(" ", "_").replace("(", "").replace(")", "")],
        ))

    # The hierarchy itself
    levels_str = " → ".join([l["level"] for l in CLASSIFICATION_DATABASE["hierarchy"]])
    facts.append(_make_fact(
        f"The Spanish wine classification hierarchy, from lowest to highest, is: {levels_str}.",
        domain="wine_regions",
        source_id=source_id,
        subdomain="classification",
        entities=[{"type": "classification", "name": "Spanish wine hierarchy"}],
        tags=base_tags + ["hierarchy"],
    ))

    # Red aging requirements
    for aging in CLASSIFICATION_DATABASE["aging_red"]:
        facts.append(_make_fact(
            f"{aging['description']}.",
            domain="winemaking",
            source_id=source_id,
            subdomain="aging",
            entities=[{"type": "aging_category", "name": aging["level"]}],
            tags=base_tags + ["aging", "red", aging["level"].lower().replace(" ", "_").replace("/", "_")],
        ))

    # White/rosé aging requirements
    for aging in CLASSIFICATION_DATABASE["aging_white_rose"]:
        facts.append(_make_fact(
            f"{aging['description']}.",
            domain="winemaking",
            source_id=source_id,
            subdomain="aging",
            entities=[{"type": "aging_category", "name": aging["level"]}],
            tags=base_tags + ["aging", "white_rose", aging["level"].lower().replace(" ", "_").replace("/", "_")],
        ))

    # General classification facts
    for fact_text in CLASSIFICATION_DATABASE["general_facts"]:
        facts.append(_make_fact(
            fact_text,
            domain="wine_regions",
            source_id=source_id,
            subdomain="classification",
            entities=[],
            tags=base_tags + ["general"],
        ))

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# FACT BUILDERS — Sherry
# ═══════════════════════════════════════════════════════════════════════════════


def _build_sherry_facts(source_id: str) -> list[dict]:
    """Build facts about Sherry styles, solera system, flor, and geography."""
    facts = []
    base_tags = ["spain", "sherry", "jerez"]

    # Sherry styles
    for style in SHERRY_DATABASE["styles"]:
        name = style["name"]
        entities = [
            {"type": "wine_style", "name": name},
            {"type": "appellation", "name": "Jerez-Xérès-Sherry"},
        ]
        style_tags = base_tags + [name.lower().replace(" ", "_")]

        facts.append(_make_fact(
            f"{style['description']}.",
            domain="winemaking",
            source_id=source_id,
            subdomain="sherry",
            entities=entities,
            tags=style_tags,
        ))

        facts.append(_make_fact(
            f"{name} Sherry has a {style['color']} color and is aged through {style['aging']} aging.",
            domain="winemaking",
            source_id=source_id,
            subdomain="sherry",
            entities=entities,
            tags=style_tags + ["appearance"],
        ))

        facts.append(_make_fact(
            f"{name} Sherry typically has an alcohol content of {style['alcohol']}.",
            domain="winemaking",
            source_id=source_id,
            subdomain="sherry",
            entities=entities,
            tags=style_tags + ["alcohol"],
        ))

        facts.append(_make_fact(
            f"{style['characteristics']}.",
            domain="winemaking",
            source_id=source_id,
            subdomain="sherry",
            entities=entities,
            tags=style_tags + ["characteristics"],
        ))

        facts.append(_make_fact(
            f"{name} Sherry is best served {style['serving']}.",
            domain="winemaking",
            source_id=source_id,
            subdomain="sherry",
            entities=entities,
            tags=style_tags + ["serving"],
        ))

        facts.append(_make_fact(
            f"{name} Sherry is made from {style['grape']}.",
            domain="winemaking",
            source_id=source_id,
            subdomain="sherry",
            entities=entities + [{"type": "grape", "name": style["grape"].split(" blend")[0]}],
            tags=style_tags + ["grape"],
        ))

    # Solera system facts
    for fact_text in SHERRY_DATABASE["solera_system"]:
        facts.append(_make_fact(
            fact_text,
            domain="winemaking",
            source_id=source_id,
            subdomain="sherry_solera",
            entities=[{"type": "technique", "name": "solera system"}],
            tags=base_tags + ["solera"],
        ))

    # Flor facts
    for fact_text in SHERRY_DATABASE["flor_facts"]:
        facts.append(_make_fact(
            fact_text,
            domain="winemaking",
            source_id=source_id,
            subdomain="sherry_flor",
            entities=[{"type": "technique", "name": "flor yeast"}],
            tags=base_tags + ["flor"],
        ))

    # Geography facts
    for fact_text in SHERRY_DATABASE["geography_facts"]:
        facts.append(_make_fact(
            fact_text,
            domain="wine_regions",
            source_id=source_id,
            subdomain="sherry_geography",
            entities=[{"type": "appellation", "name": "Jerez-Xérès-Sherry"}],
            tags=base_tags + ["geography"],
        ))

    # Age designations
    for fact_text in SHERRY_DATABASE["age_designations"]:
        facts.append(_make_fact(
            fact_text,
            domain="winemaking",
            source_id=source_id,
            subdomain="sherry_aging",
            entities=[{"type": "appellation", "name": "Jerez-Xérès-Sherry"}],
            tags=base_tags + ["aging", "age_designation"],
        ))

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# FACT BUILDERS — Cava
# ═══════════════════════════════════════════════════════════════════════════════


def _build_cava_facts(source_id: str) -> list[dict]:
    """Build facts about Cava sparkling wine production and rules."""
    facts = []
    base_tags = ["spain", "cava", "sparkling"]
    entities = [{"type": "appellation", "name": "Cava"}]

    # Production method
    for fact_text in CAVA_DATABASE["production_method"]:
        facts.append(_make_fact(
            fact_text,
            domain="winemaking",
            source_id=source_id,
            subdomain="cava_production",
            entities=entities,
            tags=base_tags + ["production_method"],
        ))

    # Aging tiers
    for tier in CAVA_DATABASE["aging_tiers"]:
        tier_entities = entities + [{"type": "aging_category", "name": tier["name"]}]
        facts.append(_make_fact(
            f"{tier['description']}.",
            domain="winemaking",
            source_id=source_id,
            subdomain="cava_aging",
            entities=tier_entities,
            tags=base_tags + ["aging", tier["name"].lower().replace(" ", "_")],
        ))
        facts.append(_make_fact(
            f"{tier['name']} requires a minimum of {tier['min_months']} months aging on lees.",
            domain="winemaking",
            source_id=source_id,
            subdomain="cava_aging",
            entities=tier_entities,
            tags=base_tags + ["aging", tier["name"].lower().replace(" ", "_")],
        ))

    # Grape facts
    for fact_text in CAVA_DATABASE["grapes"]:
        facts.append(_make_fact(
            fact_text,
            domain="grape_varieties",
            source_id=source_id,
            subdomain="cava_grapes",
            entities=entities,
            tags=base_tags + ["grapes"],
        ))

    # Geography
    for fact_text in CAVA_DATABASE["geography"]:
        facts.append(_make_fact(
            fact_text,
            domain="wine_regions",
            source_id=source_id,
            subdomain="cava_geography",
            entities=entities,
            tags=base_tags + ["geography"],
        ))

    # Quality reform
    for fact_text in CAVA_DATABASE["quality_reform"]:
        facts.append(_make_fact(
            fact_text,
            domain="winemaking",
            source_id=source_id,
            subdomain="cava_classification",
            entities=entities,
            tags=base_tags + ["classification", "quality_reform"],
        ))

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# PIPELINE
# ═══════════════════════════════════════════════════════════════════════════════


def _build_all_facts(source_id: str, data_type: str = None) -> list[dict]:
    """Build all facts, optionally filtered by type."""
    all_facts = []

    builders = {
        "appellation": _build_appellation_facts,
        "grape": _build_grape_variety_facts,
        "classification": _build_classification_facts,
        "sherry": _build_sherry_facts,
        "cava": _build_cava_facts,
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
        click.echo(f"\n[DRY RUN] Would insert {len(facts)} facts from Spanish Wine Reference Database")

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

    logger.info(f"Inserted {inserted} new facts from Spanish Wine Reference Database (duplicates skipped)")
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

    # (g) Overlap check with europe.py patterns
    europe_patterns = [
        r"^.+ is a .+ appellation in Spain\.$",
        r"^.+ DO is located in .+ Spain\.$",
        r"^The .+ DO covers approximately .+ hectares",
    ]
    overlap_count = 0
    for f in facts:
        for pat in europe_patterns:
            if re.match(pat, f["fact_text"]):
                overlap_count += 1
                break
    click.echo(f"\n  Potential europe.py overlaps: {overlap_count}")


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
        "Appellations": _build_appellation_facts,
        "Grape Varieties": _build_grape_variety_facts,
        "Classification": _build_classification_facts,
        "Sherry": _build_sherry_facts,
        "Cava": _build_cava_facts,
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
    type=click.Choice(["appellation", "grape", "classification", "sherry", "cava"]),
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
    """OenoBench Spanish Wine Enrichment Scraper — Terroir, grapes, classification, Sherry, and Cava."""
    logger.add("data/logs/spain_enrichment_{time}.log", rotation="10 MB")

    if list_sources:
        click.echo("\nAvailable data categories:")
        click.echo(f"  {'appellation':18s} — {len(APPELLATION_DATABASE)} Spanish DOs/DOCas (terroir, climate, soil, elevation, grapes)")
        click.echo(f"  {'grape':18s} — {len(GRAPE_VARIETY_DATABASE)} grape variety profiles (origin, synonyms, characteristics)")
        click.echo(f"  {'classification':18s} — Spanish wine hierarchy and aging system (DO/DOCa/VP, Crianza/Reserva/Gran Reserva)")
        click.echo(f"  {'sherry':18s} — Sherry styles, solera system, flor yeast, geography, age designations")
        click.echo(f"  {'cava':18s} — Cava traditional method, aging tiers, grapes, geography, quality reform")
        click.echo(f"\nKnowledge base coverage:")
        click.echo(f"  Appellations:     {len(APPELLATION_DATABASE)}")
        click.echo(f"  Grape varieties:  {len(GRAPE_VARIETY_DATABASE)}")
        click.echo(f"  Sherry styles:    {len(SHERRY_DATABASE['styles'])}")
        click.echo(f"  Cava aging tiers: {len(CAVA_DATABASE['aging_tiers'])}")
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
