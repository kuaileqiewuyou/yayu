from types import SimpleNamespace

from PySide6.QtWidgets import QApplication

from ui.settings_ui.character_controller import CharacterSettingsController


class FakeItem:
    def __init__(self, text):
        self._text = str(text)

    def text(self):
        return self._text


class FakeCombo:
    def __init__(self, current=""):
        self.items = []
        self._current = current
        if current:
            self.items.append(current)

    def currentText(self):
        return self._current

    def clear(self):
        self.items.clear()
        self._current = ""

    def addItem(self, text):
        self.items.append(text)
        if not self._current:
            self._current = text

    def findText(self, text):
        try:
            return self.items.index(text)
        except ValueError:
            return -1

    def setCurrentText(self, text):
        if text and text not in self.items:
            self.items.append(text)
        self._current = text

    def setCurrentIndex(self, index):
        self._current = self.items[index]

    def currentIndex(self):
        try:
            return self.items.index(self._current)
        except ValueError:
            return -1


class FakeEmotionTable:
    def __init__(self):
        self.rows = []

    def rowCount(self):
        return len(self.rows)

    def item(self, row, column):
        return self.rows[row].get(("item", column))

    def cellWidget(self, row, column):
        return self.rows[row].get(("widget", column))


class FakeWindow:
    def __init__(self):
        self.emotion_binding_table = FakeEmotionTable()


class FakeCharacterWindow(FakeWindow):
    def __init__(self, character):
        super().__init__()
        self.config = SimpleNamespace(characters=[character])
        self._current_character_index = 0
        self.sprite_list = FakeSpriteList()


def test_character_controller_formats_structured_emotion_items_before_legacy_tags():
    character = SimpleNamespace(
        emotion_tags="0: legacy-neutral\n1: legacy-happy",
        emotion_items=[
            {"id": 1, "label": "neutral", "sprite_path": "neutral.png"},
            SimpleNamespace(id=2, label="happy", sprite_path="happy.png"),
        ],
    )

    assert CharacterSettingsController.format_emotion_items_for_editor(character) == "1: neutral\n2: happy"


def test_character_controller_falls_back_to_legacy_emotion_tags_without_structured_items():
    character = SimpleNamespace(
        emotion_tags="0: legacy-neutral\n1: legacy-happy",
        emotion_items=[],
    )

    assert CharacterSettingsController.format_emotion_items_for_editor(character) == "0: legacy-neutral\n1: legacy-happy"


def test_character_controller_extracts_sprite_paths_from_dicts_and_objects():
    character = SimpleNamespace(
        sprites=[
            {"path": "dict-sprite.png"},
            SimpleNamespace(path="object-sprite.png"),
            {"path": ""},
        ]
    )

    assert CharacterSettingsController.sprite_paths_for_character(character) == [
        "dict-sprite.png",
        "object-sprite.png",
    ]


def test_character_controller_builds_overview_summary():
    characters = [
        SimpleNamespace(
            sprites=[{"path": "a.png"}, {"path": "b.png"}],
            emotion_items=[{"id": 1}, {"id": 2}],
        ),
        SimpleNamespace(sprites=[], emotion_items=[{"id": 3}]),
    ]

    assert CharacterSettingsController.overview_summary_text(characters) == "2 个角色 · 2 张立绘 · 3 个情绪绑定"


def test_character_controller_collects_emotion_bindings_from_table():
    window = FakeWindow()
    window.emotion_binding_table.rows = [
        {
            ("item", 0): FakeItem("1"),
            ("item", 1): FakeItem("neutral"),
            ("widget", 2): FakeCombo("neutral.png"),
        },
        {
            ("item", 0): FakeItem("bad-id"),
            ("item", 1): FakeItem("happy"),
            ("widget", 2): FakeCombo("happy.png"),
        },
        {
            ("item", 0): FakeItem("3"),
            ("item", 1): FakeItem(""),
            ("widget", 2): FakeCombo(""),
        },
    ]

    assert CharacterSettingsController(window).collect_emotion_bindings_from_table() == [
        {"id": 1, "label": "neutral", "sprite_path": "neutral.png"},
        {"id": 2, "label": "happy", "sprite_path": "happy.png"},
    ]


