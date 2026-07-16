"""
RULERSHIP COMPENDIUM — provenance-tiered astrological rulerships for the
sector-mapping layer.

Encodes the systematic compendium (Ptolemy/Abu Ma'shar/al-Biruni/Lilly
classical core; Bills/Meridian/McWhirter/Morris/Merriman modern layer;
single-source experimental overlay) as structured data with per-mapping
provenance, so the engine can filter/weight by confidence tier.

TIERS:
  "classical"    — genuinely classical, well-attested (planet-metal set,
                   Ptolemy IV.4 trades, Lilly professions, Saturn-mines,
                   Mars-iron, mundane 2nd/8th/10th house economics).
                   Weight 1.0.
  "modern"       — modern convention, widely used across practitioners
                   (Uranus-tech, Neptune-oil/pharma, Pluto-debt/nuclear,
                   Meridian industry groups, McWhirter node cycle).
                   Weight 0.7.
  "experimental" — single-source / no-classical-basis / anachronistic
                   extension (asteroid rulerships, crypto/AI layered
                   signatures, psychedelic tables). Weight 0.0 in scoring;
                   carried as tags only.

KEY CORRECTIONS ENCODED:
  - No "day/night domicile rulers": domicile rulership is singular and
    sect-neutral. Jupiter rules Pisces (classical); Neptune is the MODERN
    co-ruler. Day/night rulers belong only to the separate TRIPLICITY
    system (element-level, Dorothean scheme).
  - Dual rulers for the three contested signs: Scorpio (Mars+Pluto),
    Aquarius (Saturn+Uranus), Pisces (Jupiter+Neptune). Score if EITHER
    fires; record which system fired.
  - David Williams has NO commodity-to-sign table; Merriman commodity
    attributions are from Basic Principles of Geocosmic Studies, not
    Ultimate Book Vol 3; Kate Silas publishes no sector table.
"""

# Compendium's recommended weighting (classical core above modern convention)
COMPENDIUM_TIER_WEIGHT = {"classical": 1.0, "modern": 0.7, "experimental": 0.0}
# EMPIRICAL weighting from test_provenance_tiers.py on the 152 corpus:
# classical-tier rulers showed +1.4pp lift over chance at bottoms (+0.1 at
# peaks); modern-tier +8.9pp (+9.1 at peaks); dual "either" +9.6pp at
# bottoms. The classical core carries provenance hygiene, not timing edge —
# so the scoring engine INVERTS the compendium's recommendation. (Partial
# circularity caveat: some modern-tier entries are tagged from the same
# corpus; but pure-convention modern attributions — Uranus-EV, Pluto-MEME,
# Pluto/Uranus-CANNABIS — also beat classical.)
TIER_WEIGHT = {"classical": 0.7, "modern": 1.0, "experimental": 0.0}

# ---------------------------------------------------------------------------
# SIGN -> DOMICILE RULERS (traditional, modern) — dual for contested signs
# ---------------------------------------------------------------------------
SIGN_RULERS = {
    # sign_index: (traditional, modern_or_None)
    0:  ("Mars", None),          # Aries
    1:  ("Venus", None),         # Taurus
    2:  ("Mercury", None),       # Gemini
    3:  ("Moon", None),          # Cancer
    4:  ("Sun", None),           # Leo
    5:  ("Mercury", None),       # Virgo
    6:  ("Venus", None),         # Libra
    7:  ("Mars", "Pluto"),       # Scorpio — CONTESTED
    8:  ("Jupiter", None),       # Sagittarius
    9:  ("Saturn", None),        # Capricorn
    10: ("Saturn", "Uranus"),    # Aquarius — CONTESTED
    11: ("Jupiter", "Neptune"),  # Pisces — CONTESTED
}

def sign_rulers(sign_index, include_modern=True):
    trad, mod = SIGN_RULERS[sign_index % 12]
    out = [("traditional", trad)]
    if include_modern and mod:
        out.append(("modern", mod))
    return out

# ---------------------------------------------------------------------------
# TRIPLICITY RULERS (Dorothean: day, night, participating) — element-level,
# NOT sign-domicile. Ptolemy/Lilly variant noted for water.
# ---------------------------------------------------------------------------
TRIPLICITY_DOROTHEAN = {
    "fire":  {"day": "Sun",    "night": "Jupiter", "participating": "Saturn"},
    "earth": {"day": "Venus",  "night": "Moon",    "participating": "Mars"},
    "air":   {"day": "Saturn", "night": "Mercury", "participating": "Jupiter"},
    "water": {"day": "Venus",  "night": "Mars",    "participating": "Moon"},
}
TRIPLICITY_PTOLEMY_WATER = {"day": "Mars", "night": "Mars"}  # Lilly follows

