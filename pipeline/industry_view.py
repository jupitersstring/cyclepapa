"""The industry lens: who holds, buys and sells each FMP industry's names.

Industries are FMP's own designations ("Banks - Regional", "Semiconductors",
"Oil & Gas E&P", "Insurance - Property & Casualty") — narrower than a sector,
which lumps banks with brokers and insurers, and independent of GICS. One
data pass shared by the universe book (Industry Index / Industry Detail) and
the style book (Industries by Style):

  holders  one vote per 13F filing (a book held under two roster names counts
           once), share classes merged (GOOG into GOOGL), equity lines only
  moves    the latest 13F quarter's position changes (fund_moves: the same
           rules as the Revealed Preference score)
  nport    the registered funds' full books: managers holding each listing
"""
import statistics
from fund_moves import quarter_moves, share_classes, short_fund

EQUITY = ("h.sh_type IN ('SH','') AND substr(h.cusip,7,1) BETWEEN '0' AND '9' "
          "AND substr(h.cusip,8,1) BETWEEN '0' AND '9'")
ONE_BOOK = "h.fund IN (SELECT MIN(fund) FROM fund_13f_holdings GROUP BY accession)"
# where EV/EBITDA means nothing and book value does
FINANCIAL = ("bank", "insurance", "capital markets", "asset management", "credit services",
             "financial - ", "mortgage", "reinsurance", "financial conglomerate")

def is_financial(industry):
    ind = (industry or "").lower()
    return any(k in ind for k in FINANCIAL)

