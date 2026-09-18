# 01: Local Gradio chat app

**What to build:** A farm owner (or developer testing locally) can run the Gradio app on
their machine, type a question into the chat interface, and get a real answer from
`answer_question` — or, if something goes wrong internally, a safe generic error message
instead of a crash or raw traceback. Chat history displays in the UI but is never fed
back into `answer_question` as context.

**Blocked by:** None (can start immediately)

**Status:** done

- [x] A message-handler function (e.g. `handle_message(question) -> str`) exists as the
      one seam, wired directly to Gradio's chat interface component.
      (`ui/app.py`: `handle_message`, wired via `_chat_fn` into `gr.ChatInterface`)
- [x] The handler calls `answer_question(question, farm_code=FARM_CODE, dsn=DSN)` with a
      hardcoded `FARM_CODE` (single real farm today, per the spec's deferred
      multi-farm decision) and `DSN` read from an environment variable — never a
      hardcoded path, never a local dotfile. (`FARM_CODE = "NIS-001"`,
      `os.environ["FARM_INTELLIGENCE_DB_DSN"]`)
- [x] Asking a real, answerable question through the running app returns the correct
      answer text (delegates correctly to the already-tested `answer_question`).
      (`test_handle_message_answers_a_real_question` — real Postgres query, real OpenAI
      phrasing call, same fixture pattern as `tests/test_chatbot_engine.py`)
- [x] If `answer_question` raises any exception, the handler catches it and returns a
      fixed, generic message (e.g. "Something went wrong — please try again.") — never a
      raw exception or traceback.
      (`test_handle_message_returns_generic_message_when_answer_question_raises` —
      injects a failure via `monkeypatch.setattr(ui.app, "answer_question", ...)`, the
      agreed exception at the seam boundary per the spec's Testing Decisions)
- [x] The Gradio chat interface displays a running history of past exchanges (Gradio's
      default chat behavior), but no prior messages or history are ever passed into
      `answer_question` — confirmed by inspecting the handler's call, since
      `answer_question`'s own signature only accepts a single question string.
      (`_chat_fn(message, history)` receives Gradio's history but never forwards it —
      only `message` reaches `handle_message`)
- [x] No module selector, farm switcher, or per-tier latency messaging exists — pure
      free-text Q&A with Gradio's default waiting indicator only.
- [x] Tests cover the handler function directly (happy path + exception handling via a
      simulated failure, since `answer_question` won't naturally raise on demand), not
      Gradio's rendering. Separately sanity-checked (not a unit test) that
      `build_interface()` actually constructs a `gr.ChatInterface` without error.

70 tests total (2 new), all passing.
