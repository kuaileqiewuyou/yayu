"""Settings save/apply helpers extracted from SettingsWindow."""
from __future__ import annotations

from copy import deepcopy
from contextlib import nullcontext
from typing import Callable, Protocol

from config.background_assets import entries_from_background, format_resource_tags
from config.llm_providers import llm_provider_choice, normalize_llm_provider, provider_setting
from config.schema import ApiConfig, AppConfig, Background, Character, MediaAssetBinding, SystemConfig


class _TextInput(Protocol):
    def text(self) -> str: ...


class _ComboBox(Protocol):
    def currentText(self) -> str: ...
    def currentData(self): ...


class _DoubleSpin(Protocol):
    def value(self) -> float: ...


class _CheckBox(Protocol):
    def isChecked(self) -> bool: ...


class ApiSettingsControls(Protocol):
    """Duck-typed subset of SettingsWindow controls needed for API/TTS/T2I save."""

    llm_provider_combo: _ComboBox
    base_url_edit: _TextInput
    api_key_edit: _TextInput
    model_edit: _TextInput
    temp_spin: _DoubleSpin
    stream_check: _CheckBox
    t2i_provider_combo: _ComboBox
    t2i_api_url_edit: _TextInput
    t2i_checkpoint_edit: _TextInput
    tts_provider_combo: _ComboBox
    tts_url_edit: _TextInput
    tts_voice_edit: _TextInput
    tts_speed_spin: _DoubleSpin


class _SkillsTab(Protocol):
    def collect_default_skills(self) -> list[str]: ...


class SystemSettingsControls(Protocol):
    """Duck-typed subset of SettingsWindow controls needed for system save."""

    lang_combo: _ComboBox
    voice_lang_combo: _ComboBox
    skills_tab: _SkillsTab | None
    system_default_skills_edit: _TextInput
    always_on_top_check: _CheckBox
    reduce_motion_check: _CheckBox
    typewriter_enabled_check: _CheckBox
    typewriter_cps_spin: _DoubleSpin


class _ListItem(Protocol):
    def text(self) -> str: ...


class _ListWidget(Protocol):
    def count(self) -> int: ...
    def item(self, index: int) -> _ListItem: ...


class _PlainTextInput(Protocol):
    def toPlainText(self) -> str: ...


class CharacterSettingsControls(Protocol):
    """Duck-typed subset of SettingsWindow controls needed for character save."""

    char_name_edit: _TextInput
    char_default_skills_edit: _TextInput
    char_setting_edit: _PlainTextInput
    avatar_path_edit: _TextInput
    emotion_tags_edit: _PlainTextInput

    refer_audio_path_edit: _TextInput
    prompt_text_edit: _PlainTextInput
    prompt_lang_combo: _ComboBox
    speech_speed_spin: _DoubleSpin

class BackgroundSettingsControls(Protocol):
    """Duck-typed subset needed for the manual background library."""

    scene_list: _ListWidget
    background_path_combo: _ComboBox


def save_api_settings_from_controls(cfg: ApiConfig, controls: ApiSettingsControls) -> None:
    """Write API, T2I, and TTS settings from UI controls into an ApiConfig."""
    provider = normalize_llm_provider(
        controls.llm_provider_combo.currentData() or controls.llm_provider_combo.currentText()
    )
    cfg.llm_provider = provider
    cfg.llm_base_url = controls.base_url_edit.text().strip()
    cfg.llm_api_key[provider] = controls.api_key_edit.text().strip()
    cfg.llm_model[provider] = controls.model_edit.text().strip()
    cfg.temperature = controls.temp_spin.value()
    cfg.is_streaming = controls.stream_check.isChecked()
    cfg.t2i_provider = controls.t2i_provider_combo.currentText()
    cfg.t2i_api_url = controls.t2i_api_url_edit.text().strip()
    cfg.t2i_checkpoint = controls.t2i_checkpoint_edit.text().strip()
    cfg.tts_provider = controls.tts_provider_combo.currentText()
    cfg.gpt_sovits_url = controls.tts_url_edit.text().strip()
    cfg.tts_voice = controls.tts_voice_edit.text().strip()
    cfg.tts_speed = controls.tts_speed_spin.value()

    web_enabled = getattr(controls, "web_search_enabled_check", None)
    if web_enabled is not None:
        cfg.web_search_enabled = web_enabled.isChecked()
    web_region = getattr(controls, "web_search_region_combo", None)
    if web_region is not None:
        cfg.web_search_region = str(web_region.currentData() or web_region.currentText()).strip()
    web_safesearch = getattr(controls, "web_search_safesearch_combo", None)
    if web_safesearch is not None:
        cfg.web_search_safesearch = str(web_safesearch.currentData() or web_safesearch.currentText()).strip()
    web_max_results = getattr(controls, "web_search_max_results_spin", None)
    if web_max_results is not None:
        cfg.web_search_max_results = int(web_max_results.value())
    web_timeout = getattr(controls, "web_extract_timeout_spin", None)
    if web_timeout is not None:
        cfg.web_extract_timeout_seconds = int(web_timeout.value())
    web_max_chars = getattr(controls, "web_extract_max_chars_spin", None)
    if web_max_chars is not None:
        cfg.web_extract_max_chars = int(web_max_chars.value())


