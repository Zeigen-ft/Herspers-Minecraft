"""Packaging gates with owned passive binary fixtures; no native build claims."""
import importlib.util
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch


PROJECT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("package_herps", PROJECT / "tools/package_herps.py")
package = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(package)


def passive_pe(machine=0x8664):
    """A non-executable PE header fixture understood by the existing inspector."""
    data = bytearray(1024)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, 128)
    data[128:132] = b"PE\0\0"
    struct.pack_into("<HHIIIHH", data, 132, machine, 1, 0, 0, 0, 240, 2)
    struct.pack_into("<H", data, 152, 0x20B)
    struct.pack_into("<I", data, 152 + 60, 512)
    struct.pack_into("<QQ", data, 152 + 72, 16 * 1024 * 1024, 4096)
    struct.pack_into("<IIII", data, 152 + 240 + 8, 512, 4096, 512, 512)
    return bytes(data)


class PackagingSmokeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="herps-package-smoke-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.output = self.root / "output"
        self.output.mkdir()
        self.executable = self.output / "Herps Launcher/Herps Launcher.exe"
        self.binary = self.executable.parent / "_internal/horizon-port-pack.exe"
        self.binary.parent.mkdir(parents=True)
        self.binary.write_bytes(b"owned passive packaged helper fixture")
        self.binary.chmod(0o755)
        self.report = {"status": "passed", "pages_opened": 7, "port_pack": {
            "status": "passed", "bundled": True, "path": str(self.binary),
            "sha256": package.digest(self.binary), "adapter_status": "Requires porting",
            "original_verdict": "works", "test_execution": None}}

    def run_smoke(self, code=0):
        def child(args, **kwargs):
            self.assertIn("--require-port-pack", args)
            self.assertIn("--require-installation", args)
            (self.output / "launcher-smoke.json").write_text(json.dumps(self.report))
            return subprocess.CompletedProcess(args, code)
        with patch.object(package.subprocess, "run", side_effect=child):
            return package.smoke(self.executable, self.output)

    def test_seven_page_report_requires_real_bundled_hash_and_passive_fixture(self):
        result = self.run_smoke()
        self.assertEqual(result, self.report)
        self.assertIsNone(result["port_pack"]["test_execution"])

    def test_obsolete_five_page_report_is_rejected(self):
        self.report["pages_opened"] = 5
        with self.assertRaisesRegex(ValueError, "smoke test failed"):
            self.run_smoke()

    def test_failed_exit_or_failed_status_cannot_use_successful_page_count(self):
        with self.assertRaises(ValueError):
            self.run_smoke(1)
        self.report["status"] = "failed"
        with self.assertRaises(ValueError):
            self.run_smoke()

    def test_stale_report_is_removed_before_process_invocation(self):
        report_path = self.output / "launcher-smoke.json"
        report_path.write_text(json.dumps(self.report))
        with patch.object(package.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)):
            with self.assertRaisesRegex(ValueError, "no successful smoke report"):
                package.smoke(self.executable, self.output)
        self.assertFalse(report_path.exists())

    def test_missing_backend_evidence_or_external_fallback_is_rejected(self):
        for backend in ({}, {**self.report["port_pack"], "bundled": False},
                        {**self.report["port_pack"], "test_execution": {"success": True}}):
            with self.subTest(backend=backend):
                self.report["port_pack"] = backend
                with self.assertRaises(ValueError):
                    self.run_smoke()

    def test_missing_or_changed_bundled_helper_is_rejected(self):
        self.binary.write_bytes(b"changed fixture")
        with self.assertRaisesRegex(ValueError, "path/hash"):
            self.run_smoke()
        self.binary.unlink()
        with self.assertRaisesRegex(ValueError, "path/hash"):
            self.run_smoke()

    def test_backend_outside_launcher_cannot_pass_with_matching_hash(self):
        outside = self.root / "horizon-port-pack.exe"
        outside.write_bytes(self.binary.read_bytes())
        outside.chmod(0o755)
        self.report["port_pack"]["path"] = str(outside)
        with self.assertRaisesRegex(ValueError, "path/hash"):
            self.run_smoke()

    def test_macos_frameworks_helper_is_validated_inside_app_with_spaces(self):
        self.executable = self.output / "Herps Launcher.app/Contents/MacOS/Herps Launcher"
        self.binary = self.output / "Herps Launcher.app/Contents/Frameworks/horizon-port-pack"
        self.binary.parent.mkdir(parents=True)
        self.binary.write_bytes(b"owned mac passive fixture")
        self.binary.chmod(0o755)
        self.report["port_pack"].update(path=str(self.binary), sha256=package.digest(self.binary))
        self.assertEqual(self.run_smoke()["port_pack"]["path"], str(self.binary))


class PortPackBuildTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="herps-package-build-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.project = self.root / "project"
        self.source = self.root / "prepared source"
        self.source.mkdir()
        self.stamp = {"upstream": {"commit": package.REVISION, "rust_toolchain": package.RUST}}
        self.write_stamp()
        root_patch = patch.object(package, "ROOT", self.project)
        root_patch.start()
        self.addCleanup(root_patch.stop)

    def write_stamp(self):
        (self.source / ".herspers-prepared.json").write_text(json.dumps(self.stamp))

    def build(self, target, create=True, wrong_arch=False):
        def cargo(args, **kwargs):
            self.command, self.build_kwargs = args, kwargs
            cache = Path(args[args.index("--target-dir") + 1])
            name = "horizon-port-pack.exe" if target.endswith("windows-msvc") else "horizon-port-pack"
            binary = cache / target / "release" / name
            if create:
                binary.parent.mkdir(parents=True)
                if name.endswith(".exe"):
                    binary.write_bytes(passive_pe(machine=0xAA64 if wrong_arch else 0x8664))
                else:
                    cpu = 0x0100000C if target.startswith("aarch64") else 0x01000007
                    binary.write_bytes(struct.pack("<8I", 0xFEEDFACF, cpu, 0, 2, 0, 0, 0, 0))
                binary.chmod(0o755)
        preparation = subprocess.CompletedProcess([], 0, str(self.source) + "\n", "")
        with patch.object(package.subprocess, "run", return_value=preparation) as prepare, \
                patch.object(package, "run", side_effect=cargo), \
                patch("tools.package_macos.verify_macos_binary") as native_macos_check:
            result = package.build_port_pack(target)
        self.prepare_args = prepare.call_args
        self.macos_check = native_macos_check.call_args
        return result

    def test_windows_build_is_locked_pinned_native_static_and_outside_prepared_tree(self):
        with patch.dict(os.environ, {"RUSTFLAGS": "-C debuginfo=0"}):
            binary, evidence = self.build("x86_64-pc-windows-msvc")
        self.assertEqual(binary.name, "horizon-port-pack.exe")
        self.assertEqual(evidence["binary_validation"]["architecture"], "x86_64")
        self.assertEqual(evidence["build_sha256"], package.digest(binary))
        self.assertEqual(self.command[:4], ["cargo", "+1.95.0", "build", "--locked"])
        self.assertIn("--release", self.command)
        self.assertEqual(self.command[self.command.index("--manifest-path") + 1], self.source.resolve() / "Cargo.toml")
        cache = self.command[self.command.index("--target-dir") + 1]
        self.assertFalse(cache.is_relative_to(self.source.resolve()))
        self.assertEqual(cache, (self.project / ".cache/port-pack-target").resolve())
        self.assertIn("-C debuginfo=0", self.build_kwargs["env"]["RUSTFLAGS"])
        self.assertIn("target-feature=+crt-static", self.build_kwargs["env"]["RUSTFLAGS"])
        self.assertTrue(self.prepare_args.kwargs["check"])
        self.assertEqual(Path(self.prepare_args.args[0][1]), self.project / "tools/prepare_upstream.py")

    def test_macos_both_architectures_use_native_validation_and_executable_bits(self):
        for target, arch in (("aarch64-apple-darwin", "arm64"), ("x86_64-apple-darwin", "x86_64")):
            with self.subTest(target=target):
                binary, evidence = self.build(target)
                self.assertEqual(binary.name, "horizon-port-pack")
                self.assertEqual(evidence["binary_validation"]["architecture"], arch)
                self.assertEqual(self.macos_check.args, (binary, arch))
                self.assertTrue(os.access(binary, os.X_OK))

    def test_missing_cargo_artifact_fails_instead_of_producing_backendless_package(self):
        with self.assertRaisesRegex(ValueError, "missing or linked"):
            self.build("x86_64-pc-windows-msvc", create=False)

    def test_wrong_architecture_artifact_is_rejected_without_execution(self):
        with self.assertRaisesRegex(ValueError, "x86_64"):
            self.build("x86_64-pc-windows-msvc", wrong_arch=True)

    def test_wrong_source_revision_or_toolchain_fails_before_cargo(self):
        for field, value in (("commit", "0" * 40), ("rust_toolchain", "1.0.0")):
            with self.subTest(field=field):
                original = self.stamp["upstream"][field]
                self.stamp["upstream"][field] = value
                self.write_stamp()
                with self.assertRaisesRegex(ValueError, "pinned"):
                    self.build("x86_64-pc-windows-msvc")
                self.stamp["upstream"][field] = original

    def test_unsupported_target_is_refused_before_preparing_or_building(self):
        with patch.object(package.subprocess, "run") as prepare:
            with self.assertRaisesRegex(ValueError, "supported Windows/macOS"):
                package.build_port_pack("x86_64-unknown-linux-gnu")
        prepare.assert_not_called()

    def test_preparation_failure_surfaces_original_diagnostic_before_cargo(self):
        error = subprocess.CalledProcessError(1, ["prepare"], output="owned stdout", stderr="owned source checksum mismatch")
        with patch.object(package.subprocess, "run", side_effect=error) as command:
            with self.assertRaisesRegex(ValueError, "owned source checksum mismatch"):
                package.build_port_pack("x86_64-pc-windows-msvc")
        self.assertEqual(command.call_count, 1)


