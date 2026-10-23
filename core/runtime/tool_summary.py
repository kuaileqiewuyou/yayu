from dataclasses import dataclass, field


@dataclass(slots=True)
class ToolInvocationRecord:
    order_index: int
    tool_name: str
    status: str
    arguments_summary: str
    result_summary: str | None = None
    error_summary: str | None = None
    approval_request: dict[str, object] | None = None


@dataclass(slots=True)
class ToolTurnSummary:
    total_count: int
    success_count: int
    failure_count: int

    @classmethod
    def from_records(cls, records: list[ToolInvocationRecord]) -> "ToolTurnSummary":
        success_count = sum(1 for record in records if record.status == "success")
        total_count = len(records)
        failure_count = total_count - success_count
        return cls(
            total_count=total_count,
            success_count=success_count,
            failure_count=failure_count,
        )


@dataclass(slots=True)
class ToolLoopTurnResult:
    final_output: str
    invocation_records: list[ToolInvocationRecord] = field(default_factory=list)
    summary: ToolTurnSummary = field(
        default_factory=lambda: ToolTurnSummary(
            total_count=0,
            success_count=0,
            failure_count=0,
        )
    )
    updated_messages: list[dict[str, str]] = field(default_factory=list)
