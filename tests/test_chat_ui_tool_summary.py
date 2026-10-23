import sys
import types
from types import SimpleNamespace

pyside6_module = types.ModuleType("PySide6")
qtcore_module = types.ModuleType("PySide6.QtCore")
qtgui_module = types.ModuleType("PySide6.QtGui")
qtwidgets_module = types.ModuleType("PySide6.QtWidgets")


class _FakeSignalDescriptor:
    def __set_name__(self, owner, name):
        self._storage_name = f"__signal_{name}"

    def __get__(self, instance, owner):
        if instance is None:
            return self
        signal = instance.__dict__.get(self._storage_name)
        if signal is None:
            signal = SimpleNamespace(connect=lambda callback: None, emit=lambda *args, **kwargs: None)
            instance.__dict__[self._storage_name] = signal
        return signal


def Signal(*args, **kwargs):
    return _FakeSignalDescriptor()


def Slot(*args, **kwargs):
    def decorator(func):
        return func
    return decorator


class _EnumValue:
    def __init__(self, name):
        self.name = name

    def __or__(self, other):
        return self


class _EnumNamespace:
    def __getattr__(self, name):
        return _EnumValue(name)


class _FakeQt:
    WindowType = _EnumNamespace()
    WidgetAttribute = _EnumNamespace()
    AlignmentFlag = _EnumNamespace()
    TransformationMode = _EnumNamespace()
    MouseButton = _EnumNamespace()
    CursorShape = _EnumNamespace()
    TextFormat = _EnumNamespace()


class _FakeWidget:
    def __init__(self, *args, **kwargs):
        pass

    def __getattr__(self, name):
        return lambda *args, **kwargs: None


class _FakeMainWindow(_FakeWidget):
    pass


class _FakeApplication(_FakeWidget):
    @classmethod
    def instance(cls):
        return None


class _FakeTimer:
    @staticmethod
    def singleShot(*args, **kwargs):
        return None


class _FakeSize:
    def __init__(self, *args, **kwargs):
        pass


class _FakeUrl:
    def __init__(self, *args, **kwargs):
        pass

    @classmethod
    def fromLocalFile(cls, path):
        return cls(path)


class _FakePixmap(_FakeWidget):
    def isNull(self):
        return False

    def scaledToWidth(self, *args, **kwargs):
        return self

    def scaledToHeight(self, *args, **kwargs):
        return self


qtcore_module.Qt = _FakeQt
qtcore_module.Signal = Signal
qtcore_module.Slot = Slot
qtcore_module.QTimer = _FakeTimer
qtcore_module.QAbstractAnimation = _FakeWidget
qtcore_module.QPropertyAnimation = _FakeWidget
qtcore_module.QSize = _FakeSize
qtcore_module.QUrl = _FakeUrl
qtcore_module.QEvent = _FakeWidget
qtcore_module.QObject = _FakeWidget
qtcore_module.QPoint = _FakeWidget
qtcore_module.QRect = _FakeWidget

qtgui_module.QPixmap = _FakePixmap
qtgui_module.QFont = _FakeWidget
qtgui_module.QColor = _FakeWidget
qtgui_module.QPalette = _FakeWidget
qtgui_module.QIcon = _FakeWidget
qtgui_module.QPainter = _FakeWidget
qtgui_module.QDesktopServices = _FakeWidget
qtgui_module.QCursor = _FakeWidget

qtwidgets_module.QApplication = _FakeApplication
qtwidgets_module.QMainWindow = _FakeMainWindow
qtwidgets_module.QWidget = _FakeWidget
qtwidgets_module.QVBoxLayout = _FakeWidget
qtwidgets_module.QHBoxLayout = _FakeWidget
qtwidgets_module.QTextEdit = _FakeWidget
qtwidgets_module.QLineEdit = _FakeWidget
qtwidgets_module.QPushButton = _FakeWidget
qtwidgets_module.QLabel = _FakeWidget
qtwidgets_module.QScrollArea = _FakeWidget
qtwidgets_module.QFrame = _FakeWidget
qtwidgets_module.QSizePolicy = _FakeWidget
qtwidgets_module.QGraphicsDropShadowEffect = _FakeWidget
qtwidgets_module.QDialog = _FakeWidget
qtwidgets_module.QListWidget = _FakeWidget
qtwidgets_module.QListWidgetItem = _FakeWidget
qtwidgets_module.QInputDialog = _FakeWidget
qtwidgets_module.QMessageBox = _FakeWidget
qtwidgets_module.QMenu = _FakeWidget
qtwidgets_module.QStackedLayout = _FakeWidget
qtwidgets_module.QGraphicsOpacityEffect = _FakeWidget
qtgui_module.QAction = _FakeWidget

_ORIGINAL_PYSIDE6 = {
    name: sys.modules.get(name)
    for name in (
        "PySide6",
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
    )
}
_SYS_MODULES_SNAPSHOT = set(sys.modules)

sys.modules["PySide6"] = pyside6_module
sys.modules["PySide6.QtCore"] = qtcore_module
sys.modules["PySide6.QtGui"] = qtgui_module
sys.modules["PySide6.QtWidgets"] = qtwidgets_module

from core.runtime.tool_summary import ToolInvocationRecord, ToolLoopTurnResult, ToolTurnSummary
from ui.chat_ui.chat_ui import ChatUIWindow, build_tool_summary_view_model

# 缓存 fake 期间构建的模块引用：sys.modules 条目会在下面被清理（避免污染
# 后续测试文件），但本文件的测试仍通过该引用使用 fake 版类。
_CHAT_UI_MODULE = sys.modules["ui.chat_ui.chat_ui"]

