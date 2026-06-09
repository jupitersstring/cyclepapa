"""Durable snapshot of the assembled analysis so a container rollback can't wipe it.

The expensive artifacts (the universe, the assembled fundamentals table and the
scored table) normally live only in ``cache/`` which is gitignored and ephemeral:
when the remote container is rolled back, that data is lost (or reverted to a
stale state) even though the *code* is safe in git. This tool keeps compact
copies under ``data/`` (tracked in git) and can rehydrate the cache from them.

    python scripts/snapshot.py rebuild   # cache/raw -> cache/fundamentals + scored (NO network)
    python scripts/snapshot.py save      # cache/*.parquet -> data/   (then: git add data && commit)
    python scripts/snapshot.py restore   # data/*.parquet -> cache/   (after a rollback)
    python scripts/snapshot.py status    # report row/coverage counts on both sides

``rebuild`` is pure-local: it re-derives the fundamentals straight from the
already-fetched ``cache/raw/*.json`` (so it restores every metric column without
touching Yahoo), then runs the standard analyze step to regenerate scored.parquet
and all the screen CSVs. The only thing it cannot recover offline is brand-new
surprise coverage — back-fill that separately with ``refresh_surprises``.
"""
from __future__ import annotations

import argparse
import glob
import json
import shutil
import subprocess
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from earnings_model import config, fundamentals as F, pipeline, surprise_store as S

DATA_DIR = config.DATA_DIR          # repo-anchored; independent of CWD
RAWS_ARCHIVE = DATA_DIR / "raws.tar.gz"
MANIFEST = DATA_DIR / "manifest.json"
# Files that make up a snapshot. universe + fundamentals are the inputs; scored is
# derived but kept so the workbook/screens can be regenerated without re-analyzing.
SNAPSHOT_FILES = ["universe.parquet", "fundamentals.parquet", "scored.parquet"]


def _git_sha() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, cwd=config.REPO_ROOT).stdout.strip()
    except Exception:
        return "unknown"


def _max_asof() -> str | None:
    """Most-recent price/data fetch date across the cached raws (freshness)."""
    best = None
    for p in glob.glob(str(config.RAW_CACHE_DIR / "*.json")):
        try:
            a = json.loads(Path(p).read_text()).get("asof")
        except (json.JSONDecodeError, OSError):
            continue
        if a and (best is None or a > best):
            best = a
    return best


def _write_manifest() -> None:
    scored = config.CACHE_DIR / "scored.parquet"
    rows = surp = 0
    if scored.exists():
        df = pd.read_parquet(scored, columns=[c for c in ["surprise_n"] if True] or None)
        rows = len(df)
        if "surprise_n" in df.columns:
            surp = int((df["surprise_n"].fillna(0) > 0).sum())
    MANIFEST.write_text(json.dumps({
        "schema_version": config.SCHEMA_VERSION,
        "git_sha": _git_sha(),
        "saved_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "data_asof": _max_asof(),
        "scored_rows": rows,
        "names_with_surprises": surp,
    }, indent=2))


