import hashlib
import io
import json
import zipfile

import pytest

from app import updater
from app.updater import (
    UpdateError,
    _install_archive,
    current_install,
    expected_sha256,
    prepare_latest,
    release_api_url,
    valid_release_tag,
)


def _app_zip(data: bytes) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("TipStreamApp.exe", data)
    return buffer.getvalue()


def test_release_tag_and_repository_are_validated():
    assert valid_release_tag("v1.2.3")
    assert valid_release_tag("1.2.3-rc.1")
    assert not valid_release_tag("../../evil")
    with pytest.raises(UpdateError):
        release_api_url("bad/repo/path")


def test_sha256_manifest_requires_exact_asset_name():
    digest = hashlib.sha256(b"zip").hexdigest()
    manifest = f"{digest}  TipStreamApp-win-x64.zip\n"
    assert expected_sha256(manifest) == digest
    with pytest.raises(UpdateError):
        expected_sha256(f"{digest}  other.zip")


def test_update_installs_only_the_expected_windows_executable(tmp_path):
    payload = b"MZ" + b"x" * 4096
    installed = _install_archive(_app_zip(payload), "v1.2.3", tmp_path)
    assert installed.read_bytes() == payload
    assert current_install(tmp_path) == ("v1.2.3", installed)
    assert json.loads((tmp_path / "current.json").read_text())["tag"] == "v1.2.3"


def test_update_rejects_bad_payload_and_untrusted_tag(tmp_path):
    with pytest.raises(UpdateError):
        _install_archive(_app_zip(b"not a windows exe"), "v1.2.3", tmp_path)
    with pytest.raises(UpdateError):
        _install_archive(_app_zip(b"MZ" + b"x" * 4096), "../../escape", tmp_path)


def test_prepare_latest_downloads_only_after_checksum_verification(tmp_path, monkeypatch):
    payload = b"MZ" + b"x" * 4096
    package = _app_zip(payload)
    manifest = f"{hashlib.sha256(package).hexdigest()}  TipStreamApp-win-x64.zip\n".encode()
    monkeypatch.setattr(updater, "fetch_latest_release", lambda _repo: {
        "tag": "v2.0.0", "package_url": "https://github.com/example/package",
        "checksum_url": "https://github.com/example/checksums",
    })
    monkeypatch.setattr(updater, "_open", lambda url, timeout=15: package if url.endswith("package") else manifest)
    tag, exe, updated, _message = prepare_latest("owner/repo", tmp_path)
    assert (tag, updated, exe.read_bytes()) == ("v2.0.0", True, payload)


def test_prepare_latest_falls_back_to_last_good_install_when_offline(tmp_path, monkeypatch):
    payload = b"MZ" + b"x" * 4096
    installed = _install_archive(_app_zip(payload), "v1.0.0", tmp_path)
    monkeypatch.setattr(updater, "fetch_latest_release", lambda _repo: (_ for _ in ()).throw(UpdateError("offline")))
    tag, exe, updated, _message = prepare_latest("owner/repo", tmp_path)
    assert (tag, exe, updated) == ("v1.0.0", installed, False)
