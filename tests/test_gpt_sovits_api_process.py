from pathlib import Path

import pytest

from tts.api_process import build_gpt_sovits_api_launch_spec, is_managed_local_api_url


@pytest.mark.parametrize(
    "url",
    ["http://127.0.0.1:9880", "http://localhost:9880/tts", "http://[::1]:9880"],
)
def test_managed_local_api_url_accepts_only_local_9880(url):
    assert is_managed_local_api_url(url) is True


@pytest.mark.parametrize(
    "url",
    ["http://127.0.0.1:9872", "http://192.168.1.8:9880", "https://example.com:9880"],
)
def test_managed_local_api_url_rejects_other_services(url):
    assert is_managed_local_api_url(url) is False


def test_build_launch_spec_resolves_bundled_python_from_local_config(tmp_path):
    package_root = tmp_path / "GPT-SoVITS"
    bert_path = package_root / "GPT_SoVITS" / "pretrained_models" / "bert"
    bert_path.mkdir(parents=True)
    runtime = package_root / "runtime"
    runtime.mkdir()
    (runtime / "python.exe").touch()
    (package_root / "api_v2.py").touch()
    config_path = tmp_path / "tts_infer.local.yaml"
    config_path.write_text(
        f"custom:\n  bert_base_path: {bert_path.as_posix()}\n",
        encoding="utf-8",
    )

    spec = build_gpt_sovits_api_launch_spec(config_path)

    assert spec.program == str(runtime / "python.exe")
    assert spec.working_directory == str(package_root)
    assert spec.arguments == (
        str(package_root / "api_v2.py"),
        "-c",
        str(config_path),
        "-a",
        "127.0.0.1",
        "-p",
        "9880",
    )


def test_build_launch_spec_reports_missing_local_config(tmp_path):
    with pytest.raises(FileNotFoundError, match="找不到 GPT-SoVITS 本地配置"):
        build_gpt_sovits_api_launch_spec(tmp_path / "missing.yaml")
