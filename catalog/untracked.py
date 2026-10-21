"""
The hand-curated part of the capability catalog (plan sections 4 and 8): what the farm's data cannot answer, and why.

Everything the registry CAN answer is generated from the registry (catalog/build.py). This list covers what a schema cannot prove, in
three classes, and is the single source for the refusal text, the wording cues that must back a "not tracked" claim, the prompt's refusal
vocabulary and the numbered options offered when a refusal reads two ways:

    not_tracked         the farm does not record this at all (the text says what to log to make it answerable)
    tracked_no_metric   the data IS recorded (a table exists) but no metric reads it yet (the text must not deny it is recorded)
    policy              the data is recorded but the farm has decided chat must not show it (per-person pay)
    action              a request to change data; the bot is read-only

An LLM never asserts any of these by itself: a refusal needs the user's own words behind it (`cues`), else the answer is a question.
"""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Untracked:
    code: str
    kind: str                    # not_tracked | tracked_no_metric | policy | action
    hint: str                    # one line for the router prompt: when to choose this refusal
    text: str                    # the fixed reply
    cues: re.Pattern = None      # wording that must be present for the model's choice to stand (None: no support needed)
    near_metric: str = None      # the nearest tracked metric, offered when the wording does not back the claim or reads two ways
    option: str = ""             # the "not tracked" side of that numbered question
    tables: tuple = ()           # tracked_no_metric: the tables that hold the data

    @property
    def claim(self):
        return self.kind == "not_tracked"


def _rx(pattern):
    return re.compile(pattern)


KNOWN = (
    Untracked(
        "accounts_payable", "not_tracked", "money the farm OWES others",
        "This farm doesn't track money it owes to suppliers or others (accounts payable). Only money that customers owe "
        "the farm is recorded, and I can show that. To answer this, log supplier invoices with the amount, the due date "
        "and whether each one is paid.",
        None, "receivables", "Money the farm owes others (not recorded; I can explain what is)"),
    Untracked(
        "current_sickness", "not_tracked", "whether animals are sick right now",
        "Whether an animal is sick right now isn't recorded; only health events (treatments, vaccinations and inspections) "
        "are logged, and I can show those. To answer this, log a sick-animal status for each batch, with a date.",
        _rx(r"\b(sick|sickness|ill|illness|unwell|diseas\w*|infect\w*|outbreak|symptom\w*)\b"), "health_events",
        "Whether an animal is sick right now (not recorded; I can explain what is logged)"),
    Untracked(
        "forecast_weather", "not_tracked", "future weather",
        "Only past weather is logged; there is no forecast. I can show the latest logged day, or rainfall over a period.",
        _rx(r"\b(forecast|tomorrow|next (?:week|month|few days)|will it|going to rain|predict\w*|expected)\b"), "weather",
        "A weather forecast (not recorded; only past weather is logged)"),
    Untracked(
        "equipment", "not_tracked", "machinery, tractors, vehicles",
        "Equipment, machinery and vehicle records (such as service dates) aren't tracked.",
        _rx(r"\b(tractor|tractors|machine|machinery|machines|equipment|vehicle|vehicles|truck|trucks|generator|pump|serviced?|repairs?)\b")),
    Untracked(
        "company_info", "not_tracked", "ownership, legal, registration",
        "Company ownership, legal structure and registration details aren't recorded here.",
        _rx(r"\b(owner|owners|owns|owned|ownership|company|registered|registration|director|directors|shareholders?|legal|incorporated)\b")),
    Untracked(
        "payroll_history", "not_tracked", "what each person was paid and when",
        "Payroll history (what each person was paid, and when) isn't recorded; only the labour hours logged are, and I can show "
        "labour cost and hours. To answer this, log each payment with the person, the amount and the date.",
        _rx(r"\b(payroll|payslips?|pay ?slips?|salary history|pay history|paid out)\b"), "labour",
        "Payroll history (not recorded; I can explain what is)"),
    Untracked(
        "staff_info", "tracked_no_metric", "who works on the farm and their roles",
        "Staff names and roles are recorded, but I can't answer questions about them yet. I can show labour cost, "
        "hours worked and overtime.",
        _rx(r"\b(staff|employees?|workers?|labourers?|who works|people work\w*|supervisors?|roles?)\b"), "labour",
        "Staff names and roles (recorded, but I can't answer questions about them yet)", ("staff",)),
    Untracked(
        "staff_pay", "policy", "what an individual person is paid: pay rates, salary, wage per worker",
        "I don't show what individual people are paid. I can show total labour cost, hours worked and overtime for the farm "
        "or for a section.",
        _rx(r"\b(pay rates?|rates? of pay|hourly rates?|daily rates?|salary|salaries|wages?|earn\w*|paid|pay)\b"), "labour",
        "What an individual is paid (I don't show per-person pay; I can show total labour cost)"),
    Untracked(
        "crop_scouting", "tracked_no_metric", "crop pest, disease, weed or growth-stage scouting records",
        "Crop scouting records (pests, diseases, growth stage, soil moisture) are logged, but I can't answer questions about "
        "them yet. I can show the land planted, the crops grown and harvest yields.",
        _rx(r"\b(scout\w*|pests?|diseases?|aphids?|armyworm|blight|weeds?|infest\w*|growth stage|soil moisture)\b"), "crop_plantings",
        "Crop scouting records (recorded, but I can't answer questions about them yet)", ("scouting_log",)),
    Untracked(
        "field_operations", "tracked_no_metric", "crop field work: spraying, irrigation, applications, machine hours",
        "Field operations (sprayings, fertiliser and chemical applications, irrigation, machine and labour hours for each planting) "
        "are logged, but I can't answer questions about them yet. I can show what was spent on fertiliser and chemicals, and "
        "harvest yields.",
        _rx(r"\b(irrigat\w*|spray\w*|field operations?|machine hours|tractor hours|applied|application|applications|ploughing)\b"), "harvest_yield",
        "Field operations (recorded, but I can't answer questions about them yet)", ("field_operations",)),
    Untracked(
        "write_action", "action", "a request to change, add or delete data",
        "I can only read your farm's data; I can't change, add or delete records.",
        _rx(r"\b(delete|remove|update|change|edit|add|create|insert|erase|drop|modify|overwrite)\b")),
)

BY_CODE = {u.code: u for u in KNOWN}
OUT_OF_SCOPE = ("out_of_scope",
                "I can only answer questions about this farm's piggery, poultry and crops records, such as headcount, mortality, "
                "feed, expenses, revenue and who owes you money.")

# Tables no metric reads, and why. A table is either exposed by a metric (Metric.sources), listed here, or the coverage test fails.
UNEXPOSED = {
    "farm_profile": ("internal", "The farm's own settings: name, currency, which modules are on."),
    "list_values": ("internal", "The drop-down lists the workbook uses; not farm data."),
    "staff": ("tracked_no_metric", "Staff names, roles and pay rates. Decision (plan 24.2): chat never shows per-person pay (the staff_pay "
                                   "refusal); names and roles are recorded but no metric reads them yet."),
    "scouting_log": ("tracked_no_metric", "Crop scouting: pests, diseases, growth stage, soil moisture."),
    "field_operations": ("tracked_no_metric", "Crop field work: applications, irrigation, machine and labour hours per planting."),
}