def save_system_settings_from_controls(cfg: SystemConfig, controls: SystemSettingsControls) -> None:
    """Write app-level system settings from UI controls into a SystemConfig."""
    cfg.ui_language = controls.lang_combo.currentText()
    cfg.voice_language = controls.voice_lang_combo.currentText()
    background = getattr(controls, "background_path_combo", None)
    if background is not None:
        cfg.background_path = str(background.currentData() or "")
    for name in ("always_on_top", "reduce_motion", "typewriter_enabled"):
        control = getattr(controls, f"{name}_check", None)
        if control is not None:
            setattr(cfg, name, control.isChecked())
    speed = getattr(controls, "typewriter_cps_spin", None)
    if speed is not None:
        cfg.typewriter_cps = int(speed.value())
    cfg.default_skills = controls.skills_tab.collect_default_skills() if controls.skills_tab is not None else [
        item.strip()
        for item in controls.system_default_skills_edit.text().split(",")
        if item.strip()
    ]


def save_character_settings_from_controls(
    characters: list[Character],
    current_character_index: int,
    controls: CharacterSettingsControls,
    *,
    collect_emotion_bindings: Callable[[], list[dict]],
    archive_character_sprites: Callable[[str, list], list[dict]],
    archive_character_avatar: Callable[[str, str], str] | None = None,
) -> bool:
    """Write the selected character editor controls back into the character model."""
    if not characters or not 0 <= current_character_index < len(characters):
        return False

    char = characters[current_character_index]
    new_name = controls.char_name_edit.text().strip()
    if new_name:
        char.name = new_name
    char.default_skills = [
        item.strip()
        for item in controls.char_default_skills_edit.text().split(",")
        if item.strip()
    ]
    char.character_setting = controls.char_setting_edit.toPlainText()
    refer_audio_control = getattr(controls, "refer_audio_path_edit", None)
    if refer_audio_control is not None:
        char.refer_audio_path = refer_audio_control.text().strip()
    prompt_text_control = getattr(controls, "prompt_text_edit", None)
    if prompt_text_control is not None:
        char.prompt_text = prompt_text_control.toPlainText().strip()
    prompt_lang_control = getattr(controls, "prompt_lang_combo", None)
    if prompt_lang_control is not None:
        char.prompt_lang = prompt_lang_control.currentText().strip() or "zh"
    speech_speed_control = getattr(controls, "speech_speed_spin", None)
    if speech_speed_control is not None:
        char.speech_speed = speech_speed_control.value()
    avatar_path_control = getattr(controls, "avatar_path_edit", None)
    if avatar_path_control is not None:
        avatar_path = avatar_path_control.text().strip()
        char.avatar = (
            archive_character_avatar(char.name, avatar_path)
            if archive_character_avatar is not None
            else avatar_path
        )
    collected_emotion_items = collect_emotion_bindings()
    if collected_emotion_items:
        char.emotion_items = collected_emotion_items
    elif not (getattr(char, "emotion_items", []) or []):
        char.emotion_tags = controls.emotion_tags_edit.toPlainText()
    sources = getattr(char, "sprites", []) or []
    char.sprites = archive_character_sprites(char.name, sources)
    # Bindings must follow the managed copy, including collision-renamed files.
    def value(item, key, default=None):
        return item.get(key, default) if isinstance(item, dict) else getattr(item, key, default)
    archived_by_id = {value(item, "id", index): value(item, "path", "") for index, item in enumerate(char.sprites)}
    path_map = {value(item, "path", ""): archived_by_id.get(value(item, "id", index), value(item, "path", ""))
                for index, item in enumerate(sources)}
    for item in char.emotion_items:
        path = value(item, "sprite_path", "")
        if path and path in path_map:
            if isinstance(item, dict):
                item["sprite_path"] = path_map[path]
            else:
                item.sprite_path = path_map[path]
    return True


