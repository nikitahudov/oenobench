"""
OenoBench -- French Regional Wine Scraper: Rhone, Loire, Alsace

Comprehensive enrichment scraper covering three major French wine regions
that have minimal depth beyond basic INAO appellation data.

Focus areas: detailed terroir (soil, elevation, climate), appellation-level
data, grape variety profiles, Grand Cru vineyards (Alsace), and classification
systems (AOC, VT/SGN).

Usage:
    python -m src.scrapers.rhone_loire_alsace --all
    python -m src.scrapers.rhone_loire_alsace --type rhone
    python -m src.scrapers.rhone_loire_alsace --type loire
    python -m src.scrapers.rhone_loire_alsace --type alsace
    python -m src.scrapers.rhone_loire_alsace --type grape
    python -m src.scrapers.rhone_loire_alsace --type classification
    python -m src.scrapers.rhone_loire_alsace --dry-run
    python -m src.scrapers.rhone_loire_alsace --validate
    python -m src.scrapers.rhone_loire_alsace --test-run
    python -m src.scrapers.rhone_loire_alsace --list
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

# --- Configuration ------------------------------------------------------------

USER_AGENT = "OenoBench-Research/1.0 (academic wine benchmark)"
TEST_RUN_FACT_LIMIT = 5

SOURCE = {
    "name": "French Regional Wine Reference -- Rhone, Loire, Alsace",
    "url": "https://www.inter-rhone.com",
    "source_type": "reference",
    "tier": "tier_2_authoritative",
    "language": "en",
}


# ==============================================================================
# KNOWLEDGE BASE -- Rhone Valley Appellations
# ==============================================================================

RHONE_APPELLATIONS = [
    # ---- Northern Rhone (granitic terroir, Syrah dominant) ----
    {
        "name": "Cote-Rotie",
        "sub_region": "Northern Rhone",
        "meaning": "roasted slope",
        "grapes_red": ["Syrah"],
        "grapes_white": ["Viognier"],
        "blend_rules": "Syrah dominant, may add up to 20% Viognier co-fermented",
        "soil_types": ["micaschist", "gneiss"],
        "soil_details": "Cote Blonde has lighter sandy soils with mica; Cote Brune has darker iron-rich clay soils over metamorphic bedrock",
        "elevation_range": "180-330m",
        "vineyard_area_ha": 300,
        "climate": "continental with Mediterranean transition",
        "terroir_notes": "Steep terraced vineyards on the right bank of the Rhone, up to 60-degree slopes, south and southeast facing",
        "notable_lieux_dits": ["Cote Blonde", "Cote Brune", "La Landonne", "La Mouline", "La Turque"],
        "wine_colors": ["red"],
        "tags": ["northern_rhone", "cote_rotie"],
    },
    {
        "name": "Condrieu",
        "sub_region": "Northern Rhone",
        "grapes_white": ["Viognier"],
        "blend_rules": "100% Viognier",
        "soil_types": ["granite", "mica-schist"],
        "soil_details": "Decomposed granite and mica-schist on narrow terraces above the Rhone; thin topsoil over granitic bedrock",
        "elevation_range": "150-350m",
        "vineyard_area_ha": 190,
        "climate": "continental with southern warmth",
        "terroir_notes": "Narrow terraces on steep slopes, south-facing amphitheaters trap heat for late-ripening Viognier",
        "wine_colors": ["white"],
        "tags": ["northern_rhone", "condrieu"],
    },
    {
        "name": "Chateau-Grillet",
        "sub_region": "Northern Rhone",
        "grapes_white": ["Viognier"],
        "blend_rules": "100% Viognier",
        "soil_types": ["granite", "mica-schist"],
        "soil_details": "Decomposed granite on a natural south-facing amphitheater within the Condrieu zone",
        "elevation_range": "180-250m",
        "vineyard_area_ha": 3.8,
        "climate": "continental with warm microclimate",
        "terroir_notes": "Single-estate AOC entirely within the Condrieu zone; natural amphitheater concentrates heat and protects from northern winds",
        "wine_colors": ["white"],
        "tags": ["northern_rhone", "chateau_grillet"],
    },
    {
        "name": "Hermitage",
        "sub_region": "Northern Rhone",
        "grapes_red": ["Syrah"],
        "grapes_white": ["Marsanne", "Roussanne"],
        "blend_rules": "Red: Syrah, may include up to 15% Marsanne/Roussanne; White: Marsanne and/or Roussanne",
        "soil_types": ["granite", "loess", "alluvial", "clay-limestone"],
        "soil_details": "The granite hill of Hermitage has multiple soil types: granite on the upper slopes, loess and clay on mid-slopes, and alluvial deposits at the base",
        "elevation_range": "100-350m",
        "vineyard_area_ha": 136,
        "climate": "continental with warm south-facing exposure",
        "terroir_notes": "Famous granite hill on the left bank of the Rhone; 26 named lieux-dits including Le Meal, Les Bessards, L'Hermite, Les Greffieux, and Chante-Alouette",
        "notable_lieux_dits": ["Le Meal", "Les Bessards", "L'Hermite", "Les Greffieux", "Chante-Alouette", "Les Diognieres", "Les Rocoules"],
        "wine_colors": ["red", "white"],
        "tags": ["northern_rhone", "hermitage"],
    },
    {
        "name": "Crozes-Hermitage",
        "sub_region": "Northern Rhone",
        "grapes_red": ["Syrah"],
        "grapes_white": ["Marsanne", "Roussanne"],
        "blend_rules": "Red: Syrah, may include up to 15% Marsanne/Roussanne; White: Marsanne and/or Roussanne",
        "soil_types": ["alluvial", "granite", "clay-limestone", "loess"],
        "soil_details": "Varied terroir surrounding the Hermitage hill: northern sector has granite-derived soils; southern plateau (Les Chassis) has alluvial terraces with rounded pebbles",
        "elevation_range": "100-350m",
        "vineyard_area_ha": 1700,
        "climate": "continental",
        "terroir_notes": "Largest appellation of the Northern Rhone, surrounding Hermitage on all sides; quality varies significantly between hillside and plateau sites",
        "wine_colors": ["red", "white"],
        "tags": ["northern_rhone", "crozes_hermitage"],
    },
    {
        "name": "Saint-Joseph",
        "sub_region": "Northern Rhone",
        "grapes_red": ["Syrah"],
        "grapes_white": ["Marsanne", "Roussanne"],
        "blend_rules": "Red: Syrah, may include up to 10% Marsanne/Roussanne; White: Marsanne and/or Roussanne",
        "soil_types": ["granite", "gneiss"],
        "soil_details": "Granite and gneiss on steep hillsides; best sites on the original six communes have thin, well-drained soils",
        "elevation_range": "150-400m",
        "vineyard_area_ha": 1200,
        "climate": "continental",
        "terroir_notes": "Stretches 60 km along the right bank of the Rhone from Condrieu to Cornas; original six communes (Mauves, Tournon, Saint-Jean-de-Muzols, Lemps, Glun, Vion) produce the finest wines",
        "wine_colors": ["red", "white"],
        "tags": ["northern_rhone", "saint_joseph"],
    },
    {
        "name": "Cornas",
        "sub_region": "Northern Rhone",
        "grapes_red": ["Syrah"],
        "blend_rules": "100% Syrah, no white grapes permitted",
        "soil_types": ["granite", "limestone", "clay"],
        "soil_details": "Decomposed granite on the upper slopes with clay-limestone lower down; south-facing amphitheater protects from the mistral",
        "elevation_range": "120-380m",
        "vineyard_area_ha": 150,
        "climate": "warm continental, sheltered from the mistral wind",
        "terroir_notes": "South-facing amphitheater creates one of the warmest microclimates in the Northern Rhone; the name derives from 'scorched earth' in Celtic; only red wine permitted",
        "wine_colors": ["red"],
        "tags": ["northern_rhone", "cornas"],
    },
    {
        "name": "Saint-Peray",
        "sub_region": "Northern Rhone",
        "grapes_white": ["Marsanne", "Roussanne"],
        "blend_rules": "Marsanne and/or Roussanne",
        "soil_types": ["granite", "limestone", "clay"],
        "soil_details": "Granite and limestone on hillsides above the town of Saint-Peray at the southern end of the Northern Rhone",
        "elevation_range": "120-350m",
        "vineyard_area_ha": 90,
        "climate": "warm continental",
        "terroir_notes": "Southernmost appellation of the Northern Rhone; produces both still and traditional-method sparkling white wines; only white wines are permitted",
        "wine_colors": ["white"],
        "tags": ["northern_rhone", "saint_peray"],
    },

    # ---- Southern Rhone (galets roules, Mediterranean, blends) ----
    {
        "name": "Chateauneuf-du-Pape",
        "sub_region": "Southern Rhone",
        "grapes_red": ["Grenache", "Syrah", "Mourvedre", "Cinsault", "Counoise", "Muscardin", "Vaccarese", "Terret Noir"],
        "grapes_white": ["Grenache Blanc", "Clairette", "Bourboulenc", "Roussanne", "Picardan"],
        "blend_rules": "13 permitted grape varieties; Grenache typically dominant in red blends at 50-80%",
        "soil_types": ["galets roules", "limestone", "clay", "sand"],
        "soil_details": "Famous galets roules (large rounded stones) deposited by the ancient Rhone; underlying soils include red clay, sandy limestone, and pure sand depending on the sector",
        "elevation_range": "20-120m",
        "vineyard_area_ha": 3200,
        "climate": "Mediterranean with strong mistral wind",
        "terroir_notes": "Named for the 14th-century papal palace at Avignon; the galets roules absorb daytime heat and radiate it back at night, promoting ripeness; one of the first French AOCs (1936)",
        "permitted_varieties_count": 13,
        "permitted_varieties": ["Grenache", "Syrah", "Mourvedre", "Cinsault", "Counoise",
                                "Muscardin", "Vaccarese", "Terret Noir", "Grenache Blanc",
                                "Clairette", "Bourboulenc", "Roussanne", "Picardan"],
        "wine_colors": ["red", "white"],
        "tags": ["southern_rhone", "chateauneuf_du_pape"],
    },
    {
        "name": "Gigondas",
        "sub_region": "Southern Rhone",
        "grapes_red": ["Grenache", "Syrah", "Mourvedre"],
        "blend_rules": "Grenache minimum 50%, Syrah and Mourvedre at least 15% combined; maximum 10% other permitted varieties",
        "soil_types": ["limestone", "clay", "sand"],
        "soil_details": "Dentelles de Montmirail limestone massif provides complex soils ranging from clay-limestone to sandy terraces at varying elevations",
        "elevation_range": "100-400m",
        "vineyard_area_ha": 1250,
        "climate": "Mediterranean with altitude cooling from the Dentelles de Montmirail",
        "terroir_notes": "Elevated vineyards at the foot of the Dentelles de Montmirail limestone peaks; altitude provides cooler nights than the Rhone valley floor, producing more structured wines than the plain",
        "wine_colors": ["red", "rose"],
        "tags": ["southern_rhone", "gigondas"],
    },
    {
        "name": "Vacqueyras",
        "sub_region": "Southern Rhone",
        "grapes_red": ["Grenache", "Syrah", "Mourvedre"],
        "blend_rules": "Grenache minimum 50%, Syrah and/or Mourvedre minimum 20%",
        "soil_types": ["galets roules", "limestone", "clay", "sand"],
        "soil_details": "Southern sector has galets roules similar to Chateauneuf-du-Pape; northern sector near the Dentelles has limestone and sandy soils",
        "elevation_range": "60-300m",
        "vineyard_area_ha": 1400,
        "climate": "Mediterranean",
        "terroir_notes": "Promoted from Cotes du Rhone Villages to its own AOC in 1990; straddles the transition between the Rhone plain and the Dentelles de Montmirail foothills",
        "wine_colors": ["red", "white", "rose"],
        "tags": ["southern_rhone", "vacqueyras"],
    },
    {
        "name": "Beaumes-de-Venise",
        "sub_region": "Southern Rhone",
        "grapes_red": ["Grenache", "Syrah", "Mourvedre"],
        "grapes_white": ["Muscat Blanc a Petits Grains", "Muscat a Petits Grains Rouge"],
        "blend_rules": "Red wines: Grenache minimum 50%; Muscat de Beaumes-de-Venise: 100% Muscat Blanc a Petits Grains and/or Muscat a Petits Grains Rouge",
        "soil_types": ["limestone", "clay-limestone", "sand"],
        "soil_details": "Triassic limestone bedrock with clay-limestone and sandy soils on hillsides at the southern foot of the Dentelles de Montmirail",
        "elevation_range": "100-400m",
        "vineyard_area_ha": 600,
        "climate": "Mediterranean with altitude influence",
        "terroir_notes": "Famous for Muscat de Beaumes-de-Venise (Vin Doux Naturel); also produces red wines under the Beaumes-de-Venise AOC since 2005",
        "wine_colors": ["red", "sweet white"],
        "tags": ["southern_rhone", "beaumes_de_venise"],
    },
    {
        "name": "Rasteau",
        "sub_region": "Southern Rhone",
        "grapes_red": ["Grenache", "Syrah", "Mourvedre"],
        "blend_rules": "Grenache minimum 50%; also produces Vin Doux Naturel from Grenache (minimum 90%)",
        "soil_types": ["clay-limestone", "marl", "sand"],
        "soil_details": "Blue and gray marl on north-facing slopes, clay-limestone and sandy soils on south-facing exposures; varied terroir from the Ouveze river valley",
        "elevation_range": "100-350m",
        "vineyard_area_ha": 1000,
        "climate": "Mediterranean",
        "terroir_notes": "Produces both dry red wines (Cru since 2010) and Vin Doux Naturel (since 1944); the amphitheater of hillsides around the village provides diverse exposures",
        "wine_colors": ["red", "sweet"],
        "tags": ["southern_rhone", "rasteau"],
    },
    {
        "name": "Vinsobres",
        "sub_region": "Southern Rhone",
        "grapes_red": ["Grenache", "Syrah"],
        "blend_rules": "Grenache minimum 50%, Syrah minimum 25%",
        "soil_types": ["clay-limestone", "marl", "sand"],
        "soil_details": "Clay-limestone and marl on hillsides above the Eygues river; higher elevation than most Southern Rhone communes",
        "elevation_range": "200-500m",
        "vineyard_area_ha": 500,
        "climate": "Mediterranean with significant altitude cooling",
        "terroir_notes": "First commune promoted to Cru des Cotes du Rhone Villages status (2006); higher altitude than many Southern Rhone appellations gives cooler nights and later harvests",
        "wine_colors": ["red"],
        "tags": ["southern_rhone", "vinsobres"],
    },
    {
        "name": "Lirac",
        "sub_region": "Southern Rhone",
        "grapes_red": ["Grenache", "Syrah", "Mourvedre"],
        "grapes_white": ["Grenache Blanc", "Clairette", "Bourboulenc"],
        "blend_rules": "Red: Grenache minimum 40%, Syrah and/or Mourvedre minimum 25%",
        "soil_types": ["sand", "clay", "galets roules"],
        "soil_details": "Three terroir types: sandy terraces, clay-limestone plateaus, and galets roules deposits similar to neighboring Chateauneuf-du-Pape",
        "elevation_range": "30-130m",
        "vineyard_area_ha": 700,
        "climate": "Mediterranean",
        "terroir_notes": "Located on the right (west) bank of the Rhone opposite Chateauneuf-du-Pape; produces red, white, and rose wines",
        "wine_colors": ["red", "white", "rose"],
        "tags": ["southern_rhone", "lirac"],
    },
    {
        "name": "Tavel",
        "sub_region": "Southern Rhone",
        "grapes_red": ["Grenache", "Cinsault", "Syrah", "Mourvedre", "Clairette", "Bourboulenc"],
        "blend_rules": "Grenache and Cinsault must together represent at least 60%; nine varieties permitted",
        "soil_types": ["sand", "clay", "galets roules", "limestone"],
        "soil_details": "Three main soil types: galets roules on the plateau de Vallongue, sandy soils at Les Olivets, and limestone-clay at the Vestides",
        "elevation_range": "20-100m",
        "vineyard_area_ha": 900,
        "climate": "Mediterranean",
        "terroir_notes": "France's most famous rose-only AOC; the only appellation in the Rhone exclusively dedicated to rose production; historically favored by the Avignon popes and French royalty",
        "wine_colors": ["rose"],
        "tags": ["southern_rhone", "tavel"],
    },
    {
        "name": "Cotes du Rhone",
        "sub_region": "Southern Rhone",
        "grapes_red": ["Grenache", "Syrah", "Mourvedre"],
        "grapes_white": ["Grenache Blanc", "Clairette", "Marsanne", "Roussanne", "Bourboulenc", "Viognier"],
        "blend_rules": "Red: Grenache minimum 40%, Syrah and/or Mourvedre minimum 20%",
        "soil_types": ["varied"],
        "soil_details": "Extremely varied soils across a vast region from Vienne to Avignon: alluvial terraces, galets roules, limestone, granite, sand, and clay",
        "vineyard_area_ha": 44000,
        "climate": "Mediterranean in the south, continental in the north",
        "terroir_notes": "Regional appellation spanning the entire Rhone Valley across 171 communes in six departments; the vast majority of production is in the Southern Rhone",
        "wine_colors": ["red", "white", "rose"],
        "tags": ["southern_rhone", "cotes_du_rhone"],
    },
    {
        "name": "Cotes du Rhone Villages",
        "sub_region": "Southern Rhone",
        "grapes_red": ["Grenache", "Syrah", "Mourvedre"],
        "blend_rules": "Stricter yields and minimum alcohol than basic Cotes du Rhone; Grenache minimum 50%, Syrah and/or Mourvedre minimum 20%",
        "soil_types": ["varied"],
        "soil_details": "Selected communes with superior terroir; soils range from clay-limestone to galets roules depending on the village",
        "vineyard_area_ha": 3500,
        "climate": "Mediterranean",
        "terroir_notes": "22 named villages may append their commune name to the label (e.g., Cairanne, Sablet, Seguret, Roaix, Valreas, Visan, Saint-Gervais, Plan de Dieu, Massif d'Uchaux, Puymeran, Signargues, Laudun, Chusclan, Saint-Maurice, Saint-Pantaleon-les-Vignes, Rousset-les-Vignes, Gadagne, Nyons, Bouchet, Suze-la-Rousse, Sainte-Cecile, Vaison-la-Romaine)",
        "wine_colors": ["red", "white", "rose"],
        "tags": ["southern_rhone", "cotes_du_rhone_villages"],
    },
]


# ==============================================================================
# KNOWLEDGE BASE -- Loire Valley Appellations
# ==============================================================================

LOIRE_APPELLATIONS = [
    # ---- Pays Nantais (Atlantic) ----
    {
        "name": "Muscadet",
        "sub_region": "Pays Nantais",
        "grapes_white": ["Melon de Bourgogne"],
        "blend_rules": "100% Melon de Bourgogne",
        "soil_types": ["gneiss", "gabbro", "granite", "amphibolite"],
        "soil_details": "Ancient crystalline bedrock of the Armorican Massif; gneiss dominates around Vertou, gabbro near Le Pallet, granite in the east, amphibolite near Mouzillon",
        "elevation_range": "10-70m",
        "vineyard_area_ha": 8000,
        "climate": "oceanic Atlantic",
        "terroir_notes": "Located at the mouth of the Loire near Nantes; Atlantic climate moderates temperatures; sur lie aging (on the lees) adds richness and a slight prickle of CO2",
        "wine_colors": ["white"],
        "tags": ["pays_nantais", "muscadet"],
    },
    {
        "name": "Muscadet Sevre et Maine",
        "sub_region": "Pays Nantais",
        "grapes_white": ["Melon de Bourgogne"],
        "blend_rules": "100% Melon de Bourgogne; sur lie bottling requires wine to spend at least one winter on fine lees",
        "soil_types": ["gneiss", "gabbro", "granite", "orthogneiss"],
        "soil_details": "Named for the Sevre Nantaise and Maine rivers; complex geological mosaic from the Armorican Massif with predominantly metamorphic soils",
        "elevation_range": "10-70m",
        "vineyard_area_ha": 6800,
        "climate": "oceanic Atlantic",
        "terroir_notes": "Largest Muscadet sub-appellation producing over 80% of all Muscadet; sur lie aging is a defining technique, keeping wine on its fine lees until bottling",
        "wine_colors": ["white"],
        "tags": ["pays_nantais", "muscadet_sevre_et_maine"],
    },
    {
        "name": "Muscadet Cru Communaux",
        "sub_region": "Pays Nantais",
        "grapes_white": ["Melon de Bourgogne"],
        "blend_rules": "100% Melon de Bourgogne; extended sur lie aging of 18-24 months minimum depending on cru",
        "soil_types": ["gneiss", "gabbro", "granite", "amphibolite", "serpentinite"],
        "soil_details": "Each cru has a distinct geological identity: Clisson (granite), Gorges (gabbro), Le Pallet (gabbro/gneiss), Goulaine (gneiss), Mouzillon-Tillieres (gabbro/amphibolite), Monnieres-Saint-Fiacre (gneiss/orthogneiss), La Haye-Fouassiere (gneiss), Chateau-Thebaud (orthogneiss), Maisdon-sur-Sevre (gneiss), Vallet (gabbro)",
        "vineyard_area_ha": None,
        "climate": "oceanic Atlantic",
        "terroir_notes": "Ten named crus recognized between 2011 and 2019; each requires extended lees aging (minimum 18-24 months) and expresses distinct terroir character from its geological substrate",
        "crus": ["Clisson", "Gorges", "Le Pallet", "Goulaine", "Mouzillon-Tillieres",
                 "Monnieres-Saint-Fiacre", "La Haye-Fouassiere", "Chateau-Thebaud",
                 "Maisdon-sur-Sevre", "Vallet"],
        "wine_colors": ["white"],
        "tags": ["pays_nantais", "muscadet_cru_communaux"],
    },

    # ---- Anjou-Saumur (tuffeau limestone) ----
    {
        "name": "Savennieres",
        "sub_region": "Anjou-Saumur",
        "grapes_white": ["Chenin Blanc"],
        "blend_rules": "100% Chenin Blanc",
        "soil_types": ["schist", "volcanic", "sandstone"],
        "soil_details": "Primary schist and volcanic rhyolite on steep south-facing slopes above the north bank of the Loire; warm, well-drained soils produce concentrated dry Chenin Blanc",
        "elevation_range": "30-80m",
        "vineyard_area_ha": 150,
        "climate": "oceanic with warm microclimate on south-facing slopes",
        "terroir_notes": "South-facing slopes above the Loire create an exceptionally warm microclimate for the Loire Valley; produces powerful, age-worthy dry Chenin Blanc; includes the sub-appellations Coulee de Serrant and Roche aux Moines",
        "wine_colors": ["white"],
        "tags": ["anjou_saumur", "savennieres"],
    },
    {
        "name": "Quarts de Chaume",
        "sub_region": "Anjou-Saumur",
        "grapes_white": ["Chenin Blanc"],
        "blend_rules": "100% Chenin Blanc; sweet wine from botrytized or passerillage grapes",
        "soil_types": ["schist", "carboniferous sandstone"],
        "soil_details": "Schist and carboniferous sandstone on a south-facing hillside within the Coteaux du Layon; the slope and proximity to the Layon river encourage botrytis",
        "elevation_range": "40-80m",
        "vineyard_area_ha": 40,
        "climate": "oceanic with botrytis-prone microclimate",
        "terroir_notes": "Grand Cru of the Loire, elevated to its own Grand Cru AOC in 2011; name refers to the quarter-share of harvest owed to feudal lords; extremely low yields produce some of France's greatest sweet wines",
        "wine_colors": ["sweet white"],
        "tags": ["anjou_saumur", "quarts_de_chaume"],
    },
    {
        "name": "Bonnezeaux",
        "sub_region": "Anjou-Saumur",
        "grapes_white": ["Chenin Blanc"],
        "blend_rules": "100% Chenin Blanc; sweet wine with botrytis and/or passerillage",
        "soil_types": ["schist", "carboniferous"],
        "soil_details": "Steep south-facing schist slopes within the Coteaux du Layon; three hills (La Montagne, Beauregard, Fesles) form a natural amphitheater",
        "elevation_range": "40-100m",
        "vineyard_area_ha": 100,
        "climate": "oceanic with botrytis-prone conditions",
        "terroir_notes": "Sweet Chenin Blanc from three steep, south-facing hillsides that form a natural amphitheater; produces luscious wines that can age for decades",
        "wine_colors": ["sweet white"],
        "tags": ["anjou_saumur", "bonnezeaux"],
    },
    {
        "name": "Coteaux du Layon",
        "sub_region": "Anjou-Saumur",
        "grapes_white": ["Chenin Blanc"],
        "blend_rules": "100% Chenin Blanc; sweet wine, minimum residual sugar 34 g/L",
        "soil_types": ["schist", "carboniferous", "volcanic"],
        "soil_details": "Schist and carboniferous soils along the south-facing banks of the Layon tributary; includes the superior sub-designation Coteaux du Layon Premier Cru Chaume",
        "elevation_range": "30-100m",
        "vineyard_area_ha": 1500,
        "climate": "oceanic with autumnal mists favoring botrytis",
        "terroir_notes": "Sweet Chenin Blanc from the banks of the Layon river; morning mists from the river encourage noble rot development; wines range from demi-sec to richly botrytized",
        "wine_colors": ["sweet white"],
        "tags": ["anjou_saumur", "coteaux_du_layon"],
    },
    {
        "name": "Saumur-Champigny",
        "sub_region": "Anjou-Saumur",
        "grapes_red": ["Cabernet Franc"],
        "blend_rules": "Cabernet Franc dominant (minimum 85%); may include Cabernet Sauvignon and/or Pineau d'Aunis",
        "soil_types": ["tuffeau limestone", "clay-limestone", "sand"],
        "soil_details": "White tuffeau limestone (Turonian chalk) provides excellent drainage and mineral expression; some sites have clay-limestone with flint",
        "elevation_range": "30-80m",
        "vineyard_area_ha": 1500,
        "climate": "oceanic with limestone-moderated microclimate",
        "terroir_notes": "The Loire's finest Cabernet Franc appellation alongside Chinon; white tuffeau limestone provides natural cellars carved into the rock and ideal vine-growing soils; 'Champigny' may derive from 'campus ignis' (field of fire) referring to the warm microclimate",
        "wine_colors": ["red"],
        "tags": ["anjou_saumur", "saumur_champigny"],
    },
    {
        "name": "Anjou",
        "sub_region": "Anjou-Saumur",
        "grapes_red": ["Cabernet Franc", "Cabernet Sauvignon"],
        "grapes_white": ["Chenin Blanc"],
        "blend_rules": "Red: Cabernet Franc and/or Cabernet Sauvignon; White: minimum 80% Chenin Blanc",
        "soil_types": ["schist", "slate", "limestone", "clay"],
        "soil_details": "Western Anjou has dark schist and slate (Anjou Noir); eastern Anjou has lighter limestone and tuffeau (Anjou Blanc); this geological divide strongly influences wine styles",
        "elevation_range": "20-100m",
        "vineyard_area_ha": 2500,
        "climate": "oceanic",
        "terroir_notes": "Large regional appellation encompassing diverse terroir divided into Anjou Noir (dark schist, western) and Anjou Blanc (pale limestone, eastern); also produces Anjou Villages (selected communes) and rose",
        "wine_colors": ["red", "white", "rose"],
        "tags": ["anjou_saumur", "anjou"],
    },
    {
        "name": "Saumur",
        "sub_region": "Anjou-Saumur",
        "grapes_red": ["Cabernet Franc"],
        "grapes_white": ["Chenin Blanc", "Chardonnay"],
        "blend_rules": "Red: Cabernet Franc dominant; White: Chenin Blanc minimum 80%; Sparkling (Cremant de Loire/Saumur Brut): Chenin Blanc dominant",
        "soil_types": ["tuffeau limestone", "clay-limestone"],
        "soil_details": "White tuffeau limestone creates ideal caves for sparkling wine aging; the subterranean cellars maintain constant cool temperatures year-round",
        "elevation_range": "30-80m",
        "vineyard_area_ha": 1500,
        "climate": "oceanic with mild microclimate",
        "terroir_notes": "Famous for both still and sparkling wines; the tuffeau limestone caves provide perfect conditions for traditional-method sparkling wine maturation; historically known as the 'pearl of Anjou'",
        "wine_colors": ["red", "white", "sparkling"],
        "tags": ["anjou_saumur", "saumur"],
    },

    # ---- Touraine (Garden of France) ----
    {
        "name": "Vouvray",
        "sub_region": "Touraine",
        "grapes_white": ["Chenin Blanc"],
        "blend_rules": "100% Chenin Blanc",
        "soil_types": ["tuffeau limestone", "clay-with-flint", "perruches"],
        "soil_details": "Three main soil types: tuffeau (white chalk) on the plateau edge, clay-with-flint (argile a silex) on the plateau top, and perruches (flinty clay) on slopes; all contribute distinct character",
        "elevation_range": "60-120m",
        "vineyard_area_ha": 2000,
        "climate": "oceanic, moderated by the Loire",
        "terroir_notes": "Produces the full spectrum of Chenin Blanc styles: sec (dry), demi-sec (off-dry), moelleux (sweet), and petillant/mousseux (sparkling); vintage variation strongly determines which style predominates",
        "wine_colors": ["white", "sparkling"],
        "tags": ["touraine", "vouvray"],
    },
    {
        "name": "Chinon",
        "sub_region": "Touraine",
        "grapes_red": ["Cabernet Franc"],
        "grapes_white": ["Chenin Blanc"],
        "blend_rules": "Red: primarily Cabernet Franc (may include up to 10% Cabernet Sauvignon); White: 100% Chenin Blanc",
        "soil_types": ["tuffeau limestone", "gravel", "clay", "sand"],
        "soil_details": "Three distinct terroir zones: gravel and sand along the Vienne river (lighter reds), tuffeau limestone slopes (structured, age-worthy), and clay-limestone plateau (full-bodied)",
        "elevation_range": "30-110m",
        "vineyard_area_ha": 2300,
        "climate": "oceanic, among the warmest Touraine appellations",
        "terroir_notes": "The Loire's largest Cabernet Franc appellation; three soil types produce distinct wine styles from light and fruity (gravels) to structured and cellar-worthy (tuffeau slopes); referenced by Rabelais in the 16th century",
        "wine_colors": ["red", "white", "rose"],
        "tags": ["touraine", "chinon"],
    },
    {
        "name": "Bourgueil",
        "sub_region": "Touraine",
        "grapes_red": ["Cabernet Franc"],
        "blend_rules": "Cabernet Franc dominant (minimum 90%); may include Cabernet Sauvignon",
        "soil_types": ["tuffeau limestone", "gravel", "sand"],
        "soil_details": "Two main zones: gravel and sand terraces along the Loire (lighter, fruit-driven wines) and tuffeau limestone slopes (more structured, tannic wines with greater aging potential)",
        "elevation_range": "30-110m",
        "vineyard_area_ha": 1400,
        "climate": "oceanic",
        "terroir_notes": "Located on the north bank of the Loire opposite Chinon; wines from the tuffeau slopes are generally more structured and age-worthy than those from the gravel terraces",
        "wine_colors": ["red", "rose"],
        "tags": ["touraine", "bourgueil"],
    },
    {
        "name": "Saint-Nicolas-de-Bourgueil",
        "sub_region": "Touraine",
        "grapes_red": ["Cabernet Franc"],
        "blend_rules": "Cabernet Franc dominant (minimum 90%); may include Cabernet Sauvignon",
        "soil_types": ["sand", "gravel", "tuffeau limestone"],
        "soil_details": "Predominantly sandy and gravelly soils from ancient Loire alluvial deposits; lighter and sandier than neighboring Bourgueil",
        "elevation_range": "30-80m",
        "vineyard_area_ha": 1100,
        "climate": "oceanic",
        "terroir_notes": "Sandier soils than neighboring Bourgueil produce lighter, more supple, earlier-drinking Cabernet Franc; single commune appellation entirely within the broader Bourgueil zone",
        "wine_colors": ["red", "rose"],
        "tags": ["touraine", "saint_nicolas_de_bourgueil"],
    },
    {
        "name": "Montlouis-sur-Loire",
        "sub_region": "Touraine",
        "grapes_white": ["Chenin Blanc"],
        "blend_rules": "100% Chenin Blanc",
        "soil_types": ["tuffeau limestone", "clay-with-flint", "sand"],
        "soil_details": "Similar geology to Vouvray on the opposite bank of the Loire; tuffeau limestone base with clay-flint overlay and some sandy sectors",
        "elevation_range": "60-100m",
        "vineyard_area_ha": 500,
        "climate": "oceanic, slightly warmer than Vouvray",
        "terroir_notes": "Located on the south bank of the Loire directly opposite Vouvray; produces the same range of Chenin Blanc styles (dry, off-dry, sweet, sparkling) but with slightly earlier ripening due to warmer south-bank exposure",
        "wine_colors": ["white", "sparkling"],
        "tags": ["touraine", "montlouis_sur_loire"],
    },

    # ---- Centre Loire (continental) ----
    {
        "name": "Sancerre",
        "sub_region": "Centre Loire",
        "grapes_white": ["Sauvignon Blanc"],
        "grapes_red": ["Pinot Noir"],
        "blend_rules": "White: 100% Sauvignon Blanc; Red and rose: 100% Pinot Noir",
        "soil_types": ["kimmeridgian limestone", "silex", "caillottes"],
        "soil_details": "Three main soil types: terres blanches (kimmeridgian clay-limestone, richest wines), caillottes (pebbly limestone, mineral/citrus), and silex (flinty, gunflint/smoky character)",
        "elevation_range": "200-400m",
        "vineyard_area_ha": 3000,
        "climate": "semi-continental",
        "terroir_notes": "Hilltop town overlooking the Loire from the left bank; the three soil types produce distinctly different expressions of Sauvignon Blanc; also produces notable Pinot Noir reds and roses",
        "wine_colors": ["white", "red", "rose"],
        "tags": ["centre_loire", "sancerre"],
    },
    {
        "name": "Pouilly-Fume",
        "sub_region": "Centre Loire",
        "grapes_white": ["Sauvignon Blanc"],
        "blend_rules": "100% Sauvignon Blanc",
        "soil_types": ["silex", "kimmeridgian limestone", "caillottes", "marnes kimmeridgiennes"],
        "soil_details": "Famous for silex (flint) soils that contribute a distinctive gunflint/smoky character; kimmeridgian marl in other sectors gives rounder, richer wines",
        "elevation_range": "150-300m",
        "vineyard_area_ha": 1350,
        "climate": "semi-continental",
        "terroir_notes": "Located on the right bank of the Loire opposite Sancerre; the 'fume' refers either to the smoky/flinty character from silex soils or to the grey bloom on ripe Sauvignon Blanc grapes; no Pinot Noir is permitted",
        "wine_colors": ["white"],
        "tags": ["centre_loire", "pouilly_fume"],
    },
    {
        "name": "Menetou-Salon",
        "sub_region": "Centre Loire",
        "grapes_white": ["Sauvignon Blanc"],
        "grapes_red": ["Pinot Noir"],
        "blend_rules": "White: 100% Sauvignon Blanc; Red and rose: 100% Pinot Noir",
        "soil_types": ["kimmeridgian limestone", "clay-limestone"],
        "soil_details": "Kimmeridgian clay-limestone soils similar to Sancerre; vineyards situated on gentle hillsides west of Bourges",
        "elevation_range": "150-300m",
        "vineyard_area_ha": 500,
        "climate": "semi-continental",
        "terroir_notes": "Often described as an affordable alternative to Sancerre with similar terroir and grape varieties; historically associated with Jacques Coeur, the medieval financier",
        "wine_colors": ["white", "red", "rose"],
        "tags": ["centre_loire", "menetou_salon"],
    },
    {
        "name": "Quincy",
        "sub_region": "Centre Loire",
        "grapes_white": ["Sauvignon Blanc"],
        "blend_rules": "100% Sauvignon Blanc",
        "soil_types": ["sand", "gravel", "clay"],
        "soil_details": "Ancient sand and gravel terraces deposited by the Cher river; some clay-limestone on higher ground",
        "elevation_range": "120-180m",
        "vineyard_area_ha": 300,
        "climate": "semi-continental",
        "terroir_notes": "The oldest AOC in the Loire Valley, granted in 1936; small appellation on the Cher river producing exclusively white Sauvignon Blanc with a distinct mineral character from its sandy-gravel soils",
        "wine_colors": ["white"],
        "tags": ["centre_loire", "quincy"],
    },
    {
        "name": "Reuilly",
        "sub_region": "Centre Loire",
        "grapes_white": ["Sauvignon Blanc"],
        "grapes_red": ["Pinot Noir"],
        "grapes_rose": ["Pinot Gris"],
        "blend_rules": "White: 100% Sauvignon Blanc; Red: 100% Pinot Noir; Rose: 100% Pinot Gris",
        "soil_types": ["clay-limestone", "sand", "marl"],
        "soil_details": "Kimmeridgian and Oxfordian marls and clay-limestone on gentle slopes near the Arnon river; sandier soils in some sectors",
        "elevation_range": "120-200m",
        "vineyard_area_ha": 250,
        "climate": "semi-continental",
        "terroir_notes": "One of the few appellations to use Pinot Gris for rose (called 'vin gris'); small but revived appellation on the Arnon river west of Bourges",
        "wine_colors": ["white", "red", "rose"],
        "tags": ["centre_loire", "reuilly"],
    },
]


# ==============================================================================
# KNOWLEDGE BASE -- Alsace Grand Crus & General Data
# ==============================================================================

ALSACE_GENERAL = {
    "vineyard_area_ha": 15600,
    "length_km": 119,
    "rainfall_mm": 500,
    "vosges_effect": "The Vosges mountains shield Alsace from Atlantic rain, making it one of the driest wine regions in France with approximately 500 mm of annual rainfall.",
    "geological_mosaic": "Alsace possesses one of the most geologically complex vineyard mosaics in the world, with 13 identified soil types including granite, limestone, sandstone, volcanic, clay-marl, schist, gneiss, and loess.",
    "aoc_hierarchy": "The Alsace AOC hierarchy comprises three levels: Alsace AOC (regional), Alsace Grand Cru (51 named vineyards), and Cremant d'Alsace (traditional-method sparkling).",
    "vt_sgn": "Alsace has two special sweet wine designations: Vendange Tardive (VT, late harvest) and Selection de Grains Nobles (SGN, botrytized grapes), both requiring specific minimum sugar levels at harvest.",
    "vt_requirement": "Vendange Tardive wines must reach minimum potential alcohol levels at harvest: 14.3% for Riesling and Muscat, 15.3% for Gewurztraminer and Pinot Gris.",
    "sgn_requirement": "Selection de Grains Nobles wines must reach minimum potential alcohol levels at harvest: 16.4% for Riesling and Muscat, 17.6% for Gewurztraminer and Pinot Gris.",
    "stretch_description": "The Alsace vineyard stretches 119 km from Strasbourg (Marlenheim) in the north to Mulhouse (Thann) in the south, along the eastern foothills of the Vosges mountains.",
}

ALSACE_NOBLE_GRAPES = [
    {
        "name": "Riesling",
        "area_ha": 3400,
        "pct_of_plantings": 22,
        "character": "mineral, petrol with age, citrus, steely acidity",
        "style": "Dry style preferred in Alsace; also excels as Vendange Tardive and SGN; considered the noblest Alsace grape",
        "grand_cru_star": True,
    },
    {
        "name": "Gewurztraminer",
        "area_ha": 2700,
        "pct_of_plantings": 17,
        "character": "lychee, rose petal, Turkish delight, spice",
        "style": "Naturally low acidity, rich and aromatic; frequently off-dry even when labeled dry; a Grand Cru star grape",
        "grand_cru_star": True,
    },
    {
        "name": "Pinot Gris",
        "area_ha": 2500,
        "pct_of_plantings": 16,
        "character": "rich, smoky, honeyed, stone fruit",
        "style": "Full-bodied with a smoky, rich character; formerly known as Tokay d'Alsace until EU regulations required the name change",
        "grand_cru_star": True,
    },
    {
        "name": "Muscat",
        "area_ha": 350,
        "pct_of_plantings": 2,
        "character": "grapey, floral, orange blossom, aromatic",
        "style": "Uniquely vinified dry in Alsace unlike most Muscat wines worldwide; includes both Muscat d'Alsace (Muscat Blanc a Petits Grains) and Muscat Ottonel",
        "grand_cru_star": True,
    },
]

ALSACE_OTHER_GRAPES = [
    {
        "name": "Pinot Blanc",
        "area_ha": 3200,
        "pct_of_plantings": 21,
        "character": "clean, apple, mild, refreshing",
        "style": "Alsace's workhorse white grape; versatile and food-friendly; widely used in Cremant d'Alsace production; sometimes blended with Auxerrois",
    },
    {
        "name": "Sylvaner",
        "area_ha": 1200,
        "pct_of_plantings": 8,
        "character": "light, herbal, mineral, crisp",
        "style": "Light, refreshing everyday wine; only permitted as a Grand Cru variety in Zotzenberg; declining in plantings",
    },
    {
        "name": "Pinot Noir",
        "area_ha": 1600,
        "pct_of_plantings": 10,
        "character": "red fruit, cherry, earthy, light-bodied to medium-bodied",
        "style": "Alsace's only red grape variety; increasingly taken seriously with barrel aging and lower yields; traditionally light but modern examples can be structured",
    },
]

ALSACE_GRAND_CRUS = [
    {"name": "Altenberg de Bergbieten", "commune": "Bergbieten", "soil_type": "gypsum-marl", "area_ha": 29, "key_grapes": ["Riesling", "Gewurztraminer"]},
    {"name": "Altenberg de Bergheim", "commune": "Bergheim", "soil_type": "limestone-marl", "area_ha": 35, "key_grapes": ["Riesling", "Gewurztraminer", "Pinot Gris"],
     "notes": "One of the most historically documented Alsace vineyards, with records dating to the 13th century; produces powerful, long-lived wines"},
    {"name": "Altenberg de Wolxheim", "commune": "Wolxheim", "soil_type": "calcareous marl", "area_ha": 31, "key_grapes": ["Riesling"]},
    {"name": "Brand", "commune": "Turckheim", "soil_type": "granite", "area_ha": 58, "key_grapes": ["Riesling", "Gewurztraminer", "Pinot Gris"],
     "notes": "One of the largest Alsace Grand Crus with south-southeast exposure; granite soils produce elegant, mineral wines with great aging potential"},
    {"name": "Bruderthal", "commune": "Molsheim", "soil_type": "limestone-marl", "area_ha": 18, "key_grapes": ["Riesling", "Gewurztraminer"]},
    {"name": "Eichberg", "commune": "Eguisheim", "soil_type": "calcareous marl", "area_ha": 57, "key_grapes": ["Gewurztraminer", "Pinot Gris"]},
    {"name": "Engelberg", "commune": "Dahlenheim/Scharrachbergheim", "soil_type": "limestone-marl", "area_ha": 15, "key_grapes": ["Riesling", "Gewurztraminer"]},
    {"name": "Florimont", "commune": "Ingersheim/Katzenthal", "soil_type": "calcareous-marl", "area_ha": 21, "key_grapes": ["Gewurztraminer", "Riesling"]},
    {"name": "Frankstein", "commune": "Dambach-la-Ville", "soil_type": "granite", "area_ha": 56, "key_grapes": ["Riesling", "Gewurztraminer"]},
    {"name": "Froehn", "commune": "Zellenberg", "soil_type": "clay-marl", "area_ha": 14, "key_grapes": ["Gewurztraminer", "Muscat", "Pinot Gris"]},
    {"name": "Furstentum", "commune": "Kientzheim/Sigolsheim", "soil_type": "limestone-marl", "area_ha": 30, "key_grapes": ["Gewurztraminer", "Riesling", "Pinot Gris"],
     "notes": "A steep, south-facing slope with excellent sun exposure; known for producing rich, concentrated Gewurztraminer and late-harvest wines"},
    {"name": "Geisberg", "commune": "Ribeauville", "soil_type": "calcareous marl", "area_ha": 8.5, "key_grapes": ["Riesling"],
     "notes": "One of the smallest Alsace Grand Crus, renowned for producing taut, mineral Riesling from steep calcareous slopes above Ribeauville"},
    {"name": "Gloeckelberg", "commune": "Rodern/Saint-Hippolyte", "soil_type": "granite-clay", "area_ha": 23, "key_grapes": ["Gewurztraminer", "Pinot Gris"]},
    {"name": "Goldert", "commune": "Gueberschwihr", "soil_type": "calcareous", "area_ha": 45, "key_grapes": ["Gewurztraminer", "Muscat"],
     "notes": "Particularly renowned for its Muscat, producing some of the finest dry Muscat wines in Alsace from its east-facing calcareous slopes"},
    {"name": "Hatschbourg", "commune": "Hattstatt/Voegtlinshoffen", "soil_type": "limestone-marl with loess", "area_ha": 47, "key_grapes": ["Gewurztraminer", "Pinot Gris", "Riesling"]},
    {"name": "Hengst", "commune": "Wintzenheim", "soil_type": "calcareous marl", "area_ha": 76, "key_grapes": ["Gewurztraminer", "Pinot Gris", "Riesling"],
     "notes": "One of the largest and most powerful Grand Crus; the name means 'stallion' in Alsatian dialect; known for full-bodied, robust wines"},
    {"name": "Kaefferkopf", "commune": "Ammerschwihr", "soil_type": "granite/limestone/sandstone mix", "area_ha": 71, "key_grapes": ["Gewurztraminer", "Riesling"],
     "notes": "The only Alsace Grand Cru that officially permits blends of noble grape varieties"},
    {"name": "Kanzlerberg", "commune": "Bergheim", "soil_type": "gypsum-clay-marl", "area_ha": 3.2, "key_grapes": ["Riesling", "Gewurztraminer", "Pinot Gris"],
     "notes": "The smallest Alsace Grand Cru at only 3.2 hectares; gypsum-rich soils produce distinctive, powerful wines with excellent aging potential"},
    {"name": "Kastelberg", "commune": "Andlau", "soil_type": "schist", "area_ha": 6, "key_grapes": ["Riesling"],
     "notes": "One of only three Alsace Grand Crus with schist soils; produces intensely mineral Riesling with a distinctive flinty character"},
    {"name": "Kessler", "commune": "Guebwiller", "soil_type": "sandy clay-marl", "area_ha": 28, "key_grapes": ["Gewurztraminer", "Pinot Gris", "Riesling"]},
    {"name": "Kirchberg de Barr", "commune": "Barr", "soil_type": "calcareous marl", "area_ha": 40, "key_grapes": ["Gewurztraminer", "Riesling", "Pinot Gris"]},
    {"name": "Kirchberg de Ribeauville", "commune": "Ribeauville", "soil_type": "calcareous marl with dolomite", "area_ha": 11, "key_grapes": ["Riesling", "Pinot Gris"]},
    {"name": "Kitterlé", "commune": "Guebwiller", "soil_type": "sandstone-volcanic", "area_ha": 26, "key_grapes": ["Riesling", "Gewurztraminer", "Pinot Gris"],
     "notes": "Steep terraced vineyard above Guebwiller with three different exposures (south, southeast, southwest); produces powerful, structured wines"},
    {"name": "Mambourg", "commune": "Sigolsheim", "soil_type": "calcareous marl", "area_ha": 62, "key_grapes": ["Gewurztraminer", "Pinot Gris", "Riesling"],
     "notes": "One of the warmest Grand Cru sites with full south exposure; among the earliest Alsace vineyards documented, with records from 783 AD"},
    {"name": "Mandelberg", "commune": "Mittelwihr/Beblenheim", "soil_type": "calcareous marl", "area_ha": 22, "key_grapes": ["Gewurztraminer", "Riesling"]},
    {"name": "Marckrain", "commune": "Bennwihr/Sigolsheim", "soil_type": "calcareous marl-limestone", "area_ha": 53, "key_grapes": ["Gewurztraminer", "Pinot Gris"]},
    {"name": "Moenchberg", "commune": "Andlau/Eichhoffen", "soil_type": "calcareous clay", "area_ha": 12, "key_grapes": ["Riesling", "Pinot Gris"]},
    {"name": "Muenchberg", "commune": "Nothalten", "soil_type": "volcanic sandstone", "area_ha": 18, "key_grapes": ["Riesling", "Pinot Gris"],
     "notes": "Volcanic sandstone soils from the Permian era give wines a distinctive smoky mineral character; the name refers to monks who cultivated the site"},
    {"name": "Ollwiller", "commune": "Wuenheim", "soil_type": "sandy clay", "area_ha": 36, "key_grapes": ["Riesling", "Gewurztraminer"]},
    {"name": "Osterberg", "commune": "Ribeauville", "soil_type": "calcareous marl", "area_ha": 25, "key_grapes": ["Riesling", "Gewurztraminer", "Pinot Gris"]},
    {"name": "Pfersigberg", "commune": "Eguisheim/Wettolsheim", "soil_type": "calcareous-sandstone", "area_ha": 74, "key_grapes": ["Gewurztraminer", "Pinot Gris", "Riesling"]},
    {"name": "Pfingstberg", "commune": "Orschwihr", "soil_type": "calcareous sandstone", "area_ha": 28, "key_grapes": ["Gewurztraminer", "Pinot Gris", "Riesling"]},
    {"name": "Praelatenberg", "commune": "Kintzheim/Orschwiller", "soil_type": "volcanic granite", "area_ha": 19, "key_grapes": ["Riesling", "Gewurztraminer", "Muscat"]},
    {"name": "Rangen", "commune": "Thann/Vieux-Thann", "soil_type": "volcanic (tufo-grauwacke)", "area_ha": 19, "key_grapes": ["Riesling", "Gewurztraminer", "Pinot Gris"],
     "notes": "The southernmost and one of the steepest Alsace Grand Crus; volcanic soils give intense mineral character"},
    {"name": "Rosacker", "commune": "Hunawihr", "soil_type": "dolomitic limestone", "area_ha": 26, "key_grapes": ["Riesling"],
     "notes": "Home to the famous Clos Sainte Hune Riesling by Trimbach, one of the world's most acclaimed single-vineyard white wines"},
    {"name": "Saering", "commune": "Guebwiller", "soil_type": "limestone-sandstone", "area_ha": 27, "key_grapes": ["Riesling"]},
    {"name": "Schlossberg", "commune": "Kaysersberg/Kientzheim", "soil_type": "granite", "area_ha": 80, "key_grapes": ["Riesling"],
     "notes": "The first Alsace vineyard officially designated as Grand Cru in 1975; granitic soils produce supremely mineral Riesling"},
    {"name": "Schoenenbourg", "commune": "Riquewihr", "soil_type": "gypsum-marl", "area_ha": 53, "key_grapes": ["Riesling"],
     "notes": "One of the most prized Alsace Grand Crus for Riesling; gypsum-rich marl gives long-lived, intense wines"},
    {"name": "Sommerberg", "commune": "Niedermorschwihr/Katzenthal", "soil_type": "granite", "area_ha": 28, "key_grapes": ["Riesling"],
     "notes": "The name means 'summer hill' reflecting its warm, south-facing exposure; steep granite slopes produce racy, mineral Riesling"},
    {"name": "Sonnenglanz", "commune": "Beblenheim", "soil_type": "calcareous clay-marl", "area_ha": 33, "key_grapes": ["Gewurztraminer", "Pinot Gris"]},
    {"name": "Spiegel", "commune": "Bergholtz/Guebwiller", "soil_type": "sandstone-marl", "area_ha": 18, "key_grapes": ["Gewurztraminer", "Pinot Gris", "Riesling"]},
    {"name": "Sporen", "commune": "Riquewihr", "soil_type": "clay-limestone", "area_ha": 24, "key_grapes": ["Gewurztraminer", "Pinot Gris"],
     "notes": "Heavy clay-limestone soils produce rich, opulent Gewurztraminer; one of the premier sites in the village of Riquewihr alongside Schoenenbourg"},
    {"name": "Steinert", "commune": "Pfaffenheim/Westhalten", "soil_type": "limestone", "area_ha": 39, "key_grapes": ["Gewurztraminer", "Pinot Gris", "Riesling"]},
    {"name": "Steingrubler", "commune": "Wettolsheim", "soil_type": "calcareous-sandstone", "area_ha": 23, "key_grapes": ["Gewurztraminer", "Riesling"]},
    {"name": "Steinklotz", "commune": "Marlenheim", "soil_type": "limestone", "area_ha": 41, "key_grapes": ["Pinot Noir"],
     "notes": "One of the few Alsace Grand Crus known primarily for Pinot Noir; Jurassic limestone in the northern sector of the Alsace vineyard route"},
    {"name": "Vorbourg", "commune": "Rouffach/Westhalten", "soil_type": "limestone-sandstone", "area_ha": 73, "key_grapes": ["Riesling", "Gewurztraminer", "Pinot Gris"],
     "notes": "One of the largest Grand Crus; south-facing slopes with excellent warmth and drainage; includes the famous Clos Saint-Landelin monopole"},
    {"name": "Wiebelsberg", "commune": "Andlau", "soil_type": "sandstone", "area_ha": 13, "key_grapes": ["Riesling"]},
    {"name": "Wineck-Schlossberg", "commune": "Katzenthal/Ammerschwihr", "soil_type": "granite", "area_ha": 27, "key_grapes": ["Riesling"]},
    {"name": "Winzenberg", "commune": "Blienschwiller", "soil_type": "granite", "area_ha": 19, "key_grapes": ["Riesling", "Gewurztraminer"]},
    {"name": "Zinnkoepfle", "commune": "Soultzmatt/Westhalten", "soil_type": "limestone-sandstone", "area_ha": 68, "key_grapes": ["Gewurztraminer", "Riesling", "Pinot Gris"],
     "notes": "A large, warm, south-facing Grand Cru; the name means 'sun head' in Alsatian dialect; one of the driest sites in Alsace with less than 500 mm annual rainfall"},
    {"name": "Zotzenberg", "commune": "Mittelbergheim", "soil_type": "calcareous marl", "area_ha": 36, "key_grapes": ["Sylvaner", "Riesling", "Gewurztraminer"],
     "notes": "The only Alsace Grand Cru where Sylvaner is a permitted variety"},
]


# ==============================================================================
# KNOWLEDGE BASE -- Grape Variety Profiles
# ==============================================================================

GRAPE_PROFILES = [
    # ---- Rhone Grapes ----
    {
        "name": "Syrah",
        "region_context": "Northern Rhone",
        "color": "red",
        "character": "pepper, dark fruit, violet, smoke, olive",
        "area_france_ha": 67000,
        "key_facts": [
            "Syrah is the sole permitted red grape variety in the Northern Rhone appellations of Hermitage, Cornas, Cote-Rotie, Saint-Joseph, and Crozes-Hermitage.",
            "DNA analysis has proven that Syrah originated from a natural cross between Dureza (from the Ardeche) and Mondeuse Blanche (from Savoie), disproving theories of origins in Shiraz, Persia.",
            "In Cote-Rotie, Syrah may be co-fermented with up to 20% Viognier, which stabilizes color and adds aromatic complexity.",
            "Syrah is inherently vigorous and prefers well-drained, poor soils; it is prone to coulure (poor fruit set) in cold, wet spring weather.",
        ],
        "tags": ["northern_rhone", "syrah"],
    },
    {
        "name": "Grenache",
        "region_context": "Southern Rhone",
        "color": "red",
        "character": "red fruit, herbs, white pepper, high alcohol, spice",
        "area_france_ha": 81000,
        "key_facts": [
            "Grenache is the backbone grape of the Southern Rhone Valley, forming the dominant variety in Chateauneuf-du-Pape, Gigondas, Vacqueyras, and Cotes du Rhone blends.",
            "Grenache is naturally high in sugar and low in color and tannin, often requiring blending with Syrah (for color and structure) and Mourvedre (for tannin and depth).",
            "Grenache thrives in hot, dry, windy conditions and is particularly well-suited to the mistral wind of the Southern Rhone, which dries the grapes and reduces disease pressure.",
            "Old-vine Grenache (vieilles vignes) in the Southern Rhone can produce wines of remarkable concentration, with some bush-trained vines exceeding 100 years of age.",
            "Grenache is of Spanish origin, known as Garnacha in Spain, and is one of the most widely planted red grape varieties in the world.",
        ],
        "tags": ["southern_rhone", "grenache"],
    },
    {
        "name": "Mourvedre",
        "region_context": "Southern Rhone",
        "color": "red",
        "character": "dark fruit, earth, leather, game, black pepper",
        "area_france_ha": 10000,
        "key_facts": [
            "Mourvedre contributes structure, color, tannin, and earthy complexity to Southern Rhone blends, particularly in Chateauneuf-du-Pape and Gigondas.",
            "Mourvedre requires abundant heat and sunlight to ripen fully and is one of the last varieties harvested in the Southern Rhone.",
            "In the Southern Rhone, Mourvedre is typically blended with Grenache and Syrah in the classic GSM (Grenache-Syrah-Mourvedre) combination.",
            "Mourvedre is known as Monastrell in Spain, where it is widely planted in Jumilla, Yecla, and Alicante.",
        ],
        "tags": ["southern_rhone", "mourvedre"],
    },
    {
        "name": "Viognier",
        "region_context": "Northern Rhone",
        "color": "white",
        "character": "apricot, peach, blossom, rich, low acidity",
        "area_france_ha": 6500,
        "key_facts": [
            "Viognier was nearly extinct by the 1960s, with only approximately 8 hectares remaining, almost entirely in Condrieu and Chateau-Grillet.",
            "Viognier is the exclusive grape of the Condrieu and Chateau-Grillet appellations in the Northern Rhone.",
            "In Cote-Rotie, a small proportion of Viognier is traditionally co-fermented with Syrah; the Viognier helps fix Syrah's anthocyanin pigments, resulting in more stable color.",
            "Viognier must be harvested at optimal ripeness; picked too early it lacks aromatic expression, picked too late it becomes heavy and flabby with insufficient acidity.",
        ],
        "tags": ["northern_rhone", "viognier"],
    },
    {
        "name": "Marsanne",
        "region_context": "Northern Rhone",
        "color": "white",
        "character": "almond, waxy, white peach, marzipan, honeysuckle",
        "area_france_ha": 3700,
        "key_facts": [
            "Marsanne is the principal white grape of Hermitage, Saint-Joseph, Crozes-Hermitage, and Saint-Peray in the Northern Rhone.",
            "Marsanne is typically blended with Roussanne; Marsanne provides weight, texture, and body while Roussanne contributes acidity and aromatic complexity.",
            "White Hermitage made from Marsanne and Roussanne is one of the most long-lived white wines in the world, capable of aging for 30-50 years.",
            "Marsanne tends to produce wines with a rich, waxy texture and relatively low acidity, which is why it benefits from the higher-acid Roussanne in blends.",
        ],
        "tags": ["northern_rhone", "marsanne"],
    },
    {
        "name": "Roussanne",
        "region_context": "Northern Rhone",
        "color": "white",
        "character": "herbal tea, pear, lime blossom, mineral, aromatic",
        "area_france_ha": 2000,
        "key_facts": [
            "Roussanne is the more aromatic and acidic partner to Marsanne in Northern Rhone white blends.",
            "The name Roussanne comes from the russet (roux) color of the grape skins at harvest.",
            "Roussanne is more difficult to grow than Marsanne, being susceptible to powdery mildew and wind damage, which limits its planting.",
            "Roussanne is also a permitted white variety in Chateauneuf-du-Pape and several other Southern Rhone appellations.",
        ],
        "tags": ["northern_rhone", "roussanne"],
    },
    {
        "name": "Cinsault",
        "region_context": "Southern Rhone",
        "color": "red",
        "character": "red fruit, floral, light, low tannin",
        "area_france_ha": 17000,
        "key_facts": [
            "Cinsault is a key component in Tavel rose, contributing delicacy, perfume, and light fruit character.",
            "Cinsault produces relatively light-colored, low-tannin wines and is typically used as a blending grape rather than on its own in the Rhone.",
            "Cinsault was crossed with Pinot Noir in South Africa to create Pinotage in 1925.",
        ],
        "tags": ["southern_rhone", "cinsault"],
    },
    {
        "name": "Counoise",
        "region_context": "Southern Rhone",
        "color": "red",
        "character": "spice, freshness, pepper, moderate tannin",
        "area_france_ha": 600,
        "key_facts": [
            "Counoise is one of the 13 permitted grape varieties of Chateauneuf-du-Pape.",
            "Counoise adds peppery spice and fresh acidity to Southern Rhone blends without contributing heavy tannin or color.",
            "Chateau de Beaucastel is notably one of the few Chateauneuf-du-Pape producers to include Counoise as a significant component in their red blend.",
        ],
        "tags": ["southern_rhone", "counoise"],
    },

    # ---- Loire Grapes ----
    {
        "name": "Chenin Blanc",
        "region_context": "Loire Valley",
        "color": "white",
        "character": "apple, quince, honey, wool lanolin, chamomile, mineral",
        "area_loire_ha": 10000,
        "key_facts": [
            "Chenin Blanc is the most versatile white grape in the Loire Valley, producing wines ranging from bone-dry (Savennieres) to lusciously sweet (Quarts de Chaume) to sparkling (Vouvray mousseux).",
            "Chenin Blanc is the sole permitted grape in Vouvray, Montlouis-sur-Loire, Savennieres, Quarts de Chaume, Bonnezeaux, and Coteaux du Layon.",
            "Chenin Blanc's high natural acidity allows sweet Loire wines to age for many decades, with top Vouvray moelleux and Quarts de Chaume capable of evolving for 50 or more years.",
            "Chenin Blanc is highly susceptible to botrytis cinerea, which in the autumn mists of the Layon and Loire valleys creates the conditions for noble rot essential to the great sweet wines.",
            "Chenin Blanc is believed to have originated in the Anjou region of the Loire Valley, with documented plantings dating back to the 9th century.",
        ],
        "tags": ["loire", "chenin_blanc"],
    },
    {
        "name": "Melon de Bourgogne",
        "region_context": "Pays Nantais",
        "color": "white",
        "character": "citrus, saline, mineral, green apple, neutral",
        "area_loire_ha": 8000,
        "key_facts": [
            "Melon de Bourgogne is the only permitted grape variety for Muscadet and its sub-appellations in the Pays Nantais.",
            "Melon de Bourgogne was brought to the Nantais from Burgundy after the devastating frost of 1709 because of its superior cold hardiness.",
            "Sur lie aging (on the fine lees) is the defining technique for quality Muscadet, adding body, texture, and a slight prickle of residual CO2.",
            "DNA analysis has confirmed that Melon de Bourgogne is a cross between Pinot and Gouais Blanc, making it a half-sibling of Chardonnay.",
        ],
        "tags": ["pays_nantais", "melon_de_bourgogne"],
    },
    {
        "name": "Cabernet Franc",
        "region_context": "Loire Valley",
        "color": "red",
        "character": "raspberry, violet, green pepper (if under-ripe), graphite, tobacco",
        "area_loire_ha": 15000,
        "key_facts": [
            "Cabernet Franc is the Loire Valley's premier red grape variety, dominating the appellations of Chinon, Bourgueil, Saint-Nicolas-de-Bourgueil, and Saumur-Champigny.",
            "Loire Cabernet Franc is typically lighter and more aromatic than Bordeaux expressions, emphasizing varietal purity over oak or blending.",
            "Cabernet Franc ripens earlier than Cabernet Sauvignon, making it better suited to the cooler Loire climate where Cabernet Sauvignon often fails to reach full maturity.",
            "Cabernet Franc is one of the parent varieties of Cabernet Sauvignon, which is a natural cross of Cabernet Franc and Sauvignon Blanc.",
        ],
        "tags": ["loire", "cabernet_franc"],
    },
    {
        "name": "Sauvignon Blanc",
        "region_context": "Centre Loire",
        "color": "white",
        "character": "gooseberry, citrus, mineral, grassy, flinty",
        "area_facts": [
            "Sauvignon Blanc is the dominant grape variety of the Centre Loire appellations of Sancerre, Pouilly-Fume, Menetou-Salon, Quincy, and Reuilly.",
            "Sancerre and Pouilly-Fume are considered the benchmarks for Sauvignon Blanc worldwide, producing wines with distinctive mineral and flinty character.",
            "The silex (flint) soils of Pouilly-Fume impart a characteristic smoky, gunflint note to Sauvignon Blanc that is unique to the appellation.",
            "Sauvignon Blanc in the Centre Loire is always vinified as a dry, unoaked wine, in contrast to barrel-fermented styles seen in Bordeaux or California.",
        ],
        "tags": ["centre_loire", "sauvignon_blanc"],
    },
]


# ==============================================================================
# KNOWLEDGE BASE -- Classification Systems
# ==============================================================================

CLASSIFICATION_FACTS = [
    # Rhone classifications
    "The Rhone Valley appellation hierarchy has four tiers: Cotes du Rhone (regional), Cotes du Rhone Villages (95 communes), Cotes du Rhone Villages with named commune (22 villages), and Crus (17 named appellations).",
    "The 17 Cru appellations of the Rhone Valley are Cote-Rotie, Condrieu, Chateau-Grillet, Hermitage, Crozes-Hermitage, Saint-Joseph, Cornas, and Saint-Peray in the north, and Chateauneuf-du-Pape, Gigondas, Vacqueyras, Beaumes-de-Venise, Rasteau, Vinsobres, Lirac, Tavel, and Cairanne in the south.",
    "Cairanne was promoted from Cotes du Rhone Villages to full Cru status in 2016, becoming the 17th Cru of the Rhone Valley.",
    "The Northern Rhone and Southern Rhone are separated by approximately 40 km of non-vineyard land between the appellations of Saint-Peray in the north and the beginning of the Cotes du Rhone south of Montelimar.",
    "Chateauneuf-du-Pape was one of the first appellations granted AOC status in France in 1936, and its classification rules served as a template for the broader AOC system.",
    "Tavel is the only French appellation exclusively dedicated to rose wine production.",
    "Chateau-Grillet is one of the smallest AOC appellations in France at approximately 3.8 hectares, and is a single-estate monopole within the Condrieu zone.",

    # Loire classifications
    "The Loire Valley spans approximately 1,000 km from the Atlantic at Nantes to the Massif Central near Saint-Etienne, making it France's longest wine river.",
    "The Loire Valley is divided into four major sub-regions from west to east: Pays Nantais, Anjou-Saumur, Touraine, and Centre Loire (also called Nivernais or Central Vineyards).",
    "Quarts de Chaume was elevated to Grand Cru AOC status in 2011, the first and only Grand Cru designation in the Loire Valley.",
    "Quincy holds the distinction of being the first Loire Valley appellation to receive AOC status, in 1936, the same year as Sancerre and Chateauneuf-du-Pape.",
    "The Muscadet Cru Communaux system, established between 2011 and 2019, recognizes ten named crus based on distinct geological terroir, each requiring extended sur lie aging.",
    "Cremant de Loire is the Loire Valley's regional sparkling wine appellation, requiring traditional-method production primarily from Chenin Blanc with Chardonnay and Cabernet Franc permitted.",

    # Alsace classifications
    "Alsace Grand Cru AOC recognizes 51 named vineyard sites, each with specific permitted grape varieties, maximum yields, and minimum ripeness levels.",
    "The four noble grape varieties of Alsace, permitted in all 51 Grand Crus, are Riesling, Gewurztraminer, Pinot Gris, and Muscat.",
    "Kaefferkopf in Ammerschwihr is the only Alsace Grand Cru that officially permits blends of noble grape varieties on the label.",
    "Zotzenberg in Mittelbergheim is the only Alsace Grand Cru where Sylvaner is a permitted variety.",
    "Schlossberg in Kaysersberg was the first Alsace vineyard officially designated as Grand Cru, in 1975.",
    "Vendange Tardive (VT) in Alsace requires minimum potential alcohol levels of 14.3% for Riesling and Muscat, and 15.3% for Gewurztraminer and Pinot Gris, and cannot be chaptalised.",
    "Selection de Grains Nobles (SGN) in Alsace requires minimum potential alcohol levels of 16.4% for Riesling and Muscat, and 17.6% for Gewurztraminer and Pinot Gris.",
    "Cremant d'Alsace is the largest appellation for traditional-method sparkling wine in France outside Champagne, using principally Pinot Blanc, Riesling, Pinot Gris, and Chardonnay.",
    "Alsace is the only major French wine region where varietal labeling (naming the grape on the label) is the standard practice rather than the exception.",
    "Unlike most French wines which use Burgundy or Bordeaux-shaped bottles, Alsace wines are traditionally bottled in the tall, slender flute d'Alsace, protected by regional regulation since 1972.",

    # Additional terroir and historical facts
    "The mistral is the dominant wind of the Southern Rhone Valley, a cold, dry, northerly wind that can reach speeds exceeding 100 km/h, reducing disease pressure but stressing vines.",
    "The galets roules (large, rounded river stones) of Chateauneuf-du-Pape were deposited by the ancient Rhone and Durance rivers during the Quaternary period and store heat during the day to radiate back to vines at night.",
    "White Hermitage made from Marsanne and Roussanne is one of the longest-lived white wines in the world, with top examples capable of aging for 50 years or more.",
    "The Northern Rhone is one of the most ancient winegrowing regions in France, with evidence of viticulture dating to the 1st century AD under Roman cultivation.",
    "The Southern Rhone vineyards around Avignon gained prestige in the 14th century when the papacy relocated to Avignon and planted extensive vineyards, giving rise to Chateauneuf-du-Pape (New Castle of the Pope).",
    "Condrieu and Chateau-Grillet nearly disappeared in the mid-20th century due to rural depopulation and the near-extinction of Viognier; by the 1960s, Condrieu had fewer than 10 hectares planted.",
    "The Loire Valley produces wines in all styles: dry white, sweet white, red, rose, sparkling (Cremant de Loire, Vouvray, Saumur), and even vin doux naturel, making it France's most stylistically diverse wine region.",
    "Tuffeau limestone, the soft white chalk that characterizes the Anjou-Saumur and Touraine sub-regions, is the same stone used to build the chateaux of the Loire Valley and provides ideal natural caves for wine aging.",
    "The Coteaux du Layon and its sub-appellations (Quarts de Chaume, Bonnezeaux, Chaume Premier Cru) produce some of France's greatest sweet wines from botrytis-affected Chenin Blanc.",
    "Sancerre and Pouilly-Fume face each other across the Loire River, sharing the same Kimmeridgian limestone terroir but producing subtly different expressions of Sauvignon Blanc.",
    "The Pays Nantais sub-region lies at the western end of the Loire Valley near the Atlantic coast, and its Muscadet wines reflect the maritime influence with saline, mineral character.",
    "Alsace changed hands between France and Germany multiple times (1871, 1918, 1940, 1945), and its winemaking traditions reflect both French and Germanic influences.",
    "The Vosges mountain rain shadow creates such dry conditions in Alsace that Colmar, in the heart of the vineyard, is one of the driest cities in France.",
    "Alsace Grand Cru vineyards represent approximately 4% of total Alsace production but command significantly higher prices due to stricter yield limits and site-specific regulations.",
    "The total area of all 51 Alsace Grand Cru vineyards combined is approximately 1,600 hectares, ranging from 3.2 hectares (Kanzlerberg) to 80 hectares (Schlossberg).",
    "Vendange Tardive and Selection de Grains Nobles wines in Alsace may not be chaptalised (have sugar added), ensuring that their sweetness comes entirely from the grape.",
    "In the Northern Rhone, Syrah is always vinified as a single variety or with a small proportion of white grapes, never blended with other red varieties as in the Southern Rhone.",
    "The Dentelles de Montmirail limestone peaks in the Southern Rhone create a unique microclimate for the appellations of Gigondas, Vacqueyras, and Beaumes-de-Venise, providing altitude-driven cooling.",
    "Vin Doux Naturel production in Rasteau and Beaumes-de-Venise involves arresting fermentation by adding grape spirit (mutage), preserving natural grape sugars.",
    "The Muscadet sur lie technique requires that wine remain on its fine lees (dead yeast cells) from fermentation until bottling, typically from November through March, without racking.",
    "Savennieres is considered one of the greatest dry white wine appellations in the world, producing powerful, mineral-driven Chenin Blanc that can age for 20 years or more.",
    "Vouvray moelleux (sweet) wines from exceptional botrytis vintages are among the most long-lived white wines in the world, with examples from the 1940s and 1950s still drinking superbly.",
    "The Cremant d'Alsace appellation, established in 1976, has grown to become the second-largest sparkling wine appellation in France after Champagne, producing over 30 million bottles annually.",
    "The Rhone Valley is France's second-largest AOC wine-producing region after Bordeaux, with approximately 77,000 hectares of vineyard across six departments.",
    "The Hermitage hill is composed of several distinct geological formations, with granite on top (Les Bessards), loess and alluvial deposits in the middle (Le Meal), and clay-limestone at the base (L'Hermite, Les Greffieux).",
    "In Cornas, the name derives from the Celtic word for 'scorched earth', reflecting the hot, sun-baked character of its south-facing amphitheater of vineyards.",
    "The Muscadet region was historically known for producing thin, acidic wines until the introduction of the sur lie technique and cru communaux system elevated quality and recognition.",
    "Pinot Gris was formerly labeled as Tokay d'Alsace or Tokay-Pinot Gris in Alsace until EU regulations required the exclusive use of the name Pinot Gris from 2007 to avoid confusion with Hungarian Tokaji.",
    "The Coulee de Serrant and Roche aux Moines are two celebrated sub-appellations within Savennieres, with Coulee de Serrant being one of France's rare single-vineyard AOCs.",
    "The traditional bush-trained (gobelet) vines of the Southern Rhone are particularly well-adapted to the mistral wind, their low training keeping fruit close to the warm, stony ground.",
    "The Alsace Wine Route (Route des Vins d'Alsace), established in 1953, is one of the oldest wine tourist routes in France, stretching 170 km through 70 picturesque villages.",
    "Cairanne, promoted to Cru status in 2016, was the most recent addition to the Rhone Cru appellations, recognized for its exceptional terroir of clay-limestone and galets roules at the foot of the Massif d'Uchaux.",
    "The Chenin Blanc grape is known as Pineau de la Loire in the Loire Valley, reflecting its deep historical roots in the region.",
    "Clairette de Die, a sparkling wine appellation in the Diois area of the Rhone, uses the ancestral method (methode dioise ancestrale) with Muscat Blanc a Petits Grains, distinct from the traditional method used elsewhere.",
    "The Cotes du Rhone Villages appellation requires stricter production standards than basic Cotes du Rhone, including lower maximum yields (typically 42 hl/ha vs 51 hl/ha) and higher minimum alcohol.",
]


# ==============================================================================
# HELPER -- Fact builder
# ==============================================================================


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
    """Register and return the source ID."""
    return ensure_source(
        name=SOURCE["name"],
        url=SOURCE["url"],
        source_type=SOURCE["source_type"],
        tier=SOURCE["tier"],
        language=SOURCE["language"],
    )


# ==============================================================================
# FACT BUILDERS -- Rhone
# ==============================================================================


def _build_rhone_facts(source_id: str) -> list[dict]:
    """Build facts about Rhone Valley appellations with detailed terroir."""
    facts = []

    for app in RHONE_APPELLATIONS:
        name = app["name"]
        sub = app["sub_region"]
        entities = [{"type": "appellation", "name": name}]
        base_tags = ["france", "rhone"] + app.get("tags", [])

        # Sub-region membership
        facts.append(_make_fact(
            f"{name} is an AOC appellation in the {sub} of France's Rhone Valley.",
            domain="wine_regions",
            source_id=source_id,
            subdomain="rhone_valley",
            entities=entities,
            tags=base_tags + ["appellation"],
        ))

        # Meaning / etymology
        if app.get("meaning"):
            facts.append(_make_fact(
                f"The name Cote-Rotie translates to '{app['meaning']}' in French, referring to its steep, sun-baked slopes.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="rhone_valley",
                entities=entities,
                tags=base_tags + ["etymology"],
            ))

        # Grape varieties (red)
        if app.get("grapes_red"):
            grapes_str = ", ".join(app["grapes_red"])
            grape_ent = entities + [{"type": "grape", "name": g} for g in app["grapes_red"]]
            facts.append(_make_fact(
                f"The permitted red grape varieties for {name} AOC are {grapes_str}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="appellation_grapes",
                entities=grape_ent,
                tags=base_tags + ["grapes"],
            ))

        # Grape varieties (white)
        if app.get("grapes_white"):
            grapes_str = ", ".join(app["grapes_white"])
            grape_ent = entities + [{"type": "grape", "name": g} for g in app["grapes_white"]]
            facts.append(_make_fact(
                f"The permitted white grape varieties for {name} AOC are {grapes_str}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="appellation_grapes",
                entities=grape_ent,
                tags=base_tags + ["grapes"],
            ))

        # Blend rules
        if app.get("blend_rules"):
            facts.append(_make_fact(
                f"The blend rules for {name} AOC specify: {app['blend_rules']}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="regulations",
                entities=entities,
                tags=base_tags + ["regulations", "blend"],
            ))

        # Soil types
        if app.get("soil_types") and app["soil_types"] != ["varied"]:
            soil_str = ", ".join(app["soil_types"])
            facts.append(_make_fact(
                f"The predominant soil types in the {name} appellation include {soil_str}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="terroir",
                entities=entities,
                tags=base_tags + ["soil", "terroir"],
            ))

        # Soil details
        if app.get("soil_details"):
            facts.append(_make_fact(
                f"{app['soil_details']}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="terroir",
                entities=entities,
                tags=base_tags + ["soil", "terroir"],
            ))

        # Elevation
        if app.get("elevation_range"):
            facts.append(_make_fact(
                f"Vineyards in the {name} appellation are planted at elevations of {app['elevation_range']}.",
                domain="viticulture",
                source_id=source_id,
                subdomain="terrain",
                entities=entities,
                tags=base_tags + ["elevation"],
            ))

        # Vineyard area
        if app.get("vineyard_area_ha"):
            area = app["vineyard_area_ha"]
            area_str = f"{area:,}" if isinstance(area, int) else str(area)
            facts.append(_make_fact(
                f"The {name} appellation covers approximately {area_str} hectares of vineyard.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="statistics",
                entities=entities,
                confidence=0.95,
                tags=base_tags + ["area", "statistics"],
            ))

        # Climate
        if app.get("climate"):
            facts.append(_make_fact(
                f"The {name} appellation has a {app['climate']} climate.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="climate",
                entities=entities,
                tags=base_tags + ["climate"],
            ))

        # Terroir notes
        if app.get("terroir_notes"):
            facts.append(_make_fact(
                f"{app['terroir_notes']}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="terroir",
                entities=entities,
                tags=base_tags + ["terroir"],
            ))

        # Notable lieux-dits
        if app.get("notable_lieux_dits"):
            ld_str = ", ".join(app["notable_lieux_dits"])
            facts.append(_make_fact(
                f"Notable lieux-dits in {name} include {ld_str}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="terroir",
                entities=entities,
                tags=base_tags + ["lieux_dits"],
            ))

        # Wine colors
        if app.get("wine_colors"):
            colors_str = ", ".join(app["wine_colors"])
            facts.append(_make_fact(
                f"The {name} appellation produces {colors_str} wines.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="wine_styles",
                entities=entities,
                tags=base_tags + ["wine_styles"],
            ))

        # Permitted varieties detail (Chateauneuf)
        if app.get("permitted_varieties_count"):
            facts.append(_make_fact(
                f"Chateauneuf-du-Pape permits 13 grape varieties, the most of any French AOC: Grenache, Syrah, Mourvedre, Cinsault, Counoise, Muscardin, Vaccarese, Terret Noir, Grenache Blanc, Clairette, Bourboulenc, Roussanne, and Picardan.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="regulations",
                entities=entities + [{"type": "grape", "name": g} for g in app["permitted_varieties"]],
                tags=base_tags + ["regulations", "grape_varieties"],
            ))

        # Cru communaux detail
        if app.get("crus"):
            crus_str = ", ".join(app["crus"])
            facts.append(_make_fact(
                f"The named crus of {name} are {crus_str}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="classification",
                entities=entities,
                tags=base_tags + ["crus"],
            ))

    return facts


# ==============================================================================
# FACT BUILDERS -- Loire
# ==============================================================================


def _build_loire_facts(source_id: str) -> list[dict]:
    """Build facts about Loire Valley appellations with detailed terroir."""
    facts = []

    for app in LOIRE_APPELLATIONS:
        name = app["name"]
        sub = app["sub_region"]
        entities = [{"type": "appellation", "name": name}]
        base_tags = ["france", "loire"] + app.get("tags", [])

        # Sub-region membership
        facts.append(_make_fact(
            f"{name} is an AOC appellation in the {sub} sub-region of France's Loire Valley.",
            domain="wine_regions",
            source_id=source_id,
            subdomain="loire_valley",
            entities=entities,
            tags=base_tags + ["appellation"],
        ))

        # Grape varieties (white)
        if app.get("grapes_white"):
            grapes_str = ", ".join(app["grapes_white"])
            grape_ent = entities + [{"type": "grape", "name": g} for g in app["grapes_white"]]
            facts.append(_make_fact(
                f"The permitted white grape varieties for {name} AOC are {grapes_str}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="appellation_grapes",
                entities=grape_ent,
                tags=base_tags + ["grapes"],
            ))

        # Grape varieties (red)
        if app.get("grapes_red"):
            grapes_str = ", ".join(app["grapes_red"])
            grape_ent = entities + [{"type": "grape", "name": g} for g in app["grapes_red"]]
            facts.append(_make_fact(
                f"The permitted red grape varieties for {name} AOC are {grapes_str}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="appellation_grapes",
                entities=grape_ent,
                tags=base_tags + ["grapes"],
            ))

        # Grape varieties (rose - for Reuilly)
        if app.get("grapes_rose"):
            grapes_str = ", ".join(app["grapes_rose"])
            grape_ent = entities + [{"type": "grape", "name": g} for g in app["grapes_rose"]]
            facts.append(_make_fact(
                f"The permitted rose grape variety for {name} AOC is {grapes_str}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="appellation_grapes",
                entities=grape_ent,
                tags=base_tags + ["grapes"],
            ))

        # Blend rules
        if app.get("blend_rules"):
            facts.append(_make_fact(
                f"The blend rules for {name} AOC specify: {app['blend_rules']}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="regulations",
                entities=entities,
                tags=base_tags + ["regulations", "blend"],
            ))

        # Soil types
        if app.get("soil_types"):
            soil_str = ", ".join(app["soil_types"])
            facts.append(_make_fact(
                f"The predominant soil types in the {name} appellation include {soil_str}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="terroir",
                entities=entities,
                tags=base_tags + ["soil", "terroir"],
            ))

        # Soil details
        if app.get("soil_details"):
            facts.append(_make_fact(
                f"{app['soil_details']}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="terroir",
                entities=entities,
                tags=base_tags + ["soil", "terroir"],
            ))

        # Elevation
        if app.get("elevation_range"):
            facts.append(_make_fact(
                f"Vineyards in the {name} appellation are planted at elevations of {app['elevation_range']}.",
                domain="viticulture",
                source_id=source_id,
                subdomain="terrain",
                entities=entities,
                tags=base_tags + ["elevation"],
            ))

        # Vineyard area
        if app.get("vineyard_area_ha"):
            area = app["vineyard_area_ha"]
            area_str = f"{area:,}" if isinstance(area, int) else str(area)
            facts.append(_make_fact(
                f"The {name} appellation covers approximately {area_str} hectares of vineyard.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="statistics",
                entities=entities,
                confidence=0.95,
                tags=base_tags + ["area", "statistics"],
            ))

        # Climate
        if app.get("climate"):
            facts.append(_make_fact(
                f"The {name} appellation has a {app['climate']} climate.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="climate",
                entities=entities,
                tags=base_tags + ["climate"],
            ))

        # Terroir notes
        if app.get("terroir_notes"):
            facts.append(_make_fact(
                f"{app['terroir_notes']}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="terroir",
                entities=entities,
                tags=base_tags + ["terroir"],
            ))

        # Wine colors
        if app.get("wine_colors"):
            colors_str = ", ".join(app["wine_colors"])
            facts.append(_make_fact(
                f"The {name} appellation produces {colors_str} wines.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="wine_styles",
                entities=entities,
                tags=base_tags + ["wine_styles"],
            ))

        # Named crus
        if app.get("crus"):
            crus_str = ", ".join(app["crus"])
            facts.append(_make_fact(
                f"The ten named Muscadet Cru Communaux are {crus_str}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="classification",
                entities=entities,
                tags=base_tags + ["crus"],
            ))

    return facts


# ==============================================================================
# FACT BUILDERS -- Alsace
# ==============================================================================


def _build_alsace_facts(source_id: str) -> list[dict]:
    """Build facts about Alsace: general region, Grand Crus, and grapes."""
    facts = []
    base_tags = ["france", "alsace"]

    # ---- General Alsace facts ----
    gen = ALSACE_GENERAL
    region_ent = [{"type": "region", "name": "Alsace"}]

    facts.append(_make_fact(
        f"The Alsace wine region covers approximately {gen['vineyard_area_ha']:,} hectares of vineyard along the eastern foothills of the Vosges mountains.",
        domain="wine_regions",
        source_id=source_id,
        subdomain="alsace",
        entities=region_ent,
        confidence=0.95,
        tags=base_tags + ["area", "statistics"],
    ))

    facts.append(_make_fact(
        gen["vosges_effect"],
        domain="wine_regions",
        source_id=source_id,
        subdomain="climate",
        entities=region_ent,
        tags=base_tags + ["climate", "vosges"],
    ))

    facts.append(_make_fact(
        gen["geological_mosaic"],
        domain="wine_regions",
        source_id=source_id,
        subdomain="terroir",
        entities=region_ent,
        tags=base_tags + ["terroir", "geology"],
    ))

    facts.append(_make_fact(
        gen["aoc_hierarchy"],
        domain="wine_regions",
        source_id=source_id,
        subdomain="classification",
        entities=region_ent,
        tags=base_tags + ["classification"],
    ))

    facts.append(_make_fact(
        gen["vt_sgn"],
        domain="wine_regions",
        source_id=source_id,
        subdomain="classification",
        entities=region_ent,
        tags=base_tags + ["classification", "sweet_wine"],
    ))

    facts.append(_make_fact(
        gen["vt_requirement"],
        domain="wine_regions",
        source_id=source_id,
        subdomain="classification",
        entities=region_ent,
        tags=base_tags + ["classification", "vendange_tardive"],
    ))

    facts.append(_make_fact(
        gen["sgn_requirement"],
        domain="wine_regions",
        source_id=source_id,
        subdomain="classification",
        entities=region_ent,
        tags=base_tags + ["classification", "sgn"],
    ))

    facts.append(_make_fact(
        gen["stretch_description"],
        domain="wine_regions",
        source_id=source_id,
        subdomain="alsace",
        entities=region_ent,
        tags=base_tags + ["geography"],
    ))

    # ---- Noble grapes ----
    for grape in ALSACE_NOBLE_GRAPES:
        g_ent = [{"type": "grape", "name": grape["name"]}, {"type": "region", "name": "Alsace"}]
        g_tags = base_tags + ["grape_varieties", grape["name"].lower().replace(" ", "_")]

        facts.append(_make_fact(
            f"{grape['name']} accounts for approximately {grape['pct_of_plantings']}% of Alsace plantings with around {grape['area_ha']:,} hectares.",
            domain="grape_varieties",
            source_id=source_id,
            subdomain="alsace_grapes",
            entities=g_ent,
            confidence=0.95,
            tags=g_tags + ["statistics"],
        ))

        facts.append(_make_fact(
            f"Alsace {grape['name']} is characterized by {grape['character']}.",
            domain="grape_varieties",
            source_id=source_id,
            subdomain="alsace_grapes",
            entities=g_ent,
            tags=g_tags + ["character"],
        ))

        facts.append(_make_fact(
            f"{grape['style']}.",
            domain="grape_varieties",
            source_id=source_id,
            subdomain="alsace_grapes",
            entities=g_ent,
            tags=g_tags + ["style"],
        ))

    # ---- Other grapes ----
    for grape in ALSACE_OTHER_GRAPES:
        g_ent = [{"type": "grape", "name": grape["name"]}, {"type": "region", "name": "Alsace"}]
        g_tags = base_tags + ["grape_varieties", grape["name"].lower().replace(" ", "_")]

        facts.append(_make_fact(
            f"{grape['name']} accounts for approximately {grape['pct_of_plantings']}% of Alsace plantings with around {grape['area_ha']:,} hectares.",
            domain="grape_varieties",
            source_id=source_id,
            subdomain="alsace_grapes",
            entities=g_ent,
            confidence=0.95,
            tags=g_tags + ["statistics"],
        ))

        facts.append(_make_fact(
            f"{grape['style']}.",
            domain="grape_varieties",
            source_id=source_id,
            subdomain="alsace_grapes",
            entities=g_ent,
            tags=g_tags + ["style"],
        ))

        if grape.get("character"):
            facts.append(_make_fact(
                f"Alsace {grape['name']} is characterized by {grape['character']}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="alsace_grapes",
                entities=g_ent,
                tags=g_tags + ["character"],
            ))

    # ---- Grand Crus (51 vineyards) ----
    for gc in ALSACE_GRAND_CRUS:
        gc_name = gc["name"]
        gc_ent = [
            {"type": "vineyard", "name": gc_name},
            {"type": "region", "name": "Alsace"},
        ]
        gc_tags = base_tags + ["grand_cru", gc_name.lower().replace(" ", "_").replace("é", "e")]

        # Basic identity
        commune_str = gc["commune"]
        facts.append(_make_fact(
            f"{gc_name} is an Alsace Grand Cru vineyard located in the commune of {commune_str}.",
            domain="wine_regions",
            source_id=source_id,
            subdomain="alsace_grand_cru",
            entities=gc_ent,
            tags=gc_tags,
        ))

        # Soil type
        facts.append(_make_fact(
            f"The {gc_name} Grand Cru is characterized by {gc['soil_type']} soils.",
            domain="wine_regions",
            source_id=source_id,
            subdomain="terroir",
            entities=gc_ent,
            tags=gc_tags + ["soil", "terroir"],
        ))

        # Area
        area = gc["area_ha"]
        area_str = str(area)
        facts.append(_make_fact(
            f"The {gc_name} Grand Cru covers approximately {area_str} hectares.",
            domain="wine_regions",
            source_id=source_id,
            subdomain="statistics",
            entities=gc_ent,
            confidence=0.95,
            tags=gc_tags + ["area"],
        ))

        # Key grapes
        if gc.get("key_grapes"):
            grapes_str = ", ".join(gc["key_grapes"])
            grape_ent = gc_ent + [{"type": "grape", "name": g} for g in gc["key_grapes"]]
            facts.append(_make_fact(
                f"The key grape varieties of {gc_name} Grand Cru are {grapes_str}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="grand_cru_grapes",
                entities=grape_ent,
                tags=gc_tags + ["grapes"],
            ))

        # Special notes
        if gc.get("notes"):
            facts.append(_make_fact(
                f"{gc['notes']}.",
                domain="wine_regions",
                source_id=source_id,
                subdomain="alsace_grand_cru",
                entities=gc_ent,
                tags=gc_tags + ["notable"],
            ))

    return facts


# ==============================================================================
# FACT BUILDERS -- Grape Variety Profiles
# ==============================================================================


def _build_grape_variety_facts(source_id: str) -> list[dict]:
    """Build detailed grape variety profile facts for Rhone, Loire, and Alsace grapes."""
    facts = []

    for grape in GRAPE_PROFILES:
        g_name = grape["name"]
        g_ent = [{"type": "grape", "name": g_name}]
        g_tags = ["france"] + grape.get("tags", [])

        # Character
        if grape.get("character"):
            facts.append(_make_fact(
                f"{g_name} is characterized by aromas and flavors of {grape['character']}.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="grape_profiles",
                entities=g_ent,
                tags=g_tags + ["character"],
            ))

        # Area in France
        if grape.get("area_france_ha"):
            facts.append(_make_fact(
                f"{g_name} has approximately {grape['area_france_ha']:,} hectares planted in France.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="grape_profiles",
                entities=g_ent,
                confidence=0.95,
                tags=g_tags + ["statistics"],
            ))

        # Area in Loire
        if grape.get("area_loire_ha"):
            facts.append(_make_fact(
                f"{g_name} has approximately {grape['area_loire_ha']:,} hectares planted in the Loire Valley.",
                domain="grape_varieties",
                source_id=source_id,
                subdomain="grape_profiles",
                entities=g_ent,
                confidence=0.95,
                tags=g_tags + ["statistics"],
            ))

        # Key facts
        for kf in grape.get("key_facts", []):
            facts.append(_make_fact(
                kf,
                domain="grape_varieties",
                source_id=source_id,
                subdomain="grape_profiles",
                entities=g_ent,
                tags=g_tags,
            ))

        # Area facts (for Sauvignon Blanc)
        for af in grape.get("area_facts", []):
            facts.append(_make_fact(
                af,
                domain="grape_varieties",
                source_id=source_id,
                subdomain="grape_profiles",
                entities=g_ent,
                tags=g_tags,
            ))

    return facts


# ==============================================================================
# FACT BUILDERS -- Classification Systems
# ==============================================================================


def _build_classification_facts(source_id: str) -> list[dict]:
    """Build facts about AOC classification systems for Rhone, Loire, and Alsace."""
    facts = []

    for cf in CLASSIFICATION_FACTS:
        # Determine domain / entities based on content
        entities = []
        tags = ["france", "classification"]

        text_lower = cf.lower()
        if "rhone" in text_lower or "chateauneuf" in text_lower or "tavel" in text_lower or "chateau-grillet" in text_lower:
            tags.append("rhone")
            subdomain = "rhone_classification"
        elif "loire" in text_lower or "muscadet" in text_lower or "quarts de chaume" in text_lower or "quincy" in text_lower or "cremant de loire" in text_lower:
            tags.append("loire")
            subdomain = "loire_classification"
        elif "alsace" in text_lower:
            tags.append("alsace")
            subdomain = "alsace_classification"
        else:
            subdomain = "french_classification"

        facts.append(_make_fact(
            cf,
            domain="wine_regions",
            source_id=source_id,
            subdomain=subdomain,
            entities=entities,
            tags=tags,
        ))

    return facts


# ==============================================================================
# PIPELINE -- Build all, run, validate, test
# ==============================================================================


def _build_all_facts(source_id: str, data_type: str = None) -> list[dict]:
    """Build all facts, optionally filtered by type."""
    all_facts = []

    builders = {
        "rhone": _build_rhone_facts,
        "loire": _build_loire_facts,
        "alsace": _build_alsace_facts,
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
        click.echo(f"\n[DRY RUN] Would insert {len(facts)} facts from Rhone/Loire/Alsace")

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

    logger.info(f"Inserted {inserted} new facts from Rhone/Loire/Alsace (duplicates skipped)")
    logger.info(f"Total facts in database: {get_fact_count()}")

    return summary


# ==============================================================================
# VALIDATION
# ==============================================================================


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

    # (g) Overlap check with inao.py patterns
    inao_patterns = [
        r"^.+ is a French AOC appellation",
        r"^.+ AOC is located in",
        r"^The .+ appellation was granted AOC status in",
    ]
    overlap_count = 0
    for f in facts:
        for pat in inao_patterns:
            if re.match(pat, f["fact_text"]):
                overlap_count += 1
                break
    click.echo(f"\n  Potential inao.py overlaps: {overlap_count}")


# ==============================================================================
# TEST RUN
# ==============================================================================


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
        "Rhone Appellations": _build_rhone_facts,
        "Loire Appellations": _build_loire_facts,
        "Alsace Region/GC": _build_alsace_facts,
        "Grape Varieties": _build_grape_variety_facts,
        "Classifications": _build_classification_facts,
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


# ==============================================================================
# CLI
# ==============================================================================


@click.command()
@click.option("--all", "run_all_flag", is_flag=True, help="Run full extraction")
@click.option(
    "--type",
    "data_type",
    type=click.Choice(["rhone", "loire", "alsace", "grape", "classification"]),
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
    """OenoBench French Regional Scraper -- Rhone, Loire, Alsace terroir and classification data."""
    logger.add("data/logs/rhone_loire_alsace_{time}.log", rotation="10 MB")

    if list_sources:
        click.echo("\nAvailable data categories:")
        click.echo(f"  {'rhone':18s} -- {len(RHONE_APPELLATIONS)} Rhone Valley appellations (terroir, grapes, climate)")
        click.echo(f"  {'loire':18s} -- {len(LOIRE_APPELLATIONS)} Loire Valley appellations (terroir, grapes, climate)")
        click.echo(f"  {'alsace':18s} -- Alsace region + {len(ALSACE_GRAND_CRUS)} Grand Cru vineyards + grape profiles")
        click.echo(f"  {'grape':18s} -- {len(GRAPE_PROFILES)} detailed grape variety profiles")
        click.echo(f"  {'classification':18s} -- {len(CLASSIFICATION_FACTS)} classification system facts")
        click.echo(f"\nKnowledge base coverage:")
        click.echo(f"  Rhone appellations:     {len(RHONE_APPELLATIONS)}")
        click.echo(f"  Loire appellations:     {len(LOIRE_APPELLATIONS)}")
        click.echo(f"  Alsace Grand Crus:      {len(ALSACE_GRAND_CRUS)}")
        click.echo(f"  Alsace noble grapes:    {len(ALSACE_NOBLE_GRAPES)}")
        click.echo(f"  Alsace other grapes:    {len(ALSACE_OTHER_GRAPES)}")
        click.echo(f"  Grape profiles:         {len(GRAPE_PROFILES)}")
        click.echo(f"  Classification facts:   {len(CLASSIFICATION_FACTS)}")
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
