from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.security.allowed_roots import AllowedRootsStore
from ui.settings_ui.presentation import page_layout, card, hint
from ui.settings_ui.list_cards import CardListDelegate


@dataclass(slots=True)
class SecurityTabParts:
    widget: QWidget
    allowed_roots_list: QListWidget
    add_root_button: QPushButton
    remove_root_button: QPushButton
    status_label: QLabel


def build_security_tab(parent, store: AllowedRootsStore) -> SecurityTabParts:
    widget = QWidget(parent)
    widget.setObjectName("security_tab")
    layout = page_layout(widget, "权限与安全", "管理文件工具可以访问的目录。目录授权即时保存，重启应用后生效。")

    roots_group, roots_layout = card("已授权目录")
    layout.addWidget(roots_group)
    description = QLabel("文件工具可访问以下目录。项目目录为内置授权，不能移除。")
    description.setWordWrap(True)
    roots_layout.addWidget(description)

    roots_list = QListWidget()
    roots_list.setObjectName("security_allowed_roots_list")
    roots_list.setAccessibleName("Allowed directories")
    roots_list.setMinimumHeight(230)
    roots_list.setProperty("role", "cards")
    roots_list.setItemDelegate(CardListDelegate(roots_list, formatter=lambda index: (
        "目录授权" + (" · 内置目录" if "内置授权" in index.data() else ""), index.data())))
    roots_list.setWordWrap(True)
    roots_layout.addWidget(roots_list, stretch=1)

    buttons = QHBoxLayout()
    add_button = QPushButton("添加目录")
    add_button.setObjectName("security_add_root_button")
    add_button.setMinimumHeight(40)
    remove_button = QPushButton("移除授权")
    remove_button.setObjectName("security_remove_root_button")
    remove_button.setMinimumHeight(40)
    remove_button.setProperty("role", "danger")
    buttons.addWidget(add_button)
    buttons.addWidget(remove_button)
    buttons.addStretch()
    roots_layout.addLayout(buttons)

    status = QLabel("")
    status.setObjectName("security_status_label")
    status.setWordWrap(True)
    layout.addWidget(status)
    terminal_group, terminal_layout = card("Terminal 执行权限")
    terminal_layout.addWidget(hint("已授权目录也作为 Terminal 的可信启动目录。Terminal 命令不受目录沙箱限制，每次执行仍需人工批准。", banner=True))
    layout.addWidget(terminal_group)
    layout.addStretch()

    return SecurityTabParts(
        widget=widget,
        allowed_roots_list=roots_list,
        add_root_button=add_button,
        remove_root_button=remove_button,
        status_label=status,
    )


def root_row_text(root: Path, *, project_root: Path) -> str:
    suffix = "  ·  内置授权" if root == project_root else ""
    return f"{root}{suffix}"
