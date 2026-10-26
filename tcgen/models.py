"""Data shapes shared by the generator and the verifier.

`TestCaseSet` is the JSON schema Claude is asked to fill (structured outputs).
The schema keeps the model's output parseable; it does not make the content
true. That is the verifier's job.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ACQuote(BaseModel):
    ac: int = Field(description="Number of the acceptance criterion being quoted.")
    text: str = Field(description="The acceptance criterion copied word for word from the story.")


class TestCase(BaseModel):
    __test__ = False  # not a pytest test class

    id: str = Field(description="Case id, e.g. TC-01.")
    title: str
    type: Literal["positive", "negative", "boundary"]
    preconditions: list[str]
    steps: list[str]
    expected: str = Field(description="Observable expected result.")
    ac_refs: list[int] = Field(description="Numbers of the acceptance criteria this case checks.")
    ac_quotes: list[ACQuote] = Field(description="One verbatim quote per cited acceptance criterion.")


class TestCaseSet(BaseModel):
    __test__ = False

    cases: list[TestCase]


class GeneratedCases(BaseModel):
    """What `tcgen generate` writes and `tcgen verify` reads (one file per story)."""

    story: str
    mode: Literal["live", "offline", "hand-written"]
    model: str | None = None
    cases: list[TestCase]


class Recording(BaseModel):
    """A recorded (or hand-written) model response, replayed by `generate --offline`."""

    recording: dict
    output: TestCaseSet
