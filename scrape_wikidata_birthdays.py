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
import os
import subprocess
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

# When CHECKPOINT_PUSH=1 the script commits + pushes data/ after each scope
# finishes so CI runs publish progress incrementally. Skip in local runs.
CHECKPOINT_PUSH = os.environ.get("CHECKPOINT_PUSH") == "1"
GIT_REF = os.environ.get("GITHUB_REF_NAME", "")

ROLES = [
    ("P169", "CEO"),
    ("P112", "founder"),
    ("P488", "chairperson"),
    ("P3320", "board_member"),
    ("P1037", "director"),
    ("P127", "owner"),
]

# Each scope is (name, [candidate Wikidata QIDs]).
# Some exchanges are tagged via different entities by different editors —
# e.g. companies on the Hong Kong floor may be linked to Q496772 (Stock
# Exchange of Hong Kong) or the parent Q1090009 (HKEX clearing). We try
# every candidate via SPARQL VALUES and union the results.
EXCHANGES = [
    ("NYSE",                ["Q13677"]),
    ("NASDAQ",              ["Q82059"]),
    ("LSE",                 ["Q171240"]),
    ("TSE_Tokyo",           ["Q217475"]),
    ("HKEX",                ["Q496772", "Q1090009", "Q1130758"]),
    ("SIX_Swiss",           ["Q633842", "Q1187137"]),
    ("Deutsche_Borse",      ["Q99479"]),
    ("Frankfurt",           ["Q1026145"]),
    ("Shanghai_SSE",        ["Q739514"]),
    ("Shenzhen_SZSE",       ["Q517750"]),
    ("TSX_Toronto",         ["Q482919", "Q482920", "Q1751381"]),
    ("BSE_Bombay",          ["Q1378029", "Q807565"]),
    ("NSE_India",           ["Q571393", "Q1894265"]),
    ("ASX_Australia",       ["Q484573", "Q1495972", "Q4805389"]),
    ("KRX_Korea",           ["Q489398", "Q496775"]),
    ("B3_Brazil",           ["Q27916241", "Q1273135"]),
    ("JSE_Johannesburg",    ["Q689925", "Q1681644"]),
    ("Euronext",            ["Q745519", "Q1371123"]),
    ("Euronext_Paris",      ["Q1799674", "Q637785"]),
    ("Euronext_Amsterdam",  ["Q1485531", "Q602907"]),
    ("Euronext_Brussels",   ["Q820644"]),
    ("Euronext_Lisbon",     ["Q599876"]),
    ("Borsa_Italiana",      ["Q746118", "Q3520038"]),
    ("BME_Madrid",          ["Q11679", "Q806636"]),
    ("OMX_Nordic",          ["Q380947"]),
    ("OMX_Stockholm",       ["Q1399969", "Q852157"]),
    ("OMX_Helsinki",        ["Q1569738"]),
    ("OMX_Copenhagen",      ["Q1392919"]),
    ("Oslo_Bors",           ["Q1799794", "Q668886"]),
    ("Moscow_MOEX",         ["Q1117036", "Q1805776"]),
    ("Warsaw_GPW",          ["Q516419", "Q156711"]),
    ("Istanbul_BIST",       ["Q1371044", "Q1131722"]),
    ("TASE_Tel_Aviv",       ["Q743925"]),
    ("Taiwan_TWSE",         ["Q752907", "Q1616218"]),
    ("SGX_Singapore",       ["Q1138199", "Q623137"]),
    ("Bursa_Malaysia",      ["Q1889124", "Q1015852"]),
    ("SET_Thailand",        ["Q1663776"]),
    ("IDX_Indonesia",       ["Q688089", "Q3505144"]),
    ("PSE_Philippines",     ["Q1526381"]),
    ("Mexican_BMV",         ["Q1892454", "Q1995504"]),
    ("Santiago_SSE_Chile",  ["Q1057990"]),
    ("Tadawul_Saudi",       ["Q2720844", "Q1066198"]),
    ("ADX_Abu_Dhabi",       ["Q3578649", "Q4671922"]),
    ("DFM_Dubai",           ["Q1196338"]),
    ("EGX_Egypt",           ["Q1145812"]),
    ("NGX_Nigeria",         ["Q1568804", "Q7039674"]),
    ("Vienna_WBAG",         ["Q1321140", "Q694446"]),
    ("Athens_ASE",          ["Q1145898", "Q1138196"]),
    ("Prague_PSE",          ["Q1797014"]),
    ("Budapest_BSE",        ["Q1140488"]),
    ("Bucharest_BVB",       ["Q502974", "Q806224"]),
    ("Ireland_ISE",         ["Q1145806", "Q1364884"]),
    ("NZX_New_Zealand",     ["Q686822"]),
    ("Qatar_QE",            ["Q2632892"]),
    ("Kuwait_KSE",          ["Q4354970", "Q1781415"]),
]

