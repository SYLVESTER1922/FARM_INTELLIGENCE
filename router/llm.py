"""
Provider-neutral LLM interface for the router (plan decision D11): a question in, a validated-by-the-caller JSON spec out. One
small adapter per provider (router/llm_openai.py, router/llm_anthropic.py); swapping a provider is a config change, and the eval
runs the identical call through any of them.

API keys are read from environment variables by each provider's SDK (OPENAI_API_KEY, ANTHROPIC_API_KEY) and are never stored in
code, config or logs. If a key is missing the adapter reports `unavailable` and the runner skips that model.
"""

import time
from dataclasses import dataclass
from typing import Protocol

# USD per 1M tokens (input, output). Taken from the providers' published prices when this was written; they are CONFIG, not
# fact - check them against the current price lists before relying on a cost figure.
PRICES = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4o": (2.50, 10.00),
    "claude-haiku-5-5": (0.10, 0.50),      # up to 100K-token prompts
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
}


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    pin, pout = PRICES.get(model, (0.0, 0.0))
    return (input_tokens * pin + output_tokens * pout) / 1_000_000


@dataclass
class LLMResult:
    data: dict = None                  # the parsed JSON object, or None
    raw: str = ""
    error: str = None                  # None on success; else a short reason (timeout, rate_limit, bad_json, refusal, ...)
    model: str = ""
    provider: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    latency_s: float = 0.0
    cost_usd: float = 0.0

    @property
    def ok(self):
        return self.error is None and self.data is not None


class RouterLLM(Protocol):
    model: str
    provider: str

    def route(self, system: str, user: str, schema: dict) -> LLMResult: ...


class Unavailable(Exception):
    """The provider cannot be used here (no API key, SDK not installed). The runner skips the model and says why."""


def timed(fn):
    """Run fn() and return (value, seconds)."""
    t0 = time.perf_counter()
    value = fn()
    return value, time.perf_counter() - t0


# PROVISIONAL pin (plan section 20): the cheapest candidate that met the routing target on the dev set. Re-run the comparison before
# it is treated as final, and again before any change; the locked set is not used to choose it.
PINNED_MODEL = "gpt-4o-mini"


def available_models():
    """(model id, provider) pairs worth comparing, for the runner's default list."""
    return [("gpt-4o-mini", "openai"), ("gpt-4.1", "openai"), ("claude-haiku-5-5", "anthropic")]


def make_client(model: str) -> RouterLLM:
    """Build the adapter for a model id. Raises Unavailable (with the reason) if it cannot run here."""
    if model.startswith("claude"):
        from router.llm_anthropic import AnthropicRouter
        return AnthropicRouter(model)
    from router.llm_openai import OpenAIRouter
    return OpenAIRouter(model)
