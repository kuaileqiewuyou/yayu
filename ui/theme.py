"""晴日素笺配色：暖白面板、鼠尾草绿强调色与深墨色正文。

聊天窗口保留透明立绘层及原有控件形状，逐控件应用半透明样式。
应用级弹窗使用 dialogs_qss；设置中心的专用主题位于 settings_ui.daylight。
"""
from __future__ import annotations

# ── 调色板（暖白 + 鼠尾草绿）───────────────────
BG_DEEP      = "#EDF1E8"   # 浅绿灰底
BG_BASE      = "#F7F8F3"   # 暖白主背景
BG_ELEVATED  = "#FFFFFF"   # 卡片/容器
BG_INPUT     = "#FDFEFB"   # 输入框
BG_HOVER     = "rgba(116, 137, 118, 26)"

# 强调色：鼠尾草绿，深阶保证白色按钮文字可读
ACCENT       = "#607B65"
ACCENT_BRIGHT= "#748976"
ACCENT_DEEP  = "#526F58"   # 主色深阶（pressed）
ACCENT_SOFT  = "rgba(116, 137, 118, 31)"
ACCENT_GLOW  = "rgba(116, 137, 118, 77)"
ACCENT_TEXT  = "#FFFFFF"   # 绿色底上的白色文字

# 次强调：深绿（状态点缀）
ACCENT_BLUE  = "#526F58"
ACCENT_BLUE_SOFT = "rgba(82, 111, 88, 31)"

# 功能色
COLOR_FG     = "#233039"   # 主文字 — 深墨色
COLOR_DIM    = "#657169"   # 次要文字
COLOR_OK     = "#526F58"
COLOR_WARN   = "#936623"
COLOR_ERR    = "#AD514A"
COLOR_CYAN   = "#526F58"
COLOR_PURPLE = "#77708F"   # 薰衣草紫

# 边框：半透明绿灰
BORDER       = "rgba(116, 137, 118, 46)"
BORDER_STRONG= "rgba(116, 137, 118, 102)"
BORDER_FOCUS = ACCENT

# 字体栈（日系圆体优先，缺失时回退）
FONT_BODY    = '"ChillRoundF", "Noto Sans SC", "Microsoft YaHei UI", "Segoe UI", sans-serif'


