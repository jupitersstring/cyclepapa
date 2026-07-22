CREATE TABLE candidates (
  ticker TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  sector TEXT,
  currency TEXT NOT NULL DEFAULT 'USD',
  price REAL,
  price_asof TEXT,
  mcap_m REAL,                 -- $M, same currency as price
  shares_out_m REAL,           -- derived = mcap_m/price unless sourced
  shares_method TEXT,          -- 'sourced' | 'derived'
  tier TEXT NOT NULL,
  verification_status TEXT NOT NULL,
  known_issues TEXT,
  kill_criteria TEXT,
  factor_tags TEXT,
  source_url TEXT NOT NULL DEFAULT '',
  CHECK (price IS NULL OR price_asof IS NOT NULL)
);
CREATE TABLE signals (
  id INTEGER PRIMARY KEY,
  ticker TEXT NOT NULL,
  signal_type TEXT NOT NULL,   -- FORM4_BUY|FORM4_SELL|13D|13G|FUND_ADD|BUYBACK|BID|SALE_PROCESS|FAMILY
  actor TEXT NOT NULL,
  pct_of_company REAL CHECK (pct_of_company IS NULL OR pct_of_company BETWEEN 0 AND 100),
  pct_of_book REAL CHECK (pct_of_book IS NULL OR pct_of_book BETWEEN 0 AND 100),
  amount_usd_m REAL,
  cost_basis REAL,
  event_date TEXT,
  asof TEXT NOT NULL,
  source_url TEXT NOT NULL,
  note TEXT
);
CREATE TABLE catalysts (
  id INTEGER PRIMARY KEY,
  ticker TEXT NOT NULL,
  description TEXT NOT NULL,
  expected_date TEXT,          -- NULL = unscheduled
  status TEXT NOT NULL DEFAULT 'PENDING',  -- PENDING|HAPPENED|EXPIRED_CHECK|DEAD
  outcome TEXT,
  source_url TEXT
);
CREATE TABLE prices (
  ticker TEXT NOT NULL, date TEXT NOT NULL, close REAL NOT NULL, volume REAL,
  PRIMARY KEY (ticker, date)
);
CREATE TABLE liquidity (
  ticker TEXT PRIMARY KEY,
  adv_shares REAL, adv_usd_m REAL, asof TEXT NOT NULL,
  days_to_exit_1pct_adv10 REAL  -- days to exit a position = 1% of mcap at 10% of ADV
);
CREATE TABLE edgar_filings (
  accession TEXT PRIMARY KEY,
  ticker TEXT, cik TEXT NOT NULL, form TEXT NOT NULL, filed TEXT NOT NULL,
  primary_doc TEXT, url TEXT NOT NULL, note TEXT
);
CREATE TABLE form4_transactions (
  id INTEGER PRIMARY KEY,
  accession TEXT NOT NULL, ticker TEXT, owner TEXT, role TEXT,
  trans_date TEXT, code TEXT, shares REAL, price REAL, acquired INTEGER,
  source_url TEXT NOT NULL
);
CREATE TABLE archetype_members (
  archetype TEXT NOT NULL, ticker TEXT NOT NULL,
  thesis TEXT, valuation TEXT, catalyst TEXT, variant TEXT, smart_money TEXT,
  PRIMARY KEY (archetype, ticker)
);
CREATE TABLE backtest_events (
  id INTEGER PRIMARY KEY,
  ticker TEXT NOT NULL, bucket TEXT NOT NULL, event_date TEXT NOT NULL,
  description TEXT NOT NULL, source_note TEXT
);
CREATE TABLE backtest_results (
  event_id INTEGER PRIMARY KEY,
  entry_date TEXT, entry_px REAL,
  ret_6m REAL, ret_12m REAL, ret_18m REAL,
  spy_6m REAL, spy_12m REAL, spy_18m REAL,
  excess_6m REAL, excess_12m REAL, excess_18m REAL
);
CREATE TABLE discovery (
      ticker TEXT PRIMARY KEY, issuer TEXT, n_filings INTEGER, n_buyers INTEGER,
      total_usd_m REAL, top_buyer TEXT, top_role TEXT, avg_px REAL,
      last_close REAL, off_52w_high REAL, off_52w_low REAL,
      window TEXT, asof TEXT);
CREATE TABLE discovery_13d (
      cik TEXT, company TEXT, filed TEXT, path TEXT, PRIMARY KEY (cik, filed));
CREATE TABLE discovery_13d_subjects (
      accession TEXT PRIMARY KEY, subject TEXT, subject_cik TEXT, ticker TEXT,
      filer_hint TEXT, filed TEXT, last_close REAL, off_52w_high REAL, asof TEXT);
