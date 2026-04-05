"""
OenoBench — Bordeaux Wine Scraper (CIVB / bordeaux.com)

Extracts Bordeaux wine knowledge: appellations, classifications (1855, Saint-Émilion,
Graves/Pessac-Léognan), grape varieties, and regional structure.

Usage:
    python -m src.scrapers.bordeaux --all
    python -m src.scrapers.bordeaux --dry-run
    python -m src.scrapers.bordeaux --validate
    python -m src.scrapers.bordeaux --list
    python -m src.scrapers.bordeaux --test-run
    python -m src.scrapers.bordeaux --test-run --cleanup
"""

import random
import time
from collections import Counter
from typing import Optional

import click
import requests
from bs4 import BeautifulSoup
from loguru import logger

from src.utils.facts import ensure_source, insert_fact, insert_facts_batch, get_fact_count

# ─── Test Run ────────────────────────────────────────────────────────────────

TEST_RUN_LIMIT = 5  # items per category in --test-run mode

# ─── Configuration ────────────────────────────────────────────────────────────

BASE_URL = "https://www.bordeaux.com"
USER_AGENT = "OenoBench-Research/1.0 (academic wine benchmark)"
REQUEST_DELAY = 5  # seconds between HTTP requests
REQUEST_TIMEOUT = 30

SOURCE_NAME = "CIVB (Bordeaux Wine Council)"
SOURCE_URL = "https://www.bordeaux.com"
SOURCE_TYPE = "official_body"
SOURCE_TIER = "tier_2_authoritative"

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# ─── 1855 Classification — Complete 61 Châteaux ──────────────────────────────

CLASSIFICATION_1855 = {
    "First Growth": [
        ("Château Lafite Rothschild", "Pauillac"),
        ("Château Latour", "Pauillac"),
        ("Château Margaux", "Margaux"),
        ("Château Haut-Brion", "Pessac-Léognan"),
        ("Château Mouton Rothschild", "Pauillac"),
    ],
    "Second Growth": [
        ("Château Brane-Cantenac", "Margaux"),
        ("Château Cos d'Estournel", "Saint-Estèphe"),
        ("Château Ducru-Beaucaillou", "Saint-Julien"),
        ("Château Durfort-Vivens", "Margaux"),
        ("Château Gruaud Larose", "Saint-Julien"),
        ("Château Lascombes", "Margaux"),
        ("Château Léoville Barton", "Saint-Julien"),
        ("Château Léoville Las Cases", "Saint-Julien"),
        ("Château Léoville Poyferré", "Saint-Julien"),
        ("Château Montrose", "Saint-Estèphe"),
        ("Château Pichon Longueville Baron", "Pauillac"),
        ("Château Pichon Longueville Comtesse de Lalande", "Pauillac"),
        ("Château Rauzan-Gassies", "Margaux"),
        ("Château Rauzan-Ségla", "Margaux"),
    ],
    "Third Growth": [
        ("Château Boyd-Cantenac", "Margaux"),
        ("Château Calon-Ségur", "Saint-Estèphe"),
        ("Château Cantenac Brown", "Margaux"),
        ("Château Desmirail", "Margaux"),
        ("Château Ferrière", "Margaux"),
        ("Château Giscours", "Margaux"),
        ("Château d'Issan", "Margaux"),
        ("Château Kirwan", "Margaux"),
        ("Château Lagrange", "Saint-Julien"),
        ("Château La Lagune", "Haut-Médoc"),
        ("Château Langoa Barton", "Saint-Julien"),
        ("Château Malescot St. Exupéry", "Margaux"),
        ("Château Marquis d'Alesme Becker", "Margaux"),
        ("Château Palmer", "Margaux"),
    ],
    "Fourth Growth": [
        ("Château Beychevelle", "Saint-Julien"),
        ("Château Branaire-Ducru", "Saint-Julien"),
        ("Château Duhart-Milon", "Pauillac"),
        ("Château Lafon-Rochet", "Saint-Estèphe"),
        ("Château Marquis de Terme", "Margaux"),
        ("Château Pouget", "Margaux"),
        ("Château Prieuré-Lichine", "Margaux"),
        ("Château Saint-Pierre", "Saint-Julien"),
        ("Château Talbot", "Saint-Julien"),
        ("Château La Tour Carnet", "Haut-Médoc"),
    ],
    "Fifth Growth": [
        ("Château d'Armailhac", "Pauillac"),
        ("Château Batailley", "Pauillac"),
        ("Château Belgrave", "Haut-Médoc"),
        ("Château de Camensac", "Haut-Médoc"),
        ("Château Cantemerle", "Haut-Médoc"),
        ("Château Clerc Milon", "Pauillac"),
        ("Château Cos Labory", "Saint-Estèphe"),
        ("Château Croizet-Bages", "Pauillac"),
        ("Château Dauzac", "Margaux"),
        ("Château Grand-Puy Ducasse", "Pauillac"),
        ("Château Grand-Puy-Lacoste", "Pauillac"),
        ("Château Haut-Bages Libéral", "Pauillac"),
        ("Château Haut-Batailley", "Pauillac"),
        ("Château Lynch-Bages", "Pauillac"),
        ("Château Lynch-Moussas", "Pauillac"),
        ("Château Pédesclaux", "Pauillac"),
        ("Château Pontet-Canet", "Pauillac"),
        ("Château du Tertre", "Margaux"),
    ],
}

# French terms for the growth levels
GROWTH_FRENCH = {
    "First Growth": "Premier Cru",
    "Second Growth": "Deuxième Cru",
    "Third Growth": "Troisième Cru",
    "Fourth Growth": "Quatrième Cru",
    "Fifth Growth": "Cinquième Cru",
}

# ─── Saint-Émilion Classification (2012) ─────────────────────────────────────

SAINT_EMILION_CLASSIFICATION = {
    "Premier Grand Cru Classé A": [
        "Château Angélus",
        "Château Ausone",
        "Château Cheval Blanc",
        "Château Pavie",
    ],
    "Premier Grand Cru Classé B": [
        "Château Beau-Séjour Bécot",
        "Château Beauséjour",
        "Château Bélair-Monange",
        "Château Canon",
        "Château Canon la Gaffelière",
        "Château Figeac",
        "Château La Gaffelière",
        "Château Larcis Ducasse",
        "Château La Mondotte",
        "Château Pavie Macquin",
        "Château Troplong Mondot",
        "Château Trottevieille",
        "Château Valandraud",
        "Clos Fourtet",
    ],
}

# ─── Graves/Pessac-Léognan Classification (1953/1959) ────────────────────────

