"""Cost estimate, isolated and configurable. No built-in prices.

Prices come only from LLM_PRICE_INPUT_PER_MTOK and LLM_PRICE_OUTPUT_PER_MTOK (USD per million tokens),
set by the operator from the provider's current price list. If either is unset, cost is None.
"""

from __future__ import annotations


def estimate_usd(input_tokens: int | None, output_tokens: int | None,
                 price_in_per_mtok: float | None, price_out_per_mtok: float | None) -> float | None:
    if None in (input_tokens, output_tokens, price_in_per_mtok, price_out_per_mtok):
        return None
    return round(input_tokens / 1e6 * price_in_per_mtok + output_tokens / 1e6 * price_out_per_mtok, 6)
