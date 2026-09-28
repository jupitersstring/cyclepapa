"""Paths and study parameters."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "crypto_multibaggers"
CACHE_DIR = DATA_DIR / "cache"          # raw API pulls (git-ignored)
ANALYSIS_DIR = DATA_DIR / "analysis"    # small CSV outputs (committed)

START_DATE = "2013-01-01"

# Windows in calendar days relative to day 0 (crypto trades every day).
BASELINE = (-180, -61)      # own-history baseline for volume/volatility/liquidity
MIN_BASELINE_OBS = 60
WIN_L = (-60, -21)          # "long" pre-event window
WIN_M = (-20, -6)
WIN_S = (-5, -1)            # final week before day 0
WIN_A = (-60, -1)           # whole pre-event window
CUSUM_LEN = 120
POST = 180                  # outcome horizon (multiple measured over days 1..180)

# Trigger ("re-rating") definition
JUMP_Z = 3.0                # day-0 abnormal return, in baseline sigmas
JUMP_MIN_RET = 0.15         # and at least +15% raw on day 0
REFRACTORY = 60             # no other trigger for the same token in the prior 60 days

# Multibagger tiers on the 180-day forward multiple (5-day median close vs day -1 close)
TIERS = [(10.0, "10x+"), (5.0, "5-10x"), (3.0, "3-5x"), (2.0, "2-3x")]

# Placebo design
N_PLACEBO = 2
PLACEBO_EXCLUSION = 60      # placebo token has no trigger within +/- this many days
