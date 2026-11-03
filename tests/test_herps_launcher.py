"""Launcher integration tests run with owned fixtures, no Minecraft assets/accounts."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch
import zipfile

from herps_launcher.core import (Launcher, Installation, REVISION, archive, build_native,
    digest, find_cargo, inspect_mod, json_write, pairs, server_address, stage_native_mod, stage_native_source, support_dir, target, update_pairs)


def pack(path, files):
    with zipfile.ZipFile(path, "w") as z:
        for name, data in files.items():
            info = zipfile.ZipInfo(name)
            # Keep deliberately unsafe names raw: Windows ZipInfo construction
            # otherwise normalizes backslashes before the fixture is written.
            info.filename = name
            z.writestr(info, data)
    return path


def runtime(path, id="demo"):
    return pack(path, {"horizon-mod.toml": f'id="{id}"\nname="Demo"\nversion="1"\napi="0.1"\n', "mod.wasm": b"\0asm\x0d\0\x01\0"})


def native(path, revision=REVISION):
    return pack(path, {"horizon-native.json": json.dumps({"schema": 1, "id": "native_demo", "version": "1", "game": "26.3", "horizon": revision, "mixins": "b" * 40}),
                       "mixins/native_demo/horizon-mixin.toml": f'[mod]\nid="native_demo"\nversion="1"\n[compatibility]\nhorizon_revision="{revision}"\n',
                       "mixins/native_demo/hook.rs": "// owned test source\n"})


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.launcher = Launcher(self.root / "support")

    def test_platform_paths_and_targets(self):
        self.assertEqual(support_dir("Windows", self.root, {"LOCALAPPDATA": "C:/Local"}), Path("C:/Local/Herspers Minecraft"))
        self.assertEqual(support_dir("Darwin", self.root), self.root / "Library/Application Support/Herspers Minecraft")
        with self.assertRaises(ValueError):
            support_dir("Windows", self.root, {})
        self.assertEqual(target("Darwin", "arm64"), "aarch64-apple-darwin")
        self.assertEqual(target("Darwin", "x86_64"), "x86_64-apple-darwin")
        self.assertEqual(target("Windows", "AMD64"), "x86_64-pc-windows-msvc")
        with self.assertRaises(ValueError):
            target("Windows", "arm64")

    def test_mod_import_is_disabled_until_reviewed_and_preserves_unknown_keys(self):
        self.launcher.game.mkdir(parents=True)
        settings = self.launcher.game / "horizon-mods.txt"
        settings.write_text("key.old.toggle:R\nmod.old:true\n")
        self.launcher.install_mod(runtime(self.root / "example.hmod"))
        mod = self.launcher.mods()[0]
        self.assertFalse(self.launcher.enabled(mod))
        self.launcher.set_enabled(mod, True)
        self.assertTrue(self.launcher.enabled(mod))
        self.assertEqual(pairs(settings)["key.old.toggle"], "R")
        self.assertEqual(pairs(settings)["mod.old"], "true")
        with self.assertRaises(ValueError):
            self.launcher.install_mod(runtime(self.root / "duplicate.hmod"))
        self.launcher.remove_mod(mod)
        self.assertFalse(mod.path.exists())
        self.assertEqual(len(list((self.launcher.state / "removed").glob("*.hmod"))), 1)

    def test_native_exact_revision_and_manifest_identity(self):
        self.assertTrue(inspect_mod(native(self.root / "valid.hnmod")).native)
        with self.assertRaises(ValueError):
            inspect_mod(native(self.root / "wrong.hnmod", "c" * 40))
        with self.assertRaises(ValueError):
            build_native(self.launcher, self.root, trusted=False)

    def test_native_build_discovers_user_rustup_without_shell_path(self):
        binary = "cargo.exe" if os.name == "nt" else "cargo"
        cargo = self.root / ".cargo/bin" / binary
        cargo.parent.mkdir(parents=True)
        cargo.write_bytes(b"owned tool fixture")
        cargo.chmod(0o755)
        self.assertEqual(find_cargo({"PATH": ""}, self.root), cargo.absolute())
        custom = self.root / "custom-cargo/bin" / binary
        custom.parent.mkdir(parents=True)
        custom.write_bytes(b"custom tool fixture")
        custom.chmod(0o755)
        self.assertEqual(find_cargo({"PATH": "", "CARGO_HOME": str(custom.parent.parent)}, self.root), custom.absolute())

    def test_mixin_source_copy_has_exact_revision_and_preserves_cache(self):
        source, work = self.root / "prepared", self.root / "work"
        source.mkdir()
        work.mkdir()
        stamp = source / ".herspers-prepared.json"
        stamp.write_bytes(b'{"original":"stamp"}')
        (source / "Cargo.lock").write_bytes(b"owned locked source")
        result = stage_native_source(source, work)
        self.assertEqual((result / ".horizon-revision").read_text(), REVISION)
        self.assertFalse((source / ".horizon-revision").exists())
        self.assertEqual((result / "Cargo.lock").read_bytes(), b"owned locked source")
        self.assertEqual(stamp.read_bytes(), b'{"original":"stamp"}')

    def test_native_bundle_stages_manifest_at_cli_mod_root(self):
        path = native(self.root / "staged.hnmod")
        files = archive(path)
        files["mixins/native_demo/engine/data/salt.txt"] = b"owned nested data"
        pack(path, files)
        before = path.read_bytes()
        destination = stage_native_mod(inspect_mod(path), self.root / "incoming")
        self.assertEqual(destination, self.root / "incoming/native_demo")
        self.assertTrue((destination / "horizon-mixin.toml").is_file())
        self.assertTrue((destination / "hook.rs").is_file())
        self.assertEqual((destination / "engine/data/salt.txt").read_bytes(), b"owned nested data")
        self.assertFalse((destination / "mixins").exists())
        self.assertFalse((destination / "horizon-native.json").exists())
        self.assertEqual(path.read_bytes(), before)

    def test_native_staging_refuses_wrong_namespace_before_writing(self):
        path = native(self.root / "valid-namespace.hnmod")
        mod = inspect_mod(path)
        files = archive(path)
        files["mixins/other/evil.rs"] = b"// outside the reviewed namespace"
        mod.path = pack(self.root / "changed.hnmod", files)
        incoming = self.root / "incoming"
        with self.assertRaisesRegex(ValueError, "namespace"):
            stage_native_mod(mod, incoming)
        self.assertFalse(incoming.exists())

    def test_archive_rejects_traversal_duplicates_and_expansion(self):
        for name in ("../evil", "/evil", "C:/evil", "a\\evil", "a/./evil", "a\0evil"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                archive(pack(self.root / "bad.zip", {name: "x"}))
        with self.assertRaises(ValueError):
            archive(pack(self.root / "big.zip", {"file": "abc"}), limit=2)
        with self.assertRaises(ValueError):
            archive(pack(self.root / "case.zip", {"File": "a", "file": "b"}))

    def test_invalid_runtime_and_api_are_refused(self):
        for manifest in ('id="../escape"\nname="X"\nversion="1"\napi="0.1"',
                         'id="x"\nname="X"\nversion="1"\napi="0.9"'):
            with self.assertRaises(ValueError):
                inspect_mod(pack(self.root / "bad.hmod", {"horizon-mod.toml": manifest, "mod.wasm": b"\0asm"}))

    def test_profiles_do_not_move_or_delete_saves(self):
        world = self.launcher.game / "saves/Existing/level.dat"
        world.parent.mkdir(parents=True)
        world.write_bytes(b"owned world fixture")
        original = self.launcher.game
        self.launcher.add_profile("modded")
        self.assertNotEqual(self.launcher.game, original)
        self.assertFalse((self.launcher.game / "saves").exists())
        self.assertEqual(world.read_bytes(), b"owned world fixture")
        for name in ("../escape", "default", "UPPER"):
            with self.assertRaises(ValueError):
                self.launcher.add_profile(name)

    def test_shader_selection_uses_actual_upstream_key_and_can_reset(self):
        shader = pack(self.root / "pack.zip", {"shaders/final.fsh": "// owned shader fixture"})
        self.launcher.install_shader(shader)
        graphics = self.launcher.game / "horizon-graphics.txt"
        update_pairs(graphics, {"unknownFutureOption": "42"})
        self.launcher.select_shader("pack.zip")
        self.assertEqual(pairs(graphics)["pickedShaderPack"], "pack.zip")
        self.assertEqual(pairs(graphics)["unknownFutureOption"], "42")
        self.launcher.select_shader("")
        self.assertEqual(pairs(graphics)["pickedShaderPack"], "")
        with self.assertRaises(ValueError):
            self.launcher.select_shader("../other.zip")

    def test_settings_preserve_multiplayer_resource_packs_and_create_backup(self):
        path = self.launcher.game / "options.txt"
        path.parent.mkdir(parents=True)
        original = 'lastServer:100.80.1.1:25565\nresourcePacks:["vanilla","file/test.zip"]\nrenderDistance:6\n'
        path.write_text(original)
        self.launcher.save_graphics(1920, 1080, 16, "auto")
        self.assertEqual(pairs(path)["lastServer"], "100.80.1.1:25565")
        self.assertEqual(pairs(path)["resourcePacks"], '["vanilla","file/test.zip"]')
        self.assertEqual(path.with_name(path.name + ".herps-backup").read_text(), original)

    def test_private_addresses_cannot_be_shell_options_or_public_hosts(self):
        self.assertEqual(server_address("100.80.12.34:25565"), "100.80.12.34:25565")
        for address in ("1.1.1.1:25565", "100.80.1.1:0", "--server", "100.80.1.1:70000"):
            with self.assertRaises(ValueError):
                server_address(address)

    def fixture_install(self):
        root = self.root / "Game $(literal)"
        bins = root / "bin"
        bins.mkdir(parents=True)
        json_write(root / "upstream.lock.json", {"commit": REVISION, "minecraft_version": "26.3", "minecraft_edition": "Java"})
        json_write(root / "build-metadata.json", {"stage_only": False, "architecture": "x86_64", "product_version": "0.2.3"})
        for name in ("horizon-client.exe", "horizon-prepare.exe"):
            p = bins / name
            p.write_text("#!/bin/sh\nprintf '%s\\n' \"$@\"\nexit 0\n")
            p.chmod(0o755)
        launcher = root / "Herspers-Minecraft.exe"
        launcher.write_bytes(b"owned native entrypoint fixture")
        metadata = json.loads((root / "build-metadata.json").read_text())
        metadata["binaries"] = {p.name: {"sha256": digest(p)} for p in [*bins.iterdir(), launcher]}
        json_write(root / "build-metadata.json", metadata)
        self.launcher.config["installation"] = str(root)
        return Installation.inspect(root, enforce_platform=False)

    def test_windows_root_entrypoint_is_validated_at_its_real_package_path(self):
        install = self.fixture_install()
        self.assertEqual(Installation.inspect(install.root, enforce_platform=False).root, install.root)
        (install.root / "Herspers-Minecraft.exe").write_bytes(b"changed entrypoint")
        with self.assertRaisesRegex(ValueError, "Installation binary changed: Herspers-Minecraft.exe"):
            Installation.inspect(install.root, enforce_platform=False)

    def test_inspection_rejects_bedrock_staging_and_changed_binaries(self):
        install = self.fixture_install()
        metadata = install.assets / "build-metadata.json"
        data = json.loads(metadata.read_text())
        data["binaries"] = {"horizon-client.exe": {"sha256": "0" * 64}}
        json_write(metadata, data)
        with self.assertRaises(ValueError):
            Installation.inspect(install.root, enforce_platform=False)
        data["binaries"] = {}
        data["stage_only"] = True
        json_write(metadata, data)
        with self.assertRaises(ValueError):
            Installation.inspect(install.root, enforce_platform=False)

    @unittest.skipIf(os.name == "nt", "Owned POSIX child fixture; Windows CI covers native tests separately")
    def test_play_real_child_logs_exit_and_relaunch_without_touching_saves(self):
        installation = self.fixture_install()
        world = self.launcher.game / "saves/existing/level.dat"
        world.parent.mkdir(parents=True)
        world.write_bytes(b"preserve")
        with patch.object(self.launcher, "installation", return_value=installation):
            for _ in range(2):
                self.launcher.launch()
                with self.assertRaises(ValueError):
                    self.launcher.launch()
                self.launcher.child.wait(timeout=5)
                self.assertEqual(self.launcher.poll(), 0)
                self.assertIn("--resources", Path(self.launcher.session["log"]).read_text())
        self.assertEqual(world.read_bytes(), b"preserve")
        self.assertEqual(len(json.loads((self.launcher.state / "activity.json").read_text())), 2)
        self.assertFalse(self.launcher.operation_lock.exists())

    @unittest.skipIf(os.name == "nt", "Owned POSIX process fixture")
    def test_failed_resource_check_does_not_start_game_and_releases_lock(self):
        installation = self.fixture_install()
        installation.binary("horizon-prepare").write_text("#!/bin/sh\necho missing-fixture-resources\nexit 7\n")
        with patch.object(self.launcher, "installation", return_value=installation), self.assertRaisesRegex(ValueError, "resource validation"):
            self.launcher.launch()
        self.assertIsNone(self.launcher.child)
        self.assertFalse(self.launcher.operation_lock.exists())
        self.assertIn("missing-fixture-resources", (self.launcher.state / "resources-check.log").read_text())

    @unittest.skipIf(os.name == "nt", "Owned POSIX process fixture")
    def test_clean_launch_uses_separate_game_folder_and_original_binary(self):
        installation = self.fixture_install()
        with patch.object(self.launcher, "installation", return_value=installation):
            self.launcher.launch(clean=True)
            self.launcher.child.wait(timeout=5)
            self.launcher.poll()
            log = Path(self.launcher.session["log"]).read_text()
            self.assertIn(str(self.launcher.state / "clean-game"), log)

    def test_operation_lock_excludes_second_controller(self):
        other = Launcher(self.launcher.support)
        self.launcher.acquire()
        try:
            with self.assertRaises(ValueError):
                other.acquire()
        finally:
            self.launcher.release()
        other.acquire()
        other.release()


if __name__ == "__main__":
    unittest.main()
