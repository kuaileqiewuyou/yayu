import importlib
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

import core.runtime.startup_notices as startup_notices
from llm.tools.tool_manager import ToolManager


@pytest.fixture
def chat_app_module(monkeypatch):
    # 提前触发真实 PySide6 完整初始化：pytest-qt 的 setup 钩子在每个用例后调用
    # QApplication.instance().processEvents()；若真实 PySide6 尚未完全加载，
    # 与下方 fake 模块替换（monkeypatch sys.modules）交互会在 Windows 上触发
    # access violation（PySide6 6.8.x + pytest-qt 4.5 的时序敏感问题）。
    real_qtwidgets = sys.modules.get("PySide6.QtWidgets")
    if real_qtwidgets is not None:
        _ = real_qtwidgets.QApplication.instance()
    pyside6_module = types.ModuleType("PySide6")
    qtcore_module = types.ModuleType("PySide6.QtCore")
    qtgui_module = types.ModuleType("PySide6.QtGui")
    qtwidgets_module = types.ModuleType("PySide6.QtWidgets")
    qtmultimedia_module = types.ModuleType("PySide6.QtMultimedia")

    class _FakeWidget:
        def __init__(self, *args, **kwargs):
            pass

        def __getattr__(self, name):
            return lambda *args, **kwargs: None

    class _FakeEnumValue:
        def __init__(self, name):
            self.name = name

        def __or__(self, other):
            return self

    class _FakeEnumNamespace:
        def __getattr__(self, name):
            return _FakeEnumValue(name)

    class _FakeQt:
        WindowType = _FakeEnumNamespace()
        WidgetAttribute = _FakeEnumNamespace()
        AlignmentFlag = _FakeEnumNamespace()
        TransformationMode = _FakeEnumNamespace()
        MouseButton = _FakeEnumNamespace()
        CursorShape = _FakeEnumNamespace()
        TextFormat = _FakeEnumNamespace()

    class _FakeQUrl:
        def __init__(self, path: str = ""):
            self.path = path

        @classmethod
        def fromLocalFile(cls, path: str):
            return cls(path)

    qtcore_module.QUrl = _FakeQUrl
    qtcore_module.Qt = _FakeQt
    qtcore_module.Signal = lambda *args, **kwargs: None
    qtcore_module.Slot = lambda *args, **kwargs: (lambda func: func)
    qtcore_module.QObject = _FakeWidget
    qtcore_module.QThread = _FakeWidget
    qtcore_module.QTimer = _FakeWidget
    qtcore_module.QSize = _FakeWidget
    # ui.window_chrome（frameless title bar）依赖的 QtCore 符号
    qtcore_module.QEvent = _FakeWidget
    qtcore_module.QPoint = _FakeWidget
    qtcore_module.QRect = _FakeWidget
    qtcore_module.QEasingCurve = SimpleNamespace(Type=_FakeEnumNamespace())

    qtwidgets_module.QApplication = type("QApplication", (), {"instance": staticmethod(lambda: None)})
    qtwidgets_module.QMainWindow = _FakeWidget
    qtwidgets_module.QWidget = _FakeWidget
    qtwidgets_module.QDialog = _FakeWidget
    qtwidgets_module.QVBoxLayout = _FakeWidget
    qtwidgets_module.QHBoxLayout = _FakeWidget
    qtwidgets_module.QFormLayout = _FakeWidget
    qtwidgets_module.QGroupBox = _FakeWidget
    qtwidgets_module.QTabWidget = _FakeWidget
    qtwidgets_module.QListWidget = _FakeWidget
    qtwidgets_module.QListWidgetItem = _FakeWidget
    qtwidgets_module.QPushButton = _FakeWidget
    qtwidgets_module.QMessageBox = _FakeWidget
    qtwidgets_module.QLabel = _FakeWidget
    qtwidgets_module.QLineEdit = _FakeWidget
    qtwidgets_module.QTextEdit = _FakeWidget
    qtwidgets_module.QComboBox = _FakeWidget
    qtwidgets_module.QDoubleSpinBox = _FakeWidget
    qtwidgets_module.QCheckBox = _FakeWidget
    qtwidgets_module.QFileDialog = _FakeWidget
    qtwidgets_module.QScrollArea = _FakeWidget
    qtwidgets_module.QFrame = _FakeWidget
    qtwidgets_module.QSizePolicy = _FakeWidget
    qtwidgets_module.QGraphicsDropShadowEffect = _FakeWidget
    qtwidgets_module.QInputDialog = _FakeWidget
    qtwidgets_module.QSplitter = _FakeWidget
    qtwidgets_module.QGridLayout = _FakeWidget

    qtgui_module.QPixmap = _FakeWidget
    qtgui_module.QFont = _FakeWidget
    qtgui_module.QColor = _FakeWidget
    qtgui_module.QPalette = _FakeWidget
    qtgui_module.QIcon = _FakeWidget
    qtgui_module.QPainter = _FakeWidget
    qtgui_module.QDesktopServices = _FakeWidget

    qtmultimedia_module.QAudioOutput = _FakeWidget
    qtmultimedia_module.QMediaPlayer = _FakeWidget

    monkeypatch.setitem(sys.modules, "PySide6", pyside6_module)
    monkeypatch.setitem(sys.modules, "PySide6.QtCore", qtcore_module)
    monkeypatch.setitem(sys.modules, "PySide6.QtGui", qtgui_module)
    monkeypatch.setitem(sys.modules, "PySide6.QtWidgets", qtwidgets_module)
    monkeypatch.setitem(sys.modules, "PySide6.QtMultimedia", qtmultimedia_module)

    fake_chat_ui_module = types.ModuleType("ui.chat_ui.chat_ui")
    fake_chat_ui_module.ChatUIWindow = type("ChatUIWindow", (), {})
    monkeypatch.setitem(sys.modules, "ui.chat_ui.chat_ui", fake_chat_ui_module)

    fake_settings_ui_module = types.ModuleType("ui.settings_ui.window")
    fake_settings_ui_module.SettingsWindow = type("SettingsWindow", (), {})
    monkeypatch.setitem(sys.modules, "ui.settings_ui.window", fake_settings_ui_module)

    sys.modules.pop("core.runtime.chat_app", None)
    _snapshot = set(sys.modules)
    module = importlib.import_module("core.runtime.chat_app")
    try:
        yield module
    finally:
        sys.modules.pop("core.runtime.chat_app", None)
        # 清理 fake 期间重新加载的项目模块（chat_app import 链上被其他测试
        # 文件 pop 过的模块会在此用 fake PySide6 重建，残留会污染后续真实
        # Qt 测试，造成 Windows 堆损坏）。同步删除父包属性，避免
        # `from core.runtime import X` 命中残留对象。
        for _name in list(sys.modules):
            if _name not in _snapshot:
                _mod = sys.modules[_name]
                is_package = getattr(_mod, "__path__", None) is not None
                if not is_package:
                    # pydantic 内部模块不能 pop（理由同 test_signal_wiring）。
                    if _name.startswith("pydantic") or _name.startswith("pydantic_core"):
                        continue
                    sys.modules.pop(_name, None)
                    _parent, _, _short = _name.rpartition(".")
                    _parent_mod = sys.modules.get(_parent)
                    if _parent_mod is not None and hasattr(_parent_mod, _short):
                        try:
                            delattr(_parent_mod, _short)
                        except AttributeError:
                            pass


