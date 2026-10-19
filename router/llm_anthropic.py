"""
Claude adapter for the router interface. Uses the official Anthropic SDK (imported lazily, so the rest of the app runs without it)
and structured outputs (`output_config.format`), which guarantee the reply is schema-valid JSON in the first text block.
Reads ANTHROPIC_API_KEY (or an `ant auth login` profile) from the environment via the SDK; nothing is stored here.

Install when you want to run it:  pip install anthropic
"""

import json
import os
import time

from router.llm import RETRY_DELAYS, LLMResult, Unavailable, cost_usd, route_with_retries

TIMEOUT_S = 15.0


class AnthropicRouter:
    provider = "anthropic"

    def __init__(self, model: str, client=None, timeout: float = TIMEOUT_S, retry_delays=RETRY_DELAYS, sleep=time.sleep):
        self.model = model
        self._delays, self._sleep = retry_delays, sleep
        if client is None:
            if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
                raise Unavailable("no ANTHROPIC_API_KEY (or ANTHROPIC_AUTH_TOKEN) in the environment")
            try:
                import anthropic
            except ImportError:
                raise Unavailable("the anthropic package is not installed (pip install anthropic)")
            client = anthropic.Anthropic(timeout=timeout, max_retries=0)
        self._client = client

    def route(self, system: str, user: str, schema: dict) -> LLMResult:
        return route_with_retries(lambda: self._route_once(system, user, schema), self._delays, self._sleep)

    def _route_once(self, system: str, user: str, schema: dict) -> LLMResult:
        import anthropic

        res = LLMResult(model=self.model, provider=self.provider)
        t0 = time.perf_counter()
        try:
            resp = self._client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=system,
                messages=[{"role": "user", "content": user}],
                # Routing is a short, bounded classification: low effort. No temperature (current models reject non-default).
                output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
            )
        except anthropic.RateLimitError:
            res.error = "RateLimitError"
        except anthropic.APIStatusError as e:
            res.error = f"APIStatusError_{e.status_code}"
        except anthropic.APIConnectionError:                      # includes timeouts
            res.error = "APIConnectionError"
        if res.error:
            res.latency_s = time.perf_counter() - t0
            return res
        res.latency_s = time.perf_counter() - t0
        res.input_tokens, res.output_tokens = resp.usage.input_tokens, resp.usage.output_tokens
        res.cost_usd = cost_usd(self.model, res.input_tokens, res.output_tokens)
        if resp.stop_reason == "refusal":
            res.error = "refusal"
            return res
        res.raw = next((b.text for b in resp.content if b.type == "text"), "")
        try:
            res.data = json.loads(res.raw)
        except (json.JSONDecodeError, TypeError):
            res.error = "bad_json"
        return res
