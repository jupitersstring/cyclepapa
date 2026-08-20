"""Robustness-audit regression tests: crash-safe I/O, the raws-archive shrink
guard, pathspec-scoped checkpoint commits, and the refresh valuation guard."""
import json
import math
import subprocess
import tarfile

import pandas as pd
import pytest

from earnings_model import config, fundamentals as F, util, yahoo


# --------------------------------------------------------------------------- #
# Atomic writes
# --------------------------------------------------------------------------- #
def test_atomic_write_text_roundtrip_no_tmp_left(tmp_path):
    p = tmp_path / "sub" / "x.json"
    util.atomic_write_text(p, '{"a": 1}')
    assert json.loads(p.read_text()) == {"a": 1}
    assert list(tmp_path.rglob("*.tmp")) == []


def test_atomic_write_failure_keeps_original(tmp_path, monkeypatch):
    p = tmp_path / "x.json"
    util.atomic_write_text(p, "good")

    def boom(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr("earnings_model.util.os.replace", boom)
    with pytest.raises(OSError):
        util.atomic_write_text(p, "half-written garbage")
    assert p.read_text() == "good"                  # original untouched
    assert list(tmp_path.glob("*.tmp")) == []       # tmp cleaned up


def test_atomic_parquet_roundtrip(tmp_path):
    df = pd.DataFrame({"symbol": ["A", "B"], "v": [1.0, 2.0]})
    p = tmp_path / "t.parquet"
    util.atomic_to_parquet(df, p)
    assert pd.read_parquet(p)["v"].sum() == 3.0
    assert list(tmp_path.glob("*.tmp")) == []


def test_save_raw_atomic_and_slash_mapping(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RAW_CACHE_DIR", tmp_path)
    F.save_raw("BRK/B", {"symbol": "BRK/B", "fetch_ok": True})
    assert (tmp_path / "BRK_B.json").exists()
    assert F.load_raw("BRK/B", ttl_days=None, fail_ttl_days=None)["symbol"] == "BRK/B"
    assert list(tmp_path.glob("*.tmp")) == []


# --------------------------------------------------------------------------- #
# Raws-archive shrink guard
# --------------------------------------------------------------------------- #
def _seed_raws(raw_dir, n):
    raw_dir.mkdir(parents=True, exist_ok=True)
    for f in raw_dir.glob("*.json"):
        f.unlink()
    for i in range(n):
        (raw_dir / f"S{i}.json").write_text('{"fetch_ok": true}')


def test_archive_raws_guard_blocks_half_wiped_cache(tmp_path, monkeypatch):
    raw_dir = tmp_path / "raw"
    dest = tmp_path / "raws.tar.gz"
    monkeypatch.setattr(config, "RAW_CACHE_DIR", raw_dir)

    _seed_raws(raw_dir, 10)
    assert util.archive_raws(dest) == 10

    _seed_raws(raw_dir, 2)                          # container-reset half-state
    with pytest.raises(RuntimeError, match="refusing to shrink"):
        util.archive_raws(dest)
    with tarfile.open(dest, "r:gz") as t:           # full archive survives intact
        assert sum(1 for _ in t) == 10

    assert util.archive_raws(dest, force=True) == 2  # explicit override works
    assert list(tmp_path.glob("*.tmp")) == []


def test_archive_raws_replaces_corrupt_archive(tmp_path, monkeypatch):
    raw_dir = tmp_path / "raw"
    dest = tmp_path / "raws.tar.gz"
    monkeypatch.setattr(config, "RAW_CACHE_DIR", raw_dir)
    dest.write_text("this is not a tar file")       # corrupt durable archive
    _seed_raws(raw_dir, 3)
    assert util.archive_raws(dest) == 3             # no guard false-positive
    with tarfile.open(dest, "r:gz") as t:
        assert sum(1 for _ in t) == 3


def test_archive_raws_small_shrink_allowed(tmp_path, monkeypatch):
    """Normal churn (a few delisted names dropped) must not trip the guard."""
    raw_dir = tmp_path / "raw"
    dest = tmp_path / "raws.tar.gz"
    monkeypatch.setattr(config, "RAW_CACHE_DIR", raw_dir)
    _seed_raws(raw_dir, 100)
    util.archive_raws(dest)
    _seed_raws(raw_dir, 95)                         # >90% of previous: fine
    assert util.archive_raws(dest) == 95


# --------------------------------------------------------------------------- #
# Pathspec-scoped checkpoint commits
# --------------------------------------------------------------------------- #
def test_commit_paths_scoped_and_sha_detected(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    bare = tmp_path / "origin.git"
    subprocess.run(["git", "-c", "init.defaultBranch=main", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)

    def g(*a):
        return subprocess.run(["git", *a], cwd=repo, capture_output=True, text=True)

    g("config", "user.email", "t@example.com")
    g("config", "user.name", "t")
    g("remote", "add", "origin", str(bare))
    (repo / "seed.txt").write_text("seed")
    g("add", "."), g("commit", "-q", "-m", "init")

    (repo / "target.txt").write_text("checkpoint payload")
    (repo / "unrelated.txt").write_text("someone else's staged work")
    g("add", "unrelated.txt")

    monkeypatch.setattr(config, "REPO_ROOT", repo)
    assert util.commit_paths_and_push("checkpoint", [repo / "target.txt"]) is True

    files = g("show", "--name-only", "--format=", "HEAD").stdout.split()
    assert files == ["target.txt"]                  # unrelated work NOT swept in
    assert "unrelated.txt" in g("status", "--porcelain").stdout  # still staged
    # unchanged path -> sha-based no-commit detection, no push attempted
    assert util.commit_paths_and_push("noop", [repo / "target.txt"]) is False


# --------------------------------------------------------------------------- #
# refresh_market keeps a real valuation over an empty quoteSummary shell
# --------------------------------------------------------------------------- #
def _base_raw():
    return {"symbol": "T", "annual": {"dates": ["2024-12-31"], "revenue": [100.0]},
            "quarterly": {}, "surprises": [],
            "valuation": {"marketCap": 5e9, "trailingPE": 10.0, "currency": "USD"},
            "prices": {"monthly": {"dates": ["2026-01-31"], "close": [10.0]}},
            "fetch_ok": True}


class _ShellClient:
    """quoteSummary answers with an empty result shell; the chart leg fails."""

    def get_json(self, path, params, retries=3):
        if "quoteSummary" in path:
            return {"quoteSummary": {"result": [{}]}}
        raise RuntimeError("chart down")


class _LiveClient:
    def get_json(self, path, params, retries=3):
        if "quoteSummary" in path:
            return {"quoteSummary": {"result": [{
                "summaryDetail": {"marketCap": {"raw": 7e9}, "trailingPE": {"raw": 12.0}},
                "price": {"currency": "USD"},
            }]}}
        raise RuntimeError("chart down")


def test_refresh_keeps_valuation_on_empty_shell():
    out = yahoo.refresh_market("T", _ShellClient(), _base_raw())
    assert out is not None
    assert out["valuation"]["marketCap"] == 5e9        # old real block kept
    assert out["prices"]["monthly"]["dates"]           # old prices kept too
    assert out["fetch_ok"] is True


def test_refresh_replaces_valuation_when_new_is_real():
    out = yahoo.refresh_market("T", _LiveClient(), _base_raw())
    assert out["valuation"]["marketCap"] == 7e9
    assert out["valuation"]["trailingPE"] == 12.0


def test_refresh_takes_new_when_old_also_empty():
    base = _base_raw()
    base["valuation"] = {}
    out = yahoo.refresh_market("T", _ShellClient(), base)
    assert out["valuation"]["marketCap"] is None       # new shell accepted
    assert out["fetch_ok"] is True                     # statements carry it