def make_api_config(
    *,
    llm_provider="OpenAI",
    llm_api_key=None,
    llm_base_url="https://api.example.test/v1",
    llm_model=None,
    tts_provider="gpt-sovits",
    gpt_sovits_url="http://127.0.0.1:9880",
):
    if llm_api_key is None:
        llm_api_key = {"OpenAI": "test-api-key"}
    if llm_model is None:
        llm_model = {"OpenAI": "gpt-test"}
    return SimpleNamespace(
        llm_provider=llm_provider,
        llm_api_key=llm_api_key,
        llm_base_url=llm_base_url,
        llm_model=llm_model,
        tts_provider=tts_provider,
        gpt_sovits_url=gpt_sovits_url,
    )


class FakeApp:
    def __init__(self, argv, calls=None, exec_result=0, exec_error=None):
        self.argv = argv
        self.calls = calls if calls is not None else []
        self.exec_result = exec_result
        self.exec_error = exec_error
        self.style_sheets = []

    def setStyleSheet(self, sheet):
        self.style_sheets.append(sheet)

    def exec(self):
        self.calls.append("app.exec")
        if self.exec_error is not None:
            raise self.exec_error
        return self.exec_result


class FakeWorkers:
    def __init__(self, calls, *, start_error=None, stop_error=None):
        self.calls = calls
        self.start_error = start_error
        self.stop_error = stop_error
        self.llm_worker = SimpleNamespace()
        self.ui_worker = SimpleNamespace()

    def start_all(self):
        self.calls.append("workers.start_all")
        if self.start_error is not None:
            raise self.start_error

    def stop_all(self):
        self.calls.append("workers.stop_all")
        if self.stop_error is not None:
            raise self.stop_error


class FakeWindow:
    def __init__(self, calls):
        self.calls = calls
        self.reply_status_calls = []
        self.config_notice_calls = []
        self.tts_connection_status_calls = []

    def show(self):
        self.calls.append("window.show")

    def set_reply_status(self, message, *, error=False):
        self.reply_status_calls.append((message, error))
        self.calls.append(("window.set_reply_status", message, error))

    def set_config_notice(self, message):
        self.config_notice_calls.append(message)
        self.calls.append(("window.set_config_notice", message))

    def configure_tts_connection_status(self, provider, server_url):
        self.tts_connection_status_calls.append((provider, server_url))
        self.calls.append(("window.configure_tts_connection_status", provider, server_url))


class FakeSettingsWindow:
    def __init__(self, calls):
        self.calls = calls

    def set_mcp_runtime_controller(self, controller):
        self.calls.append(("settings_window.set_mcp_runtime_controller", controller))

    def refresh_mcp_status(self, snapshot):
        self.calls.append(("settings_window.refresh_mcp_status", snapshot))

    def show(self):
        self.calls.append("settings_window.show")


class FakeSpriteController:
    def __init__(self, window, characters, sprite_map, calls):
        self.window = window
        self.characters = characters
        self.sprite_map = sprite_map
        self.calls = calls

    def show_default_sprite(self):
        self.calls.append("sprite_controller.show_default_sprite")


class FakeChatHistory:
    def __init__(self, calls, *, save_error=None):
        self.calls = calls
        self.save_error = save_error
        self.history = [{"role": "user", "content": "你好"}]
        self.characters = []

    def load(self):
        self.calls.append("chat_history.load")

    def save(self):
        self.calls.append("chat_history.save")
        if self.save_error is not None:
            raise self.save_error

    def get_history(self):
        self.calls.append("chat_history.get_history")
        return self.history


