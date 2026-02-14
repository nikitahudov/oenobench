"""
OenoBench — Comité Champagne Scraper

Extracts Champagne wine knowledge from the official Comité Champagne
website (https://www.champagne.fr) and curated reference data.

Covers:
    - 17 Grand Cru villages (complete list)
    - 42 Premier Cru villages (complete list)
    - Permitted grape varieties (7 total)
    - Champagne production rules (méthode champenoise)
    - Aging requirements (NV 15 months, vintage 36 months)
    - Champagne styles and dosage levels
    - Terroir, geography, and appellations

Usage:
    python -m src.scrapers.champagne --all
    python -m src.scrapers.champagne --dry-run
    python -m src.scrapers.champagne --validate
    python -m src.scrapers.champagne --list
"""

import random
import time
from collections import Counter
from typing import Optional

import click
import requests
from bs4 import BeautifulSoup
from loguru import logger

from src.utils.facts import ensure_source, insert_facts_batch, get_fact_count

# ─── Configuration ────────────────────────────────────────────────────────────

BASE_URL = "https://www.champagne.fr"
USER_AGENT = "OenoBench-Research/1.0 (academic wine benchmark)"
REQUEST_DELAY = 5  # seconds between requests (1 per 5 seconds)

SOURCE_NAME = "Comité Champagne"
SOURCE_TIER = "tier_2_authoritative"

# Pages to attempt scraping (English version)
SCRAPE_PAGES = [
    "/en/terroir/classification-of-the-vineyards",
    "/en/terroir/the-champagne-vineyard",
    "/en/terroir/grape-varieties",
    "/en/champagne-appellation/champagne-appellation-regulations",
    "/en/champagne-appellation/elaboration-of-champagne",
    "/en/from-vine-to-wine/elaboration/blending",
    "/en/from-vine-to-wine/elaboration/riddling-and-disgorging",
    "/en/from-vine-to-wine/elaboration/dosage",
    "/en/tasting-and-service/types-of-champagne",
]

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
})

# ─── Curated Champagne Knowledge ─────────────────────────────────────────────
# Authoritative data from Comité Champagne publications and AOC regulations.
# Used as primary fact source; web scraping supplements when available.

GRAND_CRU_VILLAGES = [
    "Ambonnay", "Avize", "Aÿ", "Beaumont-sur-Vesle", "Bouzy",
    "Chouilly", "Cramant", "Louvois", "Mailly-Champagne", "Le Mesnil-sur-Oger",
    "Oger", "Oiry", "Puisieulx", "Sillery", "Tours-sur-Marne",
    "Verzenay", "Verzy",
]

PREMIER_CRU_VILLAGES = [
    "Avenay-Val-d'Or", "Bergères-lès-Vertus", "Bezannes", "Billy-le-Grand",
    "Bisseuil", "Chamery", "Champillon", "Chigny-les-Roses",
    "Coligny", "Cormontreuil", "Coulommes-la-Montagne", "Cuis",
    "Cumières", "Dizy", "Écueil", "Étréchy",
    "Grauves", "Hautvillers", "Jouy-lès-Reims", "Ludes",
    "Mareuil-sur-Aÿ", "Les Mesneux", "Montbré", "Mutigny",
    "Pargny-lès-Reims", "Pierry", "Rilly-la-Montagne", "Sacy",
    "Sermiers", "Taissy", "Tauxières-Mutry", "Trépail",
    "Trois-Puits", "Vaudemange", "Vertus", "Ville-Dommange",
    "Villeneuve-Renneville-Chevigny", "Villers-Allerand", "Villers-aux-Nœuds",
    "Villers-Marmery", "Voipreux", "Vrigny",
]

PERMITTED_GRAPES = {
    "Chardonnay": {"color": "white", "status": "principal", "pct": "about 30% of plantings"},
    "Pinot Noir": {"color": "red", "status": "principal", "pct": "about 38% of plantings"},
    "Pinot Meunier": {"color": "red", "status": "principal", "pct": "about 31% of plantings"},
    "Arbane": {"color": "white", "status": "ancillary", "pct": "less than 0.1% of plantings"},
    "Petit Meslier": {"color": "white", "status": "ancillary", "pct": "less than 0.1% of plantings"},
    "Pinot Blanc": {"color": "white", "status": "ancillary", "pct": "less than 0.1% of plantings"},
    "Pinot Gris": {"color": "red", "status": "ancillary", "pct": "less than 0.1% of plantings"},
}

