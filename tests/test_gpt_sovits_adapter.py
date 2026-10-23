from pathlib import Path

import httpx

from tts.tts_adapter import GPTSoVITSAdapter
from tts.tts_manager import TTSManager


class FakeResponse:
    def __init__(self, *, content=b"RIFF-audio", content_type="audio/wav", text=""):
        self.content = content
        self.headers = {"content-type": content_type}
        self.text = text

    def raise_for_status(self):
        return None


def test_gpt_sovits_adapter_posts_v2_payload_and_writes_wav(monkeypatch, tmp_path):
    reference = tmp_path / "reference.wav"
    reference.write_bytes(b"reference")
    captured = {}

    def fake_post(url, *, json, timeout):
        captured.update(url=url, json=json, timeout=timeout)
        return FakeResponse()

    def fail_get(*_args, **_kwargs):
        raise AssertionError("The project must not switch GPT-SoVITS weights")

    monkeypatch.setattr(httpx, "get", fail_get)
    monkeypatch.setattr(httpx, "post", fake_post)
    adapter = GPTSoVITSAdapter(server_url="http://127.0.0.1:9880/", work_path=str(tmp_path))

    output = adapter.synthesize(
        "hello",
        language="zh",
        speed=1.15,
        ref_audio_path=str(reference),
        prompt_text="reference text",
        prompt_lang="zh",
    )

    assert captured == {
        "url": "http://127.0.0.1:9880/tts",
        "json": {
            "text": "hello",
            "text_lang": "zh",
            "ref_audio_path": str(reference),
            "prompt_text": "reference text",
            "prompt_lang": "zh",
            "speed_factor": 1.15,
            "media_type": "wav",
            "streaming_mode": False,
        },
        "timeout": 120.0,
    }
    assert Path(output).read_bytes() == b"RIFF-audio"


def test_gpt_sovits_adapter_does_not_save_json_error_as_audio(monkeypatch, tmp_path, capsys):
    reference = tmp_path / "reference.wav"
    reference.write_bytes(b"reference")
    monkeypatch.setattr(
        httpx,
        "post",
        lambda *args, **kwargs: FakeResponse(content=b'{"message":"bad"}', content_type="application/json", text="bad"),
    )
    adapter = GPTSoVITSAdapter(work_path=str(tmp_path))

    output = adapter.synthesize("hello", ref_audio_path=str(reference), prompt_lang="zh")

    assert output is None
    assert "server returned an error" in capsys.readouterr().out
    assert list(tmp_path.glob("*.wav")) == [reference]


class RecordingAdapter:

    def __init__(self):
        self.calls = []

    def synthesize(self, **kwargs):
        self.calls.append(kwargs)
        return "voice.wav"

    def shutdown(self):
        pass


def test_tts_manager_forwards_character_reference_settings():
    adapter = RecordingAdapter()
    manager = TTSManager()
    manager.set_tts_adapter(adapter)
    manager.set_language("zh")
    manager.set_speed(0.8)

    output = manager.synthesize(
        "hello",
        ref_audio_path="reference.wav",
        prompt_text="reference text",
        prompt_lang="zh",
        speed=1.1,
    )

    assert output == "voice.wav"
    assert adapter.calls == [{
        "text": "hello",
        "speaker": "",
        "language": "zh",
        "speed": 1.1,
        "ref_audio_path": "reference.wav",
        "prompt_text": "reference text",
        "prompt_lang": "zh",
    }]
