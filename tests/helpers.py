"""Shared paths and builders for the tests."""

from __future__ import annotations

from pathlib import Path

from tcgen.models import GeneratedCases, TestCase
from tcgen.story import Story, parse_story

ROOT = Path(__file__).resolve().parent.parent
STORIES = ROOT / "stories"
RECORDINGS = ROOT / "recordings"
CLEAN = ROOT / "tests" / "fixtures" / "clean"


def load_clean(stem: str) -> tuple[Story, list[TestCase]]:
    generated = GeneratedCases.model_validate_json((CLEAN / f"{stem}.json").read_text(encoding="utf-8"))
    return parse_story(STORIES / f"{stem}.md"), generated.cases


def make_case(case_id: str, refs: list[int], story: Story, *, type: str = "positive", title: str | None = None,
              steps: list[str] | None = None, expected: str = "It works.", quotes: dict[int, str] | None = None,
              preconditions: list[str] | None = None) -> TestCase:
    """Build a case that quotes its ACs correctly unless `quotes` overrides them."""
    if quotes is None:
        quotes = {n: story.ac(n).text for n in refs if story.ac(n)}
    return TestCase(
        id=case_id,
        title=title or f"Case {case_id}",
        type=type,
        preconditions=preconditions or [],
        steps=steps or ["Do the thing"],
        expected=expected,
        ac_refs=refs,
        ac_quotes=[{"ac": n, "text": t} for n, t in quotes.items()],
    )
