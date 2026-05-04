"""International small/micro-cap universe (non-US, non-UK).

Curated tickers across Australia (.AX), Canada (.TO/.V), Japan (.T),
Hong Kong (.HK), Singapore (.SI), and selected Euro markets where
yfinance returns data. Treated as fundamentals-only (no equivalent of
EDGAR proxy text); the today_picks UK proxy mechanism extends here.
"""

INTL_UNIVERSE: dict[str, dict] = {
    # Australia (small/mid-cap value names with historical activist activity)
    "BSL.AX":    {"sector": "INDUST",    "name": "BlueScope Steel"},
    "PMV.AX":    {"sector": "RETAIL",    "name": "Premier Investments"},
    "JBH.AX":    {"sector": "RETAIL",    "name": "JB Hi-Fi"},
    "FLT.AX":    {"sector": "CONSUMER",  "name": "Flight Centre"},
    "SUL.AX":    {"sector": "RETAIL",    "name": "Super Retail Group"},
    "WEB.AX":    {"sector": "MEDIA",     "name": "Webjet"},
    "GUD.AX":    {"sector": "INDUST",    "name": "GUD Holdings"},
    "ARB.AX":    {"sector": "INDUST",    "name": "ARB Corporation"},
    "REH.AX":    {"sector": "BUILD",     "name": "Reece"},
    "ABC.AX":    {"sector": "BUILD",     "name": "Adbri"},

    # Canada (TSX) — small/mid value with M&A history
    "ATD.TO":    {"sector": "RETAIL",    "name": "Alimentation Couche-Tard"},
    "EQB.TO":    {"sector": "FIN",       "name": "EQB Inc"},
    "RCH.TO":    {"sector": "RETAIL",    "name": "Richelieu Hardware"},
    "TFII.TO":   {"sector": "INDUST",    "name": "TFI International"},
    "GIB-A.TO":  {"sector": "TECH",      "name": "CGI Inc"},
    "CIGI.TO":   {"sector": "PROP",      "name": "Colliers International"},
    "DOO.TO":    {"sector": "CONSUMER",  "name": "BRP Inc"},
    "MTY.TO":    {"sector": "CONSUMER",  "name": "MTY Food Group"},
    "GFL.TO":    {"sector": "INDUST",    "name": "GFL Environmental"},
    "WCN.TO":    {"sector": "INDUST",    "name": "Waste Connections"},
    "DPM.TO":    {"sector": "METALS",    "name": "Dundee Precious Metals"},
    "CGY.TO":    {"sector": "ENERGY",    "name": "Calfrac Well Services"},
    "PEY.TO":    {"sector": "ENERGY",    "name": "Peyto Exploration"},
    "BTE.TO":    {"sector": "ENERGY",    "name": "Baytex Energy"},
    "VET.TO":    {"sector": "ENERGY",    "name": "Vermilion Energy"},
    "AC.TO":     {"sector": "CONSUMER",  "name": "Air Canada"},
    "ONEX.TO":   {"sector": "FIN",       "name": "Onex Corporation"},
    "OTEX.TO":   {"sector": "TECH",      "name": "Open Text"},
    "BBD-B.TO":  {"sector": "INDUST",    "name": "Bombardier"},
    "IFP.TO":    {"sector": "INDUST",    "name": "Interfor"},

    # Hong Kong (selected mid-caps and special-situation candidates)
    "0700.HK":   {"sector": "TECH",      "name": "Tencent"},
    "0941.HK":   {"sector": "TELECOM",   "name": "China Mobile"},
    "0027.HK":   {"sector": "CONSUMER",  "name": "Galaxy Entertainment"},
    "1109.HK":   {"sector": "PROP",      "name": "China Resources Land"},
    "0001.HK":   {"sector": "PROP",      "name": "CK Hutchison"},
    "0006.HK":   {"sector": "ENERGY",    "name": "Power Assets"},
    "1928.HK":   {"sector": "CONSUMER",  "name": "Sands China"},
    "2318.HK":   {"sector": "FIN",       "name": "Ping An"},

    # Singapore
    "Z74.SI":    {"sector": "TELECOM",   "name": "Singtel"},
    "C09.SI":    {"sector": "PROP",      "name": "City Developments"},
    "F34.SI":    {"sector": "CONSUMER",  "name": "Wilmar International"},
    "C07.SI":    {"sector": "INDUST",    "name": "Jardine Cycle & Carriage"},
    "U11.SI":    {"sector": "FIN",       "name": "UOB"},

    # Japan (selected mid/small with recent governance activism)
    "9434.T":    {"sector": "TELECOM",   "name": "SoftBank Corp"},
    "8801.T":    {"sector": "PROP",      "name": "Mitsui Fudosan"},
    "8830.T":    {"sector": "PROP",      "name": "Sumitomo Realty"},
    "7203.T":    {"sector": "CONSUMER",  "name": "Toyota Motor"},
    "8267.T":    {"sector": "RETAIL",    "name": "AEON"},
    "3382.T":    {"sector": "RETAIL",    "name": "Seven & i Holdings"},
    "9613.T":    {"sector": "TECH",      "name": "NTT Data"},
    "4063.T":    {"sector": "INDUST",    "name": "Shin-Etsu Chemical"},

    # Germany/Continental Europe (mid-caps with recent activist + bid activity)
    "TKA.DE":    {"sector": "INDUST",    "name": "ThyssenKrupp"},
    "VARTA.DE":  {"sector": "INDUST",    "name": "Varta AG"},
    "RHM.DE":    {"sector": "DEFENCE",   "name": "Rheinmetall"},
    "ZAL.DE":    {"sector": "RETAIL",    "name": "Zalando"},
    "DPW.DE":    {"sector": "INDUST",    "name": "DHL Group"},
    "VOW3.DE":   {"sector": "CONSUMER",  "name": "Volkswagen"},

    # France
    "AC.PA":     {"sector": "CONSUMER",  "name": "Accor"},
    "CA.PA":     {"sector": "RETAIL",    "name": "Carrefour"},
    "EN.PA":     {"sector": "INDUST",    "name": "Bouygues"},

    # Italy
    "PIRC.MI":   {"sector": "INDUST",    "name": "Pirelli"},
    "G.MI":      {"sector": "FIN",       "name": "Generali"},
}


def by_region() -> dict[str, list[str]]:
    out = {"AU": [], "CA": [], "HK": [], "SG": [], "JP": [], "DE": [],
           "FR": [], "IT": []}
    for tk in INTL_UNIVERSE:
        if tk.endswith(".AX"): out["AU"].append(tk)
        elif tk.endswith(".TO") or tk.endswith(".V"): out["CA"].append(tk)
        elif tk.endswith(".HK"): out["HK"].append(tk)
        elif tk.endswith(".SI"): out["SG"].append(tk)
        elif tk.endswith(".T"): out["JP"].append(tk)
        elif tk.endswith(".DE") or tk.endswith(".F"): out["DE"].append(tk)
        elif tk.endswith(".PA"): out["FR"].append(tk)
        elif tk.endswith(".MI"): out["IT"].append(tk)
    return out