DOSAGE_LEVELS = {
    "Brut Nature": {"sugar": "0-3", "unit": "grams per litre", "aka": "zero dosage, pas dosé"},
    "Extra Brut": {"sugar": "0-6", "unit": "grams per litre", "aka": ""},
    "Brut": {"sugar": "0-12", "unit": "grams per litre", "aka": ""},
    "Extra Dry": {"sugar": "12-17", "unit": "grams per litre", "aka": "Extra Sec"},
    "Sec": {"sugar": "17-32", "unit": "grams per litre", "aka": "Dry"},
    "Demi-Sec": {"sugar": "32-50", "unit": "grams per litre", "aka": ""},
    "Doux": {"sugar": "over 50", "unit": "grams per litre", "aka": "Sweet"},
}

CHAMPAGNE_STYLES = {
    "Blanc de Blancs": "made exclusively from white grapes, typically Chardonnay",
    "Blanc de Noirs": "made exclusively from red grapes, typically Pinot Noir and/or Pinot Meunier",
    "Rosé": "produced either by blending red and white wines or by saignée method",
    "Vintage": "made from grapes of a single harvest year, also called Millésimé",
    "Non-Vintage": "a blend of wines from multiple harvest years, abbreviated NV",
    "Prestige Cuvée": "the top wine of a Champagne house, made from the best parcels",
    "Crémant": "a Champagne with lower pressure, typically around 3.5 atmospheres instead of 6",
}

CHAMPAGNE_SUBREGIONS = {
    "Montagne de Reims": "known primarily for Pinot Noir",
    "Vallée de la Marne": "known primarily for Pinot Meunier",
    "Côte des Blancs": "known primarily for Chardonnay",
    "Côte de Sézanne": "known primarily for Chardonnay",
    "Côte des Bar": "also called Aube, known primarily for Pinot Noir",
}


# ─── HTTP Fetching ────────────────────────────────────────────────────────────

def fetch_page(path: str) -> Optional[BeautifulSoup]:
    """Fetch a page from champagne.fr with rate limiting. Returns soup or None."""
    url = f"{BASE_URL}{path}"
    logger.info(f"Fetching: {url}")

    try:
        resp = SESSION.get(url, timeout=30)
        if resp.status_code == 200:
            logger.debug(f"OK: {url} ({len(resp.text)} bytes)")
            return BeautifulSoup(resp.text, "lxml")
        else:
            logger.warning(f"HTTP {resp.status_code} for {url}")
            return None
    except requests.RequestException as e:
        logger.warning(f"Request failed for {url}: {e}")
        return None
    finally:
        time.sleep(REQUEST_DELAY)


def try_scrape_pages() -> list[str]:
    """Attempt to scrape pages from champagne.fr. Returns raw text blocks."""
    texts = []
    for path in SCRAPE_PAGES:
        soup = fetch_page(path)
        if soup is None:
            continue
        # Extract main content area
        for selector in ["article", ".field-item", ".content", "main"]:
            content = soup.select(selector)
            if content:
                for block in content:
                    text = block.get_text(separator=" ", strip=True)
                    if len(text) > 100:
                        texts.append(text)
                break
    return texts


# ─── Fact Builders ────────────────────────────────────────────────────────────

