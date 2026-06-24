"""Extract every revenue-flavored tag from cached EDGAR companyfacts for
every company we have, building a wide table that maps:

  ticker × revenue-tag → LTM value, YoY growth, share-of-total, n_periods

This is the "use everything we have" companion to segment_inflection_screener:
where segment_inflection filters for cleanly-inflecting product-services-
licenses-subscription splits, this extracts ALL revenue disaggregation
(including industry-specific totals like InterestAndDividendIncomeOperating
for banks, PremiumsEarnedNet for insurers, RealEstateRevenueNet for REITs)
without imposing the inflection filter.

Output: results_revenue_decomp/all.csv  — every (ticker, tag, value) tuple
        results_revenue_decomp/wide.csv — one row per ticker, columns per tag

Note: SEC's `companyfacts` JSON only carries non-dimensional consolidated
facts — true axis-level segments (Apple iPhone vs Mac) require parsing
XBRL instance documents via edgartools. This script extracts what's
available WITHOUT extra dependencies.
"""
from __future__ import annotations
import json, gzip, sys, re, collections
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from edgar_fetcher import _quarterly_records, _series_from_records, _derive_q4

EDGAR = Path('.cache/edgar')
OUT = Path('results_revenue_decomp'); OUT.mkdir(exist_ok=True)


# Every us-gaap revenue-flavored tag worth extracting. Far broader than
# REVENUE_CATEGORIES in the inflection screener — the goal here is to use
# EVERY revenue tag a filer reports, regardless of whether it's a
# disaggregated stream or an industry-specific total.
REVENUE_TAGS = [
    # Consolidated revenue totals (used to compute share-of-total)
    'Revenues', 'SalesRevenueNet', 'RevenueFromContractWithCustomerExcludingAssessedTax',
    'RevenueFromContractWithCustomerIncludingAssessedTax',
    'RevenuesNetOfInterestExpense',  # banks
    # Generic disaggregation
    'SalesRevenueGoodsNet', 'SalesRevenueServicesNet', 'SalesRevenueProductLine',
    'ProductRevenue', 'ProductSales', 'ProductsRevenue',
    'ServiceRevenue', 'ServiceSales', 'RevenueFromServices', 'ServicesRevenue',
    'HostingServicesRevenue', 'TechnologyServicesRevenue',
    'LicensesRevenue', 'LicenseRevenue', 'LicenseAndServicesRevenue',
    'LicensesAndServicesRevenue', 'RoyaltyRevenue',
    'SubscriptionRevenue', 'RecurringRevenue', 'SubscriptionAndCirculationRevenue',
    'AdvertisingRevenue', 'AdvertisingAndOtherRevenue',
    # Banks
    'InterestAndDividendIncomeOperating', 'InterestIncomeOperating',
    'InterestAndFeeIncomeLoansAndLeases', 'InterestIncomeOnDepositsWithBanks',
    'NoninterestIncome', 'FeesAndCommissionsCreditAndDebitCards',
    'FeesAndCommissionsDepositorAccounts',
    # Insurance
    'PremiumsEarnedNet', 'PremiumsWrittenNet', 'InsurancePremiumsAndContractsRevenue',
    # Real estate / lodging
    'OperatingLeasesIncomeStatementLeaseRevenue', 'RentalIncomeNonoperating',
    'LeaseAndRentalRevenue', 'RealEstateRevenueNet', 'CasinoRevenue', 'GamingRevenue',
    'HotelRevenue', 'OccupancyRevenue',
    # Energy
    'OilAndGasRevenue', 'OilAndGasSalesRevenue',
    'RegulatedAndUnregulatedOperatingRevenue',
    # Brokerage
    'BrokerageCommissionsRevenue', 'CommissionsRevenue', 'InvestmentBankingRevenue',
    'PrincipalTransactionsRevenue',
    # Healthcare
    'HealthCareOrganizationRevenue', 'PharmaceuticalRevenue',
    # Cloud / software
    'CloudServicesRevenue', 'SoftwareRevenue', 'HardwareRevenue',
    # Other
    'EquipmentRevenue', 'FranchiseRevenue', 'MaintenanceRevenue', 'OtherRevenue',
    'SubleaseIncome',
]


