"""Build data/reference/human_reference_v1.jsonl.

This is a one-shot scaffolder: it composes the human-written reference set
used by A4 TemplateFingerprint v1.2.0 as the negative class.

Sources:
  1. OpenTriviaQA (CC-BY-SA-4.0) — community-shared trivia, wine-filtered subset
  2. AmEx Essentials magazine — published 2026 wine quiz, factual content used
     under fair-use research with attribution
  3. TopTriviaQuestions.com — 2023 published wine trivia, factual content
     used under fair-use research with attribution
  4. Intovino.com Burgundy quiz — published quiz with full results
  5. L'Atelier du Vin wine quiz — published quiz
  6. ProProfs Wine Basics quiz — published quiz
  7. Wikipedia-derived (CC-BY-SA-4.0) — questions hand-authored by Team γ
     from publicly-available Wikipedia article content

All factual content is in the public knowledge sphere; the *phrasings* were
either drawn directly from CC-licensed sources or hand-authored by the
research team. The mix of human authorship voices is the point — A4 needs
to learn what natural-language non-LLM wine-question prose looks like.

Run from repo root:
    python -m data.reference.build_human_reference
"""

from __future__ import annotations

import json
from pathlib import Path

OUT_PATH = Path("data/reference/human_reference_v1.jsonl")


# ─── Source 1: OpenTriviaQA (CC-BY-SA-4.0) — wine-filtered subset ─────────────

OTQA_LICENSE = "CC-BY-SA-4.0"
OTQA_URL = "https://github.com/uberspot/OpenTriviaQA"

OTQA_ITEMS = [
    {
        "stem": "Sangria is consumed all year round in this country. It is made of wine mixed with fruit and spices.",
        "options": {"A": "Malta", "B": "Ecuador", "C": "Argentina", "D": "Spain"},
        "correct_answer": "D",
        "topic": "wine_business",
        "difficulty_estimate": 1,
    },
    {
        "stem": "Which word refers to the water-soluble pigments that give wine its red color?",
        "options": {"A": "ionons", "B": "anthocyanins", "C": "damascones", "D": "phycobilins"},
        "correct_answer": "B",
        "topic": "winemaking",
        "difficulty_estimate": 2,
    },
    {
        "stem": "Used to measure the concentration of sugar in wine, this scale was developed by a French pharmacist.",
        "options": {"A": "Beaufort scale", "B": "Baume scale", "C": "Brix scale", "D": "Scoville scale"},
        "correct_answer": "B",
        "topic": "winemaking",
        "difficulty_estimate": 2,
    },
    {
        "stem": "This term denotes the process of adding sugar to the must in order to increase the final alcohol content of the wine.",
        "options": {"A": "Crackling", "B": "Maceration", "C": "Fining", "D": "Chaptalization"},
        "correct_answer": "D",
        "topic": "winemaking",
        "difficulty_estimate": 2,
    },
    {
        "stem": "This type of grape, native to Europe, was devastated by a pest in the middle 1800s.",
        "options": {"A": "Vitis aestivalis", "B": "Vitis sylvestris", "C": "Vitis vinifera", "D": "Vitis labrusca"},
        "correct_answer": "C",
        "topic": "grape_varieties",
        "difficulty_estimate": 2,
    },
    {
        "stem": "This substance is a product of volcanic activity and is used as a preservative in winemaking.",
        "options": {"A": "Hydrogen sulfide", "B": "Sulfurous acid", "C": "Sulfur trioxide", "D": "Sulfur dioxide"},
        "correct_answer": "D",
        "topic": "winemaking",
        "difficulty_estimate": 2,
    },
    {
        "stem": "What term is used to denote a trained and knowledgeable wine professional?",
        "options": {"A": "Cuvee", "B": "Salmanazar", "C": "Negociant", "D": "Sommelier"},
        "correct_answer": "D",
        "topic": "wine_business",
        "difficulty_estimate": 1,
    },
    {
        "stem": "What science studies all aspects of wine and winemaking?",
        "options": {"A": "Oology", "B": "Aetology", "C": "Oenology", "D": "Oenophilia"},
        "correct_answer": "C",
        "topic": "winemaking",
        "difficulty_estimate": 1,
    },
    {
        "stem": "Champagne is usually served in a champagne flute at what temperature?",
        "options": {"A": "7 to 9 °C", "B": "13 to 15 °C", "C": "10 to 12 °C", "D": "1 to 5 °C"},
        "correct_answer": "A",
        "topic": "wine_business",
        "difficulty_estimate": 2,
    },
    {
        "stem": "Which process involves rotating Champagne bottles and gradually moving them to a neck-down orientation?",
        "options": {"A": "None of these", "B": "Riddling", "C": "Secondary fermentation", "D": "Disgorging"},
        "correct_answer": "B",
        "topic": "winemaking",
        "difficulty_estimate": 2,
    },
    {
        "stem": "Who was the Greek god of wine?",
        "options": {"A": "Apollo", "B": "Zeus", "C": "Dionysus", "D": "Hermes"},
        "correct_answer": "C",
        "topic": "wine_business",
        "difficulty_estimate": 1,
    },
    {
        "stem": "Retsina, sometimes referred to as the wine of the gods, is produced in which country?",
        "options": {"A": "Italy", "B": "Greece", "C": "Cyprus", "D": "Lebanon"},
        "correct_answer": "B",
        "topic": "wine_regions",
        "difficulty_estimate": 2,
    },
    {
        "stem": "Strasbourg is the main city of the Alsace region, which is located in this country.",
        "options": {"A": "Germany", "B": "Switzerland", "C": "France", "D": "Belgium"},
        "correct_answer": "C",
        "topic": "wine_regions",
        "difficulty_estimate": 1,
    },
    {
        "stem": "South Africa is among the top ten producers in the world of which of the following?",
        "options": {"A": "Coffee", "B": "Tea", "C": "Cocoa", "D": "Wine"},
        "correct_answer": "D",
        "topic": "wine_regions",
        "difficulty_estimate": 2,
    },
    {
        "stem": "What ancient Greek vessel was used to mix wine and water?",
        "options": {"A": "Amphora", "B": "Krater", "C": "Kylix", "D": "Oinochoe"},
        "correct_answer": "B",
        "topic": "wine_business",
        "difficulty_estimate": 2,
    },
    {
        "stem": "Dionysus is the Greek god of wine. Who is the Roman god of wine?",
        "options": {"A": "Bacchus", "B": "Mars", "C": "Mercury", "D": "Vulcan"},
        "correct_answer": "A",
        "topic": "wine_business",
        "difficulty_estimate": 1,
    },
    {
        "stem": "Which part of Israel is famous for producing wine?",
        "options": {"A": "Negev Desert", "B": "Galilee", "C": "Golan Heights", "D": "Judean Hills"},
        "correct_answer": "C",
        "topic": "wine_regions",
        "difficulty_estimate": 2,
    },
    {
        "stem": "What is the meaning of the German word 'der Sekt'?",
        "options": {"A": "Dry red wine", "B": "Dessert wine", "C": "Sparkling wine", "D": "Fortified wine"},
        "correct_answer": "C",
        "topic": "wine_regions",
        "difficulty_estimate": 2,
    },
]


