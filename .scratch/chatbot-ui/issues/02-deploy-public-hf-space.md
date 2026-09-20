# 02: Deploy to a public Hugging Face Space

**What to build:** The chat app is live on a public Hugging Face Space, free CPU tier —
matching where JCC-Chatbot and the Pharmacy Assistant already run — so a farm owner (or
anyone) can actually reach it via a URL. No access control: this app's data is the
project's synthetic demo dataset (Chiedza Mixed Farm), not a real farm's real records,
the same situation as both sibling products.

**Correction from the original ticket**: this was initially scoped as a *private*,
password-protected Space, based on treating the chatbot's data as sensitive real farm
records. Checked directly against Hugging Face's own docs before starting this ticket:
HF Spaces has no literal password-prompt feature separate from visibility — true
"Private" visibility requires every viewer to have their own HF account and be added as
a collaborator, a much heavier UX than "type a password." The user then clarified this
app's data is synthetic/demo, the same category as JCC-Chatbot and the Pharmacy
Assistant, which are both public — so access control isn't warranted here at all, and
this ticket (and `spec-chatbot-ui.md`) were corrected accordingly before implementation.

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] The app from ticket 01 is deployed to a Hugging Face Space.
- [ ] The Space's visibility is **public**, and it runs on the **free CPU tier** (no GPU
      needed for this chatbot) — matching how JCC-Chatbot and the Pharmacy Assistant are
      hosted, not a paid compute plan.
- [ ] `FARM_INTELLIGENCE_DB_DSN` and `OPENAI_API_KEY` are both provided to the deployed
      app via Hugging Face Spaces Secrets (environment variables), never committed to
      the repo or hardcoded — mirroring the credentials pattern already used locally in
      ticket 01.
- [ ] A real question asked against the live deployed Space returns a correct answer,
      confirming the deployed environment's credentials and connectivity (to both
      Postgres/Supabase and OpenAI) work end-to-end — verified manually, not via an
      automated test, per the spec's own Testing Decisions (platform/deployment
      configuration isn't something to unit test).
- [ ] The deployed Space's URL is recorded somewhere accessible to the user for future
      reference.

**Note for whoever starts this ticket:** deploying to Hugging Face Spaces needs the
user's own HF account and credentials, similar to how Supabase and OpenAI setup went
earlier in this project — expect to ask the user for a personal access token, saved to
a local file the same secure way as those, never pasted into chat.
