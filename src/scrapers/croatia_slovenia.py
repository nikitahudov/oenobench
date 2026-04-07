"""
OenoBench — Croatia & Slovenia Wine Scraper

Extracts structured wine data for Croatia and Slovenia, covering wine regions,
indigenous grape varieties, classification systems, and unique wine heritage.

Focus areas: Croatian Dalmatia, Istria, Slavonia, and uplands regions;
Slovenian Goriška Brda, Vipava, Karst, Štajerska, and Posavje regions;
indigenous grapes (Plavac Mali, Rebula, Zelen, Pinela, Grk, etc.);
Zinfandel origin story; orange wine tradition; Maribor Old Vine.

Usage:
    python -m src.scrapers.croatia_slovenia --all
    python -m src.scrapers.croatia_slovenia --type croatia
    python -m src.scrapers.croatia_slovenia --type slovenia
    python -m src.scrapers.croatia_slovenia --type grape
    python -m src.scrapers.croatia_slovenia --type classification
    python -m src.scrapers.croatia_slovenia --type unique
    python -m src.scrapers.croatia_slovenia --dry-run
    python -m src.scrapers.croatia_slovenia --validate
    python -m src.scrapers.croatia_slovenia --test-run
    python -m src.scrapers.croatia_slovenia --list
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
    "name": "Croatia & Slovenia Wine Reference Database",
    "url": "https://www.croatianwine.com",
    "source_type": "reference",
    "tier": "tier_2_authoritative",
    "language": "en",
}


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Croatian Regions
# ═══════════════════════════════════════════════════════════════════════════════

CROATIA_REGIONS = [
    {
        "name": "Dalmatia",
        "local_name": "Dalmacija",
        "country": "Croatia",
        "climate": "Mediterranean",
        "climate_details": "Hot dry summers with cooling Adriatic sea breezes and mild winters; coastal and island vineyards benefit from reflected light off the sea and limestone karst terrain that retains heat",
        "soil_types": ["limestone", "karst", "terra rossa", "rocky"],
        "soil_details": "Predominantly limestone and karst geology with pockets of terra rossa (iron-rich red soil); rocky terrain forces deep root penetration, contributing to concentrated fruit character",
        "vineyard_area_ha": 6000,
        "elevation_range": "10-500m",
        "annual_rainfall_mm": 700,
        "key_grapes": ["Plavac Mali", "Babić", "Plavina", "Pošip", "Grk", "Bogdanuša", "Debit"],
        "sub_regions": [
            {
                "name": "Central Dalmatia",
                "details": "Includes the islands of Hvar, Brač, and Vis, with ancient viticultural traditions dating to Greek colonization; south-facing coastal slopes provide intense sun exposure",
                "key_grapes": ["Plavac Mali", "Bogdanuša", "Vugava"],
                "islands": ["Hvar", "Brač", "Vis", "Šolta"],
            },
            {
                "name": "Southern Dalmatia",
                "details": "Centered on the Pelješac peninsula, home to Croatia's most prestigious red wine appellations Dingač and Postup; extreme south-facing slopes with up to 45-degree gradient",
                "key_grapes": ["Plavac Mali"],
                "notable_sites": ["Dingač", "Postup"],
            },
            {
                "name": "Northern Dalmatia",
                "details": "The heartland of Babić production around Primošten, where old bush-trained vines grow on rocky terraces above the Adriatic; also known for Debit white grape",
                "key_grapes": ["Babić", "Debit"],
                "notable_sites": ["Primošten"],
            },
        ],
    },
    {
        "name": "Istria",
        "local_name": "Istra",
        "country": "Croatia",
        "climate": "maritime Mediterranean",
        "climate_details": "Moderate Mediterranean climate with warm summers and mild winters; the interior hills have more continental influence with cooler nights, benefiting white grape aromatic development",
        "soil_types": ["white soil (limestone)", "grey soil (flysch/marl)", "red soil (terra rossa)"],
        "soil_details": "Famous for the 'soil triangle': white soils (limestone) in the north for elegant whites, grey soils (flysch/marl) in the center for structured wines, and red soils (terra rossa) in the south and coast for powerful reds",
        "vineyard_area_ha": 3000,
        "elevation_range": "50-400m",
        "annual_rainfall_mm": 900,
        "key_grapes": ["Malvasia Istriana", "Teran", "Muškat Momjanski", "Refošk"],
        "sub_regions": [],
    },
    {
        "name": "Slavonia",
        "local_name": "Slavonija",
        "country": "Croatia",
        "climate": "continental",
        "climate_details": "Classic continental climate with cold winters and warm to hot summers; gentle hills provide good sun exposure and air drainage, while the Danube and Drava rivers moderate extremes",
        "soil_types": ["loess", "clay", "sand", "gravel"],
        "soil_details": "Deep loess deposits on gentle slopes provide well-drained, mineral-rich soils ideal for Graševina; clay subsoils retain moisture during dry summer periods",
        "vineyard_area_ha": 7000,
        "elevation_range": "100-400m",
        "annual_rainfall_mm": 700,
        "key_grapes": ["Graševina", "Frankovka", "Traminer", "Pinot Noir"],
        "sub_regions": [],
        "notable": "Kutjevo, founded in 1232 by Cistercian monks, is one of the oldest continuously operating wine cellars in Europe.",
    },
    {
        "name": "Croatian Uplands",
        "local_name": "Hrvatsko Zagorje",
        "country": "Croatia",
        "climate": "continental",
        "climate_details": "Cool continental climate with significant rainfall and marked seasonal variation; rolling green hills north of Zagreb provide moderate elevations for quality white wine production",
        "soil_types": ["clay", "marl", "limestone", "loess"],
        "soil_details": "Clay and marl soils on rolling hills with limestone outcrops; well-drained slopes produce aromatic white wines with good natural acidity",
        "vineyard_area_ha": 2500,
        "elevation_range": "150-400m",
        "annual_rainfall_mm": 900,
        "key_grapes": ["Riesling", "Sauvignon Blanc", "Chardonnay", "Pinot Blanc", "Škrlet"],
        "sub_regions": [],
    },
    {
        "name": "Plešivica",
        "local_name": "Plešivica",
        "country": "Croatia",
        "climate": "continental",
        "climate_details": "Cool continental climate on the southwestern slopes of the Plešivica hills near Zagreb; good diurnal temperature variation supports both still and sparkling wine production",
        "soil_types": ["limestone", "clay", "marl"],
        "soil_details": "Limestone bedrock with clay and marl overlays on south- and southwest-facing slopes; the chalky limestone soils are well suited to traditional method sparkling wines",
        "vineyard_area_ha": 1500,
        "elevation_range": "200-400m",
        "annual_rainfall_mm": 850,
        "key_grapes": ["Chardonnay", "Pinot Noir", "Riesling", "Portugizac"],
        "sub_regions": [],
        "notable": "Plešivica is Croatia's premier sparkling wine region, producing traditional method wines that rival those of more established European sparkling wine zones.",
    },
    {
        "name": "Moslavina",
        "local_name": "Moslavina",
        "country": "Croatia",
        "climate": "continental",
        "climate_details": "Moderate continental climate between the Sava and Drava rivers; the Moslavačka Gora hills provide gentle slopes for vineyard planting with adequate sun exposure",
        "soil_types": ["clay", "sand", "loess"],
        "soil_details": "Mix of clay, sand, and loess soils on the gentle slopes of the Moslavačka Gora hills; these varied soils give the indigenous Škrlet grape its distinctive mineral character",
        "vineyard_area_ha": 1500,
        "elevation_range": "100-300m",
        "annual_rainfall_mm": 800,
        "key_grapes": ["Škrlet", "Graševina", "Chardonnay"],
        "sub_regions": [],
        "notable": "Moslavina is the home region of Škrlet, an indigenous Croatian white grape found almost nowhere else in the world.",
    },
    {
        "name": "Prigorje-Bilogora",
        "local_name": "Prigorje-Bilogora",
        "country": "Croatia",
        "climate": "continental",
        "climate_details": "Continental climate with cold winters and warm summers; the Bilogora hills and the Kalnik mountain range provide diverse mesoclimates for mixed plantings",
        "soil_types": ["clay", "sand", "loess", "gravel"],
        "soil_details": "Varied soils including clay, sand, loess, and gravel on gentle to moderate slopes; the diversity of soils supports a wide range of grape varieties",
        "vineyard_area_ha": 2000,
        "elevation_range": "150-350m",
        "annual_rainfall_mm": 850,
        "key_grapes": ["Graševina", "Riesling", "Sauvignon Blanc", "Frankovka"],
        "sub_regions": [],
    },
    {
        "name": "Podunavlje",
        "local_name": "Podunavlje",
        "country": "Croatia",
        "climate": "extreme continental",
        "climate_details": "The most extreme continental climate of any Croatian wine region, with very cold winters and hot summers; located in the far east along the Danube, temperature swings drive high natural acidity",
        "soil_types": ["loess", "sand", "clay"],
        "soil_details": "Deep loess deposits characteristic of the Danube basin provide well-drained, nutrient-rich soils; sandy and clay soils also occur along the river terraces",
        "vineyard_area_ha": 2000,
        "elevation_range": "80-250m",
        "annual_rainfall_mm": 600,
        "key_grapes": ["Graševina", "Frankovka", "Traminer"],
        "sub_regions": [],
    },
]

CROATIA_ISLANDS = [
    {
        "name": "Hvar",
        "region": "Central Dalmatia",
        "details": "One of Croatia's sunniest islands with 2,724 hours of sunshine per year; ancient Greek settlers planted vineyards here in the 4th century BC, making it one of Europe's oldest viticultural sites",
        "key_grapes": ["Plavac Mali", "Bogdanuša"],
        "vineyard_area_ha": 600,
        "soil": "Rocky limestone with thin pockets of red soil",
        "notable": "The Stari Grad Plain on Hvar, a UNESCO World Heritage Site, preserves an ancient Greek agricultural landscape including vineyard plots dating to the 4th century BC.",
    },
    {
        "name": "Korčula",
        "region": "Central Dalmatia",
        "details": "Known as the birthplace of Pošip and home to the extremely rare Grk grape; vineyards face the open Adriatic and benefit from constant sea breezes and reflected light",
        "key_grapes": ["Pošip", "Grk", "Plavac Mali"],
        "vineyard_area_ha": 500,
        "soil": "Limestone karst with sandy pockets in Lumbarda",
        "notable": "The village of Lumbarda on Korčula is the only place in the world where Grk is commercially cultivated, on sandy soils near the sea.",
    },
    {
        "name": "Vis",
        "region": "Central Dalmatia",
        "details": "Croatia's most remote major inhabited island, closed to tourists until 1989 due to military use; home to the indigenous Vugava white grape, which thrives in the island's extreme maritime conditions",
        "key_grapes": ["Vugava", "Plavac Mali"],
        "vineyard_area_ha": 200,
        "soil": "Volcanic and limestone, with pockets of deeper soil in sheltered valleys",
        "notable": "Vugava is an indigenous white grape found almost exclusively on Vis island, producing aromatic wines with notes of wild herbs and honey.",
    },
    {
        "name": "Brač",
        "region": "Central Dalmatia",
        "details": "The largest island in central Dalmatia, known for its white limestone (used to build the White House in Washington); south-facing slopes produce concentrated Plavac Mali with intense sun exposure",
        "key_grapes": ["Plavac Mali", "Pošip"],
        "vineyard_area_ha": 300,
        "soil": "White limestone with terra rossa pockets",
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Slovenian Regions
# ═══════════════════════════════════════════════════════════════════════════════

SLOVENIA_REGIONS = [
    {
        "name": "Goriška Brda",
        "local_name": "Goriška Brda",
        "country": "Slovenia",
        "climate": "Mediterranean with continental influence",
        "climate_details": "A continuation of Italy's Collio hills across the border; warm Mediterranean air from the Adriatic meets cooler Alpine breezes, creating ideal conditions for aromatic white wines and skin-contact orange wines",
        "soil_types": ["ponca/flysch", "marl", "sandstone", "clay"],
        "soil_details": "The signature ponca soils (compressed layers of Eocene-era sandstone and marl, known as flysch) provide excellent drainage and mineral complexity; identical geology to Italian Collio across the border",
        "vineyard_area_ha": 2000,
        "elevation_range": "100-400m",
        "annual_rainfall_mm": 1300,
        "key_grapes": ["Rebula", "Malvazija", "Chardonnay", "Sauvignon Blanc", "Merlot", "Cabernet Sauvignon"],
        "sub_regions": [],
        "notable": "Goriška Brda is the epicenter of Slovenia's natural wine and orange wine movement, with producers using extended skin maceration and amphora fermentation in the tradition of nearby Georgia.",
    },
    {
        "name": "Vipava Valley",
        "local_name": "Vipavska Dolina",
        "country": "Slovenia",
        "climate": "Mediterranean with sub-Alpine influence",
        "climate_details": "A sheltered east-west valley between the Trnovski Gozd plateau and the Nanos massif; warm Mediterranean air channels through the valley while the bora wind from the northeast provides natural ventilation and disease prevention",
        "soil_types": ["flysch", "marl", "limestone", "alluvial"],
        "soil_details": "Flysch and marl dominate the hillsides while alluvial deposits fill the valley floor; the varied soils and aspects support an unusually diverse range of grape varieties for such a compact area",
        "vineyard_area_ha": 2200,
        "elevation_range": "100-400m",
        "annual_rainfall_mm": 1400,
        "key_grapes": ["Zelen", "Pinela", "Malvazija", "Rebula", "Barbera", "Merlot"],
        "sub_regions": [],
        "notable": "Vipava Valley is the exclusive home of two indigenous grape varieties found nowhere else: Zelen (green-skinned, aromatic) and Pinela (crisp, light-bodied).",
    },
    {
        "name": "Karst",
        "local_name": "Kras",
        "country": "Slovenia",
        "climate": "Mediterranean with strong wind influence",
        "climate_details": "A high limestone karst plateau exposed to the powerful bora wind that blows from the northeast; the wind provides natural ventilation but can damage vines; warm Mediterranean influence from the nearby Adriatic",
        "soil_types": ["terra rossa", "limestone karst", "rocky"],
        "soil_details": "Thin terra rossa (iron-rich red clay) overlying limestone karst bedrock; the iron-rich soils contribute to high iron content and tannic structure in Teran wines, and give the wine its characteristic deep color",
        "vineyard_area_ha": 600,
        "elevation_range": "200-400m",
        "annual_rainfall_mm": 1200,
        "key_grapes": ["Teran", "Vitovska", "Malvazija"],
        "sub_regions": [],
        "notable": "Karst Teran is so closely associated with its terra rossa soils that Slovenian producers have long argued it should be distinguished from Italian Refosco, despite being genetically identical.",
    },
    {
        "name": "Slovenian Istria",
        "local_name": "Slovenska Istra",
        "country": "Slovenia",
        "climate": "Mediterranean",
        "climate_details": "Warmest and most Mediterranean of all Slovenian wine regions; Adriatic coast location provides ample sunshine and sea breezes; the hilly hinterland around Koper offers slightly cooler sites",
        "soil_types": ["flysch", "marl", "sandstone", "terra rossa"],
        "soil_details": "Flysch soils (alternating layers of sandstone and marl) on the coastal hills; terra rossa on the lower slopes near the coast; these soils share characteristics with neighboring Croatian Istria",
        "vineyard_area_ha": 2000,
        "elevation_range": "20-300m",
        "annual_rainfall_mm": 1000,
        "key_grapes": ["Refošk", "Malvazija", "Cabernet Sauvignon", "Merlot"],
        "sub_regions": [],
    },
    {
        "name": "Štajerska Slovenija",
        "local_name": "Štajerska Slovenija",
        "english_name": "Slovenian Styria",
        "country": "Slovenia",
        "climate": "continental",
        "climate_details": "Cool continental climate in northeastern Slovenia with cold winters and warm summers; steep hillside vineyards maximize sun exposure and air drainage; some of the steepest vineyard slopes in Europe",
        "soil_types": ["marl", "clay", "limestone", "sandstone"],
        "soil_details": "Calcareous marl and clay on steep hillsides, often exceeding 40% gradient; the soils are mineral-rich and well-drained, producing white wines of remarkable purity and longevity",
        "vineyard_area_ha": 6500,
        "elevation_range": "200-400m",
        "annual_rainfall_mm": 900,
        "key_grapes": ["Sauvignon Blanc", "Šipon", "Riesling", "Chardonnay", "Laški Rizling", "Žametovka"],
        "sub_regions": [],
        "notable": "The city of Maribor in Štajerska is home to the Stara Trta (Old Vine), a Žametovka vine planted around 1570, certified by Guinness World Records as the oldest living grapevine in the world.",
    },
    {
        "name": "Posavje",
        "local_name": "Posavje",
        "country": "Slovenia",
        "climate": "continental",
        "climate_details": "Continental climate in southeastern Slovenia along the Sava and Krka rivers; moderate hills with varied aspects provide diverse growing conditions; slightly warmer than Štajerska",
        "soil_types": ["clay", "marl", "sand", "limestone"],
        "soil_details": "Mixed clay and marl soils on gentle hills along river valleys; limestone outcrops on higher ground; soils produce lighter, fresh-styled wines suited to the local Cviček tradition",
        "vineyard_area_ha": 2500,
        "elevation_range": "150-350m",
        "annual_rainfall_mm": 1000,
        "key_grapes": ["Modra Frankinja", "Žametovka", "Laški Rizling", "Kraljevina"],
        "sub_regions": [],
        "notable": "Posavje is the home of Cviček, a unique Slovenian PTP-protected light rosé blend (typically 9-11% alcohol) made from a traditional mix of red and white grapes, considered Slovenia's most traditional wine style.",
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Grape Varieties (both countries)
# ═══════════════════════════════════════════════════════════════════════════════

GRAPE_DATABASE = [
    # ── Croatian Reds ──
    {
        "name": "Plavac Mali",
        "color": "red",
        "country": "Croatia",
        "regions": ["Dalmatia"],
        "area_ha": 3000,
        "description": "Croatia's most important red grape variety, producing deeply colored, high-alcohol wines with rich dark fruit, dried herb, and spice character.",
        "parentage": "Natural cross of Crljenak Kaštelanski (Zinfandel) and Dobričić, confirmed by DNA analysis.",
        "key_facts": [
            "Plavac Mali is a natural cross between Crljenak Kaštelanski (Zinfandel) and Dobričić, as confirmed by DNA analysis at the University of Zagreb.",
            "Plavac Mali is the most planted red grape variety in Croatia, with approximately 3,000 hectares under vine primarily in Dalmatia.",
            "The finest Plavac Mali wines come from the steep south-facing slopes of the Pelješac peninsula, particularly the Dingač and Postup appellations.",
            "Plavac Mali wines typically reach 14-16% alcohol and are characterized by deep color, rich dark fruit, dried herbs, and firm tannins.",
            "Despite being a child of Zinfandel (Crljenak Kaštelanski), Plavac Mali produces wines that are structurally distinct — more tannic, darker, and higher in alcohol.",
        ],
    },
    {
        "name": "Crljenak Kaštelanski",
        "color": "red",
        "country": "Croatia",
        "regions": ["Dalmatia"],
        "area_ha": 50,
        "description": "Nearly extinct Croatian grape identified in 2001 as genetically identical to Zinfandel (USA) and Primitivo (Italy).",
        "parentage": "Parent of Zinfandel/Primitivo. DNA match confirmed by Carole Meredith (UC Davis) and Ivan Pejić (University of Zagreb) in 2001.",
        "key_facts": [
            "In 2001, DNA profiling by Carole Meredith of UC Davis and Ivan Pejić of the University of Zagreb proved that Crljenak Kaštelanski is genetically identical to Zinfandel and Primitivo.",
            "Crljenak Kaštelanski was found in the Kaštela area near Split, Croatia, where only a handful of ancient vines survived, making it nearly extinct at the time of its identification.",
            "The discovery of Crljenak Kaštelanski resolved decades of debate about the origins of Zinfandel, tracing America's most planted red grape to the Croatian Adriatic coast.",
            "Crljenak Kaštelanski translates roughly to 'the red one from Kaštela,' referring to the string of coastal towns between Split and Trogir in central Dalmatia.",
            "Since the 2001 DNA discovery, several Croatian producers have replanted Crljenak Kaštelanski, but total plantings remain under 50 hectares.",
        ],
    },
    {
        "name": "Babić",
        "color": "red",
        "country": "Croatia",
        "regions": ["Northern Dalmatia"],
        "area_ha": 500,
        "description": "Indigenous northern Dalmatian red grape producing medium-bodied wines with fresh red fruit, herbal notes, and moderate tannins.",
        "key_facts": [
            "Babić is an indigenous red grape variety primarily cultivated around the town of Primošten in northern Dalmatia, Croatia.",
            "Babić covers approximately 500 hectares in Croatia, mainly in the northern Dalmatia subregion where it grows on rocky limestone terraces above the Adriatic Sea.",
            "Babić produces medium-bodied red wines with fresh cherry and red berry fruit, herbal and Mediterranean scrub aromas, and moderate tannins suited to everyday drinking.",
            "Traditional Babić vineyards around Primošten use the ancient low bush-training system (gobelet) on rocky terraced slopes overlooking the sea.",
        ],
    },
    {
        "name": "Teran",
        "color": "red",
        "country": "Croatia",
        "regions": ["Istria"],
        "area_ha": 500,
        "description": "Istrian red grape (genetically identical to Refosco) known for high acidity, deep color, and elevated iron content from terra rossa soils.",
        "key_facts": [
            "Teran is the Istrian name for Refosco, producing deeply colored red wines with high acidity, firm tannins, and notable iron content derived from terra rossa soils.",
            "Teran grown on Istria's iron-rich terra rossa soils is reputed to have the highest iron content of any European red wine, a claim long promoted by local tradition.",
            "Teran covers approximately 500 hectares in Croatian Istria, where it thrives on the red soil (terra rossa) areas of the Istrian wine triangle.",
            "The naming of Teran has been a diplomatic issue between Croatia, Slovenia, and Italy, as all three countries claim the name for wines made from Refosco on terra rossa soils.",
        ],
    },
    {
        "name": "Plavina",
        "color": "red",
        "country": "Croatia",
        "regions": ["Dalmatia"],
        "area_ha": 800,
        "description": "Light-bodied Dalmatian red grape used primarily for blending and everyday rosé wines.",
        "key_facts": [
            "Plavina is a light-bodied red grape widely planted across Dalmatia, used primarily as a blending partner or for producing light, fresh rosé wines.",
            "Despite large plantings, Plavina is rarely seen as a varietal wine; it serves as an important component in Dalmatian field blends and bulk wine production.",
        ],
    },
    # ── Croatian Whites ──
    {
        "name": "Graševina",
        "color": "white",
        "country": "Croatia",
        "regions": ["Slavonia", "Croatian Uplands", "Podunavlje", "Prigorje-Bilogora"],
        "area_ha": 8000,
        "description": "Croatia's most widely planted grape variety (known internationally as Welschriesling), producing fresh, aromatic white wines ranging from dry to sweet.",
        "key_facts": [
            "Graševina (Welschriesling) is the most planted grape variety in Croatia, covering approximately 8,000 hectares, predominantly in the continental regions of Slavonia and Podunavlje.",
            "Graševina is not related to true Riesling despite the Welschriesling synonym; it is a distinct variety that produces lighter, less complex wines in a fresh aromatic style.",
            "In the Slavonia region, Graševina produces a wide range of wine styles from dry and crisp to late-harvest and ice wine, showcasing the variety's versatility in a continental climate.",
            "The historic Kutjevo cellar in Slavonia, founded by Cistercian monks in 1232, is one of Europe's oldest continually operating wine cellars and has been producing Graševina for nearly 800 years.",
        ],
    },
    {
        "name": "Malvasia Istriana",
        "color": "white",
        "country": "Croatia",
        "regions": ["Istria"],
        "area_ha": 3000,
        "local_name": "Malvazija Istarska",
        "description": "Istria's flagship white grape, producing aromatic wines with floral, almond, and stone fruit character.",
        "key_facts": [
            "Malvasia Istriana (Malvazija Istarska) is the dominant white grape of the Istrian peninsula, covering approximately 3,000 hectares in Croatian Istria alone.",
            "Malvasia Istriana produces aromatic white wines characterized by floral notes, almond, acacia, and stone fruit, with moderate acidity and a distinctive slightly bitter finish.",
            "Malvasia Istriana is shared across the borders of Croatia, Slovenia, and northeast Italy (Friuli), with each country's producers making stylistically distinct interpretations.",
            "In Istria, Malvasia Istriana is increasingly being made in an extended skin-contact (orange wine) style, reviving traditional maceration techniques that pre-date modern white winemaking.",
        ],
    },
    {
        "name": "Pošip",
        "color": "white",
        "country": "Croatia",
        "regions": ["Dalmatia"],
        "area_ha": 800,
        "description": "Full-bodied aromatic white grape from Korčula island, now planted across Dalmatia.",
        "key_facts": [
            "Pošip is an indigenous white grape that originated on the island of Korčula and is now planted across Dalmatia, covering approximately 800 hectares.",
            "Pošip was the first Croatian white grape to receive protected designation of origin (PDO) status, underscoring its importance to the national wine identity.",
            "Pošip produces full-bodied white wines with tropical fruit, citrus, and herb aromas, moderate to high alcohol, and a distinctive round, slightly oily texture.",
        ],
    },
    {
        "name": "Grk",
        "color": "white",
        "country": "Croatia",
        "regions": ["Dalmatia"],
        "area_ha": 50,
        "description": "Extremely rare Croatian white grape from Lumbarda on Korčula, notable for having only female flowers.",
        "key_facts": [
            "Grk is an extremely rare indigenous white grape cultivated almost exclusively in the village of Lumbarda on the island of Korčula, with fewer than 50 hectares planted worldwide.",
            "Grk has only female (functionally pistillate) flowers and cannot self-pollinate; it requires a pollinator variety planted nearby, traditionally Plavac Mali, to set fruit.",
            "Grk produces rich, full-bodied white wines with honey, herb, and stone fruit character, often with a slightly bitter, almond-like finish reminiscent of Greek varieties.",
            "The name Grk may derive from the Croatian word for Greek (Grk/Grci), suggesting possible ancient Greek origins from when Greek colonists planted vines on Korčula.",
            "Grk must be grown on the sandy soils of Lumbarda to produce its characteristic flavors; attempts to grow it elsewhere have not replicated the original wine's quality.",
        ],
    },
    {
        "name": "Bogdanuša",
        "color": "white",
        "country": "Croatia",
        "regions": ["Dalmatia"],
        "area_ha": 100,
        "description": "Rare indigenous white grape from Hvar island with floral, herbal character.",
        "key_facts": [
            "Bogdanuša is a rare indigenous white grape cultivated primarily on the island of Hvar in central Dalmatia, with fewer than 100 hectares remaining.",
            "Bogdanuša produces delicate white wines with floral and herbal aromas, light body, and moderate acidity, best consumed young and fresh.",
            "The name Bogdanuša is thought to derive from 'Bog dana' meaning 'God-given' in Croatian, reflecting the historical esteem for this island grape.",
        ],
    },
    {
        "name": "Debit",
        "color": "white",
        "country": "Croatia",
        "regions": ["Northern Dalmatia"],
        "area_ha": 300,
        "description": "Northern Dalmatian white grape producing crisp, refreshing wines.",
        "key_facts": [
            "Debit is an indigenous white grape of northern Dalmatia, covering approximately 300 hectares, primarily around the coastal areas near Zadar and Šibenik.",
            "Debit produces crisp, light-bodied white wines with citrus and green apple notes, designed for early drinking and seafood pairing.",
        ],
    },
    {
        "name": "Škrlet",
        "color": "white",
        "country": "Croatia",
        "regions": ["Moslavina"],
        "area_ha": 200,
        "description": "Indigenous white grape unique to the Moslavina region of Croatia.",
        "key_facts": [
            "Škrlet is an indigenous Croatian white grape found almost exclusively in the Moslavina region, covering approximately 200 hectares.",
            "Škrlet produces fresh, aromatic white wines with green apple, citrus, and mineral character, and has recently attracted attention from quality-focused Croatian producers.",
            "The name Škrlet is thought to derive from the old Croatian word for 'scarlet,' despite being a white grape, possibly referring to the reddish tinge of the ripe berry skins.",
        ],
    },
    {
        "name": "Vugava",
        "color": "white",
        "country": "Croatia",
        "regions": ["Dalmatia"],
        "area_ha": 30,
        "description": "Extremely rare indigenous white grape from Vis island.",
        "key_facts": [
            "Vugava is an indigenous white grape found almost exclusively on the island of Vis, one of Croatia's most remote inhabited islands in the central Adriatic.",
            "Vugava produces aromatic white wines with notes of wild herbs, honey, and Mediterranean scrub, reflecting the island's unique maritime terroir.",
            "With fewer than 30 hectares planted, Vugava is one of Croatia's rarest commercially cultivated grape varieties.",
        ],
    },
    # ── Slovenian Varieties ──
    {
        "name": "Rebula",
        "color": "white",
        "country": "Slovenia",
        "regions": ["Goriška Brda"],
        "area_ha": 600,
        "description": "Goriška Brda's star grape (known as Ribolla Gialla in Italy), widely used for orange/amber wines.",
        "key_facts": [
            "Rebula (known as Ribolla Gialla in Italy) is the signature white grape of Goriška Brda, covering approximately 600 hectares in Slovenia.",
            "Rebula is one of the primary grapes used for Slovenian orange (amber) wines, made with extended skin maceration that produces deep golden colors and complex tannic structure.",
            "Rebula has been cultivated in the Brda/Collio hills for centuries, with documentation dating back to at least the 13th century in local records.",
            "In Goriška Brda, Rebula is vinified in styles ranging from fresh and modern stainless steel to extended maceration orange wines aged in amphora or large oak.",
        ],
    },
    {
        "name": "Malvazija",
        "color": "white",
        "country": "Slovenia",
        "regions": ["Slovenian Istria", "Karst"],
        "area_ha": 1000,
        "description": "Slovenian expression of Malvasia Istriana, dominant in the coastal regions.",
        "key_facts": [
            "Malvazija (Malvasia Istriana) is the most important white grape in Slovenia's coastal regions, covering approximately 1,000 hectares in Slovenian Istria and the Karst.",
            "Slovenian Malvazija produces aromatic wines with floral, almond, and stone fruit notes, stylistically similar to but often more mineral-driven than Croatian Istrian expressions.",
        ],
    },
    {
        "name": "Refošk",
        "color": "red",
        "country": "Slovenia",
        "regions": ["Karst", "Slovenian Istria"],
        "area_ha": 800,
        "description": "Slovenian name for Refosco, the primary red grape of the Karst and Istrian coast.",
        "key_facts": [
            "Refošk (Refosco) is the primary red grape of Slovenia's Karst and Slovenian Istria regions, covering approximately 800 hectares.",
            "On the Karst plateau, Refošk grown on terra rossa soils is called Teran and has been the subject of a long-running EU naming dispute between Slovenia and Croatia.",
            "Refošk produces deeply colored, high-acid red wines with dark fruit, herbal, and earthy character, well suited to the rustic cuisine of the Karst region.",
        ],
    },
    {
        "name": "Šipon",
        "color": "white",
        "country": "Slovenia",
        "regions": ["Štajerska Slovenija"],
        "area_ha": 300,
        "description": "Slovenian name for Furmint, producing full-bodied dry whites in Štajerska.",
        "key_facts": [
            "Šipon is the Slovenian name for Furmint, the famous Tokaj grape of Hungary, and covers approximately 300 hectares in the Štajerska region of northeastern Slovenia.",
            "In Štajerska, Šipon (Furmint) is vinified as a full-bodied dry white wine with quince, honey, and mineral character, stylistically quite different from Hungarian Tokaji.",
            "Šipon was historically one of Štajerska's most prized grapes, though plantings have declined as Sauvignon Blanc and international varieties have expanded.",
        ],
    },
    {
        "name": "Zelen",
        "color": "white",
        "country": "Slovenia",
        "regions": ["Vipava Valley"],
        "area_ha": 200,
        "description": "Indigenous Slovenian variety exclusive to the Vipava Valley, with distinctive green-skinned berries.",
        "key_facts": [
            "Zelen is an indigenous Slovenian grape found exclusively in the Vipava Valley, covering approximately 200 hectares — it is not cultivated commercially anywhere else in the world.",
            "Zelen takes its name from the Slovenian word for 'green,' referring to the distinctive green color of its berry skins even at full ripeness.",
            "Zelen produces aromatic white wines with green apple, citrus, herbal, and floral notes, with moderate acidity and a characteristic slightly bitter finish.",
        ],
    },
    {
        "name": "Pinela",
        "color": "white",
        "country": "Slovenia",
        "regions": ["Vipava Valley"],
        "area_ha": 150,
        "description": "Indigenous Slovenian variety exclusive to the Vipava Valley, producing crisp light wines.",
        "key_facts": [
            "Pinela is an indigenous Slovenian grape cultivated exclusively in the Vipava Valley, covering approximately 150 hectares.",
            "Pinela produces light, crisp white wines with green apple and citrus notes, typically consumed young as a refreshing everyday wine.",
            "Pinela and Zelen are the two indigenous grapes unique to the Vipava Valley, and together they represent an irreplaceable piece of Slovenian viticultural heritage.",
        ],
    },
    {
        "name": "Vitovska",
        "color": "white",
        "country": "Slovenia",
        "regions": ["Karst"],
        "area_ha": 100,
        "description": "Mineral-driven white grape of the Karst plateau, expressing limestone terroir.",
        "key_facts": [
            "Vitovska is a white grape variety cultivated on the Karst plateau, covering approximately 100 hectares in Slovenia and also found across the border in Friuli Venezia Giulia, Italy.",
            "Vitovska produces intensely mineral white wines that express the limestone karst terroir, with flavors of white flowers, almonds, straw, and a saline finish.",
            "Vitovska has become a darling of the natural wine movement, with many producers in both Slovenia and Italy making skin-contact versions in amphora or large casks.",
        ],
    },
    {
        "name": "Žametovka",
        "color": "red",
        "country": "Slovenia",
        "regions": ["Štajerska Slovenija", "Posavje"],
        "area_ha": 200,
        "local_name": "Žametna Črnina",
        "description": "Slovenian red grape meaning 'velvet black,' known as the variety of the world's oldest vine.",
        "key_facts": [
            "Žametovka (also called Žametna Črnina, meaning 'velvet black') is a Slovenian red grape covering approximately 200 hectares, primarily in Štajerska and Posavje.",
            "Žametovka is the grape variety of the Stara Trta (Old Vine) in Maribor, the oldest living grapevine in the world, planted around 1570 and still producing grapes.",
            "Žametovka produces light-bodied, soft red wines with low tannins and gentle fruit, often used as a component in the traditional Cviček blend of Posavje.",
        ],
    },
    {
        "name": "Modra Frankinja",
        "color": "red",
        "country": "Slovenia",
        "regions": ["Posavje", "Štajerska Slovenija"],
        "area_ha": 500,
        "description": "Slovenian name for Blaufränkisch, the principal red grape for structured wines.",
        "key_facts": [
            "Modra Frankinja (Blaufränkisch) is Slovenia's most important red grape for quality dry reds, covering approximately 500 hectares in Posavje and Štajerska.",
            "Modra Frankinja produces medium to full-bodied red wines with dark cherry, black pepper, and mineral character, with firm acidity and age-worthy structure.",
            "In Posavje, Modra Frankinja serves as the primary red grape in the traditional Cviček blend alongside Žametovka and white grape varieties.",
        ],
    },
    {
        "name": "Laški Rizling",
        "color": "white",
        "country": "Slovenia",
        "regions": ["Štajerska Slovenija", "Posavje"],
        "area_ha": 2500,
        "description": "Slovenian name for Welschriesling, the most widely planted grape in Slovenia.",
        "key_facts": [
            "Laški Rizling (Welschriesling) is the most widely planted grape variety in Slovenia, covering approximately 2,500 hectares across Štajerska and Posavje.",
            "Like its Croatian counterpart Graševina, Laški Rizling is not related to true Rhine Riesling; it produces lighter, simpler wines used for everyday drinking and blending.",
            "Laški Rizling produces fresh, floral white wines with moderate acidity and apple-citrus character, and is an important component of the traditional Cviček blend in Posavje.",
        ],
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Classification Systems
# ═══════════════════════════════════════════════════════════════════════════════

CLASSIFICATION_DATABASE = {
    "croatia": {
        "country": "Croatia",
        "system_name": "Croatian Wine Classification",
        "pdo_name": "Zaštićena oznaka izvornosti (ZOI)",
        "pgi_name": "Zaštićena oznaka podrijetla (ZOP)",
        "facts": [
            "Croatia's wine classification system follows EU regulations with two protected categories: Zaštićena oznaka izvornosti (ZOI, equivalent to PDO) and Zaštićena oznaka podrijetla (ZOP, equivalent to PGI).",
            "Croatia recognizes four quality levels for wine: stolno vino (table wine), kvalitetno vino (quality wine), vrhunsko vino (premium wine), and arhivsko vino (archive/reserve wine).",
            "Dingač, on the Pelješac peninsula in southern Dalmatia, was the first Croatian wine appellation to receive protected designation of origin status, established in 1961.",
            "Croatia is divided into four main wine-growing regions for administrative purposes: Slavonia and the Danube, Croatian Uplands, Istria and Kvarner, and Dalmatia.",
            "Croatian wine law requires that PDO wines must be made from approved grape varieties, meet minimum quality standards, and undergo panel tasting before release.",
            "Postup, adjacent to Dingač on the Pelješac peninsula, is Croatia's second protected wine appellation, also designated for Plavac Mali.",
            "Croatian wine labels may carry a quality designation ranging from stolno vino at the base level through kvalitetno vino and vrhunsko vino up to the top-tier predikatno vino for special late-harvest and dried-grape wines.",
        ],
    },
    "slovenia": {
        "country": "Slovenia",
        "system_name": "Slovenian Wine Classification",
        "ptp_name": "Priznano Tradicionalno Poimenovanje (PTP)",
        "facts": [
            "Slovenia's wine classification system uses four quality tiers: namizno vino (table wine), deželno vino PGO (regional wine with geographical indication), kakovostno vino ZGP (quality wine from a designated region), and vrhunsko vino ZGP (premium wine from a designated region).",
            "PTP (Priznano Tradicionalno Poimenovanje, meaning 'recognized traditional denomination') is a special Slovenian designation protecting wines made by traditional methods, including Cviček and Teran.",
            "Slovenia is divided into three wine-growing regions: Podravje (northeast, including Štajerska), Posavje (southeast), and Primorska (southwest, including Brda, Vipava, Karst, and Slovenian Istria).",
            "Cviček is a PTP-protected Slovenian wine from the Posavje region, defined as a light rosé blend (9-11% alcohol) of specific red and white grape varieties in regulated proportions.",
            "The Slovenian quality designation vrhunsko vino ZGP (premium wine) requires grapes from a single ZGP-designated area, minimum must weight, and compulsory panel tasting and chemical analysis.",
            "Teran from the Karst region holds PTP status in Slovenia, protecting the name for Refošk (Refosco) wines grown specifically on the terra rossa soils of the Slovenian Karst plateau.",
            "Slovenia has approximately 28,000 registered winegrowers, most cultivating very small plots, making the average Slovenian vineyard holding one of the smallest in Europe at roughly 0.3 hectares.",
        ],
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Unique Heritage & Cultural Facts
# ═══════════════════════════════════════════════════════════════════════════════

UNIQUE_FACTS_DATABASE = [
    # ── Zinfandel Origin Story ──
    {
        "category": "zinfandel_origin",
        "facts": [
            "The 2001 DNA fingerprinting that identified Crljenak Kaštelanski as Zinfandel was a collaborative effort between Carole Meredith of UC Davis and Croatian scientists Edi Maletić and Ivan Pejić at the University of Zagreb.",
            "Before the 2001 DNA proof, Zinfandel's origins were debated for over a century; hypotheses ranged from Hungarian, Italian, to various Balkan origins.",
            "The Croatian grape Dobričić, native to the island of Šolta in central Dalmatia, was identified as the second parent of Plavac Mali alongside Crljenak Kaštelanski (Zinfandel).",
            "Crljenak Kaštelanski, Zinfandel (USA), and Primitivo (Italy) are genetically identical — the same grape variety that traveled along Mediterranean trade routes before arriving in America in the 1820s.",
            "The discovery of Crljenak Kaštelanski as Zinfandel's ancestor made Kaštela, a string of seven small towns near Split, an unexpected pilgrimage site for wine enthusiasts from around the world.",
            "Mike Grgich, the Croatian-American winemaker who won the 1976 Judgment of Paris with Chateau Montelena Chardonnay, helped fund and publicize the research connecting Zinfandel to Croatia.",
            "Following the 2001 discovery, Croatian winemakers began marketing Plavac Mali internationally by emphasizing its genetic connection to Zinfandel, calling it 'Zinfandel's Croatian cousin.'",
        ],
    },
    # ── Orange Wine Tradition ──
    {
        "category": "orange_wine",
        "facts": [
            "The orange (amber) wine tradition in Goriška Brda and the Karst region predates the modern natural wine movement by centuries, rooted in the historical practice of fermenting white grapes with extended skin contact.",
            "Slovenian and Italian producers in the Brda/Collio border region pioneered the revival of orange wine in the late 20th century, with Joško Gravner and Stanko Radikon among the most influential advocates.",
            "Joško Gravner, born in Oslavia on the Italian side of the Brda/Collio hills, began importing Georgian qvevri (clay amphorae) in 2001 and was instrumental in reviving amphora fermentation in the region.",
            "Orange wines from Goriška Brda are typically made from Rebula (Ribolla Gialla), fermented on skins for weeks to months, producing wines with amber color, tannic grip, and complex dried fruit and nutty aromas.",
            "The Slovenian-Italian border region around Brda/Collio has become the global epicenter of the orange wine movement, attracting natural wine enthusiasts and influencing winemakers worldwide.",
            "Traditional skin-contact winemaking in the Karst region involves fermenting Vitovska and Malvazija with their skins in open-top wooden vats, a practice that was standard before the introduction of temperature-controlled stainless steel.",
        ],
    },
    # ── Maribor Old Vine ──
    {
        "category": "old_vine",
        "facts": [
            "The Stara Trta (Old Vine) in Maribor, Slovenia, is certified by Guinness World Records as the oldest living grapevine in the world, planted around 1570 during the late Renaissance.",
            "The Maribor Old Vine (Stara Trta) is a Žametovka (Žametna Črnina) variety and still produces approximately 35-55 kilograms of grapes each year, which are ceremonially harvested each autumn.",
            "Wine from the Maribor Old Vine is bottled in specially commissioned 0.25-liter bottles and presented as diplomatic gifts to visiting heads of state, dignitaries, and partner cities worldwide.",
            "The Old Vine House (Hiša Stare Trte) in Maribor's Lent district is a dedicated museum and cultural center built around the vine, attracting over 100,000 visitors annually.",
            "The Maribor Old Vine survived the phylloxera epidemic that devastated European vineyards in the late 19th century because it grows on its own roots in an urban setting where the pest did not reach.",
            "Cuttings from the Maribor Old Vine have been planted in partner cities around the world, symbolizing friendship and cultural exchange between Maribor and the international community.",
        ],
    },
    # ── Dingač ──
    {
        "category": "dingac",
        "facts": [
            "Dingač is located on the south-facing slopes of the Pelješac peninsula in southern Dalmatia, where vineyards face the open Adriatic at gradients of up to 45 degrees.",
            "Dingač vineyards are so steep that historically grapes were transported down the slopes by mules or via a small tunnel carved through the mountain to the northern side of the peninsula.",
            "Dingač was designated as Croatia's first protected wine appellation in 1961, restricted to Plavac Mali grown on the specific south-facing slopes above the village of Potomje.",
            "The extreme sun exposure at Dingač, with slopes facing due south over the Adriatic, produces Plavac Mali wines that regularly exceed 15% alcohol naturally, with intense concentration.",
            "A 400-meter tunnel (the 'Dingač tunnel') was carved through the Pelješac mountainside to allow vineyard access from the northern village of Potomje to the south-facing slopes.",
            "The microclimate at Dingač benefits from sunlight reflected off the Adriatic Sea and radiated from limestone rocks, effectively giving vines triple sun exposure — direct, reflected, and re-radiated.",
        ],
    },
    # ── Croatian Island Viticulture ──
    {
        "category": "island_viticulture",
        "facts": [
            "Greek colonists from the island of Paros established vineyards on Hvar and Vis in the 4th century BC, making these among the oldest documented vineyard sites in continental Europe.",
            "The Stari Grad Plain on Hvar island is a UNESCO World Heritage Site (inscribed 2008) preserving an ancient Greek agricultural division of land (chora) that includes vineyard plots continuously cultivated for over 2,400 years.",
            "Croatia has over 1,200 islands and islets, of which approximately 50 are inhabited, and many maintain small-scale viticultural traditions that preserve indigenous grape varieties found nowhere else.",
            "Island viticulture in the Croatian Adriatic is characterized by extreme maritime influence, rocky limestone soils, constant sea breezes, and traditional bush-trained (gobelet) vines requiring no irrigation.",
            "The island of Korčula claims to be the birthplace of Marco Polo and is also the origin of both Pošip (Croatia's first PDO white grape) and Grk (a rare female-only flowering variety).",
            "Vis island was a Yugoslav military base closed to foreign visitors from 1945 to 1989, which inadvertently preserved its ancient vineyards and the indigenous Vugava grape from modernization pressures.",
        ],
    },
    # ── Cross-border Wine Culture ──
    {
        "category": "cross_border",
        "facts": [
            "The Istrian wine region spans three countries — Croatia, Slovenia, and Italy — with shared grape varieties (Malvasia Istriana, Teran/Refosco) and a common viticultural heritage despite political borders.",
            "The Brda/Collio wine region straddles the Slovenian-Italian border, with Goriška Brda on the Slovenian side and Collio Goriziano on the Italian side sharing identical ponca (flysch) soils and grape varieties.",
            "Croatia, Slovenia, and Italy share a long history of winemaking disputes, including ongoing debates about who may use the names Teran, Malvasia/Malvazija, and Prošek/Prosecco.",
            "The Croatian-Slovenian-Italian border wine regions represent one of Europe's most complex viticultural zones, where Mediterranean, continental, and Alpine climatic influences converge within a remarkably small area.",
        ],
    },
    # ── General Wine Industry ──
    {
        "category": "wine_industry",
        "facts": [
            "Croatia has approximately 20,000 hectares of vineyards and produces around 700,000 hectoliters of wine annually, making it a small but significant European wine producer.",
            "Slovenia has approximately 16,000 hectares of vineyards and produces around 600,000 hectoliters of wine annually, with the majority consumed domestically.",
            "Croatia has over 130 recognized indigenous grape varieties, one of the highest concentrations of autochthonous vine diversity in Europe relative to the country's size.",
            "Slovenia has approximately 52 officially recognized grape varieties, of which several — including Zelen, Pinela, and Vitovska — are found almost exclusively within its borders.",
            "Both Croatia and Slovenia have experienced a wine quality renaissance since the 2000s, with a new generation of producers focusing on indigenous varieties, organic farming, and minimal-intervention winemaking.",
            "The Adriatic coast of Croatia and Slovenia benefits from the cooling mistral (maestral) wind in summer, which moderates temperatures and reduces disease pressure in coastal and island vineyards.",
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


# ═══════════════════════════════════════════════════════════════════════════════
# FACT BUILDERS — Croatia
# ═══════════════════════════════════════════════════════════════════════════════


def _build_croatia_facts(source_id: str) -> list[dict]:
    """Build facts about Croatian wine regions and islands."""
    facts = []

    for region in CROATIA_REGIONS:
        name = region["name"]
        local = region["local_name"]
        entities = [{"type": "region", "name": name}, {"type": "country", "name": "Croatia"}]
        base_tags = ["croatia", name.lower().replace(" ", "_").replace("-", "_")]

        # Basic region info
        facts.append(_make_fact(
            f"{name} ({local}) is a wine region in Croatia.",
            domain="wine_regions",
            source_id=source_id,
            subdomain="croatia",
            entities=entities,
            tags=base_tags,
        ))

        # Climate
        facts.append(_make_fact(
            f"The {name} wine region of Croatia has a {region['climate']} climate.",
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
                f"The predominant soil types in Croatia's {name} wine region include {soil_list}.",
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
                f"Vineyards in Croatia's {name} wine region are planted at elevations ranging from {region['elevation_range']}.",
                domain="viticulture",
                source_id=source_id,
                subdomain="terrain",
                entities=entities,
                tags=base_tags + ["elevation"],
            ))

        # Rainfall
        if region.get("annual_rainfall_mm"):
            facts.append(_make_fact(
                f"Croatia's {name} wine region receives approximately {region['annual_rainfall_mm']}mm of annual rainfall.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="climate",
                entities=entities,
                tags=base_tags + ["rainfall", "climate"],
            ))

        # Vineyard area
        if region.get("vineyard_area_ha"):
            facts.append(_make_fact(
                f"The {name} wine region of Croatia has approximately {region['vineyard_area_ha']:,} hectares under vine.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="statistics",
                entities=entities,
                tags=base_tags + ["area", "statistics"],
            ))

        # Key grapes
        if region.get("key_grapes"):
            grape_list = ", ".join(region["key_grapes"])
            facts.append(_make_fact(
                f"The key grape varieties grown in Croatia's {name} region include {grape_list}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="croatia",
                entities=entities + [{"type": "grape", "name": g} for g in region["key_grapes"]],
                tags=base_tags + ["grapes"],
            ))

        # Notable
        if region.get("notable"):
            facts.append(_make_fact(
                region["notable"],
                domain="wine_regions",
                source_id=source_id,
                subdomain="croatia",
                entities=entities,
                tags=base_tags + ["heritage"],
            ))

        # Sub-regions
        for sub in region.get("sub_regions", []):
            sub_entities = entities + [{"type": "subregion", "name": sub["name"]}]
            sub_tags = base_tags + [sub["name"].lower().replace(" ", "_")]

            facts.append(_make_fact(
                f"{sub['details']}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="croatia",
                entities=sub_entities,
                tags=sub_tags,
            ))

            if sub.get("key_grapes"):
                grape_list = ", ".join(sub["key_grapes"])
                facts.append(_make_fact(
                    f"The key grape varieties in {sub['name']} ({name}, Croatia) include {grape_list}.",
                    domain="grape_varieties",
                    source_id=source_id,
                    subdomain="croatia",
                    entities=sub_entities + [{"type": "grape", "name": g} for g in sub["key_grapes"]],
                    tags=sub_tags + ["grapes"],
                ))

            if sub.get("islands"):
                island_list = ", ".join(sub["islands"])
                facts.append(_make_fact(
                    f"The main wine-producing islands in {sub['name']} include {island_list}.",
                    domain="wine_regions",
                    source_id=source_id,
                    subdomain="croatia",
                    entities=sub_entities,
                    tags=sub_tags + ["islands"],
                ))

            if sub.get("notable_sites"):
                site_list = ", ".join(sub["notable_sites"])
                facts.append(_make_fact(
                    f"Notable wine appellations in {sub['name']} ({name}, Croatia) include {site_list}.",
                    domain="wine_regions",
                    source_id=source_id,
                    subdomain="croatia",
                    entities=sub_entities,
                    tags=sub_tags + ["appellations"],
                ))

    # ── Islands ──
    for island in CROATIA_ISLANDS:
        entities = [{"type": "island", "name": island["name"]}, {"type": "country", "name": "Croatia"}]
        base_tags = ["croatia", "island", island["name"].lower()]

        facts.append(_make_fact(
            f"{island['details']}.",
            domain="wine_regions",
            source_id=source_id,
            subdomain="croatia_islands",
            entities=entities,
            tags=base_tags,
        ))

        if island.get("key_grapes"):
            grape_list = ", ".join(island["key_grapes"])
            facts.append(_make_fact(
                f"The main grape varieties grown on the Croatian island of {island['name']} include {grape_list}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="croatia_islands",
                entities=entities + [{"type": "grape", "name": g} for g in island["key_grapes"]],
                tags=base_tags + ["grapes"],
            ))

        if island.get("vineyard_area_ha"):
            facts.append(_make_fact(
                f"The island of {island['name']} has approximately {island['vineyard_area_ha']} hectares of vineyards.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="croatia_islands",
                entities=entities,
                tags=base_tags + ["area"],
            ))

        if island.get("soil"):
            facts.append(_make_fact(
                f"The soils on the Croatian island of {island['name']} are characterized by {island['soil'].lower()}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="terroir",
                entities=entities,
                tags=base_tags + ["soil", "terroir"],
            ))

        if island.get("notable"):
            facts.append(_make_fact(
                island["notable"],
                domain="wine_regions",
                source_id=source_id,
                subdomain="croatia_islands",
                entities=entities,
                tags=base_tags + ["heritage"],
            ))

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# FACT BUILDERS — Slovenia
# ═══════════════════════════════════════════════════════════════════════════════


def _build_slovenia_facts(source_id: str) -> list[dict]:
    """Build facts about Slovenian wine regions."""
    facts = []

    for region in SLOVENIA_REGIONS:
        name = region["name"]
        local = region["local_name"]
        entities = [{"type": "region", "name": name}, {"type": "country", "name": "Slovenia"}]
        base_tags = ["slovenia", name.lower().replace(" ", "_").replace("š", "s").replace("č", "c").replace("ž", "z")]

        # Basic region info
        facts.append(_make_fact(
            f"{name} ({local}) is a wine region in Slovenia.",
            domain="wine_regions",
            source_id=source_id,
            subdomain="slovenia",
            entities=entities,
            tags=base_tags,
        ))

        # English name if available
        if region.get("english_name"):
            facts.append(_make_fact(
                f"{name} is also known as {region['english_name']} in English.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="slovenia",
                entities=entities,
                tags=base_tags,
            ))

        # Climate
        facts.append(_make_fact(
            f"The {name} wine region of Slovenia has a {region['climate']} climate.",
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
                f"The predominant soil types in Slovenia's {name} wine region include {soil_list}.",
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
                f"Vineyards in Slovenia's {name} wine region are planted at elevations ranging from {region['elevation_range']}.",
                domain="viticulture",
                source_id=source_id,
                subdomain="terrain",
                entities=entities,
                tags=base_tags + ["elevation"],
            ))

        # Rainfall
        if region.get("annual_rainfall_mm"):
            facts.append(_make_fact(
                f"Slovenia's {name} wine region receives approximately {region['annual_rainfall_mm']}mm of annual rainfall.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="climate",
                entities=entities,
                tags=base_tags + ["rainfall", "climate"],
            ))

        # Vineyard area
        if region.get("vineyard_area_ha"):
            facts.append(_make_fact(
                f"The {name} wine region of Slovenia has approximately {region['vineyard_area_ha']:,} hectares under vine.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="statistics",
                entities=entities,
                tags=base_tags + ["area", "statistics"],
            ))

        # Key grapes
        if region.get("key_grapes"):
            grape_list = ", ".join(region["key_grapes"])
            facts.append(_make_fact(
                f"The key grape varieties grown in Slovenia's {name} region include {grape_list}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="slovenia",
                entities=entities + [{"type": "grape", "name": g} for g in region["key_grapes"]],
                tags=base_tags + ["grapes"],
            ))

        # Notable
        if region.get("notable"):
            facts.append(_make_fact(
                region["notable"],
                domain="wine_regions",
                source_id=source_id,
                subdomain="slovenia",
                entities=entities,
                tags=base_tags + ["heritage"],
            ))

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# FACT BUILDERS — Grape Varieties
# ═══════════════════════════════════════════════════════════════════════════════


def _build_grape_variety_facts(source_id: str) -> list[dict]:
    """Build facts about Croatian and Slovenian grape varieties."""
    facts = []

    for grape in GRAPE_DATABASE:
        name = grape["name"]
        color = grape["color"]
        country = grape["country"]
        entities = [{"type": "grape", "name": name}, {"type": "country", "name": country}]
        base_tags = [country.lower(), "grape", name.lower().replace(" ", "_").replace("š", "s").replace("č", "c").replace("ž", "z")]

        # Basic description
        facts.append(_make_fact(
            f"{name} is a {color} grape variety from {country}.",
            domain="grape_varieties",
            source_id=source_id,
            subdomain=country.lower(),
            entities=entities,
            tags=base_tags,
        ))

        # Description
        if grape.get("description"):
            facts.append(_make_fact(
                f"{name}: {grape['description']}",
                domain="grape_varieties",
                source_id=source_id,
                subdomain=country.lower(),
                entities=entities,
                tags=base_tags,
            ))

        # Local name
        if grape.get("local_name"):
            facts.append(_make_fact(
                f"{name} is also known locally as {grape['local_name']}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain=country.lower(),
                entities=entities,
                tags=base_tags + ["synonym"],
            ))

        # Area
        if grape.get("area_ha"):
            facts.append(_make_fact(
                f"{name} covers approximately {grape['area_ha']:,} hectares in {country}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain=country.lower(),
                entities=entities,
                tags=base_tags + ["area"],
            ))

        # Regions
        if grape.get("regions"):
            region_list = ", ".join(grape["regions"])
            facts.append(_make_fact(
                f"In {country}, {name} is primarily grown in the {region_list} region{'s' if len(grape['regions']) > 1 else ''}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain=country.lower(),
                entities=entities + [{"type": "region", "name": r} for r in grape["regions"]],
                tags=base_tags + ["regions"],
            ))

        # Parentage
        if grape.get("parentage"):
            facts.append(_make_fact(
                f"{name} parentage: {grape['parentage']}",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="genetics",
                entities=entities,
                tags=base_tags + ["genetics", "parentage"],
            ))

        # Key facts
        for kf in grape.get("key_facts", []):
            facts.append(_make_fact(
                kf,
                domain="grape_varieties",
                source_id=source_id,
                subdomain=country.lower(),
                entities=entities,
                tags=base_tags,
            ))

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# FACT BUILDERS — Classification Systems
# ═══════════════════════════════════════════════════════════════════════════════


def _build_classification_facts(source_id: str) -> list[dict]:
    """Build facts about Croatian and Slovenian wine classification systems."""
    facts = []

    for key, data in CLASSIFICATION_DATABASE.items():
        country = data["country"]
        entities = [{"type": "country", "name": country}]
        base_tags = [country.lower(), "classification", "wine_law"]

        for fact_text in data["facts"]:
            facts.append(_make_fact(
                fact_text,
                domain="wine_regions",
                source_id=source_id,
                subdomain="classification",
                entities=entities,
                tags=base_tags,
            ))

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# FACT BUILDERS — Unique Heritage
# ═══════════════════════════════════════════════════════════════════════════════


def _build_unique_facts(source_id: str) -> list[dict]:
    """Build facts about unique wine heritage: Zinfandel origin, orange wine, old vine, Dingač, islands."""
    facts = []

    category_config = {
        "zinfandel_origin": {
            "domain": "grape_varieties",
            "subdomain": "genetics",
            "entities": [{"type": "grape", "name": "Crljenak Kaštelanski"}, {"type": "grape", "name": "Zinfandel"}],
            "tags": ["croatia", "zinfandel", "genetics", "dna"],
        },
        "orange_wine": {
            "domain": "winemaking",
            "subdomain": "orange_wine",
            "entities": [{"type": "region", "name": "Goriška Brda"}, {"type": "country", "name": "Slovenia"}],
            "tags": ["slovenia", "orange_wine", "natural_wine", "skin_contact"],
        },
        "old_vine": {
            "domain": "wine_regions",
            "subdomain": "heritage",
            "entities": [{"type": "city", "name": "Maribor"}, {"type": "country", "name": "Slovenia"}, {"type": "grape", "name": "Žametovka"}],
            "tags": ["slovenia", "maribor", "old_vine", "heritage"],
        },
        "dingac": {
            "domain": "wine_regions",
            "subdomain": "croatia",
            "entities": [{"type": "appellation", "name": "Dingač"}, {"type": "country", "name": "Croatia"}, {"type": "grape", "name": "Plavac Mali"}],
            "tags": ["croatia", "dingac", "peljasac", "appellation"],
        },
        "island_viticulture": {
            "domain": "viticulture",
            "subdomain": "island_viticulture",
            "entities": [{"type": "country", "name": "Croatia"}],
            "tags": ["croatia", "islands", "heritage", "history"],
        },
        "cross_border": {
            "domain": "wine_regions",
            "subdomain": "cross_border",
            "entities": [{"type": "country", "name": "Croatia"}, {"type": "country", "name": "Slovenia"}],
            "tags": ["croatia", "slovenia", "cross_border", "shared_heritage"],
        },
        "wine_industry": {
            "domain": "wine_business",
            "subdomain": "industry_statistics",
            "entities": [{"type": "country", "name": "Croatia"}, {"type": "country", "name": "Slovenia"}],
            "tags": ["croatia", "slovenia", "industry", "statistics"],
        },
    }

    for entry in UNIQUE_FACTS_DATABASE:
        cat = entry["category"]
        config = category_config.get(cat, {
            "domain": "wine_regions",
            "subdomain": "heritage",
            "entities": [],
            "tags": ["croatia", "slovenia"],
        })

        for fact_text in entry["facts"]:
            facts.append(_make_fact(
                fact_text,
                domain=config["domain"],
                source_id=source_id,
                subdomain=config["subdomain"],
                entities=config["entities"],
                tags=config["tags"],
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
        "croatia": _build_croatia_facts,
        "slovenia": _build_slovenia_facts,
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
        click.echo(f"\n[DRY RUN] Would insert {len(facts)} facts from Croatia & Slovenia Wine Reference")

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

    logger.info(f"Inserted {inserted} new facts from Croatia & Slovenia (duplicates skipped)")
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

    # (g) Country balance
    croatia_count = sum(1 for f in facts if any("croatia" in t for t in f.get("tags", [])))
    slovenia_count = sum(1 for f in facts if any("slovenia" in t for t in f.get("tags", [])))
    click.echo(f"\n  Country balance:")
    click.echo(f"    Croatia facts:  {croatia_count}")
    click.echo(f"    Slovenia facts: {slovenia_count}")


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
        "Croatia Regions": _build_croatia_facts,
        "Slovenia Regions": _build_slovenia_facts,
        "Grape Varieties": _build_grape_variety_facts,
        "Classification": _build_classification_facts,
        "Unique Heritage": _build_unique_facts,
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
    type=click.Choice(["croatia", "slovenia", "grape", "classification", "unique"]),
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
    """OenoBench Croatia & Slovenia Wine Scraper — Regions, grapes, classification, and heritage data."""
    logger.add("data/logs/croatia_slovenia_{time}.log", rotation="10 MB")

    if list_sources:
        click.echo("\nAvailable data categories:")
        click.echo(f"  {'croatia':15s} — {len(CROATIA_REGIONS)} Croatian wine regions + {len(CROATIA_ISLANDS)} islands")
        click.echo(f"  {'slovenia':15s} — {len(SLOVENIA_REGIONS)} Slovenian wine regions")
        click.echo(f"  {'grape':15s} — {len(GRAPE_DATABASE)} grape variety profiles (both countries)")
        click.echo(f"  {'classification':15s} — Classification systems for Croatia and Slovenia")
        click.echo(f"  {'unique':15s} — {len(UNIQUE_FACTS_DATABASE)} unique heritage categories (Zinfandel origin, orange wine, old vine, etc.)")
        click.echo(f"\nKnowledge base coverage:")
        click.echo(f"  Croatian regions:    {len(CROATIA_REGIONS)}")
        click.echo(f"  Croatian islands:    {len(CROATIA_ISLANDS)}")
        click.echo(f"  Slovenian regions:   {len(SLOVENIA_REGIONS)}")
        click.echo(f"  Grape varieties:     {len(GRAPE_DATABASE)}")
        click.echo(f"  Heritage categories: {len(UNIQUE_FACTS_DATABASE)}")
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