class FakeSpriteList:
    def __init__(self):
        self.items = []

    def clear(self):
        self.items.clear()

    def addItem(self, text):
        self.items.append(text.text() if hasattr(text, "text") else text)


class FakeConfig:
    def __init__(self, characters_path):
        self._CHARACTERS_CONFIG_PATH = characters_path


class FakeArchiveWindow:
    def __init__(self, characters_path):
        self.sprite_list = FakeSpriteList()
        self.config = FakeConfig(characters_path)


def test_character_controller_refreshes_sprite_list_for_character():
    window = FakeArchiveWindow(characters_path=None)
    character = SimpleNamespace(
        sprites=[
            {"path": "dict-sprite.png"},
            SimpleNamespace(path="object-sprite.png"),
            {"path": ""},
        ]
    )

    CharacterSettingsController(window).refresh_sprite_list_for_character(character)

    assert window.sprite_list.items == ["立绘 #01", "立绘 #02"]


def test_character_controller_archives_character_sprites(tmp_path):
    imported = tmp_path / "incoming" / "neutral.png"
    imported.parent.mkdir()
    imported.write_text("sprite", encoding="utf-8")
    characters_path = tmp_path / "config" / "characters.yaml"
    characters_path.parent.mkdir()
    window = FakeArchiveWindow(characters_path=characters_path)

    archived = CharacterSettingsController(window).archive_character_sprites(
        "角色 名",
        [{"path": str(imported)}, SimpleNamespace(path="")],
    )

    assert len(archived) == 1
    archived_path = archived[0]["path"]
    assert archived_path.endswith("neutral.png")
    assert "角色_名" in archived_path
    assert archived_path != str(imported)
    assert (tmp_path / "sprites" / "角色_名" / "neutral.png").read_text(encoding="utf-8") == "sprite"


def test_character_controller_archives_explicit_avatar(tmp_path):
    source = tmp_path / "source" / "portrait.png"
    source.parent.mkdir()
    source.write_bytes(b"avatar")
    characters_path = tmp_path / "config" / "characters.yaml"
    characters_path.parent.mkdir()
    window = FakeArchiveWindow(characters_path=characters_path)

    archived = CharacterSettingsController(window).archive_character_avatar("角色 名", str(source))

    expected = tmp_path / "avatars" / "角色_名" / "portrait.png"
    assert archived == str(expected.resolve())
    assert expected.read_bytes() == b"avatar"


def test_character_controller_adds_imported_sprite_and_binds_emotion_row():
    character = SimpleNamespace(sprites=[{"path": "neutral.png"}])
    window = FakeCharacterWindow(character)
    window.emotion_binding_table.rows = [
        {
            ("widget", 2): FakeCombo(""),
        }
    ]

    CharacterSettingsController(window).add_imported_sprite_to_emotion_row(0, "surprised.png")

    assert character.sprites == [{"path": "neutral.png", "id": 0}, {"path": "surprised.png", "id": 1}]
    assert window.sprite_list.items == ["立绘 #01", "立绘 #02"]
    combo = window.emotion_binding_table.cellWidget(0, 2)
    assert combo.currentText() == "立绘 #02"
    assert combo.items == ["未绑定", "立绘 #01", "立绘 #02"]


def test_character_controller_imports_sprite_paths_for_current_character():
    character = SimpleNamespace(sprites=[{"path": "neutral.png"}])
    window = FakeCharacterWindow(character)

    CharacterSettingsController(window).import_sprite_paths_for_current_character(["happy.png", "sad.png"])

    assert character.sprites == [
        {"path": "neutral.png", "id": 0},
        {"path": "happy.png", "id": 1},
        {"path": "sad.png", "id": 2},
    ]
    assert window.sprite_list.items == ["立绘 #01", "立绘 #02", "立绘 #03"]


class FakeVisibilityWidget:
    def __init__(self):
        self.hidden_calls = 0
        self.show_calls = 0
        self.hide_calls = 0

    def hide(self):
        self.hide_calls += 1

    def show(self):
        self.show_calls += 1