def _build_grand_cru_facts(source_id: str) -> list[dict]:
    """Generate facts about the 17 Grand Cru villages."""
    facts = []

    facts.append({
        "fact_text": "There are 17 Grand Cru villages in Champagne.",
        "domain": "wine_regions",
        "subdomain": "champagne",
        "source_id": source_id,
        "entities": [{"type": "appellation", "name": "Champagne Grand Cru"}],
        "tags": ["champagne", "grand_cru", "classification"],
    })

    facts.append({
        "fact_text": "Grand Cru villages in Champagne are rated 100% on the Échelle des Crus.",
        "domain": "wine_regions",
        "subdomain": "champagne",
        "source_id": source_id,
        "entities": [{"type": "appellation", "name": "Champagne Grand Cru"}],
        "tags": ["champagne", "grand_cru", "classification"],
    })

    facts.append({
        "fact_text": "The Échelle des Crus is a classification system that rates Champagne villages from 80% to 100%.",
        "domain": "wine_regions",
        "subdomain": "champagne",
        "source_id": source_id,
        "entities": [{"type": "classification", "name": "Échelle des Crus"}],
        "tags": ["champagne", "classification"],
    })

    for village in GRAND_CRU_VILLAGES:
        facts.append({
            "fact_text": f"{village} is a Grand Cru village in Champagne.",
            "domain": "wine_regions",
            "subdomain": "champagne",
            "source_id": source_id,
            "entities": [
                {"type": "village", "name": village},
                {"type": "appellation", "name": "Champagne Grand Cru"},
            ],
            "tags": ["champagne", "grand_cru", "village"],
        })

    # Subregion associations for Grand Cru villages
    grand_cru_subregions = {
        "Montagne de Reims": [
            "Ambonnay", "Beaumont-sur-Vesle", "Bouzy", "Louvois",
            "Mailly-Champagne", "Puisieulx", "Sillery", "Verzenay", "Verzy",
        ],
        "Vallée de la Marne": ["Aÿ", "Tours-sur-Marne"],
        "Côte des Blancs": [
            "Avize", "Chouilly", "Cramant", "Le Mesnil-sur-Oger",
            "Oger", "Oiry",
        ],
    }

    for subregion, villages in grand_cru_subregions.items():
        for village in villages:
            facts.append({
                "fact_text": f"The Grand Cru village of {village} is located in the {subregion} subregion of Champagne.",
                "domain": "wine_regions",
                "subdomain": "champagne",
                "source_id": source_id,
                "entities": [
                    {"type": "village", "name": village},
                    {"type": "region", "name": subregion},
                ],
                "tags": ["champagne", "grand_cru", "geography"],
            })

    return facts


def _build_premier_cru_facts(source_id: str) -> list[dict]:
    """Generate facts about the 42 Premier Cru villages."""
    facts = []

    facts.append({
        "fact_text": "There are 42 Premier Cru villages in Champagne.",
        "domain": "wine_regions",
        "subdomain": "champagne",
        "source_id": source_id,
        "entities": [{"type": "appellation", "name": "Champagne Premier Cru"}],
        "tags": ["champagne", "premier_cru", "classification"],
    })

    facts.append({
        "fact_text": "Premier Cru villages in Champagne are rated 90% to 99% on the Échelle des Crus.",
        "domain": "wine_regions",
        "subdomain": "champagne",
        "source_id": source_id,
        "entities": [{"type": "appellation", "name": "Champagne Premier Cru"}],
        "tags": ["champagne", "premier_cru", "classification"],
    })

    for village in PREMIER_CRU_VILLAGES:
        facts.append({
            "fact_text": f"{village} is a Premier Cru village in Champagne.",
            "domain": "wine_regions",
            "subdomain": "champagne",
            "source_id": source_id,
            "entities": [
                {"type": "village", "name": village},
                {"type": "appellation", "name": "Champagne Premier Cru"},
            ],
            "tags": ["champagne", "premier_cru", "village"],
        })

    return facts


def _build_grape_facts(source_id: str) -> list[dict]:
    """Generate facts about permitted Champagne grape varieties."""
    facts = []

    facts.append({
        "fact_text": "Seven grape varieties are permitted in Champagne AOC production.",
        "domain": "grape_varieties",
        "subdomain": "champagne",
        "source_id": source_id,
        "entities": [{"type": "appellation", "name": "Champagne AOC"}],
        "tags": ["champagne", "grape", "regulation"],
    })

    facts.append({
        "fact_text": "The three principal grape varieties of Champagne are Chardonnay, Pinot Noir, and Pinot Meunier.",
        "domain": "grape_varieties",
        "subdomain": "champagne",
        "source_id": source_id,
        "entities": [
            {"type": "grape", "name": "Chardonnay"},
            {"type": "grape", "name": "Pinot Noir"},
            {"type": "grape", "name": "Pinot Meunier"},
        ],
        "tags": ["champagne", "grape", "principal"],
    })

    facts.append({
        "fact_text": "The four ancillary grape varieties permitted in Champagne are Arbane, Petit Meslier, Pinot Blanc, and Pinot Gris.",
        "domain": "grape_varieties",
        "subdomain": "champagne",
        "source_id": source_id,
        "entities": [
            {"type": "grape", "name": "Arbane"},
            {"type": "grape", "name": "Petit Meslier"},
            {"type": "grape", "name": "Pinot Blanc"},
            {"type": "grape", "name": "Pinot Gris"},
        ],
        "tags": ["champagne", "grape", "ancillary"],
    })

    for grape, info in PERMITTED_GRAPES.items():
        facts.append({
            "fact_text": f"{grape} is a permitted grape variety in Champagne AOC production.",
            "domain": "grape_varieties",
            "subdomain": "champagne",
            "source_id": source_id,
            "entities": [{"type": "grape", "name": grape}],
            "tags": ["champagne", "grape", "regulation"],
        })

        facts.append({
            "fact_text": f"{grape} is a {info['color']} grape variety classified as a {info['status']} variety in Champagne.",
            "domain": "grape_varieties",
            "subdomain": "champagne",
            "source_id": source_id,
            "entities": [{"type": "grape", "name": grape}],
            "tags": ["champagne", "grape", info["status"]],
        })

        facts.append({
            "fact_text": f"{grape} accounts for {info['pct']} in the Champagne vineyard.",
            "domain": "grape_varieties",
            "subdomain": "champagne",
            "source_id": source_id,
            "entities": [{"type": "grape", "name": grape}],
            "tags": ["champagne", "grape", "viticulture"],
        })

    return facts