# ---------------------------------------------------------------------------
# CLASSICAL PLANET-METAL SET (Babylonian -> alchemical; tier: classical)
# ---------------------------------------------------------------------------
PLANET_METALS = {
    "Sun": "gold", "Moon": "silver", "Mercury": "quicksilver",
    "Venus": "copper", "Mars": "iron", "Jupiter": "tin", "Saturn": "lead",
    # 20th-c. wordplay extensions (tier: experimental):
    "Uranus": "uranium?", "Neptune": "platinum?", "Pluto": "plutonium?",
}

# ---------------------------------------------------------------------------
# REVERSE LOOKUP: internal sector label -> list of (planet, tier, source)
# Mapped onto the framework's sector labels (v23/v24 MODERN_SECTOR space).
# ---------------------------------------------------------------------------
SECTOR_RULERSHIP = {
    # -- Energy --
    "FOSSIL": [
        ("Neptune", "modern",       "Meridian; Gidel; Merriman Mars/Neptune"),
        ("Pluto",   "modern",       "Orr revisionist (underground/power)"),
        ("Saturn",  "classical",    "Lilly: things found underground, mines"),
        ("Mars",    "modern",       "Merriman: crude volatility pair"),
    ],
    "ENERGY": [
        ("Neptune", "modern",       "Meridian liquids/oil"),
        ("Saturn",  "classical",    "underground/mines"),
        ("Jupiter", "modern",       "EMPIRICAL: 152-corpus bottoms lead"),
    ],
    "URANIUM": [
        ("Pluto",   "modern",       "nuclear/plutonium wordplay"),
        ("Uranus",  "experimental", "uranium namesake"),
        ("Saturn",  "classical",    "mining/ores"),
    ],
    "NUCLEAR": [
        ("Pluto",   "modern",       "consensus nuclear"),
        ("Uranus",  "modern",       "electricity/novelty"),
    ],
    "CLEAN": [
        ("Uranus",  "modern",       "electricity/innovation"),
        ("Sun",     "experimental", "solar namesake"),
    ],
    # -- Materials --
    "METALS": [
        ("Mars",    "classical",    "Ptolemy IV.4 smiths/iron -> steel/defence through-line"),
        ("Saturn",  "classical",    "mines/lead"),
        ("Pluto",   "modern",       "deep mining"),
    ],
    "PRECIOUS_METALS": [
        ("Sun",     "classical",    "gold (planet-metal set)"),
        ("Moon",    "classical",    "silver"),
    ],
    "MATERIALS": [
        ("Saturn",  "classical",    "earth/structure"),
        ("Mars",    "classical",    "processing/fire-crafts"),
    ],
    # -- Industrials --
    "DEFENSE": [
        ("Mars",    "classical",    "iron/weapons/soldiers — strongest classical through-line"),
    ],
    "AEROSPACE": [
        ("Uranus",  "modern",       "aviation (Meridian)"),
        ("Mars",    "classical",    "weapons component"),
    ],
    "DRONES": [
        ("Uranus",  "modern",       "aviation/novel tech"),
        ("Mars",    "classical",    "weapons"),
    ],
    "INDUSTRIAL": [
        ("Saturn",  "classical",    "builders/capital goods"),
        ("Mars",    "classical",    "machinery/fire-crafts"),
    ],
    "HOMEBUILDER": [
        ("Saturn",  "classical",    "builders/land"),
        ("Moon",    "modern",       "residential (Cancer)"),
    ],
    # -- Financials --
    "FINANCE": [
        ("Jupiter", "classical",    "bankers/financiers (Ptolemy: Mercury bankers too) — CONTESTED"),
        ("Venus",   "classical",    "money — contested"),
        ("Saturn",  "modern",       "institutions — contested"),
        ("Pluto",   "modern",       "debt/credit/8th-house; EMPIRICAL: 152-corpus bottoms lead"),
    ],
    "FINTECH": [
        ("Mercury", "classical",    "commerce/accounting"),
        ("Uranus",  "experimental", "disruption overlay"),
    ],
    "CRYPTO": [
        ("Uranus",  "experimental", "decentralised tech — no classical basis"),
        ("Neptune", "experimental", "intangible/speculative"),
        ("Pluto",   "experimental", "hidden/transformative money"),
        ("Jupiter", "modern",       "EMPIRICAL: 152-corpus peak lead"),
    ],
    # -- Tech --
    "TECH": [
        ("Uranus",  "modern",       "technology (pure 20th-c. invention)"),
        ("Mercury", "classical",    "calculation/communication root"),
        ("Saturn",  "modern",       "EMPIRICAL: 152-corpus bottoms lead; Uranus peaks"),
    ],
    "SEMIS": [
        ("Uranus",  "experimental", "no classical basis"),
        ("Mercury", "modern",       "computation analogy"),
        ("Jupiter", "modern",       "EMPIRICAL: SEMIS-subset bottoms lead (67% <=5)"),
    ],
    "AI_QUANTUM": [
        ("Uranus",  "experimental", "no classical basis"),
        ("Mercury", "experimental", "cognition/data"),
        ("Neptune", "modern",       "EMPIRICAL: AI_QUANTUM-subset bottom ruler (57% <=5)"),
    ],
    "CYBERSEC": [
        ("Pluto",   "experimental", "hidden/protection"),
        ("Mercury", "classical",    "information root"),
    ],
    # -- Communication / Media --
    "MEDIA": [
        ("Mercury", "classical",    "scribes/messengers/publishing"),
        ("Neptune", "modern",       "film/photography (Meridian)"),
    ],
    "STREAMING": [
        ("Neptune", "modern",       "film/media"),
        ("Uranus",  "experimental", "distribution tech"),
    ],
    "ENTERTAINMENT": [
        ("Venus",   "classical",    "arts/music"),
        ("Sun",     "classical",    "Leo/spectacle"),
        ("Neptune", "modern",       "film"),
    ],
    "CREATOR_ECONOMY": [
        ("Venus",   "classical",    "arts"),
        ("Mercury", "classical",    "communication"),
    ],
    "GAMBLING": [
        ("Jupiter", "classical",    "5th-house speculation / Meridian gambling"),
        ("Venus",   "modern",       "leisure"),
    ],
    # -- Health --
    "BIOPHARM": [
        ("Neptune", "modern",       "pharma consensus — CONTESTED with Jupiter for scale"),
        ("Mercury", "classical",    "Virgo clinical/physicians"),
        ("Pluto",   "modern",       "EMPIRICAL: 152-corpus bottoms lead (67% <=5)"),
    ],
    "BIOTECH": [
        ("Pluto",   "modern",       "transformation/gene-editing"),
        ("Neptune", "modern",       "pharma"),
        ("Mercury", "classical",    "clinical"),
    ],
    "HEALTH": [
        ("Mercury", "classical",    "Virgo/physicians"),
        ("Neptune", "modern",       "hospitals/12th"),
        ("Pluto",   "modern",       "EMPIRICAL sector-test lead"),
    ],
    # -- Consumer --
    "RETAIL": [
        ("Moon",    "classical",    "common people / walk-in (Meridian)"),
        ("Mercury", "classical",    "merchants"),
        ("Venus",   "classical",    "goods/adornment"),
        ("Jupiter", "modern",       "EMPIRICAL: 152-corpus bottoms lead"),
    ],
    "LUXURY": [
        ("Venus",   "classical",    "perfumes/adornment/jewels — strong consensus"),
    ],
    "FOOD_BEV": [
        ("Moon",    "classical",    "food/liquids/public"),
        ("Venus",   "classical",    "wine"),
        ("Ceres",   "experimental", "Meridian asteroid"),
    ],
    "STAPLES": [
        ("Moon",    "classical",    "necessities/public"),
        ("Saturn",  "classical",    "agriculture/land"),
    ],
    "HOSPITALITY": [
        ("Moon",    "classical",    "Cancer inns/food"),
        ("Venus",   "classical",    "leisure"),
        ("Juno",    "experimental", "Meridian asteroid"),
    ],
    "CANNABIS": [
        ("Neptune", "modern",       "intoxicants — EMPIRICALLY REFUTED on 152 corpus (0% <=5 at bottoms)"),
        ("Pluto",   "modern",       "EMPIRICAL: 152-corpus lead"),
        ("Uranus",  "modern",       "EMPIRICAL: co-lead"),
    ],
    # -- Other --
    "EV": [
        ("Uranus",  "modern",       "electricity/novel transport; EMPIRICAL: 152-corpus confirmed (55% <=5 at bottoms)"),
        ("Mercury", "classical",    "transport root"),
    ],
    "AUTONOMOUS": [
        ("Uranus",  "experimental", "novel transport"),
        ("Mercury", "classical",    "transport"),
    ],
    "SPACE": [
        ("Uranus",  "modern",       "aerospace"),
        ("Jupiter", "modern",       "9th-house long journeys"),
    ],
    "SATELLITES": [
        ("Uranus",  "modern",       "aerospace/comm tech"),
        ("Mercury", "classical",    "messages"),
    ],
    "REIT": [
        ("Saturn",  "classical",    "land/real estate — strong consensus; EMPIRICAL confirmed"),
        ("Moon",    "modern",       "residential"),
    ],
    "UTILS": [
        ("Saturn",  "classical",    "regulated/structure; EMPIRICAL confirmed"),
        ("Uranus",  "modern",       "electricity"),
        ("Moon",    "modern",       "water"),
    ],
    "WATER_UTIL": [
        ("Moon",    "classical",    "water/liquids"),
        ("Saturn",  "classical",    "regulated infrastructure"),
    ],
    "MEME": [
        ("Pluto",   "modern",       "EMPIRICAL: 152-corpus dominant (71% <=5 at bottoms); no classical category"),
        ("Saturn",  "modern",       "EMPIRICAL: peak flip (71% at peaks)"),
    ],
    "GOLD": [
        ("Sun",     "classical",    "planet-metal set"),
    ],
    "INDEX": [],  # broad-market — no sector ruler
    "UNK": [],
}

