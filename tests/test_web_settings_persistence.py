from types import SimpleNamespace

from config.schema import ApiConfig
from ui.settings_ui.save_service import save_api_settings_from_controls


class _Text:
    def __init__(self, value=""):
        self.value = value

    def text(self):
        return self.value


class _Combo:
    def __init__(self, text, data=None):
        self.text = text
        self.data = data

    def currentText(self):
        return self.text

    def currentData(self):
        return self.data


class _Value:
    def __init__(self, value):
        self.current = value

    def value(self):
        return self.current


class _Check:
    def __init__(self, checked):
        self.checked = checked

    def isChecked(self):
        return self.checked


def test_save_service_persists_free_web_search_controls_without_api_key() -> None:
    controls = SimpleNamespace(
        llm_provider_combo=_Combo("openai"),
        base_url_edit=_Text("https://api.example/v1"),
        api_key_edit=_Text("existing-llm-key"),
        model_edit=_Text("model"),
        temp_spin=_Value(0.7),
        stream_check=_Check(True),
        t2i_provider_combo=_Combo("none"),
        t2i_api_url_edit=_Text(""),
        t2i_checkpoint_edit=_Text(""),
        tts_provider_combo=_Combo("none"),
        tts_url_edit=_Text(""),
        tts_voice_edit=_Text(""),
        tts_speed_spin=_Value(1.0),
        web_search_enabled_check=_Check(True),
        web_search_region_combo=_Combo("中国 / 中文", "cn-zh"),
        web_search_safesearch_combo=_Combo("严格", "on"),
        web_search_max_results_spin=_Value(7),
        web_extract_timeout_spin=_Value(25),
        web_extract_max_chars_spin=_Value(18000),
    )
    config = ApiConfig()

    save_api_settings_from_controls(config, controls)

    assert config.web_search_enabled is True
    assert config.web_search_region == "cn-zh"
    assert config.web_search_safesearch == "on"
    assert config.web_search_max_results == 7
    assert config.web_extract_timeout_seconds == 25
    assert config.web_extract_max_chars == 18000
