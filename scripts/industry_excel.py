"""Build a downloadable Excel workbook of industries ranked by behaviour change
+ growth (global, region x industry, top names, legend).

Reads cache/scored.parquet (run `analyze` first). Usage:
    PYTHONPATH=. python scripts/industry_excel.py
Output: UK_US_EU_industry_behaviour_growth.xlsx (git-ignored artifact).
"""
import warnings, pandas as pd, numpy as np
warnings.filterwarnings("ignore")
from datetime import date
s=pd.read_parquet("cache/scored.parquet"); op=s[s.is_operating].copy()

def agg(df, keys):
    g=df.groupby(keys).agg(
        n=("symbol","count"),
        rev_growth_med=("revenue_growth","median"),
        ebitda_growth_med=("ebitda_growth","median"),
        earnings_growth_med=("earnings_growth","median"),
        pct_sales_accel=("revenue_accel",lambda x:(x>0).mean()),
        pct_ebitda_accel=("ebitda_accel_abs",lambda x:(x>0).mean()),
        pct_broad_inflection=("broad_inflection","mean"),
        pct_margin_expanding=("margin_delta3",lambda x:(x>0).mean()),
        fwd_pe_med=("forwardPE",lambda x:x[x>0].median()),
        ev_ebitda_med=("enterpriseToEbitda",lambda x:x[x>0].median()),
        ret_12m_med=("ret_12m","median"),
        ret_24m_med=("ret_24m","median"),
    ).reset_index()
    # BEHAVIOUR CHANGE = breadth of acceleration + inflection + margin expansion
    g["behaviour_change"]=g[["pct_sales_accel","pct_ebitda_accel","pct_broad_inflection","pct_margin_expanding"]].mean(axis=1)
    # GROWTH = median sales + ebitda growth, percentile-ranked then averaged
    gr=pd.concat([g["rev_growth_med"].rank(pct=True),g["ebitda_growth_med"].rank(pct=True)],axis=1).mean(axis=1)
    g["growth_rank"]=gr
    # COMBINED SCORE: most changing behaviour AND best growth
    g["score"]=0.55*g["behaviour_change"]+0.45*g["growth_rank"]
    return g.sort_values("score",ascending=False)

glob=agg(op,["industry"]); glob=glob[glob.n>=8]
ci=agg(op,["region","industry"]); ci=ci[ci.n>=6]

# Top names per top-10 global industry (actionable detail)
top_inds=glob.head(12)["industry"].tolist()
names=op[op.industry.isin(top_inds)].copy()
names["name_score"]=(names["revenue_growth"].rank(pct=True)+names["ebitda_accel_abs"].rank(pct=True))/2
namecols=["industry","region","symbol","name","size_bucket","revenue_growth","ebitda_growth","earnings_growth","ebitda_margin","margin_delta3","enterpriseToEbitda","forwardPE","ret_24m"]
names=names.sort_values(["industry","name_score"],ascending=[True,False])[namecols]

# ---- WRITE FORMATTED XLSX ----
path="industry_behaviour_growth.xlsx"
w=pd.ExcelWriter(path, engine="xlsxwriter")
gcols=["industry","n","score","behaviour_change","growth_rank","rev_growth_med","ebitda_growth_med","earnings_growth_med","pct_sales_accel","pct_ebitda_accel","pct_broad_inflection","pct_margin_expanding","fwd_pe_med","ev_ebitda_med","ret_12m_med","ret_24m_med"]
glob[gcols].to_excel(w,sheet_name="Global Industries",index=False,startrow=1,header=False)
cicols=["region","industry","n","score","behaviour_change","growth_rank","rev_growth_med","ebitda_growth_med","pct_sales_accel","pct_ebitda_accel","pct_broad_inflection","pct_margin_expanding","fwd_pe_med","ev_ebitda_med","ret_24m_med"]
ci.sort_values("score",ascending=False)[cicols].to_excel(w,sheet_name="By Region x Industry",index=False,startrow=1,header=False)
names.to_excel(w,sheet_name="Top Names (top industries)",index=False,startrow=1,header=False)

