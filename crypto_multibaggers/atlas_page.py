"""Render data/crypto_multibaggers/atlas.json into a self-contained HTML atlas.

    python -m crypto_multibaggers.atlas_page
"""
from __future__ import annotations

import json
import math

from .config import DATA_DIR

TEMPLATE = r"""<title>Crypto Multibagger Tape Atlas</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans+Condensed:wght@600;700&family=IBM+Plex+Sans:wght@400;500;600&display=swap">
<style>
:root{--paper:#f2f5f5;--surface:#ffffff;--ink:#132028;--ink2:#46545e;--muted:#74828c;--rule:#d4dcdc;--grid:#e3e9e8;
--accent:#0b6e6b;--t1:#0d366b;--t2:#1c5cab;--t3:#3987e5;--t4:#86b6ef;--fade:#eb6834;--plc:#8b939b;
--lo:#2a78d6;--mid:#eceeec;--hi:#d64545;--good:#006300;--bad:#c23b3b;color-scheme:light}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--paper:#0f1417;--surface:#151c20;--ink:#e6eeef;--ink2:#b3c0c4;
--muted:#87959b;--rule:#2a3439;--grid:#222c31;--accent:#43b8b2;--t1:#9ec5f4;--t2:#5598e7;--t3:#256abf;--t4:#184f95;--fade:#d95926;
--plc:#7a838c;--lo:#3987e5;--mid:#2a3037;--hi:#e06060;--good:#3fbf5f;--bad:#e36b6b;color-scheme:dark}}
:root[data-theme="dark"]{--paper:#0f1417;--surface:#151c20;--ink:#e6eeef;--ink2:#b3c0c4;--muted:#87959b;--rule:#2a3439;--grid:#222c31;
--accent:#43b8b2;--t1:#9ec5f4;--t2:#5598e7;--t3:#256abf;--t4:#184f95;--fade:#d95926;--plc:#7a838c;--lo:#3987e5;--mid:#2a3037;
--hi:#e06060;--good:#3fbf5f;--bad:#e36b6b;color-scheme:dark}
*{box-sizing:border-box}
body{background:var(--paper);color:var(--ink);font:15px/1.55 "IBM Plex Sans",system-ui,-apple-system,"Segoe UI",sans-serif;margin:0}
.wrap{max-width:1100px;margin:0 auto;padding-inline:20px;padding-block:28px 64px}
h1,h2,h3{font-family:"IBM Plex Sans Condensed","IBM Plex Sans",system-ui,sans-serif;text-wrap:balance;margin:0}
h1{font-size:2.3rem;line-height:1.1;font-weight:700;letter-spacing:-.01em}
h2{font-size:1.45rem;font-weight:600;margin-top:4px}
h3{font-size:1.05rem;font-weight:600}
p{max-width:70ch;margin:0}
.mono,.num{font-family:"IBM Plex Mono",ui-monospace,Menlo,monospace;font-variant-numeric:tabular-nums}
header.top{display:grid;gap:12px;padding-bottom:22px;border-bottom:1px solid var(--rule)}
.stamp{display:inline-flex;gap:8px;align-items:center;font:500 .72rem/1 "IBM Plex Mono",monospace;letter-spacing:.12em;
text-transform:uppercase;color:var(--accent);border:1.5px solid var(--accent);padding:6px 9px;border-radius:3px;width:max-content;max-width:100%}
.lede{color:var(--ink2);font-size:1.05rem}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-top:18px}
.tile{background:var(--surface);border:1px solid var(--rule);border-radius:6px;padding:12px 14px;display:grid;gap:2px;align-content:start}
.tile .v{font:600 1.5rem/1.2 "IBM Plex Sans",sans-serif}
.tile .k{color:var(--muted);font-size:.8rem}
section.ex{display:grid;gap:14px;padding-block:30px;border-bottom:1px solid var(--rule)}
.eyebrow{font:500 .72rem/1 "IBM Plex Mono",monospace;letter-spacing:.14em;text-transform:uppercase;color:var(--muted)}
.take{border-left:3px solid var(--accent);padding:4px 0 4px 12px;color:var(--ink);max-width:76ch}
.scroll{overflow-x:auto;background:var(--surface);border:1px solid var(--rule);border-radius:6px}
table{border-collapse:collapse;width:100%;font-size:.86rem}
th,td{padding:7px 10px;text-align:right;border-bottom:1px solid var(--grid);white-space:nowrap}
th:first-child,td:first-child{text-align:left}
td.long{white-space:normal;min-width:220px;text-align:left}
#durable svg,#ocwin svg{max-width:680px}
th{color:var(--muted);font-weight:500;font-size:.75rem;letter-spacing:.04em;text-transform:uppercase;vertical-align:bottom}
tr.grp td{background:var(--paper);color:var(--muted);font:500 .72rem/1.2 "IBM Plex Mono",monospace;letter-spacing:.1em;text-transform:uppercase}
td.num{font-size:.84rem}
.pos{color:var(--good)} .neg{color:var(--bad)}
.chart{background:var(--surface);border:1px solid var(--rule);border-radius:6px;padding:12px;position:relative}
.chart svg{display:block;width:100%;height:auto}
.legend{display:flex;flex-wrap:wrap;gap:6px 16px;font-size:.8rem;color:var(--ink2)}
.legend i{display:inline-block;width:14px;height:3px;border-radius:2px;margin-right:6px;vertical-align:middle}
.tip{position:absolute;pointer-events:none;background:var(--surface);border:1px solid var(--rule);border-radius:5px;padding:7px 9px;
font-size:.78rem;box-shadow:0 2px 10px rgba(0,0,0,.12);display:none;z-index:2;min-width:180px;color:var(--ink)}
.two{display:grid;grid-template-columns:repeat(auto-fit,minmax(310px,1fr));gap:14px}
.card{background:var(--surface);border:1px solid var(--rule);border-radius:6px;padding:14px;display:grid;gap:8px;align-content:start}
.arch{display:grid;gap:10px}
.arow{display:grid;grid-template-columns:minmax(0,1fr) 170px;gap:14px;align-items:center;background:var(--surface);
border:1px solid var(--rule);border-radius:6px;padding:12px 14px}
.arow .nm{font-weight:600}
.arow .meta{color:var(--ink2);font-size:.8rem}
.chips{display:flex;flex-wrap:wrap;gap:4px 6px;margin-top:4px}
.chip{font:500 .72rem/1 "IBM Plex Mono",monospace;padding:4px 6px;border-radius:3px;background:var(--paper);color:var(--ink2);border:1px solid var(--rule)}
.chip.up{border-color:var(--hi);color:var(--ink)} .chip.dn{border-color:var(--lo);color:var(--ink)}
.bar{height:8px;border-radius:4px;background:var(--grid);position:relative;overflow:hidden}
.bar>span{position:absolute;left:0;top:0;bottom:0;background:var(--accent);border-radius:4px}
.small{font-size:.82rem;color:var(--ink2)}
button.tog{font:500 .8rem "IBM Plex Sans",sans-serif;background:var(--surface);color:var(--ink);border:1px solid var(--rule);
border-radius:4px;padding:6px 10px;cursor:pointer;width:max-content}
button.tog:hover{border-color:var(--accent)}
footer{padding-top:24px;color:var(--muted);font-size:.8rem;display:grid;gap:6px}
code{font-family:"IBM Plex Mono",monospace;font-size:.85em}
@media (max-width:560px){h1{font-size:1.8rem}.arow{grid-template-columns:1fr}}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
</style>
<div class="wrap">
<header class="top">
  <span class="stamp">Case file · crypto re-ratings</span>
  <h1>What the tape looked like before the multibagger</h1>
  <p class="lede" id="lede"></p>
  <div class="tiles" id="tiles"></div>
</header>

<section class="ex"><span class="eyebrow">Exhibit A · the database</span><h2>Re-ratings by outcome, size and regime</h2>
<p class="small">Day 0 is the first day a coin's market-model abnormal return reaches 3 sigmas of its own baseline and +15% raw, after 60 quiet days.
The multiple is the best 5-day median close within 180 days over the day −1 close. "Paid": day 0–1 abnormal return above zero and above two sigmas.
"Durable": still +20% after 60 days.</p>
<div class="scroll"><table id="fams"></table></div>
<div class="scroll"><table id="sectors"></table></div></section>

<section class="ex"><span class="eyebrow">Exhibit B · the common signature</span><h2>Volume builds before price moves</h2>
<p class="take" id="take-b"></p>
<div class="two"><div class="chart" id="pav"></div><div class="chart" id="pcar"></div></div>
<div class="chart" id="plong"></div>
<div class="legend" id="plegend"></div></section>

<section class="ex"><span class="eyebrow">Exhibit C · events vs matched placebo</span><h2>Which pre-event measures separate re-ratings from ordinary tape</h2>
<p class="small">Each cell is an AUC: the probability that an event's pre-window value exceeds its matched placebo window's (same calendar day, other coin with no
trigger within ±60 days, nearest in baseline dollar volume, volatility and age). 0.5 means no difference; red means higher before events, blue lower.
A dot marks q ≥ 0.01 after Benjamini–Hochberg correction. Hover a cell for medians.</p>
<button class="tog" id="gridtog" type="button">Show all measures</button>
<div class="scroll"><table id="grid"></table></div></section>

<section class="ex"><span class="eyebrow">Exhibit D · winners vs losers</span><h2>Which pops become multibaggers</h2>
<p class="take" id="take-d"></p>
<div class="two" id="winners"></div></section>

<section class="ex"><span class="eyebrow">Exhibit E · durable re-ratings vs faded pops</span><h2>Separating re-ratings from pumps</h2>
<div class="chart" id="durable"></div></section>

<section class="ex"><span class="eyebrow">Exhibit F · archetypes</span><h2>Tape archetypes before multibaggers</h2>
<p class="small" id="arch-note"></p>
<div class="arch" id="arch"></div>
<h3>Out of time: archetypes fitted on 2017–21, applied to 2022+ triggers</h3>
<div class="scroll"><table id="archoos"></table></div></section>

<section class="ex"><span class="eyebrow">Exhibit G · what works best</span><h2>Ranking the signals on every coin, every two weeks</h2>
<p class="small" id="screen-note"></p>
<p class="take" id="take-g"></p>
<div class="scroll"><table id="lb"></table></div>
<h3>Best one-, two- and three-signal screens</h3>
<p class="small" id="rec-note"></p>
<div class="scroll"><table id="recipes"></table></div>
<h3>Toxic overlays against their plain signals</h3>
<p class="small">Same screen, same test years. A toxic overlay keeps only days whose 20-day VPIN sits above the coin's own baseline 80th percentile,
with buy-side BVC imbalance where direction matters.</p>
<div class="scroll"><table id="pairs"></table></div>
<h3>Once a coin pops: which measure picks the multibaggers</h3>
<p class="small" id="tlb-note"></p>
<div class="scroll"><table id="tlb"></table></div>
<h3>Out-of-sample classifiers</h3>
<div class="tiles" id="cv"></div></section>

<section class="ex"><span class="eyebrow">Exhibit O · on-chain layer</span><h2>Network activity, holders, supply and TVL before re-ratings</h2>
<p class="small" id="oc-note"></p>
<div class="scroll"><table id="ocgrid"></table></div>
<div class="chart" id="ocwin"></div></section>

<section class="ex"><span class="eyebrow">Exhibit H · validation cases</span><h2>Known catalysts, re-dated from the tape</h2>
<p class="small">Legal, regulatory, listing and narrative catalysts. "Trigger" says whether the day was caught by the event scan. Score is the pre-event
multibagger score's percentile among placebo windows, using only the tape before the day.</p>
<div class="scroll"><table id="val"></table></div></section>

<section class="ex"><span class="eyebrow">Exhibit L · live scan</span><h2>Coins whose tape looks like pre-multibagger tape today</h2>
<p class="small" id="live-note"></p>
<div class="scroll"><table id="live"></table></div></section>

<section class="ex"><span class="eyebrow">Using it</span><h2>From signature to screen</h2>
<div class="two" id="use"></div></section>

<footer id="foot"></footer>
</div>
<script type="application/json" id="data">__DATA__</script>
<script>
const D = JSON.parse(document.getElementById('data').textContent);
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const ok = x => x!=null && !isNaN(x);
const pct = x => ok(x) ? (100*x).toFixed(x<0.1&&x>0?1:0)+'%' : '–';
const f2 = x => ok(x) ? x.toFixed(2) : '–';
const sgn = x => ok(x) ? (x>0?'+':'')+(100*x).toFixed(1)+'%' : '–';
const lgp = x => ok(x) ? (x>0?'+':'')+(100*(Math.exp(x)-1)).toFixed(0)+'%' : '–';
const mult = x => ok(x) ? (x>=10? x.toFixed(0) : x.toFixed(1))+'×' : '–';
const n0 = x => ok(x) ? Math.round(x).toLocaleString() : '–';
const money = x => !ok(x) ? '–' : x>=1e9 ? '$'+(x/1e9).toFixed(1)+'bn' : x>=1e6 ? '$'+(x/1e6).toFixed(1)+'m' : x>=1e3 ? '$'+(x/1e3).toFixed(0)+'k' : '$'+x.toFixed(0);
function el(t,a={},p){const e=document.createElementNS('http://www.w3.org/2000/svg',t);for(const k in a)e.setAttribute(k,a[k]);if(p)p.appendChild(e);return e;}
const TIER_VAR={'10x+':'--t1','5-10x':'--t2','3-5x':'--t3','2-3x':'--t4','<2x':'--fade','all':'--ink2'};

function header(){
  document.getElementById('lede').textContent=`${n0(D.n_events)} crypto re-ratings (${D.first}–${D.last}) across ${n0(D.n_tokens)} coins from a `+
   `${n0(D.n_universe)}-coin universe: the first 3-sigma, +15% day after 60 quiet days. Each is measured against its own baseline, against `+
   `${n0(D.n_placebo)} matched placebo windows and on 180 days of outcomes, with the informed-flow, toxic-flow and idiosyncratic-volume `+
   `measures of the equity study plus on-chain activity.`;
  const t=[[n0(D.n_events),'re-rating events after data-quality screens'],[n0(D.n_tokens),'coins, including ones that later died'],
   [n0(D.n_placebo),'matched placebo windows'],[n0(D.n_mb3),'became 3x+ within 180 days'],[n0(D.n_mb10),'became 10x+ within 180 days']];
  document.getElementById('tiles').innerHTML=t.map(([v,k])=>`<div class="tile"><span class="v num">${v}</span><span class="k">${k}</span></div>`).join('');
}
function fams(){const t=document.getElementById('fams');const b=D.placebo_rates||{};
  let h='<thead><tr><th>Family</th><th>Events</th><th>Coins</th><th>Micro tape</th><th>Paid</th><th>Durable 60d</th><th>2x+</th><th>3x+</th><th>10x+</th><th>Median multiple</th><th>From day-1 close</th><th>Run-up −60…−1</th></tr></thead><tbody>';
  D.families.filter(f=>!f.key.startsWith('sector:')).forEach(f=>{h+=`<tr><td>${f.label}</td><td class="num">${n0(f.events)}</td><td class="num">${n0(f.tokens)}</td><td class="num">${pct(f.micro_share)}</td><td class="num">${pct(f.paid)}</td><td class="num">${pct(f.durable)}</td><td class="num">${pct(f.p_2x)}</td><td class="num">${pct(f.p_3x)}</td><td class="num">${pct(f.p_10x)}</td><td class="num">${mult(f.mult_med)}</td><td class="num">${mult(f.mult_entry_med)}</td><td class="num ${f.runup>0?'pos':'neg'}">${lgp(f.runup)}</td></tr>`;});
  h+=`<tr><td><b>Matched placebo windows</b></td><td class="num">${n0(D.n_placebo)}</td><td></td><td></td><td class="num">${pct(b.paid)}</td><td class="num">${pct(b.durable)}</td><td class="num">${pct(b.p_2x)}</td><td class="num">${pct(b.p_3x)}</td><td class="num">${pct(b.p_10x)}</td><td class="num">${mult(b.mult_med)}</td><td></td><td></td></tr>`;
  t.innerHTML=h+'</tbody>';
  if(D.sectors&&D.sectors.length){const s=document.getElementById('sectors');let g='<thead><tr><th>Sector (CoinGecko)</th><th>Events</th><th>Coins</th><th>3x+</th><th>10x+</th><th>Durable 60d</th><th>Median multiple</th><th>Median CAR 0–1</th></tr></thead><tbody>';
   D.sectors.forEach(r=>{g+=`<tr><td>${r.sector}</td><td class="num">${n0(r.events)}</td><td class="num">${n0(r.tokens)}</td><td class="num">${pct(r.p_3x)}</td><td class="num">${pct(r.p_10x)}</td><td class="num">${pct(r.durable)}</td><td class="num">${mult(r.mult_med)}</td><td class="num">${lgp(r.car01)}</td></tr>`;});
   s.innerHTML=g+'</tbody>';}}

function pathsChart(id,key,title,fmt,lo_,hi_,ticks){
  const P=D.paths;if(!P)return;const host=document.getElementById(id);
  const W=id==='plong'?1040:520,H=300,L=48,R=12,T=26,B=34;const svg=el('svg',{viewBox:`0 0 ${W} ${H}`,role:'img','aria-label':title},host);
  const i0=P.rel.indexOf(lo_),i1=P.rel.indexOf(hi_);const xs=P.rel.slice(i0,i1+1);
  const S=P.series.filter(s=>s.key!=='all').map(s=>({...s,v:s[key].slice(i0,i1+1),col:css(TIER_VAR[s.key]||'--ink2')}));
  const pv=P.placebo?P.placebo[key].slice(i0,i1+1):null;
  const all=[];S.forEach(s=>all.push(...s.v.filter(ok)));if(pv)all.push(...pv.filter(ok));
  let lo=Math.min(...all),hi=Math.max(...all);const pad=(hi-lo)*.08;lo-=pad;hi+=pad;
  const X=v=>L+(v-xs[0])/(xs[xs.length-1]-xs[0])*(W-L-R),Y=v=>T+(hi-v)/(hi-lo)*(H-T-B);
  for(let i=0;i<=5;i++){const v=lo+(hi-lo)*i/5;el('line',{x1:L,x2:W-R,y1:Y(v),y2:Y(v),stroke:css('--grid')},svg);
    const t=el('text',{x:L-6,y:Y(v)+4,'text-anchor':'end','font-size':10,fill:css('--muted')},svg);t.textContent=fmt(v);}
  ticks.forEach(v=>{const t=el('text',{x:X(v),y:H-12,'text-anchor':'middle','font-size':10,fill:css('--muted')},svg);t.textContent=v;});
  el('line',{x1:X(0),x2:X(0),y1:T,y2:H-B,stroke:css('--muted')},svg);
  const tt=el('text',{x:L,y:14,'font-size':12,'font-weight':600,fill:css('--ink')},svg);tt.textContent=title;
  const line=(arr,col)=>{let d='';arr.forEach((v,i)=>{if(!ok(v))return;d+=(d?'L':'M')+X(xs[i]).toFixed(1)+','+Y(v).toFixed(1);});
    el('path',{d,fill:'none',stroke:col,'stroke-width':2,'stroke-linejoin':'round','stroke-linecap':'round'},svg);};
  if(pv)line(pv,css('--plc'));S.slice().reverse().forEach(s=>line(s.v,s.col));
  const tip=document.createElement('div');tip.className='tip';host.appendChild(tip);
  const cross=el('line',{y1:T,y2:H-B,stroke:css('--ink2'),'stroke-width':1,visibility:'hidden'},svg);
  svg.addEventListener('mousemove',ev=>{const r=svg.getBoundingClientRect();const px=(ev.clientX-r.left)/r.width*W;
    let i=Math.round((px-L)/(W-L-R)*(xs.length-1));i=Math.max(0,Math.min(xs.length-1,i));
    cross.setAttribute('x1',X(xs[i]));cross.setAttribute('x2',X(xs[i]));cross.setAttribute('visibility','visible');
    let h=`<b>day ${xs[i]}</b><br>`;S.forEach(s=>{h+=`<span style="color:${s.col}">■</span> ${s.label}: ${fmt(s.v[i])}<br>`;});
    if(pv)h+=`<span style="color:${css('--plc')}">■</span> placebo: ${fmt(pv[i])}`;
    tip.innerHTML=h;tip.style.display='block';const bx=host.getBoundingClientRect();
    tip.style.left=Math.min(ev.clientX-bx.left+12,bx.width-200)+'px';tip.style.top=(ev.clientY-bx.top+12)+'px';});
  svg.addEventListener('mouseleave',()=>{tip.style.display='none';cross.setAttribute('visibility','hidden');});
}
function legend(){const P=D.paths;if(!P)return;const h=document.getElementById('plegend');
  P.series.filter(s=>s.key!=='all').forEach(s=>h.insertAdjacentHTML('beforeend',`<span><i style="background:${css(TIER_VAR[s.key])}"></i>${s.label} (n=${n0(s.n)})</span>`));
  h.insertAdjacentHTML('beforeend',`<span><i style="background:${css('--plc')}"></i>Matched placebo windows (n=${n0(P.placebo.n)})</span>`);}

function mix(a,b,t){const p=c=>c.replace('#','').match(/\w\w/g).map(x=>parseInt(x,16));const A=p(a),B=p(b);return '#'+A.map((v,i)=>Math.round(v+(B[i]-v)*t).toString(16).padStart(2,'0')).join('');}
function aucColor(a){const t=Math.max(-1,Math.min(1,(a-.5)/.18));return t<0?mix(css('--mid'),css('--lo'),-t):mix(css('--mid'),css('--hi'),t);}
function lum(h){const c=h.replace('#','').match(/\w\w/g).map(x=>parseInt(x,16)/255);return .2126*c[0]+.7152*c[1]+.0722*c[2];}
const GROUP_LABEL={volume:'Volume',flow:'Flow and toxicity',price:'Price path',liquidity:'Liquidity',toxic:'Toxic overlays',size:'Size and age',
  'on-chain':'Network activity (CoinMetrics)',defi:'DeFi fundamentals (DefiLlama)',day0:'Day 0'};
function gridTable(id,G,showAll,keyFeats){const t=document.getElementById(id);if(!G)return;
  const byF={};G.rows.forEach(r=>{(byF[r.feature]=byF[r.feature]||{label:r.label,group:r.group,cells:{}}).cells[r.family]=r;});
  let feats=Object.keys(byF);
  const strength=f=>Math.max(...G.families.map(fm=>{const c=byF[f].cells[fm.key];return c&&ok(c.auc)?Math.abs(c.auc-.5):0;}));
  if(!showAll&&keyFeats)feats=feats.filter(f=>keyFeats.includes(f));
  const order=['volume','flow','toxic','price','liquidity','size','on-chain','defi'];
  feats.sort((a,b)=>order.indexOf(byF[a].group)-order.indexOf(byF[b].group)||strength(b)-strength(a));
  let h='<thead><tr><th>Pre-event measure</th>'+G.families.map(f=>`<th>${f.label}</th>`).join('')+'</tr></thead><tbody>';let g0='';
  feats.forEach(f=>{const r=byF[f];if(r.group!==g0){g0=r.group;h+=`<tr class="grp"><td colspan="${G.families.length+1}">${GROUP_LABEL[g0]||g0}</td></tr>`;}
    h+=`<tr><td>${r.label}</td>`+G.families.map(fm=>{const c=r.cells[fm.key];if(!c||!ok(c.auc))return '<td>–</td>';const bg=aucColor(c.auc);
    const ink=lum(bg)>.45?'#132028':'#ffffff';const dot=(c.q==null||c.q>=0.01)?' ·':'';
    return `<td class="num" style="background:${bg};color:${ink}" title="${fm.label}: event median ${f2(c.ma)} vs placebo ${f2(c.mb)} (n=${n0(c.n)}, q=${ok(c.q)?c.q.toExponential(1):'–'})">${c.auc.toFixed(2)}${dot}</td>`;}).join('')+'</tr>';});
  t.innerHTML=h+'</tbody>';}
let gridAll=false;
const KEY_FEATS=['av_mean_S','av_mean_L','cusum_av_120','iv_mean_S','uv_mean_A','n_av2_A','vpin_cdf','oi_vw_L','cmf20','obv_A','tobv_A',
 'toxic_breakout_S20','toxic_mom_A','toxic_trend_A','toxic_squeeze','capitulation_S','car_L','car_S','mom_90','dd_ath','vol_ratio_A','vol_ratio_S',
 'bbw_pct','n_up_jumps_A','skew_A','brk_90','trend_t60','amihud_ratio_A','kyle_ratio_A','corr_mkt_A','log_age'];
function grid(){gridTable('grid',D.grid,gridAll,KEY_FEATS);document.getElementById('gridtog').textContent=gridAll?'Show key measures':'Show all measures';}

function aucBars(host,rows,ka,kb,la,lb){const W=560,rowH=28,L=300,R=56,T=8;const H=T+rows.length*rowH+24;
  const svg=el('svg',{viewBox:`0 0 ${W} ${H}`,role:'img'},host);const X=v=>L+(v-.2)/(.6)*(W-L-R);
  [0.3,0.4,0.5,0.6,0.7].forEach(v=>{el('line',{x1:X(v),x2:X(v),y1:T,y2:H-20,stroke:v==0.5?css('--muted'):css('--grid')},svg);
    const t=el('text',{x:X(v),y:H-6,'text-anchor':'middle','font-size':10,fill:css('--muted')},svg);t.textContent=v.toFixed(1);});
  rows.forEach((r,i)=>{const y=T+i*rowH+rowH/2;const t=el('text',{x:L-8,y:y+4,'text-anchor':'end','font-size':11,fill:css('--ink2')},svg);
    t.textContent=r.label.length>46?r.label.slice(0,45)+'…':r.label;
    const x0=X(.5),x1=X(Math.max(.2,Math.min(.8,r.auc)));const g=el('g',{},svg);
    el('rect',{x:Math.min(x0,x1),y:y-7,width:Math.max(2,Math.abs(x1-x0)),height:14,rx:3,fill:r.auc>.5?css('--hi'):css('--lo')},g);
    const v=el('text',{x:r.auc>.5?x1+5:x1-5,y:y+4,'text-anchor':r.auc>.5?'start':'end','font-size':10,fill:css('--ink')},g);v.textContent=r.auc.toFixed(2);
    const tl=el('title',{},g);tl.textContent=`${r.label}: ${la} median ${f2(r[ka])} vs ${lb} median ${f2(r[kb])}, q=${ok(r.q)?r.q.toExponential(1):'–'}`;});}
function winners(){const W=D.winners;if(!W)return;const h=document.getElementById('winners');
  const c1=document.createElement('div');c1.className='card';c1.innerHTML=`<h3>3x+ multibaggers vs faded pops</h3><div class="small">${n0(W.n_w)} triggers that reached 3x within 180 days vs ${n0(W.n_l)} that never reached 1.5x and sat below the day −1 close after 60 days. Pre-event and day-0 measures; bars right of 0.5 are higher before multibaggers.</div>`;
  h.appendChild(c1);aucBars(c1,W.rows,'m_w','m_l','multibaggers','faded');
  const c2=document.createElement('div');c2.className='card';c2.innerHTML=`<h3>10x+ vs 3–5x</h3><div class="small">${n0(W.tenx.n_a)} ten-baggers vs ${n0(W.tenx.n_b)} runs that stopped between 3x and 5x.</div>`;
  h.appendChild(c2);aucBars(c2,W.tenx.rows,'m_10x','m_3to5x','10x+','3-5x');}
function durable(){const d=D.durable;if(!d)return;const h=document.getElementById('durable');
  h.insertAdjacentHTML('beforeend',`<div class="small">${n0(d.n_d)} re-ratings still +20% after 60 days vs ${n0(d.n_f)} that fell below the day −1 close. Bars right of 0.5: higher before durable re-ratings.</div>`);
  aucBars(h,d.rows,'m_d','m_f','durable','faded');}

const PROFILE_LABEL={av_mean_S:'final-week volume',av_mean_L:'volume −60…−21',cusum_av_120:'volume build-up',uv_mean_A:'volume without price',
 iv_mean_S:'idiosyncratic volume',vpin_cdf:'VPIN percentile',oi_vw_L:'buy imbalance −60…−21',oi_vw_S:'final-week imbalance',cmf20:'money flow',
 tobv_A:'toxic OBV',car_L:'return −60…−21',car_S:'final-week return',dd_ath:'distance from high',vol_ratio_A:'volatility 60d',vol_ratio_S:'final-week volatility',
 bbw_pct:'band width',n_up_jumps_A:'up-spikes',skew_A:'skew',brk_90:'vs 90d high',trend_t60:'trend',amihud_ratio_A:'illiquidity',
 toxic_breakout_S20:'toxic breakouts',toxic_mom_A:'toxic momentum',corr_mkt_A:'market correlation',rs_btc_90:'vs BTC 90d'};
function archetypes(){const A=D.archetypes;if(!A)return;const I=D.arch_info||{};
  document.getElementById('arch-note').textContent=`Gaussian-mixture clusters (k=${I.k}, chosen by BIC) of the pre-event tape of the ${n0(D.n_mb3)} re-ratings that reached 3x+ `+
   `within 180 days. Each measure is rank-mapped onto the placebo distribution first, so the profile reads as distance from ordinary tape. Lift compares how often `+
   `multibaggers vs placebo windows fall in each archetype's core region (posterior ≥ 0.6). Conversion is the share of all triggers in the archetype that `+
   `went on to 3x, against ${pct(I.base_conversion)} for all triggers. Re-fitting under four more seeds gives mean adjusted Rand index ${f2(I.ari_mean)}.`;
  const h=document.getElementById('arch');const mx=Math.max(...A.map(a=>ok(a.lift)?a.lift:0),1);
  A.forEach((a,idx)=>{const prof=Object.entries(a.profile||{}).sort((x,y)=>Math.abs(y[1])-Math.abs(x[1])).slice(0,6);
   const chips=prof.map(([k,v])=>`<span class="chip ${v>0?'up':'dn'}">${PROFILE_LABEL[k]||k} ${v>0?'+':''}${v.toFixed(1)}</span>`).join('');
   h.insertAdjacentHTML('beforeend',`<div class="arow"><div><div class="nm">A${idx+1} · ${a.name}</div>
   <div class="meta">${n0(a.n)} multibaggers (${pct(a.share)}) · median multiple ${mult(a.mult_med)} · 10x+ ${pct(a.p_10x)} · day 0–1 ${lgp(a.car01)} · durable ${pct(a.durable)}</div>
   <div class="chips">${chips}</div>
   <div class="meta mono">${(a.examples||[]).join(' · ')}</div></div>
   <div><div class="small">Lift ${ok(a.lift)?a.lift.toFixed(1)+'×':'–'}</div><div class="bar"><span style="width:${Math.min(100,100*(ok(a.lift)?a.lift:0)/mx)}%"></span></div>
   <div class="small">${pct(a.ctl)} of placebo tapes look like this</div><div class="small">Conversion ${a.conversion!=null?pct(a.conversion):'–'} of ${n0(a.n_triggers)} triggers</div></div></div>`);});}

function screen(){const S=D.screen;if(!S)return;
  document.getElementById('screen-note').textContent=`Every eligible coin on a 14-day grid (${n0(S.n)} coin-dates with a full 180-day outcome). `+
   `The label is a 3x within 180 days (base rate ${pct(S.base3)} over 2017–2026; 10x: ${pct(S.base10)}). Each measure's direction is fixed on 2017–2021; the columns `+
   `score 2022 onward only. AUC is within each date; hit rate is the share of the top-decile coins (by that measure) that went on to 3x.`;
  const t=document.getElementById('lb');const rows=S.leaderboard.slice(0,24);
  let h='<thead><tr><th>Signal</th><th>Group</th><th>Direction</th><th>AUC 2017–21</th><th>AUC 2022+</th><th>Top-decile hit rate 2022+</th><th>Base rate</th><th>Lift 2022+</th><th>Lift 2017–21</th></tr></thead><tbody>';
  (S.model||[]).forEach(M=>{h+=`<tr><td><b>${M.label}</b></td><td>model</td><td>${M.direction>0?'high':'low'}</td><td class="num">${f2(M.direction>0?M.auc_train:1-M.auc_train)}</td><td class="num">${f2(M.auc_test_dir)}</td><td class="num">${pct(M.hit_test)}</td><td class="num">${pct(M.base_test)}</td><td class="num"><b>${f2(M.lift_test)}×</b></td><td class="num">${f2(M.lift_train)}×</td></tr>`;});
  rows.forEach(r=>{h+=`<tr><td>${r.label}</td><td>${GROUP_LABEL[r.group]||r.group}</td><td>${r.direction>0?'high':'low'}</td><td class="num">${f2(r.direction>0?r.auc_train:1-r.auc_train)}</td><td class="num">${f2(r.auc_test_dir)}</td><td class="num">${pct(r.hit_test)}</td><td class="num">${pct(r.base_test)}</td><td class="num">${f2(r.lift_test)}×</td><td class="num">${f2(r.lift_train)}×</td></tr>`;});
  t.innerHTML=h+'</tbody>';
  const p=document.getElementById('pairs');let g='<thead><tr><th>Signal</th><th>Plain AUC</th><th>Toxic AUC</th><th>Plain lift</th><th>Toxic lift</th><th>Verdict</th></tr></thead><tbody>';
  (S.pairs||[]).forEach(r=>{const d=r.toxic_lift-r.plain_lift;const v=Math.abs(d)<0.05?'no difference':(d>0?'toxic overlay adds':'plain signal better');
   g+=`<tr><td>${r.signal}</td><td class="num">${f2(r.plain_auc)}</td><td class="num">${f2(r.toxic_auc)}</td><td class="num">${f2(r.plain_lift)}×</td><td class="num">${f2(r.toxic_lift)}×</td><td>${v}</td></tr>`;});
  p.innerHTML=g+'</tbody>';}
function recipes(){const R=D.recipes;if(!R||!R.length)return;const I=D.recipes_info||{};
  document.getElementById('rec-note').textContent=`A coin passes a signal when it ranks in that date's top ${Math.round(100*(1-I.quantile))}% on it (direction fixed on 2017–21). `+
   `Combinations of the ${I.n_signals} strongest 2017–21 signals are ranked on 2017–21 lift and then scored on 2022 onward. Base rates: ${pct(I.base_train)} (2017–21), ${pct(I.base_test)} (2022+).`;
  let h='<thead><tr><th>Screen</th><th>Coin-dates 2017–21</th><th>Lift 2017–21</th><th>Coin-dates 2022+</th><th>3x hit rate 2022+</th><th>Lift 2022+</th></tr></thead><tbody>';
  R.forEach(r=>{h+=`<tr><td class="long">${r.labels.join(' <b>+</b> ')}</td><td class="num">${n0(r.n_train)}</td><td class="num">${f2(r.lift_train)}×</td><td class="num">${n0(r.n_test)}</td><td class="num">${pct(r.hit_test)}</td><td class="num"><b>${f2(r.lift_test)}×</b></td></tr>`;});
  document.getElementById('recipes').innerHTML=h+'</tbody>';}
function triggerLb(){const T=D.trigger_lb;if(!T||!T.length)return;
  document.getElementById('tlb-note').textContent=`Triggers only. Direction is set on 2017–21 triggers; the table scores 2022 onward: the 3x rate among the top fifth `+
   `of triggers by each measure, against ${pct(T[0].base_test)} for all 2022+ triggers. Day-0 measures are known at that day's close.`;
  let h='<thead><tr><th>Measure</th><th>Group</th><th>Direction</th><th>AUC 2017–21</th><th>AUC 2022+</th><th>3x rate, top fifth</th><th>Lift</th><th>Triggers 2022+</th></tr></thead><tbody>';
  T.slice(0,16).forEach(r=>{h+=`<tr><td>${r.label}</td><td>${GROUP_LABEL[r.group]||r.group}</td><td>${r.direction>0?'high':'low'}</td><td class="num">${f2(r.auc_train)}</td><td class="num">${f2(r.auc_test)}</td><td class="num">${pct(r.hit_test)}</td><td class="num"><b>${f2(r.lift_test)}×</b></td><td class="num">${n0(r.n_test)}</td></tr>`;});
  document.getElementById('tlb').innerHTML=h+'</tbody>';}
function archOos(){const A=D.arch_oos;if(!A||!A.length)return;
  let h='<thead><tr><th>Archetype (2017–21 fit)</th><th>Conversion 2017–21</th><th>2022+ triggers in it</th><th>Conversion 2022+</th><th>All 2022+ triggers</th><th>Lift vs placebo 2022+</th></tr></thead><tbody>';
  A.slice().sort((a,b)=>(b.conversion_test??-1)-(a.conversion_test??-1)).forEach(r=>{h+=`<tr><td class="long">${r.name}</td><td class="num">${pct(r.train_conversion)}</td><td class="num">${n0(r.n_test)}</td><td class="num"><b>${r.conversion_test!=null?pct(r.conversion_test):'–'}</b></td><td class="num">${pct(r.base_test)}</td><td class="num">${f2(r.lift_test)}×</td></tr>`;});
  document.getElementById('archoos').innerHTML=h+'</tbody>';}
function cv(){const h=document.getElementById('cv');if(!D.cv)return;
  D.cv.filter(c=>c.model==='gbm').forEach(c=>{h.insertAdjacentHTML('beforeend',`<div class="tile"><span class="k">${c.sample} · ${c.split}</span>
  <span class="v num">${f2(c.auc)}</span><span class="k">AUC · ${pct(c.cap)} caught at a 10% false-positive rate · n=${n0(c.n)}</span></div>`);});}

function onchain(){const O=D.onchain;if(!O)return;const cov=O.coverage||{},tok=O.tokens||{};
  const mx=Math.max(...Object.values(cov));
  document.getElementById('oc-note').textContent=`Coverage is partial: CoinMetrics community data carries network activity for about a hundred large coins and a market-cap estimate `+
   `for ~600; DefiLlama carries TVL and fees for ~880 protocol tokens. Up to ${n0(mx)} events have a given measure. Etherscan transfer-level data `+
   `(holder growth, first-time receivers for ERC-20s) needs an ETHERSCAN_API_KEY in the environment; the client is in the code but was not run.`;
  gridTable('ocgrid',O,true,null);
  const rows=(O.winners||[]).filter(r=>ok(r.auc)).slice(0,10);const h=document.getElementById('ocwin');
  if(rows.length){h.insertAdjacentHTML('beforeend','<div class="small">On-chain measures: 3x+ multibaggers vs faded pops (events with coverage only).</div>');aucBars(h,rows,'m_w','m_l','multibaggers','faded');}}

function validation(){const t=document.getElementById('val');if(!D.validation)return;
  let h='<thead><tr><th>Case</th><th>Date</th><th>Direction</th><th>Trigger</th><th>Day-0 return</th><th>Run-up −60…−1</th><th>Final-week volume</th><th>Best multiple 180d</th><th>Return 60d</th><th>Score pct</th></tr></thead><tbody>';
  D.validation.forEach(v=>{h+=`<tr><td class="long">${v.symbol} · ${v.desc}</td><td class="num">${v.date}</td><td>${v.sign>0?'Positive':'Negative'}</td><td>${v.trigger?'Yes':'No'}</td><td class="num ${v.d0_ret>0?'pos':'neg'}">${sgn(v.d0_ret)}</td><td class="num">${lgp(v.car_pre)}</td><td class="num">${f2(v.av_S)}</td><td class="num">${mult(v.mult_180)}</td><td class="num ${v.r_60>0?'pos':'neg'}">${lgp(v.r_60)}</td><td class="num">${pct(v.score_pct)}</td></tr>`;});
  t.innerHTML=h+'</tbody>';}
function live(){const L=D.live;if(!L)return;
  document.getElementById('live-note').textContent=`As of ${D.asof}. ${n0(D.live_n)} coins pass the history screen and trade at least $100k a day on six of the last seven days `+
   `(${n0(D.live_excluded)} more fail that live-tape check). Rows are ranked on the average of two percentiles: the event model (pre-event tape of 3x+ multibaggers vs matched placebos, `+
   `placed among placebo windows) and the cross-sectional screen (within-date ranks, trained on 2017–21). Even the top of the list historically converts to 3x `+
   `only a minority of the time. Treat it as a research queue, not a buy list.`;
  const t=document.getElementById('live');let h='<thead><tr><th>Coin</th><th>Event-model pct</th><th>Screen pct</th><th>Archetype</th><th>$ volume, last 7d</th><th>Final-week volatility</th><th>VPIN pct</th><th>Toxic breakouts</th><th>60d max drawdown</th><th>Run-up 60d</th><th>From high</th></tr></thead><tbody>';
  L.slice(0,30).forEach(r=>{h+=`<tr><td>${r.symbol.replace(/USD$/,'')} <span class="small">${r.name||''}${r.sector?' · '+r.sector:''}</span></td><td class="num">${pct(r.score_pct)}</td><td class="num">${pct(r.screen_pct)}</td><td class="long">${r.archetype}</td><td class="num">${money(r.dv7)}</td><td class="num">${f2(r.vol_ratio_S)}</td><td class="num">${pct(r.vpin_cdf)}</td><td class="num">${n0(r.toxic_breakout_S20)}</td><td class="num">${lgp(r.max_dd_A)}</td><td class="num">${lgp(r.car_A)}</td><td class="num">${lgp(r.dd_ath)}</td></tr>`;});
  t.innerHTML=h+'</tbody>';}
function useCards(){const U=D.use||[];document.getElementById('use').innerHTML=U.map(u=>`<div class="card"><h3>${u.h}</h3><p class="small">${u.p}</p></div>`).join('');}
function takes(){const T=D.takes||{};['b','d','g'].forEach(k=>{const e=document.getElementById('take-'+k);if(e)e.textContent=T[k]||'';});
  document.getElementById('foot').innerHTML=(D.footer||[]).map(x=>`<span>${x}</span>`).join('');}

header();fams();takes();grid();winners();durable();archetypes();archOos();screen();recipes();triggerLb();cv();onchain();validation();live();useCards();
document.getElementById('gridtog').addEventListener('click',()=>{gridAll=!gridAll;grid();});
pathsChart('pav','av','Abnormal log volume (z vs own baseline)',v=>v.toFixed(1),-60,30,[-60,-40,-20,0,20]);
pathsChart('pcar','car','Median cumulative abnormal return from day −60',v=>(100*(Math.exp(v)-1)).toFixed(0)+'%',-60,30,[-60,-40,-20,0,20]);
pathsChart('plong','car','Median cumulative abnormal return, day −60 to +180',v=>(100*(Math.exp(v)-1)).toFixed(0)+'%',-60,180,[-60,0,30,60,90,120,150,180]);
legend();
</script>
"""


def _clean(o):
    if isinstance(o, float):
        return None if (math.isnan(o) or math.isinf(o)) else round(o, 6)
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_clean(v) for v in o]
    return o


def build(extra: dict | None = None, out=None) -> str:
    atlas = json.loads((DATA_DIR / "atlas.json").read_text())
    if extra:
        atlas.update(extra)
    data = json.dumps(_clean(atlas), separators=(",", ":")).replace("</", "<\\/")
    html = TEMPLATE.replace("__DATA__", data)
    out = out or (DATA_DIR / "atlas.html")
    out.write_text(html)
    return str(out)


if __name__ == "__main__":
    print(build())
