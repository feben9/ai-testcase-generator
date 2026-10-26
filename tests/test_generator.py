"""Generator: offline replay, and the live request shape (with a fake client, no network)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from helpers import RECORDINGS, STORIES
from tcgen import DEFAULT_MODEL
from tcgen.cli import main
from tcgen.generator import FALLBACK_BETA, GenerationError, generate_live, generate_offline
from tcgen.models import TestCaseSet
from tcgen.story import parse_story

STORY = parse_story(STORIES / "money-transfer.md")


def test_offline_reads_the_recording():
    case_set, meta = generate_offline(STORY, RECORDINGS)
    assert len(case_set.cases) == 18
    assert meta["source"] == "hand-written"


def test_offline_without_recording(tmp_path):
    with pytest.raises(GenerationError):
        generate_offline(STORY, tmp_path)


class FakeStream:
    def __init__(self, message):
        self.message = message

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self.message


class FakeClient:
    """Mimics client.beta.messages.stream(...) and records the request."""

    def __init__(self, message):
        self.request = None
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._stream))
        self._message = message

    def _stream(self, **kwargs):
        self.request = kwargs
        return FakeStream(self._message)


def _message(stop_reason="end_turn", parsed=None, text=""):
    return SimpleNamespace(
        stop_reason=stop_reason,
        stop_details=SimpleNamespace(category="cyber") if stop_reason == "refusal" else None,
        parsed_output=parsed,
        content=[SimpleNamespace(type="text", text=text)],
    )


def test_live_request_shape():
    expected = generate_offline(STORY, RECORDINGS)[0]
    client = FakeClient(_message(parsed=expected))
    result = generate_live(STORY, client=client)
    assert result == expected
    request = client.request
    assert request["model"] == DEFAULT_MODEL == "claude-sonnet-5-5"
    assert request["output_format"] is TestCaseSet
    assert request["thinking"] == {"type": "adaptive"}
    assert request["output_config"] == {"effort": "high"}
    assert request["betas"] == [FALLBACK_BETA] and request["fallbacks"] == "default"
    assert "temperature" not in request
    assert STORY.markdown in request["messages"][0]["content"]


def test_live_falls_back_to_parsing_text():
    expected = generate_offline(STORY, RECORDINGS)[0]
    client = FakeClient(_message(parsed=None, text=expected.model_dump_json()))
    assert generate_live(STORY, client=client) == expected


@pytest.mark.parametrize("stop_reason", ["refusal", "max_tokens"])
def test_live_stops_on_refusal_or_truncation(stop_reason):
    with pytest.raises(GenerationError):
        generate_live(STORY, client=FakeClient(_message(stop_reason=stop_reason)))


def test_live_mode_needs_a_key(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert main(["generate", str(STORIES / "money-transfer.md"), "--out", str(tmp_path)]) == 2
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().err


def test_schema_is_accepted_by_the_sdk_helper():
    from anthropic.lib._parse._transform import to_json_output_format

    fmt = to_json_output_format(TestCaseSet)
    assert fmt["type"] == "json_schema"
    assert "cases" in fmt["schema"]["properties"]
