#!/usr/bin/env python3
"""Stage checksum-locked Herspers engine patches over a pristine upstream archive."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
STAMP = ".herspers-prepared.json"
_spec = importlib.util.spec_from_file_location("_herspers_fetch", ROOT / "tools/fetch_upstream.py")
fetcher = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fetcher)


def relative_path(value: str) -> PurePosixPath:
    if (not isinstance(value, str) or not value or "\\" in value or ":" in value
            or "\0" in value or any(p in ("", ".", "..") for p in value.split("/"))):
        raise ValueError(f"Unsafe relative path: {value!r}")
    reserved = {"con", "prn", "aux", "nul", *[f"{kind}{n}" for kind in ("com", "lpt") for n in range(1, 10)]}
    if any(p.endswith((".", " ")) or p.split(".")[0].lower() in reserved for p in value.split("/")):
        raise ValueError(f"Unsafe portable relative path: {value!r}")
    return PurePosixPath(value)


def no_links(path: Path) -> None:
    for item in (path, *path.parents):
        if item.is_symlink():
            raise ValueError(f"Symlink is unsupported; preserve it: {item}")


def ordinary(path: Path, base: Path) -> None:
    """Refuse links, including links in a path's parent directories."""
    path.relative_to(base)
    no_links(path)
    if not path.is_file():
        raise ValueError(f"Missing regular file: {path}")


def apply_patch(original: bytes, patch: bytes, path: str, new_file: bool = False) -> bytes:
    """Apply one exact unified diff, without fuzzy offsets or external commands."""
    lines = patch.splitlines(keepends=True)
    index = 0
    while index < len(lines) and lines[index].startswith((b"diff --git ", b"index ", b"new file mode ")):
        index += 1
    expected = (b"/dev/null" if new_file else b"a/" + path.encode(), b"b/" + path.encode())
    for prefix, name in zip((b"--- ", b"+++ "), expected):
        if index >= len(lines) or lines[index].rstrip(b"\r\n").split(b"\t", 1)[0] != prefix + name:
            raise ValueError(f"Patch headers do not match {path}")
        index += 1
    source, output, cursor, hunks = original.splitlines(keepends=True), [], 0, 0
    while index < len(lines):
        match = re.fullmatch(rb"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@[^\r\n]*\r?\n?", lines[index])
        if not match:
            raise ValueError(f"Invalid unified hunk for {path}")
        start, old_count, new_start, new_count = [int(v) if v is not None else 1 for v in match.groups()]
        old_offset = start - 1 if old_count else start
        new_offset = new_start - 1 if new_count else new_start
        if old_offset < cursor or old_offset > len(source):
            raise ValueError(f"Overlapping or out-of-range patch hunk: {path}")
        output.extend(source[cursor:old_offset])
        if new_offset != len(output):
            raise ValueError(f"Patch output position mismatch: {path}")
        cursor, old_seen, new_seen = old_offset, 0, 0
        index += 1
        while old_seen < old_count or new_seen < new_count:
            if index >= len(lines) or lines[index][:1] not in (b" ", b"-", b"+"):
                raise ValueError(f"Incomplete patch hunk: {path}")
            kind, body = lines[index][:1], lines[index][1:]
            index += 1
            if index < len(lines) and lines[index].rstrip(b"\r\n") == b"\\ No newline at end of file":
                body = body[:-1] if body.endswith(b"\n") else body
                index += 1
            if kind != b"+":
                if cursor >= len(source) or source[cursor] != body:
                    raise ValueError(f"Patch context mismatch: {path}")
                cursor += 1
                old_seen += 1
            if kind != b"-":
                output.append(body)
                new_seen += 1
            if old_seen > old_count or new_seen > new_count:
                raise ValueError(f"Patch hunk count mismatch: {path}")
        hunks += 1
    if not hunks:
        raise ValueError(f"Patch has no hunks: {path}")
    return b"".join(output + source[cursor:])


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    def failed(error):
        raise error
    for folder, dirs, files in os.walk(root, onerror=failed, followlinks=False):
        dirs.sort()
        for name in sorted(dirs + files):
            item = Path(folder) / name
            if item.is_symlink():
                raise ValueError(f"Edited prepared cache contains a symlink; preserve it: {item}")
            if item.is_dir():
                continue
            if item == root / STAMP:
                continue
            ordinary(item, root)
            digest.update(item.relative_to(root).as_posix().encode() + b"\0")
            digest.update(b"x" if item.stat().st_mode & 0o111 else b"-")
            digest.update(fetcher.digest(item).encode() + b"\0")
    return digest.hexdigest()


