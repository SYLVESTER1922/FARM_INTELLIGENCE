# 02: Deploy to a public web app

**What to build:** The chat app is live on a public URL, free tier, no access control —
so a farm owner (or anyone) can actually reach it via a browser. This app's data is the
project's synthetic demo dataset (Chiedza Mixed Farm), not a real farm's real records,
the same situation as JCC-Chatbot and the Pharmacy Assistant.

**Correction from the original ticket (private HF Space)**: initially scoped as a
*private*, password-protected Hugging Face Space, based on treating the chatbot's data
as sensitive. Checked directly against HF's own docs: HF Spaces has no literal
password-prompt feature separate from visibility. The user then clarified this app's
data is synthetic/demo, the same category as the two sibling products (both public) — so
access control isn't warranted at all. Spec and ticket were corrected to public/no-auth
before implementation.

**Second correction from the original ticket (platform: HF Spaces → Render)**: Hugging
Face was the originally planned host, matching the sibling products. In practice, every
compute-backed free path on HF was tested directly and confirmed blocked, not assumed:

- `cpu-basic` under the `Netrisyl` org → 402, requires a Team/Enterprise plan for the org.
- `zero-a10g` (ZeroGPU) under the `Netrisyl` org → 402, same Team/Enterprise requirement.
- `zero-a10g` under the personal account → *creation succeeded*, but the deployed Space
  hit `RUNTIME_ERROR`: `"No @spaces.GPU function detected during startup"`. ZeroGPU
  requires an actual `@spaces.GPU`-decorated function; this chatbot has no GPU workload,
  so there's nothing genuine to decorate. Faking one just to pass the platform's startup
  check was rejected as gaming the gate, not a real fit.
- `cpu-basic` under the personal account → 402, requires a PRO subscription. This is a
  platform-wide requirement (confirmed after deleting and recreating the Space fresh so
  a stale ZeroGPU hardware assignment couldn't confound the result), not a per-namespace
  or per-slot quota — pausing another Space (`Netrisyl/JCC_AFM_CHAT_BOT`) to free capacity
  did not help, because the blocker was plan tier, not slot count.

With every free HF compute path exhausted, the app was deployed to **Render** instead
(free tier, Python web service, deployed straight from the public GitHub repo). This
needed two small additions to make the app deployable outside HF's Spaces runtime, which
handles these implicitly:

- A root-level `requirements.txt` (`gradio==6.27.0`, `openai>=1.0.0`,
  `psycopg[binary]>=3.1.0`), since Render has no bundled dependency set the way an HF
  Space's `README.md` YAML frontmatter provides.
- `ui/app.py`'s `launch()` call now binds `server_name="0.0.0.0"` and
  `server_port=int(os.environ.get("PORT", 7860))`, since Render assigns the listen port
  via `$PORT` at runtime rather than a fixed port. Local dev is unaffected (falls back to
  7860 when `$PORT` is unset).
- The start command runs the app as a module (`python -m ui.app`, not `python
  ui/app.py`), so the repo root stays on `sys.path` and the `chatbot` package resolves
  from the top-level app process the same way it does under pytest.

**Third finding, not a code bug**: the first live deploy returned the generic error
message for every question despite verified-correct credentials. Root cause: Supabase's
**direct** database host (`db.<ref>.supabase.co`) resolves only to an IPv6 address (no
`A` record, only `AAAA`) on this project's tier, and Render's free web services have no
IPv6 egress — so every DB connection attempt failed silently into the generic error
message. Fixed by switching `FARM_INTELLIGENCE_DB_DSN` to Supabase's connection pooler
(Supavisor) host instead (`aws-0-us-west-2.pooler.supabase.com:6543`, user
`postgres.<project_ref>`, transaction pool mode), which does resolve to IPv4. Verified by
direct `psycopg` connection test before rolling the change out to Render.

**A related incident during this ticket**: while diagnosing the DSN, a shell command's
redaction regex only matched `://user:pass@` URL syntax and missed the DSN's actual
`key=value` libpq format, printing the real Supabase DB password into the chat
transcript. The password was immediately rotated via the Supabase Management API (value
never printed), `.env.supabase` and the Render secret were both updated to the new
value, and the new password was verified with a real connection before being rolled out
— the same "real proof, not assumption" discipline used throughout this project.

**Blocked by:** 01

**Status:** done

- [x] The app from ticket 01 is deployed and reachable at a public URL:
      `https://netrisyl-farm-intelligence.onrender.com`.
- [x] The deployment is public with no access control, and runs on Render's **free**
      web service tier — no paid compute plan, consistent with the spec's intent (the
      platform changed from HF to Render; the free-tier, no-auth requirement did not).
- [x] `FARM_INTELLIGENCE_DB_DSN` and `OPENAI_API_KEY` are both provided to the deployed
      app via Render's environment variable / secrets mechanism, never committed to the
      repo or hardcoded — mirroring the credentials pattern already used locally in
      ticket 01.
- [x] A real question asked against the live deployed app returns a correct answer,
      confirming the deployed environment's credentials and connectivity (to both
      Postgres/Supabase and OpenAI) work end-to-end — verified manually via
      `gradio_client` against the live URL, not via an automated test, per the spec's own
      Testing Decisions (platform/deployment configuration isn't something to unit
      test). Also verified the scoped-out/out-of-catalog refusal path still returns a
      clean, non-error message on the deployed app.
- [x] The deployed app's URL is recorded here for future reference:
      `https://netrisyl-farm-intelligence.onrender.com`.
