"""
Named refusals: fixed, hand-written text for the things this farm's data cannot answer (plan decisions: accounts payable and
"currently sick" state exactly what isn't tracked and what the farm would need to log). Never model-authored. `claim` refusals say
that something isn't tracked (the eval checks they never deny data that IS tracked); `generic` ones are plain limits.
"""

from catalog.untracked import KNOWN, OUT_OF_SCOPE

NAMED = {u.code: ("claim" if u.claim else "generic", u.text) for u in KNOWN}
NAMED[OUT_OF_SCOPE[0]] = ("generic", OUT_OF_SCOPE[1])

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
