"""Rough USD estimates from published list prices (override via pricing.yaml)."""

from __future__ import annotations

from pathlib import Path

import yaml

from skill_token_bench.models import TokenUsage

# Per-million-token list prices. Override with benchmarks/pricing.yaml.
DEFAULT_PRICES: dict[str, dict[str, float]] = {
    "claude-haiku-4-5": {"input": 1.0, "output": 5.0, "cache_read": 0.1, "cache_write": 1.25},
    "claude-sonnet-4-5": {"input": 3.0, "output": 15.0, "cache_read": 0.3, "cache_write": 3.75},
    "claude-opus-4-5": {"input": 15.0, "output": 75.0, "cache_read": 1.5, "cache_write": 18.75},
    "mock-haiku": {"input": 1.0, "output": 5.0, "cache_read": 0.1, "cache_write": 1.25},
}


def load_prices(path: Path | None = None) -> dict[str, dict[str, float]]:
    prices = {k: dict(v) for k, v in DEFAULT_PRICES.items()}
    if path and path.exists():
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for model, vals in (data.get("models") or data).items():
            prices[model] = {**prices.get(model, {}), **vals}
    return prices


def estimate_cost(model: str, tokens: TokenUsage, prices: dict | None = None) -> float:
    table = prices or DEFAULT_PRICES
    rate = table.get(model) or table.get("mock-haiku")
    assert rate is not None
    cost = (
        tokens.input_tokens * rate.get("input", 0.0)
        + tokens.output_tokens * rate.get("output", 0.0)
        + tokens.cache_read_tokens * rate.get("cache_read", 0.0)
        + tokens.cache_write_tokens * rate.get("cache_write", 0.0)
    ) / 1_000_000
    return round(cost, 8)
