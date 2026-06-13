"""Brand / product aliases for entity resolution.

The single biggest implementation pitfall in social-arb pipelines is ticker
collisions ($X is US Steel and a domain; $APPL doesn't exist but "Apple" hits
fruit). We seed a small high-quality mapping for the Camillo-archetype names
and let users append to it via CSV.

Each row maps an alias (case-insensitive) to a ticker. An alias is "ambiguous"
if the term is also a common English word -- those require a finance-context
co-occurrence before they fire as a mention.
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .config import Config

log = logging.getLogger(__name__)


# Curated seed: Camillo's published trades plus a handful of common collisions.
# Keep aliases lowercase; the resolver normalizes on read.
SEED_ALIASES: list[tuple[str, str, bool]] = [
    # (alias, ticker, ambiguous)
    ("cannondale", "DII.B.TO", False),         # Dorel (delisted post-buyout; placeholder)
    ("dorel", "DII.B.TO", False),
    ("mattel", "MAT", False),
    ("barbie", "MAT", True),                    # film + doll + name
    ("hot wheels", "MAT", False),
    ("crocs", "CROX", False),
    ("celsius energy", "CELH", False),
    ("celsius drink", "CELH", False),
    ("$celh", "CELH", False),
    ("tapestry", "TPR", False),
    ("coach handbag", "TPR", False),
    ("kate spade", "TPR", False),
    ("newell brands", "NWL", False),
    ("elmer's glue", "NWL", False),
    ("rubbermaid", "NWL", False),
    ("sharpie", "NWL", False),
    ("yankee candle", "NWL", False),
    ("under armour", "UAA", False),
    ("lululemon", "LULU", False),
    ("ugg", "DECK", True),                      # also slang
    ("hoka", "DECK", False),
    ("teva sandals", "DECK", False),
    ("nvidia", "NVDA", False),
    ("$nvda", "NVDA", False),
    ("stanley cup tumbler", "ELUX-B.ST", True), # Stanley brand owner placeholder; collides with NHL
    ("hydroflask", "HELE", False),              # Helen of Troy
    ("yeti", "YETI", False),
    ("owala", "PRIVATE", True),                 # private; tracked for read-across
    ("gamestop", "GME", False),
    ("$gme", "GME", False),
    ("sol de janeiro", "ULTA", True),           # sold at Ulta; read-across only
    ("temu", "PDD", False),
    ("shein", "PRIVATE", True),
    ("amazon", "AMZN", False),
    ("$amzn", "AMZN", False),
]


@dataclass(frozen=True)
class Alias:
    alias: str
    ticker: str
    ambiguous: bool


def write_seed_csv(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["alias", "ticker", "ambiguous"])
        for alias, ticker, ambiguous in SEED_ALIASES:
            writer.writerow([alias, ticker, int(ambiguous)])
    return path


def load_aliases(cfg: Config) -> list[Alias]:
    path = Path(cfg.aliases_csv)
    if not path.exists():
        write_seed_csv(path)
    df = pd.read_csv(path)
    out: list[Alias] = []
    for row in df.itertuples(index=False):
        out.append(
            Alias(
                alias=str(row.alias).lower().strip(),
                ticker=str(row.ticker).upper().strip(),
                ambiguous=bool(int(row.ambiguous)),
            )
        )
    return out


def _english_word_stoplist() -> frozenset[str]:
    """Programmatic stoplist of common English words 1-6 chars long.

    Uses wordfreq's top-12k English wordlist when available; falls back
    to the hand-curated `COMMON_WORD_TICKERS` set below.

    Cached at import time. ~5,700 unique tokens when available.
    """
    try:
        from wordfreq import top_n_list
        words = top_n_list("en", 12000)
        # Tickers are uppercase letters only, 1-5 chars in our universe.
        # Lift to uppercase and bound length to match.
        out = {w.upper() for w in words if 1 <= len(w) <= 6 and w.isalpha()}
        return frozenset(out)
    except Exception:
        return frozenset()


_ENGLISH_WORDS: frozenset[str] = _english_word_stoplist()


def is_dictionary_word(symbol: str) -> bool:
    """True if `symbol` (uppercase) is a common English word.

    Combines the programmatic wordfreq list with our hand-curated
    COMMON_WORD_TICKERS set so we keep the manual entries for terms
    that wordfreq misses (REPO, CLI, tickers from finance slang).
    """
    s = symbol.upper().strip()
    if not s:
        return False
    return s in _ENGLISH_WORDS or s in COMMON_WORD_TICKERS


# Common English words / abbreviations that also happen to be ticker symbols.
# These fire constantly on social-media text without actually referring to the
# stock. We force them to require a cashtag (`$XX`) before firing.
COMMON_WORD_TICKERS: frozenset[str] = frozenset({
    "A", "AI", "ALL", "AM", "AMP", "AN", "AND", "ANY", "ARE", "AT", "BE", "BEST",
    "BIG", "BIT", "BLOCK", "BOOM", "BOSS", "BUY", "BY", "CAN", "CAR", "CARE",
    "CASH", "CAT", "CEO", "CFO", "CHAT", "CITY", "CLEAN", "CLEAR", "CLEAN",
    "CODE", "COIN", "COLD", "COMP", "COOK", "COOL", "COST", "CRM", "DARK",
    "DAY", "DEEP", "DO", "DOG", "DOWN", "DR", "DREAM", "DROP", "DRY", "EACH",
    "EAR", "EAT", "EDGE", "ELSE", "END", "EVER", "EVERY", "FAR", "FAST",
    "FATE", "FAT", "FAVE", "FIND", "FINE", "FINISH", "FIRE", "FIRST", "FIT",
    "FIX", "FLY", "FOR", "FREE", "FROM", "FULL", "FUN", "GAME", "GENERAL",
    "GET", "GIFT", "GIVE", "GO", "GOOD", "GOLD", "GOT", "GRAB", "GREAT",
    "GREEN", "GROW", "GT", "HALF", "HALO", "HAS", "HAVE", "HE", "HEAD", "HEAR",
    "HELP", "HER", "HERE", "HI", "HIGH", "HIT", "HOLD", "HOME", "HOPE", "HOT",
    "HOUR", "HOW", "HUGE", "ICE", "IF", "IN", "INFO", "IS", "IT", "ITS", "JOB",
    "JUMP", "JUST", "KEEP", "KEY", "KID", "KIDS", "KIND", "KING", "LAB",
    "LADY", "LAND", "LANE", "LARGE", "LAST", "LATE", "LAW", "LAY", "LEAD",
    "LEAF", "LEFT", "LESS", "LET", "LIFE", "LIGHT", "LIKE", "LINE", "LINK",
    "LIVE", "LONG", "LOOK", "LOSE", "LOSS", "LOT", "LOTS", "LOUD", "LOVE",
    "LOW", "MAIN", "MAKE", "MAN", "MANY", "MARK", "MASK", "MAY", "ME", "MEAN",
    "MEET", "MID", "MIND", "MINE", "MISS", "MIST", "MO", "MORE", "MOST",
    "MOVE", "MUCH", "MUST", "MX", "MY", "NAME", "NEAR", "NEED", "NEW", "NEXT",
    "NICE", "NO", "NONE", "NOR", "NORTH", "NOT", "NOW", "OF", "OFF", "OK",
    "OLD", "ON", "ONCE", "ONE", "ONLY", "OPEN", "OR", "ORG", "OTHER", "OUR",
    "OUT", "OVER", "OWN", "PACK", "PAGE", "PAID", "PAIN", "PAIR", "PARK",
    "PART", "PAST", "PATH", "PAY", "PEAR", "PER", "PICK", "PLAN", "PLAY",
    "PLUS", "POOL", "POOR", "POST", "POWER", "PRICE", "PRO", "PUT", "QUICK",
    "RAIN", "RARE", "RATE", "READ", "READY", "REAL", "RED", "REST", "RICH",
    "RIDE", "RIGHT", "RISE", "ROAD", "ROCK", "ROLL", "ROOM", "ROUND", "RUN",
    "SAFE", "SAID", "SAME", "SAVE", "SAY", "SEA", "SEAT", "SEE", "SEED",
    "SELF", "SELL", "SEND", "SENT", "SHE", "SHIP", "SHOP", "SHOW", "SHY",
    "SICK", "SIDE", "SIGN", "SILK", "SIR", "SIT", "SITE", "SIZE", "SKY",
    "SLOW", "SMART", "SNAP", "SO", "SOAP", "SOFT", "SOLO", "SOME", "SONG",
    "SOON", "SORT", "SOUL", "SOUP", "SOUR", "SPEED", "SPIN", "STAR", "STAY",
    "STEP", "STILL", "STOP", "STORE", "STORM", "STRONG", "SUN", "SURE", "SWAP",
    "TAKE", "TALK", "TASK", "TEAM", "TELL", "TEN", "TEST", "THAN", "THAT",
    "THE", "THEM", "THEN", "THIN", "THIS", "TIDE", "TIME", "TINY", "TIP",
    "TO", "TOLD", "TON", "TOO", "TOP", "TOUR", "TOWN", "TRACK", "TRAVEL",
    "TREE", "TRIP", "TRUE", "TRUST", "TRY", "TURN", "TWO", "UP", "US", "USA",
    "USE", "USED", "USER", "VAN", "VARY", "VERY", "VIEW", "VISA", "VOTE",
    "WAGE", "WAIT", "WAKE", "WALL", "WANT", "WARM", "WAS", "WAVE", "WAY",
    "WE", "WEAR", "WEEK", "WELL", "WENT", "WERE", "WEST", "WET", "WHAT",
    "WHEN", "WHERE", "WHICH", "WHILE", "WHITE", "WHO", "WHY", "WIDE", "WILL",
    "WIN", "WIND", "WINE", "WING", "WISE", "WISH", "WITH", "WOOD", "WORD",
    "WORK", "WORLD", "WORN", "WOULD", "WOW", "WRITE", "WRONG", "YEAR", "YEAH",
    "YES", "YET", "YOU", "YOUR", "ZONE", "DAY", "ABLE", "AGE", "APP", "APPS",
    "BAGS", "BAND", "BANK", "BAR", "BASE", "BEAT", "BEER", "BIG", "BILL",
    "BLUE", "BOLD", "BOOK", "BOOM", "BOOT", "BOX", "BOY", "BRO", "BUS",
    "BUSY", "CAFE", "CAMP", "CAP", "CARD", "CART", "CASE", "CHAR", "CHIP",
    "CIVIL", "CLEAR", "CLIP", "CLUB", "CLUE", "COIN", "COKE", "COLA", "COME",
    "COOL", "CORE", "DEAD", "DEAL", "DEAR", "DEEP", "DEER", "DELI", "DOOR",
    "DOUBLE", "DOZE", "DRAIN", "DRAW", "DRIVE", "DRUG", "DUE", "DUTY",
    "EACH", "EASY", "EAT", "EGG", "ELITE", "ELSE", "EMAIL", "EYE", "FAIR",
    "FAKE", "FALL", "FAR", "FARE", "FARM", "FAT", "FAX", "FEE", "FIRE",
    "FLASH", "FLAT", "FOOD", "FOOT", "FOUR", "FOX", "FREE", "FRESH", "FRY",
    "FUEL", "FUN", "FUND", "FURY", "GAIN", "GAS", "GATE", "GEAR", "GEM",
    "GENE", "GENERAL", "GENIE", "GIANT", "GIFT", "GIRL", "GIVE", "GLOBE",
    "GLOW", "GOAL", "GOAT", "GUN", "GUY", "HAIR", "HAND", "HARD", "HARSH",
    "HATE", "HEAD", "HEAR", "HEAT", "HERO", "HOOK", "HORSE", "HOST", "ICE",
    "IDEA", "INTO", "ISLE", "ITEM", "JADE", "JOY", "KEY", "LAKE", "LARGE",
    "LATE", "LEAN", "LIFT", "LITE", "LOAD", "LOAN", "LOOP", "LOSS", "LOUD",
    "LOVE", "LUCK", "LUNG", "MAIL", "MARK", "MART", "MASS", "MAT", "MEAL",
    "MEAT", "MEET", "MERE", "MILE", "MILK", "MINI", "MOM", "MOOD", "MOON",
    "MOST", "MOVE", "MUST", "NAVY", "NEED", "NEST", "NET", "NEW", "NEWS",
    "NICE", "NIGHT", "NINE", "NODE", "NOW", "ODD", "OIL", "ORE", "OWN",
    "PAIN", "PALE", "PALM", "PAPER", "PARK", "PEAK", "PEAR", "PEN", "PINK",
    "PLAY", "PLUS", "POEM", "POOL", "POP", "PORK", "PORT", "POSE", "POST",
    "PUMP", "PUNK", "PURE", "QUEEN", "QUICK", "QUIET", "QUIT", "RACE",
    "RAGE", "RAGS", "RAIL", "RAIN", "RAKE", "RAM", "RANK", "RAPID", "RATE",
    "RAW", "REAL", "REEF", "RIDE", "RIPE", "RISE", "RIVER", "ROCK", "ROLE",
    "ROOM", "ROOT", "ROSE", "ROUTE", "SAFE", "SAGE", "SAIL", "SALT", "SAND",
    "SAVE", "SCALE", "SEAT", "SEED", "SEEK", "SELF", "SELL", "SHARE", "SHARP",
    "SHIFT", "SHIP", "SHOE", "SHOP", "SHOW", "SIDE", "SIGN", "SILK", "SING",
    "SIZE", "SKILL", "SKIN", "SKY", "SLAB", "SLAM", "SLOPE", "SLOW", "SMART",
    "SMOKE", "SNAP", "SNOW", "SOAP", "SOFT", "SOLE", "SOLO", "SOUR", "SPEED",
    "SPICE", "SPIN", "SPOT", "STAR", "STAY", "STEP", "STIR", "STOP", "STORE",
    "STORM", "STUDY", "SUITE", "SUN", "SUSHI", "SWAP", "TAKE", "TALK", "TASTE",
    "TAX", "TEA", "TEAM", "TECH", "TEEN", "TELL", "TEST", "TEXT", "THICK",
    "TIDE", "TIE", "TIGHT", "TIME", "TINY", "TIP", "TOKE", "TONE", "TONIC",
    "TOOL", "TOP", "TORN", "TOSS", "TOUCH", "TOUR", "TOWER", "TOWN", "TOY",
    "TRACK", "TRAIL", "TRAIN", "TRASH", "TREE", "TRIP", "TROY", "TRUE",
    "TRUST", "TRY", "TUNA", "TUNE", "TURN", "TWIN", "TWO", "UNIT", "UNITY",
    "UNIV", "URGE", "USE", "USER", "VARY", "VEER", "VEIL", "VERY", "VIBE",
    "VICE", "VIEW", "VINE", "VITAL", "VOICE", "VOTE", "WAGE", "WAKE", "WAR",
    "WARM", "WARN", "WARP", "WASH", "WASTE", "WATER", "WAVE", "WAX", "WAY",
    "WEAR", "WEEK", "WHITE", "WHOLE", "WIDE", "WILD", "WILL", "WIN", "WIND",
    "WINE", "WINK", "WISE", "WISH", "WOLF", "WOOD", "WORD", "WORK", "WORLD",
    "WORTH", "WOW", "YEAR", "YEAR", "YES", "ZERO", "ZONE", "ZOOM",
    "BOTH", "BACK", "BEEN", "MAC", "VIA", "WWW", "QUOT", "MIST", "WORD",
    "REAL", "OPEN", "ROOT", "ROCK", "TIME", "WORK", "TREE", "WIND", "WAVE",
    "MORE", "MOST", "LESS", "BEST", "FAST", "SLOW", "EVEN", "AGAIN", "ONLY",
    "OURS", "MINE", "YOURS", "FIRST", "BLOCK", "BUILT", "MAYBE", "OFTEN",
    "WITHIN", "BELOW", "ABOVE", "AFTER", "BEFORE", "DURING", "WITHOUT",
    "ITSELF", "ETC", "TEAM", "PLAN", "ROLE", "RATE", "AUTH", "DATA", "TYPE",
    "CODE", "VIEW", "DRAW", "SHOW", "MOVE", "LOAD", "SAVE", "SEND", "FROM",
    "INTO", "MAKE", "EDIT", "TODO", "TEXT", "VOTE", "BUY", "SELL", "DEAL",
    "MOON", "PUMP", "DUMP", "STOP", "FOMO", "FUD", "DUE", "OUT", "GANG",
})


def from_universe(universe: pd.DataFrame) -> list[Alias]:
    """Auto-derive aliases from a financedatabase universe.

    Adds:
      - the symbol itself (e.g. "AAPL") -- flagged ambiguous if it's a common
        English word or <= 2 chars
      - the cashtag form ("$AAPL") -- never ambiguous
      - the company short name -- never ambiguous if >= 4 chars
    Consumer-facing aliases for ambiguous brand names live in the CSV.
    """
    out: list[Alias] = []
    suffixes = (
        " inc", " inc.", " incorporated", " corp", " corp.", " corporation",
        " co", " co.", " ltd", " ltd.", " plc", " sa", " ag", " holdings",
        " holding", " group", " brands", " company",
    )
    for row in universe.itertuples(index=False):
        sym = str(getattr(row, "symbol", "")).upper().strip()
        name = str(getattr(row, "name", "")).lower().strip()
        if not sym:
            continue
        # Word-collision check: programmatic English-word list + curated
        # finance-slang list + length<=2 catchall.
        is_common = is_dictionary_word(sym) or len(sym) <= 2
        # Common-word symbols are cashtag-only -- the bare alias produces too
        # many false positives even with finance-context gating (e.g. HN posts
        # about "AI company" trip "$AI").
        if not is_common:
            out.append(Alias(alias=sym.lower(), ticker=sym, ambiguous=False))
        out.append(Alias(alias=f"${sym.lower()}", ticker=sym, ambiguous=False))
        if name:
            short = name
            for suf in suffixes:
                if short.endswith(suf):
                    short = short[: -len(suf)].strip(" ,.")
                    break
            # Skip company-name aliases that are dictionary words
            # (e.g. "Jack" matching the name).
            if short and len(short) >= 4 and not is_dictionary_word(short):
                out.append(Alias(alias=short, ticker=sym, ambiguous=False))
    return out