CREATE TABLE insider_clusters (
      ticker TEXT PRIMARY KEY, window_start TEXT, window_end TEXT,
      n_insiders INTEGER, total_usd_m REAL, avg_price REAL,
      top_buyer TEXT, top_buyer_usd_m REAL, trigger TEXT, asof TEXT);
CREATE TABLE base_rates (
      factor TEXT PRIMARY KEY, hit_rate REAL, avg_excess_12m REAL, sample_n INTEGER);
CREATE TABLE fund_meta (
      fund TEXT PRIMARY KEY, fund_group TEXT, source_block TEXT, total_rows INTEGER);
CREATE TABLE fund_positions (
      id INTEGER PRIMARY KEY, fund TEXT, ticker TEXT, company TEXT, section INTEGER,
      pct_value REAL, pct_kind TEXT, dollar_m REAL, change_text TEXT,
      event_date TEXT, raw_text TEXT, asof TEXT);
CREATE TABLE expected_return (
      ticker TEXT PRIMARY KEY, tags_n INTEGER, weighted_excess_12m REAL,
      best_tag TEXT, best_tag_excess REAL, worst_tag TEXT, worst_tag_excess REAL,
      cluster_live INTEGER, asof TEXT);
CREATE TABLE archetype_member_status (
      archetype TEXT, ticker TEXT, status TEXT, er REAL, factor_tags TEXT,
      thesis TEXT, PRIMARY KEY (archetype, ticker));
CREATE TABLE archetype_status (
      archetype TEXT PRIMARY KEY, mapped_factor TEXT, base_rate_excess REAL,
      members_total INTEGER, members_live_t1 INTEGER, members_live_t2 INTEGER,
      members_live_t3 INTEGER, members_demoted INTEGER, members_graduated INTEGER,
      members_dead INTEGER, members_untracked INTEGER, members_excluded INTEGER,
      best_member TEXT, best_member_er REAL, verdict TEXT);
CREATE TABLE "activist_catalysts" ("ticker" TEXT, "n_threshold_filings" INTEGER, "funds_5pct" TEXT, "n_funds_positive" INTEGER, "max_pct_any_fund" REAL, "flags" TEXT, "sample_notes" TEXT);
CREATE TABLE "consensus_buys" ("ticker" TEXT, "n_funds" INTEGER, "max_pct" TEXT, "flags" REAL, "funds" INTEGER, "narratives" INTEGER);
CREATE TABLE "conviction_adds" ("ticker" TEXT, "n_funds_adding" INTEGER, "n_new_inits" INTEGER, "sum_dollar_m" REAL, "max_dollar_m" REAL, "max_pct_add" REAL, "funds" TEXT, "narratives" TEXT);
CREATE TABLE "fund_canon" ("fund" TEXT, "canon" TEXT);
CREATE TABLE "fund_cik_map" ("fund" TEXT, "cik" INTEGER, "edgar_name" TEXT, "confidence" REAL, "has_13f" INTEGER, "asof" TEXT);
CREATE TABLE "fund_resolution_state" ("fund" TEXT, "n_candidates" INTEGER, "best_cik" INTEGER, "best_conf" REAL, "status" TEXT, "asof" TEXT);
CREATE TABLE "highest_conviction" ("ticker" TEXT, "n_funds" REAL, "max_pct_book" TEXT, "n_threshold" INTEGER, "n_hyper" INTEGER, "flags" INTEGER, "top_funds" TEXT);
CREATE TABLE "microcap_conviction_adds" ("ticker" TEXT, "n_funds_adding" INTEGER, "n_new_inits" INTEGER, "sum_dollar_m" REAL, "max_dollar_m" REAL, "max_pct_add" REAL, "funds" TEXT, "narratives" TEXT);
CREATE TABLE "multi_fund_new_inits" ("ticker" TEXT, "n_funds_initiating" INTEGER, "sum_dollar_m" TEXT, "funds" INTEGER);
CREATE TABLE "ticker_valuation" ("ticker" TEXT, "cik" INTEGER, "ebitda_ttm" REAL, "book_value" REAL, "net_debt" REAL, "ev_m" REAL, "ev_ebitda" REAL, "pb_ratio" REAL, "ebitda_is_ebit_fallback" INTEGER, "asof" TEXT);
CREATE TABLE fund_13f_holdings (
      fund TEXT, cik TEXT, accession TEXT, filed TEXT,
      issuer TEXT, cusip TEXT, ticker TEXT, value_k INTEGER, shares INTEGER,
      sh_type TEXT, pct_book REAL,
      PRIMARY KEY (fund, accession, cusip));
