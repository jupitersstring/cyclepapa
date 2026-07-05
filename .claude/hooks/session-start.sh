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
elif [ -f "$PROJECT_DIR/.deep_rendered" ]; then
    # Deep phase done — resume the standard fundamentals + chart enrichers.
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

exit 0