GRAVES_CLASSIFICATION = {
    "red": [
        ("Château Bouscaut", "Cadaujac"),
        ("Château Carbonnieux", "Léognan"),
        ("Domaine de Chevalier", "Léognan"),
        ("Château de Fieuzal", "Léognan"),
        ("Château Haut-Bailly", "Léognan"),
        ("Château Haut-Brion", "Pessac"),
        ("Château La Mission Haut-Brion", "Talence"),
        ("Château La Tour Haut-Brion", "Talence"),
        ("Château Latour-Martillac", "Martillac"),
        ("Château Malartic-Lagravière", "Léognan"),
        ("Château Olivier", "Léognan"),
        ("Château Pape Clément", "Pessac"),
        ("Château Smith Haut Lafitte", "Martillac"),
    ],
    "white": [
        ("Château Bouscaut", "Cadaujac"),
        ("Château Carbonnieux", "Léognan"),
        ("Domaine de Chevalier", "Léognan"),
        ("Château Couhins", "Villenave-d'Ornon"),
        ("Château Couhins-Lurton", "Villenave-d'Ornon"),
        ("Château Haut-Brion", "Pessac"),
        ("Château Laville Haut-Brion", "Talence"),
        ("Château Latour-Martillac", "Martillac"),
        ("Château Malartic-Lagravière", "Léognan"),
        ("Château Olivier", "Léognan"),
    ],
}

# ─── Bordeaux Appellations ────────────────────────────────────────────────────

APPELLATIONS = {
    # (name, level, parent_region, bank, wine_colors, notes)
    "generic": [
        ("Bordeaux", "regional", "Bordeaux", None, ["red", "white", "rosé"],
         "Bordeaux AOC is the largest appellation in the region, covering the entire Bordeaux vineyard area."),
        ("Bordeaux Supérieur", "regional", "Bordeaux", None, ["red"],
         "Bordeaux Supérieur requires lower yields and longer aging than basic Bordeaux AOC."),
        ("Crémant de Bordeaux", "regional", "Bordeaux", None, ["sparkling white", "sparkling rosé"],
         "Crémant de Bordeaux is produced using the traditional method of secondary fermentation in bottle."),
    ],
    "medoc": [
        ("Médoc", "subregional", "Médoc", "Left Bank", ["red"],
         "Médoc AOC covers the northern part of the Médoc peninsula."),
        ("Haut-Médoc", "subregional", "Médoc", "Left Bank", ["red"],
         "Haut-Médoc AOC covers the southern, more prestigious part of the Médoc peninsula."),
        ("Saint-Estèphe", "communal", "Haut-Médoc", "Left Bank", ["red"],
         "Saint-Estèphe is the northernmost of the six communal appellations in the Haut-Médoc."),
        ("Pauillac", "communal", "Haut-Médoc", "Left Bank", ["red"],
         "Pauillac is home to three of the five First Growth estates of the 1855 Classification."),
        ("Saint-Julien", "communal", "Haut-Médoc", "Left Bank", ["red"],
         "Saint-Julien is the smallest of the major Haut-Médoc communal appellations."),
        ("Margaux", "communal", "Haut-Médoc", "Left Bank", ["red"],
         "Margaux is the largest communal appellation in the Médoc and the southernmost of the six."),
        ("Listrac-Médoc", "communal", "Haut-Médoc", "Left Bank", ["red"],
         "Listrac-Médoc is one of the two inland communal appellations in the Haut-Médoc."),
        ("Moulis-en-Médoc", "communal", "Haut-Médoc", "Left Bank", ["red"],
         "Moulis-en-Médoc is the smallest communal appellation in the Haut-Médoc by area."),
    ],
    "graves": [
        ("Graves", "subregional", "Graves", "Left Bank", ["red", "white"],
         "Graves AOC is one of the oldest wine regions in Bordeaux, named for its gravelly soil."),
        ("Pessac-Léognan", "communal", "Graves", "Left Bank", ["red", "white"],
         "Pessac-Léognan was created in 1987 from the northern part of the Graves region."),
        ("Sauternes", "communal", "Graves", "Left Bank", ["sweet white"],
         "Sauternes produces some of the world's most renowned sweet wines affected by noble rot (botrytis)."),
        ("Barsac", "communal", "Graves", "Left Bank", ["sweet white"],
         "Barsac wines may be labeled as either Barsac AOC or Sauternes AOC."),
        ("Cérons", "communal", "Graves", "Left Bank", ["sweet white"],
         "Cérons AOC produces sweet white wines from an area between Graves and Barsac."),
        ("Graves Supérieures", "subregional", "Graves", "Left Bank", ["sweet white"],
         "Graves Supérieures AOC produces semi-sweet to sweet white wines."),
    ],
    "saint_emilion": [
        ("Saint-Émilion", "communal", "Libournais", "Right Bank", ["red"],
         "Saint-Émilion is one of the oldest wine-producing areas in Bordeaux, with a UNESCO World Heritage designation."),
        ("Saint-Émilion Grand Cru", "communal", "Libournais", "Right Bank", ["red"],
         "Saint-Émilion Grand Cru requires stricter production rules than the base Saint-Émilion appellation."),
        ("Lussac-Saint-Émilion", "communal", "Libournais", "Right Bank", ["red"],
         "Lussac-Saint-Émilion is a satellite appellation of Saint-Émilion."),
        ("Montagne-Saint-Émilion", "communal", "Libournais", "Right Bank", ["red"],
         "Montagne-Saint-Émilion is the largest of the Saint-Émilion satellite appellations."),
        ("Puisseguin-Saint-Émilion", "communal", "Libournais", "Right Bank", ["red"],
         "Puisseguin-Saint-Émilion is a satellite appellation east of Saint-Émilion."),
        ("Saint-Georges-Saint-Émilion", "communal", "Libournais", "Right Bank", ["red"],
         "Saint-Georges-Saint-Émilion is the smallest of the Saint-Émilion satellite appellations."),
    ],
    "pomerol": [
        ("Pomerol", "communal", "Libournais", "Right Bank", ["red"],
         "Pomerol has no official classification system despite producing some of Bordeaux's most expensive wines."),
        ("Lalande-de-Pomerol", "communal", "Libournais", "Right Bank", ["red"],
         "Lalande-de-Pomerol is located north of Pomerol, separated by the Barbanne stream."),
    ],
    "fronsac": [
        ("Fronsac", "communal", "Libournais", "Right Bank", ["red"],
         "Fronsac AOC is located west of Pomerol on the right bank of the Dordogne."),
        ("Canon-Fronsac", "communal", "Libournais", "Right Bank", ["red"],
         "Canon-Fronsac is considered the superior appellation within the Fronsac area."),
    ],
    "entre_deux_mers": [
        ("Entre-Deux-Mers", "subregional", "Entre-Deux-Mers", None, ["dry white"],
         "Entre-Deux-Mers lies between the Garonne and Dordogne rivers."),
        ("Entre-Deux-Mers Haut-Benauge", "communal", "Entre-Deux-Mers", None, ["dry white"],
         "Entre-Deux-Mers Haut-Benauge is a sub-appellation in the southeastern part of Entre-Deux-Mers."),
    ],
    "cotes": [
        ("Blaye Côtes de Bordeaux", "subregional", "Blayais", "Right Bank", ["red", "white"],
         "Blaye Côtes de Bordeaux is located on the right bank of the Gironde estuary opposite the Médoc."),
        ("Côtes de Bourg", "subregional", "Bourgeais", "Right Bank", ["red", "white"],
         "Côtes de Bourg is one of the oldest wine areas in Bordeaux, predating the Médoc."),
        ("Cadillac Côtes de Bordeaux", "subregional", "Premières Côtes", None, ["red"],
         "Cadillac Côtes de Bordeaux covers the right bank slopes of the Garonne."),
        ("Castillon Côtes de Bordeaux", "subregional", "Libournais", "Right Bank", ["red"],
         "Castillon Côtes de Bordeaux is located east of Saint-Émilion."),
        ("Francs Côtes de Bordeaux", "subregional", "Libournais", "Right Bank", ["red", "white"],
         "Francs Côtes de Bordeaux is the easternmost appellation in the Bordeaux region."),
        ("Sainte-Foy Côtes de Bordeaux", "subregional", "Entre-Deux-Mers", None, ["red", "white"],
         "Sainte-Foy Côtes de Bordeaux is in the far east of the Bordeaux region near the Dordogne border."),
    ],
    "sweet": [
        ("Cadillac", "communal", "Premières Côtes", None, ["sweet white"],
         "Cadillac AOC is a sweet white wine appellation on the right bank of the Garonne."),
        ("Loupiac", "communal", "Premières Côtes", None, ["sweet white"],
         "Loupiac AOC faces Sauternes across the Garonne and produces botrytized sweet wines."),
        ("Sainte-Croix-du-Mont", "communal", "Premières Côtes", None, ["sweet white"],
         "Sainte-Croix-du-Mont produces sweet white wines from hillside vineyards overlooking the Garonne."),
    ],
    "other": [
        ("Graves de Vayres", "communal", "Entre-Deux-Mers", None, ["red", "white"],
         "Graves de Vayres is located in the northwest of the Entre-Deux-Mers area."),
        ("Bordeaux Haut-Benauge", "subregional", "Entre-Deux-Mers", None, ["sweet white"],
         "Bordeaux Haut-Benauge is a small appellation producing semi-sweet and sweet white wines."),
        ("Côtes de Bordeaux Saint-Macaire", "subregional", "Premières Côtes", None, ["sweet white"],
         "Côtes de Bordeaux Saint-Macaire produces sweet white wines south of the Entre-Deux-Mers."),
        ("Sainte-Foy Bordeaux", "communal", "Entre-Deux-Mers", None, ["red", "white"],
         "Sainte-Foy Bordeaux is located around the town of Sainte-Foy-la-Grande in eastern Bordeaux."),
    ],
}

