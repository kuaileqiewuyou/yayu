from core.runtime.tool_loop import run_serial_tool_loop
from llm.tools.tool_manager import ToolManager


class SequencedAdapter:
    def __init__(self, responses):
        self.responses = list(responses)

    def generate(self, messages, *, tools=None, generation_config=None):
        return self.responses.pop(0)


def test_tool_loop_reports_real_web_search_progress_in_execution_order():
    adapter = SequencedAdapter(
        [
            {
                "content": "",
                "tool_calls": [
                    {
                        "id": "search-1",
                        "type": "function",
                        "function": {
                            "name": "web_search",
                            "arguments": '{"query": "GPT-SoVITS 最新版本"}',
                        },
                    }
                ],
            },
            {"content": "搜索后的回答", "tool_calls": []},
        ]
    )
    manager = ToolManager()
    manager.register(
        "web_search",
        lambda query: {"results": [{"title": query}]},
        parameters={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    )
    progress = []

    result = run_serial_tool_loop(
        messages=[{"role": "user", "content": "查一下"}],
        adapter=adapter,
        tool_manager=manager,
        progress_callback=progress.append,
    )

    assert result.final_output == "搜索后的回答"
    assert progress == [
        "正在请求模型...",
        "正在联网搜索：GPT-SoVITS 最新版本",
        "联网搜索 完成",
        "正在结合工具结果继续思考...",
        "模型已生成回复",
    ]


def test_workspace_lookup_has_specific_visible_progress_messages():
    adapter = SequencedAdapter(
        [
            {
                "content": "",
                "tool_calls": [
                    {
                        "id": "workspace-1",
                        "type": "function",
                        "function": {
                            "name": "get_workspace_info",
                            "arguments": "{}",
                        },
                    }
                ],
            },
            {"content": "项目根目录已找到", "tool_calls": []},
        ]
    )
    manager = ToolManager()
    manager.register(
        "get_workspace_info",
        lambda: {
            "project_root": "D:/project",
            "process_cwd": "D:/project",
            "allowed_roots": ["D:/project"],
        },
        parameters={"type": "object", "properties": {}},
    )
    progress = []

    run_serial_tool_loop(
        messages=[{"role": "user", "content": "项目根目录在哪"}],
        adapter=adapter,
        tool_manager=manager,
        progress_callback=progress.append,
    )

    assert "正在查看工作区信息" in progress
    assert "工作区信息查询 完成" in progress


def test_progress_callback_failure_never_interrupts_agent_execution():
    adapter = SequencedAdapter([{"content": "正常回复", "tool_calls": []}])
    manager = ToolManager()

    def broken_callback(_text):
        raise RuntimeError("UI closed")

    result = run_serial_tool_loop(
        messages=[{"role": "user", "content": "你好"}],
        adapter=adapter,
        tool_manager=manager,
        progress_callback=broken_callback,
    )

    assert result.final_output == "正常回复"
