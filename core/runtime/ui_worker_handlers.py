"""UIWorker 信号到聊天窗口的处理器。"""

from __future__ import annotations

from typing import Any, Callable

from sdk.messages import TTSOutputMessage


class UIWorkerHandlers:
    """封装 UIWorker 输出事件对应的聊天窗口更新逻辑。"""

    def __init__(
        self,
        window: Any,
        config: Any,
        play_audio: Callable[[str], bool | None],
        submit_t2i_prompt: Callable[[str], None] | None = None,
    ) -> None:
        self.window = window
        self.config = config
        self.play_audio = play_audio
        self.submit_t2i_prompt = submit_t2i_prompt

    def on_update_dialog(self, out: TTSOutputMessage) -> None:
        """普通对话：播放音频，并把非致命语音错误显示到状态栏。"""
        if out.error:
            self.window.set_reply_status(out.error, error=True)
        if out.audio_path:
            played = self.play_audio(out.audio_path)
            if played is False:
                self.window.set_reply_status(f"语音播放失败：{out.audio_path}", error=True)

    def on_update_narration(self, text: str) -> None:
        self.window.add_message(text, is_user=False, char_name="旁白", char_color="#AAAAAA")

    def on_update_options(self, options: list) -> None:
        self.window.post_options(options)

    def on_update_cg(self, prompt: str) -> None:
        """CG 触发：显示 prompt，并在有后台 worker submitter 时提交生成任务。"""
        self.window.add_message(f"[CG] {prompt}", is_user=False, char_name="系统", char_color="#84C2D5")
        if self.submit_t2i_prompt is None:
            return
        self.submit_t2i_prompt(prompt)
        self.window.set_reply_status("CG 生成已提交，正在等待 ComfyUI 生成…")

    def on_update_stat(self, text: str) -> None:
        """数值/系统信息：仅显示到 UI，不写入聊天历史。"""
        self.window.add_message(text, is_user=False, char_name="系统", char_color="#84C2D5")

    def on_update_cot(self, text: str) -> None:
        """思维链默认不显示，仅在控制台调试输出。"""
        if text:
            print(f"[COT] {text}")
