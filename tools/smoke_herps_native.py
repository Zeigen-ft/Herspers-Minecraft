#!/usr/bin/env python3
"""Compile an owned native mod using the real Windows launcher path; no game assets."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from herps_launcher.core import GAME, REVISION, Launcher, build_native, digest, json_write
from tools.prepare_upstream import tree_digest
from tools.package_windows import verify_binary

MIXINS = "4342a0bfbe71d4d14185528d64e496d6022f16a1"
MARKER = "HERPS_CI_NATIVE_MARKER_7301f6fd"


def owned_mod(path: Path):
    identity = "herps_ci_smoke"
    manifest = {"schema": 1, "id": identity, "version": "0.1.0", "game": GAME,
                "horizon": REVISION, "mixins": MIXINS, "hooks": 1}
    mixin = f'''[mod]
id = "{identity}"
version = "0.1.0"
[compatibility]
horizon_revision = "{REVISION}"
[[injection]]
id = "frame"
hook = "frame"
hook_version = 1
kind = "HEAD"
helper = "frame.rs"
bindings = [{{ name = "game", ty = "&mut crate::game::Game<'_>", value = "&mut *self" }}]
'''
    helper = f'''fn herps_ci_frame(game: &mut crate::game::Game<'_>) {{
    let _ = game;
    static ONCE: std::sync::Once = std::sync::Once::new();
    ONCE.call_once(|| eprintln!("{MARKER}"));
}}
'''
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("horizon-native.json", json.dumps(manifest))
        archive.writestr(f"mixins/{identity}/horizon-mixin.toml", mixin)
        archive.writestr(f"mixins/{identity}/frame.rs", helper)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--target-cache", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    if platform.system() != "Windows":
        raise ValueError("This compilation smoke check currently targets Windows x64")
    source = args.source.resolve(strict=True)
    before_source = tree_digest(source)
    scratch = ROOT / ".cache"
    scratch.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="native-smoke-", dir=scratch) as directory:
        support = Path(directory)
        launcher = Launcher(support)
        launcher.config["installation"] = str(args.game.resolve(strict=True))
        installation = launcher.installation()
        original = installation.binary("horizon-client")
        original_hash = digest(original)
        world = launcher.game / "saves/owned-sentinel/level.dat"
        world.parent.mkdir(parents=True)
        world.write_bytes(b"Herps native compilation must preserve existing worlds")
        world_hash = digest(world)
        bundle = support / "owned.hnmod"
        owned_mod(bundle)
        mod = launcher.install_mod(bundle)
        launcher.set_enabled(mod, True)
        cache = args.target_cache.resolve(strict=True)
        cache_bytes = 0
        for folder, dirs, files in os.walk(cache):
            dirs[:] = [name for name in dirs if name != "incremental"]
            cache_bytes += sum((Path(folder) / name).stat().st_size for name in files)
        free = shutil.disk_usage(support).free
        print(f"Native smoke cache copy: {cache_bytes} bytes; free disk: {free} bytes", flush=True)
        if free < cache_bytes + (2 << 30):
            raise RuntimeError("Native smoke requires room for its private target cache and 2 GiB of working space")
        # Copy rather than link: native outputs must not overwrite the clean engine cache.
        shutil.copytree(cache, launcher.state / "native/target", ignore=shutil.ignore_patterns("incremental"))
        build_native(launcher, source, trusted=True, progress=lambda line: print(line, flush=True))
        native = launcher.native_binary()
        if native is None or MARKER.encode() not in native.read_bytes():
            raise AssertionError("The compiled binary does not contain the injected owned hook")
        binary_info = verify_binary(native)
        if binary_info["stack_reserve_bytes"] < 16 << 20:
            raise AssertionError("Native Windows binary lost the 16 MiB stack setting")
        if Path(launcher.command()[0]) != native:
            raise AssertionError("Enabled mod did not select the rebuilt native binary")
        launcher.set_enabled(mod, False)
        if launcher.native_binary() is not None or Path(launcher.command()[0]) != original:
            raise AssertionError("Disabling native mods did not restore original binary selection")
        if digest(original) != original_hash or digest(world) != world_hash:
            raise AssertionError("Native rebuild changed the clean game or existing save")
        if tree_digest(source) != before_source:
            raise AssertionError("Native rebuild changed the verified source cache")
        report = {"status": "passed", "target": "x86_64-pc-windows-msvc", "revision": REVISION,
                  "mixins": MIXINS, "compiled_binary_sha256": digest(native), "injected_marker_present": True,
                  "native_selection_verified": True, "rollback_selection_verified": True,
                  "save_preserved": True, "clean_binary_preserved": True, "source_cache_preserved": True,
                  "hook_execution_verified": False, "gameplay_verified": False}
        json_write(args.report, report)
        print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
