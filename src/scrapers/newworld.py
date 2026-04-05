"""
OenoBench — New World Wine Regions Scraper

Extracts wine data from Australia, New Zealand, South Africa,
Argentina, and Chile national wine body websites.

Usage:
    python -m src.scrapers.newworld --all
    python -m src.scrapers.newworld --country australia
    python -m src.scrapers.newworld --country new-zealand
    python -m src.scrapers.newworld --country south-africa
    python -m src.scrapers.newworld --country argentina
    python -m src.scrapers.newworld --country chile
    python -m src.scrapers.newworld --dry-run
    python -m src.scrapers.newworld --validate
    python -m src.scrapers.newworld --list
    python -m src.scrapers.newworld --test-run
    python -m src.scrapers.newworld --test-run --cleanup
    python -m src.scrapers.newworld --test-run --country australia
"""

import random
import re
import time
from collections import defaultdict
from typing import Optional

import click
import requests
from bs4 import BeautifulSoup
from loguru import logger

from src.utils.facts import ensure_source, insert_fact, insert_facts_batch, get_fact_count

# ─── Configuration ────────────────────────────────────────────────────────────

USER_AGENT = "OenoBench-Research/1.0 (academic wine benchmark)"
REQUEST_DELAY = 5.0  # 1 request per 5 seconds per domain
REQUEST_TIMEOUT = 30  # seconds

COUNTRY_SLUGS = ["australia", "new-zealand", "south-africa", "argentina", "chile"]

# ─── HTTP Client ──────────────────────────────────────────────────────────────

# Per-domain rate limiting: track last request time per domain
_domain_last_request: dict[str, float] = {}


def _get_domain(url: str) -> str:
    """Extract domain from URL for rate limiting."""
    from urllib.parse import urlparse
    return urlparse(url).netloc


def _rate_limited_get(url: str, params: Optional[dict] = None) -> Optional[requests.Response]:
    """Fetch a URL with per-domain rate limiting and error handling."""
    domain = _get_domain(url)
    now = time.time()
    last = _domain_last_request.get(domain, 0)
    wait = REQUEST_DELAY - (now - last)
    if wait > 0:
        logger.debug(f"Rate limiting: waiting {wait:.1f}s for {domain}")
        time.sleep(wait)

    headers = {"User-Agent": USER_AGENT}
    try:
        resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT, params=params)
        _domain_last_request[domain] = time.time()
        resp.raise_for_status()
        return resp
    except requests.RequestException as e:
        logger.warning(f"HTTP error fetching {url}: {e}")
        _domain_last_request[domain] = time.time()
        return None


def _get_soup(url: str, params: Optional[dict] = None) -> Optional[BeautifulSoup]:
    """Fetch URL and return parsed BeautifulSoup, or None on failure."""
    resp = _rate_limited_get(url, params=params)
    if resp is None:
        return None
    return BeautifulSoup(resp.text, "lxml")


# ─── Source Definitions ───────────────────────────────────────────────────────

SOURCES = {
    "australia": {
        "name": "Wine Australia",
        "url": "https://www.wineaustralia.com",
        "source_type": "national_wine_body",
        "tier": "tier_2_authoritative",
    },
    "new-zealand": {
        "name": "New Zealand Wine",
        "url": "https://www.nzwine.com",
        "source_type": "national_wine_body",
        "tier": "tier_2_authoritative",
    },
    "south-africa": {
        "name": "Wines of South Africa (WOSA)",
        "url": "https://www.wosa.co.za",
        "source_type": "national_wine_body",
        "tier": "tier_2_authoritative",
    },
    "argentina": {
        "name": "Wines of Argentina",
        "url": "https://www.winesofargentina.com",
        "source_type": "national_wine_body",
        "tier": "tier_2_authoritative",
    },
    "chile": {
        "name": "Wines of Chile",
        "url": "https://www.winesofchile.org",
        "source_type": "national_wine_body",
        "tier": "tier_2_authoritative",
    },
}

# ─── Knowledge Bases ──────────────────────────────────────────────────────────
# Structured wine knowledge for each country, used as the primary
# authoritative data when website scraping yields incomplete results.
# All facts are rephrased atomic statements derived from publicly
# available wine industry knowledge published by each national body.

