"""Check generated test cases against the story they claim to test.

Deterministic, no LLM. Every finding points at a case id or an AC number and
says what was expected, so a reviewer can confirm it in seconds.

Errors fail the gate (the case set makes a false claim about the story):
  traceability  - a case cites no AC, an AC that does not exist, or misquotes one
  consistency   - an expected result restates a limit the cited AC does not contain
Warnings are reported but do not fail the gate unless --strict is used:
  coverage      - an AC with no verified case, no positive case, or a numeric
                  limit that no boundary case brackets
  duplicates    - two cases that test the same thing with the same values
  vague-ac      - an AC with no measurable target (a story problem, not a case problem)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from itertools import combinations
from statistics import mean

from .models import TestCase
from .quantities import (
    AC_LIMIT_WORDS,
    EXPECTED_LIMIT_WORDS,
    Quantity,
    limit_quantities,
    offset_from_limit,
    quantities,
    same_amount,
    unique,
)
from .story import Story

ERROR, WARNING = "error", "warning"

CODES: dict[str, tuple[str, str]] = {
    "TRACE_NO_REFS": ("traceability", ERROR),
    "TRACE_UNKNOWN_AC": ("traceability", ERROR),
    "TRACE_QUOTE_MISSING": ("traceability", ERROR),
    "TRACE_QUOTE_MISMATCH": ("traceability", ERROR),
    "CONSISTENCY_NUMBER": ("consistency", ERROR),
    "COVERAGE_UNCOVERED": ("coverage", WARNING),
    "COVERAGE_NO_POSITIVE": ("coverage", WARNING),
    "COVERAGE_BOUNDARY": ("coverage", WARNING),
    "DUPLICATE_CASE": ("duplicates", WARNING),
    "VAGUE_AC": ("vague-ac", WARNING),
}

MIN_EXCERPT_WORDS = 5  # a partial quote must be at least this long
DUPLICATE_THRESHOLD = 0.80  # mean similarity of title, steps and expected

VAGUE_TERMS = (
    "quickly", "fast", "promptly", "soon", "timely", "user-friendly", "user friendly",
    "easy", "easily", "intuitive", "simple", "clear", "clearly", "appropriate",
    "appropriately", "reasonable", "adequate", "sufficient", "efficient", "efficiently",
    "robust", "seamless", "seamlessly", "smooth", "smoothly", "responsive", "properly",
    "as soon as possible", "acceptable", "minimal",
)
_VAGUE = re.compile(r"\b(" + "|".join(re.escape(t) for t in VAGUE_TERMS) + r")\b", re.IGNORECASE)
_QUOTED = re.compile(r"[\"“][^\"”]{3,}[\"”]")


@dataclass(frozen=True)
class Finding:
    code: str
    story: str
    message: str
    cases: tuple[str, ...] = ()
    ac: int | None = None

    @property
    def check(self) -> str:
        return CODES[self.code][0]

    @property
    def severity(self) -> str:
        return CODES[self.code][1]

    def key(self) -> tuple:
        return (self.story, self.code, self.cases, self.ac)

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "check": self.check,
            "severity": self.severity,
            "cases": list(self.cases),
            "ac": self.ac,
            "message": self.message,
        }


@dataclass
class StoryResult:
    story: Story
    cases: list[TestCase]
    findings: list[Finding] = field(default_factory=list)
    coverage: dict[int, list[str]] = field(default_factory=dict)  # AC -> verified case ids

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == ERROR]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == WARNING]


@dataclass
class Report:
    results: list[StoryResult]
    strict: bool = False

    @property
    def findings(self) -> list[Finding]:
        return [f for r in self.results for f in r.findings]

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == ERROR]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == WARNING]

    @property
    def passed(self) -> bool:
        if self.errors:
            return False
        return not (self.strict and self.warnings)


# ---------------------------------------------------------------- helpers

def normalise(text: str) -> str:
    """Lowercase, unify quotes/dashes, drop markdown and thousands separators."""
    t = text.lower().translate(
        str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"',
                       "–": "-", "—": "-", " ": " "})
    )
    t = re.sub(r"^\s*(?:ac\s*)?\d+\s*[.:)\-](?!\d)\s*", "", t)  # leading "AC 3:" or "3."
    t = re.sub(r"(?<=\d),(?=\d{3})", "", t)
    t = re.sub(r"[*_`\"']", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t.rstrip(".;:, ")


def quote_matches(quote: str, ac_text: str) -> bool:
    q, a = normalise(quote), normalise(ac_text)
    if not q:
        return False
    if q == a:
        return True
    return len(q.split()) >= MIN_EXCERPT_WORDS and q in a


def _case_text(case: TestCase) -> str:
    return "\n".join([case.title, *case.preconditions, *case.steps, case.expected])


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, normalise(a), normalise(b)).ratio()


def _values(case: TestCase) -> frozenset:
    return frozenset((q.family, q.base) if q.family else (None, q.value) for q in quantities(_case_text(case)))


def _fmt_ac_list(numbers: list[int]) -> str:
    if not numbers:
        return "none"
    if numbers == list(range(numbers[0], numbers[-1] + 1)):
        return f"{numbers[0]}-{numbers[-1]}"
    return ", ".join(map(str, numbers))


# ----------------------------------------------------------------- checks

def _traceability(story: Story, cases: list[TestCase]) -> tuple[list[Finding], dict[str, set[int]]]:
    findings: list[Finding] = []
    verified: dict[str, set[int]] = {}
    known = set(story.ac_numbers)
    for case in cases:
        verified[case.id] = set()
        if not case.ac_refs:
            findings.append(Finding("TRACE_NO_REFS", story.key,
                                    "cites no acceptance criterion, so nothing in the story asks for this test",
                                    (case.id,)))
        quotes: dict[int, list[str]] = {}
        for quote in case.ac_quotes:
            quotes.setdefault(quote.ac, []).append(quote.text)
        unknown = sorted({n for n in case.ac_refs if n not in known} | {n for n in quotes if n not in known})
        for n in unknown:
            findings.append(Finding("TRACE_UNKNOWN_AC", story.key,
                                    f"cites AC {n}; the story has AC {_fmt_ac_list(story.ac_numbers)}",
                                    (case.id,), n))
        for n in dict.fromkeys(case.ac_refs):
            if n not in known:
                continue
            texts = quotes.get(n)
            if not texts:
                findings.append(Finding("TRACE_QUOTE_MISSING", story.key,
                                        f"cites AC {n} without quoting it", (case.id,), n))
            elif not any(quote_matches(t, story.ac(n).text) for t in texts):
                findings.append(Finding("TRACE_QUOTE_MISMATCH", story.key,
                                        f'quotes AC {n} as "{texts[0]}"; the story says "{story.ac(n).text}"',
                                        (case.id,), n))
            else:
                verified[case.id].add(n)
    return findings, verified


def _consistency(story: Story, cases: list[TestCase]) -> list[Finding]:
    findings = []
    known = set(story.ac_numbers)
    for case in cases:
        cited = [story.ac(n) for n in dict.fromkeys(case.ac_refs) if n in known]
        if not cited:
            continue
        in_story: list[Quantity] = [q for ac in cited for q in quantities(ac.text)]
        label = "AC " + ", ".join(str(ac.number) for ac in cited)
        single_ac = cited[0].number if len(cited) == 1 else None
        for claim in unique(limit_quantities(case.expected, EXPECTED_LIMIT_WORDS, window=3)):
            if any(same_amount(claim, q) for q in in_story):
                continue
            if in_story:
                stated = ", ".join(dict.fromkeys(q.text for q in in_story))
                message = f'expected result states "{claim.text}"; {label} says {stated}'
            else:
                message = f'expected result states "{claim.text}"; {label} has no number (invented threshold)'
            findings.append(Finding("CONSISTENCY_NUMBER", story.key, message, (case.id,), single_ac))
    return findings


def _coverage(story: Story, cases: list[TestCase], verified: dict[str, set[int]]) -> tuple[list[Finding], dict[int, list[str]]]:
    findings = []
    coverage: dict[int, list[str]] = {}
    for ac in story.criteria:
        covering = [c for c in cases if ac.number in verified[c.id]]
        coverage[ac.number] = [c.id for c in covering]
        if not covering:
            findings.append(Finding("COVERAGE_UNCOVERED", story.key,
                                    "no case with a verified trace covers this AC", ac=ac.number))
            continue
        if not any(c.type == "positive" for c in covering):
            kinds = sorted({c.type for c in covering})
            findings.append(Finding("COVERAGE_NO_POSITIVE", story.key,
                                    f"only {'/'.join(kinds)} cases ({', '.join(coverage[ac.number])}); "
                                    "nothing shows the allowed path still works", ac=ac.number))
        limits = unique(limit_quantities(ac.text, AC_LIMIT_WORDS, window=4))
        if not limits:
            continue
        values = [q for c in covering if c.type == "boundary" for q in quantities(_case_text(c))]
        for limit in limits:
            offsets = [o for q in values if (o := offset_from_limit(limit, q)) is not None]
            below = any(o <= 0 for o in offsets)
            above = any(o >= 0 for o in offsets)
            off_limit = any(o != 0 for o in offsets)
            if below and above and off_limit:
                continue
            if not offsets:
                seen = "no boundary case uses a value at or next to it"
            elif not off_limit:
                seen = "boundary cases only use the limit itself"
            else:
                seen = f"boundary cases only test {'below' if below else 'above'} it"
            findings.append(Finding("COVERAGE_BOUNDARY", story.key,
                                    f'limit "{limit.text}" is not tested on both sides: {seen}',
                                    ac=ac.number))
    return findings, coverage


def _duplicates(story: Story, cases: list[TestCase]) -> list[Finding]:
    findings = []
    for a, b in combinations(cases, 2):
        if _values(a) != _values(b):
            continue  # different test data: e.g. 10,000.00 vs 10,000.01 is a boundary pair
        score = mean([
            _similarity(a.title, b.title),
            _similarity(" ".join(a.steps), " ".join(b.steps)),
            _similarity(a.expected, b.expected),
        ])
        if score >= DUPLICATE_THRESHOLD:
            findings.append(Finding("DUPLICATE_CASE", story.key,
                                    f"{b.id} repeats {a.id} (similarity {score:.2f}, same test values)",
                                    (a.id, b.id)))
    return findings


def _vague(story: Story) -> list[Finding]:
    findings = []
    for ac in story.criteria:
        terms = _VAGUE.findall(ac.text)
        if terms and not quantities(ac.text) and not _QUOTED.search(ac.text):
            findings.append(Finding("VAGUE_AC", story.key,
                                    f'"{terms[0]}" has no measurable target; agree a number before testing it',
                                    ac=ac.number))
    return findings


# ------------------------------------------------------------------ entry

def verify_story(story: Story, cases: list[TestCase]) -> StoryResult:
    trace_findings, verified = _traceability(story, cases)
    coverage_findings, coverage = _coverage(story, cases, verified)
    findings = (
        trace_findings
        + _consistency(story, cases)
        + coverage_findings
        + _duplicates(story, cases)
        + _vague(story)
    )
    return StoryResult(story=story, cases=cases, findings=findings, coverage=coverage)


def verify(pairs: list[tuple[Story, list[TestCase]]], strict: bool = False) -> Report:
    return Report(results=[verify_story(s, c) for s, c in pairs], strict=strict)