# ─── Key Grape Varieties ─────────────────────────────────────────────────────

GRAPE_VARIETIES = {
    "Cabernet Sauvignon": {
        "color": "red",
        "bank": "Left Bank",
        "facts": [
            "Cabernet Sauvignon is the dominant red grape variety on the Left Bank of Bordeaux.",
            "Cabernet Sauvignon is a cross between Cabernet Franc and Sauvignon Blanc.",
            "Cabernet Sauvignon produces wines with firm tannins, blackcurrant flavors, and aging potential.",
            "Cabernet Sauvignon accounts for approximately 26% of the total Bordeaux vineyard area.",
            "Cabernet Sauvignon thrives in the gravelly soils of the Médoc and Graves regions.",
        ],
    },
    "Merlot": {
        "color": "red",
        "bank": "Right Bank",
        "facts": [
            "Merlot is the most widely planted grape variety in the Bordeaux region.",
            "Merlot is the dominant grape variety on the Right Bank of Bordeaux.",
            "Merlot accounts for approximately 66% of the total Bordeaux red grape plantings.",
            "Merlot produces softer, rounder wines than Cabernet Sauvignon with plum and cherry flavors.",
            "Merlot ripens earlier than Cabernet Sauvignon, making it suited to the cooler clay soils of the Right Bank.",
        ],
    },
    "Cabernet Franc": {
        "color": "red",
        "bank": "Right Bank",
        "facts": [
            "Cabernet Franc is the third most planted red grape variety in Bordeaux.",
            "Cabernet Franc plays a significant blending role in Saint-Émilion, where Château Cheval Blanc is Cabernet Franc-dominant.",
            "Cabernet Franc contributes aromatic complexity with notes of violets, raspberries, and graphite.",
            "Cabernet Franc buds and ripens earlier than Cabernet Sauvignon.",
            "Cabernet Franc is one of the parent varieties of Cabernet Sauvignon.",
        ],
    },
    "Sémillon": {
        "color": "white",
        "bank": None,
        "facts": [
            "Sémillon is the primary grape variety used in Sauternes and Barsac sweet wines.",
            "Sémillon is particularly susceptible to noble rot (Botrytis cinerea), which concentrates sugars.",
            "Sémillon is the most planted white grape variety in the Bordeaux region.",
            "Sémillon produces full-bodied white wines with honeyed, waxy character when aged.",
            "Sémillon is often blended with Sauvignon Blanc in dry white Bordeaux wines.",
        ],
    },
    "Sauvignon Blanc": {
        "color": "white",
        "bank": None,
        "facts": [
            "Sauvignon Blanc is the second most planted white grape variety in Bordeaux.",
            "Sauvignon Blanc provides acidity and aromatic freshness to Bordeaux white blends.",
            "Sauvignon Blanc is used in both dry white Bordeaux and as a component in Sauternes.",
            "Sauvignon Blanc in Bordeaux shows citrus, boxwood, and mineral characters.",
            "Sauvignon Blanc is one of the parent grapes of Cabernet Sauvignon.",
        ],
    },
    "Muscadelle": {
        "color": "white",
        "bank": None,
        "facts": [
            "Muscadelle is a minor white grape variety used in Bordeaux blends.",
            "Muscadelle adds floral and musky aromas to white Bordeaux and Sauternes wines.",
            "Muscadelle is typically used in small proportions, rarely exceeding 10% of a blend.",
            "Muscadelle is susceptible to rot and requires careful canopy management.",
        ],
    },
}

# ─── Regional / General Bordeaux Facts ────────────────────────────────────────