class PyInstallerInputsTests(unittest.TestCase):
    def test_backend_and_both_feature_packages_are_explicit_for_all_targets(self):
        for target in ("x86_64-pc-windows-msvc", "aarch64-apple-darwin", "x86_64-apple-darwin"):
            with self.subTest(target=target):
                name = "horizon-port-pack.exe" if target.endswith("windows-msvc") else "horizon-port-pack"
                binary = Path("/owned cache/target") / target / name
                command = package.pyinstaller_command(Path("/output"), Path("/build"), Path("/herps-host"), binary, target)
                binaries = [command[i + 1] for i, arg in enumerate(command) if arg == "--add-binary"]
                self.assertIn(f"{binary}{os.pathsep}.", binaries)
                packages = [command[i + 1] for i, arg in enumerate(command) if arg == "--collect-submodules"]
                self.assertEqual(packages, ["herps_launcher.javamods", "herps_launcher.modpacks"])
                data = [str(command[i + 1]) for i, arg in enumerate(command) if arg == "--add-data"]
                self.assertFalse(any(name in item for item in data for name in ("horizon-port-pack", "herps-host")))
                self.assertEqual(len(data), 5)
                self.assertEqual(sum(item.endswith("phase5c-tests") for item in data), 4)
                self.assertTrue(any("herspers_rl_chainmail-0.1.0.hmod" in item and item.endswith("targeted-content") for item in data))
                if target.endswith("apple-darwin"):
                    expected = "arm64" if target.startswith("aarch64") else "x86_64"
                    self.assertEqual(command[command.index("--target-architecture") + 1], expected)


if __name__ == "__main__":
    unittest.main()
