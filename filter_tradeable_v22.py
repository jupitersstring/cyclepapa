"""
Post-filter v22 asymmetric output to currently-tradeable names.
Excludes SPACs, units/warrants, defunct companies, share-class duplicates.
"""
import csv, re

BAD_NAME = re.compile(
    r"Acquisition|Acq Corp|Acquisitions|Blank Check|Capital Corp|Cap Corp|"
    r"\bTrust\b|Muni|Municipal|LP|Holdings Ltd$|Partners$|Ltd Partnership|"
    r"Warrant|Rights|Debenture|Preferred|Bond Fund|Income Fund|Strategic Muni|"
    r"Emerging Mkts|Frontier Fund|BlackRock.*Muni|Blackrock.*Muni|"
    r"SPAC|Unit\b|Units\b|Note\b|Notes\b|Preferreds",
    re.I,
)
BAD_TICKER = re.compile(
    r"^.{0,}[.]|U$|UR$|WS$|WT$|PR$|RT$|WWW$|LOKB|CAPAU|TWND|BYNOU|EVGRU|"
    r"CPAQU|DTRTU|INAQ|HTPA|SPFR|MPAQU|LACQU|OXUSU|DWACU|KOYNU|MBVIU|SBXC|"
    r"SGAMU|MSTMU|ACAHU|GPATU|SFHG"
)

# Curated allowlist of currently-tradeable US equities of interest.
# Union of: S&P500 mega-caps, Russell-2000 notables, recent IPOs (>=2015),
# meme stocks, ETFs, popular small/mid caps. Used to filter down the ~3500
# v22 asymmetric candidates to things you can actually buy today.
# If ticker not in this set AND source != SP500 AND IPO year < 2015, we drop.
CURATED_ACTIVE = set("""
AAL AAPL ABBV ABNB ABR ABT ACHR ACN ADBE ADI ADM ADP ADSK AEE AEP AES AFL AFRM
AIG AIZ AJG AKAM ALAB ALB ALGN ALK ALL ALLE ALLY AMAT AMC AMCR AMD AME AMGN AMP
AMT AMZN ANET ANSS AON AOS APA APD APH APO APP APTV ARE ARKK ARM ARW ASML ATO
AVB AVGO AVY AWK AXON AXP AZO BA BAC BALL BAX BBBY BBY BDX BEN BF.B BG BIIB
BIO BK BKNG BKR BLDR BLK BMY BNTX BR BRK.B BRO BSX BTC BTI BWA BX BXP C CAG
CAH CARR CAT CB CBOE CBRE CCI CCL CCJ CDNS CDW CE CEG CF CFG CHD CHRW CHTR
CHWY CI CINF CL CLDX CLF CLX CMCSA CME CMG CMI CMS CNC CNP COF COIN COO COP
COR COST CPAY CPB CPRT CPT CRL CRM CRWD CRWV CSCO CSGP CSX CTAS CTRA CTSH
CTVA CVNA CVS CVX CZR D DAL DASH DAY DDOG DE DECK DELL DFS DG DGX DHI DHR
DIA DIS DKNG DKS DLR DLTR DOC DOCU DOV DOW DPZ DRI DT DTE DUK DUOL DVA DVN
DXCM EA EBAY ECL ED EFX EIX EL ELF ELV EMN EMR ENPH EOG EPAM EQH EQIX EQR
EQT ERIE ES ESS ETN ETR ETSY EVRG EW EXC EXE EXPD EXPE EXR F FAST FCX FDS
FDX FE FFIV FI FICO FIS FITB FIVE FIX FLS FMC FOX FOXA FSLR FSLY FTI FTNT
FTV GD GDDY GE GEHC GEN GEV GILD GIS GL GLW GM GME GNRC GOOG GOOGL GPC GPN
GRMN GS GWW HAL HAS HBAN HCA HD HES HIG HII HIMS HLT HOLX HON HOOD HPE HPQ
HRL HSIC HST HSY HUBB HUM HWM IBM ICE IDXX IEX IFF INCY INGM INTC INTU INVH
IONQ IP IPG IQV IR IRM ISRG IT ITW IVV IVZ J JBHT JBL JCI JKHY JNJ JNPR JPM
K KDP KEY KEYS KHC KIM KLAC KMB KMI KMX KO KR KSS KVUE KVYO KWEB L LCID LDOS
LEN LH LHX LI LIN LKQ LLY LMT LNT LOW LPSN LRCX LULU LUV LVS LW LYB LYV MA
MAA MAR MAS MCD MCHP MCK MCO MDB MDLZ MDT MET META MGM MHK MKC MKTX MLM MMC
MMM MNST MO MOH MOS MPC MPWR MRK MRNA MS MSCI MSFT MSI MSTR MTB MTCH MTD MU
NCLH NDAQ NDSN NEE NEM NET NFLX NI NIO NKE NNE NOC NOW NRG NSC NTAP NTRS NUE
NVDA NVR NWS NWSA NXE NXPI O ODFL OKE OKLO OKTA OMC ON ORCL ORLY OS OTIS
OXY PANW PARA PAYC PAYX PCAR PCG PEG PEP PFE PFG PG PGR PH PHM PINS PKG PLD
PLTR PM PNC PNR PNW POOL PPG PPL PRU PSA PSX PTC PTON PWR PYPL QBTS QCOM QQQ
QRVO RBRK RCL REG REGN RF RGTI RIVN RJF RKLB RL RMD ROKU ROL ROP ROST RPRX
RSG RTX RVTY RYAN SBAC SBUX SCHW SHOP SHW SJM SLB SMCI SMR SNA SNAP SNDR
SNOW SNPS SO SOFI SOUN SPG SPGI SPLK SPXL SPY SQQQ SRE STE STLD STT STX STZ
SW SWK SWKS SYF SYK SYY T TAP TDG TDY TECH TEL TER TFC TFX TGT TGTX TJX TKO
TMO TMUS TPG TPL TPR TRGP TRMB TROW TRV TSCO TSLA TSN TT TTWO TXN TXT TYL
UAL UBER UDR UHS ULTA UNH UNP UPS UPST URA URI USB V VICI VKTX VLO VLTO VMC
VRSK VRSN VRTX VST VTR VTRS VZ W WAB WAT WBA WBD WCN WDC WEC WELL WFC WM WMB
WMT WRB WSM WST WY WYNN XEL XOM XPEV XYL YUM ZBH ZBRA ZS ZTS
""".split())

