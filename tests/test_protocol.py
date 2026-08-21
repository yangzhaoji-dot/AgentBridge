import json

import pytest

from common.protocol import PROTOCOL_VERSION, ProtocolError, make_message, parse_message


def test_message_round_trip() -> None:
    original = make_message("task.start", {"text": "hello"})
    parsed = parse_message(json.dumps(original))
    assert parsed["type"] == "task.start"
    assert parsed["payload"] == {"text": "hello"}
    assert parsed["protocol_version"] == PROTOCOL_VERSION


@pytest.mark.parametrize(
    "raw",
    [
        "not-json",
        "[]",
        '{"payload": {}}',
        '{"type": "x", "payload": []}',
        '{"type": "x", "protocol_version": 99}',
    ],
)
def test_invalid_messages_are_rejected(raw: str) -> None:
    with pytest.raises(ProtocolError):
        parse_message(raw)
