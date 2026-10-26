"""Ask Claude for test cases (live), or replay a recorded response (offline)."""

from __future__ import annotations

from pathlib import Path

from . import DEFAULT_MODEL
from .models import Recording, TestCaseSet
from .story import Story

# Server-side fallback: if the model declines for policy reasons, the API retries
# on Anthropic's recommended fallback model inside the same call.
FALLBACK_BETA = "server-side-fallback-2026-07-01"
MAX_TOKENS = 64000  # streamed, so a long case list with thinking is not cut off
EFFORT = "high"

SYSTEM_PROMPT = """\
You are a senior QA engineer writing manual test cases from a user story.

Rules:
- Test only behaviour the acceptance criteria (AC) state. Do not add features, limits or messages the story does not contain.
- Every case lists the AC numbers it checks in ac_refs, and copies each of those AC lines word for word into ac_quotes.
- Every AC gets at least one positive case that shows the allowed path works.
- For every numeric limit (amounts, sizes, counts, durations), add boundary cases at the limit and just past it.
- Expected results use the exact numbers and messages from the AC.
- If an AC has no measurable target, do not invent one. Write one case for it whose expected result says the target must be agreed with the product owner, and keep numbers out of that expected result.
- Number the cases TC-01, TC-02, and so on.
"""


class GenerationError(RuntimeError):
    pass


def user_prompt(story: Story) -> str:
    return (
        "Write test cases for this user story. Cover every acceptance criterion.\n\n"
        f"<story>\n{story.markdown}\n</story>"
    )


def generate_offline(story: Story, recordings_dir: str | Path) -> tuple[TestCaseSet, dict]:
    path = Path(recordings_dir) / f"{story.key}.json"
    if not path.exists():
        raise GenerationError(f"no recording for {story.key}: expected {path}")
    recording = Recording.model_validate_json(path.read_text(encoding="utf-8"))
    return recording.output, recording.recording


def generate_live(story: Story, model: str = DEFAULT_MODEL, client=None) -> TestCaseSet:
    """One structured-output call per story. `client` is injectable for tests."""
    if client is None:
        import anthropic

        client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY

    with client.beta.messages.stream(
        model=model,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt(story)}],
        thinking={"type": "adaptive"},
        output_config={"effort": EFFORT},
        output_format=TestCaseSet,
        betas=[FALLBACK_BETA],
        fallbacks="default",
    ) as stream:
        message = stream.get_final_message()

    if message.stop_reason == "refusal":
        category = getattr(getattr(message, "stop_details", None), "category", None)
        raise GenerationError(f"{story.key}: the model declined the request (category: {category})")
    if message.stop_reason == "max_tokens":
        raise GenerationError(f"{story.key}: output was cut off at max_tokens={MAX_TOKENS}")

    parsed = message.parsed_output
    if parsed is None:  # fall back to validating the text block ourselves
        text = "".join(block.text for block in message.content if block.type == "text")
        parsed = TestCaseSet.model_validate_json(text)
    return parsed