class FakeStack:
    def __init__(self):
        self.current = None

    def setCurrentWidget(self, widget):
        self.current = widget


class FakeNavigationWindow:
    def __init__(self):
        self.character_empty_state_label = FakeVisibilityWidget()
        self.character_detail_content_widget = FakeVisibilityWidget()
        self.character_stack = FakeStack()
        self.character_overview_page = object()
        self.character_detail_page = object()


def test_character_controller_updates_detail_visibility():
    window = FakeNavigationWindow()
    controller = CharacterSettingsController(window)

    controller.update_character_detail_visibility(True)

    assert window.character_empty_state_label.hide_calls == 1
    assert window.character_detail_content_widget.show_calls == 1

    controller.update_character_detail_visibility(False)

    assert window.character_empty_state_label.show_calls == 1
    assert window.character_detail_content_widget.hide_calls == 1


def test_character_controller_switches_character_stack_pages():
    window = FakeNavigationWindow()
    controller = CharacterSettingsController(window)

    controller.show_character_overview_page()
    assert window.character_stack.current is window.character_overview_page

    controller.show_character_detail_page()
    assert window.character_stack.current is window.character_detail_page


class FakeLineEdit:
    def __init__(self):
        self.value = ""

    def setText(self, value):
        self.value = value


class FakeTextEdit:
    def __init__(self):
        self.value = ""

    def setPlainText(self, value):
        self.value = value


class FakeLoadCharacterWindow(FakeNavigationWindow):
    def __init__(self, characters):
        from PySide6.QtWidgets import QComboBox, QDoubleSpinBox, QLabel, QLineEdit, QListWidget, QPushButton, QTableWidget

        QApplication.instance() or QApplication([])
        super().__init__()
        self.config = SimpleNamespace(characters=characters)
        self._current_character_index = 0
        self.char_name_edit = FakeLineEdit()
        self.char_default_skills_edit = FakeLineEdit()
        self.char_setting_edit = FakeTextEdit()
        self.avatar_path_edit = QLineEdit()
        self.refer_audio_path_edit = FakeLineEdit()
        self.prompt_text_edit = FakeTextEdit()
        self.prompt_lang_combo = QComboBox()
        self.prompt_lang_combo.addItems(["zh", "ja", "en"])
        self.speech_speed_spin = QDoubleSpinBox()
        self.avatar_preview_label = QLabel()
        self.avatar_status_label = QLabel()
        self.clear_avatar_button = QPushButton()
        self.emotion_tags_edit = FakeTextEdit()
        self.emotion_binding_table = QTableWidget(0, 4)
        self.sprite_list = QListWidget()


def test_character_controller_loads_character_into_form():
    character = SimpleNamespace(
        name="铃音",
        default_skills=["romance", "mystery"],
        character_setting="安静敏锐的同伴。",
        emotion_tags="legacy: ignored",
        emotion_items=[{"id": 1, "label": "neutral", "sprite_path": "neutral.png"}],
        refer_audio_path="reference.wav",
        prompt_text="reference text",
        prompt_lang="zh",
        speech_speed=1.1,
        sprites=[{"path": "neutral.png"}, SimpleNamespace(path="happy.png")],
    )
    window = FakeLoadCharacterWindow([character])

    CharacterSettingsController(window).load_character_into_form(0)

    assert window._current_character_index == 0
    assert window.character_empty_state_label.hide_calls == 1
    assert window.character_detail_content_widget.show_calls == 1
    assert window.char_name_edit.value == "铃音"
    assert window.char_default_skills_edit.value == "romance, mystery"
    assert window.char_setting_edit.value == "安静敏锐的同伴。"
    assert window.avatar_path_edit.text() == ""
    assert "第一张立绘" in window.avatar_status_label.text()
    assert window.refer_audio_path_edit.value == "reference.wav"
    assert window.prompt_text_edit.value == "reference text"
    assert window.prompt_lang_combo.currentText() == "zh"
    assert window.speech_speed_spin.value() == 1.1
    assert window.emotion_tags_edit.value == "1: neutral"
    assert window.emotion_binding_table.rowCount() == 1
    assert [window.sprite_list.item(row).text() for row in range(window.sprite_list.count())] == ["立绘 #01", "立绘 #02"]


