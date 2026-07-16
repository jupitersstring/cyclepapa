"""Provenance-tiered sector-rulership layer for the reverse-arch scanner.

Encodes the compendium's three-tier confidence schema:
  classical      1.00  (Ptolemy/al-Biruni/Lilly through-line: Mars-iron, Saturn-mines, Sun-gold...)
  modern         0.65  (Meridian/Bills convention: Uranus-tech, Neptune-oil/pharma, Pluto-debt)
  contested      0.50  (banking Jupiter-vs-Saturn-vs-Venus etc.)
  experimental   0.35  (crypto/AI/psychedelics layered signatures — no classical basis)

Dual rulers are kept for the three contested signs (Scorpio Mars+Pluto,
Aquarius Saturn+Uranus, Pisces Jupiter+Neptune): a sector fires if EITHER
ruler is emphasized, and the tier flags which system fired.

Note on the day/night correction: domicile rulership is singular and
sect-neutral (Jupiter rules Pisces classically; Neptune is the modern
co-ruler). "Day/night rulers" belong only to the triplicity system and are
not used here.
"""
from __future__ import annotations

TIER_WEIGHT = {"classical": 1.00, "modern": 0.65, "contested": 0.50, "experimental": 0.35}

# sector -> [(planet, tier, source)]
SECTOR_RULERS: dict[str, list[tuple[str, str, str]]] = {
    "gold": [("Sun", "classical", "planet-metal core")],
    "silver": [("Moon", "classical", "planet-metal core")],
    "steel_defense": [("Mars", "classical", "Ptolemy IV.4 smiths/iron -> defence"),
                      ("Uranus", "modern", "Meridian aviation/aerospace")],
    "mining_materials": [("Saturn", "classical", "Lilly miners-underground"),
                         ("Pluto", "modern", "deep/underground revisionist"),
                         ("Mars", "classical", "metals")],
    "oil_gas": [("Saturn", "classical", "things-found-underground"),
                ("Neptune", "modern", "Meridian/Gidel liquids"),
                ("Pluto", "modern", "black-gold revisionist")],
    "utilities": [("Saturn", "modern", "Meridian regulated"),
                  ("Uranus", "modern", "electricity"),
                  ("Moon", "modern", "water")],
    "banking_financial": [("Jupiter", "contested", "wealth/finance"),
                          ("Venus", "contested", "money"),
                          ("Saturn", "contested", "institutions")],
    "insurance": [("Pluto", "modern", "8th-house/OPM"),
                  ("Jupiter", "contested", "scale")],
    "real_estate": [("Saturn", "classical", "land/4th house"),
                    ("Moon", "modern", "residential/Cancer")],
    "pharma_biotech": [("Neptune", "modern", "Meridian chemicals/pharma"),
                       ("Mercury", "modern", "Virgo clinical"),
                       ("Pluto", "experimental", "transformation/psychedelic layer"),
                       ("Jupiter", "contested", "big-pharma scale")],
    "healthcare_services": [("Neptune", "modern", "hospitals/12th"),
                            ("Mercury", "modern", "Virgo service")],
    "tech_software": [("Uranus", "experimental", "no classical basis"),
                      ("Mercury", "modern", "data/cognition")],
    "semiconductors": [("Uranus", "experimental", "no classical basis"),
                       ("Mercury", "modern", "precision/data")],
    "telecom_media": [("Mercury", "modern", "Meridian communications"),
                      ("Neptune", "modern", "film/photography")],
    "entertainment": [("Venus", "classical", "arts/adornment"),
                      ("Neptune", "modern", "film"),
                      ("Sun", "modern", "Leo spotlight")],
    "retail_consumer": [("Moon", "modern", "Meridian walk-in"),
                        ("Venus", "classical", "luxury/adornment")],
    "food_agriculture": [("Moon", "classical", "liquids/public/dairy"),
                         ("Saturn", "classical", "land/farmers")],
    "transport_shipping": [("Mercury", "modern", "Meridian trucking/short-travel"),
                           ("Neptune", "modern", "marine")],
    "hospitality": [("Moon", "modern", "hotels/public"),
                    ("Venus", "modern", "leisure")],
    "crypto_digital": [("Uranus", "experimental", "decentralised tech"),
                       ("Neptune", "experimental", "intangible/speculative"),
                       ("Pluto", "experimental", "hidden money")],
    "aerospace_aviation": [("Uranus", "modern", "Meridian aviation"),
                           ("Mars", "classical", "defence")],
    "nuclear": [("Pluto", "modern", "atomic"),
                ("Uranus", "modern", "novel energy")],
}

