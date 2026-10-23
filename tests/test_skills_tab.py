import ast
import os
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from ui.settings_ui.skills_tab import SkillsTabController


def test_skill_card_checkbox_click_updates_saved_selection():
    from PySide6.QtCore import QPoint
    from PySide6.QtTest import QTest
    app = _app()
    config = SimpleNamespace(system_config=SimpleNamespace(default_skills=["shared"], skills_root="", skill_presets=[]))
    controller = SkillsTabController(None, config)
    controller.refresh()
    controller.widget.resize(1100, 700)
    controller.widget.show()
    QApplication.processEvents()
    view = controller.system_skill_list
    rect = view.visualItemRect(view.item(0))
    QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=rect.topLeft() + QPoint(23, 27))
    assert controller.collect_default_skills() == []
    view.setFocus()
    QTest.keyClick(view, Qt.Key.Key_Space)
    assert controller.collect_default_skills() == ["shared"]
    controller.widget.close()
    controller.widget.deleteLater()
    QApplication.processEvents()


def _app():
    return QApplication.instance() or QApplication([])


class _Preset:
    def __init__(self, name, skills=None):
        self.name = name
        self.skills = list(skills or [])


def test_skills_tab_refresh_populates_lists_and_checked_defaults():
    _app()
    config = SimpleNamespace(
        system_config=SimpleNamespace(
            default_skills=["shared"],
            skills_root="data/skills",
            skill_presets=[_Preset("推理", ["mystery-a"]), _Preset("日常", ["slice-of-life"])],
        )
    )

    class FakeRepo:
        def __init__(self, roots):
            self.roots = roots

        def list_skills(self):
            return [
                SimpleNamespace(name="shared", description="Shared desc"),
                SimpleNamespace(name="mystery-a", description="Mystery desc"),
            ]

    controller = SkillsTabController(parent=None, config_manager=config, repository_factory=FakeRepo)
    controller.refresh()

    assert [controller.system_skill_list.item(i).text() for i in range(controller.system_skill_list.count())] == [
        "shared — Shared desc",
        "mystery-a — Mystery desc",
    ]
    assert controller.system_skill_list.item(0).checkState() == Qt.CheckState.Checked
    assert controller.system_skill_list.item(1).checkState() == Qt.CheckState.Unchecked
    assert [controller.skill_preset_list.item(i).text() for i in range(controller.skill_preset_list.count())] == ["推理", "日常"]


def test_settings_window_skill_preset_compatibility_methods_delegate_to_skills_tab_controller():
    window_path = Path(__file__).resolve().parents[1] / "ui" / "settings_ui" / "window.py"
    source = window_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    settings_class = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "SettingsWindow")

    def method_source(name: str) -> str:
        method = next(
            node
            for node in settings_class.body
            if isinstance(node, ast.FunctionDef) and node.name == name
        )
        return ast.get_source_segment(source, method) or ""

    refresh_source = method_source("_refresh_skill_settings_lists")
    assert "self.skills_tab.refresh()" in refresh_source
    assert "QListWidgetItem" not in refresh_source
    assert "SkillRepository" not in refresh_source
    assert "setCheckState" not in refresh_source

    for method_name, delegated_name in (
        ("_add_skill_preset", "_add_skill_preset"),
        ("_rename_skill_preset", "_rename_skill_preset"),
        ("_delete_skill_preset", "_delete_skill_preset"),
    ):
        source_segment = method_source(method_name)
        assert f"self.skills_tab.{delegated_name}()" in source_segment
        assert "QInputDialog.getText" not in source_segment
        assert "SkillPreset" not in source_segment
        assert "skill_presets =" not in source_segment


def test_skills_tab_collect_default_skills_reads_checked_items():
    _app()
    config = SimpleNamespace(
        system_config=SimpleNamespace(default_skills=[], skills_root="", skill_presets=[])
    )
    controller = SkillsTabController(parent=None, config_manager=config, repository_factory=lambda roots: None)
    controller.system_skill_list.addItem("placeholder")
    item = controller.system_skill_list.item(0)
    item.setData(Qt.ItemDataRole.UserRole, "shared")
    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
    item.setCheckState(Qt.CheckState.Checked)

    assert controller.collect_default_skills() == ["shared"]


def test_missing_default_skills_remain_explicit_and_can_be_unchecked():
    _app()
    config = SimpleNamespace(system_config=SimpleNamespace(default_skills=["unavailable"], skills_root="", skill_presets=[]))
    controller = SkillsTabController(None, config)
    controller.refresh()
    assert controller.collect_default_skills() == ["unavailable"]
    controller.system_skill_list.item(0).setCheckState(Qt.CheckState.Unchecked)
    assert controller.collect_default_skills() == []
    controller.refresh(preserve_selection=True)
    assert controller.collect_default_skills() == []


def test_manual_default_names_stay_editable_in_skills_page(monkeypatch):
    from PySide6.QtWidgets import QInputDialog
    _app()
    config = SimpleNamespace(system_config=SimpleNamespace(default_skills=[], skills_root="", skill_presets=[]))
    controller = SkillsTabController(None, config)
    controller.refresh()
    monkeypatch.setattr(QInputDialog, "getText", lambda *args, **kwargs: ("custom, another, custom", True))
    controller.add_default_skill_button.click()
    assert controller.collect_default_skills() == ["custom", "another"]
    assert config.system_config.default_skills == []
    controller.refresh(preserve_selection=True)
    assert sorted(controller.collect_default_skills()) == ["another", "custom"]
