"""Memory editor with source inspection and explicit sharing controls."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, QSignalBlocker, QSize
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QLineEdit, QPlainTextEdit, QCheckBox,
    QMessageBox, QSplitter, QDialog, QHBoxLayout)

from ui.settings_ui.controls import SafeComboBox, NoWheelSpinBox
from ui.settings_ui.presentation import FlowLayout, ResponsiveFields, heading, scroll_content, row_widget, card, hint
from ui.settings_ui.dialogs import SettingsDialog, SettingsMessageBox, confirm
from ui.settings_ui.daylight import icon
from ui.settings_ui.list_cards import CardListDelegate

TYPE_NAMES = {"profile": "用户资料", "preference": "偏好", "event": "共同经历", "relationship": "关系",
              "promise": "约定", "state": "剧情状态", "item": "物品"}
STATUS_NAMES = {"active": "有效", "completed": "已完成", "cancelled": "已取消", "pending": "待核实"}
JOB_NAMES = {"idle": "等待新增对话", "queued": "等待整理", "running": "正在后台整理", "ready": "整理完成", "failed": "整理失败"}


class MemoryTab(QWidget):
    def __init__(self, config, parent=None, *, history=None):
        super().__init__(parent)
        self.setObjectName("memory_management_tab")
        self.config = config
        self._history = history
        self._owned_service = None
        self.current = None
        self.loaded = False
        self.dirty = False
        self._loading = False
        self._status_signature = None
        self._editor_session_id = ""
        self._filter_snapshot = None
        self._options_dirty = False
        self._options_session_id = ""
        self._compact = False
        self._compact_detail = False
        self._empty_mode = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 18)
        layout.setSpacing(14)
        heading(layout, "记忆管理")
        self.subtitle = hint("管理角色的记忆，保持连贯的对话体验。跨存档继承与共享由你选择。")
        layout.addWidget(self.subtitle)
        self.filter_toggle = QPushButton("筛选与管理")
        self.filter_toggle.setCheckable(True)
        self.filter_toggle.setChecked(True)
        self.filter_toggle.hide()
        layout.addWidget(self.filter_toggle)
        self.filters_widget = QWidget()
        row = FlowLayout()
        self.filters_widget.setLayout(row)
        self.sessions = SafeComboBox()
        self.sessions.setObjectName("memory_session_combo")
        self.characters = SafeComboBox()
        self.characters.addItem("全部角色", "")
        for character in config.characters:
            self.characters.addItem(character.name, character.memory_id)
        self.types = SafeComboBox()
        self.types.addItem("全部类型", "")
        for kind, name in TYPE_NAMES.items():
            self.types.addItem(name, kind)
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索记忆内容")
        self.search.setClearButtonEnabled(True)
        self.sessions.setMinimumWidth(140)
        self.characters.setMinimumWidth(120)
        self.types.setMinimumWidth(110)
        self.search.setMinimumWidth(160)
        for label, widget in (("选择存档", self.sessions), ("选择角色", self.characters), ("记忆类型", self.types)):
            row.addWidget(row_widget([QLabel(label), widget]))
        row.addWidget(self.search)
        layout.addWidget(self.filters_widget)
        self.range_toggle = QPushButton("记忆范围")
        self.range_toggle.setCheckable(True)
        self.range_toggle.setChecked(True)
        self.range_toggle.setVisible(False)
        layout.addWidget(self.range_toggle)
        self.options_widget = QWidget()
        options = FlowLayout(self.options_widget)
        self.inherit = QCheckBox("继承此角色的长期记忆")
        self.global_memory = QCheckBox("使用我明确共享的全局资料")
        self.save_options_button = QPushButton("保存记忆范围")
        self.save_options_button.setProperty("role", "primary")
        options.addWidget(self.inherit)
        options.addWidget(self.global_memory)
        options.addWidget(self.save_options_button)
        options.addStretch()
        layout.addWidget(self.options_widget)
        self.range_toggle.toggled.connect(self.options_widget.setVisible)
        tools = FlowLayout()
        self.tools_widget = QWidget()
        self.tools_widget.setLayout(tools)
        self.tool_buttons = {}
        for text, callback in [("刷新", self.refresh_sessions), ("新增记忆", self.new_memory),
                               ("立即整理 / 重试", self.organize), ("重新构建", self.rebuild),
                               ("本轮使用的记忆", self.show_recall)]:
            button = QPushButton(text)
            self.tool_buttons[text] = button
            button.clicked.connect(callback)
            tools.addWidget(button)
        layout.addWidget(self.tools_widget)
        self.filter_toggle.toggled.connect(lambda _: self._apply_compact_layout())
        self.progress = QLabel("")
        self.progress.setProperty("role", "muted")
        self.progress.setWordWrap(True)
        layout.addWidget(self.progress)
        splitter = self.splitter = QSplitter()
        splitter.setChildrenCollapsible(False)
        self.list_panel = QWidget()
        list_layout = QVBoxLayout(self.list_panel)
        list_layout.setContentsMargins(0, 0, 0, 0)
        self.list = QListWidget()
        self.list.setObjectName("memory_list")
        self.list.setWordWrap(True)
        self.list.setMinimumWidth(160)
        self.list.setProperty("role", "cards")
        self.list.setItemDelegate(CardListDelegate(self.list, height=112))
        list_layout.addWidget(self.list, 1)
        self.empty_panel = QWidget()
        empty_layout = QVBoxLayout(self.empty_panel)
        empty_layout.addStretch()
        empty_icon = QLabel()
        empty_icon.setPixmap(icon("memory", 72).pixmap(72, 72))
        empty_layout.addWidget(empty_icon, alignment=Qt.AlignmentFlag.AlignCenter)
        self.empty_state = QLabel("尚无记忆，可以添加一条或从已有对话整理。")
        self.empty_state.setWordWrap(True)
        self.empty_state.setProperty("role", "muted")
        self.empty_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(self.empty_state)
        self.empty_add = QPushButton("新增第一条记忆")
        self.empty_add.setProperty("role", "primary")
        self.empty_add.clicked.connect(self.new_memory)
        empty_layout.addWidget(self.empty_add, alignment=Qt.AlignmentFlag.AlignCenter)
        empty_layout.addStretch()
        layout.addWidget(self.empty_panel, 1)
        self.empty_panel.hide()
        splitter.addWidget(self.list_panel)
        editor = QWidget()
        form = QVBoxLayout(editor)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(10)
        self.editor_panel = QWidget()
        self.editor_panel.setObjectName("memory_editor_card")
        editor_layout = QVBoxLayout(self.editor_panel)
        editor_layout.setContentsMargins(18, 18, 18, 14)
        self.back_button = QPushButton("← 返回记忆列表")
        self.back_button.clicked.connect(self.show_list)
        editor_layout.addWidget(self.back_button)
        self.editor_scroll = scroll_content(editor)
        editor_layout.addWidget(self.editor_scroll, 1)
        self.kind = SafeComboBox()
        for key, name in TYPE_NAMES.items():
            self.kind.addItem(name, key)
        self.content = QPlainTextEdit()
        self.content.setObjectName("memory_content")
        self.content.setPlaceholderText("例如：希望角色称呼我为小林。")
        self.content.setMinimumHeight(90)
        self.content.setMaximumHeight(120)
        self.subject = QLineEdit()
        self.scope = SafeComboBox()
        for text, value in [("仅此存档", "session"), ("此角色长期记忆", "character"), ("全局共享资料", "global")]:
            self.scope.addItem(text, value)
        self.status = SafeComboBox()
        for key, name in STATUS_NAMES.items():
            self.status.addItem(name, key)
        self.pinned = QCheckBox("固定，优先用于回复")
        self.importance = NoWheelSpinBox()
        self.importance.setRange(1, 5)
        self.importance.setValue(3)
        self.known_by = QListWidget()
        self.known_by.setMaximumHeight(54)
        self.known_by.setFlow(QListWidget.Flow.LeftToRight)
        self.known_by.setWrapping(False)
        self.known_by.setGridSize(QSize(120, 32))
        self.known_by.setStyleSheet("QListWidget { border: none; background: transparent; padding: 0; } QListWidget::item { padding: 2px; }")
        for character in config.characters:
            item = QListWidgetItem(character.name)
            item.setData(Qt.ItemDataRole.UserRole, character.memory_id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.known_by.addItem(item)
        self.source_text = QPlainTextEdit()
        self.source_text.setReadOnly(True)
        self.source_text.setObjectName("memory_sources")
        self.source_text.setMinimumHeight(95)
        self.source_text.setMaximumHeight(120)
        form.addWidget(ResponsiveFields([("类型", self.kind), ("涉及人物", self.subject)], breakpoint=440, inline=True))
        form.addWidget(QLabel("内容"))
        form.addWidget(self.content)
        self.scope.setMinimumContentsLength(7)
        self.scope.setSizeAdjustPolicy(SafeComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        form.addWidget(ResponsiveFields([("使用范围", self.scope), ("状态", self.status),
                                         ("重要程度", self.importance)], columns=3, breakpoint=570, inline=True))
        form.addWidget(ResponsiveFields([("", self.pinned), ("知情角色", self.known_by)], breakpoint=480, inline=True))
        form.addWidget(QLabel("原始出处"))
        form.addWidget(self.source_text)
        actions = QHBoxLayout()
        actions.addStretch()
        save = self.save_button = QPushButton("保存这条记忆")
        save.setProperty("role", "primary")
        save.setObjectName("memory_save_button")
        delete = self.delete_button = QPushButton("删除这条记忆")
        delete.setProperty("role", "danger")
        delete.setObjectName("memory_delete_button")
        actions.addWidget(save)
        actions.addWidget(delete)
        editor_layout.addLayout(actions)
        self.edit_status = QLabel("记忆操作独立保存")
        self.edit_status.setProperty("role", "muted")
        editor_layout.addWidget(self.edit_status)
        splitter.addWidget(self.editor_panel)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([420, 680])
        layout.addWidget(splitter, 1)
        note = self.note = QLabel("范围与记录分别保存。删除记忆不会删除原始聊天，并阻止它从相同旧记录中恢复。")
        note.setProperty("role", "muted")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.sessions.currentIndexChanged.connect(self.refresh)
        self.characters.currentIndexChanged.connect(self.refresh)
        self.types.currentIndexChanged.connect(self.refresh)
        self.search.textChanged.connect(self.refresh)
        self.list.currentRowChanged.connect(self.select)
        self.list.itemClicked.connect(lambda: self._show_editor())
        save.clicked.connect(self.save_memory)
        delete.clicked.connect(self.delete_memory)
        self.save_options_button.clicked.connect(self.save_options)
        self.inherit.toggled.connect(self.mark_options_dirty)
        self.global_memory.toggled.connect(self.mark_options_dirty)
        self.content.textChanged.connect(self.mark_dirty)
        self.subject.textChanged.connect(self.mark_dirty)
        for combo in (self.kind, self.scope, self.status):
            combo.currentIndexChanged.connect(self.mark_dirty)
        self.pinned.toggled.connect(self.mark_dirty)
        self.importance.valueChanged.connect(self.mark_dirty)
        self.known_by.itemChanged.connect(self.mark_dirty)
        self.timer = QTimer(self)
        self.timer.setInterval(1500)
        self.timer.timeout.connect(self.refresh_status)
        self._apply_compact_layout()

    @property
    def history(self):
        if self._history is None:
            from core.sprite import chat_history
            self._history = chat_history
        return self._history

    @property
    def store(self):
        return self.history.get_memory_store()

    def showEvent(self, event):
        super().showEvent(event)
        if not self.dirty and not self._options_dirty:
            self.refresh_sessions()
        self.timer.start()

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)

    def session_id(self):
        return self.sessions.currentData() or ""

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "editor_panel"):
            compact = self.width() < 900
            if compact != self._compact:
                self._compact = compact
                self.range_toggle.setChecked(not compact)
            self._apply_compact_layout()

    def _apply_compact_layout(self):
        expanded = not self._compact or self.filter_toggle.isChecked()
        self.filter_toggle.setVisible(self._compact)
        self.subtitle.setVisible(not self._compact)
        self.filters_widget.setVisible(expanded)
        self.tools_widget.setVisible(expanded)
        self.range_toggle.setVisible(self._compact and expanded)
        self.options_widget.setVisible(expanded and (not self._compact or self.range_toggle.isChecked()))
        self.note.setVisible(not self._compact)
        self.back_button.setVisible(self._compact)
        self.list_panel.setVisible(not self._compact or not self._compact_detail)
        self.editor_panel.setVisible(not self._compact or self._compact_detail)
        self.splitter.setVisible(not self._empty_mode)
        self.empty_panel.setVisible(self._empty_mode)

    def show_list(self):
        if self.confirm_pending_edits():
            self.refresh()
            self._compact_detail = False
            self.filter_toggle.setChecked(True)
            self._apply_compact_layout()

    def _show_editor(self):
        self._empty_mode = False
        self._compact_detail = True
        if self._compact:
            self.filter_toggle.setChecked(False)
            self.filter_toggle.setText(f"筛选与管理 · {self.sessions.currentText()}")
        self._apply_compact_layout()

    def _filters(self):
        return (self.session_id(), self.characters.currentData(), self.types.currentData(), self.search.text())

    def _restore_filters(self):
        if self._filter_snapshot is None:
            return
        for combo, value in zip((self.sessions, self.characters, self.types), self._filter_snapshot[:3]):
            with QSignalBlocker(combo):
                combo.setCurrentIndex(combo.findData(value))
        with QSignalBlocker(self.search):
            self.search.setText(self._filter_snapshot[3])

    def confirm_pending_edits(self):
        if not self.dirty and not self._options_dirty:
            return True
        dialog = SettingsMessageBox(self)
        dialog.setWindowTitle("尚有未保存的记忆修改")
        dialog.setText("保存当前修改后再继续？")
        dialog.setInformativeText("记忆内容与使用范围独立保存，切换或关闭前可以保存或放弃此次修改。")
        keep = dialog.addButton("继续编辑", QMessageBox.ButtonRole.RejectRole)
        discard = dialog.addButton("放弃修改", QMessageBox.ButtonRole.DestructiveRole)
        save = dialog.addButton("保存并继续", QMessageBox.ButtonRole.AcceptRole)
        dialog.setDefaultButton(keep)
        dialog.exec()
        dialog.deleteLater()
        if dialog.clickedButton() is save:
            if self.dirty and not self._save_record():
                return False
            if self._options_dirty:
                self.save_options()
            return True
        if dialog.clickedButton() is discard:
            self.dirty = False
            self._options_dirty = False
            state = self.store.session(self._options_session_id) if self._options_session_id else None
            self._loading = True
            self.inherit.setChecked(bool(state and state["mode"] == "character"))
            self.global_memory.setChecked(bool(state and state["share_global"]))
            self._loading = False
            self.save_options_button.setText("保存记忆范围")
            return True
        return False

    def refresh_sessions(self):
        if not self.confirm_pending_edits():
            return
        selected = self.session_id() or self.history.get_active_session_id()
        self.sessions.blockSignals(True)
        self.sessions.clear()
        # Management sees every character's records. The chat history facade
        # deliberately filters its list to the active character.
        session_store = self.history.get_session_store()
        session_store.claim_legacy_sessions(self.config.characters)
        for session in session_store.list_sessions(include_archived=True):
            self.sessions.addItem(session.title, session.id)
            # Stable ownership survives renaming and duplicate display names.
            # Unclaimed legacy records stay available without guessing an owner.
            self.store.ensure_session(session.id, session.character_id)
        index = self.sessions.findData(selected)
        self.sessions.setCurrentIndex(max(0, index))
        self.sessions.blockSignals(False)
        self.loaded = True
        self.refresh()

    def refresh(self, *_):
        if not self.loaded:
            return
        if not self.confirm_pending_edits():
            self._restore_filters()
            return
        selected_id = self.current.get("id") if self.current else None
        self._filter_snapshot = self._filters()
        self._editor_session_id = self.session_id()
        self._options_session_id = self.session_id()
        state = self.store.session(self.session_id())
        self._loading = True
        self.inherit.setChecked(bool(state and state["mode"] == "character"))
        self.global_memory.setChecked(bool(state and state["share_global"]))
        self._loading = False
        self._options_dirty = False
        self.save_options_button.setText("保存记忆范围")
        self.list.blockSignals(True)
        self.list.clear()
        selected_row = 0
        for memory in self.store.list_memories(self.session_id()):
            if self.characters.currentData() and memory["character_id"] != self.characters.currentData():
                continue
            if self.types.currentData() and memory["type"] != self.types.currentData():
                continue
            if self.search.text().strip().lower() not in memory["content"].lower():
                continue
            prefix = "★ " if memory["pinned"] else ""
            item = QListWidgetItem(f"{prefix}{TYPE_NAMES[memory['type']]} · {STATUS_NAMES[memory['status']]}\n{memory['content']}")
            item.setData(Qt.ItemDataRole.UserRole, memory)
            item.setSizeHint(QSize(0, 112))
            self.list.addItem(item)
            if memory["id"] == selected_id:
                selected_row = self.list.count() - 1
        self.list.blockSignals(False)
        self._empty_mode = not self.list.count()
        self.empty_state.setText("尚无存档，请先开始聊天。" if not self.session_id() else
                                "没有符合条件的记忆。可调整筛选，或新增一条记忆。")
        self.empty_add.setVisible(bool(self.session_id()))
        self.search.setEnabled(bool(self.session_id()))
        self.characters.setEnabled(bool(self.session_id()))
        self.types.setEnabled(bool(self.session_id()))
        self.editor_panel.setEnabled(bool(self.session_id()))
        self.options_widget.setEnabled(bool(self.session_id()))
        for text, button in self.tool_buttons.items():
            button.setEnabled(bool(self.session_id()) or text == "刷新")
        if self.list.count():
            with QSignalBlocker(self.list):
                self.list.setCurrentRow(selected_row)
            self.select(selected_row)
        else:
            self._clear_editor()
        self.refresh_status()
        self._apply_compact_layout()

    def refresh_status(self):
        if not self.loaded:
            return
        state = self.store.session(self.session_id())
        signature = (self.session_id(), state["status"], state["processed"], state["updated_at"]) if state else None
        changed = signature != self._status_signature
        self._status_signature = signature
        self.progress.setText((f"{JOB_NAMES.get(state['status'], state['status'])} · 已整理 {state['processed']} 轮 · "
                               f"上次完成：{state['updated_at'] or '尚未整理'}" + (f"\n{state['error']}" if state['error'] else "")) if state else "暂无会话，请先开始聊天。")
        self.tool_buttons["立即整理 / 重试"].setEnabled(bool(state and state["status"] not in ("queued", "running")))
        self.tool_buttons["重新构建"].setEnabled(bool(state and state["status"] not in ("queued", "running")))
        status = state["status"] if state else "idle"
        if self.progress.property("state") != status:
            self.progress.setProperty("state", status)
            self.progress.style().unpolish(self.progress)
            self.progress.style().polish(self.progress)
            self.progress.setMargin(10 if status in ("failed", "running", "queued") else 0)
            self.progress.updateGeometry()
        self.tool_buttons["立即整理 / 重试"].setText("重试整理" if status == "failed" else "立即整理 / 重试")
        if changed and state and state["status"] == "ready" and not self.dirty and not self._options_dirty:
            self.refresh()

    def mark_dirty(self, *_):
        if not self._loading:
            self.dirty = True
            self.edit_status.setText("有未保存的修改")
        self.save_button.setEnabled(bool(self.session_id() and self.content.toPlainText().strip()))

    def mark_options_dirty(self, *_):
        if not self._loading:
            self._options_dirty = True
            self.save_options_button.setText("保存记忆范围 · 未保存")

    def new_memory(self):
        if not self.confirm_pending_edits():
            return
        self._clear_editor()
        self._show_editor()

    def _clear_editor(self):
        self._loading = True
        self.current = None
        self._editor_session_id = self.session_id()
        with QSignalBlocker(self.list):
            self.list.setCurrentRow(-1)
        self.content.clear()
        self.subject.clear()
        self.source_text.setPlainText("手动添加的记忆，无自动提取出处。")
        self.pinned.setChecked(False)
        self.scope.setCurrentIndex(0)
        self.status.setCurrentIndex(0)
        self.kind.setCurrentIndex(0)
        self.importance.setValue(3)
        state = self.store.session(self.session_id()) if self.session_id() else None
        for row in range(self.known_by.count()):
            item = self.known_by.item(row)
            item.setCheckState(Qt.CheckState.Checked if state and item.data(Qt.ItemDataRole.UserRole) == state["character_id"] else Qt.CheckState.Unchecked)
        self._loading = False
        self.dirty = False
        self.delete_button.setEnabled(False)
        self.save_button.setEnabled(False)
        self.edit_status.setText("新增记忆，填写后单独保存")

    def select(self, row):
        if row < 0:
            return
        target = self.list.item(row).data(Qt.ItemDataRole.UserRole)
        if not self.confirm_pending_edits():
            with QSignalBlocker(self.list):
                previous = next((i for i in range(self.list.count()) if self.current and
                    self.list.item(i).data(Qt.ItemDataRole.UserRole)["id"] == self.current["id"]), -1)
                self.list.setCurrentRow(previous)
            return
        self._loading = True
        self.current = target
        self._editor_session_id = self.session_id()
        memory = self.current
        self.kind.setCurrentIndex(self.kind.findData(memory["type"]))
        self.content.setPlainText(memory["content"])
        self.subject.setText(memory["subject"])
        self.scope.setCurrentIndex(self.scope.findData(memory["scope"]))
        self.status.setCurrentIndex(self.status.findData(memory["status"]))
        self.pinned.setChecked(memory["pinned"])
        self.importance.setValue(memory["importance"])
        for row in range(self.known_by.count()):
            item = self.known_by.item(row)
            item.setCheckState(Qt.CheckState.Checked if item.data(Qt.ItemDataRole.UserRole) in memory["visible_to"] else Qt.CheckState.Unchecked)
        sources = []
        for turn_id in memory["source_turn_ids"]:
            source = self.store.source(turn_id)
            if source:
                suffix = "（重试保留的用户原话）" if source.get("user_retained") else ("（已回溯）" if not source["active"] else "")
                sources.append(f"第 {source['position'] + 1} 轮" + suffix)
                sources.extend(f"{m['role']}: {m.get('content', '')}" for m in source["messages"]
                               if not source.get("user_retained") or m["role"] == "user")
        self.source_text.setPlainText("\n\n".join(sources) or "手动添加的记忆。")
        self._loading = False
        self.dirty = False
        self.delete_button.setEnabled(True)
        self.save_button.setEnabled(True)
        self.edit_status.setText("记忆操作独立保存")
        if self.sender() is self.list:
            self._show_editor()

    def save_memory(self):
        if self._save_record():
            self._refresh_preserving_options()
            self.edit_status.setText("这条记忆已保存")

    def _refresh_preserving_options(self):
        # A record operation does not save or discard the separate range draft.
        options = (self.inherit.isChecked(), self.global_memory.isChecked(), self._options_dirty)
        self._options_dirty = False
        self.refresh()
        self._loading = True
        self.inherit.setChecked(options[0])
        self.global_memory.setChecked(options[1])
        self._loading = False
        self._options_dirty = options[2]
        self.save_options_button.setText("保存记忆范围 · 未保存" if options[2] else "保存记忆范围")

    def _save_record(self):
        session_id = self._editor_session_id or self.session_id()
        if not session_id:
            return False
        if not self.content.toPlainText().strip():
            QMessageBox.warning(self, "记忆未保存", "请先填写记忆内容。")
            return False
        fact = dict(self.current or {})
        fact.update(type=self.kind.currentData(), content=self.content.toPlainText(), subject=self.subject.text(),
                    scope=self.scope.currentData(), status=self.status.currentData(), certainty="explicit",
                    pinned=self.pinned.isChecked(), importance=self.importance.value(),
                    visible_to=[self.known_by.item(row).data(Qt.ItemDataRole.UserRole) for row in range(self.known_by.count())
                                if self.known_by.item(row).checkState() == Qt.CheckState.Checked])
        try:
            fact["id"] = self.store.edit(session_id, fact)
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, "记忆未保存", str(exc))
            return False
        self.current = fact
        self.dirty = False
        return True

    def delete_memory(self):
        if self.current and confirm(self, "删除这条记忆？", self.current["content"],
                                    detail="删除不会影响原始聊天，也会阻止这条记忆从相同旧记录中自动恢复。",
                                    action="删除记忆", destructive=True):
            self.store.delete(self.current["id"])
            self.dirty = False
            self._refresh_preserving_options()

    def save_options(self):
        session_id = self._options_session_id or self.session_id()
        if session_id:
            self.store.configure(session_id, mode="character" if self.inherit.isChecked() else "fresh",
                                 share_global=self.global_memory.isChecked())
            self._options_dirty = False
            self.save_options_button.setText("保存记忆范围")
            self.refresh_status()

    def service(self):
        from core.runtime.app_runtime import try_get_app_runtime
        runtime = try_get_app_runtime()
        service = getattr(runtime, "memory_service", None) if runtime else None
        if service and service.store.path == self.store.path and not service.closed:
            return service
        if self._owned_service is None or self._owned_service.closed:
            from core.memory.service import MemoryService
            from llm.llm_adapter import LLMAdapterFactory
            session_store = self.history.get_session_store()
            self._owned_service = MemoryService(self.store, LLMAdapterFactory.create_adapter(**self.config.merged_llm_factory_kwargs()),
                                                character_names={c.memory_id: c.name for c in self.config.characters},
                                                context_tokens=self.config.api_config.max_context_tokens,
                                                session_owner=lambda session_id: getattr(session_store.get_session(session_id), "character_id", ""))
        return self._owned_service

    def organize(self):
        if not self.session_id():
            return
        try:
            payload = self.history.get_session_store().read_session_payload(self.session_id())
            self.store.sync_messages(self.session_id(), payload.get("messages", []))
            self.service().schedule(self.session_id(), force=True)
        except Exception as exc:
            QMessageBox.warning(self, "无法整理记忆", f"请检查模型配置或本地存储（{type(exc).__name__}）。")
        self.refresh_status()

    def rebuild(self):
        if self.session_id() and confirm(self, "重新构建记忆？", "从已有原始聊天记录重新整理当前存档的记忆。",
                                          detail="手动修改和删除标记会保留，原始聊天不会被修改。", action="开始重新构建"):
            self.store.rebuild(self.session_id())
            self.organize()

    def show_recall(self):
        memories = self.store.last_recall(self.session_id())
        dialog = SettingsDialog("本轮使用的记忆", self)
        dialog.resize(650, 580)
        layout = dialog.body
        layout.addWidget(hint(f"当前存档：{self.sessions.currentText()}  ·  {len(memories)} 条记忆"))
        content = QWidget()
        cards = QVBoxLayout(content)
        for memory in memories:
            group, box = card(TYPE_NAMES[memory["type"]])
            box.addWidget(hint({"session": "仅此存档", "character": "角色长期记忆", "global": "全局共享资料"}.get(memory.get("scope"), "")))
            label = QLabel(memory["content"])
            label.setWordWrap(True)
            box.addWidget(label)
            cards.addWidget(group)
        if not memories:
            cards.addWidget(hint("本轮没有使用长期记忆。"))
        cards.addStretch()
        layout.addWidget(scroll_content(content), 1)
        close = QPushButton("关闭")
        close.clicked.connect(dialog.accept)
        layout.addWidget(close)
        dialog.exec()
        dialog.deleteLater()

    def closeEvent(self, event):
        if not self.confirm_pending_edits():
            event.ignore()
            return
        super().closeEvent(event)

    def close_service(self):
        if self._owned_service:
            self._owned_service.close()
        return not (self._owned_service and self._owned_service.is_running())