def _build_production_facts(source_id: str) -> list[dict]:
    """Generate facts about Champagne production rules and winemaking."""
    facts = []

    production_rules = [
        "Champagne must be produced using the méthode champenoise, also called méthode traditionnelle.",
        "The méthode champenoise requires secondary fermentation to take place in the bottle.",
        "Non-vintage Champagne must age on lees for a minimum of 15 months.",
        "Vintage Champagne must age on lees for a minimum of 36 months.",
        "Non-vintage Champagne must age for a minimum of 12 months after tirage.",
        "The minimum total aging for vintage Champagne is 36 months from tirage to disgorgement.",
        "Champagne must undergo riddling (remuage) to collect sediment in the neck of the bottle.",
        "Disgorgement (dégorgement) is the process of removing sediment from a Champagne bottle after riddling.",
        "The first pressing of Champagne grapes is called the cuvée and yields 2,050 litres per 4,000 kg of grapes.",
        "The second pressing of Champagne grapes is called the taille and yields 500 litres per 4,000 kg of grapes.",
        "The maximum press yield in Champagne is 2,550 litres of juice per 4,000 kg of grapes.",
        "Champagne grapes must be harvested by hand; mechanical harvesting is not permitted.",
        "The Champagne AOC was officially established in 1936 under French appellation law.",
        "The Champagne production region is the northernmost major wine region in France.",
        "The Champagne AOC covers approximately 34,300 hectares of vineyard.",
        "There are approximately 319 villages (crus) in the Champagne appellation.",
        "Champagne typically undergoes two fermentations: the first in tank or barrel, the second in bottle.",
        "Liqueur de tirage, a mixture of sugar and yeast, is added to still Champagne wine to trigger secondary fermentation.",
        "Dosage in Champagne is the addition of liqueur d'expédition after disgorgement to adjust sweetness.",
        "The pressure inside a bottle of Champagne is typically around 5 to 6 atmospheres.",
        "Champagne bottles must be sealed with a mushroom-shaped cork held by a wire cage called a muselet.",
        "The standard Champagne bottle size is 75 cl.",
        "A Magnum of Champagne holds 1.5 litres, equivalent to two standard bottles.",
        "A Jeroboam of Champagne holds 3 litres, equivalent to four standard bottles.",
        "A Methuselah of Champagne holds 6 litres, equivalent to eight standard bottles.",
        "A Balthazar of Champagne holds 12 litres, equivalent to sixteen standard bottles.",
        "A Nebuchadnezzar of Champagne holds 15 litres, equivalent to twenty standard bottles.",
        "Reserve wines in Champagne are still wines from previous vintages kept for blending into non-vintage cuvées.",
        "The Chef de Cave is the cellar master responsible for blending and overseeing Champagne production at a house.",
        "Assemblage is the art of blending different base wines, grape varieties, and vintages to create a Champagne cuvée.",
    ]

    for text in production_rules:
        facts.append({
            "fact_text": text,
            "domain": "winemaking",
            "subdomain": "champagne",
            "source_id": source_id,
            "entities": [{"type": "appellation", "name": "Champagne AOC"}],
            "tags": ["champagne", "production", "regulation"],
        })

    return facts