def save_background_settings_from_controls(cfg: AppConfig, controls: BackgroundSettingsControls) -> None:
    """Update images and bound names, preserving inert legacy config values."""
    background = cfg.backgrounds[0].model_copy(deep=True) if cfg.backgrounds else Background(name="背景图库")
    named_entries = getattr(controls.scene_list, "named_entries", None)
    if callable(named_entries):
        bindings = [MediaAssetBinding.model_validate(entry) for entry in named_entries()]
        draft = Background(
            name=background.name,
            sprites=[{"path": item.path} for item in bindings],
            scene_bindings=bindings,
        )
        entries = entries_from_background(draft)
        background.scene_bindings = [MediaAssetBinding.model_validate(entry) for entry in entries]
        background.sprites = [{"path": entry["path"]} for entry in entries]
        background.bg_tags = format_resource_tags(entries)
    else:
        background.sprites = [{"path": controls.scene_list.item(index).text()}
                              for index in range(controls.scene_list.count())]
        background.scene_bindings = []
        old_tags = getattr(controls, "bg_tags_edit", None)
        background.bg_tags = old_tags.text().strip() if old_tags is not None else ""
    cfg.backgrounds = [Background.model_validate(background.model_dump()), *cfg.backgrounds[1:]]


def save_settings_from_controls(
    config_store,
    controls,
    *,
    current_character_index: int,
    collect_emotion_bindings: Callable[[], list[dict]],
    archive_character_sprites: Callable[[str, list], list[dict]],
    archive_character_avatar: Callable[[str, str], str] | None = None,
    removed_sprite_paths: tuple[str, ...] = (),
) -> bool:
    """Prepare all settings changes off-model, then publish and persist them."""
    pending_api = config_store.api_config.model_copy(deep=True)
    pending_system = config_store.system_config.model_copy(deep=True)
    pending_characters = deepcopy(config_store.characters)
    pending_app = config_store.config.model_copy(deep=True)

    original_app = config_store.config.model_copy(deep=True)
    original_api_ref = config_store.api_config
    original_system_ref = config_store.system_config
    original_characters_ref = config_store.characters

    try:
        transaction = getattr(config_store, "persistence_transaction", nullcontext)
        with transaction():
            save_api_settings_from_controls(pending_api, controls)
            save_system_settings_from_controls(pending_system, controls)
            character_saved = save_character_settings_from_controls(
                pending_characters,
                current_character_index,
                controls,
                collect_emotion_bindings=collect_emotion_bindings,
                archive_character_sprites=archive_character_sprites,
                archive_character_avatar=archive_character_avatar,
            )
            save_background_settings_from_controls(pending_app, controls)

            config_store.config.api_config = pending_api
            config_store.config.system_config = pending_system
            config_store.config.characters = pending_characters
            config_store.config.backgrounds = pending_app.backgrounds
            if config_store.api_config is not config_store.config.api_config:
                config_store.api_config.__dict__.update(pending_api.__dict__)
            if config_store.system_config is not config_store.config.system_config:
                config_store.system_config.__dict__.update(pending_system.__dict__)
            if config_store.characters is not config_store.config.characters:
                config_store.characters[:] = pending_characters

            config_store.save_api_config()
            if character_saved:
                config_store.save_characters()
            config_store.save_system_config()
            config_store.save_mcp_servers()
            config_store.save_backgrounds()
            if removed_sprite_paths:
                from config.character_assets import cleanup_removed_sprites
                cleanup_removed_sprites(config_store, removed_sprite_paths)
    except Exception:
        config_store.config.api_config = original_app.api_config
        config_store.config.system_config = original_app.system_config
        config_store.config.characters = original_app.characters
        config_store.config.backgrounds = original_app.backgrounds
        config_store.config.mcp_servers = original_app.mcp_servers
        if original_api_ref is not config_store.config.api_config:
            original_api_ref.__dict__.update(original_app.api_config.__dict__)
        if original_system_ref is not config_store.config.system_config:
            original_system_ref.__dict__.update(original_app.system_config.__dict__)
        if original_characters_ref is not config_store.config.characters:
            original_characters_ref[:] = original_app.characters
        raise
    return character_saved


def _set_combo_text(combo, value: str) -> None:
    index = combo.findText(value)
    if index >= 0:
        combo.setCurrentIndex(index)
    else:
        combo.setCurrentText(value)


def _set_combo_data(combo, value: str) -> None:
    index = combo.findData(value)
    if index >= 0:
        combo.setCurrentIndex(index)
    else:
        _set_combo_text(combo, value)


