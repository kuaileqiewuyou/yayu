from pathlib import Path

from PySide6.QtWidgets import QApplication, QFileDialog

from config.config_manager import ConfigManager
from core.security.allowed_roots import AllowedRootsStore
from ui.settings_ui.window import SettingsWindow


def test_settings_security_tab_manages_persistent_allowed_roots(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    project_root = tmp_path / "project"
    custom_root = tmp_path / "custom"
    project_root.mkdir()
    custom_root.mkdir()
    store = AllowedRootsStore(tmp_path / "security" / "allowed-roots.json", project_root=project_root)
    monkeypatch.setattr(
        QFileDialog,
        "getExistingDirectory",
        lambda *args, **kwargs: str(custom_root),
    )
    app = QApplication.instance() or QApplication([])

    window = SettingsWindow(allowed_roots_store=store)
    try:
        assert window.security_allowed_roots_list.count() == 1
        security_description = window._security_tab_parts.widget.findChildren(type(window.security_status_label))
        assert any("每次执行仍需人工批准" in label.text() for label in security_description)
        assert "内置授权" in window.security_allowed_roots_list.item(0).text()
        assert window.security_remove_root_button.isEnabled() is False

        window.security_add_root_button.click()
        assert window.security_allowed_roots_list.count() == 2
        assert store.load() == [project_root.resolve(), custom_root.resolve()]
        assert "重启" in window.security_status_label.text()

        window.security_allowed_roots_list.setCurrentRow(1)
        assert window.security_remove_root_button.isEnabled() is True
        window.security_remove_root_button.click()
        assert store.load() == [project_root.resolve()]
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()
        ConfigManager.reset()
