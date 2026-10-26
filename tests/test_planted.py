"""The recordings contain planted problems. The verifier must find each one,
and nothing else (no misses, no false alarms)."""

from __future__ import annotations

import json
from collections import Counter

import pytest

from helpers import RECORDINGS, STORIES
from tcgen.cli import main
from tcgen.models import GeneratedCases
from tcgen.story import parse_story
from tcgen.verifier import verify


@pytest.fixture(scope="module")
def planted_report(tmp_path_factory):
    out = tmp_path_factory.mktemp("generated")
    stories = sorted(str(p) for p in STORIES.glob("*.md"))
    assert main(["generate", *stories, "--offline", "--recordings", str(RECORDINGS), "--out", str(out)]) == 0
    pairs = []
    for file in sorted(out.glob("*.json")):
        generated = GeneratedCases.model_validate_json(file.read_text(encoding="utf-8"))
        pairs.append((parse_story(STORIES / f"{file.stem}.md"), generated.cases))
    return verify(pairs), out


def _key(item: dict) -> tuple:
    return (item["story"], item["code"], tuple(item["cases"]), item["ac"])


def test_every_story_has_a_recording():
    assert sorted(p.stem for p in STORIES.glob("*.md")) == sorted(p.stem for p in RECORDINGS.glob("*.json"))


def test_finds_exactly_the_planted_problems(planted_report, expected_findings):
    report, _ = planted_report
    found = Counter(f.key() for f in report.findings)
    expected = Counter(_key(item) for item in expected_findings)
    missed = expected - found
    false_alarms = found - expected
    assert not missed, f"planted problems the verifier missed: {sorted(missed)}"
    assert not false_alarms, f"findings that were not planted: {sorted(false_alarms)}"


@pytest.mark.parametrize("code", [
    "TRACE_UNKNOWN_AC",      # case cites an AC number that does not exist
    "TRACE_QUOTE_MISMATCH",  # fabricated AC quote
    "TRACE_NO_REFS",         # case with no ac_refs
    "COVERAGE_UNCOVERED",    # AC left uncovered
    "DUPLICATE_CASE",        # duplicate case
    "CONSISTENCY_NUMBER",    # expected result contradicts the AC's number
    "VAGUE_AC",              # vague AC flagged
    "COVERAGE_BOUNDARY",     # numeric limit without boundary cases on both sides
])
def test_each_kind_of_planted_problem_is_caught(planted_report, code):
    report, _ = planted_report
    assert any(f.code == code for f in report.findings)


def test_gate_fails_on_planted_recordings(planted_report):
    report, _ = planted_report
    assert not report.passed
    assert len(report.errors) == 5
    assert len(report.warnings) == 6


def test_verify_cli_exit_code_and_json(planted_report, tmp_path, capsys):
    _, generated = planted_report
    json_path = tmp_path / "report.json"
    code = main(["verify", "--cases", str(generated), "--stories", str(STORIES), "--json", str(json_path)])
    assert code == 1
    assert "Gate: FAIL" in capsys.readouterr().out
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["gate"]["passed"] is False
    assert data["summary"] == {
        "stories": 5,
        "cases": 75,
        "errors": 5,
        "warnings": 6,
        "by_code": {
            "CONSISTENCY_NUMBER": 2,
            "COVERAGE_BOUNDARY": 1,
            "COVERAGE_NO_POSITIVE": 1,
            "COVERAGE_UNCOVERED": 1,
            "DUPLICATE_CASE": 1,
            "TRACE_NO_REFS": 1,
            "TRACE_QUOTE_MISMATCH": 1,
            "TRACE_UNKNOWN_AC": 1,
            "VAGUE_AC": 2,
        },
    }


def test_offline_generate_is_deterministic(planted_report, tmp_path):
    _, first = planted_report
    stories = sorted(str(p) for p in STORIES.glob("*.md"))
    main(["generate", *stories, "--offline", "--recordings", str(RECORDINGS), "--out", str(tmp_path)])
    for file in first.glob("*.json"):
        assert (tmp_path / file.name).read_text() == file.read_text()


def test_recordings_say_they_are_hand_written():
    for path in RECORDINGS.glob("*.json"):
        meta = json.loads(path.read_text(encoding="utf-8"))["recording"]
        assert meta["source"] == "hand-written", path.name
