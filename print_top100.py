import csv

with open('/home/user/cyclepapa/top100.csv') as f:
    rows = list(csv.DictReader(f))

print(f'TOP {len(rows)} ranked')
print(f"{'#':<4}{'TKR':<11}{'REG':<5}{'MCAP':>7}{'PX':>9}{'TS':>6}{'CN':>4}{'C':>3} {'HQ':<13} SIGNALS")
print('-' * 130)
for r in rows:
    tk = r['ticker'][:10]
    rg = r['region']
    mc = r.get('market_cap_musd') or '0'
    px = r.get('current_price') or '0'
    ts = r.get('today_score') or '0'
    cf = r.get('confidence') or '-'
    ct = r.get('catalyst_hardness') or '-'
    hq = (r.get('hurdle_quality') or '-')[:12]
    sigs = []
    if r.get('transformation_signal') == 'True': sigs.append('TR')
    if r.get('active_bid') == 'True': sigs.append('BID')
    if r.get('has_special_committee') == 'True': sigs.append('CMTE')
    if r.get('activists_named'): sigs.append(f"ACT({r['activists_named'][:18]})")
    if r.get('advisers_named'): sigs.append('ADV')
    try:
        c = int(r.get('insider_form4_count_90d') or 0)
        if c >= 5: sigs.append(f'F4({c})')
    except Exception:
        pass
    if r.get('has_debt_event') == 'True': sigs.append('DEBT')
    if r.get('has_spinoff') == 'True': sigs.append('SPIN')
    if r.get('go_private_language') == 'True': sigs.append('PRIV')
    sig_str = ' '.join(sigs)[:78]
    try:
        px_n = float(px); px_str = f"${px_n:.2f}"
    except Exception:
        px_str = '-'
    try:
        mc_n = float(mc); mc_str = f"${mc_n:.0f}M" if mc_n > 0 else '-'
    except Exception:
        mc_str = '-'
    try:
        ts_str = f"{float(ts):.0f}"
    except Exception:
        ts_str = '-'
    print(f"{r['rank']:<4}{tk:<11}{rg:<5}{mc_str:>7}{px_str:>9}{ts_str:>6}{cf:>4}{ct:>3} {hq:<13} {sig_str}")
