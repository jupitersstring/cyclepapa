"""
Backtest harness: turn a position series in {-1, 0, +1} into an equity
curve and standard metrics (CAGR, Sharpe, max DD, win rate, PF, n_trades,
avg hold). Trades execute at the NEXT bar's open with round-trip
transaction costs in basis points.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd


@dataclass
class BacktestMetrics:
    cagr: float
    sharpe: float
    max_dd: float
    win_rate: float
    profit_factor: float
    n_trades: int
    avg_hold_bars: float
    final_equity: float
    total_return: float
    exposure: float        # fraction of bars in market


def _bars_per_year(idx: pd.DatetimeIndex) -> float:
    if len(idx) < 2:
        return 252.0
    dt = (idx[-1] - idx[0]).total_seconds()
    if dt <= 0:
        return 252.0
    bars_per_sec = (len(idx) - 1) / dt
    return bars_per_sec * 365.25 * 24 * 3600


def run_backtest(df: pd.DataFrame, position: pd.Series, *,
                  tx_cost_bps: float = 25.0,
                  long_only: bool = False) -> tuple[BacktestMetrics, pd.Series, pd.DataFrame]:
    """
    df: OHLCV with at least 'open' and 'close'.
    position: -1/0/+1 series aligned to df.index. The position at bar t is
              assumed *known* at bar t close (signal generators don't peek).
    Execution: change in position from bar t-1 to t executes at bar t open.
    Returns (metrics, equity_curve, trades_df).
    """
    if long_only:
        position = position.clip(lower=0)
    open_ = df["open"].astype(float)
    close = df["close"].astype(float)
    pos = position.reindex(df.index).fillna(0).astype(int)
    pos_prev = pos.shift(1).fillna(0).astype(int)
    # Returns from holding the prior bar's position over [open_t -> close_t]
    bar_ret = (close / open_ - 1).fillna(0)
    # Position effective during bar t is the value we set at bar t-1's close,
    # so we use pos_prev for the bar's return.
    strat_ret = pos_prev * bar_ret
    # Transaction cost charged on each unit of position turnover at bar t open
    turnover = (pos - pos_prev).abs()
    tx_cost = turnover * (tx_cost_bps / 10000.0)
    strat_ret = strat_ret - tx_cost

    equity = (1 + strat_ret).cumprod()
    final_equity = float(equity.iloc[-1])
    total_return = final_equity - 1.0

    bpy = _bars_per_year(df.index)
    n_years = max(1e-9, len(df) / bpy)
    cagr = float(final_equity ** (1 / n_years) - 1) if final_equity > 0 else -1.0
    ret_std = strat_ret.std()
    sharpe = float(strat_ret.mean() / ret_std * np.sqrt(bpy)) if ret_std > 0 else 0.0

    peak = equity.cummax()
    dd = equity / peak - 1
    max_dd = float(dd.min())

    # Trades = blocks of constant non-zero position
    trades = []
    cur_dir = 0
    entry_idx: Optional[int] = None
    entry_px: Optional[float] = None
    for i in range(len(df)):
        new_dir = int(pos.iloc[i])
        if new_dir != cur_dir:
            if cur_dir != 0 and entry_idx is not None:
                exit_px = float(open_.iloc[i])
                if entry_px == 0 or not np.isfinite(entry_px) or not np.isfinite(exit_px):
                    pnl_pct = 0.0
                else:
                    pnl_pct = (exit_px / entry_px - 1) * cur_dir
                trades.append({
                    "entry_bar": entry_idx, "exit_bar": i,
                    "direction": cur_dir,
                    "entry_px": entry_px, "exit_px": exit_px,
                    "hold_bars": i - entry_idx,
                    "pnl_pct": pnl_pct,
                })
            if new_dir != 0:
                entry_idx = i
                entry_px = float(open_.iloc[i])
            cur_dir = new_dir
    if cur_dir != 0 and entry_idx is not None:
        exit_px = float(close.iloc[-1])
        if entry_px == 0 or not np.isfinite(entry_px) or not np.isfinite(exit_px):
            pnl_pct = 0.0
        else:
            pnl_pct = (exit_px / entry_px - 1) * cur_dir
        trades.append({
            "entry_bar": entry_idx, "exit_bar": len(df) - 1,
            "direction": cur_dir,
            "entry_px": entry_px, "exit_px": exit_px,
            "hold_bars": len(df) - 1 - entry_idx,
            "pnl_pct": pnl_pct,
        })
    trades_df = pd.DataFrame(trades)

    if len(trades_df) > 0:
        wins = trades_df["pnl_pct"] > 0
        win_rate = float(wins.mean())
        gross_win = float(trades_df.loc[wins, "pnl_pct"].sum())
        gross_loss = float(-trades_df.loc[~wins, "pnl_pct"].sum())
        pf = gross_win / gross_loss if gross_loss > 0 else float("inf") if gross_win > 0 else 0.0
        avg_hold = float(trades_df["hold_bars"].mean())
    else:
        win_rate = pf = avg_hold = 0.0
    exposure = float((pos != 0).mean())

    metrics = BacktestMetrics(
        cagr=cagr, sharpe=sharpe, max_dd=max_dd,
        win_rate=win_rate, profit_factor=pf,
        n_trades=len(trades_df), avg_hold_bars=avg_hold,
        final_equity=final_equity, total_return=total_return,
        exposure=exposure,
    )
    return metrics, equity, trades_df


def buy_and_hold(df: pd.DataFrame, tx_cost_bps: float = 25.0) -> BacktestMetrics:
    """Reference: buy-and-hold from first bar to last."""
    pos = pd.Series(1, index=df.index, dtype=int)
    m, _, _ = run_backtest(df, pos, tx_cost_bps=tx_cost_bps)
    return m