CREATE INDEX idx_13f_ticker ON fund_13f_holdings(ticker);
CREATE INDEX idx_13f_fund ON fund_13f_holdings(fund);
CREATE TABLE fund_13f_state (
      fund TEXT PRIMARY KEY, cik TEXT, last_accession TEXT, last_filed TEXT,
      n_holdings INTEGER, total_value_k INTEGER, ingested_at TEXT);
CREATE TABLE holder_13d (
      holder TEXT, holder_cik TEXT, form TEXT, filed TEXT, accession TEXT,
      subject_name TEXT, subject_cik TEXT, subject_ticker TEXT,
      pct_class REAL, source_url TEXT,
      PRIMARY KEY (holder_cik, accession));
CREATE TABLE catalysts_8k (
      ticker TEXT, cik TEXT, accession TEXT, filed TEXT,
      items TEXT,                -- comma-separated item codes
      item_labels TEXT,          -- human-readable labels
      has_ma INTEGER, has_director INTEGER, has_earnings INTEGER,
      has_bankruptcy INTEGER, has_pipe INTEGER, has_control INTEGER,
      source_url TEXT,
      PRIMARY KEY (cik, accession));
CREATE INDEX idx_8k_ticker ON catalysts_8k(ticker);
CREATE INDEX idx_8k_filed ON catalysts_8k(filed);
CREATE UNIQUE INDEX ux_form4_txn
        ON form4_transactions(accession, owner, code, trans_date, shares, COALESCE(price,-1));
CREATE TABLE ticker_yf ("ticker" TEXT PRIMARY KEY, "mcap_m" REAL, "enterprise_value_m" REAL, "ev_ebitda" REAL, "pb_ratio" REAL, "pe_ttm" REAL, "fwd_pe" REAL, "ev_revenue" REAL, "peg" REAL, "price" REAL, "currency" TEXT, "shares_out_m" REAL, "ebitda_m" REAL, "total_debt_m" REAL, "total_cash_m" REAL, "profit_margin" REAL, "rev_growth" REAL, "sector" TEXT, "industry" TEXT, "asof" TEXT, "business_summary" TEXT, "long_name" TEXT);
CREATE TABLE ticker_meta ("ticker" TEXT PRIMARY KEY, "name" TEXT, "exchange" TEXT, "market" TEXT, "sector" TEXT, "industry" TEXT, "mcap_m" REAL, "price" REAL, "price_currency" TEXT, "adv_3m_usd_m" REAL, "shares_out_m" REAL, "pe_ttm" TEXT, "fwd_pe" TEXT, "beta" TEXT, "asof" TEXT, "sic" INTEGER, "sic_description" TEXT);
CREATE TABLE yf_dead (ticker TEXT PRIMARY KEY, asof TEXT);
CREATE INDEX idx_yf_evebitda ON ticker_yf(ev_ebitda);
CREATE INDEX idx_yf_pb ON ticker_yf(pb_ratio);
CREATE TABLE pb_people (
      person_id TEXT, first_name TEXT, last_name TEXT, full_name TEXT,
      primary_company TEXT, primary_company_type TEXT, primary_position TEXT,
      is_former INTEGER, board_seats TEXT, roles TEXT,
      location TEXT, country TEXT, biography TEXT,
      theme TEXT, company_website TEXT, is_principal INTEGER DEFAULT 0);
CREATE INDEX idx_pbp_name ON pb_people(full_name);
CREATE INDEX idx_pbp_company ON pb_people(primary_company);
CREATE INDEX idx_pbp_theme ON pb_people(theme);
CREATE TABLE pb_affiliation (
      full_name TEXT, company TEXT, company_type TEXT, position TEXT,
      is_former INTEGER, theme TEXT, ticker TEXT, is_principal INTEGER DEFAULT 0,
      role_class TEXT);
CREATE INDEX idx_pba_company ON pb_affiliation(company);
CREATE INDEX idx_pba_ticker ON pb_affiliation(ticker);
CREATE TABLE pb_principal (name TEXT PRIMARY KEY);
CREATE TABLE pb_principal_fund (principal TEXT, fund TEXT);
CREATE TABLE cusip_map (
        cusip TEXT PRIMARY KEY, ticker TEXT, sec_type TEXT, source TEXT, asof TEXT);
CREATE INDEX idx_cusipmap_tk ON cusip_map(ticker);
CREATE TABLE price_stats (
        ticker TEXT PRIMARY KEY, mom_3mo REAL, mom_20d REAL, off_high REAL,
        last_close REAL, n_pts INTEGER, asof TEXT);
CREATE TABLE fund_13f_prior (
      fund TEXT, cik TEXT, accession TEXT, filed TEXT,
      issuer TEXT, cusip TEXT, ticker TEXT, value_k INTEGER, shares INTEGER,
      sh_type TEXT, pct_book REAL,
      PRIMARY KEY (fund, accession, cusip));
