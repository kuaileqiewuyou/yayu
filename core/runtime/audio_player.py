"""Qt audio playback runtime helper."""
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer


class AudioPlayer:
    """Owns Qt multimedia objects and plays local audio files."""

    def __init__(self) -> None:
        self._audio_output = None
        self._media_player = None

    def _ensure_backend(self) -> None:
        if self._media_player is None:
            audio_output = QAudioOutput()
            media_player = QMediaPlayer()
            media_player.setAudioOutput(audio_output)
            self._audio_output = audio_output
            self._media_player = media_player

    @property
    def audio_output(self):
        self._ensure_backend()
        return self._audio_output

    @property
    def media_player(self):
        self._ensure_backend()
        return self._media_player

    def play(self, path: str) -> bool:
        """Play a local audio file. Return whether playback was started."""
        if not path:
            return False
        if not Path(path).exists():
            print(f"[Audio] 文件不存在: {path}")
            return False
        self.media_player.setSource(QUrl.fromLocalFile(path))
        self.media_player.play()
        return True

    def stop(self) -> None:
        if self._media_player is not None:
            self._media_player.stop()
            self._media_player.setSource(QUrl())
