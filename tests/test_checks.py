"""Unit tests for each verifier rule, on a small synthetic story."""

from __future__ import annotations

import pytest

from helpers import make_case
from tcgen.quantities import AC_LIMIT_WORDS, EXPECTED_LIMIT_WORDS, limit_quantities, quantities
from tcgen.story import StoryError, parse_story
from tcgen.verifier import quote_matches, verify_story


def codes(result) -> list[tuple]:
    return sorted((f.code, f.cases, f.ac) for f in result.findings)


def full_set(story):
    """Cases that cover the mini story cleanly (AC 4 stays vague by design)."""
    return [
        make_case("TC-01", [1], story, steps=["Upload a 2 MB PDF"]),
        make_case("TC-02", [1], story, type="boundary", steps=["Upload a file of exactly 10 MB"]),
        make_case("TC-03", [1], story, type="boundary", steps=["Upload a file of 10,485,761 bytes"],
                  expected='Rejected with "File is too big".'),
        make_case("TC-04", [2], story, steps=["Sign in and stay active"]),
        make_case("TC-05", [2], story, type="boundary", steps=["Wait 29 minutes, then click"]),
        make_case("TC-06", [2], story, type="boundary", steps=["Wait 31 minutes, then click"],
                  expected="The session has expired."),
        make_case("TC-07", [3], story, steps=["Open the receipt", "Click Download PDF"]),
        make_case("TC-08", [4], story, steps=["Open the dashboard"], expected="Load time recorded; target to be agreed."),
    ]


# ------------------------------------------------------------- story parsing

def test_story_parsing(mini_story):
    assert mini_story.id == "US-900"
    assert mini_story.ac_numbers == [1, 2, 3, 4]


def test_story_continuation_lines(tmp_path):
    path = tmp_path / "s.md"
    path.write_text("# S\n\n## Acceptance criteria\n\n1. First line\n   continues here.\n2. Second.\n\n## Notes\n3. not an AC\n")
    story = parse_story(path)
    assert [c.text for c in story.criteria] == ["First line continues here.", "Second."]


def test_story_without_criteria_is_an_error(tmp_path):
    path = tmp_path / "s.md"
    path.write_text("# S\n\nNo list here.\n")
    with pytest.raises(StoryError):
        parse_story(path)


# --------------------------------------------------------------- baseline

def test_full_set_only_flags_the_vague_ac(mini_story):
    assert codes(verify_story(mini_story, full_set(mini_story))) == [("VAGUE_AC", (), 4)]


# ------------------------------------------------------------ traceability

@pytest.mark.parametrize("quote", [
    "A session expires 30 minutes after the last action.",
    "AC 2: “A session expires 30 minutes after the last action”",  # prefix + curly quotes
    "a session expires 30 minutes after the last action",  # case, trailing period
    "session expires 30 minutes after the",  # excerpt of 6 words
])
def test_quotes_that_match(mini_story, quote):
    assert quote_matches(quote, mini_story.ac(2).text)


@pytest.mark.parametrize("quote", [
    "A session expires 60 minutes after the last action.",  # changed number
    "Sessions time out after half an hour.",  # paraphrase
    "30 minutes",  # too short to be a quote
    "",
])
def test_quotes_that_do_not_match(mini_story, quote):
    assert not quote_matches(quote, mini_story.ac(2).text)


def test_thousands_separators_do_not_matter():
    assert quote_matches("at most 10000.00 EUR per transfer", "Each transfer is at most 10,000.00 EUR per transfer.")


def test_quote_missing(mini_story):
    cases = full_set(mini_story)
    cases[6] = make_case("TC-07", [3], mini_story, quotes={})
    assert ("TRACE_QUOTE_MISSING", ("TC-07",), 3) in codes(verify_story(mini_story, cases))


def test_unknown_ac_in_quotes_only(mini_story):
    cases = full_set(mini_story)
    cases[6] = make_case("TC-07", [3], mini_story, quotes={3: mini_story.ac(3).text, 9: "Invented."})
    assert ("TRACE_UNKNOWN_AC", ("TC-07",), 9) in codes(verify_story(mini_story, cases))


