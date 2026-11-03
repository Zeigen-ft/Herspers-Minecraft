#!/usr/bin/env python3
"""Package the shared Qt launcher beside a verified Herspers Java installation.

Run on the actual target OS/architecture. No game assets, account tokens, or
original Horizon launcher are included. Repeated runs use a new output folder.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from herps_launcher import __version__
from herps_launcher.core import Installation, target


def run(args, **kwargs):
    subprocess.run(list(map(str, args)), check=True, **kwargs)


def smoke(executable: Path, output: Path):
    report_path = output / "launcher-smoke.json"
    result = subprocess.run([str(executable), "--smoke-test", "--require-installation", "--smoke-report", str(report_path)],
                            env={**os.environ, "QT_QPA_PLATFORM": "offscreen"}, cwd=output, timeout=120)
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.is_file() else {}
    if result.returncode or report.get("status") != "passed" or report.get("pages_opened") != 5:
        raise ValueError(f"Packaged launcher smoke test failed: {report.get('error', 'no successful smoke report')}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", type=Path, required=True, help="Verified packaged Herspers-Minecraft folder or .app")
    parser.add_argument("--source", type=Path, help="Optional checksum-prepared engine source for native mods")
    parser.add_argument("--output", type=Path, default=ROOT / "dist/herps")
    args = parser.parse_args()
    host_target = target()
    installation = Installation.inspect(args.game)
    args.output.mkdir(parents=True, exist_ok=True)
    output = Path(tempfile.mkdtemp(prefix=f"herps-{__version__}-{host_target}-", dir=args.output.resolve()))
    # PyInstaller work/spec artifacts stay in ignored cache, never tracked source.
    cache = ROOT / ".cache/herps-package"
    cache.mkdir(parents=True, exist_ok=True)
    build = Path(tempfile.mkdtemp(prefix="build-", dir=cache))
    helper = build / ("herps-host.exe" if platform.system() == "Windows" else "herps-host")
    rust_args = ["rustc", "+1.95.0", "--edition=2021", "--target", host_target, "-O", ROOT / "packaging/herps_host.rs", "-o", helper]
    if platform.system() == "Windows":
        rust_args += ["-C", "target-feature=+crt-static"]
    run(rust_args, cwd=ROOT)
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--onedir",
        "--name", "Herps Launcher", "--paths", ROOT, "--distpath", output, "--workpath", build / "work", "--specpath", build,
        "--add-binary", f"{helper}{os.pathsep}.", "--hidden-import", "PySide6.QtTest",
        "--copy-metadata", "PySide6-Essentials", "--copy-metadata", "shiboken6"]
    if platform.system() == "Darwin":
        command += ["--osx-bundle-identifier", "io.herspers.herps-launcher", "--target-architecture", "arm64" if host_target.startswith("aarch64") else "x86_64"]
        if os.environ.get("HERPS_CODESIGN_IDENTITY"):
            command += ["--codesign-identity", os.environ["HERPS_CODESIGN_IDENTITY"], "--osx-entitlements-file", ROOT / "packaging/herps-entitlements.plist"]
    command += [ROOT / "packaging/herps_entry.py"]
    run(command, cwd=ROOT)
    if platform.system() == "Darwin":
        app = output / "Herps Launcher.app"
        game_destination = output / "Herspers Minecraft.app"
        shutil.copytree(installation.root, game_destination, symlinks=True)
        identity = os.environ.get("HERPS_CODESIGN_IDENTITY")
        if identity:
            metadata_path = game_destination / "Contents/Resources/build-metadata.json"
            metadata = json.loads(metadata_path.read_text())
            from herps_launcher.core import digest
            for binary in (game_destination / "Contents/MacOS").iterdir():
                if binary.is_file():
                    run(["codesign", "--force", "--options", "runtime", "--timestamp", "--sign", identity, binary])
            metadata["binaries_sha256"] = {name: digest(game_destination / "Contents/MacOS" / name)
                                            for name in metadata["binaries_sha256"]}
            metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")
            run(["codesign", "--force", "--options", "runtime", "--timestamp", "--sign", identity, game_destination])
            run(["codesign", "--verify", "--deep", "--strict", game_destination])
        # Keep the already-signed game bundle a sibling, preserving its binary checksums.
        executable = app / "Contents/MacOS/Herps Launcher"
        smoke(executable, output)
        # PyInstaller also emits an unpackaged onedir tree; the .app is the delivery.
        shutil.rmtree(output / "Herps Launcher")
    else:
        folder = output / "Herps Launcher"
        shutil.copytree(installation.root, folder / "game/Herspers-Minecraft")
        executable = folder / "Herps Launcher.exe"
        smoke(executable, output)
    if args.source:
        stamp = json.loads((args.source / ".herspers-prepared.json").read_text())
        from herps_launcher.core import REVISION
        if stamp.get("upstream", {}).get("commit") != REVISION:
            raise ValueError("Prepared source does not match this launcher")
        # copy2 preserves source executable bits used by the preparation digest.
        destination = output / "engine-source" if platform.system() == "Darwin" else output / "Herps Launcher/engine-source"
        shutil.copytree(args.source, destination)
    shutil.copy2(ROOT / "LICENSE", output / "LICENSE-HERPS.txt")
    shutil.copy2(ROOT / "docs/HERPS-LAUNCHER.md", output / "START-HERE.txt")
    for name in ("Horizon-LICENSE.txt", "Horizon-THIRD_PARTY_NOTICES.md"):
        source = ROOT / "licenses" / name
        if source.is_file():
            shutil.copy2(source, output / name)
    (output / "package.json").write_text(json.dumps({"launcher_version": __version__, "target": host_target,
        "native_ui_smoke_passed": True, "gameplay_verified": False, "notarized": False}, indent=2) + "\n")
    archive_name = args.output.resolve() / f"Herps-Launcher-{__version__}-{host_target}-{output.name[-8:]}"
    if platform.system() == "Darwin":
        # Users with configured Developer ID credentials can sign and notarize before distribution.
        run(["hdiutil", "create", "-volname", "Herps Launcher", "-srcfolder", output, "-format", "UDZO", str(archive_name) + ".dmg"])
        profile = os.environ.get("HERPS_NOTARY_PROFILE")
        if profile:
            if not os.environ.get("HERPS_CODESIGN_IDENTITY"):
                raise ValueError("Notarization requires HERPS_CODESIGN_IDENTITY and a configured notarytool keychain profile")
            run(["xcrun", "notarytool", "submit", str(archive_name) + ".dmg", "--keychain-profile", profile, "--wait"])
            run(["xcrun", "stapler", "staple", str(archive_name) + ".dmg"])
    else:
        shutil.make_archive(str(archive_name), "zip", root_dir=output)
    print(f"Herps Launcher package: {archive_name}")


if __name__ == "__main__":
    main()
