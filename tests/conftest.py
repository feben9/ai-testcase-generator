from __future__ import annotations

import json

import pytest

from helpers import ROOT
from tcgen.story import Story, parse_story


@pytest.fixture
def expected_findings() -> list[dict]:
    return json.loads((ROOT / "tests" / "expected_findings.json").read_text(encoding="utf-8"))


@pytest.fixture
def mini_story(tmp_path) -> Story:
    """A small story for unit tests of individual checks."""
    path = tmp_path / "mini.md"
    path.write_text(
        "# US-900: Mini story\n\n"
        "## Acceptance criteria\n\n"
        "1. A single file must be at most 10 MB; a larger file is rejected with the message \"File is too big\".\n"
        "2. A session expires 30 minutes after the last action.\n"
        "3. The user can download the receipt as PDF.\n"
        "4. The dashboard should load quickly.\n",
        encoding="utf-8",
    )
    return parse_story(path)