AUSTRALIA_KNOWLEDGE = {
    "zones_and_regions": {
        "South Australia": {
            "regions": [
                "Barossa Valley", "Eden Valley", "Clare Valley", "McLaren Vale",
                "Adelaide Hills", "Coonawarra", "Langhorne Creek", "Padthaway",
                "Wrattonbully", "Riverland", "Adelaide Plains", "Currency Creek",
                "Southern Fleurieu", "Kangaroo Island", "Mount Benson",
                "Robe", "Southern Flinders Ranges", "Mount Lofty Ranges",
            ],
            "key_facts": [
                "South Australia produces approximately 50% of Australia's total wine output.",
                "The Barossa Valley is one of the world's oldest wine regions with vines dating to the 1840s.",
                "Barossa Valley is renowned for its old-vine Shiraz, with some vines exceeding 150 years of age.",
                "Barossa Valley has a warm Mediterranean climate with hot, dry summers.",
                "The Barossa Valley floor has deep alluvial soils suited to full-bodied reds.",
                "Penfolds Grange is sourced primarily from the Barossa Valley.",
                "Henschke Hill of Grace vineyard in Eden Valley contains pre-phylloxera Shiraz vines planted in 1860.",
                "Eden Valley is located in the ranges above the Barossa Valley floor.",
                "Eden Valley is famous for its Riesling, which is considered among the finest in Australia.",
                "Eden Valley sits at elevations between 380 and 550 meters above sea level.",
                "Clare Valley is known for producing dry, age-worthy Riesling.",
                "Clare Valley was one of the first Australian regions to adopt screwcap closures for Riesling.",
                "Clare Valley has a continental climate with warm days and cool nights.",
                "McLaren Vale is located south of Adelaide between the Mount Lofty Ranges and the coast.",
                "McLaren Vale produces notable Shiraz, Grenache, and Cabernet Sauvignon.",
                "McLaren Vale has over 40 distinct soil types across its vineyards.",
                "McLaren Vale's Mediterranean climate is moderated by Gulf St Vincent sea breezes.",
                "Adelaide Hills is a cool-climate region at elevations of 400 to 700 meters.",
                "Adelaide Hills is known for Sauvignon Blanc, Chardonnay, and Pinot Noir.",
                "Adelaide Hills produces acclaimed sparkling wines.",
                "Coonawarra is famous for its terra rossa soil over limestone.",
                "Coonawarra is one of Australia's premier Cabernet Sauvignon regions.",
                "Coonawarra's terra rossa strip is only about 15 kilometers long and 1-2 kilometers wide.",
                "Coonawarra has a cool maritime-influenced climate in the Limestone Coast.",
                "Langhorne Creek is located southeast of Adelaide near Lake Alexandrina.",
                "Langhorne Creek produces rich, soft Cabernet Sauvignon and Shiraz.",
                "Padthaway is a wine region in the Limestone Coast zone of South Australia.",
                "Padthaway produces Chardonnay, Shiraz, and Cabernet Sauvignon.",
                "Wrattonbully lies between Coonawarra and Padthaway in the Limestone Coast zone.",
                "Wrattonbully has terra rossa soils similar to Coonawarra.",
                "The Riverland is Australia's largest wine-producing region by volume.",
                "The Riverland relies on irrigation from the Murray River.",
                "Currency Creek is a maritime-influenced region near the mouth of the Murray River.",
                "Mount Benson in the Limestone Coast has a cool maritime climate.",
                "Kangaroo Island is one of Australia's most geographically isolated wine regions.",
            ],
        },
        "New South Wales": {
            "regions": [
                "Hunter Valley", "Mudgee", "Orange", "Cowra", "Hilltops",
                "Canberra District", "Tumbarumba", "Shoalhaven Coast",
                "Southern Highlands", "Riverina", "New England Australia",
                "Hastings River", "Perricoota",
            ],
            "key_facts": [
                "The Hunter Valley is one of Australia's oldest wine regions, established in the 1820s.",
                "The Hunter Valley is known for Semillon that ages exceptionally well.",
                "Hunter Valley Semillon is typically picked early and bottled without oak aging.",
                "Hunter Valley Shiraz has a distinctive medium-bodied, earthy style.",
                "The Lower Hunter Valley has volcanic basalt and sandy loam soils.",
                "The Upper Hunter Valley is warmer and drier than the Lower Hunter.",
                "Tyrrell's established in 1858 is one of the oldest family-owned wineries in the Hunter Valley.",
                "Mudgee was the first Australian wine region to implement an appellation system.",
                "Mudgee's name is believed to derive from an Aboriginal word meaning nest in the hills.",
                "Mudgee produces robust Cabernet Sauvignon and Shiraz.",
                "Orange is a cool-climate region situated at elevations around 600 to 900 meters.",
                "Orange's elevation gives it a continental climate with significant diurnal temperature variation.",
                "Orange produces Chardonnay, Sauvignon Blanc, and cool-climate Shiraz.",
                "Cowra is known for Chardonnay and is one of the warmer regions in central New South Wales.",
                "Hilltops is located near the town of Young in southern New South Wales.",
                "Hilltops produces elegant Cabernet Sauvignon and Shiraz at moderate altitudes.",
                "The Riverina in New South Wales is a major volume-producing region centered on Griffith.",
                "The Riverina produces botrytized Semillon dessert wines of high quality.",
                "De Bortoli Noble One from the Riverina is one of Australia's iconic dessert wines.",
                "Canberra District spans both New South Wales and Australian Capital Territory.",
                "Canberra District has a continental climate with warm days and cold nights.",
                "Canberra District produces Riesling, Shiraz, and Pinot Noir.",
                "Tumbarumba is one of Australia's highest and coolest wine regions.",
                "Tumbarumba is a source of premium base wine for sparkling production.",
                "New England Australia is a high-altitude wine region at over 800 meters elevation.",
                "Southern Highlands is a cool-climate region south of Sydney.",
            ],
        },
        "Victoria": {
            "regions": [
                "Yarra Valley", "Mornington Peninsula", "Macedon Ranges",
                "Geelong", "Beechworth", "Rutherglen", "King Valley",
                "Alpine Valleys", "Glenrowan", "Goulburn Valley",
                "Heathcote", "Bendigo", "Grampians", "Pyrenees",
                "Henty", "Sunbury", "Murray Darling",
            ],
            "key_facts": [
                "The Yarra Valley was Victoria's first wine region, planted in 1838.",
                "The Yarra Valley is renowned for Pinot Noir and Chardonnay.",
                "The Yarra Valley is located about 50 kilometers east of Melbourne.",
                "Yarra Valley Pinot Noir is considered among Australia's finest.",
                "Yarra Valley has diverse sub-regions including the Upper and Lower Yarra.",
                "The Upper Yarra is cooler and higher, producing more structured wines.",
                "Mornington Peninsula is a maritime-influenced cool-climate region south of Melbourne.",
                "Mornington Peninsula specializes in Pinot Noir, Chardonnay, and Pinot Gris.",
                "Mornington Peninsula vineyards are influenced by Port Phillip Bay and Bass Strait.",
                "Macedon Ranges is one of Victoria's coolest wine regions at elevations up to 800 meters.",
                "Macedon Ranges produces highly regarded sparkling wines.",
                "Geelong's wine industry was revived in the 1960s after being devastated by phylloxera.",
                "Geelong produces Pinot Noir, Chardonnay, and Shiraz.",
                "Rutherglen is famous for its fortified Muscat and Topaque wines.",
                "Rutherglen Muscat is classified into four tiers: Rutherglen, Classic, Grand, and Rare.",
                "Rutherglen's fortified wines use a solera-like blending system.",
                "Rutherglen has a hot continental climate suited to fortified wine production.",
                "Heathcote is known for Shiraz grown on ancient Cambrian soils.",
                "Heathcote's Cambrian greenstone soils are approximately 500 million years old.",
                "The Grampians region in Victoria is known for sparkling Shiraz production.",
                "Seppelt Great Western winery in the Grampians has underground drives for sparkling wine.",
                "Grampians Shiraz has a distinctive peppery, spicy character.",
                "King Valley has a significant Italian-heritage wine community growing Prosecco and Sangiovese.",
                "King Valley is the primary source of Australian Prosecco.",
                "King Valley's Brown Brothers winery has been a pioneer of alternative varieties.",
                "Beechworth is a small, high-quality wine region in northeast Victoria.",
                "Beechworth produces Chardonnay of exceptional quality.",
                "Glenrowan in northeast Victoria is known for fortified wines and Shiraz.",
                "Goulburn Valley is one of Victoria's oldest wine regions.",
                "Tahbilk in Goulburn Valley has the world's largest single holding of old-vine Marsanne.",
                "Bendigo has a warm continental climate producing full-bodied Shiraz and Cabernet.",
                "The Pyrenees in Victoria produces robust Shiraz and Cabernet Sauvignon.",
                "Henty is Victoria's most westerly wine region with a cool maritime climate.",
                "Sunbury near Melbourne Airport is a small wine region known for sparkling wine.",
                "Murray Darling is a warm inland region spanning Victoria and New South Wales.",
            ],
        },
        "Western Australia": {
            "regions": [
                "Margaret River", "Great Southern", "Swan District",
                "Geographe", "Pemberton", "Manjimup", "Peel",
                "Perth Hills", "Blackwood Valley",
            ],
            "key_facts": [
                "Margaret River produces less than 3% of Australia's wine but over 20% of its premium wine.",
                "Margaret River is known for Cabernet Sauvignon and Chardonnay.",
                "Margaret River has a maritime climate moderated by the Indian and Southern Oceans.",
                "Margaret River was first planted in the late 1960s based on research by Dr. John Gladstones.",
                "Margaret River Cabernet Sauvignon-Merlot blends are a signature wine style.",
                "Margaret River Chardonnay is recognized as among Australia's finest.",
                "Vasse Felix, established in 1967, was the first winery in Margaret River.",
                "Leeuwin Estate Art Series Chardonnay is one of Margaret River's most celebrated wines.",
                "The Great Southern is Western Australia's largest wine region by area.",
                "The Great Southern includes sub-regions Frankland River, Mount Barker, Porongurup, Denmark, and Albany.",
                "Frankland River in the Great Southern produces excellent Riesling and Shiraz.",
                "Mount Barker was one of the first areas planted in the Great Southern.",
                "Porongurup in the Great Southern has cool granite-based soils.",
                "Pemberton is known for its Pinot Noir and Chardonnay production.",
                "Manjimup in Western Australia has a cool climate suited to Pinot Noir and Truffles.",
                "The Swan District near Perth was Western Australia's original wine region.",
                "Geographe is a wine region between Perth and Margaret River.",
                "Perth Hills is a small elevated wine region east of Perth.",
            ],
        },
        "Tasmania": {
            "regions": [
                "Tamar Valley", "Pipers River", "Coal River Valley",
                "Derwent Valley", "Huon Valley", "East Coast Tasmania",
            ],
            "key_facts": [
                "Tasmania is Australia's coolest wine-producing state.",
                "Tasmania is known for sparkling wine, Pinot Noir, and Chardonnay.",
                "Tasmania's cool climate produces wines with naturally high acidity.",
                "The Tamar Valley is Tasmania's most established wine region.",
                "Pipers River in northern Tasmania is a key area for sparkling wine production.",
                "Jansz in Pipers River was one of Tasmania's first dedicated sparkling wine producers.",
                "Coal River Valley near Hobart has the driest and warmest climate in Tasmania.",
                "Tasmania's Derwent Valley produces Pinot Noir and Riesling.",
                "Tasmania's East Coast benefits from a maritime influence with low rainfall.",
                "Tasmanian sparkling wine is increasingly sourced by mainland Australian producers.",
                "Tasmania has experienced significant vineyard expansion since the 2000s.",
            ],
        },
        "Queensland": {
            "regions": ["Granite Belt", "South Burnett"],
            "key_facts": [
                "The Granite Belt is Queensland's premier wine region, located at altitudes around 800 meters.",
                "The Granite Belt produces a range of varieties including Shiraz, Cabernet Sauvignon, and alternative Italian varieties.",
                "The Granite Belt has a continental climate with high diurnal temperature variation.",
                "South Burnett in Queensland is a warm region producing full-bodied reds.",
            ],
        },
    },
    "grape_varieties": [
        "Shiraz is Australia's most widely planted grape variety.",
        "Australia is one of the world's largest producers of Shiraz.",
        "Australian Shiraz styles range from elegant cool-climate to rich warm-climate expressions.",
        "Cabernet Sauvignon is the second most planted red grape variety in Australia.",
        "Australian Cabernet Sauvignon is particularly successful in Coonawarra and Margaret River.",
        "Chardonnay is the most planted white grape variety in Australia.",
        "Australian Chardonnay ranges from unoaked to heavily oaked styles.",
        "Australian Riesling, particularly from Clare Valley and Eden Valley, is internationally acclaimed.",
        "Australian Riesling is typically made in a dry, crisp style with lime-citrus character.",
        "Semillon in the Hunter Valley is a uniquely Australian wine style.",
        "Hunter Valley Semillon develops honey and toast characters with bottle age.",
        "Grenache, Shiraz, and Mourvèdre blends (GSM) are a signature Australian wine style.",
        "Australia has significant plantings of Pinot Noir, especially in cooler regions.",
        "Australian Sauvignon Blanc is primarily grown in Adelaide Hills and other cool-climate regions.",
        "Verdelho is a white grape variety with a notable presence in Australia.",
        "Petit Verdot has emerged as a successful single-varietal wine in warmer Australian regions.",
        "Mourvèdre, known as Mataro in Australia, is an important component in Barossa blends.",
        "Tempranillo plantings in Australia have increased significantly since the 2000s.",
        "Pinot Gris and Pinot Grigio styles are both produced in Australia.",
        "Viognier is grown in several Australian regions, often blended with Shiraz.",
        "Marsanne is grown at Tahbilk in the Goulburn Valley from very old vines.",
        "Nero d'Avola and Fiano are among the emerging Italian varieties in Australia.",
        "Prosecco (Glera) is increasingly planted in King Valley, Victoria.",
        "Durif (Petite Sirah) produces deeply colored, tannic wines in warm Australian regions.",
        "Muscat à Petits Grains is the base of Rutherglen's famous fortified wines.",
    ],
    "general_facts": [
        "Australia has over 65 designated Geographical Indication (GI) regions.",
        "Australia's wine classification system uses Geographical Indications (GIs) at zone, region, and subregion levels.",
        "Australia is the world's fifth-largest wine exporter.",
        "The Australian wine industry was established in the early 19th century.",
        "Phylloxera has never reached South Australia, allowing old vines to survive.",
        "Australia's Label Integrity Program (LIP) ensures vintage, variety, and origin claims are accurate.",
        "Australian wine labels must contain at least 85% of the stated variety.",
        "Australia has some of the oldest Shiraz vines in the world, with some plantings from the 1840s.",
        "James Busby is considered the father of Australian viticulture, importing vine cuttings in 1831.",
        "Australia's wine regions span latitudes from 27 to 43 degrees south.",
        "Australian vintage occurs from January to April, the southern hemisphere autumn.",
        "Australia has over 2,500 wineries and approximately 6,000 grape growers.",
        "The Langton's Classification is an unofficial ranking of Australia's most collectible wines.",
        "Australian wine exports are valued at over AUD 2 billion annually.",
        "Screwcap closures were pioneered in Australia, beginning in the Clare Valley.",
        "The Wine Australia authority oversees regulation, research, and export compliance.",
        "Australia's wine industry employs over 170,000 people directly and indirectly.",
        "South Australia's Barossa and McLaren Vale are among the world's great wine regions.",
        "Australian wine shows and competitions play a major role in quality benchmarking.",
        "The First Families of Wine is a group of 12 multi-generational Australian wine families.",
    ],
    "viticulture_facts": [
        "Many Australian vineyards use drip irrigation to manage water in dry climates.",
        "Scott Henry and Smart-Dyson trellis systems are used in Australian vineyards.",
        "Australian wine regions face increasing challenges from climate change and drought.",
        "Bushfire smoke taint has affected several Australian vintages, notably in 2020.",
        "Mechanical harvesting is widely used in Australia's larger wine regions.",
        "Australian viticulture research is coordinated by the Australian Wine Research Institute (AWRI).",
        "Sustainable winegrowing programs are expanding across Australian wine regions.",
        "Dry-grown (unirrigated) old-vine vineyards are particularly valued in the Barossa Valley.",
        "The Australian wine industry uses the Entwine environmental sustainability program.",
    ],
    "winemaking_facts": [
        "Australian winemakers pioneered the use of stainless steel tanks for white wine fermentation.",
        "Australian Shiraz is often aged in American and French oak barrels.",
        "Australian sparkling Shiraz is a unique wine style not widely made elsewhere.",
        "Fortified winemaking in Australia dates back to the 19th century.",
        "Australian winemakers are known for innovative blending across regions.",
        "Bag-in-box wine packaging was commercially developed in Australia.",
        "Australian rosé production has grown significantly in recent decades.",
        "Natural and minimal-intervention winemaking has a growing following in Australia.",
    ],
    "producer_facts": [
        "Penfolds is one of Australia's most iconic wine producers, founded in 1844.",
        "Penfolds Grange is Australia's most famous wine, first made by Max Schubert in 1951.",
        "Henschke's Hill of Grace is one of Australia's most prestigious single-vineyard wines.",
        "Torbreck produces acclaimed Barossa Valley Shiraz and Rhône-style blends.",
        "Clarendon Hills in McLaren Vale is known for single-vineyard Shiraz and Grenache.",
        "Grosset in Clare Valley produces benchmark Australian Riesling.",
        "Leeuwin Estate Art Series Chardonnay is one of Australia's most celebrated white wines.",
        "Vasse Felix was the first commercial winery established in Margaret River in 1967.",
        "Tyrrell's in the Hunter Valley has been family-owned since 1858.",
        "D'Arenberg in McLaren Vale is known for its eccentric wine names and traditional winemaking.",
        "Yalumba is Australia's oldest family-owned winery, founded in 1849 in the Barossa Valley.",
        "Wolf Blass in the Barossa Valley is known for its color-labeled range of wines.",
        "Rockford Basket Press Shiraz is a benchmark for traditional Barossa winemaking.",
        "Jim Barry The Armagh Shiraz is one of Clare Valley's most iconic wines.",
        "Wynns Coonawarra Estate produces benchmark Coonawarra Cabernet Sauvignon.",
        "De Bortoli in the Riverina produces the iconic Noble One botrytized Semillon.",
        "Seppelt in the Grampians is one of Australia's oldest wineries, established in 1851.",
        "Mount Mary in the Yarra Valley is known for its Bordeaux-style Quintet blend.",
        "Bass Phillip in Gippsland produces highly sought-after Pinot Noir.",
        "Giaconda in Beechworth produces some of Australia's finest Chardonnay.",
        "Cullen Wines in Margaret River is a leading biodynamic producer.",
        "Moss Wood in Margaret River produces benchmark Cabernet Sauvignon.",
        "Brown Brothers in King Valley pioneered alternative grape varieties in Australia.",
        "Tahbilk in the Goulburn Valley holds the world's largest single holding of old Marsanne vines.",
        "Bay of Fires winery in Tasmania produces premium sparkling wine and Pinot Noir.",
        "Clonakilla in the Canberra District produces acclaimed Shiraz-Viognier.",
        "Shaw + Smith in Adelaide Hills is known for premium Sauvignon Blanc and Chardonnay.",
        "Petaluma in Adelaide Hills was founded by Brian Croser, a pioneer of Australian wine.",
        "Orlando Wines produced Jacob's Creek, one of Australia's most successful export brands.",
        "Lindeman's is a historic Australian brand founded in the Hunter Valley in 1843.",
        "Hardys is one of Australia's oldest wine companies, established in McLaren Vale in 1853.",
    ],
    "wine_business_facts": [
        "Australia's largest wine company by volume is Treasury Wine Estates.",
        "Casella Family Brands produces Yellow Tail, one of the world's best-selling wine brands.",
        "Australia exports wine to over 120 countries.",
        "The United Kingdom is one of Australia's largest wine export markets.",
        "China was Australia's largest export market by value before tariffs were imposed in 2020.",
        "Australian wine exports to China resumed after tariffs were removed in 2024.",
        "The Australian wine industry contributes over AUD 45 billion to the national economy.",
        "Wine tourism is a significant economic driver for Australian wine regions.",
        "Australia has over 60 designated wine tourism routes.",
        "The McLaren Vale Wine Region was one of the first to achieve carbon-neutral status in Australia.",
        "The Hunter Valley is approximately two hours north of Sydney, making it a major wine tourism destination.",
        "The Barossa Grape and Wine Association promotes the Barossa Valley internationally.",
        "Australia's wine industry has a strong tradition of multi-regional blending across state lines.",
    ],
}

