"""Scrape birthdates of people associated with listed equities from Wikidata.

For each stock exchange we query every listing (P414) and pull any linked
person who has a date of birth (P569) via one of these roles:
    P169  chief executive officer
    P112  founder
    P488  chairperson
    P3320 board member
    P1037 director / manager
    P127  owned by (for major individual owners)

The Wikidata public SPARQL endpoint times out after 60s, so we split the
work per-exchange and per-role. Results are streamed to a single CSV so the
job can be interrupted and resumed without losing progress.

Run:
    pip install requests
    python3 scrape_wikidata_birthdays.py

Output: listed_equity_birthdays.csv  (one row per person/role/company).
"""

from __future__ import annotations

import csv
import sys
import time
from pathlib import Path

import requests

ENDPOINT = "https://query.wikidata.org/sparql"
USER_AGENT = (
    "cyclepapa-birthday-scraper/0.1 "
    "(https://github.com/jupitersstring/cyclepapa; research) "
    "python-requests"
)

OUT_PATH = Path(__file__).parent / "listed_equity_birthdays.csv"

ROLES = [
    ("P169", "CEO"),
    ("P112", "founder"),
    ("P488", "chairperson"),
    ("P3320", "board_member"),
    ("P1037", "director"),
    ("P127", "owner"),
]

# Major stock exchanges (Wikidata QIDs). Covering these captures the bulk of
# globally-listed equities.
EXCHANGES = [
    ("Q13677", "NYSE"),
    ("Q82059", "NASDAQ"),
    ("Q171240", "LSE"),
    ("Q217475", "TSE_Tokyo"),
    ("Q496772", "HKEX"),
    ("Q633842", "SIX_Swiss"),
    ("Q99479", "Deutsche_Borse"),
    ("Q1026145", "Frankfurt"),
    ("Q739514", "Shanghai_SSE"),
    ("Q517750", "Shenzhen_SZSE"),
    ("Q482920", "TSX_Toronto"),
    ("Q807565", "BSE_Bombay"),
    ("Q1894265", "NSE_India"),
    ("Q484573", "ASX_Australia"),
    ("Q496775", "KRX_Korea"),
    ("Q27916241", "B3_Brazil"),
    ("Q689925", "JSE_Johannesburg"),
    ("Q1371123", "Euronext"),
    ("Q1799674", "Euronext_Paris"),
    ("Q1485531", "Euronext_Amsterdam"),
    ("Q746118", "Borsa_Italiana"),
    ("Q806636", "BME_Madrid"),
    ("Q380947", "OMX_Nordic"),
    ("Q1399969", "OMX_Stockholm"),
    ("Q1569738", "OMX_Helsinki"),
    ("Q1392919", "OMX_Copenhagen"),
    ("Q1799794", "Oslo_Bors"),
    ("Q1805776", "Moscow_MOEX"),
    ("Q516419", "Warsaw_GPW"),
    ("Q1371044", "Istanbul_BIST"),
    ("Q743925", "TASE_Tel_Aviv"),
    ("Q1616218", "Taiwan_TWSE"),
    ("Q623137", "SGX_Singapore"),
    ("Q1889124", "Bursa_Malaysia"),
    ("Q1663776", "SET_Thailand"),
    ("Q688089", "IDX_Indonesia"),
    ("Q1526381", "PSE_Philippines"),
    ("Q1892454", "Mexican_BMV"),
    ("Q1057990", "Santiago_SSE_Chile"),
    ("Q2720844", "Tadawul_Saudi"),
    ("Q3578649", "ADX_Abu_Dhabi"),
    ("Q1196338", "DFM_Dubai"),
    ("Q1145812", "EGX_Egypt"),
    ("Q1568804", "NGX_Nigeria"),
    ("Q1321140", "Vienna_WBAG"),
    ("Q1145898", "Athens_ASE"),
    ("Q1797014", "Prague_PSE"),
    ("Q1140488", "Budapest_BSE"),
    ("Q502974", "Bucharest_BVB"),
    ("Q1145806", "Ireland_ISE"),
    ("Q686822", "NZX_New_Zealand"),
    ("Q2632892", "Qatar_QE"),
    ("Q4354970", "Kuwait_KSE"),
]


