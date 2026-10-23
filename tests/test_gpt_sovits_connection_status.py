import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from tts.connection_monitor import gpt_sovits_health_url
from ui.chat_ui.chat_ui import ChatUIWindow


def test_gpt_sovits_health_url_uses_docs_without_touching_tts_endpoint():
    assert gpt_sovits_health_url("http://127.0.0.1:9880") == "http://127.0.0.1:9880/docs"
    assert gpt_sovits_health_url("http://127.0.0.1:9880/tts") == "http://127.0.0.1:9880/docs"
    assert gpt_sovits_health_url("  ") == ""


def test_gpt_sovits_connection_status_is_visible_in_conversation_info_popup():
    QApplication.instance() or QApplication([])
    window = ChatUIWindow()
    try:
        label = window.gpt_sovits_status_label
        refresh = window.gpt_sovits_refresh_btn
        assert label.text() == "GPT-SoVITS：未启用"
        assert label.objectName() == "gpt_sovits_connection_status_label"
        assert refresh.objectName() == "refresh_gpt_sovits_connection_button"
        assert window.conversation_info_popup.isAncestorOf(label)
        assert window.chat_layout.indexOf(label) == -1

        window.configure_tts_connection_status("gpt-sovits", "")
        assert label.text() == "GPT-SoVITS：未配置"

        window._set_gpt_sovits_connection_status("checking", "http://127.0.0.1:9880/docs")
        assert label.text() == "GPT-SoVITS：◌ 检查中…"
        window._set_gpt_sovits_connection_status("connected", "http://127.0.0.1:9880/docs")
        assert label.text() == "GPT-SoVITS：● 已连接"
        assert "rgba(82, 111, 88" in label.styleSheet()
        window._set_gpt_sovits_connection_status("disconnected", "Connection refused")
        assert label.text() == "GPT-SoVITS：● 未连接"
        assert label.toolTip() == "Connection refused"
    finally:
        window.close()