def install_build_fakes(monkeypatch, chat_app, *, app=None, start_error=None, stop_error=None, save_error=None, api_config=None):
    calls = []
    if api_config is None:
        api_config = make_api_config()
    config = SimpleNamespace(
        api_config=api_config,
        system_config=SimpleNamespace(ui_language="zh_CN"),
        characters=[SimpleNamespace(name="诺艾尔")],
    )
    llm_context = SimpleNamespace(
        manager=object(),
        active_character_name="诺艾尔",
        active_character_color="#ABCDEF",
    )
    tool_manager = ToolManager()
    tts_manager = object()
    t2i_manager = object()
    runtime_setup = SimpleNamespace(name="runtime_setup")
    runtime_setup.runtime = SimpleNamespace(tool_manager=None)
    workers = FakeWorkers(calls, start_error=start_error, stop_error=stop_error)
    window = FakeWindow(calls)
    settings_window = FakeSettingsWindow(calls)
    audio_player = SimpleNamespace(name="audio_player")
    signal_wiring_handles = SimpleNamespace(name="signal_wiring_handles")
    chat_history = FakeChatHistory(calls, save_error=save_error)
    sprite_map = {"0": "data/sprites/default/default.png"}

    if app is None:
        app = FakeApp([], calls=calls, exec_result=7)
    else:
        app.calls = calls

    class FakeQApplication:
        def __new__(cls, argv):
            calls.append(("QApplication", argv))
            app.argv = argv
            return app

    class FakeConfigManager:
        def __new__(cls):
            calls.append("ConfigManager")
            return config

    class FakeChatUIWindow:
        def __new__(cls):
            calls.append("ChatUIWindow")
            return window

    class FakeSettingsWindowFactory:
        def __new__(cls, _factory):
            calls.append("LazySettingsWindow")
            return settings_window

    class FakeAudioPlayer:
        def __new__(cls):
            calls.append("AudioPlayer")
            return audio_player

    def fake_init_i18n(language):
        calls.append(("init_i18n", language))

    def fake_create_llm_runtime_context(created_config):
        calls.append(("create_llm_runtime_context", created_config))
        return llm_context

    def fake_create_tts_manager(created_config):
        calls.append(("create_tts_manager", created_config))
        return tts_manager

    def fake_create_t2i_manager(created_config):
        calls.append(("create_t2i_manager", created_config))
        return t2i_manager

    def fake_create_runtime_setup(created_config, manager, created_tts_manager):
        calls.append(("create_runtime_setup", created_config, manager, created_tts_manager))
        return runtime_setup

    def fake_create_runtime_workers(created_runtime_setup, *, t2i_manager=None):
        calls.append(("create_runtime_workers", created_runtime_setup, t2i_manager))
        return workers

    def fake_restore_chat_history_to_window(created_window, history, *, default_char_color):
        calls.append(("restore_chat_history_to_window", created_window, history, default_char_color))

    def fake_build_sprite_map(created_characters, sprites_dir=Path("data/sprites/default"), character_index=0):
        calls.append(("build_sprite_map", created_characters, character_index))
        return sprite_map

    class FakeSpriteControllerFactory:
        def __new__(cls, created_window, created_characters, created_sprite_map):
            calls.append(("SpriteController", created_window, created_characters, created_sprite_map))
            return FakeSpriteController(created_window, created_characters, created_sprite_map, calls)

    def fake_wire_runtime_signals(**kwargs):
        calls.append(("wire_runtime_signals", kwargs))
        return signal_wiring_handles

    def fake_apply_llm_config_startup_notice(created_window, created_config):
        calls.append(("apply_llm_config_startup_notice", created_window, created_config))
        return startup_notices.apply_llm_config_startup_notice(created_window, created_config)

    def fake_apply_mcp_status_startup_notice(created_window, snapshot):
        calls.append(("apply_mcp_status_startup_notice", created_window, snapshot))
        return startup_notices.apply_mcp_status_startup_notice(created_window, snapshot)

    monkeypatch.setattr(chat_app, "QApplication", FakeQApplication)
    monkeypatch.setattr(chat_app, "prepare_application_identity", lambda app_id: calls.append(("prepare_application_identity", app_id)))
    monkeypatch.setattr(chat_app, "apply_application_icon", lambda app: calls.append(("apply_application_icon", app)))
    monkeypatch.setattr(chat_app, "ConfigManager", FakeConfigManager)
    monkeypatch.setattr(chat_app, "init_i18n", fake_init_i18n)
    monkeypatch.setattr(chat_app, "create_llm_runtime_context", fake_create_llm_runtime_context)
    monkeypatch.setattr(chat_app, "create_tts_manager", fake_create_tts_manager)
    monkeypatch.setattr(chat_app, "create_t2i_manager", fake_create_t2i_manager)
    monkeypatch.setattr(chat_app, "create_runtime_setup", fake_create_runtime_setup)
    monkeypatch.setattr(chat_app, "ToolManager", lambda: tool_manager)
    monkeypatch.setattr(chat_app, "create_runtime_workers", fake_create_runtime_workers)
    monkeypatch.setattr(chat_app, "restore_chat_history_to_window", fake_restore_chat_history_to_window)
    monkeypatch.setattr(chat_app, "build_sprite_map", fake_build_sprite_map)
    monkeypatch.setattr(chat_app, "SpriteController", FakeSpriteControllerFactory)
    monkeypatch.setattr(chat_app, "ChatUIWindow", FakeChatUIWindow)
    monkeypatch.setattr(chat_app, "LazySettingsWindow", FakeSettingsWindowFactory)
    monkeypatch.setattr(chat_app, "AudioPlayer", FakeAudioPlayer)
    monkeypatch.setattr(chat_app, "wire_runtime_signals", fake_wire_runtime_signals)
    monkeypatch.setattr(chat_app, "apply_llm_config_startup_notice", fake_apply_llm_config_startup_notice)
    monkeypatch.setattr(chat_app, "apply_mcp_status_startup_notice", fake_apply_mcp_status_startup_notice)
    monkeypatch.setattr(chat_app, "chat_history", chat_history)

    def fake_load_mcp_tools_into_tool_manager(created_config, manager):
        calls.append(("load_mcp_tools_into_tool_manager", created_config, manager))
        return SimpleNamespace(name="mcp_controller"), SimpleNamespace(state="disabled")

    monkeypatch.setattr(chat_app, "load_mcp_tools_into_tool_manager", fake_load_mcp_tools_into_tool_manager)

    return SimpleNamespace(
        calls=calls,
        app=app,
        config=config,
        llm_context=llm_context,
        tool_manager=tool_manager,
        tts_manager=tts_manager,
        t2i_manager=t2i_manager,
        runtime_setup=runtime_setup,
        workers=workers,
        window=window,
        settings_window=settings_window,
        audio_player=audio_player,
        signal_wiring_handles=signal_wiring_handles,
        chat_history=chat_history,
        sprite_map=sprite_map,
    )


def test_llm_config_startup_notice_complete_returns_empty():
    config = SimpleNamespace(api_config=make_api_config())
    assert startup_notices.llm_config_startup_notice(config) == ""


def test_llm_config_startup_notice_missing_fields_lists_labels_without_api_key_value():
    config = SimpleNamespace(
        api_config=make_api_config(
            llm_provider="Anthropic",
            llm_api_key={"Anthropic": "secret-value"},
            llm_base_url="",
            llm_model={"Anthropic": ""},
        )
    )
    message = startup_notices.llm_config_startup_notice(config)
    assert "API Key" not in message
    assert "Base URL" in message
    assert "模型 ID" in message
    assert "secret-value" not in message


def test_llm_config_startup_notice_trims_values():
    config = SimpleNamespace(
        api_config=make_api_config(
            llm_provider="  OpenAI  ",
            llm_api_key={"OpenAI": "  test-api-key  "},
            llm_base_url="  https://api.example.test/v1  ",
            llm_model={"OpenAI": "  gpt-test  "},
        )
    )
    assert startup_notices.llm_config_startup_notice(config) == ""


def test_llm_config_startup_notice_missing_api_config_returns_friendly_message():
    message = startup_notices.llm_config_startup_notice(SimpleNamespace())
    assert message == "LLM 配置不完整：API 配置。请先在设置中补全后再开始对话。"


def test_llm_config_startup_notice_empty_provider_lists_provider_key_and_model():
    config = SimpleNamespace(api_config=make_api_config(llm_provider=""))
    message = startup_notices.llm_config_startup_notice(config)
    assert message == "LLM 配置不完整：LLM 供应商、API Key、模型 ID。请先在设置中补全后再开始对话。"


def test_llm_config_startup_notice_missing_api_key_lists_label():
    config = SimpleNamespace(api_config=make_api_config(llm_api_key={"OpenAI": ""}))
    message = startup_notices.llm_config_startup_notice(config)
    assert message == "LLM 配置不完整：API Key。请先在设置中补全后再开始对话。"


def test_apply_llm_config_startup_notice_sets_config_notice_when_message_present():
    window = FakeWindow([])
    config = SimpleNamespace(api_config=make_api_config(llm_api_key={"OpenAI": ""}))
    message = startup_notices.apply_llm_config_startup_notice(window, config)
    assert message == "LLM 配置不完整：API Key。请先在设置中补全后再开始对话。"
    assert window.config_notice_calls == [message]


def test_apply_llm_config_startup_notice_skips_when_configuration_complete():
    window = FakeWindow([])
    config = SimpleNamespace(api_config=make_api_config())
    message = startup_notices.apply_llm_config_startup_notice(window, config)
    assert message == ""
    assert window.config_notice_calls == []


def test_mcp_status_startup_notice_returns_empty_for_disabled_snapshot():
    snapshot = SimpleNamespace(state="disabled", servers=[])
    assert startup_notices.mcp_status_startup_notice(snapshot) == ""