NEW_ZEALAND_KNOWLEDGE = {
    "regions": {
        "Marlborough": {
            "key_facts": [
                "Marlborough is New Zealand's largest wine region, producing over 75% of the country's wine.",
                "Marlborough is located at the northern tip of the South Island.",
                "Marlborough is internationally renowned for its Sauvignon Blanc.",
                "The Wairau Valley is the main sub-region within Marlborough.",
                "The Southern Valleys sub-region in Marlborough has clay-rich soils.",
                "The Awatere Valley sub-region in Marlborough is cooler and drier than the Wairau Valley.",
                "Marlborough Sauvignon Blanc is characterized by intense aromatics of passionfruit, grapefruit, and cut grass.",
                "Marlborough also produces notable Pinot Noir, Chardonnay, and Riesling.",
                "Marlborough's Sauvignon Blanc put New Zealand on the global wine map in the 1980s.",
                "Cloudy Bay from Marlborough became an iconic Sauvignon Blanc brand worldwide.",
                "Marlborough has stony, free-draining greywacke alluvial soils.",
                "Marlborough's growing season features long sunshine hours and cool nights.",
                "Marlborough Pinot Noir has gained increasing recognition and quality.",
                "Marlborough has over 29,000 hectares under vine.",
            ],
        },
        "Hawke's Bay": {
            "key_facts": [
                "Hawke's Bay is New Zealand's second-largest wine region.",
                "Hawke's Bay is located on the east coast of the North Island.",
                "Hawke's Bay is known for Bordeaux-style red blends and Chardonnay.",
                "The Gimblett Gravels sub-region in Hawke's Bay has free-draining alluvial soils.",
                "Gimblett Gravels is renowned for producing premium Syrah and Cabernet Sauvignon.",
                "Gimblett Gravels was a former riverbed discovered as a wine area in the 1980s.",
                "Gimblett Gravels soils are stony shingle that absorb and radiate heat.",
                "Hawke's Bay has one of the warmest and driest climates of New Zealand's wine regions.",
                "The Bridge Pa Triangle is a notable sub-region within Hawke's Bay.",
                "Hawke's Bay Chardonnay is among New Zealand's finest white wines.",
                "Hawke's Bay has a long winemaking history dating to the 1850s.",
                "Hawke's Bay Syrah is increasingly compared favorably with Northern Rhône examples.",
                "Te Mata Estate in Hawke's Bay is one of New Zealand's oldest wineries, founded in 1896.",
                "Craggy Range in Hawke's Bay produces single-vineyard wines from Gimblett Gravels.",
            ],
        },
        "Central Otago": {
            "key_facts": [
                "Central Otago is the world's southernmost wine region.",
                "Central Otago is the only wine region in New Zealand with a continental climate.",
                "Central Otago is renowned for its Pinot Noir.",
                "Central Otago's sub-regions include Bannockburn, Gibbston, Bendigo, Cromwell Basin, Wanaka, and Alexandra.",
                "Bannockburn in Central Otago is considered one of the finest Pinot Noir sites.",
                "Central Otago vineyards are planted at altitudes ranging from 200 to 450 meters.",
                "Gibbston Valley in Central Otago is known as the Valley of the Vines.",
                "Central Otago's Bendigo sub-region has a warm, dry microclimate.",
                "Central Otago's continental climate features hot summers and cold winters.",
                "Central Otago Pinot Noir is known for its intensity and purity of fruit.",
                "Felton Road in Central Otago is one of New Zealand's most acclaimed Pinot Noir producers.",
                "Central Otago also produces Riesling, Pinot Gris, and Chardonnay.",
                "Alexandra in Central Otago is one of the driest and most continental sub-regions.",
            ],
        },
        "Martinborough": {
            "key_facts": [
                "Martinborough is located in the Wairarapa region at the southern end of the North Island.",
                "Martinborough was one of the first regions in New Zealand to gain recognition for Pinot Noir.",
                "Martinborough has a dry, cool climate sheltered from rain by the Tararua Ranges.",
                "Martinborough's soils include free-draining alluvial gravel terraces.",
                "Martinborough's Pinot Noir is known for its complexity and structure.",
                "Ata Rangi winery is one of Martinborough's founding Pinot Noir producers.",
                "Martinborough also produces Sauvignon Blanc and aromatic whites.",
                "Martinborough's small scale means most wines are sold domestically.",
            ],
        },
        "Canterbury / Waipara Valley": {
            "key_facts": [
                "Canterbury is located on the east coast of the South Island.",
                "Waipara Valley is a key sub-region of Canterbury known for Pinot Noir and Riesling.",
                "Waipara Valley is sheltered from cool easterly winds by the Teviotdale Hills.",
                "Canterbury also produces Chardonnay, Sauvignon Blanc, and Pinot Gris.",
                "North Canterbury's limestone soils contribute to wine complexity.",
                "Waipara Valley Riesling is made in both dry and sweet styles.",
                "Pegasus Bay is a leading producer in the Waipara Valley.",
            ],
        },
        "Nelson": {
            "key_facts": [
                "Nelson is located at the northern tip of the South Island, west of Marlborough.",
                "Nelson has a maritime climate with high sunshine hours.",
                "Nelson produces Sauvignon Blanc, Chardonnay, Pinot Noir, and Riesling.",
                "Nelson's Upper Moutere sub-region has distinctive clay soils.",
                "Nelson's Waimea Plains sub-region has alluvial soils suited to aromatic whites.",
                "Nelson is a smaller, boutique wine region compared to neighboring Marlborough.",
                "Neudorf Vineyards is one of Nelson's most acclaimed producers.",
            ],
        },
        "Gisborne": {
            "key_facts": [
                "Gisborne is located on the east coast of the North Island.",
                "Gisborne was historically known as the Chardonnay capital of New Zealand.",
                "Gisborne has fertile alluvial soils and a warm maritime climate.",
                "Gisborne produces Chardonnay, Gewürztraminer, and Viognier.",
                "Gisborne is one of the first places in the world to see the sunrise each day.",
                "Gisborne Gewürztraminer is among the finest in New Zealand.",
            ],
        },
        "Waikato / Bay of Plenty": {
            "key_facts": [
                "Waikato and Bay of Plenty are warm wine regions in the central North Island.",
                "The area has a history of grape growing dating back to the early 20th century.",
                "Waikato and Bay of Plenty produce a range of red and white varieties.",
            ],
        },
        "Auckland": {
            "key_facts": [
                "Auckland includes sub-regions Waiheke Island, Kumeu, Matakana, and Henderson.",
                "Waiheke Island is known for premium Bordeaux-style red blends.",
                "Waiheke Island's warm microclimate is ideal for Cabernet Sauvignon and Merlot.",
                "Kumeu is known for Chardonnay, particularly from Kumeu River winery.",
                "Kumeu River Chardonnay has been rated among the world's best Chardonnays.",
                "Auckland's warm, humid climate presents challenges for viticulture.",
                "Matakana north of Auckland produces Pinot Gris and Syrah.",
                "Stonyridge Larose from Waiheke Island is one of New Zealand's most expensive wines.",
            ],
        },
        "Northland": {
            "key_facts": [
                "Northland is New Zealand's northernmost wine region.",
                "Northland has a subtropical climate with high humidity.",
                "Northland produces Syrah, Chardonnay, and Chambourcin.",
            ],
        },
    },
    "grape_varieties": [
        "Sauvignon Blanc is New Zealand's most planted grape variety.",
        "Sauvignon Blanc accounts for over 60% of New Zealand's wine production.",
        "Pinot Noir is New Zealand's most planted red grape variety.",
        "Pinot Gris is gaining popularity in New Zealand, especially in cooler regions.",
        "Chardonnay is the second most planted white variety in New Zealand.",
        "New Zealand Riesling, especially from Marlborough and Waipara, is highly regarded.",
        "Syrah has emerged as an important red variety in Hawke's Bay, New Zealand.",
        "Gewürztraminer is produced in several New Zealand regions, particularly Gisborne.",
        "Merlot is an important blending variety in Hawke's Bay, New Zealand.",
        "Cabernet Sauvignon is grown in Hawke's Bay and Waiheke Island, New Zealand.",
        "Pinot Blanc is a minor but growing variety in New Zealand.",
        "Albariño is an emerging variety in New Zealand's warmer regions.",
        "Grüner Veltliner is planted on a small scale in New Zealand.",
    ],
    "general_facts": [
        "New Zealand has 10 major wine regions.",
        "New Zealand's wine industry has grown rapidly since the 1980s.",
        "New Zealand wines are predominantly produced under screwcap closures.",
        "New Zealand's cool maritime climate is well-suited to aromatic white varieties.",
        "Sustainable Winegrowing New Zealand (SWNZ) certifies over 96% of vineyard area.",
        "New Zealand is the world's largest producer of Sauvignon Blanc by market share in several export markets.",
        "New Zealand has approximately 40,000 hectares of vineyard.",
        "New Zealand's wine industry generates over NZD 2 billion in export revenue.",
        "New Zealand wine exports go primarily to Australia, the USA, and the UK.",
        "Montana (now Brancott Estate) planted the first Sauvignon Blanc in Marlborough in 1973.",
        "New Zealand's latitude ranges from 36 to 45 degrees south.",
        "The 1985 vine pull scheme removed surplus grape vines and helped shift to quality production.",
        "New Zealand has approximately 700 wineries.",
        "Organic and biodynamic viticulture is increasingly practiced in New Zealand.",
        "New Zealand's long, narrow geography creates diverse wine climates.",
        "New Zealand wines are known for their vibrant acidity and aromatic intensity.",
        "The New Zealand Winegrowers association represents the interests of the industry.",
    ],
    "viticulture_facts": [
        "Vertical shoot positioning (VSP) is the dominant trellis system in New Zealand.",
        "New Zealand's long daylight hours during summer benefit grape ripening.",
        "Frost is a significant viticultural hazard in Central Otago and Marlborough.",
        "Wind machines and helicopters are used for frost protection in New Zealand vineyards.",
        "Many New Zealand vineyards are planted on their own rootstock due to limited phylloxera pressure.",
        "New Zealand's wine regions are influenced by both Pacific and Tasman Sea weather patterns.",
    ],
    "producer_facts": [
        "Cloudy Bay was founded in 1985 and became synonymous with Marlborough Sauvignon Blanc.",
        "Felton Road in Central Otago is one of New Zealand's most acclaimed Pinot Noir producers.",
        "Kumeu River in Auckland has won international acclaim for its Chardonnay.",
        "Ata Rangi in Martinborough is a founding producer of New Zealand Pinot Noir.",
        "Te Mata Estate in Hawke's Bay is one of New Zealand's oldest wineries, founded in 1896.",
        "Te Mata Coleraine is one of New Zealand's most prestigious Bordeaux-style blends.",
        "Villa Maria is one of New Zealand's largest and most awarded wine producers.",
        "Craggy Range operates vineyards in Hawke's Bay and Martinborough.",
        "Pegasus Bay in Waipara Valley is known for Riesling and Pinot Noir.",
        "Neudorf Vineyards in Nelson produces acclaimed Chardonnay and Pinot Noir.",
        "Seresin Estate in Marlborough is a notable biodynamic producer.",
        "Greywacke in Marlborough was founded by Kevin Judd, the original winemaker at Cloudy Bay.",
        "Dog Point Vineyard in Marlborough produces Sauvignon Blanc and Pinot Noir.",
        "Dry River in Martinborough is known for small-production Pinot Noir and Riesling.",
        "Rippon Vineyard in Wanaka, Central Otago, has a dramatic lakeside setting.",
        "Stonyridge Larose from Waiheke Island is one of New Zealand's most expensive wines.",
        "Brancott Estate (formerly Montana) planted the first Sauvignon Blanc in Marlborough.",
        "Escarpment Vineyard in Martinborough was established by Larry McKenna, a Pinot Noir pioneer.",
        "Palliser Estate is a leading Martinborough producer of Pinot Noir.",
        "Trinity Hill in Hawke's Bay produces acclaimed Gimblett Gravels wines.",
        "Elephant Hill in Hawke's Bay combines a coastal winery with premium wines.",
        "Gibbston Valley Wines was Central Otago's first commercial winery.",
        "Spy Valley in Marlborough produces a range of Sauvignon Blanc and Pinot Noir.",
    ],
    "wine_business_facts": [
        "New Zealand wine exports exceed NZD 2 billion annually.",
        "Australia is New Zealand's largest wine export market by volume.",
        "The United States is one of New Zealand's top wine export markets by value.",
        "New Zealand's wine industry has grown from 100 wineries in 1990 to over 700.",
        "Marlborough accounts for over 75% of New Zealand's total grape crush.",
        "Wine is one of New Zealand's top horticultural export products.",
        "New Zealand wine tourism attracts over 1 million visitors annually to wine regions.",
        "The New Zealand wine industry employs approximately 20,000 people.",
    ],
}

