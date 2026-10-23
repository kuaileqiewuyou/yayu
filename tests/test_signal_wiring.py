import sys
import types
from types import SimpleNamespace

pyside6_module = types.ModuleType("PySide6")
qtcore_module = types.ModuleType("PySide6.QtCore")
qtgui_module = types.ModuleType("PySide6.QtGui")
qtwidgets_module = types.ModuleType("PySide6.QtWidgets")
qtmultimedia_module = types.ModuleType("PySide6.QtMultimedia")


class _FakeQtSignal:
    def __init__(self, *args, **kwargs):
        self._slots = []

    def connect(self, slot):
        self._slots.append(slot)

    def emit(self, *args, **kwargs):
        for slot in list(self._slots):
            slot(*args, **kwargs)


class _FakeQObject:
    def __init__(self, *args, **kwargs):
        pass


class _FakeQUrl:
    def __init__(self, path: str = ""):
        self.path = path

    @classmethod
    def fromLocalFile(cls, path: str):
        return cls(path)


class _FakeQt:
    UserRole = 0


class _FakeMediaPlayer:
    def __init__(self, *args, **kwargs):
        self.audio_output = None
        self.source = None
        self.play_called = False

    def setAudioOutput(self, audio_output):
        self.audio_output = audio_output

    def setSource(self, source):
        self.source = source

    def play(self):
        self.play_called = True


class _FakeAudioOutput:
    def __init__(self, *args, **kwargs):
        self.volume = None

    def setVolume(self, value):
        self.volume = value


class _FakeWidget:
    def __init__(self, *args, **kwargs):
        pass


qtcore_module.Signal = _FakeQtSignal
qtcore_module.QObject = _FakeQObject
qtcore_module.QUrl = _FakeQUrl
qtcore_module.Qt = _FakeQt
# ui.window_chrome（frameless title bar）依赖的 QtCore 符号
qtcore_module.QEvent = _FakeWidget
qtcore_module.QPoint = _FakeWidget
qtcore_module.QRect = _FakeWidget
qtmultimedia_module.QMediaPlayer = _FakeMediaPlayer
qtmultimedia_module.QAudioOutput = _FakeAudioOutput

qtwidgets_module.QDialog = _FakeWidget
qtwidgets_module.QVBoxLayout = _FakeWidget
qtwidgets_module.QListWidget = _FakeWidget
qtwidgets_module.QListWidgetItem = _FakeWidget
qtwidgets_module.QPushButton = _FakeWidget
qtwidgets_module.QMessageBox = _FakeWidget
qtwidgets_module.QFrame = _FakeWidget
qtwidgets_module.QHBoxLayout = _FakeWidget
qtwidgets_module.QLabel = _FakeWidget
qtwidgets_module.QWidget = _FakeWidget

_ORIGINAL_PYSIDE6 = {
    name: sys.modules.get(name)
    for name in (
        "PySide6",
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
        "PySide6.QtMultimedia",
    )
}
_SYS_MODULES_SNAPSHOT = set(sys.modules)

sys.modules["PySide6"] = pyside6_module
sys.modules["PySide6.QtCore"] = qtcore_module
sys.modules["PySide6.QtGui"] = qtgui_module
sys.modules["PySide6.QtWidgets"] = qtwidgets_module
sys.modules["PySide6.QtMultimedia"] = qtmultimedia_module

from core.runtime.signal_wiring import wire_runtime_signals, wire_t2i_worker_signals
from core.runtime.tool_summary import ToolInvocationRecord, ToolLoopTurnResult, ToolTurnSummary

# 缓存 fake 期间构建的模块引用：sys.modules 条目会在下面被清理（避免污染
# 后续测试文件），但本文件的测试仍通过该引用使用 fake 版类。
_SIGNAL_WIRING_MODULE = sys.modules["core.runtime.signal_wiring"]

for _name, _module in _ORIGINAL_PYSIDE6.items():
    if _module is None:
        sys.modules.pop(_name, None)
    else:
        sys.modules[_name] = _module