def test_mcp_status_startup_notice_reports_partial_state():
    snapshot = SimpleNamespace(
        state="partial",
        servers=[
            SimpleNamespace(state="ready", tool_count=2),
            SimpleNamespace(state="failed", tool_count=0),
        ],
    )
    message = startup_notices.mcp_status_startup_notice(snapshot)
    assert message == "MCP 部分可用：成功 1 个，失败 1 个。可在设置中查看详情。"


def test_apply_mcp_status_startup_notice_sets_reply_status_when_message_present():
    window = FakeWindow([])
    snapshot = SimpleNamespace(
        state="partial",
        servers=[
            SimpleNamespace(state="ready", tool_count=1),
            SimpleNamespace(state="failed", tool_count=0),
        ],
    )
    message = startup_notices.apply_mcp_status_startup_notice(window, snapshot)
    assert message == "MCP 部分可用：成功 1 个，失败 1 个。可在设置中查看详情。"
    assert window.reply_status_calls == [(message, True)]


def test_create_chat_windows_defers_settings_until_first_open(monkeypatch, chat_app_module):
    calls = []
    config = SimpleNamespace(api_config=make_api_config())
    window = FakeWindow(calls)
    settings_window = FakeSettingsWindow(calls)

    class FakeChatUIWindow:
        def __new__(cls):
            calls.append("ChatUIWindow")
            return window

    class FakeSettingsWindowFactory:
        def __new__(cls):
            calls.append("SettingsWindow")
            return settings_window

    def fake_apply_llm_config_startup_notice(created_window, created_config):
        calls.append(("apply_llm_config_startup_notice", created_window, created_config))
        return ""

    monkeypatch.setattr(chat_app_module, "ChatUIWindow", FakeChatUIWindow)
    monkeypatch.setattr(chat_app_module, "create_settings_window", FakeSettingsWindowFactory)
    monkeypatch.setattr(chat_app_module, "apply_llm_config_startup_notice", fake_apply_llm_config_startup_notice)

    created_window, created_settings_window = chat_app_module.create_chat_windows(config)

    assert created_window is window
    assert not created_settings_window.is_created
    assert calls == [
        "ChatUIWindow",
        ("apply_llm_config_startup_notice", window, config),
        (
            "window.configure_tts_connection_status",
            config.api_config.tts_provider,
            config.api_config.gpt_sovits_url,
        ),
    ]
    created_settings_window.show()
    assert created_settings_window.is_created
    assert calls[-2:] == ["SettingsWindow", "settings_window.show"]


def test_create_initial_chat_display_restores_history_and_builds_sprite_controller(monkeypatch, chat_app_module):
    calls = []
    window = FakeWindow(calls)
    characters = [SimpleNamespace(name="诺艾尔")]
    config = SimpleNamespace(characters=characters)
    llm_context = SimpleNamespace(active_character_color="#ABCDEF")
    history_store = FakeChatHistory(calls)
    sprite_map = {"诺艾尔": {"default": "noelle.png"}}

    def fake_restore_chat_history_to_window(created_window, history, *, default_char_color):
        calls.append(("restore_chat_history_to_window", created_window, history, default_char_color))

    def fake_build_sprite_map(created_characters, sprites_dir=Path("data/sprites/default"), character_index=0):
        calls.append(("build_sprite_map", created_characters, character_index))
        return sprite_map

    class FakeSpriteControllerFactory:
        def __new__(cls, created_window, created_characters, created_sprite_map):
            calls.append(("SpriteController", created_window, created_characters, created_sprite_map))
            return FakeSpriteController(created_window, created_characters, created_sprite_map, calls)

    monkeypatch.setattr(chat_app_module, "restore_chat_history_to_window", fake_restore_chat_history_to_window)
    monkeypatch.setattr(chat_app_module, "build_sprite_map", fake_build_sprite_map)
    monkeypatch.setattr(chat_app_module, "SpriteController", FakeSpriteControllerFactory)

    sprite_controller = chat_app_module.create_initial_chat_display(window, config, llm_context, history_store)

    assert sprite_controller.window is window
    assert sprite_controller.characters is characters
    assert sprite_controller.sprite_map is sprite_map
    assert calls == [
        "chat_history.get_history",
        ("restore_chat_history_to_window", window, history_store.history, "#ABCDEF"),
        ("build_sprite_map", characters, 0),
        ("SpriteController", window, characters, sprite_map),
        "sprite_controller.show_default_sprite",
    ]


def test_create_initial_chat_display_uses_restored_history_before_building_sprite_map(monkeypatch, chat_app_module):
    calls = []
    window = FakeWindow(calls)
    characters = [SimpleNamespace(name="诺艾尔")]
    config = SimpleNamespace(characters=characters)
    llm_context = SimpleNamespace(active_character_color="#123456")
    history_store = FakeChatHistory(calls)
    history_store.history = [{"role": "assistant", "content": "欢迎回来"}]
    sprite_map = {"诺艾尔": {"default": "noelle.png"}}

    def fake_restore_chat_history_to_window(created_window, history, *, default_char_color):
        calls.append(("restore_chat_history_to_window", created_window, history, default_char_color))

    def fake_build_sprite_map(created_characters, sprites_dir=Path("data/sprites/default"), character_index=0):
        calls.append(("build_sprite_map", created_characters, character_index))
        return sprite_map

    class FakeSpriteControllerFactory:
        def __new__(cls, created_window, created_characters, created_sprite_map):
            calls.append(("SpriteController", created_window, created_characters, created_sprite_map))
            return FakeSpriteController(created_window, created_characters, created_sprite_map, calls)

    monkeypatch.setattr(chat_app_module, "restore_chat_history_to_window", fake_restore_chat_history_to_window)
    monkeypatch.setattr(chat_app_module, "build_sprite_map", fake_build_sprite_map)
    monkeypatch.setattr(chat_app_module, "SpriteController", FakeSpriteControllerFactory)

    chat_app_module.create_initial_chat_display(window, config, llm_context, history_store)

    assert calls[0] == "chat_history.get_history"
    assert calls[1] == ("restore_chat_history_to_window", window, history_store.history, "#123456")
    assert calls[2] == ("build_sprite_map", characters, 0)
    assert calls[3] == ("SpriteController", window, characters, sprite_map)