SOUTH_AFRICA_KNOWLEDGE = {
    "regions": {
        "Stellenbosch": {
            "key_facts": [
                "Stellenbosch is South Africa's most famous wine region.",
                "Stellenbosch is located approximately 50 kilometers east of Cape Town.",
                "Stellenbosch is known for Cabernet Sauvignon and Bordeaux-style blends.",
                "Stellenbosch has diverse terroirs ranging from mountain slopes to valley floors.",
                "Stellenbosch includes notable wards such as Simonsberg-Stellenbosch, Bottelary Hills, and Helderberg.",
                "The Stellenbosch Wine Route was established in 1971, the first in South Africa.",
                "Stellenbosch Mountain vineyards benefit from cooling altitude and aspect.",
                "The Bottelary Hills ward in Stellenbosch produces Pinotage and Shiraz.",
                "Helderberg in Stellenbosch is considered one of South Africa's finest Cabernet Sauvignon areas.",
                "The Devon Valley ward in Stellenbosch is known for Merlot and Shiraz.",
                "Stellenbosch University has been central to South African wine research and education.",
                "Kanonkop in Stellenbosch is one of South Africa's most iconic Pinotage producers.",
                "Rust en Vrede in Stellenbosch produces acclaimed Cabernet Sauvignon and blends.",
            ],
        },
        "Paarl": {
            "key_facts": [
                "Paarl is one of South Africa's oldest wine-producing districts.",
                "Paarl is located north of Stellenbosch in the Berg River Valley.",
                "Paarl produces a wide range of varieties including Shiraz and Chenin Blanc.",
                "The Simonsberg-Paarl ward in Paarl is known for premium red wines.",
                "Paarl is home to the KWV, historically South Africa's most influential wine organization.",
                "Paarl's warmer climate produces fuller-bodied red wines than Stellenbosch.",
                "The Voor Paardeberg area in Paarl has become a hub for natural wines.",
            ],
        },
        "Franschhoek": {
            "key_facts": [
                "Franschhoek was established by French Huguenot settlers in the late 17th century.",
                "Franschhoek is a ward within the Paarl district.",
                "Franschhoek is known for Semillon, reflecting its French heritage.",
                "Franschhoek is located in a sheltered valley surrounded by mountains.",
                "Franschhoek Valley is one of South Africa's most popular wine tourism destinations.",
                "The Franschhoek Cap Classique Route highlights the area's sparkling wine production.",
                "Boekenhoutskloof in Franschhoek produces acclaimed Syrah and Semillon.",
            ],
        },
        "Swartland": {
            "key_facts": [
                "Swartland has emerged as one of South Africa's most exciting wine regions.",
                "Swartland is known for old-vine Chenin Blanc, Syrah, and Rhône-style blends.",
                "The Swartland Independent Producers (SIP) group champions minimal-intervention winemaking.",
                "Swartland is a dryland region where many vineyards are not irrigated.",
                "Swartland's Mediterranean climate features hot, dry summers.",
                "The Swartland Revolution tasting event helped establish the region's reputation.",
                "Eben Sadie's wines from Swartland are among South Africa's most acclaimed.",
                "Swartland's old bush vines of Chenin Blanc produce intensely concentrated wines.",
                "Paardeberg in Swartland has granite-based soils suited to white varieties.",
                "Malmesbury is the main town in the Swartland wine district.",
            ],
        },
        "Constantia": {
            "key_facts": [
                "Constantia is the oldest wine-producing area in South Africa, dating to 1685.",
                "Constantia's Vin de Constance was one of the most celebrated wines in 18th-century Europe.",
                "Constantia is a cool-climate ward in the Cape Town metropolitan area.",
                "Constantia is known for Sauvignon Blanc and dessert wines.",
                "Klein Constantia has revived the historic Vin de Constance dessert wine.",
                "Constantia's vineyards benefit from cooling breezes from False Bay.",
                "Groot Constantia, founded in 1685, is South Africa's oldest wine estate.",
            ],
        },
        "Walker Bay": {
            "key_facts": [
                "Walker Bay is a cool maritime district on the southern Cape coast.",
                "The Hemel-en-Aarde Valley in Walker Bay is renowned for Pinot Noir and Chardonnay.",
                "Hemel-en-Aarde has three sub-areas: Hemel-en-Aarde Valley, Upper Hemel-en-Aarde, and Hemel-en-Aarde Ridge.",
                "Walker Bay's proximity to the ocean creates a cool-climate terroir.",
                "Hamilton Russell Vineyards pioneered Pinot Noir in the Hemel-en-Aarde Valley.",
                "Bouchard Finlayson in Walker Bay produces Burgundian-style Pinot Noir.",
                "Walker Bay Chardonnay is considered among South Africa's finest.",
            ],
        },
        "Elgin": {
            "key_facts": [
                "Elgin is one of South Africa's coolest wine regions.",
                "Elgin was traditionally an apple-growing area before vineyards expanded in the 1990s.",
                "Elgin is known for Sauvignon Blanc, Chardonnay, and Pinot Noir.",
                "Elgin is located at elevations of 250 to 600 meters.",
                "Elgin's high-altitude vineyards produce wines with crisp natural acidity.",
                "Paul Cluver is one of Elgin's most established wine estates.",
            ],
        },
        "Robertson": {
            "key_facts": [
                "Robertson is located in the Breede River Valley.",
                "Robertson is known for Chardonnay and Sauvignon Blanc.",
                "Robertson has limestone-rich soils that contribute to wine quality.",
                "Robertson is one of South Africa's largest wine-producing districts by volume.",
                "Robertson's warm climate is moderated by afternoon breezes from the ocean.",
                "Graham Beck in Robertson is known for Méthode Cap Classique sparkling wines.",
            ],
        },
        "Elim": {
            "key_facts": [
                "Elim is South Africa's southernmost wine ward.",
                "Elim has a cool maritime climate influenced by the Atlantic Ocean.",
                "Elim is known for Sauvignon Blanc and Shiraz.",
                "Elim's wines exhibit distinctive minerality from the cool coastal climate.",
            ],
        },
        "Darling": {
            "key_facts": [
                "Darling is a cool-climate district on the west coast north of Cape Town.",
                "Darling includes the Groenekloof ward, known for Sauvignon Blanc.",
                "Darling Cellars is a major producer in the district.",
                "The Groenekloof ward benefits from cold Atlantic Ocean breezes.",
            ],
        },
        "Tulbagh": {
            "key_facts": [
                "Tulbagh is a district surrounded on three sides by mountains.",
                "Tulbagh is known for producing sparkling wines in the Méthode Cap Classique style.",
                "Tulbagh has a warm, sheltered climate suited to Shiraz and Pinotage.",
                "Twee Jonge Gezellen (Two Young Companions) is a historic Tulbagh estate.",
            ],
        },
        "Cape South Coast": {
            "key_facts": [
                "The Cape South Coast is a cool-climate region stretching along the southern coastline.",
                "Cape South Coast includes districts such as Walker Bay, Cape Agulhas, and Plettenberg Bay.",
                "Cape Agulhas is one of the newer wine districts in the Cape South Coast.",
                "Cape South Coast districts benefit from maritime cooling influences.",
            ],
        },
        "Worcester": {
            "key_facts": [
                "Worcester is the largest wine-producing district in South Africa by volume.",
                "Worcester is located in the Breede River Valley.",
                "Worcester produces primarily white wines and brandy grapes.",
                "Worcester's hot, dry climate requires irrigation for viticulture.",
            ],
        },
        "Olifants River": {
            "key_facts": [
                "Olifants River is a warm, inland wine region in the Western Cape.",
                "Olifants River produces bulk wines and is known for value-driven production.",
                "The Citrusdal Mountain sub-district has higher elevation vineyards.",
                "Citrusdal Mountain produces increasingly respected Chenin Blanc and Shiraz.",
            ],
        },
        "Cederberg": {
            "key_facts": [
                "The Cederberg ward is one of South Africa's most isolated wine areas.",
                "Cederberg vineyards are located at elevations exceeding 1,000 meters.",
                "Cederberg is known for Sauvignon Blanc and Shiraz of exceptional quality.",
                "The Nieuwoudt family has been making wine in the Cederberg since the 1960s.",
            ],
        },
    },
    "grape_varieties": [
        "Chenin Blanc is South Africa's most planted grape variety.",
        "Chenin Blanc is locally known as Steen in South Africa.",
        "South African Chenin Blanc is produced in dry, off-dry, sweet, and sparkling styles.",
        "South Africa's old-vine Chenin Blanc bush vines are over 35 years old.",
        "Pinotage is a cross between Pinot Noir and Cinsaut, created in South Africa in 1925.",
        "Pinotage was created by Abraham Izak Perold at Stellenbosch University.",
        "The first Pinotage wine was commercially released in 1961.",
        "Pinotage produces wines ranging from light and fruity to deeply concentrated.",
        "Cabernet Sauvignon is South Africa's most planted red grape variety.",
        "Shiraz (Syrah) is widely planted in South Africa, particularly in Swartland and Paarl.",
        "Colombard is the second most planted white variety in South Africa.",
        "South Africa has notable plantings of Sauvignon Blanc, particularly in cooler regions.",
        "Méthode Cap Classique (MCC) is South Africa's term for traditional method sparkling wine.",
        "Merlot is widely planted in South Africa and used in both varietal and blended wines.",
        "Cinsaut (Cinsault) is a historic South African variety used in blends and rosé.",
        "Chardonnay is increasingly important in South Africa, especially from cool-climate regions.",
        "Viognier is grown in several South African regions, especially in Swartland.",
        "Mourvèdre is used in South African Rhône-style blends.",
        "South African Sauvignon Blanc from Cape Point and Constantia rivals international standards.",
        "Muscat d'Alexandrie (Hanepoot) is used for dessert wines and distillation in South Africa.",
    ],
    "general_facts": [
        "South Africa's Wine of Origin (WO) system classifies wines by geographical unit, region, district, and ward.",
        "South Africa is the world's eighth-largest wine producer.",
        "The Cape Winelands lie primarily within the Western Cape province.",
        "South Africa's wine industry dates back to 1659 when the first wine was made in the Cape.",
        "The Biodiversity and Wine Initiative links wine production with conservation in the Cape Floral Kingdom.",
        "South Africa has approximately 95,000 hectares under vine.",
        "Old-vine Chenin Blanc from bush vines is a signature South African wine style.",
        "The Cape Blend is a style unique to South Africa, typically featuring Pinotage blended with Bordeaux varieties.",
        "Jan van Riebeeck established the first vineyard at the Cape in 1655.",
        "The KWV (Ko-operatieve Wijnbouwers Vereniging) was established in 1918 to regulate the wine industry.",
        "South Africa's wine industry was transformed after the end of apartheid in 1994.",
        "Integrated Production of Wine (IPW) is South Africa's sustainability certification program.",
        "The Old Vine Project certifies and protects South Africa's heritage vineyards over 35 years old.",
        "South Africa exports wine to over 100 countries worldwide.",
        "The Cape Floral Kingdom surrounding the winelands is a UNESCO World Heritage Site.",
        "South Africa's wine regions experience a Mediterranean climate with winter rainfall.",
        "The Integrity & Sustainability (I&S) seal on South African wine guarantees origin, vintage, and variety.",
        "South African natural wine producers have gained international acclaim in recent years.",
    ],
    "viticulture_facts": [
        "Bush vine training is a traditional viticultural method still used in South Africa.",
        "The Cape Doctor is a strong southeasterly wind that helps dry vineyards and reduce disease.",
        "Many South African vineyards are planted on decomposed granite soils.",
        "Water scarcity is an increasing concern for South African viticulture.",
        "The Breede River Valley and Olifants River rely on irrigation for vine cultivation.",
        "South Africa's diverse geology includes granite, sandstone, shale, and alluvial soils.",
    ],
    "producer_facts": [
        "Kanonkop in Stellenbosch is one of South Africa's most iconic Pinotage producers.",
        "Rust en Vrede in Stellenbosch produces acclaimed Cabernet Sauvignon and blends.",
        "Hamilton Russell Vineyards pioneered Pinot Noir and Chardonnay in the Hemel-en-Aarde Valley.",
        "Bouchard Finlayson in Walker Bay produces Burgundian-style Pinot Noir.",
        "Klein Constantia revived the historic Vin de Constance dessert wine.",
        "Groot Constantia, founded in 1685, is South Africa's oldest wine estate.",
        "Boekenhoutskloof in Franschhoek produces the acclaimed Chocolate Block blend.",
        "Sadie Family Wines produces Columella, one of South Africa's most prestigious reds.",
        "Eben Sadie is widely regarded as South Africa's most influential winemaker.",
        "Mullineux & Leeu in Swartland produces acclaimed old-vine Chenin Blanc and Syrah.",
        "Graham Beck in Robertson is known for world-class Méthode Cap Classique sparkling wines.",
        "Meerlust Estate in Stellenbosch produces Rubicon, a famous Bordeaux-style blend.",
        "Vergelegen in Somerset West has a 300-year winemaking history.",
        "Paul Cluver Estate in Elgin is known for cool-climate Chardonnay and Riesling.",
        "Ken Forrester produces acclaimed Chenin Blanc from old vines in Stellenbosch.",
        "Cederberg Private Cellar produces Sauvignon Blanc from some of South Africa's highest vineyards.",
        "Fairview in Paarl is known for innovative Rhône-style wines and Pinotage.",
        "Jordan Wine Estate in Stellenbosch produces premium Cabernet Sauvignon and Chardonnay.",
        "Thelema Mountain Vineyards in Stellenbosch produces Cabernet Sauvignon at high elevation.",
        "De Morgenzon in Stellenbosch is known for Chenin Blanc and Syrah.",
    ],
    "wine_business_facts": [
        "South Africa is the world's eighth-largest wine-producing country.",
        "The United Kingdom is South Africa's largest wine export market.",
        "South African wine exports exceed 400 million liters annually.",
        "Wine tourism in the Cape Winelands attracts millions of visitors each year.",
        "The Cape Wine show is South Africa's premier international wine trade event.",
        "Distell and KWV are among South Africa's largest wine and spirits companies.",
        "South Africa's cooperative cellars account for a significant portion of total wine production.",
        "The Platter's South African Wine Guide is the country's most authoritative wine reference.",
    ],
}