# Some Ritter entries are misdated (SP500 added date used as IPO).
# These tickers are fine to keep but will be flagged.
MISDATED_RITTER = {"AMD","BLK","XYZ","NRTY"}

def looks_tradeable(name, ticker, source, ipo_year):
    if not name or not ticker: return False
    if BAD_NAME.search(name): return False
    if BAD_TICKER.search(ticker): return False
    if len(ticker) > 5: return False
    # SP500 source or curated list only — everything else is noise/defunct
    return source == "SP500" or ticker in CURATED_ACTIVE

def main():
    rows = []
    with open("/home/user/cyclepapa/data/universe_asymmetric_v22.csv") as f:
        for r in csv.DictReader(f):
            try:
                iy = int((r.get("ipo") or "0000")[:4])
            except:
                iy = 0
            if looks_tradeable(r["name"], r["ticker"], r.get("source",""), iy):
                rows.append(r)

    # Sort by asymmetry
    rows.sort(key=lambda r: -float(r["asymmetry"]))

    # Export filtered CSV
    out = "/home/user/cyclepapa/data/tradeable_asymmetric_v22.csv"
    fields = ["rank","ticker","name","sector","source","ipo","age","asymmetry",
              "score_now","score_peak","improvement","peak_month","runway_mo",
              "saturn_pop","bubblish_now","bubblish_peak","bubblish_month",
              "peak_jup_natNep","peak_nep_sun","peak_nep_mc"]
    with open(out,"w",newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for i, r in enumerate(rows, 1):
            r["rank"] = i
            w.writerow(r)

    print(f"{len(rows)} tradeable survivors -> {out}\n")

    # Top 50 overall
    print(f"{'='*160}")
    print(f"TOP 50 MOST ASYMMETRIC TRADEABLE NAMES (Saturn-safe, improving>=4, bubblish_peak>=2, score_now<18)")
    print(f"{'='*160}")
    print(f"{'Rk':>3s} {'Tkr':<6s} {'IPO':<11s} {'Age':>3s} {'Src':<7s} {'Now':>5s} {'Peak':>5s} {'Δ':>5s} {'PkMo':<8s} {'Run':>3s} {'BubPk':>5s} {'BubMo':<8s} {'Asym':>6s}  Name")
    for i, r in enumerate(rows[:50], 1):
        nm = (r["name"] or "")[:34]
        print(f"{i:3d} {r['ticker']:<6s} {r['ipo']:<11s} {int(r['age']):>3d} {r['source']:<7s} "
              f"{float(r['score_now']):5.1f} {float(r['score_peak']):5.1f} "
              f"{r['improvement']:>5s} {r['peak_month']:<8s} {int(r['runway_mo']):>3d} "
              f"{float(r['bubblish_peak']):5.2f} {r['bubblish_month']:<8s} {float(r['asymmetry']):6.2f}  {nm}")

    # By runway bucket
    for (lo, hi, lbl) in [(1,4,"IMMINENT (1-4 mo, peaks Apr-Aug 2026)"),
                          (5,9,"NEAR (5-9 mo, peaks Sep 2026-Jan 2027)"),
                          (10,15,"MEDIUM (10-15 mo, peaks Feb-Jul 2027)"),
                          (16,24,"LONG (16-24 mo, peaks Aug 2027-Apr 2028)")]:
        sub = [r for r in rows if lo <= int(r["runway_mo"]) <= hi][:20]
        if not sub: continue
        print(f"\n{'-'*160}")
        print(f"{lbl}  — top 20 by asymmetry")
        print(f"{'-'*160}")
        print(f"{'Rk':>3s} {'Tkr':<6s} {'IPO':<11s} {'Age':>3s} {'Src':<7s} {'Now':>5s} {'Peak':>5s} {'Δ':>5s} {'PkMo':<8s} {'Run':>3s} {'BubPk':>5s} {'Asym':>6s}  Name")
        for i, r in enumerate(sub, 1):
            nm = (r["name"] or "")[:35]
            print(f"{i:3d} {r['ticker']:<6s} {r['ipo']:<11s} {int(r['age']):>3d} {r['source']:<7s} "
                  f"{float(r['score_now']):5.1f} {float(r['score_peak']):5.1f} "
                  f"{r['improvement']:>5s} {r['peak_month']:<8s} {int(r['runway_mo']):>3d} "
                  f"{float(r['bubblish_peak']):5.2f} {float(r['asymmetry']):6.2f}  {nm}")

if __name__ == "__main__":
    main()
