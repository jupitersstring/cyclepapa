#!/usr/bin/env python3
"""
build_ledger_html.py — render the listed-equity reorganization watchlist as
a *Times Lattice* broadsheet (per docs STYLE_GUIDE.md, times-lattice-compact).

A 19th-century financial broadsheet rebuilt for the screen: Times New Roman
at one size, black ink on white, 1px hairlines only, a vertically-stretched
nameplate over a fleur-de-lis divider, and just two accent inks — lapis
(good) and crimson (bad). Reads the durable output/listed_equity_watchlist.md
so the ledger regenerates whenever the screen reruns.

Output: output/listed_equity_ledger.html

Usage:
    python -m src.build_ledger_html
"""

from __future__ import annotations

import html
import re
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC_MD = REPO / "output" / "listed_equity_watchlist.md"
OUT = REPO / "output" / "listed_equity_ledger.html"


def _tables(md: str) -> list[tuple[list[str], list[list[str]]]]:
    out, hdr, rows = [], None, []
    for line in md.splitlines():
        s = line.strip()
        is_row = s.startswith("|") and s.endswith("|")
        if is_row and set(s) <= set("|-: "):
            continue
        if is_row:
            cells = [c.strip() for c in s.strip("|").split("|")]
            if hdr is None:
                hdr = cells
            else:
                rows.append(cells)
        else:
            if hdr is not None:
                out.append((hdr, rows)); hdr, rows = None, []
    if hdr is not None:
        out.append((hdr, rows))
    return out


def _stat(md: str, label: str) -> str:
    m = re.search(re.escape(label) + r".{0,40}?\*\*(\d+)\*\*", md)
    return m.group(1) if m else "—"


# --- geometry marks (font-independent, per guide §1.6) --------------------

FLEUR = (
    '<svg class="fleur" viewBox="0 0 24 32" width="15" height="20" '
    'aria-hidden="true"><path fill="var(--ink)" d="M12 0c-1.6 2.3-1.2 4.6 0 '
    '6.2 1.2-1.6 1.6-3.9 0-6.2zM12 7.4c-2.1 1.7-2.4 4.2-1.3 6.1-2.3-1.9-5.6'
    '-1.3-6.4 1.3-.8 2.6 1 4.9 3.4 5 .9 0 1.8-.3 2.5-.9-1 1.9-.6 4.3 1.3 '
    '5.6-.7.2-1.2.8-1.2 1.6 0 .9.7 1.6 1.6 1.7v3.3h-2.2v1.3h2.2V32h1.4v-3.6'
    'h2.2v-1.3h-2.2v-3.3c.9-.1 1.6-.8 1.6-1.7 0-.8-.5-1.4-1.2-1.6 1.9-1.3 '
    '2.3-3.7 1.3-5.6.7.6 1.6.9 2.5.9 2.4-.1 4.2-2.4 3.4-5-.8-2.6-4.1-3.2-6.4'
    '-1.3 1.1-1.9.8-4.4-1.3-6.1z"/></svg>')

STAR = ('<svg class="star" viewBox="-10 -10 20 20" width="9" height="9" '
        'aria-hidden="true"><path fill="var(--lapis)" d="M0-9 2-2 9 0 2 2 0 9'
        ' -2 2 -9 0 -2-2Z"/></svg>')


def dot(mark: str) -> str:
    if mark == "●":                     # ●  question met
        return '<span class="pip on"></span>'
    return '<span class="pip off"></span>'   # ·  not met


def esc(s: str) -> str:
    return html.escape(s or "")


