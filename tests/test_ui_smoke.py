"""Offscreen smoke tests for the real chat application UI bootstrap."""
import os
import struct
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication

import core.runtime.app_runtime as app_runtime
import core.runtime.chat_app as chat_app
import core.security.bootstrap as security_bootstrap
from config.config_manager import ConfigManager
from core.runtime.lazy_settings import LazySettingsWindow
from core.security.allowed_roots import AllowedRootsStore
from core.sessions.store import SessionStore
from core.sprite import chat_history
from llm import llm_adapter
from ui.chat_ui.chat_ui import ChatUIWindow
from ui.settings_ui.window import SettingsWindow


def _minimal_png_rgba(width: int = 1, height: int = 1) -> bytes:
    """Return a tiny valid RGBA PNG generated locally for the smoke sprite."""
    import zlib

    def chunk(kind: bytes, data: bytes) -> bytes:
        payload = kind + data
        return (
            struct.pack(">I", len(data))
            + payload
            + struct.pack(">I", zlib.crc32(payload) & 0xFFFFFFFF)
        )

    raw = b"".join(b"\x00" + (b"\xff\xff\xff\xff" * width) for _ in range(height))
    return b"".join(
        [
            b"\x89PNG\r\n\x1a\n",
            chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)),
            chunk(b"IDAT", zlib.compress(raw)),
            chunk(b"IEND", b""),
        ]
    )


def _runtime_worker_threads(workers):
    return (workers.llm_worker, workers.tts_worker, workers.ui_worker)


def _cleanup_workers(workers) -> None:
    running_workers = [worker for worker in _runtime_worker_threads(workers) if worker.isRunning()]
    if not running_workers:
        return

    workers.stop_all()
    for worker in running_workers:
        worker.quit()
    for worker in running_workers:
        worker.wait(1000)


def _write_smoke_config(root: Path) -> None:
    config_dir = root / "data" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "api.yaml").write_text(
        "\n".join(
            [
                "llm_provider: OpenAI",
                "llm_model:",
                "  OpenAI: smoke-model",
                "llm_api_key:",
                "  OpenAI: smoke-key",
                "llm_base_url: http://127.0.0.1:9/v1",
                "tts_provider: none",
                "gpt_sovits_url: ''",
            ]
        ),
        encoding="utf-8",
    )
    (config_dir / "system_config.yaml").write_text("ui_language: zh_CN\n", encoding="utf-8")
    (config_dir / "background.yaml").write_text("[]\n", encoding="utf-8")
    (config_dir / "characters.yaml").write_text(
        "\n".join(
            [
                "- name: Smoke",
                "  color: '#ABCDEF'",
                "  sprite_scale: 1.0",
                "  character_setting: smoke test character",
                "  sprites:",
                "    - path: default.png",
            ]
        ),
        encoding="utf-8",
    )

    sprite_dir = root / "data" / "sprites" / "default"
    sprite_dir.mkdir(parents=True, exist_ok=True)
    (sprite_dir / "default.png").write_bytes(_minimal_png_rgba())


