"""工具管理器：注册和调用 LLM 可用的工具。"""
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from core.mcp.registry import namespace_mcp_tool_name


@dataclass(frozen=True)
class ToolExecutionResult:
    success: bool
    value: Any = None
    error: str | None = None


class ToolManager:
    """管理 LLM 可调用的工具"""

    def __init__(self):
        self._tools: Dict[str, Dict[str, Any]] = {}
        self._quotas: Dict[str, int] = {}
        self._quota_usage: Dict[str, int] = {}

    def register(self, name: str, func: Callable, description: str = "",
                 parameters: Optional[Dict] = None):
        """注册一个工具"""
        self._tools[name] = {
            "function": func,
            "description": description,
            "parameters": parameters or {},
        }

    def set_tool_quota(self, name: str, max_calls: int) -> None:
        """设置某工具单轮调用的配额上限（<1 视为移除配额）。"""
        if max_calls is None or int(max_calls) < 1:
            self._quotas.pop(name, None)
        else:
            self._quotas[name] = int(max_calls)

    def get_tool_quota(self, name: str) -> Optional[int]:
        """返回某工具单轮调用配额上限，未设置时为 None。"""
        return self._quotas.get(name)

    def reset_quotas(self) -> None:
        """清空本轮配额使用计数（新一轮工具循环开始前调用）。"""
        self._quota_usage = {}

    def register_mcp_tool(
        self,
        *,
        server_name: str,
        tool_name: str,
        session: Any,
        description: str = "",
        parameters: Optional[Dict] = None,
        on_call_failure: Optional[Callable[[str], None]] = None,
    ):
        namespaced_name = namespace_mcp_tool_name(server_name, tool_name)

        def call_mcp_tool(**arguments):
            try:
                return session.call_tool(tool_name, arguments)
            except Exception as exc:
                if on_call_failure is not None:
                    on_call_failure(str(exc))
                raise

        self._tools[namespaced_name] = {
            "function": call_mcp_tool,
            "description": description,
            "parameters": parameters or {"type": "object", "properties": {}},
        }

    def get_tool_definitions(self) -> List[Dict]:
        """获取 OpenAI 格式的工具定义列表"""
        definitions = []
        for name, tool in self._tools.items():
            definitions.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": tool["description"],
                    "parameters": tool["parameters"],
                },
            })
        return definitions

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> ToolExecutionResult:
        """调用指定工具"""
        if name not in self._tools:
            return ToolExecutionResult(success=False, error=f"Tool {name} does not exist")
        quota = self._quotas.get(name)
        if quota is not None:
            used = self._quota_usage.get(name, 0)
            if used >= quota:
                return ToolExecutionResult(
                    success=False,
                    error=(
                        f"已达到本轮 {name} 调用配额上限（{quota} 次）。"
                        "请基于已有信息直接回答，或改用其他工具，不要再调用本工具。"
                    ),
                )
            self._quota_usage[name] = used + 1
        try:
            result = self._tools[name]["function"](**arguments)
            if isinstance(result, ToolExecutionResult):
                return result
            return ToolExecutionResult(success=True, value=result)
        except Exception as e:
            return ToolExecutionResult(success=False, error=str(e))

    def list_tools(self) -> List[str]:
        return list(self._tools.keys())
