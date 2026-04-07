"""
OenoBench — USA Wine Enrichment Scraper

Adds terroir, climate, and soil depth for US wine regions. The existing TTB
scraper covers AVA names and regulatory data only — this scraper provides the
complementary terroir information (climate, soil types, soil details, elevation,
key grapes, wine styles, and notable producers/sites).

Focus areas: California (Napa, Sonoma, Central Coast, other), Oregon
(Willamette Valley sub-AVAs), Washington (Columbia Valley sub-AVAs),
other US regions (NY, VA, TX, MI), US grape variety profiles, and
AVA classification/labeling rules.

Usage:
    python -m src.scrapers.usa_enrichment --all
    python -m src.scrapers.usa_enrichment --type california
    python -m src.scrapers.usa_enrichment --type oregon
    python -m src.scrapers.usa_enrichment --type washington
    python -m src.scrapers.usa_enrichment --type other
    python -m src.scrapers.usa_enrichment --type grape
    python -m src.scrapers.usa_enrichment --type classification
    python -m src.scrapers.usa_enrichment --dry-run
    python -m src.scrapers.usa_enrichment --validate
    python -m src.scrapers.usa_enrichment --test-run
    python -m src.scrapers.usa_enrichment --list
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
    "name": "US Wine Regions Reference Database",
    "url": "https://www.wineinstitute.org",
    "source_type": "reference",
    "tier": "tier_2_authoritative",
    "language": "en",
}


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — California Regions
# ═══════════════════════════════════════════════════════════════════════════════

NAPA_VALLEY_AVAS = [
    {
        "name": "Oakville",
        "county": "Napa",
        "parent_ava": "Napa Valley",
        "climate": "warm",
        "climate_details": "Warm days moderated by afternoon marine breezes through the Petaluma Gap; protected benchland location between the Mayacamas and Vaca ranges",
        "soil_types": ["alluvial gravel", "gravelly loam", "well-drained benchland"],
        "soil_details": "Deep, well-drained alluvial gravel and gravelly loam deposited by ancient streams from the Mayacamas Mountains; the western benchland (including the renowned To Kalon vineyard) features particularly gravelly, well-drained soils",
        "elevation_range": "40-150m",
        "key_grapes": ["Cabernet Sauvignon", "Merlot", "Sauvignon Blanc"],
        "wine_styles": ["Full-bodied Cabernet Sauvignon", "structured Bordeaux blends"],
        "notes": "Home to iconic vineyards including To Kalon and sites for Opus One; considered the heart of Napa Valley Cabernet Sauvignon production",
    },
    {
        "name": "Rutherford",
        "county": "Napa",
        "parent_ava": "Napa Valley",
        "climate": "warm",
        "climate_details": "Warm days with afternoon marine influence; slightly warmer than Oakville due to narrowing valley floor that limits fog penetration",
        "soil_types": ["alluvial gravel", "loam", "clay-loam"],
        "soil_details": "Famous 'Rutherford Dust' terroir derives from deep alluvial gravel and loam soils with excellent drainage; benchland deposits from ancient alluvial fans off the western mountains give distinctive mineral character",
        "elevation_range": "45-150m",
        "key_grapes": ["Cabernet Sauvignon", "Merlot"],
        "wine_styles": ["Powerful Cabernet Sauvignon with Rutherford Dust character"],
        "notes": "Andre Tchelistcheff coined the term 'Rutherford Dust' to describe the earthy, mineral quality of Cabernets from this area; home to historic producers including Inglenook and Beaulieu Vineyard",
    },
    {
        "name": "Stags Leap District",
        "county": "Napa",
        "parent_ava": "Napa Valley",
        "climate": "warm days with cool nights",
        "climate_details": "A gap in the eastern Vaca Range hills channels cool afternoon breezes from San Pablo Bay, creating a natural air conditioning effect that moderates temperatures and extends the growing season",
        "soil_types": ["volcanic", "alluvial", "rocky loam"],
        "soil_details": "Mix of volcanic soils from ancient eruptions and alluvial deposits; the rocky, well-drained soils produce wines known for their elegance and silky tannins compared to other Napa sub-AVAs",
        "elevation_range": "30-120m",
        "key_grapes": ["Cabernet Sauvignon", "Merlot"],
        "wine_styles": ["Elegant, silky Cabernet Sauvignon"],
        "notes": "The 1976 Judgment of Paris winning red wine (Stag's Leap Wine Cellars 1973 S.L.V.) came from this district; known for producing more elegant, less tannic Cabernet than the western benchlands",
    },
    {
        "name": "Howell Mountain",
        "county": "Napa",
        "parent_ava": "Napa Valley",
        "climate": "warm days with significant diurnal temperature variation",
        "climate_details": "Situated above the fog line at over 427m (1,400 feet), Howell Mountain receives more intense sunlight and warmer daytime temperatures than the valley floor, but experiences dramatically cooler nights",
        "soil_types": ["volcanic red clay", "tufa", "iron-rich"],
        "soil_details": "Volcanic red soils derived from ancient eruptions, with high iron content and excellent drainage; thin, rocky soils stress vines and produce small, concentrated berries with intense flavors",
        "elevation_range": "427-700m",
        "key_grapes": ["Cabernet Sauvignon", "Merlot", "Zinfandel"],
        "wine_styles": ["Intense, structured, tannic Cabernet Sauvignon", "mountain-grown Zinfandel"],
        "notes": "One of Napa Valley's original mountain appellations (established 1983); the minimum elevation requirement of 1,400 feet (427m) ensures all vineyards are above the fog line",
    },
    {
        "name": "Diamond Mountain District",
        "county": "Napa",
        "parent_ava": "Napa Valley",
        "climate": "warm days, cool nights",
        "climate_details": "Mountain climate above the fog line with intense morning sun exposure on east-facing slopes; volcanic soils retain heat during the day and release it slowly at night",
        "soil_types": ["volcanic ash", "tufa", "rocky"],
        "soil_details": "Soils are derived from volcanic ash and tufa (volcanic rock) with excellent drainage; the porous, mineral-rich soils force vine roots deep and produce concentrated, tannic wines",
        "elevation_range": "400-670m",
        "key_grapes": ["Cabernet Sauvignon", "Cabernet Franc"],
        "wine_styles": ["Powerful, mineral-driven Cabernet Sauvignon"],
        "notes": "One of the smallest Napa mountain AVAs at approximately 2,000 hectares; Diamond Creek Vineyards helped pioneer the district",
    },
    {
        "name": "Spring Mountain District",
        "county": "Napa",
        "parent_ava": "Napa Valley",
        "climate": "moderate, above fog line",
        "climate_details": "Mountain vineyards above the fog line on the Mayacamas Range receive afternoon sun on east-facing slopes; steep terrain creates numerous microclimates at different elevations and aspects",
        "soil_types": ["volcanic", "sedimentary", "rocky clay"],
        "soil_details": "Complex mix of volcanic and sedimentary soils on steep, well-drained slopes; many vineyard blocks are small due to the rugged terrain, each with distinct soil characteristics",
        "elevation_range": "200-800m",
        "key_grapes": ["Cabernet Sauvignon", "Merlot", "Cabernet Franc"],
        "wine_styles": ["Structured, age-worthy Cabernet Sauvignon with firm tannins"],
        "notes": "Historic wine region dating to the 1870s; steep slopes mean most vineyards must be farmed by hand; approximately 400 hectares under vine",
    },
    {
        "name": "Mt. Veeder",
        "county": "Napa",
        "parent_ava": "Napa Valley",
        "climate": "cool to moderate mountain climate",
        "climate_details": "The highest and coolest mountain appellation in Napa Valley; steep, west-facing slopes receive less direct afternoon sun than eastern mountain AVAs; above the fog line with excellent air drainage",
        "soil_types": ["volcanic", "thin rocky clay", "sandstone"],
        "soil_details": "Very thin, rocky volcanic soils with poor fertility force vine roots deep; the stressed growing conditions produce small berries with intense concentration and firm tannins",
        "elevation_range": "150-800m",
        "key_grapes": ["Cabernet Sauvignon", "Merlot", "Malbec"],
        "wine_styles": ["Intense, small-berry Cabernet with firm tannins and dark fruit"],
        "notes": "Named after a German Protestant minister who homesteaded on the mountain in the 1860s; some of Napa's most extreme vineyard sites with very low yields",
    },
    {
        "name": "Calistoga",
        "county": "Napa",
        "parent_ava": "Napa Valley",
        "climate": "warm to hot",
        "climate_details": "The warmest sub-AVA in Napa Valley; located at the northern end of the valley, it is the furthest from San Pablo Bay cooling influence and flanked by mountains that trap heat",
        "soil_types": ["volcanic", "alluvial gravel", "ash"],
        "soil_details": "Volcanic soils from ancient eruptions of nearby Mt. St. Helena, mixed with alluvial gravel deposits; some areas feature geothermal activity and warm soils",
        "elevation_range": "100-400m",
        "key_grapes": ["Cabernet Sauvignon", "Petite Sirah", "Zinfandel"],
        "wine_styles": ["Bold, ripe Cabernet Sauvignon", "Petite Sirah"],
        "notes": "Established as an AVA in 2009; Chateau Montelena, whose 1973 Chardonnay won at the Judgment of Paris, is located here",
    },
    {
        "name": "St. Helena",
        "county": "Napa",
        "parent_ava": "Napa Valley",
        "climate": "warm",
        "climate_details": "Warm valley floor location benefiting from a mix of soil types washed down from both the Mayacamas and Vaca mountain ranges; moderate marine influence reaches this mid-valley position",
        "soil_types": ["alluvial", "volcanic", "gravel-loam"],
        "soil_details": "Diverse alluvial and volcanic soils deposited from both western (Mayacamas) and eastern (Vaca) mountain ranges; well-drained benchland and valley floor deposits",
        "elevation_range": "50-150m",
        "key_grapes": ["Cabernet Sauvignon", "Merlot", "Zinfandel"],
        "wine_styles": ["Rich Cabernet Sauvignon", "Zinfandel"],
        "notes": "One of Napa Valley's historic wine towns; home to numerous historic wineries including Charles Krug (founded 1861) and Louis M. Martini",
    },
    {
        "name": "Atlas Peak",
        "county": "Napa",
        "parent_ava": "Napa Valley",
        "climate": "cool nights, warm days",
        "climate_details": "High-altitude vineyards in the Vaca Range experience intense daytime sun and dramatic nighttime cooling; situated above the fog line with some of the greatest diurnal temperature swings in Napa",
        "soil_types": ["volcanic", "red clay", "rocky"],
        "soil_details": "Volcanic soils derived from ancient eruptions, predominantly red iron-rich clay with rocky outcrops; thin topsoil over fractured volcanic bedrock provides excellent drainage",
        "elevation_range": "460-760m",
        "key_grapes": ["Cabernet Sauvignon", "Sangiovese", "Chardonnay"],
        "wine_styles": ["Mountain Cabernet", "Italian varieties at altitude"],
        "notes": "One of the highest-elevation AVAs in Napa Valley; Antinori's Atlas Peak Winery helped introduce Sangiovese to the region in the 1980s",
    },
    {
        "name": "Yountville",
        "county": "Napa",
        "parent_ava": "Napa Valley",
        "climate": "warm to moderate",
        "climate_details": "Mild climate moderated by consistent marine influence from San Pablo Bay; the Yountville bench provides slightly warmer conditions than the immediate valley floor",
        "soil_types": ["alluvial benchland", "gravel-loam", "clay"],
        "soil_details": "Well-drained alluvial benchland soils with gravel and loam; deposits from ancient Napa River channels provide good mineral complexity",
        "elevation_range": "5-100m",
        "key_grapes": ["Cabernet Sauvignon", "Merlot"],
        "wine_styles": ["Elegant Cabernet Sauvignon"],
        "notes": "Named after George Yount, the first American to settle in Napa Valley; Dominus Estate and Napanook are located in this AVA",
    },
    {
        "name": "Los Carneros",
        "county": "Napa/Sonoma",
        "parent_ava": "Napa Valley / Sonoma Valley",
        "climate": "cool",
        "climate_details": "The coolest AVA in both Napa and Sonoma, directly exposed to winds and fog from San Pablo Bay; strong afternoon winds moderate temperatures and extend the growing season significantly",
        "soil_types": ["shallow clay", "clay-loam", "rocky"],
        "soil_details": "Shallow, thin clay soils over bedrock with poor water retention; the clay-heavy soils stress vines naturally and produce low yields of concentrated fruit",
        "elevation_range": "5-120m",
        "key_grapes": ["Pinot Noir", "Chardonnay"],
        "wine_styles": ["Pinot Noir", "Chardonnay", "sparkling wine"],
        "notes": "Overlaps both Napa and Sonoma counties; a key sparkling wine region with Domaine Carneros (Taittinger), Artesa, and Gloria Ferrer; 'Carneros' means 'rams' in Spanish",
    },
    {
        "name": "Coombsville",
        "county": "Napa",
        "parent_ava": "Napa Valley",
        "climate": "moderate to cool",
        "climate_details": "Cooler than most Napa Valley floor AVAs due to proximity to the eastern hills and San Pablo Bay influence; morning fog burns off earlier than on the valley floor",
        "soil_types": ["volcanic", "alluvial", "basalt-derived"],
        "soil_details": "Mix of volcanic soils from the Vaca Range and alluvial deposits; basalt-derived soils in the eastern portions provide excellent drainage and mineral character",
        "elevation_range": "20-250m",
        "key_grapes": ["Cabernet Sauvignon", "Syrah", "Merlot"],
        "wine_styles": ["Elegant Cabernet Sauvignon", "cool-climate Syrah"],
        "notes": "One of the newest Napa Valley sub-AVAs, established in 2011; named for Nathan Coombs, one of the founders of the city of Napa",
    },
    {
        "name": "Chiles Valley",
        "county": "Napa",
        "parent_ava": "Napa Valley",
        "climate": "warm days, cool nights",
        "climate_details": "A small inland valley east of the main Napa Valley floor, isolated by surrounding hills; warm daytime temperatures with significant nighttime cooling due to cold air drainage",
        "soil_types": ["volcanic", "clay", "rocky loam"],
        "soil_details": "Volcanic soils with clay and rocky loam; the valley's isolation from the main Napa Valley creates distinct growing conditions",
        "elevation_range": "200-450m",
        "key_grapes": ["Zinfandel", "Cabernet Sauvignon", "Sauvignon Blanc"],
        "wine_styles": ["Zinfandel", "Sauvignon Blanc"],
        "notes": "One of Napa Valley's least-known sub-AVAs; a small, isolated inland valley with a handful of producers",
    },
]

SONOMA_AVAS = [
    {
        "name": "Russian River Valley",
        "county": "Sonoma",
        "parent_ava": None,
        "climate": "cool",
        "climate_details": "Heavy morning fog from the Pacific Ocean funnels through the Petaluma Gap and Russian River corridor, burning off by mid-morning; one of the coolest growing climates in California",
        "soil_types": ["Goldridge sandy loam", "alluvial", "clay"],
        "soil_details": "The signature Goldridge sandy loam is a well-drained, nutrient-poor soil that stresses vines and produces concentrated fruit; alluvial soils along the Russian River provide different character",
        "elevation_range": "15-300m",
        "key_grapes": ["Pinot Noir", "Chardonnay", "Zinfandel"],
        "wine_styles": ["Cool-climate Pinot Noir", "Chardonnay", "old-vine Zinfandel"],
        "notes": "One of California's premier Pinot Noir appellations; the Goldridge sandy loam soil is so distinctive that producers often reference it on labels",
    },
    {
        "name": "Dry Creek Valley",
        "county": "Sonoma",
        "parent_ava": None,
        "climate": "warm",
        "climate_details": "Warm benchland climate on the valley floor and western slopes; eastern benchlands are slightly cooler; minimal fog penetration compared to Russian River Valley",
        "soil_types": ["gravel", "loam", "alluvial benchland", "red clay"],
        "soil_details": "Well-drained gravel and loam on the valley floor and benchlands; western hillsides have red clay soils; some of California's oldest Zinfandel vines (100+ years) grow on the benchlands",
        "elevation_range": "60-600m",
        "key_grapes": ["Zinfandel", "Cabernet Sauvignon", "Sauvignon Blanc"],
        "wine_styles": ["Old-vine Zinfandel", "Cabernet Sauvignon", "Sauvignon Blanc"],
        "notes": "Considered the heartland of California Zinfandel; many old-vine blocks date to the late 1800s and early 1900s, having survived Prohibition as 'home winemaking' grapes",
    },
    {
        "name": "Alexander Valley",
        "county": "Sonoma",
        "parent_ava": None,
        "climate": "warm",
        "climate_details": "Warm valley floor with less marine influence than other Sonoma AVAs; the Russian River flows through the valley, providing some moderating influence; warm days and mild nights",
        "soil_types": ["alluvial gravel", "loam", "volcanic"],
        "soil_details": "Deep alluvial gravel and loam soils deposited by the Russian River; volcanic soils on the higher slopes and benchlands; excellent drainage supports vigorous vine growth",
        "elevation_range": "45-600m",
        "key_grapes": ["Cabernet Sauvignon", "Merlot", "Chardonnay"],
        "wine_styles": ["Supple Cabernet Sauvignon", "Merlot"],
        "notes": "Named after Cyrus Alexander, a pioneer who established one of the first vineyards in Sonoma County in the 1840s; Silver Oak Alexander Valley is a benchmark producer",
    },
    {
        "name": "Sonoma Coast",
        "county": "Sonoma",
        "parent_ava": None,
        "climate": "cool",
        "climate_details": "Strong Pacific influence with persistent fog and wind; the extreme Sonoma Coast (Fort Ross-Seaview) experiences the most dramatic maritime conditions with temperature swings and cooling winds",
        "soil_types": ["Goldridge sandy loam", "clay", "weathered sandstone"],
        "soil_details": "Diverse soils ranging from Goldridge sandy loam in the inland portions to thin, rocky soils on the extreme coastal ridges; poor fertility and wind stress produce low yields",
        "elevation_range": "15-500m",
        "key_grapes": ["Pinot Noir", "Chardonnay", "Syrah"],
        "wine_styles": ["Intense, mineral-driven Pinot Noir", "crisp Chardonnay"],
        "notes": "A vast AVA encompassing diverse terrain from Fort Ross-Seaview on the extreme coast to inland areas overlapping other Sonoma AVAs; the true Sonoma Coast frontier is one of California's most exciting Pinot Noir regions",
    },
    {
        "name": "Bennett Valley",
        "county": "Sonoma",
        "parent_ava": None,
        "climate": "cool to moderate",
        "climate_details": "Mountain-sheltered valley with a gap in the Sonoma Mountains that channels cool air and fog from the Petaluma Gap; one of the cooler AVAs in Sonoma",
        "soil_types": ["volcanic", "clay-loam", "ash"],
        "soil_details": "Volcanic soils derived from ancient eruptions of Sonoma Mountain, with clay-loam and volcanic ash; the soils retain moisture well while providing good drainage on the hillsides",
        "elevation_range": "80-500m",
        "key_grapes": ["Merlot", "Cabernet Sauvignon", "Sauvignon Blanc"],
        "wine_styles": ["Cool-climate Merlot", "Sauvignon Blanc"],
        "notes": "One of Sonoma's smaller and less well-known AVAs; the Matanzas Creek Winery helped establish the area's reputation for Merlot",
    },
    {
        "name": "Sonoma Valley",
        "county": "Sonoma",
        "parent_ava": None,
        "climate": "moderate to warm",
        "climate_details": "Diverse climate ranging from cool in the southern portion near San Pablo Bay to warm in the northern section; the valley runs roughly north-south between Sonoma Mountain and the Mayacamas Range",
        "soil_types": ["volcanic", "alluvial", "clay"],
        "soil_details": "Volcanic soils on the surrounding mountains, alluvial on the valley floor, and clay in lower areas; the diversity of soils supports a wide range of grape varieties",
        "elevation_range": "5-450m",
        "key_grapes": ["Cabernet Sauvignon", "Zinfandel", "Chardonnay", "Merlot"],
        "wine_styles": ["Diverse styles reflecting the Valley of the Moon's varied microclimates"],
        "notes": "Known as the 'Valley of the Moon' (from a Jack London reference); includes the town of Sonoma, where Buena Vista Winery (founded 1857 by Agoston Haraszthy) is considered California's first premium winery",
    },
    {
        "name": "Knights Valley",
        "county": "Sonoma",
        "parent_ava": None,
        "climate": "warm",
        "climate_details": "One of the warmest AVAs in Sonoma County, sheltered by mountains on three sides; minimal marine influence; warm days similar to Alexander Valley",
        "soil_types": ["volcanic", "clay-loam", "gravel"],
        "soil_details": "Volcanic soils from ancient eruptions with clay-loam and gravel; the warm climate and volcanic soils produce ripe, full-bodied wines",
        "elevation_range": "120-500m",
        "key_grapes": ["Cabernet Sauvignon", "Sauvignon Blanc"],
        "wine_styles": ["Full-bodied Cabernet Sauvignon"],
        "notes": "Named after Thomas Knight, an early settler; Beringer Vineyards sources grapes from Knights Valley for some of their premium Cabernets",
    },
]

CENTRAL_COAST_AVAS = [
    {
        "name": "Paso Robles",
        "county": "San Luis Obispo",
        "parent_ava": None,
        "climate": "warm",
        "climate_details": "One of the largest diurnal temperature swings in California, often exceeding 25 degrees Celsius between day and night; warm days and very cool nights preserve acidity while building ripe fruit flavors",
        "soil_types": ["limestone", "calcareous", "clay", "shale"],
        "soil_details": "Predominantly calcareous and limestone soils with significant calcium carbonate content; the Adelaida District in the west has calcareous shale at higher elevation, while the eastern side has more alluvial, warmer soils",
        "elevation_range": "200-600m",
        "vineyard_area_acres": 40000,
        "key_grapes": ["Cabernet Sauvignon", "Zinfandel", "Syrah", "Grenache", "Mourvèdre"],
        "wine_styles": ["Rhône-style blends", "Zinfandel", "Bordeaux-style blends"],
        "notes": "Divided into 11 official sub-districts since 2014; the western Adelaida District is cooler with calcareous soils, while the eastern Estrella District is warmer and flatter; approximately 40,000 acres under vine",
    },
    {
        "name": "Sta. Rita Hills",
        "county": "Santa Barbara",
        "parent_ava": "Santa Ynez Valley",
        "climate": "cool",
        "climate_details": "One of the coolest AVAs in California; the unique east-west orientation of the Santa Ynez Valley channels Pacific fog and wind directly into the vineyards, creating a natural wind tunnel effect",
        "soil_types": ["diatomaceous earth", "clay", "sand", "limestone"],
        "soil_details": "Distinctive diatomaceous earth (ancient siliceous marine sediment) mixed with clay and limestone; the chalky, mineral-rich soils contribute to the region's characteristic intensity and minerality in Pinot Noir",
        "elevation_range": "60-300m",
        "key_grapes": ["Pinot Noir", "Chardonnay"],
        "wine_styles": ["Intense, structured Pinot Noir", "mineral-driven Chardonnay"],
        "notes": "Originally named 'Santa Rita Hills' but changed to 'Sta. Rita Hills' to avoid confusion with Chile's Viña Santa Rita; home to producers like Sanford, Sea Smoke, and Domaine de la Côte",
    },
    {
        "name": "Santa Ynez Valley",
        "county": "Santa Barbara",
        "parent_ava": None,
        "climate": "varies from cool (west) to warm (east)",
        "climate_details": "The east-west orientation creates a dramatic climate gradient: the western end near Lompoc is cool and foggy, while the eastern end near Santa Ynez town is warm and dry, spanning 15-20 degrees difference",
        "soil_types": ["alluvial", "clay", "sand", "limestone"],
        "soil_details": "Diverse soils reflecting the complex geology; alluvial deposits on the valley floor, clay and limestone on hillsides, and sandy loam in the eastern sections",
        "elevation_range": "60-600m",
        "key_grapes": ["Pinot Noir", "Chardonnay", "Syrah", "Sauvignon Blanc", "Grenache"],
        "wine_styles": ["Diverse styles from cool-climate whites to warm-climate reds"],
        "notes": "The transverse mountain ranges running east-west are a geological rarity in California and key to the region's diverse microclimates; featured in the 2004 film 'Sideways'",
    },
    {
        "name": "Happy Canyon of Santa Barbara",
        "county": "Santa Barbara",
        "parent_ava": "Santa Ynez Valley",
        "climate": "warm",
        "climate_details": "The warmest sub-AVA in Santa Barbara County, located at the eastern end of the Santa Ynez Valley where marine influence is minimal; warm days with moderate nighttime cooling",
        "soil_types": ["alluvial", "sandy loam", "clay"],
        "soil_details": "Alluvial soils with sandy loam and clay; the warm climate and well-drained soils are ideal for late-ripening Bordeaux varieties",
        "elevation_range": "180-600m",
        "key_grapes": ["Cabernet Sauvignon", "Cabernet Franc", "Sauvignon Blanc"],
        "wine_styles": ["Bordeaux-style reds and whites"],
        "notes": "One of the few areas in Santa Barbara County warm enough for Cabernet Sauvignon to fully ripen; established as an AVA in 2009",
    },
    {
        "name": "Ballard Canyon",
        "county": "Santa Barbara",
        "parent_ava": "Santa Ynez Valley",
        "climate": "warm to moderate",
        "climate_details": "A north-south canyon that channels afternoon wind from the Pacific, creating a moderate climate warmer than Sta. Rita Hills but cooler than Happy Canyon; excellent for Syrah",
        "soil_types": ["clay", "limestone", "sand"],
        "soil_details": "Clay and limestone soils with sandy deposits; the moderately warm canyon environment is considered ideal for Rhône varieties, especially Syrah",
        "elevation_range": "120-400m",
        "key_grapes": ["Syrah", "Grenache", "Viognier"],
        "wine_styles": ["Northern Rhône-style Syrah"],
        "notes": "Established as an AVA in 2013; considered one of California's top Syrah-producing regions; Rusack and Jonata are notable producers",
    },
    {
        "name": "Edna Valley",
        "county": "San Luis Obispo",
        "parent_ava": None,
        "climate": "cool",
        "climate_details": "One of the closest California wine regions to the Pacific Ocean; consistent marine fog and wind create a very long, cool growing season ideal for Chardonnay",
        "soil_types": ["volcanic", "clay-loam", "ancient marine sediment"],
        "soil_details": "Volcanic soils from the ancient Nine Sisters chain of volcanic peaks, mixed with clay-loam and marine sedimentary deposits; the distinctive Islay Hill is a volcanic remnant in the valley",
        "elevation_range": "30-250m",
        "key_grapes": ["Chardonnay", "Pinot Noir", "Syrah"],
        "wine_styles": ["Cool-climate Chardonnay", "Pinot Noir"],
        "notes": "Named after the wife of a local rancher; proximity to the ocean gives Edna Valley one of the longest growing seasons in California, often harvesting weeks after inland regions",
    },
    {
        "name": "Arroyo Grande Valley",
        "county": "San Luis Obispo",
        "parent_ava": None,
        "climate": "cool",
        "climate_details": "Cool maritime climate with fog and wind from the Pacific; slightly warmer than neighboring Edna Valley at higher elevations, but still a distinctly cool-climate region",
        "soil_types": ["calcareous", "clay-loam", "sandy"],
        "soil_details": "Calcareous soils with clay-loam and sandy deposits; the limestone content contributes to bright acidity in the wines",
        "elevation_range": "30-400m",
        "key_grapes": ["Chardonnay", "Pinot Noir", "Zinfandel"],
        "wine_styles": ["Chardonnay", "sparkling wine", "Pinot Noir"],
        "notes": "Laetitia Vineyard (formerly Maison Deutz) produces notable sparkling wines, reflecting the Champagne-like cool climate; one of the smallest AVAs on the Central Coast",
    },
    {
        "name": "Santa Cruz Mountains",
        "county": "Santa Cruz/Santa Clara/San Mateo",
        "parent_ava": None,
        "climate": "diverse, cool to moderate",
        "climate_details": "Mountain vineyards above the fog line on both the Pacific and San Francisco Bay sides of the range; significant variation by aspect and elevation creates many microclimates within a compact area",
        "soil_types": ["shale", "limestone", "sandstone", "clay"],
        "soil_details": "Diverse geology with shale, limestone, sandstone, and clay; the western (ocean) side has different soil types than the eastern (bay) side; Ridge Vineyards' Monte Bello sits on limestone at 800m",
        "elevation_range": "120-800m",
        "key_grapes": ["Cabernet Sauvignon", "Pinot Noir", "Chardonnay"],
        "wine_styles": ["Terroir-driven Cabernet Sauvignon", "Pinot Noir"],
        "notes": "One of California's oldest wine regions; Ridge Monte Bello is one of the most celebrated Cabernet Sauvignons in the world; the appellation has a minimum elevation requirement of 240m (800 feet)",
    },
]

OTHER_CALIFORNIA_AVAS = [
    {
        "name": "Lodi",
        "county": "San Joaquin/Sacramento",
        "parent_ava": None,
        "climate": "warm",
        "climate_details": "Warm Mediterranean climate moderated by Delta breezes from the Sacramento-San Joaquin Delta; the cooling afternoon winds help preserve acidity despite warm daytime temperatures",
        "soil_types": ["sandy loam", "clay", "alluvial"],
        "soil_details": "Deep sandy loam and alluvial soils with excellent drainage; the Mokelumne River sub-AVA has particularly sandy soils ideal for old-vine Zinfandel, producing wines with soft tannins",
        "elevation_range": "5-60m",
        "vineyard_area_acres": 100000,
        "key_grapes": ["Zinfandel", "Cabernet Sauvignon", "Chardonnay", "Merlot"],
        "wine_styles": ["Old-vine Zinfandel", "value Cabernet Sauvignon"],
        "notes": "The largest wine grape appellation in California with approximately 100,000 acres under vine; home to some of California's oldest Zinfandel vines, many planted in the 1880s-1920s; divided into 7 sub-AVAs",
    },
    {
        "name": "Sierra Foothills",
        "county": "Multiple (Amador, El Dorado, Calaveras, Placer)",
        "parent_ava": None,
        "climate": "warm days, cool nights",
        "climate_details": "Gold Country wine region with warm daytime temperatures at moderate elevation; significant diurnal temperature variation due to altitude; lower humidity than coastal regions",
        "soil_types": ["granite", "volcanic", "decomposed slate", "red clay"],
        "soil_details": "Ancient granite, volcanic, and metamorphic soils from the Gold Rush-era geology; decomposed granite and red volcanic soils in Amador County produce intense, concentrated old-vine Zinfandel",
        "elevation_range": "300-900m",
        "key_grapes": ["Zinfandel", "Barbera", "Syrah", "Tempranillo"],
        "wine_styles": ["Old-vine Zinfandel", "Barbera", "Italian varieties"],
        "notes": "Wine production dates to the Gold Rush era of the 1850s; Amador County (Shenandoah Valley) has some of the oldest Zinfandel vines in California; Italian immigrants brought Barbera and other varieties",
    },
    {
        "name": "Anderson Valley",
        "county": "Mendocino",
        "parent_ava": None,
        "climate": "cool",
        "climate_details": "Cool, foggy climate influenced by Pacific Ocean proximity through the Navarro River gap; the western 'deep end' is coolest and foggiest, while the southeastern end near Boonville is warmer",
        "soil_types": ["sandy loam", "clay", "gravel", "alluvial"],
        "soil_details": "Well-drained sandy loam and gravelly soils with alluvial deposits along the Navarro River; the nutrient-poor soils and cool climate produce low-vigor vines with concentrated fruit",
        "elevation_range": "60-450m",
        "key_grapes": ["Pinot Noir", "Chardonnay", "Gewürztraminer", "Riesling"],
        "wine_styles": ["Pinot Noir", "sparkling wine", "Alsatian-style whites"],
        "notes": "Roederer Estate (owned by Champagne Louis Roederer) produces some of California's finest sparkling wines here; the cool climate drew comparisons to Champagne and Burgundy; known for its own dialect called 'Boontling'",
    },
    {
        "name": "Livermore Valley",
        "county": "Alameda",
        "parent_ava": None,
        "climate": "warm",
        "climate_details": "Warm climate moderated by marine air funneling through the wind gap from San Francisco Bay; the gravel-rich soils retain heat; one of California's oldest wine regions",
        "soil_types": ["gravel", "sandy loam", "clay"],
        "soil_details": "Deep gravel beds from ancient alluvial deposits provide excellent drainage and heat retention; the gravelly soils are sometimes compared to those of Graves in Bordeaux",
        "elevation_range": "30-200m",
        "key_grapes": ["Petite Sirah", "Cabernet Sauvignon", "Chardonnay", "Sauvignon Blanc"],
        "wine_styles": ["Petite Sirah", "Bordeaux-style blends"],
        "notes": "One of California's oldest wine regions, with continuous production since the 1840s; Wente Vineyards (founded 1883) and Concannon Vineyard (founded 1883) are among the oldest continuously operating wineries in the US; the Wente clone of Chardonnay is the most widely planted Chardonnay clone in California",
    },
]

# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Oregon Regions
# ═══════════════════════════════════════════════════════════════════════════════

OREGON_AVAS = [
    {
        "name": "Willamette Valley",
        "state": "Oregon",
        "climate": "cool, maritime",
        "climate_details": "Cool maritime climate with warm, dry summers and wet, mild winters; the Coast Range blocks much of the Pacific moisture, but enough marine influence penetrates to keep temperatures moderate; rain falls primarily in winter, leaving a dry growing season",
        "soil_types": ["volcanic (Jory/Nekia)", "marine sedimentary (Willakenzie)", "loess (Laurelwood)"],
        "soil_details": "Three major soil series define Willamette Valley terroir: volcanic Jory soils (red, iron-rich basalt-derived), marine sedimentary Willakenzie soils (sandstone and siltstone), and wind-blown loess (Laurelwood) over basalt; each imparts distinct character to Pinot Noir",
        "elevation_range": "60-300m",
        "key_grapes": ["Pinot Noir", "Pinot Gris", "Chardonnay", "Riesling"],
        "wine_styles": ["Burgundian-style Pinot Noir", "Pinot Gris", "Chardonnay"],
        "notes": "Home to over 800 wineries; widely considered the premier Pinot Noir region in the United States; David Lett of The Eyrie Vineyards planted the first Pinot Noir vines in 1965; contains 11 sub-AVAs",
    },
    {
        "name": "Dundee Hills",
        "state": "Oregon",
        "parent_ava": "Willamette Valley",
        "climate": "cool, maritime",
        "climate_details": "Slightly warmer than some other Willamette sub-AVAs due to south-facing hillside exposure; morning fog from the valley floor burns off by midday; elevations above 200m avoid the coldest valley floor air",
        "soil_types": ["volcanic Jory red soil"],
        "soil_details": "Predominantly Jory series volcanic red soils derived from Columbia River Basalt flows; the iron-rich, well-drained clay-loam is considered the signature soil of Oregon Pinot Noir and produces wines with distinctive red fruit and earthy character",
        "elevation_range": "60-310m",
        "key_grapes": ["Pinot Noir", "Chardonnay"],
        "wine_styles": ["Classic Oregon Pinot Noir with red fruit and earth"],
        "notes": "The first sub-AVA of Willamette Valley (established 2005); Domaine Drouhin Oregon, Sokol Blosser, and Domaine Serene are located here; the Jory soil is so iconic that it is Oregon's official state soil",
    },
    {
        "name": "Eola-Amity Hills",
        "state": "Oregon",
        "parent_ava": "Willamette Valley",
        "climate": "cool, windy",
        "climate_details": "The Van Duzer Corridor channels cool Pacific air directly into the Eola-Amity Hills each afternoon, making it one of the windiest and coolest sub-AVAs in Willamette Valley; significant diurnal temperature variation",
        "soil_types": ["volcanic (Jory/Nekia)", "marine sedimentary"],
        "soil_details": "Mix of volcanic Jory and Nekia soils on the higher slopes and marine sedimentary soils at lower elevations; the volcanic soils produce more structured, mineral-driven wines while sedimentary soils yield rounder, fruit-forward styles",
        "elevation_range": "60-340m",
        "key_grapes": ["Pinot Noir", "Chardonnay", "Pinot Blanc"],
        "wine_styles": ["Structured, mineral Pinot Noir", "Chardonnay"],
        "notes": "The Van Duzer Corridor wind effect is the defining feature; Bethel Heights, Cristom, and Evening Land are prominent producers; cooler conditions favor Pinot Noir with more structure and savory character",
    },
    {
        "name": "McMinnville",
        "state": "Oregon",
        "parent_ava": "Willamette Valley",
        "climate": "cool, maritime",
        "climate_details": "Protected from the strongest Van Duzer winds by the Coast Range foothills; moderate maritime influence with slightly warmer and drier conditions than the eastern Willamette sub-AVAs",
        "soil_types": ["marine sedimentary", "clay-loam", "basalt"],
        "soil_details": "Predominantly marine sedimentary soils (uplifted ocean floor deposits) with clay-loam and some basalt-derived soils at higher elevations; the well-drained hillside sites are prized for Pinot Noir",
        "elevation_range": "60-300m",
        "key_grapes": ["Pinot Noir", "Chardonnay"],
        "wine_styles": ["Pinot Noir with bright fruit and moderate structure"],
        "notes": "Named after the city of McMinnville, which hosts the International Pinot Noir Celebration (IPNC) annually; marine sedimentary soils give distinctive texture to the wines",
    },
    {
        "name": "Ribbon Ridge",
        "state": "Oregon",
        "parent_ava": "Willamette Valley",
        "climate": "cool, maritime",
        "climate_details": "A small, sheltered ridge with slightly warmer conditions than the surrounding valley floor; protected from cold winds by surrounding hills; consistent temperatures support even ripening",
        "soil_types": ["marine sedimentary", "clay-loam"],
        "soil_details": "Entirely marine sedimentary soils (Willakenzie series) formed from uplifted ancient ocean floor; the compact, well-structured clay-loam soils produce concentrated, age-worthy Pinot Noir",
        "elevation_range": "60-270m",
        "key_grapes": ["Pinot Noir", "Chardonnay", "Riesling"],
        "wine_styles": ["Concentrated, age-worthy Pinot Noir"],
        "notes": "One of the smallest AVAs in Oregon at approximately 1,400 hectares; entirely nested within the Chehalem Mountains AVA; Beaux Frères (co-owned by Robert Parker) is the most famous producer",
    },
    {
        "name": "Chehalem Mountains",
        "state": "Oregon",
        "parent_ava": "Willamette Valley",
        "climate": "cool, maritime",
        "climate_details": "Diverse exposures on the Chehalem Mountain range create varied microclimates; higher elevations are cooler and windier; the eastern slopes face the Willamette Valley floor",
        "soil_types": ["volcanic (Jory)", "marine sedimentary (Willakenzie)", "loess (Laurelwood)"],
        "soil_details": "Unique among Willamette sub-AVAs in having all three major soil types: volcanic Jory on the peaks, marine sedimentary Willakenzie on lower slopes, and wind-blown loess (Laurelwood) on the eastern flanks; this allows direct comparison of soil influence on Pinot Noir",
        "elevation_range": "60-450m",
        "key_grapes": ["Pinot Noir", "Pinot Gris", "Chardonnay", "Riesling"],
        "wine_styles": ["Varied Pinot Noir styles reflecting diverse soils"],
        "notes": "The only Willamette sub-AVA with all three major soil types; Ponzi Vineyards, Adelsheim, and Rex Hill are notable producers; the diversity of soils makes it a natural laboratory for terroir studies",
    },
    {
        "name": "Yamhill-Carlton",
        "state": "Oregon",
        "parent_ava": "Willamette Valley",
        "climate": "cool, maritime",
        "climate_details": "Sheltered from the strongest maritime winds by the Coast Range; slightly warmer and drier than more exposed sub-AVAs; a rain shadow effect from the surrounding hills reduces rainfall during the growing season",
        "soil_types": ["marine sedimentary", "clay-loam"],
        "soil_details": "Ancient marine sedimentary soils formed from uplifted seabed deposits; the well-drained, nutrient-poor soils stress vines naturally and produce intensely flavored, concentrated wines",
        "elevation_range": "60-300m",
        "key_grapes": ["Pinot Noir", "Chardonnay"],
        "wine_styles": ["Rich, powerful Pinot Noir"],
        "notes": "Known for producing some of the richest, most powerful Pinot Noirs in the Willamette Valley; Ken Wright Cellars and Shea Vineyard are prominent names in the district",
    },
    {
        "name": "Laurelwood District",
        "state": "Oregon",
        "parent_ava": "Willamette Valley",
        "climate": "cool, maritime",
        "climate_details": "Cool maritime climate with consistent temperatures; the eastern exposure of the Chehalem Mountains catches morning sun and is protected from the strongest afternoon coastal winds",
        "soil_types": ["wind-blown loess over basalt"],
        "soil_details": "Defined by Laurelwood series soils: wind-blown loess (fine-grained glacial dust carried by Ice Age winds) deposited over ancient Columbia River Basalt; the loess creates a deep, silty topsoil with excellent water retention",
        "elevation_range": "60-300m",
        "key_grapes": ["Pinot Noir", "Chardonnay"],
        "wine_styles": ["Elegant, floral Pinot Noir"],
        "notes": "The newest Willamette Valley sub-AVA (established 2020); defined entirely by soil type (Laurelwood loess) rather than solely by geographical boundaries; the loess soils produce a distinctive floral, elegant style of Pinot Noir",
    },
    {
        "name": "Rogue Valley",
        "state": "Oregon",
        "parent_ava": None,
        "climate": "warm",
        "climate_details": "Warmer and drier than the Willamette Valley; located in southern Oregon near the California border; higher elevation sites in the surrounding mountains provide some cooling",
        "soil_types": ["granite", "clay", "alluvial"],
        "soil_details": "Granitic and metamorphic soils from the Klamath Mountains; well-drained clay and alluvial deposits in the valley floor; the diverse geology supports a wider range of grape varieties than the Willamette Valley",
        "elevation_range": "300-600m",
        "key_grapes": ["Syrah", "Tempranillo", "Cabernet Sauvignon", "Viognier"],
        "wine_styles": ["Warm-climate reds", "Rhône-style wines"],
        "notes": "The warmest wine region in Oregon; the diversity of climate allows production of both warm-climate reds (Syrah, Tempranillo) and cool-climate whites at higher elevations",
    },
    {
        "name": "Umpqua Valley",
        "state": "Oregon",
        "parent_ava": None,
        "climate": "transitional",
        "climate_details": "Transitional climate between the cool Willamette Valley to the north and warmer Rogue Valley to the south; three distinct subregions with varying maritime, transitional, and inland conditions",
        "soil_types": ["sandstone", "clay", "alluvial", "volcanic"],
        "soil_details": "Diverse soils reflecting complex geology; sandstone and sedimentary in the western portion, volcanic soils near Roseburg, and alluvial deposits in the river valleys",
        "elevation_range": "120-450m",
        "key_grapes": ["Pinot Noir", "Tempranillo", "Syrah", "Riesling"],
        "wine_styles": ["Diverse styles", "emerging Tempranillo"],
        "notes": "HillCrest Vineyard (now known as Abacela) planted Oregon's first modern Tempranillo vines; the region's diversity of microclimates supports an unusually wide range of grape varieties for Oregon",
    },
    {
        "name": "Columbia Gorge",
        "state": "Oregon/Washington",
        "parent_ava": None,
        "climate": "diverse, transitional",
        "climate_details": "The Columbia River Gorge creates a dramatic climate gradient from wet and maritime on the western end to arid continental on the eastern end; the gorge channels powerful winds that moderate temperatures",
        "soil_types": ["volcanic basalt", "loess", "alluvial"],
        "soil_details": "Volcanic basalt from ancient Columbia River Basalt flows, loess (wind-blown silt), and alluvial deposits from the Missoula Floods; the diverse soils reflect the dramatic geological history of the gorge",
        "elevation_range": "30-600m",
        "key_grapes": ["Pinot Noir", "Chardonnay", "Syrah", "Zinfandel", "Riesling"],
        "wine_styles": ["Cool-climate whites (west)", "warm-climate reds (east)"],
        "notes": "Shared between Oregon and Washington; spans the transition from maritime to continental climate within a very short distance; the Missoula Floods carved the gorge and deposited many of the soils",
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Washington Regions
# ═══════════════════════════════════════════════════════════════════════════════

WASHINGTON_AVAS = [
    {
        "name": "Columbia Valley",
        "state": "Washington",
        "climate": "arid continental",
        "climate_details": "A vast desert wine region receiving less than 8 inches (200mm) of annual rainfall; warm to hot days with dramatic nighttime cooling; virtually all vineyards are irrigated using water from the Columbia River basin",
        "soil_types": ["basalt", "loess", "sand", "caliche"],
        "soil_details": "The geological foundation is ancient Columbia River Basalt (massive basalt lava flows), topped by windblown loess (fine silt), sand, and caliche (calcium carbonate hardpan); the Missoula Floods deposited massive gravel and sediment layers throughout the valley",
        "elevation_range": "120-500m",
        "vineyard_area_acres": 60000,
        "key_grapes": ["Cabernet Sauvignon", "Merlot", "Syrah", "Riesling", "Chardonnay"],
        "wine_styles": ["Ripe, fruit-forward Cabernet", "Merlot", "Syrah", "Riesling"],
        "notes": "Encompasses approximately 11 million acres, making it one of the largest AVAs in the US; nearly all of Washington State's wine grapes are grown here; the rain shadow of the Cascade Range creates the arid conditions; long summer daylight hours (up to 17 hours) compensate for the shorter growing season",
    },
    {
        "name": "Walla Walla Valley",
        "state": "Washington/Oregon",
        "parent_ava": "Columbia Valley",
        "climate": "continental",
        "climate_details": "Slightly more rainfall than the rest of Columbia Valley (12-18 inches); warm days and cool nights; the Blue Mountains to the east provide some cold air drainage; winter temperatures can be extreme, occasionally damaging vines",
        "soil_types": ["loess over basalt", "cobblestones", "alluvial"],
        "soil_details": "Deep loess deposits over fractured basalt bedrock; alluvial cobblestones from ancient rivers in some areas; the Rocks District sub-AVA has distinctive rounded basalt cobblestones (fractured by the Missoula Floods) that retain and radiate heat",
        "elevation_range": "150-500m",
        "key_grapes": ["Cabernet Sauvignon", "Syrah", "Merlot", "Tempranillo"],
        "wine_styles": ["Powerful Cabernet Sauvignon", "Syrah", "Merlot"],
        "notes": "Shared between Washington and Oregon; home to over 140 wineries; Leonetti Cellar (founded 1977) and Woodward Canyon (founded 1981) were pioneers; The Rocks District of Milton-Freewater (in Oregon) is a sub-AVA defined by its distinctive cobblestone soils",
    },
    {
        "name": "Red Mountain",
        "state": "Washington",
        "parent_ava": "Columbia Valley",
        "climate": "hot, windy",
        "climate_details": "The smallest, warmest, and windiest AVA in Washington State; south-southwest facing slopes receive intense sun exposure; persistent winds stress vines and produce small, concentrated berries; one of the warmest sites in the state",
        "soil_types": ["sand", "loess", "windblown silt", "caliche"],
        "soil_details": "Sandy, windblown soils over caliche (calcium carbonate hardpan); the wind-eroded, mineral-rich soils produce intensely concentrated wines; the name refers to the reddish-colored native bunchgrass, not the soil color",
        "elevation_range": "180-450m",
        "vineyard_area_acres": 4000,
        "key_grapes": ["Cabernet Sauvignon", "Merlot", "Syrah", "Cabernet Franc"],
        "wine_styles": ["Intense, concentrated Cabernet Sauvignon", "powerful reds"],
        "notes": "Approximately 4,000 acres under vine; despite its small size, Red Mountain produces some of Washington's most sought-after and expensive wines; Quilceda Creek, Hedges, and Col Solare source grapes here",
    },
    {
        "name": "Yakima Valley",
        "state": "Washington",
        "parent_ava": "Columbia Valley",
        "climate": "warm, arid",
        "climate_details": "The first AVA established in Washington State (1983); warm and arid with less than 8 inches of annual rainfall; the Yakima River provides irrigation water; Rattlesnake Hills sub-AVA on the southern edge is slightly warmer",
        "soil_types": ["loess", "volcanic ash", "alluvial", "basalt"],
        "soil_details": "Wind-deposited loess over volcanic basalt; some areas have volcanic ash layers from ancient Cascade Range eruptions; alluvial deposits along the Yakima River",
        "elevation_range": "200-450m",
        "key_grapes": ["Merlot", "Cabernet Sauvignon", "Chardonnay", "Riesling", "Syrah"],
        "wine_styles": ["Value-driven reds and whites", "Riesling"],
        "notes": "The oldest AVA in Washington State (established 1983); Chateau Ste. Michelle's Cold Creek Vineyard is located here; produces approximately 40% of Washington's wine grapes",
    },
    {
        "name": "Horse Heaven Hills",
        "state": "Washington",
        "parent_ava": "Columbia Valley",
        "climate": "warm, very windy",
        "climate_details": "Extremely windy conditions along the ridge tops, with constant winds from the west; the wind moderates temperatures and thickens grape skins, producing deeply colored wines with good structure",
        "soil_types": ["loess", "sand", "silt", "caliche"],
        "soil_details": "Deep windblown loess and sandy soils over caliche; the well-drained soils and persistent wind stress vines and concentrate flavors; south-facing slopes above the Columbia River receive intense sun",
        "elevation_range": "150-450m",
        "key_grapes": ["Cabernet Sauvignon", "Riesling", "Chardonnay", "Syrah"],
        "wine_styles": ["Wind-influenced Cabernet Sauvignon", "aromatic whites"],
        "notes": "Named after the wild horses that once roamed the hills; Columbia Crest's Horse Heaven Vineyard is one of the largest single vineyards in the state; the Champoux Vineyard is one of Washington's most storied sites",
    },
    {
        "name": "Wahluke Slope",
        "state": "Washington",
        "parent_ava": "Columbia Valley",
        "climate": "warm, arid",
        "climate_details": "One of the warmest and driest AVAs in Washington, receiving only about 6 inches (150mm) of annual rainfall; a large, south-facing slope that captures maximum sun exposure",
        "soil_types": ["sand", "loess", "gravel"],
        "soil_details": "Sandy and gravelly soils deposited by the Missoula Floods; the coarse, well-drained soils warm quickly in spring and retain heat; wind erosion has created some of the deepest loess deposits in the Columbia Valley",
        "elevation_range": "180-450m",
        "key_grapes": ["Cabernet Sauvignon", "Merlot", "Syrah", "Riesling"],
        "wine_styles": ["Ripe, powerful reds"],
        "notes": "Formerly part of the Hanford Nuclear Reservation, much of the land was released for agricultural use in the 1960s; the single south-facing slope is one of the most uniform growing environments in Washington",
    },
    {
        "name": "Ancient Lakes of Columbia Valley",
        "state": "Washington",
        "parent_ava": "Columbia Valley",
        "climate": "cool to moderate, arid",
        "climate_details": "One of the cooler AVAs within Columbia Valley; situated on bluffs above ancient lakes formed by Missoula Flood waters; cooling winds from the gorge moderate temperatures, making it suitable for white varieties",
        "soil_types": ["sand", "silt", "gravel", "basalt"],
        "soil_details": "Sandy and gravelly soils deposited by the Missoula Floods, often over basalt bedrock; the ancient lake beds left mineral-rich sedimentary deposits",
        "elevation_range": "180-400m",
        "key_grapes": ["Riesling", "Pinot Gris", "Chardonnay", "Cabernet Sauvignon"],
        "wine_styles": ["Crisp, mineral Riesling", "aromatic whites"],
        "notes": "Named for the ancient lakes carved by the Missoula Floods; known for producing some of Washington's finest Rieslings; Cave B Estate Winery and Vineyard is a notable producer",
    },
    {
        "name": "Puget Sound",
        "state": "Washington",
        "climate": "cool, maritime",
        "climate_details": "Western Washington's maritime wine region with cool temperatures, abundant rainfall, and cloudy skies; the Puget Sound moderates temperatures but growing degree days are limited; a fundamentally different climate from eastern Washington",
        "soil_types": ["glacial till", "sandy loam", "clay"],
        "soil_details": "Glacial till and sandy loam from Pleistocene glaciation; the cool, wet climate limits production to cool-climate varieties and hybrid grapes",
        "elevation_range": "5-200m",
        "key_grapes": ["Müller-Thurgau", "Madeleine Angevine", "Siegerrebe", "Pinot Noir"],
        "wine_styles": ["Cool-climate whites", "light reds", "fruit wines"],
        "notes": "Fundamentally different from eastern Washington; one of the few US wine regions suited to German and northern European grape varieties; Bainbridge Island Vineyards is a notable producer",
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Other US Regions
# ═══════════════════════════════════════════════════════════════════════════════

OTHER_US_AVAS = [
    {
        "name": "Finger Lakes",
        "state": "New York",
        "climate": "cool continental",
        "climate_details": "Cold continental climate moderated by deep glacial lakes (Seneca Lake reaches 188m depth and never freezes); the lakes act as thermal regulators, warming nearby vineyards in autumn and delaying bud break in spring to reduce frost risk",
        "soil_types": ["shale", "limestone", "glacial till", "gravel"],
        "soil_details": "Shale and limestone bedrock with glacial till deposits from Pleistocene glaciation; steep lake banks provide natural drainage and cold air drainage away from vines; the mineral-rich soils contribute to distinctive Riesling character",
        "elevation_range": "150-500m",
        "key_grapes": ["Riesling", "Gewürztraminer", "Cabernet Franc", "Pinot Noir"],
        "wine_styles": ["Riesling (dry to sweet)", "Gewürztraminer", "sparkling wine", "Cabernet Franc"],
        "notes": "Widely regarded as the finest Riesling region in the eastern United States; Dr. Konstantin Frank pioneered European vinifera cultivation in the 1960s, proving that cold-hardy vinifera could succeed in New York; Seneca Lake and Keuka Lake are the most important growing areas",
    },
    {
        "name": "Monticello",
        "state": "Virginia",
        "climate": "warm, humid",
        "climate_details": "Hot, humid summers with significant disease pressure; the Blue Ridge Mountains provide some elevation relief and air drainage; autumn can be challenging with hurricane remnants bringing heavy rainfall near harvest",
        "soil_types": ["clay", "granite", "schist", "red piedmont clay"],
        "soil_details": "Red Piedmont clay and decomposed granite soils on hillsides; well-drained sites on slopes above 200m are preferred to avoid frost and humidity; the granite-derived soils provide good drainage in the humid climate",
        "elevation_range": "150-400m",
        "key_grapes": ["Viognier", "Petit Manseng", "Cabernet Franc", "Merlot", "Norton"],
        "wine_styles": ["Viognier", "Petit Manseng", "Bordeaux-style blends"],
        "notes": "Virginia has adopted Viognier as its unofficial signature grape; Petit Manseng from southwest France has shown particular promise in Virginia's humid climate due to its thick skin and resistance to rot; Thomas Jefferson attempted to grow European grapes at Monticello in the 18th century",
    },
    {
        "name": "Texas High Plains",
        "state": "Texas",
        "climate": "warm, semi-arid",
        "climate_details": "High-altitude semi-arid climate at 1,000-1,200m elevation on the Llano Estacado (Staked Plains); warm days with significant diurnal cooling due to altitude; low humidity and ample sunshine; occasional spring hail is a hazard",
        "soil_types": ["sandy loam", "caliche", "red clay"],
        "soil_details": "Sandy loam soils over caliche (calcium carbonate hardpan); the porous, well-drained soils and arid conditions require drip irrigation; the high altitude moderates what would otherwise be extreme summer heat",
        "elevation_range": "1000-1200m",
        "key_grapes": ["Tempranillo", "Mourvèdre", "Cabernet Sauvignon", "Viognier"],
        "wine_styles": ["Spanish and Rhône-style wines", "Tempranillo"],
        "notes": "Shares a similar latitude and altitude with Spain's Ribera del Duero, which has inspired successful Tempranillo plantings; approximately 90% of Texas wine grapes are grown on the High Plains; Llano Estacado Winery is a pioneer",
    },
    {
        "name": "Texas Hill Country",
        "state": "Texas",
        "climate": "warm, variable",
        "climate_details": "Warm climate with significant variability; limestone hills provide some elevation relief; spring frost and Pierce's disease (spread by glassy-winged sharpshooter) are ongoing challenges",
        "soil_types": ["limestone", "caliche", "clay", "sandy loam"],
        "soil_details": "Limestone and caliche soils over Edwards Plateau bedrock; the limestone-rich soils are well-drained and reminiscent of Mediterranean wine regions; some producers compare the terrain to Provence or parts of Spain",
        "elevation_range": "300-600m",
        "key_grapes": ["Tempranillo", "Mourvèdre", "Viognier", "Tannat", "Blanc du Bois"],
        "wine_styles": ["Mediterranean and Spanish-style wines"],
        "notes": "One of the largest AVAs in the US by area; more winery tasting rooms than actual vineyard acreage, as many wineries source grapes from the Texas High Plains; Fredericksburg is the tourist hub",
    },
    {
        "name": "Lake Michigan Shore",
        "state": "Michigan",
        "climate": "cool continental",
        "climate_details": "Lake Michigan moderates temperatures, warming the lakeshore in autumn and delaying spring bud break; the lake effect creates a microclimate milder than the inland areas, extending the growing season by several weeks",
        "soil_types": ["sandy loam", "glacial till", "clay"],
        "soil_details": "Sandy loam soils from ancient glacial lake deposits; the well-drained, sandy soils warm quickly in spring and provide a relatively frost-free environment near the lakeshore",
        "elevation_range": "180-300m",
        "key_grapes": ["Riesling", "Gewürztraminer", "Pinot Noir", "Cabernet Franc"],
        "wine_styles": ["Riesling", "Gewürztraminer", "fruit wines"],
        "notes": "Lake Michigan's moderating effect is critical to viticulture in this otherwise too-cold climate; the lake effect parallels the role of Lake Constance for German and Swiss viticulture",
    },
    {
        "name": "Walla Walla Valley (Oregon portion)",
        "state": "Oregon",
        "parent_ava": "Columbia Valley",
        "climate": "continental",
        "climate_details": "The Oregon portion of Walla Walla Valley includes The Rocks District of Milton-Freewater, defined by its unique cobblestone terroir; warmer than most Oregon wine regions, more akin to eastern Washington climate",
        "soil_types": ["basalt cobblestones", "alluvial gravel", "loess"],
        "soil_details": "The Rocks District features fractured basalt cobblestones (ranging from fist-sized to basketball-sized) that absorb heat during the day and radiate it at night, extending ripening; the cobblestones were deposited by the Missoula Floods",
        "elevation_range": "250-400m",
        "key_grapes": ["Syrah", "Cabernet Sauvignon", "Grenache"],
        "wine_styles": ["Northern Rhône-style Syrah", "Cabernet Sauvignon"],
        "notes": "The Rocks District of Milton-Freewater was the first AVA in the US defined primarily by soil type (basalt cobblestones); Cayuse Vineyards' Christophe Baron pioneered the district, drawing comparisons to Châteauneuf-du-Pape's galets roulés",
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — US Grape Variety Profiles
# ═══════════════════════════════════════════════════════════════════════════════

US_GRAPE_PROFILES = [
    {
        "name": "Cabernet Sauvignon",
        "us_context": "The dominant premium red variety in the United States, with Napa Valley as its most celebrated expression.",
        "key_regions": ["Napa Valley", "Sonoma County", "Paso Robles", "Columbia Valley", "Red Mountain"],
        "us_styles": "Napa Valley Cabernet is typically full-bodied with ripe cassis, blackberry, and vanilla oak character, often higher in alcohol (14-15.5%) than Bordeaux equivalents; Washington State Cabernet tends toward darker fruit with herbal and mineral notes due to continental climate.",
        "notable_facts": [
            "Napa Valley Cabernet Sauvignon is the most expensive American wine category, with top bottles exceeding $500.",
            "The 1976 Judgment of Paris put Napa Valley Cabernet Sauvignon on the world stage when Stag's Leap Wine Cellars 1973 S.L.V. defeated top Bordeaux Grand Crus in a blind tasting.",
            "Washington State is the second largest Cabernet Sauvignon producer in the US after California.",
            "Screaming Eagle Cabernet Sauvignon from Oakville, Napa Valley, became one of the world's most expensive wines with bottles selling for over $5,000 at auction.",
        ],
    },
    {
        "name": "Pinot Noir",
        "us_context": "Oregon's Willamette Valley is the premier US Pinot Noir region, with California's Sonoma Coast, Russian River Valley, and Santa Barbara also producing world-class examples.",
        "key_regions": ["Willamette Valley", "Russian River Valley", "Sonoma Coast", "Sta. Rita Hills", "Los Carneros", "Anderson Valley"],
        "us_styles": "Oregon Pinot Noir tends toward a Burgundian style with red fruit (cherry, cranberry), earth, and moderate alcohol; California Pinot Noir is typically riper with darker fruit and more body; Sta. Rita Hills produces structured, intense Pinot Noir from diatomaceous earth soils.",
        "notable_facts": [
            "David Lett planted Oregon's first Pinot Noir vines in the Willamette Valley in 1965, and his 1975 Eyrie Vineyards South Block Pinot Noir placed in the top tier at a 1979 Burgundy tasting organized by Robert Drouhin.",
            "The success of Oregon Pinot Noir led Joseph Drouhin of Burgundy to establish Domaine Drouhin Oregon in the Dundee Hills in 1987.",
            "Oregon law requires that any wine labeled as Pinot Noir must contain at least 90% Pinot Noir, stricter than the US federal minimum of 75%.",
            "California Pinot Noir production surpasses Oregon by volume, but Oregon's reputation for Pinot Noir quality rivals or exceeds California's in many experts' assessments.",
        ],
    },
    {
        "name": "Zinfandel",
        "us_context": "Often called America's heritage grape, Zinfandel has been grown in California since the 1850s. DNA analysis proved it is genetically identical to Croatia's Crljenak Kaštelanski and Italy's Primitivo.",
        "key_regions": ["Lodi", "Dry Creek Valley", "Sierra Foothills", "Paso Robles"],
        "us_styles": "Old-vine Zinfandel (from vines 50-130+ years old) produces concentrated wines with bramble fruit, spice, and pepper; White Zinfandel (a rosé style created by Sutter Home in 1975) was once America's most popular wine by volume.",
        "notable_facts": [
            "Zinfandel was long considered uniquely American until DNA analysis by Dr. Carole Meredith at UC Davis in 1994-2001 proved it is genetically identical to Croatia's Crljenak Kaštelanski and Italy's Primitivo.",
            "Some of California's oldest surviving Zinfandel vines are over 130 years old, particularly in Lodi, Dry Creek Valley, and Amador County.",
            "White Zinfandel was accidentally created by Sutter Home Winery in 1975 when a batch of red Zinfandel experienced a stuck fermentation, leaving residual sugar and pink color.",
            "There is no legal definition of 'old vine' in the United States, though industry convention generally considers vines over 50 years old as 'old vine.'",
        ],
    },
    {
        "name": "Chardonnay",
        "us_context": "The most widely planted white grape variety in the United States, with dramatically different expressions from cool-climate Oregon to warm Napa Valley.",
        "key_regions": ["Sonoma Coast", "Russian River Valley", "Carneros", "Edna Valley", "Willamette Valley", "Sta. Rita Hills"],
        "us_styles": "California Chardonnay ranges from rich, buttery, oaky (Napa/Sonoma) to lean, mineral, and unoaked (Sonoma Coast/Sta. Rita Hills); Oregon Chardonnay tends toward a Burgundian style with moderate oak and crisp acidity.",
        "notable_facts": [
            "The Wente clone is the most widely planted Chardonnay clone in California, propagated from cuttings brought from the University of Montpellier by Ernest Wente in 1912.",
            "Chateau Montelena's 1973 Chardonnay from Napa Valley won the white wine category at the 1976 Judgment of Paris, defeating top white Burgundies.",
            "The 'ABC' (Anything But Chardonnay) movement of the late 1990s and 2000s was a backlash against heavily oaked, malolactic California Chardonnay, leading to a shift toward more restrained, balanced styles.",
            "California alone produces more Chardonnay than all of France, with over 90,000 acres planted statewide.",
        ],
    },
    {
        "name": "Merlot",
        "us_context": "Washington State has emerged as a leading US Merlot region, producing wines with more structure and complexity than California's softer examples.",
        "key_regions": ["Columbia Valley", "Walla Walla Valley", "Napa Valley", "Sonoma County"],
        "us_styles": "Washington Merlot tends to be more structured with darker fruit and firmer tannins than California versions, benefiting from the state's continental climate and extended sunlight hours.",
        "notable_facts": [
            "Washington State Merlot gained acclaim in the 1990s and 2000s, with producers like Leonetti Cellar and Andrew Will demonstrating that the variety could produce world-class wines outside of Bordeaux.",
            "The 2004 film 'Sideways' famously disparaged Merlot, leading to a measurable decline in US Merlot sales and an increase in Pinot Noir sales.",
            "Despite the 'Sideways Effect,' Washington State Merlot producers continued to produce critically acclaimed wines, and the variety remains Washington's second most planted red grape after Cabernet Sauvignon.",
        ],
    },
    {
        "name": "Petite Sirah",
        "us_context": "A variety with deep California roots, Petite Sirah (Durif) produces inky, tannic wines that are one of America's most distinctive red wine styles.",
        "key_regions": ["Livermore Valley", "Lodi", "Paso Robles", "Napa Valley"],
        "us_styles": "California Petite Sirah produces deeply colored, tannic, and age-worthy wines with dark berry, pepper, and chocolate notes; often used as a blending component to add color and structure.",
        "notable_facts": [
            "Petite Sirah is a cross of Syrah and Peloursin, created by Francois Durif in the 1880s in southern France, but has found its greatest success in California.",
            "Concannon Vineyard in Livermore Valley is credited with preserving and championing Petite Sirah in California, maintaining old vines that were the basis for widespread clonal propagation.",
            "PS I Love You (Petite Sirah: I Love You) is a producer advocacy group dedicated to promoting and preserving Petite Sirah.",
        ],
    },
    {
        "name": "Sauvignon Blanc",
        "us_context": "Known in California by the alternative name 'Fumé Blanc,' coined by Robert Mondavi in 1968 to rebrand the then-unfashionable variety as a dry, oak-aged wine.",
        "key_regions": ["Napa Valley", "Sonoma County", "Lake County"],
        "us_styles": "California Sauvignon Blanc ranges from grassy and citrusy (Sonoma) to rich, oak-aged Fumé Blanc (Napa); some producers blend with Sémillon in Bordeaux-style white blends.",
        "notable_facts": [
            "Robert Mondavi coined the term 'Fumé Blanc' in 1968 to market dry, barrel-fermented Sauvignon Blanc, creating an entirely new style category.",
            "The Fumé Blanc style remains distinctly American, with oak fermentation and aging distinguishing it from the typically unoaked New Zealand and Loire Valley expressions.",
        ],
    },
    {
        "name": "Viognier",
        "us_context": "Virginia has adopted Viognier as its signature white grape variety, and it has found success in several US regions with warm climates.",
        "key_regions": ["Virginia (Monticello)", "Paso Robles", "Santa Barbara", "Columbia Valley"],
        "us_styles": "Virginia Viognier tends to be aromatic with stone fruit and floral notes, with moderate alcohol; California versions are typically richer and more opulent.",
        "notable_facts": [
            "Virginia has become the most prominent Viognier-producing state in the eastern United States, with many Virginia winemakers considering it the state's signature white grape.",
            "Viognier was nearly extinct worldwide in the 1960s (fewer than 15 hectares in Condrieu), but has been widely planted in the US since the 1990s.",
            "Horton Vineyards in Virginia was an early champion of Viognier in the eastern US, planting it in 1990.",
        ],
    },
    {
        "name": "Riesling",
        "us_context": "The Finger Lakes region of New York and Washington State are the two most important US Riesling-producing areas, with dramatically different styles.",
        "key_regions": ["Finger Lakes", "Columbia Valley", "Yakima Valley", "Anderson Valley", "Michigan"],
        "us_styles": "Finger Lakes Riesling ranges from bone-dry to intensely sweet (ice wine style), with bright acidity and mineral character from shale/limestone soils; Washington Riesling tends to be off-dry with ripe stone fruit character.",
        "notable_facts": [
            "Dr. Konstantin Frank, a Ukrainian immigrant, revolutionized Finger Lakes winemaking in the 1960s by demonstrating that European Vinifera varieties, especially Riesling, could survive New York winters.",
            "The International Riesling Foundation, which developed the Riesling Taste Profile sweetness scale used on many labels, is based in the US.",
            "Chateau Ste. Michelle in Washington produces more Riesling than any other American winery and has a collaboration with Mosel producer Dr. Loosen called Eroica.",
        ],
    },
    {
        "name": "Syrah",
        "us_context": "Washington State and Paso Robles are the leading US Syrah regions, producing styles that range from Northern Rhône-like elegance to ripe, powerful New World expressions.",
        "key_regions": ["Walla Walla Valley", "Red Mountain", "Paso Robles", "Sta. Rita Hills", "Santa Barbara"],
        "us_styles": "Washington Syrah, especially from Walla Walla and Red Mountain, often shows dark fruit, pepper, and smoked meat similar to Côte-Rôtie; Paso Robles Syrah tends to be riper and more fruit-forward.",
        "notable_facts": [
            "The Rocks District of Milton-Freewater in Walla Walla Valley is considered one of the finest Syrah-producing terroirs in the Americas, with cobblestone soils reminiscent of Châteauneuf-du-Pape.",
            "The Rhône Rangers, an advocacy group for Rhône grape varieties in California, was founded in the 1980s and helped popularize Syrah, Grenache, and Mourvèdre in the US.",
            "Washington State Syrah production has grown significantly since the 1990s, with the variety now the state's third most planted red grape.",
        ],
    },
    {
        "name": "Cabernet Franc",
        "us_context": "Emerging as an important varietal wine in Virginia and the Finger Lakes, where it ripens more reliably than Cabernet Sauvignon in cooler or more humid climates.",
        "key_regions": ["Virginia", "Finger Lakes", "Napa Valley", "Columbia Valley"],
        "us_styles": "Virginia and Finger Lakes Cabernet Franc tends toward red fruit, herbs, and moderate tannins; in Napa Valley it is primarily a blending component for Cabernet Sauvignon-based wines.",
        "notable_facts": [
            "Cabernet Franc has become one of Virginia's most successful red grape varieties, ripening more consistently than Cabernet Sauvignon in the state's humid climate.",
            "In the Finger Lakes, Cabernet Franc has emerged as the most reliable premium red vinifera grape, producing lighter-bodied wines with bright acidity and red fruit.",
            "Chinon in the Loire Valley and the Finger Lakes share similar cool-climate expressions of Cabernet Franc, with bright cherry fruit and herbal notes.",
        ],
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — US Wine Classification & Regulations
# ═══════════════════════════════════════════════════════════════════════════════

US_CLASSIFICATION_DATA = [
    {
        "topic": "AVA System",
        "facts": [
            "The American Viticultural Area (AVA) system was established by the Bureau of Alcohol, Tobacco, Firearms and Explosives (now TTB) in 1980 as a system of geographically defined winegrowing regions.",
            "Unlike European appellation systems (AOC, DOC, DOCG), the AVA system regulates only geographic origin and does not impose requirements on grape varieties, winemaking methods, yields, or aging.",
            "A wine labeled with an AVA name must contain at least 85% grapes grown within that AVA's boundaries.",
            "A wine labeled with a state or county name (rather than an AVA) must contain at least 75% grapes from that state or county.",
            "If a wine is labeled with a specific vineyard name, 95% of the grapes must come from that vineyard.",
            "There are over 270 established AVAs in the United States as of 2025, with California, Oregon, and Washington containing the majority.",
            "The AVA petition process requires demonstrating that the proposed area has distinctive geographic features (climate, soil, elevation, or physical features) that differentiate it from surrounding regions.",
            "Oregon is the only US state that requires 90% minimum varietal content for Pinot Noir, Pinot Gris, Pinot Blanc, and Chardonnay, exceeding the federal 75% minimum.",
        ],
    },
    {
        "topic": "Estate Bottled",
        "facts": [
            "The term 'Estate Bottled' on a US wine label means that the winery grew the grapes in its own vineyards or vineyards it controls within the same AVA as the winery, and the wine was crushed, fermented, finished, and bottled at the winery.",
            "For a wine to carry the 'Estate Bottled' designation, both the winery and the vineyards must be located within the same AVA.",
            "The 'Estate Bottled' requirement is the closest the US system comes to the European concept of domaine or château bottling.",
        ],
    },
    {
        "topic": "Old Vine",
        "facts": [
            "There is no legal definition of 'Old Vine' in the United States, unlike some other countries; the term is unregulated and self-declared by producers.",
            "Industry convention in the US generally considers vines over 50 years old as qualifying for the 'old vine' designation, though some producers use the term for vines as young as 25-35 years.",
            "California's oldest surviving grapevines include Zinfandel vines in Lodi, Dry Creek Valley, and Amador County dating to the 1880s-1890s, over 130 years old.",
            "Australia's Barossa Valley has a formal Old Vine Charter with specific age thresholds (35+ years for old vines, 70+ for survivors, 100+ for centenarians, 125+ for ancestors), which has no equivalent in the US.",
        ],
    },
    {
        "topic": "Meritage",
        "facts": [
            "Meritage is a trademarked name (a portmanteau of 'merit' and 'heritage') for American Bordeaux-style blends, registered by the Meritage Alliance since 1988.",
            "A red Meritage must be a blend of two or more of the five traditional Bordeaux red varieties: Cabernet Sauvignon, Merlot, Cabernet Franc, Petit Verdot, and Malbec.",
            "A white Meritage must be a blend of Sauvignon Blanc, Sémillon, and/or Muscadelle du Bordelais.",
            "No single variety may comprise more than 90% of a Meritage blend, ensuring it is truly a blend and not a varietal wine.",
            "The term 'Meritage' was created because US labeling law requires wines labeled with a single variety to contain at least 75% of that variety, leaving no established term for premium Bordeaux-style blends.",
        ],
    },
    {
        "topic": "Judgment of Paris",
        "facts": [
            "The 1976 Judgment of Paris was a blind tasting organized by British wine merchant Steven Spurrier in which California wines defeated French Grand Cru wines in both red and white categories.",
            "The winning red wine was the 1973 Stag's Leap Wine Cellars S.L.V. Cabernet Sauvignon from the Stags Leap District of Napa Valley, which defeated Château Mouton-Rothschild, Château Haut-Brion, and Château Montrose.",
            "The winning white wine was the 1973 Chateau Montelena Chardonnay from Calistoga, Napa Valley, which defeated Meursault-Charmes and Puligny-Montrachet from Burgundy.",
            "The Judgment of Paris is widely considered the most significant event in the history of American wine, establishing California as a world-class wine region and challenging the prevailing European hierarchy.",
            "A 30th anniversary re-tasting in 2006 again placed the 1973 Stag's Leap Wine Cellars as the top red wine, demonstrating the aging ability of Napa Valley Cabernet Sauvignon.",
        ],
    },
    {
        "topic": "Labeling Regulations",
        "facts": [
            "US federal wine labeling regulations require that a varietal wine contain at least 75% of the named grape variety.",
            "Oregon requires a higher minimum of 90% for Pinot Noir, Pinot Gris, Pinot Blanc, and Chardonnay, but only 75% for other varieties.",
            "The vintage year on a US wine label requires at least 95% of the wine to be from the stated vintage.",
            "The term 'Reserve' has no legal definition in the United States and can be used freely on any wine label, unlike in Spain (Reserva/Gran Reserva) or Italy (Riserva).",
            "Alcohol content on US wine labels must be within 1.5% of the actual alcohol for wines between 7% and 14%, and within 1% for wines over 14%.",
            "US wine labels are required to carry a government health warning about the risks of alcohol consumption during pregnancy and impaired driving.",
        ],
    },
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


def _build_ava_facts(ava: dict, source_id: str, state_tag: str) -> list[dict]:
    """Build facts from a single AVA entry (used by California, Oregon, Washington builders)."""
    facts = []
    name = ava["name"]
    county = ava.get("county", "")
    parent = ava.get("parent_ava")
    state = ava.get("state", state_tag.replace("_", " ").title())
    entities = [{"type": "region", "name": name}]
    base_tags = ["usa", state_tag, name.lower().replace(" ", "_").replace(".", "")]

    # Parent AVA relationship
    if parent:
        facts.append(_make_fact(
            f"The {name} AVA is a sub-appellation of the {parent} AVA.",
            domain="wine_regions",
            source_id=source_id,
            subdomain="usa_ava",
            entities=entities + [{"type": "region", "name": parent}],
            tags=base_tags + ["ava"],
        ))

    # County/location
    if county:
        loc = f" in {county} County" if "/" not in county else f" spanning {county} counties"
        facts.append(_make_fact(
            f"The {name} AVA is located{loc}, {state}.",
            domain="wine_regions",
            source_id=source_id,
            subdomain="usa_ava",
            entities=entities,
            tags=base_tags + ["ava"],
        ))

    # Climate
    facts.append(_make_fact(
        f"The {name} AVA has a {ava['climate']} climate.",
        domain="wine_regions",
        source_id=source_id,
        subdomain="climate",
        entities=entities,
        tags=base_tags + ["climate"],
    ))
    if ava.get("climate_details"):
        facts.append(_make_fact(
            f"{ava['climate_details']}.",
            domain="wine_regions",
            source_id=source_id,
            subdomain="climate",
            entities=entities,
            tags=base_tags + ["climate"],
        ))

    # Soil types
    if ava.get("soil_types"):
        soil_list = ", ".join(ava["soil_types"])
        facts.append(_make_fact(
            f"The predominant soil types in the {name} AVA include {soil_list}.",
            domain="wine_regions",
            source_id=source_id,
            subdomain="terroir",
            entities=entities,
            tags=base_tags + ["soil", "terroir"],
        ))

    # Soil details
    if ava.get("soil_details"):
        facts.append(_make_fact(
            f"{ava['soil_details']}.",
            domain="wine_regions",
            source_id=source_id,
            subdomain="terroir",
            entities=entities,
            tags=base_tags + ["soil", "terroir"],
        ))

    # Elevation
    if ava.get("elevation_range"):
        facts.append(_make_fact(
            f"Vineyards in the {name} AVA are planted at elevations ranging from {ava['elevation_range']}.",
            domain="viticulture",
            source_id=source_id,
            subdomain="terrain",
            entities=entities,
            tags=base_tags + ["elevation"],
        ))

    # Vineyard area
    if ava.get("vineyard_area_acres"):
        facts.append(_make_fact(
            f"The {name} AVA has approximately {ava['vineyard_area_acres']:,} acres under vine.",
            domain="wine_regions",
            source_id=source_id,
            subdomain="usa_ava",
            entities=entities,
            tags=base_tags + ["area"],
        ))

    # Key grapes
    if ava.get("key_grapes"):
        grape_list = ", ".join(ava["key_grapes"])
        grape_entities = [{"type": "grape", "name": g} for g in ava["key_grapes"]]
        facts.append(_make_fact(
            f"The key grape varieties grown in the {name} AVA include {grape_list}.",
            domain="grape_varieties",
            source_id=source_id,
            subdomain="usa_grapes",
            entities=entities + grape_entities,
            tags=base_tags + ["grapes"],
        ))

    # Wine styles
    if ava.get("wine_styles"):
        style_list = ", ".join(ava["wine_styles"])
        facts.append(_make_fact(
            f"The {name} AVA is known for producing {style_list}.",
            domain="wine_regions",
            source_id=source_id,
            subdomain="wine_styles",
            entities=entities,
            tags=base_tags + ["styles"],
        ))

    # Notes
    if ava.get("notes"):
        facts.append(_make_fact(
            f"{ava['notes']}.",
            domain="wine_regions",
            source_id=source_id,
            subdomain="usa_ava",
            entities=entities,
            tags=base_tags + ["notes"],
        ))

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# FACT BUILDERS
# ═══════════════════════════════════════════════════════════════════════════════


def _build_california_facts(source_id: str) -> list[dict]:
    """Build facts about California wine regions (Napa, Sonoma, Central Coast, other)."""
    facts = []

    for ava in NAPA_VALLEY_AVAS:
        facts.extend(_build_ava_facts(ava, source_id, "california"))

    for ava in SONOMA_AVAS:
        facts.extend(_build_ava_facts(ava, source_id, "california"))

    for ava in CENTRAL_COAST_AVAS:
        facts.extend(_build_ava_facts(ava, source_id, "california"))

    for ava in OTHER_CALIFORNIA_AVAS:
        facts.extend(_build_ava_facts(ava, source_id, "california"))

    logger.info(f"Built {len(facts)} California AVA facts")
    return facts


def _build_oregon_facts(source_id: str) -> list[dict]:
    """Build facts about Oregon wine regions (Willamette Valley sub-AVAs and others)."""
    facts = []

    for ava in OREGON_AVAS:
        facts.extend(_build_ava_facts(ava, source_id, "oregon"))

    logger.info(f"Built {len(facts)} Oregon AVA facts")
    return facts


def _build_washington_facts(source_id: str) -> list[dict]:
    """Build facts about Washington State wine regions (Columbia Valley sub-AVAs)."""
    facts = []

    for ava in WASHINGTON_AVAS:
        facts.extend(_build_ava_facts(ava, source_id, "washington"))

    logger.info(f"Built {len(facts)} Washington AVA facts")
    return facts


def _build_other_us_facts(source_id: str) -> list[dict]:
    """Build facts about other US wine regions (NY, VA, TX, MI)."""
    facts = []

    for ava in OTHER_US_AVAS:
        facts.extend(_build_ava_facts(ava, source_id, ava["state"].lower().replace(" ", "_")))

    logger.info(f"Built {len(facts)} other US region facts")
    return facts


def _build_grape_variety_facts(source_id: str) -> list[dict]:
    """Build facts about US grape variety profiles."""
    facts = []

    for grape in US_GRAPE_PROFILES:
        name = grape["name"]
        entities = [{"type": "grape", "name": name}]
        base_tags = ["usa", "grape", name.lower().replace(" ", "_")]

        # US context
        facts.append(_make_fact(
            f"{grape['us_context']}",
            domain="grape_varieties",
            source_id=source_id,
            subdomain="usa_grapes",
            entities=entities,
            tags=base_tags,
        ))

        # Key regions
        if grape.get("key_regions"):
            region_list = ", ".join(grape["key_regions"])
            region_entities = [{"type": "region", "name": r} for r in grape["key_regions"]]
            facts.append(_make_fact(
                f"The key US regions for {name} include {region_list}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="usa_grapes",
                entities=entities + region_entities,
                tags=base_tags + ["regions"],
            ))

        # US styles
        if grape.get("us_styles"):
            facts.append(_make_fact(
                f"{grape['us_styles']}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="usa_grapes",
                entities=entities,
                tags=base_tags + ["styles"],
            ))

        # Notable facts
        for nf in grape.get("notable_facts", []):
            # Strip trailing period if already present, then add one
            text = nf.rstrip(".")
            facts.append(_make_fact(
                f"{text}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="usa_grapes",
                entities=entities,
                tags=base_tags,
            ))

    logger.info(f"Built {len(facts)} US grape variety facts")
    return facts


def _build_classification_facts(source_id: str) -> list[dict]:
    """Build facts about US wine classification and labeling regulations."""
    facts = []

    for section in US_CLASSIFICATION_DATA:
        topic = section["topic"]
        base_tags = ["usa", "classification", topic.lower().replace(" ", "_")]
        entities = [{"type": "regulation", "name": topic}]

        for fact_text in section["facts"]:
            text = fact_text.rstrip(".")
            facts.append(_make_fact(
                f"{text}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="usa_classification",
                entities=entities,
                tags=base_tags,
            ))

    logger.info(f"Built {len(facts)} US classification/regulation facts")
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
        "california": _build_california_facts,
        "oregon": _build_oregon_facts,
        "washington": _build_washington_facts,
        "other": _build_other_us_facts,
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
        click.echo(f"\n[DRY RUN] Would insert {len(facts)} facts from US Wine Regions Reference Database")

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

    logger.info(f"Inserted {inserted} new facts from US Wine Regions Reference Database (duplicates skipped)")
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

    # (g) Overlap check with TTB scraper patterns
    ttb_patterns = [
        r"^.+ is an? (established )?AVA in",
        r"^.+ AVA was established in \d{4}",
        r"^The TTB ",
    ]
    overlap_count = 0
    for f in facts:
        for pat in ttb_patterns:
            if re.match(pat, f["fact_text"]):
                overlap_count += 1
                break
    click.echo(f"\n  Potential TTB scraper overlaps: {overlap_count}")


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
        "California": _build_california_facts,
        "Oregon": _build_oregon_facts,
        "Washington": _build_washington_facts,
        "Other US": _build_other_us_facts,
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
    type=click.Choice(["california", "oregon", "washington", "other", "grape", "classification"]),
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
    """OenoBench USA Wine Enrichment Scraper — Terroir, climate, soil, and classification data for US wine regions."""
    logger.add("data/logs/usa_enrichment_{time}.log", rotation="10 MB")

    if list_sources:
        click.echo("\nAvailable data categories:")
        click.echo(f"  {'california':16s} — {len(NAPA_VALLEY_AVAS) + len(SONOMA_AVAS) + len(CENTRAL_COAST_AVAS) + len(OTHER_CALIFORNIA_AVAS)} California AVAs (Napa, Sonoma, Central Coast, other)")
        click.echo(f"  {'oregon':16s} — {len(OREGON_AVAS)} Oregon AVAs (Willamette Valley sub-AVAs and others)")
        click.echo(f"  {'washington':16s} — {len(WASHINGTON_AVAS)} Washington AVAs (Columbia Valley sub-AVAs)")
        click.echo(f"  {'other':16s} — {len(OTHER_US_AVAS)} other US regions (NY, VA, TX, MI)")
        click.echo(f"  {'grape':16s} — {len(US_GRAPE_PROFILES)} US grape variety profiles")
        click.echo(f"  {'classification':16s} — {len(US_CLASSIFICATION_DATA)} classification/regulation topics")
        click.echo(f"\nKnowledge base coverage:")
        click.echo(f"  Napa Valley AVAs:    {len(NAPA_VALLEY_AVAS)}")
        click.echo(f"  Sonoma AVAs:         {len(SONOMA_AVAS)}")
        click.echo(f"  Central Coast AVAs:  {len(CENTRAL_COAST_AVAS)}")
        click.echo(f"  Other CA AVAs:       {len(OTHER_CALIFORNIA_AVAS)}")
        click.echo(f"  Oregon AVAs:         {len(OREGON_AVAS)}")
        click.echo(f"  Washington AVAs:     {len(WASHINGTON_AVAS)}")
        click.echo(f"  Other US regions:    {len(OTHER_US_AVAS)}")
        click.echo(f"  Grape profiles:      {len(US_GRAPE_PROFILES)}")
        click.echo(f"  Classification topics: {len(US_CLASSIFICATION_DATA)}")
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
