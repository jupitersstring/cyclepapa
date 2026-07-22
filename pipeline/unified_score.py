"""Unified per-ticker score combining every signal we have.

Inputs (joined per ticker):
  - fund_13f_holdings       smart money holding count + position size
  - fund_positions          XLSX-derived signals by section
  - holder_13d              SC 13D/G filings + activist pct
  - insider_clusters        live insider buy cluster (window_end ≤180d)
  - form4_transactions      recent open-market buys (code=P)
  - ticker_meta             mcap, exchange, ADV, price (from enrich_tickers.py)
  - candidates              curated qualitative tier + sector
  - expected_return         base-rate weighted ER

Output table: unified_signal (ticker, components, score, mcap_bucket)
Score formula:
  smart_money       =  log(1 + n_funds_13F)
  S3_new_init       =  3 * n_funds_section3
  S4_material_add   =  1.5 * n_funds_section4
  S1_top_pick       =  2 * n_funds_section1
  activist_13G_pct  =  0.5 * max_pct_class (capped at 30)
  insider_cluster   =  +5 if live cluster, +10 if 3+ insiders, +15 if 5+
  form4_buying      =  log(1 + cumulative_open_market_$M)
  micro_bonus       =  +5 if mcap <$300M, +3 if <$2B
  expected_return   =  ER% * 0.5
"""
import math, os, re, sqlite3, sys

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cyclepapa.db")

# Approximate FX -> USD (mid-2026). ticker_yf.mcap_m is in the LISTING currency;
# without conversion, foreign mega/micro-caps size and bucket by their raw local
# number (Samsung ₩1.87e15 -> "$1.87 quadrillion"; FPT.VN's $5M co -> "large").
# Minor units (GBp pence, ZAc cents) convert via their major /100. A currency
# absent here yields mcap=None (unknown bucket) rather than a wrong USD figure.
_FX_USD = {
    "USD": 1.0, "CAD": 0.73, "EUR": 1.08, "GBP": 1.28, "GBp": 0.0128, "JPY": 0.0064,
    "HKD": 0.128, "AUD": 0.66, "CHF": 1.12, "SGD": 0.74, "INR": 0.012, "KRW": 0.00073,
    "TWD": 0.031, "ZAR": 0.055, "ZAc": 0.00055, "NOK": 0.093, "DKK": 0.145, "SEK": 0.095,
    "PLN": 0.25, "IDR": 0.0000615, "TRY": 0.030, "HUF": 0.0028, "MYR": 0.21, "CNY": 0.138,
    "BRL": 0.18, "MXN": 0.055, "THB": 0.028, "PHP": 0.017, "NZD": 0.60, "ILS": 0.27,
    "VND": 0.0000393, "AED": 0.272, "SAR": 0.267, "QAR": 0.275, "EGP": 0.020, "NGN": 0.00065,
}

# --- security-type classification -------------------------------------------
# 13F filings include ETFs, preferreds, warrants, units and CVRs. Those are
# hedges/arb legs, not stock picks — an index fund held by 50 quants must not
# rank as a "consensus idea". Classified here once; pick sheets filter to
# sec_type='common' while reference sheets keep everything.
_ETF_TICKERS = frozenset("""SPY QQQ QQQM IWM IWN IWO IWF IWD IVV VOO DIA MDY RSP
 GLD SLV TLT IEF SHY HYG LQD JNK EEM EFA VWO FXI EWJ EWZ EZU ASHR GDX GDXJ GDXD
 USO UNG SMH SOXX XBI IBB KRE KBE VNQ ARKK GSG TIP ITA ITB IYE IYW IYM IYT IEO
 IEZ IXC SCJ LEMB XLE XLF XLK XLU XLV XLI XLY XLP XLB XLRE XLC BOXX MAGS TQQQ
 SQQQ""".split())
_ETF_NAME_RE = re.compile(
    r"\b(ETF|ETN)\b|iShares|SPDR|ProShares|Direxion|VanEck|WisdomTree|Global X|"
    r"YieldMax|GraniteShares|Xtrackers|Roundhill|Defiance|Pacer |Amplify |"
    r"First Trust|Invesco (QQQ|S&P|Exchange)|Vanguard .*(ETF|Index)|"
    r"Strategy Shares|Tidal Trust|Index Fund", re.I)
_PREF_RE = re.compile(r"-P[A-Z]{0,2}$")