CSS = """
:root{
  --ink:#000; --paper:#fff; --muted:#3f3f3f;
  --lapis:#061933; --crimson:#7a0019; --neutral:#8a8a8a;
  --gap-xs:.236rem; --gap-sm:.382rem; --gap-md:.618rem;
  --gap-lg:1rem; --gap-xl:1.618rem;
}
*{box-sizing:border-box;}
html{font-size:13.5px;}
body{margin:0;background:#e9e7e2;color:var(--ink);
  font-family:"Times New Roman",Times,"Liberation Serif",serif;
  line-height:1.16;font-variant-numeric:tabular-nums;
  -webkit-font-smoothing:antialiased;}
.page{width:min(74rem,100vw - 1rem);margin:.5rem auto;background:var(--paper);
  border:1px solid var(--ink);padding:var(--gap-md) .9rem;}
h1,h2,p,td,th,a,li,div,span{font-size:1rem;}
a{color:var(--ink);text-decoration:underline;text-underline-offset:.08em;
  text-decoration-thickness:1px;}
.tnum{font-variant-numeric:tabular-nums;}

/* masthead */
.masthead{display:grid;grid-template-columns:1fr auto;align-items:end;
  gap:var(--gap-md);padding-bottom:var(--gap-sm);border-bottom:1px solid var(--ink);}
.kicker{text-transform:uppercase;font-weight:700;letter-spacing:.06em;}
.masthead h1{margin:.15rem 0 0;line-height:1;}
.masthead h1 strong{display:inline-block;transform:scaleY(1.5);
  transform-origin:0 82%;text-transform:uppercase;font-weight:700;
  letter-spacing:.02em;}
.mast-sub{text-transform:uppercase;font-weight:700;letter-spacing:.10em;
  margin-top:.5rem;}
.mast-right{text-align:right;color:var(--muted);line-height:1.28;}
.mast-right b{color:var(--ink);font-weight:700;}

/* fleur divider */
.divider{display:flex;align-items:center;gap:.55rem;
  padding:.34rem 0 var(--gap-sm);}
.divider .rule{flex:1;height:1px;background:var(--ink);}

/* snapshot strip */
.snapshot{display:grid;grid-template-columns:repeat(5,1fr);
  gap:var(--gap-sm);padding-bottom:var(--gap-sm);border-bottom:1px solid var(--ink);}
.snapshot .cell{display:flex;flex-direction:column;gap:.05rem;}
.snapshot .v{font-weight:700;font-size:1rem;}
.snapshot .l{text-transform:uppercase;letter-spacing:.05em;color:var(--muted);}
.snapshot .cell + .cell{padding-left:var(--gap-sm);border-left:1px solid var(--neutral);}

/* panels */
.panel{margin-top:var(--gap-lg);border:1px solid var(--ink);}
.panel-title{display:flex;justify-content:space-between;align-items:baseline;
  text-transform:uppercase;font-weight:700;letter-spacing:.04em;
  padding:var(--gap-xs) var(--gap-sm);border-bottom:1px solid var(--ink);}
.panel-title .legend{font-weight:400;text-transform:none;letter-spacing:0;
  color:var(--muted);}

/* ledger table */
table{width:100%;border-collapse:collapse;}
thead th{text-transform:uppercase;font-weight:700;letter-spacing:.02em;
  text-align:left;padding:var(--gap-xs) var(--gap-xs);
  border-bottom:1px solid var(--ink);white-space:nowrap;}
tbody td{padding:.18rem var(--gap-xs);border-bottom:1px solid var(--ink);
  vertical-align:baseline;}
tbody tr:last-child td{border-bottom:none;}
th.n,td.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap;}
th.c,td.c{text-align:center;}
.tk{font-weight:700;white-space:nowrap;}
.emd{color:var(--muted);white-space:nowrap;}
.emd.live{color:var(--lapis);font-weight:700;}
.liq-ok{color:var(--ink);}
.liq-thin{color:var(--muted);}
.liq-micro{color:var(--crimson);}
.tag{color:var(--ink);}
.tag.none{color:var(--neutral);}
.conf-y{color:var(--ink);font-weight:700;}
.conf-n{color:var(--muted);}
.prime td{background:rgba(6,25,51,.07);}
.arch-lapis{color:var(--lapis);font-weight:700;}

/* question pips — CSS geometry, not glyphs */
.pip{display:inline-block;border-radius:50%;vertical-align:middle;}
.pip.on{width:.5rem;height:.5rem;background:var(--lapis);}
.pip.off{width:.28rem;height:.28rem;background:var(--neutral);}

/* prose blocks */
.prose{padding:var(--gap-xs) var(--gap-sm);}
.prose + .prose{border-top:1px solid var(--ink);}
.prose .lede{font-weight:700;}
.prose .why{color:var(--muted);}
.sweet{padding:var(--gap-xs) var(--gap-sm);color:var(--muted);font-style:italic;
  border-bottom:1px solid var(--ink);}

/* set-aside */
.aside td{color:var(--muted);}
.aside .tk{color:var(--ink);}

.colophon{margin-top:var(--gap-lg);padding-top:var(--gap-sm);
  border-top:1px solid var(--ink);color:var(--muted);}
.colophon b{color:var(--ink);}
.colophon .marks{display:flex;gap:var(--gap-lg);flex-wrap:wrap;
  margin-top:var(--gap-xs);}
.tablewrap{overflow-x:auto;}

@media print{
  body{background:#fff;} .page{border:none;margin:0;width:auto;}
  @page{margin:.35in;}
}
@media (max-width:640px){
  .snapshot{grid-template-columns:repeat(2,1fr);}
  .masthead h1 strong{transform:scaleY(1.35);}
}
"""


