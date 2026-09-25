"""Compound screens: incentive signals are most informative when they
*overlap*, per the InsideArbitrage tradition (Double Dipper = buyback +
insider buying; Spinsider = spin-off + insider buying).

Each screen takes a row-dict produced by psu_pipeline._process_filing
and returns (triggered: bool, reason: str). The pipeline runs every
screen and emits a `compound_screens` column listing every triggered
screen for a row.
"""

from __future__ import annotations

from typing import Callable


Row = dict


def _truthy(row: Row, key: str) -> bool:
    v = row.get(key)
    if isinstance(v, list):
        return bool(v)
    if isinstance(v, (int, float)):
        return v > 0
    return bool(v)


# ---------------------------------------------------------------------------
# Individual screens
# ---------------------------------------------------------------------------

def double_dipper(row: Row) -> tuple[bool, str]:
    """Buyback authorisation + insider buying language."""
    bb = (row.get("buyback_authorisation_musd") or 0) > 0
    ib = row.get("insider_buying_language") or False
    if bb and ib:
        return True, ("Double Dipper: buyback + insider buying ($"
                      f"{row.get('buyback_authorisation_musd'):.0f}M auth)")
    return False, ""


def spinsider(row: Row) -> tuple[bool, str]:
    """Spin-off + insider buying."""
    if (row.get("has_spinoff") and row.get("insider_buying_language")):
        return True, "Spinsider: spin-off + insider buying language"
    return False, ""


def activist_catalyst(row: Row) -> tuple[bool, str]:
    """Activist named + special committee or strategic-alts language."""
    has_activist = bool(row.get("activists_named"))
    process = (row.get("has_special_committee") or
               row.get("strategic_alts_language"))
    if has_activist and process:
        return True, ("Activist Catalyst: "
                      f"{', '.join((row.get('activists_named') or [])[:3])}"
                      " + process machinery")
    return False, ""


def inducement_lottery(row: Row) -> tuple[bool, str]:
    """Inducement-grant deep-OTM hurdle ladder.

    Triggered when the PSU asymmetry signal fires AND the top hurdle is
    >=2x current price -- the FNKO/RYAM/OPEN setup. Filters out SPAC
    warrant noise (-WT/-W/-UN/-R suffixes, 'Acquisition Corp' / 'SPAC'
    in the company name) where $18 trust-redemption prices look like
    deep-OTM hurdles but are just SPAC mechanics."""
    h = row.get("stock_price_hurdles") or []
    px = row.get("current_price") or 0
    if not h or not px:
        return False, ""
    ticker = (row.get("ticker") or "").upper()
    company = (row.get("company") or "").lower()
    spac_suffixes = ("-WT", "-W", "-UN", "-R", "+", ".U", ".W", ".WS")
    if (any(ticker.endswith(s) for s in spac_suffixes)
        or "acquisition corp" in company
        or "spac" in company
            or "blank check" in company):
        return False, ""
    # SPAC trust prices cluster at $10-12 / $18 (warrants) -- if every
    # hurdle is exactly one of these, treat as noise.
    if all(round(v, 2) in (10.0, 11.5, 12.0, 18.0) for v in h):
        return False, ""
    top = max(h)
    if top / px >= 2.0:
        return True, (f"Inducement Lottery: top hurdle ${top:.2f} "
                      f"vs spot ${px:.2f} = {top/px:.1f}x")
    return False, ""


def distressed_stub(row: Row) -> tuple[bool, str]:
    """BBGI / RGS pattern: debt event + tiny mcap + common preserved."""
    if (row.get("has_debt_event")
        and (row.get("balance_sheet_convexity") or 0) >= 60
            and (row.get("common_preservation") or 0) >= 50):
        return True, (f"Distressed Stub: debt event with "
                      f"{row.get('balance_sheet_convexity'):.0f} convexity "
                      f"+ {row.get('common_preservation'):.0f} preservation")
    return False, ""


def process_architecture(row: Row) -> tuple[bool, str]:
    """Boone-Mulherin: committee + adviser + (active bid OR strategic-alts)."""
    cmte = row.get("has_special_committee")
    adv = row.get("engaged_adviser") or bool(row.get("advisers_named"))
    salts = row.get("strategic_alts_language") or row.get("active_bid")
    if cmte and adv and salts:
        return True, "Process Architecture: committee + adviser + strategic alts"
    return False, ""


def cash_shell_activist(row: Row) -> tuple[bool, str]:
    """Cash-shell language + activist holder."""
    if (row.get("cash_shell_language") and row.get("activists_named")):
        return True, "Cash Shell + Activist"
    return False, ""


def controller_squeeze(row: Row) -> tuple[bool, str]:
    """Controller present + go-private language + majority-of-minority
    protection -- the bump trade setup."""
    ctrl = (row.get("largest_owner_pct") or 0) >= 30
    gp = row.get("go_private_language") or row.get("active_bid")
    mm = row.get("majority_of_minority")
    if ctrl and gp and mm:
        return True, ("Controller Squeeze: controller "
                      f"{row.get('largest_owner_pct'):.0f}% + "
                      "go-private + MoM protection")
    return False, ""


def governance_reset_buyback(row: Row) -> tuple[bool, str]:
    """Governance reset + buyback amplifier."""
    if (row.get("governance_reset")
        and (row.get("buyback_authorisation_musd") or 0) > 0):
        return True, "Governance Reset + Buyback"
    return False, ""


# ---------------------------------------------------------------------------
# Run-all
# ---------------------------------------------------------------------------

ALL_SCREENS: list[Callable[[Row], tuple[bool, str]]] = [
    double_dipper,
    spinsider,
    activist_catalyst,
    inducement_lottery,
    distressed_stub,
    process_architecture,
    cash_shell_activist,
    controller_squeeze,
    governance_reset_buyback,
]


def run_screens(row: Row) -> list[str]:
    """Return the list of screen names that triggered for this row."""
    triggered: list[str] = []
    for fn in ALL_SCREENS:
        ok, reason = fn(row)
        if ok:
            triggered.append(reason)
    return triggered
