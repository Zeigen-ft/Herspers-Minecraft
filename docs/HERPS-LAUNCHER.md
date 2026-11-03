# Herps Launcher 0.1.0

Herps Launcher is a shared Python/Qt desktop launcher for **Herspers Minecraft Java 26.3** on Windows 10/11 x64, macOS Apple Silicon, and macOS Intel. Bedrock is separate. It does not require the original Horizon Launcher.

Start with the [step-by-step use and integration guide](HERPS-QUICKSTART.md) for installation, first launch, connecting an existing game, mods, shaders, multiplayer, and source/repository integration.

## Install and play

The `Build Herps Launcher` workflow builds a separate native game and launcher package for each architecture. See [the native validation run](https://github.com/Zeigen-ft/Herspers-Minecraft/actions/runs/41571739445) for each platform's result and downloadable artifacts. The older Herspers game download links in the repository README are separate from these Herps Launcher packages.

Run **41571739445**, built from source commit **2aee3c77a3c03e91a680f3342267c435a392d737**, passed on all three platforms:

| Platform | Download | Verified |
| --- | --- | --- |
| Windows 10/11 x64 | [Installer and portable ZIP](https://github.com/Zeigen-ft/Herspers-Minecraft/actions/runs/41571739445/artifacts/13202422947) | Native build, packaged game discovery/UI, install/start/shortcuts/uninstall, actual native-mod compile and rollback |
| Mac Apple Silicon | [ARM64 DMG](https://github.com/Zeigen-ft/Herspers-Minecraft/actions/runs/41571739445/artifacts/13202148293) | Native build, packaged game discovery/UI, DMG integrity |
| Mac Intel | [x86_64 DMG](https://github.com/Zeigen-ft/Herspers-Minecraft/actions/runs/41571739445/artifacts/13202408890) | Native build, packaged game discovery/UI, DMG integrity |

Download and extract GitHub's outer artifact ZIP first. Windows users can then run the `-Setup.exe`; Mac users can open the enclosed `.dmg`. GitHub may require sign-in to download Actions artifacts.

On Windows, install the Microsoft Visual C++ x64 runtime from https://aka.ms/vc14/vc_redist.x64.exe if missing, then run the generated per-user installer (optional desktop shortcut and Start Menu shortcut), or extract the entire ZIP and run `Herps Launcher/Herps Launcher.exe`. Keep its game and `_internal` directories intact. On macOS, mount the DMG and copy **both** `Herps Launcher.app` and `Herspers Minecraft.app` into Applications. If you want to compile native mods, also retain the included `engine-source` folder and choose it in Settings. Qt 6.8 requires macOS 12 or later.

The launcher discovers the bundled Windows game or `/Applications/Herspers Minecraft.app`; otherwise select the complete Herspers Java package in Settings. Installation validation rejects staged placeholders, wrong source/game versions, changed engine binary checksums, and incompatible platform/architecture. No Minecraft assets are shipped. Use the game's existing `Setup.cmd` (Windows) or `Contents/Resources/prepare.command` (macOS) with **JDK 25 and your own matching game files** before PLAY. Resource validation runs before any game process starts.

The default profile uses the existing `Herspers Minecraft/game` data folder, preserving saves. New named profiles have separate folders under `Herspers Minecraft/herps-launcher/profiles`. A new profile does not copy existing worlds. Clean startup uses another separate folder with no user mods or shader selection. This mode starts clean without altering the default world's saves or settings. Do not run the old launcher concurrently against the same game folder.

PLAY keeps the launcher open, captures output and exit codes, and becomes available again after the game exits. Home shows recent runs. The launcher prevents concurrent operations through a lock file. After a machine crash, first close all game/launcher processes, then remove `herps-launcher/operation.lock` if it remains. A `pending-session.json` preserves the last interrupted run's log path.

## Mods and native builds

Import `.hmod` or `.hnmod` on Mods. Imports start **disabled**. Review the manifest details and enable explicitly. Runtime API lines 0.1/0.2/0.3 are read from `horizon-mod.toml`; code is loaded by Horizon's actual runtime. This format has capabilities and side declarations, but no dependency graph. The game remains responsible for WebAssembly component linking, namespace clashes, and loading errors; inspect game logs. Forge/Fabric JAR mods are unsupported.

Native `.hnmod` bundles must target **7301f6fdd7f470b11317276e7a11b4dc615c137a**, Java **26.3**, and an exact `horizon-mixins` revision. Different mixin-tool revisions in one build are rejected. This intentionally rejects some hooks-only mods tested against other revisions instead of silently changing the engine version. Native sources are **not sandboxed**: build scripts, post-build programs and game code run with your permissions. Review and trust the source before each build.

Native compilation requires Rust **1.95.0**, network access to GitHub/crates.io, and the platform's build tools: Visual Studio C++ Build Tools + Windows SDK on Windows, Xcode Command Line Tools on Mac. Set Prepared native source to the included verified `engine-source`, or run `python tools/prepare_upstream.py` from a development checkout and select the printed folder. The preparer's content digest is checked again before using that source. Rebuild installs the pinned mixins tool, applies it into a separate work directory, checks the staged dependency lock against Horizon's lock, builds with audio/controllers/runtime mods, runs declared post-build tools, and caches the binary by source revision, architecture and enabled mod hashes. Windows retains the 16 MiB stack setting.

The original installation's binaries are never overwritten. Changes to enabled native mods require a matching build before PLAY. Roll back by disabling all native mods; ordinary PLAY then selects the original client. Removed mods are moved into `herps-launcher/removed`, and mod data is retained. Native bundle staging follows the mixins CLI's direct per-mod directory layout, and the source copy receives its exact revision marker without changing the verified source cache. Rust installed under `CARGO_HOME/bin` or `~/.cargo/bin` is discovered even when a Mac app opened from Finder has no Rust directory on PATH.

## Shaders and settings

Import `.zip` or `.hshader`, then select it. The launcher writes the actual upstream setting **`pickedShaderPack` in `horizon-graphics.txt`** and stores packs beside the profile's `options.txt`. This is configuration, not a claim that the shader rendered. Horizon compiles the pack through its own loader and falls back on failure. **Restore default shaders** clears the selection before the next launch. macOS uses Metal; Windows offers the engine's auto/Vulkan/DX12/OpenGL preferences. A shader working on Vulkan has not thereby been verified on Metal.

Settings edit window resolution and render distance while preserving other options, resource packs, and multiplayer settings. First edits save `.herps-backup` files. Restore original graphics settings uses those backups. Install updates by extracting a new complete trusted Herspers package and selecting it; the previous installation remains available for rollback. There is no automatic downloader, ownership bypass, or replacement asset-acquisition path.

## Tailscale multiplayer

Multiplayer displays local Tailscale status, stores favorites, and launches the game with the existing `--server` / `--name` options for private player names. The launcher requires a Tailscale IPv4 in `100.64.0.0/10` and a nonzero port. Connect Tailscale on both machines and grant peer access there. Windows hosting opens the existing Herspers host console. macOS uses a small native helper sharing the **unchanged** `packaging/private_server.rs` implementation and server directory policy. It retains the existing private-server configuration, EULA consent, backups, tailnet-only bind, and console shutdown behavior. Type **stop** in the hosting console to save and shut down. Existing singleplayer worlds are separate from the host's server folder.

## Develop and package

Use the existing checkout in this isolated cloud task; do not create a worktree unless explicitly requested.

```sh
python3 -m venv .local/herps-venv
.local/herps-venv/bin/python -m pip install -r herps_launcher/requirements.txt
.local/herps-venv/bin/python -m herps_launcher
python3 -m unittest discover -s tests -v
QT_QPA_PLATFORM=offscreen .local/herps-venv/bin/python -m unittest discover -s tests -p 'test_herps*.py' -v
```

Use `.local/herps-venv/Scripts/python.exe` on Windows. The implementation uses Qt rather than Tauri: it fits the repository's Python packaging/test tooling and can be functionally exercised offscreen in Linux without Linux WebKit prerequisites. The core, profiles, process lifecycle, imports and build orchestration are shared across platforms; only paths, architecture checks, console launching and packaging differ.

On native Windows/macOS, run the existing engine build script first, then:

```sh
python tools/package_herps.py --game /path/to/complete/Herspers-package --source /path/printed/by/prepare_upstream.py
```

The packaging command builds the native hosting helper, bundles Python/Qt, starts the packaged UI smoke test, and emits a Windows ZIP or macOS DMG. Windows CI also compiles `packaging/herps-windows.iss` with Inno Setup 6 for shortcuts and uninstallation. Native source inclusion is optional. macOS is ad hoc signed by default, **not notarized**. Optional Developer ID signing uses `HERPS_CODESIGN_IDENTITY`; optional notarization uses an already-configured `notarytool` keychain profile named by `HERPS_NOTARY_PROFILE`. No signing credentials are included in this repository or requested by the launcher. Qt's LGPL/commercial terms and bundled license notices continue to apply; Herps source is GPLv3 and the game retains its original notices.

## Verification boundaries

Linux checks cover real owned child processes, failure/exit handling and relaunch, mod import/enable/removal, raw unsafe ZIP names, native manifest pins and staging, source/target fingerprints, shader configuration/reset, save preservation, and actual Qt page navigation. The original 161 engine/preparer library tests and Linux client compile check passed during development.

The linked native workflow runs the full test suite on Windows x64, Mac ARM64 and Mac Intel, then builds their actual game and launcher packages. Packaged UI smoke checks require successful discovery and checksum validation of the bundled game plus all five launcher pages. Windows additionally checks silent installation, both shortcuts, installed-app startup and uninstallation. Mac packages undergo DMG integrity verification.

The Windows native-mod check imports and enables an owned `.hnmod`, uses the pinned mixins tool and real prepared source to compile the game, verifies its injected marker and 16 MiB stack, checks native/original binary selection and rollback, and verifies that the save sentinel, clean installation and source cache remain unchanged. Its proof explicitly leaves hook execution and gameplay unverified. It uses a private copy of the clean target cache. Mac native-mod compilation has not been exercised by this check.

Read the actual job conclusions in the linked workflow before treating a platform as verified. Real shader activation/rendering, prepared-game startup, hook execution, account login and a two-machine Tailscale session still need the user's legitimate game files and suitable hardware/services. These checks do not establish gameplay readiness or notarization.