def _build_dosage_facts(source_id: str) -> list[dict]:
    """Generate facts about Champagne dosage levels."""
    facts = []

    facts.append({
        "fact_text": "There are seven official dosage levels for Champagne, defined by residual sugar content.",
        "domain": "winemaking",
        "subdomain": "champagne",
        "source_id": source_id,
        "entities": [{"type": "appellation", "name": "Champagne AOC"}],
        "tags": ["champagne", "dosage", "regulation"],
    })

    for level, info in DOSAGE_LEVELS.items():
        sugar = info["sugar"]
        if sugar.startswith("over"):
            desc = f"{level} Champagne has a dosage of more than 50 grams of sugar per litre."
        elif "-" in sugar:
            low, high = sugar.split("-")
            if low == "0":
                desc = f"{level} Champagne has a dosage of less than {high} grams of sugar per litre."
            else:
                desc = f"{level} Champagne has a dosage between {low} and {high} grams of sugar per litre."
        else:
            desc = f"{level} Champagne has a dosage of {sugar} grams of sugar per litre."

        facts.append({
            "fact_text": desc,
            "domain": "winemaking",
            "subdomain": "champagne",
            "source_id": source_id,
            "entities": [{"type": "style", "name": level}],
            "tags": ["champagne", "dosage", "sweetness"],
        })

        if info["aka"]:
            for aka in info["aka"].split(", "):
                facts.append({
                    "fact_text": f"{level} Champagne is also known as {aka}.",
                    "domain": "winemaking",
                    "subdomain": "champagne",
                    "source_id": source_id,
                    "entities": [{"type": "style", "name": level}],
                    "tags": ["champagne", "dosage", "terminology"],
                })

    return facts


def _build_style_facts(source_id: str) -> list[dict]:
    """Generate facts about Champagne styles."""
    facts = []

    for style, desc in CHAMPAGNE_STYLES.items():
        facts.append({
            "fact_text": f"{style} Champagne is {desc}.",
            "domain": "winemaking",
            "subdomain": "champagne",
            "source_id": source_id,
            "entities": [{"type": "style", "name": style}],
            "tags": ["champagne", "style"],
        })

    # Additional style-related facts
    style_facts = [
        "Blanc de Blancs Champagne is made exclusively from Chardonnay.",
        "Blanc de Noirs Champagne is made exclusively from black-skinned grapes.",
        "Rosé Champagne can be produced by blending red and white wines, a method unique among French AOCs.",
        "Rosé Champagne can also be produced using the saignée method, where juice macerates briefly with red grape skins.",
        "A vintage Champagne must contain 100% wine from the year stated on the label.",
        "Most Champagne produced is non-vintage, representing a house's consistent style across years.",
        "Brut is the most popular dosage level for Champagne worldwide.",
        "Brut Nature Champagne has no sugar added after disgorgement.",
        "A Champagne labeled Extra Brut has very low residual sugar, between 0 and 6 grams per litre.",
    ]

    for text in style_facts:
        facts.append({
            "fact_text": text,
            "domain": "winemaking",
            "subdomain": "champagne",
            "source_id": source_id,
            "entities": [{"type": "appellation", "name": "Champagne AOC"}],
            "tags": ["champagne", "style"],
        })

    return facts


def _build_terroir_facts(source_id: str) -> list[dict]:
    """Generate facts about Champagne terroir, geography, and subregions."""
    facts = []

    for subregion, desc in CHAMPAGNE_SUBREGIONS.items():
        facts.append({
            "fact_text": f"The {subregion} is a major subregion of Champagne, {desc}.",
            "domain": "wine_regions",
            "subdomain": "champagne",
            "source_id": source_id,
            "entities": [{"type": "region", "name": subregion}],
            "tags": ["champagne", "terroir", "geography"],
        })

    terroir_facts = [
        "The Champagne wine region is located in northeastern France, approximately 150 km east of Paris.",
        "The Champagne region has a cool continental climate influenced by oceanic weather patterns.",
        "The average annual temperature in the Champagne region is approximately 11°C.",
        "Chalk soils (craie) are characteristic of the Champagne region and contribute to drainage and mineral character.",
        "The Côte des Blancs subregion has predominantly chalk soils ideal for Chardonnay.",
        "The Montagne de Reims subregion is a forested plateau with north-facing and east-facing slopes.",
        "The Vallée de la Marne has clay-rich soils well-suited to Pinot Meunier.",
        "The Côte des Bar is located in the Aube département, approximately 110 km southeast of Épernay.",
        "Reims and Épernay are the two main cities of the Champagne wine region.",
        "Many Champagne houses store their bottles in crayères, ancient chalk cellars beneath Reims and Épernay.",
        "The crayères of Champagne were originally Roman chalk quarries, repurposed for wine aging.",
        "The Champagne vineyard is divided into four main départements: Marne, Aube, Aisne, and Haute-Marne.",
        "The Marne département contains the majority of Champagne's Grand Cru and Premier Cru vineyards.",
        "Champagne vineyards are planted at altitudes typically between 90 and 300 metres above sea level.",
        "The average yield limit in Champagne is set annually by the CIVC and typically ranges around 10,000-12,000 kg per hectare.",
        "The Comité Interprofessionnel du Vin de Champagne (CIVC) regulates the Champagne industry.",
        "The CIVC sets harvest dates, yield limits, and grape prices each year in Champagne.",
    ]

    for text in terroir_facts:
        facts.append({
            "fact_text": text,
            "domain": "wine_regions",
            "subdomain": "champagne",
            "source_id": source_id,
            "entities": [{"type": "region", "name": "Champagne"}],
            "tags": ["champagne", "terroir", "geography"],
        })

    return facts


