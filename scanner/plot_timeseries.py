import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np, pandas as pd
from scanner import backtest as BT, highfreq as HF
from scanner.sources import prices as PX, monthly as MO, quarterly as QT
from scanner.archetypes import lookup

INK='#000';LAPIS='#061933';CRIMSON='#7a0019';MUTED='#3f3f3f';GOLD='#9a7d0a';PAPER='#fff'
plt.rcParams.update({'font.family':'serif','font.serif':['Liberation Serif','Times New Roman'],
  'figure.facecolor':PAPER,'axes.facecolor':PAPER,'savefig.facecolor':PAPER,
  'axes.edgecolor':INK,'axes.linewidth':0.7,'font.size':9})

def country_tearsheet(iso, fname):
    name=lookup(iso).name
    sc=BT.reconstruct_score(iso); px=PX.annual_prices(iso)
    if sc is None or px is None: print(iso,'no data'); return False
    fig=plt.figure(figsize=(13,11))
    gs=fig.add_gridspec(3,1,height_ratios=[1.15,1,1],hspace=0.34)
    yrs=[y for y in sc.index if y in px.index and 1990<=y<=2024]
    pv=px.reindex(yrs)

    # A: composite score bars + price (dual, log)
    ax=fig.add_subplot(gs[0]); s=sc['gscore_smooth'].reindex(yrs)
    ax.bar(yrs,s.values,color=[LAPIS if v>=0 else CRIMSON for v in s.values],width=0.8,alpha=0.55)
    ax.axhline(0,color=MUTED,lw=0.6); ax.set_ylabel('Godley composite (smoothed z)',fontsize=9)
    ax.set_ylim(-max(1.3,abs(s).max()*1.1),max(1.3,abs(s).max()*1.1))
    ax2=ax.twinx(); ax2.plot(yrs,pv.values,color=INK,lw=1.5); ax2.set_yscale('log')
    ax2.set_ylabel('equity index (log)',fontsize=9)
    ax.set_title(f'{name} — composite sectoral-balance score vs equity price',fontsize=11,fontweight='bold',loc='left')
    ax.set_zorder(ax2.get_zorder()+1); ax.patch.set_visible(False)

    # B: the four annual factor legs as lines
    axb=fig.add_subplot(gs[1])
    cols={'profit_fuel':(LAPIS,'-'),'external':(GOLD,'-'),'valuation':(MUTED,'--'),'credit':(CRIMSON,':')}
    for k,(c,ls) in cols.items():
        axb.plot(yrs,sc[k].reindex(yrs).values,color=c,ls=ls,lw=1.6,label=k.replace('_',' '))
    axb.axhline(0,color=INK,lw=0.5); axb.set_ylabel('factor z (vs own history)',fontsize=9)
    axb.legend(ncol=4,fontsize=8,frameon=False,loc='upper left')
    axb.set_title('Factor legs — profit fuel & external lead, valuation mean-reverts, credit is coincident',fontsize=10.5,fontweight='bold',loc='left')

    # C: high-frequency measures (monthly money growth + quarterly credit impulse) + price
    axc=fig.add_subplot(gs[2])
    rmg=HF.real_money_growth(iso); ci=HF.credit_impulse(iso)
    plotted=False
    if rmg is not None:
        axc.plot(rmg.index.year+ (rmg.index.month-1)/12, rmg.values, color=CRIMSON, lw=1.1, label='real money growth % (monthly, Process 3)'); plotted=True
    if ci is not None:
        cidx=ci.index.year+(ci.index.month-1)/12
        axc.plot(cidx, ci['credit_impulse'].values, color=GOLD, lw=1.1, label='credit impulse (quarterly, Biggs-Mayer)'); plotted=True
    axc.axhline(0,color=INK,lw=0.5); axc.set_ylabel('% / pp',fontsize=9); axc.set_xlim(1990,2025)
    if plotted: axc.legend(fontsize=8,frameon=False,loc='upper left')
    axc2=axc.twinx(); axc2.plot(yrs,pv.values,color=INK,lw=1.0,alpha=0.5); axc2.set_yscale('log'); axc2.set_ylabel('price (log)',fontsize=8)
    axc.set_title('High-frequency legs — the fast Godley measures (money Process 3, credit impulse)',fontsize=10.5,fontweight='bold',loc='left')
    axc.set_zorder(axc2.get_zorder()+1); axc.patch.set_visible(False)

    fig.suptitle(f'Godley time-series tearsheet — {name}',fontsize=14,fontweight='bold',y=0.995)
    fig.text(0.5,0.004,'Score & factors reconstructed from World Bank + IMF annual data (z-scored vs own history, no look-ahead). '
      'High-frequency from OECD money+CPI and BIS credit. Prices: OECD share-price index. All keyless public data.',ha='center',fontsize=7.5,color=MUTED)
    plt.savefig(fname,dpi=105,bbox_inches='tight'); plt.close()
    print('saved',fname); return True


def generate(isos, outdir="scanner"):
    import os
    done=[]
    for iso in isos:
        f=os.path.join(outdir,f"timeseries_{iso}.png")
        if country_tearsheet(iso,f): done.append(iso)
    return done


if __name__=="__main__":
    import sys
    isos=sys.argv[1:] or ["US","KR","JP","GB"]
    print("generated:", generate(isos))
