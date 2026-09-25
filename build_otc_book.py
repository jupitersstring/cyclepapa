"""OTC book -- the OTC opportunity set, kept out of the main ranking.

The main book ranks US-exchange names; OTC is a different animal (thin,
often dark, no index flows) but it is exactly where net-nets, cash shells,
going-dark squeeze-outs and NOL shells live. FMP now gives us quotes and TTM
ratios for ~10k active OTC common stocks (fmp_quotes.json), so this book
screens them with explicit data-quality guards:

  * CURRENCY: FMP's NCAV / net-net fields are in each company's REPORTING
    currency while OTC prices are USD per ADR/F-share -- comparing them for
    foreign names is meaningless (e.g. a JPY per-share net-net vs a USD ADR
    price). Balance-sheet screens therefore use US-domiciled names only.
    Foreign OTC gets a separate, ratio-only tab with sanity bounds.
  * LIQUIDITY: every name carries a dollar-volume tier (A >= $25k/day,
    B >= $5k, C >= $1k); below $1k/day is excluded as untradable.
  * SANITY: NCAV/mcap capped at 15x, ratios bounded -- FMP OTC data has
    share-count artifacts (e.g. post-reverse-split) that otherwise flood the
    top of a net-net screen.

Tabs: Contents | US Net-Nets | US Deep Value | Cash Shells | Going Dark |
NOL Shells | Foreign OTC | Methodology.  Output: OTC_BOOK.xlsx.
"""

from __future__ import annotations

import json
from pathlib import Path

from openpyxl import Workbook

from build_most_asymmetric_xlsx import (set_col_widths, write_title_band,
                                        write_header_row, write_body_row,
                                        write_footnote, BODY_BOLD, BODY_FONT)

ROOT = Path("/home/user/cyclepapa")
OUT = ROOT / "OTC_BOOK.xlsx"


def _load(n):
    p = ROOT / n
    return json.loads(p.read_text()) if p.exists() else {}


def _n(x):
    return x if isinstance(x, (int, float)) else None


import re as _re
_NON_COMMON = _re.compile(r"\b(preferred|pfd|pref|depositary|series\s+[a-z]\b|"
                          r"notes?|debentures?|warrants?|units?|rights?|trust\s+pref)\b|%", _re.I)


def is_common(v):
    return not _NON_COMMON.search(v.get("name") or "")


# FINRA OTC 5th-letter codes that mark NON-common lines: G/H/I convertible
# bonds, M/N/O/P preferreds, R rights, T with-warrants, U units, V when-issued,
# W warrants, X mutual fund. (A/B class, E delinquent, F foreign, Q
# bankruptcy, Y ADR are kept.)
_SECONDARY_5TH = set("GHIMNOPRTUVWX")


def _norm(name):
    return _re.sub(r"[^a-z0-9]", "", (name or "").lower().replace("inc", "")
                   .replace("corporation", "").replace("corp", "")
                   .replace("company", "").replace("ltd", ""))


def dollar_vol(v):
    return (v.get("avg_volume") or 0) * (v.get("price") or 0)


def tier(v):
    dv = dollar_vol(v)
    return "A" if dv >= 25e3 else "B" if dv >= 5e3 else "C" if dv >= 1e3 else None


def _pct(x):
    return f"{x*100:.0f}%" if x is not None else "—"


def _num(x, d=2):
    return round(x, d) if isinstance(x, (int, float)) else "—"


def _range_pos(v):
    lo, hi, px = v.get("fwk_low"), v.get("fwk_high"), v.get("price")
    if lo and hi and px and hi > lo:
        return (px - lo) / (hi - lo)
    return None


def sheet(wb, title, cols, headline, sub, headers, rows, foot):
    ws = wb.create_sheet(title)
    set_col_widths(ws, cols)
    write_title_band(ws, headline, sub, n_cols=len(cols))
    write_header_row(ws, 4, headers)
    r = 5
    for i, row in enumerate(rows, 1):
        write_body_row(ws, r, row, band=(i % 2 == 0), bold_first=True)
        ws.row_dimensions[r].height = 20
        r += 1
    if not rows:
        ws.cell(row=5, column=1, value="No names pass the screen.").font = BODY_FONT
        r = 6
    m = _re.match(r"\s*(\d+)", foot)
    if m and rows and int(m.group(1)) > len(rows):
        foot = f"Top {len(rows)} shown of {m.group(1)}. " + foot
    write_footnote(ws, r + 1, foot, len(cols))
    ws.sheet_view.showGridLines = False
    ws.freeze_panes = "A5"
    return ws