def settings_qss() -> str:
    """返回设置窗口的全局 QSS 样式表。"""
    return f"""
    /* ── 基础 ────────────────────────────────── */
    QMainWindow, QWidget {{
        background-color: {BG_BASE};
        color: {COLOR_FG};
        font-family: {FONT_BODY};
        font-size: 13px;
    }}

    /* ── 标签页 ───────────────────────────────── */
    QTabWidget::pane {{
        border: 1px solid {BORDER};
        border-top: none;
        background: {BG_DEEP};
        border-radius: 0 0 14px 14px;
    }}
    QTabBar {{
        background: transparent;
    }}
    QTabBar::tab {{
        background: {BG_DEEP};
        color: {COLOR_DIM};
        border: 1px solid {BORDER};
        border-bottom: none;
        padding: 8px 22px;
        margin-right: 3px;
        border-radius: 10px 10px 0 0;
        font-size: 13px;
        font-weight: 500;
    }}
    QTabBar::tab:selected {{
        background: {BG_ELEVATED};
        color: {ACCENT};
        border-color: {BORDER_STRONG};
        border-bottom: 2px solid {ACCENT};
        font-weight: 600;
    }}
    QTabBar::tab:hover:!selected {{
        background: {BG_HOVER};
        color: {COLOR_FG};
    }}

    /* ── 分组框 ────────────────────────────────── */
    QGroupBox {{
        background: {BG_ELEVATED};
        border: 1px solid {BORDER};
        border-radius: 14px;
        margin-top: 14px;
        padding: 20px 12px 12px 12px;
        font-weight: 600;
        color: {ACCENT};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: 16px;
        padding: 0 8px;
        background: {BG_ELEVATED};
    }}

    /* ── 按钮 ─────────────────────────────────── */
    QPushButton {{
        background-color: {BG_ELEVATED};
        color: {COLOR_FG};
        border: 1px solid {BORDER};
        border-radius: 10px;
        padding: 8px 18px;
        font-size: 13px;
        font-weight: 500;
    }}
    QPushButton:hover {{
        background-color: {ACCENT_SOFT};
        border-color: {BORDER_STRONG};
        color: {ACCENT};
    }}
    QPushButton:pressed {{
        background-color: {ACCENT_GLOW};
    }}
    QPushButton:disabled {{
        background-color: rgba(247, 248, 243, 150);
        color: rgba(35, 48, 57, 70);
        border-color: rgba(116, 137, 118, 20);
    }}

    /* ── 输入控件 ─────────────────────────────── */
    QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox {{
        background-color: {BG_INPUT};
        color: {COLOR_FG};
        border: 1px solid {BORDER};
        border-radius: 10px;
        padding: 7px 12px;
        font-size: 13px;
        selection-background-color: {ACCENT_GLOW};
        selection-color: {COLOR_FG};
    }}
    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus,
    QSpinBox:focus, QDoubleSpinBox:focus {{
        border: 1px solid {BORDER_FOCUS};
        background-color: {BG_ELEVATED};
    }}
    QLineEdit:disabled, QTextEdit:disabled {{
        background-color: rgba(247, 248, 243, 150);
        color: rgba(35, 48, 57, 70);
    }}
    QLineEdit::placeholder, QTextEdit::placeholder {{
        color: rgba(35, 48, 57, 90);
    }}

    /* ── 下拉框 ─────────────────────────────────── */
    QComboBox {{
        background-color: {BG_INPUT};
        color: {COLOR_FG};
        border: 1px solid {BORDER};
        border-radius: 10px;
        padding: 7px 12px;
        font-size: 13px;
        min-width: 120px;
    }}
    QComboBox:hover {{
        border-color: {BORDER_STRONG};
    }}
    QComboBox:focus {{
        border: 1px solid {BORDER_FOCUS};
    }}
    QComboBox::drop-down {{
        border: none;
        width: 28px;
    }}
    QComboBox::down-arrow {{
        width: 12px;
        height: 12px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {BG_ELEVATED};
        color: {COLOR_FG};
        border: 1px solid {BORDER};
        border-radius: 10px;
        padding: 4px;
        selection-background-color: {ACCENT_SOFT};
        selection-color: {ACCENT};
    }}
    QComboBox QAbstractItemView::item {{
        padding: 5px 10px;
        border-radius: 6px;
    }}
    QComboBox QAbstractItemView::item:hover {{
        background-color: {BG_HOVER};
    }}

    /* ── 复选框 ─────────────────────────────────── */
    QCheckBox {{
        color: {COLOR_FG};
        spacing: 8px;
        font-size: 13px;
    }}
    QCheckBox::indicator {{
        width: 18px;
        height: 18px;
        border: 1px solid {BORDER};
        border-radius: 6px;
        background: {BG_INPUT};
    }}
    QCheckBox::indicator:hover {{
        border-color: {BORDER_STRONG};
    }}
    QCheckBox::indicator:checked {{
        background: {ACCENT};
        border-color: {ACCENT};
        image: none;
    }}

    /* ── 滚动区域 ────────────────────────────────── */
    QScrollArea {{
        background: transparent;
        border: 1px solid {BORDER};
        border-radius: 14px;
    }}
    QScrollArea > QWidget > QWidget {{
        background: transparent;
    }}

    /* ── 列表 ──────────────────────────────────── */
    QListWidget {{
        background-color: {BG_INPUT};
        color: {COLOR_FG};
        border: 1px solid {BORDER};
        border-radius: 10px;
        padding: 4px;
        font-size: 13px;
    }}
    QListWidget::item {{
        padding: 6px 8px;
        border-radius: 6px;
    }}
    QListWidget::item:hover {{
        background-color: {BG_HOVER};
    }}
    QListWidget::item:selected {{
        background-color: {ACCENT_SOFT};
        color: {ACCENT};
        border-left: 3px solid {ACCENT};
    }}

    /* ── 滚动条 ────────────────────────────────── */
    QScrollBar:vertical {{
        background: transparent;
        width: 8px;
        margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background: rgba(116, 137, 118, 90);
        border-radius: 4px;
        min-height: 24px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {ACCENT};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        background: transparent;
    }}
    QScrollBar:horizontal {{
        background: transparent;
        height: 8px;
        margin: 0;
    }}
    QScrollBar::handle:horizontal {{
        background: rgba(116, 137, 118, 90);
        border-radius: 4px;
        min-width: 24px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background: {ACCENT};
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0;
    }}
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
        background: transparent;
    }}

    /* ── 标签 ──────────────────────────────────── */
    QLabel {{
        color: {COLOR_FG};
        background: transparent;
        font-size: 13px;
    }}

    /* ── 消息框 ────────────────────────────────── */
    QMessageBox {{
        background: {BG_ELEVATED};
    }}
    QMessageBox QLabel {{
        color: {COLOR_FG};
        font-size: 13px;
    }}
    QMessageBox QPushButton {{
        min-width: 70px;
        background-color: {ACCENT};
        color: {ACCENT_TEXT};
        border: none;
        border-radius: 8px;
        padding: 8px 20px;
        font-weight: 600;
    }}
    QMessageBox QPushButton:hover {{
        background-color: {ACCENT_BRIGHT};
    }}

    /* ── 输入对话框 ────────────────────────────── */
    QInputDialog {{
        background: {BG_ELEVATED};
    }}

    /* ── 文件对话框 ─────────────────────────────── */
    QFileDialog {{
        background: {BG_BASE};
    }}

    /* ── 分割器 ────────────────────────────────── */
    QSplitter::handle {{
        background: {BORDER};
    }}
    QSplitter::handle:horizontal {{
        width: 2px;
    }}
    QSplitter::handle:vertical {{
        height: 2px;
    }}

    /* ── 表单布局间距 ──────────────────────────── */
    QFormLayout {{
        spacing: 10px;
    }}

    /* ── 工具提示 ──────────────────────────────── */
    QToolTip {{
        background: {BG_ELEVATED};
        color: {COLOR_FG};
        border: 1px solid {BORDER};
        border-radius: 6px;
        padding: 5px 10px;
        font-size: 12px;
    }}
    """