CREATE INDEX idx_prior_ticker ON fund_13f_prior(ticker);
CREATE INDEX idx_prior_fund ON fund_13f_prior(fund);
CREATE TABLE fund_13f_prior_state (
      fund TEXT PRIMARY KEY, accession TEXT, filed TEXT, n_holdings INTEGER, total_value_k INTEGER);
CREATE TABLE ticker_entry_intact (
      ticker TEXT PRIMARY KEY,
      current_px REAL, anchor_px REAL, anchor_source TEXT,
      vs_entry_pct REAL, bucket TEXT,
      conviction_score REAL, n_funds INTEGER,
      n_hyper INTEGER, has_insider_cobuy INTEGER, sum_dollar_m REAL,
      anchors_seen TEXT);
CREATE TABLE fund_conviction (
      fund TEXT, ticker TEXT, signals TEXT, raw_score REAL, style_weight REAL,
      score REAL, macro_style TEXT,
      pct_book REAL, pct_company REAL, dollar_m REAL,
      PRIMARY KEY (fund, ticker));
CREATE TABLE ticker_conviction (
      ticker TEXT PRIMARY KEY, score REAL, raw_score REAL, n_funds INTEGER,
      n_hyper INTEGER, n_top_pick INTEGER, n_activist_13d INTEGER, n_passive_13g INTEGER,
      n_new_init INTEGER, n_material_add INTEGER, n_public_letter INTEGER,
      n_follow_on INTEGER, n_persist INTEGER, has_insider_cobuy INTEGER,
      sum_dollar_m REAL, max_pct_book REAL, max_pct_company REAL,
      fund_signals_summary TEXT, styles_summary TEXT);
CREATE TABLE ticker_style_conviction (
      ticker TEXT, macro_style TEXT, score REAL, n_funds INTEGER,
      n_hyper INTEGER, dollar_m REAL,
      PRIMARY KEY (ticker, macro_style));
CREATE TABLE unified_signal (
      ticker TEXT PRIMARY KEY,
      name TEXT, exchange TEXT, sector TEXT, mcap_m REAL, price REAL,
      mcap_bucket TEXT,
      smart_money_n REAL,
      s1_top INTEGER, s2_thresh INTEGER, s3_new INTEGER, s4_add INTEGER,
      activist_filings INTEGER, activist_max_pct REAL,
      insider_cluster_dollars_m REAL, insider_n INTEGER,
      form4_buy_usd_m REAL, form4_sell_usd_m REAL,
      form4_buy_30d_m REAL, form4_sell_30d_m REAL,
      max_pct_book REAL, n_funds_5pct_book INTEGER,
      global_score REAL,        -- score using only signals that work cross-listing
      is_us INTEGER,            -- 1 if US-registered (no dot suffix), 0 otherwise
      cat8k_ma INTEGER, cat8k_dir INTEGER, cat8k_ctrl INTEGER,
      cat8k_pipe INTEGER, cat8k_bnk INTEGER, cat8k_n INTEGER,
      ev_ebitda REAL, pb_ratio REAL, pe_ttm REAL,
      revealed_pref REAL,       -- active accumulation: 2*s3 + s4 + 0.5*s1
      asymmetry_score REAL,     -- downside protection × upside potential
      expected_return_pct REAL,
      entry_bucket TEXT, vs_entry_pct REAL, anchor_px REAL, anchor_source TEXT,
      sec_type TEXT,            -- 'common'|'etf'|'preferred'|'warrant'|'unit'|'right'|'delisted'
      score REAL,
      components TEXT
    );
CREATE INDEX idx_us_score ON unified_signal(score DESC);
CREATE INDEX idx_us_bucket ON unified_signal(mcap_bucket);
CREATE INDEX idx_us_pb ON unified_signal(max_pct_book DESC);
CREATE INDEX idx_us_entry ON unified_signal(entry_bucket);
CREATE TABLE fund_style (
      fund TEXT PRIMARY KEY, sub_group TEXT, macro_style TEXT,
      total_rows INTEGER, conviction_n INTEGER, threshold_n INTEGER,
      new_n INTEGER, adds_n INTEGER);
CREATE TABLE style_summary (
      macro_style TEXT PRIMARY KEY,
      n_funds INTEGER, total_rows INTEGER,
      n_conviction INTEGER, n_threshold INTEGER, n_new INTEGER, n_adds INTEGER,
      top_funds TEXT, top_consensus TEXT);
CREATE TABLE style_consensus (
      macro_style TEXT, ticker TEXT, n_funds INTEGER, dollar_m REAL,
      sections_seen TEXT, in_tier1 INTEGER, has_cluster INTEGER, entry_bucket TEXT,
      PRIMARY KEY (macro_style, ticker));