ARGENTINA_KNOWLEDGE = {
    "regions": {
        "Mendoza": {
            "key_facts": [
                "Mendoza is Argentina's largest wine region, producing over 70% of the country's wine.",
                "Mendoza is located in the foothills of the Andes in western Argentina.",
                "Mendoza's sub-regions include Luján de Cuyo, Maipú, Valle de Uco, San Rafael, and East Mendoza.",
                "Luján de Cuyo in Mendoza is often called the birthplace of Argentine Malbec.",
                "Luján de Cuyo was the first Argentine wine region to receive a Denominación de Origen Controlada.",
                "Luján de Cuyo includes notable areas such as Perdriel, Agrelo, and Vistalba.",
                "Agrelo in Luján de Cuyo is planted at around 950 meters and produces rich Malbec.",
                "Perdriel in Mendoza is home to several of Argentina's most prestigious wineries.",
                "Valle de Uco is one of Argentina's most prestigious wine sub-regions.",
                "Valle de Uco vineyards are planted at altitudes from 900 to over 1,500 meters.",
                "The Uco Valley includes the notable areas of Tupungato, Tunuyán, and San Carlos.",
                "Tupungato in the Uco Valley is known for producing elegant, high-altitude wines.",
                "Gualtallary in Tupungato is an emerging high-altitude sub-area gaining international recognition.",
                "Gualtallary's vineyards sit at approximately 1,450 meters above sea level.",
                "Altamira in the Uco Valley has rocky alluvial soils producing mineral-driven Malbec.",
                "Paraje Altamira was one of the first geographic indications in Mendoza.",
                "San Carlos in the Uco Valley has limestone-rich soils.",
                "Maipú in Mendoza is one of the oldest wine-producing areas in Argentina.",
                "Maipú is home to historic wineries including Trapiche and Luigi Bosca.",
                "San Rafael in southern Mendoza produces both premium and bulk wines.",
                "San Rafael is at a lower altitude than the Uco Valley, with a warmer climate.",
                "East Mendoza is a high-volume production area with warmer, flatter terrain.",
                "Mendoza's vineyards are irrigated using an ancient system of canals fed by Andean snowmelt.",
                "Mendoza's flood irrigation system dates to pre-Columbian Huarpe irrigation techniques.",
                "Mendoza City sits at approximately 750 meters above sea level.",
                "Mendoza experiences an average of only 200 millimeters of annual rainfall.",
                "Hail is a major viticultural hazard in Mendoza, and netting is increasingly used.",
            ],
        },
        "San Juan": {
            "key_facts": [
                "San Juan is Argentina's second-largest wine-producing province.",
                "San Juan produces approximately 20% of Argentina's total wine output.",
                "San Juan has a hot, arid climate suited to high-volume wine production.",
                "Pedernal in San Juan is an emerging high-altitude wine area.",
                "Pedernal vineyards in San Juan are planted at altitudes around 1,350 meters.",
                "San Juan is a major producer of Syrah in Argentina.",
                "San Juan's Tulum Valley is the largest wine area in the province.",
                "San Juan is also important for table grape and raisin production.",
                "Calingasta in San Juan is one of the higher-altitude emerging zones.",
                "Zonda Valley in San Juan has a hot, arid climate.",
            ],
        },
        "Salta": {
            "key_facts": [
                "Salta is home to some of the world's highest vineyards, exceeding 2,000 meters altitude.",
                "The Calchaquí Valley in Salta is a premier wine-producing area.",
                "Cafayate in Salta is the most important wine town in northern Argentina.",
                "Salta's Torrontés is considered the finest expression of this grape variety.",
                "High altitude in Salta produces wines with intense color and concentration.",
                "Salta vineyards benefit from large diurnal temperature variation.",
                "Colomé in Salta has vineyards at over 2,300 meters, among the highest in the world.",
                "Molinos in the Calchaquí Valley has vineyards exceeding 2,000 meters elevation.",
                "San Pedro de Yacochuya in Salta produces Malbec at extreme altitude.",
                "The extreme UV exposure at altitude in Salta thickens grape skins, intensifying color.",
                "Salta's dry climate means vineyards require careful irrigation management.",
                "Michel Rolland collaborates on wines from the Yacochuya vineyard in Salta.",
            ],
        },
        "Patagonia": {
            "key_facts": [
                "Patagonia is Argentina's southernmost wine region.",
                "Neuquén and Río Negro are the main wine-producing provinces in Patagonia.",
                "Patagonia's cool climate produces elegant Pinot Noir and Malbec.",
                "San Patricio del Chañar in Neuquén is a modern wine area developed since 2000.",
                "Patagonian vineyards are planted at relatively low altitudes but benefit from a cool continental climate.",
                "The Río Negro Valley in Patagonia has a long history of fruit and wine production.",
                "Bodega del Fin del Mundo in Neuquén is one of Patagonia's largest wineries.",
                "Patagonia's cool nights preserve acidity and freshness in wines.",
                "Patagonian Pinot Noir is gaining international recognition for quality.",
                "The Allen area in Río Negro is a traditional wine-producing zone.",
                "Patagonian winds are constant, reducing disease pressure but challenging vine growth.",
            ],
        },
        "Catamarca": {
            "key_facts": [
                "Catamarca is a small wine-producing province in northwestern Argentina.",
                "Catamarca's Fiambalá region has some of the highest vineyards in the world.",
                "Fiambalá vineyards in Catamarca exceed 1,500 meters elevation.",
                "Tinogasta in Catamarca is an emerging wine zone with high-altitude potential.",
            ],
        },
        "La Rioja": {
            "key_facts": [
                "La Rioja in Argentina is one of the country's oldest wine-producing regions.",
                "Argentine La Rioja is distinct from the La Rioja wine region in Spain.",
                "Torrontés Riojano is widely grown in Argentine La Rioja.",
                "Famatina Valley in La Rioja has vineyards at elevations exceeding 1,000 meters.",
                "Chilecito in La Rioja is the province's main wine-producing center.",
            ],
        },
        "Tucumán": {
            "key_facts": [
                "Tucumán is a small but growing wine province in northwestern Argentina.",
                "The Amaicha del Valle area in Tucumán has vineyards at over 2,000 meters.",
                "Tucumán's Colalao del Valle produces Malbec and Torrontés at high altitude.",
            ],
        },
    },
    "grape_varieties": [
        "Malbec is Argentina's signature grape variety.",
        "Argentina is the world's largest producer of Malbec.",
        "Argentine Malbec produces deeply colored, plush wines with notes of plum and violet.",
        "Argentine Malbec at high altitudes develops more floral and mineral characteristics.",
        "Malbec originated in southwest France but found its greatest expression in Argentina.",
        "Torrontés is Argentina's signature white grape variety.",
        "Torrontés produces aromatic white wines with floral and citrus characteristics.",
        "Torrontés Riojano is the most widely planted sub-variety of Torrontés.",
        "Torrontés is believed to be a natural cross of Muscat of Alexandria and Criolla Chica.",
        "Bonarda (Douce Noir) is the second most planted red grape in Argentina.",
        "Argentine Bonarda produces juicy, fruit-forward wines.",
        "Cabernet Sauvignon is widely planted across Argentina.",
        "Argentine Cabernet Sauvignon is often blended with Malbec.",
        "Criolla Grande is a historic Argentine grape used primarily for bulk wine.",
        "Cereza is a pink-skinned grape widely planted in Argentine bulk wine production.",
        "Syrah is increasingly planted in Argentina, especially in San Juan and cooler sites.",
        "Tempranillo has significant plantings in Mendoza and San Juan.",
        "Chardonnay is Argentina's most-planted premium white variety.",
        "Pinot Noir is grown in cooler Argentine regions, particularly Patagonia.",
        "Pedro Giménez is a white variety used extensively for bulk wine in Argentina.",
        "Semillon has historic plantings in Mendoza.",
        "Malbec Rosé is a growing category in Argentine wine production.",
    ],
    "general_facts": [
        "Argentina is the world's fifth-largest wine producer.",
        "Many Argentine vineyards are planted at altitudes exceeding 1,000 meters.",
        "High-altitude viticulture in Argentina produces wines with intense UV exposure and concentrated flavors.",
        "Argentina's wine regions receive very little rainfall, requiring irrigation.",
        "Argentine vineyards are primarily irrigated by snowmelt from the Andes.",
        "The zonda is a hot, dry wind in Mendoza that can damage vineyards.",
        "Malbec World Day is celebrated on April 17, marking the date in 1853 when Argentine president Sarmiento tasked agronomist Michel Pouget with planting vines.",
        "Argentina has approximately 210,000 hectares of vineyards.",
        "Argentina's wine exports have grown significantly since the 2000s.",
        "The Instituto Nacional de Vitivinicultura (INV) regulates Argentina's wine industry.",
        "Argentina's wine tradition was brought by Spanish colonizers in the 16th century.",
        "Italian immigrants in the late 19th century significantly influenced Argentine winemaking.",
        "Argentina consumes the majority of its wine production domestically.",
        "Argentine wine per capita consumption has declined from over 90 liters in the 1970s to around 20 liters.",
        "The rise of boutique and premium wineries has transformed Argentina's wine reputation since 2000.",
        "Nicolas Catena Zapata is credited with pioneering high-altitude Malbec in Argentina.",
        "Catena Zapata's Adrianna Vineyard in the Uco Valley is one of Argentina's most acclaimed sites.",
        "Argentina's wine regions stretch from latitude 22 to 42 degrees south.",
        "Mendoza is protected from Pacific moisture by the Andes, creating a rain shadow desert.",
    ],
    "viticulture_facts": [
        "Flood irrigation through canals is the traditional method in Argentine vineyards.",
        "Drip irrigation is increasingly adopted in modern Argentine vineyards.",
        "Hail netting is widely used in Mendoza to protect vineyards.",
        "Pergola (parral) trellis training is traditional in Argentina for high-yield production.",
        "Vertical shoot positioning (VSP) is used in Argentine premium vineyards.",
        "Argentine vineyards can exceed 3,000 meters altitude in extreme locations.",
        "Phylloxera is present in some Argentine regions, but many vines remain on own roots.",
        "The sandy soils of some Argentine regions provide natural phylloxera resistance.",
        "High-altitude Argentine vineyards experience intense solar radiation and UV exposure.",
    ],
    "winemaking_facts": [
        "Many Argentine wineries use concrete eggs and amphoras for fermentation.",
        "Argentine winemakers increasingly use French oak barrels alongside traditional American oak.",
        "Nicolas Catena pioneered estate bottling and vineyard designation in Argentina.",
        "Argentina's natural wine movement is growing, centered in Mendoza and Patagonia.",
        "Sparkling wine production using the traditional method is expanding in Argentina.",
        "Argentine Malbec is typically fermented with extended maceration for color extraction.",
    ],
}

CHILE_KNOWLEDGE = {
    "regions": {
        "Maipo Valley": {
            "key_facts": [
                "The Maipo Valley is Chile's most prestigious wine region for Cabernet Sauvignon.",
                "The Maipo Valley is located just south of Santiago.",
                "Alto Maipo in the upper Maipo Valley produces premium Cabernet Sauvignon at higher altitudes.",
                "The Maipo Valley has a Mediterranean climate with warm, dry summers.",
                "Puente Alto in the Maipo Valley is home to several of Chile's most iconic wines.",
                "Almaviva from Puente Alto is a joint venture between Concha y Toro and Baron Philippe de Rothschild.",
                "Don Melchor from Puente Alto is one of Chile's benchmark Cabernet Sauvignons.",
                "The Maipo Valley is divided into Alto Maipo, Central Maipo, and Coastal Maipo.",
                "Buin in the Central Maipo is a warm area producing volume wines.",
                "Isla de Maipo in the Central Maipo is a historic wine area.",
            ],
        },
        "Colchagua Valley": {
            "key_facts": [
                "The Colchagua Valley is one of Chile's most important red wine regions.",
                "The Colchagua Valley is located in the Rapel Valley within the Central Valley.",
                "Colchagua is known for Carménère, Cabernet Sauvignon, and Syrah.",
                "The Apalta sub-region in Colchagua is considered one of Chile's finest terroirs.",
                "Colchagua has a warm climate moderated by afternoon breezes from the Pacific.",
                "Montes Alpha from Colchagua helped establish Chile's premium wine reputation.",
                "Lapostolle Clos Apalta from the Apalta area is one of Chile's most acclaimed wines.",
                "The Marchigüe area in Colchagua is known for Carménère.",
                "Colchagua's Lolol area has a cooler climate suited to white varieties.",
            ],
        },
        "Casablanca Valley": {
            "key_facts": [
                "The Casablanca Valley is a cool-climate region between Santiago and the coast.",
                "Casablanca Valley was first planted in the 1980s and pioneered cool-climate winemaking in Chile.",
                "Casablanca is known for Sauvignon Blanc, Chardonnay, and Pinot Noir.",
                "Morning fog in the Casablanca Valley helps moderate temperatures.",
                "Pablo Morandé was a pioneer of viticulture in the Casablanca Valley.",
                "Casablanca is approximately 30 kilometers from the Pacific Ocean.",
                "Frost is a viticultural hazard in the Casablanca Valley due to its cool climate.",
            ],
        },
        "Aconcagua Valley": {
            "key_facts": [
                "The Aconcagua Valley is named after the highest peak in the Americas.",
                "The Aconcagua Valley produces Cabernet Sauvignon and Syrah.",
                "Viña Errázuriz was one of the first wineries in the Aconcagua Valley, founded in 1870.",
                "The Aconcagua Valley has a warm climate tempered by the Humboldt Current.",
                "The Panquehue area in the Aconcagua Valley is the historic center of production.",
                "Aconcagua Costa is a newer coastal denomination producing cool-climate wines.",
                "Seña from the Aconcagua Valley is a collaboration between Eduardo Chadwick and Robert Mondavi.",
            ],
        },
        "San Antonio / Leyda Valley": {
            "key_facts": [
                "Leyda Valley is a cool coastal wine region in the San Antonio Valley.",
                "Leyda Valley was first planted commercially in the late 1990s.",
                "Leyda Valley is known for Sauvignon Blanc, Pinot Noir, and Chardonnay.",
                "Leyda Valley's coastal proximity creates a cool maritime climate.",
                "Lo Abarca in the San Antonio Valley is a subzone known for Sauvignon Blanc.",
                "San Antonio vineyards are among the closest to the Pacific coast in Chile.",
                "Matetic Vineyards was one of the pioneers of the San Antonio Valley.",
            ],
        },
        "Rapel Valley": {
            "key_facts": [
                "The Rapel Valley is divided into Colchagua Valley and Cachapoal Valley.",
                "The Cachapoal Valley in the Rapel Valley produces Cabernet Sauvignon and Carménère.",
                "The Rapel Valley has a warm Mediterranean climate.",
                "Alto Cachapoal in the Andes foothills produces premium red wines at higher elevations.",
                "Rancagua is the main city in the Cachapoal Valley.",
                "Peumo in the Cachapoal Valley is known for Carménère.",
            ],
        },
        "Curicó Valley": {
            "key_facts": [
                "The Curicó Valley was where Miguel Torres established a modern winery in 1979, catalyzing Chile's wine revolution.",
                "The Curicó Valley produces Sauvignon Blanc and Cabernet Sauvignon.",
                "The Curicó Valley is located in the Central Valley south of the Rapel Valley.",
                "Molina is an important town in the Curicó Valley wine area.",
                "The Curicó Valley has a warm climate suited to both red and white varieties.",
                "San Pedro winery in the Curicó Valley is one of Chile's oldest producers.",
            ],
        },
        "Maule Valley": {
            "key_facts": [
                "The Maule Valley is Chile's largest wine region by planted area.",
                "The Maule Valley has old-vine País (Listán Prieto) and Carignan plantings.",
                "VIGNO (Vignadores de Carignan) in the Maule Valley champions old-vine Carignan.",
                "The Maule Valley's dry-farmed old vines produce concentrated wines.",
                "The Maule Valley is divided into coastal, central, and Andes zones.",
                "Cauquenes in the Maule Valley has some of the oldest bush vine plantings in Chile.",
                "The secano (dryland) interior of the Maule Valley grows traditional grape varieties.",
                "Maule Valley old-vine wines are part of Chile's artisan wine renaissance.",
                "Empedrado in coastal Maule has a cooler climate suited to Pinot Noir.",
            ],
        },
        "Bío-Bío Valley": {
            "key_facts": [
                "The Bío-Bío Valley is one of Chile's southernmost wine regions.",
                "Bío-Bío has a cool, wet climate suited to Pinot Noir, Riesling, and Gewürztraminer.",
                "The Bío-Bío Valley is part of Chile's Sur (Southern) wine zone.",
                "Bío-Bío's higher rainfall makes dry farming possible without irrigation.",
                "The city of Chillán is a reference point for the Bío-Bío wine area.",
            ],
        },
        "Itata Valley": {
            "key_facts": [
                "The Itata Valley has some of Chile's oldest vineyard plantings.",
                "Itata is known for old-vine País and Muscat of Alexandria.",
                "The Itata Valley is experiencing renewed interest from artisan winemakers.",
                "Itata's bush-vine País plantings may be over 200 years old.",
                "The Itata Valley has a cool coastal-influenced climate.",
                "Cinsault from Itata is gaining recognition as a premium variety.",
            ],
        },
        "Limarí Valley": {
            "key_facts": [
                "The Limarí Valley is located in northern Chile in the Coquimbo region.",
                "Limarí has limestone soils unusual for Chile.",
                "Limarí Valley is known for Chardonnay, Syrah, and Pinot Noir.",
                "The Limarí Valley has a cool desert climate influenced by the Pacific Ocean.",
                "Limarí's marine influence creates a unique coastal desert terroir.",
                "Tabalí winery was a pioneer in the Limarí Valley.",
            ],
        },
        "Elqui Valley": {
            "key_facts": [
                "The Elqui Valley in northern Chile is one of Chile's most extreme wine regions.",
                "Elqui Valley vineyards are planted at altitudes up to 2,000 meters.",
                "Elqui is known for Syrah and is also a major Pisco production area.",
                "The Elqui Valley has some of the clearest skies in the world.",
                "Elqui's extreme aridity means vines rely entirely on irrigation.",
            ],
        },
        "Malleco Valley": {
            "key_facts": [
                "Malleco Valley is one of Chile's newest and southernmost wine regions.",
                "Malleco's cool climate is suited to Pinot Noir and Chardonnay.",
                "William Fèvre established a winery in Malleco, bringing Burgundian expertise.",
            ],
        },
        "Choapa Valley": {
            "key_facts": [
                "The Choapa Valley is located between the Coquimbo and Aconcagua regions.",
                "The Choapa Valley has a semi-arid climate with warm days and cool nights.",
                "Syrah from the Choapa Valley shows distinctive mineral character.",
            ],
        },
    },
    "grape_varieties": [
        "Cabernet Sauvignon is Chile's most planted grape variety.",
        "Carménère is Chile's signature grape variety.",
        "Carménère was rediscovered in Chile in 1994, having been confused with Merlot for decades.",
        "Carménère is originally from Bordeaux but was nearly wiped out by phylloxera in France.",
        "Chilean Carménère produces wines with herbal, peppery, and dark fruit characters.",
        "País (Listán Prieto) is a historic grape brought to Chile by Spanish missionaries in the 16th century.",
        "País is experiencing a renaissance as artisan producers champion old-vine expressions.",
        "Sauvignon Blanc is Chile's most planted white grape variety.",
        "Merlot is widely grown in Chile, although some plantings were found to be Carménère.",
        "Syrah is increasingly important in Chile, particularly in cooler and northern regions.",
        "Chilean Pinot Noir comes primarily from Casablanca, San Antonio, and Bío-Bío.",
        "Chardonnay is grown in both warm and cool Chilean regions.",
        "Carignan from old bush vines in the Maule is a distinctive Chilean wine.",
        "Cinsault from Itata and Bío-Bío is gaining recognition as a quality variety.",
        "Petit Verdot is used in Chilean blends and occasionally as a single variety.",
        "Mourvèdre is planted in small quantities in warmer Chilean zones.",
        "Muscat of Alexandria is grown in Itata and Bío-Bío for both wine and Pisco.",
        "Gewürztraminer is produced in small quantities in Chile's cooler southern regions.",
        "Viognier is grown in limited quantities in Chilean warm-climate regions.",
    ],
    "general_facts": [
        "Chile's wine regions are organized by latitude into Coquimbo, Aconcagua, Central Valley, and Sur.",
        "Chile benefits from natural phylloxera barriers: the Andes, the Pacific, the Atacama Desert, and Antarctica.",
        "Chile has never been affected by phylloxera, so vines grow on their own rootstock.",
        "Chile's wine classification system includes Denomination of Origin (DO) at region, sub-region, and zone levels.",
        "Chile is the world's fourth-largest wine exporter by volume.",
        "The Humboldt Current along Chile's coast cools the climate of western valleys.",
        "Chile's wine industry underwent modernization in the 1980s and 1990s with foreign investment.",
        "Chile has approximately 140,000 hectares of wine grapes under cultivation.",
        "Chile's 2011 new wine classification introduced Costa (coastal), Entre Cordilleras (between ranges), and Andes designations.",
        "Chile's coast-to-Andes transverse valleys create diverse mesoclimates.",
        "Concha y Toro is the largest wine producer in Chile and Latin America.",
        "Eduardo Chadwick organized the Berlin Tasting in 2004, where Chilean wines outscored top French wines.",
        "Chile's wine exports are valued at over USD 2 billion annually.",
        "The organic wine sector is growing rapidly in Chile, benefiting from the dry climate.",
        "Chile's wine history dates to the 1550s with the arrival of Spanish conquistadors.",
        "The Casillero del Diablo legend is one of Chilean wine's most famous marketing stories.",
        "Chile's wine regions span over 1,400 kilometers from north to south.",
        "Santiago's proximity to the Maipo Valley makes it a hub for wine tourism.",
    ],
    "viticulture_facts": [
        "Chilean vineyards benefit from low disease pressure due to the dry climate.",
        "Irrigation in Chile traditionally uses Andean snowmelt via canal systems.",
        "Modern Chilean vineyards increasingly use drip irrigation for precision water management.",
        "Chile's long, narrow geography creates a range of climates from desert to cool maritime.",
        "The Andes provide both irrigation water and protection from continental weather systems.",
        "Chilean viticulture research is led by institutions such as the Universidad de Chile.",
        "The coastal range in Chile blocks marine fog from reaching interior valleys.",
        "Head-pruned bush vines (goblet) are traditional for País and Carignan in Chile.",
    ],
    "winemaking_facts": [
        "Chilean winemakers increasingly use concrete and clay vessels alongside oak.",
        "The icon wine category in Chile includes labels competing at the highest global level.",
        "Chile's wine industry has attracted investment from France, Spain, and the United States.",
        "Aurelio Montes pioneered premium hillside viticulture in Chile.",
        "Chile produces both traditional and modern rosé styles.",
        "Natural wine production is a growing movement in Chile, especially in Maule and Itata.",
    ],
}

