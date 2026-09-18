# 02: Deploy to a private Hugging Face Space

**What to build:** The chat app is live on a private, password-protected Hugging Face
Space — matching where JCC-Chatbot and the Pharmacy Assistant already run — so a farm
owner (or the developer, for now) can actually reach it via a URL, protected from
public/unauthenticated access given the sensitivity of the data in the chatbot's answers.

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] The app from ticket 01 is deployed to a Hugging Face Space.
- [ ] The Space's visibility is set to private / password-protected (HF's built-in
      setting) — verified manually by confirming the Space prompts for a password
      before showing the chat interface to an unauthenticated visitor.
- [ ] `DSN` and `OPENAI_API_KEY` are both provided to the deployed app via Hugging Face
      Spaces Secrets (environment variables), never committed to the repo or hardcoded —
      mirroring the credentials pattern already used locally in ticket 01.
- [ ] A real question asked against the live deployed Space returns a correct answer,
      confirming the deployed environment's credentials and connectivity (to both
      Postgres/Supabase and OpenAI) work end-to-end — verified manually, not via an
      automated test, per the spec's own Testing Decisions (platform/deployment
      configuration isn't something to unit test).
- [ ] The deployed Space's URL and password are recorded somewhere accessible to the
      user (not committed to the repo) for future reference.

**Note for whoever starts this ticket:** deploying to Hugging Face Spaces will need the
user's own HF account and credentials, similar to how Supabase and OpenAI setup went
earlier in this project — expect to ask the user to create a Space and hand over
access the same secure way (credentials saved to a local file by the user, never pasted
into chat).
