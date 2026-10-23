"""Galgame 风格聊天主窗口 — 全透明背景，只显示立绘和气泡"""
import html
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from core.runtime.application_identity import APPLICATION_DISPLAY_NAME
from core.runtime.tool_summary import ToolLoopTurnResult
from core.runtime.terminal_executor import approve_terminal_decision, deny_terminal_decision
from ui.window_chrome import FramelessResizeController, WindowDragController
from ui import motion
from ui.frameless_dialog import build_frameless_dialog_shell
from ui.theme import (
    CHAT_BTN_PRIMARY, CHAT_BTN_NORMAL, CHAT_BTN_DANGER, CHAT_BTN_SMALL, CHAT_CHOICE_BTN,
    CHAT_INPUT_ROW_ICON_BTN,
    CHAT_BTN_CLOSE, CHAT_DIALOGUE_GLASS_STYLE, CHAT_DIALOGUE_LOWER_STYLE,
    CHAT_TEMPORARY_CONTENT_GLASS_STYLE, CHAT_TEMPORARY_CONTENT_STYLE,
    CHAT_INPUT_STYLE,
    CHAT_ICON_BTN, CHAT_ICON_BTN_CLOSE, CHAT_NAME_PLATE,
    CHAT_DIALOG_INFO_POPUP_STYLE, CHAT_DIALOG_INFO_TOGGLE_STYLE,
    CHAT_COMPANION_TOGGLE_BTN,
    HISTORY_PANEL_STYLE, HISTORY_TITLE_STYLE,
    HISTORY_BUBBLE_AI, HISTORY_BUBBLE_USER,
    COLOR_CYAN, COLOR_FG, COLOR_DIM,
    ACCENT, ACCENT_SOFT, BORDER, BG_INPUT, BG_ELEVATED,
)

try:
    from PySide6.QtWidgets import (
        QApplication,
        QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QTextEdit, QLineEdit, QPushButton, QLabel, QScrollArea,
        QFrame, QSizePolicy, QDialog, QStackedLayout,
        QListWidget, QListWidgetItem, QInputDialog, QMessageBox,
        QMenu, QGraphicsOpacityEffect
    )
    from PySide6.QtCore import Qt, Signal, Slot, QTimer, QRect, QSize, QPoint, QUrl, QEvent, QAbstractAnimation, QPropertyAnimation
    from PySide6.QtGui import QPixmap, QFont, QPalette, QIcon, QPainter, QDesktopServices, QAction, QCursor
    PYSIDE6_AVAILABLE = True
    from ui.chat_ui.sprite_widget import SpriteWidget
    from ui.chat_ui.background_surface import BackgroundSurface
    from ui.chat_ui.dialogue_text import DialogueTextLabel
    from ui.chat_ui.entrance import play_entrance
    from ui.resources import application_icon, ensure_ui_font, set_button_icon
except ModuleNotFoundError:
    PYSIDE6_AVAILABLE = False

    class _MissingPySide6:
        def __init__(self, *args, **kwargs):
            raise ModuleNotFoundError("PySide6 is required for ui.chat_ui.chat_ui")

    def Signal(*args, **kwargs):
        return None

    def Slot(*args, **kwargs):
        def decorator(func):
            return func
        return decorator

    QApplication = QMainWindow = QWidget = QVBoxLayout = QHBoxLayout = _MissingPySide6
    QTextEdit = QLineEdit = QPushButton = QLabel = QScrollArea = _MissingPySide6
    QFrame = QSizePolicy = QDialog = QStackedLayout = QGraphicsOpacityEffect = _MissingPySide6
    QListWidget = QListWidgetItem = QInputDialog = QMessageBox = _MissingPySide6
    Qt = QTimer = QRect = QSize = QPoint = QUrl = QPixmap = QFont = QPalette = QIcon = QPainter = QDesktopServices = _MissingPySide6
    QAbstractAnimation = QPropertyAnimation = _MissingPySide6
    BackgroundSurface = SpriteWidget = DialogueTextLabel = _MissingPySide6

    def play_entrance(widget, owner):
        return None


# 这些“说话者”不是角色本人，出现时立绘不做说话反馈。
_NON_CHARACTER_SPEAKERS = frozenset({"", "系统", "旁白", "资料卡"})


@dataclass(slots=True)
class ChatHistoryEntry:
    text: str
    is_user: bool = False
    char_name: str = ""
    char_color: str = "#f2a0bd"

    @property
    def speaker_name(self) -> str:
        return "你" if self.is_user else self.char_name

    def to_snapshot(self) -> dict:
        return {
            "text": self.text,
            "is_user": self.is_user,
            "char_name": self.char_name,
            "char_color": self.char_color,
        }


class HistoryBubbleLabel(QLabel):
    """Word-wrapped history bubble whose height follows its assigned width."""

    _HORIZONTAL_PADDING = 26
    _VERTICAL_PADDING = 18

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setWordWrap(True)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        policy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        content_width = max(1, width - self._HORIZONTAL_PADDING)
        flags = Qt.TextFlag.TextWordWrap | Qt.TextFlag.TextWrapAnywhere | Qt.TextFlag.TextExpandTabs
        bounds = self.fontMetrics().boundingRect(0, 0, content_width, 100000, int(flags), self.text())
        return max(self.fontMetrics().height(), bounds.height()) + self._VERTICAL_PADDING

    def sizeHint(self):
        hint = super().sizeHint()
        width = min(self.maximumWidth(), hint.width()) if self.maximumWidth() < 16777215 else hint.width()
        width = max(self.minimumWidth(), width)
        return QSize(width, self.heightForWidth(width))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        required_height = self.heightForWidth(event.size().width())
        if self.minimumHeight() != required_height:
            self.setMinimumHeight(required_height)


@dataclass(slots=True)
class ToolSummaryViewModel:
    visible: bool
    expanded: bool
    count_text: str
    toggle_text: str
    detail_rows: list[str]


def build_tool_summary_view_model(result: ToolLoopTurnResult, expanded: bool = False) -> ToolSummaryViewModel:
    records = list(result.invocation_records)
    if not records:
        return ToolSummaryViewModel(
            visible=False,
            expanded=False,
            count_text="",
            toggle_text="展开工具摘要",
            detail_rows=[],
        )

    detail_rows: list[str] = []
    if expanded:
        for record in records:
            status_text = "成功" if record.status == "success" else "失败"
            detail_rows.append(f"#{record.order_index + 1} · {record.tool_name} · {status_text}")
            detail_rows.append(f"参数：{record.arguments_summary}")
            if record.status == "success":
                detail_rows.append(f"结果：{record.result_summary or ''}")
            else:
                detail_rows.append(f"错误：{record.error_summary or ''}")

    summary = result.summary
    return ToolSummaryViewModel(
        visible=True,
        expanded=expanded,
        count_text=(
            f"本轮工具调用：{summary.total_count} 次（成功 {summary.success_count} / 失败 {summary.failure_count}）"
        ),
        toggle_text="收起工具摘要" if expanded else "展开工具摘要",
        detail_rows=detail_rows,
    )


class CGPreviewLabel(QLabel):
    """可点击的 CG 缩略图标签。"""

    def __init__(self, image_path: str, open_callback, parent=None):
        super().__init__(parent)
        self.image_path = image_path
        self._source_pixmap = QPixmap(image_path)
        self._open_callback = open_callback
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.setStyleSheet("background: transparent;")

    def set_preview_width(self, width: int) -> None:
        """按目标宽度刷新缩略图显示。"""
        if self._source_pixmap.isNull():
            self.clear()
            return
        target_width = max(160, width)
        self.setPixmap(
            self._source_pixmap.scaledToWidth(
                target_width,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._open_callback(self.image_path)
            event.accept()
            return
        super().mousePressEvent(event)


class NamePlateLabel(QLabel):
    """骑边名牌：渐变胶囊，文本变化时自动调整自身尺寸。"""

    clicked = Signal()

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.adjustSize()

    def setText(self, text: str) -> None:
        super().setText(text)
        self.adjustSize()

    def mouseReleaseEvent(self, event) -> None:
        if self.isEnabled() and event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:
        if self.isEnabled() and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space, Qt.Key.Key_Down):
            self.clicked.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setPen(self.palette().color(QPalette.ColorRole.WindowText))
        x, y = self.width() - 13, self.height() // 2
        painter.drawLine(x - 3, y - 1, x, y + 2)
        painter.drawLine(x, y + 2, x + 3, y - 1)
        painter.end()


class FloatingDialogUnit(QWidget):
    """底部悬浮对话单元：名牌胶囊骑在玻璃面板的上边缘（经典 ADV 构图）。

    内部布局只放玻璃面板，并为其上方预留名牌的重叠高度；
    名牌作为本控件的绝对定位子控件，横跨面板的上边框。
    """

    _PLATE_X = 16
    _PLATE_OVERLAP = 14

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setObjectName("floating_dialog_unit")
        self.setStyleSheet("QWidget#floating_dialog_unit { background: transparent; }")
        self._name_plate = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, self._PLATE_OVERLAP, 0, 0)
        layout.setSpacing(0)

    def set_name_plate(self, plate: QLabel) -> None:
        self._name_plate = plate
        plate.setParent(self)
        plate.move(self._PLATE_X, 0)
        plate.raise_()

    def set_content(self, panel: QWidget) -> None:
        self.layout().addWidget(panel)
        if self._name_plate is not None:
            self._name_plate.raise_()


