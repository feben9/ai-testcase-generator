"""Parse a user story written in markdown into numbered acceptance criteria."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_TITLE = re.compile(r"^#\s+(?:(?P<id>[A-Z]+-\d+)\s*[:·–—-]\s*)?(?P<title>.+?)\s*$")
_AC_HEADING = re.compile(r"^#{2,6}\s+acceptance criteria\b", re.IGNORECASE)
_HEADING = re.compile(r"^#{1,6}\s")
_ITEM = re.compile(r"^\s*(\d+)[.)]\s+(.*\S)\s*$")


class StoryError(ValueError):
    pass


@dataclass(frozen=True)
class AcceptanceCriterion:
    number: int
    text: str


@dataclass(frozen=True)
class Story:
    key: str  # file stem, used to pair a story with its generated cases
    id: str
    title: str
    path: Path
    markdown: str
    criteria: tuple[AcceptanceCriterion, ...]

    def ac(self, number: int) -> AcceptanceCriterion | None:
        for criterion in self.criteria:
            if criterion.number == number:
                return criterion
        return None

    @property
    def ac_numbers(self) -> list[int]:
        return [c.number for c in self.criteria]


def parse_story(path: str | Path) -> Story:
    path = Path(path)
    markdown = path.read_text(encoding="utf-8")
    lines = markdown.splitlines()

    story_id, title = path.stem, path.stem
    for line in lines:
        match = _TITLE.match(line)
        if match:
            story_id = match.group("id") or path.stem
            title = match.group("title")
            break

    criteria: list[AcceptanceCriterion] = []
    in_section = False
    for line in lines:
        if _AC_HEADING.match(line):
            in_section = True
            continue
        if not in_section:
            continue
        if _HEADING.match(line):
            break
        item = _ITEM.match(line)
        if item:
            criteria.append(AcceptanceCriterion(int(item.group(1)), item.group(2)))
        elif line.strip() and line[:1].isspace() and criteria:
            # indented continuation of the previous item
            last = criteria.pop()
            criteria.append(AcceptanceCriterion(last.number, f"{last.text} {line.strip()}"))

    if not criteria:
        raise StoryError(f"{path}: no numbered list under an 'Acceptance criteria' heading")
    numbers = [c.number for c in criteria]
    if len(set(numbers)) != len(numbers):
        raise StoryError(f"{path}: acceptance criteria numbers repeat: {numbers}")

    return Story(
        key=path.stem,
        id=story_id,
        title=title,
        path=path,
        markdown=markdown,
        criteria=tuple(criteria),
    )