# 清理 fake 期间新增的项目模块（如用 fake 基类构建的 ui.window_chrome）：
# 否则残留的 fake 版类会让后续测试文件（如 test_settings_window）与真实 Qt
# 交互时 TypeError。core.runtime.signal_wiring 保留：它被 pop 后，后续文件
# import chat_actions → window_action_wiring 时会触发它顶层重载（fake 再次
# 替换 sys.modules，产品代码存在循环 import），造成二次污染。
for _name in list(sys.modules):
    _mod = sys.modules[_name]
    is_package = getattr(_mod, "__path__", None) is not None
    if _name not in _SYS_MODULES_SNAPSHOT and _name != "core.runtime.signal_wiring" and not is_package:
        # pydantic 内部模块不能 pop：重新加载会创建新的描述符/类型类，破坏
        # 既有模型（如 config.schema.Character）的 private attributes 收集，
        # 导致 model_validate 时 RecursionError。
        if _name.startswith("pydantic") or _name.startswith("pydantic_core"):
            continue
        sys.modules.pop(_name, None)
        # import 系统会在父包上设置子模块属性（如 core.runtime.chat_actions）；
        # 只 pop sys.modules 无法清除该引用，后续 `from core.runtime import X`
        # 仍会命中残留的 fake 版对象。这里同步删除父包属性。
        _parent, _, _short = _name.rpartition(".")
        _parent_mod = sys.modules.get(_parent)
        if _parent_mod is not None and hasattr(_parent_mod, _short):
            try:
                delattr(_parent_mod, _short)
            except AttributeError:
                pass


class FakeSignal:
    def __init__(self):
        self.slots = []

    def connect(self, slot):
        self.slots.append(slot)

    def emit(self, *args, **kwargs):
        for slot in list(self.slots):
            slot(*args, **kwargs)


class FakeLLMWorker:
    def __init__(self):
        self.status_changed = FakeSignal()
        self.stream_start = FakeSignal()
        self.stream_chunk = FakeSignal()
        self.dialog_parsed = FakeSignal()
        self.tool_summary_ready = FakeSignal()
        self.stream_end = FakeSignal()
        self.error = FakeSignal()


class FakeUIWorker:
    def __init__(self):
        self.update_dialog = FakeSignal()
        self.update_narration = FakeSignal()
        self.update_options = FakeSignal()
        self.update_scene = FakeSignal()
        self.update_bgm = FakeSignal()
        self.update_cg = FakeSignal()
        self.update_stat = FakeSignal()
        self.update_cot = FakeSignal()


class FakeT2IWorker:
    def __init__(self):
        self.image_generated = FakeSignal()
        self.generation_failed = FakeSignal()


class FakeWindow:
    def __init__(self):
        self.user_message_sent = FakeSignal()
        self.clear_requested = FakeSignal()
        self.reroll_requested = FakeSignal()
        self.settings_requested = FakeSignal()
        self.reply_statuses = []
        self.messages = []
        self.cg_previews = []
        self.tool_summaries = []

    def add_message(self, text, is_user=False, char_name="", char_color="#f2a0bd"):
        self.messages.append((text, is_user, char_name, char_color))

    def add_cg_preview(self, image_path):
        self.cg_previews.append(image_path)
        return True

    def set_reply_status(self, text, error=False):
        self.reply_statuses.append((text, error))

    def set_tool_summary_result(self, result):
        self.tool_summaries.append(result)


class FakeAudioPlayer:
    def __init__(self):
        self.played = []

    def play(self, path):
        self.played.append(path)


class FakeSettingsWindow:
    def __init__(self):
        self.calls = []

    def show(self):
        self.calls.append("show")

    def raise_(self):
        self.calls.append("raise_")

    def activateWindow(self):
        self.calls.append("activateWindow")


def assert_bound_to(slot, obj, method_name):
    assert getattr(slot, "__self__", None) is obj
    assert getattr(slot, "__func__", None) is getattr(type(obj), method_name)


def make_runtime_parts():
    llm_worker = FakeLLMWorker()
    ui_worker = FakeUIWorker()
    workers = SimpleNamespace(llm_worker=llm_worker, ui_worker=ui_worker, t2i_worker=None)
    runtime_setup = SimpleNamespace(
        user_input_queue=object(),
        t2i_prompt_queue=SimpleNamespace(put=lambda prompt: None),
    )
    llm_context = SimpleNamespace(
        active_character_name="诺艾尔",
        active_character_color="#ABCDEF",
    )
    sprite_controller = SimpleNamespace(set_sprite_by_id=lambda asset_id: None)
    config = SimpleNamespace(backgrounds=[])
    history = object()
    audio_player = FakeAudioPlayer()
    window = FakeWindow()
    return SimpleNamespace(
        window=window,
        workers=workers,
        runtime_setup=runtime_setup,
        llm_context=llm_context,
        history=history,
        config=config,
        sprite_controller=sprite_controller,
        audio_player=audio_player,
    )


