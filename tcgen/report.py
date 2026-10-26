"""Render a verification Report as readable text and as JSON."""

from __future__ import annotations

from collections import Counter

from . import __version__
from .verifier import CODES, ERROR, Report, StoryResult

_SEVERITY_ORDER = {ERROR: 0, "warning": 1}
_CHECK_ORDER = {"traceability": 0, "consistency": 1, "coverage": 2, "duplicates": 3, "vague-ac": 4}
_TYPE_MARK = {"positive": "+", "negative": "-", "boundary": "b"}
GATE_RULE = "fails on any traceability or consistency error"


def _sorted(findings):
    return sorted(
        findings,
        key=lambda f: (_SEVERITY_ORDER[f.severity], _CHECK_ORDER[f.check], f.ac or 0, f.cases),
    )


def _plural(n: int, word: str) -> str:
    if n == 1:
        return f"{n} {word}"
    return f"{n} {'stories' if word == 'story' else word + 's'}"


def _where(finding) -> str:
    if finding.cases:
        return "/".join(finding.cases)
    return f"AC {finding.ac}" if finding.ac is not None else ""


def _story_block(result: StoryResult, matrix: bool) -> list[str]:
    story = result.story
    covered = sum(1 for ids in result.coverage.values() if ids)
    lines = [
        f"{story.key} - {story.id} {story.title}",
        f"  {_plural(len(story.criteria), 'AC')}, {_plural(len(result.cases), 'case')}, "
        f"{covered}/{len(story.criteria)} ACs covered by a verified case, "
        f"{_plural(len(result.errors), 'error')}, {_plural(len(result.warnings), 'warning')}",
    ]
    for f in _sorted(result.findings):
        tag = "ERROR" if f.severity == ERROR else "WARN "
        lines.append(f"  {tag}  {f.code:<21} {_where(f):<12} {f.message}")
    if not result.findings:
        lines.append("  ok     no findings")
    if matrix:
        types = {c.id: c.type for c in result.cases}
        lines.append("  traceability matrix (+ positive, - negative, b boundary):")
        for ac in story.criteria:
            ids = result.coverage.get(ac.number, [])
            cells = " ".join(f"{i}({_TYPE_MARK[types[i]]})" for i in ids) or "-"
            lines.append(f"    AC {ac.number:<3} {cells}")
    return lines


def render_text(report: Report, matrix: bool = False) -> str:
    total_cases = sum(len(r.cases) for r in report.results)
    lines = [
        f"tcgen verify: {_plural(len(report.results), 'story')}, {_plural(total_cases, 'case')}",
        "",
    ]
    for result in report.results:
        lines += _story_block(result, matrix)
        lines.append("")

    by_check = Counter(f.check for f in report.findings)
    errors = ", ".join(f"{c} {by_check[c]}" for c in ("traceability", "consistency") if by_check[c])
    warnings = ", ".join(f"{c} {by_check[c]}" for c in ("coverage", "duplicates", "vague-ac") if by_check[c])
    lines.append(f"Summary: {_plural(len(report.errors), 'error')}" + (f" ({errors})" if errors else "")
                 + f", {_plural(len(report.warnings), 'warning')}" + (f" ({warnings})" if warnings else ""))
    if report.passed:
        lines.append("Gate: PASS" + (" (strict: warnings count)" if report.strict else ""))
    else:
        reason = "errors found" if report.errors else "warnings found in strict mode"
        lines.append(f"Gate: FAIL ({reason}; the gate {GATE_RULE}"
                     + (", and on warnings in strict mode" if report.strict else "") + ")")
    return "\n".join(lines)


def render_json(report: Report) -> dict:
    return {
        "tool": f"tcgen {__version__}",
        "gate": {"passed": report.passed, "strict": report.strict, "rule": GATE_RULE},
        "summary": {
            "stories": len(report.results),
            "cases": sum(len(r.cases) for r in report.results),
            "errors": len(report.errors),
            "warnings": len(report.warnings),
            "by_code": dict(sorted(Counter(f.code for f in report.findings).items())),
        },
        "codes": {code: {"check": check, "severity": sev} for code, (check, sev) in CODES.items()},
        "stories": [
            {
                "key": r.story.key,
                "id": r.story.id,
                "title": r.story.title,
                "acceptance_criteria": len(r.story.criteria),
                "cases": len(r.cases),
                "coverage": {str(ac): ids for ac, ids in r.coverage.items()},
                "findings": [f.to_dict() for f in _sorted(r.findings)],
            }
            for r in report.results
        ],
    }