# ── 聊天窗口专用：按钮统一样式 ──────────────────
# 聊天窗口透明背景，面板使用暖白半透明底 + 绿灰描边

CHAT_TEMPORARY_CONTENT_GLASS_STYLE = """
    QScrollArea#temporary_content_scroll_area {
        background: transparent;
        border: 1px solid rgba(116, 137, 118, 46);
        border-radius: 16px;
    }
    QScrollArea#temporary_content_scroll_area > QWidget > QWidget {
        background: transparent;
    }
    QScrollBar:vertical {
        background: transparent;
        width: 6px;
        margin: 8px 2px 8px 0;
    }
    QScrollBar::handle:vertical {
        background: rgba(116, 137, 118, 110);
        border-radius: 3px;
        min-height: 30px;
    }
    QScrollBar::handle:vertical:hover {
        background: rgba(116, 137, 118, 190);
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0;
    }
"""

CHAT_TEMPORARY_CONTENT_STYLE = """
    QWidget#temporary_content_widget {
        background-color: rgba(247, 248, 243, 219);
        border-radius: 15px;
    }
"""

CHAT_DIALOGUE_GLASS_STYLE = """
    QFrame#current_message_frame {
        background-color: rgba(247, 248, 243, 219);
        border: 1px solid rgba(116, 137, 118, 46);
        border-bottom: none;
        border-top-left-radius: 20px;
        border-top-right-radius: 20px;
        border-bottom-left-radius: 0;
        border-bottom-right-radius: 0;
    }
"""

