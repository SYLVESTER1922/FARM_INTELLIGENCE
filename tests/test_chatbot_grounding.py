import decimal

import chatbot.engine
from chatbot.engine import _run_tool_call
from chatbot.grounding import (
    fallback_narration,
    is_grounded,
    numbers_in_data,
    numbers_in_text,
)
from chatbot.tools import ToolCallResult
from sync.engine import sync_workbook_to_supabase
from tests.fixtures import base_fixture
from tests.workbook_builder import build_workbook


def test_numbers_in_data_walks_nested_dicts_and_lists():
    computed = [{
        "total": 24.0,
        "as_of": "2026-09-15",
        "by_plot": [
            {"plot_code": "PL1", "yield_kg_per_ha": 22625.0},
            {"plot_code": "PL2", "yield_kg_per_ha": 2300.0},
        ],
    }]

    assert numbers_in_data(computed) == {24.0, 22625.0, 2300.0}


def test_numbers_in_data_excludes_booleans():
    assert numbers_in_data([{"found": True, "count": 0}]) == {0.0}


def test_numbers_in_data_includes_decimal_values():
    # a real production bug: tier-1 catalog queries return raw
    # decimal.Decimal columns from psycopg (unlike tier-3 tools, which
    # float()-cast everything) - the first version of this function only
    # checked (int, float), silently treating every Decimal as "not a
    # number," so numbers_in_data came back empty for any tier-1 answer.
    assert numbers_in_data([{"total_amount": decimal.Decimal("8681.12")}]) == {8681.12}


def test_is_grounded_true_for_decimal_backed_data():
    computed = [{"buyer": "Chikafu Grain Traders", "total_amount": decimal.Decimal("8681.12")}]

    assert is_grounded(
        "Chikafu Grain Traders is owing you 8681.12.", computed,
    )


def test_numbers_in_text_ignores_digits_inside_known_batch_codes():
    computed = [{"batch_code": "PIG-B01", "avg_weight_kg": 67.9}]

    # "01" inside "PIG-B01" must never be read as a freestanding number
    numbers = numbers_in_text("Batch PIG-B01 weighs 67.9 kg.", computed)

    assert numbers == {67.9}


def test_numbers_in_text_ignores_digits_inside_known_dates():
    computed = [{"as_of": "2026-09-15", "total": 45.0}]

    numbers = numbers_in_text("As of 2026-09-15, the total is 45.0.", computed)

    assert numbers == {45.0}


def test_numbers_in_text_handles_comma_formatting():
    computed = [{"total_revenue": 32240.48}]

    numbers = numbers_in_text("Total revenue is 32,240.48.", computed)

    assert numbers == {32240.48}


def test_is_grounded_true_for_correct_narration():
    computed = [{"total_expenses": 27360.0, "domain": "piggery"}]

    assert is_grounded(
        "The total expenses for piggery are 27360.0.", computed,
    )


def test_is_grounded_false_for_a_fabricated_number():
    computed = [{"total_expenses": 27360.0, "domain": "piggery"}]

    # the real failure mode this module exists to catch: a plausible-looking
    # but entirely invented number that never appeared in the computed data
    assert not is_grounded(
        "The total expenses for piggery are approximately 50000.0.", computed,
    )


def test_is_grounded_false_when_a_real_number_is_altered():
    computed = [{"headcount": 12}]

    # off by one from the real data - must not be waved through as "close enough"
    assert not is_grounded("The current headcount is 13.", computed)


def test_is_grounded_true_for_a_real_negative_number():
    # a real production bug: the number regex stripped the leading "-",
    # so a genuine loss (a negative profit) was read as its positive
    # counterpart and never matched the real (negative) data value,
    # wrongly discarding a correct narration.
    computed = [{"domain": "piggery", "profit": -5563.5}]

    assert is_grounded(
        "Piggery had a profit of -5563.5 this period.", computed,
    )


def test_is_grounded_false_when_the_sign_is_flipped():
    computed = [{"profit": -5563.5}]

    # the real failure this exists to catch: a genuinely wrong number
    # (positive) that happens to share magnitude with the real (negative)
    # one must still be rejected, not waved through by abs() comparison
    assert not is_grounded("The profit is 5563.5.", computed)


def test_numbers_in_text_captures_leading_minus_sign():
    computed = [{"total_amount": -25.0}]

    assert numbers_in_text("the amount is -25.0", computed) == {-25.0}


def test_numbers_in_text_ignores_a_known_date_reformatted_as_prose():
    # a real, frequently-triggered production false positive: the LLM
    # reformatted a known ISO date ("2026-06-17") as prose ("June 17,
    # 2026") - the literal-substring erasure alone never catches this, so
    # 2026/17 leaked through as apparently-fabricated numbers roughly 1 in
    # 5-6 real trials of an ordinary question.
    computed = [{"window_start": "2026-06-17", "deaths": 0}]

    numbers = numbers_in_text(
        "There were 0 deaths from June 17, 2026 onward.", computed,
    )

    assert numbers == {0.0}


def test_numbers_in_text_ignores_a_known_date_reformatted_day_first():
    computed = [{"window_start": "2026-06-17", "deaths": 0}]

    numbers = numbers_in_text(
        "There were 0 deaths from 17 June 2026 onward.", computed,
    )

    assert numbers == {0.0}