# ---------------------------------------------------------------------------
# MUNDANE HOUSE -> ECONOMIC DOMAIN (tier: classical/mundane tradition)
# ---------------------------------------------------------------------------
MUNDANE_HOUSES = {
    1:  "nation/people/general prosperity",
    2:  "national wealth, treasury, banks, stock exchange, currency, revenue",
    3:  "communications, transport, media, neighbouring nations",
    4:  "land, agriculture, mines, real estate, opposition party",
    5:  "stock exchange/speculation, entertainment, sport, birth rate",
    6:  "public health, food supply, armed services ranks, labour",
    7:  "foreign relations, treaties, war, international business",
    8:  "taxes, national debt, international finance, insurance, other people's money",
    9:  "foreign trade, shipping, law, higher education, publishing",
    10: "government, executive, large corporations, national prestige",
    11: "legislature, allies, national goals, reform movements",
    12: "institutions, secret enemies, espionage, hidden forces, drugs",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def sector_rulers_for(sector, min_tier="modern"):
    """Return [(planet, tier, weight, source)] for a sector, filtered by tier.
    min_tier='classical' -> classical only; 'modern' -> classical+modern;
    'experimental' -> all (experimental carried at weight 0)."""
    order = {"classical": 0, "modern": 1, "experimental": 2}
    cutoff = order[min_tier]
    out = []
    for planet, tier, source in SECTOR_RULERSHIP.get(sector, []):
        if order[tier] <= cutoff:
            out.append((planet, tier, TIER_WEIGHT[tier], source))
    return out

def ruler_weight(planet, sector, min_tier="modern"):
    """Max tier-weight of `planet` as a ruler of `sector` (0 if not a ruler)."""
    best = 0.0
    for p, tier, w, _ in sector_rulers_for(sector, min_tier):
        if p == planet and w > best:
            best = w
    return best

if __name__ == "__main__":
    print("Sector rulership table (classical+modern tiers):\n")
    for sec in sorted(SECTOR_RULERSHIP):
        rl = sector_rulers_for(sec, "modern")
        if not rl: continue
        s = ", ".join(f"{p}[{t[0].upper()}{w:.1f}]" for p, t, w, _ in rl)
        print(f"  {sec:<16s} {s}")
    print("\nContested signs (dual rulers):")
    for idx in (7, 10, 11):
        trad, mod = SIGN_RULERS[idx]
        name = ["Aries","Taurus","Gemini","Cancer","Leo","Virgo","Libra",
                "Scorpio","Sagittarius","Capricorn","Aquarius","Pisces"][idx]
        print(f"  {name:<12s} traditional={trad}  modern={mod}")