QUERY_TEMPLATE = """
SELECT DISTINCT ?company ?companyLabel ?ticker ?exchange ?exchangeLabel
       ?person ?personLabel ?dob ?pob ?pobLabel ?gender ?genderLabel
       ?citizenshipLabel ?occupationLabel
WHERE {{
  ?company p:P414 ?listingStmt .
  ?listingStmt ps:P414 wd:{exchange_qid} .
  OPTIONAL {{ ?listingStmt pq:P249 ?ticker . }}
  BIND(wd:{exchange_qid} AS ?exchange)

  ?company wdt:{role_pid} ?person .
  ?person wdt:P569 ?dob .
  OPTIONAL {{ ?person wdt:P19 ?pob . }}
  OPTIONAL {{ ?person wdt:P21 ?gender . }}
  OPTIONAL {{ ?person wdt:P27 ?citizenship . }}
  OPTIONAL {{ ?person wdt:P106 ?occupation . }}

  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en" . }}
}}
"""


def run_query(sparql: str, retries: int = 4) -> list[dict]:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/sparql-results+json",
    }
    delay = 2.0
    for attempt in range(retries):
        try:
            resp = requests.get(
                ENDPOINT,
                params={"query": sparql, "format": "json"},
                headers=headers,
                timeout=90,
            )
        except requests.RequestException as e:
            print(f"    request error: {e}; retrying in {delay}s", file=sys.stderr)
            time.sleep(delay)
            delay *= 2
            continue

        if resp.status_code == 200:
            return resp.json()["results"]["bindings"]
        if resp.status_code in (429, 500, 502, 503, 504):
            print(
                f"    http {resp.status_code}; retrying in {delay}s",
                file=sys.stderr,
            )
            time.sleep(delay)
            delay *= 2
            continue
        print(
            f"    http {resp.status_code}: {resp.text[:200]}",
            file=sys.stderr,
        )
        return []
    print("    giving up after retries", file=sys.stderr)
    return []


def extract(binding: dict, key: str) -> str:
    node = binding.get(key)
    if not node:
        return ""
    value = node.get("value", "")
    if node.get("type") == "uri" and "/entity/" in value:
        return value.rsplit("/", 1)[-1]
    return value


FIELDNAMES = [
    "person_qid",
    "person_name",
    "dob",
    "role",
    "company_qid",
    "company_name",
    "ticker",
    "exchange_qid",
    "exchange_name",
    "gender",
    "citizenship",
    "occupation",
    "place_of_birth",
]


def main() -> None:
    seen: set[tuple[str, str, str]] = set()  # (person, role, company)
    total_rows = 0

    with OUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()

        for ex_qid, ex_name in EXCHANGES:
            for role_pid, role_name in ROLES:
                print(f"[{ex_name}] {role_name} (wdt:{role_pid})", flush=True)
                sparql = QUERY_TEMPLATE.format(
                    exchange_qid=ex_qid, role_pid=role_pid
                )
                rows = run_query(sparql)
                added = 0
                for b in rows:
                    person_qid = extract(b, "person")
                    company_qid = extract(b, "company")
                    key = (person_qid, role_name, company_qid)
                    if key in seen:
                        continue
                    seen.add(key)
                    writer.writerow(
                        {
                            "person_qid": person_qid,
                            "person_name": extract(b, "personLabel"),
                            "dob": extract(b, "dob"),
                            "role": role_name,
                            "company_qid": company_qid,
                            "company_name": extract(b, "companyLabel"),
                            "ticker": extract(b, "ticker"),
                            "exchange_qid": extract(b, "exchange"),
                            "exchange_name": ex_name,
                            "gender": extract(b, "genderLabel"),
                            "citizenship": extract(b, "citizenshipLabel"),
                            "occupation": extract(b, "occupationLabel"),
                            "place_of_birth": extract(b, "pobLabel"),
                        }
                    )
                    added += 1
                total_rows += added
                print(
                    f"    -> {added} new rows (cumulative {total_rows})",
                    flush=True,
                )
                f.flush()
                time.sleep(1.0)  # polite pacing

    print(f"\nDone. Wrote {total_rows} rows to {OUT_PATH}")


if __name__ == "__main__":
    main()