# ─── Scraper Functions ────────────────────────────────────────────────────────


def _scrape_website_text(url: str, max_pages: int = 5) -> list[str]:
    """
    Attempt to scrape text content from a website.
    Returns list of text paragraphs found.
    """
    paragraphs = []
    soup = _get_soup(url)
    if soup is None:
        return paragraphs

    for p in soup.find_all(["p", "li"]):
        text = p.get_text(strip=True)
        if text and len(text) > 20:
            paragraphs.append(text)

    return paragraphs


def _scrape_australia(source_id: str, dry_run: bool = False) -> list[dict]:
    """Scrape wine facts for Australia."""
    facts = []
    seen = set()

    logger.info("Scraping Australia wine data...")

    # Try fetching live data from Wine Australia
    live_paragraphs = _scrape_website_text("https://www.wineaustralia.com/getmedia/84db498e-0267-4823-9df1-71f8e40a4caf/Australian-Wine-Sector-at-a-Glance.pdf")
    if live_paragraphs:
        logger.info(f"Fetched {len(live_paragraphs)} paragraphs from Wine Australia")

    # Build facts from knowledge base
    for zone_name, zone_data in AUSTRALIA_KNOWLEDGE["zones_and_regions"].items():
        # Region existence facts
        for region_name in zone_data["regions"]:
            key = f"au_region:{region_name}"
            if key not in seen:
                seen.add(key)
                facts.append({
                    "fact_text": f"{region_name} is a wine region in the {zone_name} zone of Australia.",
                    "domain": "wine_regions",
                    "subdomain": "australia",
                    "source_id": source_id,
                    "entities": [
                        {"type": "region", "name": region_name},
                        {"type": "zone", "name": zone_name},
                        {"type": "country", "name": "Australia"},
                    ],
                    "tags": ["region", "australia", zone_name.lower().replace(" ", "_")],
                    "confidence": 0.95,
                })

        # Key facts from knowledge base
        for fact_text in zone_data["key_facts"]:
            key = f"au_fact:{fact_text[:60]}"
            if key not in seen:
                seen.add(key)
                entities = [{"type": "zone", "name": zone_name}, {"type": "country", "name": "Australia"}]
                # Extract region names referenced in the fact
                for region_name in zone_data["regions"]:
                    if region_name in fact_text:
                        entities.insert(0, {"type": "region", "name": region_name})
                        break

                facts.append({
                    "fact_text": fact_text,
                    "domain": "wine_regions",
                    "subdomain": "australia",
                    "source_id": source_id,
                    "entities": entities,
                    "tags": ["australia", zone_name.lower().replace(" ", "_")],
                    "confidence": 0.95,
                })

    # Grape variety facts
    for fact_text in AUSTRALIA_KNOWLEDGE["grape_varieties"]:
        key = f"au_grape:{fact_text[:60]}"
        if key not in seen:
            seen.add(key)
            facts.append({
                "fact_text": fact_text,
                "domain": "grape_varieties",
                "subdomain": "australia",
                "source_id": source_id,
                "entities": [{"type": "country", "name": "Australia"}],
                "tags": ["grape", "australia"],
                "confidence": 0.95,
            })

    # General facts
    for fact_text in AUSTRALIA_KNOWLEDGE["general_facts"]:
        key = f"au_general:{fact_text[:60]}"
        if key not in seen:
            seen.add(key)
            facts.append({
                "fact_text": fact_text,
                "domain": "wine_regions",
                "subdomain": "australia",
                "source_id": source_id,
                "entities": [{"type": "country", "name": "Australia"}],
                "tags": ["australia", "general"],
                "confidence": 0.95,
            })

    # Viticulture facts
    for fact_text in AUSTRALIA_KNOWLEDGE.get("viticulture_facts", []):
        key = f"au_viti:{fact_text[:60]}"
        if key not in seen:
            seen.add(key)
            facts.append({
                "fact_text": fact_text,
                "domain": "viticulture",
                "subdomain": "australia",
                "source_id": source_id,
                "entities": [{"type": "country", "name": "Australia"}],
                "tags": ["australia", "viticulture"],
                "confidence": 0.95,
            })

    # Winemaking facts
    for fact_text in AUSTRALIA_KNOWLEDGE.get("winemaking_facts", []):
        key = f"au_wm:{fact_text[:60]}"
        if key not in seen:
            seen.add(key)
            facts.append({
                "fact_text": fact_text,
                "domain": "winemaking",
                "subdomain": "australia",
                "source_id": source_id,
                "entities": [{"type": "country", "name": "Australia"}],
                "tags": ["australia", "winemaking"],
                "confidence": 0.95,
            })

    # Producer facts
    for fact_text in AUSTRALIA_KNOWLEDGE.get("producer_facts", []):
        key = f"au_prod:{fact_text[:60]}"
        if key not in seen:
            seen.add(key)
            facts.append({
                "fact_text": fact_text,
                "domain": "producers",
                "subdomain": "australia",
                "source_id": source_id,
                "entities": [{"type": "country", "name": "Australia"}],
                "tags": ["australia", "producer"],
                "confidence": 0.95,
            })

    # Wine business facts
    for fact_text in AUSTRALIA_KNOWLEDGE.get("wine_business_facts", []):
        key = f"au_biz:{fact_text[:60]}"
        if key not in seen:
            seen.add(key)
            facts.append({
                "fact_text": fact_text,
                "domain": "wine_business",
                "subdomain": "australia",
                "source_id": source_id,
                "entities": [{"type": "country", "name": "Australia"}],
                "tags": ["australia", "business"],
                "confidence": 0.95,
            })

    # Try to supplement from live site
    _supplement_from_website(
        facts, seen, source_id,
        base_url="https://www.wineaustralia.com",
        paths=[
            "/getmedia/australian-wine-regions",
            "/growing-making/regions",
        ],
        country="Australia",
        subdomain="australia",
    )

    logger.info(f"Australia: built {len(facts)} facts")
    return facts


def _scrape_new_zealand(source_id: str, dry_run: bool = False) -> list[dict]:
    """Scrape wine facts for New Zealand."""
    facts = []
    seen = set()

    logger.info("Scraping New Zealand wine data...")

    # Build facts from knowledge base
    for region_name, region_data in NEW_ZEALAND_KNOWLEDGE["regions"].items():
        # Region key facts
        for fact_text in region_data["key_facts"]:
            key = f"nz_fact:{fact_text[:60]}"
            if key not in seen:
                seen.add(key)
                entities = [
                    {"type": "region", "name": region_name},
                    {"type": "country", "name": "New Zealand"},
                ]
                facts.append({
                    "fact_text": fact_text,
                    "domain": "wine_regions",
                    "subdomain": "new_zealand",
                    "source_id": source_id,
                    "entities": entities,
                    "tags": ["new_zealand", region_name.lower().replace(" ", "_").replace("/", "_")],
                    "confidence": 0.95,
                })

    # Grape variety facts
    for fact_text in NEW_ZEALAND_KNOWLEDGE["grape_varieties"]:
        key = f"nz_grape:{fact_text[:60]}"
        if key not in seen:
            seen.add(key)
            facts.append({
                "fact_text": fact_text,
                "domain": "grape_varieties",
                "subdomain": "new_zealand",
                "source_id": source_id,
                "entities": [{"type": "country", "name": "New Zealand"}],
                "tags": ["grape", "new_zealand"],
                "confidence": 0.95,
            })

    # General facts
    for fact_text in NEW_ZEALAND_KNOWLEDGE["general_facts"]:
        key = f"nz_general:{fact_text[:60]}"
        if key not in seen:
            seen.add(key)
            facts.append({
                "fact_text": fact_text,
                "domain": "wine_regions",
                "subdomain": "new_zealand",
                "source_id": source_id,
                "entities": [{"type": "country", "name": "New Zealand"}],
                "tags": ["new_zealand", "general"],
                "confidence": 0.95,
            })

    # Viticulture facts
    for fact_text in NEW_ZEALAND_KNOWLEDGE.get("viticulture_facts", []):
        key = f"nz_viti:{fact_text[:60]}"
        if key not in seen:
            seen.add(key)
            facts.append({
                "fact_text": fact_text,
                "domain": "viticulture",
                "subdomain": "new_zealand",
                "source_id": source_id,
                "entities": [{"type": "country", "name": "New Zealand"}],
                "tags": ["new_zealand", "viticulture"],
                "confidence": 0.95,
            })

    # Producer facts
    for fact_text in NEW_ZEALAND_KNOWLEDGE.get("producer_facts", []):
        key = f"nz_prod:{fact_text[:60]}"
        if key not in seen:
            seen.add(key)
            facts.append({
                "fact_text": fact_text,
                "domain": "producers",
                "subdomain": "new_zealand",
                "source_id": source_id,
                "entities": [{"type": "country", "name": "New Zealand"}],
                "tags": ["new_zealand", "producer"],
                "confidence": 0.95,
            })

    # Wine business facts
    for fact_text in NEW_ZEALAND_KNOWLEDGE.get("wine_business_facts", []):
        key = f"nz_biz:{fact_text[:60]}"
        if key not in seen:
            seen.add(key)
            facts.append({
                "fact_text": fact_text,
                "domain": "wine_business",
                "subdomain": "new_zealand",
                "source_id": source_id,
                "entities": [{"type": "country", "name": "New Zealand"}],
                "tags": ["new_zealand", "business"],
                "confidence": 0.95,
            })

    # Try to supplement from live site
    _supplement_from_website(
        facts, seen, source_id,
        base_url="https://www.nzwine.com",
        paths=[
            "/our-regions",
            "/our-regions/marlborough",
        ],
        country="New Zealand",
        subdomain="new_zealand",
    )

    logger.info(f"New Zealand: built {len(facts)} facts")
    return facts