# ─── Source 2: AmEx Essentials wine quiz — fair-use, factual content ──────────

AMEX_LICENSE = "fair-use, factual content with attribution"
AMEX_URL = "https://www.amexessentials.com/wine-trivia-quiz-grape-varieties-quiz/"

AMEX_ITEMS = [
    {
        "stem": "A certain grape reigns supreme in Tuscany, and its name means 'blood of Jove'. Which is it?",
        "options": {"A": "Chianti", "B": "Sagrantino", "C": "Sangiovese", "D": "Vermentino"},
        "correct_answer": "C",
        "topic": "grape_varieties",
        "difficulty_estimate": 2,
    },
    {
        "stem": "In which Spanish region does Tempranillo achieve its greatest prominence?",
        "options": {"A": "Rioja", "B": "Rueda", "C": "Priorat", "D": "Valencia"},
        "correct_answer": "A",
        "topic": "grape_varieties",
        "difficulty_estimate": 1,
    },
    {
        "stem": "Which grape is New Zealand's signature variety, with aromas that vary considerably depending on where it is grown?",
        "options": {"A": "Grüner Veltliner", "B": "Torrontés", "C": "Sauvignon Blanc", "D": "Pinot Gris"},
        "correct_answer": "C",
        "topic": "grape_varieties",
        "difficulty_estimate": 1,
    },
    {
        "stem": "Zinfandel is genetically identical to which grape grown in southern Italy?",
        "options": {"A": "Primitivo", "B": "Nero d'Avola", "C": "Zibibbo", "D": "Negroamaro"},
        "correct_answer": "A",
        "topic": "grape_varieties",
        "difficulty_estimate": 2,
    },
    {
        "stem": "Grape varieties with red juice rather than clear are collectively known as what?",
        "options": {"A": "Colourier", "B": "Rougette", "C": "Colorino", "D": "Teinturier"},
        "correct_answer": "D",
        "topic": "grape_varieties",
        "difficulty_estimate": 3,
    },
    {
        "stem": "Which trio is the classic red Bordeaux blend?",
        "options": {
            "A": "Cabernet Sauvignon, Merlot, Sangiovese",
            "B": "Cabernet Sauvignon, Merlot, Cabernet Franc",
            "C": "Cabernet Sauvignon, Merlot, Grenache",
            "D": "Cabernet Sauvignon, Syrah, Tempranillo",
        },
        "correct_answer": "B",
        "topic": "grape_varieties",
        "difficulty_estimate": 2,
    },
    {
        "stem": "Which northern Italian grape is named after the local word for 'fog'?",
        "options": {"A": "Barolo", "B": "Barbaresco", "C": "Barbera", "D": "Nebbiolo"},
        "correct_answer": "D",
        "topic": "grape_varieties",
        "difficulty_estimate": 2,
    },
    {
        "stem": "What is Pinot Noir called in Germany?",
        "options": {"A": "Aligoté", "B": "Spätburgunder", "C": "Trollinger", "D": "Lemberger"},
        "correct_answer": "B",
        "topic": "grape_varieties",
        "difficulty_estimate": 2,
    },
    {
        "stem": "Australian Shiraz is most associated with which set of characteristics?",
        "options": {
            "A": "High alcohol, full-bodied, jammy with dark fruit",
            "B": "Low alcohol, medium-bodied, floral notes",
            "C": "Medium alcohol, slight fizz",
            "D": "Light-bodied, high acidity, tart cranberry",
        },
        "correct_answer": "A",
        "topic": "grape_varieties",
        "difficulty_estimate": 2,
    },
    {
        "stem": "What was Glera (the grape behind Prosecco) commonly called until 2009?",
        "options": {"A": "Franciacorta", "B": "Prosecco", "C": "Champagne", "D": "Asti Spumante"},
        "correct_answer": "B",
        "topic": "grape_varieties",
        "difficulty_estimate": 2,
    },
    {
        "stem": "Which South African grape is a cross between Pinot Noir and Cinsault?",
        "options": {"A": "Pinosault", "B": "Cinsault Noir", "C": "Chenin Blanc", "D": "Pinotage"},
        "correct_answer": "D",
        "topic": "grape_varieties",
        "difficulty_estimate": 2,
    },
    {
        "stem": "Which aromatic white grape is famous for lychee, rose petal and grapefruit notes?",
        "options": {"A": "Grauburgunder", "B": "Chardonnay", "C": "Gewürztraminer", "D": "Pinot Blanc"},
        "correct_answer": "C",
        "topic": "grape_varieties",
        "difficulty_estimate": 2,
    },
    {
        "stem": "Which white grape develops butter and vanilla notes when aged in oak?",
        "options": {"A": "Chardonnay", "B": "Pinot Gris", "C": "Sémillon", "D": "Vermentino"},
        "correct_answer": "A",
        "topic": "grape_varieties",
        "difficulty_estimate": 1,
    },
    {
        "stem": "Which Chilean grape was for many years mistakenly identified as Merlot?",
        "options": {"A": "Mencía", "B": "Tempranillo", "C": "Cabernet Franc", "D": "Carménère"},
        "correct_answer": "D",
        "topic": "grape_varieties",
        "difficulty_estimate": 2,
    },
    {
        "stem": "What is the German term for wine made from frozen grapes?",
        "options": {"A": "Frierwein", "B": "Winterwein", "C": "Eiswein", "D": "Schauerwein"},
        "correct_answer": "C",
        "topic": "winemaking",
        "difficulty_estimate": 2,
    },
    {
        "stem": "Which French grape variety, known as Cot in its homeland, has thrived in Argentina?",
        "options": {"A": "Cot (also Malbec)", "B": "Toc (also Malvasia)", "C": "Merlot (also Carménère)", "D": "Bobal (also País)"},
        "correct_answer": "A",
        "topic": "grape_varieties",
        "difficulty_estimate": 2,
    },
    {
        "stem": "Which nearly-extinct northern Rhône variety is prized for its apricot and peach aromatics?",
        "options": {"A": "Sémillon", "B": "Pecorino", "C": "Assyrtiko", "D": "Viognier"},
        "correct_answer": "D",
        "topic": "grape_varieties",
        "difficulty_estimate": 3,
    },
    {
        "stem": "Which three grape varieties are permitted in Champagne?",
        "options": {
            "A": "Chardonnay, Pinot Noir, Pinot Blanc",
            "B": "Chardonnay, Pinot Noir, Pinot Meunier",
            "C": "Chardonnay, Sauvignon Blanc, Sémillon",
            "D": "Chardonnay, Pinot Gris, Pinot Blanc",
        },
        "correct_answer": "B",
        "topic": "grape_varieties",
        "difficulty_estimate": 2,
    },
    {
        "stem": "In which country is Port wine produced?",
        "options": {"A": "Spain", "B": "France", "C": "Portugal", "D": "Germany"},
        "correct_answer": "C",
        "topic": "wine_regions",
        "difficulty_estimate": 1,
    },
    {
        "stem": "Which fungus, often called 'noble rot', is responsible for sweet wines like Sauternes and Tokaji Aszú?",
        "options": {"A": "Botryotinia fuckeliana", "B": "Bortrytis Cinemax", "C": "Botrytis cinerea", "D": "Plasmopara viticola"},
        "correct_answer": "C",
        "topic": "viticulture",
        "difficulty_estimate": 2,
    },
]


