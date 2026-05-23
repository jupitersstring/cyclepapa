"""FinBERT financial-text sentiment via HuggingFace Transformers.

ProsusAI/finbert (the spec's "default") is a BERT model fine-tuned on
Financial PhraseBank for 3-class sentiment (positive / neutral /
negative). Substantially outperforms VADER on earnings calls,
analyst notes, news headlines, and 10-K language. Runs on CPU at
50-200ms per sentence; we batch for throughput.

Drop-in alternative to the VADER-based SentimentScorer. The
class signature matches `SentimentScorer.score()` so any consumer
can switch by importing FinBERTScorer instead.

LAZY IMPORT: transformers + torch are large (~2GB) so we import on
first use and degrade gracefully if not installed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)

_FINBERT = None
_TOKENIZER = None
_LABELS = ["positive", "neutral", "negative"]


@dataclass
class FinbertScore:
    compound: float    # signed: positive - negative, in [-1, 1]
    positive: float
    neutral: float
    negative: float
    label: str         # "bullish" / "bearish" / "neutral"


def _load(model_name: str = "ProsusAI/finbert"):
    global _FINBERT, _TOKENIZER
    if _FINBERT is not None:
        return _FINBERT, _TOKENIZER
    try:
        from transformers import AutoModelForSequenceClassification, AutoTokenizer  # type: ignore
        import torch  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "FinBERT needs `pip install transformers torch`. "
            f"Got: {exc}"
        )
    _TOKENIZER = AutoTokenizer.from_pretrained(model_name)
    _FINBERT = AutoModelForSequenceClassification.from_pretrained(model_name)
    _FINBERT.eval()
    return _FINBERT, _TOKENIZER


class FinBERTScorer:
    """Drop-in upgrade for SentimentScorer using FinBERT.

    Falls back to VADER+LM when the model isn't installed so the pipeline
    keeps running.
    """

    def __init__(self, model_name: str = "ProsusAI/finbert", fallback: bool = True):
        self._model_name = model_name
        self._fallback = None
        try:
            _load(model_name)
        except RuntimeError as exc:
            log.warning("FinBERT unavailable (%s); falling back to VADER+LM", exc)
            if fallback:
                from .sentiment import SentimentScorer
                self._fallback = SentimentScorer()

    def score(self, text: str) -> FinbertScore:
        if not text:
            return FinbertScore(0.0, 0.0, 1.0, 0.0, "neutral")
        if self._fallback is not None:
            r = self._fallback.score(text)
            return FinbertScore(
                compound=r.compound, positive=r.pos, neutral=r.neu, negative=r.neg,
                label=r.label,
            )
        return self.score_batch([text])[0]

    def score_batch(self, texts: list[str], batch_size: int = 16) -> list[FinbertScore]:
        if self._fallback is not None:
            return [self.score(t) for t in texts]
        import torch
        model, tokenizer = _load(self._model_name)
        out: list[FinbertScore] = []
        for i in range(0, len(texts), batch_size):
            chunk = texts[i: i + batch_size]
            enc = tokenizer(chunk, truncation=True, padding=True, max_length=128, return_tensors="pt")
            with torch.no_grad():
                logits = model(**enc).logits
            probs = torch.softmax(logits, dim=-1).cpu().numpy()
            for p in probs:
                pos, neu, neg = float(p[0]), float(p[1]), float(p[2])
                comp = pos - neg
                if comp >= 0.2:
                    label = "bullish"
                elif comp <= -0.2:
                    label = "bearish"
                else:
                    label = "neutral"
                out.append(FinbertScore(
                    compound=comp, positive=pos, neutral=neu, negative=neg, label=label,
                ))
        return out
