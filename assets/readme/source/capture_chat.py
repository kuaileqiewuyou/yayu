"""Capture the real Yayu UI with shipped XiaoYa assets and isolated demo data.

Run from any working directory with the project's installed dependencies:
    python assets/readme/source/capture_chat.py

No application runtime, model service or conversation store is started. All six
ConfigManager file paths point to an empty temporary directory; no private
configuration or chat history is loaded or changed. The background and dialogue
are authored demonstration content, rendered by the production Qt widgets.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile


SOURCE = Path(__file__).resolve().parent
ROOT = SOURCE.parents[2]
ASSETS = SOURCE.parent


def make_background(destination):
    """Create the original geometric demo background with Qt painting."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter

    image = QImage(1100, 850, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    gradient = QLinearGradient(0, 0, 1100, 850)
    gradient.setColorAt(0, QColor("#E7EDDD"))
    gradient.setColorAt(1, QColor("#C0D4C3"))
    painter.fillRect(image.rect(), gradient)
    painter.setPen(Qt.PenStyle.NoPen)
    for color, geometry in (
        ("#F8F7EC", (-200, -260, 650, 650)),
        ("#AFCCB5", (870, 70, 580, 580)),
        ("#D5E2CE", (-160, 470, 680, 680)),
        ("#E6EBDD", (720, 610, 640, 640)),
    ):
        painter.setBrush(QColor(color))
        painter.drawEllipse(*geometry)
    painter.end()
    if not image.save(str(destination)):
        raise RuntimeError(f"Cannot save demonstration background: {destination}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ASSETS / "chat-demo.png")
    parser.add_argument("--settings-output", type=Path, default=ASSETS / "settings-demo.png")
    args = parser.parse_args()
    output = args.output.resolve()
    settings_output = args.settings_output.resolve()

    # Fix the platform/scale before importing Qt for reproducible pixel sizes.
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["QT_SCALE_FACTOR"] = "1"
    sys.path.insert(0, str(ROOT))

    from PySide6.QtCore import QCoreApplication, QEvent, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QPushButton
    from config.config_manager import ConfigManager

    original_cwd = Path.cwd()
    names = (
        "API_CONFIG", "API_LOCAL_CONFIG", "SYSTEM_CONFIG",
        "CHARACTERS_CONFIG", "BACKGROUND_CONFIG", "MCP_CONFIG",
    )
    path_names = [f"_{name}_PATH" for name in names]
    original_paths = {name: getattr(ConfigManager, name) for name in path_names}
    report = {
        "data_kind": "authored demonstration dialogue and geometric background",
        "runtime_services_started": False,
        "model_calls": 0,
        "private_config_and_history_loaded": False,
        "image_size": [1100, 850],
    }
    with tempfile.TemporaryDirectory(prefix="yayu-readme-chat-") as folder:
        temporary = Path(folder)
        try:
            # Set the working directory and *all* configuration paths before UI
            # imports can instantiate the manager or read product preferences.
            os.chdir(temporary)
            for name in names:
                setattr(ConfigManager, f"_{name}_PATH", temporary / f"{name.lower()}.yaml")
            ConfigManager.reset()

            from core.runtime.sprite_controller import SpriteController, build_sprite_map
            from ui import motion
            from ui.chat_ui.chat_ui import ChatUIWindow
            from ui.resources import application_icon, ensure_ui_font
            from ui.theme import dialogs_qss

            app = QApplication.instance() or QApplication([])
            ensure_ui_font()
            app.setWindowIcon(application_icon())
            app.setStyleSheet(dialogs_qss())
            motion.set_reduced_motion(True)
            config = ConfigManager()
            character = config.characters[0]
            assert character.memory_id == "builtin-xiaoya" and character.name == "小芽"
            sprite_map = build_sprite_map(config.characters)
            assert set(sprite_map) == {"1", "2", "3"}

            background = temporary / "demo-geometric-background.png"
            make_background(background)
            chat = ChatUIWindow()
            chat.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
            chat.resize(1100, 850)
            chat.set_active_character_name(character.name)
            controller = SpriteController(chat, config.characters, sprite_map)
            controller.show_default_sprite()
            pixmap = chat.sprite_widget._source_pixmap
            assert pixmap is not None and not pixmap.isNull() and pixmap.hasAlphaChannel()
            assert chat.set_background(str(background))
            chat.add_message(
                "下午好，我是小芽。今天想从哪里开始？\n"
                "这是未连接模型的演示对话，试试选项，或者写下你自己的回答吧。",
                char_name=character.name, char_color=character.color,
            )
            chat.post_options([
                "聊聊今天发生的小事", "一起想一个故事的开头", "给我一个轻松的话题",
            ])
            chat.set_notification("README 演示数据 · 未连接模型服务")
            chat.show()
            QTest.qWait(120)
            for name in ("choice_custom_reply_button", "choice_skip_button"):
                button = chat.findChild(QPushButton, name)
                assert button is not None and button.isVisible()
            assert len(chat.findChildren(QPushButton, "choice_button")) == 3
            screenshot = chat.grab().toImage()
            assert [screenshot.width(), screenshot.height()] == report["image_size"]
            output.parent.mkdir(parents=True, exist_ok=True)
            if not screenshot.save(str(output)):
                raise RuntimeError(f"Cannot save screenshot: {output}")
            source = Path(sprite_map["1"])
            report.update({
                "qt_platform": app.platformName(),
                "sprite_source": source.relative_to(ROOT).as_posix(),
                "sprite_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "sprite_size": [pixmap.width(), pixmap.height()],
                "image_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
                "chat_window_title": chat.windowTitle(),
            })
            chat.close()
            chat.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            app.processEvents()

            # The system-settings capture uses the same empty temporary
            # configuration and an explicit temporary authorization store.
            # No runtime, history controller or model adapter is started.
            from core.security.allowed_roots import AllowedRootsStore
            from ui.settings_ui.window import SettingsWindow

            settings = SettingsWindow(allowed_roots_store=AllowedRootsStore(
                temporary / "roots.json", project_root=temporary,
            ))
            settings.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
            settings.settings_nav.setCurrentRow(4)
            settings._page_transition.finish()
            settings.resize(1280, 900)
            settings.show()
            settings._set_status_message("README 演示配置 · 未连接模型服务")
            QTest.qWait(120)
            settings_image = settings.grab().toImage()
            assert [settings_image.width(), settings_image.height()] == [1280, 900]
            settings_output.parent.mkdir(parents=True, exist_ok=True)
            if not settings_image.save(str(settings_output)):
                raise RuntimeError(f"Cannot save screenshot: {settings_output}")
            report.update({
                "settings_window_title": settings.windowTitle(),
                "settings_image_size": [1280, 900],
                "settings_image_sha256": hashlib.sha256(settings_output.read_bytes()).hexdigest(),
            })
            settings._settings_dirty = False
            settings.close()
            settings.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            app.processEvents()
            assert not list(temporary.glob("*.yaml")), "Capture must not save configuration"
        finally:
            ConfigManager.reset()
            for name, value in original_paths.items():
                setattr(ConfigManager, name, value)
            os.chdir(original_cwd)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
