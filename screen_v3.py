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
import saba_ukit
import screen_core as core
from aic_scraper import fetch_aic_raw, fetch_aic_summary
from yahoo_nav_scraper import fetch_yahoo_discounts

try:
    import activist_campaigns as _campaigns
    _HAS_CAMPAIGNS = True
except Exception:
    _HAS_CAMPAIGNS = False


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
    active_campaigns: dict[str, list[str]] | None = None,
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
    # If we still have nothing, mark explicitly — the previous
    # behaviour silently scored these at zero IRR which made them
    # invisible to the diagnostics. We want to see them.
    if r.nav_discount_est is None:
        r.error = "no_discount"
        return r

    # NAV trajectory + historical discount context from AIC
    # (informational + needed early for discount-stretch promotion)
    if aic_summary is not None:
        r.nav_tr_1y = aic_summary.get("nav_tr_1y")
        r.nav_tr_3y = aic_summary.get("nav_tr_3y")
        r.aic_sector_code = aic_summary.get("sector")
        r.discount_3y_avg = aic_summary.get("discount_3y_avg")
        r.discount_52w_high = aic_summary.get("discount_52w_high")
        r.discount_52w_low = aic_summary.get("discount_52w_low")
        r.dividend_yield_pct = aic_summary.get("dividend_yield_pct")

    # Saba UKIT membership — strong activist-engagement flag
    try:
        r.saba_ukit_member = ticker in saba_ukit.saba_ukit_all()
    except Exception:
        r.saba_ukit_member = False

    # Recovery + total return, with NAV-trajectory penalty applied
    recovery, etr, nav_pen = core.compute_recovery_upside(
        r.nav_discount_est, r.nav_quality, navtr_1y=r.nav_tr_1y)
    r.recovery_rate = recovery
    r.expected_total_return = etr
    r.nav_penalty_applied = nav_pen

    # Path-risk haircut: PE/property books can mark down before we see
    # crystallisation. Listed-clean has zero haircut; PE 15%.
    pr = core.path_risk_haircut(r.nav_quality)
    r.path_risk_haircut = pr
    if r.expected_total_return is not None:
        r.expected_total_return = r.expected_total_return * (1.0 - pr)

    # POST_RERATING taper — adjust the remaining-return potential
    if r.phase == "POST_RERATING" and r.chg_13w_pct and r.expected_total_return:
        remaining = core._post_rerating_taper(r.chg_13w_pct, r.expected_total_return)
        r.expected_total_return = r.expected_total_return * remaining

    # Catalyst auto-promotion. Static tags in universe.csv get stale;
    # two live signals can override:
    #   (a) RNS density — multiple winddown/tender filings or active
    #       TR-1 + PDMR cluster → promote to LIKELY/REVIEW
    #   (b) Discount stretch — discount > 1.4× 3y-avg OR > 52w-high +
    #       4pp → promote to DCM_ACTIVE (the SERE pattern)
    r.catalyst_static = r.catalyst
    promoted = r.catalyst
    promoted_by = "none"
    if signal is not None and signal.rns_available:
        rns = signal.rns_counts or {}
        wd = rns.get("winddown", 0)
        tender = rns.get("tender", 0)
        tr1 = rns.get("tr1", 0)
        pdmr = rns.get("pdmr", 0)
        review = rns.get("review", 0)
        if wd >= 3 or tender >= 2:
            promoted = "WIND_DOWN_LIKELY"
            promoted_by = "rns"
        elif review >= 3 or (tr1 >= 5 and pdmr >= 2):
            if r.catalyst in ("", "STRUCTURAL_DISCOUNT", None):
                promoted = "STRATEGIC_REVIEW"
                promoted_by = "rns"
    # Discount stretch — only when RNS didn't already promote and the
    # current tag is the generic structural / empty bucket.
    if promoted_by == "none" and r.catalyst in ("", "STRUCTURAL_DISCOUNT", None):
        if core.is_discount_stretched(r.nav_discount_est, r.discount_3y_avg,
                                       r.discount_52w_high):
            promoted = params.DISCOUNT_STRETCH_TARGET
            promoted_by = "discount_stretch"
    if promoted != r.catalyst and promoted:
        r.catalyst = promoted
    r.catalyst_promoted_by = promoted_by
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
        r.rns_pdmr_buys = getattr(signal, "pdmr_buys", 0) or None
        r.rns_pdmr_sells = getattr(signal, "pdmr_sells", 0) or None
        r.pdmr_buy_gbp = getattr(signal, "pdmr_buy_gbp", 0.0) or None
        r.rns_tr1_buys = getattr(signal, "tr1_buys", 0) or None
        r.rns_tr1_sells = getattr(signal, "tr1_sells", 0) or None
        r.rns_tr1_material_adds = getattr(signal, "tr1_material_adds", 0) or None
        r.rns_tr1_activist_buys = getattr(signal, "tr1_activist_buys", 0) or None
        r.tr1_buy_total_pp = getattr(signal, "tr1_buy_total_pp", 0.0) or None
        holders = getattr(signal, "activist_holders", []) or []
        r.activist_holders = "|".join(holders[:5]) if holders else None
        r.resolution_score = getattr(signal, "resolution_score", 0.0)
    # Apply the multiplier only if at least one source provided usable
    # coverage — else keep the base prob to avoid silent no-news penalty
    # from a failed scrape.
    # Active cross-name campaign membership — additional probability
    # uplift when this ticker is part of a current activist sweep.
    campaign_mult = 1.0
    if active_campaigns is not None and ticker in active_campaigns:
        groups = active_campaigns[ticker]
        r.active_campaign_groups = "|".join(groups)
        # +5% per distinct activist group, capped at +20%
        campaign_mult = 1.0 + min(0.20, 0.05 * len(groups))

    if signal is not None and (signal.coverage_ok or signal.rns_available):
        mult = 0.70 + 1.30 * signal.signal_score
        res = getattr(signal, "resolution_score", 0.0) or 0.0
        res_mult = 1.0 + 0.40 * res
        r.catalyst_prob_signal_adj = min(
            0.95, base_prob * mult * res_mult * campaign_mult)
    else:
        r.catalyst_prob_signal_adj = min(0.95, base_prob * campaign_mult)

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
            # Anchored VWAP from catalyst date — surfaces names trading
            # below the post-announcement market consensus (workout
            # being doubted = entry opportunity).
            if data is not None and r.catalyst in (
                    "WIND_DOWN_COMMITTED", "WIND_DOWN_LIKELY",
                    "RETURN_OF_CAPITAL_LIVE", "STRATEGIC_REVIEW"):
                avwap = core.anchored_vwap(data, d0)
                if avwap and avwap > 0 and r.last_close:
                    r.anchored_vwap_since_catalyst = avwap
                    r.price_vs_avwap_pct = (r.last_close / avwap) - 1.0
        except ValueError:
            pass
    r.expected_duration_months = months
    r.expected_upside = (r.expected_total_return or 0.0) * (r.catalyst_prob_signal_adj or 0.0)
    # IRR has two components:
    #   (a) annualised event return (existing math)
    #   (b) dividend carry — what we earn waiting for the event to fire
    irr_event = core.annualise(r.expected_upside, months)
    irr_carry = core.dividend_carry_irr(
        r.dividend_yield_pct, months,
        r.catalyst_prob_signal_adj or 0.0)
    r.irr_from_event = irr_event
    r.irr_from_carry = irr_carry
    r.expected_irr = irr_event + irr_carry

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
    # Fundamentals sleeve: event catalyst + investable + positive IRR.
    # Now includes OPEN_END_CONVERSION_PROPOSED and DCM_ACTIVE — both
    # have meaningful catalyst probability without needing chart
    # confirmation. Open-end conversion is the Saba-preferred exit and
    # the highest-P event catalyst we score.
    if r.investable and r.catalyst in (
            "OPEN_END_CONVERSION_PROPOSED",
            "WIND_DOWN_COMMITTED", "WIND_DOWN_LIKELY",
            "RETURN_OF_CAPITAL_LIVE", "STRATEGIC_REVIEW",
            "DCM_ACTIVE"):
        if (r.expected_irr or 0) > 0:
            r.in_fundamentals_sleeve = True
    # Saba UKIT bonus: also qualifies for the fundamentals sleeve
    # because activist engagement IS an event catalyst even if the
    # static tag doesn't reflect it yet.
    if r.investable and r.saba_ukit_member and (r.expected_irr or 0) > 0:
        r.in_fundamentals_sleeve = True
    # Resolution-score promotion. >=0.5 means multiple fresh
    # corporate-action precursors are stacked: advisor appointment +
    # strategic review + buybacks + insider buys, all in the last 30
    # days. Promote even when the static catalyst tag is generic.
    if (r.investable
        and (r.resolution_score or 0.0) >= 0.50
        and (r.expected_irr or 0) > 0):
        r.in_fundamentals_sleeve = True
    # MICRO sleeve — gate-failed but catalyst alive. AEET/RMII/SBO
    # class: real committed wind-downs that have dried up below the
    # standard daily-value floor. Don't silently drop them.
    if (not r.investable
        and (r.expected_irr or 0) > 0.05
        and core.check_micro_investability(aic_record, r.catalyst)):
        r.in_micro_sleeve = True
        r.micro_position_size_pct = 1.0

    # (Historical discount context populated earlier — used for the
    # discount-stretch promotion test.)

    # Per-name "why this rank" explainer
    r.top_drivers = core.explain_drivers(r)

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

    # Sector median discount — for peer-relative scoring. Computed
    # once across all AIC names per sector code.
    sector_discounts: dict[str, list[float]] = {}
    for sym, rec in aic_summ.items():
        sec = rec.get("sector")
        d = rec.get("discount")
        if sec and d is not None:
            sector_discounts.setdefault(sec, []).append(d)
    import statistics
    sector_median = {sec: statistics.median(vals) for sec, vals in sector_discounts.items()
                     if len(vals) >= 3}
    print(f"[v3] sector medians computed for {len(sector_median)} AIC sectors",
          file=sys.stderr)

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

    # 4b) Cross-name activist campaigns — load active targets so each
    # screened name knows whether it's part of a current sweep.
    active_campaigns: dict[str, list[str]] = {}
    if _HAS_CAMPAIGNS:
        try:
            filings = _campaigns.collect_filings()
            camps = _campaigns.detect_campaigns(filings)
            active_campaigns = _campaigns.active_targets(camps)
            print(f"[v3] active activist campaigns: "
                  f"{len(active_campaigns)} target(s)", file=sys.stderr)
        except Exception as exc:
            print(f"[v3] campaign detector failed: {exc}", file=sys.stderr)

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
                active_campaigns=active_campaigns,
            )
            # Peer-relative discount — current vs sector median.
            # Positive = wider than peers (potentially more setup).
            if r.aic_sector_code and r.nav_discount_est is not None:
                med = sector_median.get(r.aic_sector_code)
                if med is not None:
                    r.discount_vs_sector_pp = (r.nav_discount_est - med) * 100
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
                "signal_score", "resolution_score",
                "rns_pdmr_buys", "rns_pdmr_sells",
                "rns_tr1_material_adds", "rns_tr1_activist_buys",
                "has_daily_spike",
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

    # ACTIVIST WATCH — names where institutional/insider conviction is
    # building right now. Sorted by resolution_score (fresh-only signal:
    # advisor appointment + strategic review + buybacks + PDMR buys +
    # institutional material adds, 15d half-life). This is the
    # "corporate action coming" tell — irrespective of phase or IRR.
    if "resolution_score" in df.columns:
        watch = df[(df["error"].isna()) & (df["resolution_score"] > 0.20)]
        if not watch.empty:
            cols_watch = ["ticker", "name", "phase", "catalyst",
                          "resolution_score", "rns_pdmr_buys",
                          "rns_tr1_material_adds", "rns_tr1_activist_buys",
                          "activist_holders", "expected_irr",
                          "composite_score"]
            cols_watch = [c for c in cols_watch if c in watch.columns]
            print("\n=== ACTIVIST WATCH — resolution signal > 0.20 "
                  f"({len(watch)}) ===")
            with pd.option_context("display.width", 240,
                                   "display.max_colwidth", 36):
                print(watch.sort_values(
                    "resolution_score", ascending=False)[cols_watch]
                    .head(20).to_string(index=False))

    # MICRO sleeve — gate-failed wind-downs with non-trivial IRR.
    # Position size ≤ 1% per name; assemble over multiple sessions.
    if "in_micro_sleeve" in df.columns:
        micro = df[(df["in_micro_sleeve"] == True) & (df["error"].isna())]
        show("MICRO SLEEVE — gate-failed but catalyst alive (size ≤1% per)",
             micro.sort_values("expected_irr", ascending=False),
             min(args.top, 20))

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
