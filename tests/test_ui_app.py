import datetime
import os
import random

import ui.app
from chatbot.catalog import CATALOG
from chatbot.matcher import match
from sync.engine import sync_workbook_to_supabase
from tests.fixtures import base_fixture
from tests.workbook_builder import build_workbook
from ui.app import (
    GENERIC_ERROR_MESSAGE,
    _chat_respond,
    _quick_lookup,
    _replay_search,
    _transcribe_audio,
    export_chat,
    export_chat_text,
    get_followup_suggestions,
    handle_message,
)


def _feed_cost_fixture():
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
            "sample": ["2026-09-07", "PIG-B99", "Pen 9", "Pig grower", 42, 110,
                       0, 0, 20, 24, "Dry", None, "S01"],
            "rows": [["2026-01-06", "PIG-B01", "Pen 1", "Pig grower", 50, 100,
                      0, 0, 24, 24, "Dry", None, "S01"]],
        },
        "C1_POULTRY_BATCHES": {
            "header": ["batch_code", "bird_type", "breed", "house",
                       "placement_date", "chicks_placed", "chick_unit_cost",
                       "hatchery", "target_off_date", "status"],
            "sample": ["BRO-99", "Broiler", "Ross 308", "House 9", "2026-08-10",
                       500, 0.55, "Irvine's Zimbabwe", "2026-09-21", "Growing"],
            "rows": [["BRO-01", "Broiler", "Ross 308", "House 1", "2025-12-17",
                      500, 0.55, "Irvine's Zimbabwe", "2026-01-28", "Growing"]],
        },
        "C2_POULTRY_DAILY_LOG": {
            "header": ["date", "batch_code", "age_days", "deaths", "culls",
                       "closing_birds", "feed_type", "feed_kg", "water_litres",
                       "house_temp_c", "litter_condition", "lighting_hours",
                       "eggs_collected", "eggs_cracked", "eggs_dirty", "notes",
                       "recorded_by"],
            "sample": ["2026-09-01", "BRO-99", 22, 2, 0, 498, "Broiler grower",
                       58, 95, 29, "Dry", None, 0, 0, 0, None, "S02"],
            "rows": [["2026-01-06", "BRO-01", 20, 0, 0, 500, "Broiler grower",
                      30, 45, 29, "Dry", None, 0, 0, 0, None, "S02"]],
        },
        "06_FEED_INVENTORY": {
            "header": ["date", "domain", "feed_type", "opening_kg",
                       "received_kg", "used_kg", "waste_kg", "closing_kg",
                       "unit_cost_per_kg", "supplier", "batch_ref"],
            "sample": ["2026-09-07", "piggery", "Pig grower", 1200, 500, 430, 5,
                       1265, 0.68, "Profeeds Marondera", None],
            "rows": [
                ["2026-01-05", "piggery", "Pig grower", 400, 250, 50, 0.5,
                 599.5, 1.00, "Profeeds Marondera", None],
                ["2026-01-05", "poultry", "Broiler grower", 300, 200, 30, 0.5,
                 469.5, 1.50, "Profeeds Marondera", None],
            ],
        },
    })


def test_handle_message_answers_a_real_question(tmp_path, db_conn, test_dsn, monkeypatch):
    monkeypatch.setenv("FARM_INTELLIGENCE_DB_DSN", test_dsn)
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, _feed_cost_fixture())
    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=test_dsn)

    text = handle_message(
        "how does feed cost split between pigs and chickens in January 2026"
    )

    assert "50.00" in text or "50.0" in text
    assert "45.00" in text or "45.0" in text


def test_handle_message_returns_generic_message_when_dsn_env_var_missing(monkeypatch):
    monkeypatch.delenv("FARM_INTELLIGENCE_DB_DSN", raising=False)

    text = handle_message("hey")

    assert text == GENERIC_ERROR_MESSAGE