def test_create_initial_chat_display_passes_selected_character_index_to_build_sprite_map(monkeypatch, chat_app_module):
    calls = []
    window = FakeWindow(calls)
    characters = [SimpleNamespace(name="小雪"), SimpleNamespace(name="新角色")]
    config = SimpleNamespace(characters=characters, current_character_index=1)
    llm_context = SimpleNamespace(active_character_color="#123456")
    history_store = FakeChatHistory(calls)
    history_store.history = [{"role": "assistant", "content": "欢迎回来"}]
    sprite_map = {"新角色": {"default": "new.png"}}

    def fake_restore_chat_history_to_window(created_window, history, *, default_char_color):
        calls.append(("restore_chat_history_to_window", created_window, history, default_char_color))

    def fake_build_sprite_map(created_characters, sprites_dir=Path("data/sprites/default"), character_index=0):
        calls.append(("build_sprite_map", created_characters, character_index))
        return sprite_map

    class FakeSpriteControllerFactory:
        def __new__(cls, created_window, created_characters, created_sprite_map):
            calls.append(("SpriteController", created_window, created_characters, created_sprite_map))
            return FakeSpriteController(created_window, created_characters, created_sprite_map, calls)

    monkeypatch.setattr(chat_app_module, "restore_chat_history_to_window", fake_restore_chat_history_to_window)
    monkeypatch.setattr(chat_app_module, "build_sprite_map", fake_build_sprite_map)
    monkeypatch.setattr(chat_app_module, "SpriteController", FakeSpriteControllerFactory)

    chat_app_module.create_initial_chat_display(window, config, llm_context, history_store)

    assert calls[0] == "chat_history.get_history"
    assert calls[1] == ("restore_chat_history_to_window", window, history_store.history, "#123456")
    assert calls[2] == ("build_sprite_map", characters, 1)
    assert calls[3] == ("SpriteController", window, characters, sprite_map)


def test_create_initial_chat_display_clamps_out_of_range_character_index_to_zero(monkeypatch, chat_app_module):
    calls = []
    window = FakeWindow(calls)
    characters = [SimpleNamespace(name="小雪"), SimpleNamespace(name="新角色")]
    config = SimpleNamespace(characters=characters, current_character_index=99)
    llm_context = SimpleNamespace(active_character_color="#FEDCBA")
    history_store = FakeChatHistory(calls)
    history_store.history = [{"role": "assistant", "content": "欢迎回来"}]
    sprite_map = {"小雪": {"default": "first.png"}}

    def fake_restore_chat_history_to_window(created_window, history, *, default_char_color):
        calls.append(("restore_chat_history_to_window", created_window, history, default_char_color))

    def fake_build_sprite_map(created_characters, sprites_dir=Path("data/sprites/default"), character_index=0):
        calls.append(("build_sprite_map", created_characters, character_index))
        return sprite_map

    class FakeSpriteControllerFactory:
        def __new__(cls, created_window, created_characters, created_sprite_map):
            calls.append(("SpriteController", created_window, created_characters, created_sprite_map))
            return FakeSpriteController(created_window, created_characters, created_sprite_map, calls)

    monkeypatch.setattr(chat_app_module, "restore_chat_history_to_window", fake_restore_chat_history_to_window)
    monkeypatch.setattr(chat_app_module, "build_sprite_map", fake_build_sprite_map)
    monkeypatch.setattr(chat_app_module, "SpriteController", FakeSpriteControllerFactory)

    chat_app_module.create_initial_chat_display(window, config, llm_context, history_store)

    assert calls[0] == "chat_history.get_history"
    assert calls[1] == ("restore_chat_history_to_window", window, history_store.history, "#FEDCBA")
    assert calls[2] == ("build_sprite_map", characters, 0)
    assert calls[3] == ("SpriteController", window, characters, sprite_map)


def test_create_initial_chat_display_clamps_negative_character_index_to_zero(monkeypatch, chat_app_module):
    calls = []
    window = FakeWindow(calls)
    characters = [SimpleNamespace(name="小雪"), SimpleNamespace(name="新角色")]
    config = SimpleNamespace(characters=characters, current_character_index=-3)
    llm_context = SimpleNamespace(active_character_color="#0F0F0F")
    history_store = FakeChatHistory(calls)
    history_store.history = [{"role": "assistant", "content": "欢迎回来"}]
    sprite_map = {"小雪": {"default": "first.png"}}

    def fake_restore_chat_history_to_window(created_window, history, *, default_char_color):
        calls.append(("restore_chat_history_to_window", created_window, history, default_char_color))

    def fake_build_sprite_map(created_characters, sprites_dir=Path("data/sprites/default"), character_index=0):
        calls.append(("build_sprite_map", created_characters, character_index))
        return sprite_map

    class FakeSpriteControllerFactory:
        def __new__(cls, created_window, created_characters, created_sprite_map):
            calls.append(("SpriteController", created_window, created_characters, created_sprite_map))
            return FakeSpriteController(created_window, created_characters, created_sprite_map, calls)

    monkeypatch.setattr(chat_app_module, "restore_chat_history_to_window", fake_restore_chat_history_to_window)
    monkeypatch.setattr(chat_app_module, "build_sprite_map", fake_build_sprite_map)
    monkeypatch.setattr(chat_app_module, "SpriteController", FakeSpriteControllerFactory)

    chat_app_module.create_initial_chat_display(window, config, llm_context, history_store)

    assert calls[0] == "chat_history.get_history"
    assert calls[1] == ("restore_chat_history_to_window", window, history_store.history, "#0F0F0F")
    assert calls[2] == ("build_sprite_map", characters, 0)
    assert calls[3] == ("SpriteController", window, characters, sprite_map)


def test_create_initial_chat_display_shows_default_sprite_after_building_controller(monkeypatch, chat_app_module):
    calls = []
    window = FakeWindow(calls)
    characters = [SimpleNamespace(name="诺艾尔")]
    config = SimpleNamespace(characters=characters)
    llm_context = SimpleNamespace(active_character_color="#ABCDEF")
    history_store = FakeChatHistory(calls)
    history_store.characters = [{
        "name": "诺艾尔",
        "emotion_tags": "0: legacy-zero",
        "sprites": [{"path": "legacy-first.png"}, {"path": "legacy-second.png"}],
        "emotion_items": [{"id": 2, "label": "happy", "sprite_path": "structured-happy.png"}],
    }]
    sprite_map = {"0": "data/sprites/default/default.png"}

    def fake_restore_chat_history_to_window(created_window, history, *, default_char_color):
        calls.append(("restore_chat_history_to_window", created_window, history, default_char_color))

    def fake_build_sprite_map(created_characters, sprites_dir=Path("data/sprites/default"), character_index=0):
        calls.append(("build_sprite_map", created_characters, character_index))
        return sprite_map

    class FakeSpriteControllerFactory:
        def __new__(cls, created_window, created_characters, created_sprite_map):
            calls.append(("SpriteController", created_window, created_characters, created_sprite_map))
            return FakeSpriteController(created_window, created_characters, created_sprite_map, calls)

    monkeypatch.setattr(chat_app_module, "restore_chat_history_to_window", fake_restore_chat_history_to_window)
    monkeypatch.setattr(chat_app_module, "build_sprite_map", fake_build_sprite_map)
    monkeypatch.setattr(chat_app_module, "SpriteController", FakeSpriteControllerFactory)

    sprite_controller = chat_app_module.create_initial_chat_display(window, config, llm_context, history_store)

    assert sprite_controller.window is window
    assert calls == [
        "chat_history.get_history",
        ("restore_chat_history_to_window", window, history_store.history, "#ABCDEF"),
        ("build_sprite_map", characters, 0),
        ("SpriteController", window, characters, sprite_map),
        "sprite_controller.show_default_sprite",
    ]
    assert history_store.characters[0]["emotion_tags"] == "0: legacy-zero"
    assert history_store.characters[0]["emotion_items"] == [{"id": 2, "label": "happy", "sprite_path": "structured-happy.png"}]


