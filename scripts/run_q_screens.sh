#!/bin/bash
# Run Qullamaggie + EP screeners across all existing universes.
# Serial — uses bulk yf.download chunks, so single-process is fine.
set -e
cd "$(dirname "$0")/.."

mkdir -p data/qmaggie data/ep

declare -a MARKETS=(
    us uk japan germany france italy spain netherlands belgium switzerland
    sweden norway finland denmark austria ireland portugal greece
    canada australia nz hk korea taiwan singapore thailand indonesia
    israel brazil mexico chile argentina southafrica turkey china
)

for mkt in "${MARKETS[@]}"; do
    for cap_path in "data/universes/uni_${mkt}.csv" "data/universes/large/uni_${mkt}_lg.csv"; do
        [ -f "$cap_path" ] || continue
        n=$(($(wc -l < "$cap_path") - 1))
        [ "$n" -lt 10 ] && continue
        cap_tag=$([ "${cap_path}" != "${cap_path%_lg.csv}" ] && echo "_lg" || echo "")

        out_q="data/qmaggie/qmaggie_${mkt}${cap_tag}.csv"
        if [ ! -f "$out_q" ] || [ "$(stat -c%s "$out_q" 2>/dev/null)" -lt 500 ]; then
            echo "============ [Q] $mkt$cap_tag ($n) ============"
            python3 screeners/qullamaggie_screen.py --universe "$cap_path" --out "$out_q" \
                > "/tmp/log_q_${mkt}${cap_tag}.txt" 2>&1 || true
        fi

        out_e="data/ep/ep_${mkt}${cap_tag}.csv"
        if [ ! -f "$out_e" ] || [ "$(stat -c%s "$out_e" 2>/dev/null)" -lt 500 ]; then
            echo "============ [EP] $mkt$cap_tag ($n) ============"
            python3 screeners/episodic_pivot_screen.py --universe "$cap_path" --out "$out_e" \
                > "/tmp/log_ep_${mkt}${cap_tag}.txt" 2>&1 || true
        fi
    done
    sleep 20
done
echo "[q_screens] DONE all markets"
