"""Backfill blank company names/sectors from financedatabase (offline).

The Wikipedia-index universes (wiki-union / wiki-r1k / wiki-aim100) carry only
tickers, no company names, so ~12% of the consolidated common-equity rows show
up nameless in the workbooks. financedatabase ships a bundled 151k-equity table
(name/sector/industry) that resolves offline, so we use it to fill the gaps.

Idempotent. Usage: python3 backfill_names.py [csv_path]
"""

import sys
import warnings
warnings.filterwarnings("ignore")
import pandas as pd
import financedatabase as fd


def _blank(s):
    return s.isna() | (s.astype(str).str.strip().isin(["", "nan", "None"]))


def main():
    csv_path = sys.argv[1] if len(sys.argv) > 1 else "global_equities_consolidated.csv"
    df = pd.read_csv(csv_path, index_col=0, low_memory=False)
    n = len(df)

    eq = fd.Equities().select()
    fd_name = eq["name"].to_dict()
    fd_sector = eq["sector"].to_dict() if "sector" in eq.columns else {}

    def lookup(tkr, table):
        s = str(tkr)
        if s in table and pd.notna(table[s]):
            return table[s]
        # try without exchange suffix (e.g. RIO.L -> RIO) and vice-versa
        if "." in s:
            base = s.rsplit(".", 1)[0]
            if base in table and pd.notna(table[base]):
                return table[base]
        return None

    if "name" not in df.columns:
        df["name"] = pd.NA
    name_blank = _blank(df["name"])
    before = int(name_blank.sum())
    filled_name = 0
    for t in df.index[name_blank]:
        v = lookup(t, fd_name)
        if v is not None:
            df.at[t, "name"] = v
            filled_name += 1

    filled_sector = 0
    if "sector" in df.columns and fd_sector:
        sec_blank = _blank(df["sector"])
        for t in df.index[sec_blank]:
            v = lookup(t, fd_sector)
            if v is not None:
                df.at[t, "sector"] = v
                filled_sector += 1

    still_blank = int(_blank(df["name"]).sum())
    df.to_csv(csv_path)
    print(f"Loaded {n} rows from {csv_path}")
    print(f"Blank names before: {before}  ->  filled {filled_name}  ->  still blank {still_blank}")
    print(f"Sectors backfilled: {filled_sector}")
    print(f"Wrote {csv_path}")


if __name__ == "__main__":
    main()
