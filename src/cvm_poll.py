#!/usr/bin/env python3
"""
cvm_poll.py — Brazilian CVM IPE (material-fact) disclosure poller.

Implements recommendation #2 from output/process_improvements.md.

CVM (Comissão de Valores Mobiliários) publishes IPE — Informações
Periódicas e Eventuais — filings as a free public weekly-refreshed
ZIP archive at dados.cvm.gov.br. Format is semicolon-delimited CSV
in latin-1 encoding, columns documented at
dados.cvm.gov.br/dados/CIA_ABERTA/DOC/IPE/META/meta_ipe_cia_aberta.txt.

IPE is the Brazilian equivalent of EDGAR 8-K + DEF 14A + S-1 combined:
material facts (Fato Relevante), assemblies (Assembleia), tender
offers (OPA), restructurings (Recuperação Judicial), capital increases
(Aumento de Capital), etc. — all in one feed.

Special-situation event filters (mapped from Tipo + Assunto fields):
  - Fato Relevante → tier_s.material_fact
  - OPA / Oferta Pública de Aquisição → tier_s.opa (tender offer)
  - Recuperação Judicial → tier_s.judicial_recovery (Brazil's Chapter 11)
  - Recuperação Extrajudicial → tier_s.extrajudicial_recovery
  - Cisão → tier_s.spinoff (demerger)
  - Incorporação / Fusão → tier_s.merger
  - Aumento do Capital Social → tier_s.capital_increase
  - Falência → tier_s.bankruptcy_br

Closes the Brazil leg of the LatAm coverage gap. Currently four of the
universe top 8 are Argentine A1 names (TGS, EDN, GGAL, PAM); Brazil
has been entirely absent. Petrobras governance, Eletrobras post-
privatisation, JBS-Mariana cycle — all special-situations playbooks
this poller starts surfacing.

Usage:
    python -m src.cvm_poll                     # poll today + last 1d
    python -m src.cvm_poll --days-back 7       # last week
    python -m src.cvm_poll --year 2025         # historical year
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import sys
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path

try:
    import requests
except ImportError:
    print("Install requests: pip install requests", file=sys.stderr)
    sys.exit(1)

REPO = Path(__file__).resolve().parent.parent
INBOX = REPO / "data" / "inbox"
ARCHIVE_BASE = ("https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/IPE/"
                "DADOS/ipe_cia_aberta_{year}.zip")

USER_AGENT = os.environ.get(
    "CVM_USER_AGENT", "cyclepapa-screener research@example.com")

# Pattern → (tier, sub_query_label, english_note).
# Matches Tipo + Especie + Assunto fields case-insensitively.
# Ordered: first match wins.
FILING_PATTERNS: list[tuple[str, str, str, str]] = [
    # ---- Tier-S: hard restructuring events ----
    (r"recupera[cç][aã]o\s+judicial",         "tier_s", "judicial_recovery",
     "Recuperação Judicial — Brazil's Chapter 11 equivalent"),
    (r"recupera[cç][aã]o\s+extrajudicial",    "tier_s", "extrajudicial_recovery",
     "Recuperação Extrajudicial — out-of-court restructuring"),
    (r"fal[eê]ncia",                          "tier_s", "bankruptcy_br",
     "Falência — formal bankruptcy"),
    (r"liquida[cç][aã]o",                     "tier_s", "liquidation",
     "Liquidação — formal liquidation"),
    (r"\boferta\s+p[uú]blica\s+de\s+aquisi[cç][aã]o\b|\bOPA\b", "tier_s", "opa",
     "OPA — Oferta Pública de Aquisição (tender offer)"),
    (r"cis[aã]o",                             "tier_s", "spinoff",
     "Cisão — demerger / spinoff"),
    (r"incorpora[cç][aã]o(?!\s+de\s+a[cç][oõ]es)", "tier_s", "merger",
     "Incorporação — merger by absorption"),
    (r"\bfus[aã]o\b",                         "tier_s", "merger",
     "Fusão — merger"),
    (r"aumento\s+do?\s+capital\s+social",     "tier_s", "capital_increase",
     "Aumento do Capital Social — capital increase / rights issue"),
    (r"grupamento|desdobramento",             "tier_s", "stock_split",
     "Grupamento / Desdobramento — reverse split / split"),
    (r"reorganiza[cç][aã]o\s+societ[aá]ria",  "tier_s", "corp_reorg",
     "Reorganização Societária — corporate reorganization"),
    # ---- Tier-S: material fact disclosure (Brazil's 8-K) ----
    (r"fato\s+relevante",                     "tier_s", "material_fact",
     "Fato Relevante — material-fact disclosure (8-K analogue)"),
    # ---- Revealed-preference signals ----
    (r"comunicado.*?(participa[cç][aã]o|aquisi[cç][aã]o).*?relevante",
     "rev_pref", "shareholding_change",
     "Material change in significant shareholding"),
    (r"recompra|programa\s+de\s+recompra",    "rev_pref", "buyback",
     "Share buyback programme"),
    # ---- Red flags ----
    (r"refor[mc]ula[cç][aã]o.*?demonstra[cç][oõ]es", "red_flag", "restatement",
     "Restatement of financial statements"),
]
FILING_PATTERNS_COMPILED = [(re.compile(p, re.I), t, s, n)
                            for p, t, s, n in FILING_PATTERNS]


def download_archive(year: int, retries: int = 3) -> bytes | None:
    """Fetch the year's IPE archive. Returns raw ZIP bytes."""
    url = ARCHIVE_BASE.format(year=year)
    headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    delay = 1.0
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=headers, timeout=60)
            if r.status_code == 404:
                print(f"  ! CVM {year} archive not yet published",
                      file=sys.stderr)
                return None
            r.raise_for_status()
            return r.content
        except requests.RequestException as exc:
            if attempt == retries - 1:
                print(f"  ! CVM {year} download failed after "
                      f"{retries} attempts: {exc}", file=sys.stderr)
                return None
            import time; time.sleep(delay); delay *= 2
    return None


