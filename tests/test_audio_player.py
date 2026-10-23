from pathlib import Path

from core.runtime.audio_player import AudioPlayer


class FakeAudioOutput:
    pass


class FakeMediaPlayer:
    instances = []

    def __init__(self):
        self.audio_outputs = []
        self.sources = []
        self.play_count = 0
        self.stop_count = 0
        FakeMediaPlayer.instances.append(self)

    def setAudioOutput(self, audio_output):
        self.audio_outputs.append(audio_output)

    def setSource(self, source):
        self.sources.append(source)

    def play(self):
        self.play_count += 1

    def stop(self):
        self.stop_count += 1


class FakeQUrl:
    local_files = []

    @staticmethod
    def fromLocalFile(path):
        FakeQUrl.local_files.append(path)
        return f"url:{path}"


def install_fakes(monkeypatch):
    FakeMediaPlayer.instances = []
    FakeQUrl.local_files = []
    monkeypatch.setattr("core.runtime.audio_player.QAudioOutput", FakeAudioOutput)
    monkeypatch.setattr("core.runtime.audio_player.QMediaPlayer", FakeMediaPlayer)
    monkeypatch.setattr("core.runtime.audio_player.QUrl", FakeQUrl)


def test_audio_player_holds_qt_objects_and_wires_audio_output(monkeypatch):
    install_fakes(monkeypatch)

    player = AudioPlayer()

    assert FakeMediaPlayer.instances == []
    assert isinstance(player.audio_output, FakeAudioOutput)
    assert isinstance(player.media_player, FakeMediaPlayer)
    assert player.media_player.audio_outputs == [player.audio_output]


def test_play_sets_local_file_source_and_starts_for_existing_path(monkeypatch, tmp_path):
    install_fakes(monkeypatch)
    audio_file = tmp_path / "voice.wav"
    audio_file.write_bytes(b"fake audio")
    player = AudioPlayer()

    assert player.play(str(audio_file)) is True

    assert FakeQUrl.local_files == [str(audio_file)]
    assert player.media_player.sources == [f"url:{audio_file}"]
    assert player.media_player.play_count == 1


def test_play_silently_ignores_empty_or_missing_path(monkeypatch, tmp_path):
    install_fakes(monkeypatch)
    player = AudioPlayer()
    missing = tmp_path / "missing.wav"

    assert player.play("") is False
    assert player.play(str(missing)) is False

    assert FakeQUrl.local_files == []
    assert player._media_player is None
    assert FakeMediaPlayer.instances == []


def test_stop_before_play_never_initializes_devices(monkeypatch):
    install_fakes(monkeypatch)
    player = AudioPlayer()
    player.stop()
    assert FakeMediaPlayer.instances == []


def test_backend_is_reused_and_stop_clears_playback(monkeypatch, tmp_path):
    install_fakes(monkeypatch)
    path = tmp_path / "voice.wav"
    path.write_bytes(b"audio")
    player = AudioPlayer()
    assert player.play(str(path))
    assert player.play(str(path))
    player.stop()
    assert len(FakeMediaPlayer.instances) == 1
    assert player.media_player.play_count == 2
    assert player.media_player.stop_count == 1
    assert isinstance(player.media_player.sources[-1], FakeQUrl)