def main() -> int:
    q = _load("fmp_quotes.json")
    frames = _load("xbrl_frames_store.json")
    gd = _load("going_dark.json")
    nol = _load("nol_shell.json")
    oi = _load("otc_intent.json")

    def intent(k):
        """Short intent tag for the screen tabs: tier / strongest family / size."""
        r = oi.get(k)
        if not r or not r.get("families"):
            return "—"
        fam = max((f for f in r["families"] if f not in ("ANTICIPATION", "COST", "DELEVER")),
                  key=lambda f: r["families"][f], default=None)
        if not fam:
            return "—"
        t = {"ACT SIGNALLED": "▲ ", "BUILDING": "△ "}.get(r.get("tier"), "")
        sz = f" {r['size_pct_mcap']:.0%}" if r.get("size_pct_mcap", 0) >= 0.01 else ""
        return f"{t}{fam.lower().replace('_', ' ')}{sz}"
    FIN = _load("name_financials.json")

    def unvalidated(k):
        """The validated financials reject this line's market-cap basis, or it isn't the common."""
        f = FIN.get(k) or {}
        return f.get("pb_src") in ("mcap_suspect", "implausible", "inconsistent") or bool(f.get("not_common"))

    def undated(k):
        f = FIN.get(k)
        return f is not None and not f.get("stmt_date")

    def nm(k, v, n=26):
        return ((v.get("name") or "")[:n - 10] + " ⚠undated") if undated(k) else (v.get("name") or "")[:n]
    otc = {k: v for k, v in q.items() if v.get("otc")}
    # an OTC line whose company also has a US-exchange listing is a secondary
    # security (preferred / other class) -- its fundamentals are the parent's.
    exch_names = {_norm(v.get("name")) for v in q.values() if not v.get("otc")}
    def is_secondary(k, v):
        return (len(k) == 5 and k[4] in _SECONDARY_5TH) or \
            (_norm(v.get("name")) in exch_names)
    otc = {k: v for k, v in otc.items() if not is_secondary(k, v)}
    us = {k: v for k, v in otc.items()
          if v.get("country") == "US" and tier(v) and is_common(v)}
    fx = {k: v for k, v in otc.items()
          if v.get("country") not in (None, "US") and tier(v) and is_common(v)}

    wb = Workbook()
    wb.remove(wb.active)
    counts = {}

    # --- US Net-Nets: NCAV (total, USD) / mcap ---
    nn = []
    for k, v in us.items():
        if v.get("sector") == "Financial Services":
            continue                     # deposits make NCAV meaningless
        ncav, mcap = _n(v.get("ncav")), _n(v.get("mcap"))
        if unvalidated(k):
            continue
        if ncav and mcap and mcap >= 1e6:
            ratio = ncav / mcap
            if 1.0 <= ratio <= 15:
                nn.append((ratio, k, v))
    nn.sort(key=lambda t: -t[0])
    counts["US Net-Nets"] = len(nn)
    sheet(wb, "US Net-Nets", [9, 26, 7, 9, 9, 8, 8, 9, 8, 22],
          "US OTC Net-Nets — trading below net current asset value",
          "Graham's classic: NCAV (current assets − ALL liabilities) exceeds the "
          "market cap, so you buy the working capital and get the business free. "
          "US-domiciled only (currency-consistent), NCAV/mcap capped at 15× to "
          "strip data artifacts.",
          ["Ticker", "Name", "Tier", "NCAV/mcap", "Mcap $M", "P/B", "P/E",
           "52w pos", "$vol/day k", "Mgmt intent"],
          [[k, nm(k, v), tier(v), f"{r:.2f}×",
            _num(v["mcap"] / 1e6, 1), _num(v.get("p_b")), _num(v.get("p_e_trailing"), 1),
            _pct(_range_pos(v)), _num(dollar_vol(v) / 1e3, 1), intent(k)] for r, k, v in nn[:60]],
          f"{len(nn)} US OTC names trade below NCAV. Check each for: cash burn "
          "(the NCAV erodes), going-concern language, related-party or "
          "controlling-holder issues, and whether the NCAV is real (receivables/"
          "inventory quality). Tier = liquidity (A ≥$25k/day, B ≥$5k, C ≥$1k).")

    # --- US Deep Value: low P/B or low P/E with positive yields ---
    dv = []
    for k, v in us.items():
        if unvalidated(k):
            continue
        if k in FIN:                             # validated values, one number per name
            v = dict(v, p_b=FIN[k].get("p_b"), p_e_trailing=FIN[k].get("pe"))
        pb, pe = _n(v.get("p_b")), _n(v.get("p_e_trailing"))
        ey, fy = _n(v.get("earnings_yield")) or 0, _n(v.get("fcf_yield")) or 0
        if ey > 0.5 or fy > 0.6 or (pb is not None and 0 < pb < 0.05):
            continue                      # yield/book artifacts, not value
        if ey <= 0:
            continue                     # loss-makers are distress, not value
        if pe is not None and pe <= 0:
            continue                     # P/E and earnings yield disagree -> bad data
        cheap_b = pb is not None and 0.05 <= pb < 0.6
        cheap_e = pe is not None and 0 < pe < 7 and 0 < ey <= 0.5
        if (cheap_b or cheap_e) and (v.get("mcap") or 0) >= 3e6:
            score = (0.6 - min(pb, 0.6) if pb and pb > 0 else 0) * 2 + \
                    min(max(ey, 0), 0.5) + min(max(fy, 0), 0.5)
            dv.append((score, k, v))
    dv.sort(key=lambda t: -t[0])
    counts["US Deep Value"] = len(dv)
    sheet(wb, "US Deep Value", [9, 26, 7, 8, 8, 9, 9, 9, 9, 22],
          "US OTC Deep Value — low P/B or single-digit P/E with real earnings",
          "Cheap on book (P/B < 0.6) or earnings (P/E < 7 with positive earnings "
          "yield), ranked on a composite of discount-to-book + earnings yield + "
          "FCF yield. US-domiciled OTC, liquidity-tiered.",
          ["Ticker", "Name", "Tier", "P/B", "P/E", "Earn yld", "FCF yld",
           "Mcap $M", "52w pos", "Mgmt intent"],
          [[k, nm(k, v), tier(v), _num(v.get("p_b")),
            _num(v.get("p_e_trailing"), 1), _pct(v.get("earnings_yield")),
            _pct(v.get("fcf_yield")), _num((v.get("mcap") or 0) / 1e6, 1),
            _pct(_range_pos(v)), intent(k)] for s, k, v in dv[:60]],
          f"{len(dv)} names pass. Low P/B in OTC often means impaired assets or "
          "a controlled company — pair with the Net-Nets and Cash Shells tabs.")

    # --- Cash Shells: net cash (XBRL) vs market cap ---
    cs = []
    for k, v in us.items():
        if v.get("sector") == "Financial Services":
            continue                     # bank cash = deposits, not a floor
        if unvalidated(k):
            continue
        fr = frames.get(k) or {}
        nc, mcap = _n(fr.get("net_cash")), _n(v.get("mcap"))
        if nc and mcap and mcap >= 2e6 and 0.5 * mcap < nc <= 15 * mcap:
            op = _n(fr.get("op_income"))
            burn = (-op * 4) if (op is not None and op < 0) else 0.0
            runway = (nc / burn) if burn > 0 else None
            cs.append((nc / mcap, k, v, nc, op, runway))
    cs.sort(key=lambda t: -t[0])
    counts["Cash Shells"] = len(cs)
    sheet(wb, "Cash Shells", [9, 26, 7, 10, 10, 10, 10, 10, 22],
          "Cash Shells — net cash ≥ 50% of market cap",
          "US OTC SEC filers whose net cash (XBRL: cash − debt) is at least half "
          "the market cap — the floor under a shell, a reverse-merger vehicle, or "
          "a liquidation/tender candidate. Burn runway shown so eroding cash is "
          "visible.",
          ["Ticker", "Name", "Tier", "NetCash/mcap", "Net cash $M", "Mcap $M",
           "Op inc q $M", "Runway yrs", "Mgmt intent"],
          [[k, nm(k, v), tier(v), f"{r:.2f}×", _num(nc / 1e6, 1),
            _num(v["mcap"] / 1e6, 1), _num(op / 1e6, 2) if op is not None else "—",
            _num(rw, 1) if rw else ("∞" if (op or 0) >= 0 else "—"), intent(k)]
           for r, k, v, nc, op, rw in cs[:60]],
          f"{len(cs)} cash-heavy OTC filers. A cash shell with NO burn (∞ "
          "runway) is the cleanest floor; a burner's cash is a melting ice cube. "
          "Pair with the NOL tab — a cash shell with NOLs is a classic "
          "acquisition vehicle.")

    # --- Going Dark: Form 15/25 names, OTC status ---
    gdr = []
    for k, g in gd.items():
        v = q.get(k) or {}
        if not v.get("otc") and dollar_vol(v) >= 1e6:
            continue                   # still an active exchange listing: the Form 15/25 was another security
        if _re.search(r"-R[I]?$|-CVR$", k) or not (v or g.get("mcap")):
            continue                   # CVRs and lines with no data at all
        gdr.append((g.get("score", 0), k, g, v))
    gdr.sort(key=lambda t: -t[0])
    counts["Going Dark"] = len(gdr)
    sheet(wb, "Going Dark", [9, 26, 7, 8, 9, 9, 9, 8, 10],
          "Going Dark — Form 15 deregistrations & Form 25 delistings",
          "Companies leaving SEC reporting or their exchange. Controlling-holder "
          "squeeze-outs and deep-value orphans live here; the equity usually "
          "keeps trading OTC without public financials.",
          ["Ticker", "Name", "Forms", "Score", "Now OTC", "Mcap $M", "P/B",
           "Insider %", "Filed"],
          [[k, (g.get("company") or v.get("name") or "")[:26], "/".join(g.get("forms", [])),
            g.get("score"), "✓" if v.get("otc") else "—",
            _num((v.get("mcap") or g.get("mcap") or 0) / 1e6, 1),
            _num(v.get("p_b") or g.get("p_b")),
            _pct(g.get("insider_pct")), g.get("date")] for s, k, g, v in gdr[:60]],
          f"{len(gdr)} names (Form 15 = true deregistration, scores highest; "
          "Form 25 alone is often a routine security delisting). High insider % "
          "+ going dark = the squeeze-out setup.")

    # --- NOL Shells ---
    nl = sorted(nol.items(), key=lambda kv: -(kv[1].get("score") or 0))
    counts["NOL Shells"] = len(nl)
    sheet(wb, "NOL Shells", [9, 28, 7, 9, 9, 10, 11, 10],
          "NOL Shells — Section 382 tax-benefit preservation plans",
          "A Tax Benefits Preservation (NOL) rights plan means material net-"
          "operating-loss carryforwards the company is protecting — a hidden "
          "tax asset for a future acquirer (the WMIH / Clark Street archetype).",
          ["Ticker", "Name", "Score", "$vol/day k", "Mcap $M", "Cash-rich",
           "Below book", "Filed"],
          [[k, (r.get("company") or "")[:28], r.get("score"),
            _num(dollar_vol(q.get(k) or {}) / 1e3, 1) if q.get(k) else "—",
            _num((r.get("mcap") or 0) / 1e6, 1), "✓" if r.get("cash_rich") else "—",
            "✓" if r.get("below_book") else "—", r.get("date")] for k, r in nl[:60]],
          f"{len(nl)} names with an NOL rights plan in the last ~18 months. "
          "Best shells: micro-cap + cash-rich + NOL ≫ market cap.")

    # --- Foreign OTC: ratio-only, currency caveat ---
    fr_rows = []
    for k, v in fx.items():
        if unvalidated(k):
            continue
        if k in FIN:
            v = dict(v, p_b=FIN[k].get("p_b"), p_e_trailing=FIN[k].get("pe"),
                     mcap=FIN[k].get("mcap_usd") or v.get("mcap"))
        pe, pb = _n(v.get("p_e_trailing")), _n(v.get("p_b"))
        ey = _n(v.get("earnings_yield"))
        if pe and 0 < pe < 12 and pb and 0 < pb < 1.2 and ey and 0 < ey < 0.6 \
                and (v.get("mcap") or 0) >= 50e6:
            fr_rows.append((ey, k, v))
    fr_rows.sort(key=lambda t: -t[0])
    counts["Foreign OTC"] = len(fr_rows)
    sheet(wb, "Foreign OTC", [9, 26, 7, 7, 8, 8, 9, 10],
          "Foreign OTC (grey market) — cheap on dimensionless ratios",
          "Foreign companies' OTC lines (F-shares / unsponsored ADRs). Screened "
          "ONLY on currency-neutral ratios (P/E < 12, P/B < 1.2, positive "
          "earnings yield, mcap ≥ $50M). Primary-listing data should be checked.",
          ["Ticker", "Name", "Country", "Tier", "P/E", "P/B", "Earn yld", "Mcap $M"],
          [[k, (v.get("name") or "")[:26], v.get("country"), tier(v),
            _num(v.get("p_e_trailing"), 1), _num(v.get("p_b")),
            _pct(v.get("earnings_yield")), _num((v.get("mcap") or 0) / 1e6, 0)]
           for e, k, v in fr_rows[:60]],
          f"{len(fr_rows)} names. CAVEAT: net-net/NCAV figures are in the "
          "reporting currency and ADR ratios distort per-share comparisons, so "
          "balance-sheet screens are NOT applied here. Usually better executed "
          "on the home exchange.")

    # --- OTC Intent: management communications (calls, press releases, 8-K letters) ---
    cheap = {k for _, k, _ in nn} | {k for _, k, _ in dv} | {k for _, k, *_ in cs} | {k for _, k, _ in fr_rows}
    ir = [r for r in oi.values() if r.get("tier")]
    ir.sort(key=lambda r: (r["tier"] != "ACT SIGNALLED", r["ticker"] not in cheap, -r["score"]))
    counts["OTC Intent"] = len(ir)

    def ev_line(r):
        for f in (r.get("new_families") or []) + sorted(r.get("families") or {}, key=lambda f: -r["families"][f]):
            e = (r.get("evidence") or {}).get(f)
            if e and f not in ("ANTICIPATION", "COST", "DELEVER"):
                return f"[{e['date']} {e['kind'].lower()}] “{e['q'][:170]}”"
        return ""
    sheet(wb, "OTC Intent", [9, 24, 13, 6, 7, 7, 8, 9, 64],
          "OTC Intent — management says it will act (calls, press releases, letters)",
          "Most OTC companies never hold a call, so this reads where they do talk: "
          "press releases (full text from the wire), SEC 8-K EX-99 exhibits "
          "(results, shareholder letters, buyback/tender notices) and calls where "
          "they exist — clause-level commitment, negation, new-vs-routine, and the "
          "SIZE of any buyback/tender vs market cap. ● = also on a cheapness screen here.",
          ["Ticker", "Name", "Intent tier", "Score", "Size", "P/B", "Mcap $M", "Docs 12m", "Evidence (verbatim, dated)"],
          [[r["ticker"] + (" ●" if r["ticker"] in cheap else ""), (r.get("name") or "")[:24], r["tier"],
            round(r["score"], 1), (f"{r['size_pct_mcap']:.0%}" if r.get("size_pct_mcap") else "—"),
            _num(r.get("p_b")), _num((r.get("mcap") or 0) / 1e6, 1),
            " ".join(f"{k.lower()}:{n}" for k, n in sorted((r.get("docs_12m") or {}).items())),
            ev_line(r)] for r in ir[:80]],
          f"{len(ir)} OTC names with a current intent signal (ACT SIGNALLED = top decile with a "
          "realised/committed shareholder action, a NEW family vs the prior 12 months, or a "
          "stated buyback/tender >= 5% of mcap; BUILDING = top quartile; last document <= 200 "
          "days old). Weights come from the earnings-call validation (tender 2.2x, buyback/"
          "dividend 1.6x, value-gap 1.4x lift for subsequent action). Language predicts ACTION, "
          "not the re-rating by itself — pair it with the cheapness tabs. See "
          "OTC_INTENT_VALIDATION.md. Source: otc_comms.py.")

    # --- Methodology ---
    ws = wb.create_sheet("Methodology")
    set_col_widths(ws, [110])
    write_title_band(ws, "OTC Book — methodology & data quality",
                     "What is screened, and why the guards exist.", n_cols=1)
    notes = [
        f"Universe: {len(otc):,} active OTC common stocks from FMP (fmp_quotes.json); "
        f"{len(us):,} US-domiciled and {len(fx):,} foreign pass the $1k/day liquidity floor.",
        "OTC is kept OUT of the main MOST_ASYMMETRIC ranking on purpose: thin "
        "liquidity, stale quotes and no index flows would distort a universe-wide "
        "ranking. This book is the dedicated place to work it.",
        "Liquidity tiers: A ≥ $25k/day, B ≥ $5k, C ≥ $1k average dollar volume. "
        "Position size must respect the tier — a C name cannot absorb size.",
        "Currency guard: NCAV and Graham net-net are in the reporting currency; "
        "prices are USD per ADR/F-share. Balance-sheet screens use US-domiciled "
        "names only; foreign names are screened on ratios.",
        "Sanity caps: NCAV/mcap ≤ 15×; FMP OTC data contains share-count artifacts "
        "(e.g. after reverse splits) that otherwise dominate a net-net list.",
        "Cash Shells use SEC XBRL frames (net cash, operating income) where the "
        "company is an SEC filer; non-filers cannot be verified and are omitted.",
        "Going Dark / NOL Shells come from the live EDGAR scanners "
        "(going_dark_scan.py, nol_shell_scan.py) and include names on any venue.",
        "Sources: fmp_universe.py (FMP bulk profiles + TTM ratios + key metrics), "
        "xbrl_frames_store.py, going_dark_scan.py, nol_shell_scan.py.",
    ]
    for i, t in enumerate(notes, 5):
        c = ws.cell(row=i, column=1, value=t)
        c.font = BODY_FONT
        ws.row_dimensions[i].height = 32

    # --- Contents (first) ---
    ct = wb.create_sheet("Contents", 0)
    set_col_widths(ct, [22, 12, 70])
    write_title_band(ct, "OTC Book", "The OTC opportunity set, screened with "
                     "currency, liquidity and sanity guards.", n_cols=3)
    write_header_row(ct, 4, ["Tab", "Names", "What it is"])
    desc = {"US Net-Nets": "Below net current asset value (Graham).",
            "US Deep Value": "P/B < 0.6 or P/E < 7 with real earnings.",
            "Cash Shells": "Net cash ≥ 50% of market cap (with burn runway).",
            "Going Dark": "Form 15 deregistrations / Form 25 delistings.",
            "NOL Shells": "Section 382 NOL-protection rights plans.",
            "Foreign OTC": "Cheap foreign lines on currency-neutral ratios.",
            "OTC Intent": "Management communications signalling buybacks / tenders / capital return."}
    for i, (t, d) in enumerate(desc.items(), 5):
        write_body_row(ct, i, [t, counts.get(t, 0), d], band=(i % 2 == 0), bold_first=True)
    ct.sheet_view.showGridLines = False

    import name_financials
    import book_layout as bl
    fin = name_financials.load()
    name_financials.add_financials(wb, fin, index=1, skip=("Contents", "Methodology"))
    bl.key_numbers(wb, fin, skip=("Contents", "Methodology", "Name Financials"))
    dist = _load("distress_flags.json")
    if dist:
        bl.detail_column(wb, "Red flags (filings)", {t: bl.redflag_line(r) for t, r in dist.items()},
                         ["US Net-Nets", "US Deep Value", "Cash Shells", "OTC Intent", "NOL Shells"], width=40, min_fill=0.0)
    print("  QA fixes:", dict(bl.qa_fixes(wb, fin, skip=("Contents", "Methodology"))))
    cited = [str(c.value).strip() for c in wb["Name Financials"]["A"][4:] if c.value]
    intent_first = [r["ticker"] for r in sorted(oi.values(), key=lambda r: -r.get("score", 0))
                    if r.get("tier")][:20]
    bl.tear_sheets(wb, fin, list(dict.fromkeys(intent_first + cited)), max_names=50)
    bl.regroup(wb, [("Decide", ["Contents", "Tear Sheets", "Name Financials"]),
                    ("Theses", ["US Net-Nets", "US Deep Value", "Cash Shells", "Going Dark",
                                "NOL Shells", "Foreign OTC"]),
                    ("Signals", ["OTC Intent"]), ("Plumbing", ["Methodology"])],
               descriptions={"Tear Sheets": "One block per name: financials + every tab it appears on.",
                             "Name Financials": "FMP financial panel for every name in the book."})
    wb.save(OUT)
    print(f"wrote {OUT} ({len(wb.sheetnames)} tabs)")
    for t, n in counts.items():
        print(f"  {t:<14} {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
