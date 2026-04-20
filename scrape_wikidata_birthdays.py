"""Scrape Wikidata for people linked to listed equities and their birthdays.

Output: one CSV per exchange under data/, e.g.
    data/NYSE.csv
    data/NASDAQ.csv
    data/SP500.csv      (S&P 500 index members, across exchanges)

Each row: one (person, role, company) combination with date of birth (P569),
plus IPO date (qualifier P580 on the company's P414 listing statement) and
the company's inception date (P571).

Roles queried: CEO (P169), founder (P112), chairperson (P488),
board member (P3320), director (P1037), owner (P127).

The Wikidata public SPARQL endpoint times out at 60s, so we split work
per (scope, role). State is tracked in data/.state.json so reruns resume
instead of redoing completed pairs.

Run:
    pip install requests
    python3 scrape_wikidata_birthdays.py
"""

from __future__ import annotations

import csv
import json
import sys
import time
from pathlib import Path

import requests

ENDPOINT = "https://query.wikidata.org/sparql"
USER_AGENT = (
    "cyclepapa-birthday-scraper/0.2 "
    "(https://github.com/jupitersstring/cyclepapa; research) "
    "python-requests"
)

DATA_DIR = Path(__file__).parent / "data"
STATE_PATH = DATA_DIR / ".state.json"

ROLES = [
    ("P169", "CEO"),
    ("P112", "founder"),
    ("P488", "chairperson"),
    ("P3320", "board_member"),
    ("P1037", "director"),
    ("P127", "owner"),
]

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

# S&P 500 index (Wikidata QID).
SP500_QID = "Q242345"


EXCHANGE_QUERY = """
SELECT DISTINCT ?company ?companyLabel ?ticker ?listingStart ?inception
       ?exchange ?exchangeLabel
       ?person ?personLabel ?dob ?pob ?pobLabel ?gender ?genderLabel
       ?citizenshipLabel ?occupationLabel
WHERE {{
  ?company p:P414 ?listingStmt .
  ?listingStmt ps:P414 wd:{scope_qid} .
  OPTIONAL {{ ?listingStmt pq:P249 ?ticker . }}
  OPTIONAL {{ ?listingStmt pq:P580 ?listingStart . }}
  OPTIONAL {{ ?company wdt:P571 ?inception . }}
  BIND(wd:{scope_qid} AS ?exchange)

  ?company wdt:{role_pid} ?person .
  ?person wdt:P569 ?dob .
  OPTIONAL {{ ?person wdt:P19 ?pob . }}
  OPTIONAL {{ ?person wdt:P21 ?gender . }}
  OPTIONAL {{ ?person wdt:P27 ?citizenship . }}
  OPTIONAL {{ ?person wdt:P106 ?occupation . }}

  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en" . }}
}}
"""

# Members of an index (S&P 500 etc.) via part-of (P361) or member-of (P463).
INDEX_QUERY = """
SELECT DISTINCT ?company ?companyLabel ?ticker ?listingStart ?inception
       ?exchange ?exchangeLabel
       ?person ?personLabel ?dob ?pob ?pobLabel ?gender ?genderLabel
       ?citizenshipLabel ?occupationLabel
WHERE {{
  {{ ?company wdt:P361 wd:{scope_qid} }}
  UNION
  {{ ?company wdt:P463 wd:{scope_qid} }}

  OPTIONAL {{
    ?company p:P414 ?listingStmt .
    ?listingStmt ps:P414 ?exchange .
    OPTIONAL {{ ?listingStmt pq:P249 ?ticker . }}
    OPTIONAL {{ ?listingStmt pq:P580 ?listingStart . }}
  }}
  OPTIONAL {{ ?company wdt:P571 ?inception . }}

  ?company wdt:{role_pid} ?person .
  ?person wdt:P569 ?dob .
  OPTIONAL {{ ?person wdt:P19 ?pob . }}
  OPTIONAL {{ ?person wdt:P21 ?gender . }}
  OPTIONAL {{ ?person wdt:P27 ?citizenship . }}
  OPTIONAL {{ ?person wdt:P106 ?occupation . }}

  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en" . }}
}}
"""


FIELDNAMES = [
    "person_qid",
    "person_name",
    "dob",
    "role",
    "company_qid",
    "company_name",
    "ticker",
    "ipo_date",
    "company_inception",
    "exchange_qid",
    "exchange_name",
    "gender",
    "citizenship",
    "occupation",
    "place_of_birth",
]


def run_query(sparql: str, retries: int = 4) -> list[dict]:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/sparql-results+json",
    }
    delay = 2.0
    for _ in range(retries):
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


def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text())
        except Exception:
            pass
    return {"completed": []}


def save_state(state: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True))


def load_existing_keys(path: Path) -> set[tuple[str, str, str]]:
    """Return already-written (person, role, company) keys so we can dedupe
    across runs. If the file's schema is outdated, wipe it."""
    if not path.exists():
        return set()
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != FIELDNAMES:
            print(f"  {path.name}: schema mismatch, removing", flush=True)
            path.unlink()
            return set()
        return {
            (row["person_qid"], row["role"], row["company_qid"])
            for row in reader
        }


def process_scope(
    scope_qid: str,
    scope_name: str,
    query_template: str,
    state: dict,
) -> None:
    out_path = DATA_DIR / f"{scope_name}.csv"
    seen = load_existing_keys(out_path)
    fresh = not out_path.exists()
    total = len(seen)

    mode = "w" if fresh else "a"
    with out_path.open(mode, newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if fresh:
            writer.writeheader()

        for role_pid, role_name in ROLES:
            key = f"{scope_name}:{role_pid}"
            if key in state["completed"]:
                continue
            print(f"[{scope_name}] {role_name}", flush=True)
            sparql = query_template.format(
                scope_qid=scope_qid, role_pid=role_pid
            )
            rows = run_query(sparql)
            added = 0
            for b in rows:
                person_qid = extract(b, "person")
                company_qid = extract(b, "company")
                dedup = (person_qid, role_name, company_qid)
                if dedup in seen:
                    continue
                seen.add(dedup)
                writer.writerow(
                    {
                        "person_qid": person_qid,
                        "person_name": extract(b, "personLabel"),
                        "dob": extract(b, "dob"),
                        "role": role_name,
                        "company_qid": company_qid,
                        "company_name": extract(b, "companyLabel"),
                        "ticker": extract(b, "ticker"),
                        "ipo_date": extract(b, "listingStart"),
                        "company_inception": extract(b, "inception"),
                        "exchange_qid": extract(b, "exchange"),
                        "exchange_name": extract(b, "exchangeLabel") or scope_name,
                        "gender": extract(b, "genderLabel"),
                        "citizenship": extract(b, "citizenshipLabel"),
                        "occupation": extract(b, "occupationLabel"),
                        "place_of_birth": extract(b, "pobLabel"),
                    }
                )
                added += 1
            total += added
            f.flush()
            state["completed"].append(key)
            save_state(state)
            print(f"    -> {added} new rows ({out_path.name} total {total})", flush=True)
            time.sleep(0.3)


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    state = load_state()

    # S&P 500 index first so it's available even if we get timed out later.
    process_scope("Q242345", "SP500", INDEX_QUERY, state)

    for ex_qid, ex_name in EXCHANGES:
        process_scope(ex_qid, ex_name, EXCHANGE_QUERY, state)

    print("\nDone.")


if __name__ == "__main__":
    main()
