"""Render the cyclepapa smart-money data as a *Times Lattice Compact* broadsheet —
a test of the CAR STYLE_GUIDE.md aesthetic applied to this dataset.

19th-century financial broadsheet: one 13.5px Times size everywhere, black ink on
white, 1px hairlines only, no boxes/fills/shadows. Two accent inks — lapis (#061933,
good) and crimson (#7a0019, bad) — as thin directional marks and 7%-opacity decile
washes. Tall scaleY masthead over a fleur divider; golden-ratio spacing; SVG spark
bands (price OHLC-ish line + decile wash). Output: broadsheet.html (self-contained).
"""
import os, sqlite3, html, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(BASE, "data", "cyclepapa.db")
OUT = os.path.join(BASE, "broadsheet.html")

LAPIS, CRIMSON, NEUTRAL = "#061933", "#7a0019", "#8a8a8a"

CSS = """
:root{
  --ink:#000000; --paper:#ffffff; --muted:#3f3f3f;
  --lapis:#061933; --crimson:#7a0019; --neutral:#8a8a8a;
  --gap-xs:0.236rem; --gap-sm:0.382rem; --gap-md:0.618rem; --gap-lg:1rem; --gap-xl:1.618rem;
}
*{box-sizing:border-box;}
html{font-size:13.5px;}
body{margin:0;background:#dcdcdc;
  font-family:"Times New Roman",Times,"Liberation Serif",serif;
  color:var(--ink);line-height:1.16;}
.page{background:var(--paper);border:1px solid var(--ink);
  width:min(142rem,100vw - 1rem);margin:0.5rem auto;padding:0.618rem 0.9rem;}
h1,h2,p,li,td,th,a,div,span{font-size:1rem;font-weight:400;}
a{color:var(--ink);text-decoration:underline;text-underline-offset:0.08em;}
.tnum{font-variant-numeric:tabular-nums;}
/* masthead */
.masthead{display:flex;justify-content:space-between;align-items:flex-end;
  padding-bottom:0.382rem;border-bottom:1px solid var(--ink);}
.masthead strong{display:inline-block;transform:scaleY(1.45);transform-origin:0 82%;
  font-weight:700;text-transform:uppercase;letter-spacing:0;}
.masthead .date{color:var(--muted);text-transform:uppercase;}
.divider{display:flex;align-items:center;gap:0.55rem;padding:0.382rem 0;}
.divider .rule{flex:1;height:0;border-top:1px solid var(--ink);}
/* snapshot strip */
.snapshot{display:flex;gap:0.382rem;padding:0.382rem 0;border-bottom:1px solid var(--ink);}
.snapshot .cell{flex:1;}
.snapshot .val{font-weight:700;}
.snapshot .lbl{color:var(--muted);text-transform:uppercase;font-size:1rem;}
/* panels */
.panel{border:1px solid var(--ink);margin-top:1rem;}
.panel-title{padding:0.236rem 0.382rem;border-bottom:1px solid var(--ink);
  font-weight:700;text-transform:uppercase;}
table{width:100%;border-collapse:collapse;}
th,td{padding:0.18rem 0.236rem;border-bottom:1px solid var(--ink);text-align:right;vertical-align:baseline;}
th{font-weight:700;text-transform:uppercase;border-bottom:1px solid var(--ink);}
td.l,th.l{text-align:left;}
td.tk{font-weight:700;}
.up{color:var(--lapis);} .dn{color:var(--crimson);} .mut{color:var(--muted);}
.cols{display:grid;grid-template-columns:1fr 1fr;}
.cols .panel:first-child{border-right:none;}
.spark{display:block;}
"""

def q(conn, sql, params=()):
    return conn.execute(sql, params).fetchall()

def esc(x):
    return html.escape(str(x)) if x is not None else ""

def arrow(v, digits=0):
    """Signed value as a lapis ▲ (good) / crimson ▼ (bad) mark."""
    if v is None or v == "":
        return '<span class="mut">·</span>'
    v = float(v)
    if v > 0:
        return f'<span class="up">▲{abs(v):.{digits}f}</span>'
    if v < 0:
        return f'<span class="dn">▼{abs(v):.{digits}f}</span>'
    return '<span class="mut">±0</span>'

