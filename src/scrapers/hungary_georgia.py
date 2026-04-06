"""
OenoBench — Hungary & Georgia Wine Scraper

Extracts structured wine data for Hungary and Georgia — two of the world's
most historically significant wine nations. Hungary is home to Tokaj (first
legally delimited wine region, 1737) and Georgia is the cradle of winemaking
with 8,000 years of continuous viticulture and UNESCO-recognised qvevri
winemaking.

Focus areas: wine regions, Tokaj classification, Georgian qvevri winemaking,
grape varieties, appellation systems, and amber/orange wine traditions.

Usage:
    python -m src.scrapers.hungary_georgia --all
    python -m src.scrapers.hungary_georgia --type hungary
    python -m src.scrapers.hungary_georgia --type tokaj
    python -m src.scrapers.hungary_georgia --type georgia
    python -m src.scrapers.hungary_georgia --type qvevri
    python -m src.scrapers.hungary_georgia --type grape
    python -m src.scrapers.hungary_georgia --type classification
    python -m src.scrapers.hungary_georgia --dry-run
    python -m src.scrapers.hungary_georgia --validate
    python -m src.scrapers.hungary_georgia --test-run
    python -m src.scrapers.hungary_georgia --list
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
    "name": "Hungary & Georgia Wine Reference Database",
    "url": "https://www.winesofhungary.com",
    "source_type": "reference",
    "tier": "tier_2_authoritative",
    "language": "en",
}


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Hungarian Wine Regions
# ═══════════════════════════════════════════════════════════════════════════════

HUNGARY_REGIONS = [
    {
        "name": "Tokaj",
        "hungarian_name": "Tokaji",
        "climate": "continental with Bodrog and Tisza river confluence creating botrytis-friendly microclimate",
        "soil_types": ["volcanic rhyolite", "andesite", "loess", "clay"],
        "soil_details": "Volcanic bedrock of rhyolite and andesite overlaid with loess and clay; the volcanic soils contribute distinctive minerality to Tokaj wines",
        "elevation_range": "100-400m",
        "vineyard_area_ha": 5500,
        "key_grapes": ["Furmint", "Hárslevelű", "Sárgamuskotály"],
        "wine_styles": ["botrytized sweet (Aszú)", "dry Furmint", "Szamorodni", "Eszencia"],
        "notes": "First legally delimited wine region in the world (1737), predating Douro (1756) and Chianti (1716). Known as 'Wine of Kings, King of Wines' (Louis XIV). 27 classified first-growth vineyards.",
    },
    {
        "name": "Eger",
        "hungarian_name": "Egri",
        "climate": "continental",
        "soil_types": ["volcanic tufo", "rhyolite", "limestone"],
        "soil_details": "Volcanic tufo and rhyolite bedrock with limestone intrusions; the Bükk Mountains provide shelter from northern winds",
        "elevation_range": "150-500m",
        "vineyard_area_ha": 5000,
        "key_grapes": ["Kadarka", "Kékfrankos", "Blauburger", "Leányka", "Olaszrizling"],
        "wine_styles": ["Egri Bikavér (Bull's Blood)", "Egri Csillag (white star blend)"],
        "notes": "Egri Bikavér (Bull's Blood of Eger) is Hungary's most famous red blend. Egri Csillag is a white blend created to provide a white counterpart to Bikavér.",
    },
    {
        "name": "Villány",
        "hungarian_name": "Villányi",
        "climate": "warmest in Hungary with Mediterranean influence",
        "soil_types": ["loess", "limestone"],
        "soil_details": "Loess over limestone bedrock on south-facing slopes of the Villány Mountains; the warmest wine region in Hungary",
        "elevation_range": "100-400m",
        "vineyard_area_ha": 2400,
        "key_grapes": ["Cabernet Franc", "Cabernet Sauvignon", "Merlot", "Portugieser"],
        "wine_styles": ["full-bodied reds", "Bordeaux-style blends", "Cabernet Franc varietal"],
        "notes": "Villány operates a classified vineyard system with four tiers: village wine (Classicus), premium, super premium, and grand superior (Grand).",
    },
    {
        "name": "Szekszárd",
        "hungarian_name": "Szekszárdi",
        "climate": "warm continental",
        "soil_types": ["loess"],
        "soil_details": "Deep loess soils on rolling hills provide excellent drainage and heat retention; warm microclimate favours full-bodied reds",
        "elevation_range": "100-300m",
        "vineyard_area_ha": 2200,
        "key_grapes": ["Kadarka", "Kékfrankos", "Merlot", "Cabernet Sauvignon"],
        "wine_styles": ["Bikavér (Bull's Blood)", "Kadarka varietal", "red blends"],
        "notes": "Along with Eger, Szekszárd is one of only two Hungarian regions permitted to produce Bikavér (Bull's Blood).",
    },
    {
        "name": "Somló",
        "hungarian_name": "Somlói",
        "climate": "continental",
        "soil_types": ["basalt", "volcanic tuff"],
        "soil_details": "A single extinct volcanic hill with a basalt cap over volcanic tuff; one of the most geologically distinctive wine sites in Europe",
        "elevation_range": "150-400m",
        "vineyard_area_ha": 500,
        "key_grapes": ["Juhfark", "Olaszrizling", "Hárslevelű"],
        "wine_styles": ["mineral austere whites", "oxidative aged whites"],
        "notes": "Somló wine was traditionally drunk on the wedding night in the Austro-Hungarian Empire, believed to help produce male heirs. One of Hungary's smallest but most distinctive wine regions.",
    },
    {
        "name": "Badacsony",
        "hungarian_name": "Badacsonyi",
        "climate": "continental moderated by Lake Balaton",
        "soil_types": ["basalt", "volcanic"],
        "soil_details": "Basalt-capped volcanic hills rising above the northern shore of Lake Balaton; the dark basalt retains heat and the lake moderates temperature extremes",
        "elevation_range": "100-400m",
        "vineyard_area_ha": 1500,
        "key_grapes": ["Olaszrizling", "Szürkebarát", "Kéknyelű"],
        "wine_styles": ["aromatic whites", "full-bodied Olaszrizling", "rare Kéknyelű"],
        "notes": "Szürkebarát is the Hungarian name for Pinot Gris. Kéknyelű (meaning 'blue stem') is one of the rarest grape varieties in the world, with only about 20 hectares planted.",
    },
    {
        "name": "Balaton",
        "hungarian_name": "Balatoni",
        "climate": "continental moderated by Lake Balaton",
        "soil_types": ["volcanic", "sandstone", "loess"],
        "soil_details": "Multiple sub-regions surrounding Lake Balaton with diverse soils; the lake creates a moderating influence on temperature, reducing frost risk and extending the growing season",
        "elevation_range": "100-400m",
        "vineyard_area_ha": 8000,
        "key_grapes": ["Olaszrizling", "Chardonnay", "Szürkebarát"],
        "wine_styles": ["fresh whites", "rosé"],
        "notes": "The Balaton wine region encompasses multiple sub-regions around Central Europe's largest lake, including Balatonfüred-Csopak, Balatonboglár, and others.",
    },
    {
        "name": "Etyek-Buda",
        "hungarian_name": "Etyek-Budai",
        "climate": "cool continental",
        "soil_types": ["limestone"],
        "soil_details": "Limestone-rich soils near Budapest; the cooler microclimate and calcareous soils are well suited to sparkling wine production",
        "elevation_range": "150-350m",
        "vineyard_area_ha": 1500,
        "key_grapes": ["Chardonnay", "Sauvignon Blanc", "Pinot Noir"],
        "wine_styles": ["sparkling wine (traditional method)", "fresh whites"],
        "notes": "Etyek-Buda is Hungary's centre for sparkling wine production, located near Budapest. Several major Hungarian sparkling wine houses are based here.",
    },
    {
        "name": "Sopron",
        "hungarian_name": "Soproni",
        "climate": "continental with Austrian/Pannonian influence",
        "soil_types": ["gneiss", "mica-schist", "loess"],
        "soil_details": "On the Austrian border, Sopron is a geological extension of the Leithaberg in Burgenland; crystalline bedrock of gneiss and mica-schist overlaid with loess",
        "elevation_range": "150-400m",
        "vineyard_area_ha": 1600,
        "key_grapes": ["Kékfrankos"],
        "wine_styles": ["varietal Kékfrankos", "light to medium reds"],
        "notes": "Sopron specialises in Kékfrankos (known as Blaufränkisch in neighbouring Austria). The region is geologically and stylistically linked to Austria's Burgenland.",
    },
    {
        "name": "Kunság",
        "hungarian_name": "Kunsági",
        "climate": "hot continental",
        "soil_types": ["sand", "alluvial"],
        "soil_details": "Sandy soils of the Great Hungarian Plain; the deep sand historically protected vines from phylloxera, preserving own-rooted vines",
        "elevation_range": "80-130m",
        "vineyard_area_ha": 25000,
        "key_grapes": ["Cserszegi Fűszeres", "Kékfrankos", "Kadarka"],
        "wine_styles": ["high-volume everyday wines", "varietal whites and reds"],
        "notes": "Hungary's largest wine region by area. Sandy soils provided natural phylloxera resistance, and some of Europe's oldest ungrafted vines survive here.",
    },
    {
        "name": "Neszmély",
        "hungarian_name": "Neszmélyi",
        "climate": "cool continental",
        "soil_types": ["limestone", "loess"],
        "soil_details": "Along the Danube River with limestone and loess soils; cool breezes from the Danube help preserve freshness and acidity in white wines",
        "elevation_range": "100-300m",
        "vineyard_area_ha": 1000,
        "key_grapes": ["Olaszrizling", "Irsai Olivér", "Chardonnay"],
        "wine_styles": ["fresh aromatic whites"],
        "notes": "Neszmély is known for fresh, aromatic white wines, benefiting from cooling Danube influence.",
    },
    {
        "name": "Pannonhalma",
        "hungarian_name": "Pannonhalmi",
        "climate": "continental",
        "soil_types": ["loess", "limestone"],
        "soil_details": "Loess and limestone soils around the historic Pannonhalma Archabbey; monastic winemaking tradition dating to the founding of the Benedictine abbey in 996 AD",
        "elevation_range": "150-300m",
        "vineyard_area_ha": 600,
        "key_grapes": ["Olaszrizling", "Rajnai Rizling", "Sauvignon Blanc"],
        "wine_styles": ["mineral whites", "aromatic blends"],
        "notes": "Pannonhalma has the oldest documented winemaking tradition in Hungary, with Benedictine monks producing wine since 996 AD. The Pannonhalma Archabbey is a UNESCO World Heritage Site.",
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Tokaj Detailed
# ═══════════════════════════════════════════════════════════════════════════════

TOKAJ_DATABASE = {
    "wine_styles": [
        {
            "name": "Aszú",
            "description": "Botrytized berries (aszú) are harvested individually by hand and macerated in base wine or must",
            "rs_min_gl": 120,
            "aging_months_oak": 18,
            "aging_months_bottle": 6,
            "notes": "The former puttonyos system graded Aszú from 3 to 6 puttonyos by residual sugar level. Since 2013, the minimum has been standardised at 120 g/L residual sugar, eliminating the puttonyos scale.",
        },
        {
            "name": "Szamorodni",
            "description": "Whole bunches harvested together ('as it comes' in Polish) including botrytized and healthy berries",
            "styles": ["Édes (sweet)", "Száraz (dry)"],
            "notes": "Szamorodni Édes (sweet) has some botrytis character but less concentrated than Aszú. Szamorodni Száraz (dry) is fermented to dryness and can have a sherry-like oxidative character.",
        },
        {
            "name": "Eszencia",
            "description": "Free-run juice from aszú berries that drains under their own weight, without pressing",
            "rs_range_gl": "450-900",
            "alcohol_range": "1-4%",
            "notes": "Tokaji Eszencia is the rarest and most concentrated wine in the world. With 450-900 g/L residual sugar, it can take years to ferment to just 1-4% alcohol. Historically served from a spoon rather than a glass.",
        },
        {
            "name": "Fordítás",
            "description": "Must poured over the aszú dough remaining from a previous Aszú pressing",
            "notes": "Fordítás ('turned over') is a traditional Tokaj wine style made by re-extracting flavour from the pressed aszú berries using fresh must.",
        },
        {
            "name": "Máslás",
            "description": "Must poured over the lees of a finished Aszú wine",
            "notes": "Máslás ('copy') extracts residual richness from Aszú lees, producing a wine with some botrytis character at a lower concentration than Aszú.",
        },
        {
            "name": "Late Harvest",
            "hungarian_name": "Késői szüretelésű",
            "description": "Late-harvested grapes with elevated sugar levels but not necessarily botrytized",
            "notes": "Tokaj Late Harvest wines bridge the gap between dry wines and the botrytized Aszú style.",
        },
    ],
    "first_growth_vineyards": [
        "Szarvas", "Mézes Mály", "Szent Tamás", "Betsek", "Nyulászó", "Király",
        "Úrágya", "Hétszőlő", "Lapis", "Disznókő", "Palota", "Szil-völgy",
        "Danczka", "Holdvölgy", "Zsadány", "Veresek", "Percze", "Kutpatka",
        "Hasznos", "Kerékhegy", "Magita", "Pajzos", "Kővágó", "Előhegy",
        "Bomboly", "Oremus", "Henye",
    ],
    "townships": ["Tokaj", "Tarcal", "Tállya", "Mád", "Bodrogkeresztúr", "Tolcsva"],
    "history": [
        "Tokaj was declared the first legally delimited wine region in the world by royal decree of King Charles III in 1737.",
        "Louis XIV of France called Tokaji wine the 'Wine of Kings, King of Wines' (Vinum Regum, Rex Vinorum).",
        "The classification of Tokaj's vineyards in 1700 predates the Bordeaux 1855 Classification by 155 years.",
        "Tokaj has 27 classified first-growth vineyards (Első Osztályú Dűlő), established in the vineyard classification of 1700.",
        "The Tokaj wine region sits at the confluence of the Bodrog and Tisza rivers, creating autumn mists essential for noble rot (botrytis cinerea) development.",
        "Pope Benedict XIV praised Tokaji Aszú, reportedly saying: 'Blessed be the soil that produced thee, blessed be the woman who sent thee, blessed am I who drink thee.'",
        "Tokaj was included in the Hungarian national anthem, written in 1823, reflecting the region's central role in Hungarian national identity.",
        "After the fall of communism in 1989, foreign investors including AXA Millésimes, Vega Sicilia, and the Royal Tokaji Wine Company revitalised Tokaj's vineyards and winemaking.",
        "The Tokaj region was inscribed as a UNESCO World Heritage Cultural Landscape in 2002.",
        "The traditional Tokaj ageing cellars (pince) are carved into volcanic rock and covered with the beneficial black mould Cladosporium cellare, which thrives on ethanol vapour.",
        "Tokaji Aszú was historically graded using the puttonyos system, where 3 to 6 puttonyos (hods) of aszú berries were added to a barrel (gönci hordó) of 136 litres.",
        "The gönci hordó (barrel of Gönc) is the traditional Tokaj barrel of 136 litres capacity, named after the town of Gönc where they were manufactured.",
    ],
    "notable_producers": [
        "Royal Tokaji Wine Company was founded in 1990 by Hugh Johnson and others, becoming one of the first foreign-invested wine ventures in post-communist Hungary.",
        "Disznókő estate in Tokaj was acquired by AXA Millésimes in 1992 and has invested heavily in restoring traditional Tokaj winemaking.",
        "Oremus estate in Tokaj is owned by Vega Sicilia (Tempos Vega Sicilia) and has revived premium Aszú production.",
        "István Szepsy is considered the modern master of Tokaj, credited with reviving single-vineyard dry Furmint and redefining quality standards for the region.",
        "Samuel Tinon was a pioneering estate in Tokaj that helped establish the reputation of dry Furmint as a world-class white wine style.",
    ],
}


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Georgian Wine Regions
# ═══════════════════════════════════════════════════════════════════════════════

GEORGIA_REGIONS = [
    {
        "name": "Kakheti",
        "climate": "warm continental",
        "soil_types": ["alluvial", "clay", "limestone"],
        "soil_details": "Alazani Valley alluvial soils with clay and limestone on the higher slopes; diverse terroir across multiple sub-zones",
        "elevation_range": "350-800m",
        "vineyard_area_ha": 40000,
        "production_share": 70,
        "key_grapes": ["Saperavi", "Rkatsiteli", "Mtsvane", "Kisi"],
        "sub_zones": ["Tsinandali", "Mukuzani", "Kindzmarauli", "Napareuli", "Akhasheni", "Kvareli", "Manavi", "Vazisubani"],
        "notes": "Kakheti is the heart of Georgian winemaking, producing approximately 70% of the country's wine. The Alazani Valley is sheltered by the Greater Caucasus Mountains to the north.",
    },
    {
        "name": "Kartli",
        "climate": "continental",
        "soil_types": ["alluvial", "clay", "limestone"],
        "soil_details": "Central Georgian plateau around Tbilisi with varied alluvial and clay-limestone soils at moderate to high elevation",
        "elevation_range": "500-800m",
        "vineyard_area_ha": 5000,
        "key_grapes": ["Chinuri", "Goruli Mtsvane", "Tavkveri"],
        "notes": "Kartli, the region surrounding Tbilisi, has a long winemaking history. Chinuri is used for both still and sparkling wines, as well as amber wines in qvevri.",
    },
    {
        "name": "Imereti",
        "climate": "humid subtropical",
        "soil_types": ["clay-limestone", "alluvial"],
        "soil_details": "Western Georgian clay-limestone and alluvial soils in a humid climate; the Imeretian winemaking method uses partial skin contact for amber wines",
        "elevation_range": "200-800m",
        "vineyard_area_ha": 4000,
        "key_grapes": ["Tsolikouri", "Tsitska", "Krakhuna", "Otskhanuri Sapere"],
        "notes": "Imereti is known for the Imeretian method of qvevri winemaking, which uses partial skin contact (no stems) producing lighter amber wines than the Kakhetian method.",
    },
    {
        "name": "Racha-Lechkhumi",
        "climate": "mountainous continental",
        "soil_types": ["limestone", "clay", "slate"],
        "soil_details": "High-altitude mountainous terrain with limestone and clay soils; the combination of elevation and microclimate produces naturally semi-sweet wines",
        "elevation_range": "500-900m",
        "vineyard_area_ha": 2000,
        "key_grapes": ["Aleksandrouli", "Mujuretuli"],
        "notes": "Racha-Lechkhumi is home to Khvanchkara, a naturally semi-sweet red wine made from Aleksandrouli and Mujuretuli grapes. It was reportedly Stalin's favourite wine.",
    },
    {
        "name": "Adjara",
        "climate": "subtropical with Black Sea influence",
        "soil_types": ["clay", "alluvial"],
        "soil_details": "Black Sea coastal region with humid subtropical climate and clay-alluvial soils",
        "elevation_range": "0-500m",
        "vineyard_area_ha": 500,
        "key_grapes": ["Chkhaveri", "Tsolikouri"],
        "notes": "Adjara on the Black Sea coast has a humid subtropical climate. Chkhaveri is used to make light rosé-style wines.",
    },
    {
        "name": "Guria",
        "climate": "humid subtropical",
        "soil_types": ["clay", "alluvial"],
        "soil_details": "Western Georgian coastal region with humid conditions and clay soils",
        "elevation_range": "0-400m",
        "vineyard_area_ha": 300,
        "key_grapes": ["Chkhaveri", "Jani"],
        "notes": "Guria is a small western Georgian wine region with a humid climate and limited production.",
    },
    {
        "name": "Samegrelo",
        "climate": "humid subtropical",
        "soil_types": ["clay", "limestone"],
        "soil_details": "Humid western Georgia with clay and limestone soils; known for the rare Ojaleshi grape",
        "elevation_range": "0-500m",
        "vineyard_area_ha": 500,
        "key_grapes": ["Ojaleshi"],
        "notes": "Samegrelo is known for the rare Ojaleshi grape, which produces deeply coloured, tannic red wines. Ojaleshi is one of Georgia's most prized indigenous varieties but is very limited in production.",
    },
    {
        "name": "Abkhazia",
        "climate": "subtropical",
        "soil_types": ["clay", "alluvial"],
        "soil_details": "Historically important Black Sea coastal wine region with limited current production due to political situation",
        "elevation_range": "0-500m",
        "vineyard_area_ha": None,
        "key_grapes": ["Avasirkhva", "Kachichi"],
        "notes": "Abkhazia was historically an important wine region in western Georgia, though current production is limited due to the region's political status.",
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Qvevri Winemaking
# ═══════════════════════════════════════════════════════════════════════════════

QVEVRI_DATABASE = {
    "vessel": {
        "definition": "A qvevri is a large egg-shaped clay vessel, ranging from 50 to 3,500 litres, used for fermenting and ageing wine in Georgia.",
        "construction": "Qvevri are lined with beeswax on the interior to create a semi-permeable seal and buried in the ground up to the rim in a marani (traditional wine cellar).",
        "temperature": "The earth surrounding a buried qvevri naturally regulates fermentation temperature, keeping it cooler in summer and warmer in winter.",
        "sizes": "Qvevri range from small 50-litre vessels for family use to large 3,500-litre vessels for commercial production.",
    },
    "unesco": "Georgian qvevri winemaking was inscribed on the UNESCO Intangible Cultural Heritage of Humanity list in 2013.",
    "methods": [
        {
            "name": "Kakhetian method",
            "description": "Full skin contact (including stems, skins, and seeds) for white grapes fermented in qvevri for 5-6 months",
            "notes": "The Kakhetian method produces the most traditional amber wines, with deep colour, high tannin, and complex oxidative character from extended maceration.",
        },
        {
            "name": "Imeretian method",
            "description": "Partial skin contact (skins and seeds but no stems) for white grapes fermented in qvevri",
            "notes": "The Imeretian method produces lighter amber wines than the Kakhetian method, as the omission of stems reduces tannin extraction.",
        },
    ],
    "amber_wine": [
        "Amber wine (also called orange wine) is made from white grapes with extended skin contact, typically 3-6 months in qvevri.",
        "The amber colour in Georgian qvevri wines comes from phenolic compounds extracted during prolonged skin contact with white grape varieties.",
        "Georgia is the origin of the modern 'orange wine' movement, which has been adopted by natural winemakers in Italy (Friuli), Slovenia, and globally.",
        "Traditional Georgian amber wines have a tannic structure more commonly associated with red wines, due to extended maceration of white grapes.",
    ],
    "history": [
        "Georgia has 8,000 years of continuous winemaking history, making it the oldest known wine-producing country in the world.",
        "Archaeological evidence of grape winemaking dating to approximately 6000 BC was discovered at Gadachrili Gora in Georgia.",
        "Additional evidence of ancient Georgian winemaking was found at the Khramis Didi-Gora archaeological site, confirming Georgia as the cradle of viticulture.",
        "The Georgian word 'ghvino' is believed by some linguists to be the etymological root of the word 'wine' in Indo-European languages.",
        "A marani is a traditional Georgian wine cellar where qvevri are buried in the floor, serving as both a winemaking facility and a sacred space.",
        "Georgia is home to over 525 identified indigenous grape varieties, one of the highest concentrations of native vine diversity in the world.",
        "The Georgian tradition of the supra (feast) is intimately connected to wine culture, presided over by a tamada (toastmaster) who leads ritual toasts.",
        "The grapevine is a central symbol in Georgian culture and Christianity; the Cross of the Vine (Jvari) is said to have been made from a grapevine by Saint Nino in the 4th century.",
        "During the Soviet era, Georgia was the primary wine supplier for the USSR, with production focused on quantity rather than quality for the Soviet market.",
        "Russia banned Georgian wine imports in 2006, forcing Georgian winemakers to diversify into Western European and American markets and improve quality standards.",
        "The lifting of the Russian wine embargo in 2013 opened a major export market, but by then Georgian producers had established a strong presence in premium Western markets.",
        "Georgia's National Wine Agency regulates wine production and manages the country's appellations of origin system.",
        "Traditional Georgian feasts (supra) use a drinking horn (kantsi) made from animal horn, which must be emptied in one drinking as it cannot be set down.",
    ],
    "modern_revival": [
        "The natural wine movement globally has driven renewed interest in Georgian qvevri wines since the early 2000s.",
        "Italian winemakers in Friuli Venezia Giulia, including Josko Gravner and Stanko Radikon, were inspired by Georgian qvevri methods to pioneer amber wine production in Europe.",
        "Josko Gravner of Friuli travelled to Georgia in the early 2000s and subsequently adopted qvevri winemaking, catalysing the European orange wine movement.",
        "Several Georgian producers have achieved international recognition, including Pheasant's Tears, Iago's Wine, and Alaverdi Monastery.",
        "The Alaverdi Monastery in Kakheti has been producing wine continuously since the 6th century, making it one of the oldest continuously operating wineries in the world.",
    ],
}


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Grape Varieties
# ═══════════════════════════════════════════════════════════════════════════════

GRAPE_VARIETY_DATABASE = [
    # ── Hungarian varieties ──
    {
        "name": "Furmint",
        "country": "Hungary",
        "colour": "white",
        "area_ha": 4000,
        "key_region": "Tokaj",
        "characteristics": "high acidity, susceptible to botrytis, capable of great complexity",
        "notes": "Furmint is the star grape of Tokaj, used for both botrytized sweet wines (Aszú) and increasingly celebrated dry varietal wines. Its high natural acidity makes it ideal for long ageing.",
        "synonyms": [],
    },
    {
        "name": "Hárslevelű",
        "country": "Hungary",
        "colour": "white",
        "area_ha": 2000,
        "key_region": "Tokaj",
        "characteristics": "aromatic, floral (linden blossom), lower acidity than Furmint",
        "notes": "Hárslevelű means 'linden leaf' in Hungarian. It is the second most important grape in Tokaj, adding aromatic complexity and softer acidity when blended with Furmint.",
        "synonyms": ["Lindenblättriger"],
    },
    {
        "name": "Sárgamuskotály",
        "country": "Hungary",
        "colour": "white",
        "area_ha": None,
        "key_region": "Tokaj",
        "characteristics": "intensely aromatic, grapey, muscat character",
        "notes": "Sárgamuskotály is the Hungarian name for Muscat Blanc à Petits Grains. It is the third permitted grape in Tokaj wines, adding intense aromatics to blends.",
        "synonyms": ["Muscat Blanc à Petits Grains", "Muscat Lunel"],
    },
    {
        "name": "Kadarka",
        "country": "Hungary",
        "colour": "red",
        "area_ha": 1000,
        "key_region": "Szekszárd",
        "characteristics": "thin-skinned, spicy, light-bodied, high acidity",
        "notes": "Kadarka is the traditional red grape of Hungary's Bikavér (Bull's Blood) blend. It is thin-skinned, late-ripening, and difficult to grow but produces elegant, spicy wines when successful.",
        "synonyms": ["Gamza"],
    },
    {
        "name": "Kékfrankos",
        "country": "Hungary",
        "colour": "red",
        "area_ha": 7000,
        "key_region": "Sopron",
        "characteristics": "medium to full body, cherry fruit, peppery spice, firm acidity",
        "notes": "Kékfrankos is Hungary's most widely planted red grape variety, known as Blaufränkisch in Austria and Lemberger in Germany. It thrives in Sopron, Eger, Szekszárd, and Villány.",
        "synonyms": ["Blaufränkisch", "Lemberger", "Frankovka"],
    },
    {
        "name": "Juhfark",
        "country": "Hungary",
        "colour": "white",
        "area_ha": 50,
        "key_region": "Somló",
        "characteristics": "mineral, austere, high acidity, age-worthy",
        "notes": "Juhfark means 'sheep's tail' in Hungarian, referring to the elongated shape of the grape cluster. It is almost exclusively grown on the volcanic hill of Somló, where it produces mineral, austere whites.",
        "synonyms": [],
    },
    {
        "name": "Olaszrizling",
        "country": "Hungary",
        "colour": "white",
        "area_ha": None,
        "key_region": "Balaton",
        "characteristics": "versatile, fresh to full-bodied, citrus and almond notes",
        "notes": "Olaszrizling (Welschriesling) is Hungary's most planted white grape variety. Despite its name, it is unrelated to Riesling. It produces a wide range of styles from fresh everyday wines to complex single-vineyard bottlings.",
        "synonyms": ["Welschriesling", "Olaszrizling", "Graševina", "Laški Rizling"],
    },
    {
        "name": "Kéknyelű",
        "country": "Hungary",
        "colour": "white",
        "area_ha": 20,
        "key_region": "Badacsony",
        "characteristics": "mineral, herbal, complex, extremely rare",
        "notes": "Kéknyelű ('blue stem') is one of the rarest grape varieties in the world, with approximately 20 hectares planted exclusively in the Badacsony region on the shores of Lake Balaton.",
        "synonyms": [],
    },
    {
        "name": "Cserszegi Fűszeres",
        "country": "Hungary",
        "colour": "white",
        "area_ha": None,
        "key_region": "Kunság",
        "characteristics": "aromatic, Muscat-like, spicy, early-ripening",
        "notes": "Cserszegi Fűszeres is a Hungarian crossing (Irsai Olivér x Tramini) developed at the Cserszegtomaj research station. The name means 'spicy from Cserszeg'. It is widely planted for aromatic everyday wines.",
        "synonyms": [],
    },
    # ── Georgian varieties ──
    {
        "name": "Saperavi",
        "country": "Georgia",
        "colour": "red",
        "area_ha": 5000,
        "key_region": "Kakheti",
        "characteristics": "deep inky colour, teinturier (red flesh), high tannin, age-worthy",
        "notes": "Saperavi is the world's only widely planted teinturier grape used for quality wine production. Its red-fleshed berries produce wines of exceptional depth of colour. It is Georgia's most important red variety.",
        "synonyms": [],
    },
    {
        "name": "Rkatsiteli",
        "country": "Georgia",
        "colour": "white",
        "area_ha": 7000,
        "key_region": "Kakheti",
        "characteristics": "high acidity, versatile, good for amber wine and sparkling",
        "notes": "Rkatsiteli is Georgia's most planted grape variety and one of the oldest cultivated vine varieties in the world. It is used for dry white, amber (skin-contact), and sparkling wines.",
        "synonyms": [],
    },
    {
        "name": "Mtsvane Kakhuri",
        "country": "Georgia",
        "colour": "white",
        "area_ha": 1000,
        "key_region": "Kakheti",
        "characteristics": "aromatic, fruity, lower acidity than Rkatsiteli",
        "notes": "Mtsvane Kakhuri ('green of Kakheti') is often blended with Rkatsiteli to add aromatic complexity. The Tsinandali appellation requires a blend of Rkatsiteli and Mtsvane.",
        "synonyms": ["Mtsvane"],
    },
    {
        "name": "Kisi",
        "country": "Georgia",
        "colour": "white",
        "area_ha": 500,
        "key_region": "Kakheti",
        "characteristics": "aromatic, full-bodied, excellent for amber wine",
        "notes": "Kisi is an aromatic Georgian white variety increasingly valued for amber wines. It produces particularly complex and fragrant qvevri wines with stone fruit and floral character.",
        "synonyms": [],
    },
    {
        "name": "Chinuri",
        "country": "Georgia",
        "colour": "white",
        "area_ha": 300,
        "key_region": "Kartli",
        "characteristics": "crisp acidity, mineral, suitable for sparkling and amber",
        "notes": "Chinuri is the principal grape of the Kartli region around Tbilisi. It is used for still, sparkling, and amber wines, and performs particularly well in qvevri.",
        "synonyms": [],
    },
    {
        "name": "Aleksandrouli",
        "country": "Georgia",
        "colour": "red",
        "area_ha": 200,
        "key_region": "Racha-Lechkhumi",
        "characteristics": "aromatic, medium body, naturally high sugar",
        "notes": "Aleksandrouli is the primary grape in Khvanchkara, Georgia's most famous naturally semi-sweet red wine. It is grown almost exclusively in the mountainous Racha-Lechkhumi region.",
        "synonyms": [],
    },
    {
        "name": "Mujuretuli",
        "country": "Georgia",
        "colour": "red",
        "area_ha": 100,
        "key_region": "Racha-Lechkhumi",
        "characteristics": "deeply coloured, tannic, blending partner",
        "notes": "Mujuretuli is blended with Aleksandrouli to produce Khvanchkara. It adds colour and structure to the blend and is rarely vinified as a standalone variety.",
        "synonyms": [],
    },
    {
        "name": "Tsolikouri",
        "country": "Georgia",
        "colour": "white",
        "area_ha": 800,
        "key_region": "Imereti",
        "characteristics": "fresh, citrus, good acidity, main Imeretian white",
        "notes": "Tsolikouri is the principal white grape of Imereti in western Georgia. It is used for both European-style wines and amber wines made using the Imeretian qvevri method.",
        "synonyms": [],
    },
    {
        "name": "Ojaleshi",
        "country": "Georgia",
        "colour": "red",
        "area_ha": 100,
        "key_region": "Samegrelo",
        "characteristics": "deeply coloured, tannic, rare, late-ripening",
        "notes": "Ojaleshi is a rare Georgian red variety grown almost exclusively in the Samegrelo region. It produces deeply coloured, tannic wines and is considered one of Georgia's finest but most limited indigenous grapes.",
        "synonyms": [],
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Additional Wine Facts (Hungary & Georgia)
# ═══════════════════════════════════════════════════════════════════════════════

ADDITIONAL_HUNGARY_FACTS = [
    # Bikavér
    "Egri Bikavér (Bull's Blood of Eger) must be a blend of at least three grape varieties with no single variety exceeding 50% of the blend.",
    "Egri Bikavér Superior requires higher minimum alcohol content, lower yields, and longer ageing than basic Egri Bikavér.",
    "Egri Bikavér Grand Superior represents the top tier of Bull's Blood, with the strictest yield limits and longest mandatory ageing.",
    "The legend of Bull's Blood dates to the 1552 Siege of Eger, where Hungarian defenders drank red wine that stained their beards, leading Ottoman attackers to believe they were drinking bull's blood.",
    "Szekszárdi Bikavér is the other Hungarian region permitted to produce Bull's Blood (Bikavér), using a different grape blend than the Eger version.",
    # Egri Csillag
    "Egri Csillag (Star of Eger) is a white wine blend that must contain at least four grape varieties, created as a white counterpart to Egri Bikavér.",
    # Villány classification
    "Villány's Classicus tier wines are village-level wines that may be released young without extended ageing requirements.",
    "Villány's Prémium tier requires lower yields and longer ageing than Classicus wines, representing single-vineyard quality.",
    "Villány's Super Prémium tier requires significantly lower yields and extended oak ageing, from classified vineyards only.",
    "Villány's Grand Superior tier represents the pinnacle of the classification, requiring the lowest yields and longest ageing from the best classified sites.",
    "Villány has become Hungary's leading region for Cabernet Franc, with some critics comparing the best examples to Loire Valley crus.",
    # Somló traditions
    "Somló's reputation as the 'wedding night wine' of the Austro-Hungarian Empire led to it being prescribed to Habsburg brides to ensure male heirs.",
    "Somló wines are traditionally made in an oxidative style with extended lees contact, producing austere, mineral whites that improve with decades of ageing.",
    # Lake Balaton
    "Lake Balaton is Central Europe's largest lake and its moderating influence on surrounding vineyards is comparable to other great wine lakes such as Lake Geneva and Lake Garda.",
    "Balatonfüred-Csopak is one of the most prestigious sub-regions of the Balaton wine region, known for high-quality Olaszrizling from volcanic and limestone soils.",
    # Hungarian sparkling
    "Hungary has a significant sparkling wine tradition, with Etyek-Buda and the Balatonboglár region producing traditional method (pezsgő) sparkling wines.",
    "Törley is Hungary's most famous sparkling wine house, founded in 1882, and has been producing traditional method sparkling wine for over 140 years.",
    # General viticulture
    "Hungary's continental climate provides cold winters that naturally control vine diseases and pests, reducing the need for chemical treatments.",
    "The Pannonian climate influence across southern and central Hungary provides warm, dry autumns that are ideal for late-harvest and botrytized wine production.",
    "Hungarian wine law recognises three quality categories ascending from table wine (asztali bor) through regional wine (tájbor) to quality wine from a specified region (minőségi bor).",
    "The Hungarian Wine Academy (Magyar Borakadémia) was established to promote Hungarian wine culture and education both domestically and internationally.",
    # More regional detail
    "The Bükk Mountains shelter the Eger wine region from cold northern winds, creating a warmer microclimate than the surrounding terrain.",
    "Eger's volcanic tufo cellars extend for kilometres beneath the town and maintain a constant temperature of 10-12 degrees Celsius year-round.",
    "The Valley of the Beautiful Woman (Szépasszony-völgy) in Eger is a famous wine-tasting destination with dozens of cellars carved into tufo rock.",
    "Badacsony's basalt-capped volcanic hills retain heat from the sun during the day and radiate it back to the vines at night, aiding ripening.",
    "The extinct volcanic hill of Somló rises 432 metres above sea level and is surrounded by flat terrain, creating a distinctive island-like terroir.",
    "Szürkebarát is the Hungarian name for Pinot Gris, and Badacsony's volcanic soils produce particularly aromatic and full-bodied expressions of this variety.",
    "Irsai Olivér is a popular Hungarian table grape crossing (Pozsonyi Fehér x Pearl of Csaba) that produces light, Muscat-scented wines.",
    "Leányka is a traditional Hungarian white grape variety whose name means 'young girl', producing delicate, floral wines primarily in the Eger region.",
    "Királyleányka ('princess') is another Hungarian white variety related to Leányka, producing aromatic wines with slightly more body.",
    "Zweigelt has been increasingly planted in Hungary, particularly in Villány and Szekszárd, complementing the traditional Kékfrankos plantings.",
    "The Neszmély wine region along the Danube was one of the first Hungarian regions to adopt modern winemaking technology, including temperature-controlled fermentation.",
    "Hungary's Hilltop Neszmély winery was a pioneer in modern Hungarian white winemaking, helping to establish Neszmély as a quality white wine region.",
    "The Pannonhalma Archabbey winery was revitalised in the early 2000s and now produces acclaimed wines under the guidance of Benedictine monks.",
    "Kadarka was historically Hungary's most important red grape but was largely replaced by Kékfrankos during the 20th century; recent efforts aim to revive quality Kadarka production.",
    "The Hungarian wine industry experienced significant transformation after 1989, transitioning from state-owned cooperatives to private estates focused on quality.",
    "Gere Attila is a renowned Villány winemaker who pioneered the region's Bordeaux-style red blends and helped establish the classified vineyard system.",
    "Bock József is another leading Villány producer known for premium Cabernet Franc and Merlot, contributing to Villány's international reputation.",
    "Thummerer Vilmos is a prominent Eger winemaker credited with elevating Egri Bikavér to international quality standards.",
    "The Mátra wine region in northern Hungary produces fresh whites from Chardonnay, Sauvignon Blanc, and Muscat varieties at elevations up to 500 metres.",
    "Tolna is a smaller Hungarian wine region between Szekszárd and Kunság, known for both reds and whites on loess soils.",
    "The Hajós-Baja wine region in southern Hungary has a strong Swabian German heritage, with traditional wine cellars built by 18th-century settlers.",
    "Cserszegtomaj is the town where Cserszegi Fűszeres was developed at the local grape research station, crossing Irsai Olivér and Traminer.",
]

ADDITIONAL_GEORGIA_FACTS = [
    # Grape diversity
    "Of Georgia's 525 identified indigenous grape varieties, approximately 45 are in active commercial cultivation today.",
    "Georgia's grape genetic diversity is unmatched globally, with more indigenous varieties per square kilometre than any other country.",
    # Winemaking traditions
    "The traditional Georgian supra (feast) can last many hours, with the tamada (toastmaster) leading dozens of ritual toasts in a prescribed order.",
    "In the Georgian supra tradition, the first toast is always to God, followed by toasts to peace, the motherland, ancestors, and other prescribed themes.",
    "Georgian wine culture is deeply intertwined with Orthodox Christianity; the grapevine and wine feature prominently in Georgian religious art and architecture.",
    "The Khareba Winery tunnel in Kakheti uses a 7.7-kilometre network of former railway tunnels for wine storage, maintaining a natural temperature of 12-14 degrees Celsius.",
    # Specific wine styles
    "Kindzmarauli is a naturally semi-sweet red wine from the Kindzmarauli microzone in Kakheti, made from Saperavi grapes, and is one of Georgia's most popular wines.",
    "Khvanchkara is a naturally semi-sweet red wine from the Racha-Lechkhumi region, made from Aleksandrouli and Mujuretuli grapes, and was reportedly Joseph Stalin's favourite wine.",
    "Tsinandali is a dry white wine appellation in Kakheti requiring a blend of Rkatsiteli (at least 80%) and Mtsvane, aged minimum 3 years including 2 years in oak.",
    "Mukuzani is a dry red wine appellation in Kakheti made from 100% Saperavi, aged for a minimum of 3 years, producing some of Georgia's most structured and age-worthy reds.",
    # Production
    "Georgia's wine exports have grown significantly since 2013, with major markets including Russia, Ukraine, China, Poland, and Kazakhstan.",
    "The Georgian wine industry is regulated by the National Wine Agency (Ghvinis Erovnuli Saagento), which monitors appellations, quality standards, and export certification.",
    "Small-scale family winemaking (ghvino) remains widespread in rural Georgia, with many households maintaining their own qvevri and producing wine for family consumption.",
    "The Tbilisi Wine Festival and New Wine Festival are annual events celebrating Georgia's winemaking heritage, attracting international attention to Georgian wines.",
    # Archaeology
    "Residue analysis of pottery fragments from Gadachrili Gora confirmed the presence of tartaric acid, malic acid, succinic acid, and citric acid, consistent with grape wine from approximately 6000 BC.",
    "The ancient Vani archaeological site in western Georgia yielded elaborate gold wine vessels, demonstrating the high cultural status of wine in ancient Colchis.",
    "Georgian archaeologists have identified wine-related artefacts dating across all major historical periods, demonstrating an unbroken 8,000-year winemaking tradition.",
    # Terroir
    "The Greater Caucasus Mountains shelter Georgia's eastern vineyards from cold northern air masses while channelling warm, dry air from Central Asia.",
    "Georgia's western wine regions receive significantly more rainfall than the eastern regions, with the Black Sea coast receiving over 2,000mm annually compared to 400-600mm in parts of Kakheti.",
    "The Alazani Valley in Kakheti is a broad river valley running east-west, with vineyards on both the northern (Greater Caucasus) and southern (Lesser Caucasus) slopes.",
    # More winemaking and culture
    "Saperavi is a teinturier grape, meaning its flesh is red (not just its skin), which gives Saperavi wines an exceptionally deep, almost opaque colour.",
    "Saperavi-based wines from Kakheti can age for 15-50 years, developing complex aromas of dark fruit, leather, tobacco, and earth.",
    "The Kisi grape has experienced a significant revival in the 21st century, with plantings increasing from near-extinction to approximately 500 hectares.",
    "Krakhuna is a white grape variety from Imereti known for producing aromatic, full-bodied wines with stone fruit character, often vinified in qvevri.",
    "Tsitska is an Imeretian white grape with high natural acidity, used both for still wine and as a base for Georgian sparkling wine (traditional method).",
    "Otskhanuri Sapere is a rare Imeretian red grape that produces deeply coloured wines with high tannin, increasingly valued by natural winemakers.",
    "Tavkveri is a Kartli red grape used for both dry and semi-sweet rosé-style wines, known for its delicate colour and aromatic profile.",
    "Goruli Mtsvane ('green of Gori') is a Kartli white grape distinct from Mtsvane Kakhuri, used for still, sparkling, and amber wines.",
    "Chkhaveri is a pink-skinned grape from western Georgia (Adjara and Guria) that produces delicate rosé-style wines with floral aromatics.",
    "Jani is a rare white grape from Guria in western Georgia, nearly extinct but subject to conservation efforts by Georgian ampelographers.",
    "The Schuchmann Winery in Kakheti, founded by German investor Burkhard Schuchmann, combines European technology with traditional qvevri winemaking.",
    "Pheasant's Tears, co-founded by American painter John Wurdeman and Georgian winemaker Gela Patalishvili, became internationally famous for authentic qvevri wines.",
    "Iago Bitarishvili of Iago's Wine in Kartli is considered a pioneer of the modern Georgian natural wine movement, producing acclaimed Chinuri in qvevri.",
    "The Teliani Valley winery, established in 1897, is one of Georgia's oldest commercial wineries and is named after a famous vineyard site in Kakheti.",
    "Château Mukhrani in Kartli is a restored 19th-century estate that was once the private winery of Georgian royalty (the Bagration-Mukhransky family).",
    "Bagrationi 1882 is Georgia's leading sparkling wine producer, founded in Tbilisi and using the traditional method with local grape varieties.",
    "The Amber Wine Festival, held annually in Tbilisi, celebrates Georgia's unique tradition of skin-contact white wines and attracts international buyers and journalists.",
    "Georgian vine training traditionally uses the maglari system, where vines are trained up living trees, a practice dating back thousands of years.",
    "Modern Georgian viticulture increasingly uses the European cordon and guyot training systems, though traditional maglari and pergola training survive in some areas.",
    "The Racha-Lechkhumi region's high altitude (500-900m) and cool autumn temperatures naturally arrest fermentation in Khvanchkara, preserving grape sugars without artificial intervention.",
    "Georgia's climate ranges from subtropical on the Black Sea coast to semi-arid continental in eastern Kakheti, providing diverse conditions for its many indigenous grape varieties.",
]


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Classification Systems
# ═══════════════════════════════════════════════════════════════════════════════

CLASSIFICATION_DATABASE = {
    "hungary": {
        "system": [
            "Hungary uses the EU-aligned classification system with OEM (Oltalom alatt álló Eredetmegjelölés) equivalent to PDO, and OFJ (Oltalom alatt álló Földrajzi Jelzés) equivalent to PGI.",
            "Hungary has 22 officially designated wine regions (borvidék).",
            "Tokaj has its own additional sub-classification system for its sweet wines, including Aszú, Szamorodni, and Eszencia.",
            "Villány operates a classified vineyard system with four ascending quality tiers: Classicus (village wine), Prémium, Super Prémium, and Grand Superior.",
            "Eger's Bikavér (Bull's Blood) has a tiered classification: Egri Bikavér (basic), Egri Bikavér Superior, and Egri Bikavér Grand Superior.",
            "Hungary has a total vineyard area of approximately 63,000 hectares, ranking it among the medium-sized wine-producing countries of Europe.",
            "Hungarian wine production averages approximately 3 million hectolitres per year.",
            "The Hungarian Wine Act of 1997 established the modern framework for wine regulation, aligning Hungarian standards with European Union requirements.",
            "Hungary joined the European Union in 2004, bringing its wine classification system into alignment with EU PDO and PGI standards.",
            "The Kunság region on the Great Hungarian Plain is Hungary's largest wine-producing area by volume, though not by reputation.",
            "Hungary's six Great Wine Regions (történelmi borvidékek) are Tokaj, Eger, Villány, Szekszárd, Somló, and Badacsony.",
        ],
        "tokaj_rules": [
            "Tokaji Aszú must contain a minimum of 120 grams per litre residual sugar.",
            "Tokaji Aszú must be aged for a minimum of 18 months in oak barrels plus 6 months in bottle before release.",
            "The three permitted grape varieties for Tokaj wines are Furmint, Hárslevelű, and Sárgamuskotály (Muscat Blanc).",
            "Tokaji Eszencia must be made exclusively from free-run juice that drains from aszú berries under their own weight, without pressing.",
        ],
    },
    "georgia": {
        "system": [
            "Georgia operates a PDO (Protected Designation of Origin) system with Appellation of Origin Controlled wines.",
            "Georgia has 24 protected appellations of origin for wine.",
            "Georgian wine appellations are primarily concentrated in the Kakheti region, which contains the majority of the country's protected designations.",
            "Georgia has a total vineyard area of approximately 55,000 hectares.",
            "Georgia produces approximately 1.5 million hectolitres of wine annually.",
            "Georgian wine law distinguishes between wines made using European (conventional) methods and traditional (qvevri) methods.",
            "The Georgian qvevri designation on a wine label guarantees the wine was fermented and aged in a traditional buried clay vessel.",
            "Georgian naturally semi-sweet wines (such as Kindzmarauli and Khvanchkara) achieve their sweetness without added sugar, through arrested fermentation caused by cold autumn temperatures.",
        ],
        "appellations": [
            {"name": "Mukuzani", "type": "red", "grape": "Saperavi", "notes": "Dry red wine from the Mukuzani microzone in Kakheti, aged minimum 3 years."},
            {"name": "Tsinandali", "type": "white", "grape": "Rkatsiteli/Mtsvane", "notes": "Dry white blend from Tsinandali in Kakheti, aged minimum 3 years including 2 years in oak."},
            {"name": "Kindzmarauli", "type": "red", "grape": "Saperavi", "notes": "Naturally semi-sweet red wine from the Kindzmarauli microzone in Kakheti."},
            {"name": "Khvanchkara", "type": "red", "grape": "Aleksandrouli/Mujuretuli", "notes": "Naturally semi-sweet red from Racha, made from Aleksandrouli and Mujuretuli grapes."},
            {"name": "Napareuli", "type": "red/white", "grape": "Saperavi/Rkatsiteli", "notes": "Both red (Saperavi) and white (Rkatsiteli) appellations exist for Napareuli in Kakheti."},
            {"name": "Akhasheni", "type": "red", "grape": "Saperavi", "notes": "Naturally semi-sweet red from the Akhasheni microzone in Kakheti."},
            {"name": "Kvareli", "type": "red", "grape": "Saperavi", "notes": "Dry red wine from Kvareli in Kakheti, aged in large qvevri or oak."},
            {"name": "Manavi", "type": "white", "grape": "Mtsvane", "notes": "Dry white wine from the Manavi microzone in Kakheti."},
            {"name": "Vazisubani", "type": "white", "grape": "Rkatsiteli/Mtsvane", "notes": "Dry white blend from Vazisubani in Kakheti."},
        ],
    },
}


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
# FACT BUILDERS — Hungary Regions
# ═══════════════════════════════════════════════════════════════════════════════


def _build_hungary_facts(source_id: str) -> list[dict]:
    """Build facts about Hungarian wine regions."""
    facts = []

    for region in HUNGARY_REGIONS:
        name = region["name"]
        hungarian = region["hungarian_name"]
        entities = [{"type": "region", "name": name}]
        base_tags = ["hungary", name.lower().replace(" ", "_").replace("-", "_")]

        # Climate
        facts.append(_make_fact(
            f"The {name} ({hungarian}) wine region in Hungary has a {region['climate']} climate.",
            domain="wine_regions",
            source_id=source_id,
            subdomain="hungary",
            entities=entities,
            tags=base_tags + ["climate"],
        ))

        # Soil
        if region.get("soil_types"):
            soil_list = ", ".join(region["soil_types"])
            facts.append(_make_fact(
                f"The predominant soil types in Hungary's {name} wine region include {soil_list}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="hungary",
                entities=entities,
                tags=base_tags + ["soil", "terroir"],
            ))

        if region.get("soil_details"):
            facts.append(_make_fact(
                f"{region['soil_details']}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="hungary",
                entities=entities,
                tags=base_tags + ["soil", "terroir"],
            ))

        # Elevation
        if region.get("elevation_range"):
            facts.append(_make_fact(
                f"Vineyards in Hungary's {name} wine region are planted at elevations ranging from {region['elevation_range']}.",
                domain="viticulture",
                source_id=source_id,
                subdomain="hungary",
                entities=entities,
                tags=base_tags + ["elevation"],
            ))

        # Vineyard area
        if region.get("vineyard_area_ha"):
            facts.append(_make_fact(
                f"The {name} wine region in Hungary has approximately {region['vineyard_area_ha']:,} hectares of vineyards.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="hungary",
                entities=entities,
                confidence=0.95,
                tags=base_tags + ["area", "statistics"],
            ))

        # Key grapes
        if region.get("key_grapes"):
            grapes_str = ", ".join(region["key_grapes"])
            grape_entities = entities + [{"type": "grape", "name": g} for g in region["key_grapes"]]
            facts.append(_make_fact(
                f"The principal grape varieties of Hungary's {name} wine region include {grapes_str}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="hungary",
                entities=grape_entities,
                tags=base_tags + ["grapes"],
            ))

        # Wine styles
        if region.get("wine_styles"):
            styles_str = ", ".join(region["wine_styles"])
            facts.append(_make_fact(
                f"The {name} wine region in Hungary is known for producing {styles_str}.",
                domain="winemaking",
                source_id=source_id,
                subdomain="hungary",
                entities=entities,
                tags=base_tags + ["wine_styles"],
            ))

        # Notes
        if region.get("notes"):
            facts.append(_make_fact(
                region["notes"],
                domain="wine_regions",
                source_id=source_id,
                subdomain="hungary",
                entities=entities,
                tags=base_tags + ["notes"],
            ))

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# FACT BUILDERS — Tokaj Detailed
# ═══════════════════════════════════════════════════════════════════════════════


def _build_tokaj_facts(source_id: str) -> list[dict]:
    """Build detailed facts about Tokaj wines, classifications, and history."""
    facts = []
    base_entities = [{"type": "region", "name": "Tokaj"}]
    base_tags = ["hungary", "tokaj"]

    # Wine styles
    for style in TOKAJ_DATABASE["wine_styles"]:
        style_name = style["name"]
        style_entities = base_entities + [{"type": "wine_style", "name": style_name}]

        # Description
        facts.append(_make_fact(
            f"Tokaji {style_name} is made by the following method: {style['description']}.",
            domain="winemaking",
            source_id=source_id,
            subdomain="tokaj",
            entities=style_entities,
            tags=base_tags + [style_name.lower().replace(" ", "_")],
        ))

        # Residual sugar
        if style.get("rs_min_gl"):
            facts.append(_make_fact(
                f"Tokaji {style_name} must contain a minimum of {style['rs_min_gl']} grams per litre residual sugar.",
                domain="winemaking",
                source_id=source_id,
                subdomain="tokaj",
                entities=style_entities,
                tags=base_tags + [style_name.lower(), "residual_sugar"],
            ))

        if style.get("rs_range_gl"):
            facts.append(_make_fact(
                f"Tokaji {style_name} typically contains {style['rs_range_gl']} grams per litre residual sugar.",
                domain="winemaking",
                source_id=source_id,
                subdomain="tokaj",
                entities=style_entities,
                tags=base_tags + [style_name.lower(), "residual_sugar"],
            ))

        # Alcohol
        if style.get("alcohol_range"):
            facts.append(_make_fact(
                f"Tokaji {style_name} typically reaches only {style['alcohol_range']}% alcohol due to its extreme residual sugar concentration.",
                domain="winemaking",
                source_id=source_id,
                subdomain="tokaj",
                entities=style_entities,
                tags=base_tags + [style_name.lower(), "alcohol"],
            ))

        # Ageing
        if style.get("aging_months_oak"):
            facts.append(_make_fact(
                f"Tokaji {style_name} must be aged for a minimum of {style['aging_months_oak']} months in oak barrels and {style.get('aging_months_bottle', 0)} months in bottle.",
                domain="winemaking",
                source_id=source_id,
                subdomain="tokaj",
                entities=style_entities,
                tags=base_tags + [style_name.lower(), "aging"],
            ))

        # Styles (sweet/dry)
        if style.get("styles"):
            for s in style["styles"]:
                facts.append(_make_fact(
                    f"Tokaji {style_name} can be produced in {s} style.",
                    domain="winemaking",
                    source_id=source_id,
                    subdomain="tokaj",
                    entities=style_entities,
                    tags=base_tags + [style_name.lower()],
                ))

        # Hungarian name
        if style.get("hungarian_name"):
            facts.append(_make_fact(
                f"Tokaji {style_name} is also known by its Hungarian name: {style['hungarian_name']}.",
                domain="winemaking",
                source_id=source_id,
                subdomain="tokaj",
                entities=style_entities,
                tags=base_tags + [style_name.lower()],
            ))

        # Notes
        if style.get("notes"):
            facts.append(_make_fact(
                style["notes"],
                domain="winemaking",
                source_id=source_id,
                subdomain="tokaj",
                entities=style_entities,
                tags=base_tags + [style_name.lower()],
            ))

    # First-growth vineyards
    vineyards = TOKAJ_DATABASE["first_growth_vineyards"]
    facts.append(_make_fact(
        f"Tokaj has {len(vineyards)} classified first-growth vineyards (Első Osztályú Dűlő).",
        domain="wine_regions",
        source_id=source_id,
        subdomain="tokaj",
        entities=base_entities,
        tags=base_tags + ["classification", "vineyards"],
    ))

    for vineyard in vineyards:
        facts.append(_make_fact(
            f"{vineyard} is one of the 27 classified first-growth vineyards (Első Osztályú Dűlő) in the Tokaj wine region of Hungary.",
            domain="wine_regions",
            source_id=source_id,
            subdomain="tokaj",
            entities=base_entities + [{"type": "vineyard", "name": vineyard}],
            tags=base_tags + ["first_growth", vineyard.lower().replace(" ", "_")],
        ))

    # Townships
    townships = TOKAJ_DATABASE["townships"]
    townships_str = ", ".join(townships)
    facts.append(_make_fact(
        f"The six principal wine-producing townships of the Tokaj region are {townships_str}.",
        domain="wine_regions",
        source_id=source_id,
        subdomain="tokaj",
        entities=base_entities,
        tags=base_tags + ["townships"],
    ))

    for town in townships:
        facts.append(_make_fact(
            f"{town} is one of the six principal wine-producing townships in the Tokaj wine region.",
            domain="wine_regions",
            source_id=source_id,
            subdomain="tokaj",
            entities=base_entities + [{"type": "township", "name": town}],
            tags=base_tags + ["township", town.lower()],
        ))

    # History
    for hist_fact in TOKAJ_DATABASE["history"]:
        facts.append(_make_fact(
            hist_fact,
            domain="wine_regions",
            source_id=source_id,
            subdomain="tokaj",
            entities=base_entities,
            tags=base_tags + ["history"],
        ))

    # Notable producers
    for producer_fact in TOKAJ_DATABASE.get("notable_producers", []):
        facts.append(_make_fact(
            producer_fact,
            domain="producers",
            source_id=source_id,
            subdomain="tokaj",
            entities=base_entities,
            tags=base_tags + ["producers"],
        ))

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# FACT BUILDERS — Georgia Regions
# ═══════════════════════════════════════════════════════════════════════════════


def _build_georgia_facts(source_id: str) -> list[dict]:
    """Build facts about Georgian wine regions."""
    facts = []

    for region in GEORGIA_REGIONS:
        name = region["name"]
        entities = [{"type": "region", "name": name}]
        base_tags = ["georgia", name.lower().replace("-", "_")]

        # Climate
        facts.append(_make_fact(
            f"The {name} wine region in Georgia has a {region['climate']} climate.",
            domain="wine_regions",
            source_id=source_id,
            subdomain="georgia",
            entities=entities,
            tags=base_tags + ["climate"],
        ))

        # Soil
        if region.get("soil_types"):
            soil_list = ", ".join(region["soil_types"])
            facts.append(_make_fact(
                f"The predominant soil types in Georgia's {name} wine region include {soil_list}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="georgia",
                entities=entities,
                tags=base_tags + ["soil", "terroir"],
            ))

        if region.get("soil_details"):
            facts.append(_make_fact(
                f"{region['soil_details']}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="georgia",
                entities=entities,
                tags=base_tags + ["soil", "terroir"],
            ))

        # Elevation
        if region.get("elevation_range"):
            facts.append(_make_fact(
                f"Vineyards in Georgia's {name} wine region are planted at elevations ranging from {region['elevation_range']}.",
                domain="viticulture",
                source_id=source_id,
                subdomain="georgia",
                entities=entities,
                tags=base_tags + ["elevation"],
            ))

        # Vineyard area
        if region.get("vineyard_area_ha"):
            facts.append(_make_fact(
                f"The {name} wine region in Georgia has approximately {region['vineyard_area_ha']:,} hectares of vineyards.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="georgia",
                entities=entities,
                confidence=0.95,
                tags=base_tags + ["area", "statistics"],
            ))

        # Production share
        if region.get("production_share"):
            facts.append(_make_fact(
                f"The {name} region accounts for approximately {region['production_share']}% of Georgia's total wine production.",
                domain="wine_business",
                source_id=source_id,
                subdomain="georgia",
                entities=entities,
                confidence=0.95,
                tags=base_tags + ["production", "statistics"],
            ))

        # Key grapes
        if region.get("key_grapes"):
            grapes_str = ", ".join(region["key_grapes"])
            grape_entities = entities + [{"type": "grape", "name": g} for g in region["key_grapes"]]
            facts.append(_make_fact(
                f"The principal grape varieties of Georgia's {name} wine region include {grapes_str}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="georgia",
                entities=grape_entities,
                tags=base_tags + ["grapes"],
            ))

        # Sub-zones
        if region.get("sub_zones"):
            zones_str = ", ".join(region["sub_zones"])
            facts.append(_make_fact(
                f"The {name} wine region in Georgia includes the following sub-zones: {zones_str}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="georgia",
                entities=entities,
                tags=base_tags + ["sub_zones"],
            ))
            # Individual sub-zone facts
            for zone in region["sub_zones"]:
                facts.append(_make_fact(
                    f"{zone} is a recognised wine sub-zone within the {name} region of Georgia.",
                    domain="wine_regions",
                    source_id=source_id,
                    subdomain="georgia",
                    entities=entities + [{"type": "sub_zone", "name": zone}],
                    tags=base_tags + ["sub_zone", zone.lower()],
                ))

        # Notes
        if region.get("notes"):
            facts.append(_make_fact(
                region["notes"],
                domain="wine_regions",
                source_id=source_id,
                subdomain="georgia",
                entities=entities,
                tags=base_tags + ["notes"],
            ))

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# FACT BUILDERS — Qvevri Winemaking
# ═══════════════════════════════════════════════════════════════════════════════


def _build_qvevri_facts(source_id: str) -> list[dict]:
    """Build facts about qvevri winemaking and amber wine tradition."""
    facts = []
    base_entities = [{"type": "technique", "name": "qvevri"}]
    base_tags = ["georgia", "qvevri"]

    # Vessel facts
    vessel = QVEVRI_DATABASE["vessel"]
    for key in ["definition", "construction", "temperature", "sizes"]:
        facts.append(_make_fact(
            vessel[key],
            domain="winemaking",
            source_id=source_id,
            subdomain="qvevri",
            entities=base_entities,
            tags=base_tags + ["vessel"],
        ))

    # UNESCO
    facts.append(_make_fact(
        QVEVRI_DATABASE["unesco"],
        domain="winemaking",
        source_id=source_id,
        subdomain="qvevri",
        entities=base_entities,
        tags=base_tags + ["unesco", "heritage"],
    ))

    # Methods
    for method in QVEVRI_DATABASE["methods"]:
        method_entities = base_entities + [{"type": "technique", "name": method["name"]}]
        facts.append(_make_fact(
            f"The {method['name']} of qvevri winemaking involves {method['description']}.",
            domain="winemaking",
            source_id=source_id,
            subdomain="qvevri",
            entities=method_entities,
            tags=base_tags + [method["name"].lower().replace(" ", "_")],
        ))
        if method.get("notes"):
            facts.append(_make_fact(
                method["notes"],
                domain="winemaking",
                source_id=source_id,
                subdomain="qvevri",
                entities=method_entities,
                tags=base_tags + [method["name"].lower().replace(" ", "_")],
            ))

    # Amber wine
    for amber_fact in QVEVRI_DATABASE["amber_wine"]:
        facts.append(_make_fact(
            amber_fact,
            domain="winemaking",
            source_id=source_id,
            subdomain="qvevri",
            entities=base_entities + [{"type": "wine_style", "name": "amber wine"}],
            tags=base_tags + ["amber_wine", "orange_wine"],
        ))

    # History
    for hist_fact in QVEVRI_DATABASE["history"]:
        facts.append(_make_fact(
            hist_fact,
            domain="winemaking",
            source_id=source_id,
            subdomain="qvevri",
            entities=base_entities,
            tags=base_tags + ["history"],
        ))

    # Modern revival
    for revival_fact in QVEVRI_DATABASE.get("modern_revival", []):
        facts.append(_make_fact(
            revival_fact,
            domain="winemaking",
            source_id=source_id,
            subdomain="qvevri",
            entities=base_entities,
            tags=base_tags + ["modern", "revival"],
        ))

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# FACT BUILDERS — Grape Varieties
# ═══════════════════════════════════════════════════════════════════════════════


def _build_grape_variety_facts(source_id: str) -> list[dict]:
    """Build facts about Hungarian and Georgian grape varieties."""
    facts = []

    for grape in GRAPE_VARIETY_DATABASE:
        name = grape["name"]
        country = grape["country"]
        entities = [{"type": "grape", "name": name}]
        base_tags = [country.lower(), name.lower().replace(" ", "_").replace("á", "a").replace("é", "e")]

        # Basic identity
        facts.append(_make_fact(
            f"{name} is a {grape['colour']} grape variety from {country}.",
            domain="grape_varieties",
            source_id=source_id,
            subdomain=country.lower(),
            entities=entities,
            tags=base_tags,
        ))

        # Area
        if grape.get("area_ha"):
            facts.append(_make_fact(
                f"{name} has approximately {grape['area_ha']:,} hectares planted in {country}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain=country.lower(),
                entities=entities,
                confidence=0.95,
                tags=base_tags + ["area", "statistics"],
            ))

        # Key region
        if grape.get("key_region"):
            region_entities = entities + [{"type": "region", "name": grape["key_region"]}]
            facts.append(_make_fact(
                f"{name} is primarily associated with the {grape['key_region']} wine region in {country}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain=country.lower(),
                entities=region_entities,
                tags=base_tags + [grape["key_region"].lower().replace("-", "_")],
            ))

        # Characteristics
        if grape.get("characteristics"):
            facts.append(_make_fact(
                f"{name} is characterised by {grape['characteristics']}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain=country.lower(),
                entities=entities,
                tags=base_tags + ["characteristics"],
            ))

        # Notes (main detailed fact)
        if grape.get("notes"):
            facts.append(_make_fact(
                grape["notes"],
                domain="grape_varieties",
                source_id=source_id,
                subdomain=country.lower(),
                entities=entities,
                tags=base_tags + ["notes"],
            ))

        # Synonyms
        if grape.get("synonyms") and len(grape["synonyms"]) > 0:
            synonyms_str = ", ".join(grape["synonyms"])
            facts.append(_make_fact(
                f"{name} is also known as {synonyms_str}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain=country.lower(),
                entities=entities,
                tags=base_tags + ["synonyms"],
            ))

        # Colour-specific fact
        if grape["colour"] == "red":
            facts.append(_make_fact(
                f"{name} is a red grape variety cultivated in {country}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain=country.lower(),
                entities=entities,
                tags=base_tags + ["red"],
            ))
        else:
            facts.append(_make_fact(
                f"{name} is a white grape variety cultivated in {country}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain=country.lower(),
                entities=entities,
                tags=base_tags + ["white"],
            ))

    # Cross-reference: find grapes that appear in multiple regions
    regions_all = HUNGARY_REGIONS + GEORGIA_REGIONS
    grape_region_map = defaultdict(list)
    for reg in regions_all:
        for g in reg.get("key_grapes", []):
            grape_region_map[g].append(reg["name"])

    for grape_name, regions in grape_region_map.items():
        if len(regions) > 1:
            regions_str = " and ".join(regions)
            facts.append(_make_fact(
                f"{grape_name} is grown in multiple wine regions: {regions_str}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="cross_reference",
                entities=[{"type": "grape", "name": grape_name}] + [{"type": "region", "name": r} for r in regions],
                tags=["cross_reference", grape_name.lower().replace(" ", "_")],
            ))

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# FACT BUILDERS — Classification Systems
# ═══════════════════════════════════════════════════════════════════════════════


def _build_classification_facts(source_id: str) -> list[dict]:
    """Build facts about Hungarian and Georgian wine classification systems."""
    facts = []

    # ── Hungary classification ──
    for stmt in CLASSIFICATION_DATABASE["hungary"]["system"]:
        facts.append(_make_fact(
            stmt,
            domain="wine_regions",
            source_id=source_id,
            subdomain="hungary_classification",
            entities=[{"type": "country", "name": "Hungary"}],
            tags=["hungary", "classification"],
        ))

    for rule in CLASSIFICATION_DATABASE["hungary"]["tokaj_rules"]:
        facts.append(_make_fact(
            rule,
            domain="winemaking",
            source_id=source_id,
            subdomain="tokaj",
            entities=[{"type": "region", "name": "Tokaj"}],
            tags=["hungary", "tokaj", "classification", "regulations"],
        ))

    # ── Georgia classification ──
    for stmt in CLASSIFICATION_DATABASE["georgia"]["system"]:
        facts.append(_make_fact(
            stmt,
            domain="wine_regions",
            source_id=source_id,
            subdomain="georgia_classification",
            entities=[{"type": "country", "name": "Georgia"}],
            tags=["georgia", "classification"],
        ))

    for appellation in CLASSIFICATION_DATABASE["georgia"]["appellations"]:
        app_name = appellation["name"]
        app_entities = [
            {"type": "appellation", "name": app_name},
            {"type": "country", "name": "Georgia"},
        ]
        if appellation.get("grape"):
            for g in appellation["grape"].split("/"):
                app_entities.append({"type": "grape", "name": g.strip()})

        facts.append(_make_fact(
            f"{app_name} is a Georgian protected appellation of origin for {appellation['type']} wine made from {appellation['grape']}.",
            domain="wine_regions",
            source_id=source_id,
            subdomain="georgia_classification",
            entities=app_entities,
            tags=["georgia", "appellation", app_name.lower()],
        ))

        if appellation.get("notes"):
            facts.append(_make_fact(
                appellation["notes"],
                domain="wine_regions",
                source_id=source_id,
                subdomain="georgia_classification",
                entities=app_entities,
                tags=["georgia", "appellation", app_name.lower()],
            ))

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# FACT BUILDERS — Additional Facts
# ═══════════════════════════════════════════════════════════════════════════════


def _build_additional_hungary_facts(source_id: str) -> list[dict]:
    """Build additional facts about Hungarian wine culture, regulations, and traditions."""
    facts = []
    entities = [{"type": "country", "name": "Hungary"}]

    for fact_text in ADDITIONAL_HUNGARY_FACTS:
        # Determine domain based on content
        domain = "wine_regions"
        subdomain = "hungary"
        if any(kw in fact_text.lower() for kw in ["sparkling", "blend", "ageing", "aged", "oak", "oxidative", "method"]):
            domain = "winemaking"
        elif any(kw in fact_text.lower() for kw in ["törley", "founded", "house"]):
            domain = "producers"
        elif any(kw in fact_text.lower() for kw in ["law", "categor", "classif", "tier", "academy"]):
            domain = "wine_regions"
            subdomain = "hungary_classification"
        elif any(kw in fact_text.lower() for kw in ["viticult", "climate", "continental", "soil"]):
            domain = "viticulture"

        facts.append(_make_fact(
            fact_text,
            domain=domain,
            source_id=source_id,
            subdomain=subdomain,
            entities=entities,
            tags=["hungary"],
        ))

    return facts


def _build_additional_georgia_facts(source_id: str) -> list[dict]:
    """Build additional facts about Georgian wine culture, archaeology, and traditions."""
    facts = []
    entities = [{"type": "country", "name": "Georgia"}]

    for fact_text in ADDITIONAL_GEORGIA_FACTS:
        # Determine domain based on content
        domain = "wine_regions"
        subdomain = "georgia"
        if any(kw in fact_text.lower() for kw in ["winemaking", "qvevri", "ferment", "method", "semi-sweet", "aged", "oak", "blend"]):
            domain = "winemaking"
        elif any(kw in fact_text.lower() for kw in ["grape variet", "indigenous", "cultivat"]):
            domain = "grape_varieties"
        elif any(kw in fact_text.lower() for kw in ["export", "market", "festival", "agency", "regulat"]):
            domain = "wine_business"
        elif any(kw in fact_text.lower() for kw in ["archaeolog", "artefact", "pottery", "6000 bc", "8,000"]):
            domain = "wine_regions"
            subdomain = "georgia_history"
        elif any(kw in fact_text.lower() for kw in ["caucasus", "rainfall", "valley", "terroir", "mountain"]):
            domain = "viticulture"
            subdomain = "georgia"

        facts.append(_make_fact(
            fact_text,
            domain=domain,
            source_id=source_id,
            subdomain=subdomain,
            entities=entities,
            tags=["georgia"],
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
        "hungary": _build_hungary_facts,
        "tokaj": _build_tokaj_facts,
        "georgia": _build_georgia_facts,
        "qvevri": _build_qvevri_facts,
        "grape": _build_grape_variety_facts,
        "classification": _build_classification_facts,
    }

    # Additional facts are included when running all or when their parent type is selected
    additional_map = {
        "hungary": _build_additional_hungary_facts,
        "georgia": _build_additional_georgia_facts,
    }

    if data_type and data_type in builders:
        all_facts = builders[data_type](source_id)
        # Also include additional facts for matching type
        if data_type in additional_map:
            all_facts.extend(additional_map[data_type](source_id))
    else:
        for builder in builders.values():
            all_facts.extend(builder(source_id))
        for builder in additional_map.values():
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
        click.echo(f"\n[DRY RUN] Would insert {len(facts)} facts from Hungary & Georgia Wine Reference Database")

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

    logger.info(f"Inserted {inserted} new facts from Hungary & Georgia (duplicates skipped)")
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
        "Hungary Regions": _build_hungary_facts,
        "Tokaj Detailed": _build_tokaj_facts,
        "Georgia Regions": _build_georgia_facts,
        "Qvevri Winemaking": _build_qvevri_facts,
        "Grape Varieties": _build_grape_variety_facts,
        "Classification": _build_classification_facts,
        "Additional Hungary": _build_additional_hungary_facts,
        "Additional Georgia": _build_additional_georgia_facts,
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
    type=click.Choice(["hungary", "tokaj", "georgia", "qvevri", "grape", "classification"]),
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
    """OenoBench Hungary & Georgia Wine Scraper — Regions, Tokaj, qvevri, grape varieties, and classifications."""
    logger.add("data/logs/hungary_georgia_{time}.log", rotation="10 MB")

    if list_sources:
        click.echo("\nAvailable data categories:")
        click.echo(f"  {'hungary':18s} — {len(HUNGARY_REGIONS)} Hungarian wine regions (climate, soil, elevation)")
        click.echo(f"  {'tokaj':18s} — Tokaj wine styles, {len(TOKAJ_DATABASE['first_growth_vineyards'])} first-growth vineyards, history")
        click.echo(f"  {'georgia':18s} — {len(GEORGIA_REGIONS)} Georgian wine regions (climate, soil, sub-zones)")
        click.echo(f"  {'qvevri':18s} — Qvevri winemaking methods, amber wine, history")
        click.echo(f"  {'grape':18s} — {len(GRAPE_VARIETY_DATABASE)} grape variety profiles (Hungary + Georgia)")
        click.echo(f"  {'classification':18s} — Hungarian OEM/OFJ and Georgian PDO systems")
        click.echo(f"\nKnowledge base coverage:")
        click.echo(f"  Hungarian regions:    {len(HUNGARY_REGIONS)}")
        click.echo(f"  Tokaj wine styles:    {len(TOKAJ_DATABASE['wine_styles'])}")
        click.echo(f"  Tokaj first-growths:  {len(TOKAJ_DATABASE['first_growth_vineyards'])}")
        click.echo(f"  Georgian regions:     {len(GEORGIA_REGIONS)}")
        click.echo(f"  Grape varieties:      {len(GRAPE_VARIETY_DATABASE)}")
        click.echo(f"  Georgian appellations: {len(CLASSIFICATION_DATABASE['georgia']['appellations'])}")
        click.echo(f"  Additional HU facts:  {len(ADDITIONAL_HUNGARY_FACTS)}")
        click.echo(f"  Additional GE facts:  {len(ADDITIONAL_GEORGIA_FACTS)}")
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