def build() -> str:
    md = SRC_MD.read_text()
    tables = _tables(md)
    main = next((t for t in tables if t[0] and t[0][0].lower() == "name"
                 and "conf" in " ".join(t[0]).lower()), tables[0])
    aside = next((t for t in tables if t is not main and t[0]
                  and t[0][0].lower() == "name"), None)
    hdr, rows = main

    def col(row, name):
        try:
            return row[hdr.index(name)]
        except (ValueError, IndexError):
            return ""

    # --- snapshot ---
    snap = [
        (_stat(md, "cohort screened"), "Screened"),
        (_stat(md, "listed common"), "Listed common"),
        (_stat(md, "prime"), "Prime · fit ≥3"),
        (_stat(md, "filer-emergence confirmed"), "Filer-confirmed"),
        (_stat(md, "set aside"), "Set aside"),
    ]
    snap_html = "".join(
        f'<div class="cell"><span class="v tnum">{esc(v)}</span>'
        f'<span class="l">{esc(l)}</span></div>' for v, l in snap)

    # --- ledger rows ---
    body_rows = []
    for r in rows:
        name = col(r, "Name"); tk = col(r, "Ticker")
        conf = col(r, "Conf"); emd = col(r, "Emerged"); fit = col(r, "Fit")
        liq = col(r, "Liq"); arch = col(r, "Archetypes")
        u = col(r, "U"); rr = col(r, "R"); o = col(r, "O")
        c = col(r, "C"); q = col(r, "Q")
        why = col(r, "Why")
        live = "live forced-seller" in (why or "")
        prime = False
        try:
            prime = float(fit) >= 3
        except ValueError:
            pass
        star = STAR if u == "●" else ""
        conf_html = (f'<span class="conf-y">✓</span>' if conf == "✓"
                     else f'<span class="conf-n">~</span>')
        emd_cls = "emd live" if live else "emd"
        emd_html = (f'<span class="{emd_cls}">{esc(emd)}</span>'
                    if emd and emd != "—"
                    else '<span class="emd">—</span>')
        arch_disp = arch if arch and arch != "—" else ""
        arch_html = (f'<span class="arch-lapis">{esc(arch_disp)}</span>'
                     if arch_disp else '<span class="tag none">—</span>')
        # liquidity band: micro is a genuine constraint (crimson), thin a
        # de-rate (muted), deep/ok fine (ink).
        liq_cls = {"micro": "liq-micro", "thin": "liq-thin"}.get(liq, "liq-ok")
        liq_html = f'<span class="{liq_cls}">{esc(liq or "?")}</span>'
        cls = ' class="prime"' if prime else ""
        body_rows.append(
            f'<tr{cls}>'
            f'<td>{esc(name)}</td>'
            f'<td><span class="tk">{esc(tk)}</span> {star}</td>'
            f'<td class="c">{conf_html}</td>'
            f'<td>{emd_html}</td>'
            f'<td class="n">{esc(fit)}</td>'
            f'<td class="c">{liq_html}</td>'
            f'<td class="c">{dot(u)}</td><td class="c">{dot(rr)}</td>'
            f'<td class="c">{dot(o)}</td><td class="c">{dot(c)}</td>'
            f'<td class="c">{dot(q)}</td>'
            f'<td>{arch_html}</td>'
            f'</tr>')
    ledger = "\n".join(body_rows)

    # --- prime prose ---
    prime_block = ""
    m = re.search(r"## Prime setups.*?\n\n(.*?)(?:\n##|\Z)", md, re.S)
    if m:
        items = [ln[2:].strip() for ln in m.group(1).splitlines()
                 if ln.strip().startswith("- ")]
        proses = []
        for it in items:
            it = re.sub(r"\*\*(.+?)\*\*", r"<span class='lede'>\1</span>", it)
            proses.append(f'<div class="prose">{it}</div>')
        prime_block = (
            '<section class="panel"><div class="panel-title">'
            '<span>Prime setup — fitness ≥ 3</span></div>'
            + "".join(proses) + '</section>')

    # --- set-aside ---
    aside_block = ""
    if aside and aside[1]:
        arows = "\n".join(
            f'<tr class="aside"><td>{esc(a[0])}</td>'
            f'<td><span class="tk">{esc(a[1])}</span></td>'
            f'<td>{esc(a[2]) if len(a) > 2 else ""}</td></tr>'
            for a in aside[1])
        aside_block = (
            '<section class="panel"><div class="panel-title">'
            '<span>Set aside — filer’s own emergence unconfirmed</span>'
            '<span class="legend">verify · not scored · not dropped'
            '</span></div>'
            '<div class="prose why">The emergence full-text match is a '
            'third-party or subsidiary possessive, so the filer’s own '
            'reorganization could not be confirmed — usually incidental '
            '(Eastman Chemical → acquired Solutia), occasionally a '
            'genuine parent/subsidiary emergence (PG&amp;E Corp → its '
            'utility).</div>'
            '<div class="tablewrap"><table><thead><tr><th>Name</th>'
            '<th>Ticker</th><th>Filing context</th></tr></thead><tbody>'
            + arows + '</tbody></table></div></section>')

    today = date.today().strftime("%-d %B %Y")

    return f"""<style>{CSS}</style>
<div class="page">
  <header class="masthead">
    <div class="mast-left">
      <div class="kicker">Special Situations · Post-Reorganization Desk</div>
      <h1><strong>Cyclepapa</strong></h1>
      <div class="mast-sub">Listed-Equity Reorganization Ledger</div>
    </div>
    <div class="mast-right">Vol.&nbsp;I · No.&nbsp;1<br><b>{today}</b><br>
      The tradable slice only</div>
  </header>

  <div class="divider"><span class="rule"></span>{FLEUR}<span class="rule"></span></div>

  <div class="sweet">The sweet spot: a newly listed common equity, distributed
    to unnatural owners, with a genuinely repaired balance sheet, an overstated
    share count or net-debt burden, and a dated catalyst that broadens the
    natural shareholder base.</div>

  <div class="snapshot" style="margin-top:var(--gap-sm)">{snap_html}</div>

  <section class="panel">
    <div class="panel-title"><span>The Six-Question Ledger — Exchange-Listed Common Only</span>
      <span class="legend">L·isted · U·nnatural owners · R·epaired · O·verstated · C·atalyst · Q·uality</span></div>
    <div class="tablewrap">
    <table>
      <thead><tr>
        <th>Name</th><th>Ticker</th><th class="c">Conf</th><th>Emerged</th>
        <th class="n">Fit</th><th class="c">Liq</th>
        <th class="c">U</th><th class="c">R</th><th class="c">O</th>
        <th class="c">C</th><th class="c">Q</th><th>Archetype</th>
      </tr></thead>
      <tbody>
{ledger}
      </tbody>
    </table>
    </div>
  </section>

  {prime_block}
  {aside_block}

  <footer class="colophon">
    <div><b>Reading the marks.</b> A filled lapis pip means the question is met;
    a faint grey pip, not. An eight-point lapis star beside a ticker marks a
    <b>live forced-seller overhang</b> (emergence within ~24 months). <b>Conf&nbsp;✓</b>
    = the filing was read and the filer’s own emergence confirmed
    (first-person, or Successor/Predecessor fresh-start reporting), or
    PACER-corroborated; <b>~</b> = kept but unverified, never dropped.</div>
    <div class="marks">
      <span><span class="pip on"></span> question met (lapis)</span>
      <span><span class="pip off"></span> not met (grey)</span>
      <span>{STAR} live forced-seller overhang</span>
    </div>
    <div style="margin-top:var(--gap-xs)">Source: <b>output/listed_equity_watchlist.md</b>
      · SEC EDGAR full-text + XBRL, Yahoo price, PACER. Research ledger —
      not investment advice.</div>
  </footer>
</div>
"""


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(build())
    print(f"Wrote {OUT}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