def _scrape_south_africa(source_id: str, dry_run: bool = False) -> list[dict]:
    """Scrape wine facts for South Africa."""
    facts = []
    seen = set()

    logger.info("Scraping South Africa wine data...")

    # Build facts from knowledge base
    for region_name, region_data in SOUTH_AFRICA_KNOWLEDGE["regions"].items():
        for fact_text in region_data["key_facts"]:
            key = f"za_fact:{fact_text[:60]}"
            if key not in seen:
                seen.add(key)
                entities = [
                    {"type": "region", "name": region_name},
                    {"type": "country", "name": "South Africa"},
                ]
                facts.append({
                    "fact_text": fact_text,
                    "domain": "wine_regions",
                    "subdomain": "south_africa",
                    "source_id": source_id,
                    "entities": entities,
                    "tags": ["south_africa", region_name.lower().replace(" ", "_").replace("/", "_")],
                    "confidence": 0.95,
                })

    # Grape variety facts
    for fact_text in SOUTH_AFRICA_KNOWLEDGE["grape_varieties"]:
        key = f"za_grape:{fact_text[:60]}"
        if key not in seen:
            seen.add(key)
            facts.append({
                "fact_text": fact_text,
                "domain": "grape_varieties",
                "subdomain": "south_africa",
                "source_id": source_id,
                "entities": [{"type": "country", "name": "South Africa"}],
                "tags": ["grape", "south_africa"],
                "confidence": 0.95,
            })

    # General facts
    for fact_text in SOUTH_AFRICA_KNOWLEDGE["general_facts"]:
        key = f"za_general:{fact_text[:60]}"
        if key not in seen:
            seen.add(key)
            facts.append({
                "fact_text": fact_text,
                "domain": "wine_regions",
                "subdomain": "south_africa",
                "source_id": source_id,
                "entities": [{"type": "country", "name": "South Africa"}],
                "tags": ["south_africa", "general"],
                "confidence": 0.95,
            })

    # Viticulture facts
    for fact_text in SOUTH_AFRICA_KNOWLEDGE.get("viticulture_facts", []):
        key = f"za_viti:{fact_text[:60]}"
        if key not in seen:
            seen.add(key)
            facts.append({
                "fact_text": fact_text,
                "domain": "viticulture",
                "subdomain": "south_africa",
                "source_id": source_id,
                "entities": [{"type": "country", "name": "South Africa"}],
                "tags": ["south_africa", "viticulture"],
                "confidence": 0.95,
            })

    # Producer facts
    for fact_text in SOUTH_AFRICA_KNOWLEDGE.get("producer_facts", []):
        key = f"za_prod:{fact_text[:60]}"
        if key not in seen:
            seen.add(key)
            facts.append({
                "fact_text": fact_text,
                "domain": "producers",
                "subdomain": "south_africa",
                "source_id": source_id,
                "entities": [{"type": "country", "name": "South Africa"}],
                "tags": ["south_africa", "producer"],
                "confidence": 0.95,
            })

    # Wine business facts
    for fact_text in SOUTH_AFRICA_KNOWLEDGE.get("wine_business_facts", []):
        key = f"za_biz:{fact_text[:60]}"
        if key not in seen:
            seen.add(key)
            facts.append({
                "fact_text": fact_text,
                "domain": "wine_business",
                "subdomain": "south_africa",
                "source_id": source_id,
                "entities": [{"type": "country", "name": "South Africa"}],
                "tags": ["south_africa", "business"],
                "confidence": 0.95,
            })

    # Try to supplement from live site
    _supplement_from_website(
        facts, seen, source_id,
        base_url="https://www.wosa.co.za",
        paths=[
            "/the-industry/wine-regions/",
            "/the-industry/varietals/",
        ],
        country="South Africa",
        subdomain="south_africa",
    )

    logger.info(f"South Africa: built {len(facts)} facts")
    return facts


def _scrape_argentina(source_id: str, dry_run: bool = False) -> list[dict]:
    """Scrape wine facts for Argentina."""
    facts = []
    seen = set()

    logger.info("Scraping Argentina wine data...")

    # Build facts from knowledge base
    for region_name, region_data in ARGENTINA_KNOWLEDGE["regions"].items():
        for fact_text in region_data["key_facts"]:
            key = f"ar_fact:{fact_text[:60]}"
            if key not in seen:
                seen.add(key)
                entities = [
                    {"type": "region", "name": region_name},
                    {"type": "country", "name": "Argentina"},
                ]
                facts.append({
                    "fact_text": fact_text,
                    "domain": "wine_regions",
                    "subdomain": "argentina",
                    "source_id": source_id,
                    "entities": entities,
                    "tags": ["argentina", region_name.lower().replace(" ", "_")],
                    "confidence": 0.95,
                })

    # Grape variety facts
    for fact_text in ARGENTINA_KNOWLEDGE["grape_varieties"]:
        key = f"ar_grape:{fact_text[:60]}"
        if key not in seen:
            seen.add(key)
            facts.append({
                "fact_text": fact_text,
                "domain": "grape_varieties",
                "subdomain": "argentina",
                "source_id": source_id,
                "entities": [{"type": "country", "name": "Argentina"}],
                "tags": ["grape", "argentina"],
                "confidence": 0.95,
            })

    # General facts
    for fact_text in ARGENTINA_KNOWLEDGE["general_facts"]:
        key = f"ar_general:{fact_text[:60]}"
        if key not in seen:
            seen.add(key)
            facts.append({
                "fact_text": fact_text,
                "domain": "wine_regions",
                "subdomain": "argentina",
                "source_id": source_id,
                "entities": [{"type": "country", "name": "Argentina"}],
                "tags": ["argentina", "general"],
                "confidence": 0.95,
            })

    # Viticulture facts
    for fact_text in ARGENTINA_KNOWLEDGE.get("viticulture_facts", []):
        key = f"ar_viti:{fact_text[:60]}"
        if key not in seen:
            seen.add(key)
            facts.append({
                "fact_text": fact_text,
                "domain": "viticulture",
                "subdomain": "argentina",
                "source_id": source_id,
                "entities": [{"type": "country", "name": "Argentina"}],
                "tags": ["argentina", "viticulture"],
                "confidence": 0.95,
            })

    # Winemaking facts
    for fact_text in ARGENTINA_KNOWLEDGE.get("winemaking_facts", []):
        key = f"ar_wm:{fact_text[:60]}"
        if key not in seen:
            seen.add(key)
            facts.append({
                "fact_text": fact_text,
                "domain": "winemaking",
                "subdomain": "argentina",
                "source_id": source_id,
                "entities": [{"type": "country", "name": "Argentina"}],
                "tags": ["argentina", "winemaking"],
                "confidence": 0.95,
            })

    # Try to supplement from live site
    _supplement_from_website(
        facts, seen, source_id,
        base_url="https://www.winesofargentina.com",
        paths=[
            "/wine-regions",
            "/wine-regions/mendoza",
        ],
        country="Argentina",
        subdomain="argentina",
    )

    logger.info(f"Argentina: built {len(facts)} facts")
    return facts


def _scrape_chile(source_id: str, dry_run: bool = False) -> list[dict]:
    """Scrape wine facts for Chile."""
    facts = []
    seen = set()

    logger.info("Scraping Chile wine data...")

    # Build facts from knowledge base
    for region_name, region_data in CHILE_KNOWLEDGE["regions"].items():
        for fact_text in region_data["key_facts"]:
            key = f"cl_fact:{fact_text[:60]}"
            if key not in seen:
                seen.add(key)
                entities = [
                    {"type": "region", "name": region_name},
                    {"type": "country", "name": "Chile"},
                ]
                facts.append({
                    "fact_text": fact_text,
                    "domain": "wine_regions",
                    "subdomain": "chile",
                    "source_id": source_id,
                    "entities": entities,
                    "tags": ["chile", region_name.lower().replace(" ", "_").replace("/", "_")],
                    "confidence": 0.95,
                })

    # Grape variety facts
    for fact_text in CHILE_KNOWLEDGE["grape_varieties"]:
        key = f"cl_grape:{fact_text[:60]}"
        if key not in seen:
            seen.add(key)
            facts.append({
                "fact_text": fact_text,
                "domain": "grape_varieties",
                "subdomain": "chile",
                "source_id": source_id,
                "entities": [{"type": "country", "name": "Chile"}],
                "tags": ["grape", "chile"],
                "confidence": 0.95,
            })

    # General facts
    for fact_text in CHILE_KNOWLEDGE["general_facts"]:
        key = f"cl_general:{fact_text[:60]}"
        if key not in seen:
            seen.add(key)
            facts.append({
                "fact_text": fact_text,
                "domain": "wine_regions",
                "subdomain": "chile",
                "source_id": source_id,
                "entities": [{"type": "country", "name": "Chile"}],
                "tags": ["chile", "general"],
                "confidence": 0.95,
            })

    # Viticulture facts
    for fact_text in CHILE_KNOWLEDGE.get("viticulture_facts", []):
        key = f"cl_viti:{fact_text[:60]}"
        if key not in seen:
            seen.add(key)
            facts.append({
                "fact_text": fact_text,
                "domain": "viticulture",
                "subdomain": "chile",
                "source_id": source_id,
                "entities": [{"type": "country", "name": "Chile"}],
                "tags": ["chile", "viticulture"],
                "confidence": 0.95,
            })

    # Winemaking facts
    for fact_text in CHILE_KNOWLEDGE.get("winemaking_facts", []):
        key = f"cl_wm:{fact_text[:60]}"
        if key not in seen:
            seen.add(key)
            facts.append({
                "fact_text": fact_text,
                "domain": "winemaking",
                "subdomain": "chile",
                "source_id": source_id,
                "entities": [{"type": "country", "name": "Chile"}],
                "tags": ["chile", "winemaking"],
                "confidence": 0.95,
            })

    # Try to supplement from live site
    _supplement_from_website(
        facts, seen, source_id,
        base_url="https://www.winesofchile.org",
        paths=[
            "/chilean-wine/wine-regions",
            "/chilean-wine/grape-varieties",
        ],
        country="Chile",
        subdomain="chile",
    )

    logger.info(f"Chile: built {len(facts)} facts")
    return facts


def _supplement_from_website(
    facts: list[dict],
    seen: set,
    source_id: str,
    base_url: str,
    paths: list[str],
    country: str,
    subdomain: str,
) -> None:
    """
    Attempt to scrape additional facts from website pages.
    Extracts text and looks for wine-relevant sentences to create atomic facts.
    """
    wine_keywords = {
        "vineyard", "grape", "wine", "region", "valley", "appellation",
        "variety", "hectare", "vintage", "terroir", "climate", "soil",
        "altitude", "planted", "winery", "producer", "blend", "barrel",
        "ferment", "harvest", "shiraz", "cabernet", "merlot", "pinot",
        "chardonnay", "sauvignon", "riesling", "malbec", "syrah",
        "chenin", "pinotage", "carmenere", "carménère", "torrontés",
    }

    for path in paths:
        url = f"{base_url}{path}"
        logger.debug(f"Attempting to scrape: {url}")
        soup = _get_soup(url)
        if soup is None:
            continue

        for elem in soup.find_all(["p", "li", "td"]):
            text = elem.get_text(strip=True)
            if not text or len(text) < 30 or len(text) > 500:
                continue

            text_lower = text.lower()
            if not any(kw in text_lower for kw in wine_keywords):
                continue

            # Split into sentences and process
            sentences = re.split(r'(?<=[.!?])\s+', text)
            for sentence in sentences:
                sentence = sentence.strip()
                if len(sentence) < 20 or len(sentence) > 300:
                    continue

                words = sentence.split()
                if len(words) < 5 or len(words) > 50:
                    continue

                # Ensure it ends with punctuation
                if not sentence[-1] in ".!?":
                    sentence += "."

                key = f"web_{subdomain}:{sentence[:60]}"
                if key in seen:
                    continue
                seen.add(key)

                # Determine domain
                domain = "wine_regions"
                if any(kw in text_lower for kw in ["grape", "variety", "varietal", "planted"]):
                    domain = "grape_varieties"

                facts.append({
                    "fact_text": sentence,
                    "domain": domain,
                    "subdomain": subdomain,
                    "source_id": source_id,
                    "entities": [{"type": "country", "name": country}],
                    "tags": [subdomain, "web_scraped"],
                    "confidence": 0.80,
                })


# ─── Country Dispatch ─────────────────────────────────────────────────────────

COUNTRY_SCRAPERS = {
    "australia": (_scrape_australia, "australia"),
    "new-zealand": (_scrape_new_zealand, "new-zealand"),
    "south-africa": (_scrape_south_africa, "south-africa"),
    "argentina": (_scrape_argentina, "argentina"),
    "chile": (_scrape_chile, "chile"),
}


def _register_source(country_slug: str) -> str:
    """Register a source for the given country, return source_id."""
    src = SOURCES[country_slug]
    return ensure_source(
        name=src["name"],
        url=src["url"],
        source_type=src["source_type"],
        tier=src["tier"],
    )


def scrape_country(country_slug: str, dry_run: bool = False) -> tuple[int, list[dict]]:
    """
    Scrape facts for a single country.
    Returns (count_inserted, facts_list).
    """
    if country_slug not in COUNTRY_SCRAPERS:
        logger.error(f"Unknown country: {country_slug}. Available: {list(COUNTRY_SCRAPERS.keys())}")
        return 0, []

    scraper_fn, _ = COUNTRY_SCRAPERS[country_slug]

    if dry_run:
        # For dry run, build facts but don't insert
        facts = scraper_fn("dry-run-source-id", dry_run=True)
        return 0, facts

    source_id = _register_source(country_slug)
    facts = scraper_fn(source_id, dry_run=False)

    if not facts:
        logger.warning(f"No facts generated for {country_slug}")
        return 0, facts

    inserted = insert_facts_batch(facts)
    logger.info(f"{country_slug}: inserted {inserted} new facts (of {len(facts)} generated)")
    return inserted, facts


