"""
OenoBench — Burgundy (BIVB) Scraper

Extracts Burgundy wine knowledge from the BIVB website (bourgogne-wines.com).
Covers all 84 appellations, 33 Grand Crus, Premier Cru vineyards, grape
varieties, communes, and the regional hierarchy.

Usage:
    python -m src.scrapers.burgundy --all
    python -m src.scrapers.burgundy --dry-run
    python -m src.scrapers.burgundy --list
    python -m src.scrapers.burgundy --validate
    python -m src.scrapers.burgundy --test-run
    python -m src.scrapers.burgundy --test-run --cleanup
"""

import random
import re
import time
from collections import Counter, defaultdict
from typing import Optional

import click
import requests
from bs4 import BeautifulSoup
from loguru import logger

from src.utils.facts import ensure_source, insert_facts_batch, get_fact_count

# ─── Configuration ────────────────────────────────────────────────────────────

BASE_URL = "https://www.bourgogne-wines.com"
USER_AGENT = "OenoBench-Research/1.0 (academic wine benchmark)"
REQUEST_DELAY = 5  # seconds between HTTP requests
SOURCE_NAME = "BIVB (Bourgogne Wines)"
SOURCE_TIER = "tier_2_authoritative"

# ─── Authoritative Burgundy Appellation Data ─────────────────────────────────
#
# Curated from BIVB official data. The BIVB website often blocks automated
# access, so we embed the canonical appellation reference here. When the site
# is accessible, the scraper supplements this with live page content.

# The 33 Grand Cru appellations of Burgundy
GRAND_CRUS = [
    # Chablis
    {"name": "Chablis Grand Cru", "commune": "Chablis", "sub_region": "Chablis",
     "color": ["white"], "grapes": ["Chardonnay"],
     "climats": ["Blanchot", "Bougros", "Les Clos", "Grenouilles", "Preuses", "Valmur", "Vaudésir"]},
    # Côte de Nuits
    {"name": "Chambertin", "commune": "Gevrey-Chambertin", "sub_region": "Côte de Nuits",
     "color": ["red"], "grapes": ["Pinot Noir"], "area_ha": 12.9},
    {"name": "Chambertin-Clos de Bèze", "commune": "Gevrey-Chambertin", "sub_region": "Côte de Nuits",
     "color": ["red"], "grapes": ["Pinot Noir"], "area_ha": 15.39},
    {"name": "Chapelle-Chambertin", "commune": "Gevrey-Chambertin", "sub_region": "Côte de Nuits",
     "color": ["red"], "grapes": ["Pinot Noir"], "area_ha": 5.49},
    {"name": "Charmes-Chambertin", "commune": "Gevrey-Chambertin", "sub_region": "Côte de Nuits",
     "color": ["red"], "grapes": ["Pinot Noir"], "area_ha": 30.66},
    {"name": "Griotte-Chambertin", "commune": "Gevrey-Chambertin", "sub_region": "Côte de Nuits",
     "color": ["red"], "grapes": ["Pinot Noir"], "area_ha": 2.69},
    {"name": "Latricières-Chambertin", "commune": "Gevrey-Chambertin", "sub_region": "Côte de Nuits",
     "color": ["red"], "grapes": ["Pinot Noir"], "area_ha": 7.35},
    {"name": "Mazis-Chambertin", "commune": "Gevrey-Chambertin", "sub_region": "Côte de Nuits",
     "color": ["red"], "grapes": ["Pinot Noir"], "area_ha": 9.1},
    {"name": "Mazoyères-Chambertin", "commune": "Gevrey-Chambertin", "sub_region": "Côte de Nuits",
     "color": ["red"], "grapes": ["Pinot Noir"], "area_ha": 18.59},
    {"name": "Ruchottes-Chambertin", "commune": "Gevrey-Chambertin", "sub_region": "Côte de Nuits",
     "color": ["red"], "grapes": ["Pinot Noir"], "area_ha": 3.3},
    {"name": "Clos de Vougeot", "commune": "Vougeot", "sub_region": "Côte de Nuits",
     "color": ["red"], "grapes": ["Pinot Noir"], "area_ha": 50.59},
    {"name": "Échézeaux", "commune": "Flagey-Échézeaux", "sub_region": "Côte de Nuits",
     "color": ["red"], "grapes": ["Pinot Noir"], "area_ha": 37.69},
    {"name": "Grands Échézeaux", "commune": "Flagey-Échézeaux", "sub_region": "Côte de Nuits",
     "color": ["red"], "grapes": ["Pinot Noir"], "area_ha": 9.14},
    {"name": "Richebourg", "commune": "Vosne-Romanée", "sub_region": "Côte de Nuits",
     "color": ["red"], "grapes": ["Pinot Noir"], "area_ha": 8.03},
    {"name": "Romanée-Conti", "commune": "Vosne-Romanée", "sub_region": "Côte de Nuits",
     "color": ["red"], "grapes": ["Pinot Noir"], "area_ha": 1.81},
    {"name": "Romanée-Saint-Vivant", "commune": "Vosne-Romanée", "sub_region": "Côte de Nuits",
     "color": ["red"], "grapes": ["Pinot Noir"], "area_ha": 9.44},
    {"name": "La Romanée", "commune": "Vosne-Romanée", "sub_region": "Côte de Nuits",
     "color": ["red"], "grapes": ["Pinot Noir"], "area_ha": 0.85},
    {"name": "La Tâche", "commune": "Vosne-Romanée", "sub_region": "Côte de Nuits",
     "color": ["red"], "grapes": ["Pinot Noir"], "area_ha": 6.06},
    {"name": "La Grande Rue", "commune": "Vosne-Romanée", "sub_region": "Côte de Nuits",
     "color": ["red"], "grapes": ["Pinot Noir"], "area_ha": 1.65},
    {"name": "Bonnes-Mares", "commune": "Chambolle-Musigny", "sub_region": "Côte de Nuits",
     "color": ["red"], "grapes": ["Pinot Noir"], "area_ha": 15.06},
    {"name": "Musigny", "commune": "Chambolle-Musigny", "sub_region": "Côte de Nuits",
     "color": ["red", "white"], "grapes": ["Pinot Noir", "Chardonnay"], "area_ha": 10.86},
    {"name": "Clos de la Roche", "commune": "Morey-Saint-Denis", "sub_region": "Côte de Nuits",
     "color": ["red"], "grapes": ["Pinot Noir"], "area_ha": 16.9},
    {"name": "Clos Saint-Denis", "commune": "Morey-Saint-Denis", "sub_region": "Côte de Nuits",
     "color": ["red"], "grapes": ["Pinot Noir"], "area_ha": 6.62},
    {"name": "Clos de Tart", "commune": "Morey-Saint-Denis", "sub_region": "Côte de Nuits",
     "color": ["red"], "grapes": ["Pinot Noir"], "area_ha": 7.53},
    {"name": "Clos des Lambrays", "commune": "Morey-Saint-Denis", "sub_region": "Côte de Nuits",
     "color": ["red"], "grapes": ["Pinot Noir"], "area_ha": 8.84},
    # Côte de Beaune
    {"name": "Corton", "commune": "Aloxe-Corton", "sub_region": "Côte de Beaune",
     "color": ["red", "white"], "grapes": ["Pinot Noir", "Chardonnay"], "area_ha": 97.5},
    {"name": "Corton-Charlemagne", "commune": "Aloxe-Corton", "sub_region": "Côte de Beaune",
     "color": ["white"], "grapes": ["Chardonnay"], "area_ha": 52.08},
    {"name": "Charlemagne", "commune": "Aloxe-Corton", "sub_region": "Côte de Beaune",
     "color": ["white"], "grapes": ["Chardonnay"], "area_ha": 0.28},
    {"name": "Montrachet", "commune": "Puligny-Montrachet", "sub_region": "Côte de Beaune",
     "color": ["white"], "grapes": ["Chardonnay"], "area_ha": 7.99},
    {"name": "Bâtard-Montrachet", "commune": "Puligny-Montrachet", "sub_region": "Côte de Beaune",
     "color": ["white"], "grapes": ["Chardonnay"], "area_ha": 11.87},
    {"name": "Chevalier-Montrachet", "commune": "Puligny-Montrachet", "sub_region": "Côte de Beaune",
     "color": ["white"], "grapes": ["Chardonnay"], "area_ha": 7.36},
    {"name": "Criots-Bâtard-Montrachet", "commune": "Chassagne-Montrachet", "sub_region": "Côte de Beaune",
     "color": ["white"], "grapes": ["Chardonnay"], "area_ha": 1.57},
    {"name": "Bienvenues-Bâtard-Montrachet", "commune": "Puligny-Montrachet", "sub_region": "Côte de Beaune",
     "color": ["white"], "grapes": ["Chardonnay"], "area_ha": 3.69},
]