for _name, _module in _ORIGINAL_PYSIDE6.items():
    if _module is None:
        sys.modules.pop(_name, None)
    else:
        sys.modules[_name] = _module

# 清理 fake 期间新增的项目模块（如用 fake 基类构建的 ui.window_chrome）：
# 否则残留的 fake 版类会让后续测试文件（如 test_settings_window、
# test_frameless_session_dialogs）与真实 Qt 交互时 TypeError。
for _name in list(sys.modules):
    _mod = sys.modules[_name]
    is_package = getattr(_mod, "__path__", None) is not None
    if _name not in _SYS_MODULES_SNAPSHOT and not is_package:
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


def _tool_result(records: list[ToolInvocationRecord]) -> ToolLoopTurnResult:
    return ToolLoopTurnResult(
        final_output="done",
        invocation_records=records,
        summary=ToolTurnSummary.from_records(records),
    )


def test_tool_summary_hidden_when_turn_used_no_tools():
    view_model = build_tool_summary_view_model(_tool_result([]), expanded=False)

    assert view_model.visible is False
    assert view_model.toggle_text == "展开工具摘要"
    assert view_model.count_text == ""
    assert view_model.detail_rows == []


def test_tool_summary_shows_collapsed_counts_for_tool_turn():
    result = _tool_result(
        [
            ToolInvocationRecord(
                order_index=0,
                tool_name="echo_tool",
                status="success",
                arguments_summary="text=hello",
                result_summary="echo:hello",
            ),
            ToolInvocationRecord(
                order_index=1,
                tool_name="fail_tool",
                status="failed",
                arguments_summary="reason=boom",
                error_summary="boom",
            ),
        ]
    )

    view_model = build_tool_summary_view_model(result, expanded=False)

    assert view_model.visible is True
    assert view_model.expanded is False
    assert view_model.toggle_text == "展开工具摘要"
    assert view_model.count_text == "本轮工具调用：2 次（成功 1 / 失败 1）"
    assert view_model.detail_rows == []


def test_tool_summary_expands_to_show_per_invocation_rows():
    result = _tool_result(
        [
            ToolInvocationRecord(
                order_index=0,
                tool_name="echo_tool",
                status="success",
                arguments_summary="text=hello",
                result_summary="echo:hello",
            ),
            ToolInvocationRecord(
                order_index=1,
                tool_name="fail_tool",
                status="failed",
                arguments_summary="reason=boom",
                error_summary="boom",
            ),
        ]
    )

    view_model = build_tool_summary_view_model(result, expanded=True)

    assert view_model.toggle_text == "收起工具摘要"
    assert view_model.expanded is True
    assert view_model.detail_rows == [
        "#1 · echo_tool · 成功",
        "参数：text=hello",
        "结果：echo:hello",
        "#2 · fail_tool · 失败",
        "参数：reason=boom",
        "错误：boom",
    ]


def test_set_tool_summary_result_updates_chat_ui_state_without_qt():
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
    window = SimpleNamespace(
        _tool_summary_expanded=False,
        _tool_summary_result=None,
        tool_summary_frame=SimpleNamespace(visible=None, setVisible=lambda visible: setattr(window.tool_summary_frame, "visible", visible)),
        tool_summary_count_label=SimpleNamespace(text=None, setText=lambda text: setattr(window.tool_summary_count_label, "text", text)),
        tool_summary_toggle_btn=SimpleNamespace(text=None, setText=lambda text: setattr(window.tool_summary_toggle_btn, "text", text)),
        tool_summary_details_widget=SimpleNamespace(visible=None, setVisible=lambda visible: setattr(window.tool_summary_details_widget, "visible", visible)),
        _tool_summary_detail_rows=None,
    )

    def capture_rows(rows):
        window._tool_summary_detail_rows = list(rows)

    window._render_tool_summary_detail_rows = capture_rows
    window._apply_tool_summary_view_model = lambda view_model: ChatUIWindow._apply_tool_summary_view_model(window, view_model)

    ChatUIWindow.set_tool_summary_result(window, result)

    assert window._tool_summary_result is result
    assert window.tool_summary_frame.visible is True
    assert window.tool_summary_count_label.text == "本轮工具调用：1 次（成功 1 / 失败 0）"
    assert window.tool_summary_toggle_btn.text == "展开工具摘要"
    assert window.tool_summary_details_widget.visible is False
    assert window._tool_summary_detail_rows == []


def test_chat_ui_routes_terminal_approval_only_after_explicit_human_choice(monkeypatch):
    chat_ui_module = _CHAT_UI_MODULE

    approvals = []
    denials = []

    class FakeMessageBox:
        class StandardButton:
            Yes = 1
            No = 2

        @staticmethod
        def question(*args, **kwargs):
            return FakeMessageBox.StandardButton.Yes

    monkeypatch.setattr(chat_ui_module, "QMessageBox", FakeMessageBox)
    monkeypatch.setattr(chat_ui_module, "approve_terminal_decision", lambda decision_id: approvals.append(decision_id) or {"status": "consumed"})
    monkeypatch.setattr(chat_ui_module, "deny_terminal_decision", lambda decision_id: denials.append(decision_id) or {"status": "denied"})
    window = SimpleNamespace(set_reply_status=lambda text, error=False: None)
    result = _tool_result([
        ToolInvocationRecord(
            order_index=0,
            tool_name="terminal",
            status="failed",
            arguments_summary="command=rm -rf protected",
            error_summary="approval required",
            approval_request={
                "approval_required": True,
                "pending_decision_id": "decision-42",
                "risk_level": "high",
                "reason": "destructive command",
            },
        )
    ])

    ChatUIWindow._handle_approval_requests(window, result)

    assert approvals == ["decision-42"]
    assert denials == []