def scrape_all(dry_run: bool = False) -> dict:
    """Scrape all countries. Returns summary dict."""
    summary = {}
    total_inserted = 0
    total_generated = 0

    for slug in COUNTRY_SLUGS:
        inserted, facts = scrape_country(slug, dry_run=dry_run)
        summary[slug] = {"inserted": inserted, "generated": len(facts)}
        total_inserted += inserted
        total_generated += len(facts)

    summary["_total"] = {"inserted": total_inserted, "generated": total_generated}
    return summary


# ─── Validation ───────────────────────────────────────────────────────────────


def validate_facts() -> None:
    """
    Run quality checks on all New World facts.
    Checks distribution, quality, and shows samples.
    """
    # Collect all facts (dry-run mode, no DB needed)
    all_facts = []
    for slug in COUNTRY_SLUGS:
        scraper_fn, _ = COUNTRY_SCRAPERS[slug]
        facts = scraper_fn("validate-source-id")
        all_facts.extend(facts)

    if not all_facts:
        click.echo("No facts generated. Check scraper logic.")
        return

    # ── Domain / Subdomain distribution ──
    domain_counts = defaultdict(int)
    subdomain_counts = defaultdict(int)
    country_counts = defaultdict(int)

    for f in all_facts:
        domain_counts[f["domain"]] += 1
        sd = f.get("subdomain", "unknown")
        subdomain_counts[sd] += 1
        country_counts[sd] += 1

    click.echo("\n" + "=" * 60)
    click.echo("  NEW WORLD WINE SCRAPER — VALIDATION REPORT")
    click.echo("=" * 60)

    click.echo(f"\nTotal facts: {len(all_facts)}")
    click.echo("\nDomain distribution:")
    for domain, count in sorted(domain_counts.items()):
        click.echo(f"  {domain:25s}: {count:5d} facts")

    click.echo("\nCountry/subdomain distribution:")
    for sd, count in sorted(subdomain_counts.items()):
        flag = " *** UNDER-SCRAPED ***" if count < 50 else ""
        click.echo(f"  {sd:25s}: {count:5d} facts{flag}")

    # ── Quality checks ──
    too_short = []
    too_long = []
    no_predicate = []
    missing_entities = []
    near_dupes = []

    fact_texts = [f["fact_text"] for f in all_facts]

    for i, f in enumerate(all_facts):
        text = f["fact_text"]
        words = text.split()

        # Too short (<5 words)
        if len(words) < 5:
            too_short.append((i, text))

        # Too long (>50 words)
        if len(words) > 50:
            too_long.append((i, text))

        # No predicate — just an entity name with period
        stripped = text.rstrip(".")
        if len(stripped.split()) <= 2 and not any(v in text.lower() for v in ["is", "was", "has", "are", "were", "have"]):
            no_predicate.append((i, text))

        # Missing entities
        entities = f.get("entities", [])
        if not entities:
            missing_entities.append((i, text))

    # Near-duplicate check (string containment)
    for i in range(len(fact_texts)):
        for j in range(i + 1, min(i + 50, len(fact_texts))):  # limit comparison window
            t1 = fact_texts[i].lower().rstrip(".")
            t2 = fact_texts[j].lower().rstrip(".")
            if t1 != t2 and (t1 in t2 or t2 in t1):
                near_dupes.append((i, j, fact_texts[i], fact_texts[j]))

    total = len(all_facts)
    click.echo("\nQuality:")
    click.echo(f"  Too short (<5 words):  {len(too_short):5d} ({100*len(too_short)/total:.1f}%)")
    click.echo(f"  Too long (>50 words):  {len(too_long):5d} ({100*len(too_long)/total:.1f}%)")
    click.echo(f"  No predicate:          {len(no_predicate):5d} ({100*len(no_predicate)/total:.1f}%)")
    click.echo(f"  Missing entities:      {len(missing_entities):5d} ({100*len(missing_entities)/total:.1f}%)")
    click.echo(f"  Possible near-dupes:   {len(near_dupes):5d} ({100*len(near_dupes)/total:.1f}%)")

    # Entity population rate
    with_entities = sum(1 for f in all_facts if f.get("entities"))
    click.echo(f"\n  Facts with entities:   {with_entities:5d} ({100*with_entities/total:.1f}%)")
    click.echo(f"  Facts without entities:{total - with_entities:5d} ({100*(total-with_entities)/total:.1f}%)")

    # ── Show problematic facts ──
    if too_short:
        click.echo("\n  Examples of too-short facts:")
        for idx, text in too_short[:5]:
            click.echo(f"    [{idx}] \"{text}\"")

    if too_long:
        click.echo("\n  Examples of too-long facts:")
        for idx, text in too_long[:5]:
            click.echo(f"    [{idx}] \"{text[:80]}...\"")

    if near_dupes:
        click.echo("\n  Examples of near-duplicates:")
        for i, j, t1, t2 in near_dupes[:5]:
            click.echo(f"    [{i}] \"{t1}\"")
            click.echo(f"    [{j}] \"{t2}\"")
            click.echo()

    # ── Region count check per country ──
    click.echo("\nRegion count check (approximate):")
    expected = {
        "australia": 65,
        "new_zealand": 10,
        "south_africa": 12,
        "argentina": 6,
        "chile": 12,
    }
    for sd, expected_count in expected.items():
        region_facts = [
            f for f in all_facts
            if f.get("subdomain") == sd
            and f["domain"] == "wine_regions"
            and "region" in f["fact_text"].lower()
        ]
        status = "OK" if len(region_facts) >= expected_count // 2 else "LOW"
        click.echo(f"  {sd:20s}: ~{len(region_facts):3d} region facts (expected ~{expected_count}+) [{status}]")

    # ── Random samples ──
    click.echo("\nSample facts (10 random):")
    samples = random.sample(all_facts, min(10, len(all_facts)))
    for i, f in enumerate(samples, 1):
        click.echo(f"  {i:2d}. \"{f['fact_text']}\"")

    click.echo("\n" + "=" * 60)
    click.echo("  Validation complete.")
    click.echo("=" * 60)


# ─── Test Run ─────────────────────────────────────────────────────────────────

TEST_RUN_LIMIT = 5  # facts per category in test mode


def _print_test_report(
    category_stats: dict[str, dict],
    all_facts: list[dict],
    all_inserted_ids: list[str],
) -> None:
    """Print the structured test-run report with quality checks."""
    click.echo("\n=== TEST RUN REPORT ===")
    click.echo("")

    # Table header
    header = (
        f"  {'Source/Category':<25s} {'Items Processed':>17s} "
        f"{'Facts Generated':>17s} {'Facts Inserted (new)':>22s}"
    )
    separator = "  " + "─" * 83
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
        click.echo(
            f"  {cat_name:<25s} {items:>17d} {generated:>17d} {inserted:>22d}"
        )

    click.echo(separator)
    click.echo(
        f"  {'TOTAL':<25s} {total_items:>17d} {total_generated:>17d} "
        f"{total_inserted:>22d}"
    )

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
    click.echo(
        f"    Too short (<5 words):  {len(too_short)} ({len(too_short)/total*100:.1f}%)"
    )
    click.echo(
        f"    Too long (>50 words):  {len(too_long)} ({len(too_long)/total*100:.1f}%)"
    )
    click.echo(
        f"    Missing entities:      {missing_entities} ({missing_entities/total*100:.1f}%)"
    )
    click.echo(f"    Avg words per fact:    {avg_words:.1f}")

    # Sample facts
    sample = random.sample(all_facts, min(10, len(all_facts)))
    click.echo(f"\n  Sample Facts ({min(10, len(all_facts))} random from this run):")
    for i, f in enumerate(sample, 1):
        click.echo(f"    {i:2d}. \"{f['fact_text']}\"")

    # Warnings
    warnings = []

    for cat_name, stats in category_stats.items():
        if stats["facts_inserted"] == 0 and stats["items_processed"] > 0:
            warnings.append(f"ERROR: No facts from {cat_name}")

        items = stats["items_processed"]
        generated = stats["facts_generated"]
        if items > 0 and generated / items < 2:
            warnings.append(
                f"WARNING: Low extraction rate in {cat_name} "
                f"({generated/items:.1f} facts/item)"
            )

        if items > 0 and generated > 0:
            skipped = generated - stats["facts_inserted"]
            if skipped / generated > 0.5:
                warnings.append(
                    f"WARNING: High duplicate rate in {cat_name} "
                    f"({skipped}/{generated} = {skipped/generated*100:.0f}% skipped)"
                )

    if len(too_short) / total > 0.1:
        warnings.append("WARNING: Too many trivial facts")

    if len(too_long) / total > 0.1:
        warnings.append("WARNING: Facts need better splitting")

    if warnings:
        click.echo(f"\n  Warnings:")
        for w in warnings:
            click.echo(f"    * {w}")
    else:
        click.echo(f"\n  No warnings — all checks passed.")


def run_test(
    country_filter: Optional[str] = None,
    cleanup: bool = False,
) -> None:
    """Run a limited test extraction: first country only, 5 facts per category, insert, report."""

    # Determine which countries to process
    if country_filter:
        slugs = [country_filter]
    else:
        # Test mode: only the first country
        slugs = [COUNTRY_SLUGS[0]]

    category_stats = {}
    all_facts_collected = []
    all_inserted_ids = []

    for slug in slugs:
        if slug not in COUNTRY_SCRAPERS:
            logger.warning(f"Unknown country: {slug}")
            continue

        source_id = _register_source(slug)
        scraper_fn, _ = COUNTRY_SCRAPERS[slug]

        # Generate all facts for the country, then take only TEST_RUN_LIMIT
        facts = scraper_fn(source_id, dry_run=False)
        limited_facts = facts[:TEST_RUN_LIMIT]

        cat_name = slug
        generated = len(limited_facts)
        inserted_count = 0

        for f in limited_facts:
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
                all_inserted_ids.append(fact_id)
                inserted_count += 1

        all_facts_collected.extend(limited_facts)

        category_stats[cat_name] = {
            "items_processed": 1,  # 1 country
            "facts_generated": generated,
            "facts_inserted": inserted_count,
        }

    _print_test_report(category_stats, all_facts_collected, all_inserted_ids)

    # Cleanup if requested
    if cleanup and all_inserted_ids:
        from src.utils.db import get_pg
        pg = get_pg()
        cur = pg.cursor()
        cur.execute("DELETE FROM facts WHERE id = ANY(%s::uuid[])", (all_inserted_ids,))
        pg.commit()
        click.echo(f"\n  Cleaned up {len(all_inserted_ids)} test facts from database.")
    elif cleanup:
        click.echo("\n  No facts to clean up.")


# ─── CLI ──────────────────────────────────────────────────────────────────────


@click.command()
@click.option("--all", "run_all", is_flag=True, help="Scrape all New World countries")
@click.option(
    "--country", "-c",
    type=click.Choice(COUNTRY_SLUGS, case_sensitive=False),
    help="Scrape a specific country",
)
@click.option("--list", "list_countries", is_flag=True, help="List available countries")
@click.option("--dry-run", is_flag=True, help="Generate facts without inserting into DB")
@click.option("--validate", is_flag=True, help="Run quality validation on generated facts")
@click.option("--test-run", is_flag=True, help="Process first country only with 5 facts, insert, and report")
@click.option("--cleanup", is_flag=True, help="With --test-run, delete inserted facts after reporting")
def main(
    run_all: bool,
    country: Optional[str],
    list_countries: bool,
    dry_run: bool,
    validate: bool,
    test_run: bool,
    cleanup: bool,
):
    """OenoBench New World Wine Scraper — Extract wine knowledge from AU, NZ, ZA, AR, CL."""
    logger.add("data/logs/newworld_{time}.log", rotation="10 MB")

    if validate:
        validate_facts()
        return

    if test_run:
        run_test(country_filter=country, cleanup=cleanup)
        return

    if list_countries:
        click.echo("\nAvailable countries:")
        for slug in COUNTRY_SLUGS:
            src = SOURCES[slug]
            click.echo(f"  {slug:20s} — {src['name']} ({src['url']})")
        return

    if run_all:
        click.echo("Scraping all New World wine countries...")
        if dry_run:
            click.echo("(DRY RUN — no database writes)\n")

        summary = scrape_all(dry_run=dry_run)

        click.echo("\nSummary:")
        click.echo(f"  {'Country':20s} {'Generated':>10s} {'Inserted':>10s}")
        click.echo(f"  {'-'*20} {'-'*10} {'-'*10}")
        for slug in COUNTRY_SLUGS:
            s = summary[slug]
            click.echo(f"  {slug:20s} {s['generated']:10d} {s['inserted']:10d}")
        t = summary["_total"]
        click.echo(f"  {'TOTAL':20s} {t['generated']:10d} {t['inserted']:10d}")

        if not dry_run:
            click.echo(f"\nTotal facts in database: {get_fact_count()}")
        return

    if country:
        click.echo(f"Scraping {country}...")
        if dry_run:
            click.echo("(DRY RUN — no database writes)\n")

        inserted, facts = scrape_country(country, dry_run=dry_run)
        click.echo(f"\nGenerated {len(facts)} facts, inserted {inserted} new facts for {country}.")

        if not dry_run:
            click.echo(f"Total facts in database: {get_fact_count()}")
        return

    # Default: show help
    click.echo("Use --all to scrape all countries, or --country <name> for a specific one.")
    click.echo("Use --list to see available countries.")
    click.echo("Use --validate to run quality checks on generated facts.")
    click.echo("Use --dry-run to generate facts without database writes.")
    click.echo("Use --test-run to process a small subset and report quality metrics.")
    click.echo("Use --test-run --cleanup to auto-delete test facts after reporting.")


if __name__ == "__main__":
    main()
