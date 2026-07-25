"""
Godley configuration analysis -- the constellation, not the rank.

Godley never produced a cross-sectional league table. His unit of analysis was
the CONFIGURATION: given how the three balances sit, which sector is trying to
net-save, and what the policy stance is, *what must give*? This module replaces
the ranked score with that reasoning.

Three outputs:

  balance_path(iso)   the historical trajectory of all three balances (from real
                      IMF fiscal + current-account history), because the Seven
                      Unsustainable Processes are seven TRENDS, not levels.

  configure(iso)      the configuration label + the mechanism, drawn from
                      Godley's own cases:
                        savers-trap        private surplus + insufficient fiscal
                                           offset + shrinking external surplus
                                           (his Maastricht / German critique)
                        forced-borrower    private deficit deepening, externally
                                           funded (Seven Processes, US 1999)
                        deleveraging       private retrenching into surplus,
                                           fiscal absorbing (post-crisis)
                        fiscal-led         government injecting, fuel reaching
                                           profits (healthy accommodation)
                        external-dependent private deficit funded by foreign
                                           inflows (sudden-stop exposed)
                        balanced           nothing binding

  what_must_give(iso) the conditional sentence -- Godley's actual analytical
                      output. Given the constellation and the policy stance,
                      one of: fiscal accommodation / private re-leveraging /
                      income contraction / external improvement MUST occur.
                      "There is no fourth option."
"""

from __future__ import annotations

import pandas as pd

from . import strategic_analysis as SA
from .archetypes import lookup
from .sources import history as HIST


def balance_path(iso: str) -> pd.DataFrame | None:
    """
    Historical path of the three balances, %GDP, from real IMF history.
        government = fiscal balance      (negative = deficit)
        foreign    = -(current account)
        private    = current account - fiscal
    """
    rec = HIST.load().get(iso, {})
    f, c = rec.get("fiscal", {}), rec.get("ca", {})
    if not f or not c:
        return None
    yrs = sorted({int(y) for y in f} & {int(y) for y in c})
    yrs = [y for y in yrs if 1995 <= y <= 2024]
    if len(yrs) < 8:
        return None
    rows = []
    for y in yrs:
        fv, cv = f.get(str(y)), c.get(str(y))
        if fv is None or cv is None:
            continue
        rows.append({"year": y, "government": round(float(fv), 1),
                     "foreign": round(-float(cv), 1),
                     "private": round(float(cv) - float(fv), 1)})
    return pd.DataFrame(rows).set_index("year") if rows else None


def _trend(s: pd.Series, n: int = 4) -> float:
    """Change over the last n observations (the Godley 'rise in / fall in')."""
    v = s.dropna()
    if len(v) < n + 1:
        return 0.0
    return round(float(v.iloc[-1] - v.iloc[-1 - n]), 1)


def _norm(path: pd.DataFrame, col: str) -> float:
    """
    The sector's own stock-flow NORM -- its median balance over the pre-COVID
    era. Godley judged sustainability against norms, not absolute thresholds:
    a +8% private surplus is unremarkable for Germany and extraordinary for
    Brazil. The 2020-21 pandemic transfer years are excluded because they
    displaced every private balance by ~8pp and would corrupt the norm.
    """
    s = path.loc[[y for y in path.index if y <= 2019], col].dropna()
    if len(s) < 6:
        s = path[col].dropna()
    return round(float(s.median()), 1)


def configure(iso: str) -> dict | None:
    """
    Classify the current Godley configuration and state the mechanism.

    Judged on the GAP to each sector's own norm (not absolute cutoffs) and on
    the 2-year direction (not 4-year, which for a 2024 vintage would measure
    the COVID unwind rather than the structural trend).
    """
    path = balance_path(iso)
    if path is None or path.empty:
        return None
    last = path.iloc[-1]
    priv, gov, ext = float(last["private"]), float(last["government"]), float(last["foreign"])
    d_priv, d_gov, d_ext = (_trend(path["private"], 2), _trend(path["government"], 2),
                            _trend(path["foreign"], 2))
    priv_norm, gov_norm = _norm(path, "private"), _norm(path, "government")
    priv_gap = round(priv - priv_norm, 1)      # + = saving more than its norm
    gov_gap = round(gov - gov_norm, 1)         # + = tighter than its norm
    year = int(path.index[-1])

    consolidating = d_gov > 0.5     # balance improving = withdrawing demand
    expanding = d_gov < -0.5

    if priv_gap > 1.5 and not expanding:
        cfg, mech = ("savers-trap",
                     f"The private sector is saving {priv_gap:+.1f}pp more than its own "
                     f"norm while fiscal policy is {'tightening' if consolidating else 'not offsetting'}. "
                     "This is Godley's Maastricht case: if every sector tries to net-save, "
                     "income must fall.")
    elif priv_gap < -1.5 and d_priv < 0:
        cfg, mech = ("forced-borrower",
                     f"The private balance is {abs(priv_gap):.1f}pp below its norm and still "
                     "falling -- the configuration of Seven Unsustainable Processes. "
                     "It ends when the private sector refuses to borrow further.")
    elif priv < 0 and ext > 1.5:
        cfg, mech = ("external-dependent",
                     "A private deficit financed by foreign inflows. Stability is "
                     "conditional on continued foreign confidence.")
    elif d_priv > 1.5 and gov < -2.0:
        cfg, mech = ("deleveraging",
                     "The private sector is retrenching into surplus and the government "
                     "deficit is absorbing it. Demand holds only while fiscal accommodates.")
    elif gov_gap < -1.5 and priv > 0:
        cfg, mech = ("fiscal-led",
                     f"The government is running {abs(gov_gap):.1f}pp looser than its norm "
                     "and the private sector is accumulating the injection. Sustainable "
                     "while the fuel reaches profits and the external position holds.")
    else:
        cfg, mech = ("at-norm",
                     "Every sector sits close to its own historical norm: the "
                     "configuration can persist on current policy.")

    return {"iso": iso, "asof": year, "configuration": cfg, "mechanism": mech,
            "private": priv, "government": gov, "foreign": ext,
            "private_norm": priv_norm, "government_norm": gov_norm,
            "private_gap": priv_gap, "government_gap": gov_gap,
            "d_private": d_priv, "d_government": d_gov, "d_foreign": d_ext,
            "stance": "consolidating" if consolidating else
                      ("expanding" if expanding else "neutral")}


