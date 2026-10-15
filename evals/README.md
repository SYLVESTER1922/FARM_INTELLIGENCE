# Eval harness (dev set only)

Measures what the chatbot actually returns, end to end, against an independent oracle.
See `spec-chatbot-v2-plan.md`, section 11.

**Safety.** The harness drops and rebuilds the `public` schema of the database it uses, so
`evals/guard.py` refuses to run unless `DATABASE_URL` names the LOCAL `farm_intelligence_test`
database (checked on the URL and again on the live connection). It never touches Supabase.

```
export DATABASE_URL=postgresql://$USER@localhost/farm_intelligence_test
python -m evals.run --dump-review                       # writes evals/REVIEW_dev_cases.md, no LLM calls
python -m evals.run --engine-root <repo-or-worktree> --label <name> [--repeats 3] [--only id1,id2]
python -m pytest tests/test_evals_harness.py            # guard + scorer unit tests
```

- The fixture is built from `Netrisyl_Farm_Intelligence_Workbook.xlsx` through the production sync
  (read-only on the workbook; `gen_scripts/` is not touched).
- Golden figures come from `evals/oracle.py` (its own SQL; imports nothing from `chatbot/` or `ui/`).
- Each question runs `--repeats` times; a case is **wrong if any repeat is wrong**.
- Buckets: correct / wrong (by reason) / refused / clarified, plus unscored (definition pending).
- Every case is `split="dev"`. `locked` cases are refused unless `--include-locked`, and nothing may
  be locked until Sylvester and Tadiwanashe Dzimbanete have reviewed it.
- Results are written to `evals/results/<label>-<timestamp>.json` (untracked).

To compare engine versions, point `--engine-root` at a separate checkout, e.g.
`git worktree add --detach <dir> c6e455e` (and `git stash apply` inside it for the stashed fixes).
Run versions one after the other: they share the fixture database.

Eval clock: today = 2026-10-15 (Africa/Harare). Latest data in the fixture = 2026-09-15.