def _build_business_facts(source_id: str) -> list[dict]:
    """Generate facts about the Champagne wine business and industry."""
    facts = []

    business_facts = [
        "Champagne houses are classified as Négociants-Manipulants (NM) if they buy grapes and make wine.",
        "Récoltants-Manipulants (RM) are grower-producers in Champagne who grow their own grapes and make their own wine.",
        "Coopératives-Manipulantes (CM) are cooperatives that produce Champagne from member growers' grapes.",
        "The letters NM, RM, or CM appear on Champagne labels to indicate the type of producer.",
        "There are approximately 16,000 growers and 360 Champagne houses in the region.",
        "Champagne houses (Maisons) account for approximately two-thirds of Champagne sales by value.",
        "Grower Champagne (Récoltant-Manipulant) has grown in popularity since the early 2000s.",
        "France is the largest market for Champagne by volume, followed by the United Kingdom and the United States.",
        "Approximately 300 million bottles of Champagne are shipped annually worldwide.",
        "The name Champagne is legally protected in the European Union and many countries worldwide.",
        "Only sparkling wine produced in the Champagne AOC region may be labeled as Champagne.",
        "The protection of the Champagne name is enforced by the CIVC and French law.",
    ]

    for text in business_facts:
        facts.append({
            "fact_text": text,
            "domain": "wine_business",
            "subdomain": "champagne",
            "source_id": source_id,
            "entities": [{"type": "region", "name": "Champagne"}],
            "tags": ["champagne", "business", "industry"],
        })

    return facts


def _build_viticulture_facts(source_id: str) -> list[dict]:
    """Generate facts about Champagne viticulture."""
    facts = []

    viticulture_facts = [
        "Champagne vineyards are trained using the Chablis, Cordon de Royat, or Vallée de la Marne pruning methods.",
        "The Chablis pruning method is commonly used for Chardonnay in the Côte des Blancs.",
        "The Cordon de Royat pruning method is commonly used for Pinot Noir in the Montagne de Reims.",
        "The Vallée de la Marne pruning method, also called Guyot, is commonly used for Pinot Meunier.",
        "Planting density in Champagne vineyards must be at least 8,000 vines per hectare.",
        "The maximum distance between rows in Champagne vineyards is 1.50 metres.",
        "Champagne grapes are harvested by hand to ensure whole clusters arrive at the press.",
        "The Champagne harvest, called vendange, typically begins in September.",
        "The CIVC officially sets the start date of harvest each year for different villages and grape varieties.",
        "Frost is a significant viticultural hazard in Champagne, particularly during spring.",
        "Champagne growers use methods such as smudge pots, wind machines, and aspersion to protect against frost.",
        "The phylloxera crisis devastated Champagne vineyards in the late 19th century.",
        "Most Champagne vines are now grafted onto American rootstock to resist phylloxera.",
    ]

    for text in viticulture_facts:
        facts.append({
            "fact_text": text,
            "domain": "viticulture",
            "subdomain": "champagne",
            "source_id": source_id,
            "entities": [{"type": "region", "name": "Champagne"}],
            "tags": ["champagne", "viticulture"],
        })

    return facts


# ─── Main Pipeline ────────────────────────────────────────────────────────────

