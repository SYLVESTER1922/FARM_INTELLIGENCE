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
    try:
        dsn = os.environ["FARM_INTELLIGENCE_DB_DSN"]
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


def _load_local_dev_credentials() -> None:
    """Only for running this app directly on a dev machine (python
    ui/app.py) - never invoked when this module is imported under test or
    deployed to Hugging Face Spaces (there, both env vars are provided by
    HF Spaces Secrets already). Loads what's missing from the same local
    credential files the rest of this project already uses, so `python
    ui/app.py` works without the developer having to export anything by
    hand first."""
    if "OPENAI_API_KEY" not in os.environ:
        key_path = os.path.expanduser("~/.openai_api_key")
        if os.path.exists(key_path):
            with open(key_path) as f:
                os.environ["OPENAI_API_KEY"] = f.read().strip()

    if "FARM_INTELLIGENCE_DB_DSN" not in os.environ:
        env_path = os.path.join(os.path.dirname(__file__), "..", ".env.supabase")
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    if line.startswith("SUPABASE_DB_DSN="):
                        os.environ["FARM_INTELLIGENCE_DB_DSN"] = line.strip().split("=", 1)[1]
                        break


if __name__ == "__main__":
    _load_local_dev_credentials()
    build_interface().launch()
