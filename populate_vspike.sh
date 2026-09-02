#!/usr/bin/env bash
# Resume-safe driver to populate the weekly+monthly volume-spike columns
# (vspike_*) across the full universe, then rebuild master + baskets + workbook
# and persist. Designed to be re-invoked (e.g. by a scheduled Routine) until it
# completes: it self-hydrates /tmp from the git-tracked data/ tree, resumes the
# scan from wherever the last run's checkpoint left off, and no-ops once done.
#
# Environmental realities it handles:
#   * Yahoo rate limits (volume_scan exits 2 → retry with cooldown)
#   * agent-proxy port rotation (each invocation picks up the live HTTPS_PROXY)
#   * background-process reaping on idle / container resets (git checkpoints)
set -o pipefail
cd /home/user/cyclepapa

# Don't stack instances.
if pgrep -f "volume_scan.py" >/dev/null 2>&1; then
  echo "volume_scan already running; skip"; exit 0
fi

# Hydrate /tmp resume inputs from the committed data/ tree (fresh container).
[ -d /tmp ] || exit 1
for f in data/stars_aligned/stars_aligned_*.csv; do cp -n "$f" /tmp/ 2>/dev/null; done
cp -n data/psar/mtf_psar_rank*.csv /tmp/ 2>/dev/null
cp -n data/leledc/leledc_rank.csv /tmp/ 2>/dev/null
if [ ! -f /tmp/volume_rank.csv ] && head -1 data/volume/volume_rank.csv 2>/dev/null | grep -q vspike_w_rvol; then
  cp data/volume/volume_rank.csv /tmp/volume_rank.csv
  echo "hydrated volume_rank ($(($(wc -l < /tmp/volume_rank.csv) - 1)) rows)"
fi

checkpoint () {
  [ -f /tmp/volume_rank.csv ] || return 0
  cp /tmp/volume_rank.csv data/volume/volume_rank.csv
  local n; n=$(($(wc -l < data/volume/volume_rank.csv) - 1))
  git add data/volume/volume_rank.csv 2>/dev/null
  git -c user.email=noreply@anthropic.com -c user.name=Claude \
      commit -q -m "checkpoint: volume_rank spike-column rescan ($n rows)" 2>/dev/null \
    && for k in 1 2 3 4; do
         git push -q origin claude/uncorrelated-stock-selection-DWVgB 2>/dev/null && break
         sleep $((k*2))
       done
  echo "  checkpoint ($n rows)"
}

echo "=== VOLUME rescan (weekly+monthly spike columns) ==="
DONE=0
for i in $(seq 1 8); do
  python volume_scan.py && { echo "scan complete"; DONE=1; break; }
  echo "vol attempt $i rc=$?; checkpoint + cool 240"
  checkpoint
  sleep 240
done
checkpoint
[ "$DONE" = 1 ] || { echo "still incomplete; will resume next invocation"; exit 0; }

echo "=== rebuild master + merge legs ==="
python - <<'PY'
import pandas as pd, os
p='/tmp/mtf_psar_rank_full.csv'
if os.path.exists(p):
    df=pd.read_csv(p).drop_duplicates('ticker')
    keep=lambda t:(('.' in str(t)) or not (len(str(t))==5 and str(t)[-1] in ('F','Y')))
    df[df.ticker.map(keep)].to_csv('/tmp/mtf_psar_rank_full_clean.csv', index=False)
    print("cleaned PSAR:", int(df.ticker.map(keep).sum()))
PY
python master_full_universe.py
python - <<'PY'
import pandas as pd, os
m = pd.read_csv('/tmp/master_full_universe.csv', low_memory=False)
for path in ('/tmp/leledc_rank.csv','/tmp/volume_rank.csv'):
    if not os.path.exists(path): continue
    leg = pd.read_csv(path).drop_duplicates('ticker')
    cols = [c for c in leg.columns if c != 'region']
    m = m.drop(columns=[c for c in cols if c in m.columns and c!='ticker'], errors='ignore')
    m = m.merge(leg[cols], on='ticker', how='left')
if 'weekly_rank' in m.columns and 'V' in m.columns:
    m['V_combined'] = 0.70*m['weekly_rank'] + 0.30*m['V']
m.to_csv('/tmp/master_full_universe.csv', index=False)
for tf,tier in (('w','vspike_w_tier'),('m','vspike_m_tier')):
    if tier in m.columns:
        s=m[tier].fillna(0); print(f"{tf} spikes: >=2x {int((s>=2).sum())}  >=3x {int((s>=3).sum())}  >=5x {int((s>=5).sum())}")
if 'vspike_wm' in m.columns:
    print("both-timeframe (vspike_wm):", int(m['vspike_wm'].fillna(False).astype(bool).sum()))
PY

echo "=== rebuild baskets + workbook + persist ==="
python build_baskets.py || echo WARN baskets
python build_workbook.py || echo WARN workbook
python persist_results.py || echo WARN persist
echo "VSPIKE-POPULATE-DONE"