def load_settings_into_controls(config: AppConfig, controls) -> None:
    """Load API, system, and background config values into settings controls."""
    cfg = config.api_config
    sys_cfg = config.system_config

    provider = cfg.llm_provider
    _set_combo_data(controls.llm_provider_combo, llm_provider_choice(provider))
    controls.api_key_edit.setText(provider_setting(cfg.llm_api_key, provider))
    controls.base_url_edit.setText(cfg.llm_base_url)
    controls.model_edit.setText(provider_setting(cfg.llm_model, provider))
    reset_drafts = getattr(controls, "_reset_llm_provider_drafts", None)
    if reset_drafts is not None:
        reset_drafts()
    controls.temp_spin.setValue(cfg.temperature)
    controls.stream_check.setChecked(cfg.is_streaming)

    t2i_index = controls.t2i_provider_combo.findText(cfg.t2i_provider)
    if t2i_index >= 0:
        controls.t2i_provider_combo.setCurrentIndex(t2i_index)
    controls.t2i_api_url_edit.setText(cfg.t2i_api_url)
    controls.t2i_checkpoint_edit.setText(cfg.t2i_checkpoint)

    tts_index = controls.tts_provider_combo.findText(cfg.tts_provider)
    if tts_index >= 0:
        controls.tts_provider_combo.setCurrentIndex(tts_index)
    controls.tts_url_edit.setText(cfg.gpt_sovits_url)
    controls.tts_voice_edit.setText(cfg.tts_voice)
    controls.tts_speed_spin.setValue(cfg.tts_speed)

    web_enabled = getattr(controls, "web_search_enabled_check", None)
    if web_enabled is not None:
        web_enabled.setChecked(cfg.web_search_enabled)
    web_region = getattr(controls, "web_search_region_combo", None)
    if web_region is not None:
        _set_combo_data(web_region, cfg.web_search_region)
    web_safesearch = getattr(controls, "web_search_safesearch_combo", None)
    if web_safesearch is not None:
        _set_combo_data(web_safesearch, cfg.web_search_safesearch)
    web_max_results = getattr(controls, "web_search_max_results_spin", None)
    if web_max_results is not None:
        web_max_results.setValue(cfg.web_search_max_results)
    web_timeout = getattr(controls, "web_extract_timeout_spin", None)
    if web_timeout is not None:
        web_timeout.setValue(cfg.web_extract_timeout_seconds)
    web_max_chars = getattr(controls, "web_extract_max_chars_spin", None)
    if web_max_chars is not None:
        web_max_chars.setValue(cfg.web_extract_max_chars)

    lang_index = controls.lang_combo.findText(sys_cfg.ui_language)
    if lang_index >= 0:
        controls.lang_combo.setCurrentIndex(lang_index)
    voice_index = controls.voice_lang_combo.findText(sys_cfg.voice_language)
    if voice_index >= 0:
        controls.voice_lang_combo.setCurrentIndex(voice_index)
    controls.system_default_skills_edit.setText(", ".join(getattr(sys_cfg, "default_skills", []) or []))
    for name in ("always_on_top", "reduce_motion", "typewriter_enabled"):
        control = getattr(controls, f"{name}_check", None)
        if control is not None:
            control.setChecked(getattr(sys_cfg, name))
    speed = getattr(controls, "typewriter_cps_spin", None)
    if speed is not None:
        speed.setValue(sys_cfg.typewriter_cps)

    if not config.backgrounds:
        set_entries = getattr(controls.scene_list, "set_named_entries", None)
        if callable(set_entries):
            set_entries([])
    if config.backgrounds:
        background = config.backgrounds[0]
        set_scenes = getattr(controls.scene_list, "set_named_entries", None)
        if callable(set_scenes):
            set_scenes(entries_from_background(background, "scene"))
        else:
            for sprite in background.sprites:
                path = sprite.get("path", "") if isinstance(sprite, dict) else sprite.path
                if path:
                    controls.scene_list.addItem(path)
        bg_tags_edit = getattr(controls, "bg_tags_edit", None)
        if bg_tags_edit is not None:
            bg_tags_edit.setText(background.bg_tags or "")
    sync_background = getattr(controls, "set_current_background", None)
    if callable(sync_background):
        sync_background(sys_cfg.background_path)
    else:
        chooser = getattr(controls, "background_path_combo", None)
        if chooser is not None:
            chooser.setCurrentIndex(max(0, chooser.findData(sys_cfg.background_path)))
