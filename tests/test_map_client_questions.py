"""Step 0.5 mapper: classification and the report, with a scripted router (no network, no database). The questions here are invented
test inputs, not the client's."""

import csv

import pytest

from evals import map_client_questions as m
from router.llm_fake import FakeRouter, spec as S


def _run(script):
    rows = [{"id": f"t{i}", "question": q} for i, q in enumerate(script, 1)]
    return m.run(rows, FakeRouter(script=script))


def test_each_outcome_is_classified():
    res = _run({
        "how many pigs": S("active_headcount", domains=["piggery"]),
        "spend on feed": S("feed_consumed_cost", ambiguous_between=["feed_consumed_cost", "feed_purchases"]),
        "tractor service": S("none", refusal="equipment"),
        "who owes us": S("expenses"),                       # the wording says receivables, the model said expenses
        "broken": {"metric": "made_up"},
    })
    got = {r["question"]: (r["status"], r["metric"]) for r in res}
    assert got == {"how many pigs": ("matched", "active_headcount"), "spend on feed": ("ambiguous", ""),
                   "tractor service": ("no_metric", ""), "who owes us": ("ambiguous", "expenses"), "broken": ("unreadable", "")}


def test_a_failed_call_is_unreadable_not_a_guess():
    res = m.run([{"id": "a", "question": "x"}], FakeRouter(error="timeout"))
    assert res[0]["status"] == "unreadable" and "timeout" in res[0]["detail"]


def test_the_report_lists_unreached_metrics_and_counts():
    text = m.report(_run({"how many pigs": S("active_headcount")}), "fake")
    assert "| matched | 1 |" in text and "Registry metrics no question matched" in text and "active_headcount: 1" in text
    assert "weather" in text.split("no question matched")[1].split("##")[0]


def test_reading_the_csv(tmp_path):
    p = tmp_path / "q.csv"
    p.write_text("id,question,who_asked\nq1,how many pigs,manager\n,,\n,how heavy are they,\n")
    rows = m.read_questions(p)
    assert [r["question"] for r in rows] == ["how many pigs", "how heavy are they"] and rows[1]["id"] == "q02"


def test_an_empty_template_is_refused(tmp_path):
    p = tmp_path / "q.csv"
    p.write_text("id,question,who_asked,how_often,notes\n")
    with pytest.raises(SystemExit):
        m.read_questions(p)


def test_the_shipped_template_has_the_header_and_no_invented_questions():
    path = m.Path(__file__).resolve().parent.parent / "evals" / "client_questions" / "TEMPLATE.csv"
    rows = list(csv.reader(path.open()))
    assert rows == [["id", "question", "who_asked", "how_often", "notes"]]
