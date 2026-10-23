import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

from ui.settings_ui.controls import NoWheelDoubleSpinBox, SafeComboBox


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _wheel_event(delta: int = 120) -> QWheelEvent:
    return QWheelEvent(
        QPointF(5, 5),
        QPointF(5, 5),
        QPoint(0, 0),
        QPoint(0, delta),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.ScrollUpdate,
        False,
    )


def test_safe_combo_ignores_wheel_selection_when_popup_is_closed(app):
    combo = SafeComboBox()
    combo.addItems(["第一项", "第二项"])
    combo.setCurrentIndex(0)

    QApplication.sendEvent(combo, _wheel_event(-120))

    assert combo.currentIndex() == 0


def test_no_wheel_spin_box_ignores_wheel_value_changes(app):
    spin = NoWheelDoubleSpinBox()
    spin.setRange(0.0, 2.0)
    spin.setValue(1.0)

    QApplication.sendEvent(spin, _wheel_event(120))

    assert spin.value() == 1.0


def test_safe_combo_assigns_item_tooltips(app):
    combo = SafeComboBox()
    combo.addItems(["完整选项文字", "另一项"])

    assert combo.itemData(0, Qt.ItemDataRole.ToolTipRole) == "完整选项文字"
    assert combo.itemData(1, Qt.ItemDataRole.ToolTipRole) == "另一项"


def test_safe_combo_popup_stays_inside_top_level_window(app):
    window = QWidget()
    window.resize(320, 240)
    layout = QVBoxLayout(window)
    combo = SafeComboBox()
    combo.addItems(["全部", "只看可导入", "只看不可导入"])
    layout.addWidget(combo)
    window.show()
    app.processEvents()

    combo.showPopup()
    app.processEvents()
    popup = combo.view().window()
    top_left = window.mapToGlobal(QPoint(0, 0))
    bounds = window.rect().translated(top_left)
    popup_geometry = popup.geometry()

    assert popup_geometry.left() >= bounds.left()
    assert popup_geometry.right() <= bounds.right()
    assert popup_geometry.top() >= bounds.top()
    assert popup_geometry.bottom() <= bounds.bottom()

    combo.hidePopup()
    window.close()
