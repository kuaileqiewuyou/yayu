"""芽语（Yayu）主入口 — 聊天窗口"""
import sys

from core.runtime.chat_app import run_chat_app


def main() -> int:
    return run_chat_app(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