class ChatUIWindow(QMainWindow):
    """主聊天窗口 — 无边框、全透明背景"""

    # 信号
    user_message_sent = Signal(str)
    stop_requested = Signal()
    emotion_changed = Signal(str)
    clear_requested = Signal()
    reroll_requested = Signal()
    settings_requested = Signal()
    background_requested = Signal()
    character_requested = Signal(str)
    character_menu_opening = Signal()
    reply_waiting_changed = Signal(bool)
    new_session_requested = Signal(str)
    session_switch_requested = Signal(str)
    session_rename_requested = Signal(str, str)
    session_delete_requested = Signal(str)
    session_archive_requested = Signal(str, bool)
    session_skills_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("main_window")
        ensure_ui_font()
        self.setWindowIcon(application_icon())
        self.setAccessibleName("Yayu main window")
        self.setWindowTitle(APPLICATION_DISPLAY_NAME)
        self.setMinimumSize(640, 520)
        self.resize(820, 760)

        # 无边框 + 透明背景
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowSystemMenuHint
            | Qt.WindowType.WindowMinimizeButtonHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self._drag_pos = None
        self._sprite_click_origin = None
        self._cg_preview_labels = []
        self._session_items = []
        self.skill_preset_options = ["全选", "全局默认"]
        self.current_session_id = ""
        self.current_session_title = ""
        self._tool_summary_result = None
        self._tool_summary_expanded = False
        self._runtime_activity_entries = []
        self._runtime_state = "idle"
        self._waiting_for_reply = False
        self._choice_group = None
        self._focus_custom_reply_after_waiting = False
        self._active_character_name = ""
        self._active_character_id = ""
        self._character_items = []
        self._character_menu = None
        self._last_runtime_activity_text = ""
        self._closing = False
        self._suppress_next_dialog_info_click = False
        self._message_history = []
        self._stream_history_index = None
        self._stream_text = ""
        self._char_sprite_scale = 1.0
        self._user_sprite_zoom = 1.0
        self._ui_visible = True
        self._overlay_anim = None
        self._gpt_sovits_monitor = None
        self._gpt_sovits_api_controller = None
        self._gpt_sovits_api_manageable = False
        self._gpt_sovits_connection_state = "disabled"
        self._gpt_sovits_server_url = ""
        self._setup_ui()
        self._gpt_sovits_startup_probe_timer = QTimer(self)
        self._gpt_sovits_startup_probe_timer.setInterval(1000)
        self._gpt_sovits_startup_probe_timer.timeout.connect(self.refresh_gpt_sovits_connection_status)

    def _setup_ui(self):
        central = BackgroundSurface()
        central.setObjectName("chat_central")
        central.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        # Bare background rules also reach Qt's tooltip label and erase its opaque fill.
        central.setStyleSheet("QWidget#chat_central { background: transparent; }")
        self.setCentralWidget(central)

        # 全屏立绘层 + 悬浮 UI 层：StackAll 让两层铺满窗口，UI 浮于立绘之上
        self._stack = QStackedLayout(central)
        self._stack.setStackingMode(QStackedLayout.StackingMode.StackAll)
        self._stack.setContentsMargins(0, 0, 0, 0)

        # ── 底层：角色舞台，立绘占满整个窗口 ──
        self.character_stage = QFrame()
        self.character_stage.setObjectName("character_stage")
        self.character_stage.setAccessibleName("Character stage")
        self.character_stage.setStyleSheet("QFrame#character_stage { background: transparent; }")
        self.character_stage_layout = QVBoxLayout(self.character_stage)
        self.character_stage_layout.setContentsMargins(0, 0, 0, 0)
        self.character_stage_layout.setSpacing(0)
        self.sprite_widget = SpriteWidget()
        self.sprite_widget.setObjectName("character_sprite_view")
        self.sprite_widget.setAccessibleName("Character sprite view")
        self.sprite_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.character_stage_layout.addWidget(self.sprite_widget)
        self._stack.addWidget(self.character_stage)

        # ── 顶层：悬浮 UI（顶部控制条 + 底部对话单元，全部透明底） ──
        self.overlay_layer = QWidget()
        self.overlay_layer.setObjectName("overlay_layer")
        self.overlay_layer.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.overlay_layer.setStyleSheet("QWidget#overlay_layer { background: transparent; }")
        self.main_content_layout = QVBoxLayout(self.overlay_layer)
        self.main_content_layout.setContentsMargins(0, 0, 0, 0)
        self.main_content_layout.setSpacing(0)
        self._stack.addWidget(self.overlay_layer)
        # 注意：StackAll 模式下 current widget 会被 raise 到最上层，
        # 必须在添加完成后显式把 overlay 设为 current，否则立绘会盖住悬浮 UI
        self._stack.setCurrentWidget(self.overlay_layer)

        # 右上角圆形悬浮控制按钮组（☰ / ⚙ / — / ✕）
        self.top_chrome = QWidget()
        self.top_chrome.setObjectName("top_chrome")
        self.top_chrome.setStyleSheet("QWidget#top_chrome { background: transparent; }")
        top_bar = QHBoxLayout(self.top_chrome)
        top_bar.setContentsMargins(12, 10, 12, 4)
        top_bar.setSpacing(6)
        top_bar.addStretch()
        self.history_btn = QPushButton("☰")
        set_button_icon(self.history_btn, "history", light=True)
        self.history_btn.setObjectName("history_button")
        self.history_btn.setAccessibleName("Open chat history")
        self.history_btn.setToolTip("查看聊天记录")
        self.history_btn.setFixedSize(40, 40)
        self.history_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.history_btn.setStyleSheet(CHAT_ICON_BTN)
        self.history_btn.clicked.connect(self._open_chat_history)
        top_bar.addWidget(self.history_btn)
        self.background_btn = QPushButton()
        set_button_icon(self.background_btn, "image", light=True)
        self.background_btn.setObjectName("background_button")
        self.background_btn.setAccessibleName("Choose background")
        self.background_btn.setToolTip("切换背景")
        self.background_btn.setFixedSize(40, 40)
        self.background_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.background_btn.setStyleSheet(CHAT_ICON_BTN)
        self.background_btn.clicked.connect(self.background_requested.emit)
        top_bar.addWidget(self.background_btn)
        self.settings_btn = QPushButton("⚙")
        set_button_icon(self.settings_btn, "settings", light=True)
        self.settings_btn.setObjectName("settings_button")
        self.settings_btn.setAccessibleName("Open settings")
        self.settings_btn.setToolTip("打开设置中心")
        self.settings_btn.setFixedSize(40, 40)
        self.settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings_btn.setStyleSheet(CHAT_ICON_BTN)
        self.settings_btn.clicked.connect(self.settings_requested.emit)
        top_bar.addWidget(self.settings_btn)
        self.minimize_btn = QPushButton("—")
        set_button_icon(self.minimize_btn, "minus", light=True)
        self.minimize_btn.setObjectName("minimize_button")
        self.minimize_btn.setAccessibleName("Minimize")
        self.minimize_btn.setToolTip("最小化")
        self.minimize_btn.setFixedSize(40, 40)
        self.minimize_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.minimize_btn.setStyleSheet(CHAT_ICON_BTN)
        self.minimize_btn.clicked.connect(self.showMinimized)
        top_bar.addWidget(self.minimize_btn)
        self.close_btn = QPushButton("✕")
        set_button_icon(self.close_btn, "close", light=True)
        self.close_btn.setObjectName("close_button")
        self.close_btn.setAccessibleName("Close")
        self.close_btn.setToolTip("关闭窗口")
        self.close_btn.setFixedSize(40, 40)
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.setStyleSheet(CHAT_ICON_BTN_CLOSE)
        self.close_btn.clicked.connect(self.close)
        top_bar.addWidget(self.close_btn)
        self.main_content_layout.addWidget(self.top_chrome)
        self.main_content_layout.addStretch(1)

        # 底部悬浮对话单元：骑边名牌 + 玻璃面板（台词 + 临时内容 + 输入行）
        dock = QWidget()
        dock.setObjectName("floating_dock")
        dock.setStyleSheet("QWidget#floating_dock { background: transparent; }")
        dock_layout = QVBoxLayout(dock)
        dock_layout.setContentsMargins(16, 0, 16, 12)
        dock_layout.setSpacing(0)
        self.dialog_unit = FloatingDialogUnit()
        self.dialog_unit.setObjectName("floating_dialog_unit")
        dock_layout.addWidget(self.dialog_unit)
        self.main_content_layout.addWidget(dock)

        # 名牌：骑在对话框上边缘的渐变胶囊
        self.current_speaker_label = NamePlateLabel("")
        self.current_speaker_label.setObjectName("current_speaker_label")
        self.current_speaker_label.setStyleSheet(CHAT_NAME_PLATE + "QLabel { padding-right: 26px; border: 1px solid transparent; } QLabel:focus { border-color: #F8F7EC; }")
        self.current_speaker_label.setAccessibleName("切换聊天角色")
        self.current_speaker_label.setToolTip("点击切换聊天角色（每个角色的聊天记录单独保存）")
        self.current_speaker_label.clicked.connect(self._show_character_menu)
        self.current_speaker_label.setVisible(False)
        self.dialog_unit.set_name_plate(self.current_speaker_label)

        # 玻璃面板（上：当前台词；下：临时内容 + 输入行）
        panel = QWidget()
        panel.setObjectName("floating_dialog_panel")
        panel.setStyleSheet("QWidget#floating_dialog_panel { background: transparent; }")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(0)

        # ADV 对话框上半部：当前台词 + 右侧 ▼ 对话信息按钮
        self.current_message_frame = QFrame()
        self.current_message_frame.setObjectName("current_message_frame")
        self.current_message_frame.setAccessibleName("Current dialogue")
        self.current_message_frame.setMinimumHeight(88)
        self.current_message_frame.setMaximumHeight(120)
        self.current_message_frame.setStyleSheet(CHAT_DIALOGUE_GLASS_STYLE)
        dialogue_layout = QHBoxLayout(self.current_message_frame)
        dialogue_layout.setContentsMargins(20, 22, 10, 8)
        dialogue_layout.setSpacing(4)

        # 纯文本 + 逐字显示：模型台词不再按富文本解释（避免台词里的 HTML 被渲染）。
        self.current_message_label = DialogueTextLabel()
        self.current_message_label.setObjectName("current_message_label")
        self.current_message_label.setStyleSheet(
            "color: #233039; font-size: 14px; line-height: 1.7; background: transparent;"
        )
        self.current_message_scroll_area = QScrollArea()
        self.current_message_scroll_area.setWidgetResizable(True)
        self.current_message_scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.current_message_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.current_message_scroll_area.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self.current_message_scroll_area.viewport().setStyleSheet("background: transparent;")
        self.current_message_scroll_area.setWidget(self.current_message_label)
        dialogue_layout.addWidget(self.current_message_scroll_area, stretch=1)

        # 运行信息开关用 ⓘ，避免与台词结束时的 ▼ 续读提示混淆。
        self.dialog_info_toggle_btn = QPushButton("ⓘ")
        set_button_icon(self.dialog_info_toggle_btn, "info", 16)
        self.dialog_info_toggle_btn.setObjectName("dialog_next_indicator")
        self.dialog_info_toggle_btn.setAccessibleName("Toggle conversation information")
        self.dialog_info_toggle_btn.setToolTip("查看运行过程与服务状态")
        self.dialog_info_toggle_btn.setFixedSize(26, 26)
        self.dialog_info_toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.dialog_info_toggle_btn.setStyleSheet(CHAT_DIALOG_INFO_TOGGLE_STYLE)
        self.dialog_info_toggle_btn.clicked.connect(self._toggle_conversation_info_popup)
        self.dialog_next_label = self.dialog_info_toggle_btn
        dialogue_layout.addWidget(self.dialog_info_toggle_btn, 0, Qt.AlignmentFlag.AlignTop)
        panel_layout.addWidget(self.current_message_frame)

        # ADV 对话框下半部：临时内容区 / 输入栏（与上半台词框拼成一个玻璃对话框）
        chat_container = QWidget()
        chat_container.setObjectName("dialog_lower_container")
        chat_container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        chat_container.setStyleSheet(CHAT_DIALOGUE_LOWER_STYLE)
        chat_layout = QVBoxLayout(chat_container)
        chat_layout.setContentsMargins(0, 0, 0, 6)
        chat_layout.setSpacing(0)

        self.temporary_content_scroll_area = QScrollArea()
        self.temporary_content_scroll_area.setObjectName("temporary_content_scroll_area")
        self.temporary_content_scroll_area.setAccessibleName("Temporary conversation content")
        self.scroll_area = self.temporary_content_scroll_area
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet(CHAT_TEMPORARY_CONTENT_GLASS_STYLE)
        self.scroll_area.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.scroll_area.setAutoFillBackground(False)
        self.scroll_area.viewport().setAutoFillBackground(False)
        self.scroll_area.viewport().setStyleSheet("background: transparent;")

        self.temporary_content_widget = QWidget()
        self.temporary_content_widget.setObjectName("temporary_content_widget")
        self.temporary_content_widget.setAccessibleName("Temporary conversation content")
        self.temporary_content_widget.setStyleSheet(CHAT_TEMPORARY_CONTENT_STYLE)
        self.temporary_widget = self.temporary_content_widget
        self.temporary_content_layout = QVBoxLayout(self.temporary_content_widget)
        self.temporary_layout = self.temporary_content_layout
        self.temporary_layout.setContentsMargins(10, 8, 10, 8)
        self.temporary_layout.setSpacing(8)
        self.messages_widget = self.temporary_widget
        self.scroll_area.setWidget(self.temporary_widget)
        self.scroll_area.setMaximumHeight(self._temporary_area_max_height())
        self.scroll_area.setVisible(False)
        chat_layout.addWidget(self.scroll_area)

        # 按需对话信息浮层：不参与主布局高度，点击对白框右上角 ▼ 查看。
        self.conversation_info_popup = QFrame(self, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.conversation_info_popup.setObjectName("conversation_info_popup")
        self.conversation_info_popup.setAccessibleName("Conversation information")
        self.conversation_info_popup.setStyleSheet(CHAT_DIALOG_INFO_POPUP_STYLE)
        self.conversation_info_popup.installEventFilter(self)
        self.conversation_info_layout = QVBoxLayout(self.conversation_info_popup)
        self.conversation_info_layout.setContentsMargins(16, 14, 16, 14)
        self.conversation_info_layout.setSpacing(8)

        # 角色和会话操作已集中在会话管理中；隐藏对象仅用于兼容现有状态同步。
        self.current_character_info_label = QLabel("当前角色：未指定", self.conversation_info_popup)
        self.current_character_info_label.setObjectName("current_character_info_label")
        self.current_character_info_label.setAccessibleName("Current character")
        self.current_character_info_label.hide()

        self.session_title_label = QLabel("", self.conversation_info_popup)
        self.session_title_label.setObjectName("session_title_label")
        self.session_title_label.setAccessibleName("Current session title")
        self.session_title_label.hide()

        self.rename_session_btn = QPushButton("重命名当前会话", self.conversation_info_popup)
        self.rename_session_btn.setObjectName("rename_session_button")
        self.rename_session_btn.setAccessibleName("Rename current session")
        self.rename_session_btn.clicked.connect(self._rename_current_session)
        self.rename_session_btn.hide()

        self.archive_session_btn = QPushButton("归档当前会话", self.conversation_info_popup)
        self.archive_session_btn.setObjectName("archive_session_button")
        self.archive_session_btn.setAccessibleName("Archive current session")
        self.archive_session_btn.clicked.connect(self._archive_current_session)
        self.archive_session_btn.hide()

        self.runtime_activity_frame = QFrame()
        self.runtime_activity_frame.setObjectName("runtime_activity_frame")
        self.runtime_activity_frame.setAccessibleName("Runtime activity")
        self.runtime_activity_frame.setStyleSheet("""
            QFrame#runtime_activity_frame {
                background-color: rgba(237, 241, 232, 190);
                border: 1px solid rgba(116, 137, 118, 45);
                border-radius: 12px;
            }
        """)
        runtime_layout = QVBoxLayout(self.runtime_activity_frame)
        runtime_layout.setContentsMargins(12, 10, 12, 10)
        runtime_layout.setSpacing(7)

        runtime_header = QHBoxLayout()
        runtime_header.setContentsMargins(0, 0, 0, 0)
        runtime_header.setSpacing(7)
        self.runtime_state_dot_label = QLabel("●")
        self.runtime_state_dot_label.setObjectName("runtime_state_dot_label")
        self.runtime_state_dot_label.setAccessibleName("Runtime state indicator")
        runtime_header.addWidget(self.runtime_state_dot_label)
        runtime_title = QLabel("运行过程")
        runtime_title.setObjectName("runtime_activity_title")
        runtime_title.setStyleSheet(
            "color: rgba(35, 48, 57, 230); font-size: 12px; font-weight: 600; background: transparent; border: none;"
        )
        runtime_header.addWidget(runtime_title)
        runtime_header.addStretch()
        self.runtime_state_badge_label = QLabel("空闲")
        self.runtime_state_badge_label.setObjectName("runtime_state_badge_label")
        self.runtime_state_badge_label.setAccessibleName("Runtime state")
        runtime_header.addWidget(self.runtime_state_badge_label)
        runtime_layout.addLayout(runtime_header)

        self.reply_status_label = QLabel("准备就绪，等待消息")
        self.reply_status_label.setObjectName("reply_status_label")
        self.reply_status_label.setAccessibleName("Reply status")
        self.reply_status_label.setWordWrap(True)
        self.reply_status_label.setMinimumHeight(22)
        self.reply_status_label.setMaximumHeight(44)
        self.reply_status_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._apply_reply_status_style(error=False)
        runtime_layout.addWidget(self.reply_status_label)

        self.runtime_activity_scroll_area = QScrollArea()
        self.runtime_activity_scroll_area.setObjectName("runtime_activity_scroll_area")
        self.runtime_activity_scroll_area.setAccessibleName("Runtime activity timeline")
        self.runtime_activity_scroll_area.setWidgetResizable(True)
        self.runtime_activity_scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.runtime_activity_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.runtime_activity_scroll_area.setMaximumHeight(150)
        self.runtime_activity_scroll_area.setStyleSheet(
            "QScrollArea { background: transparent; border: none; } QScrollBar:vertical { width: 6px; }"
        )
        self.runtime_activity_widget = QWidget()
        self.runtime_activity_widget.setStyleSheet("background: transparent;")
        self.runtime_activity_layout = QVBoxLayout(self.runtime_activity_widget)
        self.runtime_activity_layout.setContentsMargins(0, 0, 0, 0)
        self.runtime_activity_layout.setSpacing(5)
        self.runtime_activity_scroll_area.setWidget(self.runtime_activity_widget)
        runtime_layout.addWidget(self.runtime_activity_scroll_area)
        self.conversation_info_layout.addWidget(self.runtime_activity_frame)
        self._set_runtime_state("idle")
        self._append_runtime_activity("准备就绪，等待消息", state="idle")

        tts_status_row = QHBoxLayout()
        tts_status_row.setContentsMargins(0, 0, 0, 0)
        tts_status_row.setSpacing(8)
        self.gpt_sovits_status_label = QLabel("GPT-SoVITS：未启用")
        self.gpt_sovits_status_label.setObjectName("gpt_sovits_connection_status_label")
        self.gpt_sovits_status_label.setAccessibleName("GPT-SoVITS connection status")
        self.gpt_sovits_status_label.setMaximumHeight(22)
        self.gpt_sovits_status_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._apply_gpt_sovits_status_style("disabled")
        tts_status_row.addWidget(self.gpt_sovits_status_label, stretch=1)

        self.gpt_sovits_refresh_btn = QPushButton("刷新")
        self.gpt_sovits_refresh_btn.setObjectName("refresh_gpt_sovits_connection_button")
        self.gpt_sovits_refresh_btn.setAccessibleName("Refresh GPT-SoVITS connection status")
        self.gpt_sovits_refresh_btn.setToolTip("立即检查 GPT-SoVITS API 是否可连接")
        self.gpt_sovits_refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.gpt_sovits_refresh_btn.setStyleSheet(CHAT_BTN_SMALL)
        self.gpt_sovits_refresh_btn.clicked.connect(self.refresh_gpt_sovits_connection_status)
        tts_status_row.addWidget(self.gpt_sovits_refresh_btn)

        self.gpt_sovits_api_toggle_btn = QPushButton("启动 API")
        self.gpt_sovits_api_toggle_btn.setObjectName("toggle_gpt_sovits_api_button")
        self.gpt_sovits_api_toggle_btn.setAccessibleName("Toggle local GPT-SoVITS API")
        self.gpt_sovits_api_toggle_btn.setToolTip("由项目启动或停止本地 GPT-SoVITS 9880 API")
        self.gpt_sovits_api_toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.gpt_sovits_api_toggle_btn.setStyleSheet(CHAT_BTN_SMALL)
        self.gpt_sovits_api_toggle_btn.setEnabled(False)
        self.gpt_sovits_api_toggle_btn.clicked.connect(self._toggle_gpt_sovits_api)
        tts_status_row.addWidget(self.gpt_sovits_api_toggle_btn)
        self.conversation_info_layout.addLayout(tts_status_row)

        self.tool_summary_frame = QFrame()
        self.tool_summary_frame.setObjectName("tool_summary_frame")
        self.tool_summary_frame.setAccessibleName("Tool summary")
        self.tool_summary_frame.setVisible(False)
        self.tool_summary_frame.setStyleSheet("""
            QFrame#tool_summary_frame {
                background-color: rgba(247, 248, 243, 200);
                border-top: 1px solid rgba(116, 137, 118, 50);
                border-bottom: 1px solid rgba(116, 137, 118, 50);
            }
        """)
        tool_summary_layout = QVBoxLayout(self.tool_summary_frame)
        tool_summary_layout.setContentsMargins(12, 6, 12, 6)
        tool_summary_layout.setSpacing(6)

        tool_summary_header = QHBoxLayout()
        tool_summary_header.setContentsMargins(0, 0, 0, 0)
        tool_summary_header.setSpacing(8)

        self.tool_summary_count_label = QLabel("")
        self.tool_summary_count_label.setStyleSheet(
            "color: rgba(35, 48, 57, 150); font-size: 11px; background: transparent;"
        )
        tool_summary_header.addWidget(self.tool_summary_count_label, stretch=1)

        self.tool_summary_toggle_btn = QPushButton("展开工具摘要")
        self.tool_summary_toggle_btn.setObjectName("tool_summary_toggle_button")
        self.tool_summary_toggle_btn.setAccessibleName("Toggle tool summary")
        self.tool_summary_toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.tool_summary_toggle_btn.setStyleSheet(CHAT_BTN_SMALL)
        self.tool_summary_toggle_btn.clicked.connect(self._toggle_tool_summary_details)
        tool_summary_header.addWidget(self.tool_summary_toggle_btn)
        tool_summary_layout.addLayout(tool_summary_header)

        self.tool_summary_details_widget = QWidget()
        self.tool_summary_details_widget.setVisible(False)
        self.tool_summary_details_layout = QVBoxLayout(self.tool_summary_details_widget)
        self.tool_summary_details_layout.setContentsMargins(0, 0, 0, 0)
        self.tool_summary_details_layout.setSpacing(4)
        self.tool_summary_scroll_area = QScrollArea()
        self.tool_summary_scroll_area.setWidgetResizable(True)
        self.tool_summary_scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.tool_summary_scroll_area.setMaximumHeight(180)
        self.tool_summary_scroll_area.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self.tool_summary_scroll_area.setWidget(self.tool_summary_details_widget)
        tool_summary_layout.addWidget(self.tool_summary_scroll_area)

        self.conversation_info_layout.addWidget(self.tool_summary_frame)

        # 输入区域（对话框内部底部，瘦身单行：输入框 + 发送 + ⋯）
        self.input_frame = QFrame()
        self.input_frame.setObjectName("chat_input_frame")
        self.input_frame.setStyleSheet("""
            QFrame#chat_input_frame {
                background: transparent;
                border: none;
            }
        """)
        input_layout = QHBoxLayout(self.input_frame)
        input_layout.setContentsMargins(14, 6, 14, 8)
        input_layout.setSpacing(8)

        self.input_edit = QLineEdit()
        self.input_edit.setObjectName("chat_input")
        self.input_edit.setAccessibleName("Chat input")
        self.input_edit.setPlaceholderText("说点什么吧…（Enter 发送）")
        self.input_edit.setStyleSheet(CHAT_INPUT_STYLE)
        self.input_edit.setFixedHeight(38)
        self.input_edit.returnPressed.connect(self._on_send)
        input_layout.addWidget(self.input_edit, stretch=1)

        self.send_btn = QPushButton("发送")
        self.send_btn.setObjectName("send_button")
        self.send_btn.setAccessibleName("Send message")
        self.send_btn.setFixedHeight(38)
        self.send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_btn.setStyleSheet(CHAT_BTN_PRIMARY)
        self.send_btn.clicked.connect(self._on_send)
        input_layout.addWidget(self.send_btn)
        self.stop_btn = QPushButton("停止")
        self.stop_btn.setObjectName("stop_reply_button")
        self.stop_btn.setAccessibleName("Stop reply and audio")
        self.stop_btn.setFixedHeight(38)
        self.stop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.stop_btn.setStyleSheet(CHAT_BTN_NORMAL)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setToolTip("停止当前回复、语音和图片等待")
        self.stop_btn.clicked.connect(self.stop_requested.emit)
        input_layout.addWidget(self.stop_btn)

        self.menu_btn = QPushButton("⋯")
        set_button_icon(self.menu_btn, "more", 18)
        self.menu_btn.setObjectName("action_menu_button")
        self.menu_btn.setAccessibleName("More actions")
        self.menu_btn.setToolTip("更多操作")
        self.menu_btn.setFixedSize(38, 38)
        self.menu_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.menu_btn.setStyleSheet(CHAT_INPUT_ROW_ICON_BTN)
        self.menu_btn.clicked.connect(self._show_action_menu)
        input_layout.addWidget(self.menu_btn)

        # 隐藏的功能按钮（保留属性引用，供 set_conversation_actions_enabled 使用）
        # ↻ 重发已从输入行收编进 ⋯ 菜单，此处仅作状态持有与信号入口
        self.reroll_btn = QPushButton("↻", self)
        set_button_icon(self.reroll_btn, "refresh", 18)
        self.reroll_btn.setObjectName("reroll_button")
        self.reroll_btn.setAccessibleName("Reroll last message")
        self.reroll_btn.setToolTip("重发上一条消息")
        self.reroll_btn.setVisible(False)
        self.reroll_btn.clicked.connect(self._confirm_reroll_requested)

        self.clear_btn = QPushButton("清空", self)
        self.clear_btn.setObjectName("clear_chat_button")
        self.clear_btn.setAccessibleName("Clear chat")
        self.clear_btn.setVisible(False)
        self.clear_btn.clicked.connect(self.clear_requested.emit)

        self.open_cg_generated_dir_btn = QPushButton("CG目录", self)
        self.open_cg_generated_dir_btn.setObjectName("open_cg_generated_dir_button")
        self.open_cg_generated_dir_btn.setAccessibleName("Open CG generated directory")
        self.open_cg_generated_dir_btn.setVisible(False)
        self.open_cg_generated_dir_btn.clicked.connect(self.open_cg_generated_dir)

        self.session_btn = QPushButton("会话", self)
        self.session_btn.setObjectName("session_manager_button")
        self.session_btn.setAccessibleName("Session manager")
        self.session_btn.setVisible(False)
        self.session_btn.clicked.connect(self._open_session_manager)

        chat_layout.addWidget(self.input_frame)
        self.chat_layout = chat_layout

        # 组装悬浮对话单元：上玻璃（台词）+ 下玻璃（临时内容 + 输入行）
        panel_layout.addWidget(chat_container)
        self.dialog_unit.set_content(panel)

        # 无边框窗口的 8 向边缘拖拽缩放（与空白处拖拽移动共存）
        self._resize_controller = FramelessResizeController(self)

        # ── 常驻界面开关（◉/◎）：24px 小圆钮，永远浮于右上角，
        #    点击手动切换「完整 UI ↔ 只留立绘」，显隐完全由用户掌控 ──
        self.companion_toggle_btn = QPushButton("◉", self)
        set_button_icon(self.companion_toggle_btn, "eye", 14, light=True)
        self.companion_toggle_btn.setObjectName("companion_toggle_button")
        self.companion_toggle_btn.setAccessibleName("Toggle interface visibility")
        self.companion_toggle_btn.setToolTip("收起界面，只留立绘")
        self.companion_toggle_btn.setFixedSize(24, 24)
        self.companion_toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.companion_toggle_btn.setStyleSheet(CHAT_COMPANION_TOGGLE_BTN)
        self.companion_toggle_btn.clicked.connect(self.toggle_ui_visibility)
        self.companion_toggle_btn.raise_()
        self._position_companion_toggle()

    # ── 界面显隐（手动切换） ──────────────────────────────
    def _position_companion_toggle(self) -> None:
        """把常驻开关钉在顶栏按钮组的最左边，
        与 ✕ 保持距离避免误触关闭；与 40px 按钮垂直居中对齐。"""
        top_group_width = 5 * 40 + 4 * 6
        x = self.width() - 12 - top_group_width - 6 - self.companion_toggle_btn.width()
        # 顶栏按钮：上边距 10，高 40 → 中线 y=30；24px 开关居中即 y=18。
        self.companion_toggle_btn.move(x, 10 + (40 - self.companion_toggle_btn.height()) // 2)

    def toggle_ui_visibility(self) -> None:
        """切换界面显隐：完整 UI ↔ 只留立绘与常驻开关。"""
        self._set_ui_visible(not self._ui_visible)

    def _set_ui_visible(self, visible: bool) -> None:
        if self._ui_visible == visible and self.overlay_layer.isVisible() == visible:
            return
        self._ui_visible = visible
        self._sync_companion_toggle()
        self._animate_overlay_visibility(visible)

    def _show_ui(self) -> None:
        """她有东西要展示时（新台词/选项/流式回复）自动展开界面。"""
        if not self._ui_visible:
            self._set_ui_visible(True)

    def _sync_companion_toggle(self) -> None:
        set_button_icon(self.companion_toggle_btn, "eye" if self._ui_visible else "eye-off", 14, light=True)
        self.companion_toggle_btn.setToolTip("收起界面，只留立绘" if self._ui_visible else "展开界面")

    def _animate_overlay_visibility(self, visible: bool) -> None:
        """overlay 层的快速淡入/淡出；淡出完成后隐藏，立绘层不参与。"""
        if self._overlay_anim is not None:
            self._overlay_anim.stop()
            self._overlay_anim = None
        from ui import motion
        if motion.reduced_motion():
            self.overlay_layer.setGraphicsEffect(None)
            self.overlay_layer.setVisible(visible)
            return
        effect = self.overlay_layer.graphicsEffect()
        if not isinstance(effect, QGraphicsOpacityEffect):
            effect = QGraphicsOpacityEffect(self.overlay_layer)
            effect.setOpacity(1.0 if self.overlay_layer.isVisible() else 0.0)
            self.overlay_layer.setGraphicsEffect(effect)
        if visible:
            self.overlay_layer.setVisible(True)
        animation = QPropertyAnimation(effect, b"opacity", self)
        animation.setDuration(motion.duration(motion.OVERLAY))
        animation.setStartValue(effect.opacity())
        animation.setEndValue(1.0 if visible else 0.0)
        if not visible:
            animation.finished.connect(lambda: self.overlay_layer.setVisible(False))
        animation.finished.connect(self._clear_overlay_animation)
        self._overlay_anim = animation
        animation.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)

    def _clear_overlay_animation(self) -> None:
        self._overlay_anim = None

    def refresh_motion_preferences(self) -> None:
        from ui import motion
        if motion.reduced_motion() and self._overlay_anim is not None:
            self._overlay_anim.stop()
            self._overlay_anim = None
            self.overlay_layer.setGraphicsEffect(None)
            self.overlay_layer.setVisible(self._ui_visible)

    def _sync_dialog_info_toggle(self, *, expanded: bool) -> None:
        set_button_icon(self.dialog_info_toggle_btn, "close" if expanded else "info", 16)
        self.dialog_info_toggle_btn.setToolTip("收起运行过程" if expanded else "查看运行过程与服务状态")

    def _clear_dialog_info_click_suppression(self) -> None:
        self._suppress_next_dialog_info_click = False

    @staticmethod
    def _conversation_info_popup_geometry(anchor_rect: QRect, popup_size: QSize, screen_rect: QRect) -> QRect:
        gap = 4
        width = min(popup_size.width(), screen_rect.width())
        height = min(popup_size.height(), screen_rect.height())
        x = anchor_rect.right() - width + 1
        below_y = anchor_rect.bottom() + 1 + gap
        above_y = anchor_rect.top() - height - gap
        y = above_y if below_y + height > screen_rect.bottom() + 1 else below_y
        max_x = screen_rect.right() - width + 1
        max_y = screen_rect.bottom() - height + 1
        return QRect(
            min(max(x, screen_rect.left()), max_x),
            min(max(y, screen_rect.top()), max_y),
            width,
            height,
        )

    def _toggle_conversation_info_popup(self) -> None:
        popup = self.conversation_info_popup
        if self._suppress_next_dialog_info_click:
            self._suppress_next_dialog_info_click = False
            return
        if popup.isVisible():
            popup.hide()
            self._sync_dialog_info_toggle(expanded=False)
            return
        self.refresh_gpt_sovits_connection_status()
        popup.adjustSize()
        width = max(420, min(self.current_message_frame.width(), 520))
        popup.resize(width, popup.sizeHint().height())
        anchor_top_left = self.dialog_info_toggle_btn.mapToGlobal(self.dialog_info_toggle_btn.rect().topLeft())
        anchor_rect = QRect(anchor_top_left, self.dialog_info_toggle_btn.size())
        screen = QApplication.screenAt(anchor_rect.center()) or QApplication.primaryScreen()
        popup.setGeometry(self._conversation_info_popup_geometry(anchor_rect, popup.size(), screen.availableGeometry()))
        self._sync_dialog_info_toggle(expanded=True)
        popup.show()

    def configure_tts_connection_status(self, provider: str, server_url: str) -> None:
        """Configure monitoring and the optional local API process switch."""
        from tts.api_process import GPTSoVITSApiProcessController, is_managed_local_api_url

        self._gpt_sovits_server_url = server_url.strip()
        self._gpt_sovits_api_manageable = (
            provider == "gpt-sovits" and is_managed_local_api_url(self._gpt_sovits_server_url)
        )
        if self._gpt_sovits_api_manageable and self._gpt_sovits_api_controller is None:
            project_root = Path(__file__).resolve().parents[2]
            self._gpt_sovits_api_controller = GPTSoVITSApiProcessController(project_root, self)
            self._gpt_sovits_api_controller.state_changed.connect(self._on_gpt_sovits_api_process_state)

        if provider != "gpt-sovits":
            if self._gpt_sovits_monitor is not None:
                self._gpt_sovits_monitor.stop()
            self._set_gpt_sovits_connection_status("disabled", "")
            return
        if not self._gpt_sovits_server_url:
            if self._gpt_sovits_monitor is not None:
                self._gpt_sovits_monitor.stop()
            self._set_gpt_sovits_connection_status("not_configured", "尚未配置 GPT-SoVITS 服务地址")
            return

        if self._gpt_sovits_monitor is None:
            from tts.connection_monitor import GPTSoVITSConnectionMonitor

            self._gpt_sovits_monitor = GPTSoVITSConnectionMonitor(self)
            self._gpt_sovits_monitor.status_changed.connect(self._set_gpt_sovits_connection_status)
        self._gpt_sovits_monitor.configure(self._gpt_sovits_server_url)
        self._set_gpt_sovits_connection_status("unknown", "打开倒三角或点击刷新时检查连接")

    def refresh_gpt_sovits_connection_status(self) -> None:
        if self._gpt_sovits_monitor is not None:
            self._gpt_sovits_monitor.check_now()

    def _set_gpt_sovits_connection_status(self, state: str, detail: str) -> None:
        if (
            state == "disconnected"
            and self._gpt_sovits_api_controller is not None
            and self._gpt_sovits_api_controller.is_running()
        ):
            state = "starting"
            detail = "GPT-SoVITS API 进程正在加载模型"
        self._gpt_sovits_connection_state = state
        if state == "connected":
            self._gpt_sovits_startup_probe_timer.stop()
        labels = {
            "connected": "GPT-SoVITS：● 已连接",
            "checking": "GPT-SoVITS：◌ 检查中…",
            "unknown": "GPT-SoVITS：未检查",
            "starting": "GPT-SoVITS：◌ 正在启动…",
            "stopping": "GPT-SoVITS：◌ 正在停止…",
            "disconnected": "GPT-SoVITS：● 未连接",
            "not_configured": "GPT-SoVITS：未配置",
            "disabled": "GPT-SoVITS：未启用",
        }
        self.gpt_sovits_status_label.setText(labels.get(state, labels["disconnected"]))
        self.gpt_sovits_status_label.setToolTip(detail or self._gpt_sovits_server_url)
        self._apply_gpt_sovits_status_style(state)
        self._sync_gpt_sovits_api_toggle()

    def _apply_gpt_sovits_status_style(self, state: str) -> None:
        color = {
            "connected": "rgba(82, 111, 88, 225)",
            "checking": "rgba(147, 102, 35, 220)",
            "unknown": "rgba(35, 48, 57, 135)",
            "starting": "rgba(147, 102, 35, 220)",
            "stopping": "rgba(147, 102, 35, 220)",
            "disconnected": "rgba(173, 81, 74, 225)",
            "not_configured": "rgba(173, 81, 74, 200)",
            "disabled": "rgba(35, 48, 57, 135)",
        }.get(state, "rgba(173, 81, 74, 225)")
        self.gpt_sovits_status_label.setStyleSheet(
            f"color: {color}; font-size: 11px; padding: 2px 0; background: transparent; border: none;"
        )

    def _toggle_gpt_sovits_api(self) -> None:
        controller = self._gpt_sovits_api_controller
        if controller is None or not self._gpt_sovits_api_manageable:
            return
        if controller.is_running():
            controller.stop()
        elif self._gpt_sovits_connection_state != "connected":
            controller.start()

    def _on_gpt_sovits_api_process_state(self, state: str, detail: str) -> None:
        if state in {"starting", "running"}:
            self._set_gpt_sovits_connection_status("starting", detail)
            self._gpt_sovits_startup_probe_timer.start()
            QTimer.singleShot(250, self.refresh_gpt_sovits_connection_status)
        elif state == "stopping":
            self._gpt_sovits_startup_probe_timer.stop()
            self._set_gpt_sovits_connection_status("stopping", detail)
        elif state in {"stopped", "error"}:
            self._gpt_sovits_startup_probe_timer.stop()
            self._set_gpt_sovits_connection_status("disconnected", detail)
            QTimer.singleShot(250, self.refresh_gpt_sovits_connection_status)

    def _sync_gpt_sovits_api_toggle(self) -> None:
        button = self.gpt_sovits_api_toggle_btn
        controller = self._gpt_sovits_api_controller
        if not self._gpt_sovits_api_manageable:
            button.setText("外部 API" if self._gpt_sovits_server_url else "启动 API")
            button.setEnabled(False)
            return
        if controller is not None and controller.is_running():
            button.setText("停止 API")
            button.setEnabled(True)
            return
        if self._gpt_sovits_connection_state == "connected":
            button.setText("外部运行")
            button.setEnabled(False)
        elif self._gpt_sovits_connection_state == "checking":
            button.setText("检查中")
            button.setEnabled(False)
        else:
            button.setText("启动 API")
            button.setEnabled(True)

    def eventFilter(self, watched, event):
        if (
            watched is getattr(self, "conversation_info_popup", None)
            and event.type() == QEvent.Type.Hide
            and not getattr(self, "_closing", True)
        ):
            toggle_bounds = self.dialog_info_toggle_btn.rect()
            cursor_in_toggle = self.dialog_info_toggle_btn.mapFromGlobal(QCursor.pos())
            self._suppress_next_dialog_info_click = toggle_bounds.contains(cursor_in_toggle)
            if self._suppress_next_dialog_info_click:
                QTimer.singleShot(150, self._clear_dialog_info_click_suppression)
            self._sync_dialog_info_toggle(expanded=False)
        return super().eventFilter(watched, event)

    def closeEvent(self, event):
        prepare_close = getattr(self, "prepare_runtime_close", None)
        if callable(prepare_close) and not prepare_close():
            event.ignore()
            return
        self._closing = True
        self._gpt_sovits_startup_probe_timer.stop()
        if self._gpt_sovits_api_controller is not None:
            self._gpt_sovits_api_controller.shutdown()
        super().closeEvent(event)

    def _confirm_reroll_requested(self):
        """二次确认后再触发重发上一条消息。"""
        confirm = QMessageBox.question(
            self,
            "确认重发",
            "确定要重发上一条消息吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self.reroll_requested.emit()

    def _show_action_menu(self):
        """弹出次要功能菜单。"""
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: rgba(247, 248, 243, 245);
                border: 1px solid rgba(116, 137, 118, 80);
                border-radius: 10px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 24px;
                border-radius: 6px;
                color: #233039;
            }
            QMenu::item:selected {
                background-color: rgba(116, 137, 118, 40);
                color: #607B65;
            }
        """)

        action_reroll = QAction("重发上一条消息", self)
        action_reroll.setEnabled(self.reroll_btn.isEnabled())
        action_reroll.triggered.connect(self._confirm_reroll_requested)
        menu.addAction(action_reroll)

        action_clear = QAction("清空对话", self)
        action_clear.triggered.connect(self.clear_requested.emit)
        menu.addAction(action_clear)

        action_cg = QAction("CG 目录", self)
        action_cg.triggered.connect(self.open_cg_generated_dir)
        menu.addAction(action_cg)

        action_session = QAction("会话管理", self)
        action_session.triggered.connect(self._open_session_manager)
        menu.addAction(action_session)

        menu.addSeparator()

        # 在菜单按钮左下方弹出
        btn_pos = self.menu_btn.mapToGlobal(self.menu_btn.rect().bottomLeft())
        menu.exec(btn_pos)

    # --- 拖拽移动窗口（无边框需要） ---
    def _sprite_click_at(self, position) -> bool:
        # The overlay receives stage clicks too; UI surfaces must not poke the character.
        for surface in (self.dialog_unit, self.companion_toggle_btn, self.history_btn,
                        self.background_btn, self.settings_btn, self.minimize_btn, self.close_btn):
            if surface.isVisible() and surface.rect().contains(surface.mapFrom(self, position)):
                return False
        return self.sprite_widget.hit_test(self.sprite_widget.mapFrom(self, position))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._sprite_click_origin = (
                event.globalPosition().toPoint() if self._sprite_click_at(event.position().toPoint()) else None
            )
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_pos and event.buttons() & Qt.MouseButton.LeftButton:
            if self._sprite_click_origin is not None:
                distance = (event.globalPosition().toPoint() - self._sprite_click_origin).manhattanLength()
                if distance >= QApplication.startDragDistance():
                    self._sprite_click_origin = None
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        origin = self._sprite_click_origin
        self._sprite_click_origin = None
        self._drag_pos = None
        if event.button() == Qt.MouseButton.LeftButton and origin is not None:
            distance = (event.globalPosition().toPoint() - origin).manhattanLength()
            if distance < QApplication.startDragDistance() and self._sprite_click_at(event.position().toPoint()):
                self.sprite_widget.play_click_bounce()

    # --- 公开接口 ---
    def _on_send(self):
        if self._waiting_for_reply:
            return
        text = self.input_edit.text().strip()
        if not text:
            return
        self._dismiss_options()
        self.input_edit.clear()
        self.add_message(text, is_user=True)
        self.user_message_sent.emit(text)

    def add_message(self, text: str, is_user: bool = False, char_name: str = "", char_color: str = "#f2a0bd"):
        """Show one current dialogue while retaining an ordered internal history."""
        self._show_ui()
        entry = ChatHistoryEntry(text, is_user, char_name, char_color)
        self._message_history.append(entry)
        is_character_line = not is_user and char_name not in _NON_CHARACTER_SPEAKERS
        # 角色台词逐字显示；用户输入、系统/旁白提示直接整句出现。
        self._render_current_message(entry, animate=is_character_line)
        if is_character_line:
            self.sprite_widget.play_speak_hop()

    def _render_current_message(self, entry: ChatHistoryEntry, animate: bool = False) -> None:
        speaker = entry.speaker_name
        self.current_speaker_label.setText(speaker)
        self.current_speaker_label.setVisible(bool(speaker))
        self.current_character_info_label.setText(f"当前角色：{speaker or '未指定'}")
        if animate:
            self.current_message_label.reveal(entry.text)
        else:
            self.current_message_label.setText(entry.text)

    def message_history_snapshot(self) -> list[dict]:
        return [entry.to_snapshot() for entry in self._message_history]

    def _build_chat_history_dialog(self) -> QDialog:
        """构建 mockup 风格的聊天记录浮层：❀ 标题栏 + 气泡对话流。"""
        dialog = QDialog(self)
        dialog.setObjectName("chat_history_dialog")
        dialog.setWindowTitle("聊天记录")
        dialog.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        dialog.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        dialog.resize(360, 520)
        dialog.setStyleSheet("QDialog#chat_history_dialog { background: transparent; }")
        outer = QVBoxLayout(dialog)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        panel = QFrame(dialog)
        panel.setObjectName("history_panel")
        panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        panel.setStyleSheet(HISTORY_PANEL_STYLE)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(0)
        outer.addWidget(panel)

        # 标题栏（mockup: history-titlebar）
        titlebar = QWidget(panel)
        titlebar.setObjectName("history_titlebar")
        titlebar.setStyleSheet(
            "QWidget#history_titlebar { background-color: rgba(116, 137, 118, 13);"
            " border-bottom: 1px solid rgba(116, 137, 118, 46); }"
        )
        titlebar_layout = QHBoxLayout(titlebar)
        titlebar_layout.setContentsMargins(14, 10, 10, 10)
        titlebar_layout.setSpacing(10)
        title = QLabel("❀ 聊天记录")
        title.setObjectName("history_title")
        title.setStyleSheet(HISTORY_TITLE_STYLE)
        titlebar_layout.addWidget(title)
        titlebar_layout.addStretch()
        close_btn = QPushButton("✕")
        close_btn.setObjectName("history_close_button")
        close_btn.setAccessibleName("Close history")
        close_btn.setToolTip("关闭聊天记录")
        close_btn.setFixedSize(30, 30)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(CHAT_ICON_BTN_CLOSE)
        close_btn.clicked.connect(dialog.reject)
        titlebar_layout.addWidget(close_btn)
        panel_layout.addWidget(titlebar)
        dialog._window_drag_controller = WindowDragController(dialog, [titlebar, title])

        history_snapshot = self.message_history_snapshot()
        if not history_snapshot:
            empty = QLabel("还没有聊天记录")
            empty.setObjectName("history_empty_state")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet("color: rgba(35, 48, 57, 140); font-size: 13px; background: transparent;")
            panel_layout.addWidget(empty, stretch=1)
            return dialog

        # 气泡对话流（mockup: chat-log，AI 左 / 用户右）
        scroll = QScrollArea(panel)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical { background: transparent; width: 5px; margin: 0; }
            QScrollBar::handle:vertical { background: rgba(116, 137, 118, 77); border-radius: 2px; min-height: 24px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
        """)
        scroll.viewport().setStyleSheet("background: transparent;")
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        rows = QVBoxLayout(content)
        rows.setContentsMargins(14, 16, 14, 12)
        rows.setSpacing(12)
        for entry in history_snapshot:
            is_user = entry["is_user"]
            bubble_row = QVBoxLayout()
            bubble_row.setSpacing(4)

            speaker = QLabel("你" if is_user else entry["char_name"])
            speaker.setObjectName("history_bubble_name")
            speaker.setStyleSheet(
                f"color: {'rgba(35, 48, 57, 140)' if is_user else '#607B65'};"
                " font-size: 11px; background: transparent; padding: 0 4px;"
            )
            text = HistoryBubbleLabel(entry["text"])
            text.setObjectName("history_message_text")
            text.setMaximumWidth(280)
            text.setStyleSheet(HISTORY_BUBBLE_USER if is_user else HISTORY_BUBBLE_AI)

            align = Qt.AlignmentFlag.AlignRight if is_user else Qt.AlignmentFlag.AlignLeft
            bubble_row.addWidget(speaker, alignment=align)
            bubble_row.addWidget(text, alignment=align)
            rows.addLayout(bubble_row)
        rows.addStretch()
        rows.activate()
        content.setMinimumHeight(rows.sizeHint().height())
        scroll.setWidget(content)
        panel_layout.addWidget(scroll)
        return dialog

    def _open_chat_history(self) -> None:
        self._build_chat_history_dialog().exec()

    def add_cg_preview(self, image_path: str, title: str = "CG") -> bool:
        """追加一张生成 CG 预览图到聊天区。"""
        if not image_path:
            self.set_reply_status("CG 预览失败：图片路径为空", error=True)
            return False
        if not os.path.exists(image_path):
            self.set_reply_status(f"CG 预览失败：图片文件不存在：{image_path}", error=True)
            return False

        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            self.set_reply_status(f"CG 预览失败：图片无法加载：{image_path}", error=True)
            return False

        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.NoFrame)
        frame.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        frame.setStyleSheet("""
            QFrame {
                background-color: rgba(247, 248, 243, 230);
                border: 1px solid rgba(116, 137, 118, 60);
                border-radius: 16px;
                margin-left: 8px;
                margin-right: 60px;
            }
        """)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(6)

        display_title = f"{title} · {Path(image_path).name}"
        title_label = QLabel(display_title)
        title_label.setStyleSheet(
            "color: #607B65; font-weight: bold; font-size: 13px; background: transparent;"
        )
        layout.addWidget(title_label)

        image_label = CGPreviewLabel(image_path, self._open_cg_preview)
        image_label.set_preview_width(self._cg_preview_width())
        layout.addWidget(image_label)

        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(8)

        open_image_btn = QPushButton("打开图片")
        open_image_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_image_btn.setStyleSheet(CHAT_BTN_NORMAL)
        open_image_btn.clicked.connect(lambda checked=False, path=image_path: self._open_cg_image_file(path))
        button_layout.addWidget(open_image_btn)

        copy_path_btn = QPushButton("复制路径")
        copy_path_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        copy_path_btn.setStyleSheet(open_image_btn.styleSheet())
        copy_path_btn.clicked.connect(lambda checked=False, path=image_path: self._copy_cg_image_path(path))
        button_layout.addWidget(copy_path_btn)

        button_layout.addStretch()
        layout.addLayout(button_layout)

        self.temporary_layout.addWidget(frame)
        play_entrance(frame, self)
        self.scroll_area.setVisible(True)
        self._cg_preview_labels.append(image_label)
        self.last_cg_preview_path = image_path
        QTimer.singleShot(50, self._scroll_to_bottom)
        return True

    def add_card(self, markdown: str, title: str = "资料卡"):
        """追加一张 Markdown 资料卡到聊天区；台词框只保留角色的“说”。"""
        from ui.chat_ui.info_card import InfoCardWidget

        if not (markdown or "").strip():
            return None
        self._show_ui()
        card = InfoCardWidget(
            markdown,
            title=title,
            open_url=self._open_card_link,
            copy_text=self._copy_card_text,
        )
        self.temporary_layout.addWidget(card)
        play_entrance(card, self)
        self.scroll_area.setVisible(True)
        # 聊天记录里只放一行提示，完整内容看卡片本身。
        first_line = next((line.strip("# ").strip() for line in markdown.splitlines() if line.strip()), "")
        self._message_history.append(ChatHistoryEntry(f"[{title}] {first_line}", False, title, "#84C2D5"))
        QTimer.singleShot(50, self._scroll_to_bottom)
        return card

    def _open_card_link(self, url: str) -> bool:
        from ui.chat_ui.info_card import is_safe_external_url

        if not is_safe_external_url(url):
            self.set_reply_status(f"已拦截非网页链接：{url}", error=True)
            return False
        return bool(QDesktopServices.openUrl(QUrl(url)))

    def _copy_card_text(self, text: str) -> None:
        self._copy_text_to_clipboard(text)
        self.set_reply_status("已复制资料卡内容")

    def _cg_preview_width(self) -> int:
        """返回聊天区 CG 缩略图目标宽度。"""
        return max(240, min(520, self.scroll_area.viewport().width() - 120))

    def _refresh_cg_preview_sizes(self) -> None:
        """刷新仍在窗口中的 CG 缩略图尺寸，并清理已移除的 label。"""
        width = self._cg_preview_width()
        live_labels = []
        for label in self._cg_preview_labels:
            if label.parent() is None:
                continue
            label.set_preview_width(width)
            live_labels.append(label)
        self._cg_preview_labels = live_labels

    def _temporary_area_max_height(self) -> int:
        """临时内容区（资料卡/选项/CG）随窗口变高，但不超过窗口约 38%，给立绘留出舞台。"""
        return max(180, min(340, int(self.height() * 0.38)))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.scroll_area.setMaximumHeight(self._temporary_area_max_height())
        self._refresh_cg_preview_sizes()
        self._position_companion_toggle()

    def _build_cg_preview_dialog(self, image_path: str):
        """构建 CG 大图预览 dialog；图片不可加载时返回 None。"""
        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            return None

        dialog = QDialog(self)
        dialog.setWindowTitle(f"CG 预览 - {Path(image_path).name}")
        layout = QVBoxLayout(dialog)

        image_label = QLabel()
        image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        screen = self.screen()
        max_size = screen.availableGeometry().size() if screen is not None else QSize(960, 720)
        scaled = pixmap.scaled(
            int(max_size.width() * 0.8),
            int(max_size.height() * 0.8),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        image_label.setPixmap(scaled)
        layout.addWidget(image_label)
        return dialog

    def _open_cg_preview(self, image_path: str) -> None:
        """打开 CG 大图预览。"""
        dialog = self._build_cg_preview_dialog(image_path)
        if dialog is None:
            self.set_reply_status(f"CG 预览打开失败：{image_path}", error=True)
            return
        dialog.exec()

    def _open_cg_image_file(self, image_path: str) -> bool:
        """使用系统默认图片查看器打开 CG 图片文件。"""
        path = Path(image_path)
        try:
            opened = self._open_local_path(path)
        except OSError as exc:
            self.set_reply_status(f"打开 CG 图片失败：{path}（{exc}）", error=True)
            return False

        if opened:
            self.set_reply_status(f"已打开 CG 图片：{path}")
            return True
        self.set_reply_status(f"打开 CG 图片失败：{path}", error=True)
        return False

    def _copy_cg_image_path(self, image_path: str) -> None:
        """复制 CG 图片路径到剪贴板。"""
        self._copy_text_to_clipboard(image_path)
        self.set_reply_status(f"已复制 CG 图片路径：{image_path}")

    def open_cg_generated_dir(self) -> bool:
        """创建并打开本地 CG 生成目录。"""
        generated_dir = Path("data") / "cg" / "generated"
        try:
            generated_dir.mkdir(parents=True, exist_ok=True)
            generated_dir = generated_dir.resolve()
        except OSError as exc:
            self.set_reply_status(f"打开 CG 生成目录失败：{generated_dir}（{exc}）", error=True)
            return False

        try:
            opened = self._open_local_path(generated_dir)
        except OSError as exc:
            self.set_reply_status(f"打开 CG 生成目录失败：{generated_dir}（{exc}）", error=True)
            return False

        if opened:
            self.set_reply_status(f"已打开 CG 生成目录：{generated_dir}")
            return True
        self.set_reply_status(f"打开 CG 生成目录失败：{generated_dir}", error=True)
        return False

    def _open_local_path(self, path: Path) -> bool:
        """打开本地路径；单独封装便于测试 monkeypatch，避免真实启动文件管理器。"""
        return QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _copy_text_to_clipboard(self, text: str) -> None:
        """复制文本到系统剪贴板；单独封装便于测试。"""
        QApplication.clipboard().setText(text)

    # --- 流式输出支持 ---
    def begin_stream(self, char_name: str = "", char_color: str = "#f2a0bd"):
        """Begin one provisional history entry, updated in place by chunks."""
        self._show_ui()
        entry = ChatHistoryEntry("", False, char_name, char_color)
        self._message_history.append(entry)
        self._stream_history_index = len(self._message_history) - 1
        self._stream_text = ""
        self._render_current_message(entry)
        self._sync_thinking_indicator()

    def append_stream(self, chunk: str):
        """Append text to the current stream without creating duplicate history."""
        if self._stream_history_index is None:
            return
        self._stream_text += chunk
        current = self._message_history[self._stream_history_index]
        entry = ChatHistoryEntry(self._stream_text, False, current.char_name, current.char_color)
        self._message_history[self._stream_history_index] = entry
        self._render_current_message(entry)
        self._sync_thinking_indicator()

    def end_stream(self):
        """Finalize the stream, removing an empty provisional entry."""
        if self._stream_history_index is not None and not self._stream_text:
            self._message_history.pop(self._stream_history_index)
            if self._message_history:
                self._render_current_message(self._message_history[-1])
            else:
                self._show_active_character_name()
                self.current_character_info_label.setText("当前角色：未指定")
                self.current_message_label.clear()
        self._stream_history_index = None
        self._stream_text = ""

    def discard_stream(self):
        """Discard protocol-level stream text before rendering parsed dialogue."""
        if self._stream_history_index is None:
            return
        self._message_history.pop(self._stream_history_index)
        self._stream_history_index = None
        self._stream_text = ""
        if self._message_history:
            self._render_current_message(self._message_history[-1])
        else:
            self._show_active_character_name()
            self.current_character_info_label.setText("当前角色：未指定")
            self.current_message_label.clear()
        self._sync_thinking_indicator()

    def _scroll_to_bottom(self):
        vbar = self.scroll_area.verticalScrollBar()
        vbar.setValue(vbar.maximum())

    def set_sprite(self, image_path: str, scale: float = 1.0):
        """设置立绘；角色配置缩放与用户的滚轮缩放相乘生效。"""
        self._char_sprite_scale = scale
        self.sprite_widget.set_sprite(image_path, scale * self._user_sprite_zoom)

    def clear_sprite(self) -> None:
        self._char_sprite_scale = 1.0
        self.sprite_widget.clear_sprite()

    def wheelEvent(self, event):
        """Ctrl + 滚轮：自由缩放立绘（0.2x–1.0x）。"""
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            notches = event.angleDelta().y() / 120
            if notches:
                self._adjust_sprite_zoom(notches)
                event.accept()
                return
        super().wheelEvent(event)

    def _adjust_sprite_zoom(self, notches: float) -> None:
        """按滚轮格数调整用户缩放倍率，并立即应用到当前立绘。"""
        zoom = self._user_sprite_zoom + notches * 0.06
        self._user_sprite_zoom = max(0.2, min(1.0, zoom))
        self.sprite_widget.set_scale(self._char_sprite_scale * self._user_sprite_zoom)

    def post_options(self, options: list):
        """显示可点击的选项按钮。"""
        self._dismiss_options()
        options = [str(option).strip() for option in options if option is not None and str(option).strip()]
        if not options:
            return
        self._show_ui()
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.NoFrame)
        frame.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        frame.setObjectName("choice_group")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)

        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        action_style = """
            QPushButton { background: transparent; color: #657169; border: none;
                          border-radius: 4px; font-size: 12px; padding: 2px 6px; }
            QPushButton:hover { color: #526F58; text-decoration: underline; }
            QPushButton:pressed { color: #233039; }
            QPushButton:focus { background: rgba(116, 137, 118, 25); }
        """
        custom = QPushButton("自定义回复")
        custom.setObjectName("choice_custom_reply_button")
        custom.setAccessibleName("Write a custom reply")
        custom.setToolTip("收起选项，在下方输入自己的回复")
        custom.setCursor(Qt.CursorShape.PointingHandCursor)
        custom.setStyleSheet(action_style)
        custom.setFixedHeight(24)
        custom.clicked.connect(lambda: self._on_custom_reply_clicked(frame))
        controls.addWidget(custom)
        controls.addStretch()
        skip = QPushButton("跳过")
        skip.setObjectName("choice_skip_button")
        skip.setAccessibleName("Skip suggested choices")
        skip.setToolTip("收起选项，不发送消息")
        skip.setCursor(Qt.CursorShape.PointingHandCursor)
        skip.setStyleSheet(action_style)
        skip.setFixedHeight(24)
        skip.clicked.connect(lambda: self._dismiss_options(frame))
        controls.addWidget(skip)
        layout.addLayout(controls)

        for index, opt in enumerate(options, start=1):
            btn = QPushButton(f"{index}.  {opt}")
            btn.setObjectName("choice_button")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(CHAT_CHOICE_BTN)
            btn.setEnabled(not self._waiting_for_reply)
            btn.clicked.connect(lambda checked, text=opt: self._on_option_clicked(text, frame))
            layout.addWidget(btn)

        self._choice_group = frame
        self.temporary_layout.addWidget(frame)
        play_entrance(frame, self)
        self.scroll_area.setVisible(True)
        QTimer.singleShot(50, self._scroll_to_bottom)

    def _dismiss_options(self, frame=None):
        """Remove only the current choices, retaining cards, images and drafts."""
        current = self._choice_group
        if current is None or (frame is not None and frame is not current):
            return False
        self._choice_group = None
        animation = getattr(current, "_entrance_group", None)
        if animation is not None:
            animation.stop()
            animation.deleteLater()
            current._entrance_group = None
        current.setEnabled(False)
        current.hide()
        self.temporary_layout.removeWidget(current)
        current.deleteLater()
        self.scroll_area.setVisible(self.temporary_layout.count() > 0)
        return True

    def _on_custom_reply_clicked(self, frame):
        if not self._dismiss_options(frame):
            return
        self._focus_custom_reply_after_waiting = self._waiting_for_reply
        if not self._waiting_for_reply:
            self.input_edit.setFocus(Qt.FocusReason.OtherFocusReason)

    def _on_option_clicked(self, text: str, frame: QFrame):
        """Send a current suggestion once, using the normal waiting-state guard."""
        if self._waiting_for_reply or not self._dismiss_options(frame):
            return
        self.add_message(text, is_user=True)
        self.user_message_sent.emit(text)

    def set_waiting_for_reply(self, waiting: bool):
        """设置请求中状态：等待回复时禁用输入和发送，避免连续发送导致队列/气泡错乱。"""
        was_waiting = self._waiting_for_reply
        self._waiting_for_reply = waiting
        if waiting and not was_waiting:
            self._runtime_activity_entries.clear()
            self._last_runtime_activity_text = ""
            self._render_runtime_activity_entries()
            self._set_runtime_state("running")
            self._append_runtime_activity("请求已进入执行队列", state="running")
        elif not waiting and was_waiting and self._runtime_state == "running":
            self._append_runtime_activity("本轮处理完成", state="completed")
            self._set_runtime_state("completed")
            if not self.reply_status_label.text():
                self.reply_status_label.setText("本轮处理完成")
        self.input_edit.setEnabled(not waiting)
        if self._choice_group is not None:
            for button in self._choice_group.findChildren(QPushButton, "choice_button"):
                button.setEnabled(not waiting)
        if not waiting and self._focus_custom_reply_after_waiting:
            self._focus_custom_reply_after_waiting = False
            self.input_edit.setFocus(Qt.FocusReason.OtherFocusReason)
        self.send_btn.setEnabled(not waiting)
        self.send_btn.setText("正在回复..." if waiting else "发送")
        self._sync_thinking_indicator()
        self.set_conversation_actions_enabled(not waiting)
        self.reply_waiting_changed.emit(bool(waiting))

    def _sync_thinking_indicator(self) -> None:
        """等待回复且角色还没开口时，台词框显示跳动的“…”，名牌显示角色名。"""
        thinking = self._waiting_for_reply and not self._stream_text
        if thinking:
            # 跳过尚无内容的流式占位条目，看真正的上一条消息是不是用户说的。
            visible = [
                entry for index, entry in enumerate(self._message_history)
                if not (index == self._stream_history_index and not entry.text)
            ]
            last = visible[-1] if visible else None
            if last is not None and last.is_user:
                speaker = self._thinking_speaker_name()
                self.current_speaker_label.setText(speaker)
                self.current_speaker_label.setVisible(bool(speaker))
                self.current_message_label.setText("")
            else:
                thinking = False
        was_thinking = self.current_message_label.is_thinking()
        self.current_message_label.set_thinking(thinking)
        if was_thinking and not thinking and not self._stream_text and self._message_history:
            # 等待被取消/结束且角色没开口：把台词框恢复成最后一条真实消息。
            last = self._message_history[-1]
            if last.text or self._stream_history_index is None:
                self._render_current_message(last)

    def _thinking_speaker_name(self) -> str:
        for entry in reversed(self._message_history):
            if not entry.is_user and entry.char_name not in _NON_CHARACTER_SPEAKERS:
                return entry.char_name
        return self._active_character_name

    def set_active_character_name(self, name: str) -> None:
        self._active_character_name = name or ""
        self._show_active_character_name()

    def _show_active_character_name(self) -> None:
        self.current_speaker_label.setText(self._active_character_name)
        self.current_speaker_label.setVisible(bool(self._active_character_name))

    def set_character_list(self, characters: list[dict], active_id: str = "") -> None:
        """Use stable character IDs; names are display text and may be duplicated."""
        self._character_items = [dict(item, memory_id=str(item.get("memory_id") or item.get("id")))
                                 for item in characters if item.get("memory_id") or item.get("id")]
        self.set_active_character_id(active_id)

    def set_active_character_id(self, character_id: str) -> None:
        self._active_character_id = str(character_id or "")
        for item in self._character_items:
            if item["memory_id"] == self._active_character_id:
                self.set_active_character_name(str(item.get("name") or "未命名角色"))
                break

    def _show_character_menu(self) -> None:
        if self._waiting_for_reply or not self.current_speaker_label.isEnabled():
            return
        self.character_menu_opening.emit()
        if not self._character_items:
            return
        if self._character_menu is not None:
            self._character_menu.close()
            self._character_menu.deleteLater()
        menu = QMenu(self)
        menu.setObjectName("character_switch_menu")
        menu.setAccessibleName("选择聊天角色")
        menu.setStyleSheet("QMenu { background: #F7F8F3; color: #233039; border: 1px solid #B9C9B9; border-radius: 8px; padding: 5px; } QMenu::item { padding: 8px 28px; border-radius: 5px; } QMenu::item:selected { background: #E4ECE0; } QMenu::indicator:checked { background: #607B65; border-radius: 3px; }")
        for item in self._character_items:
            character_id = str(item["memory_id"])
            action = menu.addAction(str(item.get("name") or "未命名角色"))
            action.setData(character_id)
            action.setCheckable(True)
            action.setChecked(character_id == self._active_character_id)
            action.triggered.connect(lambda _checked=False, identity=character_id: self._request_character(identity))
        self._character_menu = menu
        menu.popup(self.current_speaker_label.mapToGlobal(QPoint(0, 0)) - QPoint(0, menu.sizeHint().height()))

    def _request_character(self, character_id: str) -> None:
        if (not self._waiting_for_reply and self.current_speaker_label.isEnabled()
                and character_id != self._active_character_id
                and any(item["memory_id"] == character_id for item in self._character_items)):
            self.character_requested.emit(character_id)

    def set_conversation_actions_enabled(self, enabled: bool):
        """设置对话管理按钮是否可用。"""
        self.clear_btn.setEnabled(enabled)
        self.reroll_btn.setEnabled(enabled)
        self.open_cg_generated_dir_btn.setEnabled(enabled)
        self.session_btn.setEnabled(enabled)
        self.current_speaker_label.setEnabled(enabled)
        if not enabled and self._character_menu is not None:
            self._character_menu.close()

    def _apply_reply_status_style(self, error: bool = False):
        """应用运行过程当前状态样式。"""
        color = "rgba(173, 81, 74, 230)" if error else "rgba(35, 48, 57, 210)"
        self.reply_status_label.setStyleSheet(
            f"color: {color}; font-size: 11px; padding: 2px 0; background: transparent; border: none;"
        )

    def set_reply_status(self, text: str, error: bool = False):
        """更新当前状态，并把实际运行事件追加到时间线。"""
        self._apply_reply_status_style(error=error)
        self.reply_status_label.setText(text)
        if not text:
            return
        state = "failed" if error else ("running" if self._waiting_for_reply else "completed")
        self._set_runtime_state(state)
        self._append_runtime_activity(text, state=state)

    def _set_runtime_state(self, state: str) -> None:
        state_styles = {
            "idle": ("空闲", "rgba(101, 113, 105, 210)", "rgba(101, 113, 105, 28)"),
            "running": ("运行中", "rgba(96, 123, 101, 240)", "rgba(96, 123, 101, 34)"),
            "completed": ("已完成", "rgba(82, 111, 88, 230)", "rgba(82, 111, 88, 32)"),
            "failed": ("失败", "rgba(173, 81, 74, 235)", "rgba(173, 81, 74, 32)"),
        }
        if state not in state_styles:
            state = "idle"
        self._runtime_state = state
        badge, color, background = state_styles[state]
        self.runtime_state_dot_label.setStyleSheet(
            f"color: {color}; font-size: 10px; background: transparent; border: none;"
        )
        self.runtime_state_badge_label.setText(badge)
        self.runtime_state_badge_label.setStyleSheet(
            f"color: {color}; background-color: {background}; border: 1px solid {color}; "
            "border-radius: 8px; padding: 1px 7px; font-size: 10px;"
        )

    def _append_runtime_activity(self, text: str, *, state: str = "running") -> None:
        normalized = " ".join(str(text).split())
        if not normalized or normalized == self._last_runtime_activity_text:
            return
        self._last_runtime_activity_text = normalized
        self._runtime_activity_entries.append(
            {
                "time": datetime.now().strftime("%H:%M:%S"),
                "text": normalized,
                "state": state,
            }
        )
        self._runtime_activity_entries = self._runtime_activity_entries[-12:]
        self._render_runtime_activity_entries()

    def _render_runtime_activity_entries(self) -> None:
        while self.runtime_activity_layout.count():
            item = self.runtime_activity_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        colors = {
            "idle": "rgba(101, 113, 105, 175)",
            "running": "rgba(96, 123, 101, 220)",
            "completed": "rgba(82, 111, 88, 210)",
            "failed": "rgba(173, 81, 74, 225)",
        }
        for entry in self._runtime_activity_entries:
            safe_time = html.escape(entry["time"])
            safe_text = html.escape(entry["text"])
            color = colors.get(entry["state"], colors["idle"])
            row = QLabel(
                f"<span style='color:{color}'>●</span> "
                f"<span style='color:rgba(35,48,57,105)'>{safe_time}</span>  "
                f"<span style='color:rgba(35,48,57,185)'>{safe_text}</span>"
            )
            row.setTextFormat(Qt.TextFormat.RichText)
            row.setWordWrap(True)
            row.setObjectName("runtime_activity_entry")
            row.setStyleSheet("font-size: 10px; background: transparent; border: none;")
            self.runtime_activity_layout.addWidget(row)
        self.runtime_activity_layout.addStretch()
        QTimer.singleShot(
            0,
            self,
            lambda: self.runtime_activity_scroll_area.verticalScrollBar().setValue(
                self.runtime_activity_scroll_area.verticalScrollBar().maximum()
            ),
        )

    def set_tool_summary_result(self, result: ToolLoopTurnResult | None):
        self._tool_summary_result = result
        if result is None:
            self._tool_summary_expanded = False
        self._apply_tool_summary_view_model(
            build_tool_summary_view_model(result or ToolLoopTurnResult("", [], None), expanded=self._tool_summary_expanded)
            if result is not None
            else ToolSummaryViewModel(
                visible=False,
                expanded=False,
                count_text="",
                toggle_text="展开工具摘要",
                detail_rows=[],
            )
        )
        if result is not None:
            ChatUIWindow._handle_approval_requests(self, result)

    def _handle_approval_requests(self, result: ToolLoopTurnResult) -> None:
        for record in result.invocation_records:
            request = record.approval_request
            if not request:
                continue
            decision_id = str(request["pending_decision_id"])
            command = request.get("command", record.arguments_summary)
            reason = request.get("reason", "该操作具有较高风险")
            choice = QMessageBox.question(
                self,
                "需要批准的终端操作",
                f"Agent 请求执行高风险命令：\n\n{command}\n\n风险说明：{reason}\n\n是否仅允许执行这一次？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            try:
                if choice == QMessageBox.StandardButton.Yes:
                    approve_terminal_decision(decision_id)
                    self.set_reply_status("已批准并执行一次终端操作")
                else:
                    deny_terminal_decision(decision_id)
                    self.set_reply_status("已拒绝终端操作")
            except Exception as exc:
                self.set_reply_status(f"审批处理失败：{exc}", error=True)

    def _toggle_tool_summary_details(self):
        if self._tool_summary_result is None:
            self._tool_summary_expanded = False
            self._apply_tool_summary_view_model(
                ToolSummaryViewModel(
                    visible=False,
                    expanded=False,
                    count_text="",
                    toggle_text="展开工具摘要",
                    detail_rows=[],
                )
            )
            return
        self._tool_summary_expanded = not self._tool_summary_expanded
        self._apply_tool_summary_view_model(
            build_tool_summary_view_model(self._tool_summary_result, expanded=self._tool_summary_expanded)
        )

    def _apply_tool_summary_view_model(self, view_model: ToolSummaryViewModel):
        self.tool_summary_frame.setVisible(view_model.visible)
        self.tool_summary_count_label.setText(view_model.count_text)
        self.tool_summary_toggle_btn.setText(view_model.toggle_text)
        self.tool_summary_details_widget.setVisible(view_model.expanded)
        self._render_tool_summary_detail_rows(view_model.detail_rows)

    def _render_tool_summary_detail_rows(self, rows: list[str]):
        while self.tool_summary_details_layout.count():
            item = self.tool_summary_details_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for row in rows:
            label = QLabel(row)
            label.setWordWrap(True)
            label.setStyleSheet(
                "color: rgba(35, 48, 57, 150); font-size: 11px; background: transparent;"
            )
            self.tool_summary_details_layout.addWidget(label)

    def set_config_notice(self, text: str):
        """Show a configuration warning with an actionable settings hint."""
        suffix = " 请点击下方「设置」补全配置。"
        self.set_reply_status(f"{text}{suffix}" if text else "", error=bool(text))

    def clear_reply_status(self):
        """清空回复状态。"""
        self.set_reply_status("")

    def set_notification(self, text: str):
        """兼容旧接口：设置轻量回复状态文本。"""
        self.set_reply_status(text)

    def set_always_on_top(self, enabled: bool) -> None:
        """Change only stacking preference, retaining geometry and window state."""
        from ui.window_behavior import apply_always_on_top
        apply_always_on_top(self, enabled)

    def set_background(self, image_path: str, *, pixmap=None):
        """Apply an image with cover scaling, or restore transparency with ''."""
        return self.centralWidget().set_background(image_path, pixmap)

    def set_display_words(self, html: str):
        """显示富文本消息"""
        self.add_message(html, is_user=False, char_name="系统")

    def clear_messages(self):
        """Clear visible dialogue, history, stream, and temporary content together."""
        self._dismiss_options()
        self._focus_custom_reply_after_waiting = False
        self._message_history.clear()
        self._stream_history_index = None
        self._stream_text = ""
        self._show_active_character_name()
        self.current_character_info_label.setText("当前角色：未指定")
        self.current_message_label.clear()
        while self.temporary_layout.count():
            item = self.temporary_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.scroll_area.setVisible(False)
        self._cg_preview_labels.clear()
        self.last_cg_preview_path = ""

    def set_session_list(self, sessions: list[dict], active_session_id: str = "") -> None:
        self._session_items = list(sessions)
        self.current_session_id = active_session_id
        self.current_session_title = ""
        for item in self._session_items:
            if item.get("id") == active_session_id:
                self.current_session_title = item.get("title", "")
                break
        self._refresh_session_title_label()

    def _refresh_session_title_label(self) -> None:
        if self.current_session_title:
            self.session_title_label.setText(f"当前会话：{self.current_session_title}")
        else:
            self.session_title_label.setText("当前会话：未命名会话")

    def _rename_current_session(self) -> None:
        if not self.current_session_id:
            QMessageBox.information(self, "会话", "当前没有可重命名的会话。")
            return
        new_title, ok = QInputDialog.getText(
            self,
            "重命名当前会话",
            "新的会话标题：",
            text=self.current_session_title or "",
        )
        if ok and new_title.strip():
            self.session_rename_requested.emit(self.current_session_id, new_title.strip())

    def _archive_current_session(self) -> None:
        if not self.current_session_id:
            QMessageBox.information(self, "会话", "当前没有可归档的会话。")
            return
        confirm = QMessageBox.question(self, "归档会话", "确定要归档当前会话吗？")
        if confirm == QMessageBox.StandardButton.Yes:
            self.session_archive_requested.emit(self.current_session_id, True)

    def _build_session_manager_dialog(self) -> QDialog:
        dialog = QDialog(self)
        dialog.resize(560, 430)
        layout = build_frameless_dialog_shell(
            dialog,
            "会话管理",
            close_object_name="session_manager_close_button",
            close_accessible_name="Close session manager",
            close_tool_tip="关闭会话管理",
        )

        list_widget = QListWidget(dialog)
        for session in self._session_items:
            title = session.get("title", "未命名会话")
            if session.get("archived"):
                title = f"[已归档] {title}"
            if session.get("id") == self.current_session_id:
                title = f"{title}（当前）"
            item = QListWidgetItem(title)
            item.setData(Qt.ItemDataRole.UserRole, session.get("id", ""))
            item.setData(Qt.ItemDataRole.UserRole + 1, bool(session.get("archived", False)))
            list_widget.addItem(item)
        layout.addWidget(list_widget)

        button_row = QHBoxLayout()
        new_btn = QPushButton("新建")
        switch_btn = QPushButton("切换")
        rename_btn = QPushButton("重命名")
        skills_btn = QPushButton("Skills")
        archive_btn = QPushButton("归档/恢复")
        delete_btn = QPushButton("删除")
        close_btn = QPushButton("关闭")
        close_btn.setObjectName("session_manager_cancel_button")
        button_row.addWidget(new_btn)
        button_row.addWidget(switch_btn)
        button_row.addWidget(rename_btn)
        button_row.addWidget(skills_btn)
        button_row.addWidget(archive_btn)
        button_row.addWidget(delete_btn)
        button_row.addStretch()
        button_row.addWidget(close_btn)
        layout.addLayout(button_row)

        def _selected_session_id() -> str:
            item = list_widget.currentItem()
            if item is None:
                return ""
            return item.data(Qt.ItemDataRole.UserRole) or ""

        preset_list_widget = QListWidget(dialog)
        for preset_name in self.skill_preset_options:
            preset_list_widget.addItem(preset_name)
        if getattr(preset_list_widget, "count", lambda: 0)() > 0:
            preset_list_widget.setCurrentRow(0)
        layout.addWidget(preset_list_widget)

        from ui.settings_ui.controls import SafeComboBox
        memory_mode = SafeComboBox()
        memory_mode.setObjectName("new_session_memory_mode")
        memory_mode.addItem("全新剧情：不继承旧剧情与关系", "fresh")
        memory_mode.addItem("延续相处：继承此角色长期记忆", "character")
        memory_mode.addItem("接续上方选中的存档：复制记录后继续", "checkpoint")
        layout.addWidget(memory_mode)

        def _new_session() -> None:
            selected = _selected_session_id()
            if memory_mode.currentData() == "checkpoint" and not selected:
                QMessageBox.information(dialog, "接续存档", "请先选择要接续的存档。")
                return
            self._new_session_memory_mode = memory_mode.currentData()
            self._new_session_source_id = selected
            current_item = preset_list_widget.currentItem()
            preset_name = current_item.text() if current_item is not None else "全局默认"
            self.new_session_requested.emit(preset_name)
            dialog.accept()

        def _switch_session() -> None:
            session_id = _selected_session_id()
            if not session_id:
                QMessageBox.information(dialog, "会话管理", "请先选择一个会话。")
                return
            self.session_switch_requested.emit(session_id)
            dialog.accept()

        def _rename_session() -> None:
            session_id = _selected_session_id()
            if not session_id:
                QMessageBox.information(dialog, "会话管理", "请先选择一个会话。")
                return
            current_title = list_widget.currentItem().text().replace("（当前）", "").replace("[已归档]", "").strip()
            new_title, ok = QInputDialog.getText(dialog, "重命名会话", "新的会话标题：", text=current_title)
            if ok and new_title.strip():
                self.session_rename_requested.emit(session_id, new_title.strip())
                dialog.accept()

        def _toggle_archive_session() -> None:
            item = list_widget.currentItem()
            if item is None:
                QMessageBox.information(dialog, "会话管理", "请先选择一个会话。")
                return
            session_id = item.data(Qt.ItemDataRole.UserRole) or ""
            archived = bool(item.data(Qt.ItemDataRole.UserRole + 1))
            self.session_archive_requested.emit(session_id, not archived)
            dialog.accept()

        def _edit_session_skills() -> None:
            item = list_widget.currentItem()
            if item is None:
                QMessageBox.information(dialog, "会话管理", "请先选择一个会话。")
                return
            session_id = item.data(Qt.ItemDataRole.UserRole) or ""
            self.session_skills_requested.emit(session_id)
            dialog.accept()

        def _delete_session() -> None:
            session_id = _selected_session_id()
            if not session_id:
                QMessageBox.information(dialog, "会话管理", "请先选择一个会话。")
                return
            confirm = QMessageBox.question(dialog, "删除会话", "确定要删除选中的会话吗？")
            if confirm == QMessageBox.StandardButton.Yes:
                self.session_delete_requested.emit(session_id)
                dialog.accept()

        new_btn.clicked.connect(_new_session)
        switch_btn.clicked.connect(_switch_session)
        rename_btn.clicked.connect(_rename_session)
        skills_btn.clicked.connect(_edit_session_skills)
        archive_btn.clicked.connect(_toggle_archive_session)
        delete_btn.clicked.connect(_delete_session)
        close_btn.clicked.connect(dialog.reject)
        list_widget.itemDoubleClicked.connect(lambda *_: _switch_session())
        return dialog

    def _open_session_manager(self) -> None:
        dialog = self._build_session_manager_dialog()
        dialog.exec()