def test_build_chat_app_offscreen_smoke_shows_default_sprite_and_cleans_up(
    monkeypatch, tmp_path
):
    """Build the real PySide window graph offscreen without workers/network/history pollution."""
    repo_root = Path(__file__).resolve().parents[1]
    original_history_file = repo_root / "data" / "chat_history" / "default.json"
    original_history_bytes = (
        original_history_file.read_bytes() if original_history_file.exists() else None
    )

    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.chdir(tmp_path)
    _write_smoke_config(tmp_path)
    for name in ("API", "API_LOCAL", "SYSTEM", "CHARACTERS", "BACKGROUND", "MCP"):
        filename = {
            "API": "api.yaml", "API_LOCAL": "api.local.yaml",
            "SYSTEM": "system_config.yaml", "CHARACTERS": "characters.yaml",
            "BACKGROUND": "background.yaml", "MCP": "mcp.yaml",
        }[name]
        monkeypatch.setattr(ConfigManager, f"_{name}_CONFIG_PATH", tmp_path / "data/config" / filename)
    history_root = tmp_path / "isolated_history"
    monkeypatch.setattr(
        chat_history,
        "DEFAULT_FILE",
        history_root / "default.json",
    )
    monkeypatch.setattr(chat_history, "_session_store", SessionStore(
        history_root=history_root,
        sessions_dir=history_root / "sessions",
        index_path=history_root / "sessions.json",
        legacy_default_file=history_root / "default.json",
    ))
    monkeypatch.setattr(chat_history, "_active_session_id", None)
    monkeypatch.setattr(chat_history, "chat_history", [])
    monkeypatch.setattr(
        security_bootstrap, "_ALLOWED_ROOTS_STORE",
        AllowedRootsStore(tmp_path / "security/allowed-roots.json", project_root=tmp_path),
    )
    monkeypatch.setattr(app_runtime, "_app_runtime", None)
    ConfigManager.reset()

    client_calls = []

    def fake_client(**kwargs):
        client_calls.append(kwargs)
        return SimpleNamespace(**kwargs, close=lambda: None)

    monkeypatch.setattr(llm_adapter, "_create_openai_client", fake_client)
    created_settings = []
    real_settings_factory = chat_app.create_settings_window

    def create_real_settings():
        window = real_settings_factory()
        created_settings.append(window)
        return window

    monkeypatch.setattr(chat_app, "create_settings_window", create_real_settings)
    handles = None
    existing_app = QApplication.instance()
    if existing_app is not None:
        if existing_app.platformName().lower() != "offscreen":
            pytest.skip(
                "existing QApplication is not using the offscreen Qt platform"
            )
        monkeypatch.setattr(chat_app, "QApplication", lambda argv: existing_app)
    try:
        handles = chat_app.build_chat_app(["yayu-ui-smoke"])

        assert isinstance(handles.window, ChatUIWindow)
        assert handles.window.windowTitle() == "芽语"
        assert handles.app.applicationName() == "Yayu"
        assert handles.app.applicationDisplayName() == "芽语"
        assert hasattr(handles.window, "user_message_sent")
        assert hasattr(handles.window, "clear_requested")
        assert hasattr(handles.window, "reroll_requested")
        assert hasattr(handles.window, "settings_requested")
        assert isinstance(handles.settings_window, LazySettingsWindow)
        assert not handles.settings_window.is_created
        assert handles.settings_window.memory_tab is None
        assert created_settings == []
        assert handles.signal_wiring_handles is not None
        assert handles.runtime_setup is not None
        assert handles.workers is not None
        assert all(
            not worker.isRunning() for worker in _runtime_worker_threads(handles.workers)
        )

        handles.window.show()
        handles.sprite_controller.show_default_sprite()
        assert not handles.settings_window.is_created
        handles.window.settings_requested.emit()
        handles.app.processEvents()

        assert handles.window.isVisible()
        assert handles.settings_window.is_created
        assert len(created_settings) == 1
        settings = created_settings[0]
        assert isinstance(settings, SettingsWindow)
        assert settings.windowTitle() == "芽语 · 设置中心"
        assert settings.accessibleName() == "Yayu settings window"
        assert settings.isVisible()
        assert handles.settings_window.memory_tab is settings.memory_tab
        pixmap = handles.window.sprite_widget.pixmap()
        assert pixmap is not None
        assert not pixmap.isNull()
        assert handles.settings_window.close() is True
        assert not settings.isVisible()
        handles.window.settings_requested.emit()
        handles.app.processEvents()
        assert created_settings == [settings]
        assert settings.isVisible()
        assert client_calls == []

    finally:
        if handles is not None:
            try:
                _cleanup_workers(handles.workers)
            finally:
                handles.chat_history.save()
                handles.settings_window.close()
                for settings in created_settings:
                    settings.deleteLater()
                handles.settings_window.deleteLater()
                handles.window.close()
                handles.window.deleteLater()
                QApplication.sendPostedEvents(None, QEvent.DeferredDelete)
                handles.app.processEvents()
        monkeypatch.setattr(app_runtime, "_app_runtime", None)
        ConfigManager.reset()
        chat_history.chat_history.clear()

    assert chat_history.DEFAULT_FILE == tmp_path / "isolated_history" / "default.json"
    sessions_dir = chat_history.get_session_store().sessions_dir
    assert sessions_dir.exists()
    assert any(sessions_dir.glob("*.json"))
    if original_history_bytes is None:
        assert not original_history_file.exists()
    else:
        assert original_history_file.read_bytes() == original_history_bytes
