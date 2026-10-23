import os
from importlib import import_module

import pytest
from PySide6.QtCore import QSize
from PySide6.QtGui import QColor, QImage, QPixmapCache
from PySide6.QtWidgets import QApplication

from ui.settings_ui.image_preview import image_preview


def test_daylight_navigation_icons_render_with_the_svg_backend():
    from ui.settings_ui.daylight import icon
    for name in ("leaf", "model", "character", "music", "voice", "system", "search", "skills", "tools", "security", "memory"):
        pixmap = icon(name).pixmap(QSize(24, 24))
        assert not pixmap.isNull(), name
        assert any(pixmap.toImage().pixelColor(x, y).alpha() for x in range(24) for y in range(24)), name


@pytest.fixture(autouse=True)
def preview_app(monkeypatch, tmp_path):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(import_module("ui.settings_ui.image_preview"), "_disk_cache_root", lambda: tmp_path / "cache")
    QPixmapCache.clear()
    yield app
    QPixmapCache.clear()


def write_image(path, color="red"):
    image = QImage(240, 480, QImage.Format.Format_ARGB32)
    image.fill(QColor(color))
    assert image.save(str(path))


@pytest.fixture
def image_reads(monkeypatch):
    module = import_module("ui.settings_ui.image_preview")
    reader = module.QImageReader
    calls = []

    def create_reader(path):
        calls.append(path)
        return reader(path)

    monkeypatch.setattr(module, "QImageReader", create_reader)
    return calls


def test_repeated_previews_share_decode_and_preserve_transparency(tmp_path, image_reads):
    path = tmp_path / "sprite.png"
    write_image(path, "#80ff0000")

    first = image_preview(str(path), QSize(48, 48))
    again = image_preview(str(path), QSize(48, 48))

    assert len(image_reads) == 1
    assert first.cacheKey() == again.cacheKey()
    assert first.size() == QSize(24, 48)
    assert first.toImage().pixelColor(0, 0) == QColor("#80ff0000")


def test_preview_sizes_have_separate_cache_entries(tmp_path):
    path = tmp_path / "sprite.png"
    write_image(path)

    assert image_preview(str(path), QSize(48, 48)).size() == QSize(24, 48)
    assert image_preview(str(path), QSize(160, 160)).size() == QSize(80, 160)
    assert image_preview(str(path), QSize(220, 220)).size() == QSize(110, 220)


def test_replaced_image_is_reloaded_at_same_path(tmp_path, image_reads):
    path = tmp_path / "sprite.bmp"
    write_image(path, "red")
    old_stat = path.stat()
    first = image_preview(str(path), QSize(48, 48))
    write_image(path, "blue")
    # Same file size: the timestamp must also participate in invalidation.
    assert path.stat().st_size == old_stat.st_size
    os.utime(path, ns=(old_stat.st_atime_ns, old_stat.st_mtime_ns + 2_000_000_000))

    replaced = image_preview(str(path), QSize(48, 48))

    assert len(image_reads) == 2
    assert first.toImage().pixelColor(0, 0) == QColor("red")
    assert replaced.toImage().pixelColor(0, 0) == QColor("blue")


def test_missing_deleted_and_repaired_images_do_not_leave_stale_previews(tmp_path):
    path = tmp_path / "sprite.png"
    assert image_preview(str(path), QSize(48, 48)).isNull()
    write_image(path)
    assert not image_preview(str(path), QSize(48, 48)).isNull()
    path.unlink()
    assert image_preview(str(path), QSize(48, 48)).isNull()
    path.write_bytes(b"not an image")
    assert image_preview(str(path), QSize(48, 48)).isNull()
    write_image(path, "blue")
    assert image_preview(str(path), QSize(48, 48)).toImage().pixelColor(0, 0) == QColor("blue")


def test_relative_paths_do_not_collide_between_directories(tmp_path, monkeypatch):
    for folder, color in [("a", "red"), ("b", "blue")]:
        directory = tmp_path / folder
        directory.mkdir()
        write_image(directory / "sprite.png", color)
        monkeypatch.chdir(directory)
        assert image_preview("sprite.png", QSize(48, 48)).toImage().pixelColor(0, 0) == QColor(color)


def test_memory_eviction_reuses_disk_preview_without_losing_displayed_image(tmp_path, image_reads):
    path = tmp_path / "sprite.png"
    write_image(path)
    first = image_preview(str(path), QSize(48, 48))
    QPixmapCache.clear()
    again = image_preview(str(path), QSize(48, 48))

    assert len(image_reads) == 1
    assert first.toImage() == again.toImage()


def test_different_sizes_share_one_decode(tmp_path, image_reads):
    path = tmp_path / "sprite.png"
    write_image(path)
    for size in (48, 64, 160, 220):
        preview = image_preview(str(path), QSize(size, size))
        assert preview.size() == QSize(size // 2, size)
    assert len(image_reads) == 1


def test_unwritable_disk_cache_keeps_preview_available(tmp_path, monkeypatch):
    path = tmp_path / "sprite.png"
    write_image(path)
    blocked = tmp_path / "not-a-directory"
    blocked.write_text("occupied", encoding="utf-8")
    monkeypatch.setattr(import_module("ui.settings_ui.image_preview"), "_disk_cache_root", lambda: blocked / "cache")
    assert not image_preview(str(path), QSize(48, 48)).isNull()


def test_corrupt_cache_is_regenerated_from_original(tmp_path, image_reads):
    path = tmp_path / "sprite.png"
    write_image(path)
    first = image_preview(str(path), QSize(48, 48))
    cached = next((tmp_path / "cache").glob("*.png"))
    cached.write_bytes(b"broken cache")
    QPixmapCache.clear()
    restored = image_preview(str(path), QSize(48, 48))
    assert len(image_reads) == 2
    assert first.toImage() == restored.toImage()
    assert cached.read_bytes().startswith(b"\x89PNG")


def test_cache_pruning_only_removes_generated_thumbnails(tmp_path, monkeypatch):
    module = import_module("ui.settings_ui.image_preview")
    monkeypatch.setattr(module, "_CACHE_MAX_FILES", 2)
    monkeypatch.setattr(module, "_cache_writes", 0)
    cache = tmp_path / "cache"
    cache.mkdir()
    for i in range(3):
        path = cache / (f"{i:064x}" + ".png")
        path.write_bytes(b"old cache")
        os.utime(path, (1_600_000_000 + i, 1_600_000_000 + i))
    unrelated = cache / "keep.png"
    unrelated.write_bytes(b"not a generated thumbnail")
    source = tmp_path / "sprite.png"
    write_image(source)
    assert not image_preview(str(source), QSize(48, 48)).isNull()
    assert unrelated.read_bytes() == b"not a generated thumbnail"
    assert len([p for p in cache.glob("*.png") if p != unrelated]) == 2
