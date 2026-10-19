# The client's top 20 questions (plan step 0.5)

Collect the questions the client's own people actually ask, **in their own words** (spelling, shorthand and voice-style wording
included). Do not tidy them and do not invent any: the point is to see how real questions land on the registry before it is locked.

1. Copy `TEMPLATE.csv` to `questions.csv` (that name is git-ignored: it holds the client's data).
2. One row per question. `id` is any short label (q01, q02 ...), `question` is the exact wording, `who_asked` is a role
   (farm manager, bookkeeper ...), `how_often` is optional (daily, weekly, monthly), `notes` is anything the client said about it.
3. Run it (needs the OpenAI key, read from the environment or `~/.openai_api_key`; it uses the pinned router model unless `--model`):

   ```
   python -m evals.map_client_questions evals/client_questions/questions.csv
   ```

   It reads the router's spec for each question (no database, no answers computed) and writes `mapping-<timestamp>.md` and `.csv`
   next to the input (both git-ignored), with each question as **matched** (one registry metric), **ambiguous** (the model could not
   choose between metrics, or the wording points to a different metric than the model chose) or **no metric** (nothing in the registry
   answers it, with the refusal class). It also lists the registry metrics no question reached.
4. Decide for each ambiguous or no-metric question whether to add a metric or keep a named refusal. Lock the registry only after that.
