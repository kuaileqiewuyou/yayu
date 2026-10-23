"""国际化模块"""
import json
from pathlib import Path
from typing import Optional

_current_locale: str = "zh_CN"
_translations: dict = {}


def init_i18n(locale: str = "zh_CN") -> None:
    """初始化国际化，加载对应语言文件"""
    global _current_locale, _translations
    _current_locale = locale
    locale_file = Path(__file__).parent / "locales" / f"{locale}.json"
    if locale_file.exists():
        with open(locale_file, "r", encoding="utf-8") as f:
            _translations = json.load(f)
    else:
        _translations = {}


def tr(key: str, **kwargs) -> str:
    """翻译函数，支持占位符替换"""
    text = _translations.get(key, key)
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError):
            pass
    return text
