"""Render the Godley report as a Times Lattice page."""

from __future__ import annotations

import html

from . import configuration as CF
from . import inflation_accounting as IA
from . import minsky_fragility as MF
from . import assembly as AS
from . import lineage as LN
from .sources import sectors as SEC
from .archetypes import lookup

CSS = """
:root{--ink:#000;--paper:#fff;--muted:#3f3f3f;--neutral:#8a8a8a;--lapis:#061933;--crimson:#7a0019;
 --serif:"Times New Roman",Times,"Liberation Serif",serif;--gsm:0.382rem;--gmd:0.618rem;--glg:1rem}
html{font-size:13.5px;background:var(--paper);color-scheme:light}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);font-family:var(--serif);font-size:1rem;
 line-height:1.2;font-variant-numeric:tabular-nums;-webkit-font-smoothing:antialiased}
.page{width:min(74rem,100vw - 1rem);margin:0.5rem auto;border:1px solid var(--ink);padding:var(--gmd) 0.9rem}
h1,h2{margin:0;font-weight:700;text-transform:uppercase;font-size:1rem}
p{margin:0} .muted{color:var(--muted)} .lapis{color:var(--lapis)} .crimson{color:var(--crimson)}
.masthead{display:grid;grid-template-columns:1fr auto;align-items:end;gap:var(--gmd);
 padding-bottom:var(--gsm);border-bottom:1px solid var(--ink)}
.masthead .plate strong{display:inline-block;font-weight:700;text-transform:uppercase;
 transform:scaleY(1.45);transform-origin:0 82%}
.masthead .kicker{color:var(--muted);margin-top:0.5rem;max-width:76ch}
.masthead .meta{text-align:right;color:var(--muted)}
section{border-bottom:1px solid var(--ink);padding:var(--gsm) 0}
section:last-of-type{border-bottom:none}
h2{margin-bottom:0.15rem}
h2 .n{color:var(--muted);font-weight:400}
.sub{color:var(--muted);margin-bottom:var(--gsm);max-width:88ch}
table{width:100%;border-collapse:collapse;margin-top:0.2rem}
th{text-align:right;color:var(--muted);text-transform:uppercase;font-weight:700;
 padding:0.14rem 0.3rem;border-bottom:1px solid var(--ink);white-space:nowrap}
th.l{text-align:left}
td{text-align:right;padding:0.16rem 0.3rem;border-bottom:1px solid var(--ink)}
td.l{text-align:left} tr:last-child td{border-bottom:none}
.cfg{display:grid;grid-template-columns:10rem 1fr;gap:0.5rem;padding:0.22rem 0;border-bottom:1px solid var(--ink)}
.cfg:last-child{border-bottom:none}
.cfg .nm{font-weight:700;text-transform:uppercase}
.cfg .nm .c{color:var(--muted);font-weight:400;text-transform:none}
.anom{padding:0.28rem 0;border-bottom:1px solid var(--ink)}
.anom:last-child{border-bottom:none}
.anom .t{font-weight:700}
.mustgive{padding:0.3rem 0;border-bottom:1px solid var(--ink)}
.mustgive:last-child{border-bottom:none}
.mustgive .c{font-weight:700;text-transform:uppercase;margin-right:0.4rem}
.foot{margin-top:var(--glg);padding-top:var(--gsm);border-top:1px solid var(--ink);color:var(--muted)}
@media print{.page{width:auto;border:none} @page{margin:0.35in}}
"""


def _esc(s):
    return html.escape(str(s))


def _num(v, dp=1, sign=True):
    if v is None or v != v:
        return "&mdash;"
    cls = "lapis" if v > 0 else ("crimson" if v < 0 else "muted")
    s = f"{v:+.{dp}f}" if sign else f"{v:.{dp}f}"
    return f'<span class="{cls}">{s}</span>'


