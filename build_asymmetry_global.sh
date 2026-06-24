#!/usr/bin/env bash
# Rebuild asymmetry_global.csv from every per-country yartseva snapshot.
# Re-run after any new country scan completes.

set -u
VENV=/usr/local/bin/python3

# (filename, country-code) pairs.  Code = ISO-2 used downstream as `src`.
declare -A SRC=(
    # North America
    [us_nano_micro_small_yartseva.csv]=US
    [us_largecap_yartseva.csv]=US
    [us_unc_yartseva.csv]=US
    [us_edgar_yartseva.csv]=US
    [ca_yartseva.csv]=CA
    # UK
    [uk_yartseva.csv]=UK
    [uk_largecap_yartseva.csv]=UK
    [uk_unc_yartseva.csv]=UK
    [uk_aim_missing_yartseva.csv]=UK
    [uk_aim_extra_yartseva.csv]=UK
    # EU Core
    [italian_yartseva.csv]=IT
    [it_largecap_yartseva.csv]=IT
    [it_unc_yartseva.csv]=IT
    [de_yartseva.csv]=DE
    [de_largecap_yartseva.csv]=DE
    [de_unc_yartseva.csv]=DE
    [fr_yartseva.csv]=FR
    [fr_largecap_yartseva.csv]=FR
    [fr_unc_yartseva.csv]=FR
    [nl_yartseva.csv]=NL
    [nl_largecap_yartseva.csv]=NL
    [be_yartseva.csv]=BE
    [be_largecap_yartseva.csv]=BE
    [be_unc_yartseva.csv]=BE
    [ch_yartseva.csv]=CH
    [ch_largecap_yartseva.csv]=CH
    [ie_yartseva.csv]=IE
    [ie_largecap_yartseva.csv]=IE
    [at_yartseva.csv]=AT
    [at_largecap_yartseva.csv]=AT
    # EU Nordic
    [se_yartseva.csv]=SE
    [se_largecap_yartseva.csv]=SE
    [no_yartseva.csv]=NO
    [no_largecap_yartseva.csv]=NO
    [no_unc_yartseva.csv]=NO
    [dk_yartseva.csv]=DK
    [dk_largecap_yartseva.csv]=DK
    [fi_yartseva.csv]=FI
    [fi_largecap_yartseva.csv]=FI
    # EU Periphery
    [es_yartseva.csv]=ES
    [es_largecap_yartseva.csv]=ES
    [es_unc_yartseva.csv]=ES
    [pt_yartseva.csv]=PT
    [pt_largecap_yartseva.csv]=PT
    [gr_yartseva.csv]=GR
    [gr_largecap_yartseva.csv]=GR
    # EU CEE + Baltics
    [cz_yartseva.csv]=CZ
    [cz_largecap_yartseva.csv]=CZ
    [hu_yartseva.csv]=HU
    [hu_largecap_yartseva.csv]=HU
    [ee_yartseva.csv]=EE
    [ee_largecap_yartseva.csv]=EE
    [lv_yartseva.csv]=LV
    [lt_yartseva.csv]=LT
    # NEW European fills
    [pl_yartseva.csv]=PL
    [pl_largecap_yartseva.csv]=PL
    [is_yartseva.csv]=IS
    [is_largecap_yartseva.csv]=IS
    # Asia-Pacific
    [jp_yartseva.csv]=JP
    [kr_yartseva.csv]=KR
    [hk_yartseva.csv]=HK
    [tw_yartseva.csv]=TW
    [sg_yartseva.csv]=SG
    [au_yartseva.csv]=AU
    [nz_yartseva.csv]=NZ
    [in_yartseva.csv]=IN
    [idn_yartseva.csv]=ID
    [th_yartseva.csv]=TH
    # MEA + LatAm
    [tr_yartseva.csv]=TR
    [za_yartseva.csv]=ZA
    [il_yartseva.csv]=IL
    [br_yartseva.csv]=BR
    [mx_yartseva.csv]=MX
    # NEW phase-2 expansion: LatAm + ASEAN + MEA
    [sa_yartseva.csv]=SA
    [ar_yartseva.csv]=AR
    [cl_yartseva.csv]=CL
    [my_yartseva.csv]=MY
    # NEW gap-fill uncategorized scans
    [us_unc_deep_yartseva.csv]=US
    [at_unc_yartseva.csv]=AT
    [ch_unc_yartseva.csv]=CH
    [se_unc_yartseva.csv]=SE
    [fi_unc_yartseva.csv]=FI
    [pt_unc_yartseva.csv]=PT
    [gr_unc_yartseva.csv]=GR
    [ie_unc_yartseva.csv]=IE
    [pl_unc_yartseva.csv]=PL
    [cz_unc_yartseva.csv]=CZ
    [hu_unc_yartseva.csv]=HU
    [ee_unc_yartseva.csv]=EE
    [lv_unc_yartseva.csv]=LV
    [lt_unc_yartseva.csv]=LT
    # Widen-phase: China + Romania
    [cn_yartseva.csv]=CN
    [ro_yartseva.csv]=RO

    # NEW US+EU gap-fill from --tickers-file scrape (171 net new names)
    [at_gap_yartseva.csv]=AT
    [be_gap_yartseva.csv]=BE
    [ie_gap_yartseva.csv]=IE
    [nl_gap_yartseva.csv]=NL
    [ch_gap_yartseva.csv]=CH
    [it_gap_yartseva.csv]=IT
    [fr_gap_yartseva.csv]=FR
    [de_gap_yartseva.csv]=DE
    [uk_gap_yartseva.csv]=UK
    [us_gap_yartseva.csv]=US
    [uk_gap2_yartseva.csv]=UK
    [us_gap2_yartseva.csv]=US
)

ARGS=()
for f in "${!SRC[@]}"; do
    if [ -s "$f" ]; then
        ARGS+=("${f}:${SRC[$f]}")
    fi
done

echo "merging ${#ARGS[@]} CSVs"
"$VENV" asymmetry_rank.py \
    --csvs "${ARGS[@]}" \
    --pew pew_global.csv \
    --out asymmetry_global.csv \
    --top 30000 \
    --min-upside 0.15 \
    --min-downside-floor 0.00 \
    --min-mcap 5000000