wb=w.book
hdr=wb.add_format({"bold":True,"bg_color":"#1F4E78","font_color":"white","border":1,"text_wrap":True,"valign":"top"})
pct=wb.add_format({"num_format":"0%"}); f2=wb.add_format({"num_format":"0.00"}); f1=wb.add_format({"num_format":"0.0"})
def fmt(sheet, df, cols, pct_cols, score_col=None):
    ws=w.sheets[sheet]
    for i,c in enumerate(cols):
        ws.write(0,i,c,hdr)
        width=30 if c in ("name","industry") else (12 if len(c)>9 else 10)
        if c in pct_cols: ws.set_column(i,i,12,pct)
        elif c in ("fwd_pe_med","ev_ebitda_med","enterpriseToEbitda","forwardPE","ebitda_margin"): ws.set_column(i,i,11,f1)
        elif c in ("rev_growth_med","ebitda_growth_med","earnings_growth_med","ret_12m_med","ret_24m_med","ret_24m","revenue_growth","ebitda_growth","earnings_growth","margin_delta3","score","behaviour_change","growth_rank"): ws.set_column(i,i,12,f2)
        else: ws.set_column(i,i,width)
    ws.freeze_panes(1,0); ws.autofilter(0,0,len(df),len(cols)-1)
    if score_col is not None:
        ws.conditional_format(1,score_col,len(df),score_col,{"type":"3_color_scale","min_color":"#F8696B","mid_color":"#FFEB84","max_color":"#63BE7B"})
pctc={"pct_sales_accel","pct_ebitda_accel","pct_broad_inflection","pct_margin_expanding","behaviour_change","growth_rank","score"}
fmt("Global Industries",glob,gcols,pctc,score_col=gcols.index("score"))
fmt("By Region x Industry",ci,cicols,pctc,score_col=cicols.index("score"))
fmt("Top Names (top industries)",names,namecols,set())

# Legend sheet
leg=wb.add_worksheet("Legend"); leg.set_column(0,0,26); leg.set_column(1,1,90)
rows=[("Field","Definition"),
("score","0.55*behaviour_change + 0.45*growth_rank — ranks industries with the most changing behaviour AND best growth"),
("behaviour_change","Mean of: % names with accelerating sales, % accelerating EBITDA, % broad inflection, % margin expanding"),
("growth_rank","Cross-industry percentile of median sales & EBITDA growth"),
("rev/ebitda/earnings_growth_med","Median latest YoY growth across names in the industry"),
("pct_sales_accel / pct_ebitda_accel","Share of names whose growth RATE is rising (2nd derivative > 0)"),
("pct_broad_inflection","Share with >=2 of revenue/EBITDA/earnings inflecting"),
("pct_margin_expanding","Share with EBITDA margin expanding over last 3 yrs (all-positive)"),
("fwd_pe_med / ev_ebitda_med","Median forward P/E and EV/EBITDA (positive only)"),
("ret_12m/24m_med","Median trailing price return — low = market hasn't reacted"),
("Universe","Operating companies only (warrants/preferreds/CEFs/shells excluded). Global primary listings: US, EU, UK, JP, Greater China (CN/HK/TW), KR, SEA, ANZ, CA, LATAM, MEA."),
("Source / date",f"yfinance + financedatabase, generated {date.today().isoformat()}. Research scaffold, not advice."),
]
for r,(a,b) in enumerate(rows):
    leg.write(r,0,a,hdr if r==0 else wb.add_format({"bold":True,"valign":"top"})); leg.write(r,1,b,wb.add_format({"text_wrap":True,"valign":"top"}))
w.close()
print("WROTE",path,"| global inds:",len(glob),"| region-inds:",len(ci),"| names:",len(names))
print("\nTop 12 industries by (behaviour change + growth):")
print(glob.head(12)[["industry","n","score","behaviour_change","rev_growth_med","ebitda_growth_med","pct_margin_expanding"]].round(3).to_string(index=False))
