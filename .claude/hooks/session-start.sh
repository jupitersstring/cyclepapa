#!/bin/bash
# Auto-launch the EDGAR harvest watchdog on session start.
#
# This container is reclaimed during inactivity (typical of Claude Code
# on the web). Anything we want to keep running needs to be restarted
# at the start of every session. The per-CIK cache + edgar_full_state.json
# survive in the cloned repo, so resume is fast — we just need to make
# sure the process is alive whenever a session is.
#
# Hook contract:
#   - Return fast (we detach the watchdog and exit immediately)
#   - Idempotent (don't double-spawn if a watchdog is already alive)
#   - Web-only (no point launching on local sessions where users run it
#     themselves)
set -uo pipefail

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-/home/user/cyclepapa}"
cd "$PROJECT_DIR" || exit 0

# Only relevant in the remote (web) environment
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
    exit 0
fi

# The web container is re-cloned fresh on restart, so Python deps are
# gone every session. Reinstall (fast when already present) before any
# driver runs — otherwise the pipeline's pandas/openpyxl/etc. calls fail.
if [ -f "$PROJECT_DIR/requirements.txt" ] \
   && ! python3 -c "import pandas, openpyxl, financedatabase" > /dev/null 2>&1; then
    echo "session-start-hook: installing Python deps..." >&2
    pip3 install -q -r "$PROJECT_DIR/requirements.txt" > "$PROJECT_DIR/pip_install.log" 2>&1 \
        && echo "session-start-hook: deps installed" >&2 \
        || echo "session-start-hook: dep install had errors (see pip_install.log)" >&2
fi

# ---------------------------------------------------------------------
# Enrichment drivers launch FIRST, before the harvest idempotency check
# below — that check exits early when the (now-complete) EDGAR harvest
# watchdog is alive, which would otherwise starve these of a relaunch.
# ---------------------------------------------------------------------
# Deep multi-year enrichment of the FDB-expansion names takes priority
# while it's in flight. It's the SINGLE Yahoo hitter during that phase
# (statements + quote + chart per name) — running the other enrichers
# alongside just starves everything on the shared-IP throttle. Guarded
# by .deep_rendered; once the expansion is fully enriched + rendered the
# hook falls through to the standard ticker_yf / chart enrichers.
if [ -f "$PROJECT_DIR/run_deep_forever.sh" ] \
   && [ ! -f "$PROJECT_DIR/.deep_rendered" ] \
   && ! pgrep -f "ticker_yf_deep.py" > /dev/null 2>&1 \
   && ! pgrep -f "run_deep_forever.sh" > /dev/null 2>&1; then
    chmod +x "$PROJECT_DIR/run_deep_forever.sh" 2>/dev/null || true
    setsid nohup bash "$PROJECT_DIR/run_deep_forever.sh" \
        > "$PROJECT_DIR/deep_driver.log" 2>&1 < /dev/null &
    disown $!
    echo "session-start-hook: launched deep enrichment driver (PID $!)" >&2
elif [ -f "$PROJECT_DIR/.deep_rendered" ] \
     && [ -f "$PROJECT_DIR/run_otc_deep.sh" ] \
     && [ ! -f "$PROJECT_DIR/.otc_rendered" ] \
     && ! pgrep -f "ticker_yf_deep.py" > /dev/null 2>&1 \
     && ! pgrep -f "run_otc_deep.sh" > /dev/null 2>&1; then
    # OTC broad-universe deep enrichment is the SOLE Yahoo hitter until it
    # finishes (.otc_rendered). Running the price-refresh enrichers alongside
    # it starves everything on the shared-IP throttle and kills the deep run.
    chmod +x "$PROJECT_DIR/run_otc_deep.sh" 2>/dev/null || true
    setsid nohup bash "$PROJECT_DIR/run_otc_deep.sh" \
        > "$PROJECT_DIR/otc_driver.log" 2>&1 < /dev/null &
    disown $!
    echo "session-start-hook: launched OTC deep enrichment driver (PID $!)" >&2