def _cached_ok_symbols() -> list[str]:
    """Symbols whose cached raw has data (fetch_ok)."""
    syms = []
    for p in glob.glob(str(config.RAW_CACHE_DIR / "*.json")):
        try:
            r = json.loads(Path(p).read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if r.get("fetch_ok") and r.get("symbol"):
            syms.append(r["symbol"])
    return syms


def rebuild() -> None:
    """Re-derive fundamentals + scored straight from cache/raw (no network)."""
    # The durable surprise store (data/surprises.json) is git-tracked and survives
    # rollbacks; fold it back into cache/raw so the rebuilt parquet has full surprise
    # coverage even when the cache itself was just reverted.
    reinj = S.reinject_into_cache()
    print(f"reinjected {reinj} durable surprises into cache/raw")
    syms = _cached_ok_symbols()
    print(f"rebuilding from {len(syms)} cached names with data (no network)...")
    uni = pd.read_parquet(config.UNIVERSE_PATH)
    # refresh=False + no surprise_regions => pure cache read for every symbol.
    funda = F.build_fundamentals(uni, symbols=syms, refresh=False, surprise_regions=None)
    F.save_fundamentals(funda)
    ok = int(funda["fetch_ok"].sum()) if "fetch_ok" in funda.columns else len(funda)
    print(f"fundamentals: {len(funda)} rows ({ok} with data) -> {config.FUNDAMENTALS_PATH}")
    # Standard analyze: region-aware scoring + every screen CSV.
    pipeline.step_analyze()


def save(with_raws: bool = False) -> None:
    """Copy the cache artifacts into the tracked data/ directory + write manifest.

    ``with_raws`` also archives every cache/raw/*.json into data/raws.tar.gz —
    the irreplaceable, network-fetched statements/prices — so a rollback that
    *destroys* (not just reverts) the cache can't force a multi-day refetch.
    It's ~16 MB, so refresh it at milestones rather than on every save.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for name in SNAPSHOT_FILES:
        src = config.CACHE_DIR / name
        if src.exists():
            shutil.copy2(src, DATA_DIR / name)
            print(f"saved {src} -> {DATA_DIR / name} ({src.stat().st_size // 1024} KiB)")
        else:
            print(f"  (skip {name}: not in cache)")
    if with_raws:
        n = 0
        with tarfile.open(RAWS_ARCHIVE, "w:gz") as tar:
            for p in glob.glob(str(config.RAW_CACHE_DIR / "*.json")):
                tar.add(p, arcname=Path(p).name); n += 1
        print(f"archived {n} raws -> {RAWS_ARCHIVE} ({RAWS_ARCHIVE.stat().st_size // 1024} KiB)")
    _write_manifest()
    print(f"manifest written (schema v{config.SCHEMA_VERSION}, sha {_git_sha()}). "
          f"commit it:  git add data && git commit -m 'Refresh data snapshot'")


def restore() -> None:
    """Rehydrate the cache parquets from the tracked snapshot (post-rollback)."""
    config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    restored = 0
    for name in SNAPSHOT_FILES:
        src = DATA_DIR / name
        if src.exists():
            shutil.copy2(src, config.CACHE_DIR / name)
            print(f"restored {src} -> {config.CACHE_DIR / name}")
            restored += 1
        else:
            print(f"  (skip {name}: not in snapshot)")
    if not restored:
        print("nothing to restore — data/ is empty. Run a fetch + rebuild + save first.")
        sys.exit(1)
    # If cache/raw was *destroyed* (not just reverted), rehydrate it from the
    # committed archive so we don't have to refetch from Yahoo.
    n_raw = len(glob.glob(str(config.RAW_CACHE_DIR / "*.json")))
    if n_raw < 1000 and RAWS_ARCHIVE.exists():
        config.RAW_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with tarfile.open(RAWS_ARCHIVE, "r:gz") as tar:
            tar.extractall(config.RAW_CACHE_DIR)
        print(f"extracted raws archive -> {config.RAW_CACHE_DIR} "
              f"(cache had only {n_raw})")
    # Make cache/raw consistent with the durable surprise store too, so a later
    # rebuild keeps full surprise coverage rather than the rolled-back cache state.
    reinj = S.reinject_into_cache()
    print(f"reinjected {reinj} durable surprises into cache/raw")
    if MANIFEST.exists():
        man = json.loads(MANIFEST.read_text())
        if man.get("schema_version") != config.SCHEMA_VERSION:
            print(f"  ⚠ snapshot schema v{man.get('schema_version')} != code "
                  f"v{config.SCHEMA_VERSION} — rebuild recommended")
        print(f"  snapshot: {man.get('scored_rows')} rows, asof {man.get('data_asof','?')[:10]}, "
              f"sha {man.get('git_sha')}")


def _coverage(path: Path) -> str:
    if not path.exists():
        return "missing"
    try:
        df = pd.read_parquet(path, columns=None)
    except Exception as e:  # noqa: BLE001
        return f"unreadable ({e})"
    bits = [f"{len(df)} rows"]
    if "fetch_ok" in df.columns:
        bits.append(f"{int(df['fetch_ok'].sum())} with data")
    if "surprise_n" in df.columns:
        bits.append(f"{int((df['surprise_n'].fillna(0) > 0).sum())} with surprises")
    if "gross_margin_delta" in df.columns:
        bits.append("gross-margin col ✓")
    return ", ".join(bits)


def status() -> None:
    raws = len(glob.glob(str(config.RAW_CACHE_DIR / "*.json")))
    print(f"cache/raw: {raws} json files | code schema v{config.SCHEMA_VERSION} | HEAD {_git_sha()}")
    if MANIFEST.exists():
        print(f"manifest: {json.loads(MANIFEST.read_text())}")
    print(f"raws archive: {'present' if RAWS_ARCHIVE.exists() else 'MISSING (run save --with-raws)'}")
    print(f"data/surprises.json (durable): {len(S.load())} names with surprises")
    for name in SNAPSHOT_FILES:
        print(f"  cache/{name:22s} {_coverage(config.CACHE_DIR / name)}")
        print(f"  data/ {name:22s} {_coverage(DATA_DIR / name)}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("cmd", choices=["rebuild", "save", "restore", "status"])
    ap.add_argument("--with-raws", action="store_true",
                    help="(save) also archive cache/raw into data/raws.tar.gz")
    args = ap.parse_args()
    if args.cmd == "save":
        save(with_raws=args.with_raws)
    else:
        {"rebuild": rebuild, "restore": restore, "status": status}[args.cmd]()


if __name__ == "__main__":
    main()
