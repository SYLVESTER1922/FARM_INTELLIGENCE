"""OpenAI adapter for the router interface. Reads OPENAI_API_KEY from the environment (the SDK does); nothing is stored."""

import json
import os
import time

from router.llm import LLMResult, Unavailable, cost_usd

TIMEOUT_S = 15.0           # fail closed: no retries, a slow or failed call is reported, never papered over (plan D11)


class OpenAIRouter:
    provider = "openai"

    def __init__(self, model: str, client=None, timeout: float = TIMEOUT_S):
        self.model = model
        if client is None:
            if not os.environ.get("OPENAI_API_KEY"):
                raise Unavailable("OPENAI_API_KEY is not set in the environment")
            import openai
            client = openai.OpenAI(timeout=timeout, max_retries=0)
        self._client = client

    def route(self, system: str, user: str, schema: dict) -> LLMResult:
        res = LLMResult(model=self.model, provider=self.provider)
        kwargs = dict(
            model=self.model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            response_format={"type": "json_schema", "json_schema": {"name": "farm_route", "strict": True, "schema": schema}},
        )
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
            res.error = type(e).__name__
            return res
        res.latency_s = time.perf_counter() - t0
        usage = getattr(resp, "usage", None)
        if usage:
            res.input_tokens, res.output_tokens = usage.prompt_tokens, usage.completion_tokens
        res.cost_usd = cost_usd(self.model, res.input_tokens, res.output_tokens)
        choice = resp.choices[0]
        res.raw = choice.message.content or ""
        if getattr(choice.message, "refusal", None):
            res.error = "refusal"
            return res
        try:
            res.data = json.loads(res.raw)
        except (json.JSONDecodeError, TypeError):
            res.error = "bad_json"
        return res
