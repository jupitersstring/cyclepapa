"""Regression tests for the FMP-driven universe expansion: every company resolves
to ONE primary listing, and cross-listings / depositary receipts / secondary
lines of companies we already hold are never added."""
import importlib.util
from pathlib import Path

import pandas as pd

_spec = importlib.util.spec_from_file_location(
    "expand_universe", Path(__file__).resolve().parent.parent / "scripts" / "expand_universe.py")
eu = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(eu)

FX = {"USD": 1.0, "EUR": 1.1, "HKD": 0.13, "MXN": 0.05, "AUD": 0.65, "GBP": 1.3}


def _row(symbol, name, exchange, country, isin, mcap, price, vol, ccy="USD",
         industry="Banks - Regional", **flags):
    return {"symbol": symbol, "companyName": name, "exchange": exchange, "country": country,
            "isin": isin, "marketCap": mcap, "price": price, "averageVolume": vol,
            "currency": ccy, "industry": industry, "sector": "Financial Services",
            "isActivelyTrading": flags.get("active", True), "isEtf": flags.get("etf", False),
            "isFund": flags.get("fund", False), "isAdr": flags.get("adr", False)}


def _uni(*symbols_names):
    return pd.DataFrame([{"symbol": s, "name": n, "sector": "Financials",
                          "industry_group": "Banks", "industry": "Banks"}
                         for s, n in symbols_names])


def _run(rows, uni, min_mcap=50e6):
    prof = pd.DataFrame(rows)
    cw = eu.build_crosswalk(prof, uni)
    return eu.candidates(prof, uni, FX, min_mcap, cw)


def test_cross_listing_of_held_company_is_skipped():
    # NVIDIA held via NASDAQ; its Xetra line shares the ISIN -> never added
    rows = [_row("NVDA", "NVIDIA Corporation", "NASDAQ", "US", "US67066G1040", 5e12, 200, 2e8),
            _row("NVD.DE", "NVIDIA Corporation", "XETRA", "US", "US67066G1040", 5e12, 180, 1e5, "EUR")]
    out = _run(rows, _uni(("NVDA", "NVIDIA Corporation")))
    assert "NVD.DE" not in set(out["symbol"])


def test_primary_listing_is_highest_dollar_volume_venue():
    # Tencent (Cayman ISIN, no home exchange): HKSE line dwarfs the Vienna line
    rows = [_row("0700.HK", "Tencent Holdings Limited", "HKSE", "CN", "KYG875721634",
                 4e12, 438, 2e7, "HKD"),
            _row("NNND.VI", "Tencent Holdings Limited", "VIE", "CN", "KYG875721634",
                 4e11, 50, 1e3, "EUR")]
    out = _run(rows, _uni(("X", "Unrelated Co")))
    assert list(out["symbol"]) == ["0700.HK"]
    assert out.iloc[0]["region"] == "HK"


def test_foreign_domiciled_us_primary_listing_is_kept():
    # Medtronic: Irish ISIN, primary (and only) listing on NYSE -> added as US
    rows = [_row("MDT", "Medtronic plc", "NYSE", "IE", "IE00BTN1Y115", 1.1e11, 85, 6e6)]
    out = _run(rows, _uni(("X", "Unrelated Co")))
    assert list(out["symbol"]) == ["MDT"] and out.iloc[0]["region"] == "US"


def test_depositary_receipt_with_own_isin_skipped_by_name():
    # A Canadian CDR has its own ISIN but the held company's name
    rows = [_row("WMT.TO", "Walmart Inc.", "TSX", "US", "CA93114P1036", 8e11, 30, 5e5, "CAD")]
    out = _run(rows, _uni(("WMT", "Walmart Inc.")))
    assert out.empty


def test_cedear_and_foreign_board_listings_excluded():
    rows = [_row("BAC.BA", "Boeing Co. Cedear Each 6 Rep 1", "BUE", "US", "ARDEUT110004",
                 1.5e11, 100, 1e4),
            _row("SONYN.MX", "Sony Group Corporation", "MEX", "JP", "US8356993076",
                 1.4e11, 400, 1e4, "MXN")]
    out = _run(rows, _uni(("X", "Unrelated Co")))
    assert out.empty


def test_asx_hybrid_excluded_but_ordinary_kept():
    rows = [_row("AN3PJ.AX", "ANZ Capital Notes", "ASX", "AU", "AU0000AN3PJ1", 2e9, 100, 1e5, "AUD"),
            _row("XYZ.AX", "Xyz Mining Limited", "ASX", "AU", "AU000000XYZ1", 2e8, 1.5, 1e6, "AUD")]
    out = _run(rows, _uni(("X", "Unrelated Co")))
    assert set(out["symbol"]) == {"XYZ.AX"}


def test_dual_listing_collapsed_to_busier_line():
    # ICBC A-share and H-share: different ISINs, same company ("and" vs "&")
    rows = [_row("601398.SS", "Industrial & Commercial Bank of China", "SHH", "CN",
                 "CNE000001P37", 4.3e11, 7, 3e8, "USD"),
            _row("1398.HK", "Industrial and Commercial Bank of China", "HKSE", "CN",
                 "CNE1000003G1", 4.5e11, 6, 1e8, "USD")]
    out = _run(rows, _uni(("X", "Unrelated Co")))
    assert len(out) == 1 and out.iloc[0]["symbol"] == "601398.SS"


def test_excluded_countries_etfs_and_small_caps_skipped():
    rows = [_row("RELI.NS", "Reliance Industries", "NSE", "IN", "INE002A01018", 2e11, 1, 1e9),
            _row("SPY", "SPDR S&P 500", "AMEX", "US", "US78462F1030", 5e11, 500, 1e8, etf=True),
            _row("TINY", "Tiny Corp", "NASDAQ", "US", "US0000000001", 1e7, 1, 1e4)]
    out = _run(rows, _uni(("X", "Unrelated Co")))
    assert out.empty


def test_market_cap_normalized_to_usd_and_bucketed():
    # 1e10 HKD * 0.13 = $1.3B -> Small Cap (300M-2B); sub-unit GBp maps to GBP
    rows = [_row("1234.HK", "Some Hk Co Ltd", "HKSE", "HK", "HK0000012345", 1e10, 10, 1e6, "HKD"),
            _row("ABC.L", "Abc Widgets plc", "LSE", "GB", "GB00ABC00001", 1e9, 5, 1e6, "GBp")]
    out = _run(rows, _uni(("X", "Unrelated Co"))).set_index("symbol")
    assert abs(out.loc["1234.HK", "mcap_usd"] - 1.3e9) < 1e3
    assert out.loc["1234.HK", "size_bucket"] == "Small Cap"
    assert abs(out.loc["ABC.L", "mcap_usd"] - 1.3e9) < 1e3


def test_norm_name_strips_corporate_noise():
    assert eu._norm_name("The Walmart Inc.") == eu._norm_name("Walmart Inc")
    assert eu._norm_name("Industrial & Commercial Bank of China Ltd") == \
        eu._norm_name("Industrial and Commercial Bank of China Limited")
    assert eu._norm_name(float("nan")) == ""