def test_detail_reuses_previews_across_emotions_and_reopens_without_changing_data(tmp_path, monkeypatch):
    from importlib import import_module
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage, QPixmapCache
    from config.schema import Character

    app = QApplication.instance() or QApplication([])
    QPixmapCache.clear()
    paths = []
    for index in range(3):
        path = tmp_path / f"sprite-{index}.png"
        image = QImage(120, 240, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.red)
        assert image.save(str(path))
        paths.append(str(path))
    character = Character(
        name="预览测试", character_setting="保留角色设定", default_skills=["example"],
        refer_audio_path="voice.wav", prompt_text="参考台词", prompt_lang="ja", speech_speed=1.2,
        sprites=[{"id": index * 3, "path": path} for index, path in enumerate(paths)],
        emotion_items=[{"id": index + 1, "label": f"emotion-{index}", "sprite_path": paths[index % 3]}
                       for index in range(5)],
    )
    original = character.model_dump()
    window = FakeLoadCharacterWindow([character])
    window.avatar_preview_label.resize(160, 160)
    controller = CharacterSettingsController(window)
    module = import_module("ui.settings_ui.image_preview")
    reader = module.QImageReader
    reads = []

    def create_reader(path):
        reads.append(path)
        return reader(path)

    monkeypatch.setattr(module, "QImageReader", create_reader)
    controller.load_character_into_form(0)
    # Each source is decoded once across sprite and avatar sizes.
    assert len(reads) == 3
    controller.load_character_into_form(0)
    assert len(reads) == 3
    assert controller.collect_emotion_bindings_from_table() == original["emotion_items"]
    assert character.model_dump() == original
    assert window.refer_audio_path_edit.value == "voice.wav"
    assert window.prompt_text_edit.value == "参考台词"
    assert window.prompt_lang_combo.currentText() == "ja"
    assert window.speech_speed_spin.value() == 1.2
    assert [window.sprite_list.item(row).text() for row in range(3)] == ["立绘 #01", "立绘 #04", "立绘 #07"]
    for row in range(5):
        combo = window.emotion_binding_table.cellWidget(row, 2)
        assert combo.currentData() == paths[row % 3]
        assert not combo.itemIcon(combo.currentIndex()).isNull()
    app.processEvents()


def test_character_controller_invalid_character_index_hides_detail():
    window = FakeLoadCharacterWindow([])

    CharacterSettingsController(window).load_character_into_form(0)

    assert window.character_empty_state_label.show_calls == 1
    assert window.character_detail_content_widget.hide_calls == 1

class FakeRefreshWindow(FakeNavigationWindow):
    def __init__(self, characters):
        from PySide6.QtWidgets import QLabel, QLineEdit, QListWidget, QPushButton, QTableWidget

        QApplication.instance() or QApplication([])
        super().__init__()
        self.config = SimpleNamespace(characters=characters)
        self._current_character_index = 0
        self.character_overview_summary_label = FakeLineEdit()
        self.character_card_frames = ["stale-frame"]
        self.character_card_buttons = ["stale-button"]
        self.character_card_avatar_labels = ["stale-avatar"]
        self.character_card_stats_labels = ["stale-stats"]
        self.character_list = FakeCharacterList()
        self.character_card_grid_layout = FakeGridLayout([FakeGridItem(FakeDeletableWidget())])
        self.char_name_edit = FakeLineEdit()
        self.char_default_skills_edit = FakeLineEdit()
        self.char_setting_edit = FakeTextEdit()
        self.avatar_path_edit = QLineEdit()
        self.avatar_preview_label = QLabel()
        self.avatar_status_label = QLabel()
        self.clear_avatar_button = QPushButton()
        self.emotion_tags_edit = FakeTextEdit()
        self.emotion_binding_table = QTableWidget(0, 4)
        self.sprite_list = QListWidget()
        self.created_cards = []