# Village / Commune appellations and their Premier Cru vineyards
VILLAGE_APPELLATIONS = {
    # Chablis & Grand Auxerrois
    "Chablis": {
        "sub_region": "Chablis",
        "colors": ["white"],
        "grapes": ["Chardonnay"],
        "premier_crus": [
            "Mont de Milieu", "Montée de Tonnerre", "Fourchaume", "Vaillons",
            "Montmains", "Côte de Léchet", "Beauroy", "Vau de Vey", "Vau-Ligneau",
            "Vosgros", "Les Fourneaux", "Mélinots", "Butteaux", "Chapelot",
            "Côte de Fontenay", "Les Lys", "Séché", "Homme Mort",
            "Pied d'Aloup", "Vaucoupin", "Les Beauregards", "Chaume de Talvat",
            "Côte de Jouan", "Les Épinottes", "Troesmes", "Les Forêts",
            "Morein", "Roncieres", "Berdiot", "Côte de Prés-Girots",
            "Côte de Vaubarousse", "Beugnons", "Chatains", "Roncières",
            "Les Landes et Verjuts", "Vau de Vey", "Côte de Cuissy",
            "Vaux Ragons", "L'Ardillier", "Les Grands Crus",
        ],
    },
    # Côte de Nuits
    "Gevrey-Chambertin": {
        "sub_region": "Côte de Nuits",
        "colors": ["red"],
        "grapes": ["Pinot Noir"],
        "premier_crus": [
            "Les Cazetiers", "Clos Saint-Jacques", "Lavaux Saint-Jacques",
            "Estournelles-Saint-Jacques", "Combes au Moine", "Poissenot",
            "Champeaux", "Les Goulots", "Issarts", "Les Corbeaux",
            "Bel Air", "La Perrière", "Petite Chapelle", "Clos du Chapitre",
            "En Ergot", "Craipillot", "Champonnets", "Au Closeau",
            "Cherbaudes", "Petits Cazetiers", "La Romanée", "Les Champonnet",
            "Fonteny", "Champonnet", "Le Clos Prieur",
            "Clos Prieur",
        ],
    },
    "Morey-Saint-Denis": {
        "sub_region": "Côte de Nuits",
        "colors": ["red", "white"],
        "grapes": ["Pinot Noir", "Chardonnay"],
        "premier_crus": [
            "Les Ruchots", "Les Sorbets", "Clos Sorbé", "Les Millandes",
            "Le Village", "Les Faconnières", "Les Genavrières", "Les Chaffots",
            "Aux Charmes", "Côte Rôtie", "Les Blanchards", "La Riotte",
            "Les Gruenchers", "Les Monts Luisants", "Clos Baulet",
            "Les Charrières", "La Bussière", "Aux Cheseaux", "Maison Brûlée",
            "Clos des Ormes",
        ],
    },
    "Chambolle-Musigny": {
        "sub_region": "Côte de Nuits",
        "colors": ["red"],
        "grapes": ["Pinot Noir"],
        "premier_crus": [
            "Les Amoureuses", "Les Charmes", "Les Cras", "Les Baudes",
            "Les Plantes", "Les Hauts Doix", "Les Chatelots", "Les Groseilles",
            "Les Fuées", "Les Lavrottes", "Derrière la Grange", "Les Noirots",
            "Les Sentiers", "Les Feusselottes", "Aux Beaux Bruns",
            "Les Borniques", "Les Gruenchers", "Aux Combottes",
            "Les Combottes", "Aux Échanges", "Les Carrières",
            "Les Véroilles", "Les Chabiottes",
        ],
    },
    "Vougeot": {
        "sub_region": "Côte de Nuits",
        "colors": ["red", "white"],
        "grapes": ["Pinot Noir", "Chardonnay"],
        "premier_crus": [
            "Le Clos Blanc de Vougeot", "Les Petits Vougeots", "Les Cras",
            "Clos de la Perrière",
        ],
    },
    "Vosne-Romanée": {
        "sub_region": "Côte de Nuits",
        "colors": ["red"],
        "grapes": ["Pinot Noir"],
        "premier_crus": [
            "Les Suchots", "Aux Malconsorts", "Les Beaux Monts", "Les Brûlées",
            "Cros Parantoux", "Les Chaumes", "Aux Reignots", "Les Gaudichots",
            "Les Petits Monts", "En Orveaux", "Les Rouges",
            "La Croix Rameau", "Au-dessus des Malconsorts",
        ],
    },
    "Nuits-Saint-Georges": {
        "sub_region": "Côte de Nuits",
        "colors": ["red", "white"],
        "grapes": ["Pinot Noir", "Chardonnay"],
        "premier_crus": [
            "Les Saint-Georges", "Les Vaucrains", "Les Cailles", "Les Porêts-Saint-Georges",
            "Les Pruliers", "Les Hauts Pruliers", "Aux Murgers", "La Richemone",
            "Les Chaignots", "Les Damodes", "Aux Boudots", "Aux Cras",
            "Les Perrières", "Roncière", "Rue de Chaux", "Aux Thorey",
            "Aux Vignerondes", "Les Terres Blanches", "Les Vallerots",
            "Les Poulettes", "Chaînes Carteaux", "Les Crots", "Les Procès",
            "Les Argillats", "Clos de la Maréchale", "Clos des Porêts-Saint-Georges",
            "Clos des Corvées", "Clos des Grandes Vignes", "Clos des Argillières",
            "Clos des Forêts Saint-Georges", "Clos de l'Arlot", "Clos Saint-Marc",
            "Aux Champs Perdrix", "Les Corvées-Paget", "Les Didiers",
            "Les Grandes Vignes",
        ],
    },
    "Fixin": {
        "sub_region": "Côte de Nuits",
        "colors": ["red", "white"],
        "grapes": ["Pinot Noir", "Chardonnay"],
        "premier_crus": [
            "Clos de la Perrière", "Clos du Chapitre", "Les Arvelets",
            "Clos Napoléon", "Les Hervelets", "En Suchot",
        ],
    },
    "Marsannay": {
        "sub_region": "Côte de Nuits",
        "colors": ["red", "white", "rosé"],
        "grapes": ["Pinot Noir", "Chardonnay"],
        "premier_crus": [],
    },
    # Côte de Beaune
    "Aloxe-Corton": {
        "sub_region": "Côte de Beaune",
        "colors": ["red", "white"],
        "grapes": ["Pinot Noir", "Chardonnay"],
        "premier_crus": [
            "Les Maréchaudes", "Les Paulands", "Les Vercots", "Les Chaillots",
            "Les Fournières", "Les Guérets", "Les Valozières", "Les Moutotes",
            "Clos du Chapitre", "Les Brunettes et Planchots", "La Coutière",
            "La Toppe au Vert", "Les Petites Folières",
        ],
    },
    "Pernand-Vergelesses": {
        "sub_region": "Côte de Beaune",
        "colors": ["red", "white"],
        "grapes": ["Pinot Noir", "Chardonnay"],
        "premier_crus": [
            "Île des Vergelesses", "Les Fichots", "En Caradeux",
            "Les Basses Vergelesses", "Creux de la Net",
        ],
    },
    "Savigny-lès-Beaune": {
        "sub_region": "Côte de Beaune",
        "colors": ["red", "white"],
        "grapes": ["Pinot Noir", "Chardonnay"],
        "premier_crus": [
            "Les Lavières", "Aux Vergelesses", "Les Marconnets",
            "Aux Guettes", "Les Narbantons", "Les Peuillets",
            "Aux Serpentières", "Les Dominodes", "Les Jarrons",
            "Aux Gravains", "Les Talmettes", "Les Charnières",
            "Aux Fourneaux", "Aux Clous", "Aux Grands Liards",
            "Les Rouvrettes", "Les Hauts Marconnets", "Petits Godeaux",
            "Redrescul", "Les Hauts Jarrons", "Basses Vergelesses",
        ],
    },
    "Beaune": {
        "sub_region": "Côte de Beaune",
        "colors": ["red", "white"],
        "grapes": ["Pinot Noir", "Chardonnay"],
        "premier_crus": [
            "Les Grèves", "Les Teurons", "Clos des Mouches", "Les Bressandes",
            "Les Marconnets", "Les Fèves", "Les Cent Vignes", "Les Cras",
            "Clos du Roi", "Les Vignes Franches", "En l'Orme",
            "Les Toussaints", "Les Avaux", "Sur les Grèves",
            "Aux Coucherias", "Champs Pimont", "Les Aigrots",
            "Les Sizies", "A l'Écu", "Les Reversées", "Les Sceaux",
            "Les Épenottes", "Pertuisots", "Tiélandry",
            "Les Boucherottes", "Blanches Fleurs", "Les Montrevenots",
            "Les Tuvilains", "Sur les Grèves - Clos Sainte-Anne",
            "Les Chouacheux", "En Genêt", "Les Seurey",
            "Clos de la Mousse", "Belissand", "Clos des Ursules",
        ],
    },
    "Pommard": {
        "sub_region": "Côte de Beaune",
        "colors": ["red"],
        "grapes": ["Pinot Noir"],
        "premier_crus": [
            "Les Rugiens", "Les Épenots", "Les Grands Épenots",
            "Les Petits Épenots", "Clos de la Commaraine",
            "Les Pézerolles", "Les Boucherottes", "Les Saussilles",
            "Les Croix Noires", "Les Arvelets", "Les Chanlins",
            "Les Fremiers", "Les Bertins", "Les Poutures",
            "Les Chaponnières", "Les Jarollières", "Les Combes Dessus",
            "La Refène", "Clos Micot", "En Largillière",
            "Le Village", "Les Charmots", "Derrière Saint-Jean",
            "La Platière", "Les Rugiens-Bas", "Les Rugiens-Hauts",
            "Clos Blanc", "Clos du Verger",
        ],
    },
    "Volnay": {
        "sub_region": "Côte de Beaune",
        "colors": ["red"],
        "grapes": ["Pinot Noir"],
        "premier_crus": [
            "Clos des Ducs", "Taillepieds", "Caillerets", "En Champans",
            "Les Chevrets", "Fremiet", "Les Mitans", "En l'Ormeau",
            "Clos de la Bousse-d'Or", "Les Angles", "Pitures Dessus",
            "Santenots", "Les Brouillards", "La Gigotte", "Clos de l'Audignac",
            "Les Lurets", "Robardelle", "Les Aussy", "Chanlin",
            "Clos de la Chapelle", "Carelle sous la Chapelle",
            "Ronceret", "Clos de la Cave des Ducs",
            "Les Grands Champs", "Le Village",
        ],
    },
    "Meursault": {
        "sub_region": "Côte de Beaune",
        "colors": ["red", "white"],
        "grapes": ["Pinot Noir", "Chardonnay"],
        "premier_crus": [
            "Les Perrières", "Les Charmes", "Les Genevrières",
            "Le Porusot", "Les Bouchères", "Les Gouttes d'Or",
            "Sous le Dos d'Âne", "La Pièce sous le Bois", "Sous Blagny",
            "Les Cras", "Les Santenots Blancs", "Les Santenots du Milieu",
            "Les Plures", "Les Ravelles", "Clos des Perrières",
            "Les Perrières Dessous", "Les Perrières Dessus",
            "Les Charmes Dessus", "Les Charmes Dessous",
            "Les Genevrières Dessus", "Les Genevrières Dessous",
        ],
    },
    "Puligny-Montrachet": {
        "sub_region": "Côte de Beaune",
        "colors": ["red", "white"],
        "grapes": ["Pinot Noir", "Chardonnay"],
        "premier_crus": [
            "Les Pucelles", "Les Combettes", "Les Folatières",
            "Clavoillon", "Le Cailleret", "Les Demoiselles",
            "Les Chalumaux", "Champ Canet", "Hameau de Blagny",
            "Sous le Puits", "La Garenne", "Les Referts",
            "Champ Gain", "La Truffière", "Les Perrières",
            "Clos de la Garenne",
        ],
    },
    "Chassagne-Montrachet": {
        "sub_region": "Côte de Beaune",
        "colors": ["red", "white"],
        "grapes": ["Pinot Noir", "Chardonnay"],
        "premier_crus": [
            "Les Grandes Ruchottes", "Les Ruchottes", "La Romanée",
            "Les Embrazées", "Les Caillerets", "Clos Saint-Jean",
            "Morgeot", "La Maltroie", "Les Chenevottes",
            "Les Champs Gain", "Les Vergers", "Les Macherelles",
            "En Remilly", "La Boudriotte", "Les Baudines",
            "Les Bondues", "Blanchot Dessus", "Tête du Clos",
            "Abbaye de Morgeot", "La Chapelle", "Les Fairendes",
            "Ez Crets", "Vigne Blanche", "Clos Pitois",
        ],
    },
    "Saint-Aubin": {
        "sub_region": "Côte de Beaune",
        "colors": ["red", "white"],
        "grapes": ["Pinot Noir", "Chardonnay"],
        "premier_crus": [
            "Les Murgers des Dents de Chien", "En Remilly", "La Chatenière",
            "Les Combes au Sud", "Sur le Sentier du Clou",
            "Les Champlots", "Sur Gamay", "Bas de Vermarain à l'Est",
            "Les Cortons", "Les Frionnes", "En Montceau",
            "Derrière chez Édouard", "Les Perrières",
            "Sous Roche Dumay", "Le Charmois", "En Créot",
            "Pitangeret", "Le Bas de Gamay à l'Est",
            "Marinot", "Vignes Moingeon", "Derrière la Tour",
            "Ez Duresses", "Les Travers de Marinot",
        ],
    },
    "Santenay": {
        "sub_region": "Côte de Beaune",
        "colors": ["red", "white"],
        "grapes": ["Pinot Noir", "Chardonnay"],
        "premier_crus": [
            "Les Gravières", "Clos de Tavannes", "La Comme",
            "Beauregard", "La Maladière", "Le Passe Temps",
            "Grand Clos Rousseau", "Clos Faubard", "Beaurepaire",
            "Clos des Mouches",
        ],
    },
    "Maranges": {
        "sub_region": "Côte de Beaune",
        "colors": ["red", "white"],
        "grapes": ["Pinot Noir", "Chardonnay"],
        "premier_crus": [
            "Clos de la Boutière", "La Fussière", "Le Clos des Rois",
            "Les Clos Roussots", "Le Croix Moines", "La Croix aux Moines",
        ],
    },
    "Ladoix": {
        "sub_region": "Côte de Beaune",
        "colors": ["red", "white"],
        "grapes": ["Pinot Noir", "Chardonnay"],
        "premier_crus": [
            "La Micaude", "La Corvée", "Le Clou d'Orge",
            "Les Joyeuses", "Bois Roussot", "Basses Mourottes",
            "Hautes Mourottes",
        ],
    },
    "Chorey-lès-Beaune": {
        "sub_region": "Côte de Beaune",
        "colors": ["red", "white"],
        "grapes": ["Pinot Noir", "Chardonnay"],
        "premier_crus": [],
    },
    "Monthélie": {
        "sub_region": "Côte de Beaune",
        "colors": ["red", "white"],
        "grapes": ["Pinot Noir", "Chardonnay"],
        "premier_crus": [
            "Sur la Velle", "Les Vignes Rondes", "Le Meix Bataille",
            "Les Riottes", "La Taupine", "Le Clos Gauthey",
            "Le Château Gaillard", "Les Champs Fulliot",
            "Le Village", "Les Duresses", "Clos du Meix Garnier",
        ],
    },
    "Auxey-Duresses": {
        "sub_region": "Côte de Beaune",
        "colors": ["red", "white"],
        "grapes": ["Pinot Noir", "Chardonnay"],
        "premier_crus": [
            "Les Duresses", "Clos du Val", "Les Bréterins",
            "Les Grands Champs", "Reugne", "Les Écusseaux",
            "Bas des Duresses", "La Chapelle", "Climat du Val",
        ],
    },
    "Blagny": {
        "sub_region": "Côte de Beaune",
        "colors": ["red"],
        "grapes": ["Pinot Noir"],
        "premier_crus": [
            "La Pièce sous le Bois", "Sous le Dos d'Âne",
            "Sous Blagny", "Sous le Puits",
        ],
    },
    # Côte Chalonnaise
    "Mercurey": {
        "sub_region": "Côte Chalonnaise",
        "colors": ["red", "white"],
        "grapes": ["Pinot Noir", "Chardonnay"],
        "premier_crus": [
            "Clos des Barraults", "Clos Tonnerre", "Les Velley",
            "Clos Voyens", "Les Byots", "Les Croichots",
            "Les Combins", "Les Naugues", "Clos l'Évêque",
            "La Mission", "Les Puillets", "Les Saumonts",
            "La Bondue", "La Cailloute", "La Levrière",
            "Les Champs Martin", "Clos du Roy", "Clos Marcilly",
            "En Sazenay", "Grand Clos Fortoul", "Griffères",
            "Le Clos des Grands Voyens", "Les Vasées",
            "Les Montaigus", "Les Ruelles", "Clos des Montaigus",
            "Clos des Myglands", "Les Crêts",
        ],
    },
    "Givry": {
        "sub_region": "Côte Chalonnaise",
        "colors": ["red", "white"],
        "grapes": ["Pinot Noir", "Chardonnay"],
        "premier_crus": [
            "Clos Jus", "Clos Salomon", "Cellier aux Moines",
            "Clos Saint-Pierre", "Clos Saint-Paul",
            "Les Grandes Vignes", "Les Grands Prétans",
            "Crausot", "La Grande Berge", "Le Petit Prétan",
            "Clos de la Servoisine", "Clos du Vernoy",
            "En Choué", "La Plante", "Clos Marceaux",
            "Clos Charlé", "Les Bois Chevaux",
            "Les Grands Crus", "Les Berges", "À Vigne Rouge",
            "Clos de la Baraude",
        ],
    },
    "Rully": {
        "sub_region": "Côte Chalonnaise",
        "colors": ["red", "white"],
        "grapes": ["Pinot Noir", "Chardonnay"],
        "premier_crus": [
            "Clos Saint-Jacques", "Les Cloux", "Rabourcé",
            "La Pucelle", "Grésigny", "Vauvry",
            "Montpalais", "Meix Caillet", "Les Pierres",
            "La Bressande", "Champ Clou", "La Fosse",
            "Chapitre", "Préau", "Marissou",
            "Agneux", "Pillot", "Molesme",
            "La Renarde", "Les Margotés",
        ],
    },
    "Montagny": {
        "sub_region": "Côte Chalonnaise",
        "colors": ["white"],
        "grapes": ["Chardonnay"],
        "premier_crus": [
            "Les Coères", "Les Platières", "Les Burnins",
            "Les Las", "Les Jardins", "Les Bassets",
            "Les Vignes Derrière", "Les Resses", "Les Pidances",
            "La Grande Pièce", "Les Bonneveaux", "Les Garchères",
            "Le Vieux Château", "Montcuchot", "Les Combes",
            "Les Bouchots", "Les Vignes Longues",
            "Le Clos Chaudron", "Les Maroques",
            "Les Vignes Saint-Pierre", "Les Beaux Champs",
            "La Moullière", "Mont-Laurent",
        ],
    },
    "Bouzeron": {
        "sub_region": "Côte Chalonnaise",
        "colors": ["white"],
        "grapes": ["Aligoté"],
        "premier_crus": [],
    },
    # Mâconnais
    "Pouilly-Fuissé": {
        "sub_region": "Mâconnais",
        "colors": ["white"],
        "grapes": ["Chardonnay"],
        "premier_crus": [
            "Les Vignes Blanches", "Au Vignerais", "Aux Bouthières",
            "Aux Chailloux", "Aux Quarts", "En France",
            "La Maréchaude", "Le Clos", "Le Clos de Monsieur Noly",
            "Le Clos de Solutré", "Le Clos Reyssié", "Les Brûlés",
            "Les Chevrières", "Les Crays", "Les Ménétrières",
            "Les Perrières", "Les Reisses", "Sur la Roche",
            "Vers Cras", "Vers Pouilly",
        ],
    },
    "Pouilly-Loché": {
        "sub_region": "Mâconnais",
        "colors": ["white"],
        "grapes": ["Chardonnay"],
        "premier_crus": [],
    },
    "Pouilly-Vinzelles": {
        "sub_region": "Mâconnais",
        "colors": ["white"],
        "grapes": ["Chardonnay"],
        "premier_crus": [],
    },
    "Saint-Véran": {
        "sub_region": "Mâconnais",
        "colors": ["white"],
        "grapes": ["Chardonnay"],
        "premier_crus": [],
    },
    "Viré-Clessé": {
        "sub_region": "Mâconnais",
        "colors": ["white"],
        "grapes": ["Chardonnay"],
        "premier_crus": [],
    },
}