def test_create_initial_chat_display_uses_structured_default_without_legacy_sprites(monkeypatch, chat_app_module):
    calls = []
    window = FakeWindow(calls)
    characters = [SimpleNamespace(name="诺艾尔")]
    config = SimpleNamespace(characters=characters)
    llm_context = SimpleNamespace(active_character_color="#135790")
    history_store = FakeChatHistory(calls)
    history_store.history = [{"role": "assistant", "content": "欢迎回来"}]
    history_store.characters = [{
        "name": "诺艾尔",
        "emotion_tags": "0: legacy-zero",
        "sprites": [],
        "emotion_items": [{"id": 2, "label": "happy", "sprite_path": "structured-happy.png"}],
    }]
    sprite_map = {"0": "data/sprites/default/structured-happy.png"}

    def fake_restore_chat_history_to_window(created_window, history, *, default_char_color):
        calls.append(("restore_chat_history_to_window", created_window, history, default_char_color))

    def fake_build_sprite_map(created_characters, sprites_dir=Path("data/sprites/default"), character_index=0):
        calls.append(("build_sprite_map", created_characters, character_index))
        return sprite_map

    class FakeSpriteControllerFactory:
        def __new__(cls, created_window, created_characters, created_sprite_map):
            calls.append(("SpriteController", created_window, created_characters, created_sprite_map))
            return FakeSpriteController(created_window, created_characters, created_sprite_map, calls)

    monkeypatch.setattr(chat_app_module, "restore_chat_history_to_window", fake_restore_chat_history_to_window)
    monkeypatch.setattr(chat_app_module, "build_sprite_map", fake_build_sprite_map)
    monkeypatch.setattr(chat_app_module, "SpriteController", FakeSpriteControllerFactory)

    sprite_controller = chat_app_module.create_initial_chat_display(window, config, llm_context, history_store)

    assert sprite_controller.window is window
    assert calls == [
        "chat_history.get_history",
        ("restore_chat_history_to_window", window, history_store.history, "#135790"),
        ("build_sprite_map", characters, 0),
        ("SpriteController", window, characters, sprite_map),
        "sprite_controller.show_default_sprite",
    ]
    assert history_store.characters[0]["sprites"] == []
    assert history_store.characters[0]["emotion_items"] == [{"id": 2, "label": "happy", "sprite_path": "structured-happy.png"}]


def test_create_initial_chat_display_prefers_structured_default_over_legacy_zero_emotion_tags(monkeypatch, chat_app_module):
    calls = []
    window = FakeWindow(calls)
    characters = [SimpleNamespace(name="诺艾尔")]
    config = SimpleNamespace(characters=characters)
    llm_context = SimpleNamespace(active_character_color="#2468AC")
    history_store = FakeChatHistory(calls)
    history_store.history = [{"role": "assistant", "content": "欢迎回来"}]
    history_store.characters = [{
        "name": "诺艾尔",
        "emotion_tags": "0: legacy-zero\n2: legacy-happy",
        "sprites": [],
        "emotion_items": [{"id": 2, "label": "happy", "sprite_path": "structured-happy.png"}],
    }]
    sprite_map = {"0": "data/sprites/default/structured-happy.png"}

    def fake_restore_chat_history_to_window(created_window, history, *, default_char_color):
        calls.append(("restore_chat_history_to_window", created_window, history, default_char_color))

    def fake_build_sprite_map(created_characters, sprites_dir=Path("data/sprites/default"), character_index=0):
        calls.append(("build_sprite_map", created_characters, character_index))
        return sprite_map

    class FakeSpriteControllerFactory:
        def __new__(cls, created_window, created_characters, created_sprite_map):
            calls.append(("SpriteController", created_window, created_characters, created_sprite_map))
            return FakeSpriteController(created_window, created_characters, created_sprite_map, calls)

    monkeypatch.setattr(chat_app_module, "restore_chat_history_to_window", fake_restore_chat_history_to_window)
    monkeypatch.setattr(chat_app_module, "build_sprite_map", fake_build_sprite_map)
    monkeypatch.setattr(chat_app_module, "SpriteController", FakeSpriteControllerFactory)

    sprite_controller = chat_app_module.create_initial_chat_display(window, config, llm_context, history_store)

    assert sprite_controller.window is window
    assert calls == [
        "chat_history.get_history",
        ("restore_chat_history_to_window", window, history_store.history, "#2468AC"),
        ("build_sprite_map", characters, 0),
        ("SpriteController", window, characters, sprite_map),
        "sprite_controller.show_default_sprite",
    ]
    assert history_store.characters[0]["emotion_tags"] == "0: legacy-zero\n2: legacy-happy"
    assert history_store.characters[0]["emotion_items"] == [{"id": 2, "label": "happy", "sprite_path": "structured-happy.png"}]


def test_create_initial_chat_display_preserves_legacy_text_while_runtime_uses_structured_default(monkeypatch, chat_app_module):
    calls = []
    window = FakeWindow(calls)
    characters = [SimpleNamespace(name="结构化角色")]
    config = SimpleNamespace(characters=characters)
    llm_context = SimpleNamespace(active_character_color="#5A5A5A")
    history_store = FakeChatHistory(calls)
    history_store.history = [{"role": "assistant", "content": "欢迎回来"}]
    history_store.characters = [{
        "name": "结构化角色",
        "color": "#87CEEB",
        "character_setting": "结构化保存与 runtime 默认图应保持一致。",
        "emotion_tags": "0: legacy-zero\n2: legacy-happy",
        "sprites": [],
        "emotion_items": [{"id": 2, "label": "happy", "sprite_path": "structured-happy.png"}],
    }]
    sprite_map = {"0": "data/sprites/default/structured-happy.png"}

    def fake_restore_chat_history_to_window(created_window, history, *, default_char_color):
        calls.append(("restore_chat_history_to_window", created_window, history, default_char_color))

    def fake_build_sprite_map(created_characters, sprites_dir=Path("data/sprites/default"), character_index=0):
        calls.append(("build_sprite_map", created_characters, character_index))
        return sprite_map

    class FakeSpriteControllerFactory:
        def __new__(cls, created_window, created_characters, created_sprite_map):
            calls.append(("SpriteController", created_window, created_characters, created_sprite_map))
            return FakeSpriteController(created_window, created_characters, created_sprite_map, calls)

    monkeypatch.setattr(chat_app_module, "restore_chat_history_to_window", fake_restore_chat_history_to_window)
    monkeypatch.setattr(chat_app_module, "build_sprite_map", fake_build_sprite_map)
    monkeypatch.setattr(chat_app_module, "SpriteController", FakeSpriteControllerFactory)

    sprite_controller = chat_app_module.create_initial_chat_display(window, config, llm_context, history_store)

    assert sprite_controller.window is window
    assert calls == [
        "chat_history.get_history",
        ("restore_chat_history_to_window", window, history_store.history, "#5A5A5A"),
        ("build_sprite_map", characters, 0),
        ("SpriteController", window, characters, sprite_map),
        "sprite_controller.show_default_sprite",
    ]
    assert history_store.characters[0]["emotion_tags"] == "0: legacy-zero\n2: legacy-happy"
    assert history_store.characters[0]["emotion_items"] == [{"id": 2, "label": "happy", "sprite_path": "structured-happy.png"}]