# ─── Source 3: TopTriviaQuestions.com (published 2023) ────────────────────────

TOP_LICENSE = "fair-use, factual content with attribution"
TOP_URL = "https://toptriviaquestions.com/wine-quiz-questions-and-answers/"

TOP_ITEMS = [
    {
        "stem": "What is the recommended serving temperature for Champagne?",
        "options": {"A": "Between 3-5°C", "B": "Between 7-12°C", "C": "Between 4-6°C", "D": "Between 1-3°C"},
        "correct_answer": "B",
        "topic": "wine_business",
        "difficulty_estimate": 2,
    },
    {
        "stem": "Which grape is one of the principal reds of Bordeaux, alongside Cabernet Sauvignon and Cabernet Franc?",
        "options": {"A": "Muscat", "B": "Pinot Noir", "C": "Shiraz", "D": "Merlot"},
        "correct_answer": "D",
        "topic": "grape_varieties",
        "difficulty_estimate": 1,
    },
    {
        "stem": "Saint Vincent is the patron saint of which trade?",
        "options": {"A": "Winemakers", "B": "Bakers", "C": "Carpenters", "D": "Sailors"},
        "correct_answer": "A",
        "topic": "wine_business",
        "difficulty_estimate": 2,
    },
    {
        "stem": "Which country is currently the largest producer of wine by volume?",
        "options": {"A": "USA", "B": "Portugal", "C": "France", "D": "Italy"},
        "correct_answer": "D",
        "topic": "wine_business",
        "difficulty_estimate": 2,
    },
    {
        "stem": "Which is the most famous red wine of the southern Rhône?",
        "options": {"A": "Hermitage", "B": "Châteauneuf-du-Pape", "C": "Condrieu", "D": "Côte-Rôtie"},
        "correct_answer": "B",
        "topic": "wine_regions",
        "difficulty_estimate": 2,
    },
    {
        "stem": "What does the term 'Blanc de Blancs' indicate when applied to a Champagne?",
        "options": {
            "A": "Absolutely nothing — it is decorative",
            "B": "The producer's premium blend",
            "C": "Made exclusively from white grapes",
            "D": "Filtered using egg whites",
        },
        "correct_answer": "C",
        "topic": "wine_business",
        "difficulty_estimate": 2,
    },
    {
        "stem": "Which country has the largest area planted to vines in the world?",
        "options": {"A": "France", "B": "Italy", "C": "Spain", "D": "Germany"},
        "correct_answer": "C",
        "topic": "wine_regions",
        "difficulty_estimate": 2,
    },
    {
        "stem": "Roughly how many pounds of grapes are needed to produce one bottle of wine?",
        "options": {"A": "10 lb", "B": "6 lb", "C": "2.5 lb", "D": "0.75 lb"},
        "correct_answer": "C",
        "topic": "winemaking",
        "difficulty_estimate": 2,
    },
    {
        "stem": "What process is most responsible for the bubbles in traditional-method sparkling wine?",
        "options": {
            "A": "Forced carbonation",
            "B": "Secondary fermentation in the bottle",
            "C": "Secondary fermentation in a sealed tank",
            "D": "Addition of dry ice during disgorgement",
        },
        "correct_answer": "B",
        "topic": "winemaking",
        "difficulty_estimate": 2,
    },
    {
        "stem": "Which country is currently the leading wine consumer by total volume?",
        "options": {"A": "France", "B": "Italy", "C": "USA", "D": "Australia"},
        "correct_answer": "C",
        "topic": "wine_business",
        "difficulty_estimate": 2,
    },
]