GENERAL_FACTS = [
    # Geography and structure
    "Bordeaux is located in southwestern France along the Garonne, Dordogne, and Gironde waterways.",
    "The Bordeaux wine region covers approximately 111,000 hectares of vineyards.",
    "Bordeaux is divided into the Left Bank and Right Bank by the Gironde estuary and Garonne river.",
    "The Left Bank of Bordeaux includes the Médoc, Graves, and Sauternes areas.",
    "The Right Bank of Bordeaux includes Saint-Émilion, Pomerol, and Fronsac areas.",
    "The Entre-Deux-Mers region lies between the Garonne and Dordogne rivers.",
    "Bordeaux has over 60 distinct appellations d'origine contrôlée (AOCs).",
    "Bordeaux produces approximately 700 million bottles of wine per year.",
    "Bordeaux has a maritime climate moderated by the Atlantic Ocean and the Gulf Stream.",
    "The Gironde estuary is the largest estuary in Western Europe.",
    # Classification systems
    "The 1855 Classification ranks 61 châteaux across five growths (crus).",
    "The 1855 Classification was created for the Paris Universal Exhibition at the request of Napoleon III.",
    "The 1855 Classification has been amended only once, in 1973, when Mouton Rothschild was elevated to First Growth.",
    "The original 1855 Classification ranked only 60 châteaux; Mouton Rothschild's elevation in 1973 brought the total to 61.",
    "The 1855 Classification covers only red wines from the Médoc (plus Haut-Brion from Graves).",
    "The 1855 Sauternes Classification is a separate ranking of sweet white wine estates.",
    "Saint-Émilion's classification system is unique in Bordeaux because it is revised approximately every 10 years.",
    "The Graves Classification of 1953, updated in 1959, classifies estates for both red and white wines.",
    "The Graves Classification includes 16 estates, all now within the Pessac-Léognan appellation.",
    "Pomerol has never had an official classification despite Château Pétrus being among the most expensive Bordeaux wines.",
    # Winemaking
    "Red Bordeaux wines are predominantly blends of Cabernet Sauvignon, Merlot, and Cabernet Franc.",
    "White Bordeaux wines are typically blends of Sauvignon Blanc, Sémillon, and Muscadelle.",
    "The term 'claret' historically refers to red Bordeaux wines, derived from the French 'clairet'.",
    "Bordeaux's en primeur system allows wines to be sold as futures while still aging in barrel.",
    "Most Bordeaux wines are aged in oak barrels, with top estates using a high proportion of new French oak.",
    "The Bordeaux bottle has a distinctive high-shouldered shape, different from the Burgundy bottle.",
    # History
    "Bordeaux wine production dates back to Roman times in the 1st century AD.",
    "The Bordeaux wine trade was historically driven by English, Dutch, and Irish merchants.",
    "The phylloxera epidemic devastated Bordeaux vineyards in the 1870s and 1880s.",
    "Bordeaux vineyards were largely replanted on American rootstock after the phylloxera crisis.",
    # Soil and terroir
    "Left Bank Bordeaux soils are characterized by deep gravel beds suited to Cabernet Sauvignon.",
    "Right Bank Bordeaux soils are predominantly clay and limestone, favoring Merlot.",
    "Sauternes benefits from morning mists from the Ciron river that promote noble rot development.",
    "Pomerol's terroir features a distinctive iron-rich clay subsoil known as 'crasse de fer'.",
    "Saint-Émilion's vineyards are planted on a limestone plateau and surrounding clay slopes.",
]

# ─── Production Rules by Appellation ──────────────────────────────────────────

PRODUCTION_RULES = [
    ("Bordeaux", "The minimum alcohol level for red Bordeaux AOC is 10% ABV."),
    ("Bordeaux Supérieur", "Bordeaux Supérieur requires a minimum alcohol level of 10.5% ABV."),
    ("Bordeaux Supérieur", "Bordeaux Supérieur requires a maximum yield of 50 hectoliters per hectare."),
    ("Médoc", "Médoc AOC permits only red wines from Cabernet Sauvignon, Merlot, Cabernet Franc, Petit Verdot, Malbec, and Carmenère."),
    ("Pauillac", "Pauillac AOC has a maximum permitted yield of 47 hectoliters per hectare."),
    ("Saint-Julien", "Saint-Julien AOC has a maximum permitted yield of 47 hectoliters per hectare."),
    ("Margaux", "Margaux AOC has a maximum permitted yield of 47 hectoliters per hectare."),
    ("Saint-Estèphe", "Saint-Estèphe AOC has a maximum permitted yield of 47 hectoliters per hectare."),
    ("Sauternes", "Sauternes AOC has a maximum yield of 25 hectoliters per hectare."),
    ("Sauternes", "Sauternes AOC requires a minimum potential alcohol of 221 grams per liter of sugar."),
    ("Pomerol", "Pomerol AOC requires a minimum of 11% ABV for its red wines."),
    ("Saint-Émilion Grand Cru", "Saint-Émilion Grand Cru requires a minimum of 11.5% ABV."),
    ("Saint-Émilion Grand Cru", "Saint-Émilion Grand Cru wines must pass a tasting panel review before release."),
    ("Pessac-Léognan", "Pessac-Léognan AOC permits both red and dry white wines."),
    ("Pessac-Léognan", "Pessac-Léognan red wines must contain a minimum of 25% Cabernet Sauvignon, Cabernet Franc, or Merlot."),
    ("Entre-Deux-Mers", "Entre-Deux-Mers AOC permits only dry white wines; red wines are labeled as Bordeaux or Bordeaux Supérieur."),
    ("Crémant de Bordeaux", "Crémant de Bordeaux requires at least 9 months of aging on lees."),
]


# ─── HTTP Helpers ─────────────────────────────────────────────────────────────

def check_robots_txt() -> dict:
    """Fetch and parse robots.txt from bordeaux.com."""
    url = f"{BASE_URL}/robots.txt"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 200:
            logger.info("robots.txt fetched successfully")
            disallowed = []
            for line in resp.text.splitlines():
                line = line.strip()
                if line.lower().startswith("disallow:"):
                    path = line.split(":", 1)[1].strip()
                    if path:
                        disallowed.append(path)
            return {"status": "ok", "disallowed": disallowed, "raw": resp.text}
        else:
            logger.warning(f"robots.txt returned status {resp.status_code}")
            return {"status": "error", "code": resp.status_code}
    except requests.RequestException as e:
        logger.warning(f"Could not fetch robots.txt: {e}")
        return {"status": "error", "exception": str(e)}


def fetch_page(url: str) -> Optional[BeautifulSoup]:
    """Fetch a page with rate limiting and return parsed BeautifulSoup."""
    try:
        logger.debug(f"Fetching: {url}")
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        time.sleep(REQUEST_DELAY)
        if resp.status_code == 200:
            return BeautifulSoup(resp.text, "lxml")
        else:
            logger.warning(f"HTTP {resp.status_code} for {url}")
            return None
    except requests.RequestException as e:
        logger.warning(f"Request failed for {url}: {e}")
        return None


