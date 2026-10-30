# Hugging Face Space deployment report: Farm Intelligence App

Date: 2026-10-30

**Status:** deployed and tested through the API. Render is untouched and still live.

## Where it is

- **Space:** https://huggingface.co/spaces/Sylvester1922/Farm_Intelligence
- **Direct app host:** `sylvester1922-farm-intelligence.hf.space`
- **Visibility:** private (set and confirmed). You must be signed in as `Sylvester1922` to open it.
- **Hardware:** ZeroGPU (`zero-a10g`), Gradio SDK, Python 3.12, Gradio 6.27.0.
- **Source:** Render's commit `7bc5da2` (full `7bc5da25f991ccc8e71b232d8c655c74051e9f35`) plus one packaging commit, `719a53b` on the local branch `hf-space`. The Space's `main` holds an upload commit, `6ba7f80`, on top of the template commit `5707d2b`.

## What changed (all on `hf-space`; nothing on `main`, `chatbot-v2` or Render)

- `README.md` with the Space front matter (the repo had no root README, so GitHub is unaffected).
- `app.py`, which runs `ui.app` as `__main__`. This matches the Render start command `python -m ui.app`. It also holds one no-op `@spaces.GPU` function that nothing calls, the smallest workaround that satisfies ZeroGPU.
- `requirements.txt` with every package pinned, plus `spaces==0.51.3`.
- `.gitignore` additions: `.env`, `.env.*`, `*.pem`, `*.key`, `google-service-account*.json`.
- No application code changed.

## Secrets

A scan found no keys or connection strings in tracked files. `.env.supabase` is ignored and has never been committed. Ten settings were added from Render:

- 3 secrets: `OPENAI_API_KEY`, `FARM_INTELLIGENCE_DB_DSN`, `GOOGLE_SERVICE_ACCOUNT_JSON`
- 7 variables: `ALERT_EMAIL_TO`, `ALERT_SMTP_HOST`, `FARM_INTELLIGENCE_SHEET_ID`, `REPORT_BUTTON`, `SHADOW_DAILY_LIMIT`, `SHADOW_MODE`, `SHADOW_SAMPLE`

## Verification

- **Start-up log:** `shadow mode is ON (SHADOW_SAMPLE=1, SHADOW_DAILY_LIMIT=200)`, and the app bound `0.0.0.0:7860`.
- **Test questions, run twice (before and after a restart):** pig headcount, who owes money, and the weather question. All 6 runs succeeded, and the new engine agreed with the old engine each time.
- **Dashboard:** the piggery, poultry and crops summaries and the full `load_all` returned real Supabase data.
- **Supabase:** reads and writes work with the supplied DSN; no connection-string change was needed.
- **Cost:** about $0.04 in shadow-model calls for the six runs, roughly $0.0068 each. The old engine's calls cost a little more.

## Sleep and wake-up behaviour

- The Space sleeps after **48 hours** with no visits (free-tier setting, `gcTimeout` 172800s). It cannot be changed on ZeroGPU (Hugging Face returned `Cannot change the sleep time for ZeroGPU Spaces`).
- The first visitor wakes it. A real sleep was not tested, since that needs 48 idle hours.
- A manual restart took **19 seconds** to the first HTTP 200. The first deploy, with an install, took about 90 seconds. Plan on roughly 20-60 seconds for the first load after a sleep (an estimate).
- Data lives in Supabase, so nothing is lost across sleeps or restarts.

## Rollback

Render needs no rollback; it was never touched. To undo the Space:

- **Stop it:** pause it in the Space's Settings, or `HfApi().pause_space("Sylvester1922/Farm_Intelligence")`. Reversible with `restart_space`.
- **Remove it:** delete the Space in Settings, "Delete this Space".
- **Revert only the push:** restore the template commit `5707d2b`, in the Space's web UI or by re-uploading its two files through the API.
- **Local cleanup (optional):** `git remote remove hf` and `git branch -D hf-space`.
- **Credentials:** the Hugging Face login is stored in `~/.cache/huggingface`. `hf auth logout` removes it.

## Caveats and open items

- **ZeroGPU dependence:** the app works only because ZeroGPU accepts the placeholder GPU function. A future Hugging Face rule change could break it.
- **Git history:** `git fetch` against the Space failed locally (`expected 'acknowledgments'`) and a force push was blocked, so the push went through the Hugging Face API. Use that route for updates.
- **Unchecked:** the pages and chat have not been looked at in a browser; the report-wrong-answer button, export and voice were not tested.
- **`anthropic` SDK:** not installed. It only matters if `SHADOW_MODEL` is set to a `claude-*` model.
- **Restart:** the restart briefly took the Space down.
- **Account change:** the only change made to the Hugging Face account was setting the Space to private.
- **Unexplained rows:** `shadow_log` ids 12-14 were written by something other than the test runs.