def disaggregate(iso: str) -> dict | None:
    """
    Split the private balance into households and corporations, and name which
    one is driving it.

    Godley & Lavoie (2007, p.25) repudiated the New Cambridge amalgamation --
    "households and production firms take entirely different decisions" -- and
    Godley had already disaggregated in Seven Unsustainable Processes (1999):
    "most of the fall in the private balance and the entire deficit has taken
    place in the household sector." Bill Martin's verdict on the behavioural
    justification is that "the pierced corporate veil rationale for
    across-sector aggregation has a limited following"; for the UK the
    veil-piercing evidence is weak (Feldstein & Fane find quarter-piercing,
    Pitelis essentially none).

    So the aggregate private balance is not the right object. The same +8%
    surplus is a HOUSEHOLD saving glut in Germany (consumption suppressed) and
    a CORPORATE one in the Netherlands and Ireland (profits not reinvested) --
    different mechanisms, different remedies. Romania's benign +1.7% aggregate
    conceals households running a -4.7% deficit.

    Returns None outside the Eurostat sector-accounts panel.
    """
    from .sources import sectors as SEC
    s = SEC.split(iso)
    if not s:
        return None
    hh, corp = s["households"], s["nonfin_corp"] + s["fin_corp"]
    f = SEC.frame(iso)
    # each sub-sector against its OWN pre-2020 norm, as with the aggregate
    def norm(col):
        if f is None or col not in f.columns:
            return None
        v = f.loc[[y for y in f.index if y <= 2019], col].dropna()
        return round(float(v.median()), 1) if len(v) >= 5 else None
    hh_norm = norm("households")
    corp_norm = None
    if f is not None and "nonfin_corp" in f.columns:
        pre = f.loc[[y for y in f.index if y <= 2019]]
        cc = (pre.get("nonfin_corp", pd.Series(dtype=float)).fillna(0)
              + pre.get("fin_corp", pd.Series(dtype=float)).fillna(0)).dropna()
        corp_norm = round(float(cc.median()), 1) if len(cc) >= 5 else None

    hh_gap = round(hh - hh_norm, 1) if hh_norm is not None else None
    corp_gap = round(corp - corp_norm, 1) if corp_norm is not None else None

    # which sub-sector is driving the deviation from norm?
    if hh_gap is not None and corp_gap is not None:
        driver = "household" if abs(hh_gap) >= abs(corp_gap) else "corporate"
    else:
        driver = "household" if abs(hh) >= abs(corp) else "corporate"

    # sub-sector configuration -- the mechanism the aggregate hides
    if hh < -1.0:
        # A household deficit is only a WARNING if it is deep relative to that
        # sector's own norm. Convergence economies (Romania) structurally run
        # household deficits: -4.7% against a -7.6% norm is an improvement, not
        # a Seven-Processes deterioration. Judging the level alone would
        # misread it -- the same norm-relative discipline as the aggregate.
        if hh_gap is not None and hh_gap > 0.5:
            sub = "household-deficit-improving"
            note = (f"Households run a deficit ({hh:.1f}% of GDP) but that is "
                    f"{hh_gap:+.1f}pp BETTER than their own norm of {hh_norm:+.1f}% -- "
                    "structural borrowing that is narrowing, not a deterioration.")
        else:
            sub = "household-deficit"
            note = (f"Households are running a deficit of {hh:.1f}% of GDP"
                    + (f", {abs(hh_gap):.1f}pp below their own norm" if hh_gap is not None else "")
                    + " -- borrowing to spend, behind an aggregate that looks benign. "
                      "This is the sub-sector configuration of the Seven "
                      "Unsustainable Processes.")
    elif hh_gap is not None and hh_gap > 1.5 and driver == "household":
        sub = "household-saving-glut"
        note = (f"Households are saving {hh_gap:+.1f}pp above their own norm "
                f"({hh:+.1f}% vs {hh_norm:+.1f}%): consumption is being suppressed.")
    elif corp_gap is not None and corp_gap > 1.5 and driver == "corporate":
        sub = "corporate-saving-glut"
        note = (f"Corporations are saving {corp_gap:+.1f}pp above their norm "
                f"({corp:+.1f}% vs {corp_norm:+.1f}%): profits are not being "
                "reinvested -- a corporate savings glut, not a consumer one.")
    elif corp < -1.5:
        sub = "corporate-borrowing"
        note = (f"Corporations are net borrowers ({corp:.1f}% of GDP) -- "
                "investing beyond internal funds.")
    else:
        sub = "balanced-within"
        note = "Neither sub-sector is far from its own norm."

    return {"iso": iso, "year": s["year"], "households": hh,
            "corporates": round(corp, 1), "households_norm": hh_norm,
            "corporates_norm": corp_norm, "households_gap": hh_gap,
            "corporates_gap": corp_gap, "driver": driver,
            "sub_configuration": sub, "sub_note": note}