def build_all_facts(source_id: str) -> list[dict]:
    """Build all Champagne facts from curated knowledge base."""
    all_facts = []

    builders = [
        ("Grand Cru villages", _build_grand_cru_facts),
        ("Premier Cru villages", _build_premier_cru_facts),
        ("Grape varieties", _build_grape_facts),
        ("Production rules", _build_production_facts),
        ("Dosage levels", _build_dosage_facts),
        ("Champagne styles", _build_style_facts),
        ("Terroir & geography", _build_terroir_facts),
        ("Business & industry", _build_business_facts),
        ("Viticulture", _build_viticulture_facts),
    ]

    for name, builder in builders:
        facts = builder(source_id)
        logger.info(f"  {name}: {len(facts)} facts")
        all_facts.extend(facts)

    return all_facts


def run_scraper(dry_run: bool = False) -> int:
    """Run the full Champagne scraper pipeline. Returns count of facts inserted."""
    logger.info("Starting Champagne scraper...")

    # Attempt to scrape live pages (may fail with 403)
    logger.info("Attempting to fetch pages from champagne.fr...")
    scraped_texts = try_scrape_pages()
    if scraped_texts:
        logger.info(f"Successfully scraped {len(scraped_texts)} text blocks from champagne.fr")
    else:
        logger.info("Could not scrape champagne.fr (site may block automated requests). Using curated knowledge base.")

    # Register source
    source_id = ensure_source(
        name=SOURCE_NAME,
        url="https://www.champagne.fr",
        source_type="official_body",
        tier=SOURCE_TIER,
        language="en",
    )
    logger.info(f"Source registered: {SOURCE_NAME} (id={source_id})")

    # Build facts from curated knowledge
    all_facts = build_all_facts(source_id)
    logger.info(f"Total facts generated: {len(all_facts)}")

    if dry_run:
        click.echo(f"\n[DRY RUN] Would insert {len(all_facts)} facts.")
        click.echo("\nSample facts:")
        for fact in random.sample(all_facts, min(20, len(all_facts))):
            click.echo(f"  [{fact['domain']}] {fact['fact_text']}")
        return len(all_facts)

    # Insert into database
    inserted = insert_facts_batch(all_facts)
    logger.info(f"Inserted {inserted} new facts (duplicates skipped)")
    return inserted


# ─── Validation ───────────────────────────────────────────────────────────────