def _tool_result(records: list[ToolInvocationRecord]) -> ToolLoopTurnResult:
    return ToolLoopTurnResult(
        final_output="done",
        invocation_records=records,
        summary=ToolTurnSummary.from_records(records),
    )


def test_wire_runtime_signals_connects_llm_and_ui_worker_handlers_without_stream_chunk():
    parts = make_runtime_parts()

    handles = wire_runtime_signals(
        window=parts.window,
        workers=parts.workers,
        runtime_setup=parts.runtime_setup,
        llm_context=parts.llm_context,
        chat_history=parts.history,
        config=parts.config,
        sprite_controller=parts.sprite_controller,
        audio_player=parts.audio_player,
    )

    llm_worker = parts.workers.llm_worker
    assert len(llm_worker.status_changed.slots) == 1
    assert len(llm_worker.stream_start.slots) == 1
    assert len(llm_worker.dialog_parsed.slots) == 1
    assert len(llm_worker.tool_summary_ready.slots) == 1
    assert len(llm_worker.stream_end.slots) == 1
    assert len(llm_worker.error.slots) == 1
    assert llm_worker.stream_chunk.slots == []

    llm_worker.status_changed.slots[0]("正在回复")
    llm_worker.status_changed.slots[0]("回复失败：boom")
    assert parts.window.reply_statuses == [("正在回复", False), ("回复失败：boom", True)]

    assert handles.llm_ui_handlers.window is parts.window
    assert handles.llm_ui_handlers.history is parts.history
    assert handles.llm_ui_handlers.active_character_name == "诺艾尔"
    assert handles.llm_ui_handlers.char_color == "#ABCDEF"
    assert handles.llm_ui_handlers.set_sprite_by_id is parts.sprite_controller.set_sprite_by_id
    assert_bound_to(llm_worker.stream_start.slots[0], handles.llm_ui_handlers, "on_stream_start")
    assert_bound_to(llm_worker.dialog_parsed.slots[0], handles.llm_ui_handlers, "on_dialog_parsed")
    assert_bound_to(llm_worker.tool_summary_ready.slots[0], parts.window, "set_tool_summary_result")
    assert_bound_to(llm_worker.stream_end.slots[0], handles.llm_ui_handlers, "on_stream_end")
    assert_bound_to(llm_worker.error.slots[0], handles.llm_ui_handlers, "on_llm_error")

    ui_worker = parts.workers.ui_worker
    expected_ui_connections = {
        "update_dialog": "on_update_dialog",
        "update_narration": "on_update_narration",
        "update_options": "on_update_options",
        "update_cg": "on_update_cg",
        "update_stat": "on_update_stat",
        "update_cot": "on_update_cot",
    }
    for signal_name, method_name in expected_ui_connections.items():
        slots = getattr(ui_worker, signal_name).slots
        assert len(slots) == 1
        assert_bound_to(slots[0], handles.ui_worker_handlers, method_name)

    assert handles.ui_worker_handlers.window is parts.window
    assert handles.ui_worker_handlers.config is parts.config
    assert handles.ui_worker_handlers.submit_t2i_prompt is None
    assert_bound_to(handles.ui_worker_handlers.play_audio, parts.audio_player, "play")


def test_wire_runtime_signals_routes_tool_summary_signal_to_window_state():
    parts = make_runtime_parts()

    wire_runtime_signals(
        window=parts.window,
        workers=parts.workers,
        runtime_setup=parts.runtime_setup,
        llm_context=parts.llm_context,
        chat_history=parts.history,
        config=parts.config,
        sprite_controller=parts.sprite_controller,
        audio_player=parts.audio_player,
    )

    result = _tool_result(
        [
            ToolInvocationRecord(
                order_index=0,
                tool_name="echo_tool",
                status="success",
                arguments_summary="text=hello",
                result_summary="echo:hello",
            )
        ]
    )

    llm_worker = parts.workers.llm_worker
    assert len(llm_worker.tool_summary_ready.slots) == 1

    llm_worker.tool_summary_ready.emit(result)

    assert parts.window.tool_summaries == [result]


