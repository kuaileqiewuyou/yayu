from __future__ import annotations

import filecmp
import shutil
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QSize, Signal, QSignalBlocker
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QListWidgetItem, QPushButton, QSizePolicy, QTableWidgetItem, QVBoxLayout

from config.schema import Character
from ui.settings_ui.character_card_view_model import build_character_card_view_model
from ui.settings_ui.controls import SafeComboBox
from ui.settings_ui.image_preview import image_preview


class _ClickableCharacterAvatar(QLabel):
    clicked = Signal()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


DEFAULT_EMOTION_BINDINGS = [
    (1, "neutral"),
    (2, "happy"),
    (3, "sad"),
    (4, "angry"),
    (5, "surprised"),
]


class CharacterSettingsController:
    """Small logic facade for SettingsWindow character-management behavior."""

    CARD_WIDTH = 280
    CARD_HEIGHT = 440
    CARD_SPACING = 12

    def __init__(self, window: Any | None = None):
        self.window = window
        self.pending_removed_sprite_paths: set[str] = set()

    @staticmethod
    def overview_summary_text(characters: list[Any]) -> str:
        sprite_count = 0
        emotion_count = 0
        for character in characters:
            sprite_count += len(getattr(character, "sprites", []) or [])
            emotion_count += len(getattr(character, "emotion_items", []) or [])
        return f"{len(characters)} 个角色 · {sprite_count} 张立绘 · {emotion_count} 个情绪绑定"

    @staticmethod
    def card_avatar_source(character: Any, *, placeholder_text: str = "头像") -> str:
        return build_character_card_view_model(character, placeholder_text=placeholder_text).avatar_source

    @staticmethod
    def card_stats_text(character: Any, *, placeholder_text: str = "头像") -> str:
        return build_character_card_view_model(character, placeholder_text=placeholder_text).stats_text

    @staticmethod
    def emotion_item_values(item: Any) -> tuple[str, str, str]:
        if isinstance(item, dict):
            return str(item.get("id", "")), str(item.get("label", "")), str(item.get("sprite_path", ""))
        return str(getattr(item, "id", "")), str(getattr(item, "label", "")), str(getattr(item, "sprite_path", ""))

    @classmethod
    def format_emotion_items_for_editor(cls, character: Any) -> str:
        emotion_items = getattr(character, "emotion_items", []) or []
        if emotion_items:
            lines = []
            for item in emotion_items:
                item_id, label, _sprite_path = cls.emotion_item_values(item)
                lines.append(f"{item_id}: {label}".strip())
            return "\n".join(lines)
        return getattr(character, "emotion_tags", "")

    @staticmethod
    def sprite_entry_values(sprite: Any, fallback_id: int) -> tuple[int, str]:
        if isinstance(sprite, dict):
            raw_id = sprite.get("id", fallback_id)
            path = sprite.get("path", "")
        else:
            raw_id = getattr(sprite, "id", fallback_id)
            path = getattr(sprite, "path", "")
        try:
            sprite_id = int(raw_id) if raw_id is not None else fallback_id
        except (TypeError, ValueError):
            sprite_id = fallback_id
        return max(0, sprite_id), str(path or "")

    @classmethod
    def sprite_entries_for_character(cls, character: Any) -> list[tuple[int, str]]:
        return [
            (int(entry["id"]), str(entry.get("path", "") or ""))
            for entry in cls.normalized_sprite_entries(character)
            if entry.get("path")
        ]

    @classmethod
    def sprite_paths_for_character(cls, character: Any) -> list[str]:
        return [path for _sprite_id, path in cls.sprite_entries_for_character(character)]

    @classmethod
    def next_sprite_id(cls, sprites: list[Any]) -> int:
        ids = [cls.sprite_entry_values(sprite, index)[0] for index, sprite in enumerate(sprites)]
        return max(ids, default=-1) + 1

    def placeholder_text(self) -> str:
        if self.window is None:
            return "头像"
        character_tab = getattr(self.window, "character_tab", None)
        return getattr(character_tab, "character_card_placeholder_text", "头像")

    def character_card_avatar_text(self, character: Any) -> str:
        return self.card_avatar_source(character, placeholder_text=self.placeholder_text())

    def character_card_stats_text(self, character: Any) -> str:
        return self.card_stats_text(character, placeholder_text=self.placeholder_text())

    def character_overview_summary_text(self) -> str:
        return self.overview_summary_text(self.window.config.characters or [])

    def sprite_entries_for_current_character(self) -> list[tuple[int, str]]:
        character = self.current_character()
        if character is None:
            return []
        return self.sprite_entries_for_character(character)

    def sprite_paths_for_current_character(self) -> list[str]:
        return [path for _sprite_id, path in self.sprite_entries_for_current_character()]

    def sprite_ids_for_current_character(self) -> list[int]:
        return [sprite_id for sprite_id, _path in self.sprite_entries_for_current_character()]

    @staticmethod
    def sprite_display_text(sprite_id: int) -> str:
        return f"立绘 #{sprite_id + 1:02d}"

    @staticmethod
    def sprite_icon(path: str) -> QIcon:
        if QApplication.instance() is None:
            return QIcon()
        # One bounded thumbnail is shared by the gallery and every emotion combo.
        return QIcon(image_preview(path, QSize(180, 280)))

    @classmethod
    def _set_combo_sprite_items(
        cls,
        combo: Any,
        sprite_paths: list[str],
        selected_path: str = "",
        *,
        sprite_ids: list[int] | None = None,
    ) -> None:
        combo.clear()
        sprite_paths = list(sprite_paths)
        effective_ids = list(sprite_ids) if sprite_ids is not None else list(range(len(sprite_paths)))
        if "" not in sprite_paths:
            sprite_paths.insert(0, "")
            effective_ids.insert(0, -1)
        combo._sprite_paths = list(sprite_paths)
        for index, path in enumerate(sprite_paths):
            if path:
                sprite_id = effective_ids[index] if index < len(effective_ids) else index
                display_text = cls.sprite_display_text(sprite_id)
            else:
                display_text = "未绑定"
            combo.addItem(display_text)
            item_index = index
            if hasattr(combo, "setItemData"):
                combo.setItemData(item_index, path, Qt.ItemDataRole.UserRole)
                combo.setItemData(item_index, path, Qt.ItemDataRole.ToolTipRole)
            if hasattr(combo, "setItemIcon"):
                combo.setItemIcon(item_index, cls.sprite_icon(path))

        if selected_path and selected_path not in combo._sprite_paths:
            next_id = max((item_id for item_id in effective_ids if item_id >= 0), default=-1) + 1
            combo._sprite_paths.append(selected_path)
            display_text = cls.sprite_display_text(next_id)
            combo.addItem(display_text)
            item_index = len(combo._sprite_paths) - 1
            if hasattr(combo, "setItemData"):
                combo.setItemData(item_index, selected_path, Qt.ItemDataRole.UserRole)
                combo.setItemData(item_index, selected_path, Qt.ItemDataRole.ToolTipRole)
            if hasattr(combo, "setItemIcon"):
                combo.setItemIcon(item_index, cls.sprite_icon(selected_path))

        if selected_path and selected_path in combo._sprite_paths:
            combo.setCurrentIndex(combo._sprite_paths.index(selected_path))
        elif sprite_paths:
            combo.setCurrentIndex(0)

    @staticmethod
    def _combo_sprite_path(combo: Any) -> str:
        paths = getattr(combo, "_sprite_paths", [])
        current_index = combo.currentIndex() if hasattr(combo, "currentIndex") else -1
        if 0 <= current_index < len(paths):
            return str(paths[current_index])
        current_data = combo.currentData() if hasattr(combo, "currentData") else None
        if current_data:
            return str(current_data)
        current_text = combo.currentText().strip() if combo is not None else ""
        return current_text if not current_text.startswith("立绘 #") else ""

    def current_character(self) -> Any | None:
        if not (self.window.config.characters and 0 <= self.window._current_character_index < len(self.window.config.characters)):
            return None
        return self.window.config.characters[self.window._current_character_index]

    @classmethod
    def normalized_sprite_entries(cls, character: Any) -> list[dict]:
        entries = []
        sprites = character if isinstance(character, (list, tuple)) else getattr(character, "sprites", [])
        for sprite in sprites or []:
            if isinstance(sprite, dict):
                entry = dict(sprite)
            elif hasattr(sprite, "model_dump"):
                entry = sprite.model_dump()
            else:
                entry = {
                    "id": getattr(sprite, "id", None),
                    "path": getattr(sprite, "path", ""),
                    "voice_path": getattr(sprite, "voice_path", None),
                    "voice_text": getattr(sprite, "voice_text", None),
                }
            entries.append(entry)

        assigned_ids: list[int | None] = []
        used_ids: set[int] = set()
        for entry in entries:
            raw_id = entry.get("id")
            try:
                sprite_id = int(raw_id) if raw_id is not None else None
            except (TypeError, ValueError):
                sprite_id = None
            if sprite_id is None or sprite_id < 0 or sprite_id in used_ids:
                assigned_ids.append(None)
                continue
            assigned_ids.append(sprite_id)
            used_ids.add(sprite_id)

        next_available = max(used_ids, default=-1) + 1
        for index, sprite_id in enumerate(assigned_ids):
            if sprite_id is None:
                assigned_ids[index] = next_available
                used_ids.add(next_available)
                next_available += 1

        for entry, sprite_id in zip(entries, assigned_ids):
            entry["id"] = sprite_id
        return entries

    def append_emotion_binding_row(self, item_id: str, label: str, sprite_path: str) -> None:
        table = self.window.emotion_binding_table
        row = table.rowCount()
        table.insertRow(row)
        table.setItem(row, 0, QTableWidgetItem(str(item_id)))
        table.setItem(row, 1, QTableWidgetItem(str(label)))

        sprite_combo = SafeComboBox()
        unbound_default = sprite_path == "__UNBOUND__"
        requested_sprite_path = "" if unbound_default else sprite_path
        sprite_paths = self.sprite_paths_for_current_character()
        sprite_ids = self.sprite_ids_for_current_character()
        if unbound_default:
            sprite_paths = [""] + sprite_paths
            sprite_ids = [-1] + sprite_ids
        self._set_combo_sprite_items(sprite_combo, sprite_paths, requested_sprite_path, sprite_ids=sprite_ids)
        table.setCellWidget(row, 2, sprite_combo)
        if hasattr(self.window, "_mark_settings_dirty"):
            sprite_combo.activated.connect(self.window._mark_settings_dirty)

        import_button = QPushButton("导入图片")
        import_button.clicked.connect(lambda _checked=False, r=row: self.window._import_sprite_for_emotion_row(r))
        table.setCellWidget(row, 3, import_button)

    def populate_emotion_binding_table(self, character: Any) -> None:
        self.window.emotion_binding_table.setRowCount(0)
        for item in getattr(character, "emotion_items", []) or []:
            item_id, label, sprite_path = self.emotion_item_values(item)
            self.append_emotion_binding_row(item_id, label, sprite_path)

    def add_emotion_binding_row(self) -> None:
        existing_ids = []
        table = self.window.emotion_binding_table
        for row in range(table.rowCount()):
            item = table.item(row, 0)
            try:
                existing_ids.append(int(item.text()))
            except (AttributeError, TypeError, ValueError):
                continue
        next_id = max(existing_ids, default=0) + 1
        sprite_paths = self.sprite_paths_for_current_character()
        default_sprite = sprite_paths[0] if sprite_paths else ""
        self.append_emotion_binding_row(str(next_id), "new_emotion", default_sprite)

    def delete_selected_emotion_binding_row(self) -> None:
        row = self.window.emotion_binding_table.currentRow()
        if row < 0:
            return
        self.window.emotion_binding_table.removeRow(row)

    def fill_default_emotion_bindings(self) -> None:
        existing_labels = set()
        table = self.window.emotion_binding_table
        for row in range(table.rowCount()):
            label_item = table.item(row, 1)
            label = label_item.text().strip().lower() if label_item is not None else ""
            if label:
                existing_labels.add(label)
        for item_id, label in DEFAULT_EMOTION_BINDINGS:
            if label.lower() in existing_labels:
                continue
            self.append_emotion_binding_row(str(item_id), label, "__UNBOUND__")
            existing_labels.add(label.lower())

    def refresh_emotion_binding_sprite_combos(self) -> None:
        sprite_paths = self.sprite_paths_for_current_character()
        sprite_ids = self.sprite_ids_for_current_character()
        table = self.window.emotion_binding_table
        for row in range(table.rowCount()):
            combo = table.cellWidget(row, 2)
            if combo is None:
                continue
            current = self._combo_sprite_path(combo)
            self._set_combo_sprite_items(combo, sprite_paths, current, sprite_ids=sprite_ids)

    def collect_emotion_bindings_from_table(self) -> list[dict]:
        bindings = []
        table = self.window.emotion_binding_table
        for row in range(table.rowCount()):
            id_item = table.item(row, 0)
            label_item = table.item(row, 1)
            combo = table.cellWidget(row, 2)
            label = label_item.text().strip() if label_item is not None else ""
            sprite_path = self._combo_sprite_path(combo).strip() if combo is not None else ""
            if not label and not sprite_path:
                continue
            try:
                item_id = int(id_item.text().strip()) if id_item is not None else row + 1
            except ValueError:
                item_id = row + 1
            if item_id <= 0:
                item_id = 1
            bindings.append({"id": item_id, "label": label, "sprite_path": sprite_path})
        return bindings

    def character_sprite_dir(self, character_name: str) -> Path:
        safe_name = self.safe_character_resource_name(character_name)
        return self.window.config._CHARACTERS_CONFIG_PATH.parent.parent / "sprites" / safe_name

    @staticmethod
    def safe_character_resource_name(character_name: str) -> str:
        return "".join(
            ch if ch.isalnum() or ch in ("-", "_") else "_"
            for ch in character_name.strip()
        ) or "character"

    def character_avatar_dir(self, character_name: str) -> Path:
        safe_name = self.safe_character_resource_name(character_name)
        return self.window.config._CHARACTERS_CONFIG_PATH.parent.parent / "avatars" / safe_name

    def refresh_sprite_list_for_character(self, character: Any) -> None:
        self.window.sprite_list.clear()
        for sprite_id, path in self.sprite_entries_for_character(character):
            item = QListWidgetItem(self.sprite_icon(path), self.sprite_display_text(sprite_id))
            item.setData(Qt.ItemDataRole.UserRole, path)
            item.setData(Qt.ItemDataRole.UserRole + 1, sprite_id)
            item.setToolTip(path)
            self.window.sprite_list.addItem(item)

    @staticmethod
    def _same_sprite_path(left: str, right: str) -> bool:
        if not left or not right:
            return False
        try:
            return Path(left).resolve() == Path(right).resolve()
        except (OSError, ValueError):
            return left == right

    def _binding_matches_sprite(self, bound: str, sprite: str) -> bool:
        if self._same_sprite_path(bound, sprite):
            return True
        if not bound or not sprite:
            return False
        # Older saves kept the import source in emotion_items while the pack
        # pointed at an archived copy. Resolve this only on deletion, not while
        # opening the character page, to keep preview loading fast.
        config_path = getattr(self.window.config, "_CHARACTERS_CONFIG_PATH", None)
        if config_path is None:
            return False
        source, archived = Path(bound), Path(sprite)
        root = (Path(config_path).parent.parent / "sprites").resolve()
        if not archived.resolve().is_relative_to(root):
            return False
        matching_name = (source.name == archived.name or (
            source.suffix == archived.suffix and archived.stem.startswith(source.stem + "__sprite_")))
        return matching_name and self._same_file_content(source, archived)

    def delete_selected_sprite(self) -> str | None:
        """Remove one entry; defer managed-file deletion until settings persist."""
        character = self.current_character()
        selected = self.window.sprite_list.currentItem()
        if character is None or selected is None:
            return None
        sprite_id = selected.data(Qt.ItemDataRole.UserRole + 1)
        path = str(selected.data(Qt.ItemDataRole.UserRole) or "")
        entries = self.normalized_sprite_entries(character)
        remaining = [entry for entry in entries if entry["id"] != sprite_id]
        if len(remaining) == len(entries):
            return None
        row = self.window.sprite_list.currentRow()
        character.sprites = remaining
        self.pending_removed_sprite_paths.add(path)
        # Duplicate entries can still share this file. Keep their bindings valid.
        if not any(self._same_sprite_path(entry.get("path", ""), path) for entry in remaining):
            replacements = {}

            def replacement(bound):
                if bound not in replacements:
                    replacements[bound] = bound
                    if self._binding_matches_sprite(bound, path):
                        replacements[bound] = next((entry["path"] for entry in remaining
                            if self._binding_matches_sprite(bound, entry.get("path", ""))), "")
                return replacements[bound]

            for item in getattr(character, "emotion_items", []) or []:
                _, _, bound = self.emotion_item_values(item)
                updated = replacement(bound)
                if updated != bound:
                    if isinstance(item, dict):
                        item["sprite_path"] = updated
                    else:
                        item.sprite_path = updated
            table = self.window.emotion_binding_table
            for index in range(table.rowCount()):
                combo = table.cellWidget(index, 2)
                if combo is not None:
                    bound = self._combo_sprite_path(combo)
                    updated = replacement(bound)
                    if updated != bound:
                        self._set_combo_sprite_items(combo, ["", updated] if updated else [""], updated)
        self.refresh_emotion_binding_sprite_combos()
        self.refresh_sprite_list_for_character(character)
        if self.window.sprite_list.count():
            self.window.sprite_list.setCurrentRow(min(row, self.window.sprite_list.count() - 1))
        if hasattr(self.window, "avatar_path_edit"):
            self.update_avatar_editor(self.window.avatar_path_edit.text())
        return path

    @staticmethod
    def _same_file_content(left: Path, right: Path) -> bool:
        try:
            return left.stat().st_size == right.stat().st_size and filecmp.cmp(left, right, shallow=False)
        except OSError:
            return False

    def _collision_safe_sprite_destination(self, source: Path, target_dir: Path, sprite_id: int) -> Path:
        destination = target_dir / source.name
        if not destination.exists() or self._same_file_content(source, destination):
            return destination
        suffix_index = 0
        while True:
            suffix = f"__sprite_{sprite_id + 1:02d}" if suffix_index == 0 else f"__sprite_{sprite_id + 1:02d}_{suffix_index}"
            candidate = target_dir / f"{source.stem}{suffix}{source.suffix}"
            if not candidate.exists() or self._same_file_content(source, candidate):
                return candidate
            suffix_index += 1

    def archive_character_sprites(self, character_name: str, sprites: list) -> list[dict]:
        target_dir = self.character_sprite_dir(character_name)
        target_dir.mkdir(parents=True, exist_ok=True)
        archived = []
        normalized = self.normalized_sprite_entries(sprites)
        for entry in normalized:
            sprite_id = int(entry["id"])
            src_path = str(entry.get("path", "") or "")
            if not src_path:
                continue
            src = Path(src_path)
            if src.exists():
                dest = self._collision_safe_sprite_destination(src, target_dir, sprite_id)
                if src.resolve() != dest.resolve():
                    shutil.copy2(src, dest)
                entry["path"] = str(dest.resolve())
            else:
                entry["path"] = src_path
            archived.append(entry)
        return archived

    def archive_character_avatar(self, character_name: str, avatar_path: str) -> str:
        if not avatar_path:
            return ""
        source = Path(avatar_path)
        if not source.exists():
            return avatar_path
        target_dir = self.character_avatar_dir(character_name)
        target_dir.mkdir(parents=True, exist_ok=True)
        destination = target_dir / source.name
        if source.resolve() != destination.resolve():
            shutil.copy2(source, destination)
        return str(destination.resolve())

    @staticmethod
    def fallback_avatar_source(character: Any) -> str:
        primary_sprite_path = getattr(character, "primary_sprite_path", "") or ""
        if primary_sprite_path:
            return str(primary_sprite_path)
        for sprite in getattr(character, "sprites", []) or []:
            path = sprite.get("path", "") if isinstance(sprite, dict) else getattr(sprite, "path", "")
            if path:
                return str(path)
        return ""

    def update_avatar_editor(self, explicit_avatar_path: str) -> None:
        character = self.current_character()
        if character is None:
            return
        explicit_avatar_path = str(explicit_avatar_path or "")
        self.window.avatar_path_edit.setText(explicit_avatar_path)
        fallback_source = self.fallback_avatar_source(character)
        preview_source = explicit_avatar_path or fallback_source
        preview = image_preview(preview_source, self.window.avatar_preview_label.size())
        self.window.avatar_preview_label.setPixmap(QPixmap())
        self.window.avatar_preview_label.setToolTip(preview_source)
        if not preview.isNull():
            self.window.avatar_preview_label.setText("")
            self.window.avatar_preview_label.setPixmap(preview)
        else:
            self.window.avatar_preview_label.setText("头像")

        if explicit_avatar_path:
            status = "当前预览使用显式头像；保存后将复制到角色头像目录。"
        elif fallback_source:
            status = "未设置显式头像，当前预览使用第一张立绘。"
        else:
            status = "未设置显式头像或立绘，角色卡片将显示占位头像。"
        self.window.avatar_status_label.setText(status)
        self.window.clear_avatar_button.setEnabled(bool(explicit_avatar_path))

    def add_imported_sprite_to_emotion_row(self, row: int, file_path: str) -> None:
        character = self.current_character()
        if character is None or not file_path:
            return
        existing = self.normalized_sprite_entries(character)
        if not any(sprite.get("path") == file_path for sprite in existing):
            existing.append({"id": self.next_sprite_id(existing), "path": file_path})
        character.sprites = existing
        self.refresh_sprite_list_for_character(character)
        self.refresh_emotion_binding_sprite_combos()
        combo = self.window.emotion_binding_table.cellWidget(row, 2)
        if combo is not None:
            self._set_combo_sprite_items(
                combo,
                self.sprite_paths_for_current_character(),
                file_path,
                sprite_ids=self.sprite_ids_for_current_character(),
            )

    def import_sprite_paths_for_current_character(self, file_paths: list[str]) -> None:
        character = self.current_character()
        if character is None or not file_paths:
            return
        existing = self.normalized_sprite_entries(character)
        for path in file_paths:
            if any(sprite.get("path") == path for sprite in existing):
                continue
            existing.append({"id": self.next_sprite_id(existing), "path": path})
        character.sprites = existing
        self.refresh_sprite_list_for_character(character)
        self.refresh_emotion_binding_sprite_combos()

    def show_character_overview_page(self) -> None:
        self.stash_character_form()
        self.window.character_stack.setCurrentWidget(self.window.character_overview_page)

    def show_character_detail_page(self) -> None:
        self.window.character_stack.setCurrentWidget(self.window.character_detail_page)

    def _create_character_card(self, index: int, character: Any):
        name = getattr(character, "name", "")
        card = QFrame()
        card.setObjectName(f"character_card_{index}")
        card.setAccessibleName(f"Character card {index + 1}")
        card.setFrameShape(QFrame.Shape.StyledPanel)
        card.setMinimumWidth(240)
        card.setFixedHeight(self.CARD_HEIGHT)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        card.setStyleSheet(
            "QFrame#character_card_%d { border: 1px solid #DAE1D7; border-radius: 8px; background: #FFFFFF; }" % index
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(12)
        view_model = build_character_card_view_model(
            character,
            placeholder_text=getattr(self.window.character_tab, "character_card_placeholder_text", "头像"),
        )
        avatar_label = _ClickableCharacterAvatar(view_model.avatar_text)
        avatar_label.setObjectName(f"character_card_avatar_{index}")
        avatar_label.setAccessibleName(f"Open character detail {index + 1}")
        avatar_label.clicked.connect(lambda i=index: self.window._open_character_detail(i))
        avatar_label.setToolTip(view_model.avatar_source)
        avatar_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar_label.setMinimumSize(QSize(180, 220))
        avatar_pixmap = image_preview(view_model.avatar_source, QSize(300, 250))
        if not avatar_pixmap.isNull():
            avatar_label.setText("")
            avatar_label.setPixmap(avatar_pixmap)
        avatar_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        avatar_label.setStyleSheet(
            "QLabel { border: none; border-radius: 6px; color: #657169; background: #F1F4ED; }"
        )
        stats_label = QLabel(view_model.stats_text)
        stats_label.setObjectName(f"character_card_stats_{index}")
        stats_label.setAccessibleName(f"Character card stats {index + 1}")
        stats_label.setStyleSheet("QLabel { color: #657169; border: none; background: transparent; }")
        title = QLabel(name)
        title.setProperty("role", "character-name")
        description = QLabel((getattr(character, "character_setting", "") or "还没有填写角色设定。").replace("\n", " ")[:65])
        description.setWordWrap(True)
        description.setProperty("role", "muted")
        description.setMaximumHeight(48)
        button = QPushButton("打开详情")
        button.setToolTip(name)
        button.setObjectName(f"character_card_button_{index}")
        button.setAccessibleName(f"Select character {index + 1}")
        button.clicked.connect(lambda _checked=False, i=index: self.window._open_character_detail(i))
        character_id = str(getattr(character, "memory_id", "") or "")
        use_button = QPushButton("使用此角色")
        use_button.setObjectName(f"character_card_use_button_{index}")
        use_button.setProperty("character_id", character_id)
        use_button.setProperty("role", "primary")
        use_button.setAccessibleName(f"使用角色：{name}")
        use_button.clicked.connect(lambda _checked=False, identity=character_id: self.window._use_character(identity))
        actions = QHBoxLayout()
        actions.setSpacing(8)
        actions.addWidget(button, 1)
        actions.addWidget(use_button, 1)
        card_layout.addWidget(avatar_label, 1)
        card_layout.addWidget(title)
        card_layout.addWidget(description)
        stats_label.setParent(card)
        stats_label.hide()
        card_layout.addLayout(actions)
        self.window.character_card_use_buttons.append(use_button)
        self.refresh_character_use_buttons()
        return card, button, avatar_label, stats_label

    def refresh_character_use_buttons(self) -> None:
        active_id = getattr(self.window, "_active_character_id", "")
        enabled = getattr(self.window, "_character_switch_enabled", True)
        managed = getattr(self.window, "_character_switch_managed", False)
        for button in getattr(self.window, "character_card_use_buttons", []):
            identity = str(button.property("character_id") or "")
            active = identity == active_id
            button.setText("正在使用" if active else "使用此角色")
            button.setEnabled(bool(identity) and enabled and not active)
            if active:
                tooltip = "当前聊天角色" if managed else "已选角色，下次启动主界面时生效"
            elif not enabled:
                tooltip = "请等待当前回复完成后再切换角色"
            else:
                tooltip = "保存设定并立即切换聊天角色" if managed else "保存设定并选择此角色，下次启动主界面时生效"
            button.setToolTip(tooltip)

    def refresh_character_list(self) -> None:
        self.window.character_overview_summary_label.setText(self.character_overview_summary_text())
        self.window.character_card_frames = []
        self.window.character_card_buttons = []
        self.window.character_card_avatar_labels = []
        self.window.character_card_stats_labels = []
        self.window.character_card_use_buttons = []
        self.window.character_list.clear()
        while self.window.character_card_grid_layout.count():
            item = self.window.character_card_grid_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                if hasattr(widget, "hide"):
                    widget.hide()
                widget.deleteLater()
        for index, character in enumerate(self.window.config.characters):
            name = getattr(character, "name", "")
            self.window.character_list.addItem(name)
            card, button, avatar_label, stats_label = self._create_character_card(index, character)
            self.window.character_card_frames.append(card)
            self.window.character_card_buttons.append(button)
            self.window.character_card_avatar_labels.append(avatar_label)
            self.window.character_card_stats_labels.append(stats_label)
        self.reflow_character_cards()
        parts = getattr(self.window, "character_tab", None)
        switch = getattr(parts, "switch_character", None)
        if switch is not None:
            with QSignalBlocker(switch):
                switch.clear()
                switch.addItems([character.name for character in self.window.config.characters])
                switch.setCurrentIndex(self.window._current_character_index)

    def reflow_character_cards(self, available_width: int | None = None) -> None:
        layout = self.window.character_card_grid_layout
        while layout.count():
            layout.takeAt(0)

        if available_width is None:
            grid = getattr(self.window, "character_card_grid", None)
            available_width = grid.width() if grid is not None else 3 * self.CARD_WIDTH + 2 * self.CARD_SPACING
        columns = min(3, max(1, (max(1, available_width) + self.CARD_SPACING) // (self.CARD_WIDTH + self.CARD_SPACING)))
        for column in range(3):
            layout.setColumnStretch(column, 1 if column < columns else 0)
        for index, card in enumerate(self.window.character_card_frames):
            layout.addWidget(card, index // columns, index % columns)

    def open_character_detail(self, index: int) -> None:
        self.stash_character_form()
        self.load_character_into_form(index)
        if 0 <= index < len(self.window.config.characters):
            self.show_character_detail_page()

    def handle_character_selection_changed(self, row: int) -> None:
        self.load_character_into_form(row)

    def add_character(self, name: str) -> None:
        self.stash_character_form()
        role_name = name.strip()
        if not role_name:
            return
        self.window.config.characters.append(Character(name=role_name))
        self.refresh_character_list()
        new_index = len(self.window.config.characters) - 1
        self.window.character_list.setCurrentRow(new_index)
        self.open_character_detail(new_index)

    def stash_character_form(self):
        """Keep the outgoing editor draft when navigating between characters."""
        character = getattr(self, "_form_character", None)
        if character is None or character is not self.current_character():
            return
        from ui.settings_ui.save_service import save_character_settings_from_controls
        save_character_settings_from_controls(
            self.window.config.characters, self.window._current_character_index, self.window,
            collect_emotion_bindings=self.collect_emotion_bindings_from_table,
            archive_character_sprites=lambda _name, sprites: sprites,
        )

    def update_character_detail_visibility(self, has_selection: bool) -> None:
        if has_selection:
            self.window.character_empty_state_label.hide()
            self.window.character_detail_content_widget.show()
        else:
            self.window.character_empty_state_label.show()
            self.window.character_detail_content_widget.hide()

    def load_character_into_form(self, index: int) -> None:
        previous = getattr(self.window, "_loading_settings", False)
        self.window._loading_settings = True
        try:
            self._load_character_into_form(index)
        finally:
            self.window._loading_settings = previous

    def _load_character_into_form(self, index: int) -> None:
        if index < 0 or index >= len(self.window.config.characters):
            self.update_character_detail_visibility(False)
            return
        self.update_character_detail_visibility(True)
        self.window._current_character_index = index
        character = self.window.config.characters[index]
        self._form_character = character
        parts = getattr(self.window, "character_tab", None)
        if hasattr(parts, "header_name"):
            parts.header_title.setText("角色管理")
            parts.header_name.setText(character.name)
            parts.header_avatar.setPixmap(image_preview(self.card_avatar_source(character), QSize(64, 64)))
            with QSignalBlocker(parts.switch_character):
                parts.switch_character.setCurrentIndex(index)
        self.window.char_name_edit.setText(character.name)
        default_skills = getattr(character, "default_skills", []) or []
        self.window.char_default_skills_edit.setText(", ".join(skill for skill in default_skills if skill))
        self.window.char_setting_edit.setPlainText(character.character_setting)
        voice_text_fields = {
            "refer_audio_path_edit": getattr(character, "refer_audio_path", "") or "",
        }
        for control_name, value in voice_text_fields.items():
            control = getattr(self.window, control_name, None)
            if control is not None:
                control.setText(value)
        prompt_text_edit = getattr(self.window, "prompt_text_edit", None)
        if prompt_text_edit is not None:
            prompt_text_edit.setPlainText(getattr(character, "prompt_text", "") or "")
        prompt_lang_combo = getattr(self.window, "prompt_lang_combo", None)
        if prompt_lang_combo is not None:
            prompt_lang_combo.setCurrentText(getattr(character, "prompt_lang", "zh") or "zh")
        speech_speed_spin = getattr(self.window, "speech_speed_spin", None)
        if speech_speed_spin is not None:
            speech_speed_spin.setValue(getattr(character, "speech_speed", 1.0) or 1.0)
        self.update_avatar_editor(getattr(character, "avatar", "") or getattr(character, "avatar_path", ""))
        self.window.emotion_tags_edit.setPlainText(self.format_emotion_items_for_editor(character))
        if hasattr(self.window.emotion_tags_edit, "setReadOnly"):
            self.window.emotion_tags_edit.setReadOnly(bool(getattr(character, "emotion_items", []) or []))
        if hasattr(self.window, "emotion_tags_label"):
            self.window.emotion_tags_label.setText(
                "情绪编号预览"
                if getattr(character, "emotion_items", [])
                else "情绪标签"
            )
        self.populate_emotion_binding_table(character)
        self.refresh_sprite_list_for_character(character)
        if hasattr(parts, "refresh_emotion_chips"):
            parts.refresh_emotion_chips()
