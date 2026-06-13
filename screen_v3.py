"""v3 screener — recovery-rate × IRR × signal-adjusted probability.

Output: ranked CSV per run (results_YYYYMMDD.csv) + console tables.

Usage:
    python3 screen_v3.py                       # full universe, no signals
    python3 screen_v3.py --signals             # also scrape news signals
                                               # for top-discount UK names
    python3 screen_v3.py --refresh-prices      # force OHLCV cache refresh
    python3 screen_v3.py --tickers SEIT.L GCP.L
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import asdict
from datetime import datetime

import pandas as pd

import metadata
import params
import price_store
import screen_core as core
from aic_scraper import fetch_aic_raw, fetch_aic_summary
from yahoo_nav_scraper import fetch_yahoo_discounts


# ---------------------------------------------------------------------------

def screen_one(
    ticker: str,
    *,
    aic_record: dict | None,
    aic_summary: dict | None,
    yahoo_discount: float | None,
    signal,           # signals.TickerSignals or None
    ohlcv: pd.DataFrame | None,
    daily_ohlcv: pd.DataFrame | None = None,
) -> core.ScreenResult:

    row = metadata.load_universe().get(ticker.upper())
    r = core.ScreenResult(
        ticker=ticker,
        name=(row.name if row else None) or (aic_record.get("Name") if aic_record else None),
        isin=row.isin if row else None,
        catalyst=row.catalyst if row else "",
        nav_quality=row.nav_quality if row else "",
    )

    # Investability gates (catalyst-class-aware via params)
    investable, reasons = core.check_investability(ticker, aic_record, catalyst=r.catalyst)
    r.investable = investable
    r.investability_reasons = reasons
    r.gate_market_cap = "market cap" not in " ".join(reasons)
    r.gate_daily_value = "daily value" not in " ".join(reasons)
    r.gate_gearing = "gearing" not in " ".join(reasons)
    r.gate_ongoing_charge = "ongoing charge" not in " ".join(reasons)

    # Price data
    if ohlcv is None or len(ohlcv) < 30:
        r.error = "no price data"
        return r
    data = ohlcv
    r.last_close = float(data["Close"].iloc[-1])

    # Base detection
    base = core.detect_base(data)
    if base is None:
        r.error = "no base"
        r.phase = "NO_BASE"
        # Still populate discount & catalyst data for completeness
        _populate_discount(r, aic_summary, yahoo_discount, row)
        return r

    r.base_start = base.index[0]
    r.base_length_weeks = len(base)
    closes = base["Close"]
    r.base_low = float(closes.min())
    r.base_high = float(closes.max())
    med = float(closes.median())
    r.base_range_pct = (r.base_high - r.base_low) / med if med > 0 else None
    lo_q, hi_q = float(closes.quantile(0.25)), float(closes.quantile(0.75))
    # IQR range — robust to outliers, used by compute_setup_score for
    # the broken-base check.
    r.base_quantile_range_pct = (hi_q - lo_q) / med if med > 0 else None

    # POC
    r.poc = core.base_volume_profile(base)
    if r.poc and r.poc > 0:
        r.poc_distance_pct = abs(r.last_close - r.poc) / r.poc

    # Price change
    if len(data) >= 14:
        r.chg_13w_pct = float(data["Close"].iloc[-1] / data["Close"].iloc[-14] - 1)
    if len(data) >= 27:
        r.chg_26w_pct = float(data["Close"].iloc[-1] / data["Close"].iloc[-27] - 1)

    # Volume features
    bv = base["Volume"].astype(float)
    if len(bv) >= 5 and bv.std() > 0:
        r.vol_z_last = float((data["Volume"].iloc[-1] - bv.mean()) / bv.std())
    signed_sum, count_ge_1p5, max_abs = core.directional_vol_score(data, base, window=8)
    r.directional_vol_8w = signed_sum
    r.vol_z_8w_bars_over_1p5 = count_ge_1p5
    r.vol_z_8w_max = max_abs

    # Daily spike — single-bar volume signature that weekly bars
    # smooth over. Either modality (weekly absorption OR daily spike)
    # is enough to trigger BASE_ABSORBING.
    if daily_ohlcv is not None:
        dz_max, dz_dt, dz_signed, has_spike = core.daily_vol_spike_features(
            daily_ohlcv)
        r.daily_vol_z_max_30d = dz_max
        r.daily_vol_z_max_30d_date = dz_dt
        r.daily_vol_spike_directional = dz_signed
        r.has_daily_spike = has_spike

    # Recent selloff (renamed)
    recent = data["Close"].iloc[-6:]
    if len(recent) >= 2:
        weekly_chg = recent.pct_change().dropna()
        r.recent_selloff = bool((weekly_chg < -0.08).any())
        if r.recent_selloff:
            r.selloff_max_drop_pct = float(weekly_chg.min())

    # MFI
    mfi = core.money_flow_index(data, period=18)
    if len(mfi.dropna()) >= 2:
        r.mfi = float(mfi.iloc[-1])
        r.mfi_rising = float(mfi.iloc[-1]) > float(mfi.iloc[-2])
    if len(mfi.dropna()) >= 8:
        r.mfi_low_8w = float(mfi.iloc[-8:].min())

    in_base = (r.base_low * 0.95 <= r.last_close <= r.base_high * 1.05)
    r.in_base = in_base

    r.phase = core.classify_phase(
        in_base=in_base,
        base_length_weeks=r.base_length_weeks,
        vol_z_last=r.vol_z_last,
        vol_z_8w_max=r.vol_z_8w_max,
        directional_8w=r.directional_vol_8w,
        chg_13w=r.chg_13w_pct,
        last_close=r.last_close,
        base_high=r.base_high,
        base_low=r.base_low,
        recent_selloff=r.recent_selloff,
        mfi_low_8w=r.mfi_low_8w,
        daily_vol_z_max_30d=r.daily_vol_z_max_30d,
        daily_vol_spike_directional=r.daily_vol_spike_directional,
    )

    # Discount
    _populate_discount(r, aic_summary, yahoo_discount, row)

    # NAV trajectory from AIC (informational + recovery penalty)
    if aic_summary is not None:
        r.nav_tr_1y = aic_summary.get("nav_tr_1y")
        r.nav_tr_3y = aic_summary.get("nav_tr_3y")

    # Recovery + total return, with NAV-trajectory penalty applied
    recovery, etr, nav_pen = core.compute_recovery_upside(
        r.nav_discount_est, r.nav_quality, navtr_1y=r.nav_tr_1y)
    r.recovery_rate = recovery
    r.expected_total_return = etr
    r.nav_penalty_applied = nav_pen

    # POST_RERATING taper — adjust the remaining-return potential
    if r.phase == "POST_RERATING" and r.chg_13w_pct and r.expected_total_return:
        remaining = core._post_rerating_taper(r.chg_13w_pct, r.expected_total_return)
        r.expected_total_return = etr * remaining

    # Catalyst probability — base × signal multiplier
    base_prob = params.CATALYST_PROB_BASE.get(r.catalyst, params.DEFAULT_PROB_BASE)
    r.catalyst_prob_base = base_prob
    if signal is not None:
        r.signal_score = signal.signal_score
        r.news_score = signal.news_score
        r.rns_score = signal.rns_score
        r.rns_tr1 = signal.rns_counts.get("tr1") if signal.rns_counts else None
        r.rns_pdmr = signal.rns_counts.get("pdmr") if signal.rns_counts else None
        r.rns_winddown = signal.rns_counts.get("winddown") if signal.rns_counts else None
        r.rns_tender = signal.rns_counts.get("tender") if signal.rns_counts else None
        r.rns_buyback = signal.rns_counts.get("buyback") if signal.rns_counts else None
    # Apply the multiplier only if at least one source provided usable
    # coverage — else keep the base prob to avoid silent no-news penalty
    # from a failed scrape.
    if signal is not None and (signal.coverage_ok or signal.rns_available):
        mult = 0.70 + 1.30 * signal.signal_score
        r.catalyst_prob_signal_adj = min(0.95, base_prob * mult)
    else:
        r.catalyst_prob_signal_adj = base_prob

    # Catalyst-age adjustment for wind-downs / RoC. If the universe
    # row has a catalyst_date, compute months elapsed and apply both
    # probability uplift and duration compression. A wind-down 18
    # months in is closer to crystallisation than one announced last
    # week — higher prob, less time left.
    months = float(params.CATALYST_DURATION_MONTHS.get(
        r.catalyst, params.DEFAULT_DURATION_MONTHS))
    if row and row.catalyst_date:
        try:
            from datetime import datetime as _dt
            d0 = _dt.strptime(row.catalyst_date, "%Y-%m-%d")
            age_months = max(0.0, (_dt.utcnow() - d0).days / 30.4)
            r.catalyst_age_months = age_months
            prob_mult, dur_mult = core.wind_down_age_adjustment(age_months, r.catalyst)
            if r.catalyst_prob_signal_adj is not None:
                r.catalyst_prob_signal_adj = min(
                    0.95, r.catalyst_prob_signal_adj * prob_mult)
            months = months * dur_mult
        except ValueError:
            pass
    r.expected_duration_months = months
    r.expected_upside = (r.expected_total_return or 0.0) * (r.catalyst_prob_signal_adj or 0.0)
    r.expected_irr = core.annualise(r.expected_upside, months)

    # Setup score — pure technicals
    r.phase_score = params.PHASE_WEIGHT.get(r.phase, 0.10)
    r.setup_score = core.compute_setup_score(r)

    # Composite — setup × IRR. Investability gates can zero this out.
    if r.investable:
        r.composite_score = (r.setup_score or 0.0) * max(0.0, r.expected_irr or 0.0)
    else:
        r.composite_score = 0.0

    # Sleeve membership.
    # Setup sleeve: actually-firing phase + non-trivial setup score.
    if r.investable and (r.setup_score or 0) >= 0.05 and r.phase in (
            "BASE_ABSORBING", "BASE_BREAKOUT", "CAPITULATION",
            "BASE_QUIET"):
        r.in_setup_sleeve = True
    # Fundamentals sleeve: committed event catalyst + investable + IRR.
    # This is the leg that would have caught USF.L pre-rerating.
    if r.investable and r.catalyst in (
            "WIND_DOWN_COMMITTED", "WIND_DOWN_LIKELY",
            "RETURN_OF_CAPITAL_LIVE", "STRATEGIC_REVIEW"):
        if (r.expected_irr or 0) > 0:
            r.in_fundamentals_sleeve = True

    # Historical context (informational)
    if aic_summary is not None:
        s = aic_summary
        r.discount_3y_avg = s.get("discount_3y_avg")
        r.discount_52w_high = s.get("discount_52w_high")
        r.discount_52w_low = s.get("discount_52w_low")

    return r


def _populate_discount(r, aic_summary, yahoo_discount, row):
    """Discount lookup priority: AIC live -> Yahoo -> universe override."""
    discount = None
    src = "none"
    if aic_summary is not None and aic_summary.get("discount") is not None:
        discount = core.clamp_discount(aic_summary["discount"])
        if discount is not None:
            src = "aic_live"
    if discount is None and yahoo_discount is not None:
        discount = core.clamp_discount(yahoo_discount)
        if discount is not None:
            src = "yahoo_live"
    if discount is None and row and row.discount_override is not None:
        discount = core.clamp_discount(row.discount_override)
        if discount is not None:
            src = "override"
    r.nav_discount_est = discount
    r.discount_source = src


# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers", nargs="*")
    parser.add_argument("--groups", nargs="*")
    parser.add_argument("--signals", action="store_true",
                        help="Scrape qualitative signals (news + RNS) for "
                             "top-discount UK CEFs")
    parser.add_argument("--signals-rns-only", action="store_true",
                        help="Faster — fetches only Investegate RNS, "
                             "skips Google News. Works on all UK tickers, "
                             "not just top-N.")
    parser.add_argument("--signal-top-n", type=int, default=60)
    parser.add_argument("--refresh-prices", action="store_true")
    parser.add_argument("--price-ttl-h", type=float, default=24.0)
    parser.add_argument("--daily-spike", action="store_true",
                        help="Fetch daily bars too and check for "
                             "single-day vol spikes (the intra-week "
                             "signature weekly bars miss).")
    parser.add_argument("--top", type=int, default=25)
    parser.add_argument("--out", default=None,
                        help="Write ranked CSV to this path "
                             "(default results_YYYYMMDD.csv)")
    parser.add_argument("--include-uninvestable", action="store_true",
                        help="Also score gate-failing names (default: drop)")
    args = parser.parse_args()

    # 1) Universe
    universe = metadata.load_universe()
    if args.tickers:
        symbols = [t.upper() if "." in t else f"{t.upper()}.L" for t in args.tickers]
    elif args.groups:
        symbols = sorted({t for t, r in universe.items() if r.group in set(args.groups)})
    else:
        symbols = sorted(universe.keys())
    print(f"[v3] universe: {len(symbols)} tickers", file=sys.stderr)

    # 2) Discount feeds
    print("[v3] loading AIC live discount data...", file=sys.stderr)
    aic_raw = fetch_aic_raw()
    aic_summ = fetch_aic_summary()
    aic_by_ticker = {f"{epic}.L": rec for epic, rec in aic_raw.items()}
    print(f"[v3] AIC records: {len(aic_summ)}", file=sys.stderr)

    print("[v3] loading Yahoo bookValue discounts (non-UK)...", file=sys.stderr)
    non_uk = [t for t in symbols if not t.endswith(".L")]
    yh_discounts = fetch_yahoo_discounts(non_uk) if non_uk else {}
    print(f"[v3] Yahoo discounts: {len(yh_discounts)} resolved", file=sys.stderr)

    # 3) Price store
    if args.refresh_prices:
        print(f"[v3] refreshing price cache for {len(symbols)} tickers...",
              file=sys.stderr)
        price_store.refresh_all(symbols, ttl_hours=0, verbose=True)
    else:
        # Backfill any missing (still uses TTL)
        price_store.refresh_all(symbols, ttl_hours=args.price_ttl_h)

    # 4) Optional signals
    sig_map = {}
    if args.signals or args.signals_rns_only:
        try:
            import signals as sigmod
            include_news = bool(args.signals) and not args.signals_rns_only
            # Build candidate list. For RNS-only, sweep ALL UK tickers
            # with an AIC discount record (cheap, ~1 HTTP per ticker).
            # For news-mode, restrict to top-N by discount (slow).
            cands = []
            for sym in symbols:
                if not sym.endswith(".L"):
                    continue
                rec = aic_summ.get(sym)
                # RNS works without an AIC name (use EPIC alone) but we
                # use the AIC name for the news queries when present.
                name = rec["name"] if rec and rec.get("name") else (
                    universe.get(sym).name if universe.get(sym) else "")
                disc = rec["discount"] if rec else None
                cands.append((sym, name, disc if disc is not None else 0.0))
            if include_news:
                cands = [c for c in cands if c[2] >= 0.05]
                cands.sort(key=lambda r: -r[2])
                cands = cands[: args.signal_top_n]
            print(f"[v3] signals: scraping {len(cands)} tickers "
                  f"(include_news={include_news})", file=sys.stderr)
            sig_map = sigmod.fetch_signals_batch(
                [(t, n) for t, n, _ in cands],
                verbose=True, include_news=include_news)
        except Exception as exc:
            print(f"[v3] signals disabled: {exc}", file=sys.stderr)

    # 5) Score (with optional daily-bar pull for spike detection)
    fetch_daily = bool(args.daily_spike)
    results: list[core.ScreenResult] = []
    for i, sym in enumerate(symbols, 1):
        try:
            daily = (price_store.get_daily(sym, ttl_hours=args.price_ttl_h)
                     if fetch_daily else None)
            r = screen_one(
                sym,
                aic_record=aic_by_ticker.get(sym),
                aic_summary=aic_summ.get(sym),
                yahoo_discount=yh_discounts.get(sym),
                signal=sig_map.get(sym),
                ohlcv=price_store.get(sym, ttl_hours=args.price_ttl_h),
                daily_ohlcv=daily,
            )
        except Exception as exc:
            r = core.ScreenResult(ticker=sym, error=f"screen_one: {exc}")
        results.append(r)
        if i % 50 == 0:
            print(f"  [{i}/{len(symbols)}] scored", flush=True, file=sys.stderr)

    # 6) DataFrame
    df = pd.DataFrame([asdict(r) for r in results])
    # Reformat list field
    if "investability_reasons" in df.columns:
        df["investability_reasons"] = df["investability_reasons"].apply(
            lambda xs: "; ".join(xs) if isinstance(xs, list) else "")

    # 7) Output CSV
    out_path = args.out or f"results_{datetime.now().strftime('%Y%m%d')}.csv"
    df.to_csv(out_path, index=False)
    print(f"[v3] wrote {len(df)} rows to {out_path}", file=sys.stderr)

    # 8) Console summaries
    keep = df[(df["error"].isna()) & (df["composite_score"] > 0)] \
        if "composite_score" in df.columns else df[df["error"].isna()]

    if not args.include_uninvestable and "investable" in df.columns:
        keep = keep[keep["investable"] == True]

    cols_top = ["ticker", "name", "phase", "catalyst", "nav_quality",
                "nav_discount_est", "discount_source", "nav_tr_1y",
                "nav_penalty_applied", "recovery_rate",
                "expected_total_return", "expected_duration_months",
                "catalyst_age_months",
                "catalyst_prob_base", "catalyst_prob_signal_adj",
                "signal_score", "has_daily_spike",
                "expected_upside", "expected_irr",
                "setup_score", "composite_score"]
    cols_top = [c for c in cols_top if c in keep.columns]

    def show(title: str, frame: pd.DataFrame, n: int):
        print(f"\n=== {title} ({len(frame)}) ===")
        if frame.empty:
            print("(empty)")
            return
        with pd.option_context("display.width", 240, "display.max_colwidth", 40):
            print(frame[cols_top].head(n).to_string(index=False))

    # ---- Two-sleeve ranking ----
    # Setup-confirmed: composite (setup_score × IRR) — needs a chart
    # signature to fire.
    if "in_setup_sleeve" in df.columns:
        setup = df[(df["in_setup_sleeve"] == True) & (df["error"].isna())]
    else:
        setup = keep
    show("SETUP SLEEVE — top by composite (setup × IRR)",
         setup.sort_values("composite_score", ascending=False), args.top)

    # Fundamentals-only: event catalyst + investable, ranked by IRR
    # alone. This is the leg that catches stub wind-downs that don't
    # print a chart footprint (USF.L pattern).
    if "in_fundamentals_sleeve" in df.columns:
        fund = df[(df["in_fundamentals_sleeve"] == True) & (df["error"].isna())]
    else:
        fund = pd.DataFrame()
    show("FUNDAMENTALS SLEEVE — top by IRR alone "
         "(committed event catalysts, ignores setup score)",
         fund.sort_values("expected_irr", ascending=False), args.top)

    # Divergence — names where the two sleeves disagree.
    if "in_setup_sleeve" in df.columns and "in_fundamentals_sleeve" in df.columns:
        diverge = df[
            (df["error"].isna())
            & (df["in_fundamentals_sleeve"] == True)
            & (df["in_setup_sleeve"] == False)
            & (df["expected_irr"] > 0.05)
        ]
        show("DIVERGENCE — fundamentals say yes, setup says no "
             "(the USF.L bucket — pure catalyst trades, size small)",
             diverge.sort_values("expected_irr", ascending=False),
             min(args.top, 20))

    by_phase = keep.groupby("phase").size().sort_values(ascending=False)
    print(f"\nPhase distribution among investable:\n{by_phase}")

    if not args.include_uninvestable:
        uninv = df[(df["investable"] == False)].sort_values(
            "expected_irr", ascending=False, na_position="last") \
            if "investable" in df.columns else pd.DataFrame()
        if not uninv.empty:
            print(f"\nDropped {len(uninv)} uninvestable names; "
                  f"top 5 by IRR shown for awareness:")
            print(uninv[["ticker", "name", "expected_irr",
                        "investability_reasons"]].head(5).to_string(index=False))

    return 0


if __name__ == "__main__":
    sys.exit(main())
