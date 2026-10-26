"""A clean, hand-written case set must pass with zero findings (no false alarms)."""

from __future__ import annotations

import pytest

from helpers import CLEAN, STORIES, load_clean
from tcgen.cli import main
from tcgen.verifier import verify, verify_story

CLEAN_STORIES = sorted(p.stem for p in CLEAN.glob("*.json"))


def test_there_are_clean_sets():
    assert CLEAN_STORIES == ["money-transfer", "role-based-access"]


@pytest.mark.parametrize("stem", CLEAN_STORIES)
def test_clean_set_has_no_findings(stem):
    story, cases = load_clean(stem)
    result = verify_story(story, cases)
    assert result.findings == []
    assert all(result.coverage[n] for n in story.ac_numbers)


def test_clean_sets_pass_the_strict_gate():
    report = verify([load_clean(stem) for stem in CLEAN_STORIES], strict=True)
    assert report.passed


def test_verify_cli_passes_on_clean_sets(capsys):
    code = main(["verify", "--cases", str(CLEAN), "--stories", str(STORIES), "--json", "", "--strict"])
    assert code == 0
    assert "Gate: PASS" in capsys.readouterr().out
