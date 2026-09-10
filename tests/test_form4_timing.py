"""Regression tests for the Form 4 filing-time classifier.

The hypothesis under test: off-hours / Friday-evening open-market insider
buys are quiet accumulators (follow); market-hours buys are price support
(fade). These tests pin the wall-clock -> bucket classification and the
UTC->ET conversion the signal depends on.
"""
from __future__ import annotations
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
sys.path.insert(0, str(Path(__file__).parent.parent))
import form4_timing as ft

ET = ZoneInfo("America/New_York")


def at(c, l=""):
    if not c:
        raise AssertionError(f"FAIL {l}")


def et(y, mo, d, h, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=ET)


# --- market hours: weekday 09:30-16:00 ET ---
at(ft.classify(et(2026, 5, 15, 10, 5))[0] == "MARKET_HOURS", "10:05 Fri = market")
at(ft.classify(et(2026, 5, 13, 9, 30))[0] == "MARKET_HOURS", "09:30 exactly = market")
at(ft.classify(et(2026, 5, 13, 15, 59))[0] == "MARKET_HOURS", "15:59 = market")

# --- after-hours: weekday outside 09:30-16:00 ---
at(ft.classify(et(2026, 5, 13, 16, 0))[0] == "AFTER_HOURS", "16:00 = after (close)")
at(ft.classify(et(2026, 5, 13, 21, 0))[0] == "AFTER_HOURS", "9pm Wed = after")
at(ft.classify(et(2026, 5, 13, 7, 0))[0] == "AFTER_HOURS", "7am pre-market = after")

# --- Friday evening flag: only Friday >= 16:00 ---
b, fri = ft.classify(et(2026, 5, 15, 21, 0))       # Fri 9pm
at(b == "AFTER_HOURS" and fri, "Fri 9pm = after-hours + friday_evening")
b, fri = ft.classify(et(2026, 5, 15, 10, 0))       # Fri 10am
at(b == "MARKET_HOURS" and not fri, "Fri 10am = market, not fri-eve")
b, fri = ft.classify(et(2026, 5, 13, 21, 0))       # Wed 9pm
at(b == "AFTER_HOURS" and not fri, "Wed 9pm = after, not fri-eve")

# --- weekend ---
at(ft.classify(et(2026, 5, 16, 12, 0))[0] == "WEEKEND", "Sat noon = weekend")
at(ft.classify(et(2026, 5, 17, 12, 0))[0] == "WEEKEND", "Sun noon = weekend")

# --- UTC -> ET conversion (EDT = UTC-4 in May): 14:05Z -> 10:05 ET market ---
dt_utc = datetime(2026, 5, 15, 14, 5, tzinfo=timezone.utc)
at(ft.classify(dt_utc.astimezone(ET))[0] == "MARKET_HOURS",
   "14:05Z May -> 10:05 EDT market hours")
# 23:00Z Friday May -> 19:00 EDT Friday -> friday evening
dt_utc = datetime(2026, 5, 15, 23, 0, tzinfo=timezone.utc)
b, fri = ft.classify(dt_utc.astimezone(ET))
at(b == "AFTER_HOURS" and fri, "23:00Z Fri May -> 7pm ET friday evening")

print("test_form4_timing: all assertions passed")
