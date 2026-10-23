"""CLI for validating character template JSON-lines sample output."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TextIO

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.messaging.template_output_validator import validate_template_output


class _ParserExit(Exception):
    def __init__(self, status: int = 0) -> None:
        self.status = status


class _InjectableStreamArgumentParser(argparse.ArgumentParser):
    def __init__(self, *args, stdout: TextIO, stderr: TextIO, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._stdout = stdout
        self._stderr = stderr

    def exit(self, status: int = 0, message: str | None = None) -> None:
        if message:
            self._print_message(message, self._stderr)
        raise _ParserExit(status)

    def print_help(self, file: TextIO | None = None) -> None:
        super().print_help(file if file is not None else self._stdout)

    def print_usage(self, file: TextIO | None = None) -> None:
        super().print_usage(file if file is not None else self._stderr)

    def error(self, message: str) -> None:
        self.print_usage(self._stderr)
        self.exit(2, f"{self.prog}: error: {message}\n")


def main(
    argv: list[str] | None = None,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    stdin = sys.stdin if stdin is None else stdin
    stdout = sys.stdout if stdout is None else stdout
    stderr = sys.stderr if stderr is None else stderr

    parser = _InjectableStreamArgumentParser(
        description="校验角色模板 JSON-lines 示例输出。",
        stdout=stdout,
        stderr=stderr,
    )
    parser.add_argument(
        "path",
        nargs="?",
        default="-",
        help="要校验的 UTF-8 文件路径；省略或使用 - 时从标准输入读取。",
    )
    try:
        args = parser.parse_args(argv)
    except _ParserExit as exc:
        return exc.status

    if args.path == "-":
        text = stdin.read()
    else:
        try:
            text = Path(args.path).read_text(encoding="utf-8")
        except OSError as exc:
            print(f"无法读取 {args.path}: {exc}", file=stderr)
            return 2

    result = validate_template_output(text)

    for issue in result.errors:
        print(f"错误：第 {issue.line} 行：{issue.message}", file=stdout)
    for issue in result.warnings:
        print(f"警告：第 {issue.line} 行：{issue.message}", file=stdout)

    if result.errors:
        return 1

    if result.warnings:
        print("校验通过：存在警告，请按需调整。", file=stdout)
    else:
        print("校验通过：未发现错误或警告。", file=stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