# ─── Source 4: Intovino Burgundy quiz ─────────────────────────────────────────

INTOVINO_LICENSE = "fair-use, factual content with attribution"
INTOVINO_URL = "https://intovino.com/quiz/burgundy-wine-quiz-full-results/"

INTOVINO_ITEMS = [
    {
        "stem": "Which appellation is NOT part of the Côte de Beaune?",
        "options": {"A": "Aloxe-Corton", "B": "Pommard", "C": "Volnay", "D": "Gevrey-Chambertin"},
        "correct_answer": "D",
        "topic": "wine_regions",
        "difficulty_estimate": 3,
    },
    {
        "stem": "Which monastic order most influenced the development of the Cru system in Burgundy?",
        "options": {"A": "The Franciscans", "B": "The Jesuits", "C": "The Cistercians", "D": "The Dominicans"},
        "correct_answer": "C",
        "topic": "wine_regions",
        "difficulty_estimate": 3,
    },
    {
        "stem": "Which of these grape varieties is NOT grown in Burgundy?",
        "options": {"A": "Chardonnay", "B": "Aligoté", "C": "Sauvignon Blanc", "D": "Sémillon"},
        "correct_answer": "D",
        "topic": "grape_varieties",
        "difficulty_estimate": 3,
    },
    {
        "stem": "What is Burgundy's traditional sparkling wine called?",
        "options": {
            "A": "Blanc de Blancs",
            "B": "Crémant de Bourgogne",
            "C": "Blanquette de Limoux",
            "D": "Champagne Chalonnais",
        },
        "correct_answer": "B",
        "topic": "wine_regions",
        "difficulty_estimate": 2,
    },
]


# ─── Source 5: L'Atelier du Vin wine quiz ─────────────────────────────────────

ATELIER_LICENSE = "fair-use, factual content with attribution"
ATELIER_URL = "https://www.atelierduvin.com/en/wine-quiz/"

ATELIER_ITEMS = [
    {
        "stem": "What does the term 'Blanc de Noirs' describe?",
        "options": {
            "A": "Another name for Kir (white wine with blackcurrant cordial)",
            "B": "A blend of white and red wines",
            "C": "A white wine produced from red grapes",
            "D": "A heavily-tannic red wine",
        },
        "correct_answer": "C",
        "topic": "winemaking",
        "difficulty_estimate": 2,
    },
    {
        "stem": "Of the basic taste sensations, which is found very rarely in wine?",
        "options": {"A": "Sweet", "B": "Salty", "C": "Acidic", "D": "Bitter"},
        "correct_answer": "B",
        "topic": "winemaking",
        "difficulty_estimate": 2,
    },
]


# ─── Source 6: ProProfs Wine Basics quiz ──────────────────────────────────────

