"""
OenoBench — Lebanon & Israel Wine Scraper

Extracts structured wine data for Lebanon and Israel — two of the Eastern
Mediterranean's most important and historically significant wine-producing
countries.  Covers regions, grape varieties, producers, kosher winemaking,
classification systems, and deep historical context.

Usage:
    python -m src.scrapers.lebanon_israel --all
    python -m src.scrapers.lebanon_israel --type lebanon
    python -m src.scrapers.lebanon_israel --type israel
    python -m src.scrapers.lebanon_israel --type grape
    python -m src.scrapers.lebanon_israel --type kosher
    python -m src.scrapers.lebanon_israel --type classification
    python -m src.scrapers.lebanon_israel --dry-run
    python -m src.scrapers.lebanon_israel --validate
    python -m src.scrapers.lebanon_israel --test-run
    python -m src.scrapers.lebanon_israel --list
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
    "name": "Lebanon & Israel Wine Reference Database",
    "url": "https://www.chateaumusar.com",
    "source_type": "reference",
    "tier": "tier_2_authoritative",
    "language": "en",
}


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Lebanon Regions
# ═══════════════════════════════════════════════════════════════════════════════

LEBANON_REGIONS = [
    {
        "name": "Bekaa Valley",
        "country": "Lebanon",
        "elevation_range": "900-1,100m",
        "climate": "continental",
        "climate_details": "Hot dry summers and cold winters, situated between Mount Lebanon and Anti-Lebanon mountain ranges, creating a rain-shadow effect with minimal summer precipitation",
        "soil_types": ["limestone", "clay", "gravel"],
        "soil_details": "Well-drained limestone and clay soils with gravel deposits, particularly suited to red Bordeaux and Rhône varieties",
        "vineyard_area_ha": 2000,
        "num_wineries": 30,
        "sub_zones": ["Central Bekaa (Ksara area)", "West Bekaa (Kefraya area)", "Northern Bekaa (Baalbek, ancient Heliopolis)"],
    },
    {
        "name": "Mount Lebanon",
        "country": "Lebanon",
        "elevation_range": "up to 1,800m",
        "climate": "cool mountain",
        "climate_details": "High-altitude mountain vineyards with cooler temperatures than the Bekaa Valley, significant diurnal temperature variation, and higher rainfall from Mediterranean moisture",
        "soil_types": ["volcanic", "limestone"],
        "soil_details": "Volcanic and limestone soils on steep mountain slopes with excellent natural drainage",
        "vineyard_area_ha": 300,
    },
    {
        "name": "Batroun",
        "country": "Lebanon",
        "elevation_range": "0-1,200m",
        "climate": "coastal Mediterranean transitioning to mountain",
        "climate_details": "Coastal and mountain vineyards ranging from sea level to high altitude, benefiting from both Mediterranean breezes and cool mountain air",
        "soil_types": ["limestone"],
        "soil_details": "Limestone soils in the ancient Phoenician heartland of North Lebanon, where wine grapes have been cultivated for millennia",
        "vineyard_area_ha": 200,
    },
    {
        "name": "South Lebanon",
        "country": "Lebanon",
        "elevation_range": "200-800m",
        "climate": "warm Mediterranean",
        "climate_details": "Warm Mediterranean climate in the Nabatieh area, an emerging wine region with potential for heat-loving varieties",
        "soil_types": ["limestone", "clay"],
        "soil_details": "Limestone and clay soils on hillside vineyards in the emerging southern wine districts",
        "vineyard_area_ha": 100,
    },
    {
        "name": "Chouf Mountains",
        "country": "Lebanon",
        "elevation_range": "800-1,500m",
        "climate": "high-altitude mountain",
        "climate_details": "High-altitude vineyards in the Druze heartland of the Chouf district, with cool temperatures and significant diurnal variation",
        "soil_types": ["limestone", "clay"],
        "soil_details": "Limestone and clay soils on mountain terraces in an emerging wine district",
        "vineyard_area_ha": 100,
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Israel Regions
# ═══════════════════════════════════════════════════════════════════════════════

ISRAEL_REGIONS = [
    {
        "name": "Galilee",
        "alt_name": "Galil",
        "country": "Israel",
        "elevation_range": "400-1,200m",
        "climate": "Mediterranean with continental influence",
        "climate_details": "Israel's premium wine region comprising Upper Galilee (mountains, 500-800m, volcanic basalt and terra rossa, cool climate) and Golan Heights (volcanic plateau, 400-1,200m, basalt over chalk, cold winters, Israel's highest vineyards)",
        "soil_types": ["volcanic basalt", "terra rossa", "chalk"],
        "soil_details": "Upper Galilee features volcanic basalt and terra rossa soils on mountain slopes; the Golan Heights has basalt over chalk from ancient volcanic activity, creating mineral-rich vineyard soils",
        "vineyard_area_ha": 3000,
        "sub_zones": ["Upper Galilee", "Lower Galilee", "Golan Heights"],
    },
    {
        "name": "Judean Hills",
        "alt_name": "Harei Yehuda",
        "country": "Israel",
        "elevation_range": "600-900m",
        "climate": "Mediterranean with continental influence",
        "climate_details": "Vineyards around Jerusalem at 600-900m elevation with limestone and terra rossa soils, experiencing Mediterranean winters and dry summers with significant diurnal temperature variation",
        "soil_types": ["limestone", "terra rossa"],
        "soil_details": "Limestone and terra rossa soils on hillsides around Jerusalem, with notable old-vine Carignan sites experiencing a quality revival",
        "vineyard_area_ha": 1500,
        "sub_zones": ["Judean Hills", "Judean Foothills (Adulam, Ayalon Valley)"],
    },
    {
        "name": "Shomron",
        "alt_name": "Samaria",
        "country": "Israel",
        "elevation_range": "100-500m",
        "climate": "warm Mediterranean",
        "climate_details": "Central coastal hills with warm Mediterranean climate, traditionally planted to Cabernet Sauvignon and Merlot",
        "soil_types": ["limestone", "clay", "sand"],
        "soil_details": "Varied soils on central coastal hills ranging from limestone to clay and sandy deposits",
        "vineyard_area_ha": 2000,
    },
    {
        "name": "Negev",
        "country": "Israel",
        "elevation_range": "200-800m",
        "climate": "desert",
        "climate_details": "Desert viticulture requiring irrigation, with extreme daytime heat and cool nights at elevation; Ramat Arad is the principal sub-zone",
        "soil_types": ["loess", "sand", "limestone"],
        "soil_details": "Desert soils including loess and sandy deposits over limestone bedrock; ancient Nabataean wine routes once traversed this region",
        "vineyard_area_ha": 500,
    },
    {
        "name": "Coastal Plain",
        "alt_name": "Sharon/Shimshon",
        "country": "Israel",
        "elevation_range": "0-100m",
        "climate": "warm Mediterranean",
        "climate_details": "Warm coastal plain with sandy and alluvial soils, historically the center of large-scale Israeli wine production",
        "soil_types": ["sandy", "alluvial"],
        "soil_details": "Sandy and alluvial soils on the warm coastal plain, traditionally used for large-scale production",
        "vineyard_area_ha": 3000,
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Grape Varieties
# ═══════════════════════════════════════════════════════════════════════════════

LEBANON_GRAPES = [
    {
        "name": "Cinsault",
        "color": "red",
        "country": "Lebanon",
        "area_ha": 2000,
        "details": "Lebanon's most planted red grape variety with old vines dating from the French Mandate era, producing fresh rosés and blending components for Château Musar's iconic red",
        "heritage": "French heritage, widely planted during the French Mandate period (1920-1943)",
    },
    {
        "name": "Cabernet Sauvignon",
        "color": "red",
        "country": "Lebanon",
        "area_ha": 800,
        "details": "Widely planted in Lebanon since the 1850s when Jesuit monks established Château Ksara, performing well in the continental climate of the Bekaa Valley",
        "heritage": "First planted in Lebanon at Château Ksara around 1857 by Jesuit monks",
    },
    {
        "name": "Carignan",
        "color": "red",
        "country": "Lebanon",
        "details": "Old-vine Carignan in Lebanon produces deeply colored wines with southern French heritage, used as a blending component in traditional Lebanese reds including Château Musar",
        "heritage": "Southern French heritage variety with old vines in the Bekaa Valley",
    },
    {
        "name": "Syrah",
        "color": "red",
        "country": "Lebanon",
        "area_ha": 500,
        "details": "Increasingly important variety in Lebanese winemaking, well-suited to the hot dry climate of the Bekaa Valley and producing rich, spicy reds",
    },
    {
        "name": "Grenache",
        "color": "red",
        "country": "Lebanon",
        "area_ha": 300,
        "details": "Blending variety in Lebanon contributing fruitiness and body to red blends, performing well in the warm Bekaa Valley climate",
    },
    {
        "name": "Mourvèdre",
        "color": "red",
        "country": "Lebanon",
        "details": "Small but growing plantings in Lebanon, used in Rhône-style blends and contributing structure and dark fruit character",
    },
    {
        "name": "Obaideh",
        "color": "white",
        "country": "Lebanon",
        "area_ha": 200,
        "details": "Indigenous Lebanese white grape variety said to be an ancestor or close relative of Chardonnay, grown primarily in the Bekaa Valley and producing rich, full-bodied whites",
        "indigenous": True,
    },
    {
        "name": "Merwah",
        "color": "white",
        "country": "Lebanon",
        "area_ha": 150,
        "details": "Indigenous Lebanese white grape variety with high natural acidity, used both as a blending component and for varietal wines, producing crisp mineral whites",
        "indigenous": True,
    },
    {
        "name": "Muscat",
        "color": "white",
        "country": "Lebanon",
        "details": "Used for traditional sweet wines in Lebanon, particularly associated with the Ksara winery tradition",
    },
    {
        "name": "Viognier",
        "color": "white",
        "country": "Lebanon",
        "details": "Recent plantings in Lebanon following international trends, producing aromatic whites suited to the warm climate when planted at higher elevations",
    },
]

ISRAEL_GRAPES = [
    {
        "name": "Cabernet Sauvignon",
        "color": "red",
        "country": "Israel",
        "area_ha": 3000,
        "details": "Israel's most planted quality red grape variety, performing best in the Galilee and Judean Hills regions where elevation provides cooler nighttime temperatures",
    },
    {
        "name": "Carignan",
        "color": "red",
        "country": "Israel",
        "details": "Experiencing a dramatic quality revival from old bush vines in the Judean Hills, some 60-100 years old, previously used only for bulk wine but now producing premium single-vineyard bottlings",
        "old_vines": True,
    },
    {
        "name": "Syrah",
        "color": "red",
        "country": "Israel",
        "area_ha": 1000,
        "details": "Thriving on the Golan Heights and in Galilee, producing rich and spicy reds that benefit from volcanic basalt soils and cool-climate elevation",
    },
    {
        "name": "Merlot",
        "color": "red",
        "country": "Israel",
        "area_ha": 1500,
        "details": "Widely planted across Israel, one of the most common red varieties used both for varietal wines and Bordeaux-style blends",
    },
    {
        "name": "Petite Sirah",
        "color": "red",
        "country": "Israel",
        "area_ha": 400,
        "details": "Surprisingly successful in Israel, producing intensely colored, full-bodied wines with firm tannins, particularly in warmer regions",
    },
    {
        "name": "Argaman",
        "color": "red",
        "country": "Israel",
        "area_ha": 300,
        "details": "Israeli grape crossing of Carignan and Souzão created in 1972, producing deeply colored wines used both for varietal bottlings and as a blending component for color enhancement",
        "crossing": "Carignan × Souzão",
        "year_created": 1972,
    },
    {
        "name": "Colombard",
        "color": "white",
        "country": "Israel",
        "area_ha": 2000,
        "details": "Israel's most planted white grape variety, used primarily for everyday drinking wines and providing crisp acidity in warm-climate white blends",
    },
    {
        "name": "Sauvignon Blanc",
        "color": "white",
        "country": "Israel",
        "area_ha": 500,
        "details": "Growing in popularity in the Galilee region where cooler temperatures preserve aromatic intensity and natural acidity",
    },
    {
        "name": "Chardonnay",
        "color": "white",
        "country": "Israel",
        "area_ha": 500,
        "details": "Performing well on the Golan Heights where the high-altitude volcanic plateau provides cool enough conditions for balanced, elegant whites",
    },
    {
        "name": "Gewürztraminer",
        "color": "white",
        "country": "Israel",
        "details": "Small but notable plantings on the Golan Heights, producing aromatic whites with the variety's characteristic lychee and rose petal notes",
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Lebanon Producers
# ═══════════════════════════════════════════════════════════════════════════════

LEBANON_PRODUCERS = [
    {
        "name": "Château Musar",
        "founded": 1930,
        "founder": "Gaston Hochar",
        "location": "Ghazir (winery), Bekaa Valley (vineyards)",
        "area_ha": None,
        "signature_blend": "Cinsault, Cabernet Sauvignon, and Carignan",
        "facts": [
            "Château Musar was founded in 1930 by Gaston Hochar in Ghazir, Lebanon.",
            "Serge Hochar, son of founder Gaston Hochar, made Château Musar world-famous after presenting at the 1979 Bristol Wine Fair.",
            "Château Musar never missed a single vintage during the entire Lebanese Civil War (1975-1990), despite winemaking under bombardment and transporting grapes across front lines.",
            "Château Musar's iconic red blend is made from Cinsault, Cabernet Sauvignon, and Carignan sourced from old vines in the Bekaa Valley.",
            "Château Musar has been called 'the Petrus of Lebanon' for its extraordinary aging potential and cult following among collectors.",
            "Château Musar produces a white wine from the indigenous Lebanese grape varieties Obaideh and Merwah.",
            "Château Musar's vineyards in the Bekaa Valley sit at approximately 1,000m elevation on gravelly limestone soils.",
        ],
    },
    {
        "name": "Château Ksara",
        "founded": 1857,
        "founder": "Jesuit monks",
        "location": "Bekaa Valley",
        "area_ha": 400,
        "facts": [
            "Château Ksara, established in 1857 by Jesuit monks, is the oldest winery in Lebanon.",
            "Château Ksara's underground Roman caves, discovered in 1898, extend for nearly 2 kilometers and provide natural temperature-controlled storage.",
            "Château Ksara manages approximately 400 hectares of vineyards in the Bekaa Valley, making it Lebanon's largest winery by vineyard area.",
            "The Jesuit monks of Château Ksara introduced French grape varieties including Cabernet Sauvignon to Lebanon in the mid-19th century.",
        ],
    },
    {
        "name": "Château Kefraya",
        "founded": 1946,
        "location": "West Bekaa Valley",
        "area_ha": 300,
        "facts": [
            "Château Kefraya was established in 1946 in the West Bekaa Valley and manages 300 hectares of vineyards.",
            "Château Kefraya's flagship wine is Comte de M, a premium Bordeaux-style red blend.",
        ],
    },
    {
        "name": "Domaine des Tourelles",
        "founded": 1868,
        "location": "Bekaa Valley",
        "facts": [
            "Domaine des Tourelles was founded in 1868 and is one of Lebanon's oldest continuously operating wineries.",
            "Domaine des Tourelles produces both wine and artisanal arak, the traditional Lebanese anise-flavored spirit.",
        ],
    },
    {
        "name": "Ixsir",
        "founded": 2008,
        "location": "Batroun, with vineyards in Jezzine and Batroun",
        "facts": [
            "Ixsir was founded in 2008 as a modern Lebanese winery with vineyards at elevations up to 1,800m, among the highest in Lebanon.",
            "Ixsir sources grapes from high-altitude vineyards in both Jezzine and Batroun, blending coastal and mountain terroir.",
        ],
    },
    {
        "name": "Massaya",
        "founded": None,
        "location": "Bekaa Valley",
        "facts": [
            "Massaya is a Bekaa Valley winery established through a partnership with renowned Rhône Valley winemaking families Brunier (Vieux Télégraphe) and Chave (Hermitage).",
            "Massaya's collaboration with Rhône winemakers reflects the strong affinity between Bekaa Valley terroir and Rhône grape varieties.",
        ],
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Israel Notable Estates
# ═══════════════════════════════════════════════════════════════════════════════

ISRAEL_PRODUCERS = [
    {
        "name": "Carmel Winery",
        "founded": 1882,
        "founder": "Baron Edmond de Rothschild",
        "location": "Rishon LeZion and Zichron Ya'akov",
        "facts": [
            "Carmel Winery was established in 1882 by Baron Edmond de Rothschild, making it the oldest continuously operating winery in Israel.",
            "Baron Edmond de Rothschild founded Carmel Winery at two locations: Rishon LeZion near Tel Aviv and Zichron Ya'akov on Mount Carmel.",
            "Carmel Winery's establishment by Rothschild marked the beginning of modern commercial winemaking in Israel.",
        ],
    },
    {
        "name": "Golan Heights Winery",
        "founded": 1983,
        "location": "Katzrin, Golan Heights",
        "facts": [
            "Golan Heights Winery was founded in 1983 in Katzrin on the Golan Heights plateau, triggering Israel's quality wine revolution.",
            "Golan Heights Winery produces wine under three labels: Yarden (premium), Gamla (mid-range), and Golan (entry-level).",
            "Golan Heights Winery's vineyards on the volcanic plateau range from 400m to 1,200m elevation, among the highest in Israel.",
            "The founding of Golan Heights Winery in 1983 is widely considered the starting point of Israel's modern quality wine era.",
        ],
    },
    {
        "name": "Domaine du Castel",
        "location": "Judean Hills",
        "facts": [
            "Domaine du Castel is a boutique Judean Hills estate widely regarded as one of Israel's finest producers of Bordeaux-style blends.",
        ],
    },
    {
        "name": "Clos de Gat",
        "location": "Judean Hills (Ayalon Valley)",
        "facts": [
            "Clos de Gat is a boutique winery in the Ayalon Valley of the Judean Foothills, known for elegant Chardonnay and Bordeaux-style reds.",
        ],
    },
    {
        "name": "Flam Winery",
        "location": "Judean Foothills",
        "facts": [
            "Flam Winery in the Judean Foothills is run by brothers Golan and Gilad Flam, producing critically acclaimed Bordeaux-style blends.",
        ],
    },
    {
        "name": "Margalit Winery",
        "location": "Coastal Plain (originally), various vineyard sources",
        "facts": [
            "Margalit Winery is a pioneering Israeli boutique estate founded by Professor Yair Margalit, an enologist who helped define Israel's garagiste winemaking movement.",
        ],
    },
    {
        "name": "Yatir Winery",
        "location": "Northern Negev (Yatir Forest)",
        "facts": [
            "Yatir Winery, located at the edge of the Negev desert near the Yatir Forest, demonstrates that high-quality wines can be produced in Israel's arid southern frontier.",
        ],
    },
    {
        "name": "Pelter Winery",
        "location": "Golan Heights",
        "facts": [
            "Pelter Winery on the Golan Heights is known for innovative winemaking and was among the early boutique producers to focus on cool-climate Golan sites.",
        ],
    },
    {
        "name": "Recanati Winery",
        "location": "Upper Galilee",
        "facts": [
            "Recanati Winery in the Upper Galilee is noted for its old-vine Carignan program and Mediterranean-style blends under consultant Ido Lewinsohn.",
        ],
    },
    {
        "name": "Dalton Winery",
        "location": "Upper Galilee",
        "facts": [
            "Dalton Winery is an Upper Galilee estate known for its diverse range of varieties sourced from high-altitude vineyards in northern Israel.",
        ],
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Lebanon History
# ═══════════════════════════════════════════════════════════════════════════════

LEBANON_HISTORY_FACTS = [
    "The Phoenicians, based in what is now Lebanon, were among the first civilizations to spread viticulture across the Mediterranean beginning around 3000 BC.",
    "Lebanon has over 5,000 years of documented wine history, making it one of the oldest wine-producing regions in the world.",
    "The Temple of Bacchus at Baalbek in Lebanon's Bekaa Valley, built in the 2nd century AD, is the largest Roman temple ever dedicated to the god of wine.",
    "During the Islamic period in Lebanon, wine production continued in Christian monastic communities, preserving viticultural knowledge through centuries of Muslim rule.",
    "The French Mandate period (1920-1943) modernized Lebanese viticulture, with Jesuit monks playing a central role in introducing French grape varieties and winemaking techniques.",
    "Lebanon's wine industry experienced a remarkable renaissance from just 5 wineries in 1998 to over 50 wineries by 2025.",
    "During the Lebanese Civil War (1975-1990), several wineries continued production despite conflict, with Château Musar becoming an international symbol of perseverance.",
    "Lebanon's total vineyard area is estimated at approximately 2,700 hectares, small by global standards but culturally and historically significant.",
    "The Bekaa Valley has been cultivated for wine since Phoenician times and remains the heart of Lebanese viticulture today.",
    "Modern Lebanese winemaking draws heavily on French winemaking traditions, reflecting the deep cultural influence of the French Mandate and Jesuit missionary activity.",
]


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Israel History
# ═══════════════════════════════════════════════════════════════════════════════

ISRAEL_HISTORY_FACTS = [
    "The Bible contains numerous references to winemaking in ancient Israel, including Noah planting a vineyard after the Flood (Genesis 9:20) and the scouts of Canaan carrying enormous grape clusters back to Moses (Numbers 13:23).",
    "Ancient Israel was a major wine producer and exporter during the Bronze and Iron Ages, with archaeological evidence of large-scale wine production facilities throughout the region.",
    "Roman-period mosaics found across Israel depict vineyard scenes and wine production, attesting to the importance of viticulture in the ancient economy.",
    "Wine production in the land of Israel largely ceased during Ottoman rule (16th-20th century), as Islamic governance discouraged alcohol production.",
    "Baron Edmond de Rothschild established Carmel Winery in 1882 at Rishon LeZion and Zichron Ya'akov, founding the modern Israeli wine industry.",
    "The founding of Golan Heights Winery in 1983 is widely considered the beginning of Israel's quality wine revolution, proving that world-class wine could be produced in the country.",
    "Israel's boutique winery revolution saw the number of wineries grow from approximately 5 in the early 1990s to over 300 by 2025.",
    "The Negev desert's ancient Nabataean wine routes demonstrate that viticulture in Israel's arid south has precedent dating back over 2,000 years.",
    "Israel's total vineyard area is estimated at approximately 10,000 hectares, with the majority of premium production concentrated in Galilee and the Judean Hills.",
    "Israeli winemakers increasingly focus on Mediterranean varieties such as Carignan, Grenache, and Mourvèdre alongside traditional Bordeaux varieties, reflecting the region's warm climate.",
]


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Kosher Winemaking
# ═══════════════════════════════════════════════════════════════════════════════

KOSHER_FACTS = [
    "Kosher wine production requires supervision by a mashgiach (rabbinical supervisor) from the moment of grape crush through to bottling.",
    "In kosher winemaking, only Sabbath-observant Jews may handle the wine during production, from crushing through bottling and pouring.",
    "Mevushal wine is flash-pasteurized to approximately 85°C, allowing it to be served by anyone regardless of religious observance, making it the standard for restaurant and catering use.",
    "Non-Mevushal kosher wine is considered premium quality as it avoids heat treatment, but must be handled exclusively by Sabbath-observant Jews from production through service.",
    "All winemaking equipment used for kosher wine production must itself be kosher, and animal-derived fining agents such as isinglass are forbidden; egg whites may sometimes be used as an alternative.",
    "The Shemitah year, occurring every 7th year in the Jewish calendar, imposes special biblical rules for vineyard management including letting the land lie fallow.",
    "Yayin Nesech refers to the ancient Jewish prohibition against wine used in or potentially associated with idol worship, which is the historical origin of kosher wine laws.",
    "The global perception of kosher wine has undergone a quality revolution; kosher wine no longer means sweet Concord grape wines, with world-class dry wines now the standard from Israel and beyond.",
    "Kosher winemaking does not inherently affect wine quality — the restrictions relate to who handles the wine and equipment purity, not to viticultural or winemaking techniques.",
    "Many of Israel's top-rated wines are kosher, demonstrating that kosher certification and world-class quality are fully compatible.",
    "The mevushal flash-pasteurization process, while allowing more flexible handling, can reduce aromatic complexity, which is why premium kosher wines are typically non-mevushal.",
    "Kosher wine production has grown into a global industry, with kosher wines produced in France, Italy, Spain, Argentina, Chile, the United States, and South Africa in addition to Israel.",
]


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Classification Systems
# ═══════════════════════════════════════════════════════════════════════════════

CLASSIFICATION_FACTS = [
    "Lebanon has no formal wine appellation system; the Bekaa Valley serves as a de facto geographic designation on most Lebanese wine labels.",
    "The Investment Development Authority of Lebanon (IDAL) actively promotes the Lebanese wine industry in international markets.",
    "The Institut de la Vigne et du Vin du Liban is an emerging body working to establish quality standards and geographic designations for Lebanese wine.",
    "Israeli wine uses geographic indications on labels but these are not legally binding designations in the manner of European appellations.",
    "Israel's wine regions (Galilee, Judean Hills, Shomron, Negev, Coastal Plain) function as informal geographic designations without legal appellation status.",
    "A Quality Wine label exists in Israel but the country lacks a formal, legally enforced appellation system comparable to France's AOC or Italy's DOC/DOCG.",
    "The Israel Wine Board promotes Israeli wine exports and quality standards internationally.",
    "Both Lebanon and Israel rely primarily on producer reputation and brand recognition rather than formal appellations to communicate wine quality and origin.",
    "The absence of formal appellations in both Lebanon and Israel gives winemakers greater flexibility in blending across regions and experimenting with grape varieties.",
    "Lebanon's wine classification discussions are influenced by French models, reflecting the historical cultural ties between the two countries.",
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
# FACT BUILDERS — Lebanon
# ═══════════════════════════════════════════════════════════════════════════════


def _build_lebanon_facts(source_id: str) -> list[dict]:
    """Build facts about Lebanese wine regions, producers, and history."""
    facts = []

    # ── Region facts ──
    for region in LEBANON_REGIONS:
        name = region["name"]
        entities = [{"type": "region", "name": name}, {"type": "country", "name": "Lebanon"}]
        base_tags = ["lebanon", name.lower().replace(" ", "_")]

        # Climate
        facts.append(_make_fact(
            f"The {name} wine region in Lebanon has a {region['climate']} climate.",
            domain="wine_regions",
            source_id=source_id,
            subdomain="lebanon",
            entities=entities,
            tags=base_tags + ["climate"],
        ))

        if region.get("climate_details"):
            facts.append(_make_fact(
                f"{region['climate_details']}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="lebanon",
                entities=entities,
                tags=base_tags + ["climate"],
            ))

        # Soil
        if region.get("soil_types"):
            soil_list = ", ".join(region["soil_types"])
            facts.append(_make_fact(
                f"The predominant soil types in Lebanon's {name} wine region include {soil_list}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="lebanon",
                entities=entities,
                tags=base_tags + ["soil", "terroir"],
            ))

        if region.get("soil_details"):
            facts.append(_make_fact(
                f"{region['soil_details']}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="lebanon",
                entities=entities,
                tags=base_tags + ["soil", "terroir"],
            ))

        # Elevation
        if region.get("elevation_range"):
            facts.append(_make_fact(
                f"Vineyards in Lebanon's {name} region are planted at elevations of {region['elevation_range']}.",
                domain="viticulture",
                source_id=source_id,
                subdomain="terrain",
                entities=entities,
                tags=base_tags + ["elevation"],
            ))

        # Vineyard area
        if region.get("vineyard_area_ha"):
            facts.append(_make_fact(
                f"Lebanon's {name} wine region has approximately {region['vineyard_area_ha']:,} hectares under vine.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="lebanon",
                entities=entities,
                confidence=0.9,
                tags=base_tags + ["statistics"],
            ))

        # Sub-zones
        if region.get("sub_zones"):
            zones_str = ", ".join(region["sub_zones"])
            facts.append(_make_fact(
                f"The {name} wine region in Lebanon includes the sub-zones: {zones_str}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="lebanon",
                entities=entities,
                tags=base_tags + ["sub_zones"],
            ))

        # Number of wineries
        if region.get("num_wineries"):
            facts.append(_make_fact(
                f"Lebanon's {name} region is home to more than {region['num_wineries']} wineries.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="lebanon",
                entities=entities,
                confidence=0.9,
                tags=base_tags + ["statistics"],
            ))

    # ── Producer facts ──
    for producer in LEBANON_PRODUCERS:
        p_name = producer["name"]
        p_entities = [{"type": "producer", "name": p_name}, {"type": "country", "name": "Lebanon"}]
        p_tags = ["lebanon", "producer", p_name.lower().replace(" ", "_").replace("é", "e").replace("â", "a")]

        for fact_text in producer["facts"]:
            facts.append(_make_fact(
                fact_text,
                domain="producers",
                source_id=source_id,
                subdomain="lebanon",
                entities=p_entities,
                tags=p_tags,
            ))

        # Founded fact
        if producer.get("founded") and producer.get("founder"):
            # Skip if already covered in explicit facts
            pass
        elif producer.get("area_ha"):
            facts.append(_make_fact(
                f"{p_name} manages approximately {producer['area_ha']} hectares of vineyards.",
                domain="producers",
                source_id=source_id,
                subdomain="lebanon",
                entities=p_entities,
                confidence=0.9,
                tags=p_tags + ["statistics"],
            ))

    # ── History facts ──
    for fact_text in LEBANON_HISTORY_FACTS:
        facts.append(_make_fact(
            fact_text,
            domain="wine_regions",
            source_id=source_id,
            subdomain="lebanon_history",
            entities=[{"type": "country", "name": "Lebanon"}],
            tags=["lebanon", "history"],
        ))

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# FACT BUILDERS — Israel
# ═══════════════════════════════════════════════════════════════════════════════


def _build_israel_facts(source_id: str) -> list[dict]:
    """Build facts about Israeli wine regions, producers, and history."""
    facts = []

    # ── Region facts ──
    for region in ISRAEL_REGIONS:
        name = region["name"]
        alt = region.get("alt_name", "")
        display_name = f"{name} ({alt})" if alt else name
        entities = [{"type": "region", "name": name}, {"type": "country", "name": "Israel"}]
        base_tags = ["israel", name.lower().replace(" ", "_")]

        # Climate
        facts.append(_make_fact(
            f"The {display_name} wine region in Israel has a {region['climate']} climate.",
            domain="wine_regions",
            source_id=source_id,
            subdomain="israel",
            entities=entities,
            tags=base_tags + ["climate"],
        ))

        if region.get("climate_details"):
            facts.append(_make_fact(
                f"{region['climate_details']}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="israel",
                entities=entities,
                tags=base_tags + ["climate"],
            ))

        # Soil
        if region.get("soil_types"):
            soil_list = ", ".join(region["soil_types"])
            facts.append(_make_fact(
                f"The predominant soil types in Israel's {name} wine region include {soil_list}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="israel",
                entities=entities,
                tags=base_tags + ["soil", "terroir"],
            ))

        if region.get("soil_details"):
            facts.append(_make_fact(
                f"{region['soil_details']}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="israel",
                entities=entities,
                tags=base_tags + ["soil", "terroir"],
            ))

        # Elevation
        if region.get("elevation_range"):
            facts.append(_make_fact(
                f"Vineyards in Israel's {name} region are planted at elevations of {region['elevation_range']}.",
                domain="viticulture",
                source_id=source_id,
                subdomain="terrain",
                entities=entities,
                tags=base_tags + ["elevation"],
            ))

        # Vineyard area
        if region.get("vineyard_area_ha"):
            facts.append(_make_fact(
                f"Israel's {name} wine region has approximately {region['vineyard_area_ha']:,} hectares under vine.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="israel",
                entities=entities,
                confidence=0.9,
                tags=base_tags + ["statistics"],
            ))

        # Sub-zones
        if region.get("sub_zones"):
            zones_str = ", ".join(region["sub_zones"])
            facts.append(_make_fact(
                f"The {name} wine region in Israel includes the sub-zones: {zones_str}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="israel",
                entities=entities,
                tags=base_tags + ["sub_zones"],
            ))

    # ── Producer facts ──
    for producer in ISRAEL_PRODUCERS:
        p_name = producer["name"]
        p_entities = [{"type": "producer", "name": p_name}, {"type": "country", "name": "Israel"}]
        p_tags = ["israel", "producer", p_name.lower().replace(" ", "_").replace("'", "")]

        for fact_text in producer["facts"]:
            facts.append(_make_fact(
                fact_text,
                domain="producers",
                source_id=source_id,
                subdomain="israel",
                entities=p_entities,
                tags=p_tags,
            ))

    # ── History facts ──
    for fact_text in ISRAEL_HISTORY_FACTS:
        facts.append(_make_fact(
            fact_text,
            domain="wine_regions",
            source_id=source_id,
            subdomain="israel_history",
            entities=[{"type": "country", "name": "Israel"}],
            tags=["israel", "history"],
        ))

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# FACT BUILDERS — Grape Varieties (both countries)
# ═══════════════════════════════════════════════════════════════════════════════


def _build_grape_variety_facts(source_id: str) -> list[dict]:
    """Build facts about grape varieties grown in Lebanon and Israel."""
    facts = []

    all_grapes = LEBANON_GRAPES + ISRAEL_GRAPES

    for grape in all_grapes:
        name = grape["name"]
        color = grape["color"]
        country = grape["country"]
        country_lower = country.lower()
        entities = [{"type": "grape", "name": name}, {"type": "country", "name": country}]
        base_tags = [country_lower, "grape", name.lower().replace(" ", "_")]

        # Main description
        if grape.get("details"):
            facts.append(_make_fact(
                grape["details"] + ("" if grape["details"].endswith(".") else "."),
                domain="grape_varieties",
                source_id=source_id,
                subdomain=f"{country_lower}_grapes",
                entities=entities,
                tags=base_tags,
            ))

        # Area planted
        if grape.get("area_ha"):
            facts.append(_make_fact(
                f"{name} is planted on approximately {grape['area_ha']:,} hectares in {country}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain=f"{country_lower}_grapes",
                entities=entities,
                confidence=0.9,
                tags=base_tags + ["statistics"],
            ))

        # Heritage / origin
        if grape.get("heritage"):
            facts.append(_make_fact(
                f"{grape['heritage']}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain=f"{country_lower}_grapes",
                entities=entities,
                tags=base_tags + ["history"],
            ))

        # Indigenous varieties
        if grape.get("indigenous"):
            facts.append(_make_fact(
                f"{name} is an indigenous {country_lower.replace('lebanon', 'Lebanese').replace('israel', 'Israeli')} grape variety.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain=f"{country_lower}_grapes",
                entities=entities,
                tags=base_tags + ["indigenous"],
            ))

        # Crossing details
        if grape.get("crossing"):
            facts.append(_make_fact(
                f"Argaman is an Israeli grape crossing of {grape['crossing']}, created in {grape.get('year_created', 'the 1970s')}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="israel_grapes",
                entities=entities,
                tags=base_tags + ["crossing"],
            ))

        # Old vines
        if grape.get("old_vines"):
            facts.append(_make_fact(
                f"Old bush vines of {name} in the Judean Hills, some 60 to 100 years old, have driven a premium quality revival for a variety previously used only for bulk wine in Israel.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="israel_grapes",
                entities=entities,
                tags=base_tags + ["old_vines"],
            ))

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# FACT BUILDERS — Kosher Winemaking
# ═══════════════════════════════════════════════════════════════════════════════


def _build_kosher_facts(source_id: str) -> list[dict]:
    """Build facts about kosher winemaking practices."""
    facts = []

    for fact_text in KOSHER_FACTS:
        facts.append(_make_fact(
            fact_text,
            domain="winemaking",
            source_id=source_id,
            subdomain="kosher",
            entities=[],
            tags=["kosher", "winemaking", "israel"],
        ))

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# FACT BUILDERS — Classification Systems
# ═══════════════════════════════════════════════════════════════════════════════


def _build_classification_facts(source_id: str) -> list[dict]:
    """Build facts about Lebanese and Israeli wine classification systems."""
    facts = []

    for fact_text in CLASSIFICATION_FACTS:
        # Determine country tag
        text_lower = fact_text.lower()
        tags = ["classification"]
        if "lebanon" in text_lower or "lebanese" in text_lower:
            tags.append("lebanon")
        if "israel" in text_lower or "israeli" in text_lower:
            tags.append("israel")
        if not any(t in tags for t in ["lebanon", "israel"]):
            tags.extend(["lebanon", "israel"])

        entities = []
        if "lebanon" in tags:
            entities.append({"type": "country", "name": "Lebanon"})
        if "israel" in tags:
            entities.append({"type": "country", "name": "Israel"})

        facts.append(_make_fact(
            fact_text,
            domain="wine_regions",
            source_id=source_id,
            subdomain="classification",
            entities=entities,
            tags=tags,
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
        "lebanon": _build_lebanon_facts,
        "israel": _build_israel_facts,
        "grape": _build_grape_variety_facts,
        "kosher": _build_kosher_facts,
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
        click.echo(f"\n[DRY RUN] Would insert {len(facts)} facts from Lebanon & Israel Wine Reference")

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

    logger.info(f"Inserted {inserted} new facts from Lebanon & Israel (duplicates skipped)")
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

    # (f) Country distribution
    lebanon_count = sum(1 for f in facts if "lebanon" in " ".join(f.get("tags", [])))
    israel_count = sum(1 for f in facts if "israel" in " ".join(f.get("tags", [])))
    click.echo(f"\nCountry coverage:")
    click.echo(f"  Lebanon:  {lebanon_count} facts")
    click.echo(f"  Israel:   {israel_count} facts")

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
        "Lebanon": _build_lebanon_facts,
        "Israel": _build_israel_facts,
        "Grape Varieties": _build_grape_variety_facts,
        "Kosher Winemaking": _build_kosher_facts,
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
    type=click.Choice(["lebanon", "israel", "grape", "kosher", "classification"]),
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
    """OenoBench Lebanon & Israel Wine Scraper — Regions, producers, grapes, kosher, classification."""
    logger.add("data/logs/lebanon_israel_{time}.log", rotation="10 MB")

    if list_sources:
        click.echo("\nAvailable data categories:")
        click.echo(f"  {'lebanon':18s} — {len(LEBANON_REGIONS)} regions, {len(LEBANON_PRODUCERS)} producers, {len(LEBANON_HISTORY_FACTS)} history facts")
        click.echo(f"  {'israel':18s} — {len(ISRAEL_REGIONS)} regions, {len(ISRAEL_PRODUCERS)} producers, {len(ISRAEL_HISTORY_FACTS)} history facts")
        click.echo(f"  {'grape':18s} — {len(LEBANON_GRAPES)} Lebanese + {len(ISRAEL_GRAPES)} Israeli grape varieties")
        click.echo(f"  {'kosher':18s} — {len(KOSHER_FACTS)} kosher winemaking facts")
        click.echo(f"  {'classification':18s} — {len(CLASSIFICATION_FACTS)} classification system facts")
        click.echo(f"\nKnowledge base coverage:")
        click.echo(f"  Lebanon regions:     {len(LEBANON_REGIONS)}")
        click.echo(f"  Israel regions:      {len(ISRAEL_REGIONS)}")
        click.echo(f"  Lebanon grapes:      {len(LEBANON_GRAPES)}")
        click.echo(f"  Israel grapes:       {len(ISRAEL_GRAPES)}")
        click.echo(f"  Lebanon producers:   {len(LEBANON_PRODUCERS)}")
        click.echo(f"  Israel producers:    {len(ISRAEL_PRODUCERS)}")
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
