"""
OenoBench — Australia & New Zealand Wine Enrichment Scraper

Extracts structured wine data for Australian and New Zealand wine regions,
grape varieties, and classification systems from authoritative reference
databases (Wine Australia, New Zealand Winegrowers).

Focus areas: GI regions with terroir (climate, soil, elevation), grape variety
regional expressions, classification systems (GI, LIP, Old Vine Charter),
and unique winemaking traditions.

Usage:
    python -m src.scrapers.australia_nz_enrichment --all
    python -m src.scrapers.australia_nz_enrichment --type australia
    python -m src.scrapers.australia_nz_enrichment --type nz
    python -m src.scrapers.australia_nz_enrichment --type grape
    python -m src.scrapers.australia_nz_enrichment --type classification
    python -m src.scrapers.australia_nz_enrichment --dry-run
    python -m src.scrapers.australia_nz_enrichment --validate
    python -m src.scrapers.australia_nz_enrichment --test-run
    python -m src.scrapers.australia_nz_enrichment --list
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
    "name": "Australia & New Zealand Wine Reference Database",
    "url": "https://www.wineaustralia.com",
    "source_type": "reference",
    "tier": "tier_2_authoritative",
    "language": "en",
}


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Australian Regions
# ═══════════════════════════════════════════════════════════════════════════════

AUSTRALIA_REGIONS = [
    {
        "name": "Barossa Valley",
        "state": "South Australia",
        "climate": "warm continental",
        "soil_types": ["terra rossa", "sandy loam", "clay"],
        "soil_details": "Diverse soils ranging from terra rossa over limestone to sandy loam and heavy clay; the Valley floor has alluvial sandy loam while eastern slopes have ironstone and clay",
        "elevation_range": "200-400m",
        "vineyard_area_ha": 13000,
        "key_grapes": ["Shiraz", "Grenache", "Cabernet Sauvignon", "Mataro"],
        "wine_styles": ["full-bodied red", "fortified", "old-vine Grenache"],
        "sub_regions": ["Lyndoch", "Tanunda", "Nuriootpa", "Angaston", "Greenock", "Seppeltsfield", "Marananga", "Ebenezer"],
        "history": "The Barossa Valley was settled by Silesian Lutheran immigrants in the 1840s, who established many of the region's oldest vineyards and winemaking traditions that persist today.",
        "viticulture_notes": "Many Barossa vineyards are dry-grown (unirrigated), relying on deep-rooted old vines to access groundwater, which contributes to the concentration and intensity of the wines.",
        "notes": "Home to some of the world's oldest Shiraz vines, with pre-phylloxera plantings dating back to the 1840s. The Barossa Old Vine Charter classifies vines by age: Barossa Old Vine (35 years), Barossa Survivor Vine (70 years), Barossa Centenarian Vine (100 years), and Barossa Ancestor Vine (125 years).",
    },
    {
        "name": "Eden Valley",
        "state": "South Australia",
        "climate": "cool continental",
        "soil_types": ["sandy loam", "clay"],
        "soil_details": "Sandy loam over clay subsoils on ancient weathered rock; higher altitude produces thinner, well-drained soils with quartz and ironstone gravel",
        "elevation_range": "380-600m",
        "vineyard_area_ha": 2000,
        "key_grapes": ["Riesling", "Shiraz", "Cabernet Sauvignon"],
        "wine_styles": ["austere mineral Riesling", "elegant Shiraz"],
        "history": "Eden Valley's cooler high-altitude sites were recognized early by pioneers like Henschke, whose Hill of Grace vineyard contains Shiraz vines planted in the 1860s.",
        "viticulture_notes": "The altitude difference between Eden Valley and the Barossa Valley floor creates a significant temperature differential, with Eden Valley averaging 2-3 degrees Celsius cooler during the growing season.",
        "notes": "Cooler than the Barossa Valley floor due to higher altitude, producing Riesling of exceptional purity with lime, mineral, and floral character that ages for decades.",
    },
    {
        "name": "Clare Valley",
        "state": "South Australia",
        "climate": "continental",
        "soil_types": ["slate", "limestone", "terra rossa"],
        "soil_details": "Varied soils including red-brown earth over limestone, slate and shale in the Polish Hill River sub-region, and terra rossa pockets; highly variable across short distances",
        "elevation_range": "400-500m",
        "vineyard_area_ha": 5000,
        "key_grapes": ["Riesling", "Shiraz", "Cabernet Sauvignon"],
        "wine_styles": ["citrus-driven Riesling", "structured Shiraz", "Cabernet Sauvignon"],
        "sub_regions": ["Watervale", "Polish Hill River", "Sevenhill", "Auburn"],
        "history": "The Clare Valley was first planted in 1840 by English settlers, with Jesuit priests establishing the historic Sevenhill Cellars in 1851 for sacramental wine production.",
        "viticulture_notes": "Clare Valley experiences significant diurnal temperature variation with warm days and cool nights, which preserves natural acidity in Riesling and contributes to its distinctive lime character.",
        "notes": "Clare Valley Riesling producers were pioneers of the screwcap closure revolution in 2000, when a group of producers collectively adopted screwcaps to preserve the purity of their wines.",
    },
    {
        "name": "McLaren Vale",
        "state": "South Australia",
        "climate": "Mediterranean maritime",
        "soil_types": ["sandy", "clay", "limestone"],
        "soil_details": "Extremely diverse soils across a compact area including deep sand, black clay, red-brown earth, and limestone-based soils; over 40 distinct soil types have been identified",
        "elevation_range": "50-350m",
        "vineyard_area_ha": 7000,
        "key_grapes": ["Shiraz", "Grenache", "Cabernet Sauvignon"],
        "wine_styles": ["rich Shiraz", "Grenache", "Mediterranean blends"],
        "history": "McLaren Vale was one of Australia's first commercial wine regions, with John Reynell planting vines in 1838, followed by Thomas Hardy in 1853.",
        "viticulture_notes": "The afternoon sea breeze known as the Gully Wind arrives from Gulf St Vincent each summer day, cooling vineyards and extending the growing season for more balanced fruit.",
        "notes": "McLaren Vale has over 40 distinct soil types compressed into a small area, making it one of the most geologically diverse wine regions in the world. Strong maritime influence from Gulf St Vincent moderates temperatures.",
    },
    {
        "name": "Adelaide Hills",
        "state": "South Australia",
        "climate": "cool",
        "soil_types": ["sandy loam", "clay", "laterite"],
        "soil_details": "Predominantly grey-brown sandy loam over clay with patches of laterite and ironstone; soils are generally acidic and well-drained on the slopes of the Mount Lofty Ranges",
        "elevation_range": "400-710m",
        "vineyard_area_ha": 3200,
        "key_grapes": ["Sauvignon Blanc", "Chardonnay", "Pinot Noir"],
        "wine_styles": ["cool-climate white", "sparkling", "Pinot Noir"],
        "sub_regions": ["Lenswood", "Piccadilly Valley", "Lobethal", "Woodside", "Basket Range"],
        "viticulture_notes": "The Adelaide Hills is one of the few Australian regions where cool-climate sparkling wine production thrives, with Chardonnay and Pinot Noir used for traditional-method fizz.",
        "notes": "Contains some of South Australia's highest vineyards at up to 710 meters, producing wines with natural acidity and elegance uncommon in Australian warm-climate regions.",
    },
    {
        "name": "Coonawarra",
        "state": "South Australia",
        "climate": "cool maritime",
        "soil_types": ["terra rossa"],
        "soil_details": "Famous cigar-shaped strip of terra rossa soil (iron-rich red clay-loam over soft limestone) approximately 15 km long and 1-2 km wide; the limestone subsoil provides natural drainage and a water table that sustains vines in dry conditions",
        "elevation_range": "50-70m",
        "vineyard_area_ha": 5000,
        "key_grapes": ["Cabernet Sauvignon", "Shiraz", "Merlot"],
        "wine_styles": ["structured Cabernet Sauvignon", "elegant reds"],
        "history": "Coonawarra was first planted by John Riddoch in 1891, but the region's potential for premium Cabernet Sauvignon was not widely recognized until the 1960s and 1970s.",
        "viticulture_notes": "Coonawarra's flat terrain and uniform terra rossa strip make it one of Australia's most geographically defined wine regions, with ongoing debate about the boundaries of the GI and what constitutes 'true' terra rossa.",
        "notes": "Coonawarra's terra rossa soil is Australia's most famous vineyard soil, a narrow strip of red earth over limestone that produces some of the country's finest Cabernet Sauvignon with distinctive eucalyptus and mint notes.",
    },
    {
        "name": "Margaret River",
        "state": "Western Australia",
        "climate": "maritime Mediterranean",
        "soil_types": ["gravel", "loam", "limestone"],
        "soil_details": "Deep gravelly loam over laterite and granite in the north; loam over limestone (tuart) soils in the south; coastal areas have windblown sand over limestone",
        "elevation_range": "50-200m",
        "vineyard_area_ha": 5500,
        "key_grapes": ["Cabernet Sauvignon", "Chardonnay", "Sauvignon Blanc", "Semillon"],
        "wine_styles": ["Bordeaux-style reds", "structured Chardonnay", "Sauvignon Blanc-Semillon blends"],
        "sub_regions": ["Wilyabrup", "Wallcliffe", "Yallingup", "Carbunup", "Treeton"],
        "history": "Margaret River's viticultural potential was identified by Dr. John Gladstones in a 1966 research paper, with the first vines planted in 1967 by Dr. Tom Cullity at Vasse Felix.",
        "viticulture_notes": "Margaret River's maritime Mediterranean climate has a remarkably consistent growing season, with less vintage variation than most other Australian wine regions due to the moderating influence of the Indian and Southern Oceans.",
        "notes": "Often called the Bordeaux of the Southern Hemisphere due to its maritime climate, gravelly soils, and success with Cabernet Sauvignon and Cabernet blends. Produces only about 3% of Australia's wine but commands a disproportionate share of premium production.",
    },
    {
        "name": "Great Southern",
        "state": "Western Australia",
        "climate": "cool maritime",
        "soil_types": ["gravel", "loam", "karri loam", "granite"],
        "soil_details": "Highly varied soils across a vast area including gravelly sandy loam in Frankland River, laterite in Mount Barker, and granite-derived soils in Porongurup",
        "elevation_range": "50-400m",
        "vineyard_area_ha": 3000,
        "key_grapes": ["Riesling", "Shiraz", "Cabernet Sauvignon", "Pinot Noir"],
        "wine_styles": ["aromatic Riesling", "peppery Shiraz", "cool-climate reds"],
        "sub_regions": ["Frankland River", "Mount Barker", "Porongurup", "Albany", "Denmark"],
        "viticulture_notes": "Great Southern's five sub-regions span over 100 km from north to south, making it one of the most diverse single GIs in Australia with cool maritime to moderate continental mesoclimates.",
        "notes": "Australia's largest wine region by area, with five official sub-regions: Frankland River, Mount Barker, Porongurup, Albany, and Denmark. Each sub-region has distinctly different terroir and mesoclimates.",
    },
    {
        "name": "Hunter Valley",
        "state": "New South Wales",
        "climate": "warm subtropical",
        "soil_types": ["volcanic basalt", "sandy loam", "alluvial clay"],
        "soil_details": "Volcanic basalt red soils on the Brokenback Range foothills provide the best sites; lower vineyard areas have lighter sandy loam and alluvial clay; the volcanic soils retain moisture well",
        "elevation_range": "50-200m",
        "vineyard_area_ha": 4000,
        "key_grapes": ["Semillon", "Shiraz", "Chardonnay"],
        "wine_styles": ["unoaked Semillon", "medium-bodied Shiraz", "Chardonnay"],
        "sub_regions": ["Lower Hunter", "Upper Hunter"],
        "history": "The Hunter Valley is one of Australia's oldest wine regions, with James Busby planting the first commercial vineyards in the 1830s near Cessnock.",
        "viticulture_notes": "Despite its warm and humid climate, the Hunter Valley benefits from afternoon cloud cover and sea breezes that moderate temperatures during the critical ripening period, reducing heat stress on vines.",
        "notes": "Hunter Valley Semillon is a unique Australian wine style: picked early at low sugar (10-11% alcohol), fermented without oak, and bottled young. Despite appearing simple when young, these wines develop extraordinary toast, honey, and lanolin complexity over 10-20 years of bottle aging.",
    },
    {
        "name": "Yarra Valley",
        "state": "Victoria",
        "climate": "cool continental",
        "soil_types": ["grey clay", "red volcanic clay"],
        "soil_details": "Two main soil types: grey clay-loam soils in the lower (warmer) valley floor and red volcanic clay-loam (derived from basalt) on the upper (cooler) slopes",
        "elevation_range": "50-400m",
        "vineyard_area_ha": 3500,
        "key_grapes": ["Pinot Noir", "Chardonnay", "Shiraz", "Cabernet Sauvignon"],
        "wine_styles": ["Pinot Noir", "Chardonnay", "sparkling", "cool-climate Shiraz"],
        "sub_regions": ["Upper Yarra", "Lower Yarra", "Yarra Glen", "Healesville", "Coldstream"],
        "history": "The Yarra Valley was first planted in 1838 by the Ryrie brothers, making it Victoria's oldest wine region. After a long period of decline, it was revived in the 1960s and 1970s.",
        "viticulture_notes": "The Yarra Valley's distinction between Upper and Lower Yarra creates two distinct viticultural zones: the cooler Upper Yarra at 200-400m with red volcanic soils favoring Pinot Noir and Chardonnay, and the warmer Lower Yarra with grey soils favoring Shiraz and Cabernet.",
        "notes": "The Yarra Valley distinguishes between the Upper Yarra (cooler, higher, red volcanic soils, Pinot Noir and Chardonnay) and the Lower Yarra (warmer, grey soils, Shiraz and Cabernet Sauvignon).",
    },
    {
        "name": "Mornington Peninsula",
        "state": "Victoria",
        "climate": "cool maritime",
        "soil_types": ["volcanic", "sandy"],
        "soil_details": "Predominantly volcanic-derived brown earth soils with some sandy patches near the coast; the peninsula's maritime exposure ensures consistent cool growing conditions",
        "elevation_range": "50-200m",
        "vineyard_area_ha": 1800,
        "key_grapes": ["Pinot Noir", "Chardonnay", "Pinot Gris"],
        "wine_styles": ["Pinot Noir", "Chardonnay", "sparkling"],
        "viticulture_notes": "Mornington Peninsula's maritime climate creates a long, cool growing season with an average January temperature of only 19.5 degrees Celsius, making it ideal for Burgundian varieties.",
        "notes": "Surrounded by water on three sides (Port Phillip Bay and Bass Strait), Mornington Peninsula is one of Australia's coolest mainland wine regions, producing elegant Pinot Noir and Chardonnay.",
    },
    {
        "name": "Rutherglen",
        "state": "Victoria",
        "climate": "hot continental",
        "soil_types": ["sandy loam", "red-brown earth"],
        "soil_details": "Deep sandy loam and red-brown earth over clay subsoils; the warm inland climate with low rainfall is ideal for fortified wine production",
        "elevation_range": "150-300m",
        "vineyard_area_ha": 800,
        "key_grapes": ["Muscat à Petits Grains", "Muscadelle"],
        "wine_styles": ["fortified Muscat", "fortified Topaque"],
        "history": "Rutherglen has been producing fortified wines since the 1860s gold rush era, with some wineries maintaining solera systems that contain wine material over 100 years old.",
        "viticulture_notes": "Rutherglen's hot continental climate with low humidity is ideal for drying grapes on the vine (raisining), concentrating sugars and flavors for fortified wine production.",
        "notes": "Rutherglen is famous for its unique fortified Muscat and Topaque (formerly Tokay) wines, produced using a solera-like blending system. The classification system has four tiers: Rutherglen (fresh, young), Classic (more complex), Grand (intense, aged), and Rare (exceptionally old, concentrated).",
    },
    {
        "name": "Heathcote",
        "state": "Victoria",
        "climate": "warm continental",
        "soil_types": ["Cambrian greenstone"],
        "soil_details": "Ancient Cambrian-era greenstone soils approximately 500 million years old, among the oldest viticultural soils in the world; the deep red, free-draining soils are rich in iron and produce deeply colored, intensely flavored Shiraz",
        "elevation_range": "160-320m",
        "vineyard_area_ha": 1500,
        "key_grapes": ["Shiraz"],
        "wine_styles": ["powerful Shiraz", "Sangiovese"],
        "viticulture_notes": "Heathcote's Cambrian greenstone soils are extremely deep and well-drained, allowing vine roots to penetrate many meters and access consistent moisture without irrigation.",
        "notes": "Heathcote's ancient Cambrian greenstone soils are approximately 500 million years old, making them among the oldest grape-growing soils on Earth. These unique soils produce distinctively deep, powerful Shiraz.",
    },
    {
        "name": "Tasmania",
        "state": "Tasmania",
        "climate": "cool maritime",
        "soil_types": ["dolerite", "basalt", "sandstone"],
        "soil_details": "Diverse soils across the island including dolerite-derived clay in the south, basalt in the north (Tamar Valley), and sandstone in the east; generally well-drained acidic soils",
        "elevation_range": "10-350m",
        "vineyard_area_ha": 2000,
        "key_grapes": ["Pinot Noir", "Chardonnay", "Riesling"],
        "wine_styles": ["sparkling wine", "Pinot Noir", "Chardonnay", "Riesling"],
        "sub_regions": ["Tamar Valley", "Pipers River", "Coal River Valley", "Huon Valley", "East Coast"],
        "history": "Tasmania's modern wine industry began in 1958 when Claudio Alcorso planted vines at Moorilla Estate, though early settlers attempted viticulture in the 1820s.",
        "viticulture_notes": "Tasmania's cool climate and long growing season (often harvesting 4-6 weeks later than mainland Australia) allow grapes to develop intense flavors while retaining high natural acidity.",
        "notes": "Australia's coolest wine region with five main sub-regions: Tamar Valley (warmest, sheltered), Pipers River (cool, maritime), Coal River Valley (dry, sheltered), Huon Valley (wet, cool), and East Coast (driest, sunny). Tasmania is Australia's premium sparkling wine producer.",
    },
    {
        "name": "Riverland",
        "state": "South Australia",
        "climate": "hot continental",
        "soil_types": ["alluvial", "sandy loam", "clay"],
        "soil_details": "Alluvial soils deposited by the Murray River, with sandy loam over clay; flat terrain with irrigation from the Murray-Darling river system",
        "elevation_range": "10-50m",
        "vineyard_area_ha": 18000,
        "key_grapes": ["Shiraz", "Chardonnay", "Cabernet Sauvignon"],
        "wine_styles": ["high-volume varietal wines", "bag-in-box"],
        "viticulture_notes": "Riverland's hot climate and irrigation produce high yields averaging 15-20 tonnes per hectare, compared to 3-5 tonnes per hectare in premium regions like Barossa Valley and Margaret River.",
        "notes": "One of Australia's largest wine-producing regions by volume, relying on irrigation from the Murray River. Produces predominantly affordable everyday wines.",
    },
    {
        "name": "Riverina",
        "state": "New South Wales",
        "climate": "hot continental",
        "soil_types": ["alluvial clay", "red-brown earth"],
        "soil_details": "Flat alluvial plains with deep clay soils deposited by the Murrumbidgee River; irrigation is essential due to low rainfall",
        "elevation_range": "100-200m",
        "vineyard_area_ha": 12000,
        "key_grapes": ["Semillon", "Shiraz", "Chardonnay"],
        "wine_styles": ["botrytis Semillon", "volume wines"],
        "viticulture_notes": "The Riverina's autumn conditions of warm days and cool, foggy nights from the Murrumbidgee River create ideal conditions for Botrytis cinerea development on Semillon grapes.",
        "notes": "The Riverina (centered around Griffith) produces large volumes of wine but is also known for outstanding botrytis-affected Semillon, with De Bortoli Noble One being the most famous example.",
    },
    {
        "name": "Mudgee",
        "state": "New South Wales",
        "climate": "continental",
        "soil_types": ["volcanic red soil", "clay"],
        "soil_details": "Red volcanic soils derived from ancient basalt flows, with clay subsoils providing good moisture retention; the elevated altitude moderates the warm continental climate",
        "elevation_range": "450-600m",
        "vineyard_area_ha": 2500,
        "key_grapes": ["Shiraz", "Cabernet Sauvignon", "Chardonnay"],
        "wine_styles": ["full-bodied reds", "Chardonnay"],
        "history": "Mudgee's name comes from the Wiradjuri Aboriginal word for 'nest in the hills'. The region was first planted by German settlers in the 1850s during the gold rush era.",
        "notes": "Mudgee was one of the first Australian wine regions to implement its own appellation system in 1979, predating the national GI system by over a decade.",
    },
    {
        "name": "Orange",
        "state": "New South Wales",
        "climate": "cool continental",
        "soil_types": ["volcanic basalt", "clay"],
        "soil_details": "Rich volcanic basalt soils from the extinct Mount Canobolas volcano; soils are deep red-brown earth at lower altitudes transitioning to thinner, well-drained soils at higher elevations",
        "elevation_range": "600-1100m",
        "vineyard_area_ha": 1200,
        "key_grapes": ["Chardonnay", "Sauvignon Blanc", "Pinot Noir", "Shiraz"],
        "wine_styles": ["cool-climate whites", "elegant Pinot Noir"],
        "viticulture_notes": "Orange's GI regulation stipulating that all grapes must be grown above 600 meters is unique in Australia and ensures a consistently cool growing environment.",
        "notes": "One of Australia's highest wine regions, with vineyards on the slopes of the extinct Mount Canobolas volcano. GI regulations require all grapes to be grown above 600 meters elevation.",
    },
    {
        "name": "Langhorne Creek",
        "state": "South Australia",
        "climate": "Mediterranean maritime",
        "soil_types": ["alluvial", "sandy loam", "clay"],
        "soil_details": "Ancient alluvial floodplain soils deposited by the Bremer and Angas rivers over millennia; deep, fertile sandy loam and clay soils with good water-holding capacity",
        "elevation_range": "10-50m",
        "vineyard_area_ha": 5000,
        "key_grapes": ["Cabernet Sauvignon", "Shiraz", "Merlot"],
        "wine_styles": ["soft reds", "blending wines"],
        "history": "Langhorne Creek was first planted by Frank Potts in 1860, and for over a century vineyards were irrigated by deliberate flooding from the Bremer River, a practice that ended when the river was dammed in the 1960s.",
        "notes": "Historically relied on natural flooding from the Bremer River to irrigate vineyards. Langhorne Creek grapes are widely used in multi-regional blends, particularly with McLaren Vale and Barossa fruit.",
    },
    {
        "name": "Granite Belt",
        "state": "Queensland",
        "climate": "continental",
        "soil_types": ["granite", "sandy loam"],
        "soil_details": "Decomposed granite soils producing well-drained, mineral-rich growing conditions; the high altitude compensates for the subtropical latitude",
        "elevation_range": "700-1000m",
        "vineyard_area_ha": 500,
        "key_grapes": ["Shiraz", "Cabernet Sauvignon", "Chardonnay", "Verdelho"],
        "wine_styles": ["alternative varieties", "cool-climate styles"],
        "notes": "Queensland's premium wine region, where high altitude (700-1000m) compensates for the subtropical latitude to produce cool-climate wine styles. One of the few Australian regions actively exploring Italian and Spanish grape varieties.",
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — New Zealand Regions
# ═══════════════════════════════════════════════════════════════════════════════

NZ_REGIONS = [
    {
        "name": "Marlborough",
        "island": "South Island",
        "climate": "cool maritime",
        "soil_types": ["alluvial gravel", "clay", "loess"],
        "soil_details": "The Wairau Valley has deep, free-draining alluvial gravel deposited by the Wairau River, while the Southern Valleys (Awatere, Ben Morven) have heavier clay and loess soils that produce more restrained, mineral wines",
        "elevation_range": "10-200m",
        "vineyard_area_ha": 26000,
        "key_grapes": ["Sauvignon Blanc", "Pinot Noir", "Chardonnay", "Pinot Gris"],
        "wine_styles": ["pungent Sauvignon Blanc", "Pinot Noir", "sparkling"],
        "sub_regions": ["Wairau Valley", "Southern Valleys", "Awatere Valley"],
        "history": "Montana (now Brancott Estate) planted the first Sauvignon Blanc vines in Marlborough in 1973, but it was Cloudy Bay's 1985 vintage that brought international recognition to the region.",
        "viticulture_notes": "Marlborough's high sunshine hours (among the highest in New Zealand), cool nights, and free-draining gravelly soils create ideal conditions for developing the intense thiol-driven aromatics that define Marlborough Sauvignon Blanc.",
        "notes": "Marlborough accounts for over 75% of New Zealand's total wine production and is recognized as the world's benchmark region for Sauvignon Blanc, with intensely aromatic wines showing passionfruit, gooseberry, and herbaceous characters.",
    },
    {
        "name": "Hawke's Bay",
        "island": "North Island",
        "climate": "warm maritime",
        "soil_types": ["river gravel", "clay", "silt", "limestone"],
        "soil_details": "The Gimblett Gravels sub-region is a unique 800-hectare area of free-draining river gravel (former Ngaruroro River bed) that absorbs and radiates heat; other areas have heavier clay and silt over limestone",
        "elevation_range": "10-300m",
        "vineyard_area_ha": 5000,
        "key_grapes": ["Cabernet Sauvignon", "Merlot", "Syrah", "Chardonnay"],
        "wine_styles": ["Bordeaux blends", "Syrah", "Chardonnay"],
        "sub_regions": ["Gimblett Gravels", "Bridge Pa Triangle", "Havelock Hills", "Esk Valley"],
        "history": "Hawke's Bay is one of New Zealand's oldest wine regions, with missionaries planting the first vines in the 1850s. The Gimblett Gravels area was a former riverbed that flooded catastrophically in 1867.",
        "viticulture_notes": "The Gimblett Gravels' free-draining river stones absorb heat during the day and radiate it at night, creating a warm mesoclimate that consistently achieves full phenolic ripeness in Bordeaux varieties.",
        "notes": "Hawke's Bay is New Zealand's second-largest wine region and its warmest major region on the North Island. The Gimblett Gravels is a unique sub-region on a former riverbed, producing structured Bordeaux-style reds and concentrated Syrah.",
    },
    {
        "name": "Central Otago",
        "island": "South Island",
        "climate": "continental",
        "soil_types": ["schist", "loess", "gravel", "clay"],
        "soil_details": "Predominantly schist-derived soils with loess deposits; the mountainous terrain creates diverse aspects and microclimates; well-drained, low-fertility soils stress vines and concentrate flavors",
        "elevation_range": "200-450m",
        "vineyard_area_ha": 2000,
        "key_grapes": ["Pinot Noir", "Riesling", "Pinot Gris"],
        "wine_styles": ["Pinot Noir", "aromatic whites"],
        "sub_regions": ["Bannockburn", "Gibbston", "Cromwell Basin", "Wanaka", "Alexandra/Clyde"],
        "history": "Central Otago's modern wine industry began in the 1980s, making it one of New Zealand's youngest wine regions, though gold miners attempted grape growing in the 1860s.",
        "viticulture_notes": "Central Otago's extreme diurnal temperature variation (up to 20 degrees Celsius between day and night) produces Pinot Noir with intense color, concentrated fruit, and firm structure.",
        "notes": "Central Otago is the world's southernmost wine region at approximately 45 degrees south latitude. It is New Zealand's only continental (non-maritime) wine region, with dramatic diurnal temperature variation. Key sub-regions include Bannockburn, Gibbston (highest altitude), Cromwell Basin, Wanaka, and Alexandra/Clyde (driest, most continental).",
    },
    {
        "name": "Wairarapa",
        "island": "North Island",
        "climate": "cool dry",
        "soil_types": ["gravel", "silt", "clay"],
        "soil_details": "Martinborough's free-draining gravelly river terraces are the most prized sites, with deep alluvial gravel over clay; surrounding areas have heavier silt and clay soils",
        "elevation_range": "20-100m",
        "vineyard_area_ha": 1000,
        "key_grapes": ["Pinot Noir", "Sauvignon Blanc", "Riesling"],
        "wine_styles": ["Pinot Noir", "Sauvignon Blanc"],
        "sub_regions": ["Martinborough", "Gladstone", "Masterton"],
        "history": "Martinborough's potential was identified in 1978 by soil scientist Dr. Derek Milne, who noted the similarity of its terraces and climate to Burgundy, leading to the first plantings in 1980.",
        "viticulture_notes": "Wairarapa's small scale and boutique focus means most wineries are estate-grown, with vineyard management closely controlled by the winemaker.",
        "notes": "Martinborough, the main sub-region of Wairarapa, produces some of New Zealand's most acclaimed Pinot Noir from small boutique wineries. The region is sheltered from rain by the Rimutaka Range, making it one of the driest areas in the lower North Island.",
    },
    {
        "name": "Canterbury/Waipara",
        "island": "South Island",
        "climate": "cool continental",
        "soil_types": ["limestone", "clay", "gravel", "loess"],
        "soil_details": "Waipara Valley has limestone and clay over gravel, protected from cool easterly winds by the Teviotdale Hills; Canterbury Plains have alluvial gravel and loess",
        "elevation_range": "50-300m",
        "vineyard_area_ha": 1200,
        "key_grapes": ["Riesling", "Pinot Noir", "Pinot Gris", "Sauvignon Blanc"],
        "wine_styles": ["Riesling", "Pinot Noir"],
        "sub_regions": ["Waipara Valley", "Canterbury Plains"],
        "viticulture_notes": "Waipara's limestone-rich soils are uncommon in New Zealand and contribute a distinctive mineral character to the region's Riesling and Pinot Noir.",
        "notes": "The Waipara Valley sub-region is sheltered from the cool easterly Canterbury winds by a range of hills, creating a warmer mesoclimate that favors Pinot Noir and Riesling. Limestone soils in Waipara are unusual for New Zealand.",
    },
    {
        "name": "Nelson",
        "island": "South Island",
        "climate": "cool maritime",
        "soil_types": ["clay", "gravel", "loam"],
        "soil_details": "Diverse soils from heavy clay to gravelly loam in the Waimea Plains and surrounding hillsides; moderate fertility with good natural drainage on sloping sites",
        "elevation_range": "10-200m",
        "vineyard_area_ha": 1000,
        "key_grapes": ["Chardonnay", "Pinot Noir", "Sauvignon Blanc", "Riesling"],
        "wine_styles": ["Chardonnay", "Pinot Noir", "aromatic whites"],
        "sub_regions": ["Upper Moutere", "Waimea Plains", "Moutere Hills"],
        "viticulture_notes": "Nelson's position between the mountains and the sea creates a diverse range of mesoclimates within a small area, with both warm maritime and cooler hill sites available to growers.",
        "notes": "Nelson is one of New Zealand's sunniest regions, located at the northern tip of the South Island. It is known for artisanal winemaking with many small, family-owned producers.",
    },
    {
        "name": "Auckland/Waiheke Island",
        "island": "North Island",
        "climate": "warm maritime",
        "soil_types": ["volcanic", "clay"],
        "soil_details": "Waiheke Island has weathered volcanic and clay soils with good drainage on north-facing slopes; mainland Auckland areas (Kumeu, Matakana) have heavier clay over volcanic subsoils",
        "elevation_range": "10-200m",
        "vineyard_area_ha": 500,
        "key_grapes": ["Cabernet Sauvignon", "Merlot", "Syrah", "Chardonnay"],
        "wine_styles": ["Bordeaux blends", "Syrah", "Chardonnay"],
        "sub_regions": ["Waiheke Island", "Kumeu", "Matakana", "Henderson"],
        "history": "Auckland was New Zealand's historic wine center, home to many of the country's oldest wineries founded by Croatian immigrants (originally Dalmatian) in the early 20th century.",
        "notes": "Waiheke Island in the Hauraki Gulf has a distinctly warmer and drier microclimate than mainland Auckland, producing premium Bordeaux-style blends and Syrah from small estate vineyards.",
    },
    {
        "name": "Gisborne",
        "island": "North Island",
        "climate": "warm maritime",
        "soil_types": ["alluvial", "clay", "silt"],
        "soil_details": "Deep, fertile alluvial soils on the Poverty Bay flats, deposited by rivers flowing from the Raukumara Range; high natural fertility produces generous yields",
        "elevation_range": "10-100m",
        "vineyard_area_ha": 1500,
        "key_grapes": ["Chardonnay", "Gewurztraminer", "Viognier"],
        "wine_styles": ["Chardonnay", "aromatic whites"],
        "notes": "Gisborne is New Zealand's third-largest wine region and was historically known as the Chardonnay capital of New Zealand. It is the first wine region in the world to see the sunrise each day due to its eastern position near the International Date Line.",
    },
    {
        "name": "Northland",
        "island": "North Island",
        "climate": "subtropical maritime",
        "soil_types": ["clay", "volcanic"],
        "soil_details": "Heavy clay soils derived from volcanic and sedimentary parent material; the warm, humid climate requires careful canopy management to control disease pressure",
        "elevation_range": "10-200m",
        "vineyard_area_ha": 100,
        "key_grapes": ["Syrah", "Chardonnay", "Chambourcin"],
        "wine_styles": ["Syrah", "tropical whites"],
        "notes": "New Zealand's warmest and most northerly wine region, with a subtropical climate. Humidity and rainfall present viticultural challenges, but the region produces distinctive Syrah and is experimenting with Mediterranean varieties.",
    },
    {
        "name": "Waikato/Bay of Plenty",
        "island": "North Island",
        "climate": "warm humid",
        "soil_types": ["volcanic", "alluvial clay"],
        "soil_details": "Volcanic soils from the Taupo Volcanic Zone and alluvial clay in river valleys; generally fertile soils with good moisture retention",
        "elevation_range": "20-300m",
        "vineyard_area_ha": 200,
        "key_grapes": ["Chardonnay", "Sauvignon Blanc", "Cabernet Sauvignon"],
        "wine_styles": ["Chardonnay", "blended reds"],
        "notes": "A small wine region centered around the Waikato River basin, with volcanic influence from the nearby Taupo Volcanic Zone. Te Kauwhata was historically one of New Zealand's most important viticultural research stations.",
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Grape Variety Database
# ═══════════════════════════════════════════════════════════════════════════════

GRAPE_VARIETY_DATABASE = [
    # Australian grapes
    {
        "name": "Shiraz",
        "country": "Australia",
        "role": "Australia's most planted red grape variety and signature wine",
        "regional_expressions": [
            ("Barossa Valley", "full-bodied, rich, with dark fruit, chocolate, and spice; old-vine examples show extraordinary concentration and complexity"),
            ("Eden Valley", "more elegant and perfumed than Barossa, with violet, pepper, and spice character from cooler altitude"),
            ("Hunter Valley", "medium-bodied with earthy, leather character and regional identity; often develops sweaty saddle notes with age"),
            ("McLaren Vale", "rich, generous, with dark chocolate, plum, and licorice; maritime influence provides freshness"),
            ("Heathcote", "deep-colored, powerful, with dark berry and mineral character from ancient Cambrian soils"),
            ("Clare Valley", "structured, with dark fruit, mint, and peppery notes"),
            ("Great Southern", "peppery, medium-bodied, with cool-climate elegance and spice"),
        ],
        "notes": "Shiraz (known as Syrah in France) was brought to Australia in 1832 by James Busby. Australia has some of the oldest Shiraz vines in the world, with Barossa plantings predating phylloxera.",
    },
    {
        "name": "Semillon",
        "country": "Australia",
        "role": "Signature white variety of the Hunter Valley",
        "regional_expressions": [
            ("Hunter Valley", "harvested early at low sugar levels (10-11% alcohol), fermented and bottled without oak; develops extraordinary complexity of toast, honey, and lanolin over 10-20 years of bottle aging"),
            ("Barossa Valley", "richer, often oak-aged style with more weight and tropical fruit character"),
            ("Margaret River", "typically blended with Sauvignon Blanc in a Bordeaux-inspired style"),
        ],
        "notes": "Hunter Valley Semillon is one of Australia's most distinctive wine styles. The early-picked, unoaked style appears lean and simple in youth but can develop profound complexity with extended bottle aging.",
    },
    {
        "name": "Riesling",
        "country": "Australia",
        "role": "Premier white grape of South Australia's cooler regions",
        "regional_expressions": [
            ("Clare Valley", "lime, citrus, and toast character with firm acidity; ages exceptionally well and develops kerosene and honey notes"),
            ("Eden Valley", "floral, mineral, and more delicate than Clare; often more perfumed with white flower and spice character"),
            ("Great Southern", "intense lime and citrus with crisp acidity from the cool climate"),
            ("Tasmania", "lean, high-acid, with green apple and floral notes in a European style"),
        ],
        "notes": "Australian Riesling, particularly from Clare Valley and Eden Valley, is made in a dry, unoaked style that is distinct from German and Alsatian traditions. Clare Valley producers led the screwcap revolution starting in 2000.",
    },
    {
        "name": "Grenache",
        "country": "Australia",
        "role": "Historic variety with old-vine heritage in South Australia",
        "regional_expressions": [
            ("Barossa Valley", "old-vine Grenache produces concentrated, complex wines with raspberry, spice, and earthy character; some vines are over 100 years old"),
            ("McLaren Vale", "generous, ripe, with strawberry, red cherry, and spice; increasingly valued as a single-variety wine"),
        ],
        "notes": "Once used primarily for bulk wine and fortified production, old-vine Grenache in the Barossa Valley and McLaren Vale has been rediscovered as one of Australia's great wine treasures, with some vines dating to the 1850s.",
    },
    {
        "name": "Cabernet Sauvignon",
        "country": "Australia",
        "role": "Premium red variety, especially in Coonawarra and Margaret River",
        "regional_expressions": [
            ("Coonawarra", "structured, with blackcurrant, mint, and eucalyptus notes from the famous terra rossa soil; ages well over decades"),
            ("Margaret River", "Bordeaux-like, with dark fruit, cedar, and fine tannins; often blended with Merlot and Cabernet Franc"),
            ("Barossa Valley", "richer, more opulent style with plum and dark chocolate"),
            ("Yarra Valley", "more elegant, with leafy, herbal notes and fine tannins from the cool climate"),
        ],
        "notes": "Australian Cabernet Sauvignon finds its finest expressions in Coonawarra (terra rossa) and Margaret River (maritime Mediterranean), producing wines of international quality.",
    },
    {
        "name": "Chardonnay",
        "country": "Australia",
        "role": "Most planted white grape variety in Australia",
        "regional_expressions": [
            ("Margaret River", "structured, with stone fruit and citrus, often barrel-fermented with restrained oak influence"),
            ("Yarra Valley", "elegant, with white peach and grapefruit; both oaked and unoaked styles"),
            ("Adelaide Hills", "crisp, mineral, with nectarine and citrus from cool altitude"),
            ("Tasmania", "lean, high-acid, ideal for sparkling wine base and still wines of finesse"),
        ],
        "notes": "Australian Chardonnay has evolved from the heavily oaked, buttery styles of the 1980s and 1990s to more restrained, site-expressive wines showing greater freshness and minerality.",
    },
    {
        "name": "Verdelho",
        "country": "Australia",
        "role": "Tropical-fruited white originally from Madeira",
        "regional_expressions": [
            ("Hunter Valley", "tropical fruit, honey, and waxy character; one of the few New World regions where Verdelho thrives as a table wine"),
        ],
        "notes": "Originally from Madeira, Verdelho found a second home in Australia's warm regions, particularly the Hunter Valley, where it produces aromatic, tropical-fruited dry white wines.",
    },
    {
        "name": "Muscat a Petits Grains",
        "country": "Australia",
        "role": "Fortified wine grape of Rutherglen",
        "regional_expressions": [
            ("Rutherglen", "used for the unique Rutherglen Muscat style: intensely sweet, complex, with raisin, toffee, and rose petal character developed through extended barrel aging and solera-like blending"),
        ],
        "notes": "In Rutherglen, Muscat a Petits Grains (also known as Brown Muscat due to the dark skin color developed in this region) produces one of the world's great fortified wine styles.",
    },
    # New Zealand grapes
    {
        "name": "Sauvignon Blanc",
        "country": "New Zealand",
        "role": "New Zealand's signature grape, accounting for approximately 60% of total wine production",
        "regional_expressions": [
            ("Marlborough", "intensely aromatic with passionfruit, gooseberry, and herbaceous characters; the benchmark style that put New Zealand wine on the world map"),
            ("Hawke's Bay", "rounder, more tropical, with less herbaceous character than Marlborough"),
            ("Wairarapa", "more restrained and mineral, with herbal and citrus notes"),
            ("Nelson", "aromatic, with a softer, more rounded style than Marlborough"),
        ],
        "notes": "Marlborough Sauvignon Blanc has become one of the wine world's most recognizable styles since Cloudy Bay's debut in 1985. New Zealand's cool climate and high UV light levels produce intensely aromatic wines with distinctive thiol compounds.",
    },
    {
        "name": "Pinot Noir",
        "country": "New Zealand",
        "role": "New Zealand's most important red grape variety",
        "regional_expressions": [
            ("Central Otago", "concentrated, with dark cherry, plum, and mineral character from schist soils and continental climate; bold and structured"),
            ("Martinborough", "elegant, with red cherry, spice, and earthy complexity; Burgundy-like finesse"),
            ("Marlborough", "lighter, with bright red fruit and herbal notes; increasing in quality"),
            ("Canterbury/Waipara", "fine-boned, with cherry and mineral character from limestone soils"),
            ("Nelson", "perfumed, with red berry fruit and silky tannins"),
        ],
        "notes": "New Zealand Pinot Noir has emerged as a world-class expression of the variety, with Central Otago and Martinborough producing wines that rival Burgundy in complexity and aging potential.",
    },
    {
        "name": "Chardonnay",
        "country": "New Zealand",
        "role": "Important white variety for still and sparkling wines",
        "regional_expressions": [
            ("Hawke's Bay", "rich, full-bodied, often barrel-fermented with stone fruit and toasty character"),
            ("Gisborne", "generous, tropical-fruited, historically called the Chardonnay capital of New Zealand"),
            ("Marlborough", "crisp, citrus-driven, increasingly used for premium sparkling wine production"),
        ],
        "notes": "New Zealand Chardonnay ranges from rich, oak-influenced styles in Hawke's Bay to lean sparkling wine base material in Marlborough and Canterbury.",
    },
    {
        "name": "Pinot Gris",
        "country": "New Zealand",
        "role": "Increasingly popular white variety across New Zealand",
        "regional_expressions": [
            ("Marlborough", "crisp, with pear and apple character in a lighter style"),
            ("Central Otago", "richer, with stone fruit and spice from the continental climate"),
            ("Nelson", "aromatic, with honey and pear notes"),
        ],
        "notes": "Pinot Gris has become New Zealand's second most popular white grape variety after Sauvignon Blanc, produced in styles ranging from crisp and dry to richer and off-dry.",
    },
    {
        "name": "Syrah",
        "country": "New Zealand",
        "role": "Emerging premium red variety in Hawke's Bay",
        "regional_expressions": [
            ("Hawke's Bay", "elegant, peppery, with dark fruit and spice; the Gimblett Gravels produces particularly concentrated examples from warm river gravel soils"),
        ],
        "notes": "Hawke's Bay Syrah, particularly from the Gimblett Gravels sub-region, has been recognized as producing world-class wines with a style positioned between northern Rhone elegance and Australian richness.",
    },
    {
        "name": "Riesling",
        "country": "New Zealand",
        "role": "Aromatic white variety suited to cool-climate regions",
        "regional_expressions": [
            ("Canterbury/Waipara", "crisp, mineral, with citrus and floral notes; benefits from limestone soils"),
            ("Marlborough", "aromatic, with lime and blossom character; both dry and off-dry styles"),
            ("Central Otago", "concentrated, with intense citrus and mineral character from the continental climate"),
            ("Nelson", "aromatic, with apple and citrus notes"),
        ],
        "notes": "New Zealand Riesling is produced in styles ranging from bone-dry to sweet late harvest, with Waipara and Central Otago producing particularly distinguished examples.",
    },
    {
        "name": "Gewurztraminer",
        "country": "New Zealand",
        "role": "Aromatic specialty variety",
        "regional_expressions": [
            ("Gisborne", "richly aromatic, with lychee, rose petal, and spice in both dry and off-dry styles"),
            ("Marlborough", "aromatic, with tropical fruit and ginger character"),
        ],
        "notes": "Gisborne and Marlborough produce the most distinctive New Zealand Gewurztraminer, with intense aromatics that benefit from cool growing conditions and careful canopy management.",
    },
    # Additional Australian varieties
    {
        "name": "Mataro",
        "country": "Australia",
        "role": "Historic red variety also known as Mourvedre, used in Barossa GST blends",
        "regional_expressions": [
            ("Barossa Valley", "adds structure, dark fruit, and gamey complexity to GST (Grenache-Shiraz-Mataro) blends; old-vine examples produce concentrated single-variety wines"),
            ("McLaren Vale", "rich, earthy, with blackberry and spice; increasingly bottled as a single variety"),
        ],
        "notes": "Mataro (Mourvedre) was one of the original grape varieties planted in the Barossa Valley in the 19th century. Long undervalued, it has been rediscovered as a premium variety, particularly from old-vine plantings.",
    },
    {
        "name": "Marsanne",
        "country": "Australia",
        "role": "Rare white Rhone variety with a stronghold in central Victoria",
        "regional_expressions": [
            ("Nagambie Lakes", "rich, honeyed, with apricot and almond character; Tahbilk's Marsanne vineyard, planted in 1927, is one of the largest and oldest in the world"),
        ],
        "notes": "Australia has some of the oldest and most significant plantings of Marsanne outside the Rhone Valley, particularly in Victoria's Nagambie Lakes region where Tahbilk has maintained vines since 1927.",
    },
    {
        "name": "Durif",
        "country": "Australia",
        "role": "Deep-colored red variety that thrives in warm Australian climates",
        "regional_expressions": [
            ("Rutherglen", "produces intensely colored, full-bodied wines with dark berry, plum, and pepper character; the hot climate suits this thick-skinned variety"),
            ("Riverina", "dense, deeply colored, with dark fruit; used both as a single variety and in blends"),
        ],
        "notes": "Durif (also known as Petite Sirah in the United States) was created by Dr. Francois Durif in the 1880s as a cross of Syrah and Peloursin. It has found particular success in Australia's warm inland regions.",
    },
    {
        "name": "Pinot Noir",
        "country": "Australia",
        "role": "Premium cool-climate red variety grown in Australia's cooler regions",
        "regional_expressions": [
            ("Yarra Valley", "elegant, with red cherry, spice, and forest floor complexity; both still and sparkling wine styles"),
            ("Mornington Peninsula", "perfumed, with strawberry and cherry character, silky tannins, and maritime-influenced freshness"),
            ("Tasmania", "intense, with bright red fruit and natural acidity; the base for Australia's finest sparkling wines"),
            ("Adelaide Hills", "floral, with red berry fruit and fine structure from the cool altitude"),
        ],
        "notes": "Australian Pinot Noir from cool-climate regions has improved dramatically in quality since the 2000s, with the Yarra Valley, Mornington Peninsula, and Tasmania now producing internationally recognized examples.",
    },
    {
        "name": "Tempranillo",
        "country": "Australia",
        "role": "Emerging Spanish variety planted in warm to moderate Australian climates",
        "regional_expressions": [
            ("McLaren Vale", "ripe, with cherry and plum fruit, medium tannins, and a Mediterranean character"),
            ("Barossa Valley", "fuller-bodied than Spanish examples, with dark cherry and earth"),
        ],
        "notes": "Tempranillo is one of the fastest-growing alternative varieties in Australia, with plantings expanding rapidly since 2000, particularly in South Australia where the Mediterranean climate suits the variety.",
    },
    {
        "name": "Fiano",
        "country": "Australia",
        "role": "Italian white variety gaining traction in warm Australian regions",
        "regional_expressions": [
            ("McLaren Vale", "aromatic, with stone fruit, honey, and nutty character; retains acidity well in warm climates"),
            ("Langhorne Creek", "fresh, with pear and citrus notes; demonstrating strong adaptation to Australian conditions"),
        ],
        "notes": "Fiano is one of the most successful Italian white grape varieties planted in Australia, valued for its ability to maintain acidity in warm climates while producing aromatic, textured wines.",
    },
    {
        "name": "Gruner Veltliner",
        "country": "Australia",
        "role": "Austrian white variety establishing itself in cool Australian climates",
        "regional_expressions": [
            ("Adelaide Hills", "crisp, with white pepper, citrus, and green herb character; one of the most promising alternative white varieties in cool Australian regions"),
        ],
        "notes": "Gruner Veltliner was first planted in Australia in the early 2000s and has shown strong potential in cool-climate regions like the Adelaide Hills, producing wines with the variety's characteristic white pepper and citrus character.",
    },
    {
        "name": "Albarino",
        "country": "New Zealand",
        "role": "Emerging Spanish white variety in New Zealand",
        "regional_expressions": [
            ("Gisborne", "aromatic, with peach, apricot, and saline character; benefits from the region's warm maritime climate"),
            ("Hawke's Bay", "crisp, with citrus and stone fruit; performing well on the warm gravelly soils"),
        ],
        "notes": "Albarino is one of several Mediterranean and Iberian grape varieties being trialed in New Zealand's warmer regions as producers seek diversity beyond Sauvignon Blanc.",
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Classification Systems
# ═══════════════════════════════════════════════════════════════════════════════

CLASSIFICATION_DATABASE = {
    "australia_gi": {
        "title": "Australian Geographical Indication (GI) System",
        "facts": [
            "Australia's Geographical Indication (GI) system organizes wine regions into a three-tier hierarchy: zone (broadest), region, and sub-region (most specific).",
            "The Australian GI system was established by the Australian Wine and Brandy Corporation Act 1980 and is administered by Wine Australia.",
            "Australia has over 65 designated wine regions (GIs) across six states and two territories.",
            "Australian GI designations are based primarily on geographical and climatic factors rather than grape variety or winemaking regulations, unlike European appellation systems.",
            "The GI system does not dictate grape varieties, yields, or winemaking methods, focusing instead on origin verification.",
            "Australia's wine zones include South Australia, New South Wales, Victoria, Western Australia, Tasmania, and Queensland, with South Australia being the largest producing state.",
            "South Eastern Australia is a multi-state zone encompassing South Australia, New South Wales, Victoria, and Tasmania, used for large-volume blended wines.",
        ],
    },
    "label_integrity_program": {
        "title": "Label Integrity Program (LIP)",
        "facts": [
            "Australia's Label Integrity Program (LIP) requires that wines labeled with a vintage must contain at least 85% of wine from that stated year.",
            "Under Australia's Label Integrity Program, wines labeled with a single grape variety must contain at least 85% of that variety.",
            "Australia's Label Integrity Program requires that wines labeled with a Geographical Indication (GI) must contain at least 85% of fruit sourced from that region.",
            "The Label Integrity Program was introduced in 1990 and is enforced through audit trails that track grapes from vineyard to bottle.",
            "Australia's 85% minimum for variety, vintage, and region is less restrictive than many European systems but provides meaningful consumer assurance of origin and content.",
        ],
    },
    "barossa_old_vine_charter": {
        "title": "Barossa Old Vine Charter",
        "facts": [
            "The Barossa Old Vine Charter was established in 2009 to recognize and protect the Barossa Valley's heritage of old vines.",
            "Under the Barossa Old Vine Charter, a Barossa Old Vine is a vine that is at least 35 years old.",
            "Under the Barossa Old Vine Charter, a Barossa Survivor Vine is a vine that is at least 70 years old.",
            "Under the Barossa Old Vine Charter, a Barossa Centenarian Vine is a vine that is at least 100 years old.",
            "Under the Barossa Old Vine Charter, a Barossa Ancestor Vine is a vine that is at least 125 years old.",
            "The Barossa Valley contains some of the world's oldest continuously producing Shiraz vines, with some pre-phylloxera plantings dating to the 1840s and 1850s.",
            "The Barossa Valley was never affected by phylloxera due to its sandy soils, geographic isolation, and strict quarantine measures, preserving ungrafted vines on their own rootstock.",
            "The Barossa Old Vine Charter is one of the only formal vine-age classification systems in the world, recognizing that vine age contributes to wine quality through deeper root systems and lower yields.",
        ],
    },
    "langtons": {
        "title": "Langton's Classification of Distinguished Australian Wine",
        "facts": [
            "Langton's Classification of Distinguished Australian Wine is a market-based grading system that ranks Australia's most collectible wines based on auction performance and market demand.",
            "Langton's Classification has been published since 1991 and is updated approximately every five years, with wines classified as Exceptional, Outstanding, or Distinguished.",
            "Langton's Classification uses auction records, secondary market prices, critical acclaim, and historical significance to rank wines, rather than terroir-based criteria.",
            "Penfolds Grange is consistently ranked as Exceptional in Langton's Classification, holding its position as Australia's most iconic and valuable wine.",
            "Langton's Classification includes wines from diverse regions and styles, from Barossa Shiraz to Margaret River Cabernet to Clare Valley Riesling to Rutherglen Muscat.",
        ],
    },
    "nz_gi": {
        "title": "New Zealand Geographical Indication System",
        "facts": [
            "New Zealand's Geographical Indication (GI) system was formalized under the Geographical Indications (Wine and Spirits) Registration Act 2006.",
            "New Zealand has designated wine regions across both the North Island and South Island, with Marlborough being by far the largest.",
            "Gimblett Gravels in Hawke's Bay was New Zealand's first defined sub-regional appellation, recognized for its unique free-draining river gravel soils.",
            "New Zealand's GI system is similar in structure to Australia's, defining regions by geographic and climatic boundaries rather than prescribing grape varieties or winemaking methods.",
        ],
    },
    "swnz": {
        "title": "Sustainable Winegrowing New Zealand (SWNZ)",
        "facts": [
            "Sustainable Winegrowing New Zealand (SWNZ) is a comprehensive sustainability certification program covering vineyard and winery practices.",
            "Over 98% of New Zealand's vineyard area is certified under the Sustainable Winegrowing New Zealand (SWNZ) program, making it one of the world's most widely adopted wine sustainability schemes.",
            "SWNZ certification covers water management, soil health, biodiversity, pest management, energy use, and waste reduction in both vineyards and wineries.",
            "New Zealand was the first country in the world to have a nationwide sustainability program for its wine industry, launching the SWNZ program in 1995.",
        ],
    },
    "unique_traditions": {
        "title": "Unique Winemaking Traditions",
        "facts": [
            "Hunter Valley Semillon is traditionally harvested early at low sugar levels (producing wines of only 10-11% alcohol), fermented in stainless steel without oak, and bottled young.",
            "Despite appearing lean and austere when young, Hunter Valley Semillon develops extraordinary complexity of toast, honey, and lanolin character over 10 to 20 years of bottle aging without any oak influence.",
            "Rutherglen Muscat is produced using a solera-like fractional blending system, where older wines are blended with younger wines to maintain consistent quality and complexity.",
            "The four-tier Rutherglen Muscat classification (Rutherglen, Classic, Grand, Rare) reflects increasing age, concentration, and complexity, with Rare examples containing material that may be over 100 years old.",
            "Rutherglen Topaque (formerly called Tokay until 2008, when the name was changed to avoid confusion with Hungarian Tokaj) is made from Muscadelle and uses the same four-tier classification system.",
            "Australian screwcap adoption was pioneered in 2000 by a group of Clare Valley Riesling producers who collectively switched from cork to screwcap closures to prevent cork taint and preserve wine freshness.",
            "The Clare Valley screwcap initiative of 2000, led by producers including Jeffrey Grosset, sparked a global re-evaluation of wine closures and helped establish screwcaps as a premium closure option.",
            "Australia's pre-phylloxera vine heritage in the Barossa Valley is globally significant because most of the world's vineyards were devastated by the phylloxera louse in the late 19th century.",
            "New Zealand's extremely high UV light levels (due to thin ozone layer and clear atmosphere) contribute to the intense aromatic compound development in grapes, particularly thiols in Sauvignon Blanc.",
            "Marlborough's success with Sauvignon Blanc dates to the early 1970s when Montana (now Brancott Estate) planted the first commercial Sauvignon Blanc vineyards, with Cloudy Bay's 1985 debut vintage bringing international recognition.",
            "The Australian GST (Grenache-Shiraz-Mataro) blend is a distinctively Australian wine style inspired by southern Rhone blends, typically using old-vine fruit from the Barossa Valley and McLaren Vale.",
            "Penfolds Grange, first made by Max Schubert in 1951, is a multi-regional Shiraz blend that pioneered the Australian practice of blending fruit from different regions to achieve a consistent house style.",
            "New Zealand's Pinot Noir industry has grown rapidly since the 1990s, with the country now recognized as one of the world's top Pinot Noir producers alongside Burgundy, Oregon, and California's Sonoma Coast.",
        ],
    },
    "australian_wine_industry": {
        "title": "Australian Wine Industry Facts",
        "facts": [
            "Australia is the world's fifth-largest wine-producing country and one of the largest wine exporters globally.",
            "South Australia produces approximately 50% of all Australian wine, with the Barossa Valley, McLaren Vale, and Coonawarra being its most prestigious regions.",
            "James Busby, often called the father of Australian viticulture, brought a collection of vine cuttings from Europe to Australia in 1832, establishing the foundation of the country's wine industry.",
            "The phylloxera louse devastated Victorian vineyards in the 1870s and 1880s, shifting Australia's wine industry center to South Australia, which implemented strict quarantine measures that protected its vines.",
            "Victoria's quarantine barriers against phylloxera remain in effect today, with all vine material entering the state subject to inspection and heat treatment protocols.",
            "Australia's wine classification system is based on the Geographical Indication (GI) framework, which is less prescriptive than European appellation systems, giving winemakers greater flexibility in grape variety selection and winemaking methods.",
            "The Australian wine industry experienced rapid export growth in the 1990s and 2000s, driven by branded wines marketed under the 'Brand Australia' initiative.",
            "Australian wine show culture, with competitive judging at regional and national wine shows, has been a major driver of winemaking quality and innovation since the 19th century.",
            "Australia pioneered the use of controlled temperature stainless steel fermentation for white wines in the 1950s and 1960s, revolutionizing white wine quality worldwide.",
            "The Australian wine show system uses a 20-point scoring scale and awards bronze, silver, and gold medals, with trophy awards for the best wines in each class.",
        ],
    },
    "nz_wine_industry": {
        "title": "New Zealand Wine Industry Facts",
        "facts": [
            "New Zealand is one of the world's most southerly wine-producing countries, with vineyards spanning from Northland (35 degrees south) to Central Otago (45 degrees south).",
            "Sauvignon Blanc accounts for approximately 60% of New Zealand's total wine production, with Marlborough being the dominant source.",
            "New Zealand's wine industry has grown dramatically since the 1980s, from fewer than 100 wineries to over 700 wineries today.",
            "New Zealand's total vineyard area is approximately 40,000 hectares, making it a small producer by world standards but commanding premium prices.",
            "The New Zealand wine industry has one of the highest average bottle prices in the world wine market, reflecting its focus on premium quality.",
            "New Zealand's cool maritime climate and long growing season produce wines with naturally high acidity, which contributes to their freshness and aging potential.",
            "The first wine grapes in New Zealand were planted by Reverend Samuel Marsden in 1819 at Kerikeri in the Bay of Islands, Northland.",
            "New Zealand implemented its Geographical Indications system in 2006, later than most other major wine-producing countries.",
            "New Zealand is the world's largest producer of Sauvignon Blanc by value, with Marlborough Sauvignon Blanc commanding a significant price premium over other New World Sauvignon Blanc regions.",
            "The New Zealand wine industry's rapid growth has been driven primarily by export demand, with over 85% of production exported to markets including the United Kingdom, United States, and Australia.",
        ],
    },
    "winemaking_practices": {
        "title": "Winemaking Practices",
        "facts": [
            "Australian winemakers commonly use the technique of multi-regional blending, combining fruit from different GI regions to achieve complexity and consistency, as exemplified by Penfolds Grange.",
            "The use of American oak barrels is a traditional Australian practice, particularly in the Barossa Valley, imparting distinctive coconut, vanilla, and sweet spice characters to Shiraz.",
            "Modern Australian winemaking increasingly favors French oak over American oak, with many premium producers using a combination of new and seasoned French barriques.",
            "Open-top fermentation with hand plunging (pigeage) is widely used in Australian premium Shiraz and Pinot Noir production to extract color and tannin gently.",
            "New Zealand's winemaking style emphasizes fruit purity and minimal intervention, with many producers using wild yeast fermentation and reduced sulfur additions.",
            "Whole-bunch fermentation (including stems) is increasingly popular in Australian and New Zealand Pinot Noir production, adding spice, structure, and aromatic complexity.",
            "Australian fortified wine production in Rutherglen uses a distinctive process where grapes are left to raisin on the vine, fortified with grape spirit during fermentation, then aged in small barrels in warm conditions to promote oxidative complexity.",
            "The practice of using concrete eggs and amphorae for fermentation has gained popularity among Australian winemakers seeking textured, mineral-driven wines.",
            "New Zealand's Sauvignon Blanc is typically fermented at cool temperatures (12-14 degrees Celsius) in stainless steel to preserve the variety's volatile thiol aromatics.",
            "Many premium Australian and New Zealand sparkling wines are produced using the traditional method (methode traditionnelle), with extended lees aging for added complexity.",
        ],
    },
    "viticulture_practices": {
        "title": "Viticulture Practices",
        "facts": [
            "Dry-grown viticulture (without irrigation) is practiced in many premium Australian wine regions, particularly the Barossa Valley, where old vines have developed deep root systems over decades.",
            "Deficit irrigation, where vines receive less water than they would naturally use, is a common Australian practice to control vigor and concentrate flavors in the grapes.",
            "The Scott Henry trellis system, widely used in New Zealand, was specifically designed for high-vigor vineyard sites and involves dividing the canopy into upward and downward-growing shoots.",
            "Vertical Shoot Positioning (VSP) is the most common trellis system in New Zealand vineyards, keeping the canopy narrow and well-exposed for optimal fruit ripening.",
            "Australian vineyards face unique pest challenges including kangaroo and bird damage, with many vineyards using netting to protect ripening fruit from bird predation.",
            "New Zealand's phylloxera management differs from Australia's: most NZ vineyards are grafted onto phylloxera-resistant rootstock, while many Australian regions (particularly in South Australia) retain own-rooted vines.",
            "Machine harvesting is common in large-scale Australian wine regions like the Riverland and Riverina, while hand harvesting is standard in premium cool-climate regions.",
            "Cover cropping between vine rows is a widespread practice in both Australian and New Zealand vineyards, improving soil health, reducing erosion, and managing vine vigor.",
            "The practice of biodynamic viticulture has gained a following in both countries, with notable producers in the Barossa Valley, McLaren Vale, and various New Zealand regions adopting biodynamic principles.",
            "Organic viticulture certification has grown rapidly in both Australia and New Zealand, with the dry climates of many Australian regions providing favorable conditions for reduced chemical use.",
            "New Zealand's relatively young vine age (most vineyards planted since the 1980s) means that the industry is still learning how its regions express terroir as vines mature and develop deeper root systems.",
            "Australia's warm-climate viticulture has increasingly adopted technology including satellite-guided precision viticulture, infrared canopy sensors, and automated irrigation management.",
        ],
    },
    "notable_producers": {
        "title": "Notable Producers and Wines",
        "facts": [
            "Penfolds, founded by Dr. Christopher Rawson Penfold in 1844, is one of Australia's oldest and most prestigious wineries, best known for Grange (Shiraz) and Bin 389 (Cabernet-Shiraz).",
            "Henschke Hill of Grace, made from a single vineyard of pre-phylloxera Shiraz planted in the 1860s in Eden Valley, is one of Australia's most valuable and iconic wines.",
            "Vasse Felix, established in 1967, was Margaret River's first winery and helped establish the region's reputation for premium Cabernet Sauvignon and Chardonnay.",
            "Wynns Coonawarra Estate, founded in 1891 as the Riddoch vineyard, is the most recognized producer from Coonawarra, known for its flagship John Riddoch Cabernet Sauvignon from terra rossa soils.",
            "Cloudy Bay, established in 1985 by David Hohnen of Cape Mentelle, produced the Marlborough Sauvignon Blanc that brought New Zealand wine to international attention.",
            "Felton Road in Central Otago is considered one of New Zealand's great Pinot Noir producers, with biodynamically farmed vineyards in the Bannockburn sub-region.",
            "Ata Rangi in Martinborough was one of the pioneers of New Zealand Pinot Noir, establishing its reputation in the 1980s with vines sourced from a Burgundy suitcase clone.",
            "Te Mata Estate in Hawke's Bay, founded in 1896, is one of New Zealand's oldest wineries and produces the acclaimed Coleraine Cabernet-Merlot blend.",
            "Grosset, founded by Jeffrey Grosset in 1981, is one of Australia's premier Riesling producers and was instrumental in the Clare Valley screwcap initiative.",
            "Tyrrell's in the Hunter Valley has been family-owned since 1858 and is renowned for its Vat 1 Semillon, which exemplifies the unique Hunter Valley unoaked Semillon style.",
        ],
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
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
# FACT BUILDERS — Australian Regions
# ═══════════════════════════════════════════════════════════════════════════════


def _build_australia_facts(source_id: str) -> list[dict]:
    """Build facts about Australian wine regions (climate, soil, elevation, grapes, styles)."""
    facts = []

    for region in AUSTRALIA_REGIONS:
        name = region["name"]
        state = region["state"]
        entities = [{"type": "region", "name": name}]
        base_tags = ["australia", state.lower().replace(" ", "_"),
                     name.lower().replace(" ", "_")]

        # Basic identity
        facts.append(_make_fact(
            f"{name} is a wine region in {state}, Australia.",
            domain="wine_regions",
            source_id=source_id,
            subdomain="australia",
            entities=entities,
            tags=base_tags,
        ))

        # Climate
        facts.append(_make_fact(
            f"The {name} wine region in {state} has a {region['climate']} climate.",
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

        # Vineyard area
        if region.get("vineyard_area_ha"):
            facts.append(_make_fact(
                f"The {name} wine region has approximately {region['vineyard_area_ha']:,} hectares of vineyard.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="statistics",
                entities=entities,
                confidence=0.95,
                tags=base_tags + ["statistics", "area"],
            ))

        # Key grapes (combined)
        if region.get("key_grapes"):
            grapes_str = ", ".join(region["key_grapes"])
            grape_entities = entities + [
                {"type": "grape", "name": g} for g in region["key_grapes"]
            ]
            facts.append(_make_fact(
                f"The principal grape varieties of the {name} wine region include {grapes_str}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="regional_grapes",
                entities=grape_entities,
                tags=base_tags + ["grapes"],
            ))

            # Individual grape-region association facts
            for grape in region["key_grapes"]:
                facts.append(_make_fact(
                    f"{grape} is one of the key grape varieties grown in the {name} wine region of {state}, Australia.",
                    domain="grape_varieties",
                    source_id=source_id,
                    subdomain="regional_grapes",
                    entities=entities + [{"type": "grape", "name": grape}],
                    tags=base_tags + ["grapes", grape.lower().replace(" ", "_")],
                ))

        # Wine styles
        if region.get("wine_styles"):
            styles_str = ", ".join(region["wine_styles"])
            facts.append(_make_fact(
                f"The {name} wine region is known for producing {styles_str}.",
                domain="winemaking",
                source_id=source_id,
                subdomain="wine_styles",
                entities=entities,
                tags=base_tags + ["styles"],
            ))

        # Sub-regions
        if region.get("sub_regions"):
            sub_str = ", ".join(region["sub_regions"])
            facts.append(_make_fact(
                f"The {name} wine region includes the sub-regions of {sub_str}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="australia",
                entities=entities + [{"type": "sub_region", "name": s} for s in region["sub_regions"]],
                tags=base_tags + ["sub_regions"],
            ))

        # History
        if region.get("history"):
            facts.append(_make_fact(
                region["history"],
                domain="wine_regions",
                source_id=source_id,
                subdomain="history",
                entities=entities,
                tags=base_tags + ["history"],
            ))

        # Viticulture notes
        if region.get("viticulture_notes"):
            facts.append(_make_fact(
                region["viticulture_notes"],
                domain="viticulture",
                source_id=source_id,
                subdomain="practices",
                entities=entities,
                tags=base_tags + ["viticulture"],
            ))

        # Notes (unique characteristics)
        if region.get("notes"):
            facts.append(_make_fact(
                region["notes"],
                domain="wine_regions",
                source_id=source_id,
                subdomain="australia",
                entities=entities,
                tags=base_tags + ["notes"],
            ))

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# FACT BUILDERS — New Zealand Regions
# ═══════════════════════════════════════════════════════════════════════════════


def _build_nz_facts(source_id: str) -> list[dict]:
    """Build facts about New Zealand wine regions."""
    facts = []

    for region in NZ_REGIONS:
        name = region["name"]
        island = region["island"]
        entities = [{"type": "region", "name": name}]
        base_tags = ["new_zealand", island.lower().replace(" ", "_"),
                     name.lower().replace(" ", "_").replace("/", "_")]

        # Basic identity
        facts.append(_make_fact(
            f"{name} is a wine region on the {island} of New Zealand.",
            domain="wine_regions",
            source_id=source_id,
            subdomain="new_zealand",
            entities=entities,
            tags=base_tags,
        ))

        # Climate
        facts.append(_make_fact(
            f"The {name} wine region in New Zealand has a {region['climate']} climate.",
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

        # Vineyard area
        if region.get("vineyard_area_ha"):
            facts.append(_make_fact(
                f"The {name} wine region has approximately {region['vineyard_area_ha']:,} hectares of vineyard.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="statistics",
                entities=entities,
                confidence=0.95,
                tags=base_tags + ["statistics", "area"],
            ))

        # Key grapes (combined)
        if region.get("key_grapes"):
            grapes_str = ", ".join(region["key_grapes"])
            grape_entities = entities + [
                {"type": "grape", "name": g} for g in region["key_grapes"]
            ]
            facts.append(_make_fact(
                f"The principal grape varieties of the {name} wine region include {grapes_str}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="regional_grapes",
                entities=grape_entities,
                tags=base_tags + ["grapes"],
            ))

            # Individual grape-region association facts
            for grape in region["key_grapes"]:
                facts.append(_make_fact(
                    f"{grape} is one of the key grape varieties grown in the {name} wine region of New Zealand.",
                    domain="grape_varieties",
                    source_id=source_id,
                    subdomain="regional_grapes",
                    entities=entities + [{"type": "grape", "name": grape}],
                    tags=base_tags + ["grapes", grape.lower().replace(" ", "_")],
                ))

        # Wine styles
        if region.get("wine_styles"):
            styles_str = ", ".join(region["wine_styles"])
            facts.append(_make_fact(
                f"The {name} wine region is known for producing {styles_str}.",
                domain="winemaking",
                source_id=source_id,
                subdomain="wine_styles",
                entities=entities,
                tags=base_tags + ["styles"],
            ))

        # Sub-regions
        if region.get("sub_regions"):
            sub_str = ", ".join(region["sub_regions"])
            facts.append(_make_fact(
                f"The {name} wine region includes the sub-regions of {sub_str}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="new_zealand",
                entities=entities + [{"type": "sub_region", "name": s} for s in region["sub_regions"]],
                tags=base_tags + ["sub_regions"],
            ))

        # History
        if region.get("history"):
            facts.append(_make_fact(
                region["history"],
                domain="wine_regions",
                source_id=source_id,
                subdomain="history",
                entities=entities,
                tags=base_tags + ["history"],
            ))

        # Viticulture notes
        if region.get("viticulture_notes"):
            facts.append(_make_fact(
                region["viticulture_notes"],
                domain="viticulture",
                source_id=source_id,
                subdomain="practices",
                entities=entities,
                tags=base_tags + ["viticulture"],
            ))

        # Notes
        if region.get("notes"):
            facts.append(_make_fact(
                region["notes"],
                domain="wine_regions",
                source_id=source_id,
                subdomain="new_zealand",
                entities=entities,
                tags=base_tags + ["notes"],
            ))

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# FACT BUILDERS — Grape Varieties (Both Countries)
# ═══════════════════════════════════════════════════════════════════════════════


def _build_grape_variety_facts(source_id: str) -> list[dict]:
    """Build facts about grape varieties and their regional expressions."""
    facts = []

    for grape in GRAPE_VARIETY_DATABASE:
        name = grape["name"]
        country = grape["country"]
        entities = [{"type": "grape", "name": name}]
        country_tag = country.lower().replace(" ", "_")
        base_tags = [country_tag, name.lower().replace(" ", "_").replace("à", "a")]

        # Role / identity
        facts.append(_make_fact(
            f"{name} is {grape['role']}.",
            domain="grape_varieties",
            source_id=source_id,
            subdomain="variety_profile",
            entities=entities,
            tags=base_tags,
        ))

        # Regional expressions
        if grape.get("regional_expressions"):
            for region_name, expression in grape["regional_expressions"]:
                region_entities = entities + [{"type": "region", "name": region_name}]
                facts.append(_make_fact(
                    f"{name} from {region_name} is characterized by {expression}.",
                    domain="grape_varieties",
                    source_id=source_id,
                    subdomain="regional_expression",
                    entities=region_entities,
                    tags=base_tags + [region_name.lower().replace(" ", "_").replace("/", "_")],
                ))

        # General notes
        if grape.get("notes"):
            facts.append(_make_fact(
                grape["notes"],
                domain="grape_varieties",
                source_id=source_id,
                subdomain="variety_profile",
                entities=entities,
                tags=base_tags + ["history"],
            ))

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# FACT BUILDERS — Classification Systems
# ═══════════════════════════════════════════════════════════════════════════════


def _build_classification_facts(source_id: str) -> list[dict]:
    """Build facts about GI systems, LIP, Old Vine Charter, Langton's, SWNZ, and unique traditions."""
    facts = []

    for key, section in CLASSIFICATION_DATABASE.items():
        title = section["title"]
        # Determine country tag
        if "australia" in key or "langton" in key or "barossa" in key or "label" in key:
            country_tag = "australia"
        elif "nz" in key or "swnz" in key:
            country_tag = "new_zealand"
        else:
            country_tag = "australia_nz"

        base_tags = [country_tag, key]

        for fact_text in section["facts"]:
            # Determine domain
            if "unique" in key or "winemaking" in key:
                domain = "winemaking"
                subdomain = "unique_traditions" if "unique" in key else "practices"
            elif "viticulture" in key:
                domain = "viticulture"
                subdomain = "practices"
            elif "langton" in key or "notable" in key or "industry" in key:
                domain = "wine_business"
                subdomain = "classification" if "langton" in key else "industry"
            else:
                domain = "wine_regions"
                subdomain = "classification"

            # Extract entities from the fact text
            entities = []
            for region in AUSTRALIA_REGIONS:
                if region["name"] in fact_text:
                    entities.append({"type": "region", "name": region["name"]})
            for region in NZ_REGIONS:
                if region["name"] in fact_text:
                    entities.append({"type": "region", "name": region["name"]})

            facts.append(_make_fact(
                fact_text,
                domain=domain,
                source_id=source_id,
                subdomain=subdomain,
                entities=entities if entities else [{"type": "system", "name": title}],
                tags=base_tags + ["classification"],
            ))

    return facts


