"""
Named refusals: fixed, hand-written text for the things this farm's data cannot answer (plan decisions: accounts payable and
"currently sick" state exactly what isn't tracked and what the farm would need to log). Never model-authored. `claim` refusals say
that something isn't tracked (the eval checks they never deny data that IS tracked); `generic` ones are plain limits.
"""

NAMED = {
    "accounts_payable": ("claim",
        "This farm doesn't track money it owes to suppliers or others (accounts payable). Only money that customers owe "
        "the farm is recorded, and I can show that. To answer this, log supplier invoices with the amount, the due date "
        "and whether each one is paid."),
    "current_sickness": ("claim",
        "Whether an animal is sick right now isn't recorded; only health events (treatments, vaccinations and inspections) "
        "are logged, and I can show those. To answer this, log a sick-animal status for each batch, with a date."),
    "forecast_weather": ("claim",
        "Only past weather is logged; there is no forecast. I can show the latest logged day, or rainfall over a period."),
    "equipment": ("claim",
        "Equipment, machinery and vehicle records (such as service dates) aren't tracked."),
    "company_info": ("claim",
        "Company ownership, legal structure and registration details aren't recorded here."),
    "write_action": ("generic",
        "I can only read your farm's data; I can't change, add or delete records."),
    "out_of_scope": ("generic",
        "I can only answer questions about this farm's piggery, poultry and crops records, such as headcount, mortality, "
        "feed, expenses, revenue and who owes you money."),
}

LLM_DOWN = "I can't process questions right now. Please try again in a few minutes."
LLM_BUSY = "I'm busy right now and couldn't process that. Please try again in a minute."
COULD_NOT_READ = ("I couldn't tell what you're asking. Could you say it another way, for example "
                  "\"how many pigs do we have?\" or \"what was our feed cost last month?\"")
NO_SUBJECT = ("Could you clarify what you'd like to know? For example, a section of the farm (piggery, poultry, crops), a "
              "figure (headcount, mortality, feed cost, expenses) or a time period.")
FOLLOW_UP_WITHOUT_CONTEXT = ("I need a bit more to go on: what would you like to know? For example \"feed cost last month\" "
                             "or \"how many pigs do we have?\"")


def kind(code: str) -> str:
    return NAMED[code][0]


def text(code: str) -> str:
    return NAMED[code][1]