# Regional appellations
REGIONAL_APPELLATIONS = [
    {"name": "Bourgogne", "colors": ["red", "white", "rosé"],
     "grapes": ["Pinot Noir", "Chardonnay", "Gamay", "Aligoté"]},
    {"name": "Bourgogne Aligoté", "colors": ["white"], "grapes": ["Aligoté"]},
    {"name": "Bourgogne Passe-Tout-Grains", "colors": ["red", "rosé"],
     "grapes": ["Gamay", "Pinot Noir"]},
    {"name": "Bourgogne Hautes Côtes de Nuits", "colors": ["red", "white", "rosé"],
     "grapes": ["Pinot Noir", "Chardonnay"]},
    {"name": "Bourgogne Hautes Côtes de Beaune", "colors": ["red", "white", "rosé"],
     "grapes": ["Pinot Noir", "Chardonnay"]},
    {"name": "Bourgogne Côte d'Or", "colors": ["red", "white"],
     "grapes": ["Pinot Noir", "Chardonnay"]},
    {"name": "Bourgogne Côtes du Couchois", "colors": ["red"],
     "grapes": ["Pinot Noir"]},
    {"name": "Bourgogne Côte Chalonnaise", "colors": ["red", "white"],
     "grapes": ["Pinot Noir", "Chardonnay"]},
    {"name": "Bourgogne Côte Saint-Jacques", "colors": ["red", "white", "rosé"],
     "grapes": ["Pinot Noir", "Chardonnay"]},
    {"name": "Bourgogne Chitry", "colors": ["red", "white", "rosé"],
     "grapes": ["Pinot Noir", "Chardonnay"]},
    {"name": "Bourgogne Côtes d'Auxerre", "colors": ["red", "white", "rosé"],
     "grapes": ["Pinot Noir", "Chardonnay"]},
    {"name": "Bourgogne Coulanges-la-Vineuse", "colors": ["red", "white", "rosé"],
     "grapes": ["Pinot Noir", "Chardonnay"]},
    {"name": "Bourgogne Épineuil", "colors": ["red", "rosé"],
     "grapes": ["Pinot Noir"]},
    {"name": "Bourgogne Tonnerre", "colors": ["white"],
     "grapes": ["Chardonnay"]},
    {"name": "Crémant de Bourgogne", "colors": ["white", "rosé"],
     "grapes": ["Chardonnay", "Pinot Noir", "Aligoté", "Gamay"]},
    {"name": "Coteaux Bourguignons", "colors": ["red", "white", "rosé"],
     "grapes": ["Pinot Noir", "Gamay", "Chardonnay", "Aligoté"]},
    {"name": "Bourgogne Mousseux", "colors": ["red"], "grapes": ["Pinot Noir", "Gamay"]},
    {"name": "Mâcon", "colors": ["red", "white", "rosé"],
     "grapes": ["Chardonnay", "Gamay", "Pinot Noir"]},
    {"name": "Petit Chablis", "colors": ["white"], "grapes": ["Chardonnay"]},
    {"name": "Irancy", "colors": ["red"], "grapes": ["Pinot Noir"]},
    {"name": "Saint-Bris", "colors": ["white"], "grapes": ["Sauvignon Blanc"]},
]

