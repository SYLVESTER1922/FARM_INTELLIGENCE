"""A scripted router LLM for tests: returns a prepared spec per question (no network, no cost). Lets every pipeline branch be tested
deterministically, including failures."""

from router.llm import LLMResult


def spec(metric="none", dimension="none", category_text="", domains=(), period_phrase="", all_time=False,
         aggregation="total", grain="none", ambiguous_between=(), refusal="none", follow_up=False) -> dict:
    return {"metric": metric, "dimension": dimension, "category_text": category_text, "domains": list(domains),
            "period_phrase": period_phrase, "all_time": all_time, "aggregation": aggregation, "grain": grain,
            "ambiguous_between": list(ambiguous_between), "refusal": refusal, "follow_up": follow_up}


class FakeRouter:
    provider = "fake"

    def __init__(self, script=None, default=None, model="fake-1", error=None):
        self.model = model
        self.script = script or {}               # question -> spec dict (or an LLMResult / Exception)
        self.default = default
        self.error = error
        self.calls = []

    def route(self, system: str, user: str, schema: dict) -> LLMResult:
        question = user[3:].strip() if user.startswith("Q: ") else user
        self.calls.append(question)
        if self.error:
            return LLMResult(error=self.error, model=self.model, provider=self.provider)
        out = self.script.get(question, self.default)
        if out is None:
            return LLMResult(error="no_script", model=self.model, provider=self.provider)
        if isinstance(out, LLMResult):
            return out
        return LLMResult(data=out, raw=str(out), model=self.model, provider=self.provider,
                         input_tokens=100, output_tokens=40, latency_s=0.01)