def _get_quarterly_series(facts: dict, tag: str) -> pd.Series:
    node = facts.get(tag)
    if not node:
        return pd.Series(dtype=float)
    units = node.get('units', {})
    # Most revenue tags carry USD; bank/insurance may carry their own
    for unit_key in ('USD', 'USD/shares'):
        recs = units.get(unit_key)
        if not recs:
            continue
        qs = _quarterly_records(recs)
        if not qs:
            continue
        q, a = _series_from_records(qs)
        return _derive_q4(q, a)
    return pd.Series(dtype=float)


def _ltm_yoy(s: pd.Series) -> tuple[float | None, float | None]:
    """Return (ltm_value, yoy_growth_pct) from a quarterly series."""
    if s.empty or len(s) < 8:
        return None, None
    rolled = s.rolling(4).sum().dropna()
    if len(rolled) < 5:
        return None, None
    now = float(rolled.iloc[-1])
    prv = float(rolled.iloc[-5])
    if abs(prv) == 0:
        return now, None
    return now, (now - prv) / abs(prv) * 100


def main():
    with open(EDGAR / 'company_tickers.json') as f:
        raw = json.load(f)
    cik_to_t = {int(r['cik_str']): r['ticker'].upper() for r in raw.values()}

    files = list(EDGAR.glob('CF_*.json.gz'))
    print(f'Scanning {len(files):,} EDGAR files for revenue disaggregation...')

    rows = []  # long format: ticker, tag, ltm_M, yoy_pct, share_of_total_pct
    wide_rows = {}  # ticker -> {tag: ltm_M, tag_g: yoy_pct, ...}
    for i, f in enumerate(files):
        m = re.search(r'CF_(\d+)\.json\.gz$', f.name)
        if not m: continue
        cik = int(m.group(1))
        tkr = cik_to_t.get(cik)
        if not tkr: continue
        try:
            with gzip.open(f, 'rt') as fp:
                facts = json.load(fp)['facts'].get('us-gaap', {})
        except Exception:
            continue

        # Compute revenue total first (prefer the most common tags)
        total_ltm = None
        for tag in ('Revenues', 'SalesRevenueNet',
                    'RevenueFromContractWithCustomerExcludingAssessedTax'):
            s = _get_quarterly_series(facts, tag)
            ltm, _ = _ltm_yoy(s)
            if ltm and ltm > 0:
                total_ltm = ltm
                break

        wide_entry = {'ticker': tkr, 'total_ltm_M': total_ltm / 1e6 if total_ltm else None}
        any_subtag = False
        for tag in REVENUE_TAGS:
            s = _get_quarterly_series(facts, tag)
            ltm, g = _ltm_yoy(s)
            if ltm is None:
                continue
            share = (ltm / total_ltm * 100) if total_ltm and total_ltm > 0 else None
            rows.append({
                'ticker': tkr, 'tag': tag,
                'ltm_M': ltm / 1e6,
                'yoy_pct': g,
                'share_of_total_pct': share,
            })
            wide_entry[f'{tag}_M'] = ltm / 1e6
            if g is not None:
                wide_entry[f'{tag}_yoy'] = g
            any_subtag = True
        if any_subtag:
            wide_rows[tkr] = wide_entry

        if (i + 1) % 500 == 0:
            print(f'  {i+1:>5,}/{len(files):,}  tickers_with_data={len(wide_rows):,}')

    long_df = pd.DataFrame(rows)
    long_df.to_csv(OUT / 'all.csv', index=False)
    wide_df = pd.DataFrame(list(wide_rows.values())).set_index('ticker')
    wide_df.to_csv(OUT / 'wide.csv')
    print(f'\nrows: {len(long_df):,} (ticker, tag) tuples')
    print(f'wide: {len(wide_df):,} unique tickers with ≥1 revenue tag')
    print(f'\nMost-populated tags:')
    print(long_df['tag'].value_counts().head(20).to_string())


if __name__ == '__main__':
    main()
