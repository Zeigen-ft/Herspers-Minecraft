"""Portable engine integration. No UI, account handling, or proprietary downloads."""
from __future__ import annotations

import hashlib
import ipaddress
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import tomllib
import uuid
import zipfile
from dataclasses import dataclass

REVISION = "7301f6fdd7f470b11317276e7a11b4dc615c137a"
GAME = "26.3"
RUST = "1.95.0"
ID = re.compile(r"[a-z0-9_]{1,64}\Z")


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError(f"Refusing to replace a link: {path}")
    fd, name = tempfile.mkstemp(prefix=".herps-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def json_write(path: Path, data) -> None:
    atomic(path, (json.dumps(data, indent=2) + "\n").encode())


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def pairs(path: Path) -> dict[str, str]:
    return {k.strip(): v.strip() for line in (path.read_text(encoding="utf-8").splitlines() if path.exists() else [])
            if ":" in line for k, v in [line.split(":", 1)]}


def update_pairs(path: Path, updates: dict[str, str]) -> None:
    """Preserve unknown settings, key bindings, server and resource pack selections."""
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    lines = [line for line in text.splitlines() if line.split(":", 1)[0].strip() not in updates]
    lines.extend(f"{key}:{value}" for key, value in updates.items())
    if path.exists():
        backup = path.with_name(path.name + ".herps-backup")
        if not backup.exists():
            shutil.copy2(path, backup)
    atomic(path, ("\n".join(lines) + "\n").encode())


def support_dir(system=None, home=None, environ=None) -> Path:
    system, home, environ = system or platform.system(), home or Path.home(), os.environ if environ is None else environ
    if system == "Windows":
        if not environ.get("LOCALAPPDATA"):
            raise ValueError("Windows did not supply LOCALAPPDATA")
        return Path(environ["LOCALAPPDATA"]) / "Herspers Minecraft"
    if system == "Darwin":
        return home / "Library/Application Support/Herspers Minecraft"
    return home / ".local/share/Herspers Minecraft"


def target(system=None, machine=None) -> str:
    system, machine = system or platform.system(), (machine or platform.machine()).lower()
    if system == "Windows" and machine in ("amd64", "x86_64"):
        return "x86_64-pc-windows-msvc"
    if system == "Darwin" and machine in ("arm64", "aarch64", "x86_64"):
        return ("aarch64" if machine in ("arm64", "aarch64") else machine) + "-apple-darwin"
    raise ValueError("Game builds require Windows x64 or macOS ARM64/x64")


def safe_name(value: str) -> str:
    if not value or PurePosixPath(value).name != value or any(c in value for c in "\\/:\r\n\0") or value in (".", ".."):
        raise ValueError("Invalid file name")
    return value


def archive(path: Path, limit=64 << 20) -> dict[str, bytes]:
    """Read, never execute/extract, bounded regular files with portable paths."""
    files, total, seen = {}, 0, set()
    with zipfile.ZipFile(path) as zipped:
        if len(zipped.infolist()) > 20000:
            raise ValueError("Archive has too many entries")
        for info in zipped.infolist():
            # ZipInfo normalizes host separators and truncates NULs in filename.
            # Validate the original archive name before using any normalized path.
            name = info.orig_filename
            if ("\\" in name or ":" in name or name.startswith("/") or
                    any(p in (".", "..", "") for p in name.rstrip("/").split("/")) or
                    stat.S_IFMT(info.external_attr >> 16) not in (0, stat.S_IFREG, stat.S_IFDIR)):
                raise ValueError(f"Unsafe archive member: {name}")
            if info.is_dir():
                continue
            reserved = {"con", "prn", "aux", "nul", *[f"{p}{n}" for p in ("com", "lpt") for n in range(1, 10)]}
            if any(p.endswith((".", " ")) or p.split(".")[0].lower() in reserved or "\0" in p for p in name.split("/")):
                raise ValueError("Archive contains a nonportable file name")
            total += info.file_size
            if total > limit or name.casefold() in seen:
                raise ValueError("Archive is too large or has duplicate names")
            seen.add(name.casefold())
            files[name] = zipped.read(info)
    return files


@dataclass
class Mod:
    path: Path
    id: str
    name: str
    version: str
    native: bool
    metadata: dict


def inspect_mod(path: Path) -> Mod:
    native = path.suffix == ".hnmod"
    if path.suffix not in (".hmod", ".hnmod"):
        raise ValueError("Choose a Horizon .hmod or .hnmod, not a Forge/Fabric JAR")
    files = archive(path)
    key = "horizon-native.json" if native else "horizon-mod.toml"
    if key not in files:
        raise ValueError(f"Missing {key}")
    m = json.loads(files[key]) if native else tomllib.loads(files[key].decode())
    if not ID.fullmatch(m.get("id", "")) or not m.get("version"):
        raise ValueError("Mod needs a valid id and version")
    if native:
        if m.get("schema") != 1 or m.get("game") != GAME or m.get("horizon") != REVISION:
            raise ValueError("Native mod must target this exact Horizon revision and Java 26.3")
        if not re.fullmatch("[0-9a-f]{40}", m.get("mixins", "")):
            raise ValueError("Native mod must pin an exact horizon-mixins revision")
        prefix = f"mixins/{m['id']}/"
        for name in files:
            if name == key:
                continue
            if not name.startswith(prefix):
                raise ValueError("Native source is outside its mod namespace")
            rest = name[len(prefix):]
            parts = rest.split("/")
            data = parts[0] == "data" or (len(parts) > 2 and parts[1] == "data")
            text = len(parts) <= 2 and (parts[-1].startswith(("README", "LICENSE", "LICENCE", "NOTICE", "COPYING")) or parts[-1] == ".gitignore")
            if not (name.endswith((".rs", ".toml")) or data or text):
                raise ValueError(f"Unexpected native source: {name}")
        source = tomllib.loads(files[prefix + "horizon-mixin.toml"].decode())
        if (source.get("mod", {}).get("id") != m["id"] or source["mod"].get("version") != m["version"] or
                source.get("compatibility", {}).get("horizon_revision") != REVISION):
            raise ValueError("Native source and manifest identities differ")
    else:
        if m.get("api") not in ("0.1", "0.2", "0.3") or not m.get("name"):
            raise ValueError("Unsupported Horizon mod API or missing name")
        if (m.get("side", "client") == "server") != (m["api"] == "0.3"):
            raise ValueError("Server mods require API 0.3; client mods use 0.1/0.2")
        if "mod.wasm" not in files and "registries" not in m.get("capabilities", []):
            raise ValueError("Runtime mod has no mod.wasm")
        if "mod.wasm" in files and (not files["mod.wasm"].startswith(b"\0asm") or len(files["mod.wasm"]) > 32 << 20):
            raise ValueError("Invalid or oversized WebAssembly component")
    return Mod(path, m["id"], m.get("name", m["id"]), m["version"], native, m)


@dataclass
class Installation:
    root: Path
    binaries: Path
    assets: Path
    metadata: dict

    @classmethod
    def inspect(cls, root: Path, enforce_platform=True):
        root = root.expanduser().resolve(strict=True)
        mac = root.suffix == ".app"
        assets = root / "Contents/Resources" if mac else root
        bins = root / "Contents/MacOS" if mac else root / "bin"
        lock = read_json(assets / "upstream.lock.json")
        metadata = read_json(assets / "build-metadata.json")
        if lock.get("commit") != REVISION or lock.get("minecraft_version") != GAME or lock.get("minecraft_edition") != "Java":
            raise ValueError("Choose a Herspers Java 26.3 installation using the pinned Horizon source")
        if metadata.get("stage_only") is not False:
            raise ValueError("Staged placeholder packages cannot be played")
        arch = metadata.get("architecture")
        if enforce_platform:
            current = target()
            if mac != (platform.system() == "Darwin") or arch != ("arm64" if current.startswith("aarch64") else "x86_64"):
                raise ValueError("Installation platform/architecture does not match this launcher")
        for name in ("horizon-client", "horizon-prepare"):
            if not (bins / (name if mac else name + ".exe")).is_file():
                raise ValueError(f"Installation is missing {name}")
        checksums = metadata.get("binaries_sha256", {}) if mac else {
            name: entry.get("sha256") for name, entry in metadata.get("binaries", {}).items()}
        for name, expected in checksums.items():
            safe_name(name)
            binary_path = root / name if not mac and name == "Herspers-Minecraft.exe" else bins / name
            if not expected or digest(binary_path) != expected:
                raise ValueError(f"Installation binary changed: {name}. Re-extract a clean package; your saves are kept separately")
        return cls(root, bins, assets, metadata)

    def binary(self, name):
        return self.binaries / (name + (".exe" if self.root.suffix != ".app" else ""))


def tailscale() -> dict:
    binary = shutil.which("tailscale")
    if not binary and platform.system() == "Darwin":
        candidate = Path("/Applications/Tailscale.app/Contents/MacOS/Tailscale")
        binary = str(candidate) if candidate.exists() else None
    if not binary and platform.system() == "Windows":
        candidate = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Tailscale/tailscale.exe"
        binary = str(candidate) if candidate.exists() else None
    if not binary:
        return {"connected": False, "message": "Tailscale is not installed"}
    try:
        result = subprocess.run([binary, "status", "--json"], capture_output=True, text=True, timeout=8,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if result.returncode:
            raise ValueError(result.stderr.strip() or "Tailscale status failed")
        data = json.loads(result.stdout)
        return {"connected": data.get("BackendState") == "Running", "message": data.get("BackendState", "Unknown"),
                "ips": data.get("TailscaleIPs", [])}
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        return {"connected": False, "message": str(error)}


def server_address(value: str) -> str:
    host, separator, port = value.strip().rpartition(":")
    if not separator or not 1 <= int(port) <= 65535:
        raise ValueError("Use a Tailscale IPv4 address and port, for example 100.80.12.34:25565")
    if ipaddress.ip_address(host) not in ipaddress.ip_network("100.64.0.0/10"):
        raise ValueError("Use the host's Tailscale IPv4 address")
    return f"{host}:{int(port)}"


class Launcher:
    def __init__(self, support: Path | None = None):
        self.support = support if support is not None else support_dir()
        self.state = self.support / "herps-launcher"
        self.state.mkdir(parents=True, exist_ok=True)
        self.config_file = self.state / "settings.json"
        self.config = read_json(self.config_file) if self.config_file.exists() else {
            "installation": "", "profile": "default", "profiles": ["default"], "servers": [], "close_on_play": False,
        }
        self.child = None
        self.log_stream = None
        self.session = None
        self.pending_file = self.state / "pending-session.json"
        self.operation_lock = self.state / "operation.lock"
        self.lock_fd = None
        if not self.config["installation"]:
            candidates = [Path("/Applications/Herspers Minecraft.app")]
            if getattr(sys, "frozen", False):
                candidates += [Path(sys.executable).parent / "game/Herspers-Minecraft"]
                if platform.system() == "Darwin":
                    candidates += [Path(sys.executable).parents[3] / "Herspers Minecraft.app"]
            for candidate in candidates:
                if candidate.exists():
                    try:
                        self.config["installation"] = str(Installation.inspect(candidate).root)
                        self.save()
                        break
                    except (OSError, ValueError, KeyError):
                        continue
        if not self.config.get("native_source") and getattr(sys, "frozen", False):
            locations = [Path(sys.executable).parent / "engine-source"]
            if platform.system() == "Darwin":
                locations += [Path(sys.executable).parents[3] / "engine-source"]
            for source in locations:
                if (source / ".herspers-prepared.json").is_file():
                    self.config["native_source"] = str(source)
                    self.save()
                    break

    def save(self):
        json_write(self.config_file, self.config)

    def acquire(self):
        try:
            self.lock_fd = os.open(self.operation_lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.write(self.lock_fd, str(os.getpid()).encode())
        except FileExistsError:
            raise ValueError("Another launcher owns this game. If it crashed, close all game/launcher processes and remove operation.lock in the launcher data folder.")

    def release(self):
        if self.lock_fd is not None:
            os.close(self.lock_fd)
            self.lock_fd = None
            self.operation_lock.unlink(missing_ok=True)

    @property
    def game(self):
        profile = self.config["profile"]
        if not ID.fullmatch(profile):
            raise ValueError("Invalid profile id")
        return self.support / "game" if profile == "default" else self.state / "profiles" / profile

    def add_profile(self, name):
        if not ID.fullmatch(name) or name in self.config["profiles"]:
            raise ValueError("Use a unique profile id: 1–64 lowercase letters, numbers or underscores")
        self.config["profiles"].append(name)
        self.config["profile"] = name
        self.save()

    def installation(self):
        if not self.config["installation"]:
            raise ValueError("Select the Herspers Java installation in Settings")
        return Installation.inspect(Path(self.config["installation"]))

    def mods(self):
        found = []
        for directory, extension in (("horizon-mods", ".hmod"), ("horizon-native-mods", ".hnmod")):
            for path in sorted((self.game / directory).glob("*" + extension)):
                found.append(inspect_mod(path))
        if len({m.id for m in found}) != len(found):
            raise ValueError("Duplicate runtime/native mod ids; remove duplicates before playing")
        return found

    def enabled(self, mod):
        return pairs(self.game / "horizon-mods.txt").get("mod." + mod.id) == "true"

    def set_enabled(self, mod, enabled):
        update_pairs(self.game / "horizon-mods.txt", {"mod." + mod.id: str(bool(enabled)).lower()})

    def install_mod(self, path):
        mod = inspect_mod(path)
        if any(m.id == mod.id for m in self.mods()):
            raise ValueError("This id is already installed. Remove or disable the existing version first")
        destination = self.game / ("horizon-native-mods" if mod.native else "horizon-mods") / (mod.id + path.suffix)
        atomic(destination, path.read_bytes())
        # Explicit enable step lets the player review capabilities first.
        self.set_enabled(mod, False)
        return mod

    def remove_mod(self, mod):
        expected = self.game / ("horizon-native-mods" if mod.native else "horizon-mods")
        if mod.path.parent != expected:
            raise ValueError("Mod is outside this profile")
        destination = self.state / "removed" / (uuid.uuid4().hex + "-" + mod.path.name)
        destination.parent.mkdir(exist_ok=True)
        self.set_enabled(mod, False)
        shutil.move(str(mod.path), destination)

    def install_shader(self, path):
        if path.suffix not in (".zip", ".hshader"):
            raise ValueError("Choose a .zip shader pack or .hshader")
        files = archive(path, 256 << 20)
        if not ("horizon-shaders.toml" in files or any(n.startswith("shaders/") for n in files)):
            raise ValueError("No supported shader pack structure found")
        destination = self.game / "shaderpacks" / safe_name(path.name)
        if destination.exists():
            raise ValueError("A pack with this name already exists")
        atomic(destination, path.read_bytes())

    def select_shader(self, name):
        if name and not (self.game / "shaderpacks" / safe_name(name)).is_file():
            raise ValueError("Shader pack is missing")
        update_pairs(self.game / "horizon-graphics.txt", {"pickedShaderPack": name})

    def build_key(self, mods):
        return hashlib.sha256(json.dumps({"revision": REVISION, "target": target(), "engine": self.installation().metadata.get("engine_source"),
            "mods": [(m.id, digest(m.path)) for m in mods]}, sort_keys=True).encode()).hexdigest()

    def native_binary(self):
        mods = [m for m in self.mods() if m.native and self.enabled(m)]
        if not mods:
            return None
        build = self.state / "native" / self.build_key(mods)
        receipt = read_json(build / "receipt.json") if (build / "receipt.json").exists() else {}
        binary = build / ("horizon-client.exe" if platform.system() == "Windows" else "horizon-client")
        if not binary.is_file() or receipt.get("sha256") != digest(binary):
            raise ValueError("Native mods need rebuilding. Review and use Rebuild native mods first")
        return binary

    def command(self, server="", name="", clean=False):
        installation = self.installation()
        executable = installation.binary("horizon-client") if clean else self.native_binary() or installation.binary("horizon-client")
        args = [str(executable), "--resources", str(self.support / "resources" / GAME), "--game-dir", str(self.game), "--home", str(self.support)]
        if server:
            if not re.fullmatch("[A-Za-z0-9_]{3,16}", name):
                raise ValueError("Private multiplayer needs a player name of 3–16 letters, digits or underscores")
            args += ["--server", server_address(server), "--name", name]
        return args

    def launch(self, server="", name="", clean=False):
        if self.child and self.child.poll() is None:
            raise ValueError("The game is already running")
        self.acquire()
        try:
            installation = self.installation()
            self.game.mkdir(parents=True, exist_ok=True)
            log_path = self.state / "logs" / (time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8] + ".log")
            log_path.parent.mkdir(exist_ok=True)
            check = subprocess.run([str(installation.binary("horizon-prepare")), "--check", "--root", str(installation.assets / "preparation"),
                                    "--output", str(self.support / "resources" / GAME)], capture_output=True, timeout=120)
            atomic(self.state / "resources-check.log", check.stdout + check.stderr)
            if check.returncode:
                raise ValueError("Game resource validation failed. Use the installation's Setup.cmd / prepare.command with JDK 25 and your own matching game files. See resources-check.log")
            if server and not tailscale()["connected"]:
                raise ValueError("Connect Tailscale before joining a private server")
            args = self.command(server, name, clean)
            env = os.environ.copy()
            env.update(HORIZON_HOME=str(self.support), HORIZON_LAUNCHER_NO_SELF_UPDATE="1")
            # The game's persisted shader choice must win over developer overrides.
            env.pop("HORIZON_SHADER_PACK", None)
            env.pop("HORIZON_GRAPHICS_API", None)
            if clean:
                # Clean play gets an isolated game folder; no user mods/settings/saves are changed.
                clean_game = self.state / "clean-game"
                clean_game.mkdir(exist_ok=True)
                args[args.index("--game-dir") + 1] = str(clean_game)
            else:
                clean_game = self.game
            self.log_stream = log_path.open("wb")
            self.session = {"started": time.time(), "profile": self.config["profile"], "log": str(log_path), "clean": clean}
            json_write(self.pending_file, self.session)
            self.child = subprocess.Popen(args, cwd=clean_game, env=env, stdout=self.log_stream, stderr=subprocess.STDOUT,
                                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            self.session["pid"] = self.child.pid
            json_write(self.pending_file, self.session)
        except Exception:
            if self.log_stream:
                self.log_stream.close()
            self.release()
            self.pending_file.unlink(missing_ok=True)
            raise

    def poll(self):
        if not self.child or self.child.poll() is None:
            return None
        code = self.child.returncode
        self.log_stream.close()
        self.session.update(exit_code=code, finished=time.time())
        history = self.state / "activity.json"
        records = read_json(history) if history.exists() else []
        json_write(history, ([self.session] + records)[:30])
        self.pending_file.unlink(missing_ok=True)
        self.child = None
        self.release()
        return code

    def save_graphics(self, width, height, distance, backend):
        if not 640 <= width <= 7680 or not 480 <= height <= 4320 or not 2 <= distance <= 128:
            raise ValueError("Resolution or render distance is out of range")
        allowed = ("auto",) if platform.system() == "Darwin" else ("auto", "vulkan", "dx12", "opengl")
        if backend not in allowed:
            raise ValueError("Unsupported graphics backend on this platform; macOS auto selects Metal")
        update_pairs(self.game / "options.txt", {"overrideWidth": str(width), "overrideHeight": str(height), "renderDistance": str(distance)})
        update_pairs(self.game / "horizon-graphics.txt", {"graphicsApi": backend})


def find_cargo(environ=None, home=None) -> Path:
    """Finder's PATH commonly omits rustup's per-user bin directory."""
    environ = os.environ if environ is None else environ
    home = Path.home() if home is None else home
    filename = "cargo.exe" if platform.system() == "Windows" else "cargo"
    candidates = []
    if environ.get("CARGO_HOME"):
        candidates.append(Path(environ["CARGO_HOME"]) / "bin" / filename)
    candidates.append(home / ".cargo/bin" / filename)
    inherited = shutil.which("cargo", path=environ.get("PATH", ""))
    if inherited:
        candidates.append(Path(inherited))
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            # Keep rustup's cargo symlink name: resolving it changes proxy dispatch.
            return candidate.absolute()
    raise ValueError("Install Rust 1.95.0 using rustup; Windows also needs Visual Studio C++ Build Tools, macOS needs Xcode Command Line Tools")


def stage_native_source(source: Path, work: Path) -> Path:
    """Supply mixins' exact archive revision without changing the verified cache."""
    staged = work / "source"
    shutil.copytree(source, staged)
    atomic(staged / ".horizon-revision", REVISION.encode())
    return staged


def stage_native_mod(mod: Mod, incoming: Path) -> Path:
    """Unpack the bundle's mixin folder directly under the CLI's mods directory."""
    if not mod.native or not ID.fullmatch(mod.id):
        raise ValueError("Native staging requires a valid native mod identity")
    files = archive(mod.path)
    prefix = f"mixins/{mod.id}/"
    source_files = {name: data for name, data in files.items() if name != "horizon-native.json"}
    if (prefix + "horizon-mixin.toml" not in source_files or
            any(not name.startswith(prefix) for name in source_files)):
        raise ValueError("Native source is outside its mod namespace or has no mixin manifest")
    destination = incoming / mod.id
    for name, data in source_files.items():
        atomic(destination / name[len(prefix):], data)
    return destination


def build_native(launcher: Launcher, source: Path, trusted=False, progress=lambda line: None):
    """Apply exact-revision mixins to a verified source copy, keep clean install untouched."""
    if not trusted:
        raise ValueError("Native mods execute unsandboxed code. Review their source and explicitly trust this build")
    mods = [m for m in launcher.mods() if m.native and launcher.enabled(m)]
    if not mods:
        raise ValueError("Enable a native mod before rebuilding")
    revisions = {m.metadata["mixins"] for m in mods}
    if len(revisions) != 1:
        raise ValueError("These mods pin different mixin tools; use a compatible set")
    cargo = find_cargo()
    source = source.resolve(strict=True)
    stamp = read_json(source / ".herspers-prepared.json")
    if stamp.get("upstream", {}).get("commit") != REVISION:
        raise ValueError("Native build source is not the pinned, patched Herspers engine")
    engine = launcher.installation().metadata.get("engine_source", {})
    if stamp.get("tree_sha256") != engine.get("prepared_tree_sha256") or stamp.get("patches_sha256") != engine.get("patches_sha256"):
        raise ValueError("Native source patches do not match the selected installation; use the source shipped with that package")
    # Match prepare_upstream.py's digest, so edited sources cannot masquerade as the clean cache.
    tree_hash = hashlib.sha256()
    for folder, dirs, files in os.walk(source):
        dirs.sort()
        for name in sorted(dirs + files):
            item = Path(folder) / name
            if item.is_symlink():
                raise ValueError("Native build source contains a link")
            if item.is_dir() or item == source / ".herspers-prepared.json":
                continue
            tree_hash.update(item.relative_to(source).as_posix().encode() + b"\0")
            tree_hash.update(b"x" if item.stat().st_mode & 0o111 else b"-")
            tree_hash.update(digest(item).encode() + b"\0")
    if tree_hash.hexdigest() != stamp.get("tree_sha256"):
        raise ValueError("Native source cache has changed; regenerate it with prepare_upstream.py")
    host_target = target()
    key = launcher.build_key(mods)
    build = launcher.state / "native" / key
    build.parent.mkdir(exist_ok=True)
    launcher.acquire()
    try:
        build.mkdir(exist_ok=True)
        (build / "receipt.json").unlink(missing_ok=True)
        # Fresh work output on every attempt; cache target artifacts independently.
        work = Path(tempfile.mkdtemp(prefix="build-", dir=build.parent))
        env = os.environ.copy()
        env.update(HORIZON_VERSION="0.7.6", RUSTUP_TOOLCHAIN=RUST, CARGO_BUILD_JOBS="3", CARGO_TARGET_DIR=str(build.parent / "target"))
        env["PATH"] = str(cargo.parent) + os.pathsep + env.get("PATH", "")
        if platform.system() == "Windows":
            env["RUSTFLAGS"] = "-C target-feature=+crt-static -C link-arg=/STACK:16777216"
        log_path = launcher.state / "native-build.log"
        with log_path.open("w", encoding="utf-8") as log:
            def run(args, cwd=None, extra_env=None):
                progress("Running " + " ".join(map(str, args)))
                with subprocess.Popen(list(map(str, args)), cwd=cwd or work, env={**env, **(extra_env or {})}, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                      text=True, encoding="utf-8", errors="replace", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)) as child:
                    for line in child.stdout:
                        log.write(line)
                        log.flush()
                        progress(line.rstrip())
                    if child.wait():
                        raise ValueError(f"Native build failed; see {log_path}")
            tool_root = launcher.state / "mixins" / next(iter(revisions))
            run([cargo, "+" + RUST, "install", "--locked", "--git", "https://github.com/horizon-rust/horizon-mixins", "--rev", next(iter(revisions)),
                 "--root", tool_root, "horizon-mixins-cli"])
            incoming = work / "mods"
            for mod in mods:
                stage_native_mod(mod, incoming)
            tool = tool_root / "bin" / ("horizon-mixins.exe" if platform.system() == "Windows" else "horizon-mixins")
            stage = work / "engine"
            working_source = stage_native_source(source, work)
            run([tool, "apply", "--workspace", working_source, "--mods", incoming, "--out", stage])
            def locked_packages(path):
                return {(p["name"], p["version"], p["source"], p.get("checksum"))
                        for p in tomllib.loads(path.read_text(encoding="utf-8"))["package"] if "source" in p}
            if not locked_packages(stage / "Cargo.lock") <= locked_packages(source / "Cargo.lock"):
                raise ValueError("Native mod dependencies differ from Horizon's pinned Cargo.lock")
            run([cargo, "+" + RUST, "build", "--locked", "--profile", "fast", "--manifest-path", stage / "Cargo.toml",
                 "--target", host_target, "-p", "horizon-client", "--bin", "horizon-client", "--features", "horizon-client/mods"])
            filename = "horizon-client.exe" if platform.system() == "Windows" else "horizon-client"
            binary = Path(env["CARGO_TARGET_DIR"]) / host_target / "fast" / filename
            build.mkdir(exist_ok=True)
            shutil.copy2(binary, build / filename)
            if (stage / "native-data").exists():
                shutil.copytree(stage / "native-data", build / "native-data", dirs_exist_ok=True)
            post_file = stage / "native-post-build.json"
            for step in read_json(post_file) if post_file.exists() else []:
                if not ID.fullmatch(step["mod"]) or step["mod"] not in {m.id for m in mods}:
                    raise ValueError("Invalid post-build mod identity")
                for key_name in ("package", "bin"):
                    if not re.fullmatch(r"[A-Za-z0-9_-]+", step[key_name]):
                        raise ValueError("Invalid post-build crate/binary name")
                run([cargo, "+" + RUST, "build", "--locked", "--profile", "fast", "--manifest-path", stage / "Cargo.toml",
                     "--target", host_target, "-p", step["package"], "--bin", step["bin"]])
                program = Path(env["CARGO_TARGET_DIR"]) / host_target / "fast" / (step["bin"] + (".exe" if platform.system() == "Windows" else ""))
                data = build / "native-data" / step["mod"]
                cache = launcher.state / "native-cache" / step["mod"]
                data.mkdir(parents=True, exist_ok=True)
                cache.mkdir(parents=True, exist_ok=True)
                run([program, *step.get("args", [])], cwd=build, extra_env={"HORIZON_NATIVE_MOD": step["mod"],
                    "HORIZON_NATIVE_VERSION_DIR": str(build), "HORIZON_NATIVE_DATA_DIR": str(data), "HORIZON_NATIVE_CACHE_DIR": str(cache),
                    "HORIZON_NATIVE_BUNDLE_DATA_DIR": str(stage / "native-data" / step["mod"])})
            json_write(build / "receipt.json", {"target": host_target, "revision": REVISION, "sha256": digest(build / filename)})
            progress("Native build ready. Clean installation preserved.")
    finally:
        launcher.release()
