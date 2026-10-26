"""Command line: `python -m tcgen generate ...` and `python -m tcgen verify ...`.

Exit codes: 0 = done / gate passed, 1 = gate failed, 2 = bad input or generation failed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from pydantic import ValidationError

from . import DEFAULT_MODEL, __version__
from .generator import GenerationError, generate_live, generate_offline
from .models import GeneratedCases
from .report import render_json, render_text
from .story import StoryError, parse_story
from .verifier import verify


def _fail(message: str) -> int:
    print(f"tcgen: {message}", file=sys.stderr)
    return 2


def cmd_generate(args: argparse.Namespace) -> int:
    if not args.offline and not os.environ.get("ANTHROPIC_API_KEY"):
        return _fail("live mode needs ANTHROPIC_API_KEY; use --offline to replay recordings/ instead")

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    client = None
    if not args.offline:
        import anthropic

        client = anthropic.Anthropic()

    for story_path in args.stories:
        try:
            story = parse_story(story_path)
            if args.offline:
                case_set, meta = generate_offline(story, args.recordings)
                mode, model, source = "offline", meta.get("model"), f"{args.recordings}/{story.key}.json"
            else:
                case_set = generate_live(story, model=args.model, client=client)
                mode, model, source = "live", args.model, args.model
        except (OSError, StoryError, GenerationError, ValidationError) as exc:
            return _fail(str(exc))
        except Exception as exc:  # anthropic API errors: report and stop
            return _fail(f"{story_path}: {type(exc).__name__}: {exc}")

        generated = GeneratedCases(story=Path(story_path).as_posix(), mode=mode, model=model, cases=case_set.cases)
        target = out_dir / f"{story.key}.json"
        target.write_text(generated.model_dump_json(indent=2) + "\n", encoding="utf-8")
        print(f"{story.key}: {len(case_set.cases)} cases ({mode}: {source}) -> {target.as_posix()}")
    return 0


def _load_pairs(args: argparse.Namespace):
    cases_dir, stories_dir = Path(args.cases), Path(args.stories)
    files = sorted(cases_dir.glob("*.json"))
    if args.only:
        files = [f for f in files if f.stem in set(args.only)]
    if not files:
        raise FileNotFoundError(f"no generated cases in {cases_dir}/ (run `python -m tcgen generate ...` first)")
    pairs = []
    for file in files:
        story_path = stories_dir / f"{file.stem}.md"
        if not story_path.exists():
            raise FileNotFoundError(f"{file} has no matching story {story_path}")
        generated = GeneratedCases.model_validate_json(file.read_text(encoding="utf-8"))
        pairs.append((parse_story(story_path), generated.cases))
    return pairs


def cmd_verify(args: argparse.Namespace) -> int:
    try:
        pairs = _load_pairs(args)
    except (OSError, StoryError, ValidationError) as exc:
        return _fail(str(exc))

    report = verify(pairs, strict=args.strict)
    print(render_text(report, matrix=args.matrix))
    if args.json:
        path = Path(args.json)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(render_json(report), indent=2) + "\n", encoding="utf-8")
        print(f"JSON report: {path.as_posix()}")
    return 0 if report.passed else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tcgen",
        description="Generate test cases from user stories with Claude, then verify them against the acceptance criteria.",
    )
    parser.add_argument("--version", action="version", version=f"tcgen {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("generate", help="generate test cases for one or more stories")
    gen.add_argument("stories", nargs="+", help="story markdown files, e.g. stories/money-transfer.md")
    gen.add_argument("--offline", action="store_true", help="replay recordings/<story>.json instead of calling the API")
    gen.add_argument("--recordings", default="recordings", help="recordings folder (default: recordings)")
    gen.add_argument("--out", default="generated", help="output folder (default: generated)")
    gen.add_argument("--model", default=DEFAULT_MODEL, help=f"model id for live mode (default: {DEFAULT_MODEL})")
    gen.set_defaults(func=cmd_generate)

    ver = sub.add_parser("verify", help="verify generated cases against their stories")
    ver.add_argument("only", nargs="*", help="story keys to verify (default: every file in --cases)")
    ver.add_argument("--cases", default="generated", help="folder of generated case files (default: generated)")
    ver.add_argument("--stories", default="stories", help="folder of story files (default: stories)")
    ver.add_argument("--json", default="reports/verification.json", help="where to write the JSON report ('' to skip)")
    ver.add_argument("--strict", action="store_true", help="warnings also fail the gate")
    ver.add_argument("--matrix", action="store_true", help="print the AC-to-case traceability matrix")
    ver.set_defaults(func=cmd_verify)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)