# 对话框下半部（状态行 + 输入栏容器），与上半对话框拼成一个 ADV 对话框
CHAT_DIALOGUE_LOWER_STYLE = """
    QWidget#dialog_lower_container {
        background-color: rgba(247, 248, 243, 219);
        border: 1px solid rgba(116, 137, 118, 46);
        border-top: none;
        border-top-left-radius: 0;
        border-top-right-radius: 0;
        border-bottom-left-radius: 20px;
        border-bottom-right-radius: 20px;
    }
"""

CHAT_BTN_PRIMARY = f"""
    QPushButton {{
        background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 {ACCENT}, stop:1 {ACCENT_DEEP});
        color: {ACCENT_TEXT};
        border: none;
        border-radius: 14px;
        padding: 8px 22px;
        font-size: 14px;
        font-weight: bold;
    }}
    QPushButton:hover {{ background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 {ACCENT_BRIGHT}, stop:1 {ACCENT}); }}
    QPushButton:pressed {{ background-color: {ACCENT_DEEP}; }}
    QPushButton:disabled {{ background-color: rgba(185, 196, 184, 100); color: rgba(35, 48, 57, 110); }}
"""

CHAT_BTN_NORMAL = f"""
    QPushButton {{
        background-color: rgba(247, 248, 243, 200);
        color: {COLOR_FG};
        border: 1px solid rgba(116, 137, 118, 60);
        border-radius: 14px;
        padding: 8px 16px;
        font-size: 13px;
    }}
    QPushButton:hover {{ background-color: rgba(235, 240, 232, 220); border-color: {ACCENT}; color: {ACCENT}; }}
    QPushButton:pressed {{ background-color: rgba(116, 137, 118, 40); }}
    QPushButton:disabled {{ background-color: rgba(247, 248, 243, 120); color: rgba(35, 48, 57, 70); border-color: rgba(116, 137, 118, 25); }}
"""

# CHOICE 选项：左对齐的选择支，悬停时左侧强调条 + 轻微底色
CHAT_CHOICE_BTN = f"""
    QPushButton {{
        background-color: rgba(255, 255, 255, 150);
        color: {COLOR_FG};
        border: 1px solid rgba(116, 137, 118, 55);
        border-left: 3px solid rgba(116, 137, 118, 90);
        border-radius: 10px;
        padding: 7px 14px;
        font-size: 13px;
        text-align: left;
    }}
    QPushButton:hover {{
        background-color: rgba(235, 240, 232, 235);
        border-color: {ACCENT};
        border-left: 3px solid {ACCENT};
        color: {ACCENT_DEEP};
    }}
    QPushButton:pressed {{ background-color: rgba(116, 137, 118, 45); }}
    QPushButton:disabled {{
        background-color: rgba(247, 248, 243, 110);
        color: rgba(35, 48, 57, 90);
        border-color: rgba(116, 137, 118, 25);
    }}
"""

CHAT_BTN_DANGER = f"""
    QPushButton {{
        background-color: rgba(173, 81, 74, 190);
        color: {ACCENT_TEXT};
        border: none;
        border-radius: 14px;
        padding: 8px 16px;
        font-size: 13px;
        font-weight: 600;
    }}
    QPushButton:hover {{ background-color: rgba(183, 96, 87, 220); }}
    QPushButton:pressed {{ background-color: rgba(152, 66, 60, 220); }}
    QPushButton:disabled {{ background-color: rgba(185, 196, 184, 100); color: rgba(35, 48, 57, 100); }}
"""

CHAT_BTN_SMALL = f"""
    QPushButton {{
        background-color: rgba(247, 248, 243, 180);
        color: {COLOR_DIM};
        border: 1px solid rgba(116, 137, 118, 46);
        border-radius: 10px;
        padding: 4px 12px;
        font-size: 11px;
    }}
    QPushButton:hover {{ background-color: rgba(235, 240, 232, 220); color: {ACCENT}; border-color: {ACCENT}; }}
"""

