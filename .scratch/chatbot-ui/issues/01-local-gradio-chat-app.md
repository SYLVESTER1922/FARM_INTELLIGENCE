# 01: Local Gradio chat app

**What to build:** A farm owner (or developer testing locally) can run the Gradio app on
their machine, type a question into the chat interface, and get a real answer from
`answer_question` — or, if something goes wrong internally, a safe generic error message
instead of a crash or raw traceback. Chat history displays in the UI but is never fed
back into `answer_question` as context.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] A message-handler function (e.g. `handle_message(question) -> str`) exists as the
      one seam, wired directly to Gradio's chat interface component.
- [ ] The handler calls `answer_question(question, farm_code=FARM_CODE, dsn=DSN)` with a
      hardcoded `FARM_CODE` (single real farm today, per the spec's deferred
      multi-farm decision) and `DSN` read from an environment variable — never a
      hardcoded path, never a local dotfile.
- [ ] Asking a real, answerable question through the running app returns the correct
      answer text (delegates correctly to the already-tested `answer_question`).
- [ ] If `answer_question` raises any exception, the handler catches it and returns a
      fixed, generic message (e.g. "Something went wrong — please try again.") — never a
      raw exception or traceback.
- [ ] The Gradio chat interface displays a running history of past exchanges (Gradio's
      default chat behavior), but no prior messages or history are ever passed into
      `answer_question` — confirmed by inspecting the handler's call, since
      `answer_question`'s own signature only accepts a single question string.
- [ ] No module selector, farm switcher, or per-tier latency messaging exists — pure
      free-text Q&A with Gradio's default waiting indicator only.
- [ ] Tests cover the handler function directly (happy path + exception handling via a
      simulated failure, since `answer_question` won't naturally raise on demand), not
      Gradio's rendering.