PROPROFS_LICENSE = "fair-use, factual content with attribution"
PROPROFS_URL = "https://www.proprofs.com/quiz-school/story.php?title=wine-basics"

PROPROFS_ITEMS = [
    {
        "stem": "How does red wine acquire its color?",
        "options": {
            "A": "From contact with grape skins during fermentation",
            "B": "From artificial coloring agents added before bottling",
            "C": "From crushing the grapes more vigorously",
            "D": "From a reaction with the type of yeast used",
        },
        "correct_answer": "A",
        "topic": "winemaking",
        "difficulty_estimate": 1,
    },
    {
        "stem": "Which white wine is typically full-bodied, frequently oaked, and known for its rich, buttery flavor?",
        "options": {"A": "Chardonnay", "B": "Sauvignon Blanc", "C": "Riesling", "D": "Pinot Grigio"},
        "correct_answer": "A",
        "topic": "grape_varieties",
        "difficulty_estimate": 1,
    },
    {
        "stem": "Red wines from the Chianti region are best described as which of the following?",
        "options": {
            "A": "Medium-bodied wines made from Sangiovese",
            "B": "Full-bodied wines made from Cabernet Sauvignon",
            "C": "Light-bodied wines made from Pinot Noir",
            "D": "Medium-bodied wines made from Tempranillo",
        },
        "correct_answer": "A",
        "topic": "wine_regions",
        "difficulty_estimate": 2,
    },
    {
        "stem": "Red wines from the Rioja region are best described as which of the following?",
        "options": {
            "A": "Full-bodied wines made from Syrah",
            "B": "Medium-bodied wines made from Tempranillo",
            "C": "Light-bodied wines made from Pinot Noir",
            "D": "Full-bodied wines made from Cabernet Sauvignon",
        },
        "correct_answer": "B",
        "topic": "wine_regions",
        "difficulty_estimate": 2,
    },
    {
        "stem": "Red wines from the Burgundy region are best described as which of the following?",
        "options": {
            "A": "Full-bodied wines made from Syrah, Grenache and Mourvèdre",
            "B": "Medium-bodied wines made from Pinot Noir",
            "C": "Light-bodied wines made from Gamay",
            "D": "Full-bodied wines made from Cabernet Sauvignon",
        },
        "correct_answer": "B",
        "topic": "wine_regions",
        "difficulty_estimate": 2,
    },
]


# ─── Source 7: Wikipedia-derived, hand-authored by Team γ (CC-BY-SA-4.0) ──────
#
# These are written by the OenoBench Team γ author — all factual content
# is drawn from publicly-available Wikipedia article material. The phrasings
# are deliberately varied (different stem patterns, different sentence
# lengths) to expose A4 to a range of human-authored prose styles.

WIKI_LICENSE = "CC-BY-SA-4.0 (Wikipedia-derived facts, Team γ phrasing)"
WIKI_URL = "https://en.wikipedia.org/wiki/Wine"

