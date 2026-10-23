"""CARD 资料卡的 Qt 组件与聊天窗口集成。"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from ui.chat_ui.chat_ui import ChatUIWindow
from PySide6.QtWidgets import QTextBrowser

from ui.chat_ui.info_card import InfoCardWidget

MARKDOWN = "## 结论\n- 要点一\n\n```python\nprint('hi')\n```\n\n[示例](https://example.com)"


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def test_info_card_shows_compact_summary_without_inner_scroll(app):
    copied = []
    card = InfoCardWidget(MARKDOWN, open_url=lambda u: None, copy_text=copied.append)

    assert card.title_label.text() == "结论"
    assert card.preview_label.text().startswith("· 要点一")
    assert "##" not in card.preview_label.text()
    # 聊天区里的卡片不再嵌套可滚动的 QTextBrowser。
    assert card.findChildren(QTextBrowser) == []

    card.copy_btn.click()
    assert copied == [MARKDOWN]


def _full_view_browser(card):
    dialog = card.build_full_view_dialog()
    browsers = dialog.findChildren(QTextBrowser)
    assert len(browsers) == 1
    return dialog, browsers[0]


def test_info_card_full_view_renders_markdown(app):
    card = InfoCardWidget(MARKDOWN, open_url=lambda u: None, copy_text=lambda t: None)

    dialog, browser = _full_view_browser(card)
    try:
        assert dialog.windowTitle() == "资料卡"
        plain = browser.toPlainText()
        assert "结论" in plain and "要点一" in plain and "print('hi')" in plain
        assert "##" not in plain
        assert browser.openLinks() is False
    finally:
        dialog.close()


def test_info_card_full_view_ignores_raw_html(app):
    card = InfoCardWidget('<img src="https://evil.example/x.png">正文', open_url=lambda u: None, copy_text=lambda t: None)

    dialog, browser = _full_view_browser(card)
    try:
        assert "<img" in browser.toPlainText()
    finally:
        dialog.close()


def test_info_card_summary_strips_html_too(app):
    card = InfoCardWidget('<b>粗体</b>正文', open_url=lambda u: None, copy_text=lambda t: None)

    # 摘要是纯文本 QLabel，不会解释 HTML。
    assert card.preview_label.textFormat() == Qt.TextFormat.PlainText


def test_chat_window_add_card_shows_card_and_records_summary(app):
    window = ChatUIWindow()
    try:
        card = window.add_card(MARKDOWN)

        assert isinstance(card, InfoCardWidget)
        assert window.temporary_layout.indexOf(card) >= 0
        assert window.message_history_snapshot()[-1]["text"] == "[资料卡] 结论"

        window.add_card("   ")
        assert window.temporary_layout.count() == 1
    finally:
        window.close()


def test_chat_window_blocks_non_web_links(app):
    window = ChatUIWindow()
    statuses = []
    window.set_reply_status = lambda text, error=False: statuses.append((text, error))
    try:
        assert window._open_card_link("file:///C:/Windows/System32/cmd.exe") is False
        assert statuses and statuses[-1][1] is True
    finally:
        window.close()
