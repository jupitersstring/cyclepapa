"""User-chosen universal gates for the country books.

    --gate "fcf_yield>5%"            FCF yield above 5%
    --gate "pb<1" --gate "p_e>0"     several gates are AND-combined
    --gate "ev_ebit<=8" --gate "net_cash_pct_mcap>=0.2"

Syntax: <column><op><value>, op one of > >= < <= == !=. A trailing % divides
the value by 100 (ratios such as fcf_yield / dividend_yield / roce are stored
as fractions: 0.05 = 5%). Any numeric column of the book's data works (master,
archetype tags, FMP overlays, spirit scores ...).

A name with a MISSING value fails the gate (it is not known to pass). As with
the P/B book, a gated universe also drops data-quality-flagged rows and
non-common lines (preferreds / warrants), whose ratios are the ones most often
corrupt enough to pass a value gate by accident.
"""
from __future__ import annotations

import operator
import re

import numpy as np
import pandas as pd

_OPS = {'>=': operator.ge, '<=': operator.le, '==': operator.eq, '!=': operator.ne,
        '>': operator.gt, '<': operator.lt}
_RX = re.compile(r'^\s*([A-Za-z_][A-Za-z0-9_]*)\s*(>=|<=|==|!=|>|<)\s*(-?[0-9.eE+-]+)\s*(%?)\s*$')


def parse_gate(text: str):
    m = _RX.match(text)
    if not m:
        raise ValueError(f'bad --gate {text!r}: expected e.g. "fcf_yield>5%" or "pb<1"')
    col, op, val, pct = m.groups()
    v = float(val) / (100.0 if pct else 1.0)
    return col, op, v


def gate_label(gates: list[str]) -> str:
    out = []
    for g in gates:
        col, op, v = parse_gate(g)
        out.append(f'{col} {op} {v:g}')
    return ' AND '.join(out)


def add_gate_arg(ap) -> None:
    ap.add_argument('--gate', action='append', default=[],
                    help='universal gate applied to the whole universe before '
                         'ranking, e.g. --gate "fcf_yield>5%%" (repeatable; '
                         'AND-combined; missing values fail). See universe_gate.py.')


def apply_gates(df: pd.DataFrame, gates: list[str], verbose: bool = True) -> pd.DataFrame:
    if not gates:
        return df
    import sys
    keep = pd.Series(True, index=df.index)
    for g in gates:
        col, op, v = parse_gate(g)
        if col not in df.columns:
            raise SystemExit(f'--gate {g!r}: column {col!r} not in the book data')
        x = pd.to_numeric(df[col], errors='coerce')
        keep &= _OPS[op](x, v).fillna(False) & x.notna()
        if verbose:
            print(f'  gate {col} {op} {v:g}: {int(keep.sum()):,} names pass so far', file=sys.stderr)
    dq = pd.to_numeric(df.get('data_quality_flag', pd.Series(0, index=df.index)), errors='coerce').fillna(0)
    nc = pd.to_numeric(df.get('non_common_flag', pd.Series(0, index=df.index)), errors='coerce').fillna(0)
    keep &= (dq == 0) & (nc == 0)
    if verbose:
        print(f'  universal gate [{gate_label(gates)}] (+ clean data, common only): '
              f'{int(keep.sum()):,} names kept', file=sys.stderr)
    return df[keep].copy()
