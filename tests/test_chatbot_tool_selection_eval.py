"""
A holistic, cross-tool tool-selection accuracy eval - distinct from every
per-tool "resolve_tool_call picks X for canonical phrasings" test elsewhere
in this suite (those stay as narrow sanity checks for one tool at a time).
This file exists to answer a different question: across the *whole* tier-3
tool set at once, how often does resolve_tool_call pick the right tool (or
correctly pick none)? That number is what turns "how accurate is the
chatbot" from a guess into something measured and enforced.

Sourced from two places, deliberately not invented fresh:
- Every tool's own canonical phrasings (harvested from its
  test_chatbot_tier3_*.py file) - re-run here together, in one shared
  OpenAI-call context, rather than 19 separate ones.
- Real historical bugs found during this project's QA passes: FCR vs.
  mortality-rate confusion, expense-category vs. expense-domain
  conflation, and the "is something wrong with a batch"/"do we owe
  anyone" cases that must resolve to NO tool at all (a genuinely
  ambiguous or genuinely untracked question, left for tier-1/tier-2's
  ambiguity handling or chatbot/data_dictionary.py's honest refusal -
  never a guessed tool call). Each of these is re-tested here with a
  *different* paraphrasing than its own regression test uses, to actually
  stress the confusion boundary rather than re-assert an exact phrase.

95% is an explicit, real threshold (not just "as high as possible") -
matching this project's own accuracy target for tool selection. A failure
here means real, actionable regressions: the printed report names exactly
which questions were misrouted and to what, the same information that
would otherwise only surface after a real user hits it in production.
"""

import openai
import pytest

from chatbot.tools import resolve_tool_call

ACCURACY_THRESHOLD = 0.95

# (question, expected_tool_name_or_None, category)
EVAL_CASES = [
    # --- one tool's own canonical phrasings, all 19 tier-3 tools ---
    ("How many pigs do we have?", "q_headcount", "canonical"),
    ("How many pigs do we have?", "q_headcount", "canonical"),
    ("how many chickens do we have right now", "q_headcount", "canonical"),
    ("How many hectares of crop is planted?", "q_crop_area_planted", "canonical"),
    ("How many hectres of crop is planted?", "q_crop_area_planted", "canonical"),
    ("how much land is planted with crops", "q_crop_area_planted", "canonical"),
    ("What's the weather like today?", "q_weather", "canonical"),
    ("how much rain have we had", "q_weather", "canonical"),
    ("What crops do we have?", "q_crop_types", "canonical"),
    ("which crops are we growing", "q_crop_types", "canonical"),
    ("What's the expense amount to date?", "q_expenses_to_date", "canonical"),
    ("how much have we spent so far", "q_expenses_to_date", "canonical"),
    ("Compare piggery and poultry costs this year", "q_expenses_by_domain", "canonical"),
    ("which domain costs more, piggery or poultry", "q_expenses_by_domain", "canonical"),
    ("What's our biggest expense category overall?", "q_expense_by_category", "canonical"),
    ("how much do we spend on feed versus labour", "q_expense_by_category", "canonical"),
    ("Which batch has the worst feed conversion ratio?", "q_fcr_ranking", "canonical"),
    ("which batch has the best FCR", "q_fcr_ranking", "canonical"),
    ("What's the cost per pig?", "q_cost_per_animal", "canonical"),
    ("cost per bird", "q_cost_per_animal", "canonical"),
    ("Is the piggery profitable?", "q_profit", "canonical"),
    ("are we making money", "q_profit", "canonical"),
    ("What's our mortality rate for the whole farm?", "q_mortality_rate", "canonical"),
    ("How many chickens died last week?", "q_mortality_rate", "canonical"),
    ("What's our total labour cost this month?", "q_labour_summary", "canonical"),
    ("overtime hours for piggery", "q_labour_summary", "canonical"),
    ("Which plot yields best per hectare?", "q_harvest_yield", "canonical"),
    ("how efficient was our maize harvest", "q_harvest_yield", "canonical"),
    ("How many litters this month?", "q_breeding_summary", "canonical"),
    ("which sow had the biggest litter", "q_breeding_summary", "canonical"),
    ("How much feed do we have left?", "q_feed_stock", "canonical"),
    ("are we running low on feed", "q_feed_stock", "canonical"),
    ("What's the average weight of batch PIG-B01?", "q_batch_weight", "canonical"),
    ("how heavy are the pigs right now", "q_batch_weight", "canonical"),
    ("Which batches are ready to sell?", "q_market_readiness", "canonical"),
    ("are any pigs overdue for market", "q_market_readiness", "canonical"),
    ("How much have we spent on vet care this month?", "q_health_cost_summary", "canonical"),
    ("vet cost trend", "q_health_cost_summary", "canonical"),
    ("Who's our biggest buyer?", "q_revenue_breakdown", "canonical"),
    ("what's our best-selling product", "q_revenue_breakdown", "canonical"),

    # --- adversarial: real historical confusions, new paraphrasings ---
    # FCR vs. mortality rate (matcher.py's Jaccard-scoring bug, section 6
    # round 3) - a fresh paraphrasing of the same confusion boundary.
    ("What's the feed efficiency of our worst-performing batch?", "q_fcr_ranking", "adversarial"),
    # expense category vs. expense domain (round 3's conflation bug).
    ("Which expense category costs us the most?", "q_expense_by_category", "adversarial"),
    ("How does spending compare between piggery and poultry?", "q_expenses_by_domain", "adversarial"),

    # --- negative: must resolve to NO tool at all ---
    # genuinely domain-ambiguous - piggery disease vs. poultry mortality,
    # must be left for tier-1/tier-2's ambiguity handling, never guessed.
    ("is something wrong with a batch", None, "negative"),
    ("Something seems off with one of our batches", None, "negative"),
    # accounts payable - the real "owing" bug (section 6, round 1 and the
    # follow-up round's debt-question fix) - untracked, must never be
    # guessed at with q_expenses_to_date or any other tool.
    ("Do we owe anyone money?", None, "negative"),
    ("Are we owing anyone?", None, "negative"),
    ("What accounts payable does the farm have?", None, "negative"),
    # genuinely out of scope.
    ("what's the capital of France", None, "negative"),
    ("who owns the company?", None, "negative"),
]


def test_tool_selection_accuracy_meets_threshold():
    client = openai.OpenAI()
    misses = []

    for question, expected, category in EVAL_CASES:
        result = resolve_tool_call(question, client)
        if result.tool_name != expected:
            misses.append((question, expected, result.tool_name, category))

    total = len(EVAL_CASES)
    correct = total - len(misses)
    accuracy = correct / total

    if misses:
        report_lines = [
            f"{accuracy:.1%} accuracy ({correct}/{total}) - misses:",
        ]
        for question, expected, actual, category in misses:
            report_lines.append(
                f"  [{category}] {question!r}: expected {expected!r}, got {actual!r}"
            )
        report = "\n".join(report_lines)
    else:
        report = f"{accuracy:.1%} accuracy ({correct}/{total}) - no misses"

    print(report)
    assert accuracy >= ACCURACY_THRESHOLD, report
