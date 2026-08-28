import pytest

from agentbridge_server.remote_settings import RemoteRelaySettings


def test_remote_settings_loads_distinct_tokens_per_device(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "AGENTBRIDGE_PAIRINGS_JSON",
        '{"desktop":"D1234567890123456789012345678901","laptop":"L1234567890123456789012345678901"}',
    )
    settings = RemoteRelaySettings.load()

    assert settings.pairing_token_for("desktop") == "D1234567890123456789012345678901"
    assert settings.pairing_token_for("laptop") == "L1234567890123456789012345678901"
    assert settings.pairing_token_for("unknown") is None


def test_remote_settings_rejects_an_invalid_pairing_map(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENTBRIDGE_PAIRINGS_JSON", '{"desktop":"too-short"}')

    with pytest.raises(RuntimeError, match="at least 32 characters"):
        RemoteRelaySettings.load()
