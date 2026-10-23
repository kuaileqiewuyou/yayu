import ast
from pathlib import Path
from urllib.error import URLError

from ui.settings_ui.api_controller import APISettingsController


def test_api_controller_builds_llm_config_status_without_leaking_api_key():
    message, is_error = APISettingsController.llm_config_status_message(
        provider=" deepseek ",
        api_key=" sk-secret ",
        base_url=" https://api.deepseek.com/v1 ",
        model=" deepseek-chat ",
    )

    assert is_error is False
    assert message == "LLM 配置看起来可用：deepseek / deepseek-chat。保存后请重启聊天窗口后生效。"
    assert "sk-secret" not in message


def test_api_controller_reports_missing_llm_config_fields_like_settings_window():
    message, is_error = APISettingsController.llm_config_status_message(
        provider="deepseek",
        api_key=" ",
        base_url=" ",
        model=" ",
        saved=True,
    )

    assert is_error is True
    assert message == "配置已保存。LLM 配置不完整：API Key、Base URL、模型 ID。"


def test_api_controller_checks_comfyui_connection_success_with_normalized_url():
    calls = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"system": {}}'

    def fake_urlopen(req, timeout=None):
        calls.append({"url": req.full_url, "method": req.get_method(), "timeout": timeout})
        return FakeResponse()

    message, is_error = APISettingsController.comfyui_connection_status(
        provider="comfyui",
        base_url=" http://127.0.0.1:8188/ ",
        urlopen=fake_urlopen,
    )

    assert calls == [{"url": "http://127.0.0.1:8188/system_stats", "method": "GET", "timeout": 2.0}]
    assert is_error is False
    assert message == "ComfyUI 连接成功。"


def test_api_controller_reports_comfyui_connection_failure():
    def fake_urlopen(req, timeout=None):
        raise URLError("refused")

    message, is_error = APISettingsController.comfyui_connection_status(
        provider="comfyui",
        base_url="http://127.0.0.1:8188",
        urlopen=fake_urlopen,
    )

    assert is_error is True
    assert "ComfyUI 连接失败" in message
    assert "refused" in message


def test_api_controller_skips_comfyui_check_when_provider_is_not_comfyui():
    def fail_urlopen(req, timeout=None):
        raise AssertionError("urlopen should not be called")

    message, is_error = APISettingsController.comfyui_connection_status(
        provider="none",
        base_url="http://127.0.0.1:8188",
        urlopen=fail_urlopen,
    )

    assert is_error is True
    assert message == "请先将 T2I / CG 引擎切换为 comfyui 后再测试连接。"


def test_api_controller_reports_empty_comfyui_url_without_request():
    def fail_urlopen(req, timeout=None):
        raise AssertionError("urlopen should not be called")

    message, is_error = APISettingsController.comfyui_connection_status(
        provider="comfyui",
        base_url=" ",
        urlopen=fail_urlopen,
    )

    assert is_error is True
    assert message == "ComfyUI API URL 不能为空。"


def test_settings_window_comfyui_check_forwarder_delegates_to_api_controller():
    window_path = Path(__file__).resolve().parents[1] / "ui" / "settings_ui" / "window.py"
    source = window_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    settings_class = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "SettingsWindow")
    method = next(
        node
        for node in settings_class.body
        if isinstance(node, ast.FunctionDef) and node.name == "_check_comfyui_connection"
    )
    method_source = ast.get_source_segment(source, method) or ""

    assert "APISettingsController.comfyui_connection_status(" in method_source
    assert "self.t2i_provider_combo.currentText()" in method_source
    assert "self.t2i_api_url_edit.text()" in method_source
    assert "request.urlopen" not in method_source
    assert "system_stats" not in method_source
    assert "request.Request" not in method_source


def test_settings_window_llm_config_status_forwarder_delegates_to_api_controller():
    window_path = Path(__file__).resolve().parents[1] / "ui" / "settings_ui" / "window.py"
    source = window_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    settings_class = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "SettingsWindow")
    method = next(
        node
        for node in settings_class.body
        if isinstance(node, ast.FunctionDef) and node.name == "_llm_config_status_message"
    )
    method_source = ast.get_source_segment(source, method) or ""

    assert "APISettingsController.llm_config_status_message(" in method_source
    assert "self.llm_provider_combo.currentText()" in method_source
    assert "self.api_key_edit.text()" in method_source
    assert "missing = []" not in method_source
    assert "API Key" not in method_source
    assert "保存后请重启聊天窗口后生效" not in method_source
