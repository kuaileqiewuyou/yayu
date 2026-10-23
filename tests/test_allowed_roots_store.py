from pathlib import Path

import pytest

from core.security.allowed_roots import AllowedRootsStore


def test_allowed_roots_store_always_includes_project_root_and_normalizes_custom_roots(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    custom_root = tmp_path / "custom"
    nested_root = custom_root / "nested"
    project_root.mkdir()
    nested_root.mkdir(parents=True)
    store = AllowedRootsStore(tmp_path / "security" / "allowed-roots.json", project_root=project_root)

    stored = store.replace([nested_root, custom_root, custom_root])

    assert stored == [project_root.resolve(), custom_root.resolve()]
    assert store.load() == stored


def test_allowed_roots_store_ignores_missing_and_malformed_entries(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    valid_root = tmp_path / "valid"
    project_root.mkdir()
    valid_root.mkdir()
    path = tmp_path / "security" / "allowed-roots.json"
    path.parent.mkdir()
    path.write_text(
        '{"allowed_roots": ["' + str(valid_root).replace("\\", "\\\\") + '", 3, "' + str(tmp_path / "missing").replace("\\", "\\\\") + '"]}',
        encoding="utf-8",
    )

    store = AllowedRootsStore(path, project_root=project_root)

    assert store.load() == [project_root.resolve(), valid_root.resolve()]


def test_allowed_roots_store_cannot_remove_builtin_project_root(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    custom_root = tmp_path / "custom"
    project_root.mkdir()
    custom_root.mkdir()
    store = AllowedRootsStore(tmp_path / "security" / "allowed-roots.json", project_root=project_root)
    store.replace([custom_root])

    with pytest.raises(PermissionError, match="built-in"):
        store.remove(project_root)

    assert store.remove(custom_root) == [project_root.resolve()]


def test_allowed_roots_store_notifies_subscribers_after_mutation(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    custom_root = tmp_path / "custom"
    project_root.mkdir()
    custom_root.mkdir()
    store = AllowedRootsStore(tmp_path / "security" / "allowed-roots.json", project_root=project_root)
    snapshots: list[list[Path]] = []
    store.subscribe(lambda roots: snapshots.append(list(roots)))

    store.add(custom_root)
    store.remove(custom_root)

    assert snapshots == [
        [project_root.resolve(), custom_root.resolve()],
        [project_root.resolve()],
    ]
