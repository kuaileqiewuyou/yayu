"""资料卡（CARD）组件：在聊天区展示 Markdown 形式的实质内容。

角色台词负责“说”，资料卡负责“给”：查询结果、步骤、代码、来源链接等
放在这里渲染，可复制、可展开，不进入 TTS。

聊天区内只显示紧凑摘要（标题 + 前几行纯文本，无内部滚动条）；
完整 Markdown 在“展开”弹窗中渲染。
"""

from __future__ import annotations

import re
from typing import Callable
from urllib.parse import urlparse

_SAFE_URL_SCHEMES = frozenset({"http", "https"})

PREVIEW_MAX_LINES = 3

_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+")
_BULLET_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_EMPHASIS_RE = re.compile(r"(\*\*|__|\*|_|`)")


def is_safe_external_url(url: str) -> bool:
    """只允许打开 http/https 链接。

    资料卡内容来自模型，模型又可能读过外部网页；file:、ms-settings:、
    javascript: 等协议一律不交给系统打开。
    """
    try:
        parsed = urlparse((url or "").strip())
    except ValueError:
        return False
    return parsed.scheme.lower() in _SAFE_URL_SCHEMES and bool(parsed.netloc)


def _plain_line(line: str) -> str:
    line = _HEADING_RE.sub("", line)
    line = _LINK_RE.sub(r"\1", line)
    line = _EMPHASIS_RE.sub("", line)
    return line.strip()


def summarize_markdown(markdown: str, max_lines: int = PREVIEW_MAX_LINES) -> tuple[str, list[str]]:
    """把 Markdown 压成 (标题, 预览行)。

    标题取第一个标题行（没有则为空）；预览行取其后的非空正文，
    列表项以 “· ” 开头，代码块只保留首行。超出行数时追加 “…”。
    """
    title = ""
    lines: list[str] = []
    in_code = False
    code_line_taken = False
    truncated = False
    for raw in (markdown or "").splitlines():
        stripped = raw.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            code_line_taken = False
            continue
        if not stripped:
            continue
        if in_code:
            if code_line_taken:
                continue
            code_line_taken = True
            text = stripped
        elif not title and _HEADING_RE.match(raw):
            title = _plain_line(raw)
            continue
        else:
            text = _plain_line(raw)
            if _BULLET_RE.match(raw):
                text = "· " + _plain_line(_BULLET_RE.sub("", raw))
        if not text:
            continue
        if len(lines) >= max_lines:
            truncated = True
            break
        lines.append(text)
    if truncated and lines:
        lines[-1] = lines[-1] + " …"
    return title, lines


try:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QTextDocument
    from PySide6.QtWidgets import (
        QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QTextBrowser, QVBoxLayout,
    )
    PYSIDE6_AVAILABLE = True
except ModuleNotFoundError:  # 纯逻辑测试环境
    PYSIDE6_AVAILABLE = False