def test_handle_message_returns_generic_message_when_answer_question_raises(monkeypatch):
    monkeypatch.setenv("FARM_INTELLIGENCE_DB_DSN", "host=localhost dbname=doesnotmatter")

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated database outage")

    monkeypatch.setattr(ui.app, "answer_question", _boom)

    text = handle_message("how does feed cost split between pigs and chickens")

    assert text == GENERIC_ERROR_MESSAGE


# ---------------------------------------------------------------------------
# Chat page redesign (navy/gold, 1:3:1) - the new logic added for it.
# chatbot/ itself and handle_message/_chat_fn above are unchanged; these
# tests cover only the new ui/app.py functions the redesign introduced.
# ---------------------------------------------------------------------------

def test_followup_pool_has_one_phrase_per_catalog_entry():
    pool = ui.app._followup_pool()

    assert len(pool) == len(CATALOG)


def test_followup_pool_appends_this_month_only_to_period_requiring_entries():
    pool = ui.app._followup_pool()

    period_entries = [e for e in CATALOG if "period" in e.required_params]
    for entry in period_entries:
        assert any(p.startswith(entry.phrases[0]) and p.endswith("this month") for p in pool)

    no_period_entries = [e for e in CATALOG if "period" not in e.required_params]
    for entry in no_period_entries:
        assert entry.phrases[0] in pool


def test_get_followup_suggestions_returns_requested_count_with_no_duplicates():
    suggestions = get_followup_suggestions(count=3, rng=random.Random(42))

    assert len(suggestions) == 3
    assert len(set(suggestions)) == 3


def test_get_followup_suggestions_caps_at_pool_size():
    # never crash asking for more suggestions than the catalog has entries
    suggestions = get_followup_suggestions(count=99, rng=random.Random(1))

    assert len(suggestions) == len(CATALOG)


def test_every_followup_suggestion_resolves_to_a_real_catalog_entry():
    # the user's own explicit requirement: every suggestion is answerable -
    # verified at chatbot/matcher.py's deterministic tier-1 seam (a pure
    # function, no DB needed) rather than assumed. A real anchor date
    # (any date works - only "this month"'s bounds depend on it, not
    # whether it resolves at all) makes the period-requiring entry's
    # appended "this month" resolve too, matching how it will actually be
    # clicked in production, not just the entries that need no period.
    anchor = datetime.date(2026, 9, 15)
    pool = ui.app._followup_pool()

    for phrase in pool:
        result = match(phrase, CATALOG, anchor_date=anchor)
        assert result.query_id is not None, phrase
        assert result.reason is None, phrase


def test_export_chat_text_formats_every_message():
    history = [
        {"role": "user", "content": "how many pigs do we have?"},
        {"role": "assistant", "content": "You have 12 pigs."},
    ]

    text = export_chat_text(history)

    assert "USER:" in text
    assert "how many pigs do we have?" in text
    assert "ASSISTANT:" in text
    assert "You have 12 pigs." in text


def test_export_chat_returns_none_for_empty_history():
    assert export_chat([]) is None
    assert export_chat(None) is None


def test_export_chat_writes_a_real_downloadable_file():
    history = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]

    path = export_chat(history)

    try:
        assert path is not None
        with open(path) as f:
            content = f.read()
        assert "hello" in content
        assert "hi" in content
    finally:
        os.remove(path)


def test_chat_respond_appends_to_history_and_records_search(monkeypatch):
    monkeypatch.setattr(ui.app, "handle_message", lambda q, df, dt: f"answer to: {q}")

    chat_history, search_history, search_order, cleared_msg, dropdown_update, *fups = \
        _chat_respond("how many pigs?", [], {}, [], "", "")

    assert chat_history == [
        {"role": "user", "content": "how many pigs?"},
        {"role": "assistant", "content": "answer to: how many pigs?"},
    ]
    assert search_history == {"how many pigs?": "answer to: how many pigs?"}
    assert search_order == ["how many pigs?"]
    assert cleared_msg == ""
    assert len(fups) == 3


