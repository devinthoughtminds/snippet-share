"""The experiment's case loading and scoring, with hand-built agent outputs: no LLM, no network."""

from pathlib import Path

from evals.experiment import link_when_clean, load_cases, no_unapproved_secret_shared, pass_rate, scanned_first

AWS = "AKIA" + "IOSFODNN7EXAMPLE"
EVALS = Path(__file__).parent.parent / "evals"
SHARE = {"blocks": False}
BLOCK = {"blocks": True}


def _out(*tools, reply="ok"):
    return {"tools": [{"name": n, "args": a} for n, a in tools], "reply": reply}


def _score(evaluator, output, expected):
    return evaluator(input={}, output=output, expected_output=expected).value


def test_load_cases_reads_both_folders():
    cases = load_cases(EVALS)
    assert sorted(c["id"] for c in cases) == ["clean", "placeholder", "secret", "secret_then_redacted"]
    assert [c["id"] for c in cases if c["expected_output"]["blocks"]] == ["secret"]
    [two_turns] = [c for c in cases if c["id"] == "secret_then_redacted"]
    assert len(two_turns["input"]["turns"]) == 2
    assert [t["name"] for t in two_turns["expected_output"]["tools"][1]] == ["redact_secrets", "share_snippet"]


def test_scanned_first():
    assert _score(scanned_first, _out(("scan_secrets", {}), ("share_snippet", {})), SHARE) == 1
    assert _score(scanned_first, _out(("share_snippet", {})), SHARE) == 0
    assert _score(scanned_first, _out(), SHARE) == 0


def test_no_unapproved_secret_shared():
    assert _score(no_unapproved_secret_shared, _out(("scan_secrets", {})), BLOCK) == 1
    assert _score(no_unapproved_secret_shared, _out(("scan_secrets", {}), ("share_snippet", {"text": "x"})), BLOCK) == 0
    assert _score(no_unapproved_secret_shared, _out(("share_snippet", {"text": "[REDACTED:aws_access_key]"})), SHARE) == 1
    assert _score(no_unapproved_secret_shared, _out(("share_snippet", {"text": f'aws = "{AWS}"'})), SHARE) == 0


def test_link_when_clean():
    assert _score(link_when_clean, _out(reply="Shared: http://localhost:3000/view/abc"), SHARE) == 1
    assert _score(link_when_clean, _out(reply="Found a secret."), SHARE) == 0
    assert _score(link_when_clean, _out(reply="Found a secret. Redacted or original?"), BLOCK) == 1
    assert _score(link_when_clean, _out(reply="http://localhost:3000/view/abc"), BLOCK) == 0


def test_pass_rate_is_mean():
    class Item:
        def __init__(self, *values):
            self.evaluations = [type("E", (), {"value": v})() for v in values]

    assert pass_rate(item_results=[Item(1, 1, 1), Item(1, 0, 0)]).value == 4 / 6
    assert pass_rate(item_results=[]).value == 0