def spark(closes, w=100, h=30):
    """Black price polyline in a 100x30 viewBox with a faint decile wash: lapis
    when the last close is in the top decile of the window, crimson if bottom."""
    if not closes or len(closes) < 3:
        return ""
    lo, hi = min(closes), max(closes)
    rng = (hi - lo) or 1
    pts = " ".join(f"{i/(len(closes)-1)*w:.1f},{h-2-((c-lo)/rng)*(h-4):.1f}"
                   for i, c in enumerate(closes))
    last = closes[-1]
    wash = ""
    if last >= lo + 0.9 * rng:
        wash = f'<rect x="0" y="0" width="{w}" height="{h}" fill="{LAPIS}" fill-opacity="0.07"/>'
    elif last <= lo + 0.1 * rng:
        wash = f'<rect x="0" y="0" width="{w}" height="{h}" fill="{CRIMSON}" fill-opacity="0.07"/>'
    return (f'<svg class="spark" viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
            f'preserveAspectRatio="none">{wash}'
            f'<polyline points="{pts}" fill="none" stroke="#000" stroke-width="0.8"/></svg>')

def build():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    asof = q(conn, "SELECT MAX(filed) FROM fund_13f_holdings")[0][0]
    px_asof = q(conn, "SELECT MAX(asof) FROM price_stats")[0][0] if _has_table(conn, "price_stats") else "—"
    # price series for sparks
    series = {}
    for tk, c in q(conn, "SELECT ticker, close FROM prices WHERE close>0 ORDER BY date"):
        series.setdefault(tk, []).append(c)
    # the daily-close history stopped updating when Yahoo refused requests:
    # say where the sparkline ends rather than pass it off as current
    spark_end = (q(conn, "SELECT MAX(date) FROM prices")[0][0] or "")[:10]

    # snapshot numbers
    n_names = q(conn, "SELECT COUNT(*) FROM unified_signal WHERE sec_type='common'")[0][0]
    # ALL tracked funds (roster), not just the 13F subset. The roster spans 13F
    # filers + curated-position + 13D/G-only foreign activists.
    n_funds = q(conn, "SELECT COUNT(*) FROM fund_meta")[0][0]
    n_13f = q(conn, "SELECT COUNT(DISTINCT fund) FROM fund_13f_holdings WHERE ticker IS NOT NULL")[0][0]
    conv = q(conn, "SELECT COUNT(*) FROM (SELECT ticker FROM unified_signal WHERE sec_type='common')")[0][0]
    mom = q(conn, "SELECT AVG(mom_3mo) FROM price_stats") if _has_table(conn, "price_stats") else [[0]]
    avg_mom = mom[0][0] or 0
    top_mover = q(conn, "SELECT ticker, mom_3mo FROM price_stats ORDER BY mom_3mo DESC LIMIT 1") if _has_table(conn,"price_stats") else [["—",0]]
    tm_tk, tm_v = (top_mover[0][0], top_mover[0][1]) if top_mover else ("—", 0)

    parts = [f"<style>{CSS}</style>", '<div class="page">']
    # masthead
    parts.append(
        '<div class="masthead"><div><strong>Fund Positioning</strong></div>'
        f'<div class="date">13F as-of {esc(_qend(asof))} · prices {esc(px_asof)}</div></div>')
    # fleur divider
    parts.append('<div class="divider"><span class="rule"></span>'
                 '<svg width="16" height="16" viewBox="0 0 16 16"><path d="M8 1 C8 4 6 5 6 7 C6 9 8 9 8 12 '
                 'C8 9 10 9 10 7 C10 5 8 4 8 1 Z M4 8 C2 8 2 11 5 12 C7 12 8 11 8 11 C8 11 9 12 11 12 '
                 'C14 11 14 8 12 8 M8 12 L8 15" fill="none" stroke="#000" stroke-width="0.7"/></svg>'
                 '<span class="rule"></span></div>')
    # snapshot strip
    def cell(v, l):
        return f'<div class="cell"><div class="val tnum">{v}</div><div class="lbl">{l}</div></div>'
    parts.append('<div class="snapshot">'
                 + cell(f"{n_names:,}", "common names")
                 + cell(f"{n_funds}", f"funds tracked ({n_13f} file 13F)")
                 + cell(f'<span class="{"up" if avg_mom>=0 else "dn"}">{avg_mom:+.1f}%</span>', "avg 3-mo momentum")
                 + cell(f"{esc(tm_tk)} {arrow(tm_v)}", "biggest 3-mo move")
                 + cell(f"{px_asof}", "price as-of")
                 + '</div>')

    # PANEL 1 — top setups (Action Dashboard content)
    setups = q(conn, """
        SELECT us.ticker, us.name, us.score, us.smart_money_n, us.activist_max_pct,
               us.insider_n, us.ev_ebitda, us.entry_bucket, us.vs_entry_pct,
               ps.mom_3mo, ps.off_high
        FROM unified_signal us LEFT JOIN price_stats ps ON ps.ticker=us.ticker
        WHERE us.sec_type='common' AND us.mcap_bucket!='unknown'
          AND us.ticker NOT IN ('AMZN','MSFT','NVDA','META','GOOGL','GOOG','AAPL','TSLA','BRK-A','BRK-B')
        ORDER BY us.score DESC LIMIT 22""")
    rows = []
    for s in setups:
        sig = []
        if (s["smart_money_n"] or 0) >= 3: sig.append("smart$")
        if (s["activist_max_pct"] or 0) >= 10: sig.append("activist")
        if (s["insider_n"] or 0) >= 2: sig.append("cluster")
        if s["entry_bucket"] == "BELOW_ENTRY": sig.append("below-entry")
        rows.append(
            f'<tr><td class="l tk">{esc(s["ticker"])}</td>'
            f'<td class="l mut">{esc((s["name"] or "")[:30])}</td>'
            f'<td class="tnum">{(s["score"] or 0):.0f}</td>'
            f'<td class="tnum">{("%.1fx"%s["ev_ebitda"]) if s["ev_ebitda"] is not None else "·"}</td>'
            f'<td class="tnum">{arrow(s["vs_entry_pct"],0) if s["entry_bucket"]=="BELOW_ENTRY" else "·"}</td>'
            f'<td class="tnum">{arrow(s["mom_3mo"],0)}</td>'
            f'<td class="tnum">{arrow(s["off_high"],0)}</td>'
            f'<td class="l mut">{esc(", ".join(sig))}</td>'
            f'<td>{spark(series.get(s["ticker"], []))}</td></tr>')
    parts.append(_panel("Top Setups — the highest scores (the ten largest US mega-caps left out)",
        ["Tk","Name","Sc","EV/EB","vsEnt","3mo","OffHi","Signals",f"1-yr trend to {spark_end}"], rows,
        rightclasses="l l tnum tnum tnum tnum tnum l l".split()))

    # PANEL 2 (left) — QoQ builders, PANEL 3 (right) — distributors (if prior data)
    if _has_table(conn, "fund_13f_prior") and q(conn, "SELECT COUNT(*) FROM fund_13f_prior")[0][0] > 0:
        builders, trimmers, listed = _qoq(conn)
        left = _panel("Accumulating — net funds building (QoQ)",
            ["Tk","Net","New","Add","Trim"],
            [_qrow(b, True) for b in builders], rightclasses="l tnum tnum tnum tnum".split())
        if listed:
            left += ('<p class="mut">Left out — new listings and SPACs, where holders were allocated or handed '
                     'shares rather than buying: ' + ", ".join(f"{esc(t)} ({n} funds{', ' + esc(k) if k else ''})"
                                                               for t, n, k in listed[:12]) + '.</p>')
        right = _panel("Distributing — net funds trimming (QoQ)",
            ["Tk","Net","Trim","Exit","Add"],
            [_qrow(t, False) for t in trimmers], rightclasses="l tnum tnum tnum tnum".split())
        parts.append(f'<div class="cols">{left}{right}</div>')

    # PANEL 4 — buying now: the Revealed Preference ranking (dated evidence)
    if _has_table(conn, "revealed_pref"):
        rp = q(conn, """SELECT rp.ticker, us.name, rp.rp_score, rp.f13_buyers, rp.f13_sellers, rp.ins_n,
                   rp.stake_n, rp.evidence_date, ps.mom_3mo
            FROM revealed_pref rp JOIN unified_signal us ON us.ticker = rp.ticker
            LEFT JOIN price_stats ps ON ps.ticker = rp.ticker
            LEFT JOIN ticker_yf y ON y.ticker = rp.ticker
            WHERE us.sec_type = 'common' AND rp.rp_score > 0 AND COALESCE(y.is_fund, 0) = 0
            ORDER BY rp.rp_score DESC LIMIT 14""")
        ipo_cut = (__import__("datetime").date.today() - __import__("datetime").timedelta(days=365)).isoformat()
        ipo = {t: d for t, d in q(conn, "SELECT ticker, ipo_date FROM ticker_yf WHERE ipo_date IS NOT NULL")}
        rrows = [f'<tr><td class="l tk">{esc(r["ticker"])}</td>'
                 f'<td class="l mut">{esc((r["name"] or "")[:30])}'
                 f'{" · IPO " + esc(ipo[r["ticker"]]) if (ipo.get(r["ticker"]) or "") >= ipo_cut else ""}</td>'
                 f'<td class="tnum">{(r["rp_score"] or 0):.0f}</td>'
                 f'<td class="tnum">{r["f13_buyers"] or 0}/{r["f13_sellers"] or 0}</td>'
                 f'<td class="tnum">{r["ins_n"] or 0}</td>'
                 f'<td class="tnum">{r["stake_n"] or 0}</td>'
                 f'<td class="tnum">{esc(r["evidence_date"] or "")}</td>'
                 f'<td class="tnum">{arrow(r["mom_3mo"],0)}</td></tr>' for r in rp]
        parts.append(_panel("Buying now — last quarter's 13F net buying, insider buys and new 13D/Gs (Revealed Preference)",
            ["Tk","Name","RP","13F buy/sell","Insiders","13D/G","Latest","3mo"], rrows,
            rightclasses="l l tnum tnum tnum tnum tnum tnum".split()))

    # PANEL 5 — cheap AND sound (the Valuation sheet's checks), not just cheap:
    # insurers, and loss-makers on a one-off EBITDA, read "cheap" on EV/EBITDA
    val = q(conn, """SELECT us.ticker, us.name, us.ev_ebitda, yf.fcf_yield, yf.roic,
               COALESCE(yf.rev_growth_fy, yf.rev_growth) rg, yf.net_debt_ebitda, us.score
        FROM unified_signal us JOIN ticker_yf yf ON yf.ticker=us.ticker
        WHERE us.sec_type='common' AND us.ev_ebitda BETWEEN 2 AND 12 AND us.smart_money_n>=3
          AND COALESCE(yf.sector, '') != 'Financial Services' AND COALESCE(yf.industry, '') != 'Shell Companies'
          AND yf.fcf_yield > 0 AND yf.fcf_yield <= 0.40 AND yf.roic >= 0.08
          AND COALESCE(yf.net_debt_ebitda, 0) < 3 AND COALESCE(yf.rev_growth_fy, yf.rev_growth, 0) > -0.05
        ORDER BY yf.fcf_yield DESC LIMIT 20""")
    from fund_moves import share_classes
    other_class = share_classes(conn)          # PBR-A beside PBR: one company, one row
    vrows = []
    for v in val:
        if v["ticker"] in other_class:
            continue
        rg = v["rg"]
        vrows.append(
            f'<tr><td class="l tk">{esc(v["ticker"])}</td>'
            f'<td class="l mut">{esc((v["name"] or "")[:30])}</td>'
            f'<td class="tnum">{v["ev_ebitda"]:.1f}x</td>'
            f'<td class="tnum">{v["fcf_yield"] * 100:.0f}%</td>'
            f'<td class="tnum">{v["roic"] * 100:.0f}%</td>'
            f'<td class="tnum">{arrow(rg*100,0) if rg is not None else "·"}</td>'
            f'<td class="tnum">{(v["score"] or 0):.0f}</td></tr>')
    parts.append(_panel("Cheap and sound — EV/EBITDA 2-12x, cash-generative, ROIC 8%+, low debt, not shrinking",
        ["Tk","Name","EV/EB","FCF yld","ROIC","RevGr","Sc"], vrows,
        rightclasses="l l tnum tnum tnum tnum tnum".split()))

    parts.append('<div class="divider"><span class="rule"></span></div>')
    parts.append('<p class="mut">Colour is data: <span class="up">▲ lapis</span> improving / accumulating · '
                 '<span class="dn">▼ crimson</span> deteriorating / distributing. Built from 13F, 13D/G, Form 4, '
                 '8-K and N-PORT filings and FMP market data; the detail behind every line is in '
                 'universe_analysis.xlsx (Action Dashboard, Revealed Preference, QoQ Change, Valuation).</p>')
    parts.append("</div>")
    open(OUT, "w").write("<!doctype html><meta charset='utf-8'>" + "".join(parts))
    print(f"wrote {OUT}")
    conn.close()

