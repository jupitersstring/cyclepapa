"""Append an asymmetry-tier tab to screener_report.xlsx based on the
cross-region qualitative deep-research scoring.

Tier ratings come from the 7-agent qualitative pass:
  ★★★★★ = exceptional (clear catalyst + downside-protected + insider buying)
  ★★★★  = strong (capital return + catalyst + clean governance)
  ★★★   = solid quality but limited asymmetry
  ★★    = mixed / structural overhang
  ★     = avoid / red flags
  0     = non-investable (delisted / shell / wrong ticker)
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd
from openpyxl import load_workbook

# (ticker, region, stars, headline_thesis_short)
ASYMMETRY = [
    # ★★★★★ exceptional
    ('MGM',        'US', 5, 'IAC accumulating through 25%; mgmt buyback ~7-8%/yr; BetMGM inflection'),
    ('ACRV',       'US', 5, 'CEO+CFO+RA Capital cluster-bought at lows; 52% ORR; funded to 2027'),
    ('G1A.DE',     'EU', 5, 'Mission 30 ahead of plan; debt-free; div-grower; optional buyback'),
    ('VPK.AS',     'EU', 5, '€1.7bn 2030 distribution programme; HAL-disciplined cash compounder'),
    ('GOOS.TO',    'CA', 5, 'Live take-private at $1.35-1.4B with multi-bidder competition'),
    ('TOU.TO',     'CA', 5, 'CEO Mike Rose buying weekly; LNG Canada AECO catalyst; hedge floor'),
    # ★★★★ strong
    ('GRWG',       'US', 4, '$46M cash = 38% of cap; no debt; CEO open-market buy May 2026'),
    ('UVSP',       'US', 4, 'Buyback +50% expansion; dividend +4.5%; director open-market buys'),
    ('FRAF',       'US', 4, 'EPS +69% YoY; director $106K open-market buy; 15% ROE'),
    ('AMAL',       'US', 4, 'Dividend +21%; active buyback; 21% ROE; isolated NPL pressure'),
    ('RLMD',       'US', 4, 'Pre-funded into Phase 3; CFO bought; NDV-01 76% durable CR'),
    ('IRMD',       'US', 4, '3870 product cycle; 31% op margin compounder'),
    ('RDVT',       'US', 4, '85% gross / 41% EBITDA margin; active buyback; record customer adds'),
    ('LXRX',       'US', 4, '$199M cash; Novo partnership; multi-shot pipeline'),
    ('NBN',        'US', 4, '$525M+ loan purchases since 9/25; NIM 5.15%'),
    ('CFBK',       'US', 4, 'Director Hoeweler bought open-market Dec 2025; 5% buyback'),
    ('RBKB',       'US', 4, 'Second-step thrift conversion closing Q3 2026 at $10'),
    ('LEU',        'US', 4, '$1.87B cash; DOE HALEU re-award post-June 2026'),
    ('OFG',        'US', 4, '$200M buyback + 17% div hike; PR discount; 16.4% ROATCE'),
    ('ENVX',       'US', 4, 'Smartphone OEM qualification on new framework; $582M cash'),
    ('TWO-PA',     'US', 4, 'Merger-arb pref; mandatory redemption $25 on UWMC deal close Q3'),
    ('HFBL',       'US', 4, 'Quality LA thrift; EPS doubled YoY; 92% through buyback'),
    ('DAR',        'US', 4, 'DGD turnaround; RVO tailwind; Point72 accumulating'),
    ('LAUR',       'US', 4, 'LATAM ed +15%; raised guide; $181M buyback runway'),
    ('EIG',        'US', 4, 'New $125M buyback + CFO open-market buys Nov 2025 at $37-40'),
    ('ABOS',       'US', 4, 'Cash through Phase 2 sabirnetug Alzheimer readout late 2026'),
    ('IFX.DE',     'EU', 4, 'Guidance raised twice; FY26 segment margin lifted to ~20%'),
    ('MUV2.DE',    'EU', 4, '€2.25bn buyback through Apr 2027; €24 div; Q1 net +57%'),
    ('NEM.DE',     'EU', 4, '95% recurring rev; +17% cc; HCSS transformative deal'),
    ('SZG.DE',     'EU', 4, 'Guidance raised twice; HKM closing; Aurubis windfall'),
    ('FRE.DE',     'EU', 4, 'S&P positive outlook; CFO insider buy; Tyenne biosimilar share gains'),
    ('SAX.DE',     'EU', 4, 'Müller family insider-buy cluster + live PE sale at €3-4bn'),
    ('HNR1.DE',    'EU', 4, '€12.50 dividend (+39%); post-Henchoz reset; Talanx-controlled quality'),
    ('CWC.DE',     'EU', 4, 'Foundation patient capital; 17-yr dividend streak; Cimpress monetisation'),
    ('PAT.DE',     'EU', 4, 'Trades near book; founder buying history; EBITDA +41% Q1'),
    ('SHL.DE',     'EU', 4, 'Spin-off doubles free float (forced buying); €230m buyback Jun-Jan'),
    ('ZURN.SW',    'EU', 4, 'Beazley closing H2 2026; SST 265%; underowned post-raise'),
    ('SMHN.DE',    'EU', 4, 'Q1 trough; record HBM/hybrid bonding order intake; H2 snapback'),
    ('ARIS.TO',    'CA', 4, 'Marmato Lower Mine Q4 first-gold; Soto Norte stream eliminated'),
    ('FTT.TO',     'CA', 4, 'Record $3.8B backlog; 25-yr div streak; 9.8% NCIB'),
    ('IAG.TO',     'CA', 4, '$310M NCIB at trough; Côté ramp post-conveyor fix; net cash'),
    ('NA.TO',      'CA', 4, 'CWB synergies running ahead of guide ($176M Q1 > $116M FY25)'),
    ('CM.TO',      'CA', 4, 'Caribbean divestiture + new NCIB 30M sh; new CEO Culham reset'),
    ('QBR-B.TO',   'CA', 4, 'Wireless +85% vs Big-3 -20%; div +14%; NCIB active'),
    ('PXT.TO',     'CA', 4, 'GeoPark activist proxy fight; 40% share reduction; div cushion'),
    ('REI-UN.TO',  'CA', 4, 'Chairman Sonshine net buyer LTM; 98.6% occ; 17.5% leasing spreads'),
    ('WSP.TO',     'CA', 4, 'TRC/Power Engineers integration delivering; backlog +18%; margin raise'),
    # ★ avoid / value-trap flags
    ('BYW.DE',     'EU', 1, 'StaRUG restructuring; €2.7bn shortfall; criminal probe; audit delay'),
    ('GXI.DE',     'EU', 2, 'BaFin probe; audit delay; technical default; SDAX expulsion'),
    ('OHB.DE',     'EU', 2, 'Stock up ~8x; KKR placement = imminent overhang'),
    ('VLN.TO',     'CA', 1, 'Deal pre-priced at C$13.10 — no minority premium'),
    ('FRMM',       'US', 0, 'Not Fremont — ETHZilla rebrand pivot shell'),
    ('ELTX',       'US', 0, 'Ticker mismatch — ELEV was acquired by Concentra July 2025'),
    ('LUNA',       'US', 0, 'Nasdaq delisted Jan 2025; OTC Expert Market only'),
    ('ASPU',       'US', 0, 'Voluntarily delisted 2023; $0.4M cash; sub-scale wind-down'),
    ('HOTH',       'US', 1, 'Pivoted to "nanomagnetic space-AI chips" — narrative shell'),
    ('ENVB',       'US', 1, 'Reverse split + 5B share authority proposal + going concern'),
]

def main():
    df = pd.DataFrame(ASYMMETRY, columns=['ticker','region','asymmetry_stars','thesis'])
    df = df.sort_values(['asymmetry_stars','region','ticker'], ascending=[False, True, True])

    # Append to existing workbook
    xlsx = Path('screener_report.xlsx')
    with pd.ExcelWriter(xlsx, engine='openpyxl', mode='a', if_sheet_exists='replace') as xw:
        df.to_excel(xw, sheet_name='asymmetry_tier', index=False)
        ws = xw.sheets['asymmetry_tier']
        ws.column_dimensions['A'].width = 12
        ws.column_dimensions['B'].width = 8
        ws.column_dimensions['C'].width = 18
        ws.column_dimensions['D'].width = 90
        ws.freeze_panes = 'A2'

    # Move asymmetry_tier to the front
    wb = load_workbook(xlsx)
    if 'asymmetry_tier' in wb.sheetnames:
        idx = wb.sheetnames.index('asymmetry_tier')
        wb.move_sheet('asymmetry_tier', offset=-idx)
        wb.save(xlsx)

    print(f'Appended asymmetry_tier tab with {len(df)} rows to {xlsx}')

if __name__ == '__main__':
    main()
