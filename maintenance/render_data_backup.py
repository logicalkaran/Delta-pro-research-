"""Verified local snapshot/restore utility for collector data; no network or credentials."""
from __future__ import annotations
import argparse
import hashlib
import io
import json
import os
import tarfile
import tempfile
from pathlib import Path, PurePosixPath


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def create_backup(source: Path, output: Path) -> dict:
    source = source.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    files = {}
    payloads = {}
    for p in sorted(source.rglob("*")):
        if p.is_symlink():
            raise ValueError(f"symlink not allowed in backup source: {p}")
        if p.is_file():
            rel = p.relative_to(source).as_posix()
            data = p.read_bytes()
            files[rel] = {"sha256": sha256(data), "size": len(data)}
            payloads[rel] = data
    manifest = {"format": "btc-render-data-backup-v1", "files": files}
    fd, tmp = tempfile.mkstemp(prefix=".backup-", suffix=".tar.gz", dir=str(output.parent))
    os.close(fd)
    try:
        with tarfile.open(tmp, "w:gz") as tf:
            for rel, data in payloads.items():
                info = tarfile.TarInfo(rel)
                info.size = len(data)
                info.mode = 0o600
                tf.addfile(info, io.BytesIO(data))
            raw = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
            info = tarfile.TarInfo("BACKUP_MANIFEST.json")
            info.size = len(raw)
            info.mode = 0o600
            tf.addfile(info, io.BytesIO(raw))
        os.replace(tmp, output)
    finally:
        try: os.unlink(tmp)
        except FileNotFoundError: pass
    return {"archive": str(output), "files": len(files), "bytes": output.stat().st_size,
            "manifest_sha256": sha256(json.dumps(manifest, sort_keys=True).encode())}


def _safe_member(name: str) -> bool:
    p = PurePosixPath(name)
    return bool(name) and not p.is_absolute() and all(part not in ("", ".", "..") for part in p.parts)


def verify_backup(archive: Path) -> dict:
    with tarfile.open(archive, "r:gz") as tf:
        members = tf.getmembers()
        by_name = {m.name: m for m in members}
        if len(by_name) != len(members) or "BACKUP_MANIFEST.json" not in by_name:
            raise ValueError("missing or duplicate backup manifest")
        if any(not _safe_member(m.name) or not m.isfile() for m in members):
            raise ValueError("unsafe archive member")
        manifest = json.load(tf.extractfile(by_name["BACKUP_MANIFEST.json"]))
        if manifest.get("format") != "btc-render-data-backup-v1":
            raise ValueError("unknown backup format")
        expected = manifest.get("files")
        if not isinstance(expected, dict):
            raise ValueError("invalid manifest files")
        payload_names = set(by_name) - {"BACKUP_MANIFEST.json"}
        if payload_names != set(expected):
            raise ValueError("archive/manifest file list mismatch")
        for name, spec in expected.items():
            if not _safe_member(name):
                raise ValueError("unsafe manifest path")
            data = tf.extractfile(by_name[name]).read()
            if len(data) != spec.get("size") or sha256(data) != spec.get("sha256"):
                raise ValueError(f"checksum mismatch: {name}")
    return {"ok": True, "files": len(expected), "archive": str(archive)}


def restore_backup(archive: Path, destination: Path, overwrite: bool = False) -> dict:
    verify_backup(archive)
    destination.mkdir(parents=True, exist_ok=True)
    restored = 0
    with tarfile.open(archive, "r:gz") as tf:
        manifest = json.load(tf.extractfile("BACKUP_MANIFEST.json"))
        for name in manifest["files"]:
            target = (destination / name).resolve()
            if destination.resolve() not in target.parents:
                raise ValueError("restore path escapes destination")
            if target.exists() and not overwrite:
                raise FileExistsError(str(target))
            target.parent.mkdir(parents=True, exist_ok=True)
            data = tf.extractfile(name).read()
            tmp = target.with_name(target.name + ".restore-tmp")
            tmp.write_bytes(data)
            os.replace(tmp, target)
            restored += 1
    return {"ok": True, "restored_files": restored, "destination": str(destination)}


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="action", required=True)
    c = sub.add_parser("create"); c.add_argument("--source", type=Path, required=True); c.add_argument("--output", type=Path, required=True)
    v = sub.add_parser("verify"); v.add_argument("archive", type=Path)
    r = sub.add_parser("restore"); r.add_argument("archive", type=Path); r.add_argument("--destination", type=Path, required=True); r.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    if args.action == "create": result = create_backup(args.source, args.output)
    elif args.action == "verify": result = verify_backup(args.archive)
    else: result = restore_backup(args.archive, args.destination, args.overwrite)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