CHAT_BTN_CLOSE = f"""
    QPushButton {{
        background-color: rgba(247, 248, 243, 180);
        color: {COLOR_FG};
        border: 1px solid rgba(116, 137, 118, 46);
        border-radius: 14px;
        font-size: 14px;
        font-weight: bold;
    }}
    QPushButton:hover {{ background-color: rgba(173, 81, 74, 220); color: {ACCENT_TEXT}; border-color: transparent; }}
"""

CHAT_INPUT_STYLE = f"""
    QLineEdit {{
        background-color: rgba(255, 255, 255, 140);
        color: {COLOR_FG};
        border: 1px solid {BORDER};
        border-radius: 14px;
        padding: 9px 12px;
        font-size: 13px;
        selection-background-color: {ACCENT_GLOW};
        selection-color: {COLOR_FG};
    }}
    QLineEdit:focus {{
        border: 1px solid {ACCENT};
        background-color: rgba(255, 255, 255, 180);
    }}
    QLineEdit::placeholder {{
        color: rgba(35, 48, 57, 90);
    }}
"""


# ── mockup 对应的新组件样式 ─────────────────────

# 右上角圆形悬浮控制按钮（☰ / ⚙ / — / ✕），浮于立绘之上
CHAT_ICON_BTN = f"""
    QPushButton {{
        background-color: rgba(82, 111, 88, 184);
        color: {ACCENT_TEXT};
        border: 1px solid {BORDER};
        border-radius: 20px;
        font-size: 15px;
        padding: 0;
    }}
    QPushButton:hover {{
        background-color: rgba(116, 137, 118, 51);
        border-color: rgba(116, 137, 118, 115);
        color: {ACCENT_DEEP};
    }}
"""

# 输入行里的 ⋯ 按钮：与“停止”同一套描边圆角，不再是突兀的实心方块
CHAT_INPUT_ROW_ICON_BTN = f"""
    QPushButton {{
        background-color: rgba(247, 248, 243, 200);
        color: {ACCENT};
        border: 1px solid rgba(116, 137, 118, 60);
        border-radius: 14px;
        font-size: 16px;
        font-weight: 700;
        padding: 0;
    }}
    QPushButton:hover {{ background-color: rgba(235, 240, 232, 220); border-color: {ACCENT}; }}
    QPushButton:pressed {{ background-color: rgba(116, 137, 118, 40); }}
"""

CHAT_ICON_BTN_CLOSE = f"""
    QPushButton {{
        background-color: rgba(82, 111, 88, 184);
        color: {ACCENT_TEXT};
        border: 1px solid {BORDER};
        border-radius: 20px;
        font-size: 15px;
        padding: 0;
    }}
    QPushButton:hover {{
        background-color: rgba(173, 81, 74, 82);
        border-color: rgba(116, 137, 118, 115);
        color: {COLOR_ERR};
    }}
"""

CHAT_DIALOG_INFO_TOGGLE_STYLE = f"""
    QPushButton {{
        background-color: transparent;
        color: {ACCENT};
        border: none;
        border-radius: 20px;
        font-size: 12px;
        padding: 0;
    }}
    QPushButton:hover {{
        background-color: rgba(116, 137, 118, 31);
        color: {ACCENT_BRIGHT};
    }}
    QPushButton:pressed {{ background-color: rgba(116, 137, 118, 51); }}
"""

# 常驻界面开关（◉/◎）：24px 幽灵小圆钮，常显于右上角，不打扰立绘观感
CHAT_COMPANION_TOGGLE_BTN = f"""
    QPushButton {{
        background-color: rgba(82, 111, 88, 120);
        color: {ACCENT_TEXT};
        border: 1px solid {BORDER};
        border-radius: 12px;
        font-size: 11px;
        padding: 0;
    }}
    QPushButton:hover {{
        background-color: rgba(116, 137, 118, 46);
        border-color: {BORDER_STRONG};
        color: {ACCENT};
    }}
"""