# crude name-keyword -> sector classifier (first match wins, order matters)
SECTOR_KEYWORDS: list[tuple[str, str]] = [
    ("pharma", "pharma_biotech"), ("therapeut", "pharma_biotech"), ("biosciscience", "pharma_biotech"),
    ("bioscience", "pharma_biotech"), ("biotech", "pharma_biotech"), ("genomic", "pharma_biotech"),
    ("biolog", "pharma_biotech"), ("medicines", "pharma_biotech"), ("oncolog", "pharma_biotech"),
    ("immuno", "pharma_biotech"), ("neuro", "pharma_biotech"), ("bio ", "pharma_biotech"),
    ("labs", "pharma_biotech"), ("laborator", "pharma_biotech"),
    ("health", "healthcare_services"), ("medical", "healthcare_services"), ("hospital", "healthcare_services"),
    ("care ", "healthcare_services"), ("diagnostic", "healthcare_services"), ("surgic", "healthcare_services"),
    ("semiconductor", "semiconductors"), ("micro devices", "semiconductors"), ("chip", "semiconductors"),
    ("software", "tech_software"), ("systems", "tech_software"), ("technolog", "tech_software"),
    ("digital", "tech_software"), ("cyber", "tech_software"), ("data ", "tech_software"),
    ("network", "tech_software"), ("internet", "tech_software"), (".com", "tech_software"),
    ("computer", "tech_software"), ("informat", "tech_software"), ("cloud", "tech_software"),
    ("telecom", "telecom_media"), ("communicat", "telecom_media"), ("wireless", "telecom_media"),
    ("media", "telecom_media"), ("broadcast", "telecom_media"), ("publish", "telecom_media"),
    ("entertainment", "entertainment"), ("studios", "entertainment"), ("cinema", "entertainment"),
    ("games", "entertainment"), ("gaming", "entertainment"),
    ("gold", "gold"), ("silver", "silver"),
    ("energy", "oil_gas"), ("petroleum", "oil_gas"), ("oil ", "oil_gas"), ("gas ", "oil_gas"),
    ("midstream", "oil_gas"), ("pipeline", "oil_gas"), ("drilling", "oil_gas"), ("lng", "oil_gas"),
    ("resources", "mining_materials"), ("mining", "mining_materials"), ("minerals", "mining_materials"),
    ("steel", "steel_defense"), ("defense", "steel_defense"), ("defence", "steel_defense"),
    ("aerospace", "aerospace_aviation"), ("airlines", "aerospace_aviation"), ("airways", "aerospace_aviation"),
    ("aviation", "aerospace_aviation"), ("air ", "aerospace_aviation"),
    ("bank", "banking_financial"), ("bancorp", "banking_financial"), ("bancshares", "banking_financial"),
    ("financial", "banking_financial"), ("capital", "banking_financial"), ("credit", "banking_financial"),
    ("lending", "banking_financial"), ("invest", "banking_financial"), ("securities", "banking_financial"),
    ("asset management", "banking_financial"), ("fintech", "banking_financial"),
    ("insurance", "insurance"), ("assurance", "insurance"),
    ("reit", "real_estate"), ("realty", "real_estate"), ("properties", "real_estate"),
    ("real estate", "real_estate"), ("homes", "real_estate"), ("housing", "real_estate"),
    ("utilities", "utilities"), ("electric", "utilities"), ("power", "utilities"), ("water", "utilities"),
    ("restaurant", "hospitality"), ("hotel", "hospitality"), ("resort", "hospitality"),
    ("foods", "food_agriculture"), ("food", "food_agriculture"), ("agri", "food_agriculture"),
    ("farms", "food_agriculture"), ("grocery", "food_agriculture"), ("beverage", "food_agriculture"),
    ("retail", "retail_consumer"), ("stores", "retail_consumer"), ("brands", "retail_consumer"),
    ("apparel", "retail_consumer"), ("outfitters", "retail_consumer"), ("consumer", "retail_consumer"),
    ("shipping", "transport_shipping"), ("maritime", "transport_shipping"), ("logistics", "transport_shipping"),
    ("transport", "transport_shipping"), ("trucking", "transport_shipping"), ("freight", "transport_shipping"),
    ("railroad", "transport_shipping"), ("marine", "transport_shipping"),
    ("crypto", "crypto_digital"), ("blockchain", "crypto_digital"), ("bitcoin", "crypto_digital"),
    ("nuclear", "nuclear"), ("uranium", "nuclear"),
]


def classify_sector(name: str) -> str | None:
    nl = f" {(name or '').lower()} "
    for kw, sector in SECTOR_KEYWORDS:
        if kw in nl:
            return sector
    return None


# classical essential dignities (domicile & exaltation; modern co-rulers tagged separately)
DOMICILE = {
    "Sun": [4], "Moon": [3], "Mercury": [2, 5], "Venus": [1, 6], "Mars": [0, 7],
    "Jupiter": [8, 11], "Saturn": [9, 10],
}
MODERN_DOMICILE = {"Uranus": [10], "Neptune": [11], "Pluto": [7]}
EXALTATION = {"Sun": 0, "Moon": 1, "Mercury": 5, "Venus": 11, "Mars": 9, "Jupiter": 3, "Saturn": 6}
DETRIMENT = {p: [(s + 6) % 12 for s in signs] for p, signs in DOMICILE.items()}
FALL = {p: (s + 6) % 12 for p, s in EXALTATION.items()}
