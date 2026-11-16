"""Old GiftStream builds must not pile up in %LOCALAPPDATA%/GiftStream/versions."""
from __future__ import annotations

import json
from pathlib import Path

from app import updater


def make_version(root: Path, tag: str, payload: bytes = b"MZ" + b"0" * 2000) -> Path:
    folder = root / "versions" / tag
    folder.mkdir(parents=True)
    (folder / "GiftStream.exe").write_bytes(payload)
    return folder


def test_only_the_current_version_and_one_before_it_stay(tmp_path):
    for tag in ["v0.20.0", "v0.21.0", "v0.22.0", "v0.23.0", "v0.24.0", "v0.25.0"]:
        make_version(tmp_path, tag)
    (tmp_path / "current.json").write_text(json.dumps({"tag": "v0.25.0"}))

    removed = updater.prune_versions(tmp_path)

    left = sorted(folder.name for folder in (tmp_path / "versions").iterdir())
    assert left == ["v0.24.0", "v0.25.0"]
    assert sorted(removed) == ["v0.20.0", "v0.21.0", "v0.22.0", "v0.23.0"]


def test_the_running_version_is_never_deleted(tmp_path):
    """A rollback situation: the newest installed build is not the running one."""
    for tag in ["v0.23.0", "v0.24.0", "v0.25.0"]:
        make_version(tmp_path, tag)
    (tmp_path / "current.json").write_text(json.dumps({"tag": "v0.25.0"}))

    updater.prune_versions(tmp_path, protected=("v0.23.0",))

    left = sorted(folder.name for folder in (tmp_path / "versions").iterdir())
    assert left == ["v0.23.0", "v0.24.0", "v0.25.0"]


def test_pruning_is_a_no_op_without_versions(tmp_path):
    assert updater.prune_versions(tmp_path) == []
    (tmp_path / "versions").mkdir()
    assert updater.prune_versions(tmp_path) == []


def test_non_version_folders_are_left_alone(tmp_path):
    make_version(tmp_path, "v0.24.0")
    make_version(tmp_path, "v0.25.0")
    (tmp_path / "versions" / "notes").mkdir()
    (tmp_path / "versions" / "notes" / "readme.txt").write_text("keep me")

    updater.prune_versions(tmp_path)

    assert (tmp_path / "versions" / "notes" / "readme.txt").read_text() == "keep me"


def test_installing_a_new_version_prunes_the_old_ones(tmp_path):
    for tag in ["v0.20.0", "v0.21.0"]:
        make_version(tmp_path, tag)
    executable = b"MZ" + b"1" * 4000

    updater._install_executable(executable, "v0.22.0", tmp_path)

    left = sorted(folder.name for folder in (tmp_path / "versions").iterdir())
    assert left == ["v0.21.0", "v0.22.0"]