CHAT_DIALOG_INFO_POPUP_STYLE = f"""
    QFrame#conversation_info_popup {{
        background-color: rgba(247, 248, 243, 248);
        border: 1px solid {BORDER_STRONG};
        border-radius: 16px;
    }}
    QLabel {{ background: transparent; }}
"""

# 名牌：压在对话框左上边缘的胶囊（绿渐变 + 白色文字）
CHAT_NAME_PLATE = f"""
    QLabel {{
        background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 {ACCENT}, stop:1 {ACCENT_DEEP});
        color: {ACCENT_TEXT};
        font-weight: 700;
        font-size: 13px;
        padding: 5px 14px;
        border-radius: 13px;
    }}
"""

# 对话框内状态行（模型/技能信息，弱化显示）
CHAT_STATUS_LINE = """
    QLabel {
        color: rgba(35, 48, 57, 140);
        font-size: 10px;
        background: transparent;
        border-top: 1px solid rgba(116, 137, 118, 46);
        padding: 6px 4px 0 4px;
    }
"""

# 聊天记录浮层：面板底
HISTORY_PANEL_STYLE = f"""
    QFrame#history_panel {{
        background-color: rgba(247, 248, 243, 245);
        border: 1px solid {BORDER};
        border-radius: 20px;
    }}
"""

# 聊天记录：标题「❀ 聊天记录」
HISTORY_TITLE_STYLE = f"""
    QLabel {{
        color: {ACCENT};
        font-weight: 700;
        font-size: 14px;
        background: transparent;
    }}
"""

# 聊天记录：AI 气泡（左侧，浅绿灰底）
HISTORY_BUBBLE_AI = f"""
    QLabel {{
        background-color: rgba(235, 240, 232, 235);
        color: {COLOR_FG};
        border: 1px solid {BORDER};
        border-radius: 14px;
        border-top-left-radius: 4px;
        padding: 9px 13px;
        font-size: 13px;
    }}
"""

# 聊天记录：用户气泡（右侧，绿渐变）
HISTORY_BUBBLE_USER = f"""
    QLabel {{
        background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 {ACCENT}, stop:1 {ACCENT_DEEP});
        color: {ACCENT_TEXT};
        border-radius: 14px;
        border-top-right-radius: 4px;
        padding: 9px 13px;
        font-size: 13px;
        font-weight: 500;
    }}
"""

# 设置窗：左侧导航（QListWidget）
SETTINGS_NAV_STYLE = f"""
    QListWidget {{
        background-color: rgba(255, 255, 255, 102);
        color: {COLOR_DIM};
        border: none;
        border-right: 1px solid {BORDER};
        border-radius: 0;
        padding: 14px 10px;
        font-size: 13px;
        outline: none;
    }}
    QListWidget::item {{
        padding: 10px 12px;
        border-radius: 10px;
        border: 1px solid transparent;
        margin-bottom: 4px;
    }}
    QListWidget::item:hover {{
        background-color: rgba(116, 137, 118, 20);
        color: {COLOR_FG};
    }}
    QListWidget::item:selected {{
        background-color: rgba(116, 137, 118, 36);
        border: 1px solid rgba(116, 137, 118, 77);
        color: {ACCENT};
    }}
"""

# 设置窗：标题栏「芽语 · 设置中心」
SETTINGS_TITLEBAR_STYLE = f"""
    QWidget#settings_titlebar {{
        background-color: rgba(116, 137, 118, 13);
        border-bottom: 1px solid {BORDER};
    }}
"""