if PYSIDE6_AVAILABLE:
    from ui.frameless_dialog import build_frameless_dialog_shell
    from ui.theme import ACCENT, CHAT_BTN_NORMAL, COLOR_DIM, COLOR_FG

    # GitHub 风格 Markdown，但禁止原始 HTML，避免模型/网页内容注入样式或外链资源。
    _MARKDOWN_FEATURES = (
        QTextDocument.MarkdownFeature.MarkdownDialectGitHub
        | QTextDocument.MarkdownFeature.MarkdownNoHTML
    )

    _CARD_FRAME_STYLE = """
        QFrame#info_card {
            background-color: rgba(255, 255, 255, 150);
            border: 1px solid rgba(116, 137, 118, 60);
            border-left: 3px solid rgba(96, 123, 101, 200);
            border-radius: 12px;
        }
    """
    _CARD_TAG_STYLE = f"color: {ACCENT}; font-size: 11px; font-weight: 600; background: transparent; border: none;"
    _CARD_TITLE_STYLE = f"color: {COLOR_FG}; font-size: 13px; font-weight: 600; background: transparent; border: none;"
    _CARD_BODY_STYLE = f"color: {COLOR_DIM}; font-size: 12px; background: transparent; border: none;"
    _CARD_LINK_BTN_STYLE = f"""
        QPushButton {{
            background: transparent; border: none; color: {ACCENT};
            font-size: 12px; padding: 2px 4px;
        }}
        QPushButton:hover {{ color: {COLOR_FG}; text-decoration: underline; }}
    """
    _BROWSER_STYLE = (
        "QTextBrowser { color: #233039; font-size: 13px; background: transparent; border: none; }"
    )
    # 正文 Markdown 的版式：收紧列表缩进，代码块加底色。
    _DOCUMENT_CSS = """
        h1, h2, h3 { color: #3f5a45; margin-top: 10px; margin-bottom: 4px; }
        ul, ol { margin-left: 0px; -qt-list-indent: 1; }
        li { margin-bottom: 2px; }
        pre, code { background-color: rgba(116, 137, 118, 26); font-family: "Cascadia Mono", "Consolas", monospace; }
        a { color: #526F58; }
    """

    def _build_markdown_browser(markdown: str, open_url: Callable[[str], None]) -> QTextBrowser:
        browser = QTextBrowser()
        browser.setObjectName("info_card_browser")
        # 链接一律走 open_url 回调（带协议白名单），不让 QTextBrowser 自行导航。
        browser.setOpenLinks(False)
        browser.setOpenExternalLinks(False)
        browser.anchorClicked.connect(lambda url: open_url(url.toString()))
        browser.setStyleSheet(_BROWSER_STYLE)
        browser.setFrameShape(QFrame.Shape.NoFrame)
        browser.document().setDefaultStyleSheet(_DOCUMENT_CSS)
        browser.document().setDocumentMargin(4)
        browser.document().setMarkdown(markdown, _MARKDOWN_FEATURES)
        return browser

    class InfoCardWidget(QFrame):
        """聊天区里的紧凑资料卡：标题 + 摘要行 + 展开/复制。没有内部滚动条。"""

        def __init__(
            self,
            markdown: str,
            *,
            title: str = "资料卡",
            open_url: Callable[[str], None],
            copy_text: Callable[[str], None],
            parent=None,
        ) -> None:
            super().__init__(parent)
            self.markdown = markdown
            self.title = title
            self._open_url = open_url
            self._copy_text = copy_text

            self.setObjectName("info_card")
            self.setAccessibleName("Info card")
            self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            self.setStyleSheet(_CARD_FRAME_STYLE)

            layout = QVBoxLayout(self)
            layout.setContentsMargins(14, 8, 10, 10)
            layout.setSpacing(3)

            header = QHBoxLayout()
            header.setContentsMargins(0, 0, 0, 0)
            header.setSpacing(2)
            tag = QLabel(f"▍{title}")
            tag.setObjectName("info_card_tag")
            tag.setStyleSheet(_CARD_TAG_STYLE)
            header.addWidget(tag)
            header.addStretch()
            self.expand_btn = QPushButton("展开")
            self.expand_btn.setObjectName("info_card_expand_button")
            self.copy_btn = QPushButton("复制")
            self.copy_btn.setObjectName("info_card_copy_button")
            for btn in (self.expand_btn, self.copy_btn):
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.setStyleSheet(_CARD_LINK_BTN_STYLE)
                btn.setFlat(True)
                header.addWidget(btn)
            layout.addLayout(header)

            heading, preview_lines = summarize_markdown(markdown)
            self.title_label = QLabel(heading)
            self.title_label.setObjectName("info_card_title")
            self.title_label.setStyleSheet(_CARD_TITLE_STYLE)
            self.title_label.setWordWrap(True)
            self.title_label.setTextFormat(Qt.TextFormat.PlainText)
            self.title_label.setVisible(bool(heading))
            layout.addWidget(self.title_label)

            self.preview_label = QLabel("\n".join(preview_lines))
            self.preview_label.setObjectName("info_card_preview")
            self.preview_label.setStyleSheet(_CARD_BODY_STYLE)
            self.preview_label.setWordWrap(True)
            self.preview_label.setTextFormat(Qt.TextFormat.PlainText)
            self.preview_label.setVisible(bool(preview_lines))
            layout.addWidget(self.preview_label)

            self.expand_btn.clicked.connect(self.open_full_view)
            self.copy_btn.clicked.connect(lambda checked=False: self._copy_text(self.markdown))

        def build_full_view_dialog(self) -> QDialog:
            dialog = QDialog(self.window())
            content = build_frameless_dialog_shell(
                dialog,
                self.title,
                close_object_name="info_card_dialog_close_button",
                close_accessible_name="Close info card",
                close_tool_tip="关闭资料卡",
            )
            browser = _build_markdown_browser(self.markdown, self._open_url)
            content.addWidget(browser, stretch=1)
            copy_btn = QPushButton("复制全文")
            copy_btn.setObjectName("info_card_dialog_copy_button")
            copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            copy_btn.setStyleSheet(CHAT_BTN_NORMAL)
            copy_btn.clicked.connect(lambda checked=False: self._copy_text(self.markdown))
            content.addWidget(copy_btn, alignment=Qt.AlignmentFlag.AlignRight)
            dialog.resize(560, 620)
            return dialog

        def open_full_view(self) -> None:
            self.build_full_view_dialog().exec()
