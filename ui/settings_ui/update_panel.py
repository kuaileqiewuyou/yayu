"""Small, independently saved software-update controls for system settings."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QProgressBar, QPushButton,
    QSizePolicy, QToolButton, QVBoxLayout, QWidget,
)

from ui.settings_ui.presentation import hint


class UpdatePanel(QGroupBox):
    def __init__(self, parent=None, *, root: Path | None = None):
        super().__init__("软件更新", parent)
        self.setObjectName("software_update_panel")
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        self.setProperty("settingsIndependent", True)
        self.root = Path(root or Path(__file__).resolve().parents[2])
        try:
            self.current_version = (self.root / "VERSION").read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError):
            self.current_version = "未知"
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setSpacing(12)
        self.version_label = QLabel(f"当前版本  {self.current_version}")
        self.version_label.setObjectName("update_current_version")
        layout.addWidget(self.version_label)
        self.status_label = hint("点击检查更新；不会在启动时自动联网。")
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        self.status_label.setObjectName("update_status")
        layout.addWidget(self.status_label)
        self.mode_hint = hint("更新会保留原安装路径和完整个人数据，并自动备份程序文件。")
        layout.addWidget(self.mode_hint)
        self.progress = QProgressBar()
        self.progress.setObjectName("update_progress")
        self.progress.setRange(0, 100)
        self.progress.setStyleSheet(
            "QProgressBar { border: 1px solid #D5DDD2; border-radius: 5px; "
            "background: #F0F2ED; text-align: center; min-height: 18px; }"
            "QProgressBar::chunk { background: #748976; border-radius: 4px; }"
        )
        self.progress.hide()
        layout.addWidget(self.progress)
        actions = QHBoxLayout()
        self.check_button = QPushButton("检查更新")
        self.check_button.setObjectName("check_updates_button")
        self.install_button = QPushButton("下载并更新")
        self.install_button.setObjectName("install_update_button")
        self.install_button.setProperty("role", "primary")
        self.install_button.hide()
        self.cancel_button = QPushButton("取消")
        self.cancel_button.setObjectName("cancel_update_button")
        self.cancel_button.hide()
        actions.addWidget(self.check_button)
        actions.addWidget(self.install_button)
        actions.addWidget(self.cancel_button)
        actions.addStretch()
        layout.addLayout(actions)
        self.credentials_toggle = QToolButton()
        self.credentials_toggle.setText("GitHub 访问设置")
        self.credentials_toggle.setObjectName("update_credentials_toggle")
        self.credentials_toggle.setCheckable(True)
        self.credentials_toggle.setStyleSheet(
            "QToolButton { border: none; background: transparent; color: #526F58; padding: 5px 0; }"
            "QToolButton:hover { color: #33443B; }"
        )
        self.credentials_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.credentials_toggle.setArrowType(Qt.ArrowType.RightArrow)
        layout.addWidget(self.credentials_toggle, alignment=Qt.AlignmentFlag.AlignLeft)
        self.credentials_widget = QWidget()
        credentials = QVBoxLayout(self.credentials_widget)
        credentials.setContentsMargins(0, 0, 0, 0)
        credentials.addWidget(hint(
            "当前仓库为私有。可使用本机 gh 登录，或一次性保存有此仓库只读 Release 权限的 GitHub 令牌。"
            "只需 Contents: Read 权限；请勿填写模型 API Key。令牌仅在本机加密保存，不随更新包上传。"
        ))
        self.token_input = QLineEdit()
        self.token_input.setObjectName("update_github_token")
        self.token_input.setProperty("settingsIndependent", True)
        self.token_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.token_input.setPlaceholderText("GitHub 访问令牌（不回显已保存内容）")
        self.token_input.setAccessibleName("GitHub release access token")
        credentials.addWidget(self.token_input)
        token_actions = QHBoxLayout()
        self.save_token_button = QPushButton("仅本机保存")
        self.save_token_button.setObjectName("save_update_token_button")
        self.clear_token_button = QPushButton("清除已保存令牌")
        self.clear_token_button.setObjectName("clear_update_token_button")
        token_actions.addWidget(self.save_token_button)
        token_actions.addWidget(self.clear_token_button)
        token_actions.addStretch()
        credentials.addLayout(token_actions)
        self.credentials_widget.hide()
        self.credentials_toggle.toggled.connect(self._toggle_credentials)
        layout.addWidget(self.credentials_widget)

    def _toggle_credentials(self, expanded: bool):
        self.credentials_widget.setVisible(expanded)
        self.credentials_toggle.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)