def scrape_supplementary_facts(source_id: str) -> list[dict]:
    """Attempt to scrape bordeaux.com for supplementary appellation data."""
    facts = []
    urls_to_try = [
        f"{BASE_URL}/us/our-terroir/appellations",
        f"{BASE_URL}/us/our-wines",
        f"{BASE_URL}/us/our-terroir",
    ]

    for url in urls_to_try:
        soup = fetch_page(url)
        if not soup:
            continue

        # Extract text content from main content areas
        for tag in soup.find_all(["p", "li", "h2", "h3"]):
            text = tag.get_text(strip=True)
            if not text or len(text) < 20:
                continue

            # Look for factual statements about Bordeaux wine
            text_lower = text.lower()
            bordeaux_keywords = [
                "appellation", "vineyard", "hectare", "grape", "château",
                "classification", "médoc", "graves", "pomerol", "saint-émilion",
                "merlot", "cabernet", "sémillon", "sauvignon",
            ]
            if any(kw in text_lower for kw in bordeaux_keywords):
                # Only add if it looks like a factual statement (has a verb)
                if len(text.split()) >= 6 and len(text.split()) <= 45:
                    facts.append({
                        "fact_text": text.rstrip(".") + ".",
                        "domain": "wine_regions",
                        "subdomain": "bordeaux",
                        "source_id": source_id,
                        "entities": [],
                        "tags": ["bordeaux", "scraped"],
                        "confidence": 0.8,
                    })

    logger.info(f"Scraped {len(facts)} supplementary facts from bordeaux.com")
    return facts


# ─── Fact Builders ────────────────────────────────────────────────────────────

def build_1855_facts(source_id: str) -> list[dict]:
    """Generate atomic facts for the complete 1855 Classification."""
    facts = []
    seen = set()
    commune_counts: dict[str, dict[str, int]] = {}

    for growth, chateaux in CLASSIFICATION_1855.items():
        french = GROWTH_FRENCH[growth]
        for name, commune in chateaux:
            # Fact: château classification
            key = f"1855:{name}"
            if key not in seen:
                seen.add(key)
                facts.append({
                    "fact_text": f"{name} is a {growth} ({french} Classé) in the 1855 Bordeaux Classification.",
                    "domain": "wine_regions",
                    "subdomain": "classifications",
                    "source_id": source_id,
                    "entities": [
                        {"type": "producer", "name": name},
                        {"type": "classification", "name": "1855 Bordeaux Classification"},
                    ],
                    "tags": ["1855_classification", growth.lower().replace(" ", "_"), "bordeaux"],
                    "confidence": 1.0,
                })

            # Fact: château commune/appellation
            key2 = f"1855_commune:{name}:{commune}"
            if key2 not in seen:
                seen.add(key2)
                facts.append({
                    "fact_text": f"{name} is located in the {commune} appellation.",
                    "domain": "wine_regions",
                    "subdomain": "classifications",
                    "source_id": source_id,
                    "entities": [
                        {"type": "producer", "name": name},
                        {"type": "appellation", "name": commune},
                    ],
                    "tags": ["1855_classification", "location", "bordeaux"],
                    "confidence": 1.0,
                })

            # Track counts per commune per growth
            commune_counts.setdefault(commune, Counter())[growth] += 1

    # Aggregate facts per commune
    for commune, growth_counter in commune_counts.items():
        total = sum(growth_counter.values())
        facts.append({
            "fact_text": f"The {commune} appellation has {total} classified growths in the 1855 Classification.",
            "domain": "wine_regions",
            "subdomain": "classifications",
            "source_id": source_id,
            "entities": [{"type": "appellation", "name": commune}],
            "tags": ["1855_classification", "aggregate", "bordeaux"],
            "confidence": 1.0,
        })
        for growth_name, cnt in growth_counter.items():
            if cnt > 1:
                facts.append({
                    "fact_text": f"{commune} has {cnt} {growth_name} estates in the 1855 Classification.",
                    "domain": "wine_regions",
                    "subdomain": "classifications",
                    "source_id": source_id,
                    "entities": [{"type": "appellation", "name": commune}],
                    "tags": ["1855_classification", "aggregate", "bordeaux"],
                    "confidence": 1.0,
                })

    # Growth-level summary facts
    for growth, chateaux in CLASSIFICATION_1855.items():
        facts.append({
            "fact_text": f"There are {len(chateaux)} estates classified as {growth} in the 1855 Bordeaux Classification.",
            "domain": "wine_regions",
            "subdomain": "classifications",
            "source_id": source_id,
            "entities": [{"type": "classification", "name": "1855 Bordeaux Classification"}],
            "tags": ["1855_classification", "aggregate", "bordeaux"],
            "confidence": 1.0,
        })

    # Special historical fact about Mouton Rothschild
    facts.append({
        "fact_text": "Château Mouton Rothschild was elevated from Second Growth to First Growth in 1973.",
        "domain": "wine_regions",
        "subdomain": "classifications",
        "source_id": source_id,
        "entities": [{"type": "producer", "name": "Château Mouton Rothschild"}],
        "tags": ["1855_classification", "history", "bordeaux"],
        "confidence": 1.0,
    })

    logger.info(f"Built {len(facts)} facts from 1855 Classification")
    return facts


def build_saint_emilion_facts(source_id: str) -> list[dict]:
    """Generate atomic facts for the Saint-Émilion Classification."""
    facts = []

    for level, chateaux in SAINT_EMILION_CLASSIFICATION.items():
        for name in chateaux:
            facts.append({
                "fact_text": f"{name} holds the rank of {level} in the Saint-Émilion Classification.",
                "domain": "wine_regions",
                "subdomain": "classifications",
                "source_id": source_id,
                "entities": [
                    {"type": "producer", "name": name},
                    {"type": "classification", "name": "Saint-Émilion Classification"},
                ],
                "tags": ["saint_emilion_classification", "bordeaux"],
                "confidence": 1.0,
            })

        facts.append({
            "fact_text": f"There are {len(chateaux)} estates ranked as {level} in the Saint-Émilion Classification.",
            "domain": "wine_regions",
            "subdomain": "classifications",
            "source_id": source_id,
            "entities": [{"type": "classification", "name": "Saint-Émilion Classification"}],
            "tags": ["saint_emilion_classification", "aggregate", "bordeaux"],
            "confidence": 1.0,
        })

    # General Saint-Émilion classification facts
    total = sum(len(v) for v in SAINT_EMILION_CLASSIFICATION.values())
    facts.append({
        "fact_text": f"The Saint-Émilion Classification includes {total} Premier Grand Cru Classé estates.",
        "domain": "wine_regions",
        "subdomain": "classifications",
        "source_id": source_id,
        "entities": [{"type": "classification", "name": "Saint-Émilion Classification"}],
        "tags": ["saint_emilion_classification", "aggregate", "bordeaux"],
        "confidence": 1.0,
    })

    logger.info(f"Built {len(facts)} facts from Saint-Émilion Classification")
    return facts


