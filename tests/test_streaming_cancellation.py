import asyncio
import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace as NS

import pytest

from core.runtime.cancellation import TurnCancelled, TurnToken, run_async, turn_scope
from core.runtime.tool_loop import run_serial_tool_loop
from llm.llm_adapter import OpenAIAdapter
from llm.streaming import collect_openai_stream
from llm.tools.tool_manager import ToolManager


def test_cancellation_awaits_async_cleanup():
    token = TurnToken()
    cleaned = []

    async def blocked():
        try:
            token.cancel()
            await asyncio.sleep(10)
        finally:
            cleaned.append(True)

    with turn_scope(token), pytest.raises(TurnCancelled):
        run_async(blocked)
    assert cleaned == [True]


def test_stream_reassembles_interleaved_tool_arguments_and_closes():
    def part(index, name=None, args=None, id=None):
        return NS(index=index, id=id, function=NS(name=name, arguments=args))

    class Stream:
        closed = False

        async def __aiter__(self):
            for calls in [
                [part(0, "echo", '{"text":', "call-1"), part(1, "echo", '{"text":', "call-2")],
                [part(1, args='"second"}'), part(0, args='"first"}')],
            ]:
                yield NS(choices=[NS(delta=NS(content=None, tool_calls=calls))])
            yield NS(choices=[NS(delta=NS(content=None, tool_calls=[]), finish_reason="tool_calls")])

        async def close(self):
            self.closed = True

    stream = Stream()
    seen = []
    result = asyncio.run(collect_openai_stream(stream, seen.append))
    assert stream.closed
    assert seen == []
    assert [json.loads(c["function"]["arguments"])["text"] for c in result["tool_calls"]] == ["first", "second"]
    assert [c["id"] for c in result["tool_calls"]] == ["call-1", "call-2"]


def test_streamed_tool_loop_emits_text_before_return_and_runs_tools_once():
    seen, calls = [], []
    manager = ToolManager()
    manager.register("echo", lambda text: calls.append(text) or text, description="echo",
                     parameters={"type": "object", "properties": {"text": {"type": "string"}}})

    class Adapter:
        rounds = 0

        def generate_stream(self, messages, *, tools, generation_config, on_text):
            self.rounds += 1
            if self.rounds == 1:
                return {"content": "", "tool_calls": [{"id": "1", "type": "function", "function": {
                    "name": "echo", "arguments": '{"text":"hello"}'}}]}
            assert calls == ["hello"]
            assert messages[-1]["role"] == "tool"
            on_text("first")
            assert "first" in seen
            on_text("second")
            return {"content": "firstsecond", "tool_calls": []}

    result = run_serial_tool_loop([], Adapter(), manager, text_callback=seen.append)
    assert result.final_output == "firstsecond"
    assert calls == ["hello"]
    assert seen == [None, None, "first", "second"]


@pytest.mark.parametrize("reason", [None, "length"])
def test_incomplete_stream_is_not_committed_or_executed(reason):
    class Stream:
        closed = False

        async def __aiter__(self):
            yield NS(choices=[NS(delta=NS(content='{"speech":"partial', tool_calls=[]), finish_reason=reason)])

        async def close(self):
            self.closed = True

    stream = Stream()
    with pytest.raises(RuntimeError):
        asyncio.run(collect_openai_stream(stream, lambda text: None))
    assert stream.closed


def test_cancellation_stops_additional_tools_in_the_same_response():
    token = TurnToken()
    calls = []
    manager = ToolManager()

    def stop_here():
        calls.append("first")
        token.cancel()

    manager.register("stop_here", stop_here, description="stop", parameters={"type": "object"})
    manager.register("never", lambda: calls.append("second"), description="never", parameters={"type": "object"})

    class Adapter:
        def generate(self, *args, **kwargs):
            return {"content": "", "tool_calls": [
                {"id": name, "function": {"name": name, "arguments": "{}"}}
                for name in ("stop_here", "never")
            ]}

    with turn_scope(token), pytest.raises(TurnCancelled):
        run_serial_tool_loop([], Adapter(), manager)
    assert calls == ["first"]


@contextmanager
def stalled_server(mode):
    entered, release = threading.Event(), threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            if mode == "cg":
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"prompt_id":"owned-prompt"}')
                return
            if mode == "stream":
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                chunk = {"id": "chunk", "object": "chat.completion.chunk", "created": 0, "model": "test",
                         "choices": [{"index": 0, "delta": {"content": "first"}, "finish_reason": None}]}
                self.wfile.write(("data: " + json.dumps(chunk) + "\n\n").encode())
                self.wfile.flush()
            entered.set()
            release.wait(8)

        def do_GET(self):
            entered.set()
            release.wait(8)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", entered
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        thread.join(2)


@pytest.mark.parametrize("mode", ["headers", "stream", "tts", "cg"])
def test_cancel_closes_real_http_wait_without_waiting_for_server(mode, tmp_path):
    from tts.tts_adapter import GPTSoVITSAdapter
    from t2i.t2i_manager import ComfyUIAdapter

    token = TurnToken()
    outcome = []
    first_chunk = threading.Event()
    with stalled_server(mode) as (url, entered):
        def request():
            try:
                with turn_scope(token):
                    if mode == "tts":
                        reference = tmp_path / "reference.wav"
                        reference.write_bytes(b"test")
                        GPTSoVITSAdapter(url).synthesize("hello", ref_audio_path=str(reference))
                    elif mode == "cg":
                        ComfyUIAdapter(url).generate("test")
                    else:
                        adapter = OpenAIAdapter(api_key="local-test", base_url=url + "/v1", model="test")
                        try:
                            adapter.generate_stream([{"role": "user", "content": "hello"}],
                                                    on_text=lambda text: first_chunk.set())
                        finally:
                            adapter.close()
            except BaseException as exc:
                outcome.append(exc)

        thread = threading.Thread(target=request, daemon=True)
        thread.start()
        try:
            assert entered.wait(4), "local request did not start"
            if mode == "stream":
                assert first_chunk.wait(2)
            token.cancel()
            thread.join(2)
            assert not thread.is_alive(), "cancel did not abort the network operation"
            assert len(outcome) == 1 and isinstance(outcome[0], TurnCancelled)
        finally:
            token.cancel()
            thread.join(2)


@pytest.mark.parametrize("failure", [None, "history", "view"])
def test_cancellable_cg_keeps_download_and_fallback_behavior(monkeypatch, tmp_path, failure):
    import httpx
    from t2i.t2i_manager import ComfyUIAdapter
    real_client = httpx.AsyncClient

    def respond(request):
        path = request.url.path
        if failure and failure in path:
            return httpx.Response(503)
        if path == "/prompt":
            return httpx.Response(200, json={"prompt_id": "test-id"})
        if path.startswith("/history/"):
            return httpx.Response(200, json={"test-id": {"outputs": {"9": {"images": [{"filename": "test.png"}]}}}})
        return httpx.Response(200, content=b"image-data")

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: real_client(transport=httpx.MockTransport(respond), **kwargs))
    with turn_scope(TurnToken()):
        result = ComfyUIAdapter("http://test", output_dir=str(tmp_path)).generate("test")
    if failure == "history":
        assert result == "comfyui://prompt/test-id"
    elif failure == "view":
        assert result == "comfyui://image/test-id/test.png"
    else:
        from pathlib import Path
        assert Path(result).read_bytes() == b"image-data"
