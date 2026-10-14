import importlib.util
import io
import json
import tarfile
from pathlib import Path
import pytest

P = Path(__file__).resolve().parents[1] / "maintenance" / "render_data_backup.py"
SPEC = importlib.util.spec_from_file_location("render_data_backup", P)
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


def test_backup_verify_restore_roundtrip(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "raw.jsonl").write_text('{"ts":1}\n{"ts":2}\n')
    nested = source / "sub"
    nested.mkdir()
    (nested / "state.json").write_text('{"symbol":"BTCUSD"}')
    archive = tmp_path / "backup.tar.gz"
    result = M.create_backup(source, archive)
    assert result["files"] == 2
    assert M.verify_backup(archive)["ok"] is True
    restored = tmp_path / "restored"
    out = M.restore_backup(archive, restored)
    assert out["restored_files"] == 2
    assert (restored / "raw.jsonl").read_text() == (source / "raw.jsonl").read_text()
    assert (restored / "sub" / "state.json").read_text() == (source / "sub" / "state.json").read_text()


def test_restore_refuses_overwrite_by_default(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "a.txt").write_text("before")
    archive = tmp_path / "backup.tar.gz"
    M.create_backup(source, archive)
    dest = tmp_path / "dest"
    dest.mkdir()
    (dest / "a.txt").write_text("keep")
    with pytest.raises(FileExistsError):
        M.restore_backup(archive, dest)
    assert (dest / "a.txt").read_text() == "keep"


def test_backup_verification_rejects_tampered_payload(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "a.txt").write_text("good")
    archive = tmp_path / "backup.tar.gz"
    M.create_backup(source, archive)
    tampered = tmp_path / "tampered.tar.gz"
    with tarfile.open(archive, "r:gz") as old, tarfile.open(tampered, "w:gz") as new:
        for member in old.getmembers():
            data = old.extractfile(member).read()
            if member.name == "a.txt":
                data = b"tampered"
            info = tarfile.TarInfo(member.name)
            info.size = len(data)
            info.mode = 0o600
            new.addfile(info, io.BytesIO(data))
    with pytest.raises(ValueError, match="checksum mismatch"):
        M.verify_backup(tampered)


def test_backup_rejects_symlinks(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    target = tmp_path / "outside.txt"
    target.write_text("secret")
    (source / "link").symlink_to(target)
    with pytest.raises(ValueError, match="symlink"):
        M.create_backup(source, tmp_path / "backup.tar.gz")