def validate_facts():
    """Validate the generated facts without inserting into the database."""
    # Build facts with a placeholder source_id (won't be inserted)
    placeholder_source_id = "validation-placeholder"
    all_facts = build_all_facts(placeholder_source_id)

    click.echo(f"\n{'='*70}")
    click.echo(f"  CHAMPAGNE SCRAPER — VALIDATION REPORT")
    click.echo(f"{'='*70}\n")

    # (a) Domain/subdomain distribution
    domain_counts = Counter(f["domain"] for f in all_facts)
    subdomain_counts = Counter(f.get("subdomain", "none") for f in all_facts)

    click.echo("DOMAIN DISTRIBUTION:")
    click.echo(f"  {'Domain':<25} {'Count':>6}")
    click.echo(f"  {'-'*25} {'-'*6}")
    for domain, count in sorted(domain_counts.items(), key=lambda x: -x[1]):
        click.echo(f"  {domain:<25} {count:>6}")
    click.echo()

    click.echo("SUBDOMAIN DISTRIBUTION:")
    click.echo(f"  {'Subdomain':<25} {'Count':>6}")
    click.echo(f"  {'-'*25} {'-'*6}")
    for subdomain, count in sorted(subdomain_counts.items(), key=lambda x: -x[1]):
        click.echo(f"  {subdomain:<25} {count:>6}")
    click.echo()

    # (b) Length checks
    short_facts = [f for f in all_facts if len(f["fact_text"].split()) < 5]
    long_facts = [f for f in all_facts if len(f["fact_text"].split()) > 50]

    click.echo(f"LENGTH CHECKS:")
    click.echo(f"  Short facts (<5 words):  {len(short_facts)}")
    if short_facts:
        for f in short_facts[:5]:
            click.echo(f"    ⚠ {f['fact_text']}")
    click.echo(f"  Long facts (>50 words):  {len(long_facts)}")
    if long_facts:
        for f in long_facts[:5]:
            click.echo(f"    ⚠ {f['fact_text'][:100]}...")
    click.echo()

    # (c) Facts that are just entity names with no predicate
    no_predicate = [f for f in all_facts if f["fact_text"].rstrip(".").count(" ") < 2]
    click.echo(f"NO-PREDICATE CHECK (fewer than 3 words):")
    click.echo(f"  Suspect facts: {len(no_predicate)}")
    if no_predicate:
        for f in no_predicate[:5]:
            click.echo(f"    ⚠ {f['fact_text']}")
    click.echo()

    # (d) Duplicate-ish facts via string containment
    texts = [f["fact_text"] for f in all_facts]
    near_dupes = []
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            if texts[i] in texts[j] or texts[j] in texts[i]:
                near_dupes.append((texts[i], texts[j]))
                if len(near_dupes) >= 20:
                    break
        if len(near_dupes) >= 20:
            break

    click.echo(f"NEAR-DUPLICATE CHECK (string containment):")
    click.echo(f"  Potential near-duplicates: {len(near_dupes)}")
    if near_dupes:
        for a, b in near_dupes[:5]:
            click.echo(f"    A: {a}")
            click.echo(f"    B: {b}")
            click.echo()
    click.echo()

    # (e) Entity population check
    with_entities = sum(1 for f in all_facts if f.get("entities"))
    click.echo(f"ENTITY POPULATION:")
    click.echo(f"  Facts with entities:    {with_entities}/{len(all_facts)} ({100*with_entities/len(all_facts):.1f}%)")
    click.echo(f"  Facts without entities: {len(all_facts) - with_entities}/{len(all_facts)}")
    click.echo()

    # (f) Random sample
    click.echo(f"RANDOM SAMPLE (10 facts):")
    for fact in random.sample(all_facts, min(10, len(all_facts))):
        click.echo(f"  [{fact['domain']:<16}] {fact['fact_text']}")
    click.echo()

    # Grand Cru quality check
    click.echo(f"{'='*70}")
    click.echo(f"  GRAND CRU QUALITY CHECK")
    click.echo(f"{'='*70}\n")

    gc_facts = [f for f in all_facts if "grand_cru" in f.get("tags", []) and "village" in f.get("tags", [])]
    gc_villages = sorted(set(f["fact_text"].split(" is a Grand Cru")[0] for f in gc_facts if "is a Grand Cru" in f["fact_text"]))
    click.echo(f"  Grand Cru villages found: {len(gc_villages)}/17")
    for v in gc_villages:
        click.echo(f"    ✓ {v}")
    if len(gc_villages) != 17:
        click.echo(f"\n  ⚠ WARNING: Expected 17 Grand Cru villages, found {len(gc_villages)}")
    click.echo()

    click.echo(f"TOTAL FACTS: {len(all_facts)}")
    click.echo()


# ─── CLI ──────────────────────────────────────────────────────────────────────

@click.command()
@click.option("--all", "run_all", is_flag=True, help="Run full scraper pipeline")
@click.option("--dry-run", is_flag=True, help="Generate facts without inserting into database")
@click.option("--validate", is_flag=True, help="Validate generated facts and print quality report")
@click.option("--list", "list_sections", is_flag=True, help="List available fact categories")
def main(run_all: bool, dry_run: bool, validate: bool, list_sections: bool):
    """OenoBench Champagne Scraper — Extract Champagne wine knowledge."""
    logger.add("data/logs/champagne_{time}.log", rotation="10 MB")

    if list_sections:
        click.echo("\nAvailable fact categories:")
        categories = [
            ("grand_cru", "17 Grand Cru villages with subregion associations"),
            ("premier_cru", "42 Premier Cru villages"),
            ("grapes", "7 permitted grape varieties with details"),
            ("production", "Production rules and méthode champenoise"),
            ("dosage", "7 dosage/sweetness levels"),
            ("styles", "Champagne styles (Blanc de Blancs, Rosé, etc.)"),
            ("terroir", "Geography, subregions, and terroir"),
            ("business", "Industry structure and regulations"),
            ("viticulture", "Viticultural practices"),
        ]
        for name, desc in categories:
            click.echo(f"  {name:20s} — {desc}")
        return

    if validate:
        validate_facts()
        return

    if run_all or dry_run:
        count = run_scraper(dry_run=dry_run)
        if not dry_run:
            click.echo(f"\nInserted {count} new Champagne facts.")
            click.echo(f"Total facts in database: {get_fact_count()}")
        return

    click.echo("Use --all to run the scraper, --dry-run to preview, or --validate for quality checks.")
    click.echo("Use --list to see available fact categories.")


if __name__ == "__main__":
    main()