def prepare(lock: dict, manifest_path: Path, cache: Path, supplied_archive: Path | None = None) -> Path:
    ordinary(manifest_path, manifest_path.parent)
    raw_manifest = manifest_path.read_bytes()
    manifest = json.loads(raw_manifest)
    if not isinstance(lock.get("commit"), str) or not re.fullmatch(r"[0-9a-f]{40,64}", lock["commit"]):
        raise ValueError("Invalid pinned upstream commit")
    if not isinstance(lock.get("archive_sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", lock["archive_sha256"]):
        raise ValueError("Invalid pinned archive checksum")
    if (not isinstance(manifest, dict) or set(manifest) != {"upstream_commit", "files"} or manifest["upstream_commit"] != lock["commit"]
            or not isinstance(manifest["files"], list)):
        raise ValueError("Patch manifest must match the pinned upstream commit and contain files")
    fingerprint, entries, seen = hashlib.sha256(raw_manifest), [], set()
    for entry in manifest["files"]:
        if not isinstance(entry, dict) or set(entry) != {"path", "before_sha256", "after_sha256", "patch"}:
            raise ValueError("Invalid patch manifest file entry")
        relative = relative_path(entry["path"])
        identity = str(relative).casefold()
        if (relative.name.casefold() in ("cargo.lock", STAMP.casefold())
                or ".git" in [p.casefold() for p in relative.parts] or identity in seen):
            raise ValueError(f"Duplicate or protected patch target: {relative}")
        seen.add(identity)
        for field in ("before_sha256", "after_sha256"):
            if entry[field] is None and field == "before_sha256":
                continue
            if not isinstance(entry[field], str) or not re.fullmatch(r"[0-9a-f]{64}", entry[field]):
                raise ValueError(f"Invalid {field}: {relative}")
        patch_path = manifest_path.parent.joinpath(*relative_path(entry["patch"]).parts)
        ordinary(patch_path, manifest_path.parent)
        patch = patch_path.read_bytes()
        fingerprint.update(len(patch).to_bytes(8, "big") + patch)
        entries.append((entry, relative, patch))
    # Fetch verifies the archive; its editable extraction is deliberately never copied.
    # Repository renames change GitHub's tar wrapper without changing the git
    # commit. Preserve older checked archives/extractions in their own caches.
    upstream_cache = cache.parent / "upstream" / lock["archive_sha256"][:12]
    no_links(cache)
    no_links(upstream_cache)
    if supplied_archive is not None:
        ordinary(supplied_archive, supplied_archive.parent)
    fetcher.fetch(lock, upstream_cache, supplied_archive)
    archive = supplied_archive or upstream_cache / f"{lock['commit']}.tar.gz"
    ordinary(archive, archive.parent)
    patch_hash = fingerprint.hexdigest()
    cache.mkdir(parents=True, exist_ok=True)
    source_identity = hashlib.sha256(json.dumps(lock, sort_keys=True).encode() + bytes.fromhex(patch_hash)).hexdigest()
    destination = cache / f"{lock['commit']}-{source_identity}"
    lease = cache / f".{destination.name}.preparing"
    try:
        lease.mkdir()
    except FileExistsError as error:
        raise ValueError(f"Preparation is already in progress or has a stale lock; preserve it: {lease}") from error
    stage = None
    try:
        stage = Path(tempfile.mkdtemp(prefix="source-", dir=cache))
        fetcher.unpack(archive, stage, lock["archive_root"])
        if (stage / STAMP).exists():
            raise ValueError("Upstream archive contains a reserved preparation stamp")
        for entry, relative, patch in entries:
            target = stage.joinpath(*relative.parts)
            before = entry["before_sha256"]
            if before is None:
                if target.exists() or target.is_symlink():
                    raise ValueError(f"New patch file already exists: {relative}")
                original = b""
            else:
                ordinary(target, stage)
                original = target.read_bytes()
                if hashlib.sha256(original).hexdigest() != before:
                    raise ValueError(f"Patch preimage checksum mismatch: {relative}")
            revised = apply_patch(original, patch, str(relative), before is None)
            if hashlib.sha256(revised).hexdigest() != entry["after_sha256"]:
                raise ValueError(f"Patch postimage checksum mismatch: {relative}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(revised)
        stamp = {"upstream": lock, "patches_sha256": patch_hash, "tree_sha256": tree_digest(stage)}
        (stage / STAMP).write_text(json.dumps(stamp, sort_keys=True, indent=2) + "\n")
        if destination.exists() or destination.is_symlink():
            if destination.is_symlink() or not destination.is_dir():
                raise ValueError(f"Unknown prepared cache; preserve it: {destination}")
            ordinary(destination / STAMP, destination)
            if json.loads((destination / STAMP).read_text()) != stamp or tree_digest(destination) != stamp["tree_sha256"]:
                raise ValueError(f"Edited or unknown prepared cache; preserve it: {destination}")
        else:
            os.rename(stage, destination)
        return destination
    finally:
        if stage is not None and stage.exists():
            shutil.rmtree(stage)
        lease.rmdir()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, help="Use a local source archive (still checksum checked)")
    parser.add_argument("--manifest", type=Path, default=ROOT / "patches/upstream.json")
    parser.add_argument("--cache", type=Path, default=ROOT / ".cache/herspers-upstream")
    args = parser.parse_args()
    try:
        lock = json.loads((ROOT / "upstream.lock.json").read_text())
        print(prepare(lock, args.manifest.absolute(), args.cache.absolute(), args.archive.absolute() if args.archive else None))
        return 0
    except (OSError, ValueError, tarfile.TarError) as error:
        print(f"prepare_upstream: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
