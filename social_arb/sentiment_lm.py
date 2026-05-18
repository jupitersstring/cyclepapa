"""Loughran-McDonald financial-text sentiment overlay.

The LM dictionaries (Notre Dame, public-domain) were built specifically
to address Loughran & McDonald's (2011) finding that the Harvard-IV /
general-purpose sentiment dictionaries mis-classify finance words --
"liability", "tax", "vice", "depreciation", "amortization" all show up
as negative in general lexica but are neutral in earnings-call context.

We ship a small embedded subset of the most frequent LM terms so the
overlay works offline without a network fetch. For full coverage users
can drop in the canonical CSVs from:

    https://sraf.nd.edu/loughranmcdonald-master-dictionary/

The overlay computes per-text counts of:
  * lm_positive / lm_negative
  * lm_uncertainty
  * lm_litigious
  * lm_strong_modal / lm_weak_modal
  * lm_constraining

A `score()` helper returns a polarity score in [-1, 1] derived from
(positive - negative) / (positive + negative + 1).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

# Curated high-frequency subset of LM lexica. Roughly ~250 terms total;
# enough to materially improve over VADER on financial text without
# requiring an external download. Users can pip-install `pysentiment2`
# for the full ~2000-term version and patch `LM_LEXICON` accordingly.
LM_POSITIVE: frozenset[str] = frozenset({
    "achieve", "achievement", "advance", "advances", "advantage", "advantageous",
    "advantages", "beat", "beats", "benefit", "benefited", "benefiting",
    "benefits", "best", "better", "boost", "boosted", "breakthrough",
    "constructive", "creative", "creativity", "delight", "delighted",
    "dynamic", "effective", "efficient", "encouraged", "encouraging",
    "enhance", "enhanced", "enhancement", "enhancements", "enhancing",
    "enjoy", "enthusiastic", "exceed", "exceeded", "exceeding", "exceptional",
    "exciting", "favorable", "favorably", "favorite", "gain", "gained",
    "gaining", "gains", "good", "great", "greatest", "growth", "highest",
    "honor", "honored", "honorable", "honors", "improve", "improved",
    "improvement", "improvements", "improves", "improving", "incentive",
    "incredible", "innovate", "innovation", "innovations", "innovative",
    "leading", "leadership", "loyal", "outperform", "outperformance",
    "outperformed", "outperforming", "outperforms", "perfect", "pleased",
    "popular", "positive", "positively", "profitability", "profitable",
    "progress", "progressed", "prosper", "prospered", "prosperity",
    "prosperous", "record", "rewarded", "rewarding", "satisfied", "smooth",
    "smoothly", "solid", "strength", "strengthen", "strengthened",
    "strengthening", "strengthens", "strong", "stronger", "strongest",
    "success", "successes", "successful", "successfully", "superior",
    "surpass", "surpassed", "surpasses", "surpassing", "transparency",
    "tremendous", "upturn", "upturns", "valuable", "winning", "won",
})

LM_NEGATIVE: frozenset[str] = frozenset({
    "abandon", "abandoned", "abandoning", "abandonment", "abrupt",
    "abruptly", "abuse", "abused", "abuses", "abusive", "accusation",
    "accused", "adverse", "adversely", "alleged", "allegedly", "allegation",
    "anomalies", "anomalous", "anomaly", "anti", "argue", "argued",
    "arguing", "argument", "arrears", "ban", "banned", "banning",
    "bankrupt", "bankruptcies", "bankruptcy", "barred", "barrier",
    "barriers", "below", "bottleneck", "bottlenecks", "breach",
    "breached", "breaches", "breaching", "break", "breakage", "breakdown",
    "breaks", "burden", "burdened", "burdens", "burdensome", "calamities",
    "calamity", "cancel", "canceled", "canceling", "cancellation",
    "cancellations", "cancels", "catastrophe", "catastrophes",
    "catastrophic", "caution", "cautioned", "cautioning", "cautionary",
    "cease", "ceased", "ceasing", "challenge", "challenged", "challenges",
    "challenging", "claim", "claimed", "claiming", "claims", "closed",
    "closing", "closure", "closures", "concern", "concerned", "concerning",
    "concerns", "confiscate", "confiscated", "confiscating", "confiscation",
    "confiscatory", "conflict", "conflicting", "conflicts", "confused",
    "confusing", "confusion", "contention", "contentious", "contentiously",
    "contested", "contraction", "contractions", "convict", "convicted",
    "conviction", "corrected", "correction", "corrections", "corrupt",
    "corrupted", "corrupting", "corruption", "counter", "counterclaim",
    "counterclaims", "courtroom", "crime", "crimes", "criminal",
    "criminally", "crisis", "criticism", "criticisms", "criticize",
    "criticized", "criticizing", "critical", "cumbersome", "damage",
    "damaged", "damages", "damaging", "danger", "dangerous", "dangerously",
    "dangers", "deadlock", "deadlocked", "deadlocking", "deceased",
    "deceive", "deceived", "deceives", "deceiving", "decline", "declined",
    "declines", "declining", "deface", "defaced", "defaults", "defeat",
    "defeated", "defeats", "defect", "defective", "defects", "defendant",
    "defendants", "defer", "deferred", "deficiencies", "deficiency",
    "deficient", "deficit", "deficits", "degraded", "delay", "delayed",
    "delaying", "delays", "deleterious", "delinquencies", "delinquency",
    "delinquent", "delist", "delisted", "delisting", "deny", "denying",
    "depleted", "depletion", "deprecate", "deprecated", "depress",
    "depressed", "deteriorate", "deteriorated", "deteriorates",
    "deteriorating", "deterioration", "detract", "detracted", "detracting",
    "detrimental", "devalue", "devalued", "deviate", "deviated", "deviating",
    "deviation", "deviations", "difficult", "difficulties", "difficulty",
    "diluted", "diminish", "diminished", "diminishes", "diminishing",
    "disagree", "disagreed", "disagreement", "disagreements", "disagrees",
    "disappear", "disappeared", "disappearing", "disappoint", "disappointed",
    "disappointing", "disappointment", "disappointments", "disappoints",
    "disaster", "disasters", "disastrous", "disastrously", "discontinuance",
    "discontinue", "discontinued", "discontinuing", "discourage",
    "discouraged", "discrepancies", "discrepancy", "disgorge", "disgorged",
    "dishonor", "dishonored", "disqualified", "disqualifies", "disqualify",
    "disrupt", "disrupted", "disruption", "disruptions", "disruptive",
    "dissatisfaction", "dissident", "dissidents", "distress", "distressed",
    "divert", "diverted", "divest", "divested", "divesting", "divestiture",
    "doubt", "doubted", "doubtful", "doubts", "downgrade", "downgraded",
    "downsize", "downsized", "downsizes", "downsizing", "downturn",
    "downturns", "downward", "downwards", "drag", "drastically", "drop",
    "dropped", "drops", "embargo", "embargoed", "embarrass", "embarrassed",
    "embarrassing", "embarrassment", "embezzled", "embezzlement",
    "embezzler", "emergency", "encroach", "encroached", "encumber",
    "encumbered", "endanger", "endangered", "endangering", "erode",
    "eroded", "eroding", "erosion", "erratic", "erroneous", "erroneously",
    "error", "errors", "escalating", "evade", "evaded", "evading", "evasion",
    "exaggerate", "exaggerated", "expensive", "expensively", "expire",
    "expired", "expiring", "exploit", "exploitation", "exploited",
    "exploiting", "expose", "exposed", "exposure", "exposures", "fail",
    "failed", "failing", "fails", "failure", "failures", "fault", "faulted",
    "faults", "faulty", "fear", "fears", "felony", "fictitious", "fired",
    "force", "forced", "fraud", "frauds", "fraudulent", "fraudulently",
    "frustrated", "frustrating", "frustration", "frustrations", "halt",
    "halted", "halting", "hamper", "hampered", "hampering", "happens",
    "harassment", "hardship", "hardships", "harm", "harmed", "harmful",
    "harming", "harms", "harsh", "harshly", "hazard", "hazardous", "hazards",
    "hindered", "hostile", "hostility", "hurt", "hurting", "hurts", "ignore",
    "ignored", "ignoring", "ill", "illegal", "illegality", "illegally",
    "illicit", "illicitly", "imbalance", "impair", "impaired", "impairing",
    "impairment", "impairments", "impede", "imperative", "imperil",
    "imperiled", "imperiling", "impermissible", "impossibility", "impossible",
    "imprisoned", "imprisonment", "improper", "improperly", "inability",
    "inadequate", "inadequately", "inadvertent", "inadvertently", "incident",
    "incidents", "incompatibilities", "incompatibility", "incompatible",
    "incompetence", "incompetent", "incomplete", "inconsistencies",
    "inconsistency", "inconsistent", "inconsistently", "incorrect",
    "incorrectly", "indict", "indicted", "indictment", "ineffective",
    "ineffectively", "ineffectiveness", "inefficient", "inefficiently",
    "ineligibility", "ineligible", "inequitable", "inequitably", "inferior",
    "inflicting", "infringe", "infringed", "infringement", "infringes",
    "infringing", "injunctions", "injured", "injures", "injuries", "injuring",
    "injurious", "injury", "insecure", "insolvency", "insolvent",
    "instability", "insufficiency", "insufficient", "insufficiently",
    "intentional", "intentionally", "interference", "interferences",
    "interfering", "interfered", "interrupt", "interrupted", "interrupting",
    "interruption", "interruptions", "intimidation", "invalid", "invalidate",
    "invalidated", "invalidating", "invalidation", "invalidity",
    "investigated", "investigates", "investigating", "investigation",
    "investigations", "irreconcilable", "irreconcilably", "irregularities",
    "irregularity", "lag", "lagging", "lapse", "lapsed", "lapses", "late",
    "lawsuit", "lawsuits", "layoff", "layoffs", "litigants", "litigate",
    "litigated", "litigates", "litigating", "litigation", "litigations",
    "lockout", "lose", "loses", "losing", "loss", "losses", "lost",
    "lying", "malfunction", "malfunctioned", "malfunctioning",
    "malfunctions", "manipulate", "manipulated", "manipulates",
    "manipulating", "manipulation", "manipulations", "miscalculate",
    "miscalculated", "miscalculating", "miscalculation", "misconduct",
    "miscount", "misdate", "misdated", "misdating", "misled",
    "mismanage", "mismanaged", "mismanagement", "mismanages", "mismanaging",
    "misrepresent", "misrepresentation", "misrepresented", "misrepresenting",
    "misrepresents", "miss", "missed", "missing", "mistake", "mistaken",
    "mistakenly", "mistakes", "monopolize", "monopolized", "monopolizes",
    "monopolizing", "moratorium", "moratoriums", "negative", "negatively",
    "neglect", "neglected", "neglecting", "neglects", "noncompliance",
    "noncomplying", "noncompliant", "noncompetitive", "nonconforming",
    "nonconformities", "nonconformity", "nonpayment", "obstruct",
    "obstructed", "obstructing", "obstruction", "offend", "offended",
    "offending", "omission", "omissions", "omit", "omits", "omitted",
    "omitting", "oppose", "opposed", "opposes", "opposing", "opposition",
    "outage", "outages", "overcharge", "overcharged", "overcharges",
    "overcharging", "overdue", "overestimate", "overestimated",
    "overestimates", "overestimating", "overestimation", "overload",
    "overloaded", "overloading", "overlooked", "overpaid", "overpayment",
    "overpayments", "overrun", "overruns", "overstate", "overstated",
    "overstates", "overstating", "overstatement", "overstatements",
    "overstock", "overstocked", "overturn", "overturned", "panic",
    "panics", "penalize", "penalized", "penalizes", "penalizing",
    "penalties", "penalty", "peril", "perils", "permitted", "perpetrate",
    "perpetrated", "perpetrates", "perpetrating", "perpetration",
    "persist", "persisted", "persisting", "persists", "pervasive",
    "pessimism", "pessimistic", "petty", "plaintiff", "plead", "pleaded",
    "pleading", "pleads", "plummeted", "poor", "poorer", "poorly",
    "postpone", "postponed", "postponement", "postponements", "postpones",
    "postponing", "prejudice", "prejudiced", "prejudicial", "premature",
    "prematurely", "preoccupy", "preoccupied", "preoccupies", "preoccupying",
    "preposterous", "preposterously", "presume", "presumed", "presumes",
    "presuming", "presumption", "presumptions", "presumptive", "problem",
    "problematic", "problematical", "problems", "prolong", "prolonged",
    "prolongs", "prone", "prosecute", "prosecuted", "prosecutes",
    "prosecuting", "prosecution", "prosecutions", "protest", "protested",
    "protesting", "protests", "protested", "punish", "punished", "punishes",
    "punishing", "punishment", "punitive", "purported", "purportedly",
    "questionable", "questioned", "questioning", "quit", "racketeer",
    "racketeering", "rationalization", "rationalizations", "rationalize",
    "rationalized", "rationalizes", "rationalizing", "recall", "recalled",
    "recalling", "recalls", "redact", "redacted", "redacting", "redaction",
    "redactions", "redress", "redressed", "redressing", "refuse", "refused",
    "refuses", "refusing", "reject", "rejected", "rejecting", "rejection",
    "rejections", "rejects", "relinquish", "relinquished", "relinquishes",
    "relinquishing", "reluctance", "reluctant", "renegotiate",
    "renegotiated", "renegotiates", "renegotiating", "renegotiation",
    "renegotiations", "renounce", "renounced", "renouncement",
    "renouncements", "renounces", "renouncing", "reorganization",
    "reorganizations", "repossess", "repossessed", "repossessing",
    "repossession", "repossessions", "repudiate", "repudiated", "repudiates",
    "repudiating", "repudiation", "repudiations", "repurchase",
    "repurchased", "repurchases", "repurchasing", "rescind", "rescinded",
    "rescinding", "rescission", "restate", "restated", "restatement",
    "restatements", "restates", "restating", "restructure", "restructured",
    "restructures", "restructuring", "restructurings", "retaliate",
    "retaliated", "retaliates", "retaliating", "retaliation", "retaliations",
    "retaliatory", "revoke", "revoked", "revokes", "revoking", "ruined",
    "ruining", "ruinous", "ruled", "ruling", "rumored", "sabotage",
    "sabotaged", "scandal", "scandals", "scrutinize", "scrutinized",
    "scrutinizes", "scrutinizing", "scrutiny", "seizure", "seizures",
    "serious", "seriousness", "setback", "setbacks", "severe", "severely",
    "shock", "shocked", "shocking", "shocks", "shortage", "shortages",
    "shortfall", "shortfalls", "shrink", "shrinkage", "shrinkages",
    "shrinking", "shrinks", "shrunk", "shutdown", "shutdowns", "slow",
    "slowdown", "slowdowns", "slowed", "slower", "slowest", "slowing",
    "slowly", "slows", "sluggish", "sluggishly", "sluggishness", "stagnant",
    "stagnate", "stagnated", "stagnates", "stagnating", "stagnation",
    "standstill", "standstills", "stolen", "stoppage", "stoppages",
    "stopped", "stopping", "stops", "strain", "strained", "straining",
    "strains", "stringent", "stringently", "subsidize", "subsidized",
    "subsidizes", "subsidizing", "subpoena", "subpoenaed", "subpoenas",
    "succession", "successive", "sudden", "suddenly", "sue", "sued", "sues",
    "suffer", "suffered", "suffering", "suffers", "suicide", "sued",
    "summons", "summoned", "summoning", "summonses", "surrender",
    "surrendered", "surrendering", "surrenders", "suspect", "suspected",
    "suspecting", "suspects", "suspend", "suspended", "suspending",
    "suspension", "suspensions", "suspicion", "suspicions", "suspicious",
    "tampered", "tampering", "terminate", "terminated", "terminates",
    "terminating", "termination", "terminations", "testify", "testified",
    "testifies", "testifying", "testimonies", "testimony", "threat",
    "threaten", "threatened", "threatening", "threatens", "threats", "tight",
    "tightening", "tolerate", "tolerated", "tolerates", "tolerating",
    "trafficking", "tragedies", "tragedy", "tragic", "tragically", "trail",
    "trailing", "trails", "trial", "trials", "tribunal", "tribunals",
    "trouble", "troubled", "troubles", "tumble", "tumbled", "tumbles",
    "tumbling", "turbulence", "turmoil", "unable", "unacceptable",
    "unacceptably", "unaffordable", "unanticipated", "unapproved",
    "unattractive", "unaudited", "unauthorized", "unavailable", "unavoidable",
    "unaware", "uncertainty", "unclaimed", "unclear", "uncollectable",
    "uncollectibility", "uncollectible", "uncollected", "uncompetitive",
    "unconfirmed", "uncontested", "uncontrollable", "uncontrolled",
    "underpaid", "underperform", "underperformance", "underperformed",
    "underperforming", "underperforms", "underproduction", "underproduce",
    "underproduced", "understate", "understated", "understatement",
    "understates", "understating", "underutilization", "underutilized",
    "undesirable", "undesired", "undetected", "undisclosed", "undocumented",
    "undue", "uneconomic", "uneconomical", "uneconomically", "unemployment",
    "unenforceable", "unethical", "unexpected", "unexpectedly", "unfair",
    "unfairly", "unfavorable", "unfavorably", "unfit", "unforeseeable",
    "unforeseen", "unfortunate", "unfortunately", "unfounded", "unfriendly",
    "unfulfilled", "unfunded", "unhappy", "unhealthy", "unintended",
    "unintentional", "unintentionally", "unjust", "unjustifiable",
    "unjustified", "unjustly", "unknown", "unlawful", "unlawfully",
    "unlicensed", "unliquidated", "unmarketable", "unmerchantable",
    "unnecessarily", "unnecessary", "unneeded", "unoccupied", "unpaid",
    "unperformed", "unplanned", "unpopular", "unpredictability",
    "unpredictable", "unpredictably", "unpredicted", "unprofitability",
    "unprofitable", "unproven", "unqualified", "unrealistic", "unreasonable",
    "unreasonableness", "unreasonably", "unreceptive", "unrecoverable",
    "unrecovered", "unreimbursed", "unreliable", "unremedied", "unreported",
    "unresolved", "unsafe", "unsalable", "unsatisfactory", "unsatisfied",
    "unsold", "unsound", "unstabilized", "unstable", "unsubstantiated",
    "unsuccessful", "unsuccessfully", "unsuitable", "unsuited", "unsupported",
    "unsuspecting", "unsustainable", "untenable", "untrusted", "untruth",
    "untruthful", "untruthfully", "untruths", "unused", "unwanted",
    "unwarranted", "unwelcome", "unwilling", "unwillingness", "unwise",
    "upset", "urgency", "urgent", "usurious", "usurp", "usurped", "usurping",
    "vandalism", "verdict", "verdicts", "vexatious", "victim", "victims",
    "violate", "violated", "violates", "violating", "violation", "violations",
    "violators", "violence", "violent", "violently", "vitiate", "vitiated",
    "vitiates", "vitiating", "void", "voided", "voiding", "voids",
    "volatile", "volatility", "vulnerability", "vulnerable", "vulnerably",
    "warn", "warned", "warning", "warnings", "warns", "waste", "wasted",
    "wasteful", "wastefully", "wasting", "weak", "weaken", "weakened",
    "weakening", "weakens", "weaker", "weakest", "weakly", "weakness",
    "weaknesses", "withdraw", "withdrawal", "withdrawals", "withdrawn",
    "withdraws", "worsen", "worsened", "worsening", "worsens", "worst",
    "worthless", "writedown", "writedowns", "writeoff", "writeoffs",
    "wrong", "wrongdoing", "wrongdoings", "wrongful", "wrongfully",
    "wrongly",
})

LM_UNCERTAINTY: frozenset[str] = frozenset({
    "approximate", "approximated", "approximates", "approximately",
    "approximating", "approximation", "approximations", "arbitrarily",
    "arbitrariness", "arbitrary", "assume", "assumed", "assumes",
    "assuming", "assumption", "assumptions", "believe", "believed",
    "believes", "believing", "cautious", "cautiously", "conceivable",
    "conceivably", "conditional", "conditionally", "conditions", "confident",
    "contingencies", "contingency", "contingent", "contingently", "contingents",
    "could", "depend", "depended", "dependence", "dependencies", "dependency",
    "depending", "depends", "destabilized", "destabilizing", "doubt",
    "doubtful", "doubts", "exposure", "fluctuate", "fluctuated", "fluctuates",
    "fluctuating", "fluctuation", "fluctuations", "hidden", "imprecise",
    "imprecisely", "imprecision", "imprecisions", "improbability",
    "improbable", "indefinite", "indefinitely", "indefiniteness",
    "indeterminable", "indeterminate", "intangible", "intangibles",
    "likelihood", "may", "maybe", "might", "nearly", "occasionally", "perhaps",
    "possibilities", "possibility", "possible", "possibly", "predict",
    "predicted", "predicting", "prediction", "predictions", "predictive",
    "predictor", "predictors", "predicts", "preliminarily", "preliminary",
    "presumably", "presume", "presumed", "presumes", "presuming",
    "presumption", "presumptions", "presumptive", "presumptively", "probable",
    "probabilities", "probability", "probably", "rely", "reliance", "relied",
    "rumors", "risk", "risked", "riskier", "riskiest", "riskiness", "risking",
    "risks", "risky", "seems", "seldom", "sometime", "sometimes", "speculate",
    "speculated", "speculates", "speculating", "speculation", "speculations",
    "speculative", "speculatively", "suggest", "suggested", "suggesting",
    "suggests", "tentative", "tentatively", "turbulence", "uncertain",
    "uncertainly", "uncertainties", "uncertainty", "unclear", "unconfirmed",
    "undecided", "undefined", "undeterminable", "undetermined", "undetermined",
    "unexpected", "unexpectedly", "unforecasted", "unforeseeable",
    "unforeseen", "unguaranteed", "unhedged", "unidentifiable", "unknown",
    "unknowns", "unobservable", "unplanned", "unpredictability",
    "unpredictable", "unpredictably", "unpredicted", "unproved", "unproven",
    "unquantifiable", "unreconciled", "unsettled", "unspecific",
    "unspecified", "untested", "unusual", "unusually", "vague", "vagueness",
    "vaguer", "vaguest", "vaguely", "variability", "variable", "variables",
    "variant", "variants", "variation", "variations", "vary", "varying",
    "volatile", "volatilities", "volatility",
})

LM_LITIGIOUS: frozenset[str] = frozenset({
    "allege", "alleged", "allegedly", "alleges", "allegations",
    "appeal", "appealed", "appealing", "appeals", "arbitration",
    "arbitrator", "arbitrators", "claim", "claimed", "claims", "claimant",
    "complainant", "complainants", "complaint", "complaints", "court",
    "courts", "defendant", "defendants", "deposition", "depositions",
    "discrimination", "felonies", "felony", "filed", "filing", "filings",
    "indictment", "indictments", "injunction", "injunctions", "judge",
    "judges", "judicial", "judiciary", "juror", "jurors", "jury",
    "lawsuit", "lawsuits", "lawyer", "lawyers", "legal", "legality",
    "legally", "legislate", "legislated", "legislating", "legislation",
    "litigant", "litigants", "litigate", "litigated", "litigates",
    "litigating", "litigation", "litigations", "petition", "petitions",
    "plaintiff", "plaintiffs", "prosecute", "prosecuted", "prosecutes",
    "prosecuting", "prosecution", "prosecutions", "prosecutor",
    "prosecutors", "regulator", "regulators", "regulatory", "settled",
    "settlement", "settlements", "subpoena", "subpoenaed", "subpoenas",
    "summons", "tribunal", "tribunals", "writ", "writs",
})


WORD_RE = re.compile(r"[A-Za-z']+")


def lm_counts(text: str) -> dict[str, int]:
    """Tokenise text and return per-category LM counts."""
    if not text:
        return {"pos": 0, "neg": 0, "unc": 0, "lit": 0, "total": 0}
    tokens = [t.lower() for t in WORD_RE.findall(text)]
    pos = sum(1 for t in tokens if t in LM_POSITIVE)
    neg = sum(1 for t in tokens if t in LM_NEGATIVE)
    unc = sum(1 for t in tokens if t in LM_UNCERTAINTY)
    lit = sum(1 for t in tokens if t in LM_LITIGIOUS)
    return {"pos": pos, "neg": neg, "unc": unc, "lit": lit, "total": len(tokens)}


def lm_score(text: str) -> float:
    """LM polarity in [-1, 1]: (pos - neg) / (pos + neg + 1)."""
    c = lm_counts(text)
    return (c["pos"] - c["neg"]) / float(c["pos"] + c["neg"] + 1)


def lm_intensity(text: str) -> float:
    """Total LM hit rate per 1000 tokens. High = text is genuinely financial."""
    c = lm_counts(text)
    if c["total"] == 0:
        return 0.0
    return 1000.0 * (c["pos"] + c["neg"] + c["unc"] + c["lit"]) / c["total"]