# Sub-regions of Burgundy
SUB_REGIONS = {
    "Chablis": {
        "description": "the northernmost sub-region of Burgundy, known for its mineral-driven Chardonnay wines",
        "known_for": "white wines from Chardonnay",
    },
    "Côte de Nuits": {
        "description": "the northern half of the Côte d'Or, home to most of Burgundy's red Grand Crus",
        "known_for": "Pinot Noir red wines",
    },
    "Côte de Beaune": {
        "description": "the southern half of the Côte d'Or, renowned for its white Grand Crus",
        "known_for": "Chardonnay white wines and Pinot Noir reds",
    },
    "Côte Chalonnaise": {
        "description": "a sub-region south of the Côte d'Or producing value-oriented Burgundy wines",
        "known_for": "Pinot Noir and Chardonnay wines",
    },
    "Mâconnais": {
        "description": "the southernmost main sub-region of Burgundy, dominated by white wine production",
        "known_for": "Chardonnay white wines including Pouilly-Fuissé",
    },
}


# ─── HTTP Session ─────────────────────────────────────────────────────────────

def _get_session() -> requests.Session:
    """Create a requests session with appropriate headers."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,fr;q=0.8",
    })
    return session


def _fetch_page(session: requests.Session, url: str) -> Optional[BeautifulSoup]:
    """Fetch a page with rate limiting and error handling."""
    logger.debug(f"Fetching: {url}")
    time.sleep(REQUEST_DELAY)
    try:
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "lxml")
    except requests.RequestException as e:
        logger.warning(f"Failed to fetch {url}: {e}")
        return None


# ─── Live Scraping (supplements curated data) ────────────────────────────────

def _try_scrape_appellation_pages(session: requests.Session) -> list[dict]:
    """Attempt to scrape live appellation data from BIVB site.

    Returns a list of raw dicts with whatever extra info we can extract.
    Falls back gracefully if the site is unavailable.
    """
    extra_facts = []
    listing_urls = [
        f"{BASE_URL}/our-wines-our-appellations/discover-our-appellations/",
        f"{BASE_URL}/our-wines-our-appellations/our-appellations-map/",
    ]

    for url in listing_urls:
        soup = _fetch_page(session, url)
        if soup is None:
            logger.info(f"Could not access {url}, relying on curated data")
            continue

        # Try to find appellation links on the listing page
        links = soup.find_all("a", href=True)
        for link in links:
            href = link["href"]
            if "/appellation-" in href or "/our-appellations/" in href:
                full_url = href if href.startswith("http") else BASE_URL + href
                detail_soup = _fetch_page(session, full_url)
                if detail_soup:
                    text_blocks = detail_soup.find_all(["p", "li", "td"])
                    page_text = " ".join(
                        t.get_text(strip=True) for t in text_blocks
                    )
                    # Extract useful data patterns
                    _extract_facts_from_text(page_text, link.get_text(strip=True), extra_facts)

    return extra_facts


def _extract_facts_from_text(text: str, appellation_name: str, facts_out: list) -> None:
    """Extract factual statements from page text (best effort, no verbatim copy)."""
    # Look for area mentions
    area_match = re.search(r"(\d[\d,.]+)\s*(?:hectares|ha)", text, re.IGNORECASE)
    if area_match:
        area = area_match.group(1).replace(",", "")
        facts_out.append({
            "type": "area",
            "appellation": appellation_name,
            "area_ha": area,
        })

    # Look for altitude mentions
    alt_match = re.search(r"(\d+)\s*(?:to|–|-)\s*(\d+)\s*m(?:etres|eters)?", text, re.IGNORECASE)
    if alt_match:
        facts_out.append({
            "type": "altitude",
            "appellation": appellation_name,
            "low": alt_match.group(1),
            "high": alt_match.group(2),
        })

    # Look for production volume
    prod_match = re.search(r"([\d,.]+)\s*(?:hectolitres|hl)", text, re.IGNORECASE)
    if prod_match:
        facts_out.append({
            "type": "production",
            "appellation": appellation_name,
            "volume_hl": prod_match.group(1).replace(",", ""),
        })


# ─── Fact Generation ─────────────────────────────────────────────────────────

def build_all_facts(source_id: str, live_extras: Optional[list] = None) -> list[dict]:
    """Build the complete list of atomic facts from curated + live data."""
    facts = []
    seen = set()

    def _add(fact_text: str, domain: str, subdomain: str,
             entities: list, tags: list, confidence: float = 1.0):
        if fact_text in seen:
            return
        seen.add(fact_text)
        facts.append({
            "fact_text": fact_text,
            "domain": domain,
            "subdomain": subdomain,
            "source_id": source_id,
            "entities": entities,
            "confidence": confidence,
            "tags": tags,
        })

    # ── 1. Regional hierarchy facts ──────────────────────────────────────
    _add(
        "Burgundy is a major wine region in eastern France.",
        "wine_regions", "burgundy",
        [{"type": "region", "name": "Burgundy"}],
        ["region", "france", "burgundy"],
    )
    _add(
        "Burgundy has 84 appellations d'origine contrôlée (AOC).",
        "wine_regions", "burgundy",
        [{"type": "region", "name": "Burgundy"}],
        ["region", "appellation", "burgundy"],
    )
    _add(
        "Burgundy has 33 Grand Cru appellations.",
        "wine_regions", "burgundy",
        [{"type": "region", "name": "Burgundy"}],
        ["region", "grand_cru", "burgundy"],
    )
    _add(
        "The Burgundy classification hierarchy has four levels: regional, village, Premier Cru, and Grand Cru.",
        "wine_regions", "burgundy",
        [{"type": "region", "name": "Burgundy"}],
        ["region", "classification", "burgundy"],
    )
    _add(
        "Grand Cru is the highest classification level in the Burgundy appellation hierarchy.",
        "wine_regions", "burgundy",
        [{"type": "region", "name": "Burgundy"}],
        ["classification", "grand_cru", "burgundy"],
    )
    _add(
        "Premier Cru is the second-highest classification level in Burgundy.",
        "wine_regions", "burgundy",
        [{"type": "region", "name": "Burgundy"}],
        ["classification", "premier_cru", "burgundy"],
    )
    _add(
        "Burgundy wines are primarily made from Pinot Noir for reds and Chardonnay for whites.",
        "grape_varieties", "burgundy",
        [{"type": "grape", "name": "Pinot Noir"}, {"type": "grape", "name": "Chardonnay"}],
        ["grape", "burgundy"],
    )
    _add(
        "Aligoté is a white grape variety permitted in several Burgundy appellations.",
        "grape_varieties", "burgundy",
        [{"type": "grape", "name": "Aligoté"}],
        ["grape", "burgundy"],
    )
    _add(
        "Gamay is a red grape variety used in Bourgogne Passe-Tout-Grains and Coteaux Bourguignons.",
        "grape_varieties", "burgundy",
        [{"type": "grape", "name": "Gamay"}],
        ["grape", "burgundy"],
    )
    _add(
        "Sauvignon Blanc is permitted in the Saint-Bris appellation in Burgundy.",
        "grape_varieties", "burgundy",
        [{"type": "grape", "name": "Sauvignon Blanc"}, {"type": "appellation", "name": "Saint-Bris"}],
        ["grape", "burgundy", "saint-bris"],
    )
    _add(
        "Burgundy's vineyard classification system is based on the concept of terroir and climat.",
        "wine_regions", "burgundy",
        [{"type": "region", "name": "Burgundy"}],
        ["terroir", "classification", "burgundy"],
    )
    _add(
        "A climat in Burgundy refers to a precisely delimited vineyard parcel with its own name and terroir characteristics.",
        "viticulture", "burgundy",
        [{"type": "region", "name": "Burgundy"}],
        ["terroir", "climat", "burgundy"],
    )
    _add(
        "Burgundy's climats were inscribed as a UNESCO World Heritage Site in 2015.",
        "wine_regions", "burgundy",
        [{"type": "region", "name": "Burgundy"}],
        ["unesco", "heritage", "burgundy"],
    )
    _add(
        "The Côte d'Or in Burgundy is divided into the Côte de Nuits in the north and the Côte de Beaune in the south.",
        "wine_regions", "burgundy",
        [{"type": "region", "name": "Côte d'Or"},
         {"type": "region", "name": "Côte de Nuits"},
         {"type": "region", "name": "Côte de Beaune"}],
        ["region", "burgundy", "cote_dor"],
    )

    # ── 2. Sub-region facts ──────────────────────────────────────────────
    for sr_name, sr_info in SUB_REGIONS.items():
        _add(
            f"{sr_name} is {sr_info['description']}.",
            "wine_regions", "burgundy",
            [{"type": "region", "name": sr_name}],
            ["region", "sub_region", "burgundy"],
        )
        _add(
            f"{sr_name} is primarily known for {sr_info['known_for']}.",
            "wine_regions", "burgundy",
            [{"type": "region", "name": sr_name}],
            ["region", "sub_region", "burgundy"],
        )

    # ── 3. Grand Cru facts ───────────────────────────────────────────────
    # Count Grand Crus per commune
    gc_per_commune = Counter()
    for gc in GRAND_CRUS:
        gc_per_commune[gc["commune"]] += 1

    for gc in GRAND_CRUS:
        name = gc["name"]
        commune = gc["commune"]
        sub_region = gc["sub_region"]
        colors = gc["color"]
        grapes = gc["grapes"]

        entities = [
            {"type": "appellation", "name": name},
            {"type": "commune", "name": commune},
        ]

        # Basic identity fact
        _add(
            f"{name} is a Grand Cru appellation in {commune}, Burgundy.",
            "wine_regions", "burgundy",
            entities,
            ["grand_cru", "appellation", "burgundy"],
        )

        # Sub-region
        _add(
            f"{name} Grand Cru is located in the {sub_region} sub-region of Burgundy.",
            "wine_regions", "burgundy",
            [{"type": "appellation", "name": name}, {"type": "region", "name": sub_region}],
            ["grand_cru", "region", "burgundy"],
        )

        # Color
        if len(colors) == 1:
            color_str = colors[0]
            _add(
                f"{name} is a Grand Cru producing exclusively {color_str} wine.",
                "wine_regions", "burgundy",
                [{"type": "appellation", "name": name}],
                ["grand_cru", color_str, "burgundy"],
            )
        else:
            color_str = " and ".join(colors)
            _add(
                f"{name} Grand Cru produces both {color_str} wines.",
                "wine_regions", "burgundy",
                [{"type": "appellation", "name": name}],
                ["grand_cru", "burgundy"],
            )

        # Grape varieties
        if len(grapes) == 1:
            _add(
                f"{name} Grand Cru is made exclusively from {grapes[0]}.",
                "grape_varieties", "burgundy",
                [{"type": "appellation", "name": name}, {"type": "grape", "name": grapes[0]}],
                ["grand_cru", "grape", "burgundy"],
            )
        else:
            grape_str = " and ".join(grapes)
            _add(
                f"{name} Grand Cru permits {grape_str}.",
                "grape_varieties", "burgundy",
                [{"type": "appellation", "name": name}] +
                [{"type": "grape", "name": g} for g in grapes],
                ["grand_cru", "grape", "burgundy"],
            )

        # Area if available
        if "area_ha" in gc:
            _add(
                f"{name} Grand Cru covers {gc['area_ha']} hectares.",
                "wine_regions", "burgundy",
                [{"type": "appellation", "name": name}],
                ["grand_cru", "area", "burgundy"],
            )

        # Climats for Chablis Grand Cru
        if "climats" in gc:
            for climat in gc["climats"]:
                _add(
                    f"{climat} is one of the seven climats of {name}.",
                    "wine_regions", "burgundy",
                    [{"type": "vineyard", "name": climat}, {"type": "appellation", "name": name}],
                    ["grand_cru", "climat", "chablis", "burgundy"],
                )

    # Grand Crus per commune summary facts
    for commune, count in gc_per_commune.items():
        if count > 1:
            _add(
                f"{commune} has {count} Grand Cru vineyards.",
                "wine_regions", "burgundy",
                [{"type": "commune", "name": commune}],
                ["grand_cru", "commune", "burgundy"],
            )

    # ── 4. Village / Commune appellation facts ───────────────────────────
    for village, info in VILLAGE_APPELLATIONS.items():
        sub_region = info["sub_region"]
        colors = info["colors"]
        grapes = info["grapes"]
        premier_crus = info["premier_crus"]

        entities = [
            {"type": "commune", "name": village},
            {"type": "region", "name": sub_region},
        ]

        # Commune identity
        _add(
            f"{village} is a commune appellation in the {sub_region} sub-region of Burgundy.",
            "wine_regions", "burgundy",
            entities,
            ["commune", "appellation", "burgundy"],
        )

        # Color production
        if len(colors) == 1:
            _add(
                f"{village} produces exclusively {colors[0]} wines.",
                "wine_regions", "burgundy",
                [{"type": "commune", "name": village}],
                ["commune", colors[0], "burgundy"],
            )
        elif "rosé" in colors:
            color_str = ", ".join(colors[:-1]) + ", and " + colors[-1]
            _add(
                f"{village} produces {color_str} wines.",
                "wine_regions", "burgundy",
                [{"type": "commune", "name": village}],
                ["commune", "burgundy"],
            )
        else:
            color_str = " and ".join(colors)
            _add(
                f"{village} produces {color_str} wines.",
                "wine_regions", "burgundy",
                [{"type": "commune", "name": village}],
                ["commune", "burgundy"],
            )

        # Grape varieties
        if len(grapes) == 1:
            _add(
                f"The {village} appellation is made exclusively from {grapes[0]}.",
                "grape_varieties", "burgundy",
                [{"type": "commune", "name": village}, {"type": "grape", "name": grapes[0]}],
                ["commune", "grape", "burgundy"],
            )
        else:
            grape_str = " and ".join(grapes)
            _add(
                f"The {village} appellation permits {grape_str}.",
                "grape_varieties", "burgundy",
                [{"type": "commune", "name": village}] +
                [{"type": "grape", "name": g} for g in grapes],
                ["commune", "grape", "burgundy"],
            )

        # Premier Cru count
        if premier_crus:
            _add(
                f"{village} has {len(premier_crus)} Premier Cru vineyard sites.",
                "wine_regions", "burgundy",
                [{"type": "commune", "name": village}],
                ["commune", "premier_cru", "burgundy"],
            )

            # Individual Premier Cru facts
            for pc in premier_crus:
                _add(
                    f"{pc} is a Premier Cru vineyard in {village}, Burgundy.",
                    "wine_regions", "burgundy",
                    [{"type": "vineyard", "name": pc}, {"type": "commune", "name": village}],
                    ["premier_cru", "vineyard", "burgundy"],
                )
        else:
            _add(
                f"{village} does not have any designated Premier Cru vineyards.",
                "wine_regions", "burgundy",
                [{"type": "commune", "name": village}],
                ["commune", "burgundy"],
            )

    # Special Marsannay fact
    _add(
        "Marsannay is the only commune appellation in the Côte de Nuits that produces red, white, and rosé wines.",
        "wine_regions", "burgundy",
        [{"type": "commune", "name": "Marsannay"}],
        ["commune", "marsannay", "burgundy"],
    )

    # Bouzeron / Aligoté special fact
    _add(
        "Bouzeron is the only commune appellation in Burgundy dedicated exclusively to the Aligoté grape.",
        "wine_regions", "burgundy",
        [{"type": "commune", "name": "Bouzeron"}, {"type": "grape", "name": "Aligoté"}],
        ["commune", "grape", "bouzeron", "burgundy"],
    )

    # Meursault character
    _add(
        "Meursault is a commune in the Côte de Beaune known for white wines.",
        "wine_regions", "burgundy",
        [{"type": "commune", "name": "Meursault"}],
        ["commune", "white", "burgundy"],
    )

    # ── 5. Regional appellation facts ────────────────────────────────────
    for ra in REGIONAL_APPELLATIONS:
        name = ra["name"]
        colors = ra["colors"]
        grapes = ra["grapes"]

        entities = [{"type": "appellation", "name": name}]

        # Identity
        _add(
            f"{name} is a regional appellation in Burgundy.",
            "wine_regions", "burgundy",
            entities,
            ["regional", "appellation", "burgundy"],
        )

        # Colors
        if len(colors) == 1:
            _add(
                f"{name} produces exclusively {colors[0]} wine.",
                "wine_regions", "burgundy",
                entities,
                ["regional", colors[0], "burgundy"],
            )
        else:
            if len(colors) == 2:
                color_str = " and ".join(colors)
            else:
                color_str = ", ".join(colors[:-1]) + ", and " + colors[-1]
            _add(
                f"{name} produces {color_str} wines.",
                "wine_regions", "burgundy",
                entities,
                ["regional", "burgundy"],
            )

        # Grape varieties
        if len(grapes) == 1:
            _add(
                f"{name} is made exclusively from {grapes[0]}.",
                "grape_varieties", "burgundy",
                entities + [{"type": "grape", "name": grapes[0]}],
                ["regional", "grape", "burgundy"],
            )
        else:
            grape_str = ", ".join(grapes[:-1]) + ", and " + grapes[-1] if len(grapes) > 2 else " and ".join(grapes)
            _add(
                f"The {name} appellation permits {grape_str}.",
                "grape_varieties", "burgundy",
                entities + [{"type": "grape", "name": g} for g in grapes],
                ["regional", "grape", "burgundy"],
            )

    # ── 6. Notable specific facts ────────────────────────────────────────
    notable_facts = [
        ("Romanée-Conti is a Grand Cru vineyard in Vosne-Romanée, Burgundy.",
         "wine_regions", [{"type": "vineyard", "name": "Romanée-Conti"}, {"type": "commune", "name": "Vosne-Romanée"}],
         ["grand_cru", "famous", "burgundy"]),
        ("Romanée-Conti is the smallest Grand Cru in Vosne-Romanée at 1.81 hectares.",
         "wine_regions", [{"type": "vineyard", "name": "Romanée-Conti"}],
         ["grand_cru", "area", "burgundy"]),
        ("La Romanée is the smallest Grand Cru appellation in Burgundy at 0.85 hectares.",
         "wine_regions", [{"type": "appellation", "name": "La Romanée"}],
         ["grand_cru", "area", "burgundy"]),
        ("Clos de Vougeot is one of the largest Grand Cru vineyards in Burgundy at 50.59 hectares.",
         "wine_regions", [{"type": "vineyard", "name": "Clos de Vougeot"}],
         ["grand_cru", "area", "burgundy"]),
        ("Corton is the largest Grand Cru appellation in Burgundy by area.",
         "wine_regions", [{"type": "appellation", "name": "Corton"}],
         ["grand_cru", "area", "burgundy"]),
        ("Musigny is one of only two Grand Crus in the Côte de Nuits that can produce white wine.",
         "wine_regions", [{"type": "appellation", "name": "Musigny"}],
         ["grand_cru", "white", "burgundy"]),
        ("Corton is the only Grand Cru in the Côte de Beaune that produces red wine.",
         "wine_regions", [{"type": "appellation", "name": "Corton"}],
         ["grand_cru", "red", "burgundy"]),
        ("Bourgogne Passe-Tout-Grains must contain at least one-third Pinot Noir blended with Gamay.",
         "winemaking", [{"type": "appellation", "name": "Bourgogne Passe-Tout-Grains"},
                        {"type": "grape", "name": "Pinot Noir"}, {"type": "grape", "name": "Gamay"}],
         ["regulation", "blending", "burgundy"]),
        ("Crémant de Bourgogne is a sparkling wine produced using the traditional method.",
         "winemaking", [{"type": "appellation", "name": "Crémant de Bourgogne"}],
         ["sparkling", "winemaking", "burgundy"]),
        ("Chablis wines are produced on Kimmeridgian limestone soils containing fossilized oyster shells.",
         "viticulture", [{"type": "region", "name": "Chablis"}],
         ["terroir", "soil", "chablis", "burgundy"]),
        ("The Côte de Nuits is approximately 20 kilometers long and 200 to 300 meters wide.",
         "wine_regions", [{"type": "region", "name": "Côte de Nuits"}],
         ["region", "geography", "burgundy"]),
        ("Burgundy vineyards are generally planted at densities of 10,000 vines per hectare or higher.",
         "viticulture", [{"type": "region", "name": "Burgundy"}],
         ["viticulture", "planting", "burgundy"]),
        ("Gevrey-Chambertin is the largest commune appellation in the Côte de Nuits.",
         "wine_regions", [{"type": "commune", "name": "Gevrey-Chambertin"}],
         ["commune", "burgundy"]),
        ("Beaune is the wine capital of Burgundy and hosts the annual Hospices de Beaune wine auction.",
         "wine_business", [{"type": "commune", "name": "Beaune"}],
         ["commune", "wine_business", "burgundy"]),
        ("The Hospices de Beaune wine auction, held annually since 1859, is one of the most famous wine charity auctions in the world.",
         "wine_business", [{"type": "commune", "name": "Beaune"}],
         ["wine_business", "auction", "burgundy"]),
        ("Pouilly-Fuissé was elevated to include Premier Cru climats in 2020, effective with the 2020 vintage.",
         "wine_regions", [{"type": "appellation", "name": "Pouilly-Fuissé"}],
         ["appellation", "premier_cru", "maconnais", "burgundy"]),
        ("Charmes-Chambertin is the largest Grand Cru appellation in Gevrey-Chambertin.",
         "wine_regions", [{"type": "appellation", "name": "Charmes-Chambertin"},
                          {"type": "commune", "name": "Gevrey-Chambertin"}],
         ["grand_cru", "burgundy"]),
        ("Wines labeled as Chambertin-Clos de Bèze may also be sold as Chambertin, but not vice versa.",
         "wine_regions", [{"type": "appellation", "name": "Chambertin-Clos de Bèze"},
                          {"type": "appellation", "name": "Chambertin"}],
         ["grand_cru", "regulation", "burgundy"]),
        ("Mazoyères-Chambertin wines may alternatively be labeled as Charmes-Chambertin.",
         "wine_regions", [{"type": "appellation", "name": "Mazoyères-Chambertin"},
                          {"type": "appellation", "name": "Charmes-Chambertin"}],
         ["grand_cru", "regulation", "burgundy"]),
        ("The BIVB (Bureau Interprofessionnel des Vins de Bourgogne) is the official trade body for Burgundy wines.",
         "wine_business", [{"type": "organization", "name": "BIVB"}],
         ["wine_business", "organization", "burgundy"]),
        ("Clos de Tart is a Grand Cru monopole in Morey-Saint-Denis, wholly owned by a single proprietor.",
         "wine_regions", [{"type": "appellation", "name": "Clos de Tart"},
                          {"type": "commune", "name": "Morey-Saint-Denis"}],
         ["grand_cru", "monopole", "burgundy"]),
        ("La Grande Rue is a Grand Cru monopole in Vosne-Romanée, promoted from Premier Cru status in 1992.",
         "wine_regions", [{"type": "appellation", "name": "La Grande Rue"},
                          {"type": "commune", "name": "Vosne-Romanée"}],
         ["grand_cru", "monopole", "burgundy"]),
        ("Les Amoureuses is widely considered the most prestigious Premier Cru vineyard in Chambolle-Musigny.",
         "wine_regions", [{"type": "vineyard", "name": "Les Amoureuses"},
                          {"type": "commune", "name": "Chambolle-Musigny"}],
         ["premier_cru", "burgundy"]),
        ("Clos Saint-Jacques is one of the most renowned Premier Cru vineyards in Gevrey-Chambertin.",
         "wine_regions", [{"type": "vineyard", "name": "Clos Saint-Jacques"},
                          {"type": "commune", "name": "Gevrey-Chambertin"}],
         ["premier_cru", "burgundy"]),
        ("Montrachet is widely regarded as one of the greatest white wine vineyards in the world.",
         "wine_regions", [{"type": "appellation", "name": "Montrachet"}],
         ["grand_cru", "white", "burgundy"]),
        ("The Montrachet Grand Cru vineyard straddles the communes of Puligny-Montrachet and Chassagne-Montrachet.",
         "wine_regions", [{"type": "appellation", "name": "Montrachet"},
                          {"type": "commune", "name": "Puligny-Montrachet"},
                          {"type": "commune", "name": "Chassagne-Montrachet"}],
         ["grand_cru", "geography", "burgundy"]),
        ("Corton Grand Cru vineyards extend across the communes of Aloxe-Corton, Ladoix-Serrigny, and Pernand-Vergelesses.",
         "wine_regions", [{"type": "appellation", "name": "Corton"},
                          {"type": "commune", "name": "Aloxe-Corton"},
                          {"type": "commune", "name": "Ladoix-Serrigny"},
                          {"type": "commune", "name": "Pernand-Vergelesses"}],
         ["grand_cru", "geography", "burgundy"]),
        ("Bonnes-Mares Grand Cru vineyard spans both Chambolle-Musigny and Morey-Saint-Denis.",
         "wine_regions", [{"type": "appellation", "name": "Bonnes-Mares"},
                          {"type": "commune", "name": "Chambolle-Musigny"},
                          {"type": "commune", "name": "Morey-Saint-Denis"}],
         ["grand_cru", "geography", "burgundy"]),
        ("Pinot Noir is the dominant red grape variety of Burgundy, accounting for the vast majority of red wine production.",
         "grape_varieties", [{"type": "grape", "name": "Pinot Noir"}, {"type": "region", "name": "Burgundy"}],
         ["grape", "burgundy"]),
        ("Chardonnay is the dominant white grape variety of Burgundy.",
         "grape_varieties", [{"type": "grape", "name": "Chardonnay"}, {"type": "region", "name": "Burgundy"}],
         ["grape", "burgundy"]),
        ("Cros Parantoux is a celebrated Premier Cru vineyard in Vosne-Romanée made famous by Henri Jayer.",
         "wine_regions", [{"type": "vineyard", "name": "Cros Parantoux"},
                          {"type": "commune", "name": "Vosne-Romanée"},
                          {"type": "producer", "name": "Henri Jayer"}],
         ["premier_cru", "famous", "burgundy"]),
        ("Saint-Bris is the only Burgundy appellation where Sauvignon Blanc is the primary grape variety.",
         "wine_regions", [{"type": "appellation", "name": "Saint-Bris"}, {"type": "grape", "name": "Sauvignon Blanc"}],
         ["appellation", "grape", "burgundy"]),
        ("Irancy is a village appellation in the Auxerrois area producing red wines primarily from Pinot Noir.",
         "wine_regions", [{"type": "appellation", "name": "Irancy"}, {"type": "grape", "name": "Pinot Noir"}],
         ["appellation", "burgundy"]),
    ]

    for fact_text, domain, entities, tags in notable_facts:
        _add(fact_text, domain, "burgundy", entities, tags)

    # ── 7. Integrate any live-scraped extra data ─────────────────────────
    if live_extras:
        for extra in live_extras:
            if extra["type"] == "area":
                _add(
                    f"The {extra['appellation']} appellation covers approximately {extra['area_ha']} hectares.",
                    "wine_regions", "burgundy",
                    [{"type": "appellation", "name": extra["appellation"]}],
                    ["appellation", "area", "burgundy"],
                    confidence=0.9,
                )
            elif extra["type"] == "altitude":
                _add(
                    f"The {extra['appellation']} vineyards are situated at elevations between {extra['low']} and {extra['high']} meters.",
                    "viticulture", "burgundy",
                    [{"type": "appellation", "name": extra["appellation"]}],
                    ["appellation", "altitude", "burgundy"],
                    confidence=0.9,
                )
            elif extra["type"] == "production":
                _add(
                    f"The {extra['appellation']} appellation produces approximately {extra['volume_hl']} hectolitres annually.",
                    "wine_business", "burgundy",
                    [{"type": "appellation", "name": extra["appellation"]}],
                    ["appellation", "production", "burgundy"],
                    confidence=0.9,
                )

    return facts


# ─── Validation ───────────────────────────────────────────────────────────────

def validate_facts(facts: list[dict]) -> None:
    """Run quality checks on generated facts and print a report."""
    click.echo("\n" + "=" * 70)
    click.echo("BURGUNDY SCRAPER — VALIDATION REPORT")
    click.echo("=" * 70)

    # (a) Domain / subdomain distribution
    domain_counts = Counter()
    subdomain_counts = Counter()
    for f in facts:
        domain_counts[f["domain"]] += 1
        sd = f.get("subdomain", "none")
        subdomain_counts[f"{f['domain']}/{sd}"] += 1

    click.echo(f"\nTotal facts: {len(facts)}")
    click.echo("\nDomain distribution:")
    for domain, cnt in domain_counts.most_common():
        click.echo(f"  {domain:30s}  {cnt:5d}  ({100*cnt/len(facts):5.1f}%)")

    click.echo("\nSubdomain distribution:")
    for sd, cnt in subdomain_counts.most_common(15):
        click.echo(f"  {sd:40s}  {cnt:5d}")

    # (b) Suspiciously short / long facts
    short_facts = [f for f in facts if len(f["fact_text"].split()) < 5]
    long_facts = [f for f in facts if len(f["fact_text"].split()) > 50]

    click.echo(f"\nShort facts (<5 words): {len(short_facts)}")
    for f in short_facts[:5]:
        click.echo(f"  ⚠ {f['fact_text']}")

    click.echo(f"\nLong facts (>50 words): {len(long_facts)}")
    for f in long_facts[:5]:
        click.echo(f"  ⚠ {f['fact_text'][:100]}...")

    # (c) Facts that are just entity names with no predicate
    no_predicate = []
    for f in facts:
        text = f["fact_text"].rstrip(".")
        words = text.split()
        if len(words) <= 2:
            no_predicate.append(f)
    click.echo(f"\nFacts without predicates (<=2 words): {len(no_predicate)}")
    for f in no_predicate[:5]:
        click.echo(f"  ⚠ {f['fact_text']}")

    # (d) Duplicate-ish facts (string containment)
    duplicateish = []
    fact_texts = [f["fact_text"] for f in facts]
    # Sample-based check to avoid O(n^2) for large sets
    sample_size = min(200, len(fact_texts))
    sampled = random.sample(range(len(fact_texts)), sample_size)
    for i in sampled:
        for j in range(len(fact_texts)):
            if i != j and len(fact_texts[i]) > 20 and fact_texts[i] in fact_texts[j]:
                duplicateish.append((fact_texts[i], fact_texts[j]))
                break
    click.echo(f"\nPotential near-duplicates (containment): {len(duplicateish)}")
    for a, b in duplicateish[:5]:
        click.echo(f"  ⚠ \"{a[:60]}\" ⊂ \"{b[:60]}\"")

    # (e) Entity population rate
    with_entities = sum(1 for f in facts if f.get("entities"))
    without_entities = len(facts) - with_entities
    click.echo(f"\nFacts with entities: {with_entities} ({100*with_entities/len(facts):.1f}%)")
    click.echo(f"Facts without entities: {without_entities} ({100*without_entities/len(facts):.1f}%)")

    # (f) Random sample
    click.echo("\n10 random sample facts:")
    for f in random.sample(facts, min(10, len(facts))):
        entities_str = ", ".join(e["name"] for e in f.get("entities", []))
        click.echo(f"  [{f['domain']:20s}] {f['fact_text']}")
        if entities_str:
            click.echo(f"    entities: {entities_str}")

    # Grand Cru verification
    click.echo("\n" + "-" * 70)
    click.echo("GRAND CRU VERIFICATION")
    click.echo("-" * 70)
    gc_names = [gc["name"] for gc in GRAND_CRUS]
    click.echo(f"Grand Crus in dataset: {len(gc_names)}")
    if len(gc_names) == 33:
        click.echo("✓ All 33 Grand Cru appellations present.")
    else:
        click.echo(f"✗ Expected 33 Grand Crus, found {len(gc_names)}. Check data!")

    click.echo("\nComplete Grand Cru list:")
    for i, name in enumerate(gc_names, 1):
        commune = GRAND_CRUS[i - 1]["commune"]
        click.echo(f"  {i:2d}. {name:35s}  ({commune})")

    click.echo("\n" + "=" * 70)


# ─── Test Run ─────────────────────────────────────────────────────────────────

TEST_RUN_LIMIT = 5  # items per category


def _insert_facts_tracked(facts: list[dict]) -> tuple[int, list[str]]:
    """Insert facts and return (inserted_count, list_of_inserted_fact_ids).

    Wraps insert_facts_batch by querying back for inserted IDs.
    """
    if not facts:
        return 0, []

    fact_texts = [f["fact_text"] for f in facts]
    inserted_count = insert_facts_batch(facts)

    from src.utils.db import get_pg
    conn = get_pg()
    cur = conn.cursor()
    inserted_ids = []
    for text in fact_texts:
        cur.execute("SELECT id FROM facts WHERE fact_text = %s", (text,))
        row = cur.fetchone()
        if row:
            inserted_ids.append(str(row["id"]))

    return inserted_count, inserted_ids


def _cleanup_test_facts(fact_ids: list[str]) -> int:
    """Delete facts by their IDs. Returns count deleted."""
    if not fact_ids:
        return 0

    from src.utils.db import get_pg
    pg = get_pg()
    cur = pg.cursor()
    cur.execute("DELETE FROM facts WHERE id = ANY(%s::uuid[])", (fact_ids,))
    deleted = cur.rowcount
    pg.commit()
    return deleted


def _print_test_report(
    category_stats: dict[str, dict],
    all_facts: list[dict],
    all_inserted_ids: list[str],
) -> None:
    """Print the structured test-run report with quality checks."""
    click.echo("\n=== TEST RUN REPORT ===")
    click.echo("")

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

    if not warnings:
        click.echo(f"\n  No warnings — all checks passed.")


def run_test(cleanup: bool = False) -> None:
    """Run a limited test extraction: 5 items per category, insert, report."""
    source_id = ensure_source(
        name=SOURCE_NAME,
        url=BASE_URL,
        source_type="official_body",
        tier=SOURCE_TIER,
    )

    category_stats = {}
    all_facts_collected = []
    all_inserted_ids = []
    seen_texts = set()

    def _add(fact_text: str, domain: str, subdomain: str,
             entities: list, tags: list, confidence: float = 1.0):
        if fact_text in seen_texts:
            return
        seen_texts.add(fact_text)
        all_facts_collected.append({
            "fact_text": fact_text,
            "domain": domain,
            "subdomain": subdomain,
            "source_id": source_id,
            "entities": entities,
            "confidence": confidence,
            "tags": tags,
        })

    # ── Category 1: Grand Crus (5 items) ─────────────────────────────────
    gc_start = len(all_facts_collected)
    gc_items = 0
    for gc in GRAND_CRUS[:TEST_RUN_LIMIT]:
        name = gc["name"]
        commune = gc["commune"]
        sub_region = gc["sub_region"]
        colors = gc["color"]
        grapes = gc["grapes"]

        _add(
            f"{name} is a Grand Cru appellation in the {sub_region} sub-region of Burgundy.",
            "wine_regions", "burgundy",
            [{"type": "appellation", "name": name}],
            ["grand_cru", "burgundy"],
        )
        _add(
            f"{name} Grand Cru is located in the commune of {commune}.",
            "wine_regions", "burgundy",
            [{"type": "appellation", "name": name}, {"type": "commune", "name": commune}],
            ["grand_cru", "commune", "burgundy"],
        )
        for grape in grapes:
            _add(
                f"{name} Grand Cru wines are made from {grape}.",
                "grape_varieties", "burgundy",
                [{"type": "appellation", "name": name}, {"type": "grape", "name": grape}],
                ["grand_cru", "grape", "burgundy"],
            )
        if "area_ha" in gc:
            _add(
                f"The {name} Grand Cru vineyard covers {gc['area_ha']} hectares.",
                "wine_regions", "burgundy",
                [{"type": "appellation", "name": name}],
                ["grand_cru", "area", "burgundy"],
            )
        gc_items += 1

    gc_facts = all_facts_collected[gc_start:]
    gc_inserted, gc_ids = _insert_facts_tracked(gc_facts)
    category_stats["grand_crus"] = {
        "items_processed": gc_items,
        "facts_generated": len(gc_facts),
        "facts_inserted": gc_inserted,
    }
    all_inserted_ids.extend(gc_ids)

    # ── Category 2: Village appellations (5 items) ───────────────────────
    va_start = len(all_facts_collected)
    va_items = 0
    for village, info in list(VILLAGE_APPELLATIONS.items())[:TEST_RUN_LIMIT]:
        sub_region = info["sub_region"]
        colors = info["colors"]
        grapes = info["grapes"]
        premier_crus = info["premier_crus"]

        _add(
            f"{village} is a village appellation in the {sub_region} sub-region of Burgundy.",
            "wine_regions", "burgundy",
            [{"type": "appellation", "name": village}],
            ["village", "burgundy"],
        )
        color_str = ", ".join(colors)
        _add(
            f"{village} produces {color_str} wines.",
            "wine_regions", "burgundy",
            [{"type": "appellation", "name": village}],
            ["village", "color", "burgundy"],
        )
        for grape in grapes:
            _add(
                f"{grape} is a permitted grape variety in the {village} appellation.",
                "grape_varieties", "burgundy",
                [{"type": "appellation", "name": village}, {"type": "grape", "name": grape}],
                ["village", "grape", "burgundy"],
            )
        if premier_crus:
            _add(
                f"The {village} appellation has {len(premier_crus)} Premier Cru vineyards.",
                "wine_regions", "burgundy",
                [{"type": "appellation", "name": village}],
                ["village", "premier_cru", "burgundy"],
            )
            # Include first 3 Premier Crus as sample
            for pc in premier_crus[:3]:
                _add(
                    f"{pc} is a Premier Cru vineyard in the {village} appellation.",
                    "wine_regions", "burgundy",
                    [{"type": "appellation", "name": village}, {"type": "vineyard", "name": pc}],
                    ["premier_cru", "burgundy"],
                )
        va_items += 1

    va_facts = all_facts_collected[va_start:]
    va_inserted, va_ids = _insert_facts_tracked(va_facts)
    category_stats["village_appellations"] = {
        "items_processed": va_items,
        "facts_generated": len(va_facts),
        "facts_inserted": va_inserted,
    }
    all_inserted_ids.extend(va_ids)

    # ── Category 3: Regional appellations (5 items) ──────────────────────
    ra_start = len(all_facts_collected)
    ra_items = 0
    for ra_info in REGIONAL_APPELLATIONS[:TEST_RUN_LIMIT]:
        appellation = ra_info["name"]
        colors = ra_info["colors"]
        grapes = ra_info["grapes"]

        _add(
            f"{appellation} is a regional appellation in Burgundy.",
            "wine_regions", "burgundy",
            [{"type": "appellation", "name": appellation}],
            ["regional", "burgundy"],
        )
        color_str = ", ".join(colors)
        _add(
            f"{appellation} covers {color_str} wines.",
            "wine_regions", "burgundy",
            [{"type": "appellation", "name": appellation}],
            ["regional", "color", "burgundy"],
        )
        for grape in grapes:
            _add(
                f"{grape} is a permitted grape variety in the {appellation} appellation.",
                "grape_varieties", "burgundy",
                [{"type": "appellation", "name": appellation}, {"type": "grape", "name": grape}],
                ["regional", "grape", "burgundy"],
            )
        ra_items += 1

    ra_facts = all_facts_collected[ra_start:]
    ra_inserted, ra_ids = _insert_facts_tracked(ra_facts)
    category_stats["regional_appellations"] = {
        "items_processed": ra_items,
        "facts_generated": len(ra_facts),
        "facts_inserted": ra_inserted,
    }
    all_inserted_ids.extend(ra_ids)

    # ── Category 4: Sub-regions (5 items) ────────────────────────────────
    sr_start = len(all_facts_collected)
    sr_items = 0
    for sr_name, sr_info in list(SUB_REGIONS.items())[:TEST_RUN_LIMIT]:
        _add(
            f"{sr_name} is a sub-region of Burgundy.",
            "wine_regions", "burgundy",
            [{"type": "sub_region", "name": sr_name}],
            ["sub_region", "burgundy"],
        )
        if "description" in sr_info:
            _add(
                f"{sr_name} is {sr_info['description']}.",
                "wine_regions", "burgundy",
                [{"type": "sub_region", "name": sr_name}],
                ["sub_region", "burgundy"],
            )
        sr_items += 1

    sr_facts = all_facts_collected[sr_start:]
    sr_inserted, sr_ids = _insert_facts_tracked(sr_facts)
    category_stats["sub_regions"] = {
        "items_processed": sr_items,
        "facts_generated": len(sr_facts),
        "facts_inserted": sr_inserted,
    }
    all_inserted_ids.extend(sr_ids)

    # ── Report ────────────────────────────────────────────────────────────
    _print_test_report(category_stats, all_facts_collected, all_inserted_ids)

    # ── Cleanup ───────────────────────────────────────────────────────────
    if cleanup:
        deleted = _cleanup_test_facts(all_inserted_ids)
        click.echo(f"\n  Cleaned up {deleted} test facts from database.")


# ─── CLI ──────────────────────────────────────────────────────────────────────

@click.command()
@click.option("--all", "run_all", is_flag=True, help="Scrape all Burgundy data and insert facts")
@click.option("--dry-run", is_flag=True, help="Generate facts but do not insert into database")
@click.option("--list", "list_sources", is_flag=True, help="List data sources and expected counts")
@click.option("--validate", is_flag=True, help="Run quality checks on generated facts")
@click.option("--live/--no-live", default=True, help="Attempt live scraping of BIVB site (default: on)")
@click.option("--test-run", is_flag=True, help="Process 5 items per category, insert, and report")
@click.option("--cleanup", is_flag=True, help="With --test-run, delete inserted facts after reporting")
def main(run_all: bool, dry_run: bool, list_sources: bool, validate: bool, live: bool,
         test_run: bool, cleanup: bool):
    """OenoBench Burgundy (BIVB) Scraper — Extract Burgundy wine knowledge."""
    logger.add("data/logs/burgundy_{time}.log", rotation="10 MB")

    if list_sources:
        click.echo("\nBurgundy (BIVB) data sources:")
        click.echo(f"  Grand Cru appellations:   {len(GRAND_CRUS):4d}")
        click.echo(f"  Village appellations:     {len(VILLAGE_APPELLATIONS):4d}")
        click.echo(f"  Regional appellations:    {len(REGIONAL_APPELLATIONS):4d}")
        click.echo(f"  Sub-regions:              {len(SUB_REGIONS):4d}")
        total_pc = sum(len(v["premier_crus"]) for v in VILLAGE_APPELLATIONS.values())
        click.echo(f"  Premier Cru vineyards:    {total_pc:4d}")
        click.echo(f"\n  Base URL: {BASE_URL}")
        click.echo(f"  Source:   {SOURCE_NAME} ({SOURCE_TIER})")
        return

    if test_run:
        run_test(cleanup=cleanup)
        return

    if validate or dry_run or run_all:
        # Build facts (always needed for all three modes)
        logger.info("Building facts from curated Burgundy data...")
        live_extras = []

        if live and (run_all or dry_run):
            logger.info("Attempting live scrape of BIVB website...")
            session = _get_session()
            live_extras = _try_scrape_appellation_pages(session)
            if live_extras:
                logger.info(f"Obtained {len(live_extras)} supplementary facts from live scraping")
            else:
                logger.info("No supplementary live data obtained; using curated data only")

        # For dry-run/validate, use a placeholder source_id
        source_id = "dry-run-placeholder"
        if run_all and not dry_run:
            source_id = ensure_source(
                name=SOURCE_NAME,
                url=BASE_URL,
                source_type="official_body",
                tier=SOURCE_TIER,
            )

        facts = build_all_facts(source_id, live_extras if live_extras else None)
        logger.info(f"Generated {len(facts)} total facts")

        if validate:
            validate_facts(facts)
            return

        if dry_run:
            click.echo(f"\n[DRY RUN] Would insert {len(facts)} facts into the database.")
            click.echo(f"Source: {SOURCE_NAME} ({SOURCE_TIER})")
            click.echo(f"\nSample facts:")
            for f in random.sample(facts, min(15, len(facts))):
                click.echo(f"  [{f['domain']:20s}] {f['fact_text']}")
            return

        if run_all:
            logger.info("Inserting facts into database...")
            inserted = insert_facts_batch(facts)
            logger.info(f"Inserted {inserted} new facts (duplicates skipped)")
            click.echo(f"\nBurgundy scraping complete.")
            click.echo(f"  Facts generated:  {len(facts)}")
            click.echo(f"  Facts inserted:   {inserted}")
            click.echo(f"  Total in DB:      {get_fact_count()}")
            return

    click.echo("Use --all to scrape and insert, --dry-run to preview, or --validate to check quality.")
    click.echo("Use --list to see data sources.")
    click.echo("Use --test-run to process 5 items per category and report.")


if __name__ == "__main__":
    main()