def build_graves_facts(source_id: str) -> list[dict]:
    """Generate atomic facts for the Graves/Pessac-Léognan Classification."""
    facts = []
    all_estates = set()
    location_seen = set()

    for color, estates in GRAVES_CLASSIFICATION.items():
        for name, commune in estates:
            all_estates.add(name)
            color_label = "red" if color == "red" else "white"
            facts.append({
                "fact_text": f"{name} is a Cru Classé de Graves for {color_label} wine.",
                "domain": "wine_regions",
                "subdomain": "classifications",
                "source_id": source_id,
                "entities": [
                    {"type": "producer", "name": name},
                    {"type": "classification", "name": "Graves Classification"},
                ],
                "tags": ["graves_classification", color_label, "bordeaux"],
                "confidence": 1.0,
            })

            # Avoid duplicate location facts for estates classified in both colors
            if name not in location_seen:
                location_seen.add(name)
                facts.append({
                    "fact_text": f"{name} is located in the commune of {commune} within Pessac-Léognan.",
                    "domain": "wine_regions",
                    "subdomain": "classifications",
                    "source_id": source_id,
                    "entities": [
                        {"type": "producer", "name": name},
                        {"type": "appellation", "name": "Pessac-Léognan"},
                    ],
                    "tags": ["graves_classification", "location", "bordeaux"],
                    "confidence": 1.0,
                })

    # Both-color estates
    red_names = {n for n, _ in GRAVES_CLASSIFICATION["red"]}
    white_names = {n for n, _ in GRAVES_CLASSIFICATION["white"]}
    both = red_names & white_names
    for name in both:
        facts.append({
            "fact_text": f"{name} is classified in the Graves Classification for both red and white wines.",
            "domain": "wine_regions",
            "subdomain": "classifications",
            "source_id": source_id,
            "entities": [{"type": "producer", "name": name}],
            "tags": ["graves_classification", "bordeaux"],
            "confidence": 1.0,
        })

    # Summary
    facts.append({
        "fact_text": f"The Graves Classification includes {len(all_estates)} distinct estates.",
        "domain": "wine_regions",
        "subdomain": "classifications",
        "source_id": source_id,
        "entities": [{"type": "classification", "name": "Graves Classification"}],
        "tags": ["graves_classification", "aggregate", "bordeaux"],
        "confidence": 1.0,
    })
    facts.append({
        "fact_text": f"There are {len(GRAVES_CLASSIFICATION['red'])} estates classified for red wine in the Graves Classification.",
        "domain": "wine_regions",
        "subdomain": "classifications",
        "source_id": source_id,
        "entities": [{"type": "classification", "name": "Graves Classification"}],
        "tags": ["graves_classification", "aggregate", "bordeaux"],
        "confidence": 1.0,
    })
    facts.append({
        "fact_text": f"There are {len(GRAVES_CLASSIFICATION['white'])} estates classified for white wine in the Graves Classification.",
        "domain": "wine_regions",
        "subdomain": "classifications",
        "source_id": source_id,
        "entities": [{"type": "classification", "name": "Graves Classification"}],
        "tags": ["graves_classification", "aggregate", "bordeaux"],
        "confidence": 1.0,
    })

    logger.info(f"Built {len(facts)} facts from Graves Classification")
    return facts


def build_appellation_facts(source_id: str) -> list[dict]:
    """Generate atomic facts for Bordeaux appellations."""
    facts = []

    for _group, appellation_list in APPELLATIONS.items():
        for entry in appellation_list:
            name, level, parent, bank, colors, note = entry

            # Fact: appellation exists and its level
            facts.append({
                "fact_text": f"{name} AOC is a {level} appellation in the Bordeaux wine region.",
                "domain": "wine_regions",
                "subdomain": "appellations",
                "source_id": source_id,
                "entities": [{"type": "appellation", "name": name}],
                "tags": ["appellation", "bordeaux", level],
                "confidence": 1.0,
            })

            # Fact: hierarchy
            if level == "communal" and parent:
                facts.append({
                    "fact_text": f"{name} is a communal appellation within the {parent} area.",
                    "domain": "wine_regions",
                    "subdomain": "appellations",
                    "source_id": source_id,
                    "entities": [
                        {"type": "appellation", "name": name},
                        {"type": "region", "name": parent},
                    ],
                    "tags": ["appellation", "hierarchy", "bordeaux"],
                    "confidence": 1.0,
                })

            # Fact: bank
            if bank:
                facts.append({
                    "fact_text": f"{name} AOC is situated on the {bank} of Bordeaux.",
                    "domain": "wine_regions",
                    "subdomain": "appellations",
                    "source_id": source_id,
                    "entities": [{"type": "appellation", "name": name}],
                    "tags": ["appellation", bank.lower().replace(" ", "_"), "bordeaux"],
                    "confidence": 1.0,
                })

            # Fact: permitted wine colors
            if colors:
                color_str = ", ".join(colors)
                facts.append({
                    "fact_text": f"{name} AOC produces {color_str} wines.",
                    "domain": "wine_regions",
                    "subdomain": "appellations",
                    "source_id": source_id,
                    "entities": [{"type": "appellation", "name": name}],
                    "tags": ["appellation", "production", "bordeaux"],
                    "confidence": 1.0,
                })

            # Fact: descriptive note
            if note:
                facts.append({
                    "fact_text": note,
                    "domain": "wine_regions",
                    "subdomain": "appellations",
                    "source_id": source_id,
                    "entities": [{"type": "appellation", "name": name}],
                    "tags": ["appellation", "description", "bordeaux"],
                    "confidence": 1.0,
                })

    logger.info(f"Built {len(facts)} facts from appellations")
    return facts


def build_grape_facts(source_id: str) -> list[dict]:
    """Generate atomic facts for key Bordeaux grape varieties."""
    facts = []

    for grape_name, info in GRAPE_VARIETIES.items():
        for fact_text in info["facts"]:
            entities = [{"type": "grape", "name": grape_name}]
            tags = ["grape", info["color"], "bordeaux"]
            if info.get("bank"):
                tags.append(info["bank"].lower().replace(" ", "_"))

            facts.append({
                "fact_text": fact_text,
                "domain": "grape_varieties",
                "subdomain": "bordeaux",
                "source_id": source_id,
                "entities": entities,
                "tags": tags,
                "confidence": 1.0,
            })

    logger.info(f"Built {len(facts)} facts from grape varieties")
    return facts


