"""
OenoBench — South American Wine Scraper (Argentina & Chile)

Extracts structured wine data for Argentina and Chile covering regions,
grape varieties, classification systems, and terroir details.

Focus areas: altitude viticulture (Argentina), transversal classification
(Chile), Malbec expressions, Carmenere rediscovery, and the full
north-to-south spectrum of Chilean wine regions.

Usage:
    python -m src.scrapers.south_america --all
    python -m src.scrapers.south_america --type argentina
    python -m src.scrapers.south_america --type chile
    python -m src.scrapers.south_america --type grape
    python -m src.scrapers.south_america --type classification
    python -m src.scrapers.south_america --dry-run
    python -m src.scrapers.south_america --validate
    python -m src.scrapers.south_america --test-run
    python -m src.scrapers.south_america --list
"""

import random
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
    "name": "South American Wine Reference — Argentina & Chile",
    "url": "https://www.winesofargentina.org",
    "source_type": "reference",
    "tier": "tier_2_authoritative",
    "language": "en",
}


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Argentina Regions
# ═══════════════════════════════════════════════════════════════════════════════

ARGENTINA_REGIONS = [
    {
        "name": "Mendoza",
        "country": "Argentina",
        "climate": "arid continental with extreme diurnal temperature variation",
        "climate_details": "Mendoza has a desert climate with less than 200mm of annual rainfall, relying almost entirely on snowmelt irrigation from the Andes; over 300 days of sunshine per year and diurnal temperature swings of 15-20 degrees Celsius preserve acidity in grapes",
        "soil_types": ["alluvial", "sandy", "clay", "gravel", "limestone"],
        "soil_details": "Alluvial soils deposited by the Mendoza and Tunuyan rivers dominate the lower areas; upper zones in Lujan de Cuyo and Valle de Uco feature rocky, calcareous soils with excellent drainage",
        "vineyard_area_ha": 160000,
        "elevation_range": "600-1500m",
        "key_grapes": ["Malbec", "Cabernet Sauvignon", "Bonarda", "Syrah", "Tempranillo", "Chardonnay", "Torrontes"],
        "notes": "Mendoza accounts for approximately 70% of Argentina's total wine production and is the heartland of Argentine Malbec",
        "extra_facts": [
            "Mendoza's wine industry was largely built by Italian immigrants who arrived in the late 19th and early 20th centuries, bringing winemaking traditions that still influence the region today.",
            "The city of Mendoza sits at the base of Aconcagua, the highest peak in the Americas at 6,961 meters, and the Andes provide the snowmelt that irrigates virtually all of the province's vineyards.",
            "Mendoza province produces over 70% of all Argentine wine, making it by far the dominant wine region in the country by both volume and quality.",
            "The First Zone (Primera Zona) of Mendoza, encompassing Lujan de Cuyo and Maipu, was the traditional center of premium wine production before the development of Valle de Uco in the 1990s.",
            "Mendoza has a continental semi-arid climate classified as BWk (cold desert) in the Koppen climate classification system, with annual rainfall averaging less than 200mm.",
        ],
        "subregions": [
            {
                "name": "Lujan de Cuyo",
                "elevation_range": "900-1100m",
                "soil_types": ["alluvial", "gravel", "clay"],
                "notes": "Known as the First Zone (Primera Zona), Lujan de Cuyo was the first Argentine DOC established in 1993 and is considered the historic heartland of Malbec in Argentina",
                "key_grapes": ["Malbec", "Cabernet Sauvignon"],
            },
            {
                "name": "Valle de Uco",
                "elevation_range": "900-1500m",
                "soil_types": ["alluvial", "limestone", "gravel", "sand"],
                "notes": "Valle de Uco contains some of the highest commercial vineyards in the world and has become Argentina's most prestigious wine region for premium production since the early 2000s",
                "key_grapes": ["Malbec", "Cabernet Franc", "Chardonnay", "Pinot Noir"],
                "subdistricts": [
                    {"name": "Tupungato", "elevation_range": "1200-1500m", "notes": "The highest subdistrict in Valle de Uco, Tupungato produces intensely concentrated wines with vibrant acidity from extreme altitude"},
                    {"name": "Tunuyan", "elevation_range": "900-1200m", "notes": "Tunuyan includes the acclaimed Vista Flores district and produces elegant, balanced wines at moderate high altitude"},
                    {"name": "San Carlos", "elevation_range": "900-1200m", "notes": "San Carlos is the warmest subdistrict in Valle de Uco with slightly lower elevations and produces ripe, full-bodied wines"},
                ],
            },
            {
                "name": "Maipu",
                "elevation_range": "800-900m",
                "soil_types": ["alluvial", "clay", "gravel"],
                "notes": "Maipu is one of the traditional wine areas of Mendoza, home to many of Argentina's oldest and largest wineries established in the late 19th century",
                "key_grapes": ["Malbec", "Bonarda", "Cabernet Sauvignon"],
            },
            {
                "name": "East Mendoza",
                "elevation_range": "600-700m",
                "soil_types": ["alluvial", "sandy", "clay"],
                "notes": "East Mendoza (Zona Este) is warmer and lower in elevation, producing the majority of Argentina's high-volume everyday wines from extensive vineyard plantings",
                "key_grapes": ["Bonarda", "Criolla Grande", "Cereza", "Pedro Gimenez"],
            },
        ],
    },
    {
        "name": "Salta",
        "country": "Argentina",
        "climate": "arid desert with extreme UV radiation",
        "climate_details": "Salta's Cafayate Valley has a desert climate with less than 150mm annual rainfall; extreme ultraviolet radiation at high altitude produces thicker grape skins and higher polyphenol concentration; hailstorms are a significant viticultural hazard",
        "soil_types": ["sandy", "gravel", "calcareous"],
        "soil_details": "Sandy and gravelly alluvial soils in the Cafayate Valley with calcareous subsoils; the Quebrada de Humahuaca has some of the most mineral-rich soils from ancient Andean sediment",
        "vineyard_area_ha": 3500,
        "elevation_range": "1700-3000m",
        "key_grapes": ["Torrontes", "Malbec", "Cabernet Sauvignon", "Tannat"],
        "notes": "Salta contains the world's highest commercial vineyards, with some plantings in the Quebrada de Humahuaca and Colomé reaching above 3000 meters elevation",
        "extra_facts": [
            "The Calchaqui Valley in Salta stretches for over 200 kilometers and encompasses the main wine-producing areas of Cafayate, Molinos, and Cachi at different elevations and microclimates.",
            "Extreme UV radiation in Salta's high-altitude vineyards produces wines with exceptionally intense color and high levels of resveratrol and other antioxidant compounds.",
            "Hail is the most destructive weather hazard in Salta's vineyards, and many producers use protective hail netting (malla antigranizo) to shield their vines.",
            "Salta's Torrontes reaches peak aromatic expression in the Cafayate Valley, where the combination of intense daytime sunshine, cool nights, and sandy soils produces wines of extraordinary floral intensity.",
            "The Bodega Colomé estate in Salta's Calchaqui Valley includes the Altura Maxima vineyard at 3111 meters, among the highest vineyard blocks in the world.",
        ],
        "subregions": [
            {
                "name": "Cafayate",
                "elevation_range": "1660-1800m",
                "notes": "Cafayate is the main viticultural center of Salta province, a high-altitude desert valley producing Argentina's finest Torrontes and distinctive high-altitude Malbec and Tannat",
                "key_grapes": ["Torrontes", "Malbec", "Cabernet Sauvignon", "Tannat"],
            },
            {
                "name": "Quebrada de Humahuaca",
                "elevation_range": "2500-3329m",
                "notes": "The Quebrada de Humahuaca in Jujuy province contains the world's highest vineyards, with Bodega Fernando Dupont's vineyard at 3329 meters being among the highest commercial wine vineyard on Earth",
                "key_grapes": ["Malbec", "Torrontes"],
            },
        ],
    },
    {
        "name": "Patagonia",
        "country": "Argentina",
        "climate": "cool continental with persistent winds",
        "climate_details": "Patagonia is the southernmost wine region in South America at approximately 39 degrees south latitude; strong Patagonian winds reduce disease pressure and thicken grape skins; the long growing season with cool temperatures produces wines with bright natural acidity",
        "soil_types": ["sandy", "alluvial", "clay", "gravel"],
        "soil_details": "Sandy alluvial soils deposited by the Negro and Neuquen rivers; the arid climate and constant wind create naturally dry conditions that favor organic viticulture",
        "vineyard_area_ha": 5000,
        "elevation_range": "250-400m",
        "key_grapes": ["Pinot Noir", "Malbec", "Chardonnay", "Merlot", "Sauvignon Blanc", "Torrontes"],
        "notes": "Patagonia encompasses the Rio Negro and Neuquen provinces and has emerged as Argentina's most exciting cool-climate wine region since the early 2000s",
        "extra_facts": [
            "Patagonian wines are distinguished by their bright acidity, aromatic purity, and moderate alcohol levels, characteristics derived from the cool climate and long, slow ripening season.",
            "The constant wind in Patagonia, which can exceed 50 km/h during the growing season, acts as a natural pest deterrent and reduces the need for fungicide applications.",
            "Bodega Noemia in Rio Negro, established by Countess Noemi Marone Cinzano in 2001, helped pioneer premium Malbec production in Patagonia from 70+ year old vines.",
            "Patagonia's latitude of approximately 39 degrees south is equivalent to the northern hemisphere latitude of central Spain or southern Italy, but produces much cooler-climate wines due to the region's continental climate and elevation.",
        ],
        "subregions": [
            {
                "name": "Rio Negro",
                "notes": "The Rio Negro province has the longest winemaking history in Patagonia, with vine plantings dating to the early 20th century along the Upper Valley of the Negro River",
                "key_grapes": ["Pinot Noir", "Malbec", "Semillon", "Torrontes"],
            },
            {
                "name": "Neuquen",
                "notes": "The Neuquen province, particularly the San Patricio del Chanar district, has attracted significant investment for premium cool-climate wine production since the late 1990s",
                "key_grapes": ["Pinot Noir", "Malbec", "Chardonnay", "Merlot"],
            },
        ],
    },
    {
        "name": "San Juan",
        "country": "Argentina",
        "climate": "hot arid desert",
        "climate_details": "San Juan has an extremely hot desert climate with temperatures regularly exceeding 40 degrees Celsius in summer; irrigation is essential from Andean snowmelt; higher altitude zones in Pedernal and Calingasta are cooler and increasingly valued for quality wine",
        "soil_types": ["alluvial", "sandy", "clay", "limestone"],
        "soil_details": "Deep alluvial soils on the valley floor; the Pedernal Valley at higher elevation has calcareous and rocky soils suited to premium wine production",
        "vineyard_area_ha": 47000,
        "elevation_range": "600-1500m",
        "key_grapes": ["Syrah", "Bonarda", "Cabernet Sauvignon", "Cereza", "Muscat of Alexandria"],
        "notes": "San Juan is Argentina's second-largest wine province by area and produces significant quantities of Syrah, table grapes, and grapes for concentrate and raisins",
        "extra_facts": [
            "San Juan province accounts for approximately 22% of Argentina's total wine grape production, second only to Mendoza.",
            "The Tulum Valley is San Juan's main winemaking zone, with extensive vineyard plantings on the valley floor irrigated by water from the San Juan River.",
            "San Juan is Argentina's primary region for Syrah production, with the variety performing exceptionally well in the province's hot, dry conditions.",
        ],
        "subregions": [
            {
                "name": "Pedernal Valley",
                "elevation_range": "1350-1500m",
                "notes": "The Pedernal Valley in San Juan is a high-altitude desert zone that has emerged as one of Argentina's most promising regions for premium Syrah and Malbec since the early 2010s",
                "key_grapes": ["Syrah", "Malbec", "Cabernet Sauvignon"],
            },
        ],
    },
    {
        "name": "La Rioja (Argentina)",
        "country": "Argentina",
        "climate": "hot arid",
        "climate_details": "La Rioja province in Argentina has a hot arid climate with extremely low rainfall; the Famatina Valley offers higher-altitude sites with cooler conditions suited to Torrontes Riojano production",
        "soil_types": ["sandy", "alluvial", "clay"],
        "soil_details": "Sandy alluvial soils from Andean runoff dominate the vineyard areas of La Rioja province",
        "vineyard_area_ha": 7000,
        "elevation_range": "800-1500m",
        "key_grapes": ["Torrontes Riojano", "Bonarda", "Cabernet Sauvignon", "Syrah"],
        "notes": "La Rioja province is historically significant as one of the earliest wine regions in Argentina, with Torrontes Riojano as its signature grape variety",
        "extra_facts": [
            "The name Torrontes Riojano derives from La Rioja province, where this aromatic white grape has its traditional home and produces its most characterful wines.",
            "La Rioja province has the Famatina Valley as its primary premium wine zone, with vineyards at 1000-1500 meters elevation producing concentrated wines from the intense desert sunshine and cold nights.",
        ],
    },
    {
        "name": "Catamarca",
        "country": "Argentina",
        "climate": "arid with extreme altitude",
        "climate_details": "Catamarca province has an arid climate similar to Salta, with high-altitude vineyard sites in the Fiambala and Tinogasta valleys reaching over 2000 meters elevation",
        "soil_types": ["sandy", "gravel", "alluvial"],
        "soil_details": "Sandy and gravelly alluvial soils derived from Andean erosion with very good natural drainage",
        "vineyard_area_ha": 2500,
        "elevation_range": "1000-2500m",
        "key_grapes": ["Malbec", "Cabernet Sauvignon", "Torrontes", "Syrah"],
        "notes": "Catamarca is a frontier wine region in Argentina with some of the highest vineyard plantings in the world outside Salta, particularly in the Fiambala Valley",
        "extra_facts": [
            "The Fiambala Valley in Catamarca has vineyards planted at up to 2500 meters elevation, producing intensely concentrated and deeply colored wines from extreme UV exposure.",
            "Catamarca's Tinogasta department is gaining recognition for Malbec and Cabernet Sauvignon from high-altitude sites with calcareous soils and extreme diurnal temperature variation.",
        ],
    },
    {
        "name": "Tucuman",
        "country": "Argentina",
        "climate": "subtropical with altitude mitigation",
        "climate_details": "Tucuman province has a subtropical base climate moderated by altitude in the Tafi del Valle and Amaicha del Valle zones, where vineyards are planted above 2000 meters to achieve sufficient diurnal temperature variation",
        "soil_types": ["sandy", "clay", "gravel"],
        "soil_details": "Sandy and gravelly soils at altitude in the mountain valleys of Tucuman province",
        "vineyard_area_ha": 500,
        "elevation_range": "1800-2500m",
        "key_grapes": ["Malbec", "Torrontes", "Cabernet Sauvignon"],
        "notes": "Tucuman is one of Argentina's smallest and newest fine wine regions, with extreme altitude compensating for its subtropical latitude",
        "extra_facts": [
            "The Amaicha del Valle in Tucuman at over 2000 meters elevation is one of the few places where viticulture is viable at a subtropical latitude (26 degrees south), thanks to the extreme altitude.",
            "Tucuman's vineyards in the Tafi del Valle and Amaicha del Valle benefit from ancient pre-Incan terrace systems that were originally built for agricultural cultivation.",
        ],
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Chile Regions
# ═══════════════════════════════════════════════════════════════════════════════

CHILE_REGIONS = [
    {
        "name": "Elqui Valley",
        "country": "Chile",
        "climate": "arid desert with intense sunshine",
        "climate_details": "The Elqui Valley is Chile's northernmost wine region at approximately 30 degrees south latitude with a desert climate receiving less than 100mm of annual rainfall; clear skies produce intense solar radiation year-round",
        "soil_types": ["alluvial", "granite", "sandy"],
        "soil_details": "Stony alluvial soils with granitic influence in the narrow river valley; natural drainage is excellent due to the steep valley terrain",
        "vineyard_area_ha": 500,
        "elevation_range": "500-2000m",
        "key_grapes": ["Syrah", "Muscat", "Pedro Ximenez", "Cabernet Sauvignon"],
        "notes": "The Elqui Valley is best known for Pisco production but has increasingly attracted attention for Syrah and other red varieties planted at high altitude since the early 2000s",
        "extra_facts": [
            "The Elqui Valley is one of the clearest skies in the world, hosting major astronomical observatories; this intense solar radiation benefits vine growth and grape ripening at altitude.",
            "Viña Falernia was one of the first wineries to demonstrate the Elqui Valley's potential for premium Syrah, producing wines with intense color and concentration from desert-grown vines.",
            "Pisco, the grape-based spirit distilled from Muscat and Pedro Ximenez, has been produced in the Elqui Valley since the colonial era and remains the region's primary viticultural product.",
        ],
    },
    {
        "name": "Limari Valley",
        "country": "Chile",
        "climate": "coastal desert with maritime fog influence",
        "climate_details": "The Limari Valley benefits from camanchaca, a persistent coastal fog that rolls inland from the Pacific Ocean providing natural humidity and cooling in an otherwise arid desert environment; this fog influence moderates temperatures and extends the growing season",
        "soil_types": ["limestone", "clay", "alluvial", "calcareous"],
        "soil_details": "The Limari Valley contains some of Chile's only significant limestone deposits, which produce wines with distinctive mineral character; calcareous soils are particularly valued for Chardonnay production",
        "vineyard_area_ha": 2000,
        "elevation_range": "200-700m",
        "key_grapes": ["Chardonnay", "Syrah", "Pinot Noir", "Sauvignon Blanc"],
        "notes": "The Limari Valley's camanchaca fog and limestone soils have drawn comparisons to Burgundy for Chardonnay, making it one of Chile's most distinctive white wine regions",
        "extra_facts": [
            "The camanchaca fog in Limari Valley typically rolls inland from the Pacific in the morning and dissipates by midday, providing natural cooling and moisture in the otherwise arid desert climate.",
            "Limari Valley's limestone soils are geologically unusual for Chile, where most wine regions have volcanic or alluvial soils, giving wines from this area a distinctive chalky mineral character.",
            "The Tabalí winery was among the first to demonstrate Limari Valley's potential for world-class Chardonnay and Syrah in the early 2000s, attracting attention to this previously overlooked region.",
        ],
    },
    {
        "name": "Choapa Valley",
        "country": "Chile",
        "climate": "semi-arid with warm days and cool nights",
        "climate_details": "The Choapa Valley is a narrow, mountainous zone where the Andes and Coastal ranges nearly converge, creating a distinctive terroir with strong diurnal temperature variation and limited rainfall",
        "soil_types": ["alluvial", "granite", "clay"],
        "soil_details": "Narrow alluvial valley floor with granitic and clay soils influenced by the proximity of both mountain ranges",
        "vineyard_area_ha": 300,
        "elevation_range": "400-800m",
        "key_grapes": ["Syrah", "Cabernet Sauvignon"],
        "notes": "The Choapa Valley is one of Chile's smallest wine regions, where the Andes and Coastal ranges come closest together creating an unusually narrow viticultural corridor",
        "extra_facts": [
            "In the Choapa Valley, the distance between the Andes and the Coastal Range narrows to approximately 100 kilometers, the closest approach of the two mountain ranges in Chile's wine country.",
        ],
    },
    {
        "name": "Aconcagua Valley",
        "country": "Chile",
        "climate": "warm Mediterranean with hot dry summers",
        "climate_details": "The interior Aconcagua Valley has a warm Mediterranean climate with hot, dry summers and mild winters; the valley is open to Pacific cooling through the Aconcagua River gap but retains significant heat in its upper reaches",
        "soil_types": ["alluvial", "gravel", "clay", "granite"],
        "soil_details": "Alluvial and gravelly soils deposited by the Aconcagua River with good drainage; upper valley sites have more granitic influence from Andean material",
        "vineyard_area_ha": 1000,
        "elevation_range": "100-800m",
        "key_grapes": ["Cabernet Sauvignon", "Syrah", "Carmenere", "Merlot"],
        "notes": "The Aconcagua Valley is home to the historic Errazuriz winery established in 1870 and produces powerful Cabernet Sauvignon from warm interior sites",
        "extra_facts": [
            "The Aconcagua Valley takes its name from the nearby Aconcagua mountain, the highest peak in the Western Hemisphere at 6,961 meters, which towers over the valley's vineyard landscape.",
            "Don Maximiano's vineyard, established by Errazuriz in 1870, is one of the oldest continuously producing premium vineyard sites in Chile, now home to the Don Maximiano Founder's Reserve wine.",
            "The Panquehue area in the Aconcagua Valley, where Errazuriz is located, has warm, dry conditions with alluvial soils that produce particularly powerful and concentrated Cabernet Sauvignon.",
        ],
    },
    {
        "name": "Casablanca Valley",
        "country": "Chile",
        "climate": "cool maritime with morning fog",
        "climate_details": "The Casablanca Valley is a cool-climate region strongly influenced by cold Pacific Ocean currents and morning fog; temperatures average 5-8 degrees Celsius cooler than the Central Valley due to direct exposure to ocean breezes through a gap in the Coastal Range",
        "soil_types": ["clay", "granite", "decomposed granite", "alluvial"],
        "soil_details": "Granite-derived and clay soils with moderate fertility; the cool conditions and clay soils contribute to naturally lower yields and concentrated flavors",
        "vineyard_area_ha": 4000,
        "elevation_range": "100-400m",
        "key_grapes": ["Sauvignon Blanc", "Chardonnay", "Pinot Noir", "Syrah"],
        "notes": "The Casablanca Valley was pioneered by Pablo Morandé in the mid-1980s and is recognized as Chile's first major cool-climate wine region, transforming the country's white wine reputation",
        "extra_facts": [
            "Casablanca Valley was first planted to vine in 1982 by Pablo Morandé, who recognized the potential of this cool, foggy area between Santiago and the port city of Valparaiso.",
            "Frost is a significant viticultural hazard in Casablanca Valley, with spring frosts occasionally damaging early-budding varieties; wind machines and heaters are used for protection.",
            "Casablanca Valley's success with cool-climate varieties inspired the exploration of other Chilean coastal areas, directly leading to the development of San Antonio/Leyda and coastal Colchagua.",
        ],
    },
    {
        "name": "San Antonio Valley",
        "country": "Chile",
        "climate": "cool maritime strongly influenced by the Pacific",
        "climate_details": "The San Antonio Valley and its Leyda subregion are located just 15 kilometers from the Pacific Ocean, making them among Chile's coolest wine regions; persistent ocean breezes and fog create an extended growing season ideal for aromatic white varieties and Pinot Noir",
        "soil_types": ["granite", "decomposed granite", "clay", "limestone"],
        "soil_details": "Decomposed granite and clay soils with pockets of limestone; the thin, well-drained soils naturally limit yields and concentrate flavors",
        "vineyard_area_ha": 2500,
        "elevation_range": "100-350m",
        "key_grapes": ["Sauvignon Blanc", "Pinot Noir", "Syrah", "Chardonnay"],
        "notes": "The Leyda subzone of San Antonio Valley has become one of Chile's most acclaimed cool-climate areas since its first plantings in 1998, producing vibrant Sauvignon Blanc and elegant Pinot Noir",
        "extra_facts": [
            "San Antonio Valley was developed as a wine region in the late 1990s, making it one of Chile's newest fine wine appellations.",
            "The proximity of San Antonio Valley vineyards to the Pacific Ocean means that average growing season temperatures are among the coolest in Chile, comparable to Burgundy or the Loire Valley.",
            "Leyda's vineyards were made possible by the construction of a pipeline to bring irrigation water from the Maipo River, as the area receives insufficient natural rainfall for viticulture.",
        ],
        "subregions": [
            {
                "name": "Leyda",
                "notes": "Leyda is a subzone of San Antonio Valley located approximately 15 kilometers from the Pacific coast, where cold Humboldt Current influence produces some of Chile's most aromatic and mineral-driven white wines",
                "key_grapes": ["Sauvignon Blanc", "Pinot Noir", "Chardonnay"],
            },
        ],
    },
    {
        "name": "Maipo Valley",
        "country": "Chile",
        "climate": "warm Mediterranean",
        "climate_details": "The Maipo Valley has a warm Mediterranean climate with hot dry summers, virtually no rainfall during the growing season, and mild winters; the Andes provide cooling at higher elevations in Alto Maipo while the lower valley near Santiago is warmer",
        "soil_types": ["alluvial", "gravel", "clay", "volcanic"],
        "soil_details": "Alluvial and gravelly soils from the Maipo River with pockets of volcanic material; Alto Maipo in the Andean foothills has rockier, well-drained soils at higher elevation that produce more structured wines",
        "vineyard_area_ha": 10000,
        "elevation_range": "300-800m",
        "key_grapes": ["Cabernet Sauvignon", "Carmenere", "Merlot", "Syrah"],
        "notes": "The Maipo Valley is considered Chile's Cabernet Sauvignon capital, centered around Santiago, and home to some of the country's oldest and most prestigious wineries including Concha y Toro, Santa Rita, and Almaviva",
        "extra_facts": [
            "The Maipo Valley has been Chile's most important wine region since the 19th century, benefiting from its proximity to Santiago and the concentration of historic estates (fundos) in the area.",
            "Puente Alto, at the eastern edge of Santiago in the Alto Maipo zone, is the home of Chile's three most celebrated Cabernet Sauvignon wines: Almaviva, Don Melchor, and Vinedo Chadwick.",
            "The gravel and stone-rich soils of Alto Maipo are comparable to the Graves region in Bordeaux, providing excellent drainage and moderate water stress that concentrates flavors in Cabernet Sauvignon.",
            "Buin, in the central Maipo Valley, is home to many of Chile's largest wine producers and has traditionally been the center of the country's bulk wine production.",
        ],
        "subregions": [
            {
                "name": "Alto Maipo",
                "elevation_range": "600-800m",
                "notes": "Alto Maipo in the Andean foothills east of Santiago produces Chile's most structured and age-worthy Cabernet Sauvignon from rocky, well-drained soils at high elevation",
                "key_grapes": ["Cabernet Sauvignon", "Carmenere"],
            },
        ],
    },
    {
        "name": "Rapel Valley",
        "country": "Chile",
        "climate": "warm Mediterranean",
        "climate_details": "The Rapel Valley has a warm Mediterranean climate moderated by Pacific breezes that funnel through gaps in the Coastal Range; the valley encompasses two major subregions, Cachapoal and Colchagua, which together form Chile's largest premium red wine zone",
        "soil_types": ["alluvial", "clay", "gravel", "volcanic"],
        "soil_details": "Alluvial soils on the valley floor with clay and volcanic soils on the hillsides; Colchagua has particularly varied terrain from coastal granite to interior alluvial plains",
        "vineyard_area_ha": 30000,
        "elevation_range": "100-600m",
        "key_grapes": ["Carmenere", "Cabernet Sauvignon", "Syrah", "Merlot"],
        "notes": "The Rapel Valley, particularly Colchagua, is considered the heartland of Chilean Carmenere and has been one of the country's most dynamic wine regions since the 1990s",
        "extra_facts": [
            "Colchagua Valley's Apalta district is one of Chile's most prestigious vineyard areas, producing rich, concentrated red wines from Carmenere, Cabernet Sauvignon, and Syrah.",
            "The Marchigue area in western Colchagua has a cooler microclimate due to proximity to the Pacific, producing more elegant, aromatic wines than the warmer central valley zones.",
            "The Rapel Valley encompasses approximately 30,000 hectares of vineyards, making it one of Chile's largest premium wine-producing zones.",
        ],
        "subregions": [
            {
                "name": "Cachapoal Valley",
                "notes": "The Cachapoal Valley in the northern part of Rapel is warmer and known for powerful Cabernet Sauvignon and Carmenere from alluvial soils near the Andes",
                "key_grapes": ["Cabernet Sauvignon", "Carmenere", "Merlot"],
            },
            {
                "name": "Colchagua Valley",
                "notes": "The Colchagua Valley is Chile's most recognized export wine region, producing bold reds from Carmenere, Cabernet Sauvignon, and Syrah across a wide range of terroirs from coastal to Andean",
                "key_grapes": ["Carmenere", "Cabernet Sauvignon", "Syrah", "Malbec"],
            },
        ],
    },
    {
        "name": "Curico Valley",
        "country": "Chile",
        "climate": "Mediterranean with moderate temperatures",
        "climate_details": "The Curico Valley has a temperate Mediterranean climate with a wide range of mesoclimates from the cool western slopes near the coast to warmer sites in the interior; rainfall is moderate at around 700mm annually",
        "soil_types": ["alluvial", "clay", "volcanic", "gravel"],
        "soil_details": "Alluvial soils from the Teno and Lontue rivers dominate the central valley; clay and volcanic soils on hillsides provide natural water retention",
        "vineyard_area_ha": 19000,
        "elevation_range": "100-500m",
        "key_grapes": ["Cabernet Sauvignon", "Sauvignon Blanc", "Merlot", "Carmenere", "Chardonnay"],
        "notes": "Curico Valley is historically significant as the site of Miguel Torres' first Chilean winery established in 1979, which helped spark the modern era of Chilean wine by introducing international winemaking techniques",
        "extra_facts": [
            "Miguel Torres' decision to establish his Chilean operation in Curico in 1979 brought temperature-controlled fermentation, small French oak barrel aging, and other modern techniques that transformed Chilean winemaking.",
            "The Lontue and Teno sub-valleys within Curico offer different mesoclimates, with Lontue being warmer and more suited to reds while Teno is cooler and produces better white wines.",
        ],
    },
    {
        "name": "Maule Valley",
        "country": "Chile",
        "climate": "Mediterranean transitioning to cooler influence",
        "climate_details": "The Maule Valley has a Mediterranean climate with increasing rainfall compared to regions further north; cooler temperatures and higher humidity support a longer growing season and contribute to wines with freshness and moderate alcohol",
        "soil_types": ["clay", "volcanic", "granite", "alluvial", "sand"],
        "soil_details": "Diverse soils including volcanic-derived clays, granitic decomposition in the coastal zones, and alluvial deposits in the central plain; many old-vine vineyards are on unirrigated dryland soils",
        "vineyard_area_ha": 30000,
        "elevation_range": "100-400m",
        "key_grapes": ["Pais", "Cabernet Sauvignon", "Carmenere", "Carignan", "Malbec", "Sauvignon Blanc"],
        "notes": "The Maule Valley is Chile's largest wine region by area and contains the highest concentration of old-vine Pais (Listan Prieto), Carignan, and Cinsault plantings, many dating to the 19th century and cultivated as dry-farmed bush vines",
        "extra_facts": [
            "The Maule Valley is increasingly recognized as Chile's most important region for authentic, terroir-driven wines from heritage grape varieties, challenging the dominance of the Central Valley's international varieties.",
            "Dry-farmed old-vine vineyards in the secano costero (coastal dryland) and secano interior (interior dryland) of Maule produce some of Chile's most distinctive and characterful wines.",
            "The Cauquenes area in Maule is the center of Chile's old-vine Carignan production, where the VIGNO consortium has established quality standards for this heritage variety.",
            "Maule Valley's vast size encompasses a wide range of mesoclimates, from the warm, dry interior where Cabernet Sauvignon thrives to the cooler, wetter coastal zones where old-vine Pais and Cinsault are revered.",
        ],
    },
    {
        "name": "Itata Valley",
        "country": "Chile",
        "climate": "Mediterranean with significant rainfall",
        "climate_details": "The Itata Valley has a cooler, wetter Mediterranean climate than the Central Valley with 1000-1200mm of annual rainfall; this higher moisture allows dry-farming without irrigation, supporting old bush vines that have been cultivated for centuries",
        "soil_types": ["granite", "clay", "sand", "volcanic"],
        "soil_details": "Granitic and sandy soils predominate, particularly in the coastal zone; the naturally poor, well-drained soils combined with dry-farming produce low-yielding, concentrated old vines",
        "vineyard_area_ha": 8000,
        "elevation_range": "50-400m",
        "key_grapes": ["Pais", "Cinsault", "Muscat of Alexandria", "Semillon"],
        "notes": "The Itata Valley is one of Chile's oldest wine regions with vines dating to the Spanish colonial era; it is at the center of Chile's natural wine and old-vine revival movement, with dry-farmed Pais, Cinsault, and Muscat bush vines",
        "extra_facts": [
            "Itata Valley's winemaking tradition predates the introduction of French varieties to Chile, with Pais and Muscat vines planted by Spanish Jesuits in the 16th century still producing fruit today.",
            "The natural wine movement in Chile has focused heavily on Itata's old bush vines, with producers like Leonardo Erazo (A Los Viñateros Bravos) crafting minimal-intervention wines that express the valley's ancient viticultural heritage.",
            "Itata Valley's granitic soils produce wines with a distinctive mineral character and natural acidity that is uncommon in warmer Chilean regions further north.",
        ],
    },
    {
        "name": "Bio-Bio Valley",
        "country": "Chile",
        "climate": "cool with high rainfall",
        "climate_details": "The Bio-Bio Valley is one of Chile's coolest wine regions with over 1200mm of annual rainfall; the cooler temperatures and longer growing season are well suited to aromatic white varieties and cool-climate reds",
        "soil_types": ["clay", "volcanic", "sand", "alluvial"],
        "soil_details": "Volcanic-derived clay soils with sandy alluvial deposits along the Bio-Bio River; the higher rainfall means irrigation is not necessary in most vineyards",
        "vineyard_area_ha": 4000,
        "elevation_range": "50-400m",
        "key_grapes": ["Riesling", "Gewurztraminer", "Pinot Noir", "Muscat", "Chardonnay"],
        "notes": "The Bio-Bio Valley is Chile's primary source of Germanic aromatic white varieties, with Riesling and Gewurztraminer performing particularly well in the cool, wet conditions",
        "extra_facts": [
            "The Bio-Bio Valley marks the transition between Chile's Mediterranean climate wine regions to the north and the temperate, high-rainfall regions to the south.",
            "Bio-Bio's cool, wet conditions make it one of the few Chilean wine regions where fungal diseases like botrytis and downy mildew are significant viticultural challenges.",
            "The Mulchen area in Bio-Bio province produces some of Chile's finest Riesling, with the cool climate and long growing season developing intense acidity and aromatic complexity.",
        ],
    },
    {
        "name": "Malleco Valley",
        "country": "Chile",
        "climate": "cool, wet, with strong maritime influence",
        "climate_details": "The Malleco Valley is Chile's southernmost established wine region at approximately 38 degrees south latitude with high rainfall exceeding 1300mm annually and cool average temperatures that push the limits of grape ripening",
        "soil_types": ["volcanic", "clay", "alluvial"],
        "soil_details": "Volcanic soils with clay and alluvial deposits; the high rainfall and clay content create challenging drainage conditions",
        "vineyard_area_ha": 500,
        "elevation_range": "100-400m",
        "key_grapes": ["Pinot Noir", "Chardonnay", "Riesling"],
        "notes": "The Malleco Valley is a pioneering cool-climate frontier region in Chile, first planted to vine by Viña Aquitania in the late 1990s to explore the limits of Chilean cool-climate viticulture",
        "extra_facts": [
            "Traiguén in the Malleco Valley was the site of Viña Aquitania's experimental Pinot Noir plantings that demonstrated Chile could produce quality wine at latitudes previously considered too cold.",
            "The Malleco Valley is part of Chile's Araucania region, traditionally known for agriculture and forestry rather than viticulture, and represents the frontier of Chilean wine exploration.",
        ],
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Grape Varieties
# ═══════════════════════════════════════════════════════════════════════════════

GRAPE_VARIETY_DATABASE = [
    # Argentina
    {
        "name": "Malbec",
        "country": "Argentina",
        "area_ha": 43000,
        "type": "red",
        "origin": "Originally from Cahors in southwestern France, Malbec was brought to Argentina in 1853 by French agronomist Michel Pouget at the request of President Domingo Faustino Sarmiento",
        "characteristics": "Argentine Malbec produces deep-colored, full-bodied wines with flavors of plum, black cherry, violet, and chocolate; at higher altitudes the wines develop more floral aromatics, firmer tannins, and brighter acidity",
        "altitude_notes": "Malbec is uniquely responsive to altitude in Argentina: below 800m it produces softer, fruitier wines; at 900-1100m in Lujan de Cuyo it shows classic structure; above 1200m in Valle de Uco and Salta it develops intense color, floral notes, and mineral complexity",
        "regions": ["Mendoza", "Salta", "Patagonia", "San Juan"],
        "facts": [
            "Argentina is the world's largest producer of Malbec with approximately 43,000 hectares planted, more than all other countries combined.",
            "The original Malbec cuttings were imported to Argentina from France in 1853 by Michel Pouget at the Quinta Normal agricultural school in Mendoza.",
            "April 17 is celebrated as World Malbec Day, commemorating the date in 1853 when President Sarmiento formally commissioned the project to bring French grape varieties to Argentina.",
            "Argentine Malbec vines planted before the phylloxera devastation are grown on their own rootstock, as phylloxera has had limited impact in Argentina's sandy soils.",
            "At elevations above 1200 meters in Valle de Uco, Malbec develops thicker skins due to intense UV radiation, producing wines with deeper color and higher polyphenol concentration.",
            "Argentine Malbec is characteristically deep purple in color with blue-violet reflections, distinguishing it visually from the darker, more tannic Malbec (Cot) of Cahors in France.",
            "Malbec in Mendoza's Lujan de Cuyo at 900-1100 meters produces ripe, round wines with plum and dark cherry fruit, while at 1300+ meters in Valle de Uco it shows more floral, herbal, and mineral character.",
            "Argentina's Malbec boom began in the late 1990s when international critics highlighted the variety's unique expression at altitude, leading to a surge in planting and foreign investment.",
        ],
    },
    {
        "name": "Torrontes",
        "country": "Argentina",
        "area_ha": 8000,
        "type": "white",
        "origin": "Torrontes is a natural cross between the Mission grape (Criolla Chica/Listan Prieto) and Muscat of Alexandria that occurred spontaneously in Argentina during the colonial era",
        "characteristics": "Torrontes produces highly aromatic white wines with intense floral notes of rose petal, jasmine, and geranium, along with citrus and stone fruit flavors; the best examples balance this aromatic intensity with crisp acidity",
        "regions": ["Salta", "La Rioja (Argentina)", "Mendoza"],
        "facts": [
            "There are three distinct Torrontes varieties in Argentina: Torrontes Riojano (the most widely planted and highest quality), Torrontes Sanjuanino, and Torrontes Mendocino.",
            "Torrontes Riojano is considered Argentina's signature white grape and reaches its highest expression in the high-altitude vineyards of Cafayate in Salta province at 1700 meters elevation.",
            "DNA analysis has confirmed that Torrontes is a natural cross between Listan Prieto (Mission grape) and Muscat of Alexandria, making it a uniquely Argentine grape variety.",
            "Torrontes is often compared to Muscat and Gewurztraminer for its aromatic intensity but is typically vinified dry with crisp acidity to balance its exuberant perfume.",
            "Torrontes is best consumed young, as it loses its distinctive aromatic freshness with age and does not generally benefit from oak aging.",
            "The high-altitude desert conditions of Cafayate (1700m) preserve Torrontes' natural acidity while maximizing its aromatic potential through intense UV exposure and cool night temperatures.",
        ],
    },
    {
        "name": "Bonarda",
        "country": "Argentina",
        "area_ha": 18000,
        "type": "red",
        "origin": "Argentine Bonarda is genetically identified as Douce Noir (also known as Charbono in California), a grape originating from the Savoie region of France, distinct from Italian Bonarda varieties",
        "characteristics": "Argentine Bonarda produces deeply colored, medium-bodied wines with flavors of dark plum, cherry, and spice; it is versatile, used both for everyday wines and increasingly for premium bottlings",
        "regions": ["Mendoza", "San Juan"],
        "facts": [
            "Bonarda is Argentina's second most-planted red grape variety after Malbec with approximately 18,000 hectares under vine.",
            "Argentine Bonarda has been genetically identified as Douce Noir from France's Savoie region, not related to the Italian grape varieties also called Bonarda.",
            "Bonarda was historically used primarily for blending and bulk wine in Argentina but has gained recognition as a varietal wine since the early 2000s.",
            "The best Argentine Bonarda comes from old vines in Lujan de Cuyo and Maipu, where reduced yields produce concentrated wines with velvety tannins and dark fruit character.",
        ],
    },
    {
        "name": "Criolla Grande",
        "country": "Argentina",
        "area_ha": 14000,
        "type": "pink",
        "origin": "Criolla Grande is a cross between Listan Prieto (Mission grape) and Muscat of Alexandria that arose during the colonial period in Argentina",
        "characteristics": "Criolla Grande is a pink-skinned grape traditionally used for basic table wine and grape juice production; it produces high-yielding, light-colored wines with neutral flavor",
        "regions": ["Mendoza", "San Juan"],
        "facts": [
            "Criolla Grande was historically Argentina's most widely planted grape variety but has declined significantly as growers replaced it with Malbec and international varieties.",
            "Criolla Grande is a natural cross between Listan Prieto and Muscat of Alexandria, the same parentage as Torrontes, making the two varieties genetic siblings.",
        ],
    },
    {
        "name": "Pedro Gimenez",
        "country": "Argentina",
        "area_ha": 12000,
        "type": "white",
        "origin": "Pedro Gimenez is a white grape variety widely planted in Argentina that is genetically distinct from Spain's Pedro Ximenez despite the similar name",
        "characteristics": "Pedro Gimenez is primarily used for bulk white wine production and grape must concentrate in Argentina; it produces neutral, high-yielding white wines",
        "regions": ["Mendoza", "San Juan"],
        "facts": [
            "Pedro Gimenez is one of the most planted white grape varieties in Argentina despite having almost no varietal reputation, as it is used primarily for bulk wine and grape concentrate production.",
            "Despite the similar name, Argentine Pedro Gimenez has been confirmed by DNA analysis to be genetically distinct from Spain's Pedro Ximenez (Sherry grape).",
        ],
    },
    {
        "name": "Cereza",
        "country": "Argentina",
        "area_ha": 11000,
        "type": "pink",
        "origin": "Cereza is a pink-skinned grape variety widely cultivated in Argentina's warmer regions for high-volume production",
        "characteristics": "Cereza is a high-yielding, pink-skinned variety used primarily for basic table wine and grape concentrate in Argentina's warmer eastern regions",
        "regions": ["Mendoza", "San Juan"],
        "facts": [
            "Cereza (meaning 'cherry' in Spanish for its pinkish skin) is one of Argentina's most planted grape varieties by area, grown primarily in the warm eastern zones of Mendoza and San Juan for bulk wine production.",
        ],
    },
    # Chile
    {
        "name": "Carmenere",
        "country": "Chile",
        "area_ha": 10000,
        "type": "red",
        "origin": "Carmenere originated in Bordeaux's Medoc region where it was one of the six original Bordeaux varieties before being virtually wiped out by phylloxera in the late 19th century",
        "characteristics": "Chilean Carmenere produces medium to full-bodied wines with distinctive flavors of red bell pepper, black cherry, plum, dark chocolate, and spice; it requires a long growing season to achieve full phenolic ripeness and avoid herbaceous green pepper notes",
        "regions": ["Rapel Valley", "Maipo Valley", "Maule Valley"],
        "facts": [
            "Carmenere was rediscovered in Chile in 1994 by French ampelographer Jean-Michel Boursiquot, who identified that vines previously classified as Merlot in Chilean vineyards were in fact Carmenere.",
            "Chile is the world's largest producer of Carmenere with approximately 10,000 hectares planted, more than all other countries combined.",
            "Carmenere was officially recognized as Chile's signature grape variety and was adopted as a distinct variety in Chilean wine regulations following its 1994 identification.",
            "Before its rediscovery in Chile, Carmenere was considered virtually extinct after phylloxera destroyed most Bordeaux plantings in the late 19th century.",
            "Carmenere requires a longer growing season than Merlot to fully ripen, with harvest typically occurring 2-3 weeks later; insufficient ripeness produces the green pepper flavors that initially hampered its reputation.",
            "The DNA analysis that identified Carmenere in Chile was prompted by observations that some 'Merlot' vineyards ripened much later and had distinctive leaf shapes different from true Merlot.",
            "Carmenere was originally one of the six main grape varieties of Bordeaux alongside Cabernet Sauvignon, Merlot, Cabernet Franc, Petit Verdot, and Malbec before phylloxera devastated French vineyards.",
            "The Colchagua Valley in Chile's Rapel Valley has emerged as the premier region for Carmenere, with warm daytime temperatures and cooling Pacific breezes providing ideal conditions for full ripeness.",
        ],
    },
    {
        "name": "Pais",
        "country": "Chile",
        "area_ha": 9000,
        "type": "red",
        "origin": "Pais (also known as Listan Prieto or Mission grape) was brought to Chile by Spanish missionaries in the 16th century and was the dominant variety for over 400 years",
        "characteristics": "Pais produces light-bodied, pale-colored red wines with flavors of red cherry, herbs, and earth; modern winemakers are reviving it as a distinctive heritage variety, often vinifying it with minimal intervention",
        "regions": ["Maule Valley", "Itata Valley", "Bio-Bio Valley"],
        "facts": [
            "Pais (Listan Prieto) was the first Vitis vinifera grape planted in Chile, brought by Spanish missionaries in the 1550s, and remained Chile's most-planted variety until the late 20th century.",
            "Pais is genetically identical to California's Mission grape and Argentina's Criolla Chica, all descended from vines brought from Spain during colonial-era expansion.",
            "Many Pais vines in Chile's Maule and Itata valleys are over 100 years old, grown as ungrafted, dry-farmed bush vines (en vaso) on their own rootstock.",
            "The revival of Pais as a serious wine grape has been led by Chile's natural wine movement and producers like De Martino, Bouchon, and A Los Viñateros Bravos since the 2010s.",
            "Pais was traditionally vinified into pipeño, a rustic, unaged wine sold from clay vessels or plastic containers that is now being reclaimed as a legitimate artisanal wine style.",
            "In Chile, old-vine Pais is increasingly being vinified using carbonic maceration, producing light, aromatic, Beaujolais-like wines that showcase the variety's delicate fruit character.",
        ],
    },
    {
        "name": "Cabernet Sauvignon (Chile)",
        "country": "Chile",
        "area_ha": 40000,
        "type": "red",
        "origin": "Cabernet Sauvignon was introduced to Chile in the mid-19th century from Bordeaux during a wave of French vine imports before the phylloxera epidemic",
        "characteristics": "Chilean Cabernet Sauvignon is known for ripe fruit character, moderate tannins, and approachability; wines from Maipo Valley, especially Alto Maipo, achieve the greatest complexity and aging potential",
        "regions": ["Maipo Valley", "Rapel Valley", "Aconcagua Valley", "Curico Valley"],
        "facts": [
            "Cabernet Sauvignon is Chile's most widely planted grape variety with approximately 40,000 hectares under vine, representing about one-quarter of the country's total vineyard area.",
            "Chile imported Cabernet Sauvignon cuttings directly from Bordeaux in the 1850s-1860s, before phylloxera devastated European vineyards, preserving pre-phylloxera genetic material.",
            "The Maipo Valley, particularly the Alto Maipo subzone in the Andean foothills, is considered Chile's premier Cabernet Sauvignon terroir, producing the country's most age-worthy examples.",
            "Chile's pre-phylloxera Cabernet Sauvignon vines, imported directly from Bordeaux in the 1850s, represent some of the oldest Cabernet Sauvignon genetic material in the world.",
            "Chilean Cabernet Sauvignon is often blended with Carmenere and Merlot, reflecting its Bordeaux heritage, and the country's icon wines are typically Cabernet-based blends.",
        ],
    },
    {
        "name": "Sauvignon Blanc (Chile)",
        "country": "Chile",
        "area_ha": 15000,
        "type": "white",
        "origin": "Sauvignon Blanc was introduced to Chile from France and has become the country's leading white wine variety by reputation, particularly from cool-climate coastal regions",
        "characteristics": "Chilean Sauvignon Blanc from cool coastal regions like Casablanca, San Antonio, and Leyda produces vibrant wines with citrus, green herb, and mineral character reminiscent of Loire Valley styles",
        "regions": ["Casablanca Valley", "San Antonio Valley", "Limari Valley"],
        "facts": [
            "Chile's cool coastal valleys, particularly Casablanca, San Antonio/Leyda, and Limari, have established the country as a major source of high-quality Sauvignon Blanc since the 1990s.",
            "Prior to DNA testing, some Chilean vineyards labeled as Sauvignon Blanc were found to be planted with Sauvignon Vert (Sauvignonasse); modern plantings are verified true Sauvignon Blanc.",
            "Chile's Sauvignon Blanc from the Leyda subzone of San Antonio Valley is characterized by intense minerality and a saline, oyster shell character attributed to the proximity to the Pacific Ocean.",
        ],
    },
    {
        "name": "Cinsault",
        "country": "Chile",
        "area_ha": 3000,
        "type": "red",
        "origin": "Cinsault was brought to Chile from France in the 19th century and was historically blended or misidentified, but has been rediscovered as a heritage variety alongside Pais",
        "characteristics": "Chilean Cinsault from old vines produces light, aromatic, and fresh red wines with soft tannins; it is a key variety in Chile's old-vine and natural wine revival",
        "regions": ["Maule Valley", "Itata Valley", "Bio-Bio Valley"],
        "facts": [
            "Old-vine Cinsault in Chile's southern regions is often over 80 years old, dry-farmed as bush vines alongside Pais, and has become a fashionable variety among Chile's new generation of winemakers.",
            "Cinsault was historically undervalued in Chile and used for bulk wine, but the natural wine movement has elevated it as a source of elegant, light-bodied, and aromatic reds.",
        ],
    },
    {
        "name": "Carignan",
        "country": "Chile",
        "area_ha": 1000,
        "type": "red",
        "origin": "Carignan was brought to Chile's southern regions from France and Spain and is found primarily as old dry-farmed bush vines in the Maule Valley",
        "characteristics": "Old-vine Chilean Carignan produces deeply colored, concentrated wines with flavors of dark fruit, garrigue, and spice; the VIGNO consortium promotes single-vineyard old-vine Carignan from Maule",
        "regions": ["Maule Valley"],
        "facts": [
            "The VIGNO (Vignadores de Carignan) consortium was established in 2009 to promote and protect old-vine dry-farmed Carignan from Chile's Maule Valley, requiring vines to be at least 30 years old and dry-farmed.",
            "Old-vine Carignan in Chile's Maule Valley has become one of the country's most distinctive wine styles, with VIGNO producers like Gillmore, Garage Wine Co, and Undurraga leading the movement.",
        ],
    },
    # Additional minor varieties — Argentina
    {
        "name": "Cabernet Sauvignon (Argentina)",
        "country": "Argentina",
        "area_ha": 16000,
        "type": "red",
        "origin": "Cabernet Sauvignon was introduced to Argentina from France in the 19th century and is widely planted as both a varietal wine and a blending partner for Malbec",
        "characteristics": "Argentine Cabernet Sauvignon produces full-bodied wines with black currant, green pepper, and cedar notes; at altitude it develops concentrated fruit and firm tannins",
        "regions": ["Mendoza", "San Juan"],
        "facts": [
            "Cabernet Sauvignon is Argentina's second most-planted international red variety after Malbec, and Cabernet-Malbec blends are a common and well-regarded Argentine wine style.",
            "The Agrelo district in Lujan de Cuyo has become recognized as one of Argentina's best terroirs for Cabernet Sauvignon, producing structured, age-worthy wines from gravelly alluvial soils.",
        ],
    },
    {
        "name": "Syrah (Argentina)",
        "country": "Argentina",
        "area_ha": 12000,
        "type": "red",
        "origin": "Syrah was introduced to Argentina from France and has found an exceptional terroir in the hot, dry conditions of San Juan province",
        "characteristics": "Argentine Syrah ranges from the warm, generous, New World style of San Juan to cooler, more peppery expressions from higher altitude sites in Mendoza and Patagonia",
        "regions": ["San Juan", "Mendoza", "Patagonia"],
        "facts": [
            "San Juan province is considered Argentina's premier Syrah region, with the variety thriving in the hot, dry desert conditions and producing deeply colored, richly flavored wines.",
            "Syrah from the Pedernal Valley in San Juan at 1350-1500 meters elevation produces some of Argentina's most complex and mineral-driven expressions of the variety.",
        ],
    },
    {
        "name": "Pinot Noir (Chile and Argentina)",
        "country": "Chile",
        "area_ha": 4000,
        "type": "red",
        "origin": "Pinot Noir has been planted in South America's cooler regions since the late 20th century and has found success in Chile's Casablanca and San Antonio valleys and in Argentine Patagonia",
        "characteristics": "South American Pinot Noir from cool coastal and southern regions produces wines with red fruit character, silky tannins, and an approachable style, with the best examples showing increasing complexity",
        "regions": ["Casablanca Valley", "San Antonio Valley", "Patagonia", "Bio-Bio Valley"],
        "facts": [
            "Chile's Casablanca Valley and San Antonio/Leyda subzone have emerged as the country's primary Pinot Noir terroirs, with cool Pacific-influenced conditions ideal for the variety.",
            "Argentine Patagonia, particularly Rio Negro and Neuquen provinces, produces Pinot Noir with distinctive bright acidity and red fruit character from cool continental conditions.",
            "Pinot Noir plantings in both Chile and Argentina have expanded rapidly since the 2000s as producers seek out cooler sites suited to this demanding variety.",
        ],
    },
    {
        "name": "Chardonnay (Chile and Argentina)",
        "country": "Chile",
        "area_ha": 11000,
        "type": "white",
        "origin": "Chardonnay is widely planted across South American wine regions, with the finest examples coming from cooler sites in Chile's Limari and Casablanca valleys",
        "characteristics": "South American Chardonnay ranges from tropical, unoaked styles to complex, barrel-fermented wines with citrus, mineral, and toasty oak character",
        "regions": ["Limari Valley", "Casablanca Valley", "Mendoza"],
        "facts": [
            "Chile's Limari Valley has been recognized as one of the country's premier Chardonnay terroirs, with limestone soils and camanchaca fog creating conditions comparable to Burgundy's Chablis.",
            "Chardonnay is one of the most widely planted white varieties in South America, used for both still and sparkling wine production across multiple regions in Chile and Argentina.",
        ],
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Classification Systems
# ═══════════════════════════════════════════════════════════════════════════════

ARGENTINA_CLASSIFICATION = {
    "system_name": "Argentine Wine Classification System",
    "facts": [
        "Argentina's wine classification system includes three levels: DOC (Denominación de Origen Controlada), IG (Indicación Geográfica), and IP (Indicación de Procedencia), administered by the Instituto Nacional de Vitivinicultura (INV).",
        "Argentina has only two DOC designations: Lujan de Cuyo DOC (established 1993) and San Rafael DOC (established 1999), both in Mendoza province.",
        "The Lujan de Cuyo DOC was the first controlled appellation established in Argentina in 1993, requiring wines to be made from approved grape varieties grown in specified communes within the Lujan de Cuyo department.",
        "The San Rafael DOC was established in 1999 as Argentina's second controlled appellation, covering vineyards in the San Rafael department of southern Mendoza at 450-800 meters elevation.",
        "Argentina's IG (Indicación Geográfica) system identifies wines from specific geographic regions without the strict production controls of DOC, covering provinces, departments, and smaller geographic units.",
        "Argentina's IP (Indicación de Procedencia) is the broadest geographic designation, certifying only that grapes come from a recognized wine-producing area.",
        "The Instituto Nacional de Vitivinicultura (INV) is the Argentine government agency responsible for regulating the wine industry, including grape variety identification, labeling regulations, and geographic designations.",
        "Argentine wine labeling requires that a wine labeled with a single variety contain at least 85% of that variety, and wines labeled with a geographic indication must contain at least 85% of grapes from that area.",
        "Argentina uses a wine quality classification for age-dated wines: Reserva wines must be aged for at least one year (six months in oak for reds), and Gran Reserva wines require at least two years of aging (one year in oak for reds).",
        "The Argentine wine label term 'cosecha' refers to the vintage year, and wines labeled with a vintage must contain at least 85% of grapes harvested in that year.",
        "Argentina's wine law prohibits the use of the term 'champagne' for sparkling wines; Argentine sparkling wine is labeled as 'espumante' or 'espumoso'.",
        "The Mendoza DOC regulations for Lujan de Cuyo specify that wines must be made from vineyards within the department using approved grape varieties and meet minimum aging requirements.",
    ],
}

CHILE_CLASSIFICATION = {
    "system_name": "Chilean Wine Classification System",
    "facts": [
        "Chile's wine appellation system is based on the DO (Denominación de Origen) system established by Decree Law 464 of 1995 and updated in 2011 to include the transversal classification.",
        "Chile's DO system defines wine regions hierarchically from broadest to narrowest: Region (e.g., Central Valley), Subregion (e.g., Rapel Valley), Zone (e.g., Colchagua Valley), and Area (e.g., Marchigue).",
        "In 2011, Chile introduced a unique transversal classification system that divides wine regions from west to east into three categories: Costa (coastal influence), Entre Cordilleras (between the mountain ranges), and Andes (Andean influence).",
        "Chile's Costa designation identifies vineyard areas with direct Pacific Ocean influence, characterized by cool temperatures, fog, and maritime breezes that favor aromatic white varieties and cool-climate reds.",
        "Chile's Entre Cordilleras designation identifies the central valley floor between the Coastal Range and the Andes, the traditional and largest wine-producing zone with warm conditions ideal for full-bodied reds.",
        "Chile's Andes designation identifies vineyard areas in the Andean foothills with higher elevation, greater diurnal temperature variation, and rocky well-drained soils that produce structured, concentrated wines.",
        "Chile's transversal classification (Costa/Entre Cordilleras/Andes) can be combined with the traditional north-south DO system, allowing labels to specify both latitude and longitude influences on terroir.",
        "Chilean wine labeling requires that a wine labeled with a single variety contain at least 75% of that variety, and wines labeled with a DO must contain at least 75% of grapes from that region.",
        "The SAG (Servicio Agricola y Ganadero) is Chile's government agency responsible for wine regulations, DO certification, and vineyard registry.",
        "Chile is one of the few wine-producing countries that has remained free from phylloxera, attributed to its geographic isolation between the Andes, the Pacific Ocean, the Atacama Desert to the north, and Antarctic ice to the south.",
        "Because Chile is phylloxera-free, the vast majority of Chilean vineyards are planted on own-rooted ungrafted vines, which some winemakers argue contributes to the distinctive character of Chilean wines.",
        "Chilean wine labeling allows reserve-style designations such as 'Reserva', 'Gran Reserva', and 'Reserva Especial', though these terms are not legally regulated and their meaning varies by producer.",
        "Chile's wine regulations permit the use of the term 'Varietal' for wines containing at least 75% of the stated grape variety on the label.",
        "The Chilean DO system covers six major wine regions from north to south: Atacama, Coquimbo, Aconcagua, Valle Central, Sur, and Austral.",
        "Chile's Valle Central DO encompasses four subregions: Maipo Valley, Rapel Valley, Curico Valley, and Maule Valley, and produces the majority of Chile's commercial wine.",
        "The Aconcagua DO in Chile encompasses the Aconcagua Valley, Casablanca Valley, and San Antonio Valley, covering both warm interior and cool coastal wine zones.",
        "Chile's Coquimbo DO in the north includes the Elqui, Limari, and Choapa valleys, with viticulture extending into desert and semi-desert conditions.",
        "Chile's Sur DO covers the southern regions of Itata Valley, Bio-Bio Valley, and Malleco Valley, where rainfall is higher and cool-climate varieties excel.",
    ],
}


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Additional Terroir & Historical Facts
# ═══════════════════════════════════════════════════════════════════════════════

ARGENTINA_TERROIR_FACTS = [
    # Altitude viticulture
    "Argentina is the world's leading practitioner of high-altitude viticulture, with commercial vineyards planted from 500 meters to over 3000 meters above sea level.",
    "Altitude is the single most important terroir factor in Argentine viticulture, as each 150 meters of elevation gain reduces average temperature by approximately 1 degree Celsius.",
    "The Zuccardi winery's Finca Piedra Infinita vineyard in Altamira, Valle de Uco, is planted on ancient calcareous alluvial fan soils deposited by the Tunuyan River over millions of years.",
    "The concept of 'parajes' (specific vineyard sites) has emerged in Valle de Uco as producers identify distinct terroirs within the larger region, similar to the cru system in Burgundy.",
    "Altamira in the Uco Valley's San Carlos district has been recognized for its distinctive alluvial fan terroir with calcareous soils and large stones, producing Malbec with notable mineral complexity.",
    "Gualtallary in Tupungato, Valle de Uco, at approximately 1400 meters elevation, has calcareous and limestone soils that produce some of Argentina's most acclaimed terroir-driven Malbec.",
    "The Los Chacayes district in Tunuyan, Valle de Uco, features large rounded river stones over calcareous clay, producing Malbec with distinctive freshness and mineral notes.",
    "Vista Flores in Tunuyan, Valle de Uco, is planted at approximately 1050 meters elevation on alluvial soils and has attracted numerous premium producers since the early 2000s.",
    "The Paraje Altamira subregion was the first Argentine vineyard district to receive official geographic indication recognition within Valle de Uco in 2013.",
    "High-altitude vineyards in Argentina experience approximately 20% more UV radiation than sea-level sites, which triggers the production of anthocyanins and polyphenols in grape skins as a natural defense mechanism.",
    "The Zonda wind, a hot dry foehn wind that descends from the Andes, can rapidly raise temperatures in Mendoza by 10-15 degrees Celsius and reduce humidity, occasionally causing damage to vineyards during the growing season.",
    # Irrigation
    "Argentine viticulture relies almost entirely on irrigation from Andean snowmelt, delivered through a system of canals, ditches, and flood irrigation dating back to pre-Columbian Huarpe indigenous methods.",
    "The shift from flood irrigation to drip irrigation in Argentine vineyards since the 1990s has enabled precision viticulture and contributed significantly to quality improvement.",
    "The traditional Argentine irrigation system uses a network of canals and ditches (acequias) originally constructed by the indigenous Huarpe people before Spanish colonization.",
    "Water rights for vineyard irrigation in Mendoza are allocated through a regulated system managed by the Departamento General de Irrigacion, as water scarcity is the primary limiting factor for vineyard expansion.",
    # History
    "Argentine wine production began with Spanish missionaries planting vines in the Santiago del Estero and Mendoza regions in the mid-16th century.",
    "The arrival of European immigrants, particularly Italian, Spanish, and French settlers in the late 19th century, transformed Argentine viticulture by introducing international grape varieties and modern winemaking techniques.",
    "Argentina is the world's fifth-largest wine producer and the largest wine producer in South America.",
    "The completion of the transcontinental railroad between Buenos Aires and Mendoza in 1885 transformed Argentina's wine industry by enabling efficient transport of wine to the capital's growing population.",
    "Argentine wine consumption has declined from a peak of over 90 liters per capita in the 1970s to approximately 20 liters per capita in recent years, driving producers to focus on export markets and premium production.",
    "The 2001 economic crisis in Argentina and the resulting peso devaluation made Argentine wine significantly more competitive on international markets, helping launch the global Malbec boom.",
    "Catena Zapata's Nicolas Catena Zapata is widely credited as the pioneer of high-altitude Malbec in the 1990s, when he began planting vineyards at over 1000 meters in the Andes foothills.",
    # Wine styles
    "Argentina's signature wine style is high-altitude Malbec, distinguished from French Malbec (Cahors) by its riper fruit character, softer tannins, and violet floral aromatics.",
    "Argentine sparkling wine production, centered in Mendoza, uses both traditional method (metodo tradicional) and Charmat method, with Chardonnay and Pinot Noir as the primary varieties.",
    "Late harvest wines (cosecha tardia) are produced in several Argentine regions, with Torrontes and Semillon being the most common varieties for sweet wine production.",
    # Phylloxera
    "Argentina's sandy and alluvial soils have provided natural protection against phylloxera, and the majority of Argentine vineyards remain planted on ungrafted own-rooted vines.",
    "While phylloxera exists in some parts of Argentina, particularly in certain areas of Mendoza, the sandy soils and flood irrigation practices have limited its spread compared to other major wine-producing countries.",
    # Industry
    "Argentina's total vineyard area is approximately 215,000 hectares, making it the fifth-largest wine grape vineyard country in the world by area planted.",
    "The Instituto Nacional de Vitivinicultura (INV) reports that Argentina has approximately 860 registered wineries (bodegas), with the majority located in Mendoza province.",
    "Argentina exports wine to over 120 countries, with the United States, United Kingdom, Brazil, Canada, and the Netherlands as the primary export markets.",
    "The Wines of Argentina (WofA) organization, founded in 2003, promotes Argentine wine internationally and manages the 'Malbec World Day' campaign each April.",
    # Producers and wineries
    "Bodega Catena Zapata, founded by Nicola Catena in 1902, is one of Argentina's most prestigious wineries, known for pioneering high-altitude Malbec production under Nicolas Catena Zapata's leadership.",
    "Achaval-Ferrer was founded in 1998 and became one of the first Argentine wineries to focus on single-vineyard Malbec from specific terroirs in Mendoza, helping establish the concept of terroir-driven Argentine wine.",
    "Trapiche, one of Argentina's oldest wineries founded in 1883, produces over 20 million bottles annually and was instrumental in developing the Single Vineyard program highlighting individual terroirs.",
    "Zuccardi Valle de Uco, under the direction of third-generation winemaker Sebastian Zuccardi, was named the world's best vineyard in 2019, 2020, and 2021 by the World's Best Vineyards organization.",
    "Luigi Bosca, founded by the Arizu family in 1901, is one of the historic wineries of Lujan de Cuyo that helped establish the region as a premium wine area in the early 20th century.",
    "Bodega Colomé in Salta's Calchaqui Valley was established in 1831, making it one of the oldest continuously operating wineries in Argentina, and cultivates vineyards at up to 3111 meters elevation.",
    "The Hess Collection (Donald Hess) acquired Bodega Colomé in 2001 and invested in developing the extreme high-altitude vineyards in the Calchaqui Valley of Salta province.",
    "Kaiken, founded by Aurelio Montes (of Montes Chile fame) in 2001 in Mendoza, represents the growing trend of cross-border investment between Chilean and Argentine wine companies.",
    # Viticulture
    "The pergola (parral) training system was historically the dominant trellising method in Argentina, especially in warmer areas, providing shade to grapes and reducing sunburn.",
    "Modern Argentine viticulture has shifted increasingly from the traditional pergola system to vertical shoot positioning (VSP) trellising, which provides better canopy management and fruit exposure for premium wines.",
    "Argentina's vineyards are overwhelmingly planted on flat alluvial fans rather than hillsides, distinguishing the country's viticultural landscape from the steep-slope viticulture common in European wine regions.",
    # Winemaking
    "Argentine winemakers have increasingly embraced concrete eggs and amphorae for fermentation and aging, particularly for Malbec and white varieties, as alternatives to traditional oak barrels.",
    "The use of French oak barrels is standard for premium Argentine wines, though many producers have shifted to larger format barrels (500L and above) to minimize oak influence and emphasize terroir.",
    "Argentine winemakers commonly use cold maceration (maceracion en frio) before fermentation to extract color and fruit character from Malbec grapes without harsh tannins.",
    "Whole-cluster fermentation has gained popularity among Argentine winemakers seeking to add complexity and structure to high-altitude Malbec, particularly in Valle de Uco.",
    "Argentina's high-altitude wines naturally achieve concentrated flavors and deep color without the need for extended maceration, as the intense UV radiation at altitude promotes natural phenolic development in the vineyard.",
    "The production of orange wine (vino naranja) from skin-contact white wine fermentation has emerged in Argentina, with producers experimenting with Torrontes and other aromatic white varieties.",
    # Regional details
    "The Perdriel district in Lujan de Cuyo is one of Mendoza's most historic fine wine areas, with alluvial soils and vineyards at approximately 950 meters producing benchmark Malbec since the early 20th century.",
    "The Agrelo district in Lujan de Cuyo lies at approximately 980 meters elevation on alluvial soils with rounded river stones, and has become renowned for both Malbec and Cabernet Sauvignon.",
    "The Las Compuertas district in Lujan de Cuyo, at approximately 1050 meters elevation, is named after the irrigation gates (compuertas) that control water flow from the Mendoza River to the surrounding vineyards.",
    "The Vistalba district in Lujan de Cuyo features some of Mendoza's oldest Malbec vines, planted in the early 20th century on gravelly alluvial soils at approximately 1000 meters elevation.",
    "The San Pablo subdistrict in Tupungato, Valle de Uco, at elevations exceeding 1400 meters, represents one of the emerging frontier areas for extreme-altitude viticulture in Argentina.",
    "The Paraje Altamira alluvial fan in San Carlos, Valle de Uco, features large calcareous stones and mineral-rich soils deposited by the Tunuyan River over millions of years, producing distinctively mineral Malbec.",
    "Mendoza's southern department of San Rafael, home to one of only two Argentine DOCs, produces wines at 450-800 meters elevation from Malbec, Cabernet Sauvignon, and Chenin Blanc.",
    "The Barrancas district in eastern Maipu is known for old-vine Malbec and Bonarda planted on sandy loam soils, producing generous, fruit-forward wines.",
    # Wine tourism
    "Mendoza is Argentina's premier wine tourism destination, with over 1.5 million wine tourists visiting the region annually to experience vineyard tours, tastings, and gourmet dining.",
    "The Wine Route of Mendoza (Caminos del Vino) connects over 150 wineries across Lujan de Cuyo, Maipu, and Valle de Uco, making it one of the most developed wine tourism circuits in South America.",
]

CHILE_TERROIR_FACTS = [
    # Geography
    "Chile's wine regions stretch over 1300 kilometers from north to south, from the Atacama Desert at 27 degrees south to Malleco at 38 degrees south latitude.",
    "Chile's unique geography as a narrow strip between the Andes and the Pacific Ocean creates enormous mesoclimatic diversity over short distances from coast to mountains.",
    "The Humboldt Current (Peru Current) flows northward along Chile's Pacific coast, bringing cold Antarctic water that significantly cools coastal wine regions and creates the fog (camanchaca) that moderates temperatures in valleys like Casablanca and Limari.",
    "Chile's Coastal Range (Cordillera de la Costa) acts as a barrier between the cool Pacific influence and the warmer Central Valley, creating distinct climate zones that form the basis of the transversal classification system.",
    "The Central Valley (Valle Central) between Chile's Coastal Range and the Andes is the country's largest and most productive wine zone, with warm, dry conditions ideal for Cabernet Sauvignon, Carmenere, and Merlot.",
    "Chile's wine country lies between approximately 30 and 38 degrees south latitude, comparable in the Northern Hemisphere to the wine regions of North Africa and southern Spain.",
    "The rain shadow effect of the Andes creates Chile's arid northern wine regions, while the southern regions receive progressively more rainfall, creating a natural continuum from desert to temperate conditions.",
    "Chile's extremely narrow width, averaging only 175 kilometers between the Andes and the Pacific, means that vineyards can experience radically different climates within a very short east-west distance.",
    # History
    "Modern Chilean wine history began in the 1850s when Silvestre Ochagavia and other Chilean landowners imported noble French grape varieties from Bordeaux, establishing the foundation of Chile's fine wine industry.",
    "The arrival of Spanish winemaker Miguel Torres in 1979, who established a winery in Curico Valley and introduced stainless steel fermentation and cold temperature control, is considered a pivotal moment in Chile's modern wine revolution.",
    "Chile's wine export boom began in the 1990s, driven by political stability after the return to democracy in 1990, foreign investment, and the production of affordable, fruit-forward varietal wines.",
    "French winemaker Baron Philippe de Rothschild formed a joint venture with Concha y Toro in 1997 to create Almaviva, one of Chile's first icon wines and a symbol of the country's premium wine ambitions.",
    "The Robert Mondavi and Eduardo Chadwick partnership to create Sena in the Aconcagua Valley in 1995 was a landmark joint venture that demonstrated Chile's potential for world-class red blends.",
    "The Berlin Tasting of 2004, organized by Eduardo Chadwick, blind-tasted top Chilean wines against Bordeaux first growths and Tuscan wines, resulting in Chilean wines ranking at the top and transforming international perceptions of Chilean wine quality.",
    # Old vines
    "Chile's southern regions, particularly Maule, Itata, and Bio-Bio, contain some of the oldest continuously producing Vitis vinifera vineyards in the Americas, with Pais and Muscat vines dating to the 17th century.",
    "The secano interior (unirrigated interior) of Chile's Maule and Itata valleys supports dry-farmed bush vines on granitic soils, producing low yields and concentrated wines from heritage varieties.",
    "Chile's old-vine heritage includes Pais (Listan Prieto) plantings that predate the introduction of French varieties, representing an unbroken viticultural tradition stretching back to the 1550s.",
    # Industry
    "Chile is the world's fourth-largest wine exporter by volume and the largest wine producer in South America after Argentina.",
    "Chile's wine industry has increasingly embraced sustainability, with the Wines of Chile Sustainability Code launched in 2011 covering environmental, social, and economic criteria.",
    "Chile's total vineyard area is approximately 140,000 hectares, with red varieties accounting for roughly 75% of total plantings.",
    "Chile exports wine to over 150 countries, with China, the United States, the United Kingdom, Japan, and Brazil as the primary export destinations.",
    "The Wines of Chile (Vinos de Chile) trade organization represents over 90% of Chile's bottled wine exports and promotes Chilean wine internationally.",
    "Chile has approximately 300 commercial wineries, ranging from large-volume producers like Concha y Toro (the largest wine company in South America) to small artisanal operations.",
    "Concha y Toro, founded in 1883, is the largest wine company in South America and one of the ten largest wine companies globally by sales volume.",
    # Winemaking
    "Chile's climate allows for extremely consistent vintages compared to most Old World wine regions, with less vintage variation due to the reliably dry, warm growing seasons in most regions.",
    "Organic and biodynamic viticulture has grown significantly in Chile since the 2000s, aided by the country's dry climate, geographic isolation, and low disease pressure.",
    # Producers and wineries
    "Concha y Toro, founded by Don Melchor Concha y Toro in 1883, is the largest wine company in Latin America and one of the world's largest wine brands, best known for its Casillero del Diablo and Don Melchor labels.",
    "Almaviva, the joint venture between Baron Philippe de Rothschild and Concha y Toro, produces a single Bordeaux-style blend from Puente Alto that is considered one of Chile's top icon wines.",
    "Sena, the collaboration between Eduardo Chadwick of Errazuriz and Robert Mondavi (now fully owned by Chadwick), was one of Chile's first icon wines and helped establish the country's fine wine credentials internationally.",
    "Vinedo Chadwick, formerly known as the Chadwick family's polo field in Puente Alto, produces a single Cabernet Sauvignon that topped the Berlin Tasting of 2004 against Bordeaux first growths.",
    "Montes was founded in 1988 by Aurelio Montes, Douglas Murray, Alfredo Vidaurre, and Pedro Grand, and was one of the first Chilean wineries to focus exclusively on premium wines for export.",
    "Errazuriz, founded by Don Maximiano Errazuriz in 1870 in the Aconcagua Valley, is one of Chile's oldest wineries and produces the iconic Max Reserva and Don Maximiano Founder's Reserve wines.",
    "Santa Rita, founded in 1880 in the Maipo Valley, is one of Chile's historic wine estates, known for the Casa Real Cabernet Sauvignon and for housing the famous wine cellar where 120 soldiers reportedly hid during Chile's independence war.",
    "Lapostolle, founded by the Marnier-Lapostolle family (owners of Grand Marnier) in 1994, introduced biodynamic viticulture to Chile and produces the acclaimed Clos Apalta from the Colchagua Valley.",
    "De Martino, founded by Italian immigrant Pietro De Martino in 1934, has been at the forefront of Chile's old-vine and terroir-driven wine movement, producing acclaimed Pais, Cinsault, and Carignan from heritage vineyards.",
    "Garage Wine Co, founded by Derek Mossman Knapp in 2001, pioneered the movement to make small-lot wines from old dry-farmed vineyards in Maule, Itata, and other southern Chilean regions.",
    # Viticulture
    "Chile's viticultural landscape is dominated by drip irrigation in the northern and central regions, while the southern regions of Maule, Itata, and Bio-Bio support dry-farmed (secano) vineyards due to higher rainfall.",
    "The devastating earthquake of 2010 (magnitude 8.8) struck Chile's wine heartland, destroying millions of liters of wine in barrel and damaging numerous wineries in the Maule, Bio-Bio, and Rapel valleys.",
    "Chile's wine regions are susceptible to occasional El Nino events, which bring warmer temperatures and altered rainfall patterns that can significantly affect vintage quality.",
    # Winemaking
    "Chilean winemaking has evolved from a reliance on large rauli (native beech) wood vats and extended oxidative aging to modern temperature-controlled stainless steel and French oak barrel techniques.",
    "The use of concrete tanks for fermentation has seen a revival in Chile, with many premium producers preferring concrete's neutral flavor contribution and gentle temperature management.",
    "Chilean icon wines such as Almaviva, Don Melchor, Sena, and Clos Apalta typically command prices comparable to top Bordeaux classified growths and are among the most collected South American wines.",
    "Chile's red wine production is dominated by Bordeaux varieties (Cabernet Sauvignon, Merlot, Carmenere, Cabernet Franc) reflecting the country's 19th-century French viticultural heritage.",
    "Chilean white winemaking has been transformed by the development of cool coastal regions since the 1990s, moving from neutral, warm-climate whites to vibrant, aromatic wines that compete with top European examples.",
    "The concept of 'vino de autor' (author's wine) has become popular in Chile, referring to small-production, terroir-driven wines made by individual winemakers rather than large corporate operations.",
    # Regional details
    "Chile's Pisco-producing region in the north (Atacama and Coquimbo) overlaps with the wine-producing regions, and some valleys like Elqui produce both Pisco and table wine.",
    "The Apalta vineyard in Colchagua Valley is a natural amphitheater surrounded by hills, creating a warm microclimate that produces some of Chile's most concentrated and powerful red wines.",
    "Coastal Colchagua (Paredones, Lolol) has emerged as a cool-climate extension of the traditionally warm Colchagua Valley, producing Syrah and Pinot Noir with greater freshness and lower alcohol.",
    "The Alto Cachapoal subzone in the Rapel Valley features vineyards at the foot of the Andes at 500-700 meters elevation, producing structured Cabernet Sauvignon with pronounced mineral character.",
    "Chile's Central Valley (Valle Central) between the two mountain ranges has deep, fertile alluvial soils that produce the majority of the country's high-volume commercial wines.",
    "The Isla de Maipo (Island of Maipo) is a prestigious vineyard area within the Maipo Valley where the Maipo River creates a distinct terroir of deep alluvial gravel soils.",
    # Wine tourism
    "Chile's wine tourism industry has grown rapidly since the 2000s, with the Colchagua Valley Wine Route and Casablanca Valley becoming major tourist destinations from Santiago.",
    "The Ruta del Vino de Colchagua (Colchagua Wine Route) is Chile's most developed wine tourism circuit, featuring over 20 wineries, the Colchagua Museum, and a historic wine train.",
    "Santa Cruz in the Colchagua Valley has become Chile's de facto wine tourism capital, with the Museo de Colchagua, Hotel Santa Cruz Plaza, and numerous tasting rooms attracting visitors.",
]


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
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
    """Register and return the source ID."""
    return ensure_source(
        name=SOURCE["name"],
        url=SOURCE["url"],
        source_type=SOURCE["source_type"],
        tier=SOURCE["tier"],
        language=SOURCE["language"],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# FACT BUILDERS — Argentina
# ═══════════════════════════════════════════════════════════════════════════════


def _build_argentina_facts(source_id: str) -> list[dict]:
    """Build facts about Argentine wine regions, altitude terroir, and history."""
    facts = []

    for region in ARGENTINA_REGIONS:
        name = region["name"]
        entities = [{"type": "region", "name": name}, {"type": "country", "name": "Argentina"}]
        base_tags = ["argentina", name.lower().replace(" ", "_").replace("(", "").replace(")", "")]

        # Climate
        facts.append(_make_fact(
            f"The {name} wine region in Argentina has a {region['climate']} climate.",
            domain="wine_regions",
            source_id=source_id,
            subdomain="south_america_argentina",
            entities=entities,
            tags=base_tags + ["climate"],
        ))

        if region.get("climate_details"):
            facts.append(_make_fact(
                f"{region['climate_details']}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="south_america_argentina",
                entities=entities,
                tags=base_tags + ["climate"],
            ))

        # Soil
        if region.get("soil_types"):
            soil_list = ", ".join(region["soil_types"])
            facts.append(_make_fact(
                f"The predominant soil types in {name}, Argentina include {soil_list}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="south_america_argentina",
                entities=entities,
                tags=base_tags + ["soil", "terroir"],
            ))

        if region.get("soil_details"):
            facts.append(_make_fact(
                f"{region['soil_details']}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="south_america_argentina",
                entities=entities,
                tags=base_tags + ["soil", "terroir"],
            ))

        # Elevation
        if region.get("elevation_range"):
            facts.append(_make_fact(
                f"Vineyards in {name}, Argentina are planted at elevations ranging from {region['elevation_range']}.",
                domain="viticulture",
                source_id=source_id,
                subdomain="altitude_viticulture",
                entities=entities,
                tags=base_tags + ["elevation", "altitude"],
            ))

        # Vineyard area
        if region.get("vineyard_area_ha"):
            facts.append(_make_fact(
                f"The {name} wine region in Argentina has approximately {region['vineyard_area_ha']:,} hectares of vineyards.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="south_america_argentina",
                entities=entities,
                confidence=0.9,
                tags=base_tags + ["statistics", "area"],
            ))

        # Key grapes
        if region.get("key_grapes"):
            grapes_str = ", ".join(region["key_grapes"])
            grape_entities = entities + [{"type": "grape", "name": g} for g in region["key_grapes"]]
            facts.append(_make_fact(
                f"The principal grape varieties of {name}, Argentina include {grapes_str}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="regional_grapes",
                entities=grape_entities,
                tags=base_tags + ["grapes"],
            ))

        # Notes
        if region.get("notes"):
            facts.append(_make_fact(
                f"{region['notes']}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="south_america_argentina",
                entities=entities,
                tags=base_tags,
            ))

        # Extra facts
        for extra in region.get("extra_facts", []):
            facts.append(_make_fact(
                extra,
                domain="wine_regions",
                source_id=source_id,
                subdomain="south_america_argentina",
                entities=entities,
                tags=base_tags,
            ))

        # Subregions
        for sub in region.get("subregions", []):
            sub_name = sub["name"]
            sub_entities = [
                {"type": "region", "name": sub_name},
                {"type": "region", "name": name},
                {"type": "country", "name": "Argentina"},
            ]
            sub_tags = base_tags + [sub_name.lower().replace(" ", "_")]

            if sub.get("notes"):
                facts.append(_make_fact(
                    f"{sub['notes']}.",
                    domain="wine_regions",
                    source_id=source_id,
                    subdomain="south_america_argentina",
                    entities=sub_entities,
                    tags=sub_tags,
                ))

            if sub.get("elevation_range"):
                facts.append(_make_fact(
                    f"Vineyards in {sub_name} within {name}, Argentina are planted at elevations of {sub['elevation_range']}.",
                    domain="viticulture",
                    source_id=source_id,
                    subdomain="altitude_viticulture",
                    entities=sub_entities,
                    tags=sub_tags + ["elevation", "altitude"],
                ))

            if sub.get("soil_types"):
                soil_list = ", ".join(sub["soil_types"])
                facts.append(_make_fact(
                    f"The predominant soil types in {sub_name}, {name} include {soil_list}.",
                    domain="wine_regions",
                    source_id=source_id,
                    subdomain="south_america_argentina",
                    entities=sub_entities,
                    tags=sub_tags + ["soil", "terroir"],
                ))

            if sub.get("key_grapes"):
                grapes_str = ", ".join(sub["key_grapes"])
                grape_entities = sub_entities + [{"type": "grape", "name": g} for g in sub["key_grapes"]]
                facts.append(_make_fact(
                    f"The key grape varieties grown in {sub_name}, {name} include {grapes_str}.",
                    domain="grape_varieties",
                    source_id=source_id,
                    subdomain="regional_grapes",
                    entities=grape_entities,
                    tags=sub_tags + ["grapes"],
                ))

            # Sub-subdistricts (e.g., Tupungato, Tunuyan, San Carlos in Valle de Uco)
            for district in sub.get("subdistricts", []):
                dist_name = district["name"]
                dist_entities = [
                    {"type": "region", "name": dist_name},
                    {"type": "region", "name": sub_name},
                    {"type": "country", "name": "Argentina"},
                ]
                dist_tags = sub_tags + [dist_name.lower().replace(" ", "_")]

                if district.get("notes"):
                    facts.append(_make_fact(
                        f"{district['notes']}.",
                        domain="wine_regions",
                        source_id=source_id,
                        subdomain="south_america_argentina",
                        entities=dist_entities,
                        tags=dist_tags,
                    ))

                if district.get("elevation_range"):
                    facts.append(_make_fact(
                        f"Vineyards in {dist_name} within Valle de Uco, Mendoza are planted at elevations of {district['elevation_range']}.",
                        domain="viticulture",
                        source_id=source_id,
                        subdomain="altitude_viticulture",
                        entities=dist_entities,
                        tags=dist_tags + ["elevation", "altitude"],
                    ))

    # Additional terroir and history facts
    for fact_text in ARGENTINA_TERROIR_FACTS:
        facts.append(_make_fact(
            fact_text,
            domain="wine_regions",
            source_id=source_id,
            subdomain="south_america_argentina",
            entities=[{"type": "country", "name": "Argentina"}],
            tags=["argentina", "terroir"],
        ))

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# FACT BUILDERS — Chile
# ═══════════════════════════════════════════════════════════════════════════════


def _build_chile_facts(source_id: str) -> list[dict]:
    """Build facts about Chilean wine regions (N-S), transversal system, and history."""
    facts = []

    for region in CHILE_REGIONS:
        name = region["name"]
        entities = [{"type": "region", "name": name}, {"type": "country", "name": "Chile"}]
        base_tags = ["chile", name.lower().replace(" ", "_").replace("-", "_")]

        # Climate
        facts.append(_make_fact(
            f"The {name} wine region in Chile has a {region['climate']} climate.",
            domain="wine_regions",
            source_id=source_id,
            subdomain="south_america_chile",
            entities=entities,
            tags=base_tags + ["climate"],
        ))

        if region.get("climate_details"):
            facts.append(_make_fact(
                f"{region['climate_details']}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="south_america_chile",
                entities=entities,
                tags=base_tags + ["climate"],
            ))

        # Soil
        if region.get("soil_types"):
            soil_list = ", ".join(region["soil_types"])
            facts.append(_make_fact(
                f"The predominant soil types in the {name}, Chile include {soil_list}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="south_america_chile",
                entities=entities,
                tags=base_tags + ["soil", "terroir"],
            ))

        if region.get("soil_details"):
            facts.append(_make_fact(
                f"{region['soil_details']}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="south_america_chile",
                entities=entities,
                tags=base_tags + ["soil", "terroir"],
            ))

        # Elevation
        if region.get("elevation_range"):
            facts.append(_make_fact(
                f"Vineyards in the {name}, Chile are planted at elevations ranging from {region['elevation_range']}.",
                domain="viticulture",
                source_id=source_id,
                subdomain="terrain",
                entities=entities,
                tags=base_tags + ["elevation"],
            ))

        # Vineyard area
        if region.get("vineyard_area_ha"):
            facts.append(_make_fact(
                f"The {name} in Chile has approximately {region['vineyard_area_ha']:,} hectares of vineyards.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="south_america_chile",
                entities=entities,
                confidence=0.9,
                tags=base_tags + ["statistics", "area"],
            ))

        # Key grapes
        if region.get("key_grapes"):
            grapes_str = ", ".join(region["key_grapes"])
            grape_entities = entities + [{"type": "grape", "name": g} for g in region["key_grapes"]]
            facts.append(_make_fact(
                f"The principal grape varieties of the {name}, Chile include {grapes_str}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="regional_grapes",
                entities=grape_entities,
                tags=base_tags + ["grapes"],
            ))

        # Notes
        if region.get("notes"):
            facts.append(_make_fact(
                f"{region['notes']}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="south_america_chile",
                entities=entities,
                tags=base_tags,
            ))

        # Extra facts
        for extra in region.get("extra_facts", []):
            facts.append(_make_fact(
                extra,
                domain="wine_regions",
                source_id=source_id,
                subdomain="south_america_chile",
                entities=entities,
                tags=base_tags,
            ))

        # Subregions
        for sub in region.get("subregions", []):
            sub_name = sub["name"]
            sub_entities = [
                {"type": "region", "name": sub_name},
                {"type": "region", "name": name},
                {"type": "country", "name": "Chile"},
            ]
            sub_tags = base_tags + [sub_name.lower().replace(" ", "_")]

            if sub.get("notes"):
                facts.append(_make_fact(
                    f"{sub['notes']}.",
                    domain="wine_regions",
                    source_id=source_id,
                    subdomain="south_america_chile",
                    entities=sub_entities,
                    tags=sub_tags,
                ))

            if sub.get("elevation_range"):
                facts.append(_make_fact(
                    f"Vineyards in {sub_name} within the {name}, Chile are planted at elevations of {sub['elevation_range']}.",
                    domain="viticulture",
                    source_id=source_id,
                    subdomain="terrain",
                    entities=sub_entities,
                    tags=sub_tags + ["elevation"],
                ))

            if sub.get("key_grapes"):
                grapes_str = ", ".join(sub["key_grapes"])
                grape_entities = sub_entities + [{"type": "grape", "name": g} for g in sub["key_grapes"]]
                facts.append(_make_fact(
                    f"The key grape varieties grown in {sub_name}, {name} include {grapes_str}.",
                    domain="grape_varieties",
                    source_id=source_id,
                    subdomain="regional_grapes",
                    entities=grape_entities,
                    tags=sub_tags + ["grapes"],
                ))

    # Additional terroir and history facts
    for fact_text in CHILE_TERROIR_FACTS:
        facts.append(_make_fact(
            fact_text,
            domain="wine_regions",
            source_id=source_id,
            subdomain="south_america_chile",
            entities=[{"type": "country", "name": "Chile"}],
            tags=["chile", "terroir"],
        ))

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# FACT BUILDERS — Grape Varieties
# ═══════════════════════════════════════════════════════════════════════════════


def _build_grape_variety_facts(source_id: str) -> list[dict]:
    """Build facts about South American grape varieties."""
    facts = []

    for grape in GRAPE_VARIETY_DATABASE:
        name = grape["name"]
        country = grape["country"]
        grape_type = grape["type"]
        country_tag = country.lower().replace(" ", "_").replace("(", "").replace(")", "")
        entities = [{"type": "grape", "name": name}, {"type": "country", "name": country}]
        base_tags = [country_tag, name.lower().replace(" ", "_").replace("(", "").replace(")", "")]

        # Area
        if grape.get("area_ha"):
            facts.append(_make_fact(
                f"{name} has approximately {grape['area_ha']:,} hectares planted in {country}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="plantings",
                entities=entities,
                confidence=0.9,
                tags=base_tags + ["statistics", "area"],
            ))

        # Origin
        if grape.get("origin"):
            facts.append(_make_fact(
                f"{grape['origin']}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="history",
                entities=entities,
                tags=base_tags + ["origin", "history"],
            ))

        # Characteristics
        if grape.get("characteristics"):
            facts.append(_make_fact(
                f"{grape['characteristics']}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="characteristics",
                entities=entities,
                tags=base_tags + ["characteristics"],
            ))

        # Altitude notes (Argentina-specific)
        if grape.get("altitude_notes"):
            facts.append(_make_fact(
                f"{grape['altitude_notes']}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="altitude_viticulture",
                entities=entities,
                tags=base_tags + ["altitude", "terroir"],
            ))

        # Regions
        if grape.get("regions"):
            region_str = ", ".join(grape["regions"])
            region_entities = entities + [{"type": "region", "name": r} for r in grape["regions"]]
            facts.append(_make_fact(
                f"The main growing regions for {name} in {country} include {region_str}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="regional_grapes",
                entities=region_entities,
                tags=base_tags + ["regions"],
            ))

        # Individual detailed facts
        for fact_text in grape.get("facts", []):
            facts.append(_make_fact(
                fact_text,
                domain="grape_varieties",
                source_id=source_id,
                subdomain="south_america_grapes",
                entities=entities,
                tags=base_tags,
            ))

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# FACT BUILDERS — Classification Systems
# ═══════════════════════════════════════════════════════════════════════════════


def _build_classification_facts(source_id: str) -> list[dict]:
    """Build facts about Argentine and Chilean wine classification systems."""
    facts = []

    # Argentina
    for fact_text in ARGENTINA_CLASSIFICATION["facts"]:
        facts.append(_make_fact(
            fact_text,
            domain="wine_regions",
            source_id=source_id,
            subdomain="classification_argentina",
            entities=[{"type": "country", "name": "Argentina"}],
            tags=["argentina", "classification", "doc", "regulations"],
        ))

    # Chile
    for fact_text in CHILE_CLASSIFICATION["facts"]:
        facts.append(_make_fact(
            fact_text,
            domain="wine_regions",
            source_id=source_id,
            subdomain="classification_chile",
            entities=[{"type": "country", "name": "Chile"}],
            tags=["chile", "classification", "do", "regulations"],
        ))

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# ORCHESTRATION
# ═══════════════════════════════════════════════════════════════════════════════


def _build_all_facts(source_id: str, data_type: str = None) -> list[dict]:
    """Build all facts, optionally filtered by type."""
    all_facts = []

    builders = {
        "argentina": _build_argentina_facts,
        "chile": _build_chile_facts,
        "grape": _build_grape_variety_facts,
        "classification": _build_classification_facts,
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
        click.echo(f"\n[DRY RUN] Would insert {len(facts)} facts from South American Wine Reference")

        # Show breakdown by domain/subdomain
        domain_counts = defaultdict(int)
        subdomain_counts = defaultdict(int)
        for f in facts:
            domain_counts[f["domain"]] += 1
            sub = f.get("subdomain") or "(none)"
            subdomain_counts[f"{f['domain']}/{sub}"] += 1

        click.echo("\nDomain breakdown:")
        for d, c in sorted(domain_counts.items()):
            click.echo(f"  {d:25s}: {c}")

        click.echo("\nSubdomain breakdown:")
        for sub, c in sorted(subdomain_counts.items()):
            click.echo(f"  {sub:45s}: {c}")

        # Show samples
        click.echo(f"\nSample facts ({min(15, len(facts))} random):")
        for i, f in enumerate(random.sample(facts, min(15, len(facts))), 1):
            click.echo(f'  {i:2d}. "{f["fact_text"]}"')

        return summary

    inserted = insert_facts_batch(facts)
    summary["total_inserted"] = inserted

    logger.info(f"Inserted {inserted} new facts from South American Wine Reference (duplicates skipped)")
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

    # (f) Country coverage
    argentina_facts = sum(1 for f in facts if "argentina" in str(f.get("tags", [])).lower())
    chile_facts = sum(1 for f in facts if "chile" in str(f.get("tags", [])).lower())
    click.echo(f"\nCountry coverage:")
    click.echo(f"  Argentina:             {argentina_facts} facts")
    click.echo(f"  Chile:                 {chile_facts} facts")

    # (g) Random samples
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
        "Argentina Regions": _build_argentina_facts,
        "Chile Regions": _build_chile_facts,
        "Grape Varieties": _build_grape_variety_facts,
        "Classification": _build_classification_facts,
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
    type=click.Choice(["argentina", "chile", "grape", "classification"]),
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
    """OenoBench South American Wine Scraper — Argentina & Chile regions, grapes, and classification."""
    logger.add("data/logs/south_america_{time}.log", rotation="10 MB")

    if list_sources:
        click.echo("\nAvailable data categories:")
        click.echo(f"  {'argentina':16s} — {len(ARGENTINA_REGIONS)} Argentine wine regions (climate, soil, elevation, subregions)")
        click.echo(f"  {'chile':16s} — {len(CHILE_REGIONS)} Chilean wine regions N-S (climate, soil, transversal system)")
        click.echo(f"  {'grape':16s} — {len(GRAPE_VARIETY_DATABASE)} grape variety profiles (both countries)")
        click.echo(f"  {'classification':16s} — Argentine DOC/IG/IP and Chilean DO/transversal systems")
        click.echo(f"\nKnowledge base coverage:")
        click.echo(f"  Argentina regions:   {len(ARGENTINA_REGIONS)}")
        click.echo(f"  Chile regions:       {len(CHILE_REGIONS)}")
        click.echo(f"  Grape varieties:     {len(GRAPE_VARIETY_DATABASE)}")
        click.echo(f"  Classification facts: {len(ARGENTINA_CLASSIFICATION['facts']) + len(CHILE_CLASSIFICATION['facts'])}")
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
