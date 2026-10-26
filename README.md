# AI test case generator with a verification gate

Claude writes test cases from a user story. A deterministic verifier then checks
every case against the story's acceptance criteria (AC) before anyone trusts it.
If a case cites a requirement that isn't there, misquotes one, or states a limit
the story doesn't contain, the gate fails.

## The problem

AI-generated test cases look complete. They have ids, steps, expected results and
a neat type column. In review, the same problems keep coming back:

- **Invented requirements.** A case tests a PDF export or a virus scan that no AC mentions.
- **Misquoted ACs.** A case "quotes" an AC that says something different from the story,
  e.g. "valid for 24 hours, up to three uses" when the story says 30 minutes, once.
- **Wrong numbers.** The expected result says the limit is 5,000.00 when the AC says 10,000.00.
- **Invented thresholds.** The AC says "should arrive promptly"; the case says "within 2 minutes".
  That number came from the model, not the product owner.
- **Missing boundaries.** A rule with a numeric limit gets a happy-path case and nothing at the edge.
- **Gaps and repeats.** One AC has no case at all, and two cases test the same thing in different words.

None of these show up when you skim the output. They show up when you trace each
case back to the story line it claims to test, which is slow to do by hand and
easy to skip.

## The approach

```
story.md ──> generate (Claude, structured output) ──> cases.json ──> verify (no LLM) ──> report + gate
                     │                                                    │
                     └── or --offline: replay recordings/<story>.json     └── exit 1 on any error
```

1. **Generate.** `tcgen generate` sends the story to Claude and asks for JSON in a fixed
   schema: `id, title, type (positive/negative/boundary), preconditions, steps, expected,
   ac_refs, ac_quotes`. Every case must cite AC numbers and quote each cited AC word for word.
2. **Verify against the source.** `tcgen verify` re-reads the story and checks every claim
   the cases make about it. It uses plain rules, no LLM, so the same input always gives the
   same report and every finding can be checked by hand in seconds.
3. **Gate.** Any traceability or consistency error fails the run (exit code 1). Coverage gaps,
   duplicates and vague ACs are warnings; `--strict` makes them fail too.

The model is asked to quote the AC precisely because a quote can be checked. A case
that cites "AC 3" proves nothing; a case that quotes AC 3 can be compared with the story.

## What the verifier checks

| Check | Code | Severity | Rule |
|---|---|---|---|
| Traceability | `TRACE_NO_REFS` | error | The case cites at least one AC. |
| | `TRACE_UNKNOWN_AC` | error | Every cited AC number exists in the story. |
| | `TRACE_QUOTE_MISSING` | error | Every cited AC is quoted. |
| | `TRACE_QUOTE_MISMATCH` | error | The quote matches the story after normalising case, quote marks, dashes, markdown and thousands separators. A partial quote is fine if it is an exact excerpt of 5+ words. |
| Consistency | `CONSISTENCY_NUMBER` | error | A limit restated in the expected result ("limit of", "at most", "within", "expires", ...) must appear in the cited AC. Units are converted (0.5 hours = 30 minutes, 10,485,760 bytes = 10 MB). A number for an AC that has none is reported as an invented threshold. |
| Coverage | `COVERAGE_UNCOVERED` | warning | Every AC has at least one case whose trace verified. A misquoted case does not count. |
| | `COVERAGE_NO_POSITIVE` | warning | Every AC has a positive case, so a rule is never tested only by its rejections. |
| | `COVERAGE_BOUNDARY` | warning | Every numeric limit in an AC (amounts, sizes, counts, durations) is bracketed by boundary cases: one value at or just below it and one at or just above it. "Just" means one step of how the limit is written (1.00 → 0.01, 30 minutes → 1 minute) or 1%, whichever is larger. |
| Duplicates | `DUPLICATE_CASE` | warning | Two cases with the same test values and a mean title/steps/expected similarity of 0.80 or more (`difflib`). Cases with different values, such as a 10,000.00 / 10,000.01 boundary pair, are never duplicates. |
| Vague AC | `VAGUE_AC` | warning | An AC with a vague word ("quickly", "promptly", "user-friendly", ...) and no number or quoted message. This is a story problem: fix it before trusting any test for it. |

The verifier also prints a traceability matrix (`--matrix`) and writes everything to a
JSON report for CI.

## Example run

Real output from `python -m tcgen generate stories/*.md --offline` followed by
`python -m tcgen verify` on this repo:

