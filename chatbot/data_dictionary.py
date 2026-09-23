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
- Accounts payable - money the farm owes to suppliers or creditors (only
  revenue owed TO the farm is tracked, a different thing).
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
    engine."""
    prompt = (
        "A farm-management chatbot could not answer a question with any "
        "of its existing data or tools. Below is a description of what "
        "this farm's data does and does not track. If the question is "
        "about something specific this farm genuinely doesn't track, "
        "explain that honestly and briefly in one sentence - name what's "
        "different about it if there's something similar that IS "
        "tracked (e.g. distinguish accounts payable from revenue owed to "
        "the farm). If the question isn't really about this farm's data "
        "at all, respond with exactly the single word NONE.\n\n"
        f"{DATA_DICTIONARY}\n\n"
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