def test_create_core_runtime_components_creates_components_in_order(monkeypatch, chat_app_module):
    calls = []
    config = SimpleNamespace(name="config", api_config=SimpleNamespace(web_search_enabled=False))
    project_root = chat_app_module.PROJECT_ROOT
    allowed_roots = [project_root, project_root.parent]
    llm_manager = object()
    llm_context = SimpleNamespace(manager=llm_manager)
    tool_manager = ToolManager()
    tts_manager = object()
    t2i_manager = object()
    runtime_setup = SimpleNamespace(name="runtime_setup")
    runtime_setup.runtime = SimpleNamespace(tool_manager=None)

    def fake_create_llm_runtime_context(created_config):
        calls.append(("create_llm_runtime_context", created_config))
        return llm_context

    def fake_create_tts_manager(created_config):
        calls.append(("create_tts_manager", created_config))
        return tts_manager

    def fake_create_t2i_manager(created_config):
        calls.append(("create_t2i_manager", created_config))
        return t2i_manager

    def fake_create_runtime_setup(created_config, manager, created_tts_manager):
        calls.append(("create_runtime_setup", created_config, manager, created_tts_manager))
        return runtime_setup

    def fake_load_mcp_tools_into_tool_manager(created_config, manager):
        calls.append(("load_mcp_tools_into_tool_manager", created_config, manager))
        return SimpleNamespace(name="mcp_controller"), SimpleNamespace(state="disabled")

    monkeypatch.setattr(chat_app_module, "create_llm_runtime_context", fake_create_llm_runtime_context)
    monkeypatch.setattr(chat_app_module, "create_tts_manager", fake_create_tts_manager)
    monkeypatch.setattr(chat_app_module, "create_t2i_manager", fake_create_t2i_manager)
    monkeypatch.setattr(chat_app_module, "create_runtime_setup", fake_create_runtime_setup)
    monkeypatch.setattr(chat_app_module, "load_mcp_tools_into_tool_manager", fake_load_mcp_tools_into_tool_manager)
    monkeypatch.setattr(chat_app_module, "ToolManager", lambda: tool_manager)
    monkeypatch.setattr(
        chat_app_module,
        "load_allowed_roots",
        lambda: allowed_roots,
    )
    monkeypatch.setattr(
        chat_app_module,
        "register_builtin_tools",
        lambda manager, *, allowed_roots: calls.append(("register_builtin_tools", manager, allowed_roots)),
    )
    monkeypatch.setattr(
        chat_app_module,
        "register_configured_web_tools",
        lambda manager, api_config: calls.append(("register_configured_web_tools", manager, api_config)),
    )

    components = chat_app_module.create_core_runtime_components(config)

    assert components.llm_context is llm_context
    assert components.tts_manager is tts_manager
    assert components.t2i_manager is t2i_manager
    assert components.runtime_setup is runtime_setup
    assert runtime_setup.runtime.tool_manager is tool_manager
    assert calls == [
        ("create_llm_runtime_context", config),
        ("register_builtin_tools", tool_manager, allowed_roots),
        ("register_configured_web_tools", tool_manager, config.api_config),
        ("create_tts_manager", config),
        ("create_t2i_manager", config),
        ("create_runtime_setup", config, llm_manager, tts_manager),
        ("load_mcp_tools_into_tool_manager", config, tool_manager),
    ]


def test_load_mcp_tools_into_tool_manager_skips_cleanly_when_config_missing(monkeypatch, chat_app_module):
    config = SimpleNamespace(_MCP_CONFIG_PATH="data/config/mcp.yaml")
    manager = object()
    controller = SimpleNamespace(register_into_tool_manager=lambda created_manager: SimpleNamespace(state="disabled"))
    monkeypatch.setattr(chat_app_module, "MCPRuntimeController", lambda config_path: controller)
    created_controller, snapshot = chat_app_module.load_mcp_tools_into_tool_manager(config, manager)
    assert created_controller is controller
    assert snapshot.state == "disabled"


def test_load_mcp_tools_into_tool_manager_registers_snapshot_from_controller(monkeypatch, chat_app_module):
    config = SimpleNamespace(_MCP_CONFIG_PATH="data/config/mcp.yaml")
    manager = object()
    calls = []

    class FakeController:
        def __init__(self, config_path):
            calls.append(("controller", config_path))

        def register_into_tool_manager(self, created_manager):
            calls.append(("register_into_tool_manager", created_manager))
            return SimpleNamespace(state="partial")

    monkeypatch.setattr(chat_app_module, "MCPRuntimeController", FakeController)
    controller, snapshot = chat_app_module.load_mcp_tools_into_tool_manager(config, manager)
    assert calls == [("controller", "data/config/mcp.yaml"), ("register_into_tool_manager", manager)]
    assert snapshot.state == "partial"
    assert isinstance(controller, FakeController)


def test_load_mcp_tools_into_tool_manager_propagates_controller_instance(monkeypatch, chat_app_module):
    config = SimpleNamespace(_MCP_CONFIG_PATH="data/config/mcp.yaml")
    manager = object()
    controller = SimpleNamespace(register_into_tool_manager=lambda created_manager: SimpleNamespace(state="ready"))
    monkeypatch.setattr(chat_app_module, "MCPRuntimeController", lambda config_path: controller)
    created_controller, snapshot = chat_app_module.load_mcp_tools_into_tool_manager(config, manager)
    assert created_controller is controller
    assert snapshot.state == "ready"


def test_create_runtime_workers_after_history_load_loads_history_before_workers_and_returns_workers(monkeypatch, chat_app_module):
    calls = []
    runtime_setup = SimpleNamespace(name="runtime_setup")
    t2i_manager = object()
    workers = SimpleNamespace(name="workers")
    history_store = FakeChatHistory(calls)

    def fake_create_runtime_workers(created_runtime_setup, *, t2i_manager=None):
        calls.append(("create_runtime_workers", created_runtime_setup, t2i_manager))
        return workers

    monkeypatch.setattr(chat_app_module, "create_runtime_workers", fake_create_runtime_workers)
    created_workers = chat_app_module.create_runtime_workers_after_history_load(runtime_setup, t2i_manager, history_store)
    assert created_workers is workers
    assert calls == ["chat_history.load", ("create_runtime_workers", runtime_setup, t2i_manager)]