class IndustryData:
    def __init__(self, conn):
        self.conn = conn
        self.cls = share_classes(conn)
        self.style = {f: (st, sg) for f, st, sg in conn.execute(
            "SELECT fund, macro_style, sub_group FROM fund_style")}
        self.facts = {}
        for r in conn.execute("""SELECT us.ticker, us.sec_type, COALESCE(y.long_name, us.name), us.mcap_m,
                us.mcap_bucket, us.smart_money_n, us.max_pct_book, us.n_funds_5pct_book, us.score,
                y.industry, y.sector, y.roe, y.fcf_yield, y.ptb_ratio, us.ev_ebitda, us.pe_ttm, ps.mom_3mo,
                COALESCE(y.rev_growth_fy, y.rev_growth), y.net_buyback_yield
            FROM unified_signal us LEFT JOIN ticker_yf y ON y.ticker = us.ticker
            LEFT JOIN price_stats ps ON ps.ticker = us.ticker"""):
            self.facts[r[0]] = dict(zip(
                ("sec", "name", "mcap", "bucket", "wtd", "max_pb", "n5", "score", "industry", "sector", "roe",
                 "fcf", "ptb", "ev", "pe", "mom", "growth", "buyback"), r[1:]))
        # holders: one vote per filing, share classes merged
        hold = {}
        for fund, tk, pct, val in conn.execute(f"""SELECT h.fund, h.ticker, SUM(h.pct_book), SUM(h.value_k)
                FROM fund_13f_holdings h WHERE h.ticker IS NOT NULL AND {EQUITY} AND {ONE_BOOK}
                GROUP BY h.fund, h.ticker"""):
            t = self.cls.get(tk, tk)
            d = hold.setdefault(t, {})
            p, v = d.get(fund, (0.0, 0.0))
            d[fund] = (p + (pct or 0.0), v + (val or 0.0))
        self.holders = {t: sorted(((p, v, f) for f, (p, v) in d.items()), reverse=True)
                        for t, d in hold.items()}
        # the latest quarter's moves
        moves, self.read = quarter_moves(conn)
        self.moves = {}
        for mv in moves:
            t = self.cls.get(mv["ticker"], mv["ticker"])
            d = self.moves.setdefault(t, {"net": 0.0, "buy": [], "sell": []})
            d["net"] += mv["pts"]
            (d["buy"] if mv["kind"] in ("new", "add") else d["sell"]).append(mv)
        # the registered funds' full books (non-US listings included)
        self.nport = {}
        try:
            for tk, mgr in conn.execute("SELECT DISTINCT ticker, manager FROM nport_holdings WHERE ticker IS NOT NULL"):
                self.nport.setdefault(self.cls.get(tk, tk), set()).add(mgr)
        except Exception:
            pass

    # ---- per-name helpers ----
    def is_pick(self, t):
        f = self.facts.get(t) or {}
        return (f.get("sec") or "common") == "common" and (f.get("industry") or "") not in ("", "Shell Companies")

    def industry(self, t):
        return (self.facts.get(t) or {}).get("industry") or ""

    def held_by(self, t, k=4):
        h = self.holders.get(t, [])
        s = "; ".join(f"{short_fund(f)} {p:.1f}%" for p, v, f in h[:k])
        return s + (f"; +{len(h) - k} more" if len(h) > k else "")

    def who(self, lst):
        return "; ".join(f"{short_fund(m['fund'])} ({m['label']})"
                         for m in sorted(lst, key=lambda m: -abs(m["pts"])))

    def styles(self, t, k=3):
        """The styles holding the name, ranked by their funds' combined % of
        book in it (conviction, not head count: the 1,800-name quant books
        hold everything at a sliver), with the number of their funds."""
        w, cnt = {}, {}
        for p, v, f in self.holders.get(t, []):
            st = (self.style.get(f) or ("",))[0]
            if st:
                w[st] = w.get(st, 0.0) + min(p, 100)
                cnt[st] = cnt.get(st, 0) + 1
        return ", ".join(f"{s} ({cnt[s]})" for s, x in sorted(w.items(), key=lambda x: -x[1])[:k])

    def conviction(self, t):
        f = self.facts.get(t) or {}
        mv = self.moves.get(t) or {}
        return ((f.get("wtd") or 0) * 2 + min(f.get("max_pb") or 0, 25) * 0.5
                + abs(mv.get("net") or 0) + len(self.nport.get(t, ())))

    def names_by_industry(self):
        """{industry: [ticker...]} — operating common stocks a tracked fund
        holds (13F or N-PORT) or moved last quarter."""
        out = {}
        tickers = set(self.holders) | set(self.moves) | set(self.nport)
        for t in tickers:
            if not self.is_pick(t):
                continue
            out.setdefault(self.industry(t), []).append(t)
        for ind in out:
            out[ind].sort(key=lambda t: -self.conviction(t))
        return out

    def industry_summary(self, ind, names):
        """One index row's figures for an industry."""
        mgrs = set()
        held_usd = 0.0
        for t in names:
            for p, v, f in self.holders.get(t, []):
                mgrs.add(f)
                held_usd += v
            mgrs |= {f"np:{m}" for m in self.nport.get(t, ())}
        net = sum((self.moves.get(t) or {}).get("net", 0.0) for t in names)
        buyers = {m["fund"] for t in names for m in (self.moves.get(t) or {}).get("buy", [])}
        sellers = {m["fund"] for t in names for m in (self.moves.get(t) or {}).get("sell", [])}
        bought = sorted(((self.moves[t]["net"], t) for t in names if t in self.moves and self.moves[t]["net"] > 0),
                        reverse=True)[:3]
        sold = sorted(((self.moves[t]["net"], t) for t in names if t in self.moves and self.moves[t]["net"] < 0))[:3]
        def med(key, lo=None, hi=None):
            vals = [(self.facts.get(t) or {}).get(key) for t in names]
            vals = [v for v in vals if isinstance(v, (int, float)) and (lo is None or v > lo) and (hi is None or v < hi)]
            return statistics.median(vals) if vals else None
        st = {}                                   # conviction-weighted, as in styles()
        for t in names:
            for p, v, f in self.holders.get(t, []):
                s = (self.style.get(f) or ("",))[0]
                if s:
                    st[s] = st.get(s, 0.0) + min(p, 100)
        return {
            "names": len(names), "managers": len(mgrs), "held_m": held_usd / 1e3, "net": net,
            "buyers": len(buyers), "sellers": len(sellers),
            "top": ", ".join(names[:4]),
            "bought": ", ".join(f"{t} {n:+.1f}" for n, t in bought),
            "sold": ", ".join(f"{t} {n:+.1f}" for n, t in sold),
            "pe": med("pe", 0, 500), "ev": med("ev", 0, 200), "ptb": med("ptb", 0, 50),
            "roe": med("roe", -5, 5), "mom": med("mom"),
            "styles": ", ".join(s for s, n in sorted(st.items(), key=lambda x: -x[1])[:2]),
        }