# Indices queried via P361 (part of) / P463 (member of) on each candidate QID.
INDICES = [
    ("SP500",               ["Q242345"]),
    ("Dow_Jones",           ["Q156014", "Q105774521"]),
    ("NASDAQ_100",          ["Q14773", "Q161054"]),
    ("Russell_1000",        ["Q1545953"]),
    ("Russell_2000",        ["Q1545960"]),
    ("FTSE_100",            ["Q133297", "Q15952612"]),
    ("FTSE_250",            ["Q924210"]),
    ("FTSE_All_Share",      ["Q5429618"]),
    ("CAC_40",              ["Q213629"]),
    ("CAC_Next_20",         ["Q1023824"]),
    ("SBF_120",             ["Q1145850"]),
    ("DAX",                 ["Q155646", "Q124171"]),
    ("MDAX",                ["Q156285"]),
    ("SDAX",                ["Q156289"]),
    ("TecDAX",              ["Q157242"]),
    ("Euro_Stoxx_50",       ["Q239064"]),
    ("STOXX_Europe_600",    ["Q1478818"]),
    ("IBEX_35",             ["Q195559"]),
    ("AEX",                 ["Q198925", "Q1145823"]),
    ("BEL_20",              ["Q180457"]),
    ("SMI",                 ["Q190090"]),
    ("FTSE_MIB",            ["Q198229", "Q4174776"]),
    ("PSI_20",              ["Q740754"]),
    ("OMX_Stockholm_30",    ["Q1768921"]),
    ("OMX_Helsinki_25",     ["Q1768918"]),
    ("OMX_Copenhagen_25",   ["Q1900463"]),
    ("OBX",                 ["Q1528531"]),
    ("ATX",                 ["Q200518"]),
    ("ISEQ_20",             ["Q2607891"]),
    ("WIG_20",              ["Q461724"]),
    ("BIST_30",             ["Q262284"]),
    ("BIST_100",            ["Q806262"]),
    ("MOEX_Russia",         ["Q1139792", "Q1928619"]),
    ("Nikkei_225",          ["Q672464"]),
    ("Hang_Seng",           ["Q691419"]),
    ("KOSPI",               ["Q485947"]),
    ("ASX_200",             ["Q4807306"]),
    ("Nifty_50",            ["Q1781125"]),
    ("Sensex",              ["Q201172"]),
    ("TSX_60",              ["Q1377025"]),
]