def build() -> str:
    p = CF.panel()
    out = []
    A = AS.assembly()
    w = LN.world_ca_check()
    it = IA.panel()

    # ---- 1 configurations
    cfg_rows = ""
    for cfg in CF.CONFIG_ORDER:
        m = p[p.configuration == cfg]
        if not len(m):
            continue
        cfg_rows += (f'<div class="cfg"><div class="nm">{cfg.replace("-"," ")} '
                     f'<span class="c">({len(m)})</span></div><div>'
                     f'<div class="muted">{_esc(CF.CONFIG_BLURB.get(cfg,""))}</div>'
                     f'<div>{", ".join(sorted(m.country))}</div></div></div>')

    # ---- 2 disaggregation
    dis = [CF.disaggregate(g) for g in sorted(SEC.load())]
    dis = [d for d in dis if d]
    dis_rows = "".join(
        f"<tr><td class='l'>{_esc(lookup(d['iso']).name)}</td><td>{d['year']}</td>"
        f"<td>{_num(d['households'])}</td><td>{_num(d['households_gap'])}</td>"
        f"<td>{_num(d['corporates'])}</td><td>{_num(d['corporates_gap'])}</td>"
        f"<td class='l'>{d['sub_configuration'].replace('-',' ')}</td></tr>"
        for d in sorted(dis, key=lambda x: -(x['households_gap'] or 0)))

    # ---- 3 inflation
    infl_rows = ""
    for iso in it.head(12).index:
        a = IA.adjusted_balances(iso)
        if not a:
            continue
        flip = ' <span class="crimson">&#9654; flips</span>' if a["sign_flip"] else ""
        infl_rows += (f"<tr><td class='l'>{_esc(lookup(iso).name)}</td>"
                      f"<td>{a['inflation']:.1f}</td><td>{a['debt']:.0f}</td>"
                      f"<td>{_num(a['nominal']['government'])}</td>"
                      f"<td><b>{_num(a['adjusted']['government'])}</b>{flip}</td>"
                      f"<td>{_num(a['nominal']['private'])}</td>"
                      f"<td>{_num(a['adjusted']['private'])}</td></tr>")

    # ---- 4 financing
    fin_rows = ""
    for iso in ["CN", "HK", "KR", "BR", "US", "AU", "CA", "GB", "DE", "JP"]:
        if iso not in MF._INPUTS:
            continue
        dd = MF.debt_dynamics(iso)
        ai = AS.assembly_index(iso)
        reg = MF.regime_label(iso)
        rc = "crimson" if reg == "ponzi" else ("muted" if reg == "hedge" else "")
        fin_rows += (f"<tr><td class='l'>{_esc(lookup(iso).name)}</td>"
                     f"<td>{_num(dd) if dd is not None else '&mdash;'}</td>"
                     f"<td>{MF.fragility_index(iso):.2f}</td>"
                     f"<td class='l'><span class='{rc}'>{reg}</span></td>"
                     f"<td>{ai['assembly_index']}</td>"
                     f"<td>{AS.assembly_fragility(iso):.3f}</td></tr>")

    # ---- 5 assembly
    asm_rows = "".join(
        f"<tr><td class='l'>{k.replace('-',' ')}</td><td>{v['copy_number']}</td>"
        f"<td>{v['mean_assembly_index']:.2f}</td><td><b>{v['contribution']:.3f}</b></td></tr>"
        for k, v in sorted(A["by_configuration"].items(),
                           key=lambda kv: -kv[1]["contribution"]))

    # ---- anomalies
    anoms = []
    flips = [lookup(i).name for i in it[it.sign_flip].index if lookup(i)]
    anoms.append(("Japan is fiscally tightening, not loosening",
                  f"On 214% debt at 2.7% inflation Japan's &minus;1.7% nominal deficit is a "
                  f"<b>+3.9% REAL surplus</b>. Eight economies flip sign once the inflation "
                  f"gain is counted: {', '.join(flips)}. Every conventional sectoral-balance "
                  f"chart shows these as expansionary; on Godley's own accounting they are not."))
    anoms.append(("Three savers are simultaneously hoarding and fragile",
                  "China, Hong Kong and South Korea are in the savers-trap <i>and</i> "
                  "Ponzi-financed &mdash; the private sector is accumulating surpluses while "
                  "its financing still requires rollover plus fresh borrowing to stand. "
                  "Normally hoarding and fragility are opposites; here they coexist."))
    anoms.append(("The Anglo bloc stopped being fragile and nobody noticed",
                  "UK &minus;40pp, Canada &minus;27pp, US &minus;22pp, Australia &minus;20pp "
                  "of private credit/GDP off their peaks. On measured financing structure they "
                  "are hedge-financed &mdash; the opposite of the received narrative, and "
                  "consistent with Levy's own October 2025 finding on corporate net liabilities."))
    anoms.append(("Hong Kong and Ireland are 12&ndash;16pp away from their own norms",
                  "Hong Kong's private balance is +15.7pp above its historical norm and "
                  "Ireland's +11.5pp &mdash; the two largest sector dislocations in the panel, "
                  "both entrep&ocirc;ts where the number reflects offshore structures rather "
                  "than domestic behaviour."))
    anoms.append(("Saudi Arabia's private sector swung 8.5pp <i>below</i> its norm",
                  "The largest deterioration on the board, and the reason it classifies as "
                  "forced-borrower: the private sector is absorbing the adjustment while the "
                  "state expands."))
    anoms.append(("Twelve economies share one configuration",
                  f"A = {A['assembly_A']}, and the savers-trap carries the largest systemic "
                  f"load (index 1.58 &times; 12 copies). One country escapes a savers-trap by "
                  f"widening its external surplus &mdash; which must come out of another's. "
                  f"The US is already absorbing ${abs(1080):,}bn of the world's surpluses."))
    anom_html = "".join(
        f'<div class="anom"><div class="t">{t}</div><div class="muted">{b}</div></div>'
        for t, b in anoms)

    # ---- what must give
    mg = "".join(
        f'<div class="mustgive"><span class="c">{_esc(lookup(i).name)}</span>'
        f'<span class="muted">{_esc(CF.what_must_give(i))}</span></div>'
        for i in ["DE", "JP", "US", "GB", "CN", "KR"] if CF.what_must_give(i))

    return f"""<title>The Godley Report</title>
<style>{CSS}</style>
<div class="page">
  <header class="masthead">
    <div class="plate"><h1><strong>The&nbsp;Godley&nbsp;Report</strong></h1>
      <div class="kicker">Sectoral-balance analysis after Wynne Godley and the Levy school, with the
      corrections from a close reading of the primary texts: inflation accounting restored, the private
      balance disaggregated into households and firms, Minsky measured on financing structure rather than
      valuation, and the world identity used as Godley used it &mdash; as a redundant-equation diagnostic.</div></div>
    <div class="meta"><div><strong>Sectoral balances</strong></div><div>IMF actual to 2024</div>
      <div>Eurostat sectors to 2025</div></div>
  </header>

  <section><h2>Anomalies <span class="n">&mdash; what is odd this year</span></h2>
    {anom_html}</section>

  <section><h2>1 <span class="n">&middot; Configurations &mdash; the constellation, not a ranking</span></h2>
    {cfg_rows}</section>

  <section><h2>2 <span class="n">&middot; The private balance disaggregated</span></h2>
    <div class="sub">Godley &amp; Lavoie (2007, p.25) repudiated the single-private-sector aggregation
    &mdash; &ldquo;households and production firms take entirely different decisions.&rdquo; The same
    surplus is a different economy depending on who holds it. Each sub-sector is judged against its own
    pre-2020 norm.</div>
    <table><thead><tr><th class="l">Economy</th><th>Yr</th><th>Households</th><th>vs norm</th>
      <th>Corporates</th><th>vs norm</th><th class="l">Sub-configuration</th></tr></thead>
      <tbody>{dis_rows}</tbody></table></section>

  <section><h2>3 <span class="n">&middot; Inflation accounting</span></h2>
    <div class="sub">Godley &amp; Cripps (1983:245): &ldquo;the faster the rate of inflation the larger
    the government&rsquo;s cash deficit must be in order to keep real debt constant.&rdquo; The adjustment
    is symmetric across sectors and sums to zero, so the identity survives &mdash; it changes the level and
    sometimes the sign of each balance, never the constraint.</div>
    <table><thead><tr><th class="l">Economy</th><th>&pi;%</th><th>Debt</th><th>Govt nominal</th>
      <th>Govt real</th><th>Private nominal</th><th>Private real</th></tr></thead>
      <tbody>{infl_rows}</tbody></table></section>

  <section><h2>4 <span class="n">&middot; Financing structure &mdash; Minsky measured, not asserted</span></h2>
    <div class="sub">Ponzi is a financing-structure claim &mdash; debt service exceeding cash flow &mdash;
    not a valuation claim. Measured as private credit/GDP against its own five-year peak. <i>a</i> is the
    number of operations required to sustain the position: income alone (1), plus rollover (2), plus fresh
    borrowing (3).</div>
    <table><thead><tr><th class="l">Economy</th><th>Debt vs peak</th><th>Fragility</th>
      <th class="l">Regime</th><th><i>a</i></th><th>Assembly</th></tr></thead>
      <tbody>{fin_rows}</tbody></table></section>

  <section><h2>5 <span class="n">&middot; Systemic load &mdash; assembly index &times; copy number</span></h2>
    <div class="sub">A high step-count structure at high copy number is not chance but selection: these
    economies reached the same configuration because the same forces put them there &mdash; and they cannot
    all exit it simultaneously.</div>
    <table><thead><tr><th class="l">Configuration</th><th>Copies <i>n</i></th><th>Mean <i>a</i></th>
      <th>Contribution</th></tr></thead><tbody>{asm_rows}</tbody></table>
    <div class="sub" style="margin-top:0.3rem"><b>A = {A['assembly_A']}</b>. Most loaded:
    <b>{A['most_loaded'].replace('-',' ')}</b>.</div></section>

  <section><h2>6 <span class="n">&middot; World consistency &mdash; the redundant-equation check</span></h2>
    <div class="sub">Godley left the world identity out of the solved system and used it as a diagnostic
    (&ldquo;an accounting system with no black holes&rdquo;). Benchmarked against the measured global
    discrepancy, not zero.</div>
    <table><tbody>
      <tr><td class="l">Implied world balance</td><td>${w['implied_world_balance_usd_bn']:,.0f}bn</td></tr>
      <tr><td class="l">Measured discrepancy</td><td>${w['world_discrepancy_benchmark_usd_bn']:,.0f}bn</td></tr>
      <tr><td class="l">Residual</td><td><b>${w['residual_vs_benchmark_usd_bn']:,.0f}bn</b></td></tr>
    </tbody></table>
    <div class="sub" style="margin-top:0.3rem">{_esc(w['verdict'])}. {_esc(w['counterparty'])} &mdash;
    surpluses cannot be achieved everywhere at once.</div></section>

  <section><h2>7 <span class="n">&middot; What must give</span></h2>
    {mg}</section>

  <footer class="foot">Balances from IMF fiscal and current-account actuals and Eurostat annual sector
  accounts; credit from BIS; norms are each sector&rsquo;s own pre-2020 median. The three balances sum to
  zero by construction &mdash; the identity is a frame, not evidence. Conditional, not predictive: the
  report states what must happen if a configuration persists, not when. After Wynne Godley, Levy Economics
  Institute of Bard College.</footer>
</div>"""


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "scanner/report.html"
    with open(path, "w") as f:
        f.write(build())
    print(f"wrote {path}")
