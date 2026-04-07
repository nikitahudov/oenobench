"""
OenoBench — Canadian Wine Scraper

Extracts structured Canadian wine data covering Ontario, British Columbia,
Nova Scotia, Quebec, icewine production, grape varieties, and the VQA
classification system.

Focus areas: regional appellations (DVAs/sub-GIs), icewine regulations and
production, grape variety profiles (including cold-hardy hybrids), and the
VQA/DVA quality assurance system.

Usage:
    python -m src.scrapers.canada --all
    python -m src.scrapers.canada --type ontario
    python -m src.scrapers.canada --type bc
    python -m src.scrapers.canada --type other
    python -m src.scrapers.canada --type icewine
    python -m src.scrapers.canada --type grape
    python -m src.scrapers.canada --type classification
    python -m src.scrapers.canada --dry-run
    python -m src.scrapers.canada --validate
    python -m src.scrapers.canada --test-run
    python -m src.scrapers.canada --list
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
    "name": "Canadian Wine Reference Database",
    "url": "https://www.winesoontario.ca",
    "source_type": "reference",
    "tier": "tier_2_authoritative",
    "language": "en",
}


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Ontario Regions
# ═══════════════════════════════════════════════════════════════════════════════

ONTARIO_REGIONS = [
    {
        "name": "Niagara Peninsula",
        "province": "Ontario",
        "type": "DVA",
        "climate": "cool continental moderated by Lake Ontario and the Niagara Escarpment",
        "climate_details": "Lake Ontario acts as a heat sink, moderating winter cold and delaying spring bud break to reduce frost risk; the Niagara Escarpment deflects warm air currents back over vineyards, creating a beneficial mesoclimate",
        "soil_types": ["clay", "loam", "sand", "gravel"],
        "soil_details": "Glacial till deposited during the last ice age created a diverse soil mosaic; Beamsville Bench has clay-loam over limestone, while Niagara-on-the-Lake features heavier clay and silty-clay soils closer to the lake",
        "vineyard_area_ha": 5500,
        "key_grapes": ["Riesling", "Chardonnay", "Pinot Noir", "Cabernet Franc"],
        "sub_appellations": [
            "Niagara-on-the-Lake", "Twenty Mile Bench", "Beamsville Bench",
            "Short Hills Bench", "Vinemount Ridge", "Creek Shores",
            "Lincoln Lakeshore", "St. David's Bench", "Four Mile Creek",
            "Niagara Lakeshore", "Niagara River",
        ],
        "notable_facts": [
            "The Niagara Peninsula is Canada's largest wine-producing DVA, accounting for approximately 80% of Ontario's total wine production.",
            "Twenty Mile Bench sits on the Niagara Escarpment with limestone-rich soils that produce distinctive minerally Riesling and Chardonnay.",
            "The Beamsville Bench sub-appellation is situated on an elevated terrace of the Niagara Escarpment, benefiting from excellent air drainage that reduces frost risk.",
            "Short Hills Bench is one of the warmest sub-appellations within the Niagara Peninsula due to its protected position below the escarpment.",
            "Niagara-on-the-Lake, situated between Lake Ontario and the Niagara River, has a longer growing season than inland Niagara sites due to lake moderation.",
            "Vinemount Ridge is the highest sub-appellation in the Niagara Peninsula, with vineyards perched on the top of the escarpment receiving maximum wind exposure.",
            "Creek Shores sub-appellation in Niagara is characterized by alluvial soils deposited by Twenty Mile Creek, Jordan Harbour, and other waterways.",
            "Lincoln Lakeshore sub-appellation stretches along the Lake Ontario shore, where heavy clay soils and cool lake breezes produce structured whites and reds.",
            "St. David's Bench sub-appellation is known for red Bordeaux varieties, particularly Cabernet Franc and Merlot, due to its warm microclimate.",
            "Four Mile Creek sub-appellation benefits from both Lake Ontario and the Niagara Escarpment, creating a warm corridor suitable for full-bodied red wines.",
            "Niagara Lakeshore and Niagara River sub-appellations are the newest additions to the Niagara Peninsula's sub-appellation system.",
            "The Niagara Escarpment, a UNESCO World Biosphere Reserve, plays a critical role in viticulture by trapping warm air masses from Lake Ontario over the vineyard benchlands.",
        ],
    },
    {
        "name": "Prince Edward County",
        "province": "Ontario",
        "type": "DVA",
        "climate": "cool continental with strong Lake Ontario influence",
        "climate_details": "An island-like limestone plateau nearly surrounded by Lake Ontario, creating a maritime-influenced cool climate with significant wind exposure and shorter growing season than Niagara",
        "soil_types": ["limestone bedrock", "thin topsoil", "clay-over-limestone"],
        "soil_details": "Thin soils over flat Ordovician limestone bedrock define the terroir; some areas have only 15-30cm of soil over solid rock, producing low-vigor vines with concentrated fruit",
        "vineyard_area_ha": 700,
        "key_grapes": ["Pinot Noir", "Chardonnay", "Gamay"],
        "sub_appellations": [],
        "notable_facts": [
            "Prince Edward County was officially designated as Ontario's third DVA in 2007.",
            "The shallow limestone soils of Prince Edward County force vine roots to penetrate rock fissures, producing naturally low yields and concentrated flavors.",
            "Prince Edward County's exposed limestone bedrock gives wines a pronounced mineral character, particularly in Chardonnay and Pinot Noir.",
            "Many Prince Edward County vineyards require vine burial in winter to protect against temperatures that can drop below -25°C.",
            "Prince Edward County's wine industry is relatively young, with the first modern vineyards planted in the late 1990s.",
            "Prince Edward County is one of the few Canadian wine regions where Pinot Noir outperforms Cabernet Franc as the leading red variety.",
        ],
    },
    {
        "name": "Lake Erie North Shore",
        "province": "Ontario",
        "type": "DVA",
        "climate": "warm continental moderated by Lake Erie",
        "climate_details": "The southernmost Canadian wine region sits at approximately 42°N latitude, comparable to northern California and the Languedoc in France, receiving more heat units than Niagara",
        "soil_types": ["sandy loam", "clay", "gravel"],
        "soil_details": "Sandy loam soils with clay subsoil predominate, providing good drainage; the flat terrain near Lake Erie benefits from consistent lake breezes that moderate summer heat",
        "vineyard_area_ha": 500,
        "key_grapes": ["Cabernet Sauvignon", "Cabernet Franc", "Merlot", "Syrah"],
        "sub_appellations": [],
        "notable_facts": [
            "Lake Erie North Shore is Ontario's southernmost DVA and the southernmost designated wine region in Canada.",
            "The Lake Erie North Shore DVA receives the most growing degree days of any Ontario wine region, allowing successful ripening of later-maturing varieties like Cabernet Sauvignon.",
            "Lake Erie North Shore was the first officially designated DVA in Ontario, recognized in 1988.",
            "The Lake Erie North Shore region is the only Ontario DVA where Cabernet Sauvignon can reliably ripen in most vintages.",
        ],
    },
    {
        "name": "Pelee Island",
        "province": "Ontario",
        "type": "DVA sub-region",
        "climate": "warm continental, Canada's warmest wine region",
        "climate_details": "As Canada's southernmost inhabited island, Pelee Island benefits from the full moderating effect of Lake Erie, with the longest frost-free growing season in Canada",
        "soil_types": ["clay", "limestone", "sandy loam"],
        "soil_details": "Flat terrain with deep, fertile clay and limestone soils; the island's low elevation and lake exposure create a unique microclimate significantly warmer than the mainland",
        "vineyard_area_ha": 250,
        "key_grapes": ["Cabernet Sauvignon", "Cabernet Franc", "Merlot", "Chardonnay"],
        "sub_appellations": [],
        "notable_facts": [
            "Pelee Island is the warmest wine-growing area in Canada, located at the same latitude as the northern Rhone Valley in France.",
            "Pelee Island Winery, established in 1866, is one of Canada's oldest continuously operating wineries.",
        ],
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — British Columbia Regions
# ═══════════════════════════════════════════════════════════════════════════════

BC_REGIONS = [
    {
        "name": "Okanagan Valley",
        "province": "British Columbia",
        "type": "GI",
        "climate": "semi-arid continental with lake moderation",
        "climate_details": "A desert climate receiving only 250-350mm of annual rainfall, making irrigation essential; Okanagan Lake (135km long) moderates extremes, storing summer heat and releasing it in autumn to extend the growing season",
        "soil_types": ["glacial", "alluvial", "granite", "sand"],
        "soil_details": "Glacial deposits from retreating ice sheets created diverse soils ranging from deep sand and gravel benches to fine silty-clay lake-bottom sediments; volcanic and granitic soils appear in certain sub-regions",
        "vineyard_area_ha": 4000,
        "elevation_range": "300-600m",
        "key_grapes": ["Merlot", "Pinot Gris", "Chardonnay", "Pinot Noir", "Syrah", "Cabernet Sauvignon", "Riesling"],
        "sub_gis": [
            "Oliver", "Osoyoos", "Naramata Bench", "Summerland",
            "Kelowna", "Lake Country", "Peachland",
        ],
        "notable_facts": [
            "The Okanagan Valley is Canada's second-largest wine region after the Niagara Peninsula, producing approximately 84% of British Columbia's wine.",
            "The southern Okanagan around Oliver and Osoyoos is technically a desert, receiving less than 250mm of annual precipitation.",
            "The Black Sage Bench in the southern Okanagan is one of Canada's premier red wine sites, with deep sandy-gravel soils and intense sun exposure.",
            "The Golden Mile Bench was the first official sub-GI designated within the Okanagan Valley, recognized for its west-facing slopes and mineral-rich soils.",
            "Naramata Bench, on the east side of Okanagan Lake, benefits from cooling lake breezes and is known for producing elegant Pinot Noir and Chardonnay.",
            "Okanagan Lake acts as a thermal regulator, rarely freezing completely, which moderates vineyard temperatures along its 135-kilometer length.",
            "The Okanagan Valley has one of the widest diurnal temperature ranges of any North American wine region, with up to 20°C difference between day and night.",
        ],
    },
    {
        "name": "Similkameen Valley",
        "province": "British Columbia",
        "type": "GI",
        "climate": "hot, dry continental",
        "climate_details": "One of Canada's hottest and driest wine regions with intense summer heat; narrow valley orientation channels hot, dry winds through the region",
        "soil_types": ["alluvial", "gravel", "sand"],
        "soil_details": "Alluvial soils deposited by the Similkameen River with gravel and sand; the well-drained soils and dry climate have made the valley a pioneer of organic viticulture in Canada",
        "vineyard_area_ha": 500,
        "key_grapes": ["Merlot", "Cabernet Sauvignon", "Pinot Noir", "Pinot Gris"],
        "sub_gis": [],
        "notable_facts": [
            "The Similkameen Valley has the highest proportion of organic and biodynamic vineyards of any wine region in Canada.",
            "The Similkameen Valley's dry climate and well-drained alluvial soils naturally reduce disease pressure, favoring organic farming practices.",
        ],
    },
    {
        "name": "Fraser Valley",
        "province": "British Columbia",
        "type": "GI",
        "climate": "cool maritime",
        "climate_details": "Wet and cool maritime climate influenced by proximity to the Pacific Ocean; significant rainfall requires careful canopy management to prevent rot",
        "soil_types": ["alluvial", "clay", "silt"],
        "soil_details": "Rich alluvial soils deposited by the Fraser River; fertile but requiring drainage management due to high rainfall",
        "vineyard_area_ha": 100,
        "key_grapes": ["Pinot Noir", "Pinot Gris", "Bacchus", "Siegerrebe"],
        "sub_gis": [],
        "notable_facts": [
            "The Fraser Valley GI is British Columbia's closest wine region to the city of Vancouver.",
        ],
    },
    {
        "name": "Vancouver Island",
        "province": "British Columbia",
        "type": "GI",
        "climate": "mild maritime",
        "climate_details": "Mild maritime climate with moderate temperatures year-round; rain shadow areas on the east coast of the island receive significantly less precipitation than the west coast",
        "soil_types": ["glacial till", "sandy loam", "gravel"],
        "soil_details": "Diverse soils from glacial deposits; the Cowichan Valley on the east coast has well-drained gravelly loam suited to early-ripening grape varieties",
        "vineyard_area_ha": 200,
        "key_grapes": ["Pinot Gris", "Pinot Noir", "Ortega", "Maréchal Foch"],
        "sub_gis": [],
        "notable_facts": [
            "Vancouver Island's Cowichan Valley is one of Canada's mildest wine regions, with a growing season moderated by the Pacific Ocean.",
            "Ortega, a German-bred early-ripening white grape, has found a successful niche on Vancouver Island due to the region's short but mild growing season.",
        ],
    },
    {
        "name": "Gulf Islands",
        "province": "British Columbia",
        "type": "GI",
        "climate": "Mediterranean-like maritime",
        "climate_details": "The Gulf Islands sit in the rain shadow between Vancouver Island and the mainland, receiving less rainfall than surrounding areas and enjoying warm, dry summers reminiscent of a Mediterranean climate",
        "soil_types": ["rocky", "sandy loam", "clay"],
        "soil_details": "Thin, rocky soils over bedrock with pockets of sandy loam; the limited soil depth naturally restricts vine vigor",
        "vineyard_area_ha": 50,
        "key_grapes": ["Pinot Noir", "Pinot Gris", "Gewürztraminer"],
        "sub_gis": [],
        "notable_facts": [
            "The Gulf Islands GI has the smallest total vineyard area of any designated wine region in British Columbia, at approximately 50 hectares.",
            "The Gulf Islands benefit from a rain shadow effect created by Vancouver Island, receiving only 600-800mm of annual rainfall compared to over 2,000mm on the island's west coast.",
        ],
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Other Regions (Nova Scotia, Quebec)
# ═══════════════════════════════════════════════════════════════════════════════

OTHER_REGIONS = [
    {
        "name": "Nova Scotia",
        "province": "Nova Scotia",
        "climate": "Atlantic maritime",
        "climate_details": "Cool maritime climate moderated by the Atlantic Ocean and the Bay of Fundy; long but cool growing season with high humidity and significant fog",
        "soil_types": ["slate", "clay", "sandy loam", "gravel"],
        "soil_details": "Diverse soils from glacial deposits over a slate and granite bedrock; the Annapolis Valley has lighter sandy-loam soils with good drainage",
        "vineyard_area_ha": 400,
        "key_grapes": ["L'Acadie Blanc", "Seyval Blanc", "Tidal Bay blend grapes", "Marquette"],
        "notable_facts": [
            "Nova Scotia's Tidal Bay is the province's first regulated appellation, established in 2012 for blended white wines that must meet specific analytical standards.",
            "Tidal Bay wines must be made from approved grape varieties grown in Nova Scotia and display a crisp, aromatic character with balanced acidity.",
            "L'Acadie Blanc is a Canadian hybrid grape variety bred at Vineland, Ontario, that has become the signature grape of Nova Scotia.",
            "The Annapolis Valley is Nova Scotia's primary wine-growing area, protected by the North Mountain from harsh Atlantic weather.",
            "Nova Scotia's cool climate and long growing season produce white wines with naturally high acidity and fresh aromatic profiles.",
            "The Bay of Fundy's extreme tides create unique microclimates along Nova Scotia's coastline that moderate temperature extremes in nearby vineyards.",
        ],
    },
    {
        "name": "Quebec",
        "province": "Quebec",
        "climate": "extreme continental",
        "climate_details": "Harsh continental climate with severe winters reaching -30°C or colder; short but warm summers with long daylight hours; only cold-hardy hybrid grapes can survive without vine burial",
        "soil_types": ["clay", "sand", "glacial till", "shale"],
        "soil_details": "St. Lawrence Lowlands feature marine clay deposits; the Eastern Townships have glacial till and shale soils on rolling terrain",
        "vineyard_area_ha": 600,
        "key_grapes": ["Frontenac", "Marquette", "Seyval Blanc", "Vidal"],
        "notable_facts": [
            "Quebec is the birthplace of ice cider (cidre de glace), a dessert wine alternative made from frozen apple must, pioneered by Christian Barthomeuf in 1989.",
            "Quebec ice cider is produced either by cryoconcentration (allowing apples to freeze on the tree) or cryoextraction (pressing frozen apples), yielding an intensely sweet liquid with 130-180 g/L residual sugar.",
            "Quebec's wine industry relies heavily on cold-hardy hybrid grape varieties bred specifically to survive winters where temperatures regularly drop below -30°C.",
            "Frontenac, a hybrid grape developed by the University of Minnesota, is widely planted in Quebec for its ability to survive temperatures as low as -35°C.",
            "Marquette, another Minnesota hybrid (a grandchild of Pinot Noir), produces high-quality red wines in Quebec with good color, moderate tannin, and cherry fruit character.",
            "The Eastern Townships (Cantons-de-l'Est) south of Montreal is Quebec's most concentrated wine-growing area.",
            "Many Quebec vineyards practice vine burial (buttage) in autumn, mounding soil over the graft union and lower canes to protect against lethal winter freeze damage.",
        ],
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Icewine
# ═══════════════════════════════════════════════════════════════════════════════

ICEWINE_DATABASE = {
    "vqa_regulations": [
        "Under VQA regulations, Canadian icewine grapes must freeze naturally on the vine at a minimum temperature of -8°C.",
        "VQA icewine grapes are harvested at night or in early morning during winter, typically between December and January, while still frozen.",
        "VQA icewine must be pressed while grapes are still frozen, ensuring that only the concentrated sugar-rich juice is extracted.",
        "Canadian icewine typically yields only 15-25% of the juice volume compared to 65-75% for table wine, due to the extreme concentration from freezing.",
        "VQA icewine requires a minimum must weight of 35 degrees Brix at harvest.",
        "VQA icewine must be estate-bottled by the producing winery.",
        "VQA icewine must contain a minimum of 125 grams per liter of residual sugar.",
        "Canadian icewine typically has an alcohol level between 9% and 13% ABV.",
    ],
    "production_facts": [
        "Canada is the world's largest producer of icewine, with Ontario accounting for approximately 75% of global production.",
        "Icewine production is inherently risky: warm winters, rain, or bird and animal damage can destroy an entire crop before harvest temperatures are reached.",
        "Ontario's Niagara Peninsula produces the vast majority of Canadian icewine due to its reliable winter freezing temperatures combined with the protective influence of the Niagara Escarpment.",
        "British Columbia's Okanagan Valley is Canada's second-largest icewine-producing region, though volumes are much smaller than Ontario.",
        "The extreme concentration in icewine production means that approximately one entire vine's grape harvest is needed to produce a single 375ml bottle.",
        "Canadian icewine harvesting is done entirely by hand, as machine harvesting cannot handle frozen grapes without excessive berry damage.",
    ],
    "grape_facts": [
        "Vidal is the most widely used grape for Canadian icewine, valued for its thick skin that resists splitting during freeze-thaw cycles and its high natural acidity.",
        "Riesling icewine is considered the premium style, producing wines of exceptional complexity with intense floral aromatics, lemon curd, and honey notes.",
        "Cabernet Franc icewine is a rare Canadian specialty, producing rosé-colored dessert wine with strawberry and tropical fruit character.",
        "Vidal icewine typically displays pronounced aromas of apricot, peach, mango, and honey, with a lush, viscous texture balanced by bright acidity.",
        "Cabernet Franc red icewine is one of the rarest wine styles in the world, produced almost exclusively in Ontario's Niagara Peninsula.",
    ],
    "history_facts": [
        "Inniskillin's 1989 Vidal Icewine won the Grand Prix d'Honneur at Vinexpo in Bordeaux in 1991, launching Canadian icewine onto the international stage.",
        "The Vinexpo 1991 award for Inniskillin's icewine is widely credited with establishing Canada's reputation as a serious wine-producing country.",
        "Walter Hainle produced Canada's first commercial icewine in 1973 in the Okanagan Valley of British Columbia.",
        "Inniskillin, co-founded by Karl Kaiser and Donald Ziraldo in 1975, was the first Ontario winery granted a license since 1929.",
        "Canadian icewine is frequently counterfeited in Asian markets, prompting the Canadian government to pursue trademark protection for the term 'Icewine' internationally.",
    ],
    "aging_facts": [
        "Premium Canadian icewine has an aging potential of 10 to 20 years or more, developing increased complexity and darker amber color with bottle age.",
        "Young Vidal icewine displays bright tropical fruit and citrus notes, while aged examples develop caramel, marmalade, and dried apricot complexity.",
        "Riesling icewine tends to age more gracefully than Vidal, developing petrol and honey notes similar to aged dry Riesling but with intense sweetness.",
    ],
}


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Grape Varieties
# ═══════════════════════════════════════════════════════════════════════════════

GRAPE_VARIETY_DATABASE = [
    {
        "name": "Vidal",
        "color": "white",
        "type": "French hybrid",
        "parentage": "Ugni Blanc and Rayon d'Or",
        "area_ha": 1500,
        "primary_regions": ["Ontario"],
        "characteristics": "thick-skinned, cold-hardy, high acidity",
        "notable_facts": [
            "Vidal is a French hybrid grape created by crossing Ugni Blanc and Rayon d'Or, producing a thick-skinned variety ideally suited to Canadian icewine production.",
            "Vidal's thick skin allows it to remain intact through multiple freeze-thaw cycles on the vine, making it the most reliable grape for icewine production.",
            "Vidal is the most widely planted icewine grape in Canada, with approximately 1,500 hectares under vine, primarily in Ontario's Niagara Peninsula.",
        ],
    },
    {
        "name": "Riesling",
        "color": "white",
        "type": "vinifera",
        "parentage": None,
        "area_ha": 1200,
        "primary_regions": ["Ontario"],
        "characteristics": "aromatic, high acidity, versatile",
        "notable_facts": [
            "Riesling is one of Ontario's most important white grape varieties, producing styles ranging from bone-dry to icewine, with approximately 1,200 hectares planted.",
            "Ontario Riesling is often compared stylistically to Alsatian and German Riesling due to the cool climate and limestone-influenced soils.",
            "Niagara Peninsula Riesling is particularly acclaimed from the Bench sub-appellations, where escarpment limestone soils contribute mineral complexity.",
        ],
    },
    {
        "name": "Chardonnay",
        "color": "white",
        "type": "vinifera",
        "parentage": None,
        "area_ha": 2500,
        "primary_regions": ["Ontario", "British Columbia"],
        "characteristics": "versatile, still and sparkling",
        "notable_facts": [
            "Chardonnay is the most widely planted grape variety in Canada with approximately 2,500 hectares, grown in both Ontario and British Columbia.",
            "Canadian Chardonnay is produced in both oaked and unoaked styles, with Burgundian-style examples emerging from Prince Edward County and the Okanagan.",
            "Prince Edward County Chardonnay benefits from limestone-rich soils and cool climate conditions, producing wines with pronounced mineral character and crisp acidity.",
        ],
    },
    {
        "name": "Pinot Noir",
        "color": "red",
        "type": "vinifera",
        "parentage": None,
        "area_ha": 1800,
        "primary_regions": ["Ontario", "British Columbia"],
        "characteristics": "cool-climate expression, light to medium body",
        "notable_facts": [
            "Pinot Noir is grown across approximately 1,800 hectares in Canada, primarily in Prince Edward County, the Niagara Peninsula, and the Okanagan Valley.",
            "Prince Edward County has established itself as one of Canada's most promising Pinot Noir regions, with limestone soils producing Burgundy-inspired wines.",
            "Okanagan Pinot Noir tends to be riper and more full-bodied than Ontario examples due to the warmer continental climate and higher sun exposure.",
        ],
    },
    {
        "name": "Cabernet Franc",
        "color": "red",
        "type": "vinifera",
        "parentage": None,
        "area_ha": 1200,
        "primary_regions": ["Ontario"],
        "characteristics": "Ontario's best-adapted Bordeaux red, lighter than Bordeaux style",
        "notable_facts": [
            "Cabernet Franc is widely considered Ontario's most successful red vinifera grape, with approximately 1,200 hectares planted, primarily in the Niagara Peninsula.",
            "Ontario Cabernet Franc produces lighter-bodied wines than Bordeaux examples, with characteristic red berry, green pepper, and violet aromatics.",
            "Cabernet Franc's relatively early ripening makes it better suited to Ontario's cool climate than the later-ripening Cabernet Sauvignon.",
        ],
    },
    {
        "name": "Gamay",
        "color": "red",
        "type": "vinifera",
        "parentage": None,
        "area_ha": 400,
        "primary_regions": ["Ontario"],
        "characteristics": "light-bodied, Beaujolais-style",
        "notable_facts": [
            "Gamay is grown on approximately 400 hectares in Ontario, producing light-bodied, fruit-forward red wines in a Beaujolais-like style.",
            "Prince Edward County and the Niagara Peninsula are the primary Gamay-growing areas in Canada, with some producers using carbonic maceration in the Beaujolais tradition.",
        ],
    },
    {
        "name": "Pinot Gris",
        "color": "white",
        "type": "vinifera",
        "parentage": None,
        "area_ha": 1000,
        "primary_regions": ["British Columbia"],
        "characteristics": "BC's most planted white, crisp and aromatic",
        "notable_facts": [
            "Pinot Gris is the most widely planted white grape variety in British Columbia with approximately 1,000 hectares, producing crisp, aromatic wines.",
            "Okanagan Valley Pinot Gris ranges from lean and mineral-driven in cooler northern sites to richer and more tropical from warmer southern vineyards.",
        ],
    },
    {
        "name": "Merlot",
        "color": "red",
        "type": "vinifera",
        "parentage": None,
        "area_ha": 800,
        "primary_regions": ["British Columbia"],
        "characteristics": "ripe, fruit-forward in Okanagan warmth",
        "notable_facts": [
            "Merlot is one of British Columbia's most important red grape varieties with approximately 800 hectares, concentrated in the warm southern Okanagan.",
            "Okanagan Merlot benefits from the region's intense summer heat and wide diurnal temperature range, producing wines with ripe dark fruit and moderate tannins.",
        ],
    },
    {
        "name": "Syrah",
        "color": "red",
        "type": "vinifera",
        "parentage": None,
        "area_ha": 400,
        "primary_regions": ["British Columbia"],
        "characteristics": "warm-climate style from southern Okanagan",
        "notable_facts": [
            "Syrah is grown on approximately 400 hectares in the southern Okanagan Valley, primarily around Oliver and Osoyoos, where summer heat accumulation rivals warmer regions worldwide.",
            "Okanagan Syrah has drawn comparisons to Northern Rhone wines due to the region's combination of continental heat, mineral soils, and significant diurnal temperature variation.",
        ],
    },
    {
        "name": "Baco Noir",
        "color": "red",
        "type": "French hybrid",
        "parentage": "Folle Blanche and Vitis riparia",
        "area_ha": 300,
        "primary_regions": ["Ontario"],
        "characteristics": "dark-colored, cold-hardy, full-bodied for a hybrid",
        "notable_facts": [
            "Baco Noir is a French hybrid grape grown on approximately 300 hectares in Ontario, producing deeply colored, full-bodied red wines.",
            "Baco Noir was developed by French hybridizer Francois Baco in the 19th century as a cross between Folle Blanche and the wild American vine Vitis riparia.",
        ],
    },
    {
        "name": "Maréchal Foch",
        "color": "red",
        "type": "French hybrid",
        "parentage": "Millardet et Grasset 101-14 and Goldriesling",
        "area_ha": 200,
        "primary_regions": ["Ontario", "British Columbia", "Quebec"],
        "characteristics": "extremely cold-hardy, dark-colored, earthy",
        "notable_facts": [
            "Maréchal Foch is a cold-hardy French hybrid grape grown on approximately 200 hectares across Canada, capable of surviving extreme winter cold without vine burial.",
            "Maréchal Foch produces deeply colored red wines with earthy, gamey character and has found renewed interest among natural winemakers in Canada.",
        ],
    },
    {
        "name": "L'Acadie Blanc",
        "color": "white",
        "type": "Canadian hybrid",
        "parentage": "Cascade and Seyve-Villard 14-287",
        "area_ha": None,
        "primary_regions": ["Nova Scotia"],
        "characteristics": "crisp, high acidity, cold-hardy",
        "notable_facts": [
            "L'Acadie Blanc is a Canadian hybrid grape variety bred at the Vineland Research Station in Ontario, which has become the signature white grape of Nova Scotia.",
            "L'Acadie Blanc produces crisp, high-acid white wines and is a key component of Nova Scotia's Tidal Bay appellation blend.",
            "L'Acadie Blanc thrives in Nova Scotia's cool Atlantic maritime climate, where its natural high acidity and cold hardiness are valuable assets.",
        ],
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Classification System
# ═══════════════════════════════════════════════════════════════════════════════

CLASSIFICATION_DATABASE = {
    "vqa_system": [
        "The Vintners Quality Alliance (VQA) is Canada's appellation of origin system, establishing standards for grape growing and winemaking in Ontario and British Columbia.",
        "VQA regulations require that wines labeled with a single grape variety must contain at least 85% of that variety.",
        "VQA regulations require that wines labeled with a single DVA (Designated Viticultural Area) must contain at least 85% of grapes from that area.",
        "VQA regulations require that wines labeled with a single vintage year must contain at least 95% of grapes from that vintage.",
        "The VQA system was established in Ontario in 1988 and in British Columbia in 1990, modeled after European appellation systems.",
        "VQA wines must be made entirely from grapes grown in a designated Canadian viticultural area and must pass analytical and sensory evaluation panels.",
    ],
    "dva_system": [
        "Designated Viticultural Areas (DVAs) are the Canadian equivalent of European appellations of origin, defining specific wine-growing regions.",
        "Ontario has three DVAs: Niagara Peninsula, Prince Edward County, and Lake Erie North Shore.",
        "British Columbia uses Geographical Indications (GIs) rather than DVAs, with the Okanagan Valley, Similkameen Valley, Fraser Valley, Vancouver Island, and Gulf Islands among its designated regions.",
        "British Columbia has nine officially recognized sub-GIs within the Okanagan Valley and Similkameen Valley.",
    ],
    "regulatory_bodies": [
        "The VQA Ontario is the regulatory body that administers Ontario's appellation of origin system and conducts wine quality testing.",
        "The BC Wine Institute (BCWI) administers British Columbia's Geographical Indication system and promotes BC wines domestically and internationally.",
        "The Canadian Vintners Association represents the interests of Canada's wine industry at the federal level.",
    ],
    "labeling_rules": [
        "Canadian VQA wines may not contain any imported wine or grape must, ensuring all wine is produced from 100% Canadian-grown grapes.",
        "The term 'Icewine' (one word) is a regulated term in Canada, legally restricted to wines meeting strict VQA or equivalent provincial standards.",
        "Canadian wine labels may use the term 'Estate Bottled' only when all grapes are grown, vinified, and bottled at a single winery estate.",
    ],
}


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Unique / General Facts
# ═══════════════════════════════════════════════════════════════════════════════

UNIQUE_FACTS = [
    "Canada is the world's largest producer of icewine, a distinction earned through its unique combination of reliable winter cold and sophisticated viticultural expertise.",
    "Canada's extreme continental climate presents viticultural challenges including winter temperatures that can reach -30°C, requiring vine burial or cold-hardy grape selection in the coldest regions.",
    "First Nations peoples made wines from wild grapes (Vitis riparia) for centuries before European settlement in Canada.",
    "Hybrid grapes are essential in eastern Canada due to extreme winter cold, as most European Vitis vinifera varieties cannot survive temperatures below -25°C without protection.",
    "Canada's wine industry has grown rapidly since the 1980s, evolving from a predominantly hybrid-grape, sweet-wine industry to one producing internationally recognized vinifera wines and icewine.",
    "The Canada-US Free Trade Agreement of 1988 forced a modernization of the Canadian wine industry by eliminating protectionist tariffs that had shielded domestic producers from competition.",
    "Canada's total vineyard area is approximately 12,000 hectares, making it a relatively small wine-producing country by global standards.",
]


# ═══════════════════════════════════════════════════════════════════════════════
# FACT HELPERS
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
    """Register and return the Canadian Wine source ID."""
    return ensure_source(
        name=SOURCE["name"],
        url=SOURCE["url"],
        source_type=SOURCE["source_type"],
        tier=SOURCE["tier"],
        language=SOURCE["language"],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# FACT BUILDERS — Ontario
# ═══════════════════════════════════════════════════════════════════════════════


def _build_ontario_facts(source_id: str) -> list[dict]:
    """Build facts about Ontario wine regions (Niagara, PEC, Lake Erie)."""
    facts = []

    for region in ONTARIO_REGIONS:
        name = region["name"]
        entities = [{"type": "region", "name": name}]
        base_tags = ["canada", "ontario", name.lower().replace(" ", "_")]

        # Climate
        facts.append(_make_fact(
            f"The {name} wine region in Ontario has a {region['climate']} climate.",
            domain="wine_regions",
            source_id=source_id,
            subdomain="canada_ontario",
            entities=entities,
            tags=base_tags + ["climate"],
        ))

        if region.get("climate_details"):
            facts.append(_make_fact(
                f"{region['climate_details']}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="canada_ontario",
                entities=entities,
                tags=base_tags + ["climate"],
            ))

        # Soil
        if region.get("soil_types"):
            soil_list = ", ".join(region["soil_types"])
            facts.append(_make_fact(
                f"The predominant soil types in the {name} wine region include {soil_list}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="canada_ontario",
                entities=entities,
                tags=base_tags + ["soil", "terroir"],
            ))

        if region.get("soil_details"):
            facts.append(_make_fact(
                f"{region['soil_details']}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="canada_ontario",
                entities=entities,
                tags=base_tags + ["soil", "terroir"],
            ))

        # Vineyard area
        if region.get("vineyard_area_ha"):
            facts.append(_make_fact(
                f"The {name} wine region has approximately {region['vineyard_area_ha']:,} hectares of vineyard.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="canada_ontario",
                entities=entities,
                confidence=0.95,
                tags=base_tags + ["statistics"],
            ))

        # Key grapes
        if region.get("key_grapes"):
            grapes_str = ", ".join(region["key_grapes"])
            grape_entities = entities + [{"type": "grape", "name": g} for g in region["key_grapes"]]
            facts.append(_make_fact(
                f"The principal grape varieties of the {name} wine region include {grapes_str}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="canada_ontario",
                entities=grape_entities,
                tags=base_tags + ["grapes"],
            ))

        # Sub-appellations
        if region.get("sub_appellations"):
            sub_str = ", ".join(region["sub_appellations"])
            facts.append(_make_fact(
                f"The {name} DVA contains {len(region['sub_appellations'])} recognized sub-appellations: {sub_str}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="canada_ontario",
                entities=entities,
                tags=base_tags + ["appellations"],
            ))

        # Type / DVA status
        if region.get("type"):
            facts.append(_make_fact(
                f"{name} is designated as a {region['type']} within the Canadian VQA system.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="canada_ontario",
                entities=entities,
                tags=base_tags + ["classification", "vqa"],
            ))

        # Notable facts
        for nf in region.get("notable_facts", []):
            facts.append(_make_fact(
                nf,
                domain="wine_regions",
                source_id=source_id,
                subdomain="canada_ontario",
                entities=entities,
                tags=base_tags,
            ))

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# FACT BUILDERS — British Columbia
# ═══════════════════════════════════════════════════════════════════════════════


def _build_bc_facts(source_id: str) -> list[dict]:
    """Build facts about BC wine regions (Okanagan, Similkameen, islands)."""
    facts = []

    for region in BC_REGIONS:
        name = region["name"]
        entities = [{"type": "region", "name": name}]
        base_tags = ["canada", "british_columbia", name.lower().replace(" ", "_")]

        # Climate
        facts.append(_make_fact(
            f"The {name} wine region in British Columbia has a {region['climate']} climate.",
            domain="wine_regions",
            source_id=source_id,
            subdomain="canada_bc",
            entities=entities,
            tags=base_tags + ["climate"],
        ))

        if region.get("climate_details"):
            facts.append(_make_fact(
                f"{region['climate_details']}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="canada_bc",
                entities=entities,
                tags=base_tags + ["climate"],
            ))

        # Soil
        if region.get("soil_types"):
            soil_list = ", ".join(region["soil_types"])
            facts.append(_make_fact(
                f"The predominant soil types in the {name} wine region include {soil_list}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="canada_bc",
                entities=entities,
                tags=base_tags + ["soil", "terroir"],
            ))

        if region.get("soil_details"):
            facts.append(_make_fact(
                f"{region['soil_details']}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="canada_bc",
                entities=entities,
                tags=base_tags + ["soil", "terroir"],
            ))

        # Vineyard area
        if region.get("vineyard_area_ha"):
            facts.append(_make_fact(
                f"The {name} wine region has approximately {region['vineyard_area_ha']:,} hectares of vineyard.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="canada_bc",
                entities=entities,
                confidence=0.95,
                tags=base_tags + ["statistics"],
            ))

        # Elevation
        if region.get("elevation_range"):
            facts.append(_make_fact(
                f"Vineyards in the {name} wine region are planted at elevations ranging from {region['elevation_range']}.",
                domain="viticulture",
                source_id=source_id,
                subdomain="canada_bc",
                entities=entities,
                tags=base_tags + ["elevation"],
            ))

        # Key grapes
        if region.get("key_grapes"):
            grapes_str = ", ".join(region["key_grapes"])
            grape_entities = entities + [{"type": "grape", "name": g} for g in region["key_grapes"]]
            facts.append(_make_fact(
                f"The principal grape varieties of the {name} wine region include {grapes_str}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="canada_bc",
                entities=grape_entities,
                tags=base_tags + ["grapes"],
            ))

        # Sub-GIs
        if region.get("sub_gis"):
            sub_str = ", ".join(region["sub_gis"])
            facts.append(_make_fact(
                f"The {name} GI contains recognized sub-GIs including {sub_str}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="canada_bc",
                entities=entities,
                tags=base_tags + ["appellations"],
            ))

        # GI type
        facts.append(_make_fact(
            f"{name} is designated as a {region['type']} within British Columbia's wine classification system.",
            domain="wine_regions",
            source_id=source_id,
            subdomain="canada_bc",
            entities=entities,
            tags=base_tags + ["classification"],
        ))

        # Notable facts
        for nf in region.get("notable_facts", []):
            facts.append(_make_fact(
                nf,
                domain="wine_regions",
                source_id=source_id,
                subdomain="canada_bc",
                entities=entities,
                tags=base_tags,
            ))

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# FACT BUILDERS — Other Regions (Nova Scotia, Quebec)
# ═══════════════════════════════════════════════════════════════════════════════


def _build_other_region_facts(source_id: str) -> list[dict]:
    """Build facts about Nova Scotia and Quebec wine regions."""
    facts = []

    for region in OTHER_REGIONS:
        name = region["name"]
        province = region["province"]
        entities = [{"type": "region", "name": name}]
        base_tags = ["canada", province.lower().replace(" ", "_"), name.lower().replace(" ", "_")]

        # Climate
        facts.append(_make_fact(
            f"The {name} wine region has a {region['climate']} climate.",
            domain="wine_regions",
            source_id=source_id,
            subdomain=f"canada_{province.lower().replace(' ', '_')}",
            entities=entities,
            tags=base_tags + ["climate"],
        ))

        if region.get("climate_details"):
            facts.append(_make_fact(
                f"{region['climate_details']}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain=f"canada_{province.lower().replace(' ', '_')}",
                entities=entities,
                tags=base_tags + ["climate"],
            ))

        # Soil
        if region.get("soil_types"):
            soil_list = ", ".join(region["soil_types"])
            facts.append(_make_fact(
                f"The predominant soil types in the {name} wine region include {soil_list}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain=f"canada_{province.lower().replace(' ', '_')}",
                entities=entities,
                tags=base_tags + ["soil", "terroir"],
            ))

        if region.get("soil_details"):
            facts.append(_make_fact(
                f"{region['soil_details']}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain=f"canada_{province.lower().replace(' ', '_')}",
                entities=entities,
                tags=base_tags + ["soil", "terroir"],
            ))

        # Vineyard area
        if region.get("vineyard_area_ha"):
            facts.append(_make_fact(
                f"The {name} wine region has approximately {region['vineyard_area_ha']:,} hectares of vineyard.",
                domain="wine_regions",
                source_id=source_id,
                subdomain=f"canada_{province.lower().replace(' ', '_')}",
                entities=entities,
                confidence=0.95,
                tags=base_tags + ["statistics"],
            ))

        # Key grapes
        if region.get("key_grapes"):
            grapes_str = ", ".join(region["key_grapes"])
            grape_entities = entities + [{"type": "grape", "name": g} for g in region["key_grapes"]]
            facts.append(_make_fact(
                f"The principal grape varieties of the {name} wine region include {grapes_str}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain=f"canada_{province.lower().replace(' ', '_')}",
                entities=grape_entities,
                tags=base_tags + ["grapes"],
            ))

        # Notable facts
        for nf in region.get("notable_facts", []):
            facts.append(_make_fact(
                nf,
                domain="wine_regions",
                source_id=source_id,
                subdomain=f"canada_{province.lower().replace(' ', '_')}",
                entities=entities,
                tags=base_tags,
            ))

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# FACT BUILDERS — Icewine
# ═══════════════════════════════════════════════════════════════════════════════


def _build_icewine_facts(source_id: str) -> list[dict]:
    """Build facts about icewine regulations, production, and history."""
    facts = []
    base_tags = ["canada", "icewine"]
    entities = [{"type": "wine_style", "name": "Icewine"}]

    for section_key, section_facts in ICEWINE_DATABASE.items():
        # Determine domain and subdomain based on section
        if section_key == "vqa_regulations":
            domain = "winemaking"
            subdomain = "icewine_regulations"
            section_tags = base_tags + ["vqa", "regulations"]
        elif section_key == "production_facts":
            domain = "winemaking"
            subdomain = "icewine_production"
            section_tags = base_tags + ["production"]
        elif section_key == "grape_facts":
            domain = "grape_varieties"
            subdomain = "icewine_grapes"
            section_tags = base_tags + ["grapes"]
        elif section_key == "history_facts":
            domain = "wine_business"
            subdomain = "icewine_history"
            section_tags = base_tags + ["history"]
        elif section_key == "aging_facts":
            domain = "winemaking"
            subdomain = "icewine_aging"
            section_tags = base_tags + ["aging"]
        else:
            domain = "winemaking"
            subdomain = "icewine"
            section_tags = base_tags

        for fact_text in section_facts:
            facts.append(_make_fact(
                fact_text,
                domain=domain,
                source_id=source_id,
                subdomain=subdomain,
                entities=entities,
                tags=section_tags,
            ))

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# FACT BUILDERS — Grape Varieties
# ═══════════════════════════════════════════════════════════════════════════════


def _build_grape_variety_facts(source_id: str) -> list[dict]:
    """Build facts about Canadian grape varieties."""
    facts = []

    for grape in GRAPE_VARIETY_DATABASE:
        name = grape["name"]
        entities = [{"type": "grape", "name": name}]
        base_tags = ["canada", name.lower().replace(" ", "_").replace("'", "")]

        # Type / parentage
        if grape.get("type"):
            type_desc = grape["type"]
            if grape.get("parentage"):
                facts.append(_make_fact(
                    f"{name} is a {type_desc} grape variety, a cross of {grape['parentage']}.",
                    domain="grape_varieties",
                    source_id=source_id,
                    subdomain="canada_grapes",
                    entities=entities,
                    tags=base_tags + ["parentage"],
                ))
            else:
                facts.append(_make_fact(
                    f"{name} is a {type_desc} grape variety grown in Canada.",
                    domain="grape_varieties",
                    source_id=source_id,
                    subdomain="canada_grapes",
                    entities=entities,
                    tags=base_tags,
                ))

        # Color
        facts.append(_make_fact(
            f"{name} is a {grape['color']} grape variety.",
            domain="grape_varieties",
            source_id=source_id,
            subdomain="canada_grapes",
            entities=entities,
            tags=base_tags + [grape["color"]],
        ))

        # Area
        if grape.get("area_ha"):
            facts.append(_make_fact(
                f"{name} is planted on approximately {grape['area_ha']:,} hectares in Canada.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="canada_grapes",
                entities=entities,
                confidence=0.95,
                tags=base_tags + ["statistics"],
            ))

        # Primary regions
        if grape.get("primary_regions"):
            regions_str = " and ".join(grape["primary_regions"])
            facts.append(_make_fact(
                f"{name} is primarily grown in {regions_str} within Canada.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="canada_grapes",
                entities=entities + [{"type": "region", "name": r} for r in grape["primary_regions"]],
                tags=base_tags + ["regions"],
            ))

        # Characteristics
        if grape.get("characteristics"):
            facts.append(_make_fact(
                f"Key characteristics of {name} in Canada include: {grape['characteristics']}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="canada_grapes",
                entities=entities,
                tags=base_tags + ["characteristics"],
            ))

        # Notable facts
        for nf in grape.get("notable_facts", []):
            facts.append(_make_fact(
                nf,
                domain="grape_varieties",
                source_id=source_id,
                subdomain="canada_grapes",
                entities=entities,
                tags=base_tags,
            ))

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# FACT BUILDERS — Classification (VQA, DVA)
# ═══════════════════════════════════════════════════════════════════════════════


def _build_classification_facts(source_id: str) -> list[dict]:
    """Build facts about VQA, DVA, and Canadian wine classification."""
    facts = []
    base_tags = ["canada", "classification"]
    entities = [{"type": "classification", "name": "VQA"}]

    for section_key, section_facts in CLASSIFICATION_DATABASE.items():
        if section_key == "vqa_system":
            subdomain = "canada_vqa"
            section_tags = base_tags + ["vqa"]
        elif section_key == "dva_system":
            subdomain = "canada_dva"
            section_tags = base_tags + ["dva"]
        elif section_key == "regulatory_bodies":
            subdomain = "canada_regulatory"
            section_tags = base_tags + ["regulatory"]
        elif section_key == "labeling_rules":
            subdomain = "canada_labeling"
            section_tags = base_tags + ["labeling"]
        else:
            subdomain = "canada_classification"
            section_tags = base_tags

        for fact_text in section_facts:
            facts.append(_make_fact(
                fact_text,
                domain="wine_business",
                source_id=source_id,
                subdomain=subdomain,
                entities=entities,
                tags=section_tags,
            ))

    # Unique / general facts
    for fact_text in UNIQUE_FACTS:
        facts.append(_make_fact(
            fact_text,
            domain="wine_regions",
            source_id=source_id,
            subdomain="canada_general",
            entities=[{"type": "country", "name": "Canada"}],
            tags=["canada", "general"],
        ))

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# ORCHESTRATION
# ═══════════════════════════════════════════════════════════════════════════════


def _build_all_facts(source_id: str, data_type: str = None) -> list[dict]:
    """Build all facts, optionally filtered by type."""
    all_facts = []

    builders = {
        "ontario": _build_ontario_facts,
        "bc": _build_bc_facts,
        "other": _build_other_region_facts,
        "icewine": _build_icewine_facts,
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
        click.echo(f"\n[DRY RUN] Would insert {len(facts)} facts from Canadian Wine Reference Database")

        # Show breakdown by domain/subdomain
        domain_counts = defaultdict(int)
        for f in facts:
            domain_counts[f["domain"]] += 1
        click.echo("\nDomain breakdown:")
        for d, c in sorted(domain_counts.items()):
            click.echo(f"  {d:25s}: {c}")

        subdomain_counts = defaultdict(int)
        for f in facts:
            sub = f.get("subdomain") or "(none)"
            subdomain_counts[sub] += 1
        click.echo("\nSubdomain breakdown:")
        for s, c in sorted(subdomain_counts.items()):
            click.echo(f"  {s:35s}: {c}")

        # Show samples
        click.echo(f"\nSample facts ({min(15, len(facts))} random):")
        for i, f in enumerate(random.sample(facts, min(15, len(facts))), 1):
            click.echo(f'  {i:2d}. "{f["fact_text"]}"')

        return summary

    inserted = insert_facts_batch(facts)
    summary["total_inserted"] = inserted

    logger.info(f"Inserted {inserted} new facts from Canadian Wine Reference Database (duplicates skipped)")
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
        "Ontario Regions": _build_ontario_facts,
        "BC Regions": _build_bc_facts,
        "Other Regions": _build_other_region_facts,
        "Icewine": _build_icewine_facts,
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
    type=click.Choice(["ontario", "bc", "other", "icewine", "grape", "classification"]),
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
    """OenoBench Canadian Wine Scraper — Regions, icewine, grape varieties, and VQA classification."""
    logger.add("data/logs/canada_{time}.log", rotation="10 MB")

    if list_sources:
        click.echo("\nAvailable data categories:")
        click.echo(f"  {'ontario':16s} — Ontario wine regions (Niagara, PEC, Lake Erie, Pelee Island)")
        click.echo(f"  {'bc':16s} — British Columbia wine regions (Okanagan, Similkameen, islands)")
        click.echo(f"  {'other':16s} — Nova Scotia and Quebec wine regions")
        click.echo(f"  {'icewine':16s} — Icewine regulations, production, history, and aging")
        click.echo(f"  {'grape':16s} — {len(GRAPE_VARIETY_DATABASE)} grape variety profiles")
        click.echo(f"  {'classification':16s} — VQA, DVA, and regulatory framework")
        click.echo(f"\nKnowledge base coverage:")
        click.echo(f"  Ontario regions:    {len(ONTARIO_REGIONS)}")
        click.echo(f"  BC regions:         {len(BC_REGIONS)}")
        click.echo(f"  Other regions:      {len(OTHER_REGIONS)}")
        click.echo(f"  Icewine sections:   {len(ICEWINE_DATABASE)}")
        click.echo(f"  Grape varieties:    {len(GRAPE_VARIETY_DATABASE)}")
        click.echo(f"  Classification:     {len(CLASSIFICATION_DATABASE)} sections")
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
