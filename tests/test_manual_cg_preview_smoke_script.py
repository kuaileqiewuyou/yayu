import importlib.util
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "manual_cg_preview_smoke.py"


def _load_script_module():
    spec = importlib.util.spec_from_file_location("manual_cg_preview_smoke", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class _FakeApp:
    def __init__(self, args):
        self.args = args
        self.exec_called = False

    def exec(self):
        self.exec_called = True
        return 23


class _FakeWindow:
    instances = []

    def __init__(self):
        self.calls = []
        _FakeWindow.instances.append(self)

    def add_message(self, *args, **kwargs):
        self.calls.append(("add_message", args, kwargs))

    def set_reply_status(self, *args, **kwargs):
        self.calls.append(("set_reply_status", args, kwargs))

    def add_cg_preview(self, *args, **kwargs):
        self.calls.append(("add_cg_preview", args, kwargs))
        return True

    def show(self):
        self.calls.append(("show", (), {}))


def test_manual_cg_preview_smoke_script_exists():
    assert SCRIPT_PATH.exists()


def test_main_writes_png_under_project_root_and_drives_chat_ui_window(monkeypatch, tmp_path):
    module = _load_script_module()
    fake_apps = []

    def fake_app_factory(args):
        app = _FakeApp(args)
        fake_apps.append(app)
        return app

    _FakeWindow.instances.clear()
    cwd_path = tmp_path / "cwd"
    cwd_path.mkdir()
    project_root = tmp_path / "project"
    monkeypatch.chdir(cwd_path)
    monkeypatch.setattr(module, "PROJECT_ROOT", project_root)
    monkeypatch.setattr(module, "QApplication", fake_app_factory)
    monkeypatch.setattr(module, "ChatUIWindow", _FakeWindow)

    result = module.main()

    assert result == 23
    assert fake_apps and fake_apps[0].exec_called is True
    assert _FakeWindow.instances
    window = _FakeWindow.instances[0]

    image_path = project_root / "data" / "cg" / "generated" / "manual-preview-smoke.png"
    wrong_cwd_path = cwd_path / "data" / "cg" / "generated" / "manual-preview-smoke.png"
    assert image_path.exists()
    assert not wrong_cwd_path.exists()
    assert image_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")

    assert window.calls == [
        (
            "add_message",
            ("[CG] 手动预览验收：夕阳下的教室",),
            {"is_user": False, "char_name": "系统"},
        ),
        ("set_reply_status", (f"CG 生成完成：{image_path.resolve()}",), {}),
        ("add_cg_preview", (str(image_path.resolve()),), {}),
        ("show", (), {}),
    ]
