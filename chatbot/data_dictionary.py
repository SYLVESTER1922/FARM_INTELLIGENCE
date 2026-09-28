"""
A hand-maintained, curated description of what this farm's data does and
does not track - domain by domain, in farm-owner-legible language, never
raw table/column names. Used only when a question reaches a genuine full
miss (tier-0/1/2/3 have all failed), so the refusal can honestly
distinguish "we don't track that at all" from a generic "can't answer" -
e.g. real accounts-payable questions (money the farm owes suppliers) vs.
the crop_debtor finding's revenue tracking (money owed TO the farm).

Deliberately not derived from live schema introspection - see
spec-chatbot-catalog-expansion.md's honesty decision. Keep this in sync by
hand whenever a new tier-1/tier-3 capability is added or a genuinely new
"we don't track this" gap is identified (e.g. via real query_log misses).
"""

DATA_DICTIONARY = """
This farm's chatbot can answer questions from data the farm actually tracks:
- Piggery: batch records (breed, start count/weight, status), daily logs
  (feed, deaths, culls, closing headcount), weight samples, health and
  treatment events, breeding and farrowing records.
- Poultry: batch records (chicks placed, breed, house), daily logs (feed,
  deaths, culls, closing headcount), weight samples.
- Crops: plot records, plantings (crop, area planted, planting date),
  harvest records.
- Shared: farm profile and staff, expenses, revenue (money OWED TO the
  farm by customers/buyers - not money the farm owes to others), labour
  logs, feed inventory, and a daily weather log (historical records only,
  not a live forecast).

This farm's chatbot CANNOT answer questions about data that isn't tracked
at all:
- Accounts payable, e.g. "do we owe anyone?" or "are we owing anyone?" -
  money the farm owes to suppliers or creditors (only revenue owed TO the
  farm is tracked, a different thing).
- Staff payroll history, tax records, or anything beyond each staff
  member's current pay rate.
- Equipment, machinery, or vehicle inventory or maintenance records.
- Live or forecast weather - only a historical daily log of past
  conditions.
- Company ownership, legal structure, or business registration.
"""


def explain_gap(question: str, openai_client) -> str | None:
    """One bounded LLM call, made only when nothing at any tier resolved
    the question. Given DATA_DICTIONARY, asks whether there's a specific,
    honest reason to name for this particular question. Returns None for
    a genuinely generic miss (not farm-data-adjacent at all), in which
    case the caller falls back to the plain unresolved message - a single
    attempt, no retry, same precedent as every other LLM call in this
    engine.

    A real reliability issue found via a QA pass: the model would default
    to NONE for a short, indirectly-phrased question ("do we owe anyone?")
    even though it names a specific concept in the CANNOT-answer list
    below (accounts payable) - it read "short/vague-sounding" as "not
    really about this farm's data" rather than checking the list first.
    Verified over several repeated trials before and after this fix - the
    dictionary text alone (adding example phrasings) was NOT enough on its
    own and one earlier, longer attempt at it actually regressed a
    previously-reliable case; the instruction below explicitly telling the
    model to check the list even for short questions is what fixed it,
    confirmed stable across repeated trials with zero regression on the
    already-working longer phrasing."""
    prompt = (
        "A farm-management chatbot could not answer a question with any "
        "of its existing data or tools. Below is a description of what "
        "this farm tracks and does not track. Check the second list (what "
        "it cannot answer) carefully even for a short or indirectly-"
        "phrased question - a brief question like \"do we owe anyone?\" "
        "still names a specific concept in that list (accounts payable) "
        "and must be matched to it, not dismissed as too vague.\n\n"
        f"{DATA_DICTIONARY}\n\n"
        "If the question matches an item in that second list, state "
        "plainly and factually, in one sentence, what is not tracked and "
        "(if relevant) what similar thing IS tracked instead - do not "
        "begin the sentence with phrases like \"cannot answer\" or \"the "
        "chatbot cannot\", just state the fact directly (e.g. \"This farm "
        "does not track X...\"). If the question matches neither list at "
        "all, respond with exactly the single word NONE.\n\n"
        f"Question: {question}"
    )
    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=100,
        temperature=0,
    )
    text = (response.choices[0].message.content or "").strip()
    if text.upper() == "NONE":
        return None
    return text
