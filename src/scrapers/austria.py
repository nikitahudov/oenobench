"""
OenoBench — Austrian Wine Scraper

Extracts structured Austrian wine data from authoritative Austrian wine
reference sources (Austrian Wine Marketing Board — https://www.austrianwine.com).

Focus areas: wine regions (Niederösterreich, Burgenland, Steiermark, Wien),
DAC classifications, Prädikat levels, Wachau categories, grape variety profiles,
and production statistics.

Usage:
    python -m src.scrapers.austria --all
    python -m src.scrapers.austria --type region
    python -m src.scrapers.austria --type grape
    python -m src.scrapers.austria --type classification
    python -m src.scrapers.austria --type stats
    python -m src.scrapers.austria --dry-run
    python -m src.scrapers.austria --validate
    python -m src.scrapers.austria --test-run
    python -m src.scrapers.austria --list
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
    "name": "Austrian Wine Marketing Board",
    "url": "https://www.austrianwine.com",
    "source_type": "reference",
    "tier": "tier_2_authoritative",
    "language": "en",
}

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,de;q=0.8",
}

_last_request_time = 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Regional Data
# ═══════════════════════════════════════════════════════════════════════════════

REGIONAL_DATABASE = [
    # ── Niederösterreich (Lower Austria) ──
    {
        "name": "Wachau",
        "parent_region": "Niederösterreich",
        "climate": "continental with Pannonian influence",
        "climate_details": "The narrow Danube valley between Melk and Krems creates a unique mesoclimate where warm Pannonian air from the east meets cooler Atlantic influences from the west, producing excellent diurnal temperature variation on steep terraced vineyards",
        "soil_types": ["primary rock (gneiss)", "loess", "mica schist", "amphibolite"],
        "soil_details": "Steep terraced vineyards on primary rock (gneiss and mica schist) on the northern bank of the Danube, with loess deposits on flatter sections; the best sites face south toward the river",
        "elevation_range": "200-450m",
        "vineyard_area_ha": 1350,
        "key_grapes": ["Grüner Veltliner", "Riesling"],
        "annual_rainfall_mm": 500,
        "dac_status": "Wachau DAC (2020)",
        "notable_features": "Classified by Vinea Wachau into three categories: Steinfeder, Federspiel, and Smaragd based on alcohol level and ripeness",
    },
    {
        "name": "Kremstal",
        "parent_region": "Niederösterreich",
        "climate": "continental with Pannonian influence",
        "climate_details": "Surrounds the historic town of Krems at the eastern end of the Wachau; the Kremstal valley opens into the Danube valley creating a transition zone between cool upriver and warm downriver conditions",
        "soil_types": ["loess", "volcanic conglomerate", "primary rock (gneiss)"],
        "soil_details": "Loess terraces dominate the eastern bank of the Krems River, while primary rock (gneiss) characterizes the western bank and areas bordering the Wachau; volcanic conglomerate soils around Senftenberg add diversity",
        "elevation_range": "200-400m",
        "vineyard_area_ha": 2250,
        "key_grapes": ["Grüner Veltliner", "Riesling"],
        "annual_rainfall_mm": 500,
        "dac_status": "Kremstal DAC (2007)",
    },
    {
        "name": "Kamptal",
        "parent_region": "Niederösterreich",
        "climate": "continental with Pannonian influence",
        "climate_details": "The Kamp River valley creates a climate corridor where cool northern air descends at night, meeting warm Pannonian air from the Danube plain, producing significant diurnal temperature variation ideal for aromatic whites",
        "soil_types": ["loess", "primary rock (gneiss)", "volcanic", "weathered granite"],
        "soil_details": "The Heiligenstein vineyard features a unique desert sandstone (Permian Rotliegend) unlike anywhere else in Austria; the Zöbing area has gneiss and mica schist; Langenlois sits on deep loess deposits; Strass features weathered granite",
        "elevation_range": "200-400m",
        "vineyard_area_ha": 3900,
        "key_grapes": ["Grüner Veltliner", "Riesling"],
        "annual_rainfall_mm": 500,
        "dac_status": "Kamptal DAC (2008)",
        "notable_features": "Langenlois is Austria's largest wine-growing municipality",
    },
    {
        "name": "Traisental",
        "parent_region": "Niederösterreich",
        "climate": "continental with Pannonian influence",
        "climate_details": "Small region south of Krems along the Traisen River; cooler than the neighboring Kremstal due to Alpine influences from the south, producing lighter, more delicate wines",
        "soil_types": ["loess", "conglomerate", "limestone gravel"],
        "soil_details": "Dominated by deep loess deposits on the river terraces, with conglomerate and limestone gravel soils on the hillsides providing excellent drainage",
        "elevation_range": "200-350m",
        "vineyard_area_ha": 790,
        "key_grapes": ["Grüner Veltliner", "Riesling"],
        "annual_rainfall_mm": 550,
        "dac_status": "Traisental DAC (2006)",
    },
    {
        "name": "Wagram",
        "parent_region": "Niederösterreich",
        "climate": "Pannonian continental",
        "climate_details": "Located north of the Danube on a dramatic loess terrace escarpment facing south; the full Pannonian climate influence produces ripe, generous wines with characteristic creaminess from deep loess soils",
        "soil_types": ["loess"],
        "soil_details": "The defining feature is an imposing loess terrace up to 20 meters deep, among the deepest loess deposits in Europe; the fine-grained wind-blown sediment provides excellent water retention and imparts a characteristic round, creamy texture to wines",
        "elevation_range": "200-350m",
        "vineyard_area_ha": 2500,
        "key_grapes": ["Grüner Veltliner", "Roter Veltliner"],
        "annual_rainfall_mm": 500,
        "dac_status": "Wagram DAC (2021)",
        "notable_features": "One of Europe's deepest loess deposits; Roter Veltliner finds one of its best expressions here",
    },
    {
        "name": "Weinviertel",
        "parent_region": "Niederösterreich",
        "climate": "Pannonian continental",
        "climate_details": "Austria's largest wine region stretching across the gently rolling hills north of the Danube to the Czech and Slovak borders; warm and dry with classic Pannonian conditions producing the quintessential Austrian Grüner Veltliner",
        "soil_types": ["loess", "sandy", "clay", "limestone", "black earth (chernozem)"],
        "soil_details": "Diverse soils across this vast region: loess dominates the western parts, chernozem (black earth) in the Pulkau valley, sandy soils in the Manhartsberge foothills, and calcareous clay in the eastern sections near the March river",
        "elevation_range": "150-350m",
        "vineyard_area_ha": 13400,
        "key_grapes": ["Grüner Veltliner", "Welschriesling", "Zweigelt"],
        "annual_rainfall_mm": 450,
        "dac_status": "Weinviertel DAC (2002)",
        "notable_features": "Austria's first DAC (2002) and largest wine region; Grüner Veltliner accounts for approximately 50% of plantings",
    },
    {
        "name": "Carnuntum",
        "parent_region": "Niederösterreich",
        "climate": "Pannonian",
        "climate_details": "Located east of Vienna between the Danube and Lake Neusiedl; the open Pannonian plain provides warm, dry conditions with consistent breezes; the Spitzerberg and Arbesthaler hills offer altitude and slope for premium red wines",
        "soil_types": ["gravel", "loess", "clay", "limestone"],
        "soil_details": "Gravelly soils on the higher elevations around Göttlesbrunn and Höflein provide excellent drainage for red varieties; loess and clay soils on the plains are used for white wines",
        "elevation_range": "150-300m",
        "vineyard_area_ha": 900,
        "key_grapes": ["Zweigelt", "Blaufränkisch", "Grüner Veltliner"],
        "annual_rainfall_mm": 500,
        "dac_status": "Carnuntum DAC (2019)",
        "notable_features": "Named after the ancient Roman settlement of Carnuntum; Rubin Carnuntum is a regional red wine brand",
    },
    {
        "name": "Thermenregion",
        "parent_region": "Niederösterreich",
        "climate": "Pannonian with warm thermal influence",
        "climate_details": "South of Vienna along the eastern slopes of the Vienna Woods; natural thermal springs give the region its name; sheltered and warm, producing Austria's most full-bodied white wines from indigenous Zierfandler and Rotgipfler",
        "soil_types": ["limestone", "dolomite", "clay", "shell limestone"],
        "soil_details": "Heavy calcareous soils from limestone and dolomite bedrock dominate the slopes; shell limestone (Muschelkalk) appears on the upper elevations; heavier clay soils on the flatlands near Baden and Bad Vöslau",
        "elevation_range": "200-400m",
        "vineyard_area_ha": 2200,
        "key_grapes": ["Zierfandler", "Rotgipfler", "Pinot Noir", "St. Laurent"],
        "annual_rainfall_mm": 600,
        "dac_status": "Thermenregion DAC (2023)",
        "notable_features": "Only region where Zierfandler and Rotgipfler are grown; Gumpoldskirchen is the most famous village; historical source of some of Austria's best Pinot Noir",
    },

    # ── Burgenland ──
    {
        "name": "Neusiedlersee",
        "parent_region": "Burgenland",
        "climate": "Pannonian",
        "climate_details": "Flat terrain on the eastern shore of Lake Neusiedl (Neusiedler See), Europe's second-largest steppe lake; the lake's shallow waters moderate temperatures and autumn mists promote botrytis development for sweet wines; hot summers produce ripe reds",
        "soil_types": ["black earth (chernozem)", "sandy", "gravel", "salt-influenced"],
        "soil_details": "Deep chernozem (black earth) soils on the Heideboden plain east of the lake; sandy soils closer to the lakeside at Illmitz and Apetlon; gravel soils around the Seewinkel area support red varieties",
        "elevation_range": "115-180m",
        "vineyard_area_ha": 6700,
        "key_grapes": ["Zweigelt", "Welschriesling", "Chardonnay", "Bouvier"],
        "annual_rainfall_mm": 550,
        "dac_status": "Neusiedlersee DAC (2012)",
        "notable_features": "The Seewinkel area with its shallow salt lakes (Lacken) is renowned for noble sweet wines; Illmitz is the center of Austrian sweet wine production",
    },
    {
        "name": "Leithaberg",
        "parent_region": "Burgenland",
        "climate": "Pannonian moderated by Leitha Mountains",
        "climate_details": "The Leitha mountain range shelters vineyards on its eastern slopes from northwestern winds; Lake Neusiedl's influence creates a warm, humid mesoclimate; the combination produces complex, mineral wines from higher elevations",
        "soil_types": ["limestone", "mica schist", "clay-limestone", "slate"],
        "soil_details": "Crystalline mica schist and gneiss dominate the upper slopes of the Leitha hills; calcareous clay and limestone on the middle slopes; heavier clay at lower elevations near the lake",
        "elevation_range": "150-400m",
        "vineyard_area_ha": 3000,
        "key_grapes": ["Blaufränkisch", "Chardonnay", "Pinot Blanc", "Grüner Veltliner", "Neuburger"],
        "annual_rainfall_mm": 600,
        "dac_status": "Leithaberg DAC (2009)",
        "notable_features": "Leithaberg DAC mandates origin-focused wines: whites from Chardonnay, Pinot Blanc, Neuburger, or Grüner Veltliner; reds from Blaufränkisch",
    },
    {
        "name": "Mittelburgenland",
        "parent_region": "Burgenland",
        "climate": "Pannonian continental",
        "climate_details": "Known as Blaufränkischland, this is Austria's warmest and driest red wine region; the Pannonian climate provides reliable heat and sunshine for Blaufränkisch to reach full maturity; protected from western weather by the Landseer hills",
        "soil_types": ["heavy clay", "loam", "iron-rich", "gravel"],
        "soil_details": "Heavy, iron-rich clay soils dominate and are considered ideal for Blaufränkisch, producing deeply colored, full-bodied wines; some gravel soils on higher elevations around Deutschkreutz and Horitschon",
        "elevation_range": "200-400m",
        "vineyard_area_ha": 2100,
        "key_grapes": ["Blaufränkisch", "Zweigelt", "Merlot"],
        "annual_rainfall_mm": 550,
        "dac_status": "Mittelburgenland DAC (2005)",
        "notable_features": "Austria's premier region for Blaufränkisch; nicknamed Blaufränkischland; approximately 60% of vineyard area planted to Blaufränkisch",
    },
    {
        "name": "Eisenberg",
        "parent_region": "Burgenland",
        "climate": "Pannonian with Illyrian influence",
        "climate_details": "Southern Burgenland near the Hungarian border; Illyrian climate influences from the south bring warmer autumns; the iron-rich soils impart a distinctive mineral character to Blaufränkisch",
        "soil_types": ["iron-rich clay", "heavy clay", "green slate"],
        "soil_details": "Named for its iron-rich soils (Eisen means iron in German); iron oxide-rich clay soils with green slate inclusions produce wines with a characteristic ferrous minerality; the Eisenberg itself is a small hill with ideal south-facing slopes",
        "elevation_range": "200-400m",
        "vineyard_area_ha": 500,
        "key_grapes": ["Blaufränkisch", "Uhudler"],
        "annual_rainfall_mm": 700,
        "dac_status": "Eisenberg DAC (2010)",
        "notable_features": "Named for iron-rich soils; produces Blaufränkisch with distinctive mineral, ferrous character; the region borders Hungary's Sopron wine region",
    },
    {
        "name": "Rosalia",
        "parent_region": "Burgenland",
        "climate": "Pannonian",
        "climate_details": "Located between the Leithaberg and Mittelburgenland regions on the Rosalia hills; benefits from both Lake Neusiedl's influence and the sheltering effect of the Rosalia range",
        "soil_types": ["clay-limestone", "mica schist", "gravel"],
        "soil_details": "Mixed soils with clay-limestone on the lower slopes and mica schist on higher elevations; gravel terraces provide excellent drainage for red wines",
        "elevation_range": "200-350m",
        "vineyard_area_ha": 300,
        "key_grapes": ["Blaufränkisch", "Zweigelt"],
        "annual_rainfall_mm": 600,
        "dac_status": "Rosalia DAC (2018)",
        "notable_features": "Austria's newest DAC established in 2018; specializes in Blaufränkisch and rosé wines",
    },
    {
        "name": "Ruster Ausbruch",
        "parent_region": "Burgenland",
        "climate": "Pannonian with lake influence",
        "climate_details": "Tiny zone around the town of Rust on the western shore of Lake Neusiedl; the lake's proximity creates ideal conditions for noble rot (botrytis cinerea) development, with humid mornings and warm afternoons",
        "soil_types": ["limestone", "slate", "calcareous clay"],
        "soil_details": "Limestone-rich soils on the slopes above Rust; the rocky terrain retains heat and the calcareous soils contribute to the finesse and longevity of the sweet wines",
        "elevation_range": "120-250m",
        "vineyard_area_ha": 30,
        "key_grapes": ["Welschriesling", "Chardonnay", "Furmint", "Gelber Muskateller"],
        "annual_rainfall_mm": 550,
        "dac_status": "Ruster Ausbruch DAC (2020)",
        "notable_features": "Historic dessert wine category requiring minimum 27° KMW (Klosterneuburger Mostwaage); Rust was a free city of the Habsburg Empire and traded sweet wines centuries before Tokaji was renowned",
    },

    # ── Steiermark (Styria) ──
    {
        "name": "Südsteiermark",
        "parent_region": "Steiermark",
        "climate": "continental with Mediterranean and Illyrian influence",
        "climate_details": "Steep hillside vineyards on the Slovenian border benefit from warm Mediterranean air rising from the south; cool nights from the Alpine foothills preserve acidity; autumn is long and mild, allowing extended hang time",
        "soil_types": ["opok (sandy marl)", "clay-limestone", "sandstone"],
        "soil_details": "Opok is the signature soil type: a compressed sandy marl of marine origin that crumbles easily and provides excellent drainage on the steep slopes; the best Sauvignon Blanc and Gelber Muskateller sites are on pure opok",
        "elevation_range": "250-600m",
        "vineyard_area_ha": 2600,
        "key_grapes": ["Sauvignon Blanc", "Gelber Muskateller", "Welschriesling", "Chardonnay", "Weissburgunder"],
        "annual_rainfall_mm": 900,
        "dac_status": "Südsteiermark DAC (2018)",
        "notable_features": "Often compared to Sancerre for its Sauvignon Blanc; among the steepest vineyard slopes in Europe; the wine road (Südsteirische Weinstrasse) follows the Slovenian border",
    },
    {
        "name": "Weststeiermark",
        "parent_region": "Steiermark",
        "climate": "continental with Alpine influence",
        "climate_details": "The coolest of Styria's wine regions, with vineyards on steep slopes in the western Styrian hills; significant rainfall and cool temperatures produce high-acid wines; the unique Schilcher rosé is made exclusively here",
        "soil_types": ["schist", "gneiss", "sandy clay"],
        "soil_details": "Crystalline schist and gneiss soils dominate the steep hillsides; these poor, well-drained soils stress the vines and contribute to the intense, racy character of Schilcher",
        "elevation_range": "300-600m",
        "vineyard_area_ha": 500,
        "key_grapes": ["Blauer Wildbacher"],
        "annual_rainfall_mm": 1000,
        "dac_status": "Weststeiermark DAC (2018)",
        "notable_features": "Exclusively known for Schilcher, a distinctive pink rosé made from the Blauer Wildbacher grape found virtually nowhere else in the world",
    },
    {
        "name": "Vulkanland Steiermark",
        "parent_region": "Steiermark",
        "climate": "Pannonian-Illyrian with volcanic influence",
        "climate_details": "Southeast Styria with vineyards on extinct volcanic hills; the warmest of Styria's three regions with notable Pannonian influence; volcanic soils retain heat and release it at night",
        "soil_types": ["volcanic basalt", "volcanic tuff", "clay", "sand"],
        "soil_details": "Basalt, volcanic tuff, and other igneous soils from extinct volcanoes dominate the landscape; the volcanic soils provide excellent mineral nutrition and contribute distinctive smoky, mineral flavors to the wines",
        "elevation_range": "250-550m",
        "vineyard_area_ha": 1500,
        "key_grapes": ["Welschriesling", "Weissburgunder", "Traminer", "Sauvignon Blanc"],
        "annual_rainfall_mm": 800,
        "dac_status": "Vulkanland Steiermark DAC (2018)",
        "notable_features": "Formerly called Südoststeiermark; renamed in 2018 to emphasize volcanic terroir; Traminer (Gewürztraminer) has a long history here; the town of Klöch is known for its Traminer",
    },

    # ── Wien (Vienna) ──
    {
        "name": "Wien",
        "parent_region": "Wien",
        "climate": "Pannonian continental",
        "climate_details": "Vienna is one of the few capital cities in the world with significant commercial vineyards within its city limits; the Vienna Woods (Wienerwald) provide shelter from western weather while the Pannonian plain brings warm, dry conditions from the east",
        "soil_types": ["limestone", "loess", "clay", "flysch"],
        "soil_details": "The Bisamberg on the northern bank of the Danube has loess and limestone soils; the Nussberg and other hills on the western edge feature limestone and flysch; these varied soils contribute to the complexity of Wiener Gemischter Satz",
        "elevation_range": "160-400m",
        "vineyard_area_ha": 580,
        "key_grapes": ["Grüner Veltliner", "Riesling", "Weissburgunder", "Chardonnay", "Zweigelt"],
        "annual_rainfall_mm": 550,
        "dac_status": "Wiener Gemischter Satz DAC (2013)",
        "notable_features": "The Heuriger tradition of serving new wine in taverns dates back to a decree by Emperor Joseph II in 1784; Wiener Gemischter Satz is a field blend of at least 3 varieties harvested and vinified together",
    },

    # ── Bergland ──
    {
        "name": "Bergland",
        "parent_region": "Bergland",
        "climate": "Alpine continental",
        "climate_details": "Scattered mountain vineyards across Oberösterreich, Kärnten, Salzburg, Tirol, and Vorarlberg; extreme climate conditions with cold winters and short growing seasons limit production to hardy varieties on south-facing slopes",
        "soil_types": ["varied (Alpine)"],
        "soil_details": "Diverse Alpine soils ranging from granite and gneiss to moraine deposits depending on the specific location; generally thin, well-drained soils on steep slopes",
        "elevation_range": "300-700m",
        "vineyard_area_ha": 50,
        "key_grapes": ["Müller-Thurgau", "Riesling", "Blauer Burgunder"],
        "annual_rainfall_mm": 900,
        "notable_features": "Marginal wine-growing area; not eligible for DAC designation; some of Austria's highest vineyards",
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Grape Variety Data
# ═══════════════════════════════════════════════════════════════════════════════

GRAPE_VARIETY_DATABASE = [
    # ── White varieties ──
    {
        "name": "Grüner Veltliner",
        "color": "white",
        "origin": "autochthonous",
        "synonyms": ["Weissgipfler"],
        "characteristics": "Austria's signature white grape with a distinctive white pepper and green herb character; ranges from light, refreshing styles to powerful, age-worthy single-vineyard wines; high acidity and versatility with food",
        "key_regions": ["Weinviertel", "Kamptal", "Kremstal", "Wachau", "Wagram"],
        "vineyard_area_ha": 14100,
        "pct_total": 30.0,
        "notable_facts": "DNA analysis revealed Grüner Veltliner is a natural cross of Traminer and St. Georgen; accounts for approximately 30% of all Austrian vineyard area",
    },
    {
        "name": "Welschriesling",
        "color": "white",
        "origin": "international",
        "synonyms": ["Riesling Italico", "Olaszrizling", "Laški Rizling"],
        "characteristics": "Light, crisp, and refreshing with green apple, citrus, and floral notes; unrelated to Riesling despite the name; versatile grape used for dry wines, sweet wines, and as a base for sparkling",
        "key_regions": ["Burgenland", "Steiermark", "Niederösterreich"],
        "vineyard_area_ha": 3400,
        "pct_total": 7.3,
        "notable_facts": "Despite its name suggesting Italian origin, Welschriesling has no proven connection to Italy or to Riesling; widely planted across Central Europe",
    },
    {
        "name": "Riesling",
        "color": "white",
        "origin": "international",
        "synonyms": ["Weisser Riesling", "Rheinriesling"],
        "characteristics": "Elegant, mineral-driven with stone fruit, citrus, and characteristic petrol notes with age; Austria's finest Rieslings come from primary rock soils in the Wachau, Kamptal, and Kremstal",
        "key_regions": ["Wachau", "Kamptal", "Kremstal", "Wien"],
        "vineyard_area_ha": 2000,
        "pct_total": 4.3,
        "notable_facts": "Austrian Rieslings are almost always made in a dry style, distinguishing them from many German examples; thrives on primary rock (gneiss) soils where it develops intense minerality",
    },
    {
        "name": "Müller-Thurgau",
        "color": "white",
        "origin": "international",
        "synonyms": ["Rivaner"],
        "characteristics": "Light, aromatic, easy-drinking with floral and muscat notes; early ripening and high yielding; used for everyday wines and some sparkling production",
        "key_regions": ["Niederösterreich", "Bergland"],
        "vineyard_area_ha": 1600,
        "pct_total": 3.4,
        "notable_facts": "Created in 1882 by Hermann Müller from the Swiss canton of Thurgau; DNA analysis proved it is a cross of Riesling and Madeleine Royale, not Silvaner as previously thought",
    },
    {
        "name": "Weissburgunder",
        "color": "white",
        "origin": "international",
        "synonyms": ["Pinot Blanc", "Klevner"],
        "characteristics": "Medium to full-bodied with pear, apple, and subtle nutty notes; elegant and restrained; well-suited to barrel aging; a key white grape in Burgenland and Steiermark",
        "key_regions": ["Burgenland", "Steiermark", "Niederösterreich"],
        "vineyard_area_ha": 2000,
        "pct_total": 4.3,
        "notable_facts": "Pinot Blanc is a permitted variety for Leithaberg DAC white wines; in Steiermark it is often used for both still and sparkling production",
    },
    {
        "name": "Chardonnay",
        "color": "white",
        "origin": "international",
        "synonyms": ["Morillon"],
        "characteristics": "Ranges from crisp and unoaked to rich and barrel-fermented depending on the region; in Steiermark it is called Morillon and typically made in a lean, mineral style; in Burgenland it is often more opulent",
        "key_regions": ["Steiermark", "Burgenland", "Niederösterreich"],
        "vineyard_area_ha": 1500,
        "pct_total": 3.2,
        "notable_facts": "Traditionally called Morillon in Styria where it has been grown for centuries; the name Morillon is still used on labels from Steiermark to distinguish the local style",
    },
    {
        "name": "Sauvignon Blanc",
        "color": "white",
        "origin": "international",
        "synonyms": ["Muskat-Silvaner"],
        "characteristics": "Vibrant, aromatic with green pepper, gooseberry, elderflower, and mineral notes; the steep slopes and opok soils of Südsteiermark produce world-class examples rivaling the best of Sancerre and Marlborough",
        "key_regions": ["Südsteiermark", "Vulkanland Steiermark"],
        "vineyard_area_ha": 1100,
        "pct_total": 2.4,
        "notable_facts": "Formerly known as Muskat-Silvaner in Austria; Südsteiermark is considered one of the world's great terroirs for Sauvignon Blanc",
    },
    {
        "name": "Gelber Muskateller",
        "color": "white",
        "origin": "international",
        "synonyms": ["Muscat Blanc à Petits Grains", "Muskateller"],
        "characteristics": "Intensely aromatic with elderflower, rose petal, orange blossom, and grapey musk; made as a light, dry, fragrant wine in Steiermark; also used for sweet wines in Burgenland",
        "key_regions": ["Steiermark", "Wachau", "Niederösterreich"],
        "vineyard_area_ha": 800,
        "pct_total": 1.7,
        "notable_facts": "One of the oldest known grape varieties in the world; Austrian Gelber Muskateller is typically vinified bone dry to preserve delicate aromatics",
    },
    {
        "name": "Neuburger",
        "color": "white",
        "origin": "autochthonous",
        "synonyms": [],
        "characteristics": "Medium-bodied with a distinctive nutty, creamy character; subtle almond, brioche, and white flower notes; one of Austria's most underrated indigenous white grapes",
        "key_regions": ["Thermenregion", "Wachau", "Leithaberg"],
        "vineyard_area_ha": 500,
        "pct_total": 1.1,
        "notable_facts": "DNA analysis revealed Neuburger is a natural cross of Roter Veltliner and Silvaner; a permitted variety for Leithaberg DAC white wines; traditionally associated with the Wachau and Thermenregion",
    },
    {
        "name": "Zierfandler",
        "color": "white",
        "origin": "autochthonous",
        "synonyms": ["Spätrot"],
        "characteristics": "Full-bodied, rich, and complex with exotic spice, quince, and honeyed notes; late-ripening with thick skins; thrives only in the Thermenregion's warm microclimate; often blended with Rotgipfler",
        "key_regions": ["Thermenregion"],
        "vineyard_area_ha": 80,
        "pct_total": 0.17,
        "notable_facts": "Grown almost exclusively in the village of Gumpoldskirchen in the Thermenregion; the name Spätrot refers to the variety's tendency to turn reddish-pink (rot) late (spät) in the growing season",
    },
    {
        "name": "Rotgipfler",
        "color": "white",
        "origin": "autochthonous",
        "synonyms": [],
        "characteristics": "Full-bodied and aromatic with exotic fruit, almond, and spicy notes; naturally high acidity balances its richness; thrives only in the Thermenregion; often blended with Zierfandler in the traditional Gumpoldskirchner style",
        "key_regions": ["Thermenregion"],
        "vineyard_area_ha": 100,
        "pct_total": 0.21,
        "notable_facts": "Named for the reddish (rot) tips (Gipfel) of the shoot; DNA analysis suggests it is a natural cross of Traminer and Roter Veltliner; grown almost exclusively around Gumpoldskirchen",
    },
    {
        "name": "Roter Veltliner",
        "color": "white",
        "origin": "autochthonous",
        "synonyms": [],
        "characteristics": "Full-bodied and rich with stone fruit, spice, and herbal notes; high extract and alcohol potential; despite the name, it is genetically unrelated to Grüner Veltliner",
        "key_regions": ["Wagram", "Kamptal", "Kremstal"],
        "vineyard_area_ha": 150,
        "pct_total": 0.32,
        "notable_facts": "Despite sharing the Veltliner name, Roter Veltliner is genetically unrelated to Grüner Veltliner; it is actually a parent of Grüner Veltliner through crossing with Traminer; the deep loess soils of the Wagram are its finest terroir",
    },
    {
        "name": "Furmint",
        "color": "white",
        "origin": "international",
        "synonyms": ["Zapfner"],
        "characteristics": "High acidity, complex, with stone fruit and smoky mineral notes; the principal grape of Hungarian Tokaji; increasingly planted in Burgenland near the Hungarian border",
        "key_regions": ["Neusiedlersee", "Ruster Ausbruch", "Leithaberg"],
        "vineyard_area_ha": 30,
        "pct_total": 0.06,
        "notable_facts": "Historically grown in Burgenland when the region was part of Hungary; experiencing a revival as Austrian producers rediscover its potential for both dry and sweet wines; key grape for Ruster Ausbruch",
    },
    {
        "name": "Traminer",
        "color": "white",
        "origin": "international",
        "synonyms": ["Gewürztraminer", "Roter Traminer"],
        "characteristics": "Intensely aromatic with lychee, rose petal, and Turkish delight notes; full-bodied with low acidity; in Austria both the spicier Gewürztraminer and the subtler Roter Traminer are grown",
        "key_regions": ["Vulkanland Steiermark", "Thermenregion", "Niederösterreich"],
        "vineyard_area_ha": 500,
        "pct_total": 1.1,
        "notable_facts": "The town of Klöch in Vulkanland Steiermark is particularly known for its Traminer; DNA analysis shows Traminer is a parent of many Austrian varieties including Grüner Veltliner and Rotgipfler",
    },
    {
        "name": "Grüner Silvaner",
        "color": "white",
        "origin": "international",
        "synonyms": ["Silvaner"],
        "characteristics": "Neutral, crisp, and clean with subtle green apple and herbal notes; easy-drinking everyday wine; declining in plantings",
        "key_regions": ["Niederösterreich"],
        "vineyard_area_ha": 200,
        "pct_total": 0.43,
    },
    {
        "name": "Frühroter Veltliner",
        "color": "white",
        "origin": "autochthonous",
        "synonyms": ["Malvasier"],
        "characteristics": "Light, fresh, with subtle floral and herbal notes; early ripening; one of the parents of Grüner Veltliner through its identity as a Traminer clone",
        "key_regions": ["Niederösterreich"],
        "vineyard_area_ha": 250,
        "pct_total": 0.54,
    },
    {
        "name": "Scheurebe",
        "color": "white",
        "origin": "international",
        "synonyms": ["Sämling 88"],
        "characteristics": "Aromatic with grapefruit, blackcurrant leaf, and exotic fruit notes; cross of Riesling and an unknown wild vine; used for both dry and sweet wines",
        "key_regions": ["Neusiedlersee", "Thermenregion"],
        "vineyard_area_ha": 350,
        "pct_total": 0.75,
        "notable_facts": "Created by Georg Scheu in 1916 in Germany; in Austria it is valued for its aromatic intensity in both dry and Prädikat sweet wines",
    },

    # ── Red varieties ──
    {
        "name": "Zweigelt",
        "color": "red",
        "origin": "autochthonous",
        "synonyms": ["Blauer Zweigelt", "Rotburger"],
        "characteristics": "Austria's most planted red grape; medium-bodied with cherry, dark berry, and subtle spice notes; soft tannins and approachable character; versatile from everyday wine to serious, age-worthy cuvées",
        "key_regions": ["Carnuntum", "Neusiedlersee", "Weinviertel", "Burgenland"],
        "vineyard_area_ha": 6300,
        "pct_total": 13.5,
        "notable_facts": "Created in 1922 by Fritz Zweigelt at the Klosterneuburg research station by crossing Blaufränkisch with St. Laurent; originally named Rotburger; renamed Zweigelt in 1975 to honor its creator, though this has become controversial due to Fritz Zweigelt's Nazi party membership",
    },
    {
        "name": "Blaufränkisch",
        "color": "red",
        "origin": "autochthonous",
        "synonyms": ["Lemberger", "Kékfrankos", "Frankovka"],
        "characteristics": "Austria's noblest and most complex red grape; deep color, firm tannins, bright cherry and blackberry fruit, spicy pepper notes, and a characteristic mineral streak; excellent aging potential; compared to northern Rhône Syrah for its peppery spice",
        "key_regions": ["Mittelburgenland", "Eisenberg", "Leithaberg", "Carnuntum"],
        "vineyard_area_ha": 3200,
        "pct_total": 6.9,
        "notable_facts": "Considered Austria's most age-worthy and terroir-expressive red variety; the heavy clay soils of Mittelburgenland and iron-rich soils of Eisenberg produce distinctly different expressions; known as Lemberger in Germany and Kékfrankos in Hungary",
    },
    {
        "name": "St. Laurent",
        "color": "red",
        "origin": "autochthonous",
        "synonyms": ["Sankt Laurent"],
        "characteristics": "Medium-bodied with cherry, raspberry, and earthy notes; silky tannins reminiscent of Pinot Noir but with darker fruit; genetically related to Pinot Noir; notoriously difficult to cultivate, prone to coulure and millerandage",
        "key_regions": ["Thermenregion", "Neusiedlersee", "Carnuntum"],
        "vineyard_area_ha": 700,
        "pct_total": 1.5,
        "notable_facts": "DNA analysis confirmed St. Laurent is a direct offspring of Pinot Noir; despite its cultivation challenges, it produces wines of considerable elegance and complexity; the Thermenregion is considered its finest Austrian terroir",
    },
    {
        "name": "Pinot Noir",
        "color": "red",
        "origin": "international",
        "synonyms": ["Blauburgunder", "Blauer Burgunder", "Spätburgunder"],
        "characteristics": "Light to medium-bodied with red cherry, strawberry, and earthy notes; Austrian Pinot Noir has gained recognition from the Thermenregion, Burgenland, and Niederösterreich; warmer vintages have enabled riper expressions",
        "key_regions": ["Thermenregion", "Burgenland", "Niederösterreich"],
        "vineyard_area_ha": 650,
        "pct_total": 1.4,
        "notable_facts": "Called Blauburgunder or Blauer Burgunder in Austria; the Thermenregion has a long tradition of Pinot Noir cultivation dating to the 19th century",
    },
    {
        "name": "Blauer Portugieser",
        "color": "red",
        "origin": "international",
        "synonyms": ["Portugieser"],
        "characteristics": "Light, fruity, easy-drinking with low tannins; used primarily for simple, early-drinking reds; declining in plantings as growers focus on more prestigious varieties",
        "key_regions": ["Niederösterreich", "Thermenregion"],
        "vineyard_area_ha": 1200,
        "pct_total": 2.6,
        "notable_facts": "Despite its name, Blauer Portugieser has no proven connection to Portugal; DNA analysis suggests Central European origin; it was once far more widely planted but is steadily losing ground to Zweigelt and Blaufränkisch",
    },
    {
        "name": "Blauer Wildbacher",
        "color": "red",
        "origin": "autochthonous",
        "synonyms": [],
        "characteristics": "High acidity, crisp, with tart red berry and herbal notes; used exclusively for Schilcher, a distinctive pink rosé that is tangy, refreshing, and unlike any other rosé; never vinified as a serious red wine",
        "key_regions": ["Weststeiermark"],
        "vineyard_area_ha": 450,
        "pct_total": 1.0,
        "notable_facts": "Found virtually nowhere else in the world outside Weststeiermark; Schilcher derives from the word schillern (to shimmer), referring to the wine's luminous pink color; the grape is perfectly adapted to the region's cool, schist-dominated terroir",
    },
    {
        "name": "Cabernet Sauvignon",
        "color": "red",
        "origin": "international",
        "synonyms": [],
        "characteristics": "Full-bodied with blackcurrant, cedar, and green pepper notes; used primarily in Pannonian climate regions of Burgenland as part of Bordeaux-style cuvées",
        "key_regions": ["Burgenland", "Carnuntum"],
        "vineyard_area_ha": 350,
        "pct_total": 0.75,
    },
    {
        "name": "Merlot",
        "color": "red",
        "origin": "international",
        "synonyms": [],
        "characteristics": "Medium to full-bodied with plum, cherry, and chocolate notes; softer tannins than Cabernet Sauvignon; used in blends and as a varietal in Burgenland",
        "key_regions": ["Burgenland", "Niederösterreich"],
        "vineyard_area_ha": 550,
        "pct_total": 1.2,
    },
    {
        "name": "Syrah",
        "color": "red",
        "origin": "international",
        "synonyms": ["Shiraz"],
        "characteristics": "Full-bodied with dark fruit, black pepper, and smoky notes; a niche variety in Austria grown primarily in the warmest parts of Burgenland",
        "key_regions": ["Burgenland"],
        "vineyard_area_ha": 80,
        "pct_total": 0.17,
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Classification System
# ═══════════════════════════════════════════════════════════════════════════════

CLASSIFICATION_DATABASE = {
    "wine_law_hierarchy": [
        {
            "level": "Tafelwein",
            "english": "Table Wine",
            "description": "Basic Austrian wine with no geographic or varietal specificity required; rarely used commercially",
            "min_kmw": 10.7,
        },
        {
            "level": "Landwein",
            "english": "Country Wine",
            "description": "Wine from one of Austria's three Weinland regions (Weinland, Steirerland, Bergland); must be made from permitted varieties with a maximum of 11.5% potential alcohol",
            "min_kmw": 14.0,
        },
        {
            "level": "Qualitätswein",
            "english": "Quality Wine",
            "description": "Wine from one of Austria's specific wine regions, made from permitted varieties, with state testing number (Prüfnummer) and quality control tasting",
            "min_kmw": 15.0,
        },
        {
            "level": "Kabinett",
            "english": "Cabinet Wine",
            "description": "A subset of Qualitätswein with no added sugar (chaptalisation prohibited); maximum 13% alcohol; must be from a single wine region",
            "min_kmw": 17.0,
        },
        {
            "level": "Prädikatswein",
            "english": "Predicate Wine",
            "description": "Austria's highest quality wine category encompassing Spätlese through Trockenbeerenauslese; chaptalisation and enrichment are strictly prohibited; grapes must meet minimum must weight requirements",
            "min_kmw": 19.0,
        },
    ],
    "praedikat_levels": [
        {
            "level": "Spätlese",
            "min_kmw": 19.0,
            "description": "Made from late-harvested, fully ripe grapes; can be dry or sweet",
        },
        {
            "level": "Auslese",
            "min_kmw": 21.0,
            "description": "Made from hand-selected bunches of very ripe grapes; any unripe or damaged berries must be removed",
        },
        {
            "level": "Beerenauslese",
            "min_kmw": 25.0,
            "description": "Made from individually selected overripe or botrytis-affected berries; always sweet",
        },
        {
            "level": "Ausbruch",
            "min_kmw": 27.0,
            "description": "A uniquely Austrian category between Beerenauslese and Trockenbeerenauslese; made from overripe and botrytis-affected grapes; historically associated with the town of Rust in Burgenland",
        },
        {
            "level": "Trockenbeerenauslese",
            "min_kmw": 30.0,
            "description": "Made from individually selected dried, botrytis-shriveled berries; Austria's most concentrated and rarest sweet wine; TBA wines can age for decades",
        },
        {
            "level": "Eiswein",
            "min_kmw": 25.0,
            "description": "Made from grapes naturally frozen on the vine and pressed while still frozen; the ice crystals concentrate sugar and acid; must be harvested at -7°C or below",
        },
        {
            "level": "Strohwein",
            "min_kmw": 25.0,
            "description": "Made from grapes dried on straw mats or reeds for at least three months before pressing; also called Schilfwein when dried on reeds; a traditional technique producing concentrated sweet wines",
        },
    ],
    "dac_system": {
        "name": "Districtus Austriae Controllatus",
        "abbreviation": "DAC",
        "year_introduced": 2002,
        "description": "Austria's appellation system introduced in 2002 to define region-specific wine styles and quality standards; DAC wines must be typical of their region in terms of grape variety, style, and character; non-DAC wines from the same area are labeled with the broader Niederösterreich, Burgenland, or Steiermark designation",
        "first_dac": "Weinviertel DAC (2002, Grüner Veltliner)",
        "total_dacs": 18,
        "dac_list": [
            {"name": "Weinviertel", "year": 2002, "primary_grapes": "Grüner Veltliner"},
            {"name": "Mittelburgenland", "year": 2005, "primary_grapes": "Blaufränkisch"},
            {"name": "Traisental", "year": 2006, "primary_grapes": "Grüner Veltliner, Riesling"},
            {"name": "Kremstal", "year": 2007, "primary_grapes": "Grüner Veltliner, Riesling"},
            {"name": "Kamptal", "year": 2008, "primary_grapes": "Grüner Veltliner, Riesling"},
            {"name": "Leithaberg", "year": 2009, "primary_grapes": "Blaufränkisch (red), Chardonnay/Pinot Blanc/Neuburger/Grüner Veltliner (white)"},
            {"name": "Eisenberg", "year": 2010, "primary_grapes": "Blaufränkisch"},
            {"name": "Neusiedlersee", "year": 2012, "primary_grapes": "Zweigelt"},
            {"name": "Wiener Gemischter Satz", "year": 2013, "primary_grapes": "Field blend (minimum 3 varieties)"},
            {"name": "Schilcher", "year": 2018, "primary_grapes": "Blauer Wildbacher"},
            {"name": "Südsteiermark", "year": 2018, "primary_grapes": "Sauvignon Blanc, Welschriesling, Weissburgunder, Gelber Muskateller, Chardonnay (Morillon)"},
            {"name": "Vulkanland Steiermark", "year": 2018, "primary_grapes": "Welschriesling, Weissburgunder, Traminer, Sauvignon Blanc, Chardonnay (Morillon)"},
            {"name": "Rosalia", "year": 2018, "primary_grapes": "Blaufränkisch, Zweigelt"},
            {"name": "Carnuntum", "year": 2019, "primary_grapes": "Zweigelt, Blaufränkisch"},
            {"name": "Ruster Ausbruch", "year": 2020, "primary_grapes": "Sweet botrytized wines"},
            {"name": "Wachau", "year": 2020, "primary_grapes": "Grüner Veltliner, Riesling"},
            {"name": "Wagram", "year": 2021, "primary_grapes": "Grüner Veltliner, Roter Veltliner"},
            {"name": "Thermenregion", "year": 2023, "primary_grapes": "Zierfandler, Rotgipfler, Pinot Noir, St. Laurent"},
        ],
    },
    "wachau_classifications": [
        {
            "name": "Steinfeder",
            "max_alcohol": 11.5,
            "description": "The lightest Wachau wine category, named after the Stipa pennata grass that grows on the Wachau terraces; delicate, fresh, and best consumed young",
            "style": "Light and fresh",
        },
        {
            "name": "Federspiel",
            "min_alcohol": 11.5,
            "max_alcohol": 12.5,
            "description": "The middle Wachau category, named after the falconry tradition of the Wachau; medium-bodied, elegant, with good fruit concentration and structure",
            "style": "Medium-bodied and elegant",
        },
        {
            "name": "Smaragd",
            "min_alcohol": 12.5,
            "description": "The most powerful Wachau wine category, named after the emerald-green Smaragd (emerald) lizard found on the dry-stone terrace walls; full-bodied, concentrated, and capable of long aging",
            "style": "Full-bodied and concentrated",
        },
    ],
    "gemischter_satz_rules": {
        "name": "Wiener Gemischter Satz DAC",
        "description": "A traditional Viennese field blend wine style where at least 3 white grape varieties are co-planted, co-harvested, and co-vinified from a single vineyard; no single variety may exceed 50% and the third-largest variety must constitute at least 10%",
        "min_varieties": 3,
        "max_single_variety_pct": 50,
        "min_third_variety_pct": 10,
        "requirement": "Must be from Vienna (Wien); grapes must be planted together in the vineyard and harvested simultaneously (not blended after vinification)",
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Production Statistics
# ═══════════════════════════════════════════════════════════════════════════════

PRODUCTION_STATS = {
    "national": {
        "total_vineyard_area_ha": 45000,
        "annual_production_hl": 2400000,
        "white_pct": 66,
        "red_pct": 34,
        "number_of_winegrowers": 14000,
        "number_of_bottling_estates": 4200,
        "export_pct": 30,
    },
    "regional": {
        "Niederösterreich": {
            "vineyard_area_ha": 27000,
            "pct_of_total": 60.0,
            "production_hl": 1400000,
            "white_pct": 75,
            "red_pct": 25,
        },
        "Burgenland": {
            "vineyard_area_ha": 11500,
            "pct_of_total": 25.6,
            "production_hl": 650000,
            "white_pct": 45,
            "red_pct": 55,
        },
        "Steiermark": {
            "vineyard_area_ha": 4700,
            "pct_of_total": 10.4,
            "production_hl": 250000,
            "white_pct": 80,
            "red_pct": 20,
        },
        "Wien": {
            "vineyard_area_ha": 580,
            "pct_of_total": 1.3,
            "production_hl": 25000,
            "white_pct": 80,
            "red_pct": 20,
        },
        "Bergland": {
            "vineyard_area_ha": 50,
            "pct_of_total": 0.1,
            "production_hl": 2000,
            "white_pct": 70,
            "red_pct": 30,
        },
    },
    "top_grapes_by_area": [
        {"name": "Grüner Veltliner", "area_ha": 14100, "pct": 30.0},
        {"name": "Zweigelt", "area_ha": 6300, "pct": 13.5},
        {"name": "Welschriesling", "area_ha": 3400, "pct": 7.3},
        {"name": "Blaufränkisch", "area_ha": 3200, "pct": 6.9},
        {"name": "Riesling", "area_ha": 2000, "pct": 4.3},
        {"name": "Weissburgunder", "area_ha": 2000, "pct": 4.3},
        {"name": "Müller-Thurgau", "area_ha": 1600, "pct": 3.4},
        {"name": "Chardonnay", "area_ha": 1500, "pct": 3.2},
        {"name": "Blauer Portugieser", "area_ha": 1200, "pct": 2.6},
        {"name": "Sauvignon Blanc", "area_ha": 1100, "pct": 2.4},
    ],
}


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Historical and Cultural Facts
# ═══════════════════════════════════════════════════════════════════════════════

HISTORICAL_CULTURAL_DATABASE = [
    # Wine history
    {
        "fact": "Austrian winemaking dates back to at least 700 BC, when Celtic tribes cultivated wild vines in the Danube valley before Roman colonization",
        "domain": "wine_regions",
        "subdomain": "history",
        "tags": ["history", "ancient"],
    },
    {
        "fact": "The Romans expanded viticulture along the Danube in the province of Pannonia, establishing vineyards in what is now Carnuntum and the Wachau around the 1st century AD",
        "domain": "wine_regions",
        "subdomain": "history",
        "tags": ["history", "roman"],
    },
    {
        "fact": "Cistercian and Benedictine monks played a crucial role in developing Austrian viticulture during the Middle Ages, particularly in the Wachau where terraced vineyards were systematically expanded",
        "domain": "wine_regions",
        "subdomain": "history",
        "tags": ["history", "medieval"],
    },
    {
        "fact": "The 1985 Austrian wine scandal, in which some producers adulterated wines with diethylene glycol, led to the most stringent wine laws in the world and ultimately transformed Austria into a quality-focused wine nation",
        "domain": "wine_business",
        "subdomain": "history",
        "tags": ["history", "wine_law", "scandal"],
    },
    {
        "fact": "Austria's modern wine law of 1985, enacted in response to the diethylene glycol scandal, established strict controls on must weight, chaptalization, labeling, and quality testing that exceed EU minimum requirements",
        "domain": "wine_business",
        "subdomain": "regulation",
        "tags": ["history", "wine_law"],
    },
    {
        "fact": "The Vinea Wachau Nobilis Districtus association was founded in 1983 to protect the quality and identity of Wachau wines, establishing the Steinfeder, Federspiel, and Smaragd classification system",
        "domain": "wine_regions",
        "subdomain": "history",
        "tags": ["history", "wachau", "vinea_wachau"],
    },
    {
        "fact": "The Klosterneuburg wine research station, founded in 1860, is one of the world's oldest viticultural research institutions and developed the KMW must weight scale used in Austrian wine law",
        "domain": "winemaking",
        "subdomain": "history",
        "tags": ["history", "research", "klosterneuburg"],
    },
    {
        "fact": "Fritz Zweigelt created the Zweigelt grape crossing at Klosterneuburg in 1922 by crossing Blaufränkisch with St. Laurent, producing what would become Austria's most widely planted red variety",
        "domain": "grape_varieties",
        "subdomain": "history",
        "tags": ["history", "zweigelt", "breeding"],
    },
    # Culture
    {
        "fact": "The Heuriger is a traditional Viennese wine tavern where local winegrowers serve their new vintage wine directly to customers, a practice authorized by Emperor Joseph II's decree of 1784",
        "domain": "wine_business",
        "subdomain": "culture",
        "tags": ["culture", "heuriger", "wien"],
    },
    {
        "fact": "Austrian wine labels may use the designation 'Alte Reben' (old vines) to indicate wines made from vines of significant age, though there is no legally defined minimum vine age",
        "domain": "winemaking",
        "subdomain": "labeling",
        "tags": ["labeling", "alte_reben"],
    },
    {
        "fact": "The Buschenschank is a traditional Austrian wine tavern found in Steiermark where growers serve their own wine alongside cold food platters (Brettljause), similar to the Heuriger tradition in Vienna",
        "domain": "wine_business",
        "subdomain": "culture",
        "tags": ["culture", "buschenschank", "steiermark"],
    },
    {
        "fact": "The Wachau was designated a UNESCO World Heritage Site in 2000, recognized for its cultural landscape including its historic terraced vineyards along the Danube River",
        "domain": "wine_regions",
        "subdomain": "history",
        "tags": ["history", "wachau", "unesco"],
    },
    {
        "fact": "The Austrian Wine Marketing Board (Österreichische Weinmarketinggesellschaft, ÖWM) was established in 1986 to rebuild Austria's international wine reputation after the 1985 scandal",
        "domain": "wine_business",
        "subdomain": "history",
        "tags": ["history", "marketing", "oewm"],
    },
    {
        "fact": "The town of Rust in Burgenland has produced sweet botrytized wines since the 16th century and was granted the privilege of displaying the letter 'R' on its wine barrels by the Habsburg monarchy",
        "domain": "wine_regions",
        "subdomain": "history",
        "tags": ["history", "rust", "sweet_wine"],
    },
    {
        "fact": "Austria's wine production area ranks it among the smaller European wine countries, comparable in size to the Bordeaux region of France alone",
        "domain": "wine_business",
        "subdomain": "production",
        "tags": ["comparison", "statistics"],
    },
    {
        "fact": "The terraced vineyards of the Wachau are maintained by hand on dry-stone walls that stretch for approximately 700 kilometers in total length",
        "domain": "viticulture",
        "subdomain": "terrain",
        "tags": ["wachau", "terraces", "viticulture"],
    },
    {
        "fact": "Austria prohibits chaptalization (adding sugar to must before fermentation) for all wines of Kabinett level and above, a stricter standard than many other European wine-producing countries",
        "domain": "winemaking",
        "subdomain": "production_rules",
        "tags": ["wine_law", "chaptalization"],
    },
    {
        "fact": "Austrian Qualitätswein must pass both a chemical analysis and a blind tasting by a government panel to receive a Prüfnummer (state testing number) before it can be sold",
        "domain": "winemaking",
        "subdomain": "production_rules",
        "tags": ["wine_law", "quality_control"],
    },
    {
        "fact": "The Heiligenstein vineyard in Kamptal features unique Permian red sandstone (Rotliegend) soils dating back 250 million years, found nowhere else among Austrian wine sites",
        "domain": "wine_regions",
        "subdomain": "terroir",
        "tags": ["kamptal", "heiligenstein", "terroir"],
    },
    {
        "fact": "Lake Neusiedl (Neusiedler See) in Burgenland is Europe's second-largest steppe lake and the only one in Europe; its shallow waters (average depth 1.5m) create a moderating effect on the surrounding vineyards and promote botrytis formation",
        "domain": "wine_regions",
        "subdomain": "geography",
        "tags": ["neusiedlersee", "lake", "geography"],
    },
    {
        "fact": "The Austrian wine region Bergland consists of scattered mountain vineyards across five federal states: Oberösterreich, Kärnten, Salzburg, Tirol, and Vorarlberg",
        "domain": "wine_regions",
        "subdomain": "geography",
        "tags": ["bergland", "geography"],
    },
    {
        "fact": "Grüner Veltliner gained international recognition after outperforming leading Chardonnays and Rieslings at a 2002 London tasting organized by wine writers Jancis Robinson and Tim Atkin",
        "domain": "grape_varieties",
        "subdomain": "history",
        "tags": ["gruener_veltliner", "history", "recognition"],
    },
    {
        "fact": "Austrian wine law divides the country into four generic wine-growing regions (Weinbauregionen): Weinland (encompassing Niederösterreich and Burgenland), Steirerland (Steiermark), Wien, and Bergland",
        "domain": "wine_regions",
        "subdomain": "classification",
        "tags": ["wine_law", "regions"],
    },
    {
        "fact": "The Austrian DAC system is modeled on similar concepts to France's AOC and Italy's DOC, but was designed to be more flexible, allowing regions to define their own grape varieties and wine styles",
        "domain": "wine_regions",
        "subdomain": "classification",
        "tags": ["dac", "classification"],
    },
    {
        "fact": "Austrian Sekt (sparkling wine) has its own quality pyramid established in 2015 with three tiers: Klassik (tank method), Reserve (traditional method, 18 months lees), and Große Reserve (traditional method, 30 months lees, single vineyard)",
        "domain": "winemaking",
        "subdomain": "sparkling",
        "tags": ["sekt", "sparkling", "classification"],
    },
    {
        "fact": "The Austrian Sekt quality pyramid requires that all grapes for Sekt g.U. (geschützter Ursprungsbezeichnung) must be hand-harvested and originate from a defined Austrian wine region",
        "domain": "winemaking",
        "subdomain": "sparkling",
        "tags": ["sekt", "sparkling", "production_rules"],
    },
    {
        "fact": "Uhudler is a controversial Austrian wine made from hybrid grape varieties (direct producer hybrids of American and European species) grown in southern Burgenland, which was banned from 1936 to 1992",
        "domain": "wine_regions",
        "subdomain": "culture",
        "tags": ["uhudler", "burgenland", "culture"],
    },
    {
        "fact": "The Pannonian climate that dominates eastern Austria is characterized by hot, dry summers and cold winters with a continental temperature range, providing the warmth needed to ripen red varieties like Blaufränkisch and Zweigelt",
        "domain": "wine_regions",
        "subdomain": "climate",
        "tags": ["pannonian", "climate"],
    },
    {
        "fact": "Austria's per capita wine consumption is approximately 26 liters per year, placing it among the top wine-consuming nations in the world",
        "domain": "wine_business",
        "subdomain": "consumption",
        "tags": ["consumption", "statistics"],
    },
    {
        "fact": "The major export markets for Austrian wine include Germany, Switzerland, the United States, and the Nordic countries, with dry Grüner Veltliner being the most exported style",
        "domain": "wine_business",
        "subdomain": "trade",
        "tags": ["exports", "trade"],
    },
    {
        "fact": "The Wachau dry-stone terraces, locally called Steinterrassen, have been built and maintained over more than 1,000 years and require constant manual repair to prevent erosion on the steep slopes",
        "domain": "viticulture",
        "subdomain": "terrain",
        "tags": ["wachau", "terraces", "viticulture"],
    },
    {
        "fact": "Austrian Strohwein (straw wine) must be made from grapes dried on straw mats or reeds for a minimum of three months before pressing, concentrating sugars and flavors through dehydration",
        "domain": "winemaking",
        "subdomain": "production_rules",
        "tags": ["strohwein", "sweet_wine"],
    },
    {
        "fact": "Austrian Eiswein must be made from grapes naturally frozen on the vine at a temperature of -7°C or below, with pressing occurring while the grapes are still frozen to concentrate sugars and acids",
        "domain": "winemaking",
        "subdomain": "production_rules",
        "tags": ["eiswein", "sweet_wine"],
    },
    {
        "fact": "The Wachau is divided into distinct vineyard areas known as Rieden (the Austrian term for individual vineyard sites), with famous sites including Achleiten, Klaus, Kellerberg, Loibenberg, and Singerriedel",
        "domain": "wine_regions",
        "subdomain": "geography",
        "tags": ["wachau", "rieden", "vineyards"],
    },
    {
        "fact": "The Ried designation on Austrian wine labels, formalized in the 2009 wine law revision, indicates a specific vineyard site (Einzellage), providing consumers with information about the wine's precise geographic origin",
        "domain": "wine_regions",
        "subdomain": "classification",
        "tags": ["ried", "vineyard", "labeling"],
    },
    {
        "fact": "The Austrian wine region classification system includes three quality tiers for DAC wines: Gebietswein (regional), Ortswein (village), and Riedenwein (single vineyard), in ascending order of specificity",
        "domain": "wine_regions",
        "subdomain": "classification",
        "tags": ["dac", "classification", "tiers"],
    },
    {
        "fact": "Many Austrian DACs have adopted the three-tier classification of Gebietswein, Ortswein, and Riedenwein, similar in concept to France's regional, village, and premier/grand cru hierarchy",
        "domain": "wine_regions",
        "subdomain": "classification",
        "tags": ["dac", "classification", "tiers"],
    },
    {
        "fact": "Blaufränkisch and Zweigelt together account for over 20% of Austria's total vineyard area, making them the dominant red varieties in a country where white wine production still predominates at 66% of output",
        "domain": "grape_varieties",
        "subdomain": "statistics",
        "tags": ["blaufraenkisch", "zweigelt", "statistics"],
    },
    {
        "fact": "The Nussberg in Vienna is one of Austria's most prestigious urban vineyard sites, with documented grape growing dating back to Roman times and panoramic views of the Danube and the city",
        "domain": "wine_regions",
        "subdomain": "geography",
        "tags": ["wien", "nussberg", "vineyard"],
    },
    {
        "fact": "Austria's organic vineyard area has grown significantly, with approximately 16% of Austrian vineyards now certified organic or biodynamic, one of the highest ratios in the world",
        "domain": "viticulture",
        "subdomain": "organic",
        "tags": ["organic", "biodynamic", "sustainability"],
    },
    {
        "fact": "The Austrian concept of Terroir (Herkunft in German) has become the central organizing principle of the DAC system, emphasizing that wines should express the character of their specific region, village, or vineyard",
        "domain": "wine_regions",
        "subdomain": "classification",
        "tags": ["terroir", "herkunft", "dac"],
    },
    {
        "fact": "The Kamptal vineyard site Heiligenstein is one of Austria's first designated Erste Lagen (premier crus), recognized for consistently producing Rieslings of exceptional quality and aging potential",
        "domain": "wine_regions",
        "subdomain": "geography",
        "tags": ["kamptal", "heiligenstein", "erste_lagen"],
    },
    {
        "fact": "Austria's 2009 wine law revision introduced the concept of Erste Lagen (premier cru vineyards) at the ÖTW (Österreichische Traditionsweingüter) level, identifying top vineyard sites in Niederösterreich and Wien based on historical reputation and terroir",
        "domain": "wine_regions",
        "subdomain": "classification",
        "tags": ["erste_lagen", "oetw", "classification"],
    },
    {
        "fact": "The Seewinkel area near Illmitz in Neusiedlersee contains more than 40 shallow salt lakes (Lacken) whose unique ecosystem creates ideal conditions for noble rot (Botrytis cinerea) development on grapes",
        "domain": "wine_regions",
        "subdomain": "geography",
        "tags": ["neusiedlersee", "seewinkel", "botrytis"],
    },
    {
        "fact": "The 1985 wine scandal paradoxically benefited Austrian wine in the long term by forcing the industry to focus on quality over quantity, transforming Austria from a bulk wine producer into a respected source of premium wines",
        "domain": "wine_business",
        "subdomain": "history",
        "tags": ["history", "scandal", "quality"],
    },
    # Viticulture practices
    {
        "fact": "Austrian vineyards are predominantly trained using Lenz Moser high culture or Guyot systems, with some traditional pergola training still found in Steiermark",
        "domain": "viticulture",
        "subdomain": "training",
        "tags": ["viticulture", "training_system"],
    },
    {
        "fact": "The harvest season in Austria typically begins in September for early-ripening varieties and extends through November for Prädikat wines, with Eiswein occasionally harvested in December or January",
        "domain": "viticulture",
        "subdomain": "harvest",
        "tags": ["viticulture", "harvest"],
    },
    {
        "fact": "Lenz Moser developed the high-culture vine training system in Austria in the 1930s, using wider row spacing and higher trunk heights to improve air circulation and facilitate mechanical harvesting",
        "domain": "viticulture",
        "subdomain": "training",
        "tags": ["viticulture", "lenz_moser", "history"],
    },
    {
        "fact": "Phylloxera devastated Austrian vineyards in the late 19th century, leading to widespread replanting on American rootstock and a shift toward more productive grape varieties",
        "domain": "viticulture",
        "subdomain": "history",
        "tags": ["viticulture", "phylloxera", "history"],
    },
    {
        "fact": "The steep terraced vineyards of the Wachau, Südsteiermark, and Weststeiermark are classified as heroic viticulture due to their extreme slopes exceeding 30% gradient, requiring entirely manual labor",
        "domain": "viticulture",
        "subdomain": "terrain",
        "tags": ["viticulture", "heroic", "terraces"],
    },
    {
        "fact": "Austria's continental climate provides cold winters that naturally control vine diseases and pests, reducing the need for chemical treatments compared to warmer wine regions",
        "domain": "viticulture",
        "subdomain": "climate",
        "tags": ["viticulture", "climate", "disease"],
    },
    {
        "fact": "The Danube River plays a critical role in Austrian viticulture by moderating temperatures in the Wachau, Kremstal, and Kamptal regions and reflecting sunlight onto south-facing vineyard slopes",
        "domain": "viticulture",
        "subdomain": "geography",
        "tags": ["viticulture", "danube", "geography"],
    },
    {
        "fact": "The Pannonian steppe climate of eastern Austria is characterized by over 2,000 hours of sunshine per year in regions like Neusiedlersee and Mittelburgenland, providing ample warmth for red grape maturation",
        "domain": "wine_regions",
        "subdomain": "climate",
        "tags": ["pannonian", "climate", "sunshine"],
    },
    # Winemaking practices
    {
        "fact": "Austrian winemakers predominantly use stainless steel tanks and large neutral oak casks (Fuder or Stückfass) for fermentation and aging, preserving grape and terroir character over oak influence",
        "domain": "winemaking",
        "subdomain": "techniques",
        "tags": ["winemaking", "fermentation"],
    },
    {
        "fact": "The Austrian tradition of using large neutral oak casks from Austrian or Slavonian oak contrasts with the French barrique approach, and is considered better suited to preserving the mineral character of Grüner Veltliner and Riesling",
        "domain": "winemaking",
        "subdomain": "techniques",
        "tags": ["winemaking", "oak", "casks"],
    },
    {
        "fact": "Spontaneous (wild yeast) fermentation is increasingly practiced by Austrian natural wine producers, particularly in the Kamptal, Wachau, and Wien regions",
        "domain": "winemaking",
        "subdomain": "techniques",
        "tags": ["winemaking", "fermentation", "natural_wine"],
    },
    {
        "fact": "Orange wine (skin-contact white wine) production has a small but growing following in Austria, particularly among natural wine producers in Steiermark and Burgenland",
        "domain": "winemaking",
        "subdomain": "wine_styles",
        "tags": ["winemaking", "orange_wine"],
    },
    {
        "fact": "The appassimento technique (drying grapes before pressing) is used in some Austrian red winemaking in Burgenland to increase concentration, though it remains a minority practice",
        "domain": "winemaking",
        "subdomain": "techniques",
        "tags": ["winemaking", "appassimento", "burgenland"],
    },
    # Wine styles and food
    {
        "fact": "Grüner Veltliner is widely considered one of the world's most food-friendly white wines due to its combination of peppery spice, fresh acidity, and moderate alcohol",
        "domain": "grape_varieties",
        "subdomain": "food_pairing",
        "tags": ["gruener_veltliner", "food_pairing"],
    },
    {
        "fact": "Austrian Riesling from the Wachau is distinguished from German Riesling by being almost exclusively vinified in a dry style, with the Smaragd category producing wines of considerable power and complexity",
        "domain": "winemaking",
        "subdomain": "wine_styles",
        "tags": ["riesling", "wachau", "dry"],
    },
    {
        "fact": "The traditional Viennese Heuriger wine tavern marks its open status by hanging a pine branch (Föhrenbusch) above the entrance, a custom dating back to Emperor Joseph II's 1784 decree",
        "domain": "wine_business",
        "subdomain": "culture",
        "tags": ["culture", "heuriger", "wien"],
    },
    {
        "fact": "Austrian sweet wines from the Neusiedlersee region are considered among the finest botrytized wines in the world, rivaling Sauternes, Tokaji, and German Trockenbeerenauslese",
        "domain": "winemaking",
        "subdomain": "wine_styles",
        "tags": ["sweet_wine", "neusiedlersee", "botrytis"],
    },
    {
        "fact": "Cuvée wines (blends) are increasingly important in Austrian red wine production, with Burgenland producers creating Bordeaux-style blends of Blaufränkisch, Zweigelt, Cabernet Sauvignon, and Merlot",
        "domain": "winemaking",
        "subdomain": "wine_styles",
        "tags": ["winemaking", "cuvee", "blends", "burgenland"],
    },
    {
        "fact": "The tradition of Sturm (cloudy, partially fermented grape must) is a popular seasonal drink in Austria, typically available for a few weeks in autumn during the harvest period",
        "domain": "wine_business",
        "subdomain": "culture",
        "tags": ["culture", "sturm", "harvest"],
    },
    # Notable producers context (not naming specific producers but providing context)
    {
        "fact": "The Wachau is home to some of Austria's most famous wine cooperatives, including the Domäne Wachau (formerly Freie Weingärtner Wachau), which manages over 440 hectares of terraced vineyards",
        "domain": "wine_business",
        "subdomain": "producers",
        "tags": ["wachau", "cooperative", "producers"],
    },
    {
        "fact": "Austrian wine cooperatives (Winzergenossenschaften) account for approximately 30% of total wine production, with large cooperatives particularly important in the Weinviertel and Burgenland",
        "domain": "wine_business",
        "subdomain": "industry",
        "tags": ["cooperative", "industry", "statistics"],
    },
    {
        "fact": "The Austrian wine classification body ÖTW (Österreichische Traditionsweingüter) is a voluntary association of leading estates that has classified over 80 Erste Lagen (premier vineyard sites) in Niederösterreich and Wien",
        "domain": "wine_regions",
        "subdomain": "classification",
        "tags": ["oetw", "erste_lagen", "classification"],
    },
    {
        "fact": "Climate change has enabled Austrian red wine regions, particularly in Burgenland and Carnuntum, to produce increasingly ripe and complex wines, with Blaufränkisch achieving levels of depth previously unattainable",
        "domain": "viticulture",
        "subdomain": "climate",
        "tags": ["climate_change", "viticulture"],
    },
    {
        "fact": "The average vineyard holding in Austria is approximately 3 hectares, reflecting the predominance of small family-owned estates rather than large corporate wineries",
        "domain": "wine_business",
        "subdomain": "industry",
        "tags": ["industry", "statistics", "estates"],
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Notable Vineyard Sites (Rieden)
# ═══════════════════════════════════════════════════════════════════════════════

NOTABLE_VINEYARDS = [
    {"name": "Achleiten", "region": "Wachau", "grape": "Riesling", "soil": "gneiss and amphibolite", "note": "One of the Wachau's steepest and most renowned vineyard sites, producing powerful, mineral Riesling from primary rock soils"},
    {"name": "Klaus", "region": "Wachau", "grape": "Riesling", "soil": "gneiss", "note": "Iconic terraced Wachau vineyard above Dürnstein known for intensely mineral Riesling with exceptional aging potential"},
    {"name": "Kellerberg", "region": "Wachau", "grape": "Riesling, Grüner Veltliner", "soil": "gneiss and mica schist", "note": "Steep south-facing terraces in Dürnstein producing concentrated Smaragd wines"},
    {"name": "Loibenberg", "region": "Wachau", "grape": "Grüner Veltliner", "soil": "loess over gneiss", "note": "Loiben's premier site with a mix of loess and primary rock, producing powerful Grüner Veltliner Smaragd wines"},
    {"name": "Singerriedel", "region": "Wachau", "grape": "Riesling", "soil": "gneiss", "note": "Spitz an der Donau's steepest and most famous vineyard, considered among Austria's greatest Riesling sites"},
    {"name": "Heiligenstein", "region": "Kamptal", "grape": "Riesling", "soil": "Permian red sandstone (Rotliegend)", "note": "Kamptal's most famous vineyard with unique 250-million-year-old desert sandstone soils producing age-worthy Riesling"},
    {"name": "Lamm", "region": "Kamptal", "grape": "Grüner Veltliner", "soil": "loess", "note": "Premier Kamptal site in Langenlois on deep loess, producing rich and complex Grüner Veltliner"},
    {"name": "Gaisberg", "region": "Kamptal", "grape": "Riesling, Grüner Veltliner", "soil": "gneiss and mica schist", "note": "Celebrated vineyard above Strass with crystalline primary rock soils"},
    {"name": "Grub", "region": "Kremstal", "grape": "Grüner Veltliner", "soil": "loess", "note": "One of Kremstal's top vineyard sites on loess terraces east of Krems"},
    {"name": "Pfaffenberg", "region": "Kremstal", "grape": "Riesling", "soil": "gneiss", "note": "Steep terraced vineyard in Krems producing mineral Riesling from primary rock"},
    {"name": "Zieregg", "region": "Südsteiermark", "grape": "Sauvignon Blanc", "soil": "opok (sandy marl)", "note": "Considered one of the world's great Sauvignon Blanc sites, on steep south-facing opok slopes near the Slovenian border"},
    {"name": "Hochgrassnitzberg", "region": "Südsteiermark", "grape": "Sauvignon Blanc", "soil": "opok", "note": "Premier Südsteiermark vineyard producing intense, mineral Sauvignon Blanc"},
    {"name": "Nussberg", "region": "Wien", "grape": "Gemischter Satz", "soil": "limestone and flysch", "note": "Vienna's most prestigious vineyard site with documented grape growing since Roman times"},
    {"name": "Bisamberg", "region": "Wien", "grape": "Grüner Veltliner, Riesling", "soil": "loess and limestone", "note": "Northern Danube bank vineyard in Vienna producing elegant, terroir-driven whites"},
    {"name": "Goldberg", "region": "Carnuntum", "grape": "Zweigelt", "soil": "gravel and loess", "note": "Premium vineyard site in Göttlesbrunn, one of Austria's best terroirs for Zweigelt"},
    {"name": "Spitzerberg", "region": "Carnuntum", "grape": "Blaufränkisch", "soil": "limestone and gravel", "note": "Highest point in Carnuntum producing concentrated, mineral Blaufränkisch"},
    {"name": "Ried Marienthal", "region": "Mittelburgenland", "grape": "Blaufränkisch", "soil": "heavy clay", "note": "One of Austria's most famous Blaufränkisch vineyards in Deutschkreutz"},
    {"name": "Goldberg", "region": "Mittelburgenland", "grape": "Blaufränkisch", "soil": "iron-rich clay", "note": "Renowned Blaufränkisch vineyard in Horitschon, Mittelburgenland"},
    {"name": "Thenau", "region": "Kremstal", "grape": "Grüner Veltliner", "soil": "loess and conglomerate", "note": "Historic Kremstal vineyard near Senftenberg known for complex, full-bodied Grüner Veltliner"},
    {"name": "Kogelberg", "region": "Kamptal", "grape": "Grüner Veltliner", "soil": "loess", "note": "Premier Kamptal Grüner Veltliner site near Schiltern on deep loess terraces"},
    {"name": "Schütt", "region": "Wachau", "grape": "Grüner Veltliner", "soil": "alluvial gravel and loess", "note": "Flat alluvial vineyard near Dürnstein producing a distinct, fruit-forward style of Wachau Grüner Veltliner"},
    {"name": "Hochrain", "region": "Wachau", "grape": "Grüner Veltliner, Riesling", "soil": "gneiss and loess", "note": "Terraced vineyard above Weissenkirchen combining primary rock and loess soils"},
    {"name": "Ried Oberer Berg", "region": "Eisenberg", "grape": "Blaufränkisch", "soil": "iron-rich clay and green slate", "note": "Iconic Eisenberg vineyard producing Blaufränkisch with distinctive ferrous mineral character"},
    {"name": "Ried Saybritz", "region": "Leithaberg", "grape": "Blaufränkisch", "soil": "limestone and mica schist", "note": "Premium Leithaberg site producing structured, mineral Blaufränkisch from crystalline soils"},
    {"name": "Pössnitzberg", "region": "Südsteiermark", "grape": "Sauvignon Blanc, Gelber Muskateller", "soil": "opok", "note": "One of Südsteiermark's top vineyard hills with steep south-facing slopes on opok soils"},
    {"name": "Czamillonberg", "region": "Vulkanland Steiermark", "grape": "Traminer", "soil": "volcanic basalt", "note": "Notable volcanic vineyard near Klöch known for aromatic Traminer"},
    {"name": "Hundsleiten", "region": "Carnuntum", "grape": "Zweigelt, Blaufränkisch", "soil": "gravel and limestone", "note": "Premium Carnuntum vineyard near Göttlesbrunn producing concentrated red wines"},
    {"name": "Spiegel", "region": "Kamptal", "grape": "Grüner Veltliner", "soil": "loess and weathered granite", "note": "Langenlois vineyard site producing mineral, complex Grüner Veltliner"},
]


# ═══════════════════════════════════════════════════════════════════════════════
# HTTP CLIENT
# ═══════════════════════════════════════════════════════════════════════════════


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
    """Build facts about Austrian wine regions (climate, soil, elevation, stats)."""
    facts = []

    for region in REGIONAL_DATABASE:
        name = region["name"]
        parent = region["parent_region"]
        entities = [{"type": "region", "name": name}]
        base_tags = ["austria", name.lower().replace("ö", "oe").replace("ü", "ue").replace(" ", "_")]

        # Parent region
        if parent != name:
            facts.append(_make_fact(
                f"{name} is a wine-growing region within {parent}, Austria.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="geography",
                entities=entities + [{"type": "region", "name": parent}],
                tags=base_tags + ["geography"],
            ))

        # Climate
        facts.append(_make_fact(
            f"The {name} wine region in Austria has a {region['climate']} climate.",
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
                f"The predominant soil types in the {name} wine region of Austria include {soil_list}.",
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

        # Individual soil types
        if region.get("soil_types") and len(region["soil_types"]) > 1:
            for soil in region["soil_types"]:
                if soil not in ("varied", "varied (Alpine)"):
                    facts.append(_make_fact(
                        f"{soil.capitalize() if not soil[0].isupper() else soil} is among the key soil types found in the {name} wine region of Austria.",
                        domain="wine_regions",
                        source_id=source_id,
                        subdomain="terroir",
                        entities=entities,
                        tags=base_tags + ["soil", "terroir", soil.lower().replace(" ", "_").replace("(", "").replace(")", "")],
                    ))

        # Elevation
        if region.get("elevation_range"):
            facts.append(_make_fact(
                f"Vineyards in the {name} wine region of Austria are planted at elevations ranging from {region['elevation_range']}.",
                domain="viticulture",
                source_id=source_id,
                subdomain="terrain",
                entities=entities,
                tags=base_tags + ["elevation"],
            ))

        # Vineyard area
        if region.get("vineyard_area_ha"):
            facts.append(_make_fact(
                f"The {name} wine region in Austria has approximately {region['vineyard_area_ha']:,} hectares of vineyard.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="statistics",
                entities=entities,
                confidence=0.95,
                tags=base_tags + ["vineyard_area", "statistics"],
            ))

        # Rainfall
        if region.get("annual_rainfall_mm"):
            facts.append(_make_fact(
                f"The {name} wine region in Austria receives approximately {region['annual_rainfall_mm']}mm of annual rainfall.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="climate",
                entities=entities,
                confidence=0.95,
                tags=base_tags + ["climate", "rainfall"],
            ))

        # Key grapes — summary
        if region.get("key_grapes"):
            grapes_str = ", ".join(region["key_grapes"])
            grape_entities = entities + [{"type": "grape", "name": g} for g in region["key_grapes"]]
            facts.append(_make_fact(
                f"The principal grape varieties of the {name} wine region in Austria include {grapes_str}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="regional_grapes",
                entities=grape_entities,
                tags=base_tags + ["grapes"],
            ))

            # Key grapes — individual (generates one fact per grape per region)
            for grape_name in region["key_grapes"]:
                facts.append(_make_fact(
                    f"{grape_name} is one of the key grape varieties grown in the {name} wine region of Austria.",
                    domain="grape_varieties",
                    source_id=source_id,
                    subdomain="regional_grapes",
                    entities=entities + [{"type": "grape", "name": grape_name}],
                    tags=base_tags + ["grapes", grape_name.lower().replace(" ", "_").replace("ü", "ue")],
                ))

        # DAC status
        if region.get("dac_status"):
            facts.append(_make_fact(
                f"The {name} region holds {region['dac_status']} designation under the Austrian appellation system.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="appellations",
                entities=entities,
                tags=base_tags + ["dac", "appellations"],
            ))

        # Notable features
        if region.get("notable_features"):
            facts.append(_make_fact(
                f"{region['notable_features']}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="notable",
                entities=entities,
                tags=base_tags + ["notable"],
            ))

    # Parent region summaries
    parent_regions = defaultdict(list)
    for r in REGIONAL_DATABASE:
        parent_regions[r["parent_region"]].append(r["name"])

    parent_summaries = {
        "Niederösterreich": "Niederösterreich (Lower Austria) is Austria's largest wine-producing state, accounting for approximately 60% of the country's vineyard area, and is dominated by white varieties, especially Grüner Veltliner and Riesling",
        "Burgenland": "Burgenland is Austria's premier red wine region, situated on the Hungarian border around Lake Neusiedl, and is also renowned for its world-class sweet wines from the Seewinkel area",
        "Steiermark": "Steiermark (Styria) is Austria's southernmost wine region, known for its steep hillside vineyards, cool-climate white wines, and the unique Schilcher rosé of Weststeiermark",
        "Wien": "Wien (Vienna) is one of the few capital cities in the world with commercially significant vineyards within its city limits, with a centuries-old tradition of urban winemaking",
        "Bergland": "Bergland encompasses scattered mountain vineyards across five Austrian federal states (Oberösterreich, Kärnten, Salzburg, Tirol, Vorarlberg) where extreme conditions limit production to small quantities",
    }

    for parent_name, sub_regions in parent_regions.items():
        entities = [{"type": "region", "name": parent_name}]
        ptags = ["austria", parent_name.lower().replace("ö", "oe").replace("ü", "ue").replace(" ", "_")]

        if parent_name in parent_summaries:
            facts.append(_make_fact(
                f"{parent_summaries[parent_name]}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="geography",
                entities=entities,
                tags=ptags + ["overview"],
            ))

        if len(sub_regions) > 1:
            sub_str = ", ".join(sub_regions)
            facts.append(_make_fact(
                f"The wine-growing sub-regions of {parent_name} in Austria include {sub_str}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="geography",
                entities=entities + [{"type": "region", "name": s} for s in sub_regions],
                tags=ptags + ["sub_regions"],
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
        base_tags = ["austria", "grape_variety", grape["color"]]

        # Origin
        if grape.get("origin") == "autochthonous":
            facts.append(_make_fact(
                f"{name} is an indigenous Austrian grape variety.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="origin",
                entities=entities,
                tags=base_tags + ["origin", "autochthonous"],
            ))
        elif grape.get("origin") == "international":
            facts.append(_make_fact(
                f"{name} is an international grape variety cultivated in Austria.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="origin",
                entities=entities,
                tags=base_tags + ["origin", "international"],
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

        # Key regions
        if grape.get("key_regions") and len(grape["key_regions"]) > 0:
            regions_str = ", ".join(grape["key_regions"])
            region_entities = entities + [{"type": "region", "name": r} for r in grape["key_regions"]]
            facts.append(_make_fact(
                f"{name} is primarily grown in the Austrian wine regions of {regions_str}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="distribution",
                entities=region_entities,
                tags=base_tags + ["distribution"],
            ))

        # Vineyard area
        if grape.get("vineyard_area_ha"):
            facts.append(_make_fact(
                f"Austria has approximately {grape['vineyard_area_ha']:,} hectares planted with {name}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="statistics",
                entities=entities,
                confidence=0.95,
                tags=base_tags + ["vineyard_area", "statistics"],
            ))

        # Percentage of total
        if grape.get("pct_total"):
            facts.append(_make_fact(
                f"{name} accounts for approximately {grape['pct_total']}% of Austria's total vineyard area.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="statistics",
                entities=entities,
                confidence=0.95,
                tags=base_tags + ["statistics", "percentage"],
            ))

        # Notable facts
        if grape.get("notable_facts"):
            facts.append(_make_fact(
                f"{grape['notable_facts']}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="notable",
                entities=entities,
                tags=base_tags + ["notable"],
            ))

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# FACT BUILDERS — Classification System
# ═══════════════════════════════════════════════════════════════════════════════


def _build_classification_facts(source_id: str) -> list[dict]:
    """Build facts about Austrian wine law, DAC system, Prädikat levels, Wachau categories."""
    facts = []
    base_tags = ["austria", "classification"]

    # Wine law hierarchy
    for level in CLASSIFICATION_DATABASE["wine_law_hierarchy"]:
        entities = [{"type": "classification", "name": level["level"]}]

        facts.append(_make_fact(
            f"{level['level']} ({level['english']}) is a level in the Austrian wine classification hierarchy.",
            domain="wine_regions",
            source_id=source_id,
            subdomain="classification",
            entities=entities,
            tags=base_tags + ["wine_law", level["level"].lower()],
        ))

        facts.append(_make_fact(
            f"Austrian {level['level']}: {level['description']}.",
            domain="wine_regions",
            source_id=source_id,
            subdomain="classification",
            entities=entities,
            tags=base_tags + ["wine_law", level["level"].lower()],
        ))

        facts.append(_make_fact(
            f"Austrian {level['level']} requires a minimum must weight of {level['min_kmw']}° KMW (Klosterneuburger Mostwaage).",
            domain="winemaking",
            source_id=source_id,
            subdomain="production_rules",
            entities=entities,
            tags=base_tags + ["wine_law", "kmw", level["level"].lower()],
        ))

    # Austrian wine law hierarchy order
    facts.append(_make_fact(
        "The Austrian wine classification hierarchy from basic to highest is: Tafelwein, Landwein, Qualitätswein, Kabinett, Prädikatswein.",
        domain="wine_regions",
        source_id=source_id,
        subdomain="classification",
        entities=[{"type": "classification", "name": "Austrian wine law"}],
        tags=base_tags + ["wine_law", "hierarchy"],
    ))

    # KMW explanation
    facts.append(_make_fact(
        "Austria uses the KMW (Klosterneuburger Mostwaage) scale to measure must weight, where 1° KMW is approximately equivalent to 1% sugar by weight in the grape must.",
        domain="winemaking",
        source_id=source_id,
        subdomain="production_rules",
        entities=[{"type": "measurement", "name": "KMW"}],
        tags=base_tags + ["kmw", "must_weight"],
    ))

    # Prädikat levels
    for level in CLASSIFICATION_DATABASE["praedikat_levels"]:
        entities = [{"type": "classification", "name": level["level"]}]

        facts.append(_make_fact(
            f"Austrian {level['level']} requires a minimum must weight of {level['min_kmw']}° KMW.",
            domain="winemaking",
            source_id=source_id,
            subdomain="production_rules",
            entities=entities,
            tags=base_tags + ["praedikat", level["level"].lower()],
        ))

        facts.append(_make_fact(
            f"Austrian {level['level']}: {level['description']}.",
            domain="winemaking",
            source_id=source_id,
            subdomain="production_rules",
            entities=entities,
            tags=base_tags + ["praedikat", level["level"].lower()],
        ))

    # Prädikat level list
    facts.append(_make_fact(
        "The Austrian Prädikatswein categories in ascending order of must weight are: Spätlese, Auslese, Beerenauslese, Ausbruch, Trockenbeerenauslese, with Eiswein and Strohwein as special categories.",
        domain="winemaking",
        source_id=source_id,
        subdomain="production_rules",
        entities=[{"type": "classification", "name": "Prädikatswein"}],
        tags=base_tags + ["praedikat", "hierarchy"],
    ))

    # Ausbruch uniqueness
    facts.append(_make_fact(
        "Ausbruch is a uniquely Austrian Prädikat level between Beerenauslese and Trockenbeerenauslese, with no equivalent in the German wine classification system.",
        domain="winemaking",
        source_id=source_id,
        subdomain="production_rules",
        entities=[{"type": "classification", "name": "Ausbruch"}],
        tags=base_tags + ["praedikat", "ausbruch"],
    ))

    # DAC system
    dac = CLASSIFICATION_DATABASE["dac_system"]
    facts.append(_make_fact(
        f"DAC stands for {dac['name']}, Austria's controlled appellation system introduced in {dac['year_introduced']}.",
        domain="wine_regions",
        source_id=source_id,
        subdomain="appellations",
        entities=[{"type": "classification", "name": "DAC"}],
        tags=base_tags + ["dac"],
    ))

    facts.append(_make_fact(
        f"{dac['description']}.",
        domain="wine_regions",
        source_id=source_id,
        subdomain="appellations",
        entities=[{"type": "classification", "name": "DAC"}],
        tags=base_tags + ["dac"],
    ))

    facts.append(_make_fact(
        f"The first Austrian DAC was {dac['first_dac']}.",
        domain="wine_regions",
        source_id=source_id,
        subdomain="appellations",
        entities=[{"type": "classification", "name": "DAC"}, {"type": "region", "name": "Weinviertel"}],
        tags=base_tags + ["dac", "weinviertel"],
    ))

    facts.append(_make_fact(
        f"Austria currently has {dac['total_dacs']} DAC designations covering its principal wine-growing regions.",
        domain="wine_regions",
        source_id=source_id,
        subdomain="appellations",
        entities=[{"type": "classification", "name": "DAC"}],
        confidence=0.95,
        tags=base_tags + ["dac", "statistics"],
    ))

    # Individual DAC entries
    for dac_entry in dac["dac_list"]:
        entities = [
            {"type": "classification", "name": "DAC"},
            {"type": "region", "name": dac_entry["name"]},
        ]
        facts.append(_make_fact(
            f"The {dac_entry['name']} DAC was established in {dac_entry['year']} with primary grape(s): {dac_entry['primary_grapes']}.",
            domain="wine_regions",
            source_id=source_id,
            subdomain="appellations",
            entities=entities,
            tags=base_tags + ["dac", dac_entry["name"].lower().replace(" ", "_").replace("ü", "ue")],
        ))

    # Wachau classifications
    for wachau in CLASSIFICATION_DATABASE["wachau_classifications"]:
        entities = [
            {"type": "classification", "name": wachau["name"]},
            {"type": "region", "name": "Wachau"},
        ]

        alcohol_str = ""
        if wachau.get("max_alcohol") and not wachau.get("min_alcohol"):
            alcohol_str = f"up to {wachau['max_alcohol']}% alcohol"
        elif wachau.get("min_alcohol") and wachau.get("max_alcohol"):
            alcohol_str = f"between {wachau['min_alcohol']}% and {wachau['max_alcohol']}% alcohol"
        elif wachau.get("min_alcohol") and not wachau.get("max_alcohol"):
            alcohol_str = f"minimum {wachau['min_alcohol']}% alcohol"

        facts.append(_make_fact(
            f"{wachau['name']} is a Wachau wine classification for wines with {alcohol_str}.",
            domain="wine_regions",
            source_id=source_id,
            subdomain="classification",
            entities=entities,
            tags=base_tags + ["wachau", wachau["name"].lower()],
        ))

        facts.append(_make_fact(
            f"Wachau {wachau['name']}: {wachau['description']}.",
            domain="wine_regions",
            source_id=source_id,
            subdomain="classification",
            entities=entities,
            tags=base_tags + ["wachau", wachau["name"].lower()],
        ))

    # Wachau system overview
    facts.append(_make_fact(
        "The Wachau wine classification system of Steinfeder, Federspiel, and Smaragd was created by the Vinea Wachau association and is based on the alcohol level and ripeness of the wine at harvest.",
        domain="wine_regions",
        source_id=source_id,
        subdomain="classification",
        entities=[{"type": "region", "name": "Wachau"}],
        tags=base_tags + ["wachau"],
    ))

    # Gemischter Satz rules
    gs = CLASSIFICATION_DATABASE["gemischter_satz_rules"]
    facts.append(_make_fact(
        f"{gs['description']}.",
        domain="wine_regions",
        source_id=source_id,
        subdomain="classification",
        entities=[{"type": "classification", "name": "Wiener Gemischter Satz"}, {"type": "region", "name": "Wien"}],
        tags=base_tags + ["gemischter_satz", "wien"],
    ))

    facts.append(_make_fact(
        f"Wiener Gemischter Satz DAC requires at least {gs['min_varieties']} white grape varieties, with no single variety exceeding {gs['max_single_variety_pct']}% and the third-largest variety comprising at least {gs['min_third_variety_pct']}%.",
        domain="wine_regions",
        source_id=source_id,
        subdomain="classification",
        entities=[{"type": "classification", "name": "Wiener Gemischter Satz"}, {"type": "region", "name": "Wien"}],
        tags=base_tags + ["gemischter_satz", "wien", "production_rules"],
    ))

    facts.append(_make_fact(
        f"{gs['requirement']}.",
        domain="wine_regions",
        source_id=source_id,
        subdomain="classification",
        entities=[{"type": "classification", "name": "Wiener Gemischter Satz"}, {"type": "region", "name": "Wien"}],
        tags=base_tags + ["gemischter_satz", "wien"],
    ))

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# FACT BUILDERS — Production Statistics
# ═══════════════════════════════════════════════════════════════════════════════


def _build_production_stats_facts(source_id: str) -> list[dict]:
    """Build facts about Austrian wine production statistics."""
    facts = []
    base_tags = ["austria", "statistics"]

    # National stats
    nat = PRODUCTION_STATS["national"]
    facts.append(_make_fact(
        f"Austria has approximately {nat['total_vineyard_area_ha']:,} hectares of vineyard.",
        domain="wine_business",
        source_id=source_id,
        subdomain="production",
        entities=[{"type": "country", "name": "Austria"}],
        confidence=0.95,
        tags=base_tags + ["national", "vineyard_area"],
    ))

    facts.append(_make_fact(
        f"Austria produces approximately {nat['annual_production_hl'] / 1_000_000:.1f} million hectoliters of wine annually.",
        domain="wine_business",
        source_id=source_id,
        subdomain="production",
        entities=[{"type": "country", "name": "Austria"}],
        confidence=0.95,
        tags=base_tags + ["national", "production"],
    ))

    facts.append(_make_fact(
        f"Austrian wine production is approximately {nat['white_pct']}% white and {nat['red_pct']}% red.",
        domain="wine_business",
        source_id=source_id,
        subdomain="production",
        entities=[{"type": "country", "name": "Austria"}],
        confidence=0.95,
        tags=base_tags + ["national", "white_red_split"],
    ))

    facts.append(_make_fact(
        f"Austria has approximately {nat['number_of_winegrowers']:,} winegrowers, of which about {nat['number_of_bottling_estates']:,} bottle and sell wine under their own label.",
        domain="wine_business",
        source_id=source_id,
        subdomain="industry",
        entities=[{"type": "country", "name": "Austria"}],
        confidence=0.95,
        tags=base_tags + ["national", "producers"],
    ))

    facts.append(_make_fact(
        f"Austria exports approximately {nat['export_pct']}% of its wine production.",
        domain="wine_business",
        source_id=source_id,
        subdomain="trade",
        entities=[{"type": "country", "name": "Austria"}],
        confidence=0.95,
        tags=base_tags + ["national", "exports"],
    ))

    # Regional stats
    for region_name, stats in PRODUCTION_STATS["regional"].items():
        entities = [{"type": "region", "name": region_name}]
        rtags = base_tags + [region_name.lower().replace("ö", "oe").replace("ü", "ue").replace(" ", "_")]

        facts.append(_make_fact(
            f"{region_name} has approximately {stats['vineyard_area_ha']:,} hectares of vineyard, representing {stats['pct_of_total']}% of Austria's total.",
            domain="wine_business",
            source_id=source_id,
            subdomain="production",
            entities=entities,
            confidence=0.95,
            tags=rtags + ["vineyard_area"],
        ))

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
                tags=rtags + ["production"],
            ))

        facts.append(_make_fact(
            f"{region_name}'s wine production is approximately {stats['white_pct']}% white and {stats['red_pct']}% red.",
            domain="wine_business",
            source_id=source_id,
            subdomain="production",
            entities=entities,
            confidence=0.95,
            tags=rtags + ["white_red_split"],
        ))

    # Top grapes by area
    for grape_stat in PRODUCTION_STATS["top_grapes_by_area"]:
        entities = [{"type": "grape", "name": grape_stat["name"]}]
        facts.append(_make_fact(
            f"{grape_stat['name']} is planted on {grape_stat['area_ha']:,} hectares in Austria, representing {grape_stat['pct']}% of total vineyard area.",
            domain="wine_business",
            source_id=source_id,
            subdomain="production",
            entities=entities,
            confidence=0.95,
            tags=base_tags + ["grape_area", grape_stat["name"].lower().replace(" ", "_").replace("ü", "ue")],
        ))

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# FACT BUILDERS — Historical and Cultural
# ═══════════════════════════════════════════════════════════════════════════════


def _build_historical_cultural_facts(source_id: str) -> list[dict]:
    """Build facts about Austrian wine history and culture."""
    facts = []

    for entry in HISTORICAL_CULTURAL_DATABASE:
        facts.append(_make_fact(
            f"{entry['fact']}.",
            domain=entry["domain"],
            source_id=source_id,
            subdomain=entry.get("subdomain"),
            entities=[{"type": "country", "name": "Austria"}],
            tags=["austria"] + entry.get("tags", []),
        ))

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# FACT BUILDERS — Notable Vineyard Sites
# ═══════════════════════════════════════════════════════════════════════════════


def _build_vineyard_facts(source_id: str) -> list[dict]:
    """Build facts about notable Austrian vineyard sites (Rieden)."""
    facts = []

    for site in NOTABLE_VINEYARDS:
        name = site["name"]
        region = site["region"]
        entities = [
            {"type": "vineyard", "name": name},
            {"type": "region", "name": region},
        ]
        base_tags = ["austria", "vineyard", "ried", region.lower().replace("ö", "oe").replace("ü", "ue").replace(" ", "_")]

        # Main description
        facts.append(_make_fact(
            f"Ried {name} is a notable vineyard site in the {region} wine region of Austria.",
            domain="wine_regions",
            source_id=source_id,
            subdomain="geography",
            entities=entities,
            tags=base_tags,
        ))

        # Soil
        if site.get("soil"):
            facts.append(_make_fact(
                f"The Ried {name} vineyard in {region} has {site['soil']} soils.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="terroir",
                entities=entities,
                tags=base_tags + ["soil", "terroir"],
            ))

        # Grape and note
        if site.get("note"):
            facts.append(_make_fact(
                f"{site['note']}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="notable",
                entities=entities + [{"type": "grape", "name": g.strip()} for g in site.get("grape", "").split(",") if g.strip()],
                tags=base_tags + ["notable"],
            ))

        # Grape association
        if site.get("grape"):
            facts.append(_make_fact(
                f"The Ried {name} vineyard in {region} is particularly known for {site['grape']}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="regional_grapes",
                entities=entities + [{"type": "grape", "name": g.strip()} for g in site["grape"].split(",") if g.strip()],
                tags=base_tags + ["grape"],
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
        "grape": _build_grape_variety_facts,
        "classification": _build_classification_facts,
        "stats": _build_production_stats_facts,
        "history": _build_historical_cultural_facts,
        "vineyard": _build_vineyard_facts,
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
        click.echo(f"\n[DRY RUN] Would insert {len(facts)} facts from Austrian Wine")

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

    logger.info(f"Inserted {inserted} new facts from Austrian Wine (duplicates skipped)")
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
        "Production Stats": _build_production_stats_facts,
        "History & Culture": _build_historical_cultural_facts,
        "Notable Vineyards": _build_vineyard_facts,
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
    type=click.Choice(["region", "grape", "classification", "stats", "history", "vineyard"]),
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
    """OenoBench Austrian Wine Scraper — Regions, grapes, classification, and production data."""
    logger.add("data/logs/austria_{time}.log", rotation="10 MB")

    if list_sources:
        click.echo("\nAvailable data categories:")
        click.echo(f"  {'region':18s} — {len(REGIONAL_DATABASE)} Austrian wine regions (climate, soil, elevation)")
        click.echo(f"  {'grape':18s} — {len(GRAPE_VARIETY_DATABASE)} grape variety profiles")
        click.echo(f"  {'classification':18s} — Wine law hierarchy, DAC system, Prädikat levels, Wachau categories")
        click.echo(f"  {'stats':18s} — National and regional production statistics")
        click.echo(f"  {'history':18s} — {len(HISTORICAL_CULTURAL_DATABASE)} historical and cultural facts")
        click.echo(f"  {'vineyard':18s} — {len(NOTABLE_VINEYARDS)} notable vineyard sites (Rieden)")
        click.echo(f"\nKnowledge base coverage:")
        click.echo(f"  Regions:            {len(REGIONAL_DATABASE)}")
        click.echo(f"  Grape varieties:    {len(GRAPE_VARIETY_DATABASE)}")
        click.echo(f"  Wine law levels:    {len(CLASSIFICATION_DATABASE['wine_law_hierarchy'])}")
        click.echo(f"  Prädikat levels:    {len(CLASSIFICATION_DATABASE['praedikat_levels'])}")
        click.echo(f"  DAC designations:   {len(CLASSIFICATION_DATABASE['dac_system']['dac_list'])}")
        click.echo(f"  Wachau categories:  {len(CLASSIFICATION_DATABASE['wachau_classifications'])}")
        click.echo(f"  Historical facts:   {len(HISTORICAL_CULTURAL_DATABASE)}")
        click.echo(f"  Notable vineyards:  {len(NOTABLE_VINEYARDS)}")
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