```
tcgen verify: 5 stories, 75 cases

appointment-booking - US-105 Book a clinic appointment online
  6 ACs, 12 cases, 6/6 ACs covered by a verified case, 0 errors, 2 warnings
  WARN   COVERAGE_NO_POSITIVE  AC 3         only negative cases (TC-07); nothing shows the allowed path still works
  WARN   VAGUE_AC              AC 6         "quickly" has no measurable target; agree a number before testing it

file-upload - US-104 Attach supporting documents to an insurance claim
  6 ACs, 16 cases, 6/6 ACs covered by a verified case, 1 error, 1 warning
  ERROR  TRACE_UNKNOWN_AC      TC-15        cites AC 8; the story has AC 1-6
  WARN   DUPLICATE_CASE        TC-03/TC-16  TC-16 repeats TC-03 (similarity 0.87, same test values)

money-transfer - US-101 Send money to another customer
  7 ACs, 18 cases, 7/7 ACs covered by a verified case, 1 error, 1 warning
  ERROR  CONSISTENCY_NUMBER    TC-06        expected result states "5,000.00"; AC 1 says 1.00, 10,000.00
  WARN   COVERAGE_BOUNDARY     AC 3         limit "2,000.00" is not tested on both sides: no boundary case uses a value at or next to it

password-reset - US-102 Reset a forgotten password
  7 ACs, 18 cases, 7/7 ACs covered by a verified case, 2 errors, 1 warning
  ERROR  TRACE_QUOTE_MISMATCH  TC-08        quotes AC 3 as "A reset link is valid for 24 hours and can be used up to three times."; the story says "A reset link expires 30 minutes after it is sent and can be used only once."
  ERROR  CONSISTENCY_NUMBER    TC-18        expected result states "2 minutes"; AC 7 has no number (invented threshold)
  WARN   VAGUE_AC              AC 7         "promptly" has no measurable target; agree a number before testing it

role-based-access - US-103 Role-based access to finance reports
  7 ACs, 11 cases, 6/7 ACs covered by a verified case, 1 error, 1 warning
  ERROR  TRACE_NO_REFS         TC-11        cites no acceptance criterion, so nothing in the story asks for this test
  WARN   COVERAGE_UNCOVERED    AC 5         no case with a verified trace covers this AC

Summary: 5 errors (traceability 3, consistency 2), 6 warnings (coverage 3, duplicates 1, vague-ac 2)
Gate: FAIL (errors found; the gate fails on any traceability or consistency error)
JSON report: reports/verification.json
```

With `--matrix`, each story also shows which verified cases cover each AC:

```
money-transfer - US-101 Send money to another customer
  ...
  traceability matrix (+ positive, - negative, b boundary):
    AC 1   TC-01(+) TC-02(b) TC-03(b) TC-04(b) TC-05(b) TC-06(-)
    AC 2   TC-07(+) TC-08(b) TC-09(b)
    AC 3   TC-10(+) TC-11(-)
    AC 4   TC-12(+) TC-13(b) TC-14(b)
    AC 5   TC-15(-) TC-16(+)
    AC 6   TC-17(-) TC-18(+)
    AC 7   TC-01(+)
```

AC 3 has a positive and a negative case, but nothing at 2,000.00 / 2,000.01, which is
exactly where an off-by-one in the OTP rule would hide.

## Planted problems

The recordings in `recordings/` are **hand-written**, not real model responses. They
are written to look like typical model output, and each one contains known problems so
the verifier can be tested against a fixed answer key (`tests/expected_findings.json`):

| Story | Planted problem | Caught as |
|---|---|---|
| file-upload | TC-15 cites AC 8 (virus scan); the story has 6 ACs | `TRACE_UNKNOWN_AC` |
| password-reset | TC-08 quotes an AC 3 that says "24 hours, up to three times" | `TRACE_QUOTE_MISMATCH` |
| role-based-access | TC-11 tests a PDF export and cites no AC | `TRACE_NO_REFS` |
| role-based-access | AC 5 (audit log) has no case | `COVERAGE_UNCOVERED` |
| file-upload | TC-16 repeats TC-03 in different words | `DUPLICATE_CASE` |
| money-transfer | TC-06 expects a 5,000.00 limit; AC 1 says 10,000.00 | `CONSISTENCY_NUMBER` |
| password-reset | TC-18 invents "within 2 minutes" for "should arrive promptly" | `CONSISTENCY_NUMBER` |
| password-reset, appointment-booking | "should arrive promptly", "should load quickly" | `VAGUE_AC` |
| money-transfer | OTP limit 2,000.00 has no boundary cases | `COVERAGE_BOUNDARY` |
| appointment-booking | the overlap rule is only tested by a rejected booking | `COVERAGE_NO_POSITIVE` |

The tests assert that the verifier reports **exactly** these 11 findings: nothing missed
and nothing extra. `tests/fixtures/clean/` holds corrected case sets for two stories that
must pass with zero findings, even in strict mode. As a check on the tests themselves,
disabling any one rule in the verifier makes the suite fail.