def classify_sec_type(tkr, name, names):
    """names: {ticker: company name} for the whole universe — lets the suffix
    heuristic verify that RVMDW's base ticker RVMD is the SAME issuer (warrant
    quotes carry the issuer's name), so ARW/SNOW-style tickers never match."""
    nm = name or ""
    if _PREF_RE.search(tkr):
        return "preferred"
    if tkr.endswith("-RI") or re.search(r"\bCVR\b|contingent value", nm, re.I):
        return "right"
    if tkr.endswith(("-WT", "+")) or re.search(r"\bwarrant", nm, re.I):
        return "warrant"
    if tkr in _ETF_TICKERS or _ETF_NAME_RE.search(nm):
        return "etf"
    if re.search(r"\bunits?\b", nm, re.I) and re.search(r"acquisition|SPAC", nm, re.I):
        return "unit"
    # suffix heuristic: 5+ letter ticker ending W/U whose BASE ticker trades too,
    # and either we have no name, or the name matches the base issuer's name.
    if len(tkr) >= 5 and "-" not in tkr and tkr[:-1] in names:
        base_nm = names.get(tkr[:-1]) or ""
        same_issuer = (not nm) or (base_nm and nm[:12].upper() == base_nm[:12].upper())
        if same_issuer:
            if tkr.endswith("W"):
                return "warrant"
            if tkr.endswith("U"):
                return "unit"
    if re.search(r"\bnotes? due\b|% notes\b", nm, re.I):
        return "note"
    return "common"

# A fund that hasn't filed a 13F since this date is dormant/closed — its last
# (stale) holdings must NOT count as CURRENT smart money. Genuinely-active funds
# (incl. those that migrated CIKs) file quarterly, so anything filed in the last
# ~18 months is current. Holdings stay in the DB; they're just gated from the score.
STALE_FUND_CUTOFF = "2025-01-01"
_FRESH = (f"AND fund NOT IN (SELECT fund FROM fund_13f_state "
          f"WHERE last_filed IS NOT NULL AND last_filed < '{STALE_FUND_CUTOFF}')")