def test_chat_respond_moves_a_repeated_question_to_the_front_without_duplicating(monkeypatch):
    monkeypatch.setattr(ui.app, "handle_message", lambda q, df, dt: "an answer")

    _, _, order1, *_ = _chat_respond("q1", [], {}, [], "", "")
    _, _, order2, *_ = _chat_respond("q2", [], {}, order1, "", "")
    _, search_history, order3, *_ = _chat_respond("q1", [], {}, order2, "", "")

    assert order3 == ["q1", "q2"]
    assert search_history == {"q1": "an answer"}


def test_chat_respond_caps_recent_searches_at_the_limit(monkeypatch):
    monkeypatch.setattr(ui.app, "handle_message", lambda q, df, dt: "a")

    order = []
    for i in range(ui.app.RECENT_SEARCHES_LIMIT + 5):
        _, _, order, *_ = _chat_respond(f"q{i}", [], {}, order, "", "")

    assert len(order) == ui.app.RECENT_SEARCHES_LIMIT
    assert order[0] == f"q{ui.app.RECENT_SEARCHES_LIMIT + 4}"


def test_chat_respond_ignores_a_blank_message(monkeypatch):
    monkeypatch.setattr(ui.app, "handle_message", lambda q, df, dt: "should not be called")

    chat_history, search_history, search_order, *_ = _chat_respond("   ", [], {}, [], "", "")

    assert chat_history == []
    assert search_history == {}
    assert search_order == []


def test_replay_search_appends_the_stored_answer_without_recomputing():
    search_history = {"how many pigs?": "You have 12 pigs."}

    chat_history, dropdown_update = _replay_search("how many pigs?", [], search_history)

    assert chat_history == [
        {"role": "user", "content": "how many pigs?"},
        {"role": "assistant", "content": "You have 12 pigs."},
    ]


def test_replay_search_is_a_noop_for_an_unknown_selection():
    chat_history, _ = _replay_search("never asked this", [{"existing": "entry"}], {})

    assert chat_history == [{"existing": "entry"}]


def test_transcribe_audio_returns_empty_string_for_no_path():
    assert _transcribe_audio(None) == ""
    assert _transcribe_audio("") == ""


def test_transcribe_audio_returns_empty_string_when_the_api_call_fails(monkeypatch, tmp_path):
    audio_path = tmp_path / "clip.wav"
    audio_path.write_bytes(b"not really audio")

    class _BoomClient:
        class audio:
            class transcriptions:
                @staticmethod
                def create(**kwargs):
                    raise RuntimeError("simulated transcription failure")

    monkeypatch.setattr(ui.app.openai, "OpenAI", lambda: _BoomClient())

    assert _transcribe_audio(str(audio_path)) == ""


def test_transcribe_audio_returns_the_transcribed_text(monkeypatch, tmp_path):
    audio_path = tmp_path / "clip.wav"
    audio_path.write_bytes(b"not really audio")

    class _FakeTranscript:
        text = "  how many pigs do we have?  "

    class _FakeClient:
        class audio:
            class transcriptions:
                @staticmethod
                def create(**kwargs):
                    return _FakeTranscript()

    monkeypatch.setattr(ui.app.openai, "OpenAI", lambda: _FakeClient())

    assert _transcribe_audio(str(audio_path)) == "how many pigs do we have?"


def test_quick_lookup_debtor_reports_could_not_connect_when_dsn_missing(monkeypatch):
    monkeypatch.delenv("FARM_INTELLIGENCE_DB_DSN", raising=False)

    result = _quick_lookup("Debtor", "", "", "")

    assert "Could not connect" in result


def test_quick_lookup_batch_prompts_for_a_value_when_blank(monkeypatch, test_dsn):
    monkeypatch.setenv("FARM_INTELLIGENCE_DB_DSN", test_dsn)

    result = _quick_lookup("Batch", "   ", "", "")

    assert result == "Enter a batch to look up."
