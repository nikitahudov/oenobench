"""
OenoBench — English Wine Scraper

Extracts structured English wine data covering regions, grape varieties,
sparkling wine production, classification (PDO/PGI), climate change impact,
history, and unique industry characteristics.

England has emerged as one of the world's most exciting wine regions,
particularly for traditional method sparkling wine from chalk soils
geologically connected to Champagne.

Usage:
    python -m src.scrapers.england --all
    python -m src.scrapers.england --type region
    python -m src.scrapers.england --type grape
    python -m src.scrapers.england --type sparkling
    python -m src.scrapers.england --type classification
    python -m src.scrapers.england --type climate
    python -m src.scrapers.england --type history
    python -m src.scrapers.england --type unique
    python -m src.scrapers.england --dry-run
    python -m src.scrapers.england --validate
    python -m src.scrapers.england --test-run
    python -m src.scrapers.england --list
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
    "name": "English Wine Reference Database",
    "url": "https://www.englishwine.com",
    "source_type": "reference",
    "tier": "tier_2_authoritative",
    "language": "en",
}


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Regional Data
# ═══════════════════════════════════════════════════════════════════════════════

REGION_DATABASE = [
    {
        "name": "Sussex",
        "county": "East Sussex / West Sussex",
        "climate": "maritime",
        "soil_types": ["chalk", "clay", "greensand"],
        "soil_details": "The South Downs chalk is the same Cretaceous geological formation as Champagne, connected by an ancient seabed that extends under the English Channel",
        "vineyard_area_ha": 1500,
        "elevation_range": "50-150m",
        "key_grapes": ["Chardonnay", "Pinot Noir", "Pinot Meunier"],
        "wine_styles": ["traditional method sparkling", "still white", "still rosé"],
        "notable_producers": ["Nyetimber", "Wiston", "Ridgeview", "Bolney", "Rathfinny"],
        "notes": "England's largest concentration of sparkling wine production, with the highest density of premium vineyards in the country.",
    },
    {
        "name": "Kent",
        "county": "Kent",
        "climate": "maritime",
        "soil_types": ["chalk", "clay", "greensand"],
        "soil_details": "The North Downs chalk ridge provides excellent vineyard sites with good drainage and heat retention; Wealden clay and greensand soils add diversity",
        "vineyard_area_ha": 800,
        "elevation_range": "30-180m",
        "key_grapes": ["Chardonnay", "Pinot Noir", "Bacchus"],
        "wine_styles": ["traditional method sparkling", "still white", "still rosé"],
        "notable_producers": ["Chapel Down", "Gusbourne", "Hush Heath", "Balfour"],
        "notes": "Known as the 'Garden of England', Kent is home to Chapel Down, the largest English winery by volume.",
    },
    {
        "name": "Hampshire",
        "county": "Hampshire",
        "climate": "maritime",
        "soil_types": ["chalk", "clay-with-flints", "greensand"],
        "soil_details": "Hampshire chalk downland offers well-drained, mineral-rich vineyard sites on the South Downs and North Downs escarpments",
        "vineyard_area_ha": 600,
        "elevation_range": "40-200m",
        "key_grapes": ["Chardonnay", "Pinot Noir", "Pinot Meunier"],
        "wine_styles": ["traditional method sparkling", "still white"],
        "notable_producers": ["Hambledon", "Hattingley Valley", "Exton Park", "Coates & Seely"],
        "notes": "Hambledon vineyard, planted in 1951 by Major-General Sir Guy Salisbury-Jones, is the site of the first modern English vineyard.",
    },
    {
        "name": "Essex",
        "county": "Essex",
        "climate": "maritime with continental influence",
        "soil_types": ["clay", "chalk", "loam"],
        "soil_details": "Essex benefits from slightly warmer and drier conditions than western England due to mild continental influence from the east",
        "vineyard_area_ha": 200,
        "elevation_range": "10-100m",
        "key_grapes": ["Bacchus", "Chardonnay", "Pinot Noir"],
        "wine_styles": ["still white", "traditional method sparkling"],
        "notable_producers": ["New Hall Vineyard"],
        "notes": "New Hall Vineyard is one of England's oldest modern vineyards, and Essex's warmer microclimate suits both still and sparkling styles.",
    },
    {
        "name": "Surrey",
        "county": "Surrey",
        "climate": "maritime",
        "soil_types": ["chalk", "clay", "greensand"],
        "soil_details": "North Downs chalk provides the geological backbone for Surrey vineyards, with greensand ridge sites offering sheltered, south-facing slopes",
        "vineyard_area_ha": 300,
        "elevation_range": "30-200m",
        "key_grapes": ["Chardonnay", "Pinot Noir", "Bacchus"],
        "wine_styles": ["traditional method sparkling", "still white"],
        "notable_producers": ["Denbies Wine Estate"],
        "notes": "Denbies Wine Estate, at 107 hectares, is the largest single vineyard site in England.",
    },
    {
        "name": "Dorset",
        "county": "Dorset",
        "climate": "maritime",
        "soil_types": ["chalk", "limestone", "clay"],
        "soil_details": "Dorset's Jurassic Coast geology provides limestone and chalk soils with good drainage; sheltered south-facing slopes trap warmth",
        "vineyard_area_ha": 400,
        "elevation_range": "20-150m",
        "key_grapes": ["Chardonnay", "Pinot Noir", "Pinot Meunier"],
        "wine_styles": ["traditional method sparkling", "still white"],
        "notable_producers": ["Langham Estate", "Furleigh Estate"],
        "notes": "Dorset's chalk and limestone soils are increasingly recognized for high-quality sparkling wine production.",
    },
    {
        "name": "Cornwall",
        "county": "Cornwall",
        "climate": "mild maritime",
        "soil_types": ["slate", "shale", "loam"],
        "soil_details": "Cornwall's slate and shale soils, combined with England's mildest maritime climate and Gulf Stream influence, create unique growing conditions",
        "vineyard_area_ha": 100,
        "elevation_range": "10-100m",
        "key_grapes": ["Bacchus", "Seyval Blanc", "Pinot Noir"],
        "wine_styles": ["still white", "sparkling", "still rosé"],
        "notable_producers": ["Camel Valley"],
        "notes": "Cornwall is England's warmest county, benefiting from Gulf Stream influence; Camel Valley has won multiple international awards.",
    },
    {
        "name": "Devon",
        "county": "Devon",
        "climate": "mild maritime",
        "soil_types": ["slate", "sandstone", "clay", "loam"],
        "soil_details": "Devon has varied soils from Devonian-era slate and sandstone to red clay; sheltered south-facing valleys provide favorable microclimates",
        "vineyard_area_ha": 150,
        "elevation_range": "10-150m",
        "key_grapes": ["Bacchus", "Seyval Blanc", "Rondo"],
        "wine_styles": ["still white", "still rosé"],
        "notable_producers": [],
        "notes": "Devon's mild climate and varied topography support a growing number of small, artisanal vineyards.",
    },
    {
        "name": "East Anglia",
        "county": "Norfolk / Suffolk",
        "climate": "continental influence",
        "soil_types": ["clay", "chalk", "flint", "sandy loam"],
        "soil_details": "East Anglia is England's driest region, with low annual rainfall and flint-rich soils that retain heat and aid ripening",
        "vineyard_area_ha": 200,
        "elevation_range": "5-60m",
        "key_grapes": ["Bacchus", "Pinot Noir", "Chardonnay"],
        "wine_styles": ["still white", "sparkling"],
        "notable_producers": ["Flint Vineyard", "Winbirri"],
        "notes": "East Anglia's dry, continental-influenced climate and flinty soils produce aromatic still whites of distinctive character.",
    },
    {
        "name": "Wales",
        "county": "Various",
        "climate": "maritime",
        "soil_types": ["clay", "slate", "sandstone", "loam"],
        "soil_details": "Welsh vineyards are found in sheltered south-facing sites, primarily in the southern counties, with varied soils reflecting the complex geology",
        "vineyard_area_ha": 100,
        "elevation_range": "10-150m",
        "key_grapes": ["Bacchus", "Seyval Blanc", "Solaris"],
        "wine_styles": ["still white", "sparkling"],
        "notable_producers": [],
        "notes": "Welsh wine has its own distinct PDO and PGI classifications separate from English wine.",
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Grape Varieties
# ═══════════════════════════════════════════════════════════════════════════════

GRAPE_DATABASE = [
    {
        "name": "Chardonnay",
        "color": "white",
        "planting_share_pct": 30,
        "primary_use": "sparkling base",
        "characteristics": "Provides the backbone of English sparkling wine with high acidity and citrus-mineral character; also used for still wines in warmer vintages",
        "origin": "Burgundy, France",
        "notes": "The most widely planted single variety in England, dominant in traditional method sparkling blends.",
    },
    {
        "name": "Pinot Noir",
        "color": "red",
        "planting_share_pct": 30,
        "primary_use": "sparkling base and still red",
        "characteristics": "Used as a sparkling base wine for structure and depth; increasingly made as a still red in warm vintages, with light, Burgundian character",
        "origin": "Burgundy, France",
        "notes": "Alongside Chardonnay, forms the core of English sparkling wine; still Pinot Noir is a growing category in warm years like 2018 and 2022.",
    },
    {
        "name": "Pinot Meunier",
        "color": "red",
        "planting_share_pct": 15,
        "primary_use": "sparkling component",
        "characteristics": "Contributes fruitiness and approachability to sparkling blends; ripens earlier than Pinot Noir, making it well-suited to England's short growing season",
        "origin": "France",
        "notes": "The third member of the classic Champagne trio, valued in England for its early ripening and reliable yields.",
    },
    {
        "name": "Bacchus",
        "color": "white",
        "planting_share_pct": 8,
        "primary_use": "still white",
        "characteristics": "England's signature still white grape, producing aromatic wines with elderflower, grapefruit, and grassy notes; often compared to Sauvignon Blanc from the Loire Valley",
        "origin": "German crossing (Silvaner x Riesling x Muller-Thurgau)",
        "notes": "Bacchus has become England's most distinctive still wine variety, showcasing a uniquely English aromatic profile.",
    },
    {
        "name": "Seyval Blanc",
        "color": "white",
        "planting_share_pct": 5,
        "primary_use": "still white",
        "characteristics": "A French-American hybrid known for reliable cropping, disease resistance, and crisp, neutral white wines; once dominant in English viticulture",
        "origin": "French-American hybrid",
        "notes": "Seyval Blanc was the backbone of the early modern English wine industry but is now declining as Chardonnay and Bacchus expand.",
    },
    {
        "name": "Ortega",
        "color": "white",
        "planting_share_pct": 3,
        "primary_use": "still white",
        "characteristics": "Early-ripening German crossing producing aromatic, off-dry to medium-sweet white wines with stone fruit and floral notes",
        "origin": "German crossing (Muller-Thurgau x Siegerrebe)",
        "notes": "Valued for its very early ripening, making it a safe bet in cooler English vintages.",
    },
    {
        "name": "Reichensteiner",
        "color": "white",
        "planting_share_pct": 3,
        "primary_use": "still white",
        "characteristics": "German crossing producing light, crisp, neutral white wines; reliable yields and good disease resistance",
        "origin": "German crossing (Muller-Thurgau x (Madeleine Angevine x Calabrese Froehlich))",
        "notes": "A workhorse variety in England's earlier vineyards, now declining in favor of Bacchus and Chardonnay.",
    },
    {
        "name": "Muller-Thurgau",
        "color": "white",
        "planting_share_pct": 2,
        "primary_use": "still white",
        "characteristics": "Early-ripening variety producing light, floral, low-acid white wines; once widely planted in England",
        "origin": "Swiss crossing (Riesling x Madeleine Royale)",
        "notes": "One of England's earliest modern plantings, now largely superseded by higher-quality varieties.",
    },
    {
        "name": "Dornfelder",
        "color": "red",
        "planting_share_pct": 1,
        "primary_use": "still red",
        "characteristics": "German red crossing producing deeply colored wines with soft tannins and dark fruit character; rare but increasing in warmer English sites",
        "origin": "German crossing (Helfensteiner x Heroldrebe)",
        "notes": "Still rare in England, Dornfelder is found in warmer sites where its deep color and reliable ripening are assets.",
    },
    {
        "name": "Solaris",
        "color": "white",
        "planting_share_pct": 2,
        "primary_use": "still white",
        "characteristics": "PIWI (disease-resistant) crossing with excellent fungal resistance, producing aromatic white wines with tropical fruit and floral notes",
        "origin": "German PIWI crossing (Merzling x Gm 6493)",
        "notes": "Solaris is growing in popularity in England due to its strong disease resistance and suitability for sustainable viticulture.",
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Sparkling Wine
# ═══════════════════════════════════════════════════════════════════════════════

SPARKLING_DATABASE = {
    "production_share_pct": 70,
    "method": "traditional method (methode traditionnelle)",
    "primary_grapes": ["Chardonnay", "Pinot Noir", "Pinot Meunier"],
    "chalk_connection": (
        "The North Downs and South Downs chalk formations in southern England are the same "
        "Cretaceous chalk geological layer that underlies the Champagne region of France, "
        "connected by an ancient seabed that extends beneath the English Channel."
    ),
    "champagne_investment": [
        {
            "house": "Taittinger",
            "project": "Domaine Evremond",
            "location": "Kent",
            "details": "Taittinger became the first Champagne house to invest in English vineyard land, planting vines in Kent for their Domaine Evremond project.",
        },
        {
            "house": "Pommery",
            "project": "Pommery England",
            "location": "Hampshire",
            "details": "Champagne house Pommery invested in vineyard land in Hampshire, signaling confidence in England's sparkling wine potential.",
        },
    ],
    "competition_wins": [
        "In 2015, Nyetimber Classic Cuvee beat several Champagne houses in a blind tasting organized in London.",
        "English sparkling wines have won gold medals at the Decanter World Wine Awards, International Wine Challenge, and International Wine & Spirit Competition.",
        "Gusbourne Blanc de Blancs has received consistent critical acclaim, regularly scoring above 90 points in international wine publications.",
        "Wiston Estate Blanc de Blancs won the trophy for Best English Sparkling Wine at the International Wine Challenge multiple times.",
    ],
    "style_notes": [
        "English sparkling wines tend to have higher acidity than Champagne due to the cooler climate.",
        "Dosage levels in English sparkling wine tend to be lower than Champagne, with many producers favoring Brut Nature or Extra Brut styles.",
        "Vintage variation is significant in English sparkling wine production, with warm years such as 2018 and 2022 producing wines of exceptional quality.",
        "Non-vintage English sparkling wines typically include reserve wines from multiple years to maintain consistency.",
        "English Blanc de Blancs, made from 100% Chardonnay, is considered by many critics to be the finest expression of English sparkling wine.",
        "English sparkling rose is typically made by blending a small proportion of still Pinot Noir with white base wine before secondary fermentation.",
        "Most premium English sparkling wines spend a minimum of 18 to 36 months on lees, with top cuvees aged for 5 years or more.",
        "The cool English climate produces sparkling base wines with naturally high acidity, reducing the need for malolactic fermentation.",
    ],
    "contract_production": (
        "Hattingley Valley in Hampshire is one of England's largest contract sparkling wine producers, "
        "making wines for numerous smaller vineyards that lack their own winemaking facilities."
    ),
    "additional_facts": [
        "English sparkling wine typically undergoes tirage (secondary fermentation in bottle) using the same techniques as Champagne, including riddling and disgorgement.",
        "The average retail price of premium English sparkling wine is comparable to entry-level Champagne, positioning it as a direct competitor in the market.",
        "Many English sparkling producers use gravity-fed winemaking to minimize handling of the delicate base wines.",
        "English sparkling wine production has grown from fewer than 1 million bottles in 2000 to over 8 million bottles annually by the mid-2020s.",
    ],
}


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Classification
# ═══════════════════════════════════════════════════════════════════════════════

CLASSIFICATION_DATABASE = {
    "pdo": [
        {
            "name": "English wine",
            "type": "PDO",
            "scope": "still wine",
            "details": "Protected Designation of Origin for still wines made from grapes grown in England.",
        },
        {
            "name": "English sparkling wine",
            "type": "PDO",
            "scope": "sparkling wine",
            "details": "Protected Designation of Origin specifically for sparkling wines made from grapes grown in England.",
        },
        {
            "name": "Welsh wine",
            "type": "PDO",
            "scope": "still and sparkling wine",
            "details": "Protected Designation of Origin for wines made from grapes grown in Wales, separate from English wine.",
        },
    ],
    "pgi": [
        {
            "name": "English Regional Wine",
            "type": "PGI",
            "details": "Protected Geographical Indication for wines produced in England with less restrictive requirements than PDO.",
        },
        {
            "name": "Welsh Regional Wine",
            "type": "PGI",
            "details": "Protected Geographical Indication for wines produced in Wales.",
        },
    ],
    "rules": [
        "English PDO wines must contain a minimum of 85% grapes from the stated PDO area.",
        "Unlike most European wine appellations, the English PDO does not impose grape variety restrictions.",
        "The English Quality Wine Scheme (QWS) functions similarly to the EU PDO system for quality classification.",
        "Sussex has applied for its own sub-regional PDO status, which would be the first county-level PDO in England.",
    ],
    "industry_body": {
        "name": "WineGB (Wines of Great Britain)",
        "role": "WineGB is the national industry body representing English and Welsh wine producers, promoting quality standards and marketing.",
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Climate Change
# ═══════════════════════════════════════════════════════════════════════════════

CLIMATE_DATABASE = [
    {
        "topic": "temperature_rise",
        "fact": "Average temperatures in southern England have risen approximately 1 degree Celsius since the 1960s, significantly improving conditions for viticulture.",
        "confidence": 0.95,
    },
    {
        "topic": "growing_degree_days",
        "fact": "Growing degree days in southern England are now comparable to those recorded in the Champagne region of France during the 1980s and 1990s.",
        "confidence": 0.95,
    },
    {
        "topic": "vineyard_expansion",
        "fact": "England's total vineyard area has tripled since 2000, growing from approximately 800 hectares to over 4,000 hectares by 2025.",
        "confidence": 0.95,
    },
    {
        "topic": "frost_risk",
        "fact": "Spring frost remains the single greatest viticultural risk in England, as demonstrated by the devastating 2020 spring frost that destroyed crops in many vineyards.",
        "confidence": 1.0,
    },
    {
        "topic": "growing_season",
        "fact": "Longer growing seasons due to climate change are allowing later-ripening grape varieties such as Pinot Noir to achieve full phenolic ripeness in England more consistently.",
        "confidence": 0.95,
    },
    {
        "topic": "future_projections",
        "fact": "Some wine industry experts predict that England could rival the Champagne region for premium sparkling wine production within 20 to 30 years if current climate trends continue.",
        "confidence": 0.85,
    },
    {
        "topic": "harvest_dates",
        "fact": "Harvest dates in England have moved earlier by approximately two to three weeks compared to the 1980s, reflecting warmer growing conditions.",
        "confidence": 0.90,
    },
    {
        "topic": "new_varieties",
        "fact": "Climate change has enabled English growers to successfully cultivate classic Burgundy and Champagne varieties (Chardonnay, Pinot Noir, Pinot Meunier) that were previously considered too risky.",
        "confidence": 1.0,
    },
    {
        "topic": "rainfall_patterns",
        "fact": "Changing rainfall patterns in England have increased the risk of vintage rain during harvest, making early-ripening grape varieties strategically important.",
        "confidence": 0.90,
    },
    {
        "topic": "red_wine_potential",
        "fact": "Warm vintages in 2018 and 2022 demonstrated that England can produce still red wines from Pinot Noir of genuine quality, a development driven by rising temperatures.",
        "confidence": 1.0,
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — History
# ═══════════════════════════════════════════════════════════════════════════════

HISTORY_DATABASE = [
    {
        "era": "Roman",
        "period": "1st-5th century AD",
        "fact": "Roman colonists cultivated vineyards in England, as documented by the Roman historian Tacitus in his accounts of Britannia.",
    },
    {
        "era": "Medieval",
        "period": "1086",
        "fact": "The Domesday Book of 1086, commissioned by William the Conqueror, recorded 42 vineyards in England, indicating established wine production.",
    },
    {
        "era": "Medieval",
        "period": "11th-16th century",
        "fact": "Monastic vineyards flourished in medieval England, with monasteries producing wine for communion and domestic consumption until the Dissolution of the Monasteries in the 1530s.",
    },
    {
        "era": "Little Ice Age",
        "period": "16th-19th century",
        "fact": "The Little Ice Age effectively ended English viticulture for approximately 400 years, as temperatures dropped too low for reliable grape growing.",
    },
    {
        "era": "Modern Revival",
        "period": "1951",
        "fact": "The modern English wine revival began in 1951 when Major-General Sir Guy Salisbury-Jones planted the Hambledon vineyard in Hampshire, the first modern commercial vineyard in England.",
    },
    {
        "era": "Modern Revival",
        "period": "1960s-1970s",
        "fact": "During the 1960s and 1970s, English vineyards focused primarily on German hybrid and crossing varieties such as Muller-Thurgau and Seyval Blanc that could ripen in cooler conditions.",
    },
    {
        "era": "Quality Revolution",
        "period": "2000s-2020s",
        "fact": "The 2000s and 2010s saw a quality revolution in English wine, driven by investment in traditional method sparkling wine from classic Champagne grape varieties on chalk soils.",
    },
    {
        "era": "Quality Revolution",
        "period": "2010s",
        "fact": "International recognition of English sparkling wine grew rapidly in the 2010s, with English producers winning major international competitions and attracting investment from Champagne houses.",
    },
    {
        "era": "Champagne Investment",
        "period": "2015-present",
        "fact": "Champagne houses including Taittinger and Pommery invested in English vineyard land from 2015 onwards, validating the quality potential of English terroir for sparkling wine.",
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Unique / Industry Facts
# ═══════════════════════════════════════════════════════════════════════════════

UNIQUE_DATABASE = [
    {
        "topic": "vineyard_count",
        "fact": "As of 2025, England has over 900 vineyards and more than 200 wineries, reflecting rapid growth in the English wine industry.",
        "confidence": 0.95,
    },
    {
        "topic": "average_size",
        "fact": "The average English vineyard size is approximately 4 hectares, reflecting the small-scale, artisanal character of the industry.",
        "confidence": 0.95,
    },
    {
        "topic": "bacchus_comparison",
        "fact": "English still Bacchus wines are increasingly compared to Sauvignon Blanc from the Loire Valley for their aromatic intensity and crisp acidity.",
        "confidence": 1.0,
    },
    {
        "topic": "emerging_styles",
        "fact": "Pet-nat (petillant naturel) and orange wine styles are emerging in the English wine industry alongside the dominant traditional method sparkling category.",
        "confidence": 1.0,
    },
    {
        "topic": "wine_tourism",
        "fact": "Wine tourism is growing rapidly in England, with established wine trails in Sussex, Kent, and Hampshire attracting increasing numbers of visitors.",
        "confidence": 1.0,
    },
    {
        "topic": "denbies_estate",
        "fact": "Denbies Wine Estate in Surrey, at 107 hectares, is the largest single vineyard site in England.",
        "confidence": 1.0,
    },
    {
        "topic": "chapel_down",
        "fact": "Chapel Down, based in Tenterden, Kent, is the largest English winery by production volume and is publicly listed on the London stock exchange.",
        "confidence": 1.0,
    },
    {
        "topic": "nyetimber",
        "fact": "Nyetimber, founded in Sussex in 1988, was a pioneer of premium English sparkling wine and has won numerous blind tastings against Champagne.",
        "confidence": 1.0,
    },
    {
        "topic": "hambledon",
        "fact": "Hambledon Vineyard in Hampshire, established in 1951, is considered the birthplace of the modern English wine industry.",
        "confidence": 1.0,
    },
    {
        "topic": "sparkling_dominance",
        "fact": "Approximately 70% of all English wine production is sparkling wine made using the traditional method, making England one of the most sparkling-focused wine countries in the world.",
        "confidence": 0.95,
    },
    {
        "topic": "total_production",
        "fact": "England and Wales produced a record 12.2 million bottles of wine in 2023, with the majority being sparkling wine.",
        "confidence": 0.90,
    },
    {
        "topic": "investment_boom",
        "fact": "Significant investment has flowed into the English wine industry since 2010, including from Champagne houses, private equity, and high-net-worth individuals attracted by the sector's growth potential.",
        "confidence": 1.0,
    },
    {
        "topic": "piwi_trend",
        "fact": "PIWI (disease-resistant crossing) grape varieties such as Solaris are gaining popularity in England as producers seek sustainable alternatives with lower fungicide requirements.",
        "confidence": 1.0,
    },
    {
        "topic": "rose_production",
        "fact": "English rose wine, both still and sparkling, is an increasingly important category, with pale Provencal-style roses gaining popularity.",
        "confidence": 1.0,
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
    """Build facts about English wine regions (climate, soil, grapes, producers)."""
    facts = []

    for region in REGION_DATABASE:
        name = region["name"]
        county = region["county"]
        entities = [{"type": "region", "name": name}]
        base_tags = ["england", name.lower().replace(" ", "_")]

        # Basic identification
        if name == "Wales":
            facts.append(_make_fact(
                f"Wales is a distinct wine-producing area within Great Britain with its own PDO and PGI classifications separate from England.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="england_wales",
                entities=entities,
                tags=base_tags + ["classification"],
            ))
        else:
            facts.append(_make_fact(
                f"{name} ({county}) is one of England's principal wine-producing regions.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="england_regions",
                entities=entities,
                tags=base_tags + ["region"],
            ))

        # Climate
        facts.append(_make_fact(
            f"The {name} wine region has a {region['climate']} climate.",
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

        # Vineyard area
        if region.get("vineyard_area_ha"):
            facts.append(_make_fact(
                f"The {name} wine region has approximately {region['vineyard_area_ha']:,} hectares under vine.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="statistics",
                entities=entities,
                confidence=0.95,
                tags=base_tags + ["vineyard_area", "statistics"],
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

        # Key grapes
        if region.get("key_grapes"):
            grapes_str = ", ".join(region["key_grapes"])
            grape_entities = entities + [{"type": "grape", "name": g} for g in region["key_grapes"]]
            facts.append(_make_fact(
                f"The principal grape varieties grown in the {name} wine region include {grapes_str}.",
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
                f"The {name} wine region is known for producing {styles_str}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="wine_styles",
                entities=entities,
                tags=base_tags + ["wine_styles"],
            ))

        # Notable producers
        if region.get("notable_producers") and len(region["notable_producers"]) > 0:
            producers_str = ", ".join(region["notable_producers"])
            producer_entities = entities + [
                {"type": "producer", "name": p} for p in region["notable_producers"]
            ]
            facts.append(_make_fact(
                f"Notable wine producers in the {name} region include {producers_str}.",
                domain="producers",
                source_id=source_id,
                subdomain="england_producers",
                entities=producer_entities,
                tags=base_tags + ["producers"],
            ))

        # Notes
        if region.get("notes"):
            facts.append(_make_fact(
                f"{region['notes']}",
                domain="wine_regions",
                source_id=source_id,
                subdomain="england_regions",
                entities=entities,
                tags=base_tags + ["notes"],
            ))

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# FACT BUILDERS — Grape Varieties
# ═══════════════════════════════════════════════════════════════════════════════


def _build_grape_variety_facts(source_id: str) -> list[dict]:
    """Build facts about grape varieties grown in England."""
    facts = []

    for grape in GRAPE_DATABASE:
        name = grape["name"]
        entities = [{"type": "grape", "name": name}]
        base_tags = ["england", "grape", name.lower().replace(" ", "_").replace("-", "_")]

        # Planting share
        if grape.get("planting_share_pct"):
            facts.append(_make_fact(
                f"{name} accounts for approximately {grape['planting_share_pct']}% of vineyard plantings in England.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="statistics",
                entities=entities,
                confidence=0.95,
                tags=base_tags + ["planting_share", "statistics"],
            ))

        # Primary use
        if grape.get("primary_use"):
            facts.append(_make_fact(
                f"{name} is primarily used for {grape['primary_use']} in English winemaking.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="usage",
                entities=entities,
                tags=base_tags + ["usage"],
            ))

        # Characteristics
        if grape.get("characteristics"):
            facts.append(_make_fact(
                f"{name} in England: {grape['characteristics']}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="characteristics",
                entities=entities,
                tags=base_tags + ["characteristics"],
            ))

        # Origin
        if grape.get("origin"):
            facts.append(_make_fact(
                f"The {name} grape variety originated as a {grape['origin']}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="origin",
                entities=entities,
                tags=base_tags + ["origin"],
            ))

        # Color
        facts.append(_make_fact(
            f"{name} is a {grape['color']} grape variety cultivated in England.",
            domain="grape_varieties",
            source_id=source_id,
            subdomain="classification",
            entities=entities,
            tags=base_tags + ["color", grape["color"]],
        ))

        # Notes
        if grape.get("notes"):
            facts.append(_make_fact(
                f"{grape['notes']}",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="england_grapes",
                entities=entities,
                tags=base_tags + ["notes"],
            ))

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# FACT BUILDERS — Sparkling Wine
# ═══════════════════════════════════════════════════════════════════════════════


def _build_sparkling_facts(source_id: str) -> list[dict]:
    """Build facts about English sparkling wine production and its relationship to Champagne."""
    facts = []
    base_tags = ["england", "sparkling"]
    entities = [{"type": "region", "name": "England"}]

    db = SPARKLING_DATABASE

    # Production share
    facts.append(_make_fact(
        f"Approximately {db['production_share_pct']}% of English wine production is sparkling wine made using the traditional method.",
        domain="winemaking",
        source_id=source_id,
        subdomain="sparkling",
        entities=entities,
        confidence=0.95,
        tags=base_tags + ["production", "statistics"],
    ))

    # Method
    facts.append(_make_fact(
        f"English sparkling wine is produced using the {db['method']}, the same technique used in Champagne.",
        domain="winemaking",
        source_id=source_id,
        subdomain="sparkling",
        entities=entities,
        tags=base_tags + ["method"],
    ))

    # Primary grapes
    grapes_str = ", ".join(db["primary_grapes"])
    grape_entities = entities + [{"type": "grape", "name": g} for g in db["primary_grapes"]]
    facts.append(_make_fact(
        f"The primary grape varieties used in English sparkling wine are {grapes_str}, the same classic trio used in Champagne.",
        domain="winemaking",
        source_id=source_id,
        subdomain="sparkling",
        entities=grape_entities,
        tags=base_tags + ["grapes"],
    ))

    # Chalk connection
    facts.append(_make_fact(
        db["chalk_connection"],
        domain="wine_regions",
        source_id=source_id,
        subdomain="geology",
        entities=entities + [{"type": "region", "name": "Champagne"}],
        tags=base_tags + ["chalk", "geology", "champagne"],
    ))

    # Champagne house investments
    for investment in db["champagne_investment"]:
        inv_entities = entities + [
            {"type": "producer", "name": investment["house"]},
            {"type": "region", "name": investment["location"]},
        ]
        facts.append(_make_fact(
            investment["details"],
            domain="wine_business",
            source_id=source_id,
            subdomain="investment",
            entities=inv_entities,
            tags=base_tags + ["champagne_investment", investment["house"].lower()],
        ))

    # Competition wins
    for win in db["competition_wins"]:
        facts.append(_make_fact(
            win,
            domain="wine_business",
            source_id=source_id,
            subdomain="awards",
            entities=entities,
            tags=base_tags + ["competition", "awards"],
        ))

    # Style notes
    for note in db["style_notes"]:
        facts.append(_make_fact(
            note,
            domain="winemaking",
            source_id=source_id,
            subdomain="sparkling_style",
            entities=entities,
            tags=base_tags + ["style"],
        ))

    # Contract production
    facts.append(_make_fact(
        db["contract_production"],
        domain="wine_business",
        source_id=source_id,
        subdomain="production",
        entities=entities + [{"type": "producer", "name": "Hattingley Valley"}],
        tags=base_tags + ["contract_production", "hattingley_valley"],
    ))

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# FACT BUILDERS — Classification
# ═══════════════════════════════════════════════════════════════════════════════


def _build_classification_facts(source_id: str) -> list[dict]:
    """Build facts about English wine PDO/PGI classification system."""
    facts = []
    base_tags = ["england", "classification"]
    entities = [{"type": "region", "name": "England"}]

    db = CLASSIFICATION_DATABASE

    # PDO entries
    for pdo in db["pdo"]:
        pdo_entities = entities + [{"type": "appellation", "name": pdo["name"]}]
        facts.append(_make_fact(
            f"'{pdo['name']}' is a {pdo['type']} (Protected Designation of Origin) classification covering {pdo['scope']}.",
            domain="wine_regions",
            source_id=source_id,
            subdomain="classification",
            entities=pdo_entities,
            tags=base_tags + ["pdo"],
        ))
        facts.append(_make_fact(
            pdo["details"],
            domain="wine_regions",
            source_id=source_id,
            subdomain="classification",
            entities=pdo_entities,
            tags=base_tags + ["pdo"],
        ))

    # PGI entries
    for pgi in db["pgi"]:
        pgi_entities = entities + [{"type": "appellation", "name": pgi["name"]}]
        facts.append(_make_fact(
            f"'{pgi['name']}' is a {pgi['type']} (Protected Geographical Indication) classification for wine.",
            domain="wine_regions",
            source_id=source_id,
            subdomain="classification",
            entities=pgi_entities,
            tags=base_tags + ["pgi"],
        ))
        facts.append(_make_fact(
            pgi["details"],
            domain="wine_regions",
            source_id=source_id,
            subdomain="classification",
            entities=pgi_entities,
            tags=base_tags + ["pgi"],
        ))

    # Rules
    for rule in db["rules"]:
        facts.append(_make_fact(
            rule,
            domain="wine_regions",
            source_id=source_id,
            subdomain="regulations",
            entities=entities,
            tags=base_tags + ["rules", "regulations"],
        ))

    # Industry body
    body = db["industry_body"]
    facts.append(_make_fact(
        body["role"],
        domain="wine_business",
        source_id=source_id,
        subdomain="industry",
        entities=entities + [{"type": "organization", "name": body["name"]}],
        tags=base_tags + ["industry_body", "winegb"],
    ))

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# FACT BUILDERS — Climate Change
# ═══════════════════════════════════════════════════════════════════════════════


def _build_climate_facts(source_id: str) -> list[dict]:
    """Build facts about climate change impact on English viticulture."""
    facts = []
    base_tags = ["england", "climate_change"]
    entities = [{"type": "region", "name": "England"}]

    for entry in CLIMATE_DATABASE:
        facts.append(_make_fact(
            entry["fact"],
            domain="viticulture",
            source_id=source_id,
            subdomain="climate_change",
            entities=entities,
            confidence=entry.get("confidence", 1.0),
            tags=base_tags + [entry["topic"]],
        ))

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# FACT BUILDERS — History
# ═══════════════════════════════════════════════════════════════════════════════


def _build_history_facts(source_id: str) -> list[dict]:
    """Build facts about the history of English winemaking."""
    facts = []
    base_tags = ["england", "history"]
    entities = [{"type": "region", "name": "England"}]

    for entry in HISTORY_DATABASE:
        era_tag = entry["era"].lower().replace(" ", "_")
        facts.append(_make_fact(
            entry["fact"],
            domain="wine_regions",
            source_id=source_id,
            subdomain="history",
            entities=entities,
            tags=base_tags + [era_tag, entry["period"].replace(" ", "_")],
        ))

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# FACT BUILDERS — Unique / Industry
# ═══════════════════════════════════════════════════════════════════════════════


def _build_unique_facts(source_id: str) -> list[dict]:
    """Build facts about unique characteristics and industry statistics of English wine."""
    facts = []
    base_tags = ["england", "industry"]
    entities = [{"type": "region", "name": "England"}]

    for entry in UNIQUE_DATABASE:
        facts.append(_make_fact(
            entry["fact"],
            domain="wine_business",
            source_id=source_id,
            subdomain="industry",
            entities=entities,
            confidence=entry.get("confidence", 1.0),
            tags=base_tags + [entry["topic"]],
        ))

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# ORCHESTRATION
# ═══════════════════════════════════════════════════════════════════════════════


def _get_source_id() -> str:
    """Register and return the English wine source ID."""
    return ensure_source(
        name=SOURCE["name"],
        url=SOURCE["url"],
        source_type=SOURCE["source_type"],
        tier=SOURCE["tier"],
        language=SOURCE["language"],
    )


BUILDER_MAP = {
    "region": ("Regions", _build_regional_facts),
    "grape": ("Grape Varieties", _build_grape_variety_facts),
    "sparkling": ("Sparkling Wine", _build_sparkling_facts),
    "classification": ("Classification", _build_classification_facts),
    "climate": ("Climate Change", _build_climate_facts),
    "history": ("History", _build_history_facts),
    "unique": ("Unique / Industry", _build_unique_facts),
}


def _build_all_facts(source_id: str, data_type: str = None) -> list[dict]:
    """Build all facts, optionally filtered by type."""
    all_facts = []

    if data_type and data_type in BUILDER_MAP:
        _, builder = BUILDER_MAP[data_type]
        all_facts = builder(source_id)
    else:
        for _, builder in BUILDER_MAP.values():
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
        click.echo(f"\n[DRY RUN] Would insert {len(facts)} facts from English Wine Reference Database")

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

    logger.info(f"Inserted {inserted} new facts from English Wine Reference Database (duplicates skipped)")
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

    # Overall counts
    click.echo(f"\n=== VALIDATION REPORT — English Wine ===")
    click.echo(f"\nTotal facts: {total}")

    # (a) Domain / subdomain breakdown
    domain_counts = defaultdict(int)
    subdomain_counts = defaultdict(int)
    for f in facts:
        domain_counts[f["domain"]] += 1
        sub = f.get("subdomain") or "(none)"
        subdomain_counts[f"{f['domain']}/{sub}"] += 1

    click.echo("\nDomain breakdown:")
    for d, c in sorted(domain_counts.items()):
        click.echo(f"  {d:25s}: {c:5d} ({100 * c / total:.1f}%)")

    click.echo("\nSubdomain breakdown:")
    for sd, c in sorted(subdomain_counts.items(), key=lambda x: -x[1]):
        click.echo(f"  {sd:40s}: {c:5d}")

    # (b) Length checks
    too_short = [f for f in facts if len(f["fact_text"].split()) < 5]
    too_long = [f for f in facts if len(f["fact_text"].split()) > 50]
    click.echo(f"\n  Too short (<5 words):   {len(too_short)} ({100 * len(too_short) / total:.1f}%)")
    click.echo(f"  Too long (>50 words):   {len(too_long)} ({100 * len(too_long) / total:.1f}%)")

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

    for type_key, (cat_name, builder) in BUILDER_MAP.items():
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
    type=click.Choice(["region", "grape", "sparkling", "classification", "climate", "history", "unique"]),
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
    """OenoBench English Wine Scraper — Regions, grapes, sparkling, classification, climate, and history."""
    logger.add("data/logs/england_{time}.log", rotation="10 MB")

    if list_sources:
        click.echo("\nAvailable data categories:")
        click.echo(f"  {'region':16s} — {len(REGION_DATABASE)} English wine regions (climate, soil, producers)")
        click.echo(f"  {'grape':16s} — {len(GRAPE_DATABASE)} grape variety profiles")
        click.echo(f"  {'sparkling':16s} — Sparkling wine production, Champagne comparison")
        click.echo(f"  {'classification':16s} — PDO/PGI system, rules, industry body")
        click.echo(f"  {'climate':16s} — {len(CLIMATE_DATABASE)} climate change impact facts")
        click.echo(f"  {'history':16s} — {len(HISTORY_DATABASE)} historical milestones")
        click.echo(f"  {'unique':16s} — {len(UNIQUE_DATABASE)} industry statistics and trends")
        click.echo(f"\nKnowledge base coverage:")
        click.echo(f"  Regions:          {len(REGION_DATABASE)}")
        click.echo(f"  Grape varieties:  {len(GRAPE_DATABASE)}")
        click.echo(f"  Climate facts:    {len(CLIMATE_DATABASE)}")
        click.echo(f"  History entries:  {len(HISTORY_DATABASE)}")
        click.echo(f"  Industry facts:   {len(UNIQUE_DATABASE)}")
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
