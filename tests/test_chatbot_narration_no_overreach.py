from chatbot.engine import answer_question
from sync.engine import sync_workbook_to_supabase
from tests.fixtures import base_fixture
from tests.workbook_builder import build_workbook


def _weather_fixture():
    return base_fixture(extra_sheets={
        "05_WEATHER_LOG": {
            "header": ["date", "rainfall_mm", "temp_min_c", "temp_max_c",
                       "humidity_pct", "event"],
            "sample": ["2026-09-01", 0, 14, 27, 48, "Normal"],
            "rows": [["2026-01-08", 0, 22, 39, 30, "Normal"]],
        },
    })


def _seed(tmp_path, dsn):
    wb_path = tmp_path / "fixture.xlsx"
    build_workbook(wb_path, _weather_fixture())
    sync_workbook_to_supabase(str(wb_path), farm_code="NIS-001", dsn=dsn)


def test_weather_narration_does_not_claim_unsupported_causation(tmp_path, db_conn, test_dsn):
    _seed(tmp_path, test_dsn)

    # The real rambling multi-topic question from a security/edge-case QA
    # pass, verbatim - the old narration added "which suggests conditions
    # are stable and likely not directly affecting feed consumption or
    # health issues in the piggery or poultry house", a causal claim not
    # present in the weather tool's data (it only returns weather
    # conditions, nothing about feed consumption or health correlation).
    # This is a best-effort, not a guaranteed check - it's still an LLM
    # narration, just under a tightened prompt - but it directly targets
    # the exact real failure found.
    question = (
        "So I've been going through some of our records and I'm a bit confused "
        "about a few things - can you help me understand what's going on across "
        "the farm right now? I guess what I really want to know is how the pigs "
        "have been doing lately, especially compared to the poultry side, because "
        "I noticed the weather has been pretty rough the last few weeks with all "
        "that rain we had, and I'm wondering if that's affected feed consumption "
        "or maybe even caused some health issues in either the piggery or the "
        "poultry house, and on top of that I've also been trying to figure out "
        "whether we're actually making any money this quarter once you account "
        "for all the vet bills and feed costs and whatever we've spent on labour, "
        "because it feels like expenses have been creeping up but I haven't seen "
        "the revenue numbers to match, so if you could just give me a general "
        "sense of how everything is trending - pigs, chickens, money, weather, "
        "all of it together - that would be really helpful, thanks."
    )

    answer = answer_question(question, farm_code="NIS-001", dsn=test_dsn)

    assert answer.tool_name == "q_weather"
    # the real weather numbers must still be reported correctly
    assert "39" in answer.text
    # no causal/correlative claim linking weather to feed/health, since
    # the weather tool's data contains no such link
    lowered = answer.text.lower()
    for phrase in ["affecting feed", "not directly affecting", "likely not",
                   "suggests conditions", "causing health", "caused"]:
        assert phrase not in lowered, (phrase, answer.text)
