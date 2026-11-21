#!/usr/bin/env python3
"""Fetch the pinned public source with TLS and archive checksum verification."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sys
import tarfile
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
MAX_EXPANDED_BYTES = 1024 * 1024 * 1024


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def unpack(archive: Path, destination: Path, prefix: str) -> None:
    """Extract files/directories, materializing safe sibling-file symlinks."""
    with tarfile.open(archive, "r:gz") as tar:
        entries = tar.getmembers()
        if len(entries) > 50000 or sum(m.size for m in entries) > MAX_EXPANDED_BYTES:
            raise ValueError("Source archive exceeds extraction limits")
        seen = set()
        for member in entries:
            name = PurePosixPath(member.name)
            if (name.is_absolute() or ".." in name.parts or not name.parts
                    or name.parts[0] != prefix or member.name in seen
                    or not (member.isfile() or member.isdir() or member.issym())):
                raise ValueError(f"Unsafe source archive member: {member.name}")
            if member.issym():
                link = PurePosixPath(member.linkname)
                # The pinned source has CLAUDE.md -> AGENTS.md. Materialize
                # sibling regular files instead of creating filesystem links.
                if link.is_absolute() or len(link.parts) != 1 or link.parts[0] in ("..", "."):
                    raise ValueError(f"Unsafe source archive member: {member.name}")
                try:
                    original = tar.getmember(str(name.parent / link))
                except KeyError as error:
                    raise ValueError(f"Missing source archive link target: {member.name}") from error
                if not original.isfile():
                    raise ValueError(f"Unsafe source archive member: {member.name}")
            seen.add(member.name)
        # No filesystem links, devices or traversal; supports macOS Python 3.9+.
        for member in entries:
            relative = PurePosixPath(member.name).relative_to(prefix)
            target = destination.joinpath(*relative.parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            original = tar.getmember(str(PurePosixPath(member.name).parent / member.linkname)) if member.issym() else member
            source = tar.extractfile(original)
            if source is None:
                raise ValueError(f"Missing source data: {member.name}")
            with source, target.open("xb") as output:
                shutil.copyfileobj(source, output)
            target.chmod(0o755 if member.mode & 0o111 else 0o644)


def fetch(lock: dict, cache: Path, supplied_archive: Path | None = None) -> Path:
    cache.mkdir(parents=True, exist_ok=True)
    archive = supplied_archive or cache / f"{lock['commit']}.tar.gz"
    if not archive.exists():
        if supplied_archive is not None:
            raise ValueError(f"Archive does not exist: {archive}")
        if not lock["archive_url"].startswith("https://"):
            raise ValueError("Source download must use HTTPS")
        fd, download = tempfile.mkstemp(prefix="download-", dir=cache)
        try:
            with os.fdopen(fd, "wb") as output:
                with urllib.request.urlopen(lock["archive_url"], timeout=120) as response:
                    total = 0
                    while block := response.read(1024 * 1024):
                        total += len(block)
                        if total > MAX_ARCHIVE_BYTES:
                            raise ValueError("Source download exceeds size limit")
                        output.write(block)
            if digest(Path(download)) != lock["archive_sha256"]:
                raise ValueError("Source archive checksum mismatch")
            os.replace(download, archive)
        finally:
            Path(download).unlink(missing_ok=True)
    if archive.stat().st_size > MAX_ARCHIVE_BYTES or digest(archive) != lock["archive_sha256"]:
        raise ValueError("Source archive checksum mismatch; refusing to use it")
    source = cache / lock["commit"]
    stamp = source / ".herspers-source.json"
    if source.exists():
        if not stamp.is_file() or json.loads(stamp.read_text()) != lock:
            raise ValueError(f"Existing source has different provenance; preserve it: {source}")
        # Like a normal checkout, this cache can contain deliberate local edits.
        # The stamp records origin; it does not attest an unmodified source tree.
        return source
    stage = Path(tempfile.mkdtemp(prefix="source-", dir=cache))
    try:
        unpack(archive, stage, lock["archive_root"])
        (stage / ".herspers-source.json").write_text(json.dumps(lock, indent=2) + "\n")
        os.rename(stage, source)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return source


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, help="Use a previously downloaded archive (still checksum checked)")
    parser.add_argument("--cache", type=Path, default=ROOT / ".cache" / "upstream")
    args = parser.parse_args()
    try:
        lock = json.loads((ROOT / "upstream.lock.json").read_text())
        # Match the preparer's archive-specific cache while retaining older
        # source provenance and any deliberate local edits untouched.
        checksum = lock["archive_sha256"]
        if not isinstance(checksum, str) or len(checksum) != 64 or any(c not in "0123456789abcdef" for c in checksum):
            raise ValueError("Invalid pinned archive checksum")
        print(fetch(lock, args.cache.resolve() / checksum[:12], args.archive.resolve() if args.archive else None))
        return 0
    except (OSError, ValueError, tarfile.TarError) as error:
        print(f"fetch_upstream: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