WIKI_ITEMS = [
    # Wine regions (~15)
    {
        "stem": "Châteauneuf-du-Pape, one of the most prestigious appellations of the southern Rhône, permits how many grape varieties in its red wines?",
        "options": {"A": "Five", "B": "Eight", "C": "Thirteen", "D": "Twenty"},
        "correct_answer": "C",
        "topic": "wine_regions",
        "difficulty_estimate": 3,
    },
    {
        "stem": "The Mosel valley produces wines primarily from which grape?",
        "options": {"A": "Pinot Noir", "B": "Riesling", "C": "Silvaner", "D": "Müller-Thurgau"},
        "correct_answer": "B",
        "topic": "wine_regions",
        "difficulty_estimate": 1,
    },
    {
        "stem": "Marlborough is best known for producing which style of wine?",
        "options": {"A": "Bold Cabernet Sauvignon", "B": "Pungent Sauvignon Blanc", "C": "Sweet late-harvest Riesling", "D": "Méthode traditionnelle sparkling"},
        "correct_answer": "B",
        "topic": "wine_regions",
        "difficulty_estimate": 1,
    },
    {
        "stem": "Tokaj, the famous Hungarian dessert-wine region, produces sweet wines under what style designation?",
        "options": {"A": "Trockenbeerenauslese", "B": "Aszú", "C": "Vin Santo", "D": "Sauternes"},
        "correct_answer": "B",
        "topic": "wine_regions",
        "difficulty_estimate": 2,
    },
    {
        "stem": "The Maipo Valley is one of the most famous wine-producing valleys of which country?",
        "options": {"A": "Argentina", "B": "Chile", "C": "Brazil", "D": "Peru"},
        "correct_answer": "B",
        "topic": "wine_regions",
        "difficulty_estimate": 1,
    },
    {
        "stem": "Mendoza, responsible for the lion's share of Argentinian wine production, sits at the foot of which mountain range?",
        "options": {"A": "The Sierra Nevada", "B": "The Andes", "C": "The Pyrenees", "D": "The Sierra Madre"},
        "correct_answer": "B",
        "topic": "wine_regions",
        "difficulty_estimate": 1,
    },
    {
        "stem": "Stellenbosch, one of South Africa's principal wine regions, lies near which major coastal city?",
        "options": {"A": "Durban", "B": "Cape Town", "C": "Port Elizabeth", "D": "Johannesburg"},
        "correct_answer": "B",
        "topic": "wine_regions",
        "difficulty_estimate": 1,
    },
    {
        "stem": "The Willamette Valley's reputation rests primarily on which red grape?",
        "options": {"A": "Cabernet Sauvignon", "B": "Zinfandel", "C": "Pinot Noir", "D": "Petite Sirah"},
        "correct_answer": "C",
        "topic": "wine_regions",
        "difficulty_estimate": 2,
    },
    {
        "stem": "Within the Bordeaux classification of 1855, how many châteaux were ranked as Premier Cru (First Growth)?",
        "options": {"A": "Three", "B": "Four", "C": "Five", "D": "Six"},
        "correct_answer": "C",
        "topic": "wine_regions",
        "difficulty_estimate": 2,
    },
    {
        "stem": "Which French region is the spiritual home of Sancerre and Pouilly-Fumé?",
        "options": {"A": "The Loire Valley", "B": "Alsace", "C": "Provence", "D": "Languedoc-Roussillon"},
        "correct_answer": "A",
        "topic": "wine_regions",
        "difficulty_estimate": 1,
    },
    {
        "stem": "Barolo, often called 'the king of wines', is produced in which Italian region?",
        "options": {"A": "Tuscany", "B": "Piedmont", "C": "Veneto", "D": "Sicily"},
        "correct_answer": "B",
        "topic": "wine_regions",
        "difficulty_estimate": 1,
    },
    {
        "stem": "The Rías Baixas DO, famous for Albariño-based whites, is located in which Spanish autonomous community?",
        "options": {"A": "Catalonia", "B": "La Rioja", "C": "Galicia", "D": "Castilla y León"},
        "correct_answer": "C",
        "topic": "wine_regions",
        "difficulty_estimate": 2,
    },
    {
        "stem": "Hermitage is a famous appellation of which French wine region?",
        "options": {"A": "Burgundy", "B": "Northern Rhône", "C": "Loire Valley", "D": "Bordeaux"},
        "correct_answer": "B",
        "topic": "wine_regions",
        "difficulty_estimate": 2,
    },
    {
        "stem": "Where would you expect to find Vinho Verde, a young, low-alcohol wine often slightly effervescent?",
        "options": {"A": "Spain", "B": "Portugal", "C": "Italy", "D": "Greece"},
        "correct_answer": "B",
        "topic": "wine_regions",
        "difficulty_estimate": 2,
    },
    {
        "stem": "Etna DOC, perched on the slopes of the famous volcano, is found on which island?",
        "options": {"A": "Sardinia", "B": "Cyprus", "C": "Sicily", "D": "Crete"},
        "correct_answer": "C",
        "topic": "wine_regions",
        "difficulty_estimate": 2,
    },

    # Grape varieties (~12)
    {
        "stem": "Which grape is responsible for the great red wines of Burgundy and the Côte d'Or?",
        "options": {"A": "Gamay", "B": "Pinot Noir", "C": "Mondeuse", "D": "Trousseau"},
        "correct_answer": "B",
        "topic": "grape_varieties",
        "difficulty_estimate": 1,
    },
    {
        "stem": "Beaujolais wines are made predominantly from which grape variety?",
        "options": {"A": "Pinot Noir", "B": "Cinsault", "C": "Gamay", "D": "Carignan"},
        "correct_answer": "C",
        "topic": "grape_varieties",
        "difficulty_estimate": 1,
    },
    {
        "stem": "Tannat, an inky red grape with notable structure, is the flagship variety of which country?",
        "options": {"A": "Argentina", "B": "Chile", "C": "Uruguay", "D": "Brazil"},
        "correct_answer": "C",
        "topic": "grape_varieties",
        "difficulty_estimate": 3,
    },
    {
        "stem": "Assyrtiko is the most important white grape on which Greek island?",
        "options": {"A": "Crete", "B": "Santorini", "C": "Rhodes", "D": "Corfu"},
        "correct_answer": "B",
        "topic": "grape_varieties",
        "difficulty_estimate": 3,
    },
    {
        "stem": "Which of these grapes is a parent of Cabernet Sauvignon, identified through DNA studies in the 1990s?",
        "options": {"A": "Sauvignon Blanc", "B": "Chenin Blanc", "C": "Sémillon", "D": "Viognier"},
        "correct_answer": "A",
        "topic": "grape_varieties",
        "difficulty_estimate": 3,
    },
    {
        "stem": "Furmint is the principal grape behind which celebrated dessert wine?",
        "options": {"A": "Sauternes", "B": "Tokaji Aszú", "C": "Vin de Constance", "D": "Trockenbeerenauslese"},
        "correct_answer": "B",
        "topic": "grape_varieties",
        "difficulty_estimate": 3,
    },
    {
        "stem": "Grüner Veltliner, the signature white grape of Austria, is most often associated with which descriptor?",
        "options": {"A": "Lychee and rose", "B": "White pepper and citrus", "C": "Honey and almond", "D": "Tropical mango"},
        "correct_answer": "B",
        "topic": "grape_varieties",
        "difficulty_estimate": 2,
    },
    {
        "stem": "Which grape, known as 'Rhine Riesling' in some markets, is often described as one of the noble white varieties?",
        "options": {"A": "Müller-Thurgau", "B": "Riesling", "C": "Silvaner", "D": "Kerner"},
        "correct_answer": "B",
        "topic": "grape_varieties",
        "difficulty_estimate": 1,
    },
    {
        "stem": "Aglianico is most strongly associated with which two Italian regions?",
        "options": {"A": "Veneto and Friuli", "B": "Campania and Basilicata", "C": "Tuscany and Umbria", "D": "Piedmont and Lombardy"},
        "correct_answer": "B",
        "topic": "grape_varieties",
        "difficulty_estimate": 3,
    },
    {
        "stem": "Petit Manseng is most famously grown in which French region?",
        "options": {"A": "Alsace", "B": "Jura", "C": "South West (Jurançon)", "D": "Provence"},
        "correct_answer": "C",
        "topic": "grape_varieties",
        "difficulty_estimate": 3,
    },
    {
        "stem": "Which grape provides the structural backbone of most Hermitage and Côte-Rôtie reds?",
        "options": {"A": "Mourvèdre", "B": "Grenache", "C": "Syrah", "D": "Cinsault"},
        "correct_answer": "C",
        "topic": "grape_varieties",
        "difficulty_estimate": 2,
    },
    {
        "stem": "Mencía, a red grape capable of fragrant, lighter-bodied wines, is most associated with which two Spanish DOs?",
        "options": {"A": "Rioja and Ribera del Duero", "B": "Bierzo and Ribeira Sacra", "C": "Penedès and Priorat", "D": "Jumilla and Yecla"},
        "correct_answer": "B",
        "topic": "grape_varieties",
        "difficulty_estimate": 3,
    },

    # Viticulture & winemaking (~10)
    {
        "stem": "Which root-feeding insect devastated European vineyards from the 1860s and prompted widespread grafting onto American rootstocks?",
        "options": {"A": "Glassy-winged sharpshooter", "B": "Phylloxera", "C": "Vine moth", "D": "Mealybug"},
        "correct_answer": "B",
        "topic": "viticulture",
        "difficulty_estimate": 2,
    },
    {
        "stem": "What is the term for the practice of removing leaves around grape clusters to improve sun exposure and air circulation?",
        "options": {"A": "Suckering", "B": "Crop thinning", "C": "Leaf pulling", "D": "Topping"},
        "correct_answer": "C",
        "topic": "viticulture",
        "difficulty_estimate": 2,
    },
    {
        "stem": "Veraison refers to which event in the vine's annual cycle?",
        "options": {"A": "Bud break", "B": "Flowering", "C": "Onset of ripening, when berries change color", "D": "Leaf fall"},
        "correct_answer": "C",
        "topic": "viticulture",
        "difficulty_estimate": 2,
    },
    {
        "stem": "Which winemaking process intentionally converts sharper malic acid into softer lactic acid?",
        "options": {"A": "Carbonic maceration", "B": "Malolactic fermentation", "C": "Cold soaking", "D": "Bâtonnage"},
        "correct_answer": "B",
        "topic": "winemaking",
        "difficulty_estimate": 2,
    },
    {
        "stem": "The Champagne method is also known by which French term?",
        "options": {"A": "Méthode ancestrale", "B": "Méthode traditionnelle", "C": "Méthode rurale", "D": "Méthode charmat"},
        "correct_answer": "B",
        "topic": "winemaking",
        "difficulty_estimate": 1,
    },
    {
        "stem": "What term describes the practice of stirring the lees during white wine élevage to add texture and complexity?",
        "options": {"A": "Bâtonnage", "B": "Soutirage", "C": "Pigéage", "D": "Remontage"},
        "correct_answer": "A",
        "topic": "winemaking",
        "difficulty_estimate": 2,
    },
    {
        "stem": "Carbonic maceration, the technique behind young Beaujolais Nouveau, ferments grapes under what condition?",
        "options": {"A": "Open-top vats with daily punch-downs", "B": "Whole clusters in a CO₂-saturated atmosphere", "C": "Crushed must with added cultured yeast", "D": "Small oak barrels with no air contact"},
        "correct_answer": "B",
        "topic": "winemaking",
        "difficulty_estimate": 3,
    },
    {
        "stem": "What is the typical purpose of fining a wine with egg whites or bentonite before bottling?",
        "options": {"A": "To boost alcohol content", "B": "To clarify the wine and remove suspended particles", "C": "To add tannin", "D": "To stabilize residual sugar"},
        "correct_answer": "B",
        "topic": "winemaking",
        "difficulty_estimate": 2,
    },
    {
        "stem": "The 'Brix' scale, frequently used by winemakers at harvest, measures what in grape juice?",
        "options": {"A": "Acidity", "B": "Soluble sugar content", "C": "Sulfur dioxide", "D": "Color intensity"},
        "correct_answer": "B",
        "topic": "winemaking",
        "difficulty_estimate": 2,
    },
    {
        "stem": "Botrytis cinerea, when desirable, is referred to in English as 'noble rot'. Which French term denotes the same phenomenon?",
        "options": {"A": "Pourriture grise", "B": "Pourriture noble", "C": "Pourriture acide", "D": "Pourriture sèche"},
        "correct_answer": "B",
        "topic": "viticulture",
        "difficulty_estimate": 2,
    },

    # Producers & wine business (~8)
    {
        "stem": "Domaine de la Romanée-Conti is most closely associated with which Burgundy commune?",
        "options": {"A": "Gevrey-Chambertin", "B": "Vosne-Romanée", "C": "Chambolle-Musigny", "D": "Beaune"},
        "correct_answer": "B",
        "topic": "producers",
        "difficulty_estimate": 3,
    },
    {
        "stem": "Penfolds Grange, Australia's most famous luxury wine, is principally based on which grape?",
        "options": {"A": "Cabernet Sauvignon", "B": "Shiraz", "C": "Pinot Noir", "D": "Grenache"},
        "correct_answer": "B",
        "topic": "producers",
        "difficulty_estimate": 2,
    },
    {
        "stem": "Vega Sicilia, a benchmark Spanish producer, is located in which DO?",
        "options": {"A": "Rioja", "B": "Ribera del Duero", "C": "Priorat", "D": "Toro"},
        "correct_answer": "B",
        "topic": "producers",
        "difficulty_estimate": 3,
    },
    {
        "stem": "Sassicaia, often credited with launching the 'Super Tuscan' movement, is located in which appellation?",
        "options": {"A": "Chianti Classico", "B": "Brunello di Montalcino", "C": "Bolgheri", "D": "Vino Nobile di Montepulciano"},
        "correct_answer": "C",
        "topic": "producers",
        "difficulty_estimate": 3,
    },
    {
        "stem": "What is the typical bottle size of a 'magnum'?",
        "options": {"A": "0.5 L", "B": "0.75 L", "C": "1.5 L", "D": "3 L"},
        "correct_answer": "C",
        "topic": "wine_business",
        "difficulty_estimate": 1,
    },
    {
        "stem": "A 'jeroboam' of Champagne contains how many standard bottles?",
        "options": {"A": "Two", "B": "Four", "C": "Six", "D": "Eight"},
        "correct_answer": "B",
        "topic": "wine_business",
        "difficulty_estimate": 3,
    },
    {
        "stem": "What does 'En primeur' refer to in the wine trade?",
        "options": {
            "A": "A method of training young vines",
            "B": "A futures system for buying wine before bottling and release",
            "C": "A French label term for organically grown wine",
            "D": "A category of dessert wine",
        },
        "correct_answer": "B",
        "topic": "wine_business",
        "difficulty_estimate": 2,
    },
    {
        "stem": "Which Italian quality designation sits at the top of the legal hierarchy, above DOC?",
        "options": {"A": "IGT", "B": "DOCG", "C": "VDT", "D": "VDQS"},
        "correct_answer": "B",
        "topic": "wine_business",
        "difficulty_estimate": 2,
    },
]