The appointment-booking recording also shows the good case for a vague AC: TC-12 says
the story has no load-time target and asks for one, instead of making one up. The verifier
accepts it and still flags the AC itself.

## Run it

Python 3.11+.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

pytest -q                                          # 57 tests

# Offline: replay recordings/, no API key needed
python -m tcgen generate stories/*.md --offline    # writes generated/<story>.json
python -m tcgen verify                             # report + reports/verification.json, exit 1 here
python -m tcgen verify --matrix money-transfer     # one story, with the traceability matrix
python -m tcgen verify --cases tests/fixtures/clean --strict   # the clean sets pass, exit 0
```

**Live mode** calls the Claude API and needs a key:

```bash
export ANTHROPIC_API_KEY=...
python -m tcgen generate stories/password-reset.md          # default model: claude-sonnet-5-5
python -m tcgen generate stories/*.md --model <model-id>    # any other Claude model
python -m tcgen verify
```

Live output is not guaranteed to pass the gate. That is the point: the gate tells you
which cases to fix or drop before they reach a test run.

Exit codes: `0` passed, `1` gate failed, `2` bad input or the generation call failed.

### CI

`.github/workflows/ci.yml` runs on every push and pull request, with no secrets:

1. `pytest`
2. offline generate from the recordings
3. verify, and **assert the gate fails with exit 1**, because the planted problems must be caught
4. verify the clean sets in strict mode, which must pass
5. upload the JSON reports as an artifact

Live mode is optional. To try it, add a repository secret named `ANTHROPIC_API_KEY`, then
run the workflow by hand (Actions > ci > Run workflow) with **live** ticked. That job
generates cases for every story with Claude, verifies them, and uploads both. Nothing else
in the repo needs the secret.

## Design choices

- **The verifier has no LLM in it.** Asking a model to grade a model's output moves the
  trust problem instead of solving it. Plain rules are repeatable, cheap, and every finding
  points at a case id or an AC number that a reviewer can check.
- **Quotes, not just references.** Requiring the AC text forces the model to commit to what
  it thinks the requirement says, and makes misreadings visible.
- **Only verified traces count as coverage.** A case that misquotes AC 3 does not cover AC 3,
  even if it cites it.
- **Errors vs warnings.** Errors mean the case set says something false about the story, so
  they block. Coverage gaps and duplicates are review items, and a vague AC is a question for
  the product owner. Use `--strict` when you want those to block as well.
- **Duplicates need the same test values.** Boundary pairs read almost the same by design;
  comparing the numbers first avoids flagging them.
- **Structured output for the generator.** The SDK's `output_format` with a Pydantic schema
  guarantees parseable JSON. It does not make the content correct, which is why the verifier
  exists. Live calls use adaptive thinking at `high` effort and opt into the API's server-side
  fallback in case the model declines a request.
- **Offline first.** Recordings make the whole pipeline runnable in CI and on a laptop with no
  key and no cost, and keep the tests deterministic.
- **Small dependency list:** `anthropic`, `pydantic`, `pytest`. Similarity is `difflib`.

### Known limits

The rules are heuristics and I'd rather say where they stop:

- Consistency only checks limits that the expected result restates ("limit of", "at most",
  "within", ...). It does not work out whether "a 12 MB file is accepted" breaks a 10 MB rule.
- The boundary rule checks that a limit is bracketed. It does not know which side is the valid
  one, so 9,999.99 and 10,000.00 would satisfy "at most 10,000.00" without testing 10,000.01.
- Vague-AC detection uses a word list. It will miss vague wording that isn't on the list.
- Messages and behaviour that a case invents without a number, such as a made-up error text,
  pass unless the case's quote or refs give it away.

## Layout

```
stories/                 5 user stories with numbered acceptance criteria
recordings/              hand-written model responses with planted problems
tcgen/
  generator.py           live call (Claude, structured output) and offline replay
  verifier.py            traceability, consistency, coverage, duplicates, vague-AC checks
  quantities.py          numbers, units and limit detection
  story.py, models.py    story parser and data shapes
  report.py, cli.py      text/JSON report and the command line
tests/                   57 tests: planted-problem answer key, clean sets, rule unit tests
.github/workflows/ci.yml
```

## About me

I'm Feben Tibebe, a QA lead building AI-assisted test workflows with verification gates.
I use AI agents to draft test cases at work, and every generated case has to trace back to an
acceptance criterion before it counts. This repo is a public, self-contained version of that idea.
[LinkedIn](https://www.linkedin.com/in/febentibebe/)
