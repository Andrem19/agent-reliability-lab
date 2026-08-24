import json

from arl.safety.redaction import REDACTED, SecretRedactor


def test_redacts_nested_secret_keys_and_auth_headers() -> None:
    source = {
        "authorization": "Bearer extremely-secret-token",
        "nested": {"api_key": "synthetic-secret-value"},
        "items": [{"cookie": "session=abc"}],
        "safe": "visible",
    }
    result = SecretRedactor().redact(source)
    assert result["authorization"] == REDACTED
    assert result["nested"]["api_key"] == REDACTED
    assert result["items"][0]["cookie"] == REDACTED
    assert result["safe"] == "visible"
    serialized = json.dumps(result)
    assert "extremely-secret" not in serialized
    assert "1234567890" not in serialized


def test_redacts_credentials_embedded_in_text() -> None:
    value = "Authorization: Bearer abcdefghijklmnop token=my-secret-value&safe=yes"
    result = SecretRedactor().redact_text(value)
    assert "abcdefghijklmnop" not in result
    assert "my-secret-value" not in result
    assert result.count(REDACTED) == 2