class FakeCharacterList:
    def __init__(self):
        self.items = []
        self.current_row = None

    def clear(self):
        self.items.clear()

    def addItem(self, text):
        self.items.append(text)

    def setCurrentRow(self, row):
        self.current_row = row


class FakeGridLayout:
    def setColumnStretch(self, column, stretch):
        pass

    def __init__(self, items=None):
        self.items = list(items or [])
        self.added = []

    def count(self):
        return len(self.items)

    def takeAt(self, index):
        return self.items.pop(index)

    def addWidget(self, widget, row, column):
        self.added.append((widget, row, column))


class FakeGridItem:
    def __init__(self, widget):
        self._widget = widget

    def widget(self):
        return self._widget


class FakeDeletableWidget:
    def __init__(self):
        self.deleted = False

    def deleteLater(self):
        self.deleted = True


def test_character_controller_refreshes_character_cards_and_legacy_list():
    characters = [
        SimpleNamespace(name="小雪", sprites=[{"path": "neutral.png"}], emotion_items=[{"id": 1}]),
        SimpleNamespace(name="铃音", sprites=[], emotion_items=[]),
    ]
    window = FakeRefreshWindow(characters)
    stale_widget = window.character_card_grid_layout.items[0].widget()
    controller = CharacterSettingsController(window)
    controller._create_character_card = lambda index, character: (
        f"card:{index}:{character.name}",
        f"button:{index}:{character.name}",
        f"avatar:{index}:头像",
        f"stats:{index}:{controller.character_card_stats_text(character)}",
    )

    controller.refresh_character_list()

    assert window.character_overview_summary_label.value == "2 个角色 · 1 张立绘 · 1 个情绪绑定"
    assert window.character_list.items == ["小雪", "铃音"]
    assert stale_widget.deleted is True
    assert window.character_card_frames == ["card:0:小雪", "card:1:铃音"]
    assert window.character_card_buttons == ["button:0:小雪", "button:1:铃音"]
    assert window.character_card_avatar_labels == ["avatar:0:头像", "avatar:1:头像"]
    assert window.character_card_stats_labels == ["stats:0:1 张立绘 · 1 个情绪", "stats:1:0 张立绘 · 0 个情绪"]
    assert window.character_card_grid_layout.added == [
        ("card:0:小雪", 0, 0),
        ("card:1:铃音", 0, 1),
    ]


def test_character_controller_adds_character_and_opens_detail():
    window = FakeRefreshWindow([])
    controller = CharacterSettingsController(window)
    controller._create_character_card = lambda index, character: (
        f"card:{index}:{character.name}",
        f"button:{index}:{character.name}",
        f"avatar:{index}:头像",
        f"stats:{index}:{controller.character_card_stats_text(character)}",
    )

    controller.add_character("  玲奈  ")

    assert [character.name for character in window.config.characters] == ["玲奈"]
    assert window.character_list.current_row == 0
    assert window.character_stack.current is window.character_detail_page


def test_character_controller_ignores_blank_character_name():
    window = FakeRefreshWindow([])

    CharacterSettingsController(window).add_character("   ")

    assert window.config.characters == []
    assert window.character_card_grid_layout.added == []

def test_character_controller_handles_character_selection_change():
    first = SimpleNamespace(
        name="小雪",
        default_skills=[],
        character_setting="第一角色。",
        emotion_tags="0: neutral",
        emotion_items=[],
        sprites=[],
    )
    second = SimpleNamespace(
        name="铃音",
        default_skills=["mystery"],
        character_setting="第二角色。",
        emotion_tags="0: side-neutral",
        emotion_items=[],
        sprites=[{"path": "side.png"}],
    )
    window = FakeLoadCharacterWindow([first, second])

    CharacterSettingsController(window).handle_character_selection_changed(1)

    assert window._current_character_index == 1
    assert window.char_name_edit.value == "铃音"
    assert window.char_default_skills_edit.value == "mystery"
    assert window.char_setting_edit.value == "第二角色。"
    assert [window.sprite_list.item(row).text() for row in range(window.sprite_list.count())] == ["立绘 #01"]
