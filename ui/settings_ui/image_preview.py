"""Small, file-versioned previews for settings widgets (GUI thread only)."""

from __future__ import annotations

from pathlib import Path
from hashlib import sha256
import re

from PySide6.QtCore import QIODevice, QSaveFile, QSize, QStandardPaths, Qt
from PySide6.QtGui import QImageReader, QPixmap, QPixmapCache
from PySide6.QtWidgets import QApplication

_MASTER_EDGE = 384
_CACHE_MAX_BYTES = 64 * 1024 * 1024
_CACHE_MAX_FILES = 256
_cache_writes = 0


def _disk_cache_root() -> Path | None:
    root = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericCacheLocation)
    return Path(root) / "galgame-agent" / "image-previews-v1" if root else None


def _save_cached_preview(path: Path, preview: QPixmap) -> None:
    global _cache_writes
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        output = QSaveFile(str(path))
        if not output.open(QIODevice.OpenModeFlag.WriteOnly):
            return
        if not preview.save(output, "PNG"):
            output.cancelWriting()
            return
        if not output.commit():
            return
        _cache_writes += 1
        if _cache_writes % 16 != 1:
            return
        entries = []
        for candidate in path.parent.iterdir():
            if re.fullmatch(r"[0-9a-f]{64}\.png", candidate.name) and candidate.is_file():
                stat = candidate.stat()
                entries.append((stat.st_mtime_ns, stat.st_size, candidate))
        total = sum(entry[1] for entry in entries)
        count = len(entries)
        for _, size, candidate in sorted(entries):
            if total <= _CACHE_MAX_BYTES and count <= _CACHE_MAX_FILES:
                break
            candidate.unlink(missing_ok=True)
            total -= size
            count -= 1
    except OSError:
        pass  # A read-only/full cache must never prevent displaying the image.


def image_preview(path: str, size: QSize) -> QPixmap:
    """Share thumbnails without retaining full-size images or stale imports.

    Qt's application-wide LRU cache bounds memory use. The absolute path, file
    metadata and requested size separate previews across files and revisions.
    """
    if not path or QApplication.instance() is None or size.isEmpty():
        return QPixmap()
    try:
        source = Path(path).resolve()
        version = source.stat()
    except (OSError, ValueError):
        return QPixmap()
    identity = (
        "settings-image-preview", str(source), version.st_dev, version.st_ino, version.st_mtime_ns,
        version.st_ctime_ns, version.st_size,
    )
    key = repr((*identity, size.width(), size.height()))
    cached = QPixmapCache.find(key)
    if cached is not None:
        return cached

    # PNG still needs full decoding with setScaledSize(). Share one bounded
    # master across the avatar/gallery/combo sizes, including subsequent runs.
    edge = max(_MASTER_EDGE, size.width(), size.height())
    master_key = repr((*identity, "master-v1", edge))
    master = QPixmapCache.find(master_key)
    if master is None:
        cache_root = _disk_cache_root()
        cache_path = cache_root / (sha256(master_key.encode("utf-8")).hexdigest() + ".png") if cache_root else None
        master = QPixmap(str(cache_path)) if cache_path and cache_path.is_file() else QPixmap()
        if master.isNull():
            reader = QImageReader(str(source))
            original_size = reader.size()
            if original_size.isValid():
                target = original_size.scaled(QSize(edge, edge), Qt.AspectRatioMode.KeepAspectRatio)
                if target.width() < original_size.width() or target.height() < original_size.height():
                    reader.setScaledSize(target)
            image = reader.read()
            if image.isNull():
                return QPixmap()
            master = QPixmap.fromImage(image)
            if master.width() > edge or master.height() > edge:
                master = master.scaled(QSize(edge, edge), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            if cache_path:
                _save_cached_preview(cache_path, master)
        QPixmapCache.insert(master_key, master)
    preview = master.scaled(
        size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation,
    )
    QPixmapCache.insert(key, preview)
    return preview
