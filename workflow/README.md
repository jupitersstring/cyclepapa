# Fund Activity Research — Workflow Modules

This directory contains the build pipeline and underlying research data for
the `fund_activity_last_6mo.xlsx` workbook.

## Build pipeline (Python scripts)

Run these scripts in order to (re)build the workbook from the research
markdown files in `research/`. Each script reads from `/tmp/research_*.md`
paths by default — change to `./research/*.md` if running from the repo.

```
build_themed.py              Initial organization: PB saved searches -> themes
                              (produces pb_searches_by_theme.xlsx)

build_activity_xlsx.py       Ingests each research markdown -> per-fund sheet
                              in fund_activity_last_6mo.xlsx. Parses the
                              four-category structure (Cat 1-4) and writes
                              one row per (fund, category, position).

build_synthesis.py           Cross-fund analysis. Builds:
                                - Asymmetric Summary
                                - Consensus Buys
                                - Highest Conviction
                                - Activist Catalysts
                                - Multi-Fund New Inits

build_conviction_adds.py     Adds two synthesis sheets:
                                - Conviction Adds (all 483 add events)
                                - Micro-Cap Conviction Adds (358 filtered)

build_watchlist.py           User-Suggested Watchlist sheet (239 rows from
                              first user research dump).

build_watchlist_v2.py        Watchlist v2 - Warrants + Hidden Superinvestors
                              (173 rows, 50 warrant-highlighted).

build_13d_sweep_sheet.py     13D Sweep Last 14 Days. Recurring snapshot of
                              fresh SEC EDGAR filings. Re-run on any cadence.

build_sitg_spotlight.py      SITG Smallcap Spotlight. Filters universe to
                              39 fat-pitch SITG funds + extracts their
                              top conviction position from per-fund tabs.
```

## Research markdown files (`research/`)

24 markdown files containing the underlying primary research, plus a sweep:

```
research_us_activists.md           US activists Tier 1 (Elliott, Icahn, Third
                                    Point, Trian, Starboard, etc.)
research_us_activists_more.md      US activists Tier 2
research_activists_t3.md           US activists Tier 3 (small-cap)

research_smallcap_specialsits.md   Small-cap multibagger / special sits Tier 1
research_smallcap_tier2.md         Tier 2
research_smallcap_value_t3.md      Tier 3 deep value

research_intl_distressed.md        International activist + distressed
research_intl_more.md              International activist Tier 2
research_europe_asia_t2.md         European + Asia Tier 2
research_japan_distressed_t3.md    Japan + distressed Tier 3

research_distressed_eventdriven.md Distressed event-driven Tier 2

research_tiger_cubs.md             Tiger Cubs + L/S legends
research_legendary_fos.md          Legendary family offices
research_value_multistrat.md       Value + multi-strat legends

research_biotech_specialists.md    Biotech specialists
research_smaller_activists.md      Smaller activists / special sits Tier 4
research_quality_em.md             Global quality + EM specialists
research_megamulti.md              Mega multi-strats / quants
research_microcap_intl_t4.md       Microcap tactical + intl Tier 4
research_family_office_filers.md   Family office / individual filers
research_small_concentrated_t4.md  Small concentrated activists Tier 4

research_skin_game_A.md            Tier A skin-in-the-game legends (Abrams,
                                    Mecham, Greenberg/Brave Warrior, Lou,
                                    Hawkins, Wachenheim, Berkowitz, Stahl,
                                    Burry, Greenblatt)
research_value_B.md                Tier B concentrated value compounders
                                    (Akre, Weitz, Oakmark/Nygren, Robotti,
                                    FPA Crescent/Romick, Russo, Spier,
                                    Miller, Cobas, Fundsmith, Lindsell Train)
research_shorts_value_C.md         Tier C elite shorts + concentrated value
                                    (Cohodes, Muddy Waters, Sequoia Fund,
                                    Davis, Ariel)

research_warrants.md               Warrant specialists (Periscope, Polar,
                                    Glazer, Radcliffe, Karpus, Bulldog,
                                    Eric Sprott personal, Sprott Inc,
                                    Crescat, Lepard/EMA, Universa, ThreeD)

sweep_13d_may_2026.md              13D/G sweep Nov 2025 - May 2026
```

## Markdown format (for new fund research)

Each fund block follows this exact template:

```markdown
## Fund Name (key person)

**Sources used:** [list of URLs]

### (1) Highest conviction positions (recent adds)

| Ticker | Company | % of Portfolio | $ Value | Change | Source |

### (2) Recent >=5% disclosures (last 6 months)

| Ticker | Company | % of Co. | Filing date | Type | Source |

### (3) New positions sized large

| Ticker | Company | Size | Quarter | Source |

### (4) Existing positions materially increased

| Ticker | % / $ change | New weight | Source |

### Notes

Free-text on the fund's recent activity, strategy, etc.
```

The parser in `build_activity_xlsx.py` splits on `^## ` for fund blocks
and recognizes `### (1)` / `### (2)` / `### (3)` / `### (4)` / `### Notes`
for section headings.

## To add a new batch of funds

1. Dispatch a research agent with the per-fund format template (see above).
2. Save output to `research/research_<group_name>.md`.
3. Add the file path to `MD_FILES` dict in `build_activity_xlsx.py` and the
   other three build scripts.
4. Run scripts in sequence:
   - `python3 build_activity_xlsx.py`
   - `python3 build_synthesis.py`
   - `python3 build_conviction_adds.py`
   - `python3 build_watchlist.py` (optional, only if updating that sheet)
5. Commit and push.

## To run a fresh 13D sweep

1. Dispatch a research agent to scan SEC EDGAR + stocktitan + whalewisdom
   for filings in the last N days.
2. Save output to `research/sweep_13d_<window>.md`.
3. Edit `ROWS` list in `build_13d_sweep_sheet.py` to ingest the new data.
4. Run `python3 build_13d_sweep_sheet.py`.
5. Commit the updated workbook.

## Dependencies

```
Python 3.10+
openpyxl
```

That's it. No external APIs hit directly — the research is done by
delegated agents that query SEC EDGAR, WhaleWisdom, SEDAR+, stocktitan,
etc. and return structured markdown.
