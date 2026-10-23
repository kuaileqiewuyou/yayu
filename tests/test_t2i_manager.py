import json
from urllib.error import URLError
from urllib.parse import parse_qs, urlparse

import pytest

from t2i.t2i_manager import ComfyUIAdapter, T2IAdapterFactory, T2IManager


class SpyAdapter:
    def __init__(self):
        self.calls = []

    def generate(self, prompt: str, **kwargs):
        self.calls.append({"prompt": prompt, "kwargs": kwargs})
        return "data/cg/generated.png"


def test_comfyui_adapter_production_polling_defaults_are_pinned():
    assert ComfyUIAdapter.DEFAULT_POLL_ATTEMPTS == 60
    assert ComfyUIAdapter.DEFAULT_POLL_INTERVAL == 1.0


def test_factory_creates_comfyui_adapter_with_api_url():
    adapter = T2IAdapterFactory.create_adapter(
        "comfyui",
        api_url="http://example.test:8188",
    )

    assert isinstance(adapter, ComfyUIAdapter)
    assert adapter.api_url == "http://example.test:8188"


def test_factory_unknown_adapter_raises_value_error():
    with pytest.raises(ValueError, match="未知的 T2I 适配器"):
        T2IAdapterFactory.create_adapter("unknown")


def test_manager_generate_image_forwards_prompt_and_kwargs_to_adapter():
    adapter = SpyAdapter()
    manager = T2IManager(adapter)

    result = manager.generate_image("夕阳下的教室", width=768, height=512)

    assert result == "data/cg/generated.png"
    assert adapter.calls == [
        {"prompt": "夕阳下的教室", "kwargs": {"width": 768, "height": 512}}
    ]


def test_comfyui_build_workflow_contains_prompt_clip_text_encode_and_save_image():
    adapter = ComfyUIAdapter()

    workflow = adapter._build_workflow("夕阳下的教室")

    assert isinstance(workflow, dict)
    assert workflow["6"]["class_type"] == "CLIPTextEncode"
    assert workflow["6"]["inputs"]["text"] == "夕阳下的教室"
    assert workflow["9"]["class_type"] == "SaveImage"
    assert workflow["9"]["inputs"]["filename_prefix"] == "yayu"


def test_comfyui_build_prompt_payload_wraps_workflow():
    adapter = ComfyUIAdapter()

    payload = adapter._build_prompt_payload("夕阳下的教室")

    assert payload == {"prompt": adapter._build_workflow("夕阳下的教室")}


def test_comfyui_adapter_normalizes_api_url_trailing_slash():
    adapter = ComfyUIAdapter(api_url="http://127.0.0.1:8188///")

    assert adapter.api_url == "http://127.0.0.1:8188"


def test_comfyui_adapter_extracts_prompt_id():
    adapter = ComfyUIAdapter()

    assert adapter._extract_prompt_id({"prompt_id": "abc123"}) == "abc123"


def test_comfyui_adapter_extract_prompt_id_rejects_missing_id():
    adapter = ComfyUIAdapter()

    with pytest.raises(ValueError, match="prompt_id"):
        adapter._extract_prompt_id({"ok": True})


class FakeHTTPResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def test_comfyui_adapter_post_prompt_sends_json_to_prompt_endpoint(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout):
        captured["url"] = req.full_url
        captured["method"] = req.get_method()
        captured["headers"] = dict(req.header_items())
        captured["body"] = json.loads(req.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeHTTPResponse({"prompt_id": "abc123"})

    monkeypatch.setattr("t2i.t2i_manager.request.urlopen", fake_urlopen)
    adapter = ComfyUIAdapter(api_url="http://comfy.test:8188/", timeout=3)
    payload = {"prompt": {"6": {"inputs": {"text": "夕阳"}}}}

    response = adapter._post_prompt(payload)

    assert response == {"prompt_id": "abc123"}
    assert captured["url"] == "http://comfy.test:8188/prompt"
    assert captured["method"] == "POST"
    assert captured["body"] == payload
    assert captured["timeout"] == 3
    assert captured["headers"]["Content-type"] == "application/json"


def test_comfyui_adapter_post_prompt_uses_default_timeout(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout):
        captured["timeout"] = timeout
        return FakeHTTPResponse({"prompt_id": "abc123"})

    monkeypatch.setattr("t2i.t2i_manager.request.urlopen", fake_urlopen)
    adapter = ComfyUIAdapter()

    adapter._post_prompt({"prompt": {}})

    assert captured["timeout"] == 10


def test_comfyui_adapter_generate_returns_prompt_handle(monkeypatch):
    posted_payloads = []
    history_calls = []

    def fake_post_prompt(self, payload):
        posted_payloads.append(payload)
        return {"prompt_id": "abc123"}

    def fake_get_history(self, prompt_id):
        history_calls.append(prompt_id)
        raise AssertionError("history should not be polled")

    monkeypatch.setattr(ComfyUIAdapter, "_post_prompt", fake_post_prompt)
    monkeypatch.setattr(ComfyUIAdapter, "_get_history", fake_get_history)
    adapter = ComfyUIAdapter(poll_attempts=0)

    result = adapter.generate("夕阳下的教室")

    assert result == "comfyui://prompt/abc123"
    assert posted_payloads == [adapter._build_prompt_payload("夕阳下的教室")]
    assert history_calls == []


def test_comfyui_adapter_generate_returns_prompt_handle_without_polling_when_poll_attempts_zero(monkeypatch):
    history_calls = []

    def fake_post_prompt(self, payload):
        return {"prompt_id": "abc123"}

    def fake_get_history(self, prompt_id):
        history_calls.append(prompt_id)
        raise AssertionError("history should not be polled")

    monkeypatch.setattr(ComfyUIAdapter, "_post_prompt", fake_post_prompt)
    monkeypatch.setattr(ComfyUIAdapter, "_get_history", fake_get_history)
    adapter = ComfyUIAdapter(poll_attempts=0)

    assert adapter.generate("夕阳下的教室") == "comfyui://prompt/abc123"
    assert history_calls == []


def test_comfyui_adapter_generate_returns_none_when_http_fails(monkeypatch):
    def fake_urlopen(req, timeout):
        raise URLError("connection refused")

    monkeypatch.setattr("t2i.t2i_manager.request.urlopen", fake_urlopen)
    adapter = ComfyUIAdapter()

    assert adapter.generate("夕阳下的教室") is None


def test_comfyui_adapter_generate_returns_none_when_response_has_no_prompt_id(monkeypatch):
    def fake_post_prompt(self, payload):
        return {"ok": True}

    monkeypatch.setattr(ComfyUIAdapter, "_post_prompt", fake_post_prompt)
    adapter = ComfyUIAdapter()

    assert adapter.generate("夕阳下的教室") is None


def test_comfyui_adapter_get_history_fetches_prompt_history(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout):
        captured["url"] = req.full_url
        captured["method"] = req.get_method()
        captured["timeout"] = timeout
        return FakeHTTPResponse({"abc123": {"outputs": {}}})

    monkeypatch.setattr("t2i.t2i_manager.request.urlopen", fake_urlopen)
    adapter = ComfyUIAdapter(api_url="http://comfy.test:8188/", timeout=4)

    history = adapter._get_history("abc123")

    assert history == {"abc123": {"outputs": {}}}
    assert captured == {
        "url": "http://comfy.test:8188/history/abc123",
        "method": "GET",
        "timeout": 4,
    }


def test_comfyui_adapter_extracts_first_image_metadata_from_history():
    adapter = ComfyUIAdapter()
    history = {
        "abc123": {
            "outputs": {
                "9": {
                    "images": [
                        {"filename": "galgame_agent_00001_.png", "subfolder": "", "type": "output"}
                    ]
                }
            }
        }
    }

    image = adapter._extract_first_image(history, "abc123")

    assert image == {"filename": "galgame_agent_00001_.png", "subfolder": "", "type": "output"}


def test_comfyui_adapter_extract_first_image_returns_none_when_not_ready():
    adapter = ComfyUIAdapter()

    assert adapter._extract_first_image({}, "abc123") is None
    assert adapter._extract_first_image({"abc123": {"outputs": {}}}, "abc123") is None


def test_comfyui_adapter_extract_first_image_returns_none_for_malformed_history():
    adapter = ComfyUIAdapter()

    assert adapter._extract_first_image(None, "abc123") is None
    assert adapter._extract_first_image({"abc123": None}, "abc123") is None
    assert adapter._extract_first_image({"abc123": {"outputs": []}}, "abc123") is None
    assert adapter._extract_first_image({"abc123": {"outputs": {"9": None}}}, "abc123") is None
    assert adapter._extract_first_image({"abc123": {"outputs": {"9": {"images": [None]}}}}, "abc123") is None
    assert adapter._extract_first_image({"abc123": {"outputs": {"9": {"images": [{"subfolder": ""}]}}}}, "abc123") is None


def test_comfyui_adapter_builds_prompt_handle():
    adapter = ComfyUIAdapter()

    assert adapter._build_prompt_handle("abc123") == "comfyui://prompt/abc123"


def test_comfyui_adapter_builds_image_handle_with_filename():
    adapter = ComfyUIAdapter()

    handle = adapter._build_image_handle(
        "abc123",
        {"filename": "galgame_agent_00001_.png", "subfolder": "", "type": "output"},
    )

    assert handle == "comfyui://image/abc123/galgame_agent_00001_.png"


def test_comfyui_adapter_generate_polls_history_and_returns_image_handle(monkeypatch):
    sleep_calls = []
    history_calls = []

    def fake_post_prompt(self, payload):
        return {"prompt_id": "abc123"}

    def fake_get_history(self, prompt_id):
        history_calls.append(prompt_id)
        return {
            "abc123": {
                "outputs": {
                    "9": {
                        "images": [
                            {"filename": "galgame_agent_00001_.png", "subfolder": "", "type": "output"}
                        ]
                    }
                }
            }
        }

    def fake_download_image(self, prompt_id, image):
        raise URLError("view unavailable")

    monkeypatch.setattr(ComfyUIAdapter, "_post_prompt", fake_post_prompt)
    monkeypatch.setattr(ComfyUIAdapter, "_get_history", fake_get_history)
    monkeypatch.setattr(ComfyUIAdapter, "_download_image", fake_download_image)
    monkeypatch.setattr("t2i.t2i_manager.time.sleep", sleep_calls.append)
    adapter = ComfyUIAdapter(poll_attempts=3, poll_interval=0.25)

    result = adapter.generate("夕阳下的教室")

    assert result == "comfyui://image/abc123/galgame_agent_00001_.png"
    assert history_calls == ["abc123"]
    assert sleep_calls == []


def test_comfyui_adapter_generate_returns_prompt_handle_when_history_not_ready(monkeypatch):
    sleep_calls = []
    history_calls = []

    def fake_post_prompt(self, payload):
        return {"prompt_id": "abc123"}

    def fake_get_history(self, prompt_id):
        history_calls.append(prompt_id)
        return {"abc123": {"outputs": {}}}

    monkeypatch.setattr(ComfyUIAdapter, "_post_prompt", fake_post_prompt)
    monkeypatch.setattr(ComfyUIAdapter, "_get_history", fake_get_history)
    monkeypatch.setattr("t2i.t2i_manager.time.sleep", sleep_calls.append)
    adapter = ComfyUIAdapter(poll_attempts=3, poll_interval=0.25)

    result = adapter.generate("夕阳下的教室")

    assert result == "comfyui://prompt/abc123"
    assert history_calls == ["abc123", "abc123", "abc123"]
    assert sleep_calls == [0.25, 0.25]


def test_comfyui_adapter_generate_returns_prompt_handle_when_history_request_fails(monkeypatch):
    def fake_post_prompt(self, payload):
        return {"prompt_id": "abc123"}

    def fake_get_history(self, prompt_id):
        raise URLError("history unavailable")

    monkeypatch.setattr(ComfyUIAdapter, "_post_prompt", fake_post_prompt)
    monkeypatch.setattr(ComfyUIAdapter, "_get_history", fake_get_history)
    adapter = ComfyUIAdapter(poll_attempts=2, poll_interval=0)

    assert adapter.generate("夕阳下的教室") == "comfyui://prompt/abc123"


def test_comfyui_adapter_output_dir_defaults_to_generated_cache():
    adapter = ComfyUIAdapter()

    assert str(adapter._output_dir()).replace("\\", "/").endswith("data/cg/generated")


def test_comfyui_adapter_output_dir_can_be_overridden(tmp_path):
    adapter = ComfyUIAdapter(output_dir=str(tmp_path / "cg-cache"))

    assert adapter._output_dir() == tmp_path / "cg-cache"


def test_comfyui_adapter_builds_view_url_with_image_metadata():
    adapter = ComfyUIAdapter(api_url="http://comfy.test:8188/")

    url = adapter._build_view_url(
        {"filename": "galgame_agent_00001_.png", "subfolder": "", "type": "output"}
    )

    assert url == "http://comfy.test:8188/view?filename=galgame_agent_00001_.png&subfolder=&type=output"


def test_comfyui_adapter_builds_view_url_with_special_character_image_metadata():
    adapter = ComfyUIAdapter(api_url="http://comfy.test:8188/")

    url = adapter._build_view_url(
        {
            "filename": "猫 girl & sunset?.png",
            "subfolder": "outputs/day 1/猫&雨",
            "type": "temp type",
        }
    )

    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    assert parsed.scheme == "http"
    assert parsed.netloc == "comfy.test:8188"
    assert parsed.path == "/view"
    assert query == {
        "filename": ["猫 girl & sunset?.png"],
        "subfolder": ["outputs/day 1/猫&雨"],
        "type": ["temp type"],
    }


def test_comfyui_adapter_builds_safe_cache_path(tmp_path):
    adapter = ComfyUIAdapter(output_dir=str(tmp_path))

    path = adapter._build_cache_path(
        "abc123",
        {"filename": "../galgame_agent_00001_.png", "subfolder": "", "type": "output"},
    )

    assert path == tmp_path / "abc123-galgame_agent_00001_.png"


def test_comfyui_adapter_builds_safe_cache_path_with_prompt_id_traversal(tmp_path):
    adapter = ComfyUIAdapter(output_dir=str(tmp_path))

    path = adapter._build_cache_path("../bad\\prompt/id", {"filename": "safe.png"})

    assert path.parent == tmp_path
    assert path.name == "id-safe.png"
    assert "/" not in path.name
    assert "\\" not in path.name
    assert path.resolve().parent == tmp_path.resolve()


class FakeBinaryHTTPResponse:
    def __init__(self, payload: bytes):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self.payload


def test_comfyui_adapter_download_image_writes_bytes_to_cache(monkeypatch, tmp_path):
    captured = {}

    def fake_urlopen(req, timeout):
        captured["url"] = req.full_url
        captured["method"] = req.get_method()
        captured["timeout"] = timeout
        return FakeBinaryHTTPResponse(b"PNGDATA")

    monkeypatch.setattr("t2i.t2i_manager.request.urlopen", fake_urlopen)
    adapter = ComfyUIAdapter(api_url="http://comfy.test:8188", timeout=4, output_dir=str(tmp_path))

    path = adapter._download_image(
        "abc123",
        {"filename": "galgame_agent_00001_.png", "subfolder": "", "type": "output"},
    )

    assert path == tmp_path / "abc123-galgame_agent_00001_.png"
    assert path.read_bytes() == b"PNGDATA"
    assert captured == {
        "url": "http://comfy.test:8188/view?filename=galgame_agent_00001_.png&subfolder=&type=output",
        "method": "GET",
        "timeout": 4,
    }


def test_comfyui_adapter_generate_downloads_image_and_returns_local_path(monkeypatch, tmp_path):
    def fake_post_prompt(self, payload):
        return {"prompt_id": "abc123"}

    def fake_poll_first_image(self, prompt_id):
        return {"filename": "galgame_agent_00001_.png", "subfolder": "", "type": "output"}

    def fake_download_image(self, prompt_id, image):
        path = tmp_path / "abc123-galgame_agent_00001_.png"
        path.write_bytes(b"PNGDATA")
        return path

    monkeypatch.setattr(ComfyUIAdapter, "_post_prompt", fake_post_prompt)
    monkeypatch.setattr(ComfyUIAdapter, "_poll_first_image", fake_poll_first_image)
    monkeypatch.setattr(ComfyUIAdapter, "_download_image", fake_download_image)
    adapter = ComfyUIAdapter(output_dir=str(tmp_path))

    assert adapter.generate("夕阳下的教室") == str(tmp_path / "abc123-galgame_agent_00001_.png")


def test_comfyui_adapter_generate_returns_image_handle_when_download_fails(monkeypatch):
    def fake_post_prompt(self, payload):
        return {"prompt_id": "abc123"}

    def fake_poll_first_image(self, prompt_id):
        return {"filename": "galgame_agent_00001_.png", "subfolder": "", "type": "output"}

    def fake_download_image(self, prompt_id, image):
        raise URLError("view unavailable")

    monkeypatch.setattr(ComfyUIAdapter, "_post_prompt", fake_post_prompt)
    monkeypatch.setattr(ComfyUIAdapter, "_poll_first_image", fake_poll_first_image)
    monkeypatch.setattr(ComfyUIAdapter, "_download_image", fake_download_image)
    adapter = ComfyUIAdapter()

    assert adapter.generate("夕阳下的教室") == "comfyui://image/abc123/galgame_agent_00001_.png"