def test_misquoted_case_does_not_count_as_coverage(mini_story):
    cases = [c for c in full_set(mini_story) if c.id != "TC-07"]
    cases.append(make_case("TC-07", [3], mini_story, quotes={3: "The user can download the receipt as CSV or PDF."}))
    found = codes(verify_story(mini_story, cases))
    assert ("TRACE_QUOTE_MISMATCH", ("TC-07",), 3) in found
    assert ("COVERAGE_UNCOVERED", (), 3) in found


# ------------------------------------------------------------- consistency

def test_wrong_limit_in_expected_is_an_error(mini_story):
    cases = full_set(mini_story)
    cases[2] = make_case("TC-03", [1], mini_story, type="boundary", steps=["Upload a file of 10,485,761 bytes"],
                         expected="Rejected: the maximum is 5 MB.")
    assert ("CONSISTENCY_NUMBER", ("TC-03",), 1) in codes(verify_story(mini_story, cases))


def test_units_are_converted_before_comparing(mini_story):
    cases = full_set(mini_story)
    cases[5] = make_case("TC-06", [2], mini_story, type="boundary", steps=["Wait 31 minutes, then click"],
                         expected="The session expires 0.5 hours after the last action.")
    assert codes(verify_story(mini_story, cases)) == [("VAGUE_AC", (), 4)]


def test_test_data_in_expected_is_not_a_claim(mini_story):
    text = "Clicking after 31 minutes shows the sign-in page."
    assert limit_quantities(text, EXPECTED_LIMIT_WORDS, window=3) == []


# ---------------------------------------------------------------- coverage

def test_one_sided_boundary_is_flagged(mini_story):
    cases = [c for c in full_set(mini_story) if c.id != "TC-06"]  # drop the 31-minute case
    found = verify_story(mini_story, cases).findings
    boundary = [f for f in found if f.code == "COVERAGE_BOUNDARY"]
    assert [(f.ac, "only test below" in f.message) for f in boundary] == [(2, True)]


def test_limit_value_alone_is_not_enough(mini_story):
    cases = [c for c in full_set(mini_story) if c.id != "TC-03"]  # keep exactly 10 MB, drop 10 MB + 1 byte
    found = verify_story(mini_story, cases).findings
    assert [f.message for f in found if f.code == "COVERAGE_BOUNDARY"] == [
        'limit "10 MB" is not tested on both sides: boundary cases only use the limit itself'
    ]


def test_no_positive_case(mini_story):
    cases = [c for c in full_set(mini_story) if c.id != "TC-07"]
    cases.append(make_case("TC-07", [3], mini_story, type="negative", steps=["Click Download PDF offline"]))
    assert ("COVERAGE_NO_POSITIVE", (), 3) in codes(verify_story(mini_story, cases))


def test_limits_found_in_ac_text():
    text = 'A single transfer must be at least 1.00 EUR and at most 10,000.00 EUR; see "Limit of 3 per day".'
    assert [q.text for q in limit_quantities(text, AC_LIMIT_WORDS, window=4)] == ["1.00", "10,000.00", "3"]


def test_quantity_parsing_skips_ids():
    assert [q.text for q in quantities("TC-07 for US-101 on 3G uses 10 MB and a 60-minute window")] == [
        "10 MB", "60-minute",
    ]


# -------------------------------------------------------------- duplicates

def test_boundary_pair_is_not_a_duplicate(mini_story):
    found = codes(verify_story(mini_story, full_set(mini_story)))
    assert not any(code == "DUPLICATE_CASE" for code, *_ in found)


def test_reworded_case_is_a_duplicate(mini_story):
    cases = full_set(mini_story)
    cases.append(make_case("TC-09", [3], mini_story, title="Case TC-07 again",
                           steps=["Open the receipt", "Click the Download PDF button"]))
    assert ("DUPLICATE_CASE", ("TC-07", "TC-09"), None) in codes(verify_story(mini_story, cases))


# ---------------------------------------------------------------- vague AC

@pytest.mark.parametrize("text, vague", [
    ("The dashboard should load quickly.", True),
    ("Error messages should be clear and user-friendly.", True),
    ("The dashboard should load quickly, within 2 seconds on 4G.", False),
    ("The user can download the receipt as PDF.", False),
])
def test_vague_detection(tmp_path, text, vague):
    path = tmp_path / "v.md"
    path.write_text(f"# V\n\n## Acceptance criteria\n\n1. {text}\n")
    story = parse_story(path)
    result = verify_story(story, [make_case("TC-01", [1], story)])
    assert any(f.code == "VAGUE_AC" for f in result.findings) is vague
