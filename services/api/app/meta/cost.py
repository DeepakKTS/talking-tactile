"""The cost meter. Every Meta call is priced here from config/tactile_rules.yaml meta, and a
call that would pass the budget is refused before it is made. Warns once at each
configured share of the budget."""

import logging
from typing import Literal

from app.config import Meta, Prices

log = logging.getLogger(__name__)

_TOKENS_PER_MTOK = 1_000_000
_SECONDS_PER_HOUR = 3600

Unit = Literal["input_tokens", "cached_tokens", "output_tokens", "images", "audio_seconds"]


class BudgetExceededError(Exception):
    """The call would take spending past the budget."""


def _need(prices: Prices, field: str) -> float:
    value = getattr(prices, field)
    if value is None:
        raise ValueError(f"this model has no {field} price")
    return float(value)


class CostMeter:
    def __init__(self, rules: Meta) -> None:
        self._rules = rules
        self.spent_usd = 0.0
        self.warnings: list[float] = []

    def price(
        self,
        model: str,
        *,
        input_tokens: int = 0,
        cached_tokens: int = 0,
        output_tokens: int = 0,
        images: int = 0,
        audio_seconds: float = 0.0,
    ) -> float:
        """USD for one call. input_tokens counts all prompt tokens, cached ones included."""
        if model not in self._rules.prices_usd:
            raise KeyError(f"no price for model {model} in config")
        p = self._rules.prices_usd[model]
        usd = 0.0
        if input_tokens or cached_tokens:
            usd += (input_tokens - cached_tokens) * _need(p, "input_per_mtok") / _TOKENS_PER_MTOK
            usd += cached_tokens * _need(p, "cached_input_per_mtok") / _TOKENS_PER_MTOK
        if output_tokens:
            usd += output_tokens * _need(p, "output_per_mtok") / _TOKENS_PER_MTOK
        if images:
            usd += images * _need(p, "per_image")
        if audio_seconds:
            usd += audio_seconds * _need(p, "per_audio_hour") / _SECONDS_PER_HOUR
        return usd

    def check(self, model: str, **units: float) -> None:
        """Refuses a call whose price would take spending past the budget."""
        usd = self.price(model, **units)  # type: ignore[arg-type]
        if self.spent_usd + usd > self._rules.budget_usd:
            raise BudgetExceededError(
                f"{model} call of ${usd:.4f} would pass the ${self._rules.budget_usd:g} budget "
                f"(spent ${self.spent_usd:.2f})"
            )

    def record(self, model: str, **units: float) -> float:
        usd = self.price(model, **units)  # type: ignore[arg-type]
        self.spent_usd += usd
        share = self.spent_usd / self._rules.budget_usd
        for fraction in self._rules.warn_at_fractions:
            if share >= fraction and fraction not in self.warnings:
                self.warnings.append(fraction)
                log.warning("Meta spend is at %.0f%% of the budget", 100 * share)
        return usd