def build_general_facts(source_id: str) -> list[dict]:
    """Generate general Bordeaux region facts."""
    facts = []

    for fact_text in GENERAL_FACTS:
        facts.append({
            "fact_text": fact_text,
            "domain": "wine_regions",
            "subdomain": "bordeaux",
            "source_id": source_id,
            "entities": [{"type": "region", "name": "Bordeaux"}],
            "tags": ["bordeaux", "general"],
            "confidence": 1.0,
        })

    logger.info(f"Built {len(facts)} general Bordeaux facts")
    return facts


def build_production_rule_facts(source_id: str) -> list[dict]:
    """Generate facts about production rules per appellation."""
    facts = []

    for appellation, fact_text in PRODUCTION_RULES:
        facts.append({
            "fact_text": fact_text,
            "domain": "wine_regions",
            "subdomain": "production_rules",
            "source_id": source_id,
            "entities": [{"type": "appellation", "name": appellation}],
            "tags": ["production_rules", "regulation", "bordeaux"],
            "confidence": 1.0,
        })

    logger.info(f"Built {len(facts)} production rule facts")
    return facts


# ─── Validation ───────────────────────────────────────────────────────────────

def validate_facts(facts: list[dict]) -> None:
    """Run quality checks on generated facts and print report."""
    click.echo("\n" + "=" * 70)
    click.echo("BORDEAUX SCRAPER — VALIDATION REPORT")
    click.echo("=" * 70)

    # (a) Domain/subdomain distribution
    domain_counts = Counter()
    subdomain_counts = Counter()
    for f in facts:
        domain_counts[f["domain"]] += 1
        sd = f.get("subdomain") or "(none)"
        subdomain_counts[f"{f['domain']}/{sd}"] += 1

    click.echo(f"\nTotal facts: {len(facts)}")
    click.echo("\n--- Domain Distribution ---")
    for domain, cnt in domain_counts.most_common():
        click.echo(f"  {domain:30s}  {cnt:>5d}")

    click.echo("\n--- Subdomain Distribution ---")
    for sd, cnt in subdomain_counts.most_common():
        click.echo(f"  {sd:40s}  {cnt:>5d}")

    # (b) Short/long facts
    short_facts = [f for f in facts if len(f["fact_text"].split()) < 5]
    long_facts = [f for f in facts if len(f["fact_text"].split()) > 50]

    click.echo(f"\n--- Length Checks ---")
    click.echo(f"  Short facts (<5 words): {len(short_facts)}")
    for f in short_facts[:5]:
        click.echo(f"    WARNING: \"{f['fact_text']}\"")
    click.echo(f"  Long facts (>50 words):  {len(long_facts)}")
    for f in long_facts[:5]:
        click.echo(f"    WARNING: \"{f['fact_text'][:80]}...\"")

    # (c) Facts that are just entity names (no predicate)
    bare_entities = []
    for f in facts:
        text = f["fact_text"].rstrip(".")
        words = text.split()
        if len(words) <= 3:
            bare_entities.append(f)
    click.echo(f"\n  Bare entity facts (<=3 words): {len(bare_entities)}")
    for f in bare_entities[:5]:
        click.echo(f"    WARNING: \"{f['fact_text']}\"")

    # (d) Duplicate-ish facts (string containment)
    texts = [f["fact_text"] for f in facts]
    near_dupes = []
    for i in range(len(texts)):
        for j in range(i + 1, min(i + 50, len(texts))):
            if texts[i] in texts[j] or texts[j] in texts[i]:
                if texts[i] != texts[j]:
                    near_dupes.append((texts[i][:60], texts[j][:60]))
    exact_dupes = len(texts) - len(set(texts))
    click.echo(f"\n--- Duplicate Checks ---")
    click.echo(f"  Exact duplicates:    {exact_dupes}")
    click.echo(f"  Near-duplicates:     {len(near_dupes)}")
    for a, b in near_dupes[:5]:
        click.echo(f"    \"{a}...\"")
        click.echo(f"    \"{b}...\"")

    # (e) Entity population
    with_entities = sum(1 for f in facts if f.get("entities") and len(f["entities"]) > 0)
    click.echo(f"\n--- Entity Population ---")
    click.echo(f"  Facts with entities: {with_entities}/{len(facts)} ({100*with_entities/len(facts):.1f}%)")
    click.echo(f"  Facts without:       {len(facts) - with_entities}")

    # (f) Random sample
    click.echo(f"\n--- Random Sample (10 facts) ---")
    sample = random.sample(facts, min(10, len(facts)))
    for i, f in enumerate(sample, 1):
        click.echo(f"  {i:2d}. [{f['domain']}/{f.get('subdomain', '')}] {f['fact_text']}")

    # 1855 Classification verification
    click.echo(f"\n" + "=" * 70)
    click.echo("1855 CLASSIFICATION VERIFICATION")
    click.echo("=" * 70)

    total_1855 = sum(len(v) for v in CLASSIFICATION_1855.values())
    click.echo(f"\nTotal châteaux in 1855 Classification: {total_1855}")
    assert total_1855 == 61, f"FAIL: Expected 61, got {total_1855}"
    click.echo("PASS: 61 châteaux confirmed.")

    # Print grouped by growth
    for growth, chateaux in CLASSIFICATION_1855.items():
        click.echo(f"\n  {growth} ({len(chateaux)} estates):")
        for name, commune in chateaux:
            click.echo(f"    - {name} ({commune})")

    # Verify 5 First Growths
    first_growths = [n for n, _ in CLASSIFICATION_1855["First Growth"]]
    expected_firsts = {
        "Château Lafite Rothschild",
        "Château Latour",
        "Château Margaux",
        "Château Haut-Brion",
        "Château Mouton Rothschild",
    }
    if set(first_growths) == expected_firsts:
        click.echo("\nPASS: All 5 First Growths verified.")
    else:
        missing = expected_firsts - set(first_growths)
        extra = set(first_growths) - expected_firsts
        click.echo(f"\nFAIL: First Growths mismatch. Missing: {missing}, Extra: {extra}")

    click.echo(f"\n{'=' * 70}\n")


# ─── Main Pipeline ────────────────────────────────────────────────────────────

