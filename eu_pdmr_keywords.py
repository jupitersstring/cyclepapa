"""Multi-language PDMR / Directors-Dealings keyword bank.

EU Market Abuse Regulation Article 19 mandates that managers and
"persons closely associated" (PDMRs) disclose transactions in their
own company's securities within 3 business days. Each jurisdiction
uses its own canonical wording in the announcement headline. This
module compiles those patterns across the major European markets so
yfinance.Ticker(t).news titles can be scanned uniformly.

References:
  UK (FCA DTR 3.1.4R)       Listing Rule 3.1.4(R) PDMR notifications
  Germany (BaFin)            WpHG §15a Directors' Dealings / DGAP
  France (AMF)               Déclarations des dirigeants - AMF 223-22
  Italy (Consob)             Internal Dealing
  Netherlands (AFM)          Insiderstransacties
  Sweden (Finansinspekt.)    Insynstransaktion / Insynsregistret
  Spain (CNMV)               Operaciones de directivos
  Portugal (CMVM)            Operações de dirigentes
"""

from __future__ import annotations

import re


# Master pattern: PDMR-style buy announcement detection across languages.
PDMR_BUY = re.compile(
    r"\b("
    # ---- English ---------------------------------------------------------
    r"PDMR|"
    r"director(?:'s|s'?)?\s+(?:dealings?|shareholding|transactions?|notification)|"
    r"transactions?\s+in\s+own\s+shares|"
    r"(?:CEO|Chief\s+Executive|CFO|Chair|Chairman)\s+(?:purchase|acquires?|buys?)|"
    r"insider\s+(?:buy|purchase|acquisition)|"
    r"holding\s+disclosure|"
    r"persons?\s+discharging\s+managerial\s+responsibilit(?:y|ies)|"
    r"(?:exec(?:utive)?\s+)?director\s+(?:purchase|acquires?|buys?)|"
    r"open[- ]market\s+purchase|"
    # ---- Cross-cutting / EU MAR -----------------------------------------
    r"Article\s*19\s+MAR|"
    r"MAR\s+notification|"
    r"§\s*19\s+MAR|"
    r"MAR\s+§\s*19|"
    # ---- German ----------------------------------------------------------
    r"Directors?'?\s+Dealings|"
    r"Eigengesch[äa]fte\s+von\s+F[üu]hrungskr[äa]ften|"
    r"Stimmrechtsmitteilung|"
    r"§\s*15a\s+WpHG|"
    r"DGAP[- ]News|EQS[- ]News|"
    # ---- French ----------------------------------------------------------
    r"D[ée]claration[s]?\s+(?:de|des)\s+dirigeants|"
    r"Op[ée]rations?\s+r[ée]alis[ée]es?\s+par\s+(?:un|le)\s+dirigeant|"
    r"D[ée]claration\s+d['']op[ée]ration|"
    r"AMF\s+223[- ]22|"
    # ---- Italian ---------------------------------------------------------
    r"Internal\s+Dealing|"
    r"Operazioni\s+rilevanti|"
    r"Consob\s+Reg|"
    # ---- Dutch -----------------------------------------------------------
    r"Insiderstransacties|"
    r"AFM\s+meldingsregister|"
    # ---- Swedish ---------------------------------------------------------
    r"Insynstransakt|"
    r"Insynsregistret|"
    r"F[öo]rv[äa]rv\s+av\s+egna\s+aktier|"
    r"Insiderhandel|"
    # ---- Spanish ---------------------------------------------------------
    r"Operaciones?\s+de\s+(?:directivos|administradores)|"
    r"Comunicaci[óo]n\s+de\s+operaciones|"
    # ---- Portuguese ------------------------------------------------------
    r"Opera[çc][õo]es?\s+de\s+dirigentes|"
    r"CMVM\s+regulamento|"
    # ---- Buyback-specific (firm-side) -----------------------------------
    r"share\s+(?:repurchase|buy[- ]?back)\s+(?:programme|program|update)|"
    r"transaction[s]?\s+in\s+own\s+shares|"
    r"R[üu]ckkaufprogramm|"
    r"programme\s+de\s+rachat\s+d'?actions|"
    r"buyback\s+update"
    r")\b",
    re.I,
)

# Specific signal: the word "acquired" / "purchase" / "buy" within
# 200 chars of a director/PDMR mention -- distinguishes BUYS from
# sells/grants/exercises (which also use the same general wording).
PDMR_BUY_DIRECTIONAL = re.compile(
    r"(?:PDMR|director|CEO|CFO|chairman|chief executive|"
    r"f[üu]hrungskr[äa]ft|dirigeant|"
    r"insider|administrador)"
    r"[^.\n]{0,200}?"
    r"(?:purchas|acquir|bought|buys?|"
    r"erw[oa]rb|gekauft|"
    r"achat|acquis|"
    r"k[öo]p|f[öo]rv[äa]rv|"
    r"compra|adquir|"
    r"acquisto)",
    re.I,
)

# Firm-side buyback execution language
BUYBACK_EXECUTION = re.compile(
    r"\b("
    r"transaction[s]?\s+in\s+own\s+shares|"
    r"share\s+buy[- ]?back\s+update|"
    r"share\s+repurchase\s+(?:update|notification|completed)|"
    r"r[üu]ckkauf(?:s)?(?:[- ])?(?:programm|notification)|"
    r"rachat\s+d'?actions|"
    r"riacquisto\s+azioni\s+proprie|"
    r"compra\s+de\s+acciones\s+propias|"
    r"daily\s+share\s+repurchase|"
    r"acquired\s+shares\s+as\s+part\s+of\s+(?:the\s+)?repurchase"
    r")\b",
    re.I,
)


def score_titles(titles: list[str]) -> dict:
    """Return {pdmr_count, buy_directional_count, buyback_count, hits[]}."""
    body = "\n".join(titles)
    pdmr = len(PDMR_BUY.findall(body))
    direct = len(PDMR_BUY_DIRECTIONAL.findall(body))
    bb = len(BUYBACK_EXECUTION.findall(body))

    # Per-title hits (for debug surface)
    hits = []
    for t in titles:
        if PDMR_BUY.search(t) or BUYBACK_EXECUTION.search(t):
            hits.append(t[:160])

    return {
        "pdmr_count": pdmr,
        "buy_directional_count": direct,
        "buyback_count": bb,
        "total_signal_count": pdmr + direct + bb,
        "hits": hits,
    }
