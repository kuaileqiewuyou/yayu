import importlib.util
import io
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "validate_template_output.py"


def _load_script_module():
    spec = importlib.util.spec_from_file_location("validate_template_output", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_cli_accepts_valid_file(tmp_path):
    module = _load_script_module()
    sample = tmp_path / "sample.jsonl"
    sample.write_text('{"character_name":"小夏","speech":"你好","sprite":"0"}\n', encoding="utf-8")
    stdout = io.StringIO()

    exit_code = module.main([str(sample)], stdout=stdout)

    assert exit_code == 0
    assert "校验通过" in stdout.getvalue()


def test_cli_rejects_invalid_file_with_line_number(tmp_path):
    module = _load_script_module()
    sample = tmp_path / "bad.jsonl"
    sample.write_text('{"character_name":"小夏","speech":"你好"}\n', encoding="utf-8")
    stdout = io.StringIO()

    exit_code = module.main([str(sample)], stdout=stdout)

    assert exit_code == 1
    output = stdout.getvalue()
    assert "错误" in output
    assert "第 1 行" in output
    assert "sprite" in output


def test_cli_warning_only_exits_zero(tmp_path):
    module = _load_script_module()
    sample = tmp_path / "warn.jsonl"
    sample.write_text('{"character_name":"CG","speech":"","sprite":"夕阳下的教室"}\n', encoding="utf-8")
    stdout = io.StringIO()

    exit_code = module.main([str(sample)], stdout=stdout)

    assert exit_code == 0
    output = stdout.getvalue()
    assert "警告" in output
    assert "CG 的 prompt 应放在 speech" in output


def test_cli_reads_from_stdin_when_path_is_dash():
    module = _load_script_module()
    stdout = io.StringIO()
    stdin = io.StringIO('{"character_name":"小夏","speech":"你好","sprite":"0"}\n')

    exit_code = module.main(["-"], stdin=stdin, stdout=stdout)

    assert exit_code == 0
    assert "校验通过" in stdout.getvalue()


def test_cli_reads_from_stdin_when_path_is_omitted():
    module = _load_script_module()
    stdout = io.StringIO()
    stdin = io.StringIO('{"character_name":"小夏","speech":"你好","sprite":"0"}\n')

    exit_code = module.main([], stdin=stdin, stdout=stdout)

    assert exit_code == 0
    assert "校验通过" in stdout.getvalue()


def test_cli_parse_error_uses_injected_stderr_and_returns_two():
    module = _load_script_module()
    stderr = io.StringIO()

    exit_code = module.main(["--bad-option"], stderr=stderr)

    assert exit_code == 2
    error_output = stderr.getvalue()
    assert "--bad-option" in error_output
    assert "usage:" in error_output


def test_cli_missing_file_exits_two(tmp_path):
    module = _load_script_module()
    stderr = io.StringIO()

    exit_code = module.main([str(tmp_path / "missing.jsonl")], stderr=stderr)

    assert exit_code == 2
    assert "无法读取" in stderr.getvalue()