SECTIONS = {
    "1855_classification": {
        "description": "1855 Médoc Classification — 61 châteaux across 5 growths",
        "builder": build_1855_facts,
    },
    "saint_emilion": {
        "description": "Saint-Émilion Classification — Premier Grand Cru Classé A & B",
        "builder": build_saint_emilion_facts,
    },
    "graves": {
        "description": "Graves/Pessac-Léognan Classification (1953/1959)",
        "builder": build_graves_facts,
    },
    "appellations": {
        "description": "Bordeaux appellations — hierarchy, colors, descriptions",
        "builder": build_appellation_facts,
    },
    "grapes": {
        "description": "Key Bordeaux grape varieties",
        "builder": build_grape_facts,
    },
    "general": {
        "description": "General Bordeaux regional facts",
        "builder": build_general_facts,
    },
    "production_rules": {
        "description": "Production rules per appellation",
        "builder": build_production_rule_facts,
    },
}


def collect_all_facts(source_id: str, scrape: bool = True) -> list[dict]:
    """Build all facts from embedded data and optional scraping."""
    all_facts = []

    for section_name, config in SECTIONS.items():
        logger.info(f"Building facts for: {section_name}")
        section_facts = config["builder"](source_id)
        all_facts.extend(section_facts)

    if scrape:
        logger.info("Checking robots.txt...")
        robots = check_robots_txt()
        if robots["status"] == "ok":
            logger.info(f"robots.txt disallowed paths: {len(robots['disallowed'])}")

        logger.info("Scraping supplementary facts from bordeaux.com...")
        supplementary = scrape_supplementary_facts(source_id)
        # Deduplicate against existing facts
        existing_texts = {f["fact_text"] for f in all_facts}
        new_supplementary = [f for f in supplementary if f["fact_text"] not in existing_texts]
        all_facts.extend(new_supplementary)
        logger.info(f"Added {len(new_supplementary)} unique supplementary facts from scraping")

    logger.info(f"Total facts collected: {len(all_facts)}")
    return all_facts


# ─── Test Run ────────────────────────────────────────────────────────────────


def _print_test_report(
    category_stats: dict[str, dict],
    all_facts: list[dict],
    all_inserted_ids: list[str],
) -> None:
    """Print the structured test-run report with quality checks and warnings."""
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


def run_test(cleanup: bool = False) -> None:
    """Run a limited test extraction: 5 items per category, insert, report."""
    # Register source (real insert)
    source_id = ensure_source(
        name=SOURCE_NAME,
        url=SOURCE_URL,
        source_type=SOURCE_TYPE,
        tier=SOURCE_TIER,
    )

    category_stats = {}
    all_facts_collected = []
    all_inserted_ids = []

    # Process each section with a limit of TEST_RUN_LIMIT items
    for section_name, config in SECTIONS.items():
        section_facts = config["builder"](source_id)

        # Limit to TEST_RUN_LIMIT facts per section
        limited_facts = section_facts[:TEST_RUN_LIMIT]

        # Insert individually to track IDs
        inserted_count = 0
        for fact in limited_facts:
            fact_id = insert_fact(
                fact_text=fact["fact_text"],
                domain=fact["domain"],
                source_id=fact["source_id"],
                subdomain=fact.get("subdomain"),
                entities=fact.get("entities"),
                confidence=fact.get("confidence", 1.0),
                tags=fact.get("tags"),
            )
            if fact_id:
                all_inserted_ids.append(fact_id)
                inserted_count += 1

        all_facts_collected.extend(limited_facts)
        category_stats[section_name] = {
            "items_processed": len(limited_facts),
            "facts_generated": len(limited_facts),
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


# ─── CLI ──────────────────────────────────────────────────────────────────────

@click.command()
@click.option("--all", "run_all", is_flag=True, help="Run full extraction and insert into database")
@click.option("--list", "list_sections", is_flag=True, help="List available data sections")
@click.option("--dry-run", "dry_run", is_flag=True, help="Collect facts but don't insert into database")
@click.option("--validate", "validate", is_flag=True, help="Run quality checks on generated facts")
@click.option("--section", "-s", type=str, help="Run a specific section only")
@click.option("--no-scrape", is_flag=True, help="Skip web scraping, use only embedded data")
@click.option("--test-run", is_flag=True, help="Process 5 items per category, insert, and report")
@click.option("--cleanup", is_flag=True, help="With --test-run, delete inserted facts after reporting")
def main(
    run_all: bool,
    list_sections: bool,
    dry_run: bool,
    validate: bool,
    section: Optional[str],
    no_scrape: bool,
    test_run: bool,
    cleanup: bool,
):
    """OenoBench Bordeaux Scraper — Extract Bordeaux wine knowledge from CIVB."""
    logger.add("data/logs/bordeaux_{time}.log", rotation="10 MB")

    if list_sections:
        click.echo("\nAvailable sections:")
        for name, config in SECTIONS.items():
            click.echo(f"  {name:25s} — {config['description']}")
        return

    if validate:
        # Use a dummy source_id for validation (no DB needed)
        facts = collect_all_facts(source_id="validation-dummy", scrape=False)
        validate_facts(facts)
        return

    if test_run:
        run_test(cleanup=cleanup)
        return

    if dry_run:
        facts = collect_all_facts(source_id="dry-run-dummy", scrape=not no_scrape)
        click.echo(f"\n[DRY RUN] Would insert {len(facts)} facts.")

        # Print summary by section
        domain_counts = Counter()
        for f in facts:
            sd = f.get("subdomain") or "(none)"
            domain_counts[f"{f['domain']}/{sd}"] += 1

        click.echo("\nFact distribution:")
        for sd, cnt in domain_counts.most_common():
            click.echo(f"  {sd:40s}  {cnt:>5d}")

        click.echo(f"\n  {'TOTAL':40s}  {len(facts):>5d}")

        # Print 5 sample facts
        click.echo("\nSample facts:")
        for f in random.sample(facts, min(5, len(facts))):
            click.echo(f"  - {f['fact_text']}")
        return

    if run_all or section:
        # Register source
        source_id = ensure_source(
            name=SOURCE_NAME,
            url=SOURCE_URL,
            source_type=SOURCE_TYPE,
            tier=SOURCE_TIER,
        )
        logger.info(f"Source registered: {SOURCE_NAME} (id={source_id})")

        if section:
            if section not in SECTIONS:
                click.echo(f"Unknown section: {section}. Use --list to see options.")
                return
            facts = SECTIONS[section]["builder"](source_id)
        else:
            facts = collect_all_facts(source_id, scrape=not no_scrape)

        # Insert into database
        inserted = insert_facts_batch(facts)
        click.echo(f"\nInserted {inserted} new facts ({len(facts)} total, duplicates skipped).")
        click.echo(f"Total facts in database: {get_fact_count()}")
        return

    click.echo("Use --all to run full extraction, --dry-run to preview, or --validate for quality checks.")
    click.echo("Use --list to see available sections.")
    click.echo("Use --test-run to process 5 items per category and report (add --cleanup to remove test data).")


if __name__ == "__main__":
    main()