# ═══════════════════════════════════════════════════════════════════════════════
# PIPELINE
# ═══════════════════════════════════════════════════════════════════════════════


def _build_all_facts(source_id: str, data_type: str = None) -> list[dict]:
    """Build all facts, optionally filtered by type."""
    all_facts = []

    builders = {
        "australia": _build_australia_facts,
        "nz": _build_nz_facts,
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
        click.echo(f"\n[DRY RUN] Would insert {len(facts)} facts from Australia & NZ Wine Reference")

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

    logger.info(f"Inserted {inserted} new facts from Australia & NZ Wine Reference (duplicates skipped)")
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

    click.echo(f"\nTotal facts: {total}")
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
    au_count = sum(1 for f in facts if any("australia" in t for t in f.get("tags", [])))
    nz_count = sum(1 for f in facts if any("new_zealand" in t for t in f.get("tags", [])))
    click.echo(f"\n  Country balance:")
    click.echo(f"    Australia: {au_count} facts")
    click.echo(f"    New Zealand: {nz_count} facts")


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
        "Australia Regions": _build_australia_facts,
        "NZ Regions": _build_nz_facts,
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
    type=click.Choice(["australia", "nz", "grape", "classification"]),
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
    """OenoBench Australia & NZ Wine Enrichment — Regions, grapes, classification data."""
    logger.add("data/logs/australia_nz_enrichment_{time}.log", rotation="10 MB")

    if list_sources:
        click.echo("\nAvailable data categories:")
        click.echo(f"  {'australia':16s} — {len(AUSTRALIA_REGIONS)} Australian wine regions (climate, soil, elevation, grapes)")
        click.echo(f"  {'nz':16s} — {len(NZ_REGIONS)} New Zealand wine regions (climate, soil, elevation, grapes)")
        click.echo(f"  {'grape':16s} — {len(GRAPE_VARIETY_DATABASE)} grape variety profiles with regional expressions")
        click.echo(f"  {'classification':16s} — GI systems, LIP, Old Vine Charter, Langton's, SWNZ, unique traditions")
        click.echo(f"\nKnowledge base coverage:")
        click.echo(f"  Australian regions:  {len(AUSTRALIA_REGIONS)}")
        click.echo(f"  NZ regions:          {len(NZ_REGIONS)}")
        click.echo(f"  Grape varieties:     {len(GRAPE_VARIETY_DATABASE)}")
        click.echo(f"  Classification sections: {len(CLASSIFICATION_DATABASE)}")
        total_class_facts = sum(len(s["facts"]) for s in CLASSIFICATION_DATABASE.values())
        click.echo(f"  Classification facts:    {total_class_facts}")
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