def parse_archive(zip_bytes: bytes) -> list[dict]:
    """Unzip, parse CSV (latin-1, semicolon-delimited)."""
    zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    rows: list[dict] = []
    for name in zf.namelist():
        if not name.endswith(".csv"):
            continue
        with zf.open(name) as f:
            text = f.read().decode("latin-1", errors="replace")
        reader = csv.DictReader(io.StringIO(text), delimiter=";")
        for r in reader:
            rows.append(r)
    return rows


def classify(row: dict) -> tuple[str, str, str] | None:
    """Run the filing-pattern regex across Tipo + Especie + Assunto."""
    haystack = " ".join([
        row.get("Tipo", "") or "",
        row.get("Especie", "") or "",
        row.get("Assunto", "") or "",
        row.get("Categoria", "") or "",
    ])
    for pat, tier, sub, note in FILING_PATTERNS_COMPILED:
        if pat.search(haystack):
            return tier, sub, note
    return None


def normalize_hit(row: dict, tier: str, sub: str, note: str,
                  fetched_at: str) -> dict:
    name = (row.get("Nome_Companhia") or "").strip()
    cvm_code = (row.get("Codigo_CVM") or "").strip()
    cnpj = (row.get("CNPJ_Companhia") or "").strip()
    proto = (row.get("Protocolo_Entrega") or "").strip()
    delivered = (row.get("Data_Entrega") or "").strip()[:10]
    ref = (row.get("Data_Referencia") or "").strip()[:10]
    link = (row.get("Link_Download") or "").strip()
    categoria = (row.get("Categoria") or "").strip()
    tipo = (row.get("Tipo") or "").strip()
    assunto = (row.get("Assunto") or "").strip()
    headline = " · ".join(x for x in (categoria, tipo, assunto) if x)
    return {
        "tier":        tier,
        "query_label": f"{tier}.{sub}",
        "query_note":  note,
        "cik":         "",
        "ticker":      None,             # CVM doesn't expose B3 ticker
        "isin":        None,
        "cvm_code":    cvm_code,
        "cnpj":        cnpj,
        "name":        name,
        "form":        headline[:160],
        "form_code":   tipo,
        "accession":   proto or f"cvm-{cvm_code}-{delivered}",
        "filed":       delivered or ref or date.today().isoformat(),
        "jurisdiction": "BR",
        "url":         link,
        "source":      "CVM-IPE",
        "fetched_at":  fetched_at,
    }


def write_inbox(records: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in records:
        filed = r.get("filed") or date.today().isoformat()
        tier_dir = INBOX / filed[:10] / r["tier"]
        tier_dir.mkdir(parents=True, exist_ok=True)
        slug = (r["accession"] or "no-id").replace("/", "_")
        sub = r["query_label"].split(".")[-1]
        path = tier_dir / f"cvm_{slug}_{sub}.json"
        path.write_text(json.dumps(r, indent=2, sort_keys=True, default=str,
                                   ensure_ascii=False))
        key = f"{filed[:10]}/{r['tier']}"
        counts[key] = counts.get(key, 0) + 1
    return counts


def poll(year: int, cutoff: date) -> int:
    fetched_at = datetime.utcnow().isoformat() + "Z"
    print(f"Fetching CVM IPE {year} archive...")
    zip_bytes = download_archive(year)
    if not zip_bytes:
        return 0
    print(f"  {len(zip_bytes):,} bytes — parsing CSV")
    rows = parse_archive(zip_bytes)
    print(f"  {len(rows):,} IPE rows in archive")

    # Filter by date window
    in_window: list[dict] = []
    for r in rows:
        d_str = (r.get("Data_Entrega") or "")[:10]
        try:
            d = date.fromisoformat(d_str) if d_str else None
        except ValueError:
            d = None
        if d and d >= cutoff:
            in_window.append(r)
    print(f"  {len(in_window):,} rows in date window "
          f">= {cutoff.isoformat()}")

    # Classify
    hits: list[dict] = []
    from collections import Counter
    classified: Counter[str] = Counter()
    for r in in_window:
        cls = classify(r)
        if cls is None:
            continue
        tier, sub, note = cls
        classified[sub] += 1
        hits.append(normalize_hit(r, tier, sub, note, fetched_at))

    print(f"\n  {len(hits)} matched a special-situation pattern:")
    for sub, n in classified.most_common():
        print(f"    {sub:30s} {n}")

    if hits:
        counts = write_inbox(hits)
        for k, v in sorted(counts.items()):
            print(f"  {k}: {v}")
    return len(hits)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    today = date.today()
    ap.add_argument("--year", type=int, default=today.year,
                    help="Archive year (default: current year)")
    ap.add_argument("--days-back", type=int, default=1,
                    help="Date window — keep filings filed within last N "
                         "days (default 1)")
    args = ap.parse_args()
    cutoff = today - timedelta(days=args.days_back)
    total = poll(args.year, cutoff)
    print(f"\nDone. {total} records written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