def what_must_give(iso: str) -> str:
    """
    Godley's conditional output. Given the configuration and the policy stance,
    name the adjustment channels -- and be explicit that the identity leaves no
    fourth option.
    """
    cfg = configure(iso)
    if cfg is None:
        return ""
    sa = SA.evaluate(iso)
    name = lookup(iso).name if lookup(iso) else iso
    priv, gov, ext = cfg["private"], cfg["government"], cfg["foreign"]
    dp, dg = cfg["d_private"], cfg["d_government"]
    stance = cfg["stance"]

    # where the private balance must go for trend growth on current fiscal
    req = f"{sa.priv_balance_required:+.1f}" if sa else "n/a"
    now = f"{priv:+.1f}"

    head = (f"{name} runs a private balance of {now}% of GDP "
            f"(from {priv - dp:+.1f}% four years ago), a government balance of "
            f"{gov:+.1f}% ({stance}), and an external balance of {ext:+.1f}%.")

    if cfg["configuration"] == "savers-trap":
        body = (f"To grow at trend the private sector would have to absorb "
                f"{req}% of GDP. Since a surplus that large cannot be spent into "
                f"existence, either the government must accommodate, or the "
                f"external surplus must widen, or income must fall.")
    elif cfg["configuration"] == "forced-borrower":
        body = (f"Sustaining growth requires the private balance to reach {req}% "
                f"of GDP -- deeper into deficit. Either fiscal policy relaxes, or "
                f"the external deficit narrows, or the private sector stops "
                f"borrowing and income falls.")
    elif cfg["configuration"] == "external-dependent":
        body = (f"The private deficit is funded from abroad. If foreign financing "
                f"slows, either fiscal must expand to fill the gap, or the private "
                f"sector must retrench and income falls.")
    elif cfg["configuration"] == "deleveraging":
        body = (f"The private retrenchment is being absorbed by the government "
                f"deficit. If fiscal consolidates before private saving normalises, "
                f"income must fall to close the identity.")
    elif cfg["configuration"] == "fiscal-led":
        body = (f"Growth currently rests on the fiscal injection. Withdraw it before "
                f"private spending or net exports take over, and income falls.")
    else:
        body = (f"On current policy the configuration can persist; trend growth "
                f"implies a private balance of {req}% of GDP, within reach of "
                f"{now}%.")

    return head + " " + body + " There is no fourth option -- the identity must hold."


def panel() -> pd.DataFrame:
    """Configuration for every country with balance history."""
    rows = []
    from .archetypes import COUNTRIES
    for c in COUNTRIES:
        cfg = configure(c.iso)
        if cfg:
            cfg["country"] = c.name
            rows.append(cfg)
    return pd.DataFrame(rows).set_index("iso")


CONFIG_ORDER = ["savers-trap", "forced-borrower", "external-dependent",
                "deleveraging", "fiscal-led", "at-norm"]

CONFIG_BLURB = {
    "savers-trap": "Private sector insists on surplus; fiscal will not offset; "
                   "external surplus shrinking. Godley's Maastricht case.",
    "forced-borrower": "Private deficit deepening -- the Seven Unsustainable "
                       "Processes configuration.",
    "external-dependent": "Private deficit funded by foreign inflows; stability "
                          "conditional on foreign confidence.",
    "deleveraging": "Private retrenching into surplus, absorbed by the fiscal "
                    "deficit.",
    "fiscal-led": "Government injecting; private accumulating; sustainable while "
                  "fuel reaches profits.",
    "at-norm": "Every sector sits close to its own historical norm; the configuration can persist on current policy.",
}
