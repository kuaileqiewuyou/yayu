from core.runtime.cg_ui_handlers import handle_t2i_image_generated


class FakeWindow:
    def __init__(self):
        self.reply_statuses = []
        self.cg_previews = []

    def set_reply_status(self, text, error=False):
        self.reply_statuses.append((text, error))

    def add_cg_preview(self, image_path):
        self.cg_previews.append(image_path)
        return True


class StatusOnlyWindow:
    def __init__(self):
        self.reply_statuses = []

    def set_reply_status(self, text, error=False):
        self.reply_statuses.append((text, error))


def test_t2i_image_generated_local_path_updates_status_and_adds_preview(tmp_path):
    window = FakeWindow()
    image_path = tmp_path / "cg.png"
    image_path.write_bytes(b"fake image bytes")

    handle_t2i_image_generated(window, str(image_path))

    assert window.reply_statuses == [(f"CG 生成完成：{image_path}", False)]
    assert window.cg_previews == [str(image_path)]


def test_t2i_image_generated_comfyui_prompt_handle_reports_submitted_without_preview():
    window = FakeWindow()

    handle_t2i_image_generated(window, "comfyui://prompt/abc123")

    assert window.reply_statuses == [
        ("CG 已提交到 ComfyUI，但暂未取得图片：comfyui://prompt/abc123", False)
    ]
    assert window.cg_previews == []


def test_t2i_image_generated_comfyui_image_handle_reports_missing_cache_without_preview():
    window = FakeWindow()

    handle_t2i_image_generated(window, "comfyui://image/abc123/out.png")

    assert window.reply_statuses == [
        ("CG 已生成，但本地缓存不可用：comfyui://image/abc123/out.png", False)
    ]
    assert window.cg_previews == []


def test_t2i_image_generated_other_comfyui_handle_reports_comfyui_result_without_preview():
    window = FakeWindow()

    handle_t2i_image_generated(window, "comfyui://history/abc123")

    assert window.reply_statuses == [
        ("CG 返回 ComfyUI 结果：comfyui://history/abc123", False)
    ]
    assert window.cg_previews == []


def test_t2i_image_generated_empty_result_is_status_only():
    window = FakeWindow()

    handle_t2i_image_generated(window, "")

    assert window.reply_statuses == [("CG 生成未返回图片", True)]
    assert window.cg_previews == []


def test_t2i_image_generated_missing_path_is_status_only(tmp_path):
    window = FakeWindow()
    missing_path = tmp_path / "missing.png"

    handle_t2i_image_generated(window, str(missing_path))

    assert window.reply_statuses == [(f"CG 生成完成：{missing_path}", False)]
    assert window.cg_previews == []


def test_t2i_image_generated_without_preview_method_only_updates_status(tmp_path):
    window = StatusOnlyWindow()
    image_path = tmp_path / "cg.png"
    image_path.write_bytes(b"fake image bytes")

    handle_t2i_image_generated(window, str(image_path))

    assert window.reply_statuses == [(f"CG 生成完成：{image_path}", False)]


def test_t2i_image_generated_oserror_is_ignored_after_status(monkeypatch):
    window = FakeWindow()

    class RaisingPath:
        def __init__(self, value):
            self.value = value

        def exists(self):
            raise OSError("bad path")

    monkeypatch.setattr("core.runtime.cg_ui_handlers.Path", RaisingPath)

    handle_t2i_image_generated(window, "bad-path")

    assert window.reply_statuses == [("CG 生成完成：bad-path", False)]
    assert window.cg_previews == []
