"""Render the cyclepapa smart-money data as a *Times Lattice Compact* broadsheet —
a test of the CAR STYLE_GUIDE.md aesthetic applied to this dataset.

19th-century financial broadsheet: one 13.5px Times size everywhere, black ink on
white, 1px hairlines only, no boxes/fills/shadows. Two accent inks — lapis (#061933,
good) and crimson (#7a0019, bad) — as thin directional marks and 7%-opacity decile
washes. Tall scaleY masthead over a fleur divider; golden-ratio spacing; SVG spark
bands (price OHLC-ish line + decile wash). Output: broadsheet.html (self-contained).
"""
import os, sqlite3, html

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

    # snapshot numbers
    n_names = q(conn, "SELECT COUNT(*) FROM unified_signal WHERE sec_type='common'")[0][0]
    n_funds = q(conn, "SELECT COUNT(DISTINCT fund) FROM fund_13f_holdings WHERE ticker IS NOT NULL")[0][0]
    conv = q(conn, "SELECT COUNT(*) FROM (SELECT ticker FROM unified_signal WHERE sec_type='common')")[0][0]
    mom = q(conn, "SELECT AVG(mom_3mo) FROM price_stats") if _has_table(conn, "price_stats") else [[0]]
    avg_mom = mom[0][0] or 0
    top_mover = q(conn, "SELECT ticker, mom_3mo FROM price_stats ORDER BY mom_3mo DESC LIMIT 1") if _has_table(conn,"price_stats") else [["—",0]]
    tm_tk, tm_v = (top_mover[0][0], top_mover[0][1]) if top_mover else ("—", 0)

    parts = [f"<style>{CSS}</style>", '<div class="page">']
    # masthead
    parts.append(
        '<div class="masthead"><div><strong>Cyclepapa — Smart-Money Lattice</strong></div>'
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
                 + cell(f"{n_funds}", "funds tracked")
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
          AND us.ticker NOT IN ('AMZN','MSFT','NVDA','META','GOOGL','GOOG','AAPL','TSLA')
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
    parts.append(_panel("Top Setups — highest conviction ex-mega",
        ["Tk","Name","Sc","EV/EB","vsEnt","3mo","OffHi","Signals","Trend"], rows,
        rightclasses="l l tnum tnum tnum tnum tnum l l".split()))

    # PANEL 2 (left) — QoQ builders, PANEL 3 (right) — distributors (if prior data)
    if _has_table(conn, "fund_13f_prior") and q(conn, "SELECT COUNT(*) FROM fund_13f_prior")[0][0] > 0:
        builders, trimmers = _qoq(conn)
        left = _panel("Accumulating — net funds building (QoQ)",
            ["Tk","Net","New","Add","Trim"],
            [_qrow(b, True) for b in builders], rightclasses="l tnum tnum tnum tnum".split())
        right = _panel("Distributing — net funds trimming (QoQ)",
            ["Tk","Net","Trim","Exit","Add"],
            [_qrow(t, False) for t in trimmers], rightclasses="l tnum tnum tnum tnum".split())
        parts.append(f'<div class="cols">{left}{right}</div>')

    # PANEL 4 — cheap value with quality check
    val = q(conn, """SELECT us.ticker, us.name, us.ev_ebitda, us.pb_ratio, yf.rev_growth, yf.profit_margin, us.score
        FROM unified_signal us LEFT JOIN ticker_yf yf ON yf.ticker=us.ticker
        WHERE us.sec_type='common' AND us.ev_ebitda BETWEEN 2 AND 12 AND us.smart_money_n>=3
        ORDER BY us.ev_ebitda ASC LIMIT 16""")
    vrows = []
    for v in val:
        rg = v["rev_growth"]
        vrows.append(
            f'<tr><td class="l tk">{esc(v["ticker"])}</td>'
            f'<td class="l mut">{esc((v["name"] or "")[:30])}</td>'
            f'<td class="tnum">{v["ev_ebitda"]:.1f}x</td>'
            f'<td class="tnum">{("%.2f"%v["pb_ratio"]) if v["pb_ratio"] is not None else "·"}</td>'
            f'<td class="tnum">{arrow(rg*100,0) if rg is not None else "·"}</td>'
            f'<td class="tnum">{("%.0f%%"%(v["profit_margin"]*100)) if v["profit_margin"] is not None else "·"}</td>'
            f'<td class="tnum">{(v["score"] or 0):.0f}</td></tr>')
    parts.append(_panel("Cheap on EV/EBITDA — growth as the quality check",
        ["Tk","Name","EV/EB","P/B","RevGr","Margin","Sc"], vrows,
        rightclasses="l l tnum tnum tnum tnum tnum".split()))

    parts.append('<div class="divider"><span class="rule"></span></div>')
    parts.append('<p class="mut">Colour is data: <span class="up">▲ lapis</span> improving / accumulating · '
                 '<span class="dn">▼ crimson</span> deteriorating / distributing. One 13.5px Times size; '
                 'structure is hairlines only. A test of the Times-Lattice style guide on cyclepapa data.</p>')
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
    # Match on CUSIP (stable across quarters) + share counts (unit-independent),
    # then map to a ticker via cusip_map — the two quarters were mapped by
    # different logic so a ticker-level, value-based diff is pure noise.
    rows = q(conn, """
        WITH cur AS (SELECT fund,cusip,SUM(shares) sh FROM fund_13f_holdings
                     WHERE cusip IS NOT NULL AND sh_type IN ('SH','') GROUP BY fund,cusip),
             pri AS (SELECT fund,cusip,SUM(shares) sh FROM fund_13f_prior
                     WHERE cusip IS NOT NULL AND sh_type IN ('SH','') GROUP BY fund,cusip),
             chg AS (SELECT cur.fund, cur.cusip, cur.sh cur_sh, pri.sh pri_sh
                     FROM cur LEFT JOIN pri ON pri.fund=cur.fund AND pri.cusip=cur.cusip
                     UNION ALL
                     SELECT pri.fund, pri.cusip, NULL, pri.sh FROM pri LEFT JOIN cur
                       ON cur.fund=pri.fund AND cur.cusip=pri.cusip WHERE cur.fund IS NULL)
        SELECT cm.ticker AS ticker,
          SUM(CASE WHEN pri_sh IS NULL AND cur_sh>0 THEN 1 ELSE 0 END) n_new,
          SUM(CASE WHEN pri_sh IS NOT NULL AND cur_sh>pri_sh*1.05 THEN 1 ELSE 0 END) n_add,
          SUM(CASE WHEN cur_sh IS NOT NULL AND pri_sh IS NOT NULL AND cur_sh<pri_sh*0.95 THEN 1 ELSE 0 END) n_trim,
          SUM(CASE WHEN cur_sh IS NULL AND pri_sh>0 THEN 1 ELSE 0 END) n_exit
        FROM chg JOIN cusip_map cm ON cm.cusip=chg.cusip
        JOIN unified_signal u ON u.ticker=cm.ticker AND u.sec_type='common'
        WHERE cm.ticker NOT IN ('AMZN','MSFT','NVDA','META','GOOGL','GOOG','AAPL','TSLA','SPY','QQQ')
        GROUP BY cm.ticker""")
    scored = []
    for r in rows:
        net = (r["n_new"] + r["n_add"]) - (r["n_trim"] + r["n_exit"])
        scored.append((net, r))
    scored.sort(key=lambda x: -x[0])
    builders = [r for net, r in scored if net > 0][:14]
    trimmers = [r for net, r in scored if net < 0][-14:][::-1]
    return builders, trimmers

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
