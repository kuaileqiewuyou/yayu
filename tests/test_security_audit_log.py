from pathlib import Path

import json

from core.security.audit_log import SecurityAuditLog


def test_security_audit_log_redacts_secrets_and_appends_jsonl(tmp_path: Path) -> None:
    path = tmp_path / "security" / "audit.jsonl"
    audit = SecurityAuditLog(path)

    audit.record(
        "approval_requested",
        decision_id="decision-1",
        command="curl -H 'Authorization: Bearer super-secret-token' https://example.com",
        status="pending",
    )

    content = path.read_text(encoding="utf-8")
    assert "approval_requested" in content
    assert "decision-1" in content
    assert "super-secret-token" not in content
    assert "[REDACTED]" in content


def test_security_audit_log_redacts_common_cli_json_basic_cookie_and_nested_secrets(tmp_path: Path) -> None:
    path = tmp_path / "security" / "audit.jsonl"
    audit = SecurityAuditLog(path)

    audit.record(
        "credential_shapes",
        command=(
            "API_KEY='quoted-secret' --token cli-secret --api-key=equals-secret "
            "Authorization: Basic basic-secret curl -u alice:curl-secret "
            "https://bob:url-secret@example.test/private AWS_SECRET_ACCESS_KEY aws-secret "
            "Cookie: session=cookie-secret"
        ),
        request={"token": "nested-secret", "args": ["password=json-secret"]},
    )

    content = path.read_text(encoding="utf-8")
    for secret in (
        "quoted-secret",
        "cli-secret",
        "equals-secret",
        "basic-secret",
        "cookie-secret",
        "nested-secret",
        "json-secret",
        "curl-secret",
        "url-secret",
        "aws-secret",
    ):
        assert secret not in content
    entry = json.loads(content)
    assert entry["request"]["token"] == "[REDACTED]"
    assert entry["request"]["args"] == ["password=[REDACTED]"]
    assert content.count("[REDACTED]") >= 7