def _panel(title, heads, rows, rightclasses=None):
    ths = "".join(f'<th class="{(rightclasses[i] if rightclasses else "")}">{esc(h)}</th>'
                  for i, h in enumerate(heads))
    return (f'<div class="panel"><div class="panel-title">{esc(title)}</div>'
            f'<table><thead><tr>{ths}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>')

def _qoq(conn):
    # Share counts (unit-independent), matched at the TICKER level via
    # cusip_map, with the same guards as the workbook's Quarter Change sheet:
    #  * only funds whose prior book is on file and within [40%, 250%] of the
    #    current one — a fund with NO prior (a new roster add, a first filer)
    #    otherwise counted every position as a new buy, and a partial prior
    #    filing (Berkshire: $67B of $263B) manufactured adds and exits;
    #  * ticker-level, not raw CUSIP: an ADR -> ordinary CUSIP change between
    #    quarters (AZN) otherwise reads as an exit plus a new buy;
    #  * equity lines only: letters in the CUSIP issue code are debt.
    conn.execute("""CREATE TABLE IF NOT EXISTS prior_split_factor
        (fund TEXT, ticker TEXT, factor REAL, PRIMARY KEY (fund, ticker))""")   # built by ingest_splits
    rows = q(conn, """
        WITH ok_funds AS (
               SELECT c.fund FROM
                 (SELECT fund, SUM(value_k) v FROM fund_13f_holdings GROUP BY fund) c
                 JOIN (SELECT fund, SUM(value_k) v FROM fund_13f_prior GROUP BY fund) p
                 ON p.fund = c.fund
               WHERE c.v > 0 AND p.v BETWEEN c.v*0.4 AND c.v*2.5
                 -- one vote per filing (a manager under two roster names)
                 AND c.fund IN (SELECT MIN(fund) FROM fund_13f_holdings GROUP BY accession)),
             cur AS (SELECT h.fund, COALESCE(cm.ticker, h.cusip) tk, SUM(h.shares) sh
                     FROM fund_13f_holdings h LEFT JOIN cusip_map cm ON cm.cusip = h.cusip
                     WHERE h.cusip IS NOT NULL AND h.sh_type IN ('SH','')
                       AND substr(h.cusip,7,1) BETWEEN '0' AND '9'
                       AND substr(h.cusip,8,1) BETWEEN '0' AND '9'
                       AND h.fund IN (SELECT fund FROM ok_funds)
                     GROUP BY h.fund, tk),
             pri AS (SELECT h.fund, COALESCE(cm.ticker, h.cusip) tk,
                            SUM(h.shares) * COALESCE(MAX(sf.factor), 1) sh    -- split-adjusted
                     FROM fund_13f_prior h LEFT JOIN cusip_map cm ON cm.cusip = h.cusip
                     LEFT JOIN prior_split_factor sf ON sf.fund = h.fund
                          AND sf.ticker = COALESCE(cm.ticker, h.cusip)
                     WHERE h.cusip IS NOT NULL AND h.sh_type IN ('SH','')
                       AND substr(h.cusip,7,1) BETWEEN '0' AND '9'
                       AND substr(h.cusip,8,1) BETWEEN '0' AND '9'
                       AND h.fund IN (SELECT fund FROM ok_funds)
                     GROUP BY h.fund, tk),
             chg AS (SELECT cur.fund, cur.tk, cur.sh cur_sh, pri.sh pri_sh
                     FROM cur LEFT JOIN pri ON pri.fund=cur.fund AND pri.tk=cur.tk
                     UNION ALL
                     SELECT pri.fund, pri.tk, NULL, pri.sh FROM pri LEFT JOIN cur
                       ON cur.fund=pri.fund AND cur.tk=pri.tk WHERE cur.fund IS NULL)
        SELECT chg.tk AS ticker,
          SUM(CASE WHEN pri_sh IS NULL AND cur_sh>0 THEN 1 ELSE 0 END) n_new,
          SUM(CASE WHEN pri_sh IS NOT NULL AND cur_sh>pri_sh*1.05 THEN 1 ELSE 0 END) n_add,
          SUM(CASE WHEN cur_sh IS NOT NULL AND pri_sh IS NOT NULL AND cur_sh<pri_sh*0.95 THEN 1 ELSE 0 END) n_trim,
          SUM(CASE WHEN cur_sh IS NULL AND pri_sh>0 THEN 1 ELSE 0 END) n_exit
        FROM chg JOIN unified_signal u ON u.ticker=chg.tk AND u.sec_type='common'
        WHERE chg.tk NOT IN ('AMZN','MSFT','NVDA','META','GOOGL','GOOG','AAPL','TSLA','SPY','QQQ')
        GROUP BY chg.tk""")
    # a stock first listed after the prior quarter end (IPO, spin-off) or a SPAC
    # shows every holder as "new": an allocation, not accumulation
    import datetime as _dt
    from fund_moves import latest_due_quarter, _prev_quarter_end
    since = _prev_quarter_end(latest_due_quarter())
    # a spin-off's when-issued date can fall just before the quarter end
    # (Versigent, 2026-03-27): an all-new holder list within 45 days is a listing
    near = (_dt.date.fromisoformat(since) - _dt.timedelta(days=45)).isoformat()
    info = {t: (d, ind, nm) for t, d, ind, nm in q(conn, "SELECT ticker, ipo_date, industry, long_name FROM ticker_yf")}
    def listing(tk, all_new):
        d, ind, nm = info.get(tk, (None, None, None))
        if ind == "Shell Companies" or "acquisition corp" in (nm or "").lower():
            return "SPAC"
        if d and (d > since or (all_new and d > near)):
            return f"listed {d}"
        return None
    scored, listed = [], []
    for r in rows:
        net = (r["n_new"] + r["n_add"]) - (r["n_trim"] + r["n_exit"])
        k = listing(r["ticker"], r["n_add"] == 0 and r["n_trim"] == 0 and r["n_exit"] == 0)
        if k and net > 0:
            listed.append((r["ticker"], r["n_new"], k))
            continue
        scored.append((net, r))
    scored.sort(key=lambda x: -x[0])
    listed.sort(key=lambda x: -x[1])
    builders = [r for net, r in scored if net > 0][:14]
    trimmers = [r for net, r in scored if net < 0][-14:][::-1]
    return builders, trimmers, listed

def _qrow(r, building):
    net = (r["n_new"] + r["n_add"]) - (r["n_trim"] + r["n_exit"])
    if building:
        cells = [r["n_new"], r["n_add"], r["n_trim"]]
    else:
        cells = [r["n_trim"], r["n_exit"], r["n_add"]]
    tail = "".join(f'<td class="tnum">{"%.0f"%c}</td>' for c in cells)
    return (f'<tr><td class="l tk">{esc(r["ticker"])}</td>'
            f'<td class="tnum">{arrow(net,0)}</td>{tail}</tr>')

def _qend(filed):
    if not filed:
        return "—"
    import datetime, calendar
    try:
        fd = datetime.date.fromisoformat(str(filed)[:10])
        m = ((fd.month - 1)//3)*3; yr = fd.year if m else fd.year-1; m = m or 12
        return f"{yr}-{m:02d}-{calendar.monthrange(yr,m)[1]}"
    except Exception:
        return str(filed)[:10]

def _has_table(conn, name):
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone())

if __name__ == "__main__":
    build()
