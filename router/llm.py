"""
Provider-neutral LLM interface for the router (plan decision D11): a question in, a validated-by-the-caller JSON spec out. One
small adapter per provider (router/llm_openai.py, router/llm_anthropic.py); swapping a provider is a config change, and the eval
runs the identical call through any of them.

API keys are read from environment variables by each provider's SDK (OPENAI_API_KEY, ANTHROPIC_API_KEY) and are never stored in
code, config or logs. If a key is missing the adapter reports `unavailable` and the runner skips that model.
"""

import random
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
    attempts: int = 1                  # calls made (more than 1 means a transient failure was retried)

    @property
    def ok(self):
        return self.error is None and self.data is not None


class RouterLLM(Protocol):
    model: str
    provider: str

    def route(self, system: str, user: str, schema: dict) -> LLMResult: ...


class Unavailable(Exception):
    """The provider cannot be used here (no API key, SDK not installed). The runner skips the model and says why."""


# Retries (plan section 22): transient failures only, exponential backoff with a little jitter. Three attempts, waiting about 1 s and then
# 2 s. A failure that is not transient (a refusal, bad JSON, bad credentials) is never retried. When the retries run out the caller says
# the assistant is busy; it never answers without the model.
RETRY_DELAYS = (1.0, 2.0)
TRANSIENT_ERRORS = {"RateLimitError", "APITimeoutError", "APIConnectionError", "TimeoutError", "InternalServerError", "ConnectionError"}


def is_transient(error) -> bool:
    if not error:
        return False
    if error in TRANSIENT_ERRORS:
        return True
    status = error.rsplit("_", 1)[-1] if error.startswith("APIStatusError_") else ""
    return status in ("408", "409", "429", "500", "502", "503", "504", "529")


def route_with_retries(once, delays=RETRY_DELAYS, sleep=time.sleep) -> "LLMResult":
    """Call `once()` (one attempt, returns an LLMResult) until it succeeds, fails for good, or the delays run out. The latency
    reported is the whole wall time including the waits, so the cost of a retry shows up in the latency figures."""
    t0 = time.perf_counter()
    attempts = 0
    for delay in (*delays, None):
        res = once()
        attempts += 1
        if res.ok or not is_transient(res.error) or delay is None:
            break
        sleep(delay * (1 + 0.25 * random.random()))
    res.attempts = attempts
    res.latency_s = time.perf_counter() - t0
    return res


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


def make_client(model: str, **options) -> RouterLLM:
    """Build the adapter for a model id. Raises Unavailable (with the reason) if it cannot run here. `options` go to the adapter."""
    if model.startswith("claude"):
        from router.llm_anthropic import AnthropicRouter
        return AnthropicRouter(model, **options)
    from router.llm_openai import OpenAIRouter
    return OpenAIRouter(model, **options)
