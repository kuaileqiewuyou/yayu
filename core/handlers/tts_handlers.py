"""TTS handler 链 — 处理 LLMDialogMessage，决定是否合成语音。"""

from __future__ import annotations
from typing import List

from sdk.handlers import MessageHandler
from sdk.messages import LLMDialogMessage, TTSOutputMessage
from core.messaging.dialog_tokens import (
    match_bgm, match_card, match_cg, match_choice, match_cot,
    match_narr, match_scene, match_stat,
)
from core.runtime.app_runtime import get_app_runtime
from core.runtime.character_selection import get_active_character
from core.runtime.cancellation import tagged, check_cancelled, TurnCancelled


def _emit(name: str, text: str, asset_id: str, audio_path: str = "",
           effect: str = "", is_system: bool = True, error: str = "") -> None:
    """构造 TTSOutputMessage 并放入 audio_path_queue。"""
    rt = get_app_runtime()
    out = TTSOutputMessage(
        audio_path=audio_path, name=name, text=text,
        asset_id=asset_id, effect=effect, error=error, is_system_message=is_system,
    )
    check_cancelled()
    rt.audio_path_queue.put(tagged(out))


class CotTtsHandler(MessageHandler):
    def can_handle(self, msg: LLMDialogMessage) -> bool:
        return match_cot(msg.name)

    def handle(self, msg: LLMDialogMessage) -> None:
        _emit(msg.name, msg.text or "", str(msg.asset_id or "-1"),
              effect=msg.effect or "")


class BgmTtsHandler(MessageHandler):
    def can_handle(self, msg: LLMDialogMessage) -> bool:
        return match_bgm(msg.name)

    def handle(self, msg: LLMDialogMessage) -> None:
        _emit(msg.name, msg.text or "", str(msg.asset_id or "-1"),
              effect=msg.effect or "")


class SceneTtsHandler(MessageHandler):
    def can_handle(self, msg: LLMDialogMessage) -> bool:
        return match_scene(msg.name)

    def handle(self, msg: LLMDialogMessage) -> None:
        _emit(msg.name, msg.text or "", str(msg.asset_id or "-1"),
              effect=msg.effect or "")


class CgTtsHandler(MessageHandler):
    def can_handle(self, msg: LLMDialogMessage) -> bool:
        return match_cg(msg.name)

    def handle(self, msg: LLMDialogMessage) -> None:
        _emit(msg.name, msg.text or "", str(msg.asset_id or "-1"),
              effect=msg.effect or "")


class ChoiceTtsHandler(MessageHandler):
    def can_handle(self, msg: LLMDialogMessage) -> bool:
        return match_choice(msg.name)

    def handle(self, msg: LLMDialogMessage) -> None:
        _emit(msg.name, msg.text or "", str(msg.asset_id or "-1"),
              effect=msg.effect or "")


class StatTtsHandler(MessageHandler):
    def can_handle(self, msg: LLMDialogMessage) -> bool:
        return match_stat(msg.name)

    def handle(self, msg: LLMDialogMessage) -> None:
        _emit(msg.name, msg.text or "", str(msg.asset_id or "-1"),
              effect=msg.effect or "")


class CardTtsHandler(MessageHandler):
    """信息卡片：已在 LLM 即时阶段显示；这里只负责拦截，避免被兜底 handler 朗读。"""

    def can_handle(self, msg: LLMDialogMessage) -> bool:
        return match_card(msg.name)

    def handle(self, msg: LLMDialogMessage) -> None:
        check_cancelled()


class NarrTtsHandler(MessageHandler):
    def can_handle(self, msg: LLMDialogMessage) -> bool:
        return match_narr(msg.name)

    def handle(self, msg: LLMDialogMessage) -> None:
        _emit(msg.name, msg.text or "", str(msg.asset_id or "-1"),
              effect=msg.effect or "")


class DefaultCharacterTtsHandler(MessageHandler):
    """普通角色对话 — 调用 TTS 合成语音。"""

    def can_handle(self, msg: LLMDialogMessage) -> bool:
        return True  # 兜底

    def handle(self, msg: LLMDialogMessage) -> None:
        rt = get_app_runtime()
        text = msg.text or ""
        audio_path = ""
        error = ""
        if rt.tts_manager and text:
            try:
                character = get_active_character(rt.config) if rt.config else None
                if character is None and rt.config and hasattr(rt.config, "get_character_by_name"):
                    character = rt.config.get_character_by_name(msg.name)
                if character is None:
                    audio_path = rt.tts_manager.synthesize(text) or ""
                else:
                    audio_path = rt.tts_manager.synthesize(
                        text,
                        ref_audio_path=character.refer_audio_path or "",
                        prompt_text=character.prompt_text or "",
                        prompt_lang=character.prompt_lang or "",
                        speed=character.speech_speed,
                    ) or ""
            except TurnCancelled:
                raise
            except Exception as e:
                error = f"语音合成失败：{e}"
                print(f"[TTS] {error}")
        _emit(msg.name, text, str(msg.asset_id or "-1"),
              audio_path=audio_path, effect=msg.effect or "", is_system=False,
              error=error)


def get_tts_handlers() -> List[MessageHandler]:
    """返回 TTS handler 链（顺序重要，兜底放最后）。"""
    return [
        CotTtsHandler(),
        BgmTtsHandler(),
        SceneTtsHandler(),
        CgTtsHandler(),
        ChoiceTtsHandler(),
        StatTtsHandler(),
        CardTtsHandler(),
        NarrTtsHandler(),
        DefaultCharacterTtsHandler(),
    ]
