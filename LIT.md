# Informed-Flow Screen — Literature Grounding

The `informed` subcommand replaces raw-volume intuition with measures the
market-microstructure literature has tied to *informed* trading in
derivatives. The premise across this literature: informed traders prefer
options/warrants for embedded leverage, take **directional** positions, and
their footprint shows up in the derivative *before* the underlying moves.
Raw volume is the weak form of that signal; the components below are the
strong form.

## Components and citations

### 1. Abnormal option/stock volume ratio (`abn_os`)
- **Roll, Schwartz & Subrahmanyam (2010), "O/S: The relative trading
  activity in options and stock," *Journal of Financial Economics*.**
  Introduces O/S — option volume relative to stock volume — as a measure of
  informed/discretionary activity that predicts returns and earnings news.
- **Johnson & So (2012), "The option to stock volume ratio and future
  returns," *JFE*.** O/S is informative about future equity returns; the
  sign/strength interacts with short-sale costs and frictions.

Implementation: warrant is the "option." `abn_os = log( recent
warrant$vol/common$vol ÷ trailing-median of that ratio )`. Positive means
the warrant is unusually active *relative to its own norm* — the O/S signal,
de-meaned per name so a structurally high-O/S warrant isn't always "lit."

### 2. Signed order-flow imbalance (`ofi`)
- **Easley, O'Hara & Srinivas (1998), "Option volume and stock prices:
  Evidence on where informed traders trade," *Journal of Finance*.**
  Informed traders take **directional** option positions; signed option
  volume carries information about the stock. Raw (unsigned) volume does
  not separate informed buying from selling.
- **Pan & Poteshman (2006), "The information in option volume for future
  stock prices," *Review of Financial Studies*.** The predictive content is
  concentrated in **opening buy** volume — direction and initiation matter,
  not gross turnover.
- **Bollen & Whaley (2004), *JF*** — signing trades by their location
  relative to quotes. Without tick/quote data we use the daily analog, the
  **close-location value** `CLV = ((C−L)−(H−C))/(H−L) ∈ [−1,1]`: +1 closed
  at the high (net buying that day), −1 at the low.

Implementation: `ofi = Σ(CLV·$vol) / Σ($vol)` over the window ∈ [−1,1]. This
is why the screen can flag a high-volume warrant as *distribution* (ofi<0)
rather than accumulation — the distinction raw volume can't make.

### 3. Leverage / elasticity tilt (`omega_w`, `elasticity`)
- **Black (1975), "Fact and fantasy in the use of options," *Financial
  Analysts Journal*.** Informed traders gravitate to options for leverage.
- Easley-O'Hara-Srinivas formalize that the leverage advantage is *why*
  informed migrate to the derivative.

Implementation: warrant elasticity `Ω = Δ · S/W` (BS call delta × underlying
÷ warrant price) — the % move in the warrant per 1% move in the common. Used
as a bounded multiplier [1,5] so the same imbalance counts for more in a
high-convexity (deep-OTM) warrant, where informed conviction is most
concentrated.

### 4. Price impact / stealth footprint (`rel_impact`)
- **Kyle (1985), "Continuous auctions and insider trading," *Econometrica*.**
  Informed order flow moves price; price impact per unit signed volume (λ)
  measures how much private information the flow carries.
- **Amihud (2002), "Illiquidity and stock returns," *JFM*.** Daily,
  tractable proxy: `mean(|return| / dollar-volume)`.

Implementation: `rel_impact = log(Amihud_warrant / Amihud_common)`. A warrant
whose price responds far more per traded dollar than its common is being
pushed against a thin book — accumulation low raw volume would hide.
(Cross-sectionally z-scored; the *level* mostly reflects the structural
warrant-vs-common liquidity gap, so only the relative rank is used.)

### 5. Lead–lag diagnostic (`lead_lag`)
- Easley-O'Hara-Srinivas: option volume **leads** stock returns.

Implementation (reported, not scored): `corr( warrant signed-flow_t ,
common return_{t+1} )`. Positive = the warrant's flow tends to precede the
common's next-day move — the hallmark of the informed trading in the
derivative that the whole literature is about.

## Composite

```
informed_score = omega_w · ( z(abn_os) + z(ofi) + 0.5·z(rel_impact) )
```
z-scored across the day's cross-section, so it is a relative ranking. `ofi`
and `abn_os` carry the direction+concentration signal; `rel_impact` adds the
stealth-footprint tilt at half weight; `omega_w` up-weights leverage.
`lead_lag` is shown alongside as corroboration.

## Deliberate limitations
- **Daily signing is a proxy.** True informed-flow work uses signed
  tick/quote data or proprietary open-buy volume (Pan-Poteshman). CLV
  approximates direction from the daily bar only.
- **No opening/closing split.** We cannot distinguish position-opening from
  position-closing flow the way ISE/CBOE open-interest data allows.
- **Cross-sectional z-scores need breadth.** On a handful of names the
  ranking is noisy; it is designed for the full universe.
- **`rel_impact` level is structural**, not informative on its own — only
  its cross-sectional rank is used.
