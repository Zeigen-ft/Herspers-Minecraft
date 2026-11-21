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
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from herps_launcher import __version__
from herps_launcher.core import Installation, REVISION, RUST, digest, target


def run(args, **kwargs):
    subprocess.run(list(map(str, args)), check=True, **kwargs)


def smoke(executable: Path, output: Path):
    report_path = output / "launcher-smoke.json"
    # A failed/new invocation must never inherit a successful report from an old run.
    report_path.unlink(missing_ok=True)
    result = subprocess.run([str(executable), "--smoke-test", "--require-installation", "--require-port-pack", "--smoke-report", str(report_path)],
                            env={**os.environ, "QT_QPA_PLATFORM": "offscreen"}, cwd=output, timeout=120)
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.is_file() else {}
    if result.returncode or report.get("status") != "passed" or report.get("pages_opened") != 7:
        raise ValueError(f"Packaged launcher smoke test failed: {report.get('error', 'no successful smoke report')}")
    backend = report.get("port_pack", {})
    if (not isinstance(backend, dict) or backend.get("status") != "passed" or backend.get("bundled") is not True
            or backend.get("adapter_status") != "Requires porting" or backend.get("original_verdict") != "works"
            or "test_execution" not in backend or backend["test_execution"] is not None
            or not isinstance(backend.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", backend["sha256"])
            or not isinstance(backend.get("path"), str)):
        raise ValueError("Packaged launcher smoke test did not verify the bundled port-pack backend")
    binary = Path(backend["path"]).resolve()
    bundle = executable.parents[2] if executable.parent.name == "MacOS" and executable.parent.parent.name == "Contents" else executable.parent
    expected = "horizon-port-pack.exe" if executable.suffix.lower() == ".exe" else "horizon-port-pack"
    if (not binary.is_relative_to(bundle.resolve()) or binary.name != expected or not binary.is_file()
            or not os.access(binary, os.X_OK) or digest(binary) != backend["sha256"]):
        raise ValueError("Packaged launcher smoke test backend path/hash is outside or differs from the bundle")
    return report


def build_port_pack(host_target: str) -> tuple[Path, dict]:
    """Build the locked passive backend on its native packaging runner.

    Cargo is a build-time requirement only. The output cache is outside the
    checksum-prepared source, which must remain immutable for native rebuilds.
    """
    if host_target not in ("x86_64-pc-windows-msvc", "aarch64-apple-darwin", "x86_64-apple-darwin"):
        raise ValueError("port-pack packaging requires a supported Windows/macOS target")
    try:
        prepared = subprocess.run([sys.executable, str(ROOT / "tools/prepare_upstream.py")],
                                  cwd=ROOT, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as error:
        raise ValueError(f"Pinned engine preparation failed ({error.returncode}):\n"
                         f"{error.stdout or ''}\n{error.stderr or ''}") from error
    source = Path(prepared.stdout.strip()).resolve()
    stamp = json.loads((source / ".herspers-prepared.json").read_text(encoding="utf-8"))
    if stamp.get("upstream", {}).get("commit") != REVISION or stamp["upstream"].get("rust_toolchain") != RUST:
        raise ValueError("Prepared port-pack source does not match the pinned launcher engine/toolchain")
    cache = (ROOT / ".cache/port-pack-target").resolve()
    if cache.is_relative_to(source):
        raise ValueError("port-pack target cache must be outside the checksum-prepared source")
    env = dict(os.environ)
    if host_target.endswith("windows-msvc"):
        env["RUSTFLAGS"] = env.get("RUSTFLAGS", "") + " -C target-feature=+crt-static"
    run(["cargo", f"+{RUST}", "build", "--locked", "--release", "--manifest-path", source / "Cargo.toml",
         "--target", host_target, "--target-dir", cache, "-p", "horizon-port-pack", "--bin", "horizon-port-pack"],
        cwd=ROOT, env=env)
    binary = cache / host_target / "release" / ("horizon-port-pack.exe" if host_target.endswith("windows-msvc") else "horizon-port-pack")
    if binary.is_symlink() or not binary.is_file():
        raise ValueError(f"Built port-pack executable is missing or linked: {binary}")
    # Reuse the game packagers' passive architecture/dependency inspections.
    if host_target.endswith("windows-msvc"):
        from tools.package_windows import verify_binary
        verified = verify_binary(binary)
    else:
        from tools.package_macos import binary_architecture, verify_macos_binary
        arch = "arm64" if host_target.startswith("aarch64") else "x86_64"
        binary_architecture(binary, arch)
        verify_macos_binary(binary, arch)
        verified = {"architecture": arch, "sha256": digest(binary)}
    return binary, {"source_revision": REVISION, "rust_toolchain": RUST, "target": host_target,
                    "build_sha256": digest(binary), "binary_validation": verified}


def pyinstaller_command(output: Path, build: Path, helper: Path, port_pack: Path, host_target: str) -> list:
    from tools.build_rlcraft_chainmail import build as build_chainmail
    from herps_launcher.modpacks.chainmail import PACKAGE_NAME
    content = ROOT / ".cache/targeted-content"
    build_chainmail(content)
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--onedir",
        "--name", "Herps Launcher", "--paths", ROOT, "--distpath", output, "--workpath", build / "work", "--specpath", build,
        "--add-binary", f"{helper}{os.pathsep}.", "--add-binary", f"{port_pack}{os.pathsep}.",
        "--collect-submodules", "herps_launcher.javamods", "--collect-submodules", "herps_launcher.modpacks",
        "--add-data", f"{content / PACKAGE_NAME}{os.pathsep}targeted-content",
        "--hidden-import", "PySide6.QtTest", "--copy-metadata", "PySide6-Essentials", "--copy-metadata", "shiboken6"]
    # Opt-in delivered workflow verification on every supported target.
    command += ["--paths", ROOT / "packaging", "--hidden-import", "phase5c_acceptance",
                "--hidden-import", "herps_entry", "--hidden-import", "unittest.mock",
                "--hidden-import", "tools.make_javamods_fixtures",
                "--hidden-import", "tools.make_modpack_fixtures"]
    for name in ("test_javamods_ui.py", "test_modpacks_ui.py",
                 "test_javamods_library.py", "test_modpacks_service.py"):
        command += ["--add-data", f"{ROOT / 'tests' / name}{os.pathsep}phase5c-tests"]
    if host_target.endswith("apple-darwin"):
        command += ["--osx-bundle-identifier", "io.herspers.herps-launcher", "--target-architecture", "arm64" if host_target.startswith("aarch64") else "x86_64"]
        if os.environ.get("HERPS_CODESIGN_IDENTITY"):
            command += ["--codesign-identity", os.environ["HERPS_CODESIGN_IDENTITY"], "--osx-entitlements-file", ROOT / "packaging/herps-entitlements.plist"]
    return command + [ROOT / "packaging/herps_entry.py"]


def notarize_dmg(image: Path):
    """Record results beside the final DMG; never mutate submitted contents."""
    receipt = {"status": "not_requested", "notarized": False}
    profile = os.environ.get("HERPS_NOTARY_PROFILE")
    try:
        if profile:
            receipt["status"] = "failed"
            if not os.environ.get("HERPS_CODESIGN_IDENTITY"):
                raise ValueError("Notarization requires a signing identity and configured keychain profile")
            receipt["status"] = "failed"
            run(["xcrun", "notarytool", "submit", image, "--keychain-profile", profile, "--wait"])
            run(["xcrun", "stapler", "staple", image])
            run(["xcrun", "stapler", "validate", image])
            receipt.update(status="verified", notarized=True)
    finally:
        receipt["dmg_sha256"] = digest(image)
        image.with_suffix(".notarization.json").write_text(json.dumps(receipt, indent=2) + "\n")


def copy_documentation(output: Path):
    """Keep relative links valid in the delivered offline documentation."""
    shutil.copytree(ROOT / "docs", output / "docs")
    shutil.copytree(ROOT / "licenses", output / "licenses")
    shutil.copy2(ROOT / "README.md", output / "README.md")
    shutil.copy2(ROOT / "LICENSE", output / "LICENSE")
    shutil.copy2(ROOT / "LICENSE", output / "LICENSE-HERPS.txt")
    for source, destination in (("HERPS-LAUNCHER.md", "START-HERE.txt"),
                                ("herps/java-mods.md", "JAVA-MODS.txt"),
                                ("HERPS-SUPPORT.md", "SUPPORT.md")):
        (output / destination).write_text(
            f"Herps Launcher candidate documentation: docs/{source}\n"
            "Internal verification build; not a stable public release.\n", encoding="utf-8")
    for name in ("Horizon-LICENSE.txt", "Horizon-THIRD_PARTY_NOTICES.md"):
        shutil.copy2(ROOT / "licenses" / name, output / name)


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
    port_pack, backend_build = build_port_pack(host_target)
    command = pyinstaller_command(output, build, helper, port_pack, host_target)
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
        smoke_report = smoke(executable, output)
        # PyInstaller also emits an unpackaged onedir tree; the .app is the delivery.
        shutil.rmtree(output / "Herps Launcher")
    else:
        folder = output / "Herps Launcher"
        shutil.copytree(installation.root, folder / "game/Herspers-Minecraft")
        executable = folder / "Herps Launcher.exe"
        smoke_report = smoke(executable, output)
    if args.source:
        stamp = json.loads((args.source / ".herspers-prepared.json").read_text())
        from herps_launcher.core import REVISION
        if stamp.get("upstream", {}).get("commit") != REVISION:
            raise ValueError("Prepared source does not match this launcher")
        # copy2 preserves source executable bits used by the preparation digest.
        destination = output / "engine-source" if platform.system() == "Darwin" else output / "Herps Launcher/engine-source"
        shutil.copytree(args.source, destination)
    copy_documentation(output)
    (output / "package.json").write_text(json.dumps({"launcher_version": __version__, "target": host_target,
        "port_pack": {**backend_build, "bundled_sha256": smoke_report["port_pack"]["sha256"],
                      "path": str(Path(smoke_report["port_pack"]["path"]).relative_to(output.resolve())),
                      "passive_fixture_smoke_passed": True},
        "native_ui_smoke_passed": True, "gameplay_verified": False,
        "notarized": None if os.environ.get("HERPS_NOTARY_PROFILE") else False,
        "notarization": {"status": "external_receipt" if os.environ.get("HERPS_NOTARY_PROFILE") else "not_requested", "result_receipt": "external sidecar after final DMG verification"}}, indent=2) + "\n")
    from tools.release_evidence import collect_dependencies
    collect_dependencies(output)
    archive_name = args.output.resolve() / f"Herps-Launcher-{__version__}-{host_target}-{output.name[-8:]}"
    if platform.system() == "Darwin":
        # Users with configured Developer ID credentials can sign and notarize before distribution.
        run(["hdiutil", "create", "-volname", "Herps Launcher", "-srcfolder", output, "-format", "UDZO", str(archive_name) + ".dmg"])
        notarize_dmg(Path(str(archive_name) + ".dmg"))
    else:
        shutil.make_archive(str(archive_name), "zip", root_dir=output)
    print(f"Herps Launcher package: {archive_name}")


if __name__ == "__main__":
    main()