EXCHANGE_QUERY = """
SELECT DISTINCT ?company ?companyLabel ?ticker ?listingStart ?inception
       ?exchange ?exchangeLabel
       ?hq ?hqLabel ?hqCountryLabel ?companyCountryLabel
       ?exchangeCityLabel ?exchangeCountryLabel
       ?person ?personLabel ?dob ?pob ?pobLabel ?gender ?genderLabel
       ?citizenshipLabel ?occupationLabel
WHERE {{
  VALUES ?exchange {{ {scope_values} }}
  ?company p:P414 ?listingStmt .
  ?listingStmt ps:P414 ?exchange .
  OPTIONAL {{ ?listingStmt pq:P249 ?ticker . }}
  OPTIONAL {{ ?listingStmt pq:P580 ?listingStart . }}
  OPTIONAL {{ ?company wdt:P571 ?inception . }}
  OPTIONAL {{ ?company wdt:P159 ?hq . }}
  OPTIONAL {{ ?hq wdt:P17 ?hqCountry . }}
  OPTIONAL {{ ?company wdt:P17 ?companyCountry . }}
  OPTIONAL {{ ?exchange wdt:P159 ?exchangeCity . }}
  OPTIONAL {{ ?exchange wdt:P17 ?exchangeCountry . }}

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
       ?hq ?hqLabel ?hqCountryLabel ?companyCountryLabel
       ?exchangeCityLabel ?exchangeCountryLabel
       ?person ?personLabel ?dob ?pob ?pobLabel ?gender ?genderLabel
       ?citizenshipLabel ?occupationLabel
WHERE {{
  VALUES ?index {{ {scope_values} }}
  {{ ?company wdt:P361 ?index }}
  UNION
  {{ ?company wdt:P463 ?index }}

  OPTIONAL {{
    ?company p:P414 ?listingStmt .
    ?listingStmt ps:P414 ?exchange .
    OPTIONAL {{ ?listingStmt pq:P249 ?ticker . }}
    OPTIONAL {{ ?listingStmt pq:P580 ?listingStart . }}
    OPTIONAL {{ ?exchange wdt:P159 ?exchangeCity . }}
    OPTIONAL {{ ?exchange wdt:P17 ?exchangeCountry . }}
  }}
  OPTIONAL {{ ?company wdt:P571 ?inception . }}
  OPTIONAL {{ ?company wdt:P159 ?hq . }}
  OPTIONAL {{ ?hq wdt:P17 ?hqCountry . }}
  OPTIONAL {{ ?company wdt:P17 ?companyCountry . }}

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
    "hq_city",
    "hq_country",
    "company_country",
    "exchange_qid",
    "exchange_name",
    "exchange_city",
    "exchange_country",
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


def checkpoint_commit(scope_name: str, rows: int) -> None:
    """If running in CI with CHECKPOINT_PUSH=1, push the newly written CSV
    so partial progress is visible on the branch."""
    if not CHECKPOINT_PUSH or not GIT_REF:
        return
    try:
        subprocess.run(["git", "add", "data/"], check=False)
        diff = subprocess.run(
            ["git", "diff", "--cached", "--quiet"]
        )
        if diff.returncode == 0:
            return  # nothing to commit
        subprocess.run(
            [
                "git",
                "commit",
                "-m",
                f"Checkpoint: {scope_name} ({rows} rows)",
            ],
            check=False,
        )
        subprocess.run(
            ["git", "pull", "--rebase", "origin", GIT_REF], check=False
        )
        subprocess.run(
            ["git", "push", "origin", f"HEAD:{GIT_REF}"], check=False
        )
    except Exception as e:
        print(f"    checkpoint push failed: {e}", file=sys.stderr)


def load_existing_keys(
    path: Path, state: dict, scope_name: str
) -> set[tuple[str, str, str]]:
    """Return already-written (person, role, company) keys so we can dedupe
    across runs. If the file's schema is outdated, wipe it AND clear the
    scope's completion entries so it gets re-queried."""
    if not path.exists():
        return set()
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != FIELDNAMES:
            print(f"  {path.name}: schema mismatch, removing", flush=True)
            path.unlink()
            prefix = f"{scope_name}:"
            state["completed"] = [
                k for k in state["completed"] if not k.startswith(prefix)
            ]
            save_state(state)
            return set()
        return {
            (row["person_qid"], row["role"], row["company_qid"])
            for row in reader
        }


def process_scope(
    scope_qids: list[str],
    scope_name: str,
    query_template: str,
    state: dict,
) -> None:
    out_path = DATA_DIR / f"{scope_name}.csv"
    seen = load_existing_keys(out_path, state, scope_name)
    fresh = not out_path.exists()
    total = len(seen)
    scope_values = " ".join(f"wd:{q}" for q in scope_qids)

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
                scope_values=scope_values, role_pid=role_pid
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
                        "hq_city": extract(b, "hqLabel"),
                        "hq_country": extract(b, "hqCountryLabel"),
                        "company_country": extract(b, "companyCountryLabel"),
                        "exchange_qid": extract(b, "exchange"),
                        "exchange_name": extract(b, "exchangeLabel") or scope_name,
                        "exchange_city": extract(b, "exchangeCityLabel"),
                        "exchange_country": extract(b, "exchangeCountryLabel"),
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

    checkpoint_commit(scope_name, total)


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    state = load_state()

    # Indices first so the headline datasets (S&P 500, FTSE 100, DAX…)
    # are written even if exchange runs get timed out later.
    for name, qids in INDICES:
        process_scope(qids, name, INDEX_QUERY, state)

    for name, qids in EXCHANGES:
        process_scope(qids, name, EXCHANGE_QUERY, state)

    print("\nDone.")


if __name__ == "__main__":
    main()