def dialogs_qss() -> str:
    """应用级弹窗样式：让 QMessageBox / QInputDialog / QDialog 等
    原生弹窗继承晴日素笺配色。

    通过 app.setStyleSheet() 全局应用；聊天主窗口自身是无边框透明窗，
    其样式由逐控件 setStyleSheet 指定，优先级高于此全局表，互不冲突。
    """
    return f"""
    /* ── 弹窗底色 ─────────────────────────────── */
    QDialog, QMessageBox, QInputDialog {{
        background-color: {BG_ELEVATED};
        color: {COLOR_FG};
        font-family: {FONT_BODY};
        font-size: 13px;
    }}

    QDialog QLabel, QMessageBox QLabel, QInputDialog QLabel {{
        color: {COLOR_FG};
        background: transparent;
        font-size: 13px;
    }}

    /* ── 弹窗按钮 ─────────────────────────────── */
    QDialog QPushButton, QMessageBox QPushButton, QInputDialog QPushButton {{
        background-color: {BG_INPUT};
        color: {COLOR_FG};
        border: 1px solid {BORDER};
        border-radius: 10px;
        padding: 7px 18px;
        font-size: 13px;
        min-width: 64px;
    }}
    QDialog QPushButton:hover, QMessageBox QPushButton:hover, QInputDialog QPushButton:hover {{
        background-color: {ACCENT_SOFT};
        border-color: {BORDER_STRONG};
        color: {ACCENT};
    }}
    QDialog QPushButton:pressed, QMessageBox QPushButton:pressed, QInputDialog QPushButton:pressed {{
        background-color: {ACCENT_GLOW};
    }}
    QDialog QPushButton:default, QMessageBox QPushButton:default, QInputDialog QPushButton:default {{
        background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 {ACCENT}, stop:1 {ACCENT_DEEP});
        color: {ACCENT_TEXT};
        border: none;
        font-weight: 600;
    }}
    QDialog QPushButton:default:hover, QMessageBox QPushButton:default:hover,
    QInputDialog QPushButton:default:hover {{
        background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 {ACCENT_BRIGHT}, stop:1 {ACCENT});
    }}

    /* ── 弹窗输入控件 ─────────────────────────── */
    QDialog QLineEdit, QInputDialog QLineEdit {{
        background-color: {BG_INPUT};
        color: {COLOR_FG};
        border: 1px solid {BORDER};
        border-radius: 10px;
        padding: 7px 12px;
        font-size: 13px;
        selection-background-color: {ACCENT_GLOW};
        selection-color: {COLOR_FG};
    }}
    QDialog QLineEdit:focus, QInputDialog QLineEdit:focus {{
        border: 1px solid {ACCENT};
    }}

    /* ── 弹窗列表（会话管理等） ─────────────────── */
    QDialog QListWidget {{
        background-color: {BG_INPUT};
        color: {COLOR_FG};
        border: 1px solid {BORDER};
        border-radius: 10px;
        padding: 4px;
        font-size: 13px;
        outline: none;
    }}
    QDialog QListWidget::item {{
        padding: 7px 10px;
        border-radius: 8px;
    }}
    QDialog QListWidget::item:hover {{
        background-color: {BG_HOVER};
    }}
    QDialog QListWidget::item:selected {{
        background-color: {ACCENT_SOFT};
        color: {ACCENT};
        border-left: 3px solid {ACCENT};
    }}

    /* ── 弹窗滚动条 ───────────────────────────── */
    QDialog QScrollBar:vertical {{
        background: transparent;
        width: 6px;
        margin: 0;
    }}
    QDialog QScrollBar::handle:vertical {{
        background: rgba(116, 137, 118, 90);
        border-radius: 3px;
        min-height: 24px;
    }}
    QDialog QScrollBar::handle:vertical:hover {{
        background: {ACCENT};
    }}
    QDialog QScrollBar::add-line:vertical, QDialog QScrollBar::sub-line:vertical {{
        height: 0;
    }}
    QDialog QScrollBar::add-page:vertical, QDialog QScrollBar::sub-page:vertical {{
        background: transparent;
    }}

    /* ── 工具提示 ─────────────────────────────── */
    QToolTip {{
        background: {BG_ELEVATED};
        color: {COLOR_FG};
        border: 1px solid {BORDER};
        border-radius: 6px;
        padding: 5px 10px;
        font-size: 12px;
    }}
    """


