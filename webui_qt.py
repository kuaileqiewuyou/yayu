"""芽语（Yayu）设置窗口入口"""
import sys

from core.runtime.settings_app import run_settings_app


def main() -> int:
    return run_settings_app(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