def test_numbers_in_text_still_flags_a_prose_date_that_does_not_match_real_data():
    # the guard is specific, not a blanket "any Month DD, YYYY is fine" -
    # a genuinely wrong/fabricated date must still be caught.
    computed = [{"window_start": "2026-06-17", "deaths": 0}]

    numbers = numbers_in_text(
        "There were 0 deaths from July 4, 2026 onward.", computed,
    )

    assert 2026.0 in numbers
    assert 4.0 in numbers


def test_numbers_in_text_still_ignores_a_hyphenated_identifier_suffix():
    # "-25A" glued onto "PL2" must not be misread as "-25" - the character
    # immediately before the hyphen ("2") is itself alphanumeric, so the
    # lookbehind still correctly blocks a match starting there.
    computed = [{"batch_ref": "SB-PL2-25A"}]

    assert numbers_in_text("batch ref SB-PL2-25A", computed) == set()


def test_fallback_narration_mentions_every_top_level_scalar_field():
    computed = [{"domain": "piggery", "total_expenses": 27360.0}]

    text = fallback_narration(computed)

    assert "piggery" in text
    assert "27360.0" in text


def test_fallback_narration_handles_no_data():
    assert fallback_narration([]) == "No matching data was found."


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


class _FakeClient:
    """Injects a fabricated wrong-number narration at the exact seam
    boundary _phrase() calls - the same monkeypatch-a-collaborator pattern
    tests/test_ui_app.py already uses to inject a failure that can't be
    provoked by real input alone (the real model won't fabricate a number
    on demand for a test)."""
    def __init__(self, fabricated_text):
        self._fabricated_text = fabricated_text
        self.chat = self

    @property
    def completions(self):
        return self

    def create(self, **kwargs):
        return _FakeResponse(self._fabricated_text)


def _headcount_fixture():
    return base_fixture(extra_sheets={
        "P1_PIG_BATCHES": {
            "header": ["batch_code", "pen", "breed", "start_date", "start_count",
                       "start_avg_kg", "source", "target_market_date", "status"],
            "sample": ["PIG-B99", "Pen 9", "Large White", "2026-01-01", 20, 8.0,
                       "Own farrowing", "2026-05-01", "Active"],
            "rows": [["PIG-B01", "Pen 1", "Large White", "2025-12-01", 24, 8.5,
                      "Own farrowing", "2026-05-20", "Active"]],
        },
        "P2_PIG_DAILY_LOG": {
            "header": ["date", "batch_code", "pen", "feed_type", "feed_kg",
                       "water_litres", "deaths", "culls", "closing_count",
                       "pen_temp_c", "pen_condition", "notes", "recorded_by"],
            "sample": ["2026-09-07", "PIG-B99", "Pen 9", "Pig grower", 42, 110, 0,
                       0, 20, 24, "Dry", None, "S01"],
            "rows": [["2026-01-06", "PIG-B01", "Pen 1", "Pig grower", 50, 100, 0,
                      0, 24, 24, "Dry", None, "S01"]],
        },
        "C1_POULTRY_BATCHES": {
            "header": ["batch_code", "bird_type", "breed", "house",
                       "placement_date", "chicks_placed", "chick_unit_cost",
                       "hatchery", "target_off_date", "status"],
            "sample": ["BRO-99", "Broiler", "Ross 308", "House 9", "2026-08-10",
                       500, 0.55, "Irvine's Zimbabwe", "2026-09-21", "Growing"],
            "rows": [],
        },
        "C2_POULTRY_DAILY_LOG": {
            "header": ["date", "batch_code", "age_days", "deaths", "culls",
                       "closing_birds", "feed_type", "feed_kg", "water_litres",
                       "house_temp_c", "litter_condition", "lighting_hours",
                       "eggs_collected", "eggs_cracked", "eggs_dirty", "notes",
                       "recorded_by"],
            "sample": ["2026-09-01", "BRO-99", 22, 2, 0, 498, "Broiler grower",
                       58, 95, 29, "Dry", None, 0, 0, 0, None, "S02"],
            "rows": [],
        },
    })


def test_ungrounded_narration_falls_back_to_deterministic_sentence(
    tmp_path, db_conn, test_dsn, monkeypatch,
):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, _headcount_fixture())
    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=test_dsn)

    # the real headcount is 24 - a fabricated, entirely different number,
    # the same failure shape as a genuine hallucination
    fake_client = _FakeClient("We have a total of 999 pigs right now.")
    monkeypatch.setattr(chatbot.engine, "_openai_client", lambda: fake_client)

    tool_result = ToolCallResult(tool_name="q_headcount", arguments={"domain": "piggery"})
    answer = _run_tool_call(db_conn, "NIS-001", "how many pigs do we have?",
                             tool_result, None, None)

    assert "999" not in answer.text
    assert "24" in answer.text


def test_grounded_narration_passes_through_unchanged(
    tmp_path, db_conn, test_dsn, monkeypatch,
):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, _headcount_fixture())
    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=test_dsn)

    fake_client = _FakeClient("We have a total of 24 pigs right now.")
    monkeypatch.setattr(chatbot.engine, "_openai_client", lambda: fake_client)

    tool_result = ToolCallResult(tool_name="q_headcount", arguments={"domain": "piggery"})
    answer = _run_tool_call(db_conn, "NIS-001", "how many pigs do we have?",
                             tool_result, None, None)

    assert answer.text == "We have a total of 24 pigs right now."
