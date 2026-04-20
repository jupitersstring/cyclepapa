"""Scrape birthdays for companies listed in vendor-provided constituent files.

Stage 2 of the index pipeline: reads data/constituents/<INDEX>.csv produced
by fetch_index_constituents.py, resolves each ticker to a Wikidata QID
(via P249 "ticker symbol"), then runs the same execs/founders/birthdays
query we use in the main scraper — but scoped to the set of resolved
company QIDs instead of by exchange.

Output is appended to data/<INDEX>.csv using the 20-column schema, so
rows overlapping the main Wikidata-by-exchange scrape deduplicate cleanly.
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
    "cyclepapa-constituents-scraper/0.1 "
    "(https://github.com/jupitersstring/cyclepapa; research) "
    "python-requests"
)

DATA_DIR = Path(__file__).parent / "data"
CONSTITUENTS_DIR = DATA_DIR / "constituents"
STATE_PATH = DATA_DIR / ".constituents_state.json"

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

# Small batch to stay well under the 60s SPARQL timeout.
BATCH = 40


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
            print(f"    http {resp.status_code}; retrying in {delay}s", file=sys.stderr)
            time.sleep(delay)
            delay *= 2
            continue
        print(f"    http {resp.status_code}: {resp.text[:200]}", file=sys.stderr)
        return []
    return []


def extract(b: dict, key: str) -> str:
    node = b.get(key)
    if not node:
        return ""
    v = node.get("value", "")
    if node.get("type") == "uri" and "/entity/" in v:
        return v.rsplit("/", 1)[-1]
    return v


def chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def sparql_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


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


def checkpoint_commit(name: str, rows: int) -> None:
    if not CHECKPOINT_PUSH or not GIT_REF:
        return
    try:
        subprocess.run(["git", "add", "data/"], check=False)
        diff = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if diff.returncode == 0:
            return
        subprocess.run(
            ["git", "commit", "-m", f"Checkpoint (constituents): {name} ({rows} rows)"],
            check=False,
        )
        pull = subprocess.run(
            ["git", "pull", "--rebase", "--autostash", "origin", GIT_REF],
            capture_output=True,
            text=True,
        )
        if pull.returncode != 0:
            subprocess.run(
                ["git", "rebase", "--abort"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        subprocess.run(
            ["git", "push", "origin", f"HEAD:{GIT_REF}"],
            check=False,
            capture_output=True,
        )
    except Exception as e:
        print(f"    checkpoint push failed: {e}", file=sys.stderr)


def load_existing_keys(path: Path) -> set[tuple[str, str, str]]:
    if not path.exists():
        return set()
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != FIELDNAMES:
            return set()
        return {
            (r["person_qid"], r["role"], r["company_qid"])
            for r in reader
        }


def resolve_tickers(tickers: list[str]) -> dict[str, str]:
    """Map ticker string -> Wikidata QID via the P249 property."""
    out: dict[str, str] = {}
    for batch in chunks(sorted(set(tickers)), 150):
        values = " ".join(f'"{sparql_escape(t)}"' for t in batch)
        q = f"""
        SELECT ?ticker ?company WHERE {{
          VALUES ?ticker {{ {values} }}
          ?company wdt:P249 ?ticker .
        }}
        """
        rows = run_query(q)
        for b in rows:
            t = extract(b, "ticker")
            c = extract(b, "company")
            if t and c and t not in out:
                out[t] = c
        time.sleep(0.3)
    return out


def query_birthdays(company_qids: list[str], role_pid: str, role_name: str) -> list[dict]:
    values = " ".join(f"wd:{q}" for q in company_qids)
    sparql = f"""
    SELECT DISTINCT ?company ?companyLabel ?ticker ?listingStart ?inception
           ?hq ?hqLabel ?hqCountryLabel ?companyCountryLabel
           ?exchange ?exchangeLabel ?exchangeCityLabel ?exchangeCountryLabel
           ?person ?personLabel ?dob ?pob ?pobLabel ?gender ?genderLabel
           ?citizenshipLabel ?occupationLabel
    WHERE {{
      VALUES ?company {{ {values} }}
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
    bindings = run_query(sparql)
    rows = []
    for b in bindings:
        rows.append(
            {
                "person_qid": extract(b, "person"),
                "person_name": extract(b, "personLabel"),
                "dob": extract(b, "dob"),
                "role": role_name,
                "company_qid": extract(b, "company"),
                "company_name": extract(b, "companyLabel"),
                "ticker": extract(b, "ticker"),
                "ipo_date": extract(b, "listingStart"),
                "company_inception": extract(b, "inception"),
                "hq_city": extract(b, "hqLabel"),
                "hq_country": extract(b, "hqCountryLabel"),
                "company_country": extract(b, "companyCountryLabel"),
                "exchange_qid": extract(b, "exchange"),
                "exchange_name": extract(b, "exchangeLabel"),
                "exchange_city": extract(b, "exchangeCityLabel"),
                "exchange_country": extract(b, "exchangeCountryLabel"),
                "gender": extract(b, "genderLabel"),
                "citizenship": extract(b, "citizenshipLabel"),
                "occupation": extract(b, "occupationLabel"),
                "place_of_birth": extract(b, "pobLabel"),
            }
        )
    return rows


def process_constituent_file(cpath: Path, state: dict) -> None:
    name = cpath.stem
    key = f"constituents:{name}"
    if key in state["completed"]:
        return

    with cpath.open(newline="", encoding="utf-8") as f:
        tickers = [r["ticker"].strip() for r in csv.DictReader(f) if r.get("ticker")]
    if not tickers:
        print(f"[{name}] no tickers, skipping", flush=True)
        state["completed"].append(key)
        save_state(state)
        return

    print(f"[{name}] resolving {len(tickers)} tickers", flush=True)
    qids = resolve_tickers(tickers)
    print(f"    matched {len(qids)} / {len(tickers)} tickers to QIDs", flush=True)
    if not qids:
        state["completed"].append(key)
        save_state(state)
        return

    out_path = DATA_DIR / f"{name}.csv"
    seen = load_existing_keys(out_path)
    fresh = not out_path.exists()
    total = len(seen)
    mode = "w" if fresh else "a"

    all_qids = sorted(set(qids.values()))
    with out_path.open(mode, newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if fresh:
            writer.writeheader()

        for role_pid, role_name in ROLES:
            added = 0
            for batch in chunks(all_qids, BATCH):
                rows = query_birthdays(batch, role_pid, role_name)
                for row in rows:
                    dedup = (row["person_qid"], row["role"], row["company_qid"])
                    if dedup in seen:
                        continue
                    seen.add(dedup)
                    writer.writerow(row)
                    added += 1
                time.sleep(0.3)
            total += added
            f.flush()
            print(
                f"    {role_name}: +{added} rows (total {total})",
                flush=True,
            )

    state["completed"].append(key)
    save_state(state)
    checkpoint_commit(name, total)


def main() -> None:
    if not CONSTITUENTS_DIR.exists():
        print(
            f"missing {CONSTITUENTS_DIR}; run fetch_index_constituents.py first",
            file=sys.stderr,
        )
        return
    state = load_state()
    for cpath in sorted(CONSTITUENTS_DIR.glob("*.csv")):
        try:
            process_constituent_file(cpath, state)
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"[{cpath.stem}] failed: {e}", file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(0)
