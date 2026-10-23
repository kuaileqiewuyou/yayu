def test_main_delegates_to_run_chat_app(monkeypatch):
    import main

    captured_argv = []
    argv = ["main.py", "--flag"]
    monkeypatch.setattr(main.sys, "argv", argv)

    def fake_run_chat_app(argv):
        captured_argv.append(argv)
        return 23

    monkeypatch.setattr(main, "run_chat_app", fake_run_chat_app)

    assert main.main() == 23
    assert captured_argv == [argv]
    assert captured_argv[0] is argv
