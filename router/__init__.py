"""The single routing path: one LLM call that fills a closed spec, validated and cross-checked by code (plan section 6)."""

from router.pipeline import V2Answer, answer_question_v2  # noqa: F401
from router.prompt import PROMPT_VERSION  # noqa: F401