def test_wire_runtime_signals_injects_t2i_prompt_submitter_when_t2i_worker_exists():
    parts = make_runtime_parts()

    parts.workers.t2i_worker = FakeT2IWorker()
    submitted = []
    parts.runtime_setup.t2i_prompt_queue = SimpleNamespace(put=submitted.append)

    handles = wire_runtime_signals(
        window=parts.window,
        workers=parts.workers,
        runtime_setup=parts.runtime_setup,
        llm_context=parts.llm_context,
        chat_history=parts.history,
        config=parts.config,
        sprite_controller=parts.sprite_controller,
        audio_player=parts.audio_player,
    )

    handles.ui_worker_handlers.on_update_cg("夕阳")

    assert submitted == ["夕阳"]
    assert len(parts.workers.t2i_worker.image_generated.slots) == 1
    assert len(parts.workers.t2i_worker.generation_failed.slots) == 1
    parts.workers.t2i_worker.image_generated.slots[0]("data/cg/sunset.png")
    parts.workers.t2i_worker.generation_failed.slots[0]("CG 生成失败：boom")
    assert parts.window.reply_statuses == [
        ("CG 生成已提交，正在等待 ComfyUI 生成…", False),
        ("CG 生成完成：data/cg/sunset.png", False),
        ("CG 生成失败：boom", True),
    ]
    assert parts.window.cg_previews == []
    assert not hasattr(parts.window, "prompt_image_requested")


def test_wire_runtime_signals_connects_t2i_image_generated_to_cg_ui_helper(monkeypatch):
    signal_wiring = _SIGNAL_WIRING_MODULE

    parts = make_runtime_parts()
    parts.workers.t2i_worker = FakeT2IWorker()
    calls = []

    def fake_handle_t2i_image_generated(window, result):
        calls.append((window, result))

    monkeypatch.setattr(
        signal_wiring,
        "handle_t2i_image_generated",
        fake_handle_t2i_image_generated,
    )

    wire_runtime_signals(
        window=parts.window,
        workers=parts.workers,
        runtime_setup=parts.runtime_setup,
        llm_context=parts.llm_context,
        chat_history=parts.history,
        config=parts.config,
        sprite_controller=parts.sprite_controller,
        audio_player=parts.audio_player,
    )

    parts.workers.t2i_worker.image_generated.slots[0]("generated-result")

    assert calls == [(parts.window, "generated-result")]


def test_wire_t2i_worker_signals_connects_image_and_failure_callbacks(monkeypatch):
    signal_wiring = _SIGNAL_WIRING_MODULE

    window = FakeWindow()
    t2i_worker = FakeT2IWorker()
    calls = []

    def fake_handle_t2i_image_generated(received_window, result):
        calls.append((received_window, result))

    monkeypatch.setattr(
        signal_wiring,
        "handle_t2i_image_generated",
        fake_handle_t2i_image_generated,
    )

    wire_t2i_worker_signals(window, t2i_worker)

    assert len(t2i_worker.image_generated.slots) == 1
    assert len(t2i_worker.generation_failed.slots) == 1

    t2i_worker.image_generated.slots[0]("generated-result")
    t2i_worker.generation_failed.slots[0]("CG 生成失败：boom")

    assert calls == [(window, "generated-result")]
    assert window.reply_statuses == [("CG 生成失败：boom", True)]


def test_wire_runtime_signals_delegates_window_actions_to_window_action_helper(monkeypatch):
    signal_wiring = _SIGNAL_WIRING_MODULE

    parts = make_runtime_parts()
    settings_window = FakeSettingsWindow()
    calls = []

    def fake_wire_window_actions(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(signal_wiring, "wire_window_actions", fake_wire_window_actions)

    handles = wire_runtime_signals(
        window=parts.window,
        workers=parts.workers,
        runtime_setup=parts.runtime_setup,
        llm_context=parts.llm_context,
        chat_history=parts.history,
        config=parts.config,
        sprite_controller=parts.sprite_controller,
        audio_player=parts.audio_player,
        settings_window=settings_window,
    )

    assert handles.llm_ui_handlers is not None
    assert handles.ui_worker_handlers is not None
    assert calls == [{
        "window": parts.window,
        "chat_history": parts.history,
        "user_input_queue": parts.runtime_setup.user_input_queue,
        "default_char_color": "#ABCDEF",
        "active_character_name": "诺艾尔",
        "config": parts.config,
        "settings_window": settings_window,
    }]
