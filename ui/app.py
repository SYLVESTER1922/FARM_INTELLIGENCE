"""
Local Gradio chat app for the Farm Intelligence answer engine. Thin
wrapper over chatbot.engine.answer_question: credentials sourcing and
exception handling are the only new logic here - see spec-chatbot-ui.md.
"""

import os

import gradio as gr

from chatbot.engine import answer_question

FARM_CODE = "NIS-001"  # single real farm today; multi-farm UI is deferred
GENERIC_ERROR_MESSAGE = "Something went wrong - please try again."


def handle_message(question: str) -> str:
    dsn = os.environ["FARM_INTELLIGENCE_DB_DSN"]
    try:
        answer = answer_question(question, farm_code=FARM_CODE, dsn=dsn)
    except Exception:
        return GENERIC_ERROR_MESSAGE
    return answer.text


def _chat_fn(message: str, history: list) -> str:
    # `history` is Gradio's own display state (past exchanges) - it is
    # deliberately never passed into handle_message/answer_question, per
    # the backend's no-multi-turn design (spec-chatbot-ui.md).
    return handle_message(message)


def build_interface() -> gr.ChatInterface:
    return gr.ChatInterface(
        fn=_chat_fn,
        title="Farm Intelligence",
        description="Ask a question about your farm's piggery, poultry, or crops data.",
    )


if __name__ == "__main__":
    build_interface().launch()