def test_build_chat_app_assembles_runtime_and_keeps_lifecycle_handles(monkeypatch, chat_app_module):
    fakes = install_build_fakes(monkeypatch, chat_app_module)
    handles = chat_app_module.build_chat_app(["galgame_agent", "--debug"])
    assert handles.app is fakes.app
    assert handles.config is fakes.config
    assert handles.llm_context is fakes.llm_context
    assert handles.tts_manager is fakes.tts_manager
    assert handles.t2i_manager is fakes.t2i_manager
    assert handles.runtime_setup is fakes.runtime_setup
    assert handles.workers is fakes.workers
    assert handles.window is fakes.window
    assert handles.settings_window is fakes.settings_window
    assert handles.audio_player is fakes.audio_player
    assert handles.signal_wiring_handles is fakes.signal_wiring_handles
    assert handles.sprite_controller.window is fakes.window
    assert handles.chat_history is fakes.chat_history
    assert handles.mcp_controller == SimpleNamespace(name="mcp_controller")
    assert fakes.calls == [
        ("prepare_application_identity", "Yayu.Chat"),
        ("QApplication", ["galgame_agent", "--debug"]),
        ("apply_application_icon", fakes.app),
        "ConfigManager",
        ("init_i18n", "zh_CN"),
        ("create_llm_runtime_context", fakes.config),
        ("create_tts_manager", fakes.config),
        ("create_t2i_manager", fakes.config),
        ("create_runtime_setup", fakes.config, fakes.llm_context.manager, fakes.tts_manager),
        ("load_mcp_tools_into_tool_manager", fakes.config, fakes.tool_manager),
        "chat_history.load",
        ("create_runtime_workers", fakes.runtime_setup, fakes.t2i_manager),
        "ChatUIWindow",
        ("apply_llm_config_startup_notice", fakes.window, fakes.config),
        (
            "window.configure_tts_connection_status",
            fakes.config.api_config.tts_provider,
            fakes.config.api_config.gpt_sovits_url,
        ),
        "LazySettingsWindow",
        ("apply_mcp_status_startup_notice", fakes.window, SimpleNamespace(state="disabled")),
        ("settings_window.set_mcp_runtime_controller", SimpleNamespace(name="mcp_controller")),
        ("settings_window.refresh_mcp_status", SimpleNamespace(state="disabled")),
        "chat_history.get_history",
        ("restore_chat_history_to_window", fakes.window, fakes.chat_history.history, "#ABCDEF"),
        ("build_sprite_map", fakes.config.characters, 0),
        ("SpriteController", fakes.window, fakes.config.characters, fakes.sprite_map),
        "sprite_controller.show_default_sprite",
        "AudioPlayer",
        ("wire_runtime_signals", {
            "window": fakes.window,
            "workers": fakes.workers,
            "runtime_setup": fakes.runtime_setup,
            "llm_context": fakes.llm_context,
            "chat_history": fakes.chat_history,
            "config": fakes.config,
            "sprite_controller": handles.sprite_controller,
            "audio_player": fakes.audio_player,
            "settings_window": fakes.settings_window,
        }),
    ]


def test_build_chat_app_missing_llm_config_sets_config_notice_error(monkeypatch, chat_app_module):
    api_config = make_api_config(llm_api_key={"OpenAI": ""}, llm_base_url="", llm_model={"OpenAI": ""})
    fakes = install_build_fakes(monkeypatch, chat_app_module, api_config=api_config)
    chat_app_module.build_chat_app(["galgame_agent"])
    assert fakes.window.config_notice_calls == ["LLM 配置不完整：API Key、Base URL、模型 ID。请先在设置中补全后再开始对话。"]


def test_build_chat_app_complete_llm_config_does_not_set_config_notice(monkeypatch, chat_app_module):
    fakes = install_build_fakes(monkeypatch, chat_app_module)
    chat_app_module.build_chat_app(["galgame_agent"])
    assert fakes.window.config_notice_calls == []


def test_build_chat_app_partial_mcp_sets_reply_status_notice(monkeypatch, chat_app_module):
    fakes = install_build_fakes(monkeypatch, chat_app_module)

    def fake_load_mcp_tools_into_tool_manager(created_config, manager):
        fakes.calls.append(("load_mcp_tools_into_tool_manager", created_config, manager))
        return SimpleNamespace(name="mcp_controller"), SimpleNamespace(
            state="partial",
            servers=[SimpleNamespace(state="ready", tool_count=2), SimpleNamespace(state="failed", tool_count=0)],
        )

    monkeypatch.setattr(chat_app_module, "load_mcp_tools_into_tool_manager", fake_load_mcp_tools_into_tool_manager)
    chat_app_module.build_chat_app(["galgame_agent"])
    assert fakes.window.reply_status_calls == [("MCP 部分可用：成功 1 个，失败 1 个。可在设置中查看详情。", True)]


def test_run_chat_app_delegates_to_runtime_event_loop_after_successful_build(monkeypatch, chat_app_module):
    handles = SimpleNamespace(name="handles")
    calls = []

    def fake_build_chat_app(argv):
        calls.append(("build_chat_app", argv))
        return handles

    def fake_run_runtime_event_loop(created_handles):
        calls.append(("run_runtime_event_loop", created_handles))
        return 7

    monkeypatch.setattr(chat_app_module, "build_chat_app", fake_build_chat_app)
    monkeypatch.setattr(chat_app_module, "run_runtime_event_loop", fake_run_runtime_event_loop)
    result = chat_app_module.run_chat_app(["galgame_agent"])
    assert result == 7
    assert calls == [("build_chat_app", ["galgame_agent"]), ("run_runtime_event_loop", handles)]


def test_run_chat_app_clears_runtime_when_build_chat_app_raises(monkeypatch, chat_app_module):
    calls = []

    def fake_build_chat_app(argv):
        calls.append("build_chat_app")
        raise RuntimeError("build failed")

    def fake_clear_app_runtime():
        calls.append("clear_app_runtime")

    def fake_run_runtime_event_loop(handles):
        calls.append("run_runtime_event_loop")

    monkeypatch.setattr(chat_app_module, "build_chat_app", fake_build_chat_app)
    monkeypatch.setattr(chat_app_module, "clear_app_runtime", fake_clear_app_runtime)
    monkeypatch.setattr(chat_app_module, "run_runtime_event_loop", fake_run_runtime_event_loop)

    with pytest.raises(RuntimeError, match="build failed"):
        chat_app_module.run_chat_app(["galgame_agent"])

    assert calls == ["build_chat_app", "clear_app_runtime"]
