from dataclasses import fields, is_dataclass
from types import SimpleNamespace


class FakeApp:
    def __init__(self, argv):
        self.argv = argv
        self.exec_called = 0
        self.style_sheets = []

    def setStyleSheet(self, sheet):
        self.style_sheets.append(sheet)

    def exec(self):
        self.exec_called += 1
        return 37


class FakeWindow:
    def __init__(self):
        self.show_called = 0

    def show(self):
        self.show_called += 1


def test_settings_app_handles_exposes_lifetime_objects():
    from core.runtime.settings_app import SettingsAppHandles

    assert is_dataclass(SettingsAppHandles)
    assert {field.name for field in fields(SettingsAppHandles)} >= {
        "app",
        "config",
        "window",
    }


def test_build_settings_app_creates_handles_without_showing_or_execing(monkeypatch):
    from core.runtime import settings_app

    created_apps = []
    created_configs = []
    created_windows = []
    languages = []
    identity_calls = []

    class FakeQApplication(FakeApp):
        def __init__(self, argv):
            super().__init__(argv)
            created_apps.append(self)
            identity_calls.append(("QApplication", self))

    class FakeConfig:
        def __init__(self):
            self.system_config = SimpleNamespace(ui_language="zh_CN")
            created_configs.append(self)

    class FakeSettingsWindow(FakeWindow):
        def __init__(self):
            super().__init__()
            created_windows.append(self)

    monkeypatch.setattr(settings_app, "QApplication", FakeQApplication)
    monkeypatch.setattr(settings_app, "ConfigManager", FakeConfig)
    monkeypatch.setattr(settings_app, "init_i18n", lambda language: languages.append(language))
    monkeypatch.setattr(settings_app, "SettingsWindow", FakeSettingsWindow)
    monkeypatch.setattr(settings_app, "prepare_application_identity", lambda app_id: identity_calls.append(("prepare_application_identity", app_id)))
    monkeypatch.setattr(settings_app, "apply_application_icon", lambda app: identity_calls.append(("apply_application_icon", app)))

    handles = settings_app.build_settings_app(("webui_qt.py", "--sample"))

    assert len(created_apps) == 1
    assert len(created_configs) == 1
    assert len(created_windows) == 1
    assert handles.app is created_apps[0]
    assert handles.config is created_configs[0]
    assert handles.config.system_config.ui_language == "zh_CN"
    assert handles.window is created_windows[0]
    assert handles.app.argv == ["webui_qt.py", "--sample"]
    assert handles.app.exec_called == 0
    assert handles.window.show_called == 0
    assert languages == ["zh_CN"]
    assert identity_calls == [
        ("prepare_application_identity", "Yayu.Settings"),
        ("QApplication", handles.app),
        ("apply_application_icon", handles.app),
    ]


def test_run_settings_app_shows_window_and_returns_exec_code(monkeypatch):
    from core.runtime import settings_app

    fake_app = FakeApp(["webui_qt.py"])
    fake_window = FakeWindow()
    captured_argv = []

    def fake_build_settings_app(argv=None):
        captured_argv.append(argv)
        return settings_app.SettingsAppHandles(
            app=fake_app,
            config=SimpleNamespace(system_config=SimpleNamespace(ui_language="zh_CN")),
            window=fake_window,
        )

    monkeypatch.setattr(settings_app, "build_settings_app", fake_build_settings_app)

    assert settings_app.run_settings_app(["webui_qt.py"]) == 37
    assert captured_argv == [["webui_qt.py"]]
    assert fake_window.show_called == 1
    assert fake_app.exec_called == 1


def test_webui_qt_main_delegates_to_run_settings_app(monkeypatch):
    import webui_qt

    captured_argv = []
    monkeypatch.setattr(webui_qt.sys, "argv", ["webui_qt.py", "--flag"])

    def fake_run_settings_app(argv):
        captured_argv.append(argv)
        return 23

    monkeypatch.setattr(webui_qt, "run_settings_app", fake_run_settings_app)

    assert webui_qt.main() == 23
    assert captured_argv == [["webui_qt.py", "--flag"]]