elif [ -f "$PROJECT_DIR/.deep_rendered" ] \
     && [ -f "$PROJECT_DIR/.otc_rendered" ] \
     && [ -f "$PROJECT_DIR/run_rest_deep.sh" ] \
     && [ ! -f "$PROJECT_DIR/.rest_rendered" ] \
     && ! pgrep -f "ticker_yf_deep.py" > /dev/null 2>&1 \
     && ! pgrep -f "run_rest_deep.sh" > /dev/null 2>&1; then
    # "The rest": deep Tier-B enrichment of the main-universe names that still
    # lack the deep schema (~26.6k investable, highest-asymmetry first). SOLE
    # Yahoo hitter until it finishes (.rest_rendered); the deep fetch also
    # captures Tier-A valuations, so it subsumes the price-refresh enrichers
    # for the names it covers. Running them alongside starves the throttle.
    chmod +x "$PROJECT_DIR/run_rest_deep.sh" 2>/dev/null || true
    setsid nohup bash "$PROJECT_DIR/run_rest_deep.sh" \
        > "$PROJECT_DIR/rest_driver.log" 2>&1 < /dev/null &
    disown $!
    echo "session-start-hook: launched rest deep enrichment driver (PID $!)" >&2
elif [ -f "$PROJECT_DIR/.deep_rendered" ] \
     && [ -f "$PROJECT_DIR/.rest_rendered" ] \
     && [ -f "$PROJECT_DIR/run_lynch_enrich.sh" ] \
     && [ ! -f "$PROJECT_DIR/.lynch_done" ] \
     && ! pgrep -f "lynch_reward_enrich.py" > /dev/null 2>&1 \
     && ! pgrep -f "run_lynch_enrich.sh" > /dev/null 2>&1; then
    # Lynch "years of progress rewarded in a year" price-series enrichment
    # (10y weekly OHLC -> W/M/Q S&R + volatility asymmetry + long ROC). SOLE
    # Yahoo hitter until .lynch_done; the price-refresh enrichers stay paused.
    chmod +x "$PROJECT_DIR/run_lynch_enrich.sh" 2>/dev/null || true
    setsid nohup bash "$PROJECT_DIR/run_lynch_enrich.sh" \
        > "$PROJECT_DIR/lynch_driver.log" 2>&1 < /dev/null &
    disown $!
    echo "session-start-hook: launched lynch enrichment driver (PID $!)" >&2
elif [ -f "$PROJECT_DIR/.deep_rendered" ] && [ -f "$PROJECT_DIR/.rest_rendered" ] \
     && [ -f "$PROJECT_DIR/.lynch_done" ]; then
    # Deep + OTC + rest + lynch phases done — resume the standard fundamentals + chart enrichers.
    if [ -f "$PROJECT_DIR/run_ticker_yf_forever.sh" ] \
       && ! pgrep -f "ticker_yf.py" > /dev/null 2>&1 \
       && ! pgrep -f "run_ticker_yf_forever.sh" > /dev/null 2>&1; then
        chmod +x "$PROJECT_DIR/run_ticker_yf_forever.sh" 2>/dev/null || true
        setsid nohup bash "$PROJECT_DIR/run_ticker_yf_forever.sh" \
            > "$PROJECT_DIR/ticker_yf_driver.log" 2>&1 < /dev/null &
        disown $!
        echo "session-start-hook: launched ticker_yf driver (PID $!)" >&2
    fi
    if [ -f "$PROJECT_DIR/yahoo_chart_fill.py" ] \
       && ! pgrep -f "yahoo_chart_fill.py" > /dev/null 2>&1; then
        setsid nohup python3 "$PROJECT_DIR/yahoo_chart_fill.py" --workers 8 \
            > "$PROJECT_DIR/yahoo_chart_fill.log" 2>&1 < /dev/null &
        disown $!
        echo "session-start-hook: resumed yahoo_chart_fill (PID $!)" >&2
    fi
fi

# Idempotent: if a watchdog or harvest python is already running, do nothing.
# pgrep -f matches against full command line.
if pgrep -f "run_harvest_forever.sh" > /dev/null 2>&1 \
   || pgrep -f "edgar_full_harvest.py" > /dev/null 2>&1; then
    echo "session-start-hook: harvest already running, skipping spawn" >&2
    exit 0
fi

# Watchdog must be executable
if [ ! -x "$PROJECT_DIR/run_harvest_forever.sh" ]; then
    chmod +x "$PROJECT_DIR/run_harvest_forever.sh" 2>/dev/null || true
fi

# Detach: new session, redirect all I/O. The watchdog itself is a small
# bash script that re-exec's the python harvest if it dies.
setsid nohup "$PROJECT_DIR/run_harvest_forever.sh" \
    > "$PROJECT_DIR/harvest_watchdog.log" 2>&1 < /dev/null &
disown $!
echo "session-start-hook: launched harvest watchdog (PID $!) in background" >&2

exit 0
