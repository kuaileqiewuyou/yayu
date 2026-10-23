import os
from types import SimpleNamespace
import subprocess

import pytest

from core.updates import credentials
from core.updates.releases import UpdateError


FAKE_TOKEN = "test-only-credential-not-a-real-github-token"


@pytest.fixture(autouse=True)
def no_real_credentials(monkeypatch):
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(credentials.shutil, "which", lambda name: None)


def test_no_config_environment_or_cli_returns_none(tmp_path):
    assert credentials.get_token(tmp_path) is None
    assert not (tmp_path / "data").exists()


def test_environment_precedence_without_writing_any_config(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "fallback-test-value")
    monkeypatch.setenv("GH_TOKEN", FAKE_TOKEN)
    assert credentials.get_token(tmp_path) == FAKE_TOKEN
    monkeypatch.delenv("GH_TOKEN")
    assert credentials.get_token(tmp_path) == "fallback-test-value"
    assert not (tmp_path / "data").exists()


def test_saved_dpapi_is_preferred_to_environment_and_cli(tmp_path, monkeypatch):
    path = tmp_path / credentials._TOKEN_PATH
    path.parent.mkdir(parents=True)
    path.write_bytes(b"mock-encrypted")
    monkeypatch.setenv("GH_TOKEN", "ignored-environment")
    monkeypatch.setattr(credentials, "_dpapi", lambda data, decrypt: FAKE_TOKEN.encode())
    assert credentials.get_token(tmp_path) == FAKE_TOKEN


def test_gh_token_stays_in_memory_and_stderr_is_not_captured(tmp_path, monkeypatch):
    monkeypatch.setattr(credentials.shutil, "which", lambda name: "C:/mock/gh.exe")
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0, stdout=FAKE_TOKEN.encode() + b"\n")

    monkeypatch.setattr(credentials.subprocess, "run", fake_run)
    assert credentials.get_token(tmp_path) == FAKE_TOKEN
    args, kwargs = calls[0]
    assert args == ["C:/mock/gh.exe", "auth", "token", "--hostname", "github.com"]
    assert kwargs["stderr"] == subprocess.DEVNULL
    assert kwargs["stdin"] == subprocess.DEVNULL
    assert kwargs["stdout"] == subprocess.PIPE
    assert kwargs["timeout"] == 8
    assert not (tmp_path / "data").exists()


@pytest.mark.parametrize("failure", [OSError("fake CLI error"), subprocess.TimeoutExpired("gh", 8)])
def test_unavailable_or_timed_out_cli_is_optional(tmp_path, monkeypatch, failure):
    monkeypatch.setattr(credentials.shutil, "which", lambda name: "mock-gh")

    def fail(*args, **kwargs):
        raise failure

    monkeypatch.setattr(credentials.subprocess, "run", fail)
    assert credentials.get_token(tmp_path) is None


def test_corrupt_saved_token_is_actionable_and_never_silently_replaced(tmp_path, monkeypatch):
    path = tmp_path / credentials._TOKEN_PATH
    path.parent.mkdir(parents=True)
    path.write_bytes(b"corrupt")
    monkeypatch.setenv("GH_TOKEN", FAKE_TOKEN)

    def fail(*args, **kwargs):
        raise UpdateError("无法解密 GitHub 访问令牌，请重新设置。")

    monkeypatch.setattr(credentials, "_dpapi", fail)
    with pytest.raises(UpdateError, match="解密") as caught:
        credentials.get_token(tmp_path)
    assert FAKE_TOKEN not in str(caught.value)


@pytest.mark.parametrize("token", ["contains\nnewline", "contains space", "中文", "a" * 4097])
def test_invalid_input_is_rejected_without_saving(tmp_path, token):
    with pytest.raises(UpdateError, match="令牌格式") as caught:
        credentials.save_token(tmp_path, token)
    assert token not in str(caught.value)
    assert not (tmp_path / "data").exists()


def test_remove_saved_credential_does_not_touch_other_private_data(tmp_path):
    path = tmp_path / credentials._TOKEN_PATH
    path.parent.mkdir(parents=True)
    path.write_bytes(b"mock cipher")
    other = path.parent / "unrelated.txt"
    other.write_text("untouched")
    credentials.save_token(tmp_path, "  ")
    assert not path.exists()
    assert other.read_text() == "untouched"


@pytest.mark.skipif(os.name != "nt", reason="Real user-bound DPAPI requires Windows")
def test_real_dpapi_round_trip_in_temporary_directory_never_stores_plaintext(tmp_path):
    credentials.save_token(tmp_path, FAKE_TOKEN)
    path = tmp_path / credentials._TOKEN_PATH
    encrypted = path.read_bytes()
    assert FAKE_TOKEN.encode() not in encrypted
    assert credentials.get_token(tmp_path) == FAKE_TOKEN
    assert list(path.parent.glob("*.tmp")) == []
    credentials.save_token(tmp_path, "")
    assert not path.exists()


def test_non_windows_dpapi_has_no_plaintext_fallback(monkeypatch):
    # Only call the primitive while patched: changing global os.name would make
    # Windows pathlib choose an unsupported PosixPath during filesystem work.
    monkeypatch.setattr(credentials.os, "name", "posix")
    with pytest.raises(UpdateError, match="不支持 Windows DPAPI"):
        credentials._dpapi(FAKE_TOKEN.encode(), decrypt=False)


def test_save_failure_preserves_previously_saved_ciphertext(tmp_path, monkeypatch):
    path = tmp_path / credentials._TOKEN_PATH
    path.parent.mkdir(parents=True)
    path.write_bytes(b"old cipher")
    monkeypatch.setattr(credentials, "_dpapi", lambda data, decrypt: b"new cipher")

    def fail_replace(*args):
        raise OSError("test failure")

    monkeypatch.setattr(credentials.os, "replace", fail_replace)
    with pytest.raises(UpdateError, match="无法保存"):
        credentials.save_token(tmp_path, FAKE_TOKEN)
    assert path.read_bytes() == b"old cipher"
    assert list(path.parent.glob("*.tmp")) == []
