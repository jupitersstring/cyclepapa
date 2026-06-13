"""
Godley sectoral archetype taxonomy.

Every country sits in a 2x2 of (financing-constraint hardness) x (sectoral
configuration). The intersection produces nine archetypes plus a closed/
sanctioned residual. The archetype determines *how indicators are weighted* --
the same series means opposite things in different configurations (e.g. a
rising household saving rate is bullish in a deleveraging frontier economy but
bearish in an Anglo-mimic whose consumption engine is fading).

The sectoral identity throughout:  (G - T) == (S - I) + (M - X)
    fiscal balance == private net lending + external (foreign) net lending
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Archetype:
    tag: str
    name: str
    signature: str          # the binding sectoral configuration
    adjustment: str         # how the identity closes under stress
    fuel: str               # what drives the bull case


ARCHETYPES: dict[str, Archetype] = {
    "A": Archetype(
        "A", "Reserve-currency deficit absorber",
        "(G-T)>0 and (M-X)>0; private oscillates",
        "Asset-price-driven private dis-saving",
        "Equity wealth effect, central-bank liquidity",
    ),
    "B": Archetype(
        "B", "Anglo-mimic deficit economy",
        "(G-T)>0 and (M-X)>0, household-leveraged",
        "Housing/consumption retrench, FX",
        "Foreign credit inflow, housing cycle",
    ),
    "C": Archetype(
        "C", "Mercantilist saver",
        "(S-I)>0 and (X-M)>0; fiscal swings",
        "Fiscal accommodation OR income contraction",
        "External demand, weak currency, fiscal pivot",
    ),
    "D": Archetype(
        "D", "Entrepot / MNC-distorted",
        "CA hugely positive but artefactual; tiny domestic",
        "Reflects parent-economy MNC flows",
        "MNC capex, tax regime (signal is mostly noise)",
    ),
    "E": Archetype(
        "E", "EMU constraint trap",
        "(S-I)>0 and no FX/fiscal flexibility",
        "Permanent output gap or transfers",
        "Eurozone-wide cycle only",
    ),
    "F": Archetype(
        "F", "Directed-credit managed-FX",
        "State sets credit, (X-M)>0, capital account semi-closed",
        "Quasi-fiscal expansion, AMC absorption",
        "Credit-policy signal",
    ),
    "G": Archetype(
        "G", "Commodity rent surplus",
        "(X-M) tied to terms of trade; SWF absorbs",
        "ToT collapse -> fiscal/SWF drawdown",
        "Commodity prices, USD, market-opening",
    ),
    "H": Archetype(
        "H", "Convergence capital-importer",
        "(G-T) modest, (M-X)>0, FDI-funded investment",
        "FX adjustment, slower growth",
        "FDI, real-rate carry, external credit impulse",
    ),
    "I": Archetype(
        "I", "Frontier dollar-dependent",
        "Chronic (M-X)>0, FX-mismatched debt",
        "Sudden stop / IMF / devaluation",
        "Global risk appetite, USD weakness",
    ),
    "X": Archetype(
        "X", "Sanctioned / closed",
        "Identity enforced inside political constraints",
        "Real-resource shortage, parallel FX",
        "Geopolitics (data unreliable)",
    ),
}


@dataclass(frozen=True)
class Country:
    name: str
    iso: str
    primary: str                       # primary archetype tag
    secondary: str | None = None       # hybrid second cell, if any
    etf: str | None = None             # MSCI/country ETF for backtesting


# The full panel. Hybrids carry a secondary tag (tracked in two cells).
COUNTRIES: list[Country] = [
    # A -- reserve absorber
    Country("United States", "US", "A", etf="SPY"),
    # B -- Anglo-mimic
    Country("United Kingdom", "GB", "B", etf="EWU"),
    Country("Australia", "AU", "B", "G", etf="EWA"),
    Country("New Zealand", "NZ", "B", etf="ENZL"),
    Country("Canada", "CA", "B", "G", etf="EWC"),
    # C -- mercantilist saver
    Country("Germany", "DE", "C", etf="EWG"),
    Country("Japan", "JP", "C", etf="EWJ"),
    Country("South Korea", "KR", "C", etf="EWY"),
    Country("Netherlands", "NL", "C", "D", etf="EWN"),
    Country("Sweden", "SE", "C", etf="EWD"),
    Country("Denmark", "DK", "C", etf="EDEN"),
    Country("Finland", "FI", "C", etf="EFNL"),
    Country("Austria", "AT", "C", etf="EWO"),
    Country("Belgium", "BE", "C", etf="EWK"),
    Country("Taiwan", "TW", "C", etf="EWT"),
    # D -- entrepot / MNC-distorted
    Country("Switzerland", "CH", "D", "C", etf="EWL"),
    Country("Ireland", "IE", "D", etf="EIRL"),
    Country("Luxembourg", "LU", "D"),
    Country("Singapore", "SG", "D", "C", etf="EWS"),
    Country("Hong Kong", "HK", "D", etf="EWH"),
    # E -- EMU constraint trap
    Country("Italy", "IT", "E", etf="EWI"),
    Country("Spain", "ES", "E", etf="EWP"),
    Country("Portugal", "PT", "E", etf="PGAL"),
    Country("Greece", "GR", "E", etf="GREK"),
    Country("France", "FR", "C", "E", etf="EWQ"),
    # F -- directed-credit managed-FX
    Country("China", "CN", "F", etf="FXI"),
    Country("Vietnam", "VN", "F", etf="VNM"),
    Country("Malaysia", "MY", "F", "H", etf="EWM"),
    Country("Thailand", "TH", "F", "H", etf="THD"),
    # G -- commodity rent surplus
    Country("Saudi Arabia", "SA", "G", etf="KSA"),
    Country("United Arab Emirates", "AE", "G", etf="UAE"),
    Country("Qatar", "QA", "G", etf="QAT"),
    Country("Kuwait", "KW", "G"),
    Country("Norway", "NO", "G", etf="ENOR"),
    Country("Kazakhstan", "KZ", "G"),
    Country("Chile", "CL", "G", etf="ECH"),
    Country("Peru", "PE", "G", etf="EPU"),
    Country("Colombia", "CO", "G", "H", etf="GXG"),
    Country("Nigeria", "NG", "G", "I", etf="NGE"),
    # H -- convergence capital-importer
    Country("Poland", "PL", "H", etf="EPOL"),
    Country("Hungary", "HU", "H"),
    Country("Czechia", "CZ", "H"),
    Country("Romania", "RO", "H"),
    Country("Mexico", "MX", "H", etf="EWW"),
    Country("Brazil", "BR", "H", "G", etf="EWZ"),
    Country("India", "IN", "H", etf="INDA"),
    Country("Indonesia", "ID", "H", etf="EIDO"),
    Country("Philippines", "PH", "H", "I", etf="EPHE"),
    # I -- frontier dollar-dependent
    Country("Turkey", "TR", "I", etf="TUR"),
    Country("Egypt", "EG", "I", etf="EGPT"),
    Country("Pakistan", "PK", "I", etf="PAK"),
    Country("Argentina", "AR", "I", etf="ARGT"),
    Country("South Africa", "ZA", "I", "G", etf="EZA"),
    Country("Sri Lanka", "LK", "I"),
    # X -- sanctioned / closed
    Country("Russia", "RU", "X"),
    Country("Iran", "IR", "X"),
    Country("Venezuela", "VE", "X"),
]


def by_archetype() -> dict[str, list[Country]]:
    """Group countries by primary archetype tag."""
    out: dict[str, list[Country]] = {tag: [] for tag in ARCHETYPES}
    for c in COUNTRIES:
        out[c.primary].append(c)
    return out


def lookup(iso: str) -> Country | None:
    for c in COUNTRIES:
        if c.iso == iso:
            return c
    return None