def _emit(items, ref_prefix, source_label, license_str, source_url):
    out = []
    for i, it in enumerate(items, start=1):
        out.append({
            "ref_id": f"{ref_prefix}-{i:03d}",
            "source": source_label,
            "license": license_str,
            "stem": it["stem"],
            "options": it["options"],
            "correct_answer": it["correct_answer"],
            "topic": it["topic"],
            "difficulty_estimate": it["difficulty_estimate"],
            "source_url": source_url,
        })
    return out


def main():
    items = []
    items += _emit(OTQA_ITEMS, "OTQA", "OpenTriviaQA (community-shared trivia, wine subset)", OTQA_LICENSE, OTQA_URL)
    items += _emit(AMEX_ITEMS, "AMEX", "AmEx Essentials wine quiz (factual content, attribution)", AMEX_LICENSE, AMEX_URL)
    items += _emit(TOP_ITEMS, "TOP", "TopTriviaQuestions.com 2023 wine quiz", TOP_LICENSE, TOP_URL)
    items += _emit(INTOVINO_ITEMS, "INTOVINO", "Intovino.com Burgundy wine quiz", INTOVINO_LICENSE, INTOVINO_URL)
    items += _emit(ATELIER_ITEMS, "ATELIER", "L'Atelier du Vin wine quiz", ATELIER_LICENSE, ATELIER_URL)
    items += _emit(PROPROFS_ITEMS, "PROPROFS", "ProProfs Wine Basics quiz", PROPROFS_LICENSE, PROPROFS_URL)
    items += _emit(WIKI_ITEMS, "WIKI", "Wikipedia-derived facts, hand-authored by OenoBench Team γ", WIKI_LICENSE, WIKI_URL)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", encoding="utf-8") as f:
        for q in items:
            f.write(json.dumps(q, ensure_ascii=False) + "\n")

    print(f"Wrote {len(items)} questions to {OUT_PATH}")
    # Per-topic / per-source breakdown
    from collections import Counter
    topic_counts = Counter(q["topic"] for q in items)
    source_counts = Counter(q["source"].split(" (")[0] for q in items)
    print("\nBy topic:")
    for k, v in sorted(topic_counts.items()):
        print(f"  {k:<20} {v}")
    print("\nBy source:")
    for k, v in sorted(source_counts.items()):
        print(f"  {k:<55} {v}")


if __name__ == "__main__":
    main()
