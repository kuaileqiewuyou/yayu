"""Offline settings smoke check; all runtime files live in a temporary profile.

Optional --output-dir keeps two demo screenshots and an assertion report. No
model service is constructed, and no existing user configuration is loaded.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, help="Keep public demo screenshots and an assertion report.")
    arguments = parser.parse_args()
    output_dir = arguments.output_dir.resolve() if arguments.output_dir else None

    from scripts.ui_snapshot import isolated_runtime

    # Cwd, LOCALAPPDATA and all six configuration paths are isolated before UI
    # or history imports. Relative memory, template and skill paths stay here.
    with isolated_runtime() as root:
        from PySide6.QtCore import QCoreApplication, QEvent, Qt, QTimer
        from PySide6.QtGui import QFont, QFontDatabase, QImage
        from PySide6.QtWidgets import QApplication, QMessageBox
        import yaml

        from config.config_manager import ConfigManager
        from config.schema import Character
        from core.security.allowed_roots import AllowedRootsStore
        from core.sessions.store import SessionStore
        from core.sprite import chat_history
        from ui.settings_ui.dialogs import SettingsMessageBox
        from ui.settings_ui.sprite_preview import SpritePreviewDialog
        from ui.settings_ui.window import SettingsWindow

        app = QApplication.instance() or QApplication([])
        font_path = Path("C:/Windows/Fonts/msyh.ttc")
        if font_path.is_file():
            font_id = QFontDatabase.addApplicationFont(str(font_path))
            families = QFontDatabase.applicationFontFamilies(font_id)
            if families:
                app.setFont(QFont(families[0], 10))
        artifacts = output_dir or root / "artifacts"
        artifacts.mkdir(parents=True, exist_ok=True)
        config = ConfigManager()
        config.system_config.skills_root = str(root / "skills")
        history_root = root / "history"
        history_store = SessionStore(
            history_root=history_root, sessions_dir=history_root / "sessions",
            index_path=history_root / "sessions.json", legacy_default_file=history_root / "default.json",
        )
        paths = []
        for index in range(2):
            path = root / "data/sprites/preview" / f"pose-{index}.png"
            path.parent.mkdir(parents=True, exist_ok=True)
            image = QImage(800, 1200, QImage.Format.Format_ARGB32)
            image.fill(Qt.GlobalColor.red if index == 0 else Qt.GlobalColor.blue)
            assert image.save(str(path))
            paths.append(str(path))
        config.config.characters = [Character(
            name="预览测试", character_setting="温柔可靠的角色。", emotion_tags="1: neutral\n2: happy",
            sprites=[{"id": 2, "path": paths[0]}, {"id": 8, "path": paths[1]}],
            emotion_items=[{"id": 1, "label": "neutral", "sprite_path": paths[0]},
                           {"id": 2, "label": "happy", "sprite_path": paths[1]}],
        )]
        config.save_characters()
        errors = []
        confirmations = []
        with (
            patch.object(chat_history, "_session_store", history_store),
            patch.object(SettingsWindow, "_template_library_root", lambda self: root / "templates"),
            patch.object(QMessageBox, "information", lambda *args: None),
            patch.object(QMessageBox, "critical", lambda *args: errors.append(str(args[-1]))),
        ):
            window = SettingsWindow(allowed_roots_store=AllowedRootsStore(root / "roots.json", project_root=root))
            try:
                window.resize(1100, 800)
                window.settings_nav.setCurrentRow(1)
                window._open_character_detail(0)
                window.character_tab.detail_tabs.setCurrentIndex(1)
                assert window.character_tab.detail_tabs.tabText(1) == "立绘与情绪"
                window.show()
                app.processEvents()
                window.sprite_list.setCurrentRow(0)
                assert window.preview_sprite_button.isEnabled() and window.delete_sprite_button.isEnabled()
                assert window.delete_sprite_button.isVisible()
                assert window.grab().save(str(artifacts / "sprite-pack-ui.png"))
                window.sprite_list.itemDoubleClicked.emit(window.sprite_list.currentItem())
                app.processEvents()
                dialog = window.findChild(SpritePreviewDialog)
                assert dialog is not None and dialog.isVisible()
                assert dialog.grab().save(str(artifacts / "sprite-preview-ui.png"))
                dialog.accept()
                app.processEvents()

                def click_delete(*, accept):
                    """Drive the real nested confirmation loop, including cancel."""
                    answered = []
                    callback_errors = []

                    def answer():
                        modal = app.activeModalWidget()
                        try:
                            assert isinstance(modal, SettingsMessageBox)
                            assert modal.windowTitle() == "删除选中立绘？"
                            assert "neutral" in modal.informativeText()
                            assert modal.defaultButton().text() == "取消"
                            role = (QMessageBox.ButtonRole.DestructiveRole if accept
                                    else QMessageBox.ButtonRole.RejectRole)
                            button = next(button for button in modal.buttons() if modal.buttonRole(button) == role)
                            answered.append(True)
                            button.click()
                        except Exception as error:
                            callback_errors.append(str(error))
                            if modal is not None:
                                modal.reject()

                    QTimer.singleShot(0, answer)
                    window.delete_sprite_button.click()
                    assert not callback_errors, callback_errors
                    assert answered == [True]
                    confirmations.append("confirm" if accept else "cancel")

                window.char_setting_edit.setPlainText("未保存的角色设定也应保留。")
                click_delete(accept=False)
                assert window.sprite_list.count() == 2
                assert not window.character_controller.pending_removed_sprite_paths
                assert window._collect_emotion_bindings_from_table()[0]["sprite_path"] == paths[0]
                click_delete(accept=True)
                assert window.char_setting_edit.toPlainText() == "未保存的角色设定也应保留。"
                assert window.character_detail_content_widget.isVisible()
                assert window.sprite_list.count() == 1
                assert window._collect_emotion_bindings_from_table()[0]["sprite_path"] == ""
                assert Path(paths[0]).exists()

                # A failed save must retain the file and pending deletion for retry.
                def fail_save():
                    raise OSError("simulated save failure")

                with patch.object(config, "save_backgrounds", fail_save):
                    window._save_config()
                assert errors and "simulated save failure" in errors[-1]
                assert Path(paths[0]).exists()
                assert window.character_controller.pending_removed_sprite_paths == {paths[0]}
                window._save_config()
                assert len(errors) == 1, errors
                assert not window.character_controller.pending_removed_sprite_paths
                assert not Path(paths[0]).exists()
                saved = yaml.safe_load(config._CHARACTERS_CONFIG_PATH.read_text(encoding="utf-8"))[0]
                assert [item["id"] for item in saved["sprites"]] == [8]
                assert saved["emotion_items"][0]["sprite_path"] == ""
                assert saved["emotion_items"][1]["sprite_path"] == saved["sprites"][0]["path"]
                assert Path(saved["sprites"][0]["path"]).is_file()
                assert saved["character_setting"] == "未保存的角色设定也应保留。"
                report = {
                    "status": "PASS", "qpa": app.platformName(), "isolated_config_paths": 6,
                    "confirmations": confirmations, "default_confirmation": "cancel",
                    "save_failure_retains_sprite": True, "retry_removes_unused_sprite": True,
                    "remaining_sprite_ids": [item["id"] for item in saved["sprites"]],
                    "persona_edit_preserved": True, "model_services_started": False,
                }
                (artifacts / "sprite-pack-report.json").write_text(
                    json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
                )
            finally:
                window.close()
                window.deleteLater()
                QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
                app.processEvents()
        print("sprite pack UI / preview / cancel / deletion / save failure retry / persisted bindings: PASS")


if __name__ == "__main__":
    main()
