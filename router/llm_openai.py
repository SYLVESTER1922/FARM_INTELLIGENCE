"""OpenAI adapter for the router interface. Reads OPENAI_API_KEY from the environment (the SDK does); nothing is stored."""

import json
import os
import time

from router.llm import RETRY_DELAYS, LLMResult, Unavailable, cost_usd, route_with_retries

TIMEOUT_S = 15.0
MODES = ("json_schema", "tool")
# "json_schema" is what every dev-set figure in the plan was measured with. "tool" forces a strict function call instead: on one probe
# (gpt-4o-mini, a plain "total feed cost", 30 calls each) json_schema answered "none" 30 of 30 and tool routed correctly 30 of 30, at the
# same cost. It becomes the default only after a full dev run confirms it (plan section 22).
DEFAULT_MODE = "json_schema"           # fail closed: no retries, a slow or failed call is reported, never papered over (plan D11)


QUOTA_CODES = ("insufficient_quota", "credit_balance_exhausted", "billing_not_active")


def is_quota_error(e) -> bool:
    """An exhausted or inactive account. OpenAI has reported this as code `insufficient_quota` and, since October 2026, as code
    `credit_balance_exhausted` with type `insufficient_quota`; either way waiting does not help, so it is never retried."""
    body = getattr(e, "body", None) or {}
    body = body.get("error", body) if isinstance(body, dict) else {}
    return getattr(e, "code", None) in QUOTA_CODES or body.get("code") in QUOTA_CODES or body.get("type") == "insufficient_quota"


class OpenAIRouter:
    provider = "openai"

    def __init__(self, model: str, client=None, timeout: float = TIMEOUT_S, retry_delays=RETRY_DELAYS, sleep=time.sleep,
                 mode: str = DEFAULT_MODE):
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}")
        self.model, self.mode = model, mode
        self._delays, self._sleep = retry_delays, sleep
        if client is None:
            if not os.environ.get("OPENAI_API_KEY"):
                raise Unavailable("OPENAI_API_KEY is not set in the environment")
            import openai
            client = openai.OpenAI(timeout=timeout, max_retries=0)
        self._client = client

    def route(self, system: str, user: str, schema: dict) -> LLMResult:
        return route_with_retries(lambda: self._route_once(system, user, schema), self._delays, self._sleep)

    def _route_once(self, system: str, user: str, schema: dict) -> LLMResult:
        res = LLMResult(model=self.model, provider=self.provider)
        kwargs = dict(model=self.model, messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
        if self.mode == "tool":
            kwargs["tools"] = [{"type": "function", "function": {"name": "route", "description": "Fill in the routing form for the question.",
                                                                "parameters": schema, "strict": True}}]
            kwargs["tool_choice"] = {"type": "function", "function": {"name": "route"}}
        else:
            kwargs["response_format"] = {"type": "json_schema", "json_schema": {"name": "farm_route", "strict": True, "schema": schema}}
        # Reasoning models (gpt-5*, o-series) take no temperature and use max_completion_tokens; chat models are pinned to 0.
        if self.model.startswith(("gpt-5", "o1", "o3", "o4")):
            kwargs["max_completion_tokens"] = 1500
        else:
            kwargs["temperature"] = 0
            kwargs["max_tokens"] = 400
        t0 = time.perf_counter()
        try:
            resp = self._client.chat.completions.create(**kwargs)
        except Exception as e:                                   # timeout, rate limit, connection, bad request ...
            res.latency_s = time.perf_counter() - t0
            # A 429 for an exhausted account is not a rate limit: waiting a minute will not fix it, so it is not retried.
            res.error = "InsufficientQuota" if is_quota_error(e) else type(e).__name__
            if res.error == "InsufficientQuota":
                res.detail = str(e)[:300]
            return res
        res.latency_s = time.perf_counter() - t0
        usage = getattr(resp, "usage", None)
        if usage:
            res.input_tokens, res.output_tokens = usage.prompt_tokens, usage.completion_tokens
        res.cost_usd = cost_usd(self.model, res.input_tokens, res.output_tokens)
        choice = resp.choices[0]
        if getattr(choice.message, "refusal", None):
            res.error = "refusal"
            return res
        calls = getattr(choice.message, "tool_calls", None) or []
        res.raw = calls[0].function.arguments if calls else (choice.message.content or "")
        try:
            res.data = json.loads(res.raw)
        except (json.JSONDecodeError, TypeError):
            res.error = "bad_json"
        return res