def run():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
    DROP TABLE IF EXISTS unified_signal;
    CREATE TABLE unified_signal (
      ticker TEXT PRIMARY KEY,
      name TEXT, exchange TEXT, sector TEXT, mcap_m REAL, price REAL,
      mcap_bucket TEXT,
      smart_money_n REAL,
      s1_top INTEGER, s2_thresh INTEGER, s3_new INTEGER, s4_add INTEGER,
      activist_filings INTEGER, activist_max_pct REAL,
      insider_cluster_dollars_m REAL, insider_n INTEGER,
      form4_buy_usd_m REAL, form4_sell_usd_m REAL,
      form4_buy_30d_m REAL, form4_sell_30d_m REAL,
      max_pct_book REAL, n_funds_5pct_book INTEGER,
      global_score REAL,        -- score using only signals that work cross-listing
      is_us INTEGER,            -- 1 if US-registered (no dot suffix), 0 otherwise
      cat8k_ma INTEGER, cat8k_dir INTEGER, cat8k_ctrl INTEGER,
      cat8k_pipe INTEGER, cat8k_bnk INTEGER, cat8k_n INTEGER,
      ev_ebitda REAL, pb_ratio REAL, pe_ttm REAL,
      revealed_pref REAL,       -- active accumulation: 2*s3 + s4 + 0.5*s1
      asymmetry_score REAL,     -- downside protection × upside potential
      expected_return_pct REAL,
      entry_bucket TEXT, vs_entry_pct REAL, anchor_px REAL, anchor_source TEXT,
      sec_type TEXT,            -- 'common'|'etf'|'preferred'|'warrant'|'unit'|'right'|'delisted'
      score REAL,
      components TEXT
    );
    CREATE INDEX idx_us_score ON unified_signal(score DESC);
    CREATE INDEX idx_us_bucket ON unified_signal(mcap_bucket);
    CREATE INDEX idx_us_pb ON unified_signal(max_pct_book DESC);
    CREATE INDEX idx_us_entry ON unified_signal(entry_bucket);
    """)

    # Per-ticker signals.
    # smart_money_n is CONVICTION-WEIGHTED, not a raw holder count. A fund's vote
    # diffuses as it holds more names: pod-shops / quants (Citadel 6687 names,
    # Millennium 4030, AQR 3739) run statistical-arb books where holding a stock
    # conveys ~no conviction, so each fund's vote is weighted min(1, CAP/n_names).
    # A focused book (<=CAP names) counts fully; a 600-name diversified book ~0.1;
    # a 6000-name quant ~0.01 — heavily downweighted, as intended.
    SM_CAP = 75.0
    fund_hn = {r[0]: r[1] for r in conn.execute(
        "SELECT fund, COUNT(DISTINCT cusip) FROM fund_13f_holdings "
        "WHERE sh_type IN ('SH','') AND ticker IS NOT NULL GROUP BY fund")}
    fund_w = {f: min(1.0, SM_CAP / hn) for f, hn in fund_hn.items() if hn > 0}
    sm = {}
    for tk, fund in conn.execute(
            "SELECT DISTINCT ticker, fund FROM fund_13f_holdings "
            "WHERE ticker IS NOT NULL AND sh_type IN ('SH','') " + _FRESH):
        sm[tk] = sm.get(tk, 0.0) + fund_w.get(fund, 1.0)
    sm = {tk: round(v, 1) for tk, v in sm.items()}
    # Section counts dedupe by CANONICAL manager, not raw fund string — the same
    # manager appears under several name variants ("CAS Investment Partners",
    # "... (Cliff", "... Sosin"), which inflated counts (NVDA S1 was 52 strings
    # but only 37 real managers). 552 strings -> 445 canonical managers.
    from _canon import canon
    _sec_mgrs = {}
    for r in conn.execute("""SELECT DISTINCT ticker, section, fund
        FROM fund_positions WHERE ticker IS NOT NULL"""):
        _sec_mgrs.setdefault((r["ticker"], r["section"]), set()).add(canon(r["fund"]))
    s_by = {}
    for (tk, sec), mgrs in _sec_mgrs.items():
        s_by.setdefault(tk, {})[sec] = len(mgrs)
    act = {}
    for r in conn.execute("""SELECT subject_ticker, COUNT(*) n, MAX(pct_class) m
        FROM holder_13d WHERE subject_ticker IS NOT NULL
          AND filed >= date('now','-24 months')
        GROUP BY subject_ticker"""):
        # Recency window: a 13D/G filed years ago (oldest row: 2005!) says nothing
        # about TODAY's register — holders exit without us seeing every amendment.
        # Only filings from the last 24 months count as a live activist signal.
        act[r["subject_ticker"]] = (r["n"], r["m"] or 0)
    cl = {}
    for r in conn.execute("""SELECT ticker, n_insiders, total_usd_m FROM insider_clusters
        WHERE DATE(window_end) >= DATE('now', '-180 days')"""):
        cl[r["ticker"]] = (r["n_insiders"], r["total_usd_m"] or 0)
    # Form 4 buys (P-code, acquired) — time-decayed weighting:
    #   ≤30 days   : weight 1.0
    #   31–60 days : weight 0.6
    #   61–120 days: weight 0.3
    #   121–180    : weight 0.1
    # Recent buying is much more informative than 6-month-old buying.
    f4 = {}                   # weighted dollar exposure
    f4_raw = {}               # unweighted 180d sum (for display)
    f4_30 = {}                # ≤30d dollar exposure (very-recent signal)
    # Sanity guards — exclude parse artifacts from both buy and sell signals:
    #  (a) a single trade worth more than the company's market cap (ADS-ratio
    #      mismatch — SVRE reported ordinary shares at the per-ADS price,
    #      43,200x inflation — or a corrupted price field);
    #  (b) a transaction price wildly off the known market price (>5x or <0.10x).
    #      Catches local-currency filings (INFY sells at Rs.1,178 vs $10.78) and
    #      corrupted fields (SBLK "px=$227,538"). The band is ASYMMETRIC on
    #      purpose: buys far below today's price are often REAL pre-runup entries
    #      (MANE insiders bought at $17 before a run to $127 = 0.13x; CIFR $6 vs
    #      $29 = 0.21x) — only <0.10x is treated as data corruption.
    # NB: outer columns MUST be table-qualified inside the correlated subquery —
    # a bare `price` here resolves to ticker_yf.price (inner scope), turning the
    # band check into y.price > y.price*5 (never true) and silently disabling it.
    _F4_SANE = """AND NOT EXISTS (SELECT 1 FROM ticker_yf y
              WHERE y.ticker = form4_transactions.ticker
                AND ((y.mcap_m > 0
                      AND form4_transactions.shares*form4_transactions.price/1e6 > y.mcap_m)
                  OR (y.price > 0 AND (form4_transactions.price > y.price*5
                                    OR form4_transactions.price < y.price*0.10))))
          AND NOT (form4_transactions.shares*form4_transactions.price/1e6 > 250
                   AND NOT EXISTS (SELECT 1 FROM ticker_yf y2
                                   WHERE y2.ticker = form4_transactions.ticker))"""
    for r in conn.execute("""
        SELECT ticker, SUM(shares*price)/1e6 AS usd_m,
               julianday('now') - julianday(trans_date) AS days_old
        FROM form4_transactions
        WHERE code='P' AND acquired=1 AND price IS NOT NULL
          AND trans_date >= date('now','-180 days')
          """ + _F4_SANE + """
        GROUP BY ticker, days_old"""):
        tk = r["ticker"]; d = r["days_old"] or 0; u = r["usd_m"] or 0
        if   d <= 30:  w = 1.0
        elif d <= 60:  w = 0.6
        elif d <= 120: w = 0.3
        else:          w = 0.1
        f4[tk] = f4.get(tk, 0) + u * w
        f4_raw[tk] = f4_raw.get(tk, 0) + u
        if d <= 30:
            f4_30[tk] = f4_30.get(tk, 0) + u

    f4_sell = {}              # weighted dollar exposure
    f4_sell_raw = {}
    f4_sell_30 = {}
    for r in conn.execute("""
        SELECT ticker, SUM(shares*price)/1e6 AS usd_m,
               julianday('now') - julianday(trans_date) AS days_old
        FROM form4_transactions
        WHERE code='S' AND price IS NOT NULL
          AND trans_date >= date('now','-180 days')
          """ + _F4_SANE + """
        GROUP BY ticker, days_old"""):
        tk = r["ticker"]; d = r["days_old"] or 0; u = r["usd_m"] or 0
        if   d <= 30:  w = 1.0
        elif d <= 60:  w = 0.6
        elif d <= 120: w = 0.3
        else:          w = 0.1
        f4_sell[tk] = f4_sell.get(tk, 0) + u * w
        f4_sell_raw[tk] = f4_sell_raw.get(tk, 0) + u
        if d <= 30:
            f4_sell_30[tk] = f4_sell_30.get(tk, 0) + u
    # entry-intact / in-the-money — current price vs smart-money entry anchor
    entry = {}
    for r in conn.execute("""SELECT ticker, bucket, vs_entry_pct, anchor_px, anchor_source
        FROM ticker_entry_intact"""):
        entry[r["ticker"]] = (r["bucket"], r["vs_entry_pct"], r["anchor_px"], r["anchor_source"])

    # Valuation ratios — EV/EBITDA and P/B.
    # PREFER yfinance (ticker_yf) — Yahoo's authoritative pre-computed values
    # handle dual-class, ADRs, currency correctly. Fall back to SEC-derived
    # ticker_valuation only where yfinance has no value.
    # EV/EBITDA is only meaningful when BOTH EV>0 and EBITDA>0. A negative EV
    # (net cash > market cap) or negative EBITDA (unprofitable) makes the ratio
    # meaningless — and neg/neg yields a deceptively cheap positive (e.g. LAB
    # showed 2.0x from -137M EV / -68M EBITDA). Guard at the source.
    valn = {}
    try:
        for r in conn.execute("""SELECT ticker,
                CASE WHEN ev_m > 0 AND ebitda_ttm > 0 THEN ev_ebitda END AS ev_ebitda,
                CASE WHEN pb_ratio > 0 AND pb_ratio <= 30 THEN pb_ratio END AS pb_ratio
                FROM ticker_valuation"""):
            valn[r["ticker"]] = (r["ev_ebitda"], r["pb_ratio"])
    except Exception:
        pass
    yf_pe = {}; yf_mcap = {}; yf_name = {}
    try:
        # P/B only meaningful with a sane positive book. >30 is almost always a
        # data artifact — an ADR/foreign currency mismatch (TSM "98x", real ~7x)
        # or a near-zero book — so reject it rather than display a false multiple.
        # mcap is FX-converted to USD: ticker_yf.mcap_m is in the LISTING currency,
        # so foreign names (Samsung ₩1.87e15, FPT.VN) otherwise size + bucket as if
        # the raw number were USD. Convert once here so every sheet is correct.
        for r in conn.execute("""SELECT ticker,
            CASE WHEN enterprise_value_m > 0 AND ebitda_m > 0 THEN ev_ebitda END AS ev_ebitda,
            CASE WHEN pb_ratio > 0 AND pb_ratio <= 30 THEN pb_ratio END AS pb_ratio,
            pe_ttm, mcap_m, long_name, currency
            FROM ticker_yf"""):
            ev, pb = r["ev_ebitda"], r["pb_ratio"]
            prev = valn.get(r["ticker"], (None, None))
            # yfinance wins when present; keep SEC value only for the missing leg
            valn[r["ticker"]] = (ev if ev is not None else prev[0],
                                 pb if pb is not None else prev[1])
            yf_pe[r["ticker"]] = r["pe_ttm"]
            if r["mcap_m"]:
                fx = _FX_USD.get(r["currency"] or "USD")
                yf_mcap[r["ticker"]] = (r["mcap_m"] * fx) if fx is not None else None
            if r["long_name"]:
                yf_name[r["ticker"]] = r["long_name"]
    except Exception:
        pass  # ticker_yf may not exist yet

    # 8-K catalysts — count of each material item type in the last 180d
    cat8k = {}     # ticker -> dict of has_ma/has_director/has_control/has_pipe/has_bankruptcy
    for r in conn.execute("""SELECT ticker,
            MAX(has_ma) AS ma, MAX(has_director) AS dir, MAX(has_control) AS ctrl,
            MAX(has_pipe) AS pipe, MAX(has_bankruptcy) AS bnk,
            SUM(has_ma + has_director + has_control + has_pipe + has_bankruptcy) AS event_count,
            MAX(filed) AS latest
        FROM catalysts_8k
        WHERE filed >= date('now','-180 days')
        GROUP BY ticker"""):
        cat8k[r["ticker"]] = {
            "ma":   r["ma"] or 0,
            "dir":  r["dir"] or 0,
            "ctrl": r["ctrl"] or 0,
            "pipe": r["pipe"] or 0,
            "bnk":  r["bnk"] or 0,
            "n":    r["event_count"] or 0,
            "latest": r["latest"],
        }
    # pct_book — highest %-of-fund-book any single fund has assigned to this ticker
    pct_book_max = {}
    pct_book_n5 = {}
    for r in conn.execute("""SELECT ticker, MAX(pct_book) AS m,
        SUM(CASE WHEN pct_book >= 5 THEN 1 ELSE 0 END) AS n5
        FROM fund_13f_holdings
        WHERE ticker IS NOT NULL AND pct_book IS NOT NULL
          AND pct_book <= 100
        """ + _FRESH + """
        GROUP BY ticker"""):
        pct_book_max[r["ticker"]] = r["m"] or 0
        pct_book_n5[r["ticker"]] = r["n5"] or 0
    # Augment max with researcher-disclosed book weights (fund_positions, kind
    # 'book', sane 0–100) so foreign / non-13F positions (e.g. material adds in
    # funds that don't file 13F) carry a real concentration figure instead of 0.
    for r in conn.execute("""SELECT ticker, MAX(pct_value) AS m
        FROM fund_positions
        WHERE ticker IS NOT NULL AND pct_kind = 'book'
          AND pct_value IS NOT NULL AND pct_value > 0 AND pct_value <= 100
        GROUP BY ticker"""):
        if (r["m"] or 0) > pct_book_max.get(r["ticker"], 0):
            pct_book_max[r["ticker"]] = r["m"]
    er = {r[0]: r[1] for r in conn.execute(
        "SELECT ticker, weighted_excess_12m FROM expected_return")}
    tm = {}
    for r in conn.execute("""SELECT ticker, name, exchange, sector, mcap_m, price
        FROM ticker_meta"""):
        tm[r["ticker"]] = dict(r)
    # backfill curated candidates for tickers not in ticker_meta yet
    for r in conn.execute("""SELECT ticker, name, sector, mcap_m, price FROM candidates"""):
        if r["ticker"] not in tm:
            tm[r["ticker"]] = {"ticker": r["ticker"], "name": r["name"], "exchange": None,
                               "sector": r["sector"], "mcap_m": r["mcap_m"], "price": r["price"]}

    universe = set(sm) | set(s_by) | set(act) | set(cl) | set(pct_book_max)
    # ticker -> name map for sec_type's same-issuer suffix check
    _names = {t: (tm.get(t, {}).get("name") or yf_name.get(t)) for t in universe}
    # Delisted set (quote 404s under valid crumb auth — the 2025-26 M&A wave):
    # a "pick" that can no longer be bought is noise; classified out of pick
    # sheets but kept in reference sheets like everything else.
    try:
        _dead = {r[0] for r in conn.execute("SELECT ticker FROM yf_dead")}
    except Exception:
        _dead = set()
    print(f"scoring {len(universe)} tickers")
    n = 0
    for tkr in universe:
        n13f = sm.get(tkr, 0)
        sec_counts = s_by.get(tkr, {})
        s1 = sec_counts.get(1, 0); s2 = sec_counts.get(2, 0)
        s3 = sec_counts.get(3, 0); s4 = sec_counts.get(4, 0)
        n13d, pct = act.get(tkr, (0, 0))
        ins_n, ins_m = cl.get(tkr, (0, 0))
        f4m = f4.get(tkr, 0)               # time-decayed (recent buys weighted more)
        f4m_raw = f4_raw.get(tkr, 0)       # raw 180d sum for display
        f4m_30 = f4_30.get(tkr, 0)         # ≤30d buys
        f4sell_m = f4_sell.get(tkr, 0)     # time-decayed sells
        f4sell_raw = f4_sell_raw.get(tkr, 0)
        f4sell_30 = f4_sell_30.get(tkr, 0)
        max_pb = pct_book_max.get(tkr, 0)
        n5_pb = pct_book_n5.get(tkr, 0)
        er_pct = er.get(tkr, 0) or 0
        meta = tm.get(tkr, {})
        # Prefer yfinance mcap (authoritative — handles dual-class/ADR) over
        # the SEC-derived ticker_meta mcap.
        mcap = yf_mcap.get(tkr) or meta.get("mcap_m") or 0
        e = entry.get(tkr, (None, None, None, None))
        entry_bucket, vs_entry_pct, anchor_px, anchor_src = e
        c8 = cat8k.get(tkr, {})
        c8_ma   = c8.get("ma",   0)
        c8_dir  = c8.get("dir",  0)
        c8_ctrl = c8.get("ctrl", 0)
        c8_pipe = c8.get("pipe", 0)
        c8_bnk  = c8.get("bnk",  0)
        ev_ebitda, pb_ratio = valn.get(tkr, (None, None))
        pe_ttm = yf_pe.get(tkr)
        # Dead-check applies only to what would otherwise be COMMON stock:
        # ETFs/warrants often lack the equity fields (marketCap/EV/PE) in
        # quoteSummary and would misclassify as delisted when they are simply
        # fund-type quotes — their real class already excludes them from picks.
        sec_type = classify_sec_type(tkr, _names.get(tkr), _names)
        if sec_type == "common" and tkr in _dead:
            sec_type = "delisted"
        # Revealed preference — what funds are ACTIVELY doing (not just holding):
        # new major positions weigh 2×, material adds 1×, top-conviction holds 0.5×
        revealed_pref = 2.0 * s3 + 1.0 * s4 + 0.5 * s1

        # scoring
        # Count-based curated terms are CAPPED. Uncapped, they made the ranking a
        # popularity contest (AMZN's s1=35 -> 70pts dwarfed everything and pinned
        # mega-caps at the top). The Nth fund calling a name a "top pick" adds
        # little beyond a strong consensus, so we saturate: 8-12 funds captures
        # ~all the credit. Preserves ordering, removes the mega-cap runaway.
        smart_money       = math.log1p(n13f) * 2
        s3_new_init       = 3.0 * min(s3, 8)      # was 3.0*s3 (uncapped)
        s4_material_add   = 1.5 * min(s4, 10)     # was 1.5*s4
        s1_top_pick       = 2.0 * min(s1, 12)     # was 2.0*s1  (AMZN 70 -> 24)
        activist_pct      = 0.5 * min(pct, 30)
        # max_pct_book of 10%+ = HIGH conviction; 20%+ = HYPER
        max_pb_term       = 0.6 * min(max_pb, 25)
        cluster_pct_book  = 1.5 * min(n5_pb, 12)   # capped like the other counts
        insider_cluster   = (5 if ins_n >= 1 else 0) + (5 if ins_n >= 3 else 0) + (5 if ins_n >= 5 else 0)
        insider_dollars   = math.log1p(ins_m) * 3 if ins_m > 0 else 0
        # form4_buying uses time-decayed sum: recent buys weight more
        form4_buying      = math.log1p(f4m) * 2 if f4m > 0 else 0
        # extra kicker for very-recent (≤30d) buying — heaviest signal
        form4_recent_bonus = math.log1p(f4m_30) * 2 if f4m_30 > 0 else 0
        form4_selling     = -math.log1p(f4sell_m) * 1.5 if f4sell_m > 0 else 0
        # very-recent sells hit harder
        form4_recent_sell_penalty = -math.log1p(f4sell_30) * 1.5 if f4sell_30 > 0 else 0
        micro_bonus       = (5 if 0 < mcap < 300 else 3 if 0 < mcap < 2000 else 0)
        # expected_return REMOVED from the live score: it covered only 14 of ~8,900
        # tickers and derives from a 19-event backtest with n=0-2 base rates (see
        # AUDIT_2026-07.md #2/#9). Kept as a research column (expected_return_pct),
        # not a scoring input, until it has a statistically sound basis.
        er_contribution   = 0.0
        # in-the-money / entry-intact — REVISED per adversarial review.
        # Reviewers found pattern: drawdowns >50% almost always signal
        # (a) stale anchor from pre-event cohort, (b) busted thesis with
        # stuck holders, or (c) parse errors. Sweet spot is -30 to -5%.
        entry_bonus       = 0
        if entry_bucket == "BELOW_ENTRY" and vs_entry_pct:
            x = abs(vs_entry_pct)
            if 5 <= x <= 30:
                entry_bonus = x / 6.0      # peaks at +5 around -30%
            elif 30 < x <= 50:
                entry_bonus = 5.0 - (x - 30) * 0.25  # tapers from +5 → 0
            else:  # x > 50  — busted thesis territory
                entry_bonus = -3.0
        elif entry_bucket == "NEAR_ENTRY":
            entry_bonus = 1.5
        elif entry_bucket == "WELL_ABOVE":
            entry_bonus = -3.0

        # NEW: sponsor-stake / sole-concentrator detection.
        # If single fund concentration is >50% AND no cluster of other funds
        # >=5%, treat as a legacy / sponsor stake not a smart-money conviction
        # cluster. Cap the pct_book contribution.
        if max_pb > 50 and n5_pb < 3:
            max_pb_term = 0.3 * min(max_pb, 25)   # halve the bonus

        # NEW: 8-K catalyst bonuses/penalties
        #   M&A entry (1.01) or completion (2.01)  = +5  (takeover catalyst)
        #   Control change (5.01)                  = +4  (often pre-takeover)
        #   Director change (5.02)                 = +1  (could be activist)
        #   PIPE / dilution (3.02)                 = -3  (counter-signal)
        #   Bankruptcy (1.03)                      = -10 (counter-signal)
        catalyst_8k = (5 * c8_ma + 4 * c8_ctrl + 1 * c8_dir
                       - 3 * c8_pipe - 10 * c8_bnk)

        score = (smart_money + s3_new_init + s4_material_add + s1_top_pick +
                 activist_pct + max_pb_term + cluster_pct_book +
                 insider_cluster + insider_dollars +
                 form4_buying + form4_recent_bonus +
                 form4_selling + form4_recent_sell_penalty +
                 micro_bonus + er_contribution + entry_bonus +
                 catalyst_8k)

        # ASYMMETRY — margin-of-safety (downside protection) × upside potential.
        # The multibagger setup: cheap valuation + smart money already in below
        # current price + catalyst + small enough to multiply, bounded downside.
        ms_cheap = 0.0
        if ev_ebitda is not None and 0 < ev_ebitda <= 15:
            ms_cheap += (15 - ev_ebitda) * 0.45          # 0–6.75 pts, cheaper = more
        if pb_ratio is not None and 0 < pb_ratio <= 2.0:
            ms_cheap += (2.0 - pb_ratio) * 2.5           # 0–5 pts, low P/B = asset floor
        ms_entry = 0.0
        if entry_bucket == "BELOW_ENTRY" and vs_entry_pct:
            x = abs(vs_entry_pct)
            ms_entry = (x/8.0) if x <= 40 else max(0, 5 - (x-40)*0.3)  # sweet spot, decay >40%
        up_conviction = 0.5 * min(max_pb, 20) + math.log1p(n13f) * 1.2 + 2.0*s3 + 1.0*s4
        up_catalyst   = 0.4 * min(pct, 30) + insider_cluster + (5 if c8_ma else 0) + (math.log1p(f4m_30)*2 if f4m_30 else 0)
        up_size       = 6 if (0 < mcap < 300) else 4 if (mcap < 2000) else 2 if (mcap < 10000) else 0
        pen = 0.0
        if ev_ebitda is not None and ev_ebitda > 30: pen += 5
        if c8_pipe: pen += 3
        if c8_bnk:  pen += 8
        if f4sell_30 and f4sell_30 > 1: pen += math.log1p(f4sell_30)
        if entry_bucket == "WELL_ABOVE": pen += 3
        asymmetry_score = round(ms_cheap + ms_entry + up_conviction + up_catalyst + up_size - pen, 2)

        # GLOBAL-FAIR score: drops the US-only terms (Form 4, insider clusters)
        # so foreign-exchange tickers (.L .T .TO .HK .AX etc.) — which can never
        # have those signals because SEC doesn't cover them — rank fairly.
        # Used for the Global Picks sheet.
        global_score = (smart_money + s3_new_init + s4_material_add + s1_top_pick +
                        activist_pct + max_pb_term + cluster_pct_book +
                        micro_bonus + er_contribution + entry_bonus)
        is_us = 0 if "." in tkr else 1

        if not mcap or mcap <= 0:
            bucket = "unknown"
        elif mcap < 50:    bucket = "nano"
        elif mcap < 300:   bucket = "micro"
        elif mcap < 2000:  bucket = "small"
        elif mcap < 10000: bucket = "mid"
        else:              bucket = "large"

        components = (f"sm={smart_money:.1f} s3*={s3_new_init:.1f} s4*={s4_material_add:.1f} "
                      f"s1*={s1_top_pick:.1f} act={activist_pct:.1f} pb_max={max_pb_term:.1f} "
                      f"pb_n5={cluster_pct_book:.1f} clust={insider_cluster:.0f} "
                      f"clust$={insider_dollars:.1f} f4buy={form4_buying:.1f} f4rec+={form4_recent_bonus:.1f} "
                      f"f4sell={form4_selling:.1f} f4recsell={form4_recent_sell_penalty:.1f} "
                      f"mic={micro_bonus:.0f} er={er_contribution:.1f} entry={entry_bonus:.1f} cat8k={catalyst_8k:.0f}")

        conn.execute("""INSERT INTO unified_signal VALUES
            (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (tkr, meta.get("name") or yf_name.get(tkr), meta.get("exchange"), meta.get("sector"),
             mcap, meta.get("price"), bucket,
             n13f, s1, s2, s3, s4,
             n13d, pct, ins_m, ins_n,
             f4m_raw, f4sell_raw,
             f4m_30, f4sell_30,
             max_pb, n5_pb,
             global_score, is_us,
             c8_ma, c8_dir, c8_ctrl, c8_pipe, c8_bnk, c8.get("n", 0),
             ev_ebitda, pb_ratio, pe_ttm, revealed_pref, asymmetry_score,
             er_pct,
             entry_bucket, vs_entry_pct, anchor_px, anchor_src,
             sec_type, score, components))
        n += 1
    conn.commit()
    print(f"wrote {n} unified_signal rows")

    # Summary by bucket
    print("\n=== TOP 25 BY SCORE (ex mega/ETF) ===")
    MEGA = {'AMZN','MSFT','NVDA','META','GOOGL','GOOG','AAPL','TSLA','BRK-A','BRK-B',
            'JPM','BAC','WFC','UNH','JNJ','V','MA','XOM','CVX','HD','PG','KO','PEP',
            'COST','AVGO','ORCL','WMT','DIS','NFLX','CRM','ABBV','TMO','ABT','MRK',
            'LLY','NKE','MCD','CSCO','INTC','AMD','ADBE','QCOM','TXN','HON',
            'SPY','QQQ','VOO','IWM','IEF','GLD','SLV','TLT','EFA','EEM','BIL','IVV',
            'HYG','XBI'}
    print(f"{'tkr':<8} {'score':>6} {'mcap$M':>9} {'buc':<5} {'13F':>3} {'S3':>2} {'S4':>2} {'S1':>2} {'13D':>2} {'pct%':>4} {'clu$M':>5}")
    rank = 0
    for r in conn.execute("""SELECT ticker, score, mcap_m, mcap_bucket, smart_money_n,
        s3_new, s4_add, s1_top, activist_filings, activist_max_pct,
        insider_cluster_dollars_m FROM unified_signal ORDER BY score DESC"""):
        if r[0] in MEGA: continue
        rank += 1; mc = r[2] or 0
        print(f"  {r[0]:<6} {r[1]:>6.1f} ${mc:>7,.0f} {r[3]:<5} {r[4]:>3} {r[5]:>2} {r[6]:>2} {r[7]:>2} {r[8]:>2} {r[9] or 0:>4.1f} ${r[10] or 0:>3.0f}")
        if rank >= 25: break

    print("\n=== MICRO/SMALL CAP LEADERBOARD ===")
    rank = 0
    for r in conn.execute("""SELECT ticker, score, mcap_m, mcap_bucket, smart_money_n,
        s3_new, s4_add, s1_top, activist_max_pct, insider_cluster_dollars_m, sector, name
        FROM unified_signal WHERE mcap_bucket IN ('nano','micro','small')
        ORDER BY score DESC LIMIT 25"""):
        if r[0] in MEGA: continue
        rank += 1; mc = r[2] or 0
        print(f"  {r[0]:<6} {r[1]:>6.1f} ${mc:>7,.0f} {r[3]:<5} {r[4]:>3} S3={r[5]} S4={r[6]} S1={r[7]} act={r[8] or 0:.1f}% clu=${r[9] or 0:.1f}M  {(r[10] or '')[:25]:<25} {(r[11] or '')[:30]}")

if __name__ == "__main__":
    run()
